"""Per-account EXIT-shape correctness guard for all active SPY grid arms (J hard requirement 2).

Fast, deterministic, no orchestrator/pandas: for EVERY one of the 5 active SPY grid arms
(safe-2/3, risky-1, bold-2, risky-3 -- was 6 incl. safe-1 before its 2026-07-11 retirement;
its account PA3DHPT7KIQE was reassigned to core Safe/safe-2) the live executor (plan_all) must
thread each fired strategy's REGISTRY ExitShape through to the EntryPlan, PATCHED by this arm's
OWN accounts.json params_patch.exit_patch when it carries one -- because that exit_shape dict is
the exact input the live exit_manager/exit_actuator scale-out consumes (partial TP1 + runner +
profit-lock). A drift between the placed exit_shape and (registry [+ this arm's patch]) would
silently change the realized scale-out, so this is the contract that ties "the validated edge IS
its exit [+ each arm's disclosed A/B overlay]" to the live order path, for every account, off the
ONE brain.

EXIT-PARAMETER A/B (2026-07-20, J directive: "every fleet arm takes the SAME engine signals but
with DIFFERENT exit/risk parameters"): this INTENTIONALLY supersedes the pre-2026-07-20 "exit is
a property of the strategy, not the account, no per-account exit drift" invariant for any arm
carrying a non-empty exit_patch (today: safe-3, risky-3). Arms with NO exit_patch (safe-2, bold-2,
risky-1) are still held to registry-verbatim parity -- see EXPECTED_EXIT_SHAPE below, derived per
arm from ITS OWN accounts.json params_patch.exit_patch (single source of truth, never a second
hand-copied literal here). test_exit_patch_overlay.py is the dedicated vary-and-assert guard that
the patch actually REACHES the plan (differs from the unpatched registry) and that an unknown
exit_patch key raises at load.

Complements:
  * test_exit_manager.py        -- the pure 5-stage walk realizes the shape correctly.
  * test_exit_actuator.py       -- the live layer places exactly tp1_qty then runner (total == qty).
  * test_exit_patch_overlay.py  -- proves the per-arm exit_patch overlay reaches the plan + fails
                                    loud on an unknown key.
  * THIS file                   -- every account FEEDS the manager (registry [+ its own patch]),
                                    no UNDISCLOSED per-account exit drift.

Mirrors the offline harness backtest/validate_six_account_grid.py::_exit_correct in a unit form
(that harness pre-dates the 2026-07-20 exit_patch overlay -- see accounts.json's
update_note_2026_07_20 for the disclosed gap; it will legitimately report a mismatch for
safe-3/risky-3 until it's updated to read exit_patch too, which is by design, not a regression).
"""
from __future__ import annotations

import json
from pathlib import Path

import fleet_executor as fx
import strategies as strat_mod

FLEET_DIR = Path(__file__).resolve().parent
ACCOUNTS = json.loads((FLEET_DIR / "accounts.json").read_text(encoding="utf-8"))
# ACTIVE_SPY_ARMS was SIX_SPY_ARMS (6-tuple, incl. safe-1) before its 2026-07-11 retirement.
ACTIVE_SPY_ARMS = ("safe-2", "safe-3", "risky-1", "bold-2", "risky-3")


def _expected_exit_shape(arm_id: str, strategy_name: str) -> dict:
    """registry shape, shallow-patched by THIS arm's own accounts.json exit_patch (or
    unchanged when absent) -- the exact contract fleet_executor._exit_shape_dict implements."""
    base = strat_mod.by_name(strategy_name).exit.to_dict()
    patch = (_arm(arm_id).get("params_patch") or {}).get("exit_patch") or {}
    return {**base, **patch}

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
    for arm_id in ACTIVE_SPY_ARMS:
        shapes = _planned_exit_shapes(arm_id)
        assert set(shapes) == {"ribbon_ride", "vwap_continuation"}, \
            f"{arm_id} planned {sorted(shapes)}"


def test_every_arm_exit_shape_matches_registry_plus_its_own_patch():
    """The placed exit_shape per strategy == the REGISTRY ExitShape, patched by THIS arm's own
    accounts.json exit_patch when it has one (2026-07-20 A/B overlay) -- byte-identical to the
    registry for the 3 control arms (safe-2, bold-2, risky-1: no exit_patch), patched for the 2
    A/B arms (safe-3, risky-3). No UNDISCLOSED exit drift -- every difference traces to that
    arm's own accounts.json params_patch.exit_patch, nothing else."""
    for arm_id in ACTIVE_SPY_ARMS:
        shapes = _planned_exit_shapes(arm_id)
        for name, placed in shapes.items():
            expected = _expected_exit_shape(arm_id, name)
            assert placed == expected, f"{arm_id}/{name}: {placed} != expected {expected}"


def test_control_arms_stay_registry_verbatim():
    """PARITY INVARIANT preserved for arms with NO exit_patch: still byte-identical to the
    strategy's REGISTRY ExitShape, unaffected by the 2026-07-20 overlay mechanism existing.

    2026-07-31: risky-1 REMOVED from the control set. It gained the REACHABLE-TP1 exit_patch
    on 2026-07-29 (so this assertion had been stale/RED since then) and became the FULL-SEND
    arm on 2026-07-31. The CORE arms are the controls. The invariant itself is UNCHANGED --
    an exit_patch appearing on either core arm still fails loudly."""
    for arm_id in ("safe-2", "bold-2"):
        assert not (_arm(arm_id).get("params_patch") or {}).get("exit_patch"), (
            f"{arm_id} was expected to be a control arm (no exit_patch) -- update this test "
            "if that's an intentional accounts.json change"
        )
        shapes = _planned_exit_shapes(arm_id)
        for name, placed in shapes.items():
            registry = strat_mod.by_name(name).exit.to_dict()
            assert placed == registry, f"{arm_id}/{name}: {placed} != registry {registry}"


def test_exit_shape_is_full_5stage_contract():
    """Every threaded exit shape carries the FULL scale-out contract the manager needs:
    stop / TP1 partial fraction / runner profit-lock mode / runner target / chandelier trail."""
    required = {"premium_stop_pct", "tp1_premium_pct", "tp1_qty_fraction", "profit_lock_mode",
                "runner_target_pct", "trail_pct", "profit_lock_arm_pct"}
    for arm_id in ACTIVE_SPY_ARMS:
        for placed in _planned_exit_shapes(arm_id).values():
            assert required <= set(placed), f"{arm_id} exit shape missing {required - set(placed)}"


def test_ribbon_and_vwap_shapes_are_distinct_per_strategy_on_control_arms():
    """On the 3 CONTROL arms (no exit_patch), the two strategies still carry DISTINCT
    validated REGISTRY shapes (exit = strategy's property there): ribbon SS-B structure
    cell vs vwap -0.06/+0.40/0.8/fixed premium cell. Restricted to control arms because the
    2026-07-20 exit_patch overlay deliberately makes safe-3/risky-3 diverge from these exact
    registry pins by design (see test_patched_arms_ribbon_and_vwap_converge_on_stop_mode
    below) -- this test's job is now "the registry itself stays distinct per strategy",
    not "every arm reproduces it verbatim" (that was the pre-2026-07-20 invariant).

    vwap pins updated 2026-07-09 (T-W6 option a port, STOP-B): the FULL validated core cell
    (vwapcont-exit-ab-ship-gate.json 2026-07-07, all 5 OP-22 gates PASS; provenance
    markdown/audits/T-W6-VWAP-TWO-LANE-PROVENANCE-2026-07-08.md) replaced the stale
    -0.08/+0.30/0.667/trailing fleet copy.
    ribbon pins updated 2026-07-09 (SS-B structure-stop cell, STOP-B second ship:
    structure-stop-2026-07-09.json): stop_mode=structure + cat -50%, TP1 +100% sell66,
    trailing 15% runner. Distinctness now lives on the stop_mode axis too."""
    # 2026-07-31: risky-1 REMOVED from this control set. It stopped being a control on
    # 2026-07-29 (REACHABLE-TP1 exit_patch, tp1 1.0 -> 0.5) and this pin sat stale/RED from
    # then until now; on 2026-07-31 it also became the FULL-SEND arm. The CORE arms are the
    # controls. Not a weakening -- the registry pins below are unchanged and still asserted.
    for arm_id in ("safe-2", "bold-2"):
        s = _planned_exit_shapes(arm_id)
        assert s["ribbon_ride"]["premium_stop_pct"] == -0.20  # flag-OFF fallback field
        assert s["ribbon_ride"]["tp1_premium_pct"] == 1.0
        assert s["ribbon_ride"]["tp1_qty_fraction"] == 0.667
        assert s["ribbon_ride"]["profit_lock_mode"] == "trailing"
        assert s["ribbon_ride"]["stop_mode"] == "structure"
        assert s["ribbon_ride"]["catastrophe_stop_pct"] == -0.50
        assert s["vwap_continuation"]["premium_stop_pct"] == -0.06
        assert s["vwap_continuation"]["tp1_premium_pct"] == 0.40
        assert s["vwap_continuation"]["tp1_qty_fraction"] == 0.8
        assert s["vwap_continuation"]["profit_lock_mode"] == "fixed"
        assert s["vwap_continuation"].get("stop_mode", "premium") == "premium"


def test_patched_arms_ribbon_and_vwap_converge_on_stop_mode():
    """On safe-3/risky-3 (the 2026-07-20 exit_patch arms), BOTH strategies are forced onto
    stop_mode=structure + profit_lock_mode=trailing -- the exit_patch's whole point is to make
    every strategy trade this arm's chosen lane, not just ribbon_ride's own default. This is
    the mirror image of the control-arm test above: proves the patch actually reached BOTH
    strategies' placed shape, not just one."""
    for arm_id in ("safe-3", "risky-3"):
        s = _planned_exit_shapes(arm_id)
        for name in ("ribbon_ride", "vwap_continuation"):
            assert s[name]["stop_mode"] == "structure", f"{arm_id}/{name} stop_mode"
            assert s[name]["profit_lock_mode"] == "trailing", f"{arm_id}/{name} profit_lock_mode"
        # vwap_continuation is the strategy whose REGISTRY default (premium/fixed) the patch
        # actually overrides -- the discriminating proof the patch reached the plan, not a
        # coincidental match (ribbon_ride already defaults to structure/trailing).
        vwap_registry = strat_mod.by_name("vwap_continuation").exit.to_dict()
        assert s["vwap_continuation"]["stop_mode"] != vwap_registry["stop_mode"]
        assert s["vwap_continuation"]["profit_lock_mode"] != vwap_registry["profit_lock_mode"]


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
