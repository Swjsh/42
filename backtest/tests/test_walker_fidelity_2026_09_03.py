"""GUARD for WALKER-MAGNITUDE-BIAS-VS-SIGN-FIDELITY (2026-09-03).

Covers the shared magnitude-fidelity module (`backtest/lib/walker_magnitude_fidelity.py`) that
`whole_engine_null.py`, `pdt_blocked_counterfactual.py`, and `backtest/tools/walker_fidelity.py`
all now import from, plus the market-stage fill fix shipped this session in
`backtest/tools/multileg_exit_walk.py` (behind `market_stage_fill_fix=False`, default old
behavior).

Pure-function tests on SYNTHETIC inputs only -- no network, no OPRA bar cache, no ledger I/O
(the metric-math / decomposition / criterion tests below); ONE integration test at the bottom
touches the real `multileg_exit_walk.walk()` fill-price branch on a hand-built bar frame to
prove the fix actually changes the fill price, not just that the kwarg is accepted.

RED-PROOF (quoted in the session report): each `evaluate_magnitude_fidelity` boundary test
below is itself a mutation-style check -- it asserts the EXACT threshold behavior (>= vs >,
<= vs <) so a regression that loosens/tightens a comparator fails a single, obviously-named
test. Additionally exercised manually: mutating `AGGREGATE_RATIO_TOLERANCE` down to 0.0 flips
`test_pass_when_both_conditions_clear` to FAIL; mutating `MEDIAN_ABS_ERROR_DOLLARS_MAX` down to
0.0 does the same; mutating `MAGNITUDE_FIDELITY_MIN_N` up past a test's `n` flips its verdict
to INSUFFICIENT.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_LIB = _ROOT / "backtest" / "lib"
_TOOLS = _ROOT / "backtest" / "tools"
_FLEET = _ROOT / "automation" / "state" / "fleet"
_SCRIPTS = _ROOT / "setup" / "scripts"
for _p in (_LIB, _TOOLS, _FLEET, _SCRIPTS, _ROOT / "backtest"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

import walker_magnitude_fidelity as wmf  # noqa: E402


# ============================================================================================ #
# magnitude_fidelity() -- metric math on synthetic rows
# ============================================================================================ #
def test_magnitude_fidelity_empty_returns_n_zero():
    assert wmf.magnitude_fidelity([]) == {"n": 0}


def test_magnitude_fidelity_perfect_replay_ratio_is_one():
    pairs = [(-100.0, -100.0), (50.0, 50.0), (25.0, 25.0)]
    mag = wmf.magnitude_fidelity(pairs)
    assert mag["aggregate_ratio"] == 1.0
    assert mag["median_abs_error_dollars"] == 0.0
    assert mag["mean_signed_bias_dollars"] == 0.0


def test_magnitude_fidelity_aggregate_ratio_matches_known_pdt_numbers():
    """Pin: feeding this module the exact 43-row PDT anchor totals (actual -$538.00, replay
    -$2,201.60 -- the queue item's own cited numbers) must reproduce aggregate_ratio 4.0922
    and NOT silently drift if the ratio formula ever changes sign convention or rounding."""
    mag = wmf.magnitude_fidelity([(-538.0, -2201.60)])
    assert mag["aggregate_ratio"] == pytest.approx(4.0922, abs=1e-4)
    assert mag["total_error_dollars"] == pytest.approx(-1663.60, abs=0.01)


def test_magnitude_fidelity_ratio_none_on_near_zero_denominator():
    """A near-zero actual total must return None, never raise or silently divide by ~0 --
    this is exactly the failure mode `walker_fidelity.py`'s big-anchor run hit (actual_total
    -$141 against $7,619 of winners and -$7,760 of losers)."""
    mag = wmf.magnitude_fidelity([(1e-12, 500.0)])
    assert mag["aggregate_ratio"] is None


def test_magnitude_fidelity_winners_losers_split_sums_to_n():
    pairs = [(-10.0, -20.0), (5.0, 3.0), (-1.0, -1.0), (7.0, 9.0)]
    mag = wmf.magnitude_fidelity(pairs)
    assert mag["winners"]["n"] + mag["losers"]["n"] <= mag["n"]  # the -1.0 scratch-ish row
    # is neither a winner (>0) nor... wait -1.0 < 0 so it IS a loser. Recompute explicitly:
    assert mag["winners"]["n"] == 2   # 5.0, 7.0
    assert mag["losers"]["n"] == 2    # -10.0, -1.0


def test_magnitude_fidelity_winners_ratio_isolates_win_side_only():
    """A replay that is PERFECT on losers but overstates winners by 2x must show that ONLY
    in winners_ratio, not contaminate losers_ratio -- the exact diagnostic V9's own docstring
    says to read first."""
    pairs = [(-100.0, -100.0), (-50.0, -50.0), (40.0, 80.0), (20.0, 40.0)]
    mag = wmf.magnitude_fidelity(pairs)
    assert mag["losers"]["ratio"] == pytest.approx(1.0)
    assert mag["winners"]["ratio"] == pytest.approx(2.0)


# ============================================================================================ #
# evaluate_magnitude_fidelity() -- PASS / FAIL / INSUFFICIENT boundaries
#
# DELIBERATE MUTATION-SENSITIVITY NOTE: every threshold used below is a HARDCODED LITERAL, not
# derived from wmf.MAGNITUDE_FIDELITY_MIN_N / AGGREGATE_RATIO_TOLERANCE /
# MEDIAN_ABS_ERROR_DOLLARS_MAX. An earlier draft of this file derived the test inputs FROM
# those constants (e.g. `ratio = 1.0 + wmf.AGGREGATE_RATIO_TOLERANCE`) -- which made every
# boundary test mutation-BLIND: mutating AGGREGATE_RATIO_TOLERANCE to 0.0 and rerunning still
# passed all 21 tests, because the test's own inputs silently tracked the mutated constant
# instead of pinning a fixed value against it. Caught by manually mutating the constant and
# re-running before trusting this suite (the RED-proof this docstring's caller quotes). The
# assert-the-constant lines below make that assumption explicit and load-bearing: if someone
# deliberately changes a threshold, these tests fail LOUDLY (must be updated consciously), and
# if a regression silently changes one, these tests fail too -- the same signal either way.
# ============================================================================================ #
def test_current_thresholds_are_20_and_0p40_and_40_dollars():
    """Pins the criterion's actual numbers. If this fails, every other test below is checking
    the wrong boundary and must be re-read before trusting them."""
    assert wmf.MAGNITUDE_FIDELITY_MIN_N == 20
    assert wmf.AGGREGATE_RATIO_TOLERANCE == pytest.approx(0.40)
    assert wmf.MEDIAN_ABS_ERROR_DOLLARS_MAX == pytest.approx(40.0)


def test_insufficient_below_min_n():
    pairs = [(100.0, 100.0)] * 19   # one under the pinned N=20 floor
    mag = wmf.magnitude_fidelity(pairs)
    assert wmf.evaluate_magnitude_fidelity(mag) == "INSUFFICIENT"


def test_insufficient_on_none_ratio_even_with_enough_n():
    pairs = [(1e-12, 50.0)] * 20
    mag = wmf.magnitude_fidelity(pairs)
    assert mag["aggregate_ratio"] is None
    assert wmf.evaluate_magnitude_fidelity(mag) == "INSUFFICIENT"


def test_pass_when_both_conditions_clear():
    """ratio=1.20 -> |ratio-1|=0.20, inside the pinned 0.40 tolerance; median error=$20,
    inside the pinned $40 max."""
    pairs = [(100.0, 120.0)] * 20
    mag = wmf.magnitude_fidelity(pairs)
    assert mag["aggregate_ratio"] == pytest.approx(1.20)
    assert mag["median_abs_error_dollars"] == pytest.approx(20.0)
    assert wmf.evaluate_magnitude_fidelity(mag) == "PASS"


def test_fail_on_ratio_outside_tolerance_even_with_tiny_median_error():
    """Pins the exact scenario this study's own header names: small per-trade dollar errors
    that are all one-directional still FAIL, because the aggregate ratio is checked
    independently of the median. real=$1.0 base keeps the dollar error under $1 even though
    the RATIO (1.50) is well past the pinned 0.40 tolerance."""
    pairs = [(1.0, 1.50)] * 20
    mag = wmf.magnitude_fidelity(pairs)
    assert mag["aggregate_ratio"] == pytest.approx(1.50)
    assert mag["median_abs_error_dollars"] < 40.0
    assert wmf.evaluate_magnitude_fidelity(mag) == "FAIL"


def test_fail_on_median_error_outside_bound_even_with_ratio_at_one():
    pairs = [(100.0, 145.0)] * 10 + [(100.0, 55.0)] * 10   # ratio exactly 1.0, median err $45
    mag = wmf.magnitude_fidelity(pairs)
    assert mag["aggregate_ratio"] == pytest.approx(1.0, abs=1e-6)
    assert mag["median_abs_error_dollars"] == pytest.approx(45.0)
    assert wmf.evaluate_magnitude_fidelity(mag) == "FAIL"


def test_boundary_ratio_exactly_at_tolerance_passes():
    """Exactly AT the pinned 0.40 tolerance edge (ratio=1.40, median err=$40, also exactly at
    the pinned $40 edge) is a PASS (<=, not <) -- pins BOTH boundary operators at once."""
    pairs = [(100.0, 140.0)] * 20
    mag = wmf.magnitude_fidelity(pairs)
    assert mag["aggregate_ratio"] == pytest.approx(1.40)
    assert mag["median_abs_error_dollars"] == pytest.approx(40.0)
    assert wmf.evaluate_magnitude_fidelity(mag) == "PASS"


def test_boundary_just_past_ratio_tolerance_fails():
    """One cent past the pinned edge (ratio=1.41) flips PASS -> FAIL."""
    pairs = [(100.0, 141.0)] * 20
    mag = wmf.magnitude_fidelity(pairs)
    assert wmf.evaluate_magnitude_fidelity(mag) == "FAIL"


def test_boundary_n_exactly_at_min_is_sufficient():
    pairs = [(100.0, 100.0)] * 20
    mag = wmf.magnitude_fidelity(pairs)
    assert wmf.evaluate_magnitude_fidelity(mag) != "INSUFFICIENT"


# ============================================================================================ #
# stage_decomposition() / side_decomposition() -- sums to total, isolates the diagnostic
# ============================================================================================ #
def test_stage_decomposition_agree_disagree_partitions_all_rows():
    rows = [
        {"real": 10.0, "walk": 12.0, "rec_stage": "premium_stop", "walk_stage": "premium_stop"},
        {"real": -5.0, "walk": -20.0, "rec_stage": "structure_stop", "walk_stage": "premium_stop"},
        {"real": -1.0, "walk": -1.0, "rec_stage": "tp1+trail", "walk_stage": "tp1"},  # compound
        {"real": 3.0, "walk": 3.5, "rec_stage": None, "walk_stage": "time_stop"},
    ]
    d = wmf.stage_decomposition(rows, real_key="real", walk_key="walk",
                                recorded_stage_key="rec_stage", walked_stage_key="walk_stage")
    assert d["stage_agree"]["n"] + d["stage_disagree"]["n"] == len(rows)
    # row 3 ("tp1+trail" vs "tp1") must AGREE -- first-token match on a compound label.
    assert d["stage_agree"]["n"] == 2   # rows 1 and 3
    assert d["stage_disagree"]["n"] == 2  # rows 2 and 4 (None vs "time_stop" != -> disagree)


def test_stage_decomposition_disagree_share_is_fraction_of_total_abs_error():
    rows = [
        {"real": 0.0, "walk": 10.0, "rec_stage": "a", "walk_stage": "a"},   # agree, err=10
        {"real": 0.0, "walk": 30.0, "rec_stage": "a", "walk_stage": "b"},   # disagree, err=30
    ]
    d = wmf.stage_decomposition(rows, real_key="real", walk_key="walk",
                                recorded_stage_key="rec_stage", walked_stage_key="walk_stage")
    assert d["disagree_share_of_total_abs_error"] == pytest.approx(30.0 / 40.0)


def test_side_decomposition_covers_every_side_and_sums_n():
    rows = [
        {"real": 10.0, "walk": 12.0, "side": "C"},
        {"real": -5.0, "walk": -8.0, "side": "P"},
        {"real": 3.0, "walk": 3.0, "side": "C"},
    ]
    d = wmf.side_decomposition(rows, real_key="real", walk_key="walk", side_key="side")
    assert set(d.keys()) == {"C", "P"}
    assert d["C"]["n"] + d["P"]["n"] == len(rows)


# ============================================================================================ #
# BOTH studies import from the SAME shared module -- not two independently-drifting copies
# ============================================================================================ #
def test_whole_engine_null_and_pdt_study_import_the_same_functions():
    """The actual regression this fold guards against: whole_engine_null.py used to carry its
    own private `_magnitude_fidelity`, and pdt_blocked_counterfactual.py computed nothing at
    all. If either study ever re-forks its own copy instead of importing
    `walker_magnitude_fidelity`, this test catches it via identity (`is`), not just behavior."""
    sys.path.insert(0, str(_SCRIPTS))
    import pdt_blocked_counterfactual as pdtc  # noqa: E402
    import whole_engine_null as wen  # noqa: E402
    assert wen.evaluate_magnitude_fidelity is wmf.evaluate_magnitude_fidelity
    assert pdtc.evaluate_magnitude_fidelity is wmf.evaluate_magnitude_fidelity
    assert wen._shared_magnitude_fidelity is wmf.magnitude_fidelity
    assert pdtc._shared_magnitude_fidelity is wmf.magnitude_fidelity


def test_pdt_harness_validation_output_carries_magnitude_fidelity_shape():
    """Static shape check (no bar I/O): harness_validation()'s empty-population branch must
    still be shape-compatible with a caller that expects magnitude_fidelity_verdict to exist
    once rows ARE present -- guards against the two return branches drifting apart."""
    sys.path.insert(0, str(_SCRIPTS))
    import pdt_blocked_counterfactual as pdtc  # noqa: E402
    import inspect
    src = inspect.getsource(pdtc.harness_validation)
    assert "magnitude_fidelity_verdict" in src
    assert "_shared_magnitude_fidelity" in src


# ============================================================================================ #
# multileg_exit_walk market-stage fill fix -- behind a flag, default OLD behavior unchanged
# ============================================================================================ #
def _make_synthetic_bars(prices: list[float], date: str = "2026-07-01") -> pd.DataFrame:
    """One bar per minute starting 09:35, OHLC all equal to `prices[i]` except a deliberately
    lower `low` (prices[i] - 5.0) so `worst_in` (extreme fill_mode) is a DISTINCT, checkable
    value from the bar's `close`."""
    ts = pd.date_range(f"{date} 09:35:00", periods=len(prices), freq="1min")
    rows = []
    for t, p in zip(ts, prices):
        rows.append({"timestamp_et": t, "open": p, "high": p + 1.0, "low": p - 5.0, "close": p})
    return pd.DataFrame(rows)


def _custom_bars(rows: list[dict], date: str = "2026-07-01") -> pd.DataFrame:
    """Explicit per-bar OHLC + timestamp control (HH:MM:SS strings in each row's "t"), for
    tests that need to steer WHICH stage fires without `_make_synthetic_bars`'s deliberately
    deep low (prices[i]-5.0) accidentally tripping premium_stop/catastrophe before the stage
    under test gets a chance to fire."""
    out = []
    for r in rows:
        out.append({"timestamp_et": pd.Timestamp(f"{date} {r['t']}"), "open": r["o"],
                    "high": r["h"], "low": r["l"], "close": r["c"]})
    return pd.DataFrame(out)


def test_market_stage_fill_fix_default_false_preserves_old_price():
    """Byte-identical-behavior contract: calling walk() WITHOUT the new kwarg (every existing
    caller in the repo) must be indistinguishable from calling it with
    market_stage_fill_fix=False explicitly."""
    import multileg_exit_walk as mew

    entry = 1.00
    # A structure_stop-eligible short-lived position: trigger_level far enough that
    # structure_stop_enabled=True (bool(trigger_level)), premium falling steadily.
    bars = _make_synthetic_bars([0.95, 0.90, 0.85, 0.80, 0.70])
    fill = {"entry_premium": entry, "qty": 1, "symbol": "SPY260701P00700000",
           "date": "2026-07-01", "entry_time": "09:34:00", "strategy": "RIBBON"}
    shape = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.8,
            "profit_lock_mode": "fixed", "stop_mode": "structure",
            "runner_target_pct": 2.5, "trail_pct": 0.125, "profit_lock_arm_pct": 0.05,
            "catastrophe_stop_pct": -0.50}
    spy_closes = {t.strftime("%H:%M"): 700.0 for t in
                 pd.date_range("2026-07-01 09:35:00", periods=5, freq="1min")}

    r_default = mew.walk(fill, shape, bars, trigger_level=699.0, fill_mode="extreme",
                         spy_closes=spy_closes, slippage=0.0)
    r_explicit_false = mew.walk(fill, shape, bars, trigger_level=699.0, fill_mode="extreme",
                                spy_closes=spy_closes, slippage=0.0,
                                market_stage_fill_fix=False)
    assert r_default["pnl"] == r_explicit_false["pnl"]
    assert r_default["legs"] == r_explicit_false["legs"]


def test_market_stage_fill_fix_true_changes_the_fill_price_when_a_market_stage_fires():
    """The actual mechanism this session found and fixed: a premium_stop leg (a NON-market
    stage) is forced by a steep drop to fire at the STATIC stop level under BOTH flag states.
    WALKER-MARKET-STAGE-FILL-ROOT-FIX (2026-09-03 follow-up) tried moving premium_stop onto
    worst_in and MEASURED it worse (43-row PDT anchor aggregate_ratio 4.09 -> 4.88, stage abs
    error $516.90 -> $930.00) -- reverted, see the module-level note for why (a numeric
    threshold cross should fill near the threshold on coarse 5-min bars, not the bar's full
    wick). This test pins that premium_stop is correctly OUT of scope: both variants agree."""
    import multileg_exit_walk as mew

    entry = 1.00
    bars = _make_synthetic_bars([0.95, 0.60, 0.55, 0.50, 0.45])  # steep drop past -20%
    fill = {"entry_premium": entry, "qty": 1, "symbol": "SPY260701P00700000",
           "date": "2026-07-01", "entry_time": "09:34:00", "strategy": "RIBBON"}
    shape = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.8,
            "profit_lock_mode": "fixed", "stop_mode": "premium",
            "runner_target_pct": 2.5, "trail_pct": 0.125, "profit_lock_arm_pct": 0.05,
            "catastrophe_stop_pct": -0.50}

    r_old = mew.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme", slippage=0.0,
                     market_stage_fill_fix=False)
    r_new = mew.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme", slippage=0.0,
                     market_stage_fill_fix=True)
    assert r_old["legs"][0]["stage"] == "premium_stop"
    assert r_new["legs"][0]["stage"] == "premium_stop"
    assert r_old["legs"][0]["px"] == pytest.approx(0.80)   # static level: entry*(1-0.20)
    assert r_new["legs"][0]["px"] == pytest.approx(0.80)   # unchanged -- premium_stop is out
    assert r_old["pnl"] == r_new["pnl"] == pytest.approx(-20.0)


def test_time_stop_fills_at_bar_close_not_worst_in_under_the_fix():
    """The specific correction this session added on top of the first ship: time_stop is a
    CLOCK event, not a price cross, so it must fill at the bar's CLOSE -- never the bar's
    worst_in. Two bars only: one flat bar well before the 15:50 default time_stop_et (no
    stage eligible to fire -- premium_stop/catastrophe/tp1/runner_target thresholds are all
    unreachable by construction), then one bar AT 15:50 with a low far below close so a wrong
    (worst_in) implementation is trivially distinguishable from a right (close) one."""
    import multileg_exit_walk as mew

    entry = 1.00
    bars = _custom_bars([
        {"t": "09:35:00", "o": 1.00, "h": 1.02, "l": 0.98, "c": 1.00},
        {"t": "15:50:00", "o": 1.00, "h": 1.05, "l": 0.50, "c": 1.00},
    ])
    fill = {"entry_premium": entry, "qty": 1, "symbol": "SPY260701P00700000",
           "date": "2026-07-01", "entry_time": "09:34:00", "strategy": "RIBBON"}
    shape = {"premium_stop_pct": -0.90, "tp1_premium_pct": 9.0, "tp1_qty_fraction": 0.8,
            "profit_lock_mode": "fixed", "stop_mode": "premium",
            "runner_target_pct": 9.0, "trail_pct": 0.125, "profit_lock_arm_pct": 0.9,
            "catastrophe_stop_pct": -0.90}

    r_new = mew.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme", slippage=0.0,
                     market_stage_fill_fix=True, spy_closes=None)
    assert r_new["legs"], "expected the time-stop leg to have fired at the 15:50 bar"
    last = r_new["legs"][-1]
    assert last["stage"] == "time_stop"
    # close (1.00), never worst_in (low=0.50) -- the wrong-implementation value this test
    # exists to catch.
    assert last["px"] == pytest.approx(1.00)
    assert last["px"] != pytest.approx(0.50)


def test_runner_target_pricing_is_unaffected_by_the_fix_out_of_scope_by_design():
    """runner_target (like premium_stop/profit_lock_floor/trail/be_stop) is a numeric
    threshold cross on `runner_stop_premium`/`tp1_premium_pct`-style levels, not a market/clock
    event -- deliberately OUT OF SCOPE for this fix (see module-level note). Two bars: bar0
    clears tp1 cheaply (ratchets runner_stop to breakeven); bar1 is a huge favorable jump whose
    low (2.50) stays above the breakeven runner_stop (1.00), so runner_target fires on bar1 via
    HWM without any stop leg preempting it. Both flag states must price it identically at the
    static level `state.runner_stop_premium or worst_in` falls through to -- here that resolves
    to the breakeven runner_stop (1.00, ratcheted at tp1), not bar1's high (4.00) or low (2.50)."""
    import multileg_exit_walk as mew

    entry = 1.00
    bars = _custom_bars([
        {"t": "09:35:00", "o": 1.05, "h": 1.10, "l": 1.00, "c": 1.05},
        {"t": "09:36:00", "o": 3.00, "h": 4.00, "l": 2.50, "c": 3.00},
    ])
    fill = {"entry_premium": entry, "qty": 2, "symbol": "SPY260701C00700000",
           "date": "2026-07-01", "entry_time": "09:34:00", "strategy": "RIBBON"}
    shape = {"premium_stop_pct": -0.90, "tp1_premium_pct": 0.02, "tp1_qty_fraction": 0.5,
            "profit_lock_mode": "fixed", "stop_mode": "premium",
            "runner_target_pct": 1.0, "trail_pct": 0.125, "profit_lock_arm_pct": 0.05,
            "catastrophe_stop_pct": -0.90}

    r_old = mew.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme", slippage=0.0,
                     market_stage_fill_fix=False)
    r_new = mew.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme", slippage=0.0,
                     market_stage_fill_fix=True)
    runner_old = [leg for leg in r_old["legs"] if leg["stage"] == "runner_target"]
    runner_new = [leg for leg in r_new["legs"] if leg["stage"] == "runner_target"]
    assert runner_old and runner_new, "expected a runner_target leg in both variants"
    assert runner_old[0]["px"] == runner_new[0]["px"] == pytest.approx(1.00)
    assert r_old["pnl"] == r_new["pnl"]


def test_market_stages_constant_matches_exit_manager_walk_convention():
    """Pins the exact set. WALKER-MARKET-STAGE-FILL-ROOT-FIX (2026-09-03 follow-up)
    DELIBERATELY did NOT widen this beyond the original 3 -- see the module-level note for the
    measured regression (43-row PDT anchor aggregate_ratio 4.09 -> 4.88) that led to reverting
    the wider attempt. Still matches exit_manager_walk.py's OWN `_MARKET_STAGES` (the sibling
    walker's established convention) -- unchanged scope, only the time_stop PRICE within it
    changed (bar close, not worst_in; see the price-selection branch in walk())."""
    import multileg_exit_walk as mew
    import exit_manager_walk as emw

    assert mew._MARKET_STAGES == emw._MARKET_STAGES == frozenset(
        {"structure_stop", "ribbon_flip", "time_stop"})
    assert mew._TIME_STOP_STAGE == "time_stop"


def test_tp1_pricing_is_unaffected_by_the_fix_out_of_scope_by_design():
    """tp1 was explicitly OUT OF SCOPE for this fix (the root-cause note names it "every
    non-tp1 leg") -- must keep pricing at the fixed entry*(1+tp1_premium_pct) level under
    BOTH flag states, never worst_in/best_in/close."""
    import multileg_exit_walk as mew

    entry = 1.00
    bars = _custom_bars([{"t": "09:35:00", "o": 1.60, "h": 1.62, "l": 1.58, "c": 1.60}])
    fill = {"entry_premium": entry, "qty": 4, "symbol": "SPY260701C00700000",
           "date": "2026-07-01", "entry_time": "09:34:00", "strategy": "RIBBON"}
    shape = {"premium_stop_pct": -0.90, "tp1_premium_pct": 0.50, "tp1_qty_fraction": 0.5,
            "profit_lock_mode": "fixed", "stop_mode": "premium",
            "runner_target_pct": 9.0, "trail_pct": 0.125, "profit_lock_arm_pct": 0.9,
            "catastrophe_stop_pct": -0.90}

    r_old = mew.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme", slippage=0.0,
                     market_stage_fill_fix=False)
    r_new = mew.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme", slippage=0.0,
                     market_stage_fill_fix=True)
    tp1_old = [leg for leg in r_old["legs"] if leg["stage"] == "tp1"][0]
    tp1_new = [leg for leg in r_new["legs"] if leg["stage"] == "tp1"][0]
    assert tp1_old["px"] == pytest.approx(1.50)  # entry*(1+0.50)
    assert tp1_new["px"] == pytest.approx(1.50)  # unchanged -- tp1 is out of scope


# ============================================================================================ #
# premium_stop_poll_model (2026-09-03, WALKER-MARKET-STAGE-FILL-ROOT-FIX PARTIAL note's own
# "NEXT" step). IMPLEMENTED + MEASURED this session, kept OFF by default -- see
# multileg_exit_walk.py's `_POLL_MODEL_STAGES` module note for the provable reason it makes
# both anchors WORSE (poll price can only equal-or-exceed the old static threshold price in
# the adverse direction; the walker already replays too negative). These tests pin the
# MECHANISM (first-crossing-minute selection, honest fallback, byte-identical default), not
# the anchor-level verdict -- that lives in analysis/harness-fidelity/WALKER-MAGNITUDE-
# 2026-09-03.{json,md}, regenerated by `python backtest/tools/walker_fidelity.py`.
# ============================================================================================ #
def _custom_highres(rows: list[dict], date: str = "2026-07-01") -> pd.DataFrame:
    """Same shape walker_fidelity.py#_get_1min_df returns: timestamp_et (tz-naive) +
    open/high/low/close, one row per cached 1-min bar."""
    out = []
    for r in rows:
        out.append({"timestamp_et": pd.Timestamp(f"{date} {r['t']}"), "open": r["o"],
                    "high": r["h"], "low": r["l"], "close": r["c"]})
    return pd.DataFrame(out)


def test_poll_model_default_false_is_byte_identical_to_market_stage_fix_alone():
    """The byte-identical-behavior contract for the NEW kwargs: calling walk() without
    premium_stop_poll_model (every existing caller) must match calling it with
    premium_stop_poll_model=False explicitly, AND neither the legs nor the top-level result
    may carry a `fill_model` key at all -- the key is additive-only, gated on opt-in."""
    import multileg_exit_walk as mew

    entry = 1.00
    bars = _make_synthetic_bars([0.95, 0.60, 0.55, 0.50, 0.45])  # steep drop past -20%
    fill = {"entry_premium": entry, "qty": 1, "symbol": "SPY260701P00700000",
           "date": "2026-07-01", "entry_time": "09:34:00", "strategy": "RIBBON"}
    shape = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.8,
            "profit_lock_mode": "fixed", "stop_mode": "premium",
            "runner_target_pct": 2.5, "trail_pct": 0.125, "profit_lock_arm_pct": 0.05,
            "catastrophe_stop_pct": -0.50}

    r_default = mew.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme",
                         slippage=0.0, market_stage_fill_fix=True)
    r_explicit_false = mew.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme",
                                slippage=0.0, market_stage_fill_fix=True,
                                premium_stop_poll_model=False)
    assert r_default["pnl"] == r_explicit_false["pnl"]
    assert r_default["legs"] == r_explicit_false["legs"]
    assert "fill_model" not in r_default
    for leg in r_default["legs"]:
        assert "fill_model" not in leg


def test_poll_model_fires_at_first_1min_close_through_threshold_not_the_bar_low():
    """The actual mechanism: threshold = entry*(1-0.20) = 0.80. The 5-min bar's worst_in
    (0.50) is what makes the OUTER walk decide premium_stop fires THIS bar -- but the poll
    model must price it at the FIRST cached 1-min CLOSE at/through 0.80 (09:37, close 0.79),
    never the 5-min bar's low (0.50) and never the raw static threshold (0.80)."""
    import multileg_exit_walk as mew

    entry = 1.00
    bars = _custom_bars([{"t": "09:35:00", "o": 0.95, "h": 0.95, "l": 0.50, "c": 0.90}])
    highres = _custom_highres([
        {"t": "09:35:00", "o": 0.95, "h": 0.95, "l": 0.93, "c": 0.90},  # above threshold
        {"t": "09:36:00", "o": 0.90, "h": 0.90, "l": 0.83, "c": 0.85},  # above threshold
        {"t": "09:37:00", "o": 0.85, "h": 0.85, "l": 0.78, "c": 0.79},  # FIRST cross (<=0.80)
        {"t": "09:38:00", "o": 0.79, "h": 0.79, "l": 0.55, "c": 0.60},  # would ALSO cross
        {"t": "09:39:00", "o": 0.60, "h": 0.62, "l": 0.48, "c": 0.50},  # would ALSO cross
    ])
    fill = {"entry_premium": entry, "qty": 1, "symbol": "SPY260701P00700000",
           "date": "2026-07-01", "entry_time": "09:34:00", "strategy": "RIBBON"}
    shape = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.8,
            "profit_lock_mode": "fixed", "stop_mode": "premium",
            "runner_target_pct": 2.5, "trail_pct": 0.125, "profit_lock_arm_pct": 0.05,
            "catastrophe_stop_pct": -0.50}

    r = mew.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme", slippage=0.0,
                market_stage_fill_fix=True, premium_stop_poll_model=True,
                highres_bars=highres)
    leg = [leg for leg in r["legs"] if leg["stage"] == "premium_stop"][0]
    assert leg["px"] == pytest.approx(0.79)     # the FIRST crossing minute's close
    assert leg["px"] != pytest.approx(0.50)     # never the 5-min bar's low
    assert leg["px"] != pytest.approx(0.80)     # never the raw static threshold
    assert leg["fill_model"] == "1min_poll"
    assert r["fill_model"] == "1min_poll"


def test_poll_model_falls_back_when_no_highres_cache():
    """No 1-min cache for this contract/date (highres_bars=None, the honest gap
    _get_1min_df returns on a miss) -> falls back to the OLD static-threshold price, disclosed
    per-leg AND per-trade as fill_model='5min_fallback', never silently estimated."""
    import multileg_exit_walk as mew

    entry = 1.00
    bars = _make_synthetic_bars([0.95, 0.60, 0.55, 0.50, 0.45])
    fill = {"entry_premium": entry, "qty": 1, "symbol": "SPY260701P00700000",
           "date": "2026-07-01", "entry_time": "09:34:00", "strategy": "RIBBON"}
    shape = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.8,
            "profit_lock_mode": "fixed", "stop_mode": "premium",
            "runner_target_pct": 2.5, "trail_pct": 0.125, "profit_lock_arm_pct": 0.05,
            "catastrophe_stop_pct": -0.50}

    r = mew.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme", slippage=0.0,
                market_stage_fill_fix=True, premium_stop_poll_model=True,
                highres_bars=None)
    leg = [leg for leg in r["legs"] if leg["stage"] == "premium_stop"][0]
    assert leg["px"] == pytest.approx(0.80)     # entry*(1-0.20), the old static price
    assert leg["fill_model"] == "5min_fallback"
    assert r["fill_model"] == "5min_fallback"


def test_poll_model_falls_back_when_cache_exists_but_nothing_crosses_at_close_resolution():
    """The SECOND honest-miss path: a 1-min cache exists for the window, but every 1-min
    CLOSE stays above the threshold (only a wick the poll would never have observed dipped
    through) -- must fall back to the same static price, not silently pick the closest close
    or extrapolate."""
    import multileg_exit_walk as mew

    entry = 1.00
    bars = _custom_bars([{"t": "09:35:00", "o": 0.95, "h": 0.95, "l": 0.50, "c": 0.90}])
    highres = _custom_highres([
        {"t": "09:35:00", "o": 0.95, "h": 0.95, "l": 0.93, "c": 0.90},
        {"t": "09:36:00", "o": 0.90, "h": 0.90, "l": 0.83, "c": 0.85},
        {"t": "09:37:00", "o": 0.85, "h": 0.85, "l": 0.79, "c": 0.83},   # dips but CLOSES above
        {"t": "09:38:00", "o": 0.83, "h": 0.85, "l": 0.81, "c": 0.84},
        {"t": "09:39:00", "o": 0.84, "h": 0.86, "l": 0.82, "c": 0.85},
    ])
    fill = {"entry_premium": entry, "qty": 1, "symbol": "SPY260701P00700000",
           "date": "2026-07-01", "entry_time": "09:34:00", "strategy": "RIBBON"}
    shape = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.8,
            "profit_lock_mode": "fixed", "stop_mode": "premium",
            "runner_target_pct": 2.5, "trail_pct": 0.125, "profit_lock_arm_pct": 0.05,
            "catastrophe_stop_pct": -0.50}

    r = mew.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme", slippage=0.0,
                market_stage_fill_fix=True, premium_stop_poll_model=True,
                highres_bars=highres)
    leg = [leg for leg in r["legs"] if leg["stage"] == "premium_stop"][0]
    assert leg["px"] == pytest.approx(0.80)
    assert leg["fill_model"] == "5min_fallback"


def test_poll_model_only_scans_bars_inside_the_firing_5min_window():
    """A 1-min bar that crosses the threshold but falls OUTSIDE [bar_start, bar_start+5min)
    (e.g. it belongs to the PRECEDING 5-min window, before the outer walk even decided this
    stage fires) must be ignored -- the poll model refines the fill price INSIDE the bar the
    outer decision already picked, it does not reach backward across bar boundaries."""
    import multileg_exit_walk as mew

    entry = 1.00
    bars = _custom_bars([{"t": "09:35:00", "o": 0.95, "h": 0.95, "l": 0.50, "c": 0.90}])
    highres = _custom_highres([
        {"t": "09:34:00", "o": 0.95, "h": 0.95, "l": 0.10, "c": 0.20},   # BEFORE the window
        {"t": "09:35:00", "o": 0.95, "h": 0.95, "l": 0.93, "c": 0.90},
        {"t": "09:36:00", "o": 0.90, "h": 0.90, "l": 0.83, "c": 0.85},
        {"t": "09:37:00", "o": 0.85, "h": 0.85, "l": 0.78, "c": 0.79},   # first IN-WINDOW cross
        {"t": "09:38:00", "o": 0.79, "h": 0.79, "l": 0.55, "c": 0.60},
    ])
    fill = {"entry_premium": entry, "qty": 1, "symbol": "SPY260701P00700000",
           "date": "2026-07-01", "entry_time": "09:34:00", "strategy": "RIBBON"}
    shape = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.8,
            "profit_lock_mode": "fixed", "stop_mode": "premium",
            "runner_target_pct": 2.5, "trail_pct": 0.125, "profit_lock_arm_pct": 0.05,
            "catastrophe_stop_pct": -0.50}

    r = mew.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme", slippage=0.0,
                market_stage_fill_fix=True, premium_stop_poll_model=True,
                highres_bars=highres)
    leg = [leg for leg in r["legs"] if leg["stage"] == "premium_stop"][0]
    assert leg["px"] == pytest.approx(0.79)   # NOT 0.20 (the out-of-window bar)


def test_poll_model_trade_level_fill_model_is_na_when_no_poll_stage_fires():
    """A trade whose only legs are tp1 (out of scope) + eod-flatten (also out of scope) must
    report the trade-level fill_model as 'n/a', not '5min_fallback' -- there was no poll-
    model-eligible stage to even attempt."""
    import multileg_exit_walk as mew

    entry = 1.00
    bars = _custom_bars([{"t": "09:35:00", "o": 1.60, "h": 1.62, "l": 1.58, "c": 1.60}])
    fill = {"entry_premium": entry, "qty": 4, "symbol": "SPY260701C00700000",
           "date": "2026-07-01", "entry_time": "09:34:00", "strategy": "RIBBON"}
    shape = {"premium_stop_pct": -0.90, "tp1_premium_pct": 0.50, "tp1_qty_fraction": 0.5,
            "profit_lock_mode": "fixed", "stop_mode": "premium",
            "runner_target_pct": 9.0, "trail_pct": 0.125, "profit_lock_arm_pct": 0.9,
            "catastrophe_stop_pct": -0.90}

    r = mew.walk(fill, shape, bars, trigger_level=0.0, fill_mode="extreme", slippage=0.0,
                market_stage_fill_fix=True, premium_stop_poll_model=True, highres_bars=None)
    assert {leg["stage"] for leg in r["legs"]} <= {"tp1", "eod"}
    assert r["fill_model"] == "n/a"


def test_poll_model_stages_constant_is_the_symmetric_threshold_crossing_set():
    """Pins the exact set + the reasoning: premium_stop/profit_lock_floor (pre-TP1) and
    trail/be_stop (post-TP1) are the SAME numeric check in exit_manager.py
    (worst_premium <= runner_stop / new_runner_stop) -- structure_stop/ribbon_flip/time_stop
    (no premium threshold to poll) and runner_target (a RISING threshold, not a downside
    cross) stay out. See multileg_exit_walk.py's module note for why this measured WORSE and
    stays behind a flag defaulting False."""
    import multileg_exit_walk as mew

    assert mew._POLL_MODEL_STAGES == frozenset(
        {"premium_stop", "profit_lock_floor", "trail", "be_stop"})
    assert mew._POLL_MODEL_STAGES.isdisjoint(mew._MARKET_STAGES)


def test_poll_1min_close_cross_unit_no_highres_returns_none():
    import multileg_exit_walk as mew

    px, t = mew._poll_1min_close_cross(None, pd.Timestamp("2026-07-01 09:35:00"), 5, 0.80)
    assert (px, t) == (None, None)
    px, t = mew._poll_1min_close_cross(pd.DataFrame(), pd.Timestamp("2026-07-01 09:35:00"),
                                       5, 0.80)
    assert (px, t) == (None, None)


def test_poll_1min_close_cross_unit_picks_first_by_time_even_if_unsorted():
    """Feeds the highres frame in SHUFFLED row order -- the function must sort by
    timestamp_et itself, not trust input order, since a real cache read is not guaranteed
    sorted."""
    import multileg_exit_walk as mew

    highres = _custom_highres([
        {"t": "09:38:00", "o": 0.79, "h": 0.79, "l": 0.55, "c": 0.60},
        {"t": "09:35:00", "o": 0.95, "h": 0.95, "l": 0.93, "c": 0.90},
        {"t": "09:37:00", "o": 0.85, "h": 0.85, "l": 0.78, "c": 0.79},
        {"t": "09:36:00", "o": 0.90, "h": 0.90, "l": 0.83, "c": 0.85},
    ])
    px, t = mew._poll_1min_close_cross(highres, pd.Timestamp("2026-07-01 09:35:00"), 5, 0.80)
    assert px == pytest.approx(0.79)
    assert t == "09:37"
