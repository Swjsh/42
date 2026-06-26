"""6-account routing tests -- the ONE-brain-all-6 unification (J hard requirement 1).

Proves:
  * the fleet executor (run_dry) addresses ALL 6 SPY arms (safe-1/2/3, risky-1/3, bold-2)
    off one shared signal -- every arm is a grid cell (gate x sizing) on the SAME strategy set.
  * the FLEET_OWNS_ALL_6 lever toggles fleet_live's processable set: DEFAULT = 4 fleet_rest
    arms only (split execution, no double-fill); ON = all 6 (the Path-B migration).
  * the no-double-fill invariant: safe-2/bold-2 are mcp_heartbeat by default, so fleet_live
    skips them unless the lever is explicitly set (paired with GAMMA_CORE_PLACES=0 upstream).
  * every SPY arm runs the FULL strategy set with its own exit shape (gate x sizing, not a
    per-account strategy silo).
"""
from __future__ import annotations

import json
from pathlib import Path

import fleet_executor as fx
import fleet_live as fl

FLEET_DIR = Path(__file__).resolve().parent
ACCOUNTS = json.loads((FLEET_DIR / "accounts.json").read_text(encoding="utf-8"))

SIX_SPY_ARMS = {"safe-1", "safe-2", "safe-3", "risky-1", "risky-3", "bold-2"}
SIZING = [{"equity_min": 0, "equity_max": 1e9, "base_qty": 5, "elite_qty": 8}]
PARAMS = {"position_sizing_tiers": SIZING, "per_trade_risk_cap_pct": 0.5,
          "daily_loss_kill_switch_pct": 0.5, "min_contracts": 3,
          "v15_max_premium_pct_of_account": [{"equity_min": 0, "equity_max": 1e9, "max_pct": 0.9}]}


def _both_strategies_signal():
    """Both registered strategies fire on both sides -> every arm should see the full set."""
    return {"spot": 600.0, "strategies": [
        {"name": "ribbon_ride", "side": "P", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
         "triggers": ["level_rejection", "ribbon_flip"], "quality": "ELITE",
         "est_premium": None, "spot": 600.0},
        {"name": "vwap_continuation", "side": "C", "setup": "VWAP_CONTINUATION",
         "triggers": ["VWAP_TREND_ESTABLISHED", "VWAP_CONTINUATION_BREAKOUT"],
         "quality": "BASE", "est_premium": None, "spot": 600.0},
    ]}


# --- the 6 arms exist as a clean grid -----------------------------------------
def test_all_six_spy_arms_present_and_active():
    active = {a["id"] for a in ACCOUNTS["arms"]
              if a.get("status") == "active" and a.get("instrument") == "SPY_0DTE_OPTION"}
    assert SIX_SPY_ARMS <= active, f"missing arms: {SIX_SPY_ARMS - active}"


def test_run_dry_addresses_all_six_arms():
    """The brain's perception fans out to all 6 SPY arms via run_dry (one signal -> 6 cells)."""
    rows = fx.run_dry(_both_strategies_signal(), ACCOUNTS)
    addressed = {d.arm_id for d, _ in rows}
    assert SIX_SPY_ARMS <= addressed, f"run_dry skipped: {SIX_SPY_ARMS - addressed}"


def test_every_arm_runs_full_strategy_set():
    """Every SPY arm plans BOTH strategies (gate x sizing on the shared set), not a silo.
    A loose arm (no gate) should produce an ENTER plan for each fired strategy."""
    loose = next(a for a in ACCOUNTS["arms"] if a["id"] == "risky-3")  # risky x loose
    plans = fx.plan_all(loose, _both_strategies_signal(), 2000.0, PARAMS)
    strategies_seen = {p.strategy for p in plans if p.action == "ENTER"}
    assert strategies_seen == {"ribbon_ride", "vwap_continuation"}
    # each ENTER plan carries its OWN exit shape (exit is a property of the strategy)
    for p in plans:
        if p.action == "ENTER":
            assert p.exit_shape is not None
            assert {"premium_stop_pct", "tp1_premium_pct", "tp1_qty_fraction",
                    "profit_lock_mode"} <= set(p.exit_shape)


def test_exit_shape_differs_by_strategy_not_account():
    """ribbon_ride and vwap_continuation carry DISTINCT exit shapes on the SAME arm
    (exit is the strategy's property; the account only gates + sizes)."""
    loose = next(a for a in ACCOUNTS["arms"] if a["id"] == "risky-3")
    plans = {p.strategy: p for p in fx.plan_all(loose, _both_strategies_signal(), 2000.0, PARAMS)
             if p.action == "ENTER"}
    assert plans["ribbon_ride"].exit_shape["premium_stop_pct"] == -0.20
    assert plans["vwap_continuation"].exit_shape["premium_stop_pct"] == -0.08
    assert plans["ribbon_ride"].exit_shape["profit_lock_mode"] == "fixed"
    assert plans["vwap_continuation"].exit_shape["profit_lock_mode"] == "trailing"


# --- the FLEET_OWNS_ALL_6 unification lever (no double-fill invariant) ---------
def test_default_fleet_processes_only_fleet_rest_arms():
    """DEFAULT (lever off): fleet_live processes ONLY the 4 fleet_rest arms; the 2
    mcp_heartbeat controls (safe-2/bold-2) are skipped (they're placed by the brain ->
    no double-fill)."""
    orig = fl.FLEET_OWNS_ALL_6
    try:
        fl.FLEET_OWNS_ALL_6 = False
        processable = {a["id"] for a in ACCOUNTS["arms"] if fl._arm_is_processable(a)}
        assert processable == {"safe-1", "safe-3", "risky-1", "risky-3"}
        assert "safe-2" not in processable and "bold-2" not in processable
    finally:
        fl.FLEET_OWNS_ALL_6 = orig


def test_lever_on_fleet_processes_all_six_arms():
    """Lever ON (the Path-B migration): fleet_live processes all 6 SPY arms -> the fleet is
    the ONE executor for every grid cell off the ONE brain."""
    orig = fl.FLEET_OWNS_ALL_6
    try:
        fl.FLEET_OWNS_ALL_6 = True
        processable = {a["id"] for a in ACCOUNTS["arms"] if fl._arm_is_processable(a)}
        assert SIX_SPY_ARMS <= processable
    finally:
        fl.FLEET_OWNS_ALL_6 = orig


def test_lever_defaults_off_no_double_fill():
    """The unification lever DEFAULTS off so tonight's split execution (brain places
    safe-2/bold-2, fleet places the other 4) is unchanged -- no double-fill, reversible."""
    assert fl.FLEET_OWNS_ALL_6 is False


def test_futures_arms_never_processed_by_spy_runner():
    """The futures / pending-build arms are never picked up by the SPY option runner."""
    for arm in ACCOUNTS["arms"]:
        if arm.get("instrument") in ("MES_FUTURES", "MNQ_FUTURES"):
            assert not fl._arm_is_processable(arm)


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
