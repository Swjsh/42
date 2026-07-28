"""Guards for backtest/tools/exit_armscope_ab_2026_07_28.py (EXIT-ARMSCOPE-TP1 pre-reg,
analysis/recommendations/prereg-exit-armscope-tp1-2026-07-28.json).

TWO LOAD-BEARING INVARIANTS THIS FILE PINS (frozen gates G5 + the cell-application check the
task brief required "at minimum"):

  1. G5 NO LOOK-AHEAD: the pre-TP1 ARM_SCOPE_FULL ratchet must never use a tick's OWN
     favorable extreme (point-sampled best_premium == worst_premium, per exit_manager_walk.py's
     documented convention) to justify an exit trigger on that SAME tick -- the exact class of
     defect the 2026-07-09 SIM-EXIT-SHAPE-PARITY finding identified in simulator_real.py (which
     ratchets off bar.high then checks bar.low in the same bar). Pinned two ways: a direct
     em.plan_exit_actions unit test (full control over the tick sequence) and a walk_exit_manager
     integration test (the actual harness path).

  2. CELL-APPLICATION GUARD (C14 "dead/translated-but-unapplied knob" class): build_cells()
     must produce 4 genuinely DIFFERENT exit shapes (not 4 copies of the same dict by accident),
     and E1's profit_lock_arm_scope="full" must actually change what walk_exit_manager DOES on
     a synthetic incident-shaped fixture (favorable run-up, TP1 never reached, round-trip back
     down) -- not just a static dict diff that never gets threaded through.

Also pins exit_family()'s new PROFIT_LOCK_FLOOR_PRE_TP1 bucket (E1/E3-only exit stage CONTROL/E2
can never produce) and decide_arming()'s tie-break/null-result logic.

EXTENDED for ITERATION 2 (EXIT-ARM-THRESHOLD, analysis/recommendations/prereg-exit-armpct-
2026-07-28.json, commit e6ae43bf): backtest/tools/exit_armpct_ab_2026_07_28.py reuses this
file's population/ribbon/today's-trade machinery via `import exit_armscope_ab_2026_07_28 as ab1`
and adds a NEW arm_pct threshold axis (F1=0.20/F2=0.30/F3=0.40, both arm_scope AND arm_pct moved
per cell) plus a NEW global G7 dose-response gate. The iteration-2 test section below (marked
"ITERATION 2") pins that new surface -- build_cells' two-key isolation shape, the arm_pct-
parameterized look-ahead guard, assess_dose_response()'s coherence buckets, and decide_arming()'s
G4-uniform-fail / G7-incoherent short-circuits -- reusing this file's CONTROL_SHAPE/_opt_df/
_spy_df helpers verbatim rather than redefining them. Iteration-2-specific helpers/tests that
would otherwise collide by name with the iteration-1 tests above are suffixed `_armpct`.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (REPO, REPO / "backtest", REPO / "backtest" / "lib", REPO / "backtest" / "tools", FLEET_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import exit_manager as em  # noqa: E402
import exit_armscope_ab_2026_07_28 as ab  # noqa: E402
import exit_armpct_ab_2026_07_28 as abp  # noqa: E402  -- iteration 2
from exit_manager_walk import walk_exit_manager  # noqa: E402

CONTROL_SHAPE = {
    "premium_stop_pct": -0.20, "tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667,
    "profit_lock_mode": "trailing", "runner_target_pct": 99.0, "trail_pct": 0.15,
    "profit_lock_arm_pct": 0.05, "stop_mode": "structure", "catastrophe_stop_pct": -0.50,
    "profit_lock_arm_scope": "post_tp1",
}


# ---------------------------------------------------------------------------------------------
# G5 -- no look-ahead, direct em.plan_exit_actions unit test (full per-tick control)
# ---------------------------------------------------------------------------------------------
def _full_scope_shape(**overrides) -> dict:
    base = {
        "premium_stop_pct": -0.20, "tp1_premium_pct": 99.0, "tp1_qty_fraction": 0.667,
        "profit_lock_mode": "trailing", "runner_target_pct": 99.0, "trail_pct": 0.15,
        "profit_lock_arm_pct": 0.05, "stop_mode": "premium",
        "profit_lock_arm_scope": em.ARM_SCOPE_FULL,
    }
    base.update(overrides)
    return base


def test_full_scope_ratchet_cannot_trigger_exit_on_same_tick_as_new_hwm():
    """The mechanism: ARM_SCOPE_FULL ratchets runner_stop toward hwm*(1-trail_pct) using THIS
    tick's best_premium (point-sampled), then checks worst_premium (== best_premium under the
    point-sample convention) against the ratcheted stop. Since trail_pct > 0, floor =
    value*(1-trail_pct) is ALWAYS strictly < value -- a same-tick ratchet from this tick's own
    favorable extreme can never also breach the floor it just set."""
    state = em.ExitState.from_entry(
        symbol="SPY260101C00600000", side="C", entry_premium=1.00, qty=3,
        exit_shape=_full_scope_shape(), strategy="ribbon_ride")

    # tick that sets a big new favorable extreme (best=worst=1.30, point-sample convention)
    dec = em.plan_exit_actions(state, best_premium=1.30, worst_premium=1.30, open_qty=3,
                                now_et=dt.time(12, 5))
    assert not any(a.kind == "SELL_ALL" for a in dec.actions), (
        "same-tick look-ahead: the ratchet used this tick's own favorable extreme to set the "
        "floor AND the same tick's value tripped that floor -- impossible if the arithmetic is right")
    assert dec.state.runner_stop_premium < 1.30, "the new floor must sit strictly below the tick's own value"
    assert any(a.kind == "RATCHET_STOP" for a in dec.actions), (
        "expected the pre-TP1 full-scope ratchet to be recorded this tick")

    # NEXT tick: price recedes below the floor JUST set on the PRIOR tick -> now it's allowed to exit
    dec2 = em.plan_exit_actions(dec.state, best_premium=0.90, worst_premium=0.90, open_qty=3,
                                 now_et=dt.time(12, 10))
    assert any(a.kind == "SELL_ALL" and a.stage == "profit_lock_floor" for a in dec2.actions), (
        "positive control: the floor must be a REAL, enforceable stop on a LATER tick -- "
        "otherwise the no-look-ahead test above would be vacuous (the floor never fires at all)")


def test_naive_high_low_feed_WOULD_look_ahead_proving_the_guard_is_not_vacuous():
    """RED-proof for the test above: em.plan_exit_actions is NOT inherently look-ahead-safe --
    if fed the OLD simulator_real-style bar EXTREMES (best=bar.high, worst=bar.low, same bar)
    instead of exit_manager_walk's point-sample (best=worst=bar.open), it DOES ratchet off the
    high and immediately trip the floor via the SAME bar's low -- the exact 2026-07-09
    SIM-EXIT-SHAPE-PARITY defect class. This proves the protection above comes specifically
    from the point-sample convention, not from some inherent property of plan_exit_actions --
    so the guard test is pinning something real, not a vacuous invariant."""
    state = em.ExitState.from_entry(
        symbol="SPY260101C00600000", side="C", entry_premium=1.00, qty=3,
        exit_shape=_full_scope_shape(), strategy="ribbon_ride")
    dec = em.plan_exit_actions(state, best_premium=1.30, worst_premium=0.90, open_qty=3,
                                now_et=dt.time(12, 5))
    assert any(a.kind == "SELL_ALL" for a in dec.actions), (
        "expected the naive high/low feed to look-ahead-exit same-tick -- if this no longer "
        "reproduces, the contrast this guard relies on has changed and needs re-verification")


def test_full_scope_ratchet_floor_always_strictly_below_the_tick_that_set_it():
    """Algebraic form of the same invariant, swept over several HWM values -- guards against a
    future edit that removes the '< hwm' margin (e.g. an off-by-one that uses >= instead of >
    somewhere in the ratchet chain)."""
    for hwm_tick in (1.05, 1.30, 1.60, 2.00, 5.00):
        state = em.ExitState.from_entry(
            symbol="SPY260101C00600000", side="C", entry_premium=1.00, qty=3,
            exit_shape=_full_scope_shape(), strategy="ribbon_ride")
        dec = em.plan_exit_actions(state, best_premium=hwm_tick, worst_premium=hwm_tick,
                                    open_qty=3, now_et=dt.time(12, 5))
        assert not any(a.kind == "SELL_ALL" for a in dec.actions), f"look-ahead fired at hwm={hwm_tick}"


# ---------------------------------------------------------------------------------------------
# G5 -- integration test through the actual harness path (walk_exit_manager over synthetic bars)
# ---------------------------------------------------------------------------------------------
def _opt_df(opens: list) -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp_et": pd.to_datetime([t for t, _ in opens]),
        "open": [o for _, o in opens], "high": [o for _, o in opens],
        "low": [o for _, o in opens], "close": [o for _, o in opens],
    })


def _spy_df(times: list) -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp_et": pd.to_datetime(times),
        "open": [600.0] * len(times), "high": [600.5] * len(times),
        "low": [599.5] * len(times), "close": [600.0] * len(times),
    })


def test_walk_exit_manager_integration_exit_lands_on_the_receding_bar_not_the_hwm_bar():
    """Same scenario driven through the real walk_exit_manager harness: entry, then a bar that
    sets a big new HWM (must NOT resolve the position), then a bar that recedes below the floor
    just set (MUST resolve, and must be timestamped on ITS OWN bar, never the HWM bar)."""
    times = ["2026-01-01 12:00:00", "2026-01-01 12:05:00", "2026-01-01 12:10:00"]
    res = walk_exit_manager(
        symbol="SPY260101P00600000", side="P", entry_time_et=dt.datetime(2026, 1, 1, 12, 0, 0),
        entry_premium=1.00, qty=3, exit_shape=_full_scope_shape(), structure_stop_enabled=False,
        trigger_level=None, strategy="ribbon_ride", time_stop_et=dt.time(15, 40),
        opt_df=_opt_df([(times[0], 1.00), (times[1], 1.30), (times[2], 0.90)]),
        ribbon_tick_df=None, five_min_spy_df=_spy_df(times))
    assert res.resolved is True
    assert "profit_lock_floor" in res.exit_reason
    assert pd.Timestamp(res.exit_time_et) == pd.Timestamp(times[2]), (
        "the exit must land on the RECEDING bar, not the bar that set the new HWM "
        f"(got {res.exit_time_et}, HWM bar was {times[1]})")


def test_walk_exit_manager_integration_hwm_bar_alone_cannot_resolve():
    """If the series ends right after the HWM-setting bar (no receding bar at all), the position
    must NOT have resolved via that bar -- proves the HWM bar genuinely cannot self-trigger."""
    times = ["2026-01-01 12:00:00", "2026-01-01 12:05:00"]
    res = walk_exit_manager(
        symbol="SPY260101P00600000", side="P", entry_time_et=dt.datetime(2026, 1, 1, 12, 0, 0),
        entry_premium=1.00, qty=3, exit_shape=_full_scope_shape(), structure_stop_enabled=False,
        trigger_level=None, strategy="ribbon_ride", time_stop_et=dt.time(15, 40),
        opt_df=_opt_df([(times[0], 1.00), (times[1], 1.30)]),
        ribbon_tick_df=None, five_min_spy_df=_spy_df(times))
    # only resolution possible here is "data_exhausted_force_close" at the HWM bar's own close
    # (1.30, a WINNING force-close) -- never a profit_lock_floor SELL_ALL on that same bar.
    assert "profit_lock_floor" not in res.exit_reason


# ---------------------------------------------------------------------------------------------
# cell-application guard: build_cells() isolates exactly the named key(s); E1 actually changes
# the WALKED outcome relative to CONTROL on an incident-shaped fixture, not just the dict
# ---------------------------------------------------------------------------------------------
def test_build_cells_control_is_a_copy_not_an_alias():
    cells = ab.build_cells(CONTROL_SHAPE)
    assert cells["CONTROL"] == CONTROL_SHAPE
    assert cells["CONTROL"] is not CONTROL_SHAPE


def test_build_cells_e1_isolates_arm_scope_only():
    cells = ab.build_cells(CONTROL_SHAPE)
    e1 = cells["E1"]
    assert e1["profit_lock_arm_scope"] == em.ARM_SCOPE_FULL
    assert e1["tp1_premium_pct"] == CONTROL_SHAPE["tp1_premium_pct"], "E1 must not touch tp1"
    for k in ("trail_pct", "profit_lock_arm_pct", "catastrophe_stop_pct", "stop_mode"):
        assert e1[k] == CONTROL_SHAPE[k], f"no_other_knobs violated: E1 moved {k}"


def test_build_cells_e2_isolates_tp1_only():
    cells = ab.build_cells(CONTROL_SHAPE)
    e2 = cells["E2"]
    assert e2["tp1_premium_pct"] == 0.5
    assert e2["profit_lock_arm_scope"] == CONTROL_SHAPE["profit_lock_arm_scope"], "E2 must not touch arm_scope"
    for k in ("trail_pct", "profit_lock_arm_pct", "catastrophe_stop_pct", "stop_mode"):
        assert e2[k] == CONTROL_SHAPE[k], f"no_other_knobs violated: E2 moved {k}"


def test_build_cells_e3_sets_both_and_only_both():
    cells = ab.build_cells(CONTROL_SHAPE)
    e3 = cells["E3"]
    assert e3["profit_lock_arm_scope"] == em.ARM_SCOPE_FULL
    assert e3["tp1_premium_pct"] == 0.5
    for k in ("trail_pct", "profit_lock_arm_pct", "catastrophe_stop_pct", "stop_mode"):
        assert e3[k] == CONTROL_SHAPE[k], f"no_other_knobs violated: E3 moved {k}"


def test_build_cells_all_four_shapes_are_genuinely_distinct_objects():
    cells = ab.build_cells(CONTROL_SHAPE)
    dicts = list(cells.values())
    for i, a_ in enumerate(dicts):
        for j, b_ in enumerate(dicts):
            if i != j:
                assert a_ is not b_, "build_cells must never alias two cells to the same dict"


def test_e1_shape_actually_changes_the_walked_outcome_on_an_incident_shaped_fixture():
    """The whole point of this pre-reg: prove E1's shape (as it comes out of build_cells) is
    not a dead/translated-but-unapplied knob (C14). Fixture mirrors today's real incident shape
    -- runs up well past the arm threshold, never reaches TP1 (+100%), then gives most of it
    back -- and asserts walk_exit_manager (the ACTUAL harness path this pre-reg's tool uses)
    produces a DIFFERENT, BETTER outcome under E1 than CONTROL."""
    times = ["2026-01-01 12:00:00", "2026-01-01 12:05:00", "2026-01-01 12:10:00",
             "2026-01-01 12:15:00", "2026-01-01 12:20:00"]
    # 1.00 entry -> 1.60 (+60%, well past arm 5%, well short of CONTROL's tp1 @ 2.00) -> back to 0.80
    opens = [(times[0], 1.00), (times[1], 1.60), (times[2], 1.50), (times[3], 1.10), (times[4], 0.80)]
    cells = ab.build_cells(CONTROL_SHAPE)
    common = dict(symbol="SPY260101C00600000", side="C", entry_time_et=dt.datetime(2026, 1, 1, 12, 0, 0),
                  entry_premium=1.00, qty=3, structure_stop_enabled=False, trigger_level=None,
                  strategy="ribbon_ride", time_stop_et=dt.time(15, 40),
                  opt_df=_opt_df(opens), ribbon_tick_df=None, five_min_spy_df=_spy_df(times))
    ctl = walk_exit_manager(exit_shape=cells["CONTROL"], **common)
    e1 = walk_exit_manager(exit_shape=cells["E1"], **common)
    assert ctl.exit_reason != e1.exit_reason, "E1's shape produced the IDENTICAL walk outcome as CONTROL -- dead knob"
    assert e1.dollar_pnl > ctl.dollar_pnl, (
        f"expected E1 (arm_scope=full) to lock in some of the run-up better than CONTROL "
        f"(unarmed pre-TP1) on this incident-shaped fixture: ctl={ctl.dollar_pnl} e1={e1.dollar_pnl}")
    assert "profit_lock_floor" in e1.exit_reason
    assert "profit_lock_floor" not in ctl.exit_reason, "CONTROL must never emit profit_lock_floor pre-TP1 (arm_scope=post_tp1)"


# ---------------------------------------------------------------------------------------------
# exit_family() -- the NEW bucket this file adds on top of exit_leak_decompose.py's version
# ---------------------------------------------------------------------------------------------
def test_exit_family_profit_lock_floor_is_a_distinct_new_bucket():
    assert ab.exit_family("profit_lock_floor @ 1.38", "structure") == "PROFIT_LOCK_FLOOR_PRE_TP1"


def test_exit_family_plain_premium_stop_unaffected():
    assert ab.exit_family("premium_stop @ 0.80", "premium") == "PREMIUM_STOP_20"
    assert ab.exit_family("premium_stop @ 0.69", "structure") == "CATASTROPHE_50"


def test_exit_family_runner_and_structure_unaffected():
    assert ab.exit_family("runner_stop @ 1.84", "structure") == "RUNNER_TRAIL"
    assert ab.exit_family("structure_stop @ 741.0", "structure") == "STRUCTURE_STOP"


# ---------------------------------------------------------------------------------------------
# decide_arming() -- pure logic: tie-break-to-simpler and the null-result path
# ---------------------------------------------------------------------------------------------
def _fake_report(delta: float, n_keys: int, clears: bool) -> dict:
    return {"g1_positive_aggregate": {"delta": delta}, "n_keys_changed": n_keys,
            "clears_all_required_gates": clears}


def test_decide_arming_arms_nothing_when_no_cell_clears():
    reports = {"E1": _fake_report(-100.0, 1, False), "E2": _fake_report(-50.0, 1, False),
               "E3": _fake_report(-200.0, 2, False)}
    v = ab.decide_arming(reports)
    assert v["decision"] == "ARM_NOTHING"
    assert v["cell"] is None


def test_decide_arming_picks_best_performer_when_not_tied():
    reports = {"E1": _fake_report(100.0, 1, True), "E2": _fake_report(500.0, 1, True),
               "E3": _fake_report(200.0, 2, True)}
    v = ab.decide_arming(reports)
    assert v["decision"] == "ARM"
    assert v["cell"] == "E2"


def test_decide_arming_prefers_simpler_cell_on_practical_tie():
    # E1 (1 key) and E3 (2 keys) are within the $25 practical-tie band -> must prefer E1
    reports = {"E1": _fake_report(500.0, 1, True), "E2": _fake_report(100.0, 1, True),
               "E3": _fake_report(510.0, 2, True)}
    v = ab.decide_arming(reports)
    assert v["decision"] == "ARM"
    assert v["cell"] == "E1", "must prefer the simpler cell (fewer keys changed) on a practical tie"


# ---------------------------------------------------------------------------------------------
# RED-proof anchors on the shipped scorecard, if present (mirrors trail_width_exit_ab's pattern)
# ---------------------------------------------------------------------------------------------
def test_shipped_scorecard_control_reconciles_and_runner_anchor_matches():
    if not ab.OUT_JSON.exists():
        return
    d = json.loads(ab.OUT_JSON.read_text(encoding="utf-8"))
    assert d["population"]["n_control_mismatch_vs_source"] == 0, (
        "CONTROL cell drifted from the frozen source population -- do not trust this scorecard")
    rc = d["runner_cohort"]
    assert rc["anchor_check"]["n_matches"] is True
    assert rc["anchor_check"]["pnl_matches"] is True
    assert d["arming_recommendation"]["decision"] in ("ARM", "ARM_NOTHING")


def test_shipped_scorecard_g4_gate_is_the_hard_veto_it_claims_to_be():
    """If a cell's aggregate (G1) is positive but its runner-cohort delta (G4) is negative,
    it must NOT be arm-eligible -- pins that clears_all_required_gates actually ANDs in G4
    rather than only checking G1 (the exact 'gate that doesn't actually gate' failure mode)."""
    if not ab.OUT_JSON.exists():
        return
    d = json.loads(ab.OUT_JSON.read_text(encoding="utf-8"))
    for cell in ("E1", "E2", "E3"):
        g = d["gates"][cell]
        if not g["g4_runner_cohort_no_regression"]["pass"]:
            assert g["clears_all_required_gates"] is False, (
                f"{cell} failed G4 (runner-tail regression) but was still marked as clearing "
                "all required gates -- G4 must be a hard veto per the frozen pre-reg")


# =================================================================================================
# ITERATION 2 -- backtest/tools/exit_armpct_ab_2026_07_28.py (EXIT-ARM-THRESHOLD, F1=0.20/F2=0.30/
# F3=0.40, both profit_lock_arm_scope AND profit_lock_arm_pct moved per cell; NEW global G7
# dose-response gate). Reuses this file's CONTROL_SHAPE/_opt_df/_spy_df verbatim.
# =================================================================================================

# ---------------------------------------------------------------------------------------------
# build_cells() -- TWO-key isolation shape (arm_scope AND arm_pct), distinct from iteration 1
# (whose E1/E2/E3 each moved exactly ONE key)
# ---------------------------------------------------------------------------------------------
def test_build_cells_control_is_a_copy_not_an_alias_armpct():
    cells = abp.build_cells(CONTROL_SHAPE)
    assert cells["CONTROL"] == CONTROL_SHAPE
    assert cells["CONTROL"] is not CONTROL_SHAPE


def test_build_cells_f1_f2_f3_isolate_exactly_scope_and_arm_pct():
    cells = abp.build_cells(CONTROL_SHAPE)
    expected_arm_pct = {"F1": 0.20, "F2": 0.30, "F3": 0.40}
    for name, arm_pct in expected_arm_pct.items():
        shape = cells[name]
        assert shape["profit_lock_arm_scope"] == em.ARM_SCOPE_FULL, f"{name} must arm full-scope"
        assert shape["profit_lock_arm_pct"] == arm_pct, f"{name} must arm at {arm_pct}"
        for k in ("trail_pct", "catastrophe_stop_pct", "stop_mode", "tp1_premium_pct",
                  "tp1_qty_fraction", "premium_stop_pct", "profit_lock_mode", "runner_target_pct"):
            assert shape[k] == CONTROL_SHAPE[k], f"no_other_knobs violated: {name} moved {k}"


def test_build_cells_all_four_shapes_are_genuinely_distinct_objects_armpct():
    cells = abp.build_cells(CONTROL_SHAPE)
    dicts = list(cells.values())
    for i, a_ in enumerate(dicts):
        for j, b_ in enumerate(dicts):
            if i != j:
                assert a_ is not b_, "build_cells must never alias two cells to the same dict"
                assert a_ != b_, "build_cells must never produce two cells with identical shapes"


# ---------------------------------------------------------------------------------------------
# G5 no-look-ahead re-asserted at the THREE NEW arm_pct thresholds (algebra is arm-pct-
# independent -- floor = hwm*(1-trail_pct) < hwm for ANY trail_pct>0 -- but that claim is
# VERIFIED here at each threshold, not assumed from iteration 1's single-threshold proof)
# ---------------------------------------------------------------------------------------------
def _armpct_full_scope_shape(arm_pct: float, **overrides) -> dict:
    base = {
        "premium_stop_pct": -0.20, "tp1_premium_pct": 99.0, "tp1_qty_fraction": 0.667,
        "profit_lock_mode": "trailing", "runner_target_pct": 99.0, "trail_pct": 0.15,
        "profit_lock_arm_pct": arm_pct, "stop_mode": "premium",
        "profit_lock_arm_scope": em.ARM_SCOPE_FULL,
    }
    base.update(overrides)
    return base


def test_ratchet_cannot_trigger_exit_on_same_tick_as_new_hwm_at_all_three_thresholds():
    for arm_pct in (0.20, 0.30, 0.40):
        state = em.ExitState.from_entry(
            symbol="SPY260101C00600000", side="C", entry_premium=1.00, qty=3,
            exit_shape=_armpct_full_scope_shape(arm_pct), strategy="ribbon_ride")
        # tick that runs up well past THIS threshold (point-sample: best=worst=hwm_tick)
        hwm_tick = 1.00 * (1.0 + arm_pct) + 0.50
        dec = em.plan_exit_actions(state, best_premium=hwm_tick, worst_premium=hwm_tick,
                                    open_qty=3, now_et=dt.time(12, 5))
        assert not any(a.kind == "SELL_ALL" for a in dec.actions), (
            f"same-tick look-ahead at arm_pct={arm_pct}: the ratchet used this tick's own "
            "favorable extreme to set the floor AND the same tick's value tripped that floor")
        assert dec.state.runner_stop_premium < hwm_tick, (
            f"floor must sit strictly below the tick's own value at arm_pct={arm_pct}")

        # NEXT tick: price recedes below the floor JUST set -> now allowed to exit (positive
        # control -- proves the guard above isn't vacuous at this threshold either)
        receded = dec.state.runner_stop_premium - 0.05
        dec2 = em.plan_exit_actions(dec.state, best_premium=receded, worst_premium=receded,
                                     open_qty=3, now_et=dt.time(12, 10))
        assert any(a.kind == "SELL_ALL" and a.stage == "profit_lock_floor" for a in dec2.actions), (
            f"positive control failed at arm_pct={arm_pct}: floor never fires on a later tick")


def test_below_threshold_tick_never_arms_at_any_of_the_three_new_thresholds():
    """A run-up that clears the LOWEST tested threshold (0.20) but stays below the HIGHER ones
    must arm F1 while leaving F2/F3 unarmed on that same tick -- proves the three cells are
    actually threshold-differentiated, not accidentally identical (C14 dead-knob class)."""
    for arm_pct, should_arm in ((0.20, True), (0.30, False), (0.40, False)):
        state = em.ExitState.from_entry(
            symbol="SPY260101C00600000", side="C", entry_premium=1.00, qty=3,
            exit_shape=_armpct_full_scope_shape(arm_pct), strategy="ribbon_ride")
        dec = em.plan_exit_actions(state, best_premium=1.25, worst_premium=1.25, open_qty=3,
                                    now_et=dt.time(12, 5))  # +25% favor
        assert dec.state.profit_lock_armed is should_arm, (
            f"arm_pct={arm_pct}: expected profit_lock_armed={should_arm} at +25% favor")


# ---------------------------------------------------------------------------------------------
# G5 -- integration test through walk_exit_manager at F2's threshold (0.30), the middle cell
# (reuses this file's _opt_df/_spy_df helpers verbatim)
# ---------------------------------------------------------------------------------------------
def test_walk_exit_manager_integration_at_f2_threshold_exit_lands_on_receding_bar():
    times = ["2026-01-01 12:00:00", "2026-01-01 12:05:00", "2026-01-01 12:10:00"]
    res = walk_exit_manager(
        symbol="SPY260101P00600000", side="P", entry_time_et=dt.datetime(2026, 1, 1, 12, 0, 0),
        entry_premium=1.00, qty=3, exit_shape=_armpct_full_scope_shape(0.30),
        structure_stop_enabled=False, trigger_level=None, strategy="ribbon_ride",
        time_stop_et=dt.time(15, 40),
        opt_df=_opt_df([(times[0], 1.00), (times[1], 1.40), (times[2], 1.00)]),
        ribbon_tick_df=None, five_min_spy_df=_spy_df(times))
    assert res.resolved is True
    assert "profit_lock_floor" in res.exit_reason
    assert pd.Timestamp(res.exit_time_et) == pd.Timestamp(times[2]), (
        "exit must land on the RECEDING bar, not the HWM bar")


def test_f1_f2_f3_shapes_actually_change_the_walked_outcome_vs_control():
    """C14 dead-knob check for iteration 2's shapes: F1 (lowest threshold, 0.20) must arm and
    get whipsawed out on an EARLY partial pullback that never reaches F2/F3's higher thresholds
    (0.30/0.40, so they stay unarmed through it), then price resumes and clears F2/F3's
    thresholds before a SECOND, deeper pullback resolves them at a materially different (higher)
    floor than F1's. A fixture that jumps straight past all three thresholds in one tick (as a
    naive version of this test would) makes F1/F2/F3 arm simultaneously and converge to the SAME
    hwm-based trailing floor regardless of arm_pct -- which would prove nothing about
    profit_lock_arm_pct actually being threaded through. This two-stage run-up is required
    specifically to distinguish 'arm timing differs' from 'arm timing is irrelevant once armed'
    (the latter being expected, documented behavior of the trailing-mode ratchet, not a defect)."""
    times = ["2026-01-01 12:00:00", "2026-01-01 12:05:00", "2026-01-01 12:10:00",
             "2026-01-01 12:15:00", "2026-01-01 12:20:00"]
    # 1.00 entry -> 1.25 (+25%: clears F1's 0.20 arm ONLY) -> 0.95 (partial pullback: trips
    # F1's freshly-armed floor ~1.0625; F2/F3 unarmed, no exit) -> 1.70 (clears F2's 0.30 AND
    # F3's 0.40 arm, both now trail off hwm=1.70) -> 1.10 (trips F2/F3's floor ~1.445, well
    # above F1's earlier exit level -- distinct dollar outcome)
    opens = [(times[0], 1.00), (times[1], 1.25), (times[2], 0.95), (times[3], 1.70), (times[4], 1.10)]
    cells = abp.build_cells(CONTROL_SHAPE)
    common = dict(symbol="SPY260101C00600000", side="C", entry_time_et=dt.datetime(2026, 1, 1, 12, 0, 0),
                  entry_premium=1.00, qty=3, structure_stop_enabled=False, trigger_level=None,
                  strategy="ribbon_ride", time_stop_et=dt.time(15, 40),
                  opt_df=_opt_df(opens), ribbon_tick_df=None, five_min_spy_df=_spy_df(times))
    ctl = walk_exit_manager(exit_shape=cells["CONTROL"], **common)
    assert "profit_lock_floor" not in ctl.exit_reason, "CONTROL must never emit profit_lock_floor pre-TP1"
    # NOTE: this test deliberately does NOT assert F-cells beat CONTROL in dollar terms -- that
    # direction is an empirical question this exact pre-reg exists to answer (and the real
    # 2026-07-28 run found pre-TP1 arming can make a still-rising winner WORSE off, which is the
    # whole G4 runner-cohort finding). The dead-knob check below only proves profit_lock_arm_pct
    # is actually threaded through and produces mechanically DIFFERENT walked outcomes -- not
    # that those outcomes are better.
    results = {}
    for name in ("F1", "F2", "F3"):
        r = walk_exit_manager(exit_shape=cells[name], **common)
        assert r.exit_reason != ctl.exit_reason, f"{name} produced the IDENTICAL outcome as CONTROL -- dead knob"
        assert "profit_lock_floor" in r.exit_reason
        results[name] = r.dollar_pnl
    assert len({results["F1"], results["F2"], results["F3"]}) > 1, (
        "F1/F2/F3 collapsed to the SAME dollar outcome on a fixture that should differentiate "
        "them by arm timing -- profit_lock_arm_pct may not be threaded through")
    assert results["F1"] < results["F2"], (
        "F1 (armed earliest, whipsawed by the small mid-fixture pullback) should lock a lower "
        "floor than F2 (armed later at a higher HWM) -- if not, arm timing isn't differentiating "
        "outcomes the way the fixture intends")


# ---------------------------------------------------------------------------------------------
# assess_dose_response() -- pure coherence logic, including the pre-reg's own worked example
# ---------------------------------------------------------------------------------------------
def test_dose_response_monotonic_improving_is_coherent():
    d = abp.assess_dose_response({"F1": -100.0, "F2": -50.0, "F3": 0.0}, "test")
    assert d["coherent"] is True
    assert d["shape"] == "monotonic_improving_with_higher_arm_pct"


def test_dose_response_monotonic_worsening_is_coherent():
    d = abp.assess_dose_response({"F1": 100.0, "F2": 50.0, "F3": 0.0}, "test")
    assert d["coherent"] is True
    assert d["shape"] == "monotonic_worsening_with_higher_arm_pct"


def test_dose_response_flat_is_coherent():
    d = abp.assess_dose_response({"F1": 10.0, "F2": 10.5, "F3": 9.7}, "test")
    assert d["coherent"] is True
    assert d["shape"] == "flat"


def test_dose_response_prereg_worked_example_is_a_spike_noise():
    """The pre-reg's OWN example: '0.30 positive while 0.20 and 0.40 are both sharply
    negative' -- must classify as the spike/NOISE shape, not coherent."""
    d = abp.assess_dose_response({"F1": -1000.0, "F2": 800.0, "F3": -900.0}, "test")
    assert d["coherent"] is False
    assert d["shape"] == "non_monotonic_spike_at_F2_NOISE"


def test_dose_response_small_wiggle_within_tolerance_not_flagged_as_spike():
    """A sub-$250 wiggle around a roughly-flat line must NOT be flagged as a material spike --
    guards against DOSE_RESPONSE_SPIKE_MATERIAL being set too low and flagging noise-level float
    jitter as a false 'incoherent' verdict."""
    d = abp.assess_dose_response({"F1": 100.0, "F2": 150.0, "F3": 90.0}, "test")
    # non-monotonic (150 > both 100 and 90) but NOT beyond the $250 material band either side
    assert d["shape"] == "irregular_non_monotonic"
    assert d["coherent"] is False  # still non-monotonic, just not classified as a dramatic spike


# ---------------------------------------------------------------------------------------------
# decide_arming() -- G4-uniform-fail short-circuit (the actual shape of the real 2026-07-28 run)
# and the G7-incoherent-runner-axis short-circuit, both NEW vs iteration 1's decide_arming
# ---------------------------------------------------------------------------------------------
def _fake_armpct_report(agg_delta: float, g4_delta: float, g4_pass: bool, clears: bool) -> dict:
    return {"g1_positive_aggregate": {"delta": agg_delta},
            "g4_runner_cohort_no_regression": {"delta": g4_delta, "pass": g4_pass},
            "clears_all_required_gates": clears}


def test_decide_arming_g4_uniform_fail_short_circuits_with_named_reason():
    """Mirrors the real 2026-07-28 run's actual shape: G7-runner coherent, but G4 fails on
    every cell -- must ARM NOTHING and the reason string must name G4 explicitly (not just
    fall through to a generic 'no cell cleared' message that hides WHY)."""
    reports = {"F1": _fake_armpct_report(-43.2, -6700.9, False, False),
               "F2": _fake_armpct_report(1807.1, -4888.5, False, False),
               "F3": _fake_armpct_report(1324.55, -3897.55, False, False)}
    dose_runner = abp.assess_dose_response({"F1": -6700.9, "F2": -4888.5, "F3": -3897.55}, "runner")
    dose_agg = abp.assess_dose_response({"F1": -43.2, "F2": 1807.1, "F3": 1324.55}, "agg")
    assert dose_runner["coherent"] is True   # sanity: this scenario's runner axis IS coherent
    assert dose_agg["coherent"] is False     # ...but the aggregate axis is the spike/noise case
    v = abp.decide_arming(reports, dose_runner, dose_agg)
    assert v["decision"] == "ARM_NOTHING"
    assert v["cell"] is None
    assert "G4" in v["reason"], "reason must name G4 as the binding cause, not a generic message"
    assert "NOISE" in v["reason"], "reason must flag the aggregate-axis spike as noise"


def test_decide_arming_g7_incoherent_runner_axis_arms_nothing_even_if_a_cell_individually_clears():
    """If the DECIDING (runner-cohort) axis itself is incoherent, ARM NOTHING regardless of any
    individual cell's own G1-G6 arithmetic -- G7 is a GLOBAL veto, not a per-cell one."""
    reports = {"F1": _fake_armpct_report(-1000.0, -1000.0, False, False),
               "F2": _fake_armpct_report(800.0, 800.0, True, True),   # would otherwise ARM
               "F3": _fake_armpct_report(-900.0, -900.0, False, False)}
    dose_runner = abp.assess_dose_response({"F1": -1000.0, "F2": 800.0, "F3": -900.0}, "runner")
    dose_agg = abp.assess_dose_response({"F1": -1000.0, "F2": 800.0, "F3": -900.0}, "agg")
    assert dose_runner["coherent"] is False
    v = abp.decide_arming(reports, dose_runner, dose_agg)
    assert v["decision"] == "ARM_NOTHING"
    assert v["cell"] is None
    assert "G7" in v["reason"]


def test_decide_arming_arms_best_cell_when_g4_and_g7_both_clear():
    # runner-cohort axis (the deciding one G7 gates on) must itself be monotonic/coherent here --
    # only the aggregate axis (used purely for ranking among already-cleared candidates) varies
    # non-monotonically, which is fine: G7 only gates on the runner axis.
    reports = {"F1": _fake_armpct_report(100.0, 50.0, True, True),
               "F2": _fake_armpct_report(500.0, 150.0, True, True),
               "F3": _fake_armpct_report(200.0, 250.0, True, True)}
    dose_runner = abp.assess_dose_response({"F1": 50.0, "F2": 150.0, "F3": 250.0}, "runner")
    dose_agg = abp.assess_dose_response({"F1": 100.0, "F2": 500.0, "F3": 200.0}, "agg")
    assert dose_runner["coherent"] is True  # sanity: this fixture's deciding axis is coherent
    v = abp.decide_arming(reports, dose_runner, dose_agg)
    assert v["decision"] == "ARM"
    assert v["cell"] == "F2"


def test_decide_arming_prefers_lower_arm_pct_on_practical_tie():
    reports = {"F1": _fake_armpct_report(500.0, 190.0, True, True),
               "F2": _fake_armpct_report(510.0, 200.0, True, True),
               "F3": _fake_armpct_report(100.0, 205.0, True, True)}
    dose_runner = abp.assess_dose_response({"F1": 190.0, "F2": 200.0, "F3": 205.0}, "runner")
    dose_agg = abp.assess_dose_response({"F1": 500.0, "F2": 510.0, "F3": 100.0}, "agg")
    assert dose_runner["coherent"] is True  # sanity
    v = abp.decide_arming(reports, dose_runner, dose_agg)
    assert v["decision"] == "ARM"
    assert v["cell"] == "F1", "F1 (lower arm_pct) must win the practical tie over F2"


# ---------------------------------------------------------------------------------------------
# RED-proof anchors on the shipped iteration-2 scorecard, if present (mirrors iteration 1's
# pattern above)
# ---------------------------------------------------------------------------------------------
def test_shipped_scorecard_control_reconciles_and_runner_anchor_matches_armpct():
    if not abp.OUT_JSON.exists():
        return
    d = json.loads(abp.OUT_JSON.read_text(encoding="utf-8"))
    assert d["population"]["n_control_mismatch_vs_source"] == 0, (
        "CONTROL cell drifted from the frozen source population -- do not trust this scorecard")
    rc = d["runner_cohort"]
    assert rc["anchor_check"]["n_matches"] is True
    assert rc["anchor_check"]["pnl_matches"] is True
    assert d["arming_recommendation"]["decision"] in ("ARM", "ARM_NOTHING")


def test_shipped_scorecard_g4_gate_is_the_hard_veto_it_claims_to_be_armpct():
    if not abp.OUT_JSON.exists():
        return
    d = json.loads(abp.OUT_JSON.read_text(encoding="utf-8"))
    for cell in ("F1", "F2", "F3"):
        g = d["gates"][cell]
        if not g["g4_runner_cohort_no_regression"]["pass"]:
            assert g["clears_all_required_gates"] is False, (
                f"{cell} failed G4 (runner-tail regression) but was still marked as clearing "
                "all required gates -- G4 must be a hard veto per the frozen pre-reg")


def test_shipped_scorecard_if_arm_decision_made_g7_runner_axis_must_be_coherent():
    """If the shipped scorecard ever decides to ARM a cell, the runner-cohort dose-response axis
    it computed must have been coherent -- an ARM decision riding an incoherent G7 axis would
    mean decide_arming's global gate silently regressed."""
    if not abp.OUT_JSON.exists():
        return
    d = json.loads(abp.OUT_JSON.read_text(encoding="utf-8"))
    if d["arming_recommendation"]["decision"] == "ARM":
        assert d["dose_response"]["runner_cohort_deciding"]["coherent"] is True


def test_shipped_scorecard_today_trade_g6_delta_is_positive_for_every_gated_cell():
    """G6 disclosure sanity: today's real 2026-07-28 incident trade should show a positive delta
    vs CONTROL under EVERY F-cell (all three exercise arm_scope=full and today's HWM of 2.16
    clears all three thresholds 0.20/0.30/0.40 off the 1.38 entry) -- if a future re-run shows a
    gated cell with a non-positive G6 delta, that is worth a second look before trusting the row."""
    if not abp.OUT_JSON.exists():
        return
    d = json.loads(abp.OUT_JSON.read_text(encoding="utf-8"))
    for cell in ("F1", "F2", "F3"):
        assert d["gates"][cell]["g6_today_trade"]["delta"] > 0, (
            f"{cell}: today's trade G6 delta was not positive -- unexpected given HWM 2.16 "
            "clears all three arm thresholds off entry 1.38")
