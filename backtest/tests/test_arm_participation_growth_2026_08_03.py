"""Guards for backtest/tools/arm_participation_growth_2026_08_03.py -- the per-arm
participation funnel + growth-path day-count model (ARM-PARTICIPATION-AND-GROWTH-2026-08-03.md).

Covers only the PURE functions (no file I/O): mechanism_bucket, days_to_target,
windowed_real_pnl, split_recent_vs_early. The one I/O function (build_full_window_events)
is a thin, obvious pass-through to the already-guarded participation_cascade.py
(test_participation_cascade.py) and is exercised indirectly by running the real tool
against the real live ledgers (see the module's own __main__, run manually, not as a
pytest -- mirrors how CAPITAL-EFFICIENCY-2026-08-03.md's own guard suite is scoped).

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_arm_participation_growth_2026_08_03.py -q
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _load(name: str, relpath: str):
    path = os.path.join(ROOT, *relpath.split("/"), f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


apg = _load("arm_participation_growth_2026_08_03", "backtest/tools")


# ---------------------------------------------------------------------------
# mechanism_bucket
# ---------------------------------------------------------------------------

class TestMechanismBucket:
    def test_no_signal_stage_is_no_signal_from_producer(self):
        assert apg.mechanism_bucket("none", None, "NO_SIGNAL") == "no_signal_from_producer"

    def test_no_data_signal_feed_is_producer_signal_unavailable(self):
        assert apg.mechanism_bucket("none", "signal_feed", "NO_DATA") == "producer_signal_unavailable"

    def test_no_data_stale_blocker_is_producer_signal_unavailable(self):
        assert apg.mechanism_bucket("none", "stale_something", "NO_DATA") == "producer_signal_unavailable"

    def test_no_data_engine_error_is_no_data_other(self):
        assert apg.mechanism_bucket("none", "engine_error", "NO_DATA") == "no_data_other"

    def test_not_flat_blocker(self):
        assert apg.mechanism_bucket("risk_gate", "not_flat_rule4", "RISK_GATE_DENY") == "not_flat"

    def test_min_premium_floor_blocker(self):
        assert apg.mechanism_bucket("risk_gate", "min_premium_floor", "RISK_GATE_DENY") == "min_premium_floor"

    def test_pdt_blocker(self):
        assert apg.mechanism_bucket("risk_gate", "pdt", "RISK_GATE_DENY") == "pdt"

    def test_risk_cap_blocker_fleet_naming(self):
        assert apg.mechanism_bucket("risk_gate", "risk_cap", "RISK_GATE_DENY") == "risk_cap"

    def test_risk_cap_blocker_core_naming(self):
        # core rows classify as risk_deny_risk_cap (see participation_cascade._classify_action_code)
        assert apg.mechanism_bucket("risk_gate", "risk_deny_risk_cap", "RISK_GATE_DENY") == "risk_cap"

    def test_quality_lock_blocker(self):
        assert apg.mechanism_bucket("risk_gate", "quality_lock", "RISK_GATE_DENY") == "quality_lock"

    def test_structure_veto_stage(self):
        assert apg.mechanism_bucket("veto", "structure_veto", "STRUCTURE_VETO") == "gate_structure_veto"

    def test_gate_block_named_gate(self):
        assert apg.mechanism_bucket("gate", "block_elite_bull", "GATE_BLOCK") == "gate_named"

    def test_window_block_is_gate_named(self):
        assert apg.mechanism_bucket("window", "entry_ceiling_15:00", "WINDOW_BLOCK") == "gate_named"

    def test_gate_block_arm_selectivity(self):
        assert apg.mechanism_bucket("gate", "arm_selectivity_gate", "GATE_BLOCK") == "gate_arm_selectivity"

    def test_gate_block_direction_lock(self):
        assert apg.mechanism_bucket("gate", "direction_lock", "GATE_BLOCK") == "gate_arm_selectivity"

    def test_stale_trigger_stage(self):
        assert apg.mechanism_bucket("execution", "stale_trigger_bar", "STALE_TRIGGER") == "execution_stale_trigger"

    def test_place_fail_stage(self):
        assert apg.mechanism_bucket("execution", "broker_reject", "PLACE_FAIL") == "execution_place_fail"

    def test_unrecognized_falls_open_to_other_block_not_dropped(self):
        # fail-open contract: an unrecognized (category, blocker, stage) triple must still
        # be COUNTED (visible), never silently discarded -- mirrors participation_cascade's
        # own OTHER_BLOCK fail-open philosophy.
        result = apg.mechanism_bucket("gate", "some_brand_new_gate_name", "OTHER_BLOCK")
        assert result.startswith("other_block:")
        assert "some_brand_new_gate_name" in result


# ---------------------------------------------------------------------------
# days_to_target
# ---------------------------------------------------------------------------

class TestDaysToTarget:
    def test_already_at_target_is_zero(self):
        assert apg.days_to_target(5000.0, 5000.0, 10.0) == 0.0

    def test_already_past_target_is_zero(self):
        assert apg.days_to_target(6000.0, 5000.0, 10.0) == 0.0

    def test_positive_rate_simple_division(self):
        # needs 1000 more, at 10/day -> 100 days, no rounding surprises
        assert apg.days_to_target(4000.0, 5000.0, 10.0) == 100.0

    def test_zero_rate_is_none_not_infinity_or_huge_number(self):
        assert apg.days_to_target(1000.0, 5000.0, 0.0) is None

    def test_negative_rate_is_none(self):
        assert apg.days_to_target(1000.0, 5000.0, -50.0) is None

    def test_none_rate_is_none(self):
        assert apg.days_to_target(1000.0, 5000.0, None) is None

    def test_at_target_with_non_positive_rate_is_still_zero_not_none(self):
        # the equal-to-target boundary must short-circuit BEFORE the rate check -- once
        # you're there, a bad/unknown rate must not make "already arrived" look unreachable.
        assert apg.days_to_target(5000.0, 5000.0, None) == 0.0
        assert apg.days_to_target(5000.0, 5000.0, -10.0) == 0.0


# ---------------------------------------------------------------------------
# windowed_real_pnl
# ---------------------------------------------------------------------------

class TestWindowedRealPnl:
    def test_filters_to_window_inclusive_both_ends(self):
        daily = {"2026-07-01": 10.0, "2026-07-02": 20.0, "2026-07-03": -5.0, "2026-07-10": 999.0}
        total, n = apg.windowed_real_pnl(daily, "2026-07-01", "2026-07-03")
        assert total == 25.0
        assert n == 3

    def test_excludes_outside_window(self):
        daily = {"2026-06-01": 500.0, "2026-07-15": 10.0}
        total, n = apg.windowed_real_pnl(daily, "2026-07-01", "2026-07-31")
        assert total == 10.0
        assert n == 1

    def test_empty_window_returns_zero(self):
        total, n = apg.windowed_real_pnl({"2026-01-01": 5.0}, "2026-07-01", "2026-07-31")
        assert total == 0.0
        assert n == 0

    def test_ignores_blank_date_key(self):
        daily = {"": 12345.0, "2026-07-05": 1.0}
        total, n = apg.windowed_real_pnl(daily, "2026-07-01", "2026-07-31")
        assert total == 1.0
        assert n == 1


# ---------------------------------------------------------------------------
# split_recent_vs_early
# ---------------------------------------------------------------------------

class TestSplitRecentVsEarly:
    def test_even_split(self):
        dates = ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"]
        daily = {"2026-07-01": 10.0, "2026-07-02": 10.0, "2026-07-03": -20.0, "2026-07-04": -20.0}
        r = apg.split_recent_vs_early(dates, daily)
        assert r["early"]["n_days"] == 2
        assert r["recent"]["n_days"] == 2
        assert r["early"]["rate"] == 10.0
        assert r["recent"]["rate"] == -20.0
        assert r["full"]["n_days"] == 4
        assert r["full"]["rate"] == -5.0

    def test_odd_split_extra_day_goes_to_recent(self):
        dates = ["2026-07-01", "2026-07-02", "2026-07-03"]
        daily = {"2026-07-01": 0.0, "2026-07-02": 0.0, "2026-07-03": 0.0}
        r = apg.split_recent_vs_early(dates, daily)
        assert r["early"]["n_days"] == 1
        assert r["recent"]["n_days"] == 2

    def test_single_day_all_recent_no_early(self):
        dates = ["2026-07-01"]
        daily = {"2026-07-01": 42.0}
        r = apg.split_recent_vs_early(dates, daily)
        assert r["recent"]["n_days"] == 1
        assert r["early"]["n_days"] == 0
        assert r["early"]["rate"] is None

    def test_empty_dates_returns_all_none_not_a_crash(self):
        r = apg.split_recent_vs_early([], {})
        assert r["full"]["rate"] is None
        assert r["early"]["rate"] is None
        assert r["recent"]["rate"] is None


# ---------------------------------------------------------------------------
# mechanism_bucket taxonomy coverage -- every bucket the report cites must be reachable
# ---------------------------------------------------------------------------

def test_full_task_mechanism_vocabulary_is_reachable():
    """The task named 8 mechanisms explicitly: gate / min_premium_floor / sizing_deadlock
    (disclosed as unmeasured -- see module docstring) / not_flat / arm_disabled /
    no_signal_from_producer / risk_cap / pdt. Every one except sizing_deadlock and
    arm_disabled (both real but not classifiable from THIS ledger's fields -- see the
    function's own docstring) must be reachable through mechanism_bucket."""
    reachable = {
        apg.mechanism_bucket("gate", "block_elite_bull", "GATE_BLOCK"),
        apg.mechanism_bucket("gate", "arm_selectivity_gate", "GATE_BLOCK"),
        apg.mechanism_bucket("risk_gate", "min_premium_floor", "RISK_GATE_DENY"),
        apg.mechanism_bucket("risk_gate", "not_flat_rule4", "RISK_GATE_DENY"),
        apg.mechanism_bucket("none", None, "NO_SIGNAL"),
        apg.mechanism_bucket("risk_gate", "risk_cap", "RISK_GATE_DENY"),
        apg.mechanism_bucket("risk_gate", "pdt", "RISK_GATE_DENY"),
    }
    assert "gate_named" in reachable
    assert "gate_arm_selectivity" in reachable
    assert "min_premium_floor" in reachable
    assert "not_flat" in reachable
    assert "no_signal_from_producer" in reachable
    assert "risk_cap" in reachable
    assert "pdt" in reachable
