"""Tests for weekly_exit_gate -- the caller-side wrapper adding multi-day theta budget,
days-to-live, the CORRECTED Friday-only flatten schedule, and the paired shadow clock on
top of exit_manager's unforked walk. See weekly_exit_gate.py's module docstring for the
two scarred bugs this file exists to guard: the theta-timer mislabel and the dangerous
15:30 ET flatten (real cutoffs are 15:00/15:15 ET).
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "automation" / "state" / "fleet"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "automation" / "state" / "weekly"))
import exit_manager as em  # noqa: E402
import weekly_exit_gate as weg  # noqa: E402

FLATTEN = {"soft_time_stop": "14:45", "hard_backstop": "14:50",
           "last_resort_dne_sweep": "14:55"}

# Derived, not hand-picked-and-hoped: guarantees MONDAY really is a Monday even if this
# file is edited later, so the weekday-dependent tests below can never silently drift onto
# the wrong day.
_ANCHOR = date(2026, 8, 1)
MONDAY = _ANCHOR + timedelta(days=(7 - _ANCHOR.weekday()) % 7)
TUESDAY = MONDAY + timedelta(days=1)
WEDNESDAY = MONDAY + timedelta(days=2)
FRIDAY = MONDAY + timedelta(days=4)
SATURDAY = MONDAY + timedelta(days=5)
assert (MONDAY.weekday(), WEDNESDAY.weekday(), FRIDAY.weekday(), SATURDAY.weekday()) == (0, 2, 4, 5)

# A representative weekly shape (values match the shape weekly_strategies.weekly_exit_shape
# would build from params.json's current v1 defaults -- duplicated as a plain dict here so
# this test file has no import-time dependency on the live params.json content).
SHAPE = {"premium_stop_pct": -0.50, "tp1_premium_pct": 0.45, "tp1_qty_fraction": 0.5,
         "profit_lock_mode": "trailing", "runner_target_pct": 0.75, "trail_pct": 0.20,
         "profit_lock_arm_pct": 0.15, "stop_mode": "premium", "catastrophe_stop_pct": -0.50}


def _state(entry=1.00, qty=3, side="C"):
    return em.ExitState.from_entry(symbol="GLD260904C00380000", side=side,
                                    entry_premium=entry, qty=qty, exit_shape=SHAPE,
                                    strategy="weekly_level_interaction")


def _ctx(entry_session_date=MONDAY, days_to_live=3, zone_width=2.0,
         underlying_move_in_direction=0.0, max_bleed=0.30, flatten=None):
    return weg.WeeklyExitContext(
        entry_session_date=entry_session_date, days_to_live=days_to_live,
        zone_width=zone_width, underlying_move_in_direction=underlying_move_in_direction,
        max_premium_bleed_pct_without_progress=max_bleed,
        flatten_schedule_et=(flatten or FLATTEN))


# --- theta budget MUST fire before exit_manager's catastrophe/premium cap ------------------
def test_theta_budget_fires_before_catastrophe_cap():
    """Construct a position whose decay trips BOTH the theta budget (55% bleed >= the 30%
    threshold, thesis unprogressed) AND exit_manager's own -50% catastrophe/premium cap
    (worst_premium 0.45 <= runner_stop 0.50 on this shape). The wrapper must label the exit
    theta_budget, never premium_stop/structure_stop."""
    st = _state(entry=1.00, qty=3)
    ctx = _ctx(entry_session_date=TUESDAY, underlying_move_in_direction=0.0, zone_width=2.0,
               max_bleed=0.30)
    now_et = datetime.combine(TUESDAY, time(11, 0))
    dec = weg.plan_weekly_exit_actions(st, ctx, best_premium=0.50, worst_premium=0.45,
                                        open_qty=3, now_et=now_et)
    assert dec.closes_position
    assert dec.actions[0].stage == "theta_budget"
    assert dec.state.theta_budget_hit is True
    assert "theta_budget" in dec.state.theta_budget_reason

    # Same position, run through exit_manager UNWRAPPED (what a naive port would do): the
    # catastrophe/premium cap DOES also fire on this input -- proving the wrapper's ordering
    # is what changed the label, not that theta was the only condition present.
    naive = em.plan_exit_actions(st, best_premium=0.50, worst_premium=0.45, open_qty=3,
                                  now_et=time(11, 0))
    assert naive.actions[0].stage == "premium_stop"


def test_theta_budget_does_not_fire_once_thesis_has_progressed():
    st = _state(entry=1.00, qty=3)
    ctx = _ctx(entry_session_date=TUESDAY, underlying_move_in_direction=5.0, zone_width=2.0,
               max_bleed=0.30)  # 5.0 >= 0.5*2.0 -> thesis progressed, theta must stand down
    now_et = datetime.combine(TUESDAY, time(11, 0))
    dec = weg.plan_weekly_exit_actions(st, ctx, best_premium=0.50, worst_premium=0.45,
                                        open_qty=3, now_et=now_et)
    # falls through to exit_manager's own check, which fires on this worst_premium
    assert dec.actions[0].stage == "premium_stop"


def test_thesis_has_progressed_boundary():
    assert weg.thesis_has_progressed(0.999, 2.0) is False   # 0.999 < 0.5*2.0
    assert weg.thesis_has_progressed(1.0, 2.0) is True       # exactly at the boundary (>=)
    assert weg.thesis_has_progressed(1.5, 2.0) is True


# --- days-to-live ---------------------------------------------------------------------------
def test_days_to_live_expiry_on_a_non_friday_session():
    """Entered Monday (session 1); by Wednesday 3 sessions have elapsed (Mon/Tue/Wed) with
    days_to_live=3 -> expires. Wednesday is deliberately NOT a Friday, isolating this check
    from the flatten-schedule check below."""
    st = _state(entry=1.00, qty=3)
    ctx = _ctx(entry_session_date=MONDAY, days_to_live=3)
    now_et = datetime.combine(WEDNESDAY, time(11, 0))
    dec = weg.plan_weekly_exit_actions(st, ctx, best_premium=1.02, worst_premium=1.00,
                                        open_qty=3, now_et=now_et)
    assert dec.closes_position
    assert dec.actions[0].stage == "days_to_live"


def test_days_to_live_not_yet_expired_holds():
    st = _state(entry=1.00, qty=3)
    ctx = _ctx(entry_session_date=MONDAY, days_to_live=3)
    now_et = datetime.combine(TUESDAY, time(11, 0))  # only 2 sessions held
    dec = weg.plan_weekly_exit_actions(st, ctx, best_premium=1.02, worst_premium=1.00,
                                        open_qty=3, now_et=now_et)
    assert not dec.closes_position


def test_trading_sessions_held_counts_entry_day_as_session_one():
    assert weg.trading_sessions_held(MONDAY, MONDAY) == 1
    assert weg.trading_sessions_held(MONDAY, TUESDAY) == 2
    assert weg.trading_sessions_held(MONDAY, FRIDAY) == 5


def test_trading_sessions_held_rejects_weekend_endpoints():
    with pytest.raises(ValueError):
        weg.trading_sessions_held(MONDAY, SATURDAY)
    with pytest.raises(ValueError):
        weg.trading_sessions_held(SATURDAY, MONDAY)


# --- Friday-only flatten schedule (weekend_holds=false) ------------------------------------
def test_resolve_flatten_schedule_friday_returns_the_corrected_ladder():
    now_et = datetime.combine(FRIDAY, time(14, 46))
    sched = weg.resolve_flatten_schedule(now_et, FLATTEN)
    assert sched is not None
    assert sched.soft == time(14, 45)
    assert sched.hard == time(14, 50)
    assert sched.last_resort == time(14, 55)


def test_resolve_flatten_schedule_a_weekday_returns_none():
    now_et = datetime.combine(WEDNESDAY, time(14, 46))
    assert weg.resolve_flatten_schedule(now_et, FLATTEN) is None


def test_flatten_stage_ladder_priority_most_urgent_first():
    sched = weg.FlattenSchedule(soft=time(14, 45), hard=time(14, 50), last_resort=time(14, 55))
    assert weg.flatten_stage(datetime.combine(FRIDAY, time(14, 40)), sched) is None
    assert weg.flatten_stage(datetime.combine(FRIDAY, time(14, 45)), sched) == "flatten_soft_time_stop"
    assert weg.flatten_stage(datetime.combine(FRIDAY, time(14, 50)), sched) == "flatten_hard_backstop"
    assert weg.flatten_stage(datetime.combine(FRIDAY, time(14, 55)), sched) == "flatten_last_resort_dne_sweep"


def test_plan_weekly_exit_actions_friday_soft_flatten_fires_ahead_of_days_to_live():
    st = _state(entry=1.00, qty=3)
    ctx = _ctx(entry_session_date=MONDAY, days_to_live=99)  # effectively never expires
    now_et = datetime.combine(FRIDAY, time(14, 46))
    dec = weg.plan_weekly_exit_actions(st, ctx, best_premium=1.02, worst_premium=1.00,
                                        open_qty=3, now_et=now_et)
    assert dec.closes_position
    assert dec.actions[0].stage == "flatten_soft_time_stop"


def test_plan_weekly_exit_actions_weekday_never_forces_a_same_day_flatten():
    """The IDENTICAL time-of-day on a non-Friday must NOT force a close -- multi-day holds
    are the entire point of the weekly lane."""
    st = _state(entry=1.00, qty=3)
    ctx = _ctx(entry_session_date=MONDAY, days_to_live=99)
    now_et = datetime.combine(WEDNESDAY, time(14, 46))
    dec = weg.plan_weekly_exit_actions(st, ctx, best_premium=1.02, worst_premium=1.00,
                                        open_qty=3, now_et=now_et)
    assert not dec.closes_position


# --- weekend holds are structurally impossible ----------------------------------------------
def test_weekend_hold_impossible_plan_raises():
    st = _state(entry=1.00, qty=3)
    ctx = _ctx(entry_session_date=MONDAY, days_to_live=3)
    now_et = datetime.combine(SATURDAY, time(10, 0))
    with pytest.raises(ValueError, match="(?i)weekend"):
        weg.plan_weekly_exit_actions(st, ctx, best_premium=1.02, worst_premium=1.00,
                                      open_qty=3, now_et=now_et)


# --- overnight-trim multiplier: one-time entry-sizing interpretation -----------------------
def test_overnight_trim_qty_applies_once_not_compounding():
    assert weg.overnight_trim_qty(10, 0.5, held_overnight=False) == 10
    assert weg.overnight_trim_qty(10, 0.5, held_overnight=True) == 5
    with pytest.raises(ValueError):
        weg.overnight_trim_qty(0, 0.5, held_overnight=True)


# --- paired shadow clock ---------------------------------------------------------------------
def test_paired_shadow_clock_emits_both_decisions_independently():
    """Past exit_manager's own default same-day 15:50 ET time-stop, the naive 0DTE shape
    must flatten (stage=time_stop) while the weekly shape -- which passes a sentinel
    time_stop_et to its delegated call -- must NOT. Proves the two decisions are computed
    independently and the naive shape never influences the real one."""
    st = _state(entry=1.00, qty=3)
    ctx = _ctx(entry_session_date=MONDAY, days_to_live=99)
    now_et = datetime.combine(TUESDAY, time(15, 51))  # after SPY's 15:50 same-day stop
    row = weg.paired_shadow_clock(st, ctx, best_premium=1.02, worst_premium=1.00,
                                   open_qty=3, now_et=now_et)
    assert row["weekly"]["closes_position"] is False
    assert row["naive_0dte"]["closes_position"] is True
    assert row["naive_0dte"]["actions"][0]["stage"] == "time_stop"
    assert row["symbol"] == st.symbol


def test_emit_shadow_row_appends_jsonl_never_writes_the_real_ledger(tmp_path):
    path = tmp_path / "shadow-ledger.jsonl"
    weg.emit_shadow_row({"a": 1}, path=path)
    weg.emit_shadow_row({"a": 2}, path=path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"a": 2}
    # never touches the real (gitignored, shared) ledger this test's tmp path stands in for
    assert path != weg.SHADOW_LEDGER_PATH


# --- WeeklyExitContext.from_params unit conversion ------------------------------------------
def test_weekly_exit_context_from_params_converts_percent_to_fraction():
    params = {
        "exits": {
            "days_to_live": 3,
            "theta_budget": {
                "fires_before_catastrophe_cap": True,
                "max_premium_bleed_pct_without_progress": 30.0,
                "thesis_progress_definition": "underlying moved >= 0.5*zone_width",
            },
        },
        "flatten_schedule_et": FLATTEN,
    }
    ctx = weg.WeeklyExitContext.from_params(entry_session_date=MONDAY, zone_width=2.0,
                                             underlying_move_in_direction=0.0, params=params)
    assert ctx.days_to_live == 3
    assert ctx.max_premium_bleed_pct_without_progress == pytest.approx(0.30)
    assert ctx.flatten_schedule_et == FLATTEN
