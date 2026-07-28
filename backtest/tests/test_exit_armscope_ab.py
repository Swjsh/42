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
