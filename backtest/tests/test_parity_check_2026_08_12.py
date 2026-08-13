"""Guard: the live/backtest parity instrument (2026-08-12).

WHY IT EXISTS. J: "we've surfaced things that should have been found." The free-model veto killed
132 of 656 live ENTER verdicts (20.1%) across 38 days while NO backtest modelled it -- so every
backtest number described an engine that took trades production silently refused. Nothing in the
repo flagged it; a human found it by asking a question at midnight. parity_check.py is the standing
answer: any action the LIVE engine emits that nobody has classified turns it RED.

TWO DESIGN DECISIONS THAT MUST NOT ROT, both learned the hard way in this same session:

1. GROUND TRUTH IS THE LEDGER, NOT THE SOURCE. heartbeat_core assigns rec["action"] from a string
   literal in only 7 places, but also dynamically from the engine verdict (`rec["action"] = v`) and
   from the executor (`rec["exec"].get("status")`). A source-only scan sees 7 of the 20+ actions
   actually emitted -- it would have missed SKIP_STRUCTURE_VETO, every RISK_DENY_*, and NOT_FLAT.
   Same class as the bg_status bug found hours earlier: scanning the convenient surface instead of
   the real one.

2. CONFIRMED AND UNKNOWN ARE REPORTED SEPARATELY. The first version summed divergence +
   unclassified into one "97.97% unmodelled" headline. Defensible, and badly misleading -- most
   unclassified rows turned out to be gates.py verdicts that ARE modelled; the true measured figure
   was 16%. Blending a measured number with an unmeasured one into a single scary total is the
   overclaim this repo keeps having to retract.

Also pinned: severity is a share of ACTIONABLE (non-HOLD) ticks. ~91% of ticks are HOLD, so using
all ticks as the denominator makes every divergence look negligible -- SKIP_STRUCTURE_VETO is 0.4%
of ticks but 5.3% of decisions, and only the second number is a decision-relevant quantity.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import parity_check as pc  # noqa: E402

REGISTRY_PATH = REPO / "automation" / "state" / "parity-registry.json"


# --------------------------------------------------------------------- classification core


def test_an_unregistered_live_action_turns_it_RED():
    """THE WHOLE POINT. A new live refusal nobody classified is the alarm -- that is the state
    VETOED_BY_MODELS sat in for 38 days while every backtest silently overstated trade count."""
    counts = Counter({"HOLD": 900, "SKIP_SOMETHING_BRAND_NEW": 100})
    res = pc.evaluate(counts, 1000, {})
    assert res["verdict"] == "RED"
    assert res["n_unclassified"] == 1


def test_fully_classified_with_a_known_divergence_is_AMBER_not_RED():
    """A known, documented divergence is a managed risk, not an unknown one. Conflating the two
    would make the instrument cry wolf and get ignored."""
    counts = Counter({"HOLD": 900, "SKIP_STRUCTURE_VETO": 100})
    reg = {"SKIP_STRUCTURE_VETO": {"status": "LIVE_ONLY_DIVERGENCE", "reason": "x"}}
    res = pc.evaluate(counts, 1000, reg)
    assert res["verdict"] == "AMBER"
    assert res["n_unclassified"] == 0


def test_all_modeled_is_GREEN():
    counts = Counter({"HOLD": 900, "SKIP_DOJI_ENTRY_BAR": 100})
    reg = {"SKIP_DOJI_ENTRY_BAR": {"status": "MODELED", "reason": "gates.py"}}
    assert pc.evaluate(counts, 1000, reg)["verdict"] == "GREEN"


def test_a_bogus_status_string_is_treated_as_UNCLASSIFIED():
    """Typo-ing a status must not silently buy a green light."""
    counts = Counter({"HOLD": 900, "SKIP_X": 100})
    res = pc.evaluate(counts, 1000, {"SKIP_X": {"status": "modelled"}})  # wrong spelling/case
    assert res["n_unclassified"] == 1
    assert res["verdict"] == "RED"


# --------------------------------------------------------------------- honest arithmetic


def test_confirmed_and_unknown_are_never_blended():
    """Regression on my own first cut, which reported one '97.97% unmodelled' number by summing a
    MEASURED 16% with an UNMEASURED 82%."""
    counts = Counter({"HOLD": 800, "KNOWN_DIV": 100, "MYSTERY": 100})
    res = pc.evaluate(counts, 1000, {"KNOWN_DIV": {"status": "LIVE_ONLY_DIVERGENCE"}})
    assert res["confirmed_unmodelled_pct"] == 50.0
    assert res["unknown_pct"] == 50.0
    assert "unmodelled_pct_of_actionable" not in res, (
        "the blended headline came back -- confirmed and unknown are different epistemic states")


def test_denominator_excludes_HOLD():
    """Using all ticks makes every divergence look negligible: SKIP_STRUCTURE_VETO is 0.4% of ticks
    but 5.3% of actual decisions."""
    counts = Counter({"HOLD": 9000, "SKIP_X": 1000})
    res = pc.evaluate(counts, 10000, {"SKIP_X": {"status": "LIVE_ONLY_DIVERGENCE"}})
    assert res["actionable_ticks"] == 1000
    assert res["confirmed_unmodelled_pct"] == 100.0


def test_outcomes_are_not_counted_as_refusals():
    """HOLD/PLACED/PERCEPTION_ONLY are outcomes. Demanding the backtest 'model' them would
    permanently pin the check RED for no reason."""
    counts = Counter({"HOLD": 500, "PLACED": 300, "PERCEPTION_ONLY": 200})
    res = pc.evaluate(counts, 1000, {})
    assert res["rows"] == []
    assert res["verdict"] == "GREEN"


def test_strict_mode_exit_code(capsys):
    rc = pc.main(["--strict"])
    out = capsys.readouterr().out
    assert rc in (0, 1)
    if "UNCLASSIFIED" in out:
        assert rc == 1, "--strict must fail the build while live actions remain unclassified"


# --------------------------------------------------------------------- the registry itself


def test_registry_is_valid_json_with_the_expected_shape():
    d = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(d.get("actions"), dict) and d["actions"]


def test_every_registry_entry_carries_a_reason():
    """A classification without a stated reason is an assertion, and assertions are what put us
    here. MODELED especially must cite the backtest-side code path."""
    actions = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["actions"]
    for name, entry in actions.items():
        assert entry.get("status") in pc.VALID_STATUS, f"{name} has invalid status"
        assert len(entry.get("reason", "")) > 40, f"{name} has no substantive reason"


def test_the_free_model_veto_stays_recorded_as_a_divergence():
    """The founding case. If this entry is ever softened to MODELED, the lesson is lost: every
    pre-2026-08-12 backtest verdict carries this bias whether or not the veto is now off."""
    actions = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["actions"]
    assert actions["VETOED_BY_MODELS"]["status"] == "LIVE_ONLY_DIVERGENCE"


def test_the_engine_cli_blind_spot_is_recorded_as_a_class():
    """SKIP_STRUCTURE_VETO / SKIP_QUALITY_LOCK / SKIP_BAD_INPUT share one root cause: they live in
    engine_cli.decide_payload, which orchestrator never calls. Recording them as three unrelated
    one-offs would invite a fourth."""
    d = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    for name in ("SKIP_STRUCTURE_VETO", "SKIP_QUALITY_LOCK", "SKIP_BAD_INPUT"):
        assert d["actions"][name]["status"] == "LIVE_ONLY_DIVERGENCE"
    assert "_engine_cli_blind_spot" in d, "the shared root cause is no longer documented as a class"


def test_orchestrator_still_does_not_call_decide_payload():
    """The mechanism behind the blind spot. If a future change routes backtests through
    decide_payload, this goes RED -- and that is a GOOD failure: it means the three divergences
    above may now be modelled and their registry entries need re-evaluating, not deleting."""
    src = (REPO / "backtest" / "lib" / "orchestrator.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
    assert "decide_payload" not in code, (
        "orchestrator now references decide_payload -- re-evaluate SKIP_STRUCTURE_VETO, "
        "SKIP_QUALITY_LOCK and SKIP_BAD_INPUT; they may finally be modellable")


# --------------------------------------------------------------------- robustness


def test_missing_ledger_fails_open(monkeypatch, tmp_path):
    monkeypatch.setattr(pc, "LEDGER", tmp_path / "nope.jsonl")
    counts, total = pc._harvest_live_actions(pc.LEDGER)
    assert (counts, total) == (Counter(), 0)
    assert pc.main([]) == 0


def test_corrupt_registry_fails_open_to_UNCLASSIFIED(monkeypatch, tmp_path):
    """A broken registry must not read as 'everything is fine'."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert pc._load_registry(bad) == {}


def test_malformed_ledger_lines_are_skipped_not_fatal(tmp_path):
    f = tmp_path / "l.jsonl"
    f.write_text('{"action":"HOLD"}\nnot json\n\n{"action":"SKIP_X"}\n', encoding="utf-8")
    counts, total = pc._harvest_live_actions(f)
    assert total == 2 and counts["SKIP_X"] == 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
