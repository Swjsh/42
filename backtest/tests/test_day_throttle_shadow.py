"""Guard suite for setup/scripts/day_throttle_shadow.py -- the forward counter that
adjudicates day-throttle-forward-prereg-2026-08-18.

This counter's ONLY job is to be honest about a counterfactual. The failure that would
matter is silent: a leak that lets the throttle see a loss it could not have known about
turns every forward number into an oracle, and an oracle always clears its own gates. These
guards exist so that failure is loud.

  1. NO LOOK-AHEAD. `realized_before` may sum ONLY trades whose exit is at or before the
     candidate entry. Still-open and later-exiting trades contribute nothing.
  2. NOT-YET-KNOWABLE IS A THIRD STATE. `first_wave_was_red` returns None -- never False --
     while wave 1 is open or is itself the entry being judged. Folding None into False is
     how an "after a red first wave" cohort quietly acquires trades from inside wave 1.
  3. ABSTAIN, NEVER GUESS. With no start-of-day equity there is no percent to compare
     against; the row must abstain, not default to "not blocked".
  4. THE FROZEN CELLS ARE FROZEN. The pre-reg's no_peeking_rule makes the thresholds and
     the window length part of the contract. Drift here voids the window silently.
  5. THE FORWARD BLOCK IS THE ONLY ADJUDICATOR. In-sample must never be scored as forward.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "setup" / "scripts",):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import day_throttle_shadow as dts  # noqa: E402


def _f(sec, pnl, xsec=None, arm="safe", date="2026-08-20", eq=5000.0):
    return {"date": date, "arm": arm, "pnl": pnl, "sec": sec, "xsec": xsec, "eq": eq,
            "qty": 3.0, "side": "C", "setup": "X"}


# ---------------------------------------------------------------------------------
# 1. NO LOOK-AHEAD
# ---------------------------------------------------------------------------------
def test_open_position_contributes_nothing():
    """A -$500 loser still OPEN cannot arm the throttle -- we could not have known."""
    rows = [_f(34200, -500.0, xsec=None)]
    assert dts.realized_before(rows, 36000) == 0.0


def test_trade_exiting_after_the_entry_contributes_nothing():
    rows = [_f(34200, -500.0, xsec=40000)]
    assert dts.realized_before(rows, 36000) == 0.0


def test_trade_exiting_before_the_entry_counts():
    rows = [_f(34200, -500.0, xsec=35000)]
    assert dts.realized_before(rows, 36000) == -500.0


def test_exit_exactly_at_the_entry_second_counts():
    """Boundary pinned: at-or-before, not strictly-before."""
    assert dts.realized_before([_f(34200, -500.0, xsec=36000)], 36000) == -500.0


def test_evaluate_does_not_block_on_an_unexited_loss():
    fills = [_f(34200, -500.0, xsec=None), _f(36000, +300.0, xsec=40000)]
    rows = dts.evaluate(fills)
    assert rows[1]["would_block_T-2"] is False, "an open loser armed the throttle -- ORACLE LEAK"


def test_evaluate_blocks_after_a_closed_loss_past_threshold():
    # -2% of 5000 = -$100; a closed -$500 is well past it
    fills = [_f(34200, -500.0, xsec=35000), _f(36000, +300.0, xsec=40000)]
    rows = dts.evaluate(fills)
    assert rows[0]["would_block_T-2"] is False, "the losing trade itself must still be taken"
    assert rows[1]["would_block_T-2"] is True


def test_throttle_is_per_arm_not_per_book():
    """One arm's bad day must not throttle a different arm."""
    fills = [_f(34200, -500.0, xsec=35000, arm="safe"),
             _f(36000, +300.0, xsec=40000, arm="risky-1")]
    rows = dts.evaluate(fills)
    other = next(r for r in rows if r["arm"] == "risky-1")
    assert other["would_block_T-2"] is False


def test_throttle_resets_across_sessions():
    fills = [_f(34200, -900.0, xsec=35000, date="2026-08-20"),
             _f(34200, +100.0, xsec=40000, date="2026-08-21")]
    rows = dts.evaluate(fills)
    assert rows[1]["would_block_T-2"] is False


# ---------------------------------------------------------------------------------
# 2. NOT-YET-KNOWABLE IS A THIRD STATE
# ---------------------------------------------------------------------------------
def test_first_wave_unknown_while_wave_one_is_still_open():
    session = [_f(34200, -100.0, xsec=None), _f(40000, 50.0, xsec=41000)]
    assert dts.first_wave_was_red(session, 40000) is None


def test_first_wave_unknown_for_an_entry_inside_wave_one():
    session = [_f(34200, -100.0, xsec=34500), _f(34260, -50.0, xsec=34500)]
    assert dts.first_wave_was_red(session, 34260) is None


def test_first_wave_red_once_wave_one_has_closed():
    session = [_f(34200, -100.0, xsec=34500), _f(40000, 50.0, xsec=41000)]
    assert dts.first_wave_was_red(session, 39000) is True


def test_first_wave_green_is_false_not_none():
    session = [_f(34200, +100.0, xsec=34500), _f(40000, 50.0, xsec=41000)]
    assert dts.first_wave_was_red(session, 39000) is False


def test_first_wave_groups_simultaneous_arms_together():
    """Six arms entering the same impulse are ONE wave -- otherwise 'wave 1' is one arm's
    trade and the cohort is nonsense."""
    session = [_f(34200 + i, -10.0, xsec=34500, arm=a) for i, a in enumerate(
        ["safe", "bold", "safe-1", "safe-3", "risky-1", "risky-3"])]
    session.append(_f(40000, 50.0, xsec=41000))
    assert dts.first_wave_was_red(session, 39000) is True


def test_score_excludes_unknown_first_wave_rows():
    rows = [{"date": "2026-08-20", "pnl": -100.0, "first_wave_was_red": None,
             "would_block_T-2": False, "would_block_T-6": False},
            {"date": "2026-08-20", "pnl": -50.0, "first_wave_was_red": True,
             "would_block_T-2": False, "would_block_T-6": False}]
    h = dts.score(rows)["H-FIRSTWAVE"]
    assert h["n_judgeable"] == 1
    assert h["after_red_first_wave"]["n"] == 1


# ---------------------------------------------------------------------------------
# 3. ABSTAIN, NEVER GUESS
# ---------------------------------------------------------------------------------
def test_missing_equity_abstains_rather_than_defaulting_to_not_blocked():
    fills = [_f(34200, -500.0, xsec=35000, eq=None), _f(36000, +300.0, xsec=40000, eq=None)]
    rows = dts.evaluate(fills)
    assert all(r["would_block_T-2"] is None for r in rows)


def test_abstains_are_counted_separately_and_not_as_kept():
    rows = [{"date": "2026-08-20", "pnl": 10.0, "first_wave_was_red": None,
             "would_block_T-2": None, "would_block_T-6": None}]
    s = dts.score(rows)["T-2"]
    assert (s["n_abstain"], s["n_kept"], s["n_blocked"]) == (1, 0, 0)


# ---------------------------------------------------------------------------------
# 4. THE FROZEN CELLS ARE FROZEN
# ---------------------------------------------------------------------------------
def test_thresholds_match_the_prereg():
    """no_peeking_rule: moving a threshold VOIDS the window. If this fails, either restore
    the value or write a NEW pre-registration -- do not edit the number to match."""
    assert dts.CANDIDATES == {"T-2": 2.0, "T-6": 6.0}
    assert dts.SESSIONS_REQUIRED == 15
    assert dts.FORWARD_FIRST_DATE == "2026-08-18"


def test_prereg_file_exists_and_is_frozen():
    p = REPO / "analysis" / "recommendations" / "day-throttle-forward-prereg-2026-08-18.json"
    assert p.exists(), "the counter must never run without its frozen spec"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["status"] == "FROZEN_PREREG_FORWARD"
    assert {c["id"] for c in d["candidates"]} == set(dts.CANDIDATES)
    assert "shadow_only" in d


def test_counter_refuses_to_run_without_the_prereg(monkeypatch, tmp_path):
    monkeypatch.setattr(dts, "PREREG", tmp_path / "gone.json")
    assert dts.main() == 1, "produced numbers with no frozen spec behind them"


# ---------------------------------------------------------------------------------
# 5. FORWARD IS THE ONLY ADJUDICATOR
# ---------------------------------------------------------------------------------
def test_score_since_filters_to_the_forward_window():
    rows = [{"date": "2026-08-01", "pnl": -900.0, "first_wave_was_red": None,
             "would_block_T-2": True, "would_block_T-6": True},
            {"date": "2026-08-20", "pnl": -100.0, "first_wave_was_red": None,
             "would_block_T-2": True, "would_block_T-6": True}]
    fwd = dts.score(rows, since="2026-08-18")["T-2"]
    assert fwd["n_blocked"] == 1
    assert fwd["delta_usd"] == pytest.approx(100.0), "pre-window sessions leaked into forward"


def test_delta_ex_best_session_removes_the_single_best_session():
    rows = [{"date": "2026-08-20", "pnl": -900.0, "first_wave_was_red": None,
             "would_block_T-2": True, "would_block_T-6": False},
            {"date": "2026-08-21", "pnl": -100.0, "first_wave_was_red": None,
             "would_block_T-2": True, "would_block_T-6": False}]
    s = dts.score(rows)["T-2"]
    assert s["delta_usd"] == pytest.approx(1000.0)
    assert s["delta_ex_best_session_usd"] == pytest.approx(100.0)
    assert s["f_gates"]["F4_survives_dropping_best_session"] is True


def test_f2_flags_a_winner_killer():
    rows = [{"date": "2026-08-20", "pnl": +500.0, "first_wave_was_red": None,
             "would_block_T-2": True, "would_block_T-6": False},
            {"date": "2026-08-20", "pnl": -50.0, "first_wave_was_red": None,
             "would_block_T-2": True, "would_block_T-6": False}]
    g = dts.score(rows)["T-2"]["f_gates"]
    assert g["F2_not_a_winner_killer"] is False
    assert g["F1_direction_positive"] is False
