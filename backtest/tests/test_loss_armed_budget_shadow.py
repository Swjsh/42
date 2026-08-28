"""Guard: loss-armed session premium budget SHADOW CLOCK (2026-08-28).

Mirrors the five conventions `test_day_throttle_shadow.py` pins for its sibling,
plus the two that are specific to a BUDGET (rather than a hard stop):

  1. PREREG SYNC      -- the frozen constants in the script must equal the frozen
                         JSON. Silent threshold drift voids the window, and prose
                         has already failed as a control in this repo.
  2. NO LOOK-AHEAD    -- the realized P&L that arms the budget may include ONLY
                         trades already EXITED at the candidate entry's timestamp.
                         A still-open loser must NOT arm it.
  3. ABSTAIN, NEVER GUESS -- an unreadable premium yields None, never False.
                         Folding an abstention into "not blocked" would quietly
                         inflate n_kept and understate the rule.
  4. SHADOW ONLY      -- the live gate must stay inert. This test asserts the
                         params key is absent from every live params file, so the
                         shadow study and the live engine cannot silently diverge.
  5. FORWARD IS THE ONLY ADJUDICATOR -- in-sample must be reported under a key
                         that cannot be mistaken for evidence.
  6. BUDGET ARMS ONLY WHEN RED -- a green or flat session is never constrained
                         (this is the anchor-preserving property; a flat cap
                         regressed the 5 best days -32.3%).
  7. BUDGET ACCUMULATES ONLY ON TAKEN ENTRIES -- a blocked entry must not consume
                         budget, or one oversized reject would lock out the rest
                         of the session.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import loss_armed_budget_shadow as mod  # noqa: E402


# ---------------------------------------------------------------------------
# 1. PREREG SYNC
# ---------------------------------------------------------------------------
def test_prereg_file_exists():
    assert mod.PREREG.exists(), (
        "the frozen pre-registration is missing -- the builder refuses to emit "
        "numbers without it, and so should this suite"
    )


def test_candidate_caps_match_the_frozen_prereg():
    spec = json.loads(mod.PREREG.read_text(encoding="utf-8"))
    frozen_ids = {c["id"] for c in spec["candidates"]}
    frozen_pcts = {c["id"]: c["pct_of_start_of_day_equity"] for c in spec["candidates"]}
    assert mod.CANDIDATES == frozen_pcts, (
        f"pct drift: script {mod.CANDIDATES} vs prereg {frozen_pcts}")
    assert set(mod.CANDIDATES) == frozen_ids, (
        f"candidate drift: script has {sorted(mod.CANDIDATES)}, prereg froze "
        f"{sorted(frozen_ids)} -- changing either VOIDS the window"
    )
    # the pct must be recoverable from the id, so a typo cannot pass silently
    for cid, pct in mod.CANDIDATES.items():
        assert int(cid.split("-")[1]) / 100.0 == pct, f"{cid} does not encode pct {pct}"
        assert 0 < pct <= 1, f"{cid}={pct} is not a fraction -- 12 vs 0.12 foot-gun"


def test_forward_window_matches_the_frozen_prereg():
    spec = json.loads(mod.PREREG.read_text(encoding="utf-8"))
    assert mod.FORWARD_FIRST_DATE == spec["forward_window"]["first_date"]
    assert mod.SESSIONS_REQUIRED == spec["forward_window"]["sessions_required"]


def test_prereg_discloses_the_in_sample_threshold_provenance():
    """The 8-16% BAND was read off an in-sample sweep. If that disclosure is ever
    deleted the study starts reading as pre-registered when it is not."""
    spec = json.loads(mod.PREREG.read_text(encoding="utf-8"))
    disc = spec["HONESTY_DISCLOSURE_THIS_IS_THE_LOAD_BEARING_CAVEAT"]
    assert "IN-SAMPLE" in disc["threshold_provenance"].upper()
    assert "F5" in json.dumps(spec["f_gates"]) or "band" in json.dumps(spec["f_gates"]).lower()


# ---------------------------------------------------------------------------
# 2 + 6 + 7. the replay semantics
# ---------------------------------------------------------------------------
def _entry(date, arm, sec, cost, pnl, xsec, contract=None, sod_equity=5000.0):
    return {
        "sod_equity": sod_equity,
        "date": date,
        "arm": arm,
        "sec": sec,
        "contract": contract or f"C{sec}",
        "side": "C",
        "setup": "TEST",
        "quality": "ELITE",
        "pnl": pnl,
        "cost": cost,
        "cost_readable": True,
        "xsec": xsec,
    }


def test_open_loser_does_not_arm_the_budget():
    """NO LOOK-AHEAD. Entry 1 is down but has NOT exited when entry 2 is placed,
    so entry 2 must be unconstrained even though entry 1 eventually loses."""
    rows = mod.evaluate(
        [
            _entry("2026-09-01", "safe-2", 1000, 600.0, -500.0, xsec=9999),  # exits LATE
            _entry("2026-09-01", "safe-2", 2000, 600.0, +100.0, xsec=3000),
        ]
    )
    second = [r for r in rows if r["time_entry_s"] == 2000][0]
    assert second["realized_before_entry"] == 0.0
    assert second["armed"] is False
    assert second["would_block_P-08"] is False


def test_closed_loser_does_arm_the_budget():
    rows = mod.evaluate(
        [
            _entry("2026-09-01", "safe-2", 1000, 600.0, -500.0, xsec=1500),  # exits BEFORE
            _entry("2026-09-01", "safe-2", 2000, 600.0, +100.0, xsec=3000),
        ]
    )
    second = [r for r in rows if r["time_entry_s"] == 2000][0]
    assert second["realized_before_entry"] == -500.0
    assert second["armed"] is True
    # 600 already spent + 600 > 400 cap (8% of $5k) -> blocked
    assert second["would_block_P-08"] is True


def test_green_session_is_never_constrained():
    """The anchor-preserving property. Ten entries, all winners, far past every cap."""
    ents = [
        _entry("2026-09-01", "safe-2", 1000 + i * 100, 900.0, +300.0, xsec=1050 + i * 100)
        for i in range(10)
    ]
    rows = mod.evaluate(ents)
    for r in rows:
        assert r["armed"] is False, r
        for cid in mod.CANDIDATES:
            assert r[f"would_block_{cid}"] is False, (cid, r)


def test_blocked_entry_does_not_consume_budget():
    """A rejected oversized entry must not lock out a later affordable one."""
    rows = mod.evaluate(
        [
            _entry("2026-09-01", "safe-2", 1000, 100.0, -50.0, xsec=1100),   # arms it
            _entry("2026-09-01", "safe-2", 2000, 5000.0, -10.0, xsec=2100),  # way over cap
            _entry("2026-09-01", "safe-2", 3000, 100.0, +10.0, xsec=3100),   # small, affordable
        ]
    )
    big = [r for r in rows if r["time_entry_s"] == 2000][0]
    small = [r for r in rows if r["time_entry_s"] == 3000][0]
    assert big["would_block_P-08"] is True
    assert small["would_block_P-08"] is False, (
        "the blocked oversized entry consumed budget it never spent"
    )


def test_budget_is_per_arm_and_per_day():
    """Two arms on the same day, and the same arm across days, must not share."""
    rows = mod.evaluate(
        [
            _entry("2026-09-01", "safe-2", 1000, 100.0, -50.0, xsec=1100),
            _entry("2026-09-01", "safe-2", 2000, 600.0, -10.0, xsec=2100),
            _entry("2026-09-01", "risky-1", 1000, 100.0, -50.0, xsec=1100),
            _entry("2026-09-01", "risky-1", 2000, 600.0, -10.0, xsec=2100),
            _entry("2026-09-02", "safe-2", 2000, 600.0, -10.0, xsec=2100),
        ]
    )
    blocked = {(r["date"], r["arm"], r["time_entry_s"]): r["would_block_P-08"] for r in rows}
    assert blocked[("2026-09-01", "safe-2", 2000)] is True
    assert blocked[("2026-09-01", "risky-1", 2000)] is True   # own budget, own arming
    assert blocked[("2026-09-02", "safe-2", 2000)] is False   # fresh day, session flat


# ---------------------------------------------------------------------------
# 3. ABSTAIN
# ---------------------------------------------------------------------------
def test_unreadable_premium_abstains_rather_than_defaulting_to_not_blocked():
    e = _entry("2026-09-01", "safe-2", 2000, 0.0, -10.0, xsec=2100)
    e["cost_readable"] = False
    rows = mod.evaluate([_entry("2026-09-01", "safe-2", 1000, 100.0, -50.0, xsec=1100), e])
    bad = [r for r in rows if r["time_entry_s"] == 2000][0]
    assert bad["premium_paid"] is None
    for cid in mod.CANDIDATES:
        assert bad[f"would_block_{cid}"] is None, (
            f"{cid} guessed instead of abstaining on an unreadable premium"
        )


def test_abstentions_are_counted_separately_and_not_as_kept():
    e = _entry("2026-09-01", "safe-2", 2000, 0.0, -10.0, xsec=2100)
    e["cost_readable"] = False
    rows = mod.evaluate([e])
    s = mod.score(rows)
    assert s["P-08"]["n_abstain"] == 1
    assert s["P-08"]["n_kept"] == 0


# ---------------------------------------------------------------------------
# 4. SHADOW ONLY -- the live gate must stay inert
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "params_path",
    ["automation/state/params.json", "automation/state/aggressive/params.json"],
)
def test_live_gate_is_still_inert(params_path):
    p = REPO / params_path
    if not p.exists():
        pytest.skip(f"{params_path} absent")
    params = json.loads(p.read_text(encoding="utf-8"))
    assert "daily_premium_budget_dollars" not in params, (
        f"{params_path} has ARMED the budget while the forward window is still "
        "running -- the shadow study and the live engine have diverged. Either "
        "close the window and say so, or unset the key."
    )


def test_prereg_declares_shadow_only():
    spec = json.loads(mod.PREREG.read_text(encoding="utf-8"))
    assert "MEASUREMENT ONLY" in spec["shadow_only"]


# ---------------------------------------------------------------------------
# 5. FORWARD IS THE ONLY ADJUDICATOR
# ---------------------------------------------------------------------------
def test_in_sample_is_labelled_so_it_cannot_be_mistaken_for_evidence():
    rows = mod.evaluate(
        [_entry("2026-08-01", "safe-2", 1000, 100.0, -50.0, xsec=1100)]
    )
    s_all = mod.score(rows, since=None)
    s_fwd = mod.score(rows, since=mod.FORWARD_FIRST_DATE)
    assert s_all["P-08"]["n_kept"] + s_all["P-08"]["n_blocked"] == 1
    assert s_fwd["P-08"]["n_kept"] + s_fwd["P-08"]["n_blocked"] == 0, (
        "a pre-freeze row leaked into the forward window"
    )


def test_summary_keys_name_the_in_sample_block_explicitly():
    """The summary's in-sample key must carry its own warning in the key name."""
    src = (REPO / "setup/scripts/loss_armed_budget_shadow.py").read_text(encoding="utf-8")
    assert '"in_sample_NOT_EVIDENCE"' in src


# ---------------------------------------------------------------------------
# F5 band coherence -- the gate that tests the in-sample-argmax disclosure
# ---------------------------------------------------------------------------
def test_f5_band_coherence_is_computed_and_fails_when_only_one_cap_works():
    """Synthetic: make P-08 block a big winner (negative delta). F5 must go False."""
    rows = mod.evaluate(
        [
            _entry("2026-09-01", "safe-2", 1000, 100.0, -50.0, xsec=1100),
            _entry("2026-09-01", "safe-2", 2000, 600.0, +900.0, xsec=2100),
        ]
    )
    s = mod.score(rows)
    assert s["P-08"]["delta_usd"] < 0          # blocked a winner
    assert s["F5_band_coherence"]["all_three_caps_F1_positive"] is False


def test_h_tier_is_observation_only():
    rows = mod.evaluate([_entry("2026-09-01", "safe-2", 1000, 100.0, -50.0, xsec=1100)])
    s = mod.score(rows)
    assert "_observation_only" in s["H-TIER"]


# ---------------------------------------------------------------------------
# reuse, not re-inline (L184)
# ---------------------------------------------------------------------------
def test_reuses_the_sibling_helpers_rather_than_copying_them():
    src = (REPO / "setup/scripts/loss_armed_budget_shadow.py").read_text(encoding="utf-8")
    assert "from day_throttle_shadow import" in src
    for helper in ("def realized_before", "def _secs", "def _num"):
        assert helper not in src, (
            f"{helper} was re-inlined instead of imported from day_throttle_shadow "
            "-- L184, reuse the ONE implementation"
        )


# ---------------------------------------------------------------------------
# EQUITY-AWARENESS (J 2026-08-28) -- the budget is a PERCENT, so the denominator
# is now a second thing that can be missing, and a second thing to never guess.
# ---------------------------------------------------------------------------
def test_missing_start_of_day_equity_abstains():
    """No equity = no denominator = no verdict. Must NOT fall back to a dollar
    default, and must NOT quietly count as 'not blocked'."""
    e = _entry("2026-09-01", "safe-2", 2000, 600.0, -10.0, xsec=2100, sod_equity=None)
    rows = mod.evaluate(
        [_entry("2026-09-01", "safe-2", 1000, 100.0, -50.0, xsec=1100), e]
    )
    bad = [r for r in rows if r["time_entry_s"] == 2000][0]
    for cid in mod.CANDIDATES:
        assert bad[f"would_block_{cid}"] is None, f"{cid} guessed a denominator"


def test_budget_scales_with_the_account():
    """THE POINT OF THE PERCENT FORM: identical spend and identical entry, but a
    bigger account -> the cap grows and the entry survives."""
    def blocked_at(equity):
        rows = mod.evaluate([
            _entry("2026-09-01", "safe-2", 1000, 100.0, -50.0, xsec=1100, sod_equity=equity),
            _entry("2026-09-01", "safe-2", 2000, 600.0, -10.0, xsec=2100, sod_equity=equity),
        ])
        return [r for r in rows if r["time_entry_s"] == 2000][0]["would_block_P-12"]

    # 12% of $5,000 = $600; 100 spent + 600 = 700 > 600 -> blocked
    assert blocked_at(5000.0) is True
    # 12% of $20,000 = $2,400 -> same order sails through
    assert blocked_at(20000.0) is False
