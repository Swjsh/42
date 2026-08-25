"""Guards for the V-d1 / V-e3 forward-prereg adjudicator (built 2026-08-25).

WHY THESE EXIST
  1. The adjudicator RE-DERIVES the two shadow rules from entry-quality-ledger fields.
     The frozen single-source implementation lives in entry_quality_ledger cells
     (V-d1-rescore / R-PRES-1m) and is materialised in shadow-tally.jsonl. Two
     implementations of one rule is how replay engines silently disagree (L251), so the
     re-derivation is checked row-for-row and MUST match exactly. This test REDs the
     instant the two drift apart.
  2. V-d1 was KILLED on 2026-08-25 by the prereg's own ladder (F4 pooled within-day
     permutation p=0.666 vs a p<=0.10 bar). A future session must not quietly resurrect
     it. This test pins the verdict to the filed scorecard.
  3. The ladder itself (ARM / EXTEND / KILL precedence) is unit-tested against synthetic
     inputs so a refactor cannot invert an outcome.

These are all report-only surfaces -- nothing here blocks a live entry.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ADJ_PATH = REPO / "setup" / "scripts" / "entry_structure_forward_adjudicate.py"
LEDGER = REPO / "analysis" / "entry-quality" / "entry-quality-ledger.json"
TALLY = REPO / "analysis" / "entry-quality" / "shadow-tally.jsonl"
SCORECARD = REPO / "analysis" / "recommendations" / "entry-structure-forward-2026-08-06.json"
PREREG = REPO / "analysis" / "recommendations" / "entry-structure-forward-prereg-2026-08-06.json"


def _load_adjudicator():
    spec = importlib.util.spec_from_file_location("entry_structure_forward_adjudicate", ADJ_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def adj():
    assert ADJ_PATH.exists(), f"adjudicator missing: {ADJ_PATH}"
    return _load_adjudicator()


# --------------------------------------------------------------- 1. integrity gate
def test_rederived_flags_match_the_frozen_implementation(adj):
    """The whole verdict rests on this. If it REDs, the scorecard is void, not stale."""
    events = json.loads(LEDGER.read_text(encoding="utf-8"))["events"]
    tally = [json.loads(l) for l in TALLY.read_text(encoding="utf-8").splitlines() if l.strip()]

    result = adj.validate_against_frozen(events, tally)

    assert result["matched"] > 0, "no tally row joined the ledger -- silent-zero, not a pass"
    assert result["missing_from_ledger"] == 0, (
        f"{result['missing_from_ledger']} tally rows have no ledger event; "
        "the two producers have diverged")
    assert result["mismatches"]["V-d1"] == 0, (
        "re-derived V-d1 disagrees with the frozen implementation on "
        f"{result['mismatches']['V-d1']} rows -- two implementations of one rule (L251)")
    assert result["mismatches"]["V-e3"] == 0, (
        "re-derived V-e3 disagrees with the frozen implementation on "
        f"{result['mismatches']['V-e3']} rows -- two implementations of one rule (L251)")
    assert result["ok"] is True


# --------------------------------------------------------------- 2. rule semantics
@pytest.mark.parametrize(
    "opt_side,last5_dir,expected",
    [
        ("C", "down", True),    # long, last closed 5m closed down -> against -> block
        ("C", "flat", True),    # close == open satisfies "close <= open" for a long
        ("C", "up", False),
        ("P", "up", True),      # short, last closed 5m closed up -> against -> block
        ("P", "flat", True),    # close == open satisfies "close >= open" for a short
        ("P", "down", False),
        ("C", None, None),      # unknown bar -> cannot judge
        (None, "down", None),
    ],
)
def test_vd1_matches_the_prereg_wording(adj, opt_side, last5_dir, expected):
    assert adj.vd1({"opt_side": opt_side, "d_last5_dir": last5_dir}) is expected


@pytest.mark.parametrize(
    "n_closed_1m,s1_kind,expected",
    [
        (25, None, True),       # quorum reached, no BOS and no CHoCH -> structure ABSENT -> block
        (25, "BOS", False),
        (25, "CHoCH", False),
        (19, None, None),       # below the 20-bar quorum -> abstain, never block
        (0, None, None),
        (None, None, None),
    ],
)
def test_ve3_abstains_below_quorum(adj, n_closed_1m, s1_kind, expected):
    assert adj.ve3({"n_closed_1m": n_closed_1m, "s1_kind": s1_kind}) is expected


# --------------------------------------------------------------- 3. ladder precedence
def _fwd(n_blocked=20, delta=100.0, win=10.0, los=110.0):
    return {"n_blocked": n_blocked, "delta_usd": delta,
            "blocked_winner_usd": win, "blocked_loser_usd": los}


def _reg(best=0.0, worst=0.0):
    return {"best_session_rule_delta_usd": best, "worst_session_rule_delta_usd": worst}


def test_ladder_extend_wins_when_too_few_blocks(adj):
    """F3 is evaluated FIRST -- too few blocks means judge nothing, even if F4 fails."""
    out = adj.adjudicate("X", _fwd(n_blocked=4), {"p_value": 0.99}, _reg())
    assert out["verdict"] == "EXTEND"


def test_ladder_kills_on_pooled_f4_failure(adj):
    """The exact shape that killed V-d1: F1/F2/F3/F5 pass, F4 fails on pooled."""
    out = adj.adjudicate("X", _fwd(), {"p_value": 0.6661}, _reg())
    assert out["verdict"] == "KILL"
    assert "F4" in out["verdict_basis"]


def test_ladder_kills_on_winner_killer(adj):
    out = adj.adjudicate("X", _fwd(win=500.0, los=10.0), {"p_value": 0.01}, _reg())
    assert out["verdict"] == "KILL"
    assert "F2" in out["verdict_basis"]


def test_ladder_kills_on_negative_direction(adj):
    out = adj.adjudicate("X", _fwd(delta=-1.0), {"p_value": 0.01}, _reg())
    assert out["verdict"] == "KILL"
    assert "F1" in out["verdict_basis"]


def test_ladder_arms_only_when_all_five_pass(adj):
    out = adj.adjudicate("X", _fwd(), {"p_value": 0.01}, _reg())
    assert out["verdict"] == "ARM"
    assert all(out["gates"].values())


# --------------------------------------------------------------- 4. reproducibility
def test_permutation_is_deterministic(adj):
    """A verdict that moves between runs is not a verdict. Same seed -> same p."""
    events = json.loads(LEDGER.read_text(encoding="utf-8"))["events"]
    a = adj.within_day_permutation(events, adj.vd1, draws=2000)
    b = adj.within_day_permutation(events, adj.vd1, draws=2000)
    assert a["p_value"] == b["p_value"]
    assert a["observed_delta_usd"] == b["observed_delta_usd"]


# --------------------------------------------------------------- 5. the verdict stands
def test_vd1_stays_killed(adj):
    """V-d1 was killed 2026-08-25 on the prereg's own ladder. If a future session wants
    to resurrect it, that session must write a NEW pre-registration -- not edit this."""
    assert SCORECARD.exists(), "the adjudication scorecard was never filed"
    card = json.loads(SCORECARD.read_text(encoding="utf-8"))
    vd1 = card["results"]["V-d1"]
    assert vd1["verdict"] == "KILL"
    assert vd1["F4_within_day_permutation_pooled"]["p_value"] > adj.F4_P_BAR
    assert card["integrity_gate"]["ok"] is True


def test_scorecard_discloses_the_population_mismatch(adj):
    """The prereg quotes n=230 in-sample; the rebuilt ledger differs. Disclosure is not
    optional -- an undisclosed population swap is how a pooled test lies."""
    card = json.loads(SCORECARD.read_text(encoding="utf-8"))
    assert "DISCLOSURE_in_sample_n_vs_prereg" in card["population"]
    assert card["population"]["in_sample_days"] == 25, (
        "the prereg's in-sample window is 25 days; a different day count means the "
        "pooled population is not the one the prereg froze")


def test_prereg_ladder_still_says_what_the_adjudicator_implements(adj):
    """Pin the adjudicator to the FROZEN prereg thresholds, not to remembered ones."""
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    gates = prereg["forward_gates"]
    assert "p <= 0.10" in gates["F4_discrimination"] or "0.10" in gates["F4_discrimination"]
    assert "n_blocked >= 8" in gates["F3_frequency"]
    assert adj.F4_P_BAR == 0.10
    assert adj.F3_MIN_BLOCKS == 8
    assert adj.FORWARD_FIRST_DATE == "2026-08-06"
