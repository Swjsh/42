"""6-account routing tests -- the ONE-brain-all-6 unification (J hard requirement 1).

Proves:
  * the fleet executor (run_dry) addresses every ACTIVE SPY arm (safe-2/3, risky-1/3, bold-2 --
    5 as of 2026-07-11, was 6 incl. safe-1) off one shared signal -- every arm is a grid cell
    (gate x sizing) on the SAME strategy set.
  * the FLEET_OWNS_ALL_6 lever toggles fleet_live's processable set: DEFAULT = the fleet_rest
    arms only (3 as of 2026-07-11, was 4 -- split execution, no double-fill); ON = all active
    arms (the Path-B migration). Name kept as FLEET_OWNS_ALL_6 (byte-identical flag/behavior);
    only the roster it toggles over shrank.
  * the no-double-fill invariant: safe-2/bold-2 are mcp_heartbeat by default, so fleet_live
    skips them unless the lever is explicitly set (paired with GAMMA_CORE_PLACES=0 upstream).
  * every SPY arm runs the FULL strategy set with its own exit shape (gate x sizing, not a
    per-account strategy silo).

SAFE-1 RETIRED 2026-07-11: accounts.json status flipped active->retired (account PA3DHPT7KIQE
reassigned to core Safe / "safe-2", after the original safe-2 account PA3S2PYAS2WQ was deleted
2026-07-10). This file's active-roster constants and assertions were updated 6->5 / 4->3 to
match; a new explicit guard (test_safe1_is_retired_not_dispatched) pins the exclusion so a
future edit can't silently resurrect safe-1 into the live roster.
"""
from __future__ import annotations

import json
from pathlib import Path

import fleet_executor as fx
import fleet_live as fl

FLEET_DIR = Path(__file__).resolve().parent
ACCOUNTS = json.loads((FLEET_DIR / "accounts.json").read_text(encoding="utf-8"))

# ACTIVE_SPY_ARMS was SIX_SPY_ARMS (6, incl. safe-1) before 2026-07-11's retirement.
ACTIVE_SPY_ARMS = {"safe-2", "safe-3", "risky-1", "risky-3", "bold-2"}
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


# --- the active arms exist as a clean grid --------------------------------------
def test_all_six_spy_arms_present_and_active():
    """Name kept for history (was a literal 6 pre-2026-07-11); now asserts the 5 currently-
    active SPY arms are present, AND that retired safe-1 is correctly excluded from 'active'."""
    active = {a["id"] for a in ACCOUNTS["arms"]
              if a.get("status") == "active" and a.get("instrument") == "SPY_0DTE_OPTION"}
    assert ACTIVE_SPY_ARMS <= active, f"missing arms: {ACTIVE_SPY_ARMS - active}"
    assert "safe-1" not in active, "safe-1 is retired (2026-07-11) -- must not read status=='active'"


def test_run_dry_addresses_all_six_arms():
    """The brain's perception fans out to every active SPY arm via run_dry (one signal -> 5
    cells as of 2026-07-11's safe-1 retirement, was 6)."""
    rows = fx.run_dry(_both_strategies_signal(), ACCOUNTS)
    addressed = {d.arm_id for d, _ in rows}
    assert ACTIVE_SPY_ARMS <= addressed, f"run_dry skipped: {ACTIVE_SPY_ARMS - addressed}"
    assert "safe-1" not in addressed, "run_dry must skip retired safe-1 (status filter)"


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
    # vwap pins updated 2026-07-09 (T-W6 option a port, STOP-B): full validated core cell
    # -0.06/+0.40/0.8/fixed (vwapcont-exit-ab-ship-gate.json, all 5 OP-22 gates PASS).
    # ribbon pins updated 2026-07-09 (SS-B structure-stop cell, STOP-B second ship):
    # distinctness now lives on stop_mode + TP1 (structure/+100% vs premium/+40%).
    assert plans["ribbon_ride"].exit_shape["premium_stop_pct"] == -0.20  # fallback field
    assert plans["vwap_continuation"].exit_shape["premium_stop_pct"] == -0.06
    assert plans["ribbon_ride"].exit_shape["tp1_premium_pct"] == 1.0
    assert plans["ribbon_ride"].exit_shape["stop_mode"] == "structure"
    assert plans["vwap_continuation"].exit_shape["tp1_premium_pct"] == 0.40


# --- the FLEET_OWNS_ALL_6 unification lever (no double-fill invariant) ---------
def test_default_fleet_processes_only_fleet_rest_arms():
    """DEFAULT (lever off): fleet_live processes ONLY the fleet_rest arms (3 as of
    2026-07-11's safe-1 retirement, was 4); the 2 mcp_heartbeat controls (safe-2/bold-2)
    are skipped (they're placed by the brain -> no double-fill)."""
    orig = fl.FLEET_OWNS_ALL_6
    try:
        fl.FLEET_OWNS_ALL_6 = False
        processable = {a["id"] for a in ACCOUNTS["arms"] if fl._arm_is_processable(a)}
        assert processable == {"safe-3", "risky-1", "risky-3"}
        assert "safe-1" not in processable, "safe-1 retired -- must never be processable again"
        assert "safe-2" not in processable and "bold-2" not in processable
    finally:
        fl.FLEET_OWNS_ALL_6 = orig


def test_lever_on_fleet_processes_all_six_arms():
    """Lever ON (the Path-B migration): fleet_live processes every active SPY arm (5 as of
    2026-07-11, was 6) -> the fleet is the ONE executor for every grid cell off the ONE brain."""
    orig = fl.FLEET_OWNS_ALL_6
    try:
        fl.FLEET_OWNS_ALL_6 = True
        processable = {a["id"] for a in ACCOUNTS["arms"] if fl._arm_is_processable(a)}
        assert ACTIVE_SPY_ARMS <= processable
        assert "safe-1" not in processable, "retired safe-1 must stay excluded even with the lever ON"
    finally:
        fl.FLEET_OWNS_ALL_6 = orig


# --- explicit safe-1-retirement guard (2026-07-11) ------------------------------
def test_safe1_is_retired_not_dispatched():
    """EXPLICIT GUARD for the 2026-07-11 safe-1 retirement (its account PA3DHPT7KIQE was
    reassigned to core Safe / safe-2). Pins THREE things so a future edit can't silently
    resurrect dispatch to safe-1:
      1. the roster still HAS a safe-1 entry (historical record preserved, not deleted)
         but its status is 'retired', not 'active'.
      2. the active fleet_rest roster is EXACTLY {safe-3, risky-1, risky-3} -- not safe-1.
      3. nothing in the executor's live dispatch paths (run_dry / fleet_live processability)
         ever addresses "safe-1", under either FLEET_OWNS_ALL_6 setting.
    """
    safe1 = next(a for a in ACCOUNTS["arms"] if a["id"] == "safe-1")
    assert safe1["status"] == "retired", "safe-1 must be present but retired, not deleted"
    # 2026-08-03 (J's full account wipe + $5K rebuild): the shared core-Safe account is now
    # PA3POKNV46VG (the old PA3DHPT7KIQE was deleted at the broker). The guard's INTENT is
    # unchanged and still pinned: safe-1 exists, is retired, and shares core Safe's CURRENT
    # account rather than carrying a live one of its own.
    safe2 = next(a for a in ACCOUNTS["arms"] if a["id"] == "safe-2")
    assert safe1["account_number"] == safe2["account_number"] == "PA3POKNV46VG"

    fleet_rest_active = {a["id"] for a in ACCOUNTS["arms"]
                          if a.get("status") == "active" and a.get("execution") == "fleet_rest"}
    assert fleet_rest_active == {"safe-3", "risky-1", "risky-3"}

    orig = fl.FLEET_OWNS_ALL_6
    try:
        for lever in (False, True):
            fl.FLEET_OWNS_ALL_6 = lever
            processable = {a["id"] for a in ACCOUNTS["arms"] if fl._arm_is_processable(a)}
            assert "safe-1" not in processable, f"safe-1 dispatched with FLEET_OWNS_ALL_6={lever}"
    finally:
        fl.FLEET_OWNS_ALL_6 = orig

    rows = fx.run_dry(_both_strategies_signal(), ACCOUNTS)
    addressed = {d.arm_id for d, _ in rows}
    assert "safe-1" not in addressed, "run_dry must never address retired safe-1"


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
