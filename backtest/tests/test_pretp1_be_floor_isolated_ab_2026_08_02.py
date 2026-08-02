"""Guards for backtest/tools/pretp1_be_floor_isolated_ab_2026_08_02.py (PRETP1-BE-FLOOR-ISOLATED
pre-reg, iteration 4 of the exit-leak arm axis:
analysis/recommendations/prereg-pretp1-be-floor-isolated-2026-08-02.json).

TWO LOAD-BEARING INVARIANTS THIS FILE PINS:

  1. KNOB ISOLATION (the entire reason this iteration exists): pre_tp1_be_floor_arm_pct must
     NEVER set profit_lock_armed and must NEVER cause any change to post-TP1 mechanics -- unlike
     iteration 3's profit_lock_mode="fixed", which was confounded across both branches. Pinned
     via direct em.plan_exit_actions unit tests (arms pre-TP1 without profit_lock_armed; TP1 and
     post-TP1 walk byte-identical with/without the knob set) AND an end-to-end
     walk_exit_manager fixture contrasting CONTROL vs an armed cell across a full TP1+runner
     lifecycle.

  2. CELL-APPLICATION / CLASSIFICATION GUARD (C14 "dead/translated-but-unapplied knob" class):
     build_cells() isolates exactly ONE key (pre_tp1_be_floor_arm_pct) per P-cell; runner_mechanism()
     flags mechanism (b) as a KNOB_ISOLATION_VIOLATION string (not silently reused from iteration
     3's benign label) so a regression that reintroduces the confound is loud, not quiet;
     assess_dose_response()/decide_arming() pure logic (reused pattern from iteration 3).
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
import pretp1_be_floor_isolated_ab_2026_08_02 as pf  # noqa: E402
from exit_manager_walk import walk_exit_manager  # noqa: E402

CONTROL_SHAPE = {
    "premium_stop_pct": -0.20, "tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667,
    "profit_lock_mode": "trailing", "runner_target_pct": 99.0, "trail_pct": 0.15,
    "profit_lock_arm_pct": 0.05, "stop_mode": "structure", "catastrophe_stop_pct": -0.50,
    "profit_lock_arm_scope": "post_tp1",
}


# ---------------------------------------------------------------------------------------------
# build_cells() -- single-key isolation (pre_tp1_be_floor_arm_pct ONLY)
# ---------------------------------------------------------------------------------------------
def test_build_cells_control_is_a_copy_not_an_alias():
    cells = pf.build_cells(CONTROL_SHAPE)
    assert cells["CONTROL"] == CONTROL_SHAPE
    assert cells["CONTROL"] is not CONTROL_SHAPE


def test_build_cells_p1_p2_p3_isolate_exactly_one_key():
    cells = pf.build_cells(CONTROL_SHAPE)
    expected_arm_pct = {"P1": 0.30, "P2": 0.50, "P3": 0.70}
    for name, arm_pct in expected_arm_pct.items():
        shape = cells[name]
        assert shape["pre_tp1_be_floor_arm_pct"] == arm_pct
        for k in CONTROL_SHAPE:  # every pre-existing key must be UNCHANGED
            assert shape[k] == CONTROL_SHAPE[k], f"no_other_knobs violated: {name} moved {k}"
        assert shape["profit_lock_mode"] == "trailing", (
            f"{name} must keep profit_lock_mode='trailing' -- the whole point vs iteration 3")
        assert shape["profit_lock_arm_scope"] == "post_tp1", (
            f"{name} must NOT touch profit_lock_arm_scope -- orthogonal mechanism")


def test_build_cells_all_four_shapes_are_genuinely_distinct_objects():
    cells = pf.build_cells(CONTROL_SHAPE)
    dicts = list(cells.values())
    for i, a_ in enumerate(dicts):
        for j, b_ in enumerate(dicts):
            if i != j:
                assert a_ is not b_
                assert a_ != b_


# ---------------------------------------------------------------------------------------------
# INVARIANT 1 -- knob isolation: never sets profit_lock_armed, never touches post-TP1 mechanics
# ---------------------------------------------------------------------------------------------
def _iso_shape(arm_pct: float = 0.30, **overrides) -> dict:
    base = dict(CONTROL_SHAPE, pre_tp1_be_floor_arm_pct=arm_pct)
    base.update(overrides)
    return base


def test_isolated_floor_arms_without_setting_profit_lock_armed():
    """The defining contrast with iteration 3's arm_scope='full': arming this knob must NEVER
    flip profit_lock_armed, because that flag also gates post-TP1 mechanics."""
    state = em.ExitState.from_entry(
        symbol="SPY260101C00600000", side="C", entry_premium=1.00, qty=3,
        exit_shape=_iso_shape(0.30, tp1_premium_pct=99.0), strategy="ribbon_ride")
    dec1 = em.plan_exit_actions(state, best_premium=1.30, worst_premium=1.30, open_qty=3,
                                 now_et=dt.time(12, 5))
    assert dec1.state.runner_stop_premium == 1.00, "BE floor must arm exactly AT entry"
    assert dec1.state.profit_lock_armed is False, (
        "isolated floor set profit_lock_armed -- this would leak into post-TP1 mechanics "
        "exactly like iteration 3's confound")


def test_isolated_floor_does_not_trail_pre_tp1_even_with_trailing_mode():
    """Even with profit_lock_mode='trailing', the isolated floor must never ratchet past entry
    pre-TP1 -- no trailing pre-TP1, only a flat BE floor."""
    state = em.ExitState.from_entry(
        symbol="SPY260101C00600000", side="C", entry_premium=1.00, qty=3,
        exit_shape=_iso_shape(0.30, tp1_premium_pct=99.0), strategy="ribbon_ride")
    dec1 = em.plan_exit_actions(state, best_premium=2.00, worst_premium=2.00, open_qty=3,
                                 now_et=dt.time(12, 5))
    assert dec1.state.runner_stop_premium == 1.00, (
        "isolated floor ratcheted past entry pre-TP1 -- it must stay a flat BE floor, "
        "not a trail (that would reproduce the whipsaw iterations 1-2 already killed)")


def test_isolated_floor_post_tp1_mechanics_byte_identical_to_control():
    """The headline safety property, pinned directly at the plan_exit_actions layer: TP1 fill
    unconditionally resets runner_stop=entry and profit_lock_armed=True regardless of this
    knob, so post-TP1 state must be byte-identical whether or not the isolated floor is set."""
    shape_iso = _iso_shape(0.30, tp1_premium_pct=1.0)
    shape_ctl = dict(CONTROL_SHAPE, tp1_premium_pct=1.0)
    state_iso = em.ExitState.from_entry(symbol="x", side="C", entry_premium=1.00, qty=3,
                                        exit_shape=shape_iso, strategy="ribbon_ride")
    state_ctl = em.ExitState.from_entry(symbol="x", side="C", entry_premium=1.00, qty=3,
                                        exit_shape=shape_ctl, strategy="ribbon_ride")
    # pre-TP1: iso arms at +30% (best 1.35), control does nothing (post_tp1 scope default)
    d1_iso = em.plan_exit_actions(state_iso, best_premium=1.35, worst_premium=1.30, open_qty=3,
                                   now_et=dt.time(12, 0))
    d1_ctl = em.plan_exit_actions(state_ctl, best_premium=1.35, worst_premium=1.30, open_qty=3,
                                   now_et=dt.time(12, 0))
    assert d1_iso.state.runner_stop_premium == 1.00
    assert d1_ctl.state.runner_stop_premium == 0.80  # unarmed, -20% stop unchanged
    # TP1 fires for both at +100% (best 2.00) -- must land on IDENTICAL post-TP1 state
    d2_iso = em.plan_exit_actions(d1_iso.state, best_premium=2.00, worst_premium=1.90, open_qty=3,
                                   now_et=dt.time(12, 5))
    d2_ctl = em.plan_exit_actions(d1_ctl.state, best_premium=2.00, worst_premium=1.90, open_qty=3,
                                   now_et=dt.time(12, 5))
    assert d2_iso.state.runner_stop_premium == d2_ctl.state.runner_stop_premium == 1.00
    assert d2_iso.state.profit_lock_armed == d2_ctl.state.profit_lock_armed is True
    assert [(a.kind, a.stage, a.qty) for a in d2_iso.actions] == [(a.kind, a.stage, a.qty) for a in d2_ctl.actions]
    # post-TP1: runner keeps climbing -- both trail identically (trailing mode, byte-identical)
    open_qty = 3 - next(a.qty for a in d2_iso.actions if a.kind == "SELL_PARTIAL")
    d3_iso = em.plan_exit_actions(d2_iso.state, best_premium=3.00, worst_premium=2.80,
                                   open_qty=open_qty, now_et=dt.time(12, 30))
    d3_ctl = em.plan_exit_actions(d2_ctl.state, best_premium=3.00, worst_premium=2.80,
                                   open_qty=open_qty, now_et=dt.time(12, 30))
    assert d3_iso.state.runner_stop_premium == d3_ctl.state.runner_stop_premium


def test_isolated_floor_same_tick_look_ahead_is_structurally_impossible():
    for arm_pct in (0.30, 0.50, 0.70):
        state = em.ExitState.from_entry(
            symbol="x", side="C", entry_premium=1.00, qty=3,
            exit_shape=_iso_shape(arm_pct, tp1_premium_pct=99.0), strategy="ribbon_ride")
        hwm_tick = 1.00 * (1.0 + arm_pct) + 0.10
        dec = em.plan_exit_actions(state, best_premium=hwm_tick, worst_premium=hwm_tick,
                                    open_qty=3, now_et=dt.time(12, 5))
        assert not any(a.kind == "SELL_ALL" for a in dec.actions)
        assert dec.state.runner_stop_premium == 1.00


# ---------------------------------------------------------------------------------------------
# end-to-end walk_exit_manager fixture -- both mechanisms through the REAL harness path
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
    """Pre-TP1 round-trip: CONTROL (unarmed pre-TP1) rides it to a real loss via the downstream
    stop; the isolated-floor cell scratches at exactly breakeven."""
    times = ["2026-01-01 12:00:00", "2026-01-01 12:05:00", "2026-01-01 12:10:00",
             "2026-01-01 12:15:00"]
    opens = [(times[0], 1.00), (times[1], 1.40), (times[2], 1.00), (times[3], 0.75)]
    cells = pf.build_cells(CONTROL_SHAPE)
    common = dict(symbol="x", side="C", entry_time_et=dt.datetime(2026, 1, 1, 12, 0, 0),
                  entry_premium=1.00, qty=3, structure_stop_enabled=False, trigger_level=None,
                  strategy="ribbon_ride", time_stop_et=dt.time(15, 40),
                  opt_df=_opt_df(opens), ribbon_tick_df=None, five_min_spy_df=_spy_df(times))
    ctl = walk_exit_manager(exit_shape=cells["CONTROL"], **common)
    p1 = walk_exit_manager(exit_shape=cells["P1"], **common)
    assert "profit_lock_floor" in p1.exit_reason
    assert p1.dollar_pnl == 0.0
    assert p1.dollar_pnl > ctl.dollar_pnl


def test_walk_incident_shaped_fixture_post_tp1_ride_byte_identical_to_control():
    """Mechanism (b) MUST NOT occur this iteration: a trade reaching TP1 then trailing off
    post-TP1 must produce the IDENTICAL P&L whether or not the isolated floor is armed."""
    times = ["2026-01-01 12:00:00", "2026-01-01 12:05:00", "2026-01-01 12:10:00",
             "2026-01-01 15:45:00"]
    opens = [(times[0], 1.00), (times[1], 2.20), (times[2], 3.00), (times[3], 2.00)]
    cells = pf.build_cells(CONTROL_SHAPE)
    common = dict(symbol="x", side="C", entry_time_et=dt.datetime(2026, 1, 1, 12, 0, 0),
                  entry_premium=1.00, qty=3, structure_stop_enabled=False, trigger_level=None,
                  strategy="ribbon_ride", time_stop_et=dt.time(15, 40),
                  opt_df=_opt_df(opens), ribbon_tick_df=None, five_min_spy_df=_spy_df(times))
    ctl = walk_exit_manager(exit_shape=cells["CONTROL"], **common)
    p1 = walk_exit_manager(exit_shape=cells["P1"], **common)
    assert p1.exit_reason == ctl.exit_reason
    assert p1.dollar_pnl == ctl.dollar_pnl, (
        "isolated floor changed a post-TP1-only outcome -- knob isolation violated "
        f"(ctl={ctl.dollar_pnl} p1={p1.dollar_pnl})")


# ---------------------------------------------------------------------------------------------
# INVARIANT 2 -- helper classification correctness (reached_tp1 / runner_mechanism)
# ---------------------------------------------------------------------------------------------
class _FakeLeg:
    def __init__(self, stage):
        self.stage = stage


def test_reached_tp1_detects_tp1_leg():
    assert pf.reached_tp1([_FakeLeg("tp1")]) is True
    assert pf.reached_tp1([_FakeLeg("structure_stop")]) is False
    assert pf.reached_tp1([]) is False


def test_runner_mechanism_classifies_pretp1_roundtrip():
    assert pf.runner_mechanism("profit_lock_floor @ 1.00", False) == "pretp1_roundtrip_to_entry"
    assert pf.runner_mechanism("profit_lock_floor @ 1.00", True) == "pretp1_roundtrip_to_entry"


def test_runner_mechanism_flags_posttp1_as_knob_isolation_violation():
    """This iteration's key difference from iteration 3: mechanism (b) is not a benign label,
    it is a VIOLATION -- the string itself must say so, so a scorecard reader (and the
    knob-isolation-count assertion below) cannot silently gloss over a regression."""
    mech = pf.runner_mechanism("runner_stop @ 1.66", True)
    assert "KNOB_ISOLATION_VIOLATION" in mech


def test_runner_mechanism_classifies_pretp1_other_stops():
    assert pf.runner_mechanism("premium_stop @ 0.80", False) == "pretp1_catastrophe_or_other_stop"
    assert pf.runner_mechanism("structure_stop @ 741.0", False) == "pretp1_structure_stop"
    assert pf.runner_mechanism("time_stop_15:50", False) == "pretp1_time_stop"
    assert pf.runner_mechanism("ribbon_flip_back", False) == "pretp1_ribbon_flip"


# ---------------------------------------------------------------------------------------------
# assess_dose_response() / decide_arming() -- pure logic, ascending arm_pct axis P1<P2<P3
# ---------------------------------------------------------------------------------------------
def test_dose_response_monotonic_improving_is_coherent():
    d = pf.assess_dose_response(-3650.45, -905.45, -459.0, "test")
    assert d["coherent"] is True
    assert d["shape"] == "monotonic_improving_with_higher_arm_pct"


def test_dose_response_spike_at_mid_is_noise():
    d = pf.assess_dose_response(-1000.0, 800.0, -900.0, "test")
    assert d["coherent"] is False
    assert d["shape"] == "non_monotonic_spike_at_mid_NOISE"


def _fake_report(agg_delta: float, g4_delta: float, g4_pass: bool, clears: bool) -> dict:
    return {"g1_positive_aggregate": {"delta": agg_delta},
            "g4_runner_cohort_no_regression": {"delta": g4_delta, "pass": g4_pass},
            "clears_all_required_gates": clears}


def test_decide_arming_g4_uniform_fail_short_circuits_with_named_reason():
    """Mirrors the real shipped run's actual shape: G5-runner coherent, but G4 fails on every
    cell -- must ARM NOTHING and the reason string must name G4 explicitly."""
    reports = {"P1": _fake_report(-1105.85, -3650.45, False, False),
               "P2": _fake_report(-595.25, -905.45, False, False),
               "P3": _fake_report(-252.0, -459.0, False, False)}
    dose_runner = pf.assess_dose_response(-3650.45, -905.45, -459.0, "runner")
    dose_agg = pf.assess_dose_response(-1105.85, -595.25, -252.0, "agg")
    assert dose_runner["coherent"] is True
    v = pf.decide_arming(reports, dose_runner, dose_agg)
    assert v["decision"] == "ARM_NOTHING"
    assert v["cell"] is None
    assert "G4" in v["reason"]


def test_decide_arming_arms_best_cell_when_g4_and_g5_both_clear():
    reports = {"P1": _fake_report(100.0, 50.0, True, True),
               "P2": _fake_report(500.0, 150.0, True, True),
               "P3": _fake_report(200.0, 250.0, True, True)}
    dose_runner = pf.assess_dose_response(50.0, 150.0, 250.0, "runner")
    dose_agg = pf.assess_dose_response(100.0, 500.0, 200.0, "agg")
    v = pf.decide_arming(reports, dose_runner, dose_agg)
    assert v["decision"] == "ARM"
    assert v["cell"] == "P2"


# ---------------------------------------------------------------------------------------------
# RED-proof anchors on the shipped scorecard
# ---------------------------------------------------------------------------------------------
def test_shipped_scorecard_control_reconciles_and_runner_anchor_matches():
    if not pf.OUT_JSON.exists():
        return
    d = json.loads(pf.OUT_JSON.read_text(encoding="utf-8"))
    assert d["population"]["n_control_mismatch_vs_source"] == 0
    rc = d["runner_cohort"]
    assert rc["anchor_check"]["n_matches"] is True
    assert rc["anchor_check"]["pnl_matches"] is True
    assert d["arming_recommendation"]["decision"] in ("ARM", "ARM_NOTHING")


def test_shipped_scorecard_zero_knob_isolation_violations():
    """The scorecard's own headline safety metric: this iteration's whole premise is that the
    knob CANNOT touch post-TP1 mechanics. If the shipped run ever shows a nonzero violation
    count, that is a real regression, not just an unlucky trade -- must RED loudly."""
    if not pf.OUT_JSON.exists():
        return
    d = json.loads(pf.OUT_JSON.read_text(encoding="utf-8"))
    assert d["total_knob_isolation_violations"] == 0, (
        f"shipped scorecard shows {d['total_knob_isolation_violations']} knob isolation "
        "violations -- the isolated pre-TP1 floor leaked into post-TP1 mechanics, "
        "reproducing iteration 3's confound. Investigate before trusting any gate numbers.")


def test_shipped_scorecard_g4_gate_is_the_hard_veto_it_claims_to_be():
    if not pf.OUT_JSON.exists():
        return
    d = json.loads(pf.OUT_JSON.read_text(encoding="utf-8"))
    for cell in ("P1", "P2", "P3"):
        g = d["gates"][cell]
        if not g["g4_runner_cohort_no_regression"]["pass"]:
            assert g["clears_all_required_gates"] is False


def test_shipped_scorecard_mechanism_breakdown_sums_to_n_worse_per_cell():
    if not pf.OUT_JSON.exists():
        return
    d = json.loads(pf.OUT_JSON.read_text(encoding="utf-8"))
    for cell in ("P1", "P2", "P3"):
        g4 = d["gates"][cell]["g4_runner_cohort_no_regression"]
        total_classified = sum(g4["mechanism_breakdown_of_worse_trades"].values())
        assert total_classified == g4["n_worse"]
