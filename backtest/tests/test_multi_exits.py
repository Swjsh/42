"""Tests for multi/lib/exits.py (the exit DECISION core) and multi/lib/position_state.py
(the durable per-position state it reads/writes) -- the multi-symbol lane's (arm multi-1)
exit management for MULTI-DAY option holds.

RED-PROOF NOTE: this docstring intentionally documents which tests were RED-PROOFed (source
temporarily broken, pytest re-run, failure captured, source restored) rather than only ever
observed green. The actual before/after pytest output for each is quoted in the session
report, not reproduced here -- this file only carries the permanent, always-green suite.

No network, no broker, no filesystem outside pytest's `tmp_path` fixture. `multi/lib/exits.py`
is pure (params + a PositionRecord + this tick's market facts in, an ExitDecision out);
`multi/lib/position_state.py`'s load/save is exercised against tmp_path so the real
automation/state/multi/exit-state.json is never touched by the test suite.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from multi.lib import exits as ex  # noqa: E402
from multi.lib import position_state as ps  # noqa: E402

ET = ZoneInfo("America/New_York")


def _et(y: int, m: int, d: int, hh: int, mm: int) -> dt.datetime:
    return dt.datetime(y, m, d, hh, mm, tzinfo=ET)


def _params() -> dict:
    """A fresh, independent params dict each call (never a shared mutable literal) -- mirrors
    the exact shape of automation/state/multi/params.json's exits/flatten_schedule_et/risk
    blocks. Tests that need a variant mutate the RETURNED dict directly."""
    return {
        "exits": {
            "tp1_premium_pct": 45.0,
            "tp1_qty_fraction": 0.5,
            "runner_target_mult": 1.75,
            "trail_pct": 20.0,
            "profit_lock_arm_pct": 15.0,
            "catastrophe_stop_pct": -50.0,
            "theta_budget": {
                "fires_before_catastrophe_cap": True,
                "max_premium_bleed_pct_without_progress": 30.0,
                "thesis_progress_definition":
                    "underlying has moved >= 0.5 * ATR(14) in the trade's direction from entry",
            },
            "days_to_live": 3,
        },
        "flatten_schedule_et": {
            "soft_time_stop": "14:45",
            "hard_backstop": "14:50",
            "last_resort_dne_sweep": "14:55",
        },
        "risk": {"weekend_holds": False},
    }


def _record(**overrides) -> ps.PositionRecord:
    fields = dict(
        symbol="NVDA", contract="NVDA260828C00135000", side="C",
        entry_premium=1.00, entry_underlying_price=130.0, qty=10,
        entry_session_date="2026-08-19", expiry="2026-08-28",
        hwm_premium=1.00, tp1_filled=False, days_held=0,
        runner_stop_premium=None, profit_lock_armed=False, strategy="test",
    )
    fields.update(overrides)
    return ps.PositionRecord(**fields)


# =============================================================================================
# 1. THE ORDERING TEST -- theta budget must fire before the catastrophe cap when both would
# =============================================================================================
def test_theta_fires_before_catastrophe_when_both_would_fire():
    """worst_premium=0.40 is BOTH >=30% bled-without-progress (theta) AND <= the -50%
    catastrophe level (entry*0.50 = 0.50). The underlying has NOT moved at all (no thesis
    progress), so theta's condition is unambiguously true. Per params.exits.theta_budget's
    fires_before_catastrophe_cap=True (and the module docstring's ordering #2), the decision
    must be labelled THETA_BUDGET, never CATASTROPHE_STOP."""
    params = _params()
    rec = _record(entry_premium=1.00, entry_underlying_price=130.0, side="C")
    now = _et(2026, 8, 20, 11, 0)  # Thursday, not expiry day
    decision = ex.evaluate_exit(
        rec, now_et=now, best_premium=0.40, worst_premium=0.40, open_qty=10,
        underlying_price=130.0, atr14=2.0, params=params,
    )
    assert decision.action == ex.ACTION_SELL_ALL
    assert decision.stage == ex.STAGE_THETA_BUDGET, (
        f"expected THETA_BUDGET, got {decision.stage!r} -- {decision.reason}"
    )
    # sanity: catastrophe WOULD also have fired on these facts (worst 0.40 <= level 0.50) --
    # proves this is a genuine ordering conflict, not a case where only theta applies.
    cat_level = rec.entry_premium * (1.0 + params["exits"]["catastrophe_stop_pct"] / 100.0)
    assert 0.40 <= cat_level


def test_theta_flag_false_defers_to_catastrophe_same_facts():
    """Identical facts to the test above except theta_budget.fires_before_catastrophe_cap is
    flipped to False in params. This proves the ordering is genuinely READ from params (not a
    hardcoded True) -- flipping only the flag flips the label to CATASTROPHE_STOP."""
    params = _params()
    params["exits"]["theta_budget"]["fires_before_catastrophe_cap"] = False
    rec = _record(entry_premium=1.00, entry_underlying_price=130.0, side="C")
    now = _et(2026, 8, 20, 11, 0)
    decision = ex.evaluate_exit(
        rec, now_et=now, best_premium=0.40, worst_premium=0.40, open_qty=10,
        underlying_price=130.0, atr14=2.0, params=params,
    )
    assert decision.stage == ex.STAGE_CATASTROPHE_STOP


def test_theta_does_not_fire_when_thesis_progress_confirmed():
    """Same premium bleed as the ordering test, but the underlying HAS cleared 0.5*ATR14 in
    the trade's direction -- theta must not fire (thesis is confirmed, decay alone should not
    stop the position out under the THETA label). Catastrophe still fires underneath it since
    worst_premium is still <= the -50% level -- this is the correct, expected label for a
    real -50% loss once the theta escape hatch no longer applies."""
    params = _params()
    rec = _record(entry_premium=1.00, entry_underlying_price=130.0, side="C")
    now = _et(2026, 8, 20, 11, 0)
    decision = ex.evaluate_exit(
        rec, now_et=now, best_premium=0.40, worst_premium=0.40, open_qty=10,
        underlying_price=131.5,  # +1.50 >= 0.5 * ATR14(3.0) = 1.50 -- progress confirmed
        atr14=3.0, params=params,
    )
    assert decision.stage == ex.STAGE_CATASTROPHE_STOP


# =============================================================================================
# 2. EXPIRY-DAY FLATTEN -- safety, first, unskippable
# =============================================================================================
def test_expiry_flatten_overrides_happy_runner():
    """A runner that already banked TP1 and is riding nicely toward a huge gain (best_premium
    far above runner_target) would normally fire RUNNER_TARGET. On its own expiry day, at/
    after the soft cutoff, it must flatten instead -- the flatten schedule is a safety item
    that no profit-taking rule may override."""
    params = _params()
    rec = _record(entry_premium=1.00, tp1_filled=True, runner_stop_premium=1.00,
                  profit_lock_armed=True, hwm_premium=2.00, expiry="2026-08-21")
    now = _et(2026, 8, 21, 14, 46)  # expiry day, just past the 14:45 soft cutoff
    decision = ex.evaluate_exit(
        rec, now_et=now, best_premium=3.00, worst_premium=2.90, open_qty=5,
        underlying_price=140.0, atr14=2.0, params=params,
    )
    assert decision.action == ex.ACTION_SELL_ALL
    assert decision.stage == ex.STAGE_EXPIRY_SOFT
    assert decision.qty == 5
    # sanity: runner_target (1.75x = 1.75) is comfortably cleared by best_premium=3.00, so a
    # walk that DIDN'T check expiry first would have returned RUNNER_TARGET here.
    assert 3.00 >= rec.entry_premium * params["exits"]["runner_target_mult"]


@pytest.mark.parametrize("hh,mm,expected_stage", [
    (14, 45, ex.STAGE_EXPIRY_SOFT),
    (14, 50, ex.STAGE_EXPIRY_HARD),
    (14, 55, ex.STAGE_EXPIRY_LAST_RESORT),
])
def test_expiry_flatten_severity_escalates_with_time(hh, mm, expected_stage):
    params = _params()
    rec = _record(expiry="2026-08-21")
    now = _et(2026, 8, 21, hh, mm)
    decision = ex.evaluate_exit(
        rec, now_et=now, best_premium=1.01, worst_premium=1.00, open_qty=10,
        underlying_price=130.0, atr14=2.0, params=params,
    )
    assert decision.stage == expected_stage
    assert decision.action == ex.ACTION_SELL_ALL


def test_expiry_day_before_soft_cutoff_evaluates_normally():
    params = _params()
    rec = _record(expiry="2026-08-21")
    now = _et(2026, 8, 21, 14, 44)  # one minute before the soft cutoff
    decision = ex.evaluate_exit(
        rec, now_et=now, best_premium=1.01, worst_premium=1.00, open_qty=10,
        underlying_price=130.0, atr14=2.0, params=params,
    )
    assert decision.stage != ex.STAGE_EXPIRY_SOFT
    assert decision.action == ex.ACTION_HOLD


# =============================================================================================
# 3. DAYS-TO-LIVE -- trading SESSIONS, never calendar days
# =============================================================================================
def test_trading_sessions_elapsed_skips_the_weekend():
    entry = dt.date(2026, 8, 14)  # Friday
    assert ex.trading_sessions_elapsed(entry, dt.date(2026, 8, 14)) == 0
    assert ex.trading_sessions_elapsed(entry, dt.date(2026, 8, 15)) == 0  # Saturday
    assert ex.trading_sessions_elapsed(entry, dt.date(2026, 8, 16)) == 0  # Sunday
    assert ex.trading_sessions_elapsed(entry, dt.date(2026, 8, 17)) == 1  # Monday -- ONE, not 3
    assert ex.trading_sessions_elapsed(entry, dt.date(2026, 8, 18)) == 2  # Tuesday
    assert ex.trading_sessions_elapsed(entry, dt.date(2026, 8, 19)) == 3  # Wednesday


def test_days_to_live_counts_trading_sessions_not_calendar_days():
    params = _params()  # days_to_live = 3
    rec = _record(entry_session_date="2026-08-14")  # Friday

    # Monday: Fri->Mon is ONE trading session (not the 3 calendar days it spans) -- must HOLD.
    now_mon = _et(2026, 8, 17, 11, 0)
    d_mon = ex.evaluate_exit(
        rec, now_et=now_mon, best_premium=1.00, worst_premium=1.00, open_qty=10,
        underlying_price=130.0, atr14=2.0, params=params,
    )
    assert d_mon.stage != ex.STAGE_DAYS_TO_LIVE
    assert d_mon.facts["sessions_elapsed"] == 1

    # Wednesday: Mon+Tue+Wed = 3 sessions -- budget of 3 is now met, must flatten.
    now_wed = _et(2026, 8, 19, 11, 0)
    d_wed = ex.evaluate_exit(
        rec, now_et=now_wed, best_premium=1.00, worst_premium=1.00, open_qty=10,
        underlying_price=130.0, atr14=2.0, params=params,
    )
    assert d_wed.stage == ex.STAGE_DAYS_TO_LIVE
    assert d_wed.facts["sessions_elapsed"] == 3


# =============================================================================================
# 4. WEEKEND GUARD -- risk.weekend_holds=false; a hold across the weekend is impossible
# =============================================================================================
def test_weekend_hold_is_impossible():
    params = _params()
    rec = _record(entry_session_date="2026-08-19", expiry="2026-08-28")  # not expiry day

    # Friday at/after the soft cutoff -- must flatten even though nothing else would fire.
    now_fri = _et(2026, 8, 21, 15, 0)
    d_fri = ex.evaluate_exit(
        rec, now_et=now_fri, best_premium=1.00, worst_premium=1.00, open_qty=10,
        underlying_price=130.0, atr14=2.0, params=params,
    )
    assert d_fri.stage == ex.STAGE_WEEKEND_GUARD
    assert d_fri.action == ex.ACTION_SELL_ALL

    # Thursday, same time, same position -- ordinary HOLD, weekend guard is Friday-only.
    now_thu = _et(2026, 8, 20, 15, 0)
    d_thu = ex.evaluate_exit(
        rec, now_et=now_thu, best_premium=1.00, worst_premium=1.00, open_qty=10,
        underlying_price=130.0, atr14=2.0, params=params,
    )
    assert d_thu.stage != ex.STAGE_WEEKEND_GUARD
    assert d_thu.action == ex.ACTION_HOLD


def test_weekend_guard_inert_when_weekend_holds_allowed():
    params = _params()
    params["risk"]["weekend_holds"] = True
    rec = _record(entry_session_date="2026-08-19", expiry="2026-08-28")
    now_fri = _et(2026, 8, 21, 15, 0)
    decision = ex.evaluate_exit(
        rec, now_et=now_fri, best_premium=1.00, worst_premium=1.00, open_qty=10,
        underlying_price=130.0, atr14=2.0, params=params,
    )
    assert decision.stage != ex.STAGE_WEEKEND_GUARD


# =============================================================================================
# 5. TP1 fires once and only once
# =============================================================================================
def test_tp1_fires_once_not_twice():
    params = _params()
    rec = _record(entry_premium=1.00, qty=10, tp1_filled=False)
    now = _et(2026, 8, 19, 11, 0)

    d1 = ex.evaluate_exit(
        rec, now_et=now, best_premium=1.50, worst_premium=1.45, open_qty=10,
        underlying_price=132.0, atr14=2.0, params=params,
    )
    assert d1.action == ex.ACTION_SELL_PARTIAL
    assert d1.stage == ex.STAGE_TP1
    assert d1.record.tp1_filled is True
    assert d1.qty == 5  # int(10 * tp1_qty_fraction=0.5)

    # caller persists d1.record and reduces broker-truth qty by the partial sold.
    remaining_qty = 10 - d1.qty
    d2 = ex.evaluate_exit(
        d1.record, now_et=now, best_premium=1.55, worst_premium=1.50, open_qty=remaining_qty,
        underlying_price=132.0, atr14=2.0, params=params,
    )
    assert d2.stage != ex.STAGE_TP1
    assert d2.action != ex.ACTION_SELL_PARTIAL


# =============================================================================================
# 6. sanity coverage -- runner target, trailing stop, catastrophe-alone, config errors
# =============================================================================================
def test_runner_target_hit_post_tp1():
    params = _params()
    rec = _record(entry_premium=1.00, tp1_filled=True, runner_stop_premium=1.00,
                  hwm_premium=1.50)
    now = _et(2026, 8, 19, 11, 0)
    decision = ex.evaluate_exit(
        rec, now_et=now, best_premium=1.80, worst_premium=1.75, open_qty=5,
        underlying_price=134.0, atr14=2.0, params=params,
    )
    assert decision.action == ex.ACTION_SELL_ALL
    assert decision.stage == ex.STAGE_RUNNER_TARGET


def test_trailing_stop_hit_post_tp1():
    params = _params()
    # armed (best has cleared +15%), hwm 1.60 -> trail floor = 1.60*0.8 = 1.28
    rec = _record(entry_premium=1.00, tp1_filled=True, runner_stop_premium=1.00,
                  profit_lock_armed=True, hwm_premium=1.60)
    now = _et(2026, 8, 19, 11, 0)
    decision = ex.evaluate_exit(
        rec, now_et=now, best_premium=1.30, worst_premium=1.20, open_qty=5,
        underlying_price=133.0, atr14=2.0, params=params,
    )
    assert decision.action == ex.ACTION_SELL_ALL
    assert decision.stage == ex.STAGE_TRAIL_STOP


def test_catastrophe_alone_with_no_theta_condition():
    """Underlying HAS made thesis progress (so theta cannot fire) and the bleed is well past
    -50% -- catastrophe should fire cleanly with no ordering ambiguity."""
    params = _params()
    rec = _record(entry_premium=1.00, entry_underlying_price=130.0, side="C")
    now = _et(2026, 8, 19, 11, 0)
    decision = ex.evaluate_exit(
        rec, now_et=now, best_premium=0.30, worst_premium=0.30, open_qty=10,
        underlying_price=135.0,  # +5.0 >= 0.5*ATR14(2.0)=1.0 -- clear progress
        atr14=2.0, params=params,
    )
    assert decision.action == ex.ACTION_SELL_ALL
    assert decision.stage == ex.STAGE_CATASTROPHE_STOP


def test_ordinary_hold_when_nothing_fires():
    params = _params()
    rec = _record()
    now = _et(2026, 8, 19, 11, 0)
    decision = ex.evaluate_exit(
        rec, now_et=now, best_premium=1.05, worst_premium=1.02, open_qty=10,
        underlying_price=130.5, atr14=2.0, params=params,
    )
    assert decision.action == ex.ACTION_HOLD
    assert decision.qty == 0


def test_missing_required_param_key_raises_loudly():
    params = _params()
    del params["exits"]["days_to_live"]
    rec = _record()
    now = _et(2026, 8, 19, 11, 0)
    with pytest.raises(ex.ExitConfigError):
        ex.evaluate_exit(
            rec, now_et=now, best_premium=1.00, worst_premium=1.00, open_qty=10,
            underlying_price=130.0, atr14=2.0, params=params,
        )


def test_naive_datetime_rejected():
    params = _params()
    rec = _record()
    now_naive = dt.datetime(2026, 8, 19, 11, 0)  # no tzinfo
    with pytest.raises(ex.ExitConfigError):
        ex.evaluate_exit(
            rec, now_et=now_naive, best_premium=1.00, worst_premium=1.00, open_qty=10,
            underlying_price=130.0, atr14=2.0, params=params,
        )


def test_already_flat_position_is_a_pure_noop():
    params = _params()
    rec = _record()
    now = _et(2026, 8, 19, 11, 0)
    decision = ex.evaluate_exit(
        rec, now_et=now, best_premium=999.0, worst_premium=0.01, open_qty=0,
        underlying_price=130.0, atr14=2.0, params=params,
    )
    assert decision.action == ex.ACTION_HOLD
    assert decision.stage == ex.STAGE_FLAT
    assert decision.qty == 0


# =============================================================================================
# 7. position_state.py -- corrupt/missing RAISES, never a silent empty state
# =============================================================================================
def test_load_state_raises_on_missing_file(tmp_path):
    path = tmp_path / "exit-state.json"
    assert not path.exists()
    with pytest.raises(ps.PositionStateError):
        ps.load_state(path=path)


def test_load_state_raises_on_corrupt_json(tmp_path):
    path = tmp_path / "exit-state.json"
    path.write_text("{this is not valid json", encoding="utf-8")
    with pytest.raises(ps.PositionStateError):
        ps.load_state(path=path)


def test_load_state_raises_on_malformed_schema(tmp_path):
    path = tmp_path / "exit-state.json"
    path.write_text(json.dumps({"totally": "the wrong shape"}), encoding="utf-8")
    with pytest.raises(ps.PositionStateError):
        ps.load_state(path=path)


def test_load_state_raises_on_wrong_schema_version(tmp_path):
    path = tmp_path / "exit-state.json"
    path.write_text(json.dumps({"_schema": 999, "positions": {}}), encoding="utf-8")
    with pytest.raises(ps.PositionStateError):
        ps.load_state(path=path)


def test_load_state_raises_on_corrupt_individual_record(tmp_path):
    path = tmp_path / "exit-state.json"
    path.write_text(json.dumps({"_schema": 1, "positions": {"X": {"symbol": "X"}}}),
                    encoding="utf-8")
    with pytest.raises(ps.PositionStateError):
        ps.load_state(path=path)


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "exit-state.json"
    rec = _record()
    ps.save_state({rec.contract: rec}, path=path)
    loaded = ps.load_state(path=path)
    assert loaded == {rec.contract: rec}


def test_ensure_initialized_is_the_only_sanctioned_bootstrap(tmp_path):
    path = tmp_path / "exit-state.json"
    assert not path.exists()
    ps.ensure_initialized(path=path)
    assert path.exists()
    assert ps.load_state(path=path) == {}
    # idempotent -- a second call on an already-initialized file is a no-op, not an error.
    ps.ensure_initialized(path=path)
    assert ps.load_state(path=path) == {}


# =============================================================================================
# 8. atomic write survives a simulated mid-write failure
# =============================================================================================
def test_atomic_write_survives_mid_write_failure(tmp_path, monkeypatch):
    path = tmp_path / "exit-state.json"
    rec = _record()
    ps.save_state({rec.contract: rec}, path=path)
    original_bytes = path.read_bytes()

    def _boom(*_a, **_kw):
        raise RuntimeError("simulated crash mid-write")

    monkeypatch.setattr(ps.json, "dump", _boom)
    rec2 = _record(entry_premium=99.0)
    with pytest.raises(RuntimeError):
        ps.save_state({rec2.contract: rec2}, path=path)

    # the destination must be BYTE-FOR-BYTE untouched by the failed write.
    assert path.read_bytes() == original_bytes
    # no orphaned temp file left in the directory.
    leftovers = [p for p in tmp_path.iterdir() if p != path]
    assert leftovers == [], f"orphaned temp file(s) left behind: {leftovers}"
