"""Per-account EXIT-shape correctness guard for all 6 SPY grid arms (J hard requirement 2).

Fast, deterministic, no orchestrator/pandas: for EVERY one of the 6 SPY grid arms (safe-1/2/3,
risky-1, bold-2, risky-3) the live executor (plan_all) must thread each fired strategy's
REGISTRY ExitShape through to the EntryPlan VERBATIM -- because that exit_shape dict is the
exact input the live exit_manager/exit_actuator scale-out consumes (partial TP1 + runner +
profit-lock). A drift between the placed exit_shape and the registry would silently change the
realized scale-out, so this is the contract that ties "the validated edge IS its exit" to the
live order path, for every account, off the ONE brain.

Complements:
  * test_exit_manager.py  -- the pure 5-stage walk realizes the shape correctly.
  * test_exit_actuator.py -- the live layer places exactly tp1_qty then runner (total == qty).
  * THIS file             -- every account FEEDS the manager the registry shape (no per-account
                             exit drift; exit is a property of the strategy, not the account).

Mirrors the offline harness backtest/validate_six_account_grid.py::_exit_correct in a unit form.
"""
from __future__ import annotations

import json
from pathlib import Path

import fleet_executor as fx
import strategies as strat_mod

FLEET_DIR = Path(__file__).resolve().parent
ACCOUNTS = json.loads((FLEET_DIR / "accounts.json").read_text(encoding="utf-8"))
SIX_SPY_ARMS = ("safe-1", "safe-2", "safe-3", "risky-1", "bold-2", "risky-3")

# A signal where BOTH registered strategies fire, ELITE-classified so no arm's selectivity
# gate benches the plan (the exit shape is gate-independent; entry selectivity is tested
# separately in test_six_account_routing.py + the entry-fidelity replay harness).
_SIGNAL = {"spot": 600.0, "strategies": [
    {"name": "ribbon_ride", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
     "triggers": ["level_rejection", "ribbon_flip", "confluence"], "quality": "ELITE",
     "est_premium": 1.20, "spot": 600.0},
    {"name": "vwap_continuation", "side": "C", "setup": "VWAP_CONTINUATION",
     "triggers": ["sequence_reclaim", "VWAP_CONTINUATION_BREAKOUT"], "quality": "ELITE",
     "est_premium": 1.20, "spot": 600.0},
]}


def _arm(arm_id):
    for a in ACCOUNTS["arms"]:
        if a.get("id") == arm_id:
            return a
    raise AssertionError(f"arm {arm_id} not in accounts.json")


def _planned_exit_shapes(arm_id):
    arm = _arm(arm_id)
    params = fx._params_for(arm)
    equity = float(arm.get("starting_equity") or 2000.0)
    plans = fx.plan_all(arm, _SIGNAL, equity, params)
    return {p.strategy: dict(p.exit_shape) for p in plans
            if p.action == "ENTER" and p.strategy and p.exit_shape}


def test_every_arm_plans_both_strategies():
    """All 6 arms run the FULL strategy set (gate x sizing on the shared set, no silo)."""
    for arm_id in SIX_SPY_ARMS:
        shapes = _planned_exit_shapes(arm_id)
        assert set(shapes) == {"ribbon_ride", "vwap_continuation"}, \
            f"{arm_id} planned {sorted(shapes)}"


def test_every_arm_exit_shape_matches_registry():
    """The placed exit_shape per strategy == the REGISTRY ExitShape VERBATIM, on every arm
    (the exit_manager's input contract -- no per-account exit drift)."""
    for arm_id in SIX_SPY_ARMS:
        shapes = _planned_exit_shapes(arm_id)
        for name, placed in shapes.items():
            expected = strat_mod.by_name(name).exit.to_dict()
            assert placed == expected, f"{arm_id}/{name}: {placed} != registry {expected}"


def test_exit_shape_is_full_5stage_contract():
    """Every threaded exit shape carries the FULL scale-out contract the manager needs:
    stop / TP1 partial fraction / runner profit-lock mode / runner target / chandelier trail."""
    required = {"premium_stop_pct", "tp1_premium_pct", "tp1_qty_fraction", "profit_lock_mode",
                "runner_target_pct", "trail_pct", "profit_lock_arm_pct"}
    for arm_id in SIX_SPY_ARMS:
        for placed in _planned_exit_shapes(arm_id).values():
            assert required <= set(placed), f"{arm_id} exit shape missing {required - set(placed)}"


def test_ribbon_and_vwap_shapes_are_distinct_per_strategy():
    """The two strategies carry DISTINCT validated shapes on the SAME arm (exit = strategy's
    property): ribbon -0.20/+1.5/0.8/fixed vs vwap -0.08/+0.3/0.667/trailing."""
    for arm_id in SIX_SPY_ARMS:
        s = _planned_exit_shapes(arm_id)
        assert s["ribbon_ride"]["premium_stop_pct"] == -0.20
        assert s["ribbon_ride"]["tp1_qty_fraction"] == 0.8
        assert s["ribbon_ride"]["profit_lock_mode"] == "fixed"
        assert s["vwap_continuation"]["premium_stop_pct"] == -0.08
        assert s["vwap_continuation"]["tp1_qty_fraction"] == 0.667
        assert s["vwap_continuation"]["profit_lock_mode"] == "trailing"


if __name__ == "__main__":
    import sys
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f"PASS  {t.__name__}"); passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
