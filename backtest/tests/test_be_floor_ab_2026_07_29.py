"""Guards for backtest/tools/be_floor_ab_2026_07_29.py (BE-FLOOR-PRETP1 pre-reg, iteration 3 of
the exit-leak arm axis: analysis/recommendations/prereg-be-floor-2026-07-29.json).

THREE LOAD-BEARING INVARIANTS THIS FILE PINS:

  1. THE HYPOTHESIS ITSELF: profit_lock_mode="fixed" produces a BREAKEVEN floor that (a) never
     ratchets above entry once set (unlike "trailing", which chases the HWM down at trail_pct)
     and (b) can only fire an exit when price returns ALL THE WAY to entry -- structurally
     incapable of clipping a runner that stays above entry. Pinned via direct
     em.plan_exit_actions unit tests, both pre-TP1 (arm_scope=full) and post-TP1.

  2. THE STRUCTURAL SIDE-EFFECT disclosed in the pre-reg BEFORE any run: profit_lock_mode is
     read by BOTH the pre-TP1 arm_scope=full branch AND the post-TP1 runner branch. Switching it
     to "fixed" therefore ALSO removes the post-TP1 15%-trailing protection for any trade that
     reaches TP1 -- a mechanism iterations 1-2 (which held profit_lock_mode="trailing" fixed
     throughout) never exercised. Pinned by an explicit post-TP1 non-ratchet test and an
     end-to-end walk_exit_manager fixture contrasting CONTROL (trailing, ratchets with HWM) vs a
     B-cell (fixed, flat at BE post-TP1).

  3. CELL-APPLICATION / CLASSIFICATION GUARD (C14 "dead/translated-but-unapplied knob" class):
     build_cells() isolates exactly the 3 named keys per B-cell; reached_tp1() and
     runner_mechanism() -- the helpers the G4 mechanism breakdown depends on -- classify
     synthetic leg/reason fixtures correctly; assess_dose_response()/decide_arming() pure logic
     (reused pattern from iteration 2's armpct guards, reimplemented here because this axis's
     ordering -- B2(0.20) < B1(0.30) < B3(0.50) -- is not alphabetical cell-name order).
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
import be_floor_ab_2026_07_29 as bf  # noqa: E402
from exit_manager_walk import walk_exit_manager  # noqa: E402

CONTROL_SHAPE = {
    "premium_stop_pct": -0.20, "tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667,
    "profit_lock_mode": "trailing", "runner_target_pct": 99.0, "trail_pct": 0.15,
    "profit_lock_arm_pct": 0.05, "stop_mode": "structure", "catastrophe_stop_pct": -0.50,
    "profit_lock_arm_scope": "post_tp1",
}


# ---------------------------------------------------------------------------------------------
# build_cells() -- 3-key isolation shape (mode + scope + arm_pct), distinct from iterations 1-2
# ---------------------------------------------------------------------------------------------
def test_build_cells_control_is_a_copy_not_an_alias():
    cells = bf.build_cells(CONTROL_SHAPE)
    assert cells["CONTROL"] == CONTROL_SHAPE
    assert cells["CONTROL"] is not CONTROL_SHAPE


def test_build_cells_b1_b2_b3_isolate_exactly_mode_scope_and_arm_pct():
    cells = bf.build_cells(CONTROL_SHAPE)
    expected_arm_pct = {"B1": 0.30, "B2": 0.20, "B3": 0.50}
    for name, arm_pct in expected_arm_pct.items():
        shape = cells[name]
        assert shape["profit_lock_mode"] == "fixed", f"{name} must switch to fixed (BE floor)"
        assert shape["profit_lock_arm_scope"] == em.ARM_SCOPE_FULL, f"{name} must arm full-scope"
        assert shape["profit_lock_arm_pct"] == arm_pct, f"{name} must arm at {arm_pct}"
        for k in ("trail_pct", "catastrophe_stop_pct", "stop_mode", "tp1_premium_pct",
                  "tp1_qty_fraction", "premium_stop_pct", "runner_target_pct"):
            assert shape[k] == CONTROL_SHAPE[k], f"no_other_knobs violated: {name} moved {k}"


def test_build_cells_all_four_shapes_are_genuinely_distinct_objects():
    cells = bf.build_cells(CONTROL_SHAPE)
    dicts = list(cells.values())
    for i, a_ in enumerate(dicts):
        for j, b_ in enumerate(dicts):
            if i != j:
                assert a_ is not b_, "build_cells must never alias two cells to the same dict"
                assert a_ != b_, "build_cells must never produce two cells with identical shapes"


# ---------------------------------------------------------------------------------------------
# INVARIANT 1 -- the hypothesis: BE floor never ratchets above entry, fires only on a full
# round-trip back to entry, pre-TP1 (arm_scope=full)
# ---------------------------------------------------------------------------------------------
def _fixed_full_scope_shape(arm_pct: float = 0.30, **overrides) -> dict:
    base = {
        "premium_stop_pct": -0.20, "tp1_premium_pct": 99.0, "tp1_qty_fraction": 0.667,
        "profit_lock_mode": "fixed", "runner_target_pct": 99.0, "trail_pct": 0.15,
        "profit_lock_arm_pct": arm_pct, "stop_mode": "premium",
        "profit_lock_arm_scope": em.ARM_SCOPE_FULL,
    }
    base.update(overrides)
    return base


def test_fixed_floor_arms_at_entry_and_does_not_ratchet_up_with_a_new_hwm():
    """Positive-hypothesis test: unlike trailing mode, a fixed-mode floor set at entry must NOT
    move when a later tick sets an even higher HWM -- the whole point of 'fixed' vs 'trailing'."""
    state = em.ExitState.from_entry(
        symbol="SPY260101C00600000", side="C", entry_premium=1.00, qty=3,
        exit_shape=_fixed_full_scope_shape(0.30), strategy="ribbon_ride")

    # arm at +30%
    dec1 = em.plan_exit_actions(state, best_premium=1.30, worst_premium=1.30, open_qty=3,
                                 now_et=dt.time(12, 5))
    assert dec1.state.profit_lock_armed is True
    assert dec1.state.runner_stop_premium == 1.00, "BE floor must arm exactly AT entry, not above"

    # price runs MUCH higher -- a trailing floor would ratchet to hwm*(1-trail_pct); fixed must not
    dec2 = em.plan_exit_actions(dec1.state, best_premium=2.50, worst_premium=2.50, open_qty=3,
                                 now_et=dt.time(12, 10))
    assert not any(a.kind == "SELL_ALL" for a in dec2.actions)
    assert dec2.state.runner_stop_premium == 1.00, (
        "fixed-mode floor ratcheted with the HWM -- it must stay pinned at entry, that is the "
        "entire distinction between 'fixed' and 'trailing'")


def test_fixed_floor_only_fires_on_a_full_round_trip_back_to_entry():
    """Core hypothesis: a fixed floor cannot fire above entry -- only a return ALL THE WAY back
    to entry (or below) trips it. A partial pullback that stays above entry must NOT exit."""
    state = em.ExitState.from_entry(
        symbol="SPY260101C00600000", side="C", entry_premium=1.00, qty=3,
        exit_shape=_fixed_full_scope_shape(0.30), strategy="ribbon_ride")
    dec1 = em.plan_exit_actions(state, best_premium=1.30, worst_premium=1.30, open_qty=3,
                                 now_et=dt.time(12, 5))
    # partial pullback, still well above entry -- must NOT exit
    dec2 = em.plan_exit_actions(dec1.state, best_premium=1.10, worst_premium=1.10, open_qty=3,
                                 now_et=dt.time(12, 10))
    assert not any(a.kind == "SELL_ALL" for a in dec2.actions), (
        "a partial pullback that stays ABOVE entry must not trip a BE floor")
    # full round-trip back to exactly entry -- must exit at BE
    dec3 = em.plan_exit_actions(dec2.state, best_premium=1.00, worst_premium=1.00, open_qty=3,
                                 now_et=dt.time(12, 15))
    assert any(a.kind == "SELL_ALL" and a.stage == "profit_lock_floor" for a in dec3.actions), (
        "a full round-trip back to entry must trip the BE floor -- otherwise the guard above "
        "would be vacuous (the floor never fires at all)")


def test_fixed_floor_same_tick_look_ahead_is_structurally_impossible():
    """G_lookahead (unlettered here, but re-verified -- new surface, not assumed transferred from
    iterations 1-2's trailing-mode guard): the arm condition requires best_premium >=
    entry*(1+arm_pct) with arm_pct>0, so the SAME tick's value is strictly ABOVE entry and can
    never also trip worst_premium<=entry (== the floor) under the point-sample convention."""
    for arm_pct in (0.20, 0.30, 0.50):
        state = em.ExitState.from_entry(
            symbol="SPY260101C00600000", side="C", entry_premium=1.00, qty=3,
            exit_shape=_fixed_full_scope_shape(arm_pct), strategy="ribbon_ride")
        hwm_tick = 1.00 * (1.0 + arm_pct) + 0.10
        dec = em.plan_exit_actions(state, best_premium=hwm_tick, worst_premium=hwm_tick,
                                    open_qty=3, now_et=dt.time(12, 5))
        assert not any(a.kind == "SELL_ALL" for a in dec.actions), (
            f"same-tick look-ahead at arm_pct={arm_pct}: arming and exiting must not be possible "
            "on the same tick for a BE floor")
        assert dec.state.runner_stop_premium == 1.00


# ---------------------------------------------------------------------------------------------
# INVARIANT 2 -- the structural side-effect: fixed mode ALSO disables the post-TP1 trailing
# ratchet (the mechanism iterations 1-2 never exercised, because they kept mode="trailing")
# ---------------------------------------------------------------------------------------------
def test_fixed_mode_post_tp1_never_ratchets_even_as_premium_keeps_rising():
    """The structural side-effect, pinned directly: once TP1 fills (runner_stop reset to BE,
    profit_lock_armed forced True per exit_manager.py:442-444, REGARDLESS of arm_scope/arm_pct),
    a fixed-mode position's runner_stop must stay flat at entry no matter how high the premium
    goes afterward -- unlike trailing mode, which chases the new HWM down at trail_pct."""
    shape_fixed = _fixed_full_scope_shape(0.30, tp1_premium_pct=1.0)
    state = em.ExitState.from_entry(
        symbol="SPY260101C00600000", side="C", entry_premium=1.00, qty=3,
        exit_shape=shape_fixed, strategy="ribbon_ride")
    # TP1 fires at +100%
    dec_tp1 = em.plan_exit_actions(state, best_premium=2.00, worst_premium=2.00, open_qty=3,
                                    now_et=dt.time(12, 5))
    assert any(a.kind == "SELL_PARTIAL" and a.stage == "tp1" for a in dec_tp1.actions)
    assert dec_tp1.state.runner_stop_premium == 1.00
    open_qty = 3 - next(a.qty for a in dec_tp1.actions if a.kind == "SELL_PARTIAL")

    # runner keeps climbing well past TP1 -- fixed-mode stop must NOT move
    dec_run = em.plan_exit_actions(dec_tp1.state, best_premium=3.50, worst_premium=3.50,
                                    open_qty=open_qty, now_et=dt.time(12, 30))
    assert not any(a.kind == "SELL_ALL" for a in dec_run.actions)
    assert dec_run.state.runner_stop_premium == 1.00, (
        "fixed-mode post-TP1 runner_stop ratcheted -- it must stay pinned at BE forever once "
        "armed, which is precisely the mechanism that costs the runner cohort its trailing "
        "protection in the shipped scorecard")

    # CONTRAST: the SAME fixture under trailing mode DOES ratchet -- proves the difference is
    # profit_lock_mode, not some other accidental knob
    shape_trailing = dict(shape_fixed, profit_lock_mode="trailing")
    state_t = em.ExitState.from_entry(
        symbol="SPY260101C00600000", side="C", entry_premium=1.00, qty=3,
        exit_shape=shape_trailing, strategy="ribbon_ride")
    dec_tp1_t = em.plan_exit_actions(state_t, best_premium=2.00, worst_premium=2.00, open_qty=3,
                                      now_et=dt.time(12, 5))
    dec_run_t = em.plan_exit_actions(dec_tp1_t.state, best_premium=3.50, worst_premium=3.50,
                                      open_qty=open_qty, now_et=dt.time(12, 30))
    assert dec_run_t.state.runner_stop_premium > 1.00, (
        "trailing-mode control fixture did not ratchet -- the contrast fixture is broken, so the "
        "test above is not actually isolating profit_lock_mode as the cause")


# ---------------------------------------------------------------------------------------------
# end-to-end walk_exit_manager fixtures -- both mechanisms through the REAL harness path
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


def test_walk_incident_shaped_fixture_pretp1_roundtrip_scratches_instead_of_losing():
    """Mechanism (a) through the real harness: a run-up past the arm threshold that never
    reaches TP1, then a full round-trip back to entry -- CONTROL (unarmed pre-TP1) rides it to a
    real loss via its downstream stop; the B-cell scratches at exactly breakeven."""
    times = ["2026-01-01 12:00:00", "2026-01-01 12:05:00", "2026-01-01 12:10:00",
             "2026-01-01 12:15:00"]
    # 1.00 -> 1.40 (+40%, clears B1's 30% arm, short of tp1 @ 2.00) -> 1.00 (round trip to entry)
    # -> 0.75 (below CONTROL's -20% premium stop, a real loss under CONTROL)
    opens = [(times[0], 1.00), (times[1], 1.40), (times[2], 1.00), (times[3], 0.75)]
    cells = bf.build_cells(CONTROL_SHAPE)
    common = dict(symbol="SPY260101C00600000", side="C", entry_time_et=dt.datetime(2026, 1, 1, 12, 0, 0),
                  entry_premium=1.00, qty=3, structure_stop_enabled=False, trigger_level=None,
                  strategy="ribbon_ride", time_stop_et=dt.time(15, 40),
                  opt_df=_opt_df(opens), ribbon_tick_df=None, five_min_spy_df=_spy_df(times))
    ctl = walk_exit_manager(exit_shape=cells["CONTROL"], **common)
    b1 = walk_exit_manager(exit_shape=cells["B1"], **common)
    assert "profit_lock_floor" in b1.exit_reason
    assert b1.dollar_pnl == 0.0, "the BE floor must scratch at EXACTLY breakeven, not above/below"
    assert b1.dollar_pnl > ctl.dollar_pnl, (
        f"B1 should beat CONTROL on a pre-TP1 round-trip-to-loss fixture: ctl={ctl.dollar_pnl} b1={b1.dollar_pnl}")


def test_walk_incident_shaped_fixture_posttp1_loses_trailing_protection_vs_control():
    """Mechanism (b) through the real harness: a trade that DOES reach TP1, rides to a high HWM,
    then decays but stays above entry -- CONTROL's trailing lock bags most of the HWM; the
    B-cell, with NO trailing protection post-TP1, rides all the way to the natural (time_stop)
    exit and can end up WORSE off despite never round-tripping to entry."""
    times = ["2026-01-01 12:00:00", "2026-01-01 12:05:00", "2026-01-01 12:10:00",
             "2026-01-01 15:45:00"]
    # 1.00 -> 2.20 (+120%, clears TP1 @ +100%, sells tp1_qty, runner stop -> BE) -> 3.00 (new HWM,
    # CONTROL's trailing floor now sits at 3.00*0.85=2.55; B-cell's fixed floor stays at 1.00) ->
    # 2.00 at time_stop (still well above entry, but below CONTROL's 2.55 trailing floor)
    opens = [(times[0], 1.00), (times[1], 2.20), (times[2], 3.00), (times[3], 2.00)]
    cells = bf.build_cells(CONTROL_SHAPE)
    common = dict(symbol="SPY260101C00600000", side="C", entry_time_et=dt.datetime(2026, 1, 1, 12, 0, 0),
                  entry_premium=1.00, qty=3, structure_stop_enabled=False, trigger_level=None,
                  strategy="ribbon_ride", time_stop_et=dt.time(15, 40),
                  opt_df=_opt_df(opens), ribbon_tick_df=None, five_min_spy_df=_spy_df(times))
    ctl = walk_exit_manager(exit_shape=cells["CONTROL"], **common)
    b1 = walk_exit_manager(exit_shape=cells["B1"], **common)
    assert "runner_stop" in ctl.exit_reason, "CONTROL must exit via its trailing runner_stop, well before time_stop"
    assert ctl.exit_reason != b1.exit_reason, "B1 produced the IDENTICAL outcome as CONTROL -- dead knob"
    assert b1.dollar_pnl < ctl.dollar_pnl, (
        f"B1 (no post-TP1 trailing protection) should trail CONTROL on a rise-then-decay-but-"
        f"stay-above-entry fixture -- this is the structural side-effect the pre-reg disclosed: "
        f"ctl={ctl.dollar_pnl} b1={b1.dollar_pnl}")
    assert b1.dollar_pnl > 0, (
        "the position never round-tripped to entry (stayed well above it throughout) -- B1 must "
        "still be a WINNER, just a smaller one than CONTROL; if this goes negative or zero, the "
        "fixture no longer isolates mechanism (b) from mechanism (a)")


# ---------------------------------------------------------------------------------------------
# INVARIANT 3 -- helper classification correctness (reached_tp1 / runner_mechanism)
# ---------------------------------------------------------------------------------------------
class _FakeLeg:
    def __init__(self, stage):
        self.stage = stage


def test_reached_tp1_detects_tp1_leg():
    assert bf.reached_tp1([_FakeLeg("tp1")]) is True
    assert bf.reached_tp1([_FakeLeg("structure_stop")]) is False
    assert bf.reached_tp1([]) is False
    assert bf.reached_tp1([_FakeLeg("arm"), _FakeLeg("tp1"), _FakeLeg("trail")]) is True


def test_runner_mechanism_classifies_pretp1_roundtrip():
    assert bf.runner_mechanism("profit_lock_floor @ 1.00", False) == "pretp1_roundtrip_to_entry"
    # even if reached_tp1 were somehow True, a profit_lock_floor reason is unambiguously pre-TP1
    # (that stage can only be emitted from the pre-TP1 branch) -- must still classify as (a)
    assert bf.runner_mechanism("profit_lock_floor @ 1.00", True) == "pretp1_roundtrip_to_entry"


def test_runner_mechanism_classifies_posttp1_lost_trailing():
    assert bf.runner_mechanism("runner_stop @ 1.66", True) == "posttp1_lost_trailing_protection"
    assert bf.runner_mechanism("structure_stop @ 741.0 (runner)", True) == "posttp1_lost_trailing_protection"
    assert bf.runner_mechanism("time_stop_15:50 (runner)", True) == "posttp1_lost_trailing_protection"


def test_runner_mechanism_classifies_pretp1_other_stops():
    assert bf.runner_mechanism("premium_stop @ 0.80", False) == "pretp1_catastrophe_or_other_stop"
    assert bf.runner_mechanism("structure_stop @ 741.0", False) == "pretp1_structure_stop"
    assert bf.runner_mechanism("time_stop_15:50", False) == "pretp1_time_stop"
    assert bf.runner_mechanism("ribbon_flip_back", False) == "pretp1_ribbon_flip"


# ---------------------------------------------------------------------------------------------
# assess_dose_response() -- ascending arm_pct axis (B2 0.20 < B1 0.30 < B3 0.50), pure logic
# ---------------------------------------------------------------------------------------------
def test_dose_response_monotonic_improving_is_coherent():
    d = bf.assess_dose_response(-100.0, -50.0, 0.0, "test")
    assert d["coherent"] is True
    assert d["shape"] == "monotonic_improving_with_higher_arm_pct"


def test_dose_response_monotonic_worsening_is_coherent():
    d = bf.assess_dose_response(100.0, 50.0, 0.0, "test")
    assert d["coherent"] is True
    assert d["shape"] == "monotonic_worsening_with_higher_arm_pct"


def test_dose_response_flat_is_coherent():
    d = bf.assess_dose_response(10.0, 10.5, 9.7, "test")
    assert d["coherent"] is True
    assert d["shape"] == "flat"


def test_dose_response_spike_at_mid_is_noise():
    d = bf.assess_dose_response(-1000.0, 800.0, -900.0, "test")
    assert d["coherent"] is False
    assert d["shape"] == "non_monotonic_spike_at_mid_NOISE"


def test_dose_response_small_wiggle_within_tolerance_not_flagged_as_spike():
    d = bf.assess_dose_response(100.0, 150.0, 90.0, "test")
    assert d["shape"] == "irregular_non_monotonic"
    assert d["coherent"] is False


# ---------------------------------------------------------------------------------------------
# decide_arming() -- G5-incoherent global veto, G4-uniform-fail short-circuit, tie-break
# ---------------------------------------------------------------------------------------------
def _fake_report(agg_delta: float, g4_delta: float, g4_pass: bool, clears: bool) -> dict:
    return {"g1_positive_aggregate": {"delta": agg_delta},
            "g4_runner_cohort_no_regression": {"delta": g4_delta, "pass": g4_pass},
            "clears_all_required_gates": clears}


def test_decide_arming_g5_incoherent_runner_axis_arms_nothing_even_if_a_cell_individually_clears():
    reports = {"B1": _fake_report(-1000.0, -1000.0, False, False),
               "B2": _fake_report(800.0, 800.0, True, True),   # would otherwise ARM
               "B3": _fake_report(-900.0, -900.0, False, False)}
    dose_runner = bf.assess_dose_response(-1000.0, 800.0, -900.0, "runner")
    dose_agg = bf.assess_dose_response(-1000.0, 800.0, -900.0, "agg")
    assert dose_runner["coherent"] is False
    v = bf.decide_arming(reports, dose_runner, dose_agg)
    assert v["decision"] == "ARM_NOTHING"
    assert v["cell"] is None
    assert "G5" in v["reason"]


def test_decide_arming_g4_uniform_fail_short_circuits_with_named_reason():
    """Mirrors the real shipped run's actual shape: G5-runner coherent, but G4 fails on every
    cell -- must ARM NOTHING and the reason string must name G4 explicitly."""
    reports = {"B1": _fake_report(-3420.45, -5965.05, False, False),
               "B2": _fake_report(-4594.45, -7805.05, False, False),
               "B3": _fake_report(-2897.85, -3208.05, False, False)}
    dose_runner = bf.assess_dose_response(-7805.05, -5965.05, -3208.05, "runner")
    dose_agg = bf.assess_dose_response(-4594.45, -3420.45, -2897.85, "agg")
    assert dose_runner["coherent"] is True
    v = bf.decide_arming(reports, dose_runner, dose_agg)
    assert v["decision"] == "ARM_NOTHING"
    assert v["cell"] is None
    assert "G4" in v["reason"], "reason must name G4 as the binding cause, not a generic message"


def test_decide_arming_arms_best_cell_when_g4_and_g5_both_clear():
    reports = {"B1": _fake_report(100.0, 50.0, True, True),
               "B2": _fake_report(500.0, 150.0, True, True),
               "B3": _fake_report(200.0, 250.0, True, True)}
    dose_runner = bf.assess_dose_response(50.0, 150.0, 250.0, "runner")
    dose_agg = bf.assess_dose_response(100.0, 500.0, 200.0, "agg")
    assert dose_runner["coherent"] is True
    v = bf.decide_arming(reports, dose_runner, dose_agg)
    assert v["decision"] == "ARM"
    assert v["cell"] == "B2"


def test_decide_arming_prefers_lower_arm_pct_on_practical_tie():
    reports = {"B1": _fake_report(500.0, 190.0, True, True),
               "B2": _fake_report(510.0, 200.0, True, True),
               "B3": _fake_report(100.0, 205.0, True, True)}
    dose_runner = bf.assess_dose_response(190.0, 200.0, 205.0, "runner")
    dose_agg = bf.assess_dose_response(500.0, 510.0, 100.0, "agg")
    assert dose_runner["coherent"] is True
    v = bf.decide_arming(reports, dose_runner, dose_agg)
    assert v["decision"] == "ARM"
    assert v["cell"] == "B2", "B2 (lowest arm_pct=0.20) must win the practical tie"


# ---------------------------------------------------------------------------------------------
# RED-proof anchors on the shipped scorecard, if present (mirrors iterations 1-2's pattern)
# ---------------------------------------------------------------------------------------------
def test_shipped_scorecard_control_reconciles_and_runner_anchor_matches():
    if not bf.OUT_JSON.exists():
        return
    d = json.loads(bf.OUT_JSON.read_text(encoding="utf-8"))
    assert d["population"]["n_control_mismatch_vs_source"] == 0, (
        "CONTROL cell drifted from the frozen source population -- do not trust this scorecard")
    rc = d["runner_cohort"]
    assert rc["anchor_check"]["n_matches"] is True
    assert rc["anchor_check"]["pnl_matches"] is True
    assert d["arming_recommendation"]["decision"] in ("ARM", "ARM_NOTHING")


def test_shipped_scorecard_g4_gate_is_the_hard_veto_it_claims_to_be():
    if not bf.OUT_JSON.exists():
        return
    d = json.loads(bf.OUT_JSON.read_text(encoding="utf-8"))
    for cell in ("B1", "B2", "B3"):
        g = d["gates"][cell]
        if not g["g4_runner_cohort_no_regression"]["pass"]:
            assert g["clears_all_required_gates"] is False, (
                f"{cell} failed G4 (runner-tail regression) but was still marked as clearing "
                "all required gates -- G4 must be a hard veto per the frozen pre-reg")


def test_shipped_scorecard_if_arm_decision_made_g5_runner_axis_must_be_coherent():
    if not bf.OUT_JSON.exists():
        return
    d = json.loads(bf.OUT_JSON.read_text(encoding="utf-8"))
    if d["arming_recommendation"]["decision"] == "ARM":
        assert d["dose_response"]["runner_cohort_deciding"]["coherent"] is True


def test_shipped_scorecard_mechanism_breakdown_sums_to_n_worse_per_cell():
    """The G4 mechanism breakdown must account for EVERY degraded runner-cohort trade -- no
    silent drops (OP-33 visibility rule): sum of the breakdown counts must equal n_worse."""
    if not bf.OUT_JSON.exists():
        return
    d = json.loads(bf.OUT_JSON.read_text(encoding="utf-8"))
    for cell in ("B1", "B2", "B3"):
        g4 = d["gates"][cell]["g4_runner_cohort_no_regression"]
        total_classified = sum(g4["mechanism_breakdown_of_worse_trades"].values())
        assert total_classified == g4["n_worse"], (
            f"{cell}: mechanism breakdown accounts for {total_classified} trades but n_worse="
            f"{g4['n_worse']} -- every degraded runner trade must be classified")


def test_shipped_scorecard_today_trade_g6_delta_is_positive_for_every_gated_cell():
    """Today's real 2026-07-28 incident trade (entry 1.38, HWM 2.16 at 12:57) clears all three
    arm thresholds well before its eventual round-trip -- G6 should be positive under every
    B-cell (a BE floor exit here is still strictly better than the real -$305 loss)."""
    if not bf.OUT_JSON.exists():
        return
    d = json.loads(bf.OUT_JSON.read_text(encoding="utf-8"))
    for cell in ("B1", "B2", "B3"):
        assert d["gates"][cell]["g6_today_trade"]["delta"] > 0, (
            f"{cell}: today's trade G6 delta was not positive -- unexpected given HWM 2.16 "
            "clears all three arm thresholds off entry 1.38")
