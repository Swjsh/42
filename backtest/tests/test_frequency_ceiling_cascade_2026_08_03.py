"""Guards for backtest/tools/frequency_ceiling_cascade_2026_08_03.py (FREQUENCY-CEILING task,
2026-08-03). Pins the PURE functions the whole gate-cascade + AXIS-2 oracle-scan study rests
on -- no I/O, no clock, fixture-driven, mirrors the house style of
test_regime_participation_study.py / test_day_report_card.py.

RED-proofed live this session (see bottom of file's companion report for the transcript):
each of the three marked tests was checked against a deliberately-broken implementation and
observed to fail before being trusted.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_frequency_ceiling_cascade_2026_08_03.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "backtest" / "tools"
for _p in (str(REPO), str(REPO / "backtest"), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

import frequency_ceiling_cascade_2026_08_03 as fc  # noqa: E402
from lib.engine.gates import GATE_ORDER, GateContext  # noqa: E402


# =============================================================================== neutral_gate_params

def test_neutral_gate_params_covers_every_gate_order_key():
    neutral = fc.neutral_gate_params()
    for gate_id, param_key, _action in GATE_ORDER:
        assert gate_id == param_key, "GATE_ORDER's own invariant (gate_id==params_key) moved"
        assert gate_id in neutral, f"neutral_gate_params missing {gate_id!r} -- GATE_ORDER drifted"


def test_neutral_gate_params_ribbon_knobs_are_none_not_zero():
    # 0 is NOT safe here (gates.py's own MIN-RIBBON-SEMI-ARMED-FIX/MAX-RIBBON-DURATION-ZERO-FIX
    # comments: "0 and None BOTH mean off" for the CODE, but 0 for min_ribbon_momentum_cents
    # used to be misread as armed by an OLDER buggy check -- None is the unambiguous choice).
    neutral = fc.neutral_gate_params()
    assert neutral["min_ribbon_momentum_cents"] is None
    assert neutral["max_ribbon_duration_bars"] is None
    assert neutral["vix_bear_hard_cap"] is None


# =============================================================================== evaluate_gates_full

def _base_ctx(**overrides) -> GateContext:
    defaults = dict(
        winning_side="C", winning_triggers=["level_reclaim"], quality_tier="ELITE",
        has_level=True, bar={"open": 700.0, "close": 701.0}, bar_idx=100,
        bar_time=__import__("datetime").datetime(2026, 1, 2, 10, 30),
        vix_now=16.0, ribbon_spread_cents=40.0, ribbon_stack="BULL",
        spy_df=None, ribbon_df=None,
    )
    defaults.update(overrides)
    return GateContext(**defaults)


def test_evaluate_gates_full_finds_all_firing_gates_not_just_first():
    # Two independently-firing gates on the SAME bar: block_elite_bull (ELITE + level_reclaim
    # + vix in [0,25)) AND block_bull_1100_1200 (side=C, bar_time in [11:00,12:00)) both fire.
    # The short-circuiting evaluate_gates() would report ONLY block_elite_bull (it is #3 in
    # GATE_ORDER, block_bull_1100_1200 is #5) -- the whole point of this function is to find
    # BOTH.
    import datetime as dt
    ctx = _base_ctx(
        winning_side="C", winning_triggers=["level_reclaim"], quality_tier="ELITE",
        vix_now=16.0, bar_time=dt.datetime(2026, 1, 2, 11, 30),
    )
    params = {
        "block_elite_bull": True, "block_elite_bull_vix_low": 0.0, "block_elite_bull_vix_high": 25.0,
        "block_bull_1100_1200": True,
    }
    fired = fc.evaluate_gates_full(ctx, params)
    fired_ids = [b.gate_id for b in fired]
    assert fired_ids == ["block_elite_bull", "block_bull_1100_1200"], fired_ids  # GATE_ORDER order


def test_evaluate_gates_full_matches_single_short_circuit_result_as_first_element():
    from lib.engine.gates import evaluate_gates
    import datetime as dt
    ctx = _base_ctx(
        winning_side="C", winning_triggers=["level_reclaim"], quality_tier="ELITE",
        vix_now=16.0, bar_time=dt.datetime(2026, 1, 2, 10, 30),
    )
    params = {"block_elite_bull": True, "block_elite_bull_vix_low": 0.0, "block_elite_bull_vix_high": 25.0}
    short_circuit = evaluate_gates(ctx, params)
    full = fc.evaluate_gates_full(ctx, params)
    assert short_circuit is not None
    assert full[0].gate_id == short_circuit.gate_id
    assert full[0].action == short_circuit.action


def test_evaluate_gates_full_returns_empty_when_nothing_fires():
    ctx = _base_ctx(winning_side="P", winning_triggers=["level_rejection"], quality_tier="LEVEL")
    assert fc.evaluate_gates_full(ctx, {}) == []


def test_evaluate_gates_full_raises_on_unregistered_gate_id():
    """RED-PROOF #1 (mechanism test): if GATE_ORDER grows a gate that neutral_gate_params()
    doesn't know how to disarm, evaluate_gates_full must fail LOUD, not silently under-count.
    Verified live this session: temporarily removing 'block_elite_bull' from a local copy of
    neutral_gate_params's return reproduces exactly this RuntimeError; restored after."""
    import datetime as dt

    orig = fc.neutral_gate_params
    try:
        def _broken():
            d = orig()
            del d["block_elite_bull"]
            return d
        fc.neutral_gate_params = _broken
        ctx = _base_ctx(
            winning_side="C", winning_triggers=["level_reclaim"], quality_tier="ELITE",
            vix_now=16.0, bar_time=dt.datetime(2026, 1, 2, 10, 30),
        )
        params = {"block_elite_bull": True, "block_elite_bull_vix_low": 0.0, "block_elite_bull_vix_high": 25.0}
        with pytest.raises(RuntimeError, match="no neutral value registered"):
            fc.evaluate_gates_full(ctx, params)
    finally:
        fc.neutral_gate_params = orig


# =============================================================================== namespaced_filter_blockers

def test_namespaced_filter_blockers_bear_vs_bull_same_number_different_key():
    bear = fc.namespaced_filter_blockers("P", [8])
    bull = fc.namespaced_filter_blockers("C", [8])
    assert bear == {"bear:filter_8"}
    assert bull == {"bull:filter_8"}
    assert bear != bull  # RED-PROOF #2 target: a merge bug would make these equal


def test_namespaced_filter_blockers_invalid_side_raises():
    with pytest.raises(ValueError):
        fc.namespaced_filter_blockers("X", [1])


def test_namespaced_filter_blockers_empty_list():
    assert fc.namespaced_filter_blockers("P", []) == frozenset()


# =============================================================================== derive_winning_side

@pytest.mark.parametrize("bear_passed,bear_trig,bull_passed,bull_trig,expected", [
    (True, ["level_rejection"], False, [], "P"),
    (False, [], True, ["level_reclaim"], "C"),
    (False, [], False, [], None),
    (True, ["level_rejection", "confluence"], True, ["level_reclaim"], "P"),
    (True, ["level_rejection"], True, ["level_reclaim", "confluence"], "C"),
    (True, ["level_rejection"], True, ["level_reclaim"], None),  # exact tie -> conflict skip
])
def test_derive_winning_side_matches_orchestrator_tiebreak(bear_passed, bear_trig, bull_passed, bull_trig, expected):
    got = fc.derive_winning_side(
        bear_passed=bear_passed, bear_triggers=bear_trig,
        bull_passed=bull_passed, bull_triggers=bull_trig,
    )
    assert got == expected


# =============================================================================== build_overlap_matrix

def test_build_overlap_matrix_sole_vs_pair_counting():
    rows = [
        frozenset({"bear:filter_8"}),
        frozenset({"bear:filter_8"}),
        frozenset({"bear:filter_8", "bear:filter_5"}),
        frozenset({"quality_lock"}),
    ]
    out = fc.build_overlap_matrix(rows)
    assert out["n_blocked"] == 4
    assert out["size_histogram"] == {1: 3, 2: 1}
    # bear:filter_8 was the SOLE blocker twice (rows 0,1); NOT sole on row 2 (co-fired)
    assert out["sole_blocker_counts"]["bear:filter_8"] == 2
    assert out["sole_blocker_counts"]["quality_lock"] == 1
    assert "bear:filter_5" not in out["sole_blocker_counts"]
    assert out["pair_counts"]["bear:filter_5|bear:filter_8"] == 1
    assert out["member_counts"]["bear:filter_8"] == 3  # appears in rows 0,1,2


def test_build_overlap_matrix_empty_set_raises():
    """RED-PROOF #3: an empty blocker set slipping into this function would silently
    understate the blocking rate (it should never happen -- an empty set means the
    candidate ENTERED, not that it was blocked). Verified live: passing [frozenset()] here
    raised ValueError as written; a version of the function using `if not s: continue`
    instead of `raise` would swallow this silently -- exactly the bug this guards against."""
    with pytest.raises(ValueError, match="EMPTY blocker set"):
        fc.build_overlap_matrix([frozenset()])


# =============================================================================== stats: one_sample_p / bh_fdr

def test_one_sample_p_zero_mean_is_one():
    assert fc.one_sample_p([5.0, -5.0]) == pytest.approx(1.0, abs=1e-9)


def test_one_sample_p_single_value_undefined_returns_one():
    assert fc.one_sample_p([5.0]) == 1.0


def test_one_sample_p_large_consistent_effect_is_small():
    p = fc.one_sample_p([100.0, 105.0, 98.0, 102.0, 101.0])
    assert p < 0.01


def test_bh_fdr_all_survive_when_all_tiny():
    survive = fc.bh_fdr([0.001, 0.002, 0.003], q=0.10)
    assert survive == [True, True, True]


def test_bh_fdr_none_survive_when_all_large():
    survive = fc.bh_fdr([0.9, 0.8, 0.95], q=0.10)
    assert survive == [False, False, False]


def test_bh_fdr_mixed_step_up_boundary():
    # classic textbook-shape check: sorted p = [0.01, 0.04, 0.03, 0.20] at q=0.05, m=4
    # thresholds at ranks 1..4: 0.0125, 0.025, 0.0375, 0.05 -- sorted p = [0.01,0.03,0.04,0.20]
    # rank1 0.01<=0.0125 T; rank2 0.03<=0.025 F; rank3 0.04<=0.0375 F; rank4 0.20<=0.05 F
    # largest_k with p_(k)<=thresh is rank1 -> only the smallest survives
    pvals = [0.04, 0.01, 0.20, 0.03]
    survive = fc.bh_fdr(pvals, q=0.05)
    assert survive == [False, True, False, False]


def test_bh_fdr_empty_input():
    assert fc.bh_fdr([]) == []


# =============================================================================== classify_a_vs_c

def test_classify_a_vs_c_nothing_tradeable_below_floor():
    assert fc.classify_a_vs_c(oracle_bound_dollars=40.0, detector_fired_near_move=False) == "NOTHING_TRADEABLE"


def test_classify_a_vs_c_nothing_tradeable_none():
    assert fc.classify_a_vs_c(oracle_bound_dollars=None, detector_fired_near_move=False) == "NOTHING_TRADEABLE"


def test_classify_a_vs_c_detector_fired_weak():
    assert fc.classify_a_vs_c(oracle_bound_dollars=150.0, detector_fired_near_move=True) == "DETECTOR_FIRED_WEAK"


def test_classify_a_vs_c_genuine_gap():
    assert fc.classify_a_vs_c(oracle_bound_dollars=150.0, detector_fired_near_move=False) == "NO_DETECTOR_GENUINE_GAP"


def test_classify_a_vs_c_exactly_at_floor_counts_as_tradeable():
    assert fc.classify_a_vs_c(oracle_bound_dollars=100.0, detector_fired_near_move=False) == "NO_DETECTOR_GENUINE_GAP"


# =============================================================================== clean_move_candidates

def _bar(idx, o, h, l, c):
    return {"idx": idx, "open": o, "high": h, "low": l, "close": c}


def test_clean_move_candidates_finds_clean_bounce_off_support():
    # level=700. Bar 0 touches (low=699.85, within 0.30), approached from above (open=700.2).
    # Bar 1 (the break bar) closes decisively above 700+0.30. Then 3 bars hold well above the
    # level (no meaningful retrace) -> clean=True.
    # Bar 1's own low (700.50) is deliberately kept OUTSIDE tolerance of the level (700.50 -
    # 0.30 = 700.20 > 700) so it does not ALSO register as its own separate touch -- this
    # fixture isolates the single touch-at-bar-0 -> break-at-bar-1 candidate.
    bars = [
        _bar(0, 700.20, 700.40, 699.85, 700.10),
        _bar(1, 700.15, 701.00, 700.50, 700.90),   # decisive close 700.90 >= 700.30
        _bar(2, 700.90, 702.00, 700.80, 701.80),
        _bar(3, 701.80, 703.00, 701.70, 702.90),
        _bar(4, 702.90, 703.50, 702.80, 703.20),
    ]
    out = fc.clean_move_candidates([700.0], bars, tolerance=0.30, forward_bars=3)
    assert len(out) == 1
    cand = out[0]
    assert cand["direction"] == "up"
    assert cand["clean"] is True
    assert cand["peak_move_dollars"] > 2.0


def test_clean_move_candidates_rejects_chop_that_retraces_past_threshold():
    # Same touch/break shape, but the move immediately gives back >50% of its peak.
    bars = [
        _bar(0, 700.20, 700.40, 699.85, 700.10),
        _bar(1, 700.15, 701.00, 700.10, 700.90),
        _bar(2, 700.90, 702.00, 700.00, 700.05),  # gave back almost the whole move
    ]
    out = fc.clean_move_candidates([700.0], bars, tolerance=0.30, forward_bars=2)
    assert len(out) == 1
    assert out[0]["clean"] is False


def test_clean_move_candidates_no_touch_is_empty():
    bars = [_bar(0, 710.0, 711.0, 709.5, 710.5), _bar(1, 710.5, 711.5, 710.0, 711.0)]
    out = fc.clean_move_candidates([700.0], bars, tolerance=0.30)
    assert out == []


def test_clean_move_candidates_empty_bars():
    assert fc.clean_move_candidates([700.0], []) == []


# =============================================================================== levels_seen_for_day / detector_fired_near

def test_levels_seen_for_day_unions_and_dedupes():
    bear_capture = {
        10: {"levels_active": [700.001, 705.0], "multi_day_levels": [710.0]},
        11: {"levels_active": [700.002, 705.0], "multi_day_levels": [710.0]},  # near-dup of 700.001
        12: {"levels_active": [699.0], "multi_day_levels": []},
    }
    out = fc.levels_seen_for_day(bear_capture, [10, 11, 12])
    # rounded to cents: 700.00 appears once (both 700.001 and 700.002 round to 700.0)
    assert out == [699.0, 700.0, 705.0, 710.0]


def test_levels_seen_for_day_missing_bar_idx_skipped_not_raised():
    bear_capture = {10: {"levels_active": [700.0], "multi_day_levels": []}}
    out = fc.levels_seen_for_day(bear_capture, [10, 999])  # 999 not captured
    assert out == [700.0]


def test_detector_fired_near_finds_trigger_within_window():
    bear_capture = {100: {"triggers_fired": []}, 101: {"triggers_fired": ["level_rejection"]}}
    bull_capture = {100: {"triggers_fired": []}, 101: {"triggers_fired": []}}
    assert fc.detector_fired_near(bear_capture, bull_capture, touch_idx=100, window=2) is True


def test_detector_fired_near_false_when_nothing_in_window():
    bear_capture = {100: {"triggers_fired": []}, 105: {"triggers_fired": ["level_rejection"]}}
    bull_capture = {100: {"triggers_fired": []}}
    assert fc.detector_fired_near(bear_capture, bull_capture, touch_idx=100, window=2) is False
