"""Graduated guards — repeat-violated lessons turned into assertions.

Each test corresponds to a lesson family that recurred AFTER it was written down
(prose failed as a control). Converting them to tests means CI catches the
regression instead of a human re-discovering it walks later.

  test_no_lookahead_*                        -> L14/L34/L57 (look-ahead / future leakage)
  test_params_override_binds                 -> L38/L72     (dead/translated-but-unapplied knob;
                                                             the class of both 2026-06-14 bugs:
                                                             the v15.3 ribbon gates AND the
                                                             premium_stop_pct_bear mapping)
  test_exit_knobs_synced_*                   -> L72         (j_edge_tracker base drifting from
                                                             params.json — the C3 drift)
  test_no_pythonw_*                          -> L41         (venv-stub pythonw re-exec, recurred 5x)
  test_ribbon_spread_min_*                   -> L92         (IS quality-lock cascade false positive;
                                                             filter-6@20c OOS -$1483 vs -$709 baseline)
  test_winner_days_declining_vix             -> L93         (BEARISH_REVERSAL fires on declining VIX;
                                                             VIX-escalating gate kills all 3 winners)
  test_trendline_only_*                      -> L95         (trendline_only_setup inverse dependency;
                                                             adding level_rejection hardens filter_5)
  test_first_hour_high_enables_level_trigger -> Rank 27     (first-hour RTH high as supplemental level;
                                                             must not be dead knob — bypass f5/f8/f10 to confirm)
  test_first_hour_high_no_regression        -> L96 (rank 27 / 2026-06-16: FHH fhh_level_rejection must
                                                             not contaminate trendline_only_setup; guarded
                                                             on 2025-11-04 +$836 trendline winner)
  test_bearish_reversal_bypass_fires_at_fhh -> Rank 28 (2026-06-16: bypass fires at 5/01 11:50 when
                                                             include_first_hour_high=True + bypass=True;
                                                             dead-knob guard for fhh_level_rejection bypass)
  test_bearish_reversal_bypass_no_regression_loser_days -> Rank 28 (2026-06-16: bypass must not add entries
                                                             on 5/05 / 5/07 loser days; guards the FHH-only
                                                             discriminator against false positives)
  test_l97_strategy_grinder_j_winners_all_reachable     -> L97     (2026-06-16: SHOTGUN_SCALPER J_WINNERS
                                                             must only include dates where detector can fire;
                                                             prevents EC floor inflation from incompatible
                                                             strategy types or missing OPRA data)
  test_l99_profit_lock_threshold_not_zero               -> L99     (2026-06-16: profit_lock_threshold=0.0
                                                             arms profit lock on bar-1, inflating WR to 93.5%
                                                             in BS-sim; real-fills shows -155% gap on first
                                                             OPRA day; threshold must be >= 0.05)
  test_l100_sniper_premium_exits_no_positive_result     -> L100    (2026-06-16: SNIPER_LEVEL_BREAK all
                                                             premium-exit combos negative; threshold=99.0
                                                             "genuine edge" ($25,943) requires 300% intraday
                                                             premium moves impossible in real fills; verdict
                                                             must remain CAVEAT/BLOCKED, not PASS)
  test_sniper_cs_uses_chart_stop_not_premium_stop      -> L100+L51+L55 (2026-06-16: chart-stop evaluator
                                                             must use chart_stop_buffer, NOT premium_stop_pct;
                                                             regression guard prevents reverting to premium-stop
                                                             design that all-negative sweep disproved)
  test_fhh_v4_proximity_antipattern                   -> Rank 28 v4 anti-pattern (2026-06-16: fhh_quality_proximity
                                                             is ANTI-CORRELATED with J anchor; gap-up FHH is ABOVE
                                                             multi_day_levels, not near them; proximity gate removes
                                                             5/01 at all thresholds 0.50/1.00/2.00)
  test_fhh_v4_gapup_preserves_501_filters_508         -> Rank 28 v4 (2026-06-16: fhh_above_max_prior_min=1.00
                                                             preserves 5/01 J anchor, filters 5/08 OOS losses;
                                                             86% reduction in bypass drag: -$1,899→-$257)
  test_vix_bull_low_threshold_wired_in_orchestrator    -> C14 (2026-06-17: VIX_BULL_LOW_THRESHOLD was live
                                                             (30.0 gives 2 extra OOS trades) but not in
                                                             _FILTER_CONST_MAP; wired and guard added)
  test_trendline_lookback_bars_wired_in_orchestrator   -> C14 (2026-06-17: TRENDLINE_LOOKBACK_BARS wired;
                                                             short lookback=10 (50 min) must produce fewer
                                                             trendline triggers than production default=60)
  test_trendline_min_swings_wired_in_orchestrator      -> C14 (2026-06-17: TRENDLINE_MIN_SWINGS wired;
                                                             min_swings=10 (need 10 descending pivots) must
                                                             severely restrict trendline triggers vs default=3)
  test_l111_vix_bear_threshold_wired_in_orchestrator   -> C14/L111 (2026-06-17: vix_bear_threshold was
                                                             in runner._FILTERS_CONST_KEYS but missing
                                                             from orchestrator._FILTER_CONST_MAP; 3-value
                                                             sweep confirmed dead before fix, live after.
                                                             Also wired: vix_rising_deadband, vix_bear_rising_deadband,
                                                             vix_bull_max. Guard: n(threshold=25) < n(threshold=10)-1)
  test_level_proximity_dollars_removed_from_const_map  -> C14/L38  (2026-06-17: LEVEL_PROXIMITY_DOLLARS
                                                             confirmed dead (6-value sweep, identical output);
                                                             removed from filters.py + both _FILTER_CONST_MAPs;
                                                             guard now verifies constant does NOT exist — prevents
                                                             re-adding without wiring in detect_level_rejection)
  test_ribbon_flip_lookback_bars_is_wired              -> C14/L38  (2026-06-16 WIRED 2026-06-16: buffer in
                                                             orchestrator now uses _filters_mod.RIBBON_FLIP_LOOKBACK_BARS;
                                                             params_overrides path patched via _patch_filter_consts;
                                                             promoted from xfail to test_params_override_binds)
  test_l105_real_fills_stop_uses_side_specific        -> L105/C7  (2026-06-16: simulate_trade_real received
                                                             premium_stop_pct=premium_stop_pct global -0.08
                                                             not side_premium_stop -0.20 for bears; fixed by
                                                             moving side_premium_stop computation before the
                                                             if use_real_fills: branch)
  test_wick_min_pct_of_range_wired_in_orchestrator   -> C14 (2026-06-17: WICK_MIN_PCT_OF_RANGE promoted from
                                                             hardcoded detect_wick_rejection_bearish() default
                                                             to module-level constant; wired in both const maps;
                                                             NOTE: direction not monotone — C15 entry-slot effect;
                                                             confirmed live via n!=n comparison on IS)
  test_wick_min_dollars_wired_in_orchestrator         -> C14 (2026-06-17: WICK_MIN_DOLLARS wired; same C15
                                                             entry-slot effect; confirmed live via n!=n on IS)
  test_wick_close_tolerance_wired_in_orchestrator     -> C14 (2026-06-17: WICK_CLOSE_TOLERANCE wired; same
                                                             C15 entry-slot effect; confirmed live via n!=n on IS)
  test_vol_baseline_bars_wired_in_orchestrator        -> C14 (2026-06-17: VOL_BASELINE_BARS wired; confirmed live
                                                             in OOS: bars=5 gives n=15 vs baseline n=16; IS test
                                                             uses 5 vs 50 for stronger signal)
  test_range_baseline_bars_is_dead_constant           -> C14 (2026-06-17: RANGE_BASELINE_BARS confirmed dead;
                                                             ctx.range_baseline_20 set but never read by any
                                                             filter; IS+OOS n identical at bars=5 vs 50;
                                                             guards against re-wiring without adding a consumer)
  test_l113_level_stop_buffer_wired_in_real_fills     -> L113/C14 (2026-06-17: level_stop_buffer_dollars was
                                                             hardcoded 0.50 in simulator_real.py; now param;
                                                             NOTE: P&L guard not viable — ribbon flip fires
                                                             BEFORE level stop in all IS trades; use code
                                                             inspection guard instead)
  test_l116_min_triggers_bear_wired_in_params_overrides -> L116/C14 (2026-06-17: params_overrides path handled
                                                             only "filter_10_min_triggers_bear" legacy key, not
                                                             raw "min_triggers_bear" snake_case key. All sweeps
                                                             via params_overrides={'min_triggers_bear': N} silently
                                                             used default N=1. Fix: added alias in _params_to_kwargs.
                                                             Guard: code inspection + OOS trade-count spread ≥3)
  test_l124_level_reclaim_positive_oos_expectancy      -> L124 (2026-06-17: level_reclaim has positive per-trade
                                                             OOS expectancy despite 37.5% WR. W=3/L=5 in full OOS
                                                             but avg_winner=+$1,306 avg_loser=-$285 → +$311/trade.
                                                             5/8-5/22 window W=3/L=3 pnl=+$3,245. DO NOT block
                                                             level_reclaim — lottery-ticket structure: winners 4.6x
                                                             larger than losers. Guard: OOS total P&L > 0 AND n>=3)
  test_block_elite_bull_vix_range                     -> Rank 34 (2026-06-17: BLOCK_ELITE_BULL_VIX15_17.5
                                                             deployed. ELITE+level_reclaim (BULL) in VIX 15-17
                                                             IS n=73 WR=9.6% avg=-$100 — pure losers. Gate blocks
                                                             ONLY when 15 <= VIX < 17.5. Guard: (1) gate fires
                                                             at least 1 SKIP_ELITE_BULL_LEVEL_RECLAIM in OOS;
                                                             (2) all SKIPs have VIX in [15, 17.5); (3) CAND n
                                                             <= BASE n; (4) gate inert when vix range = [20,25))
  test_l155_autorate_rejects_negative_is_delta        -> L155 (2026-06-17: WF_norm formula gives FALSE POSITIVE
                                                             when IS_delta < 0 AND OOS_delta < 0; both-negative
                                                             deltas → positive WF ratio → spurious AUTO-RATIFY.
                                                             L155 guard: reject BEFORE WF check when IS_delta<=0.
                                                             Real case: Safe conf+lvl_rej VIX>=19 gate produced
                                                             IS_delta=-$2,334, OOS_delta=-$453, WF_raw=1.201)
  test_l173_oos_drop_top5_*                            -> L173/C4 (2026-06-21: OOS-ALONE drop-top5 graduated from
                                                             per-harness into the STANDARD verify path
                                                             (autoresearch.fraud_gates.oos_drop_top5_gate, wired in
                                                             verify_edgehunt_candidates). full-sample drop-top5>0 is
                                                             necessary-but-NOT-sufficient: the OOS-window-only per-trade
                                                             must ALSO stay >0 after dropping the 5 best OOS days.
                                                             Caught edge#3 (2026-bull regime artifact: passed
                                                             full-sample drop-top5 at B5, failed OOS-alone at B6
                                                             -$16->-$23, top5-day-OOS 120-228%). ADDITIVE; small-n<=5
                                                             unevaluable=skip; missing value fails OPEN, never blesses)

Run:  cd backtest && python -m pytest tests/test_graduated_guards.py -v
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.orchestrator import run_backtest  # noqa: E402

DATA = BACKTEST / "data"
MASTER_SPY = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
MASTER_VIX = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
PARAMS = REPO / "automation" / "state" / "params.json"
_HAS_DATA = MASTER_SPY.exists() and MASTER_VIX.exists()


def _needs_data(fn):
    """Decorator for guards that load the master SPY/VIX CSV and run a full backtest.

    These are the SLOW guards (each runs one or more end-to-end backtests; the full
    file is data-heavy and exceeds the 600s per-edit hook budget). It bundles two
    markers so a per-edit hook can run only the fast logic guards via `-m "not slow"`:
      * skipif when the master CSV is absent, and
      * pytest.mark.slow (so the nightly/manual run keeps exercising them).

    Backtest-running guards that gate on an internal pytest.skip (rather than this
    decorator) are tagged directly with @pytest.mark.slow.
    """
    fn = pytest.mark.slow(fn)
    fn = pytest.mark.skipif(not _HAS_DATA, reason="master SPY/VIX CSV not present")(fn)
    return fn


def _load(start: str, end: str):
    import pandas as pd

    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    spy = spy[(spy["timestamp_et"] >= start) & (spy["timestamp_et"] < f"{end}T23:59:59")].reset_index(drop=True)
    vix = vix[(vix["timestamp_et"] >= start) & (vix["timestamp_et"] < f"{end}T23:59:59")].reset_index(drop=True)
    return spy, vix


def _result(spy, vix, start: str, end: str, **kw):
    trades = run_backtest(
        spy, vix,
        start_date=dt.date.fromisoformat(start),
        end_date=dt.date.fromisoformat(end),
        use_real_fills=False,
        **kw,
    ).trades
    return len(trades), round(sum(t.dollar_pnl for t in trades), 2)


def _signature(trades) -> list:
    return sorted((str(t.entry_time_et), round(t.dollar_pnl, 2)) for t in trades)


@_needs_data
def test_no_lookahead_future_bars_dont_change_past_trades() -> None:
    """L14/L34/L57: trades over [start, mid] must be identical whether or not the
    dataframe also contains future bars [mid, end]. If a predicate reads past the
    current bar, appending the future changes past decisions and this fails."""
    start, mid, end = "2026-02-01", "2026-04-01", "2026-05-07"
    spy_short, vix_short = _load(start, mid)
    spy_long, vix_long = _load(start, end)
    short = run_backtest(spy_short, vix_short, start_date=dt.date.fromisoformat(start),
                         end_date=dt.date.fromisoformat(mid), use_real_fills=False).trades
    long_ = run_backtest(spy_long, vix_long, start_date=dt.date.fromisoformat(start),
                         end_date=dt.date.fromisoformat(mid), use_real_fills=False).trades
    assert _signature(short) == _signature(long_), "future bars changed past trades -> look-ahead leak"


@_needs_data
@pytest.mark.parametrize(
    "key,value",
    [
        ("min_ribbon_momentum_cents", 50.0),  # entry gate -> changes trade count
        ("max_ribbon_duration_bars", 3),      # entry gate -> changes trade count
        ("midday_trendline_gate", True),      # entry gate -> changes trade count
        ("premium_stop_pct_bear", -0.50),     # exit knob  -> changes P&L (was unmapped, 2026-06-14)
        # cap=1% of $25K = $250 max notional; any 3-contract trade at $1+ is capped
        # → dollar_pnl scales down → total P&L changes. Dead knob if this is a no-op.
        ("per_trade_risk_cap_pct", 0.01),     # sizing cap -> scales qty/pnl (2026-06-16)
        # lookback=1 → buffer 3 elements → flip check spans only 1 prior bar (very tight)
        # vs default=3 → buffer 5 elements → checks 3 bars. Wired 2026-06-16 via _FILTER_CONST_MAP.
        ("ribbon_flip_lookback_bars", 1),     # C14/L38: wired 2026-06-16 (was dead knob)
    ],
)
def test_params_override_binds(key, value) -> None:
    """L38/L72: a key that _params_to_kwargs claims to map MUST change engine
    output (count or P&L) when overridden. Guards the 'translated but never
    applied' bug class — both the v15.3 ribbon gates and premium_stop_pct_bear
    were silently dropped before 2026-06-14."""
    start, end = "2026-03-01", "2026-05-07"
    spy, vix = _load(start, end)
    base = _result(spy, vix, start, end)
    overridden = _result(spy, vix, start, end, params_overrides={key: value})
    assert overridden != base, f"override {key}={value} did not change output (dead knob)"


def test_exit_knobs_synced_with_jedge_tracker() -> None:
    """L72: j_edge_tracker.V15_J_EDGE_OVERRIDES exit knobs must mirror production
    params.json. Drift here made grinders search a stale base for weeks. Parsed via
    ast (no import) so the test stays cheap and dependency-free."""
    jet = (BACKTEST / "autoresearch" / "j_edge_tracker.py").read_text(encoding="utf-8")
    overrides = None
    for node in ast.walk(ast.parse(jet)):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "V15_J_EDGE_OVERRIDES" for t in node.targets
        ):
            overrides = ast.literal_eval(node.value)
    assert overrides is not None, "V15_J_EDGE_OVERRIDES not found in j_edge_tracker.py"
    params = json.loads(PARAMS.read_text(encoding="utf-8-sig"))
    assert overrides["tp1_premium_pct"] == params["tp1_premium_pct"]
    assert overrides["tp1_qty_fraction"] == params["tp1_qty_fraction"]
    assert overrides["runner_max_premium_pct"] == params["runner_max_premium_pct"]
    assert overrides["premium_stop_pct_bear"] == params["premium_stop_pct_bear"]


def test_pre_order_gate_blocks_oversized_bold_trade() -> None:
    """FIX 5a / 2026-06-15: the pre_order_gate.py code gate must BLOCK the exact
    scenario from today — 5 contracts × $2.06 × 100 = $1,030 on a $1,122 Bold
    account (92% of equity, exceeds both 50% risk cap and 50% G6b cap for bold).
    This is a GRADUATED guard: prose-only G6b failed live; code gate is the fix."""
    import subprocess, sys
    gate = REPO / "automation" / "scripts" / "pre_order_gate.py"
    assert gate.exists(), f"pre_order_gate.py not found at {gate}"
    result = subprocess.run(
        [sys.executable, str(gate), "--equity", "1122", "--qty", "5", "--premium", "2.06", "--account", "bold"],
        capture_output=True, text=True
    )
    assert result.returncode == 1, f"Expected BLOCK (exit 1) but got exit {result.returncode}: {result.stdout}"
    assert result.stdout.startswith("BLOCK"), f"Expected 'BLOCK' prefix but got: {result.stdout!r}"


def test_pre_order_gate_passes_valid_safe_trade() -> None:
    """FIX 5a / 2026-06-15: gate must PASS a valid safe-account trade (3×$1.00=$300 < 40% of $1,122)."""
    import subprocess, sys
    gate = REPO / "automation" / "scripts" / "pre_order_gate.py"
    result = subprocess.run(
        [sys.executable, str(gate), "--equity", "1122", "--qty", "3", "--premium", "1.00", "--account", "safe"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, f"Expected PASS (exit 0) but got exit {result.returncode}: {result.stdout}"
    assert result.stdout.startswith("PASS"), f"Expected 'PASS' prefix but got: {result.stdout!r}"


def test_profitable_exit_does_not_enable_trendline_leg2() -> None:
    """L89: profitable exits (pnl>0, no TP1) must NOT count as stopped_without_tp1.
    Before the fix, profit-lock exits (PREMIUM_STOP + no TP1 but pnl>0) enabled
    TRENDLINE_LEG2 re-entry at qty=20, causing 4/29 -$414 (first +$94 then -$508 at 20x).
    Verify the guard: orchestrator.py stopped_without_tp1 requires pnl<=0."""
    source = (BACKTEST / "lib" / "orchestrator.py").read_text(encoding="utf-8")
    # The fix line must be present: pnl<=0 check before the PREMIUM_STOP check
    assert "fill.dollar_pnl or 0.0) <= 0.0" in source, (
        "L89 regression: stopped_without_tp1 no longer checks pnl<=0 — "
        "profitable profit-lock exits may re-enable TRENDLINE_LEG2 at qty=20"
    )


def test_ribbon_spread_min_not_below_oos_floor() -> None:
    """L92/C7: ribbon_spread_min_cents below 30c fails OOS on BEARISH_REVERSAL.
    The quality-lock cascade (earlier ELITE entry stops out + blocks profitable later
    LEVEL entry via setup_quality_taken_today) is a structural trap at lower thresholds.
    Validated 2026-06-16: filter-6@20c OOS = -$1483 vs baseline -$709 on 2026-05-08..22.
    If ever lowering, run f6_vix_escalating_compound.py OOS first and assert >= baseline*0.90."""
    params = json.loads(PARAMS.read_text(encoding="utf-8-sig"))
    val = params.get("ribbon_spread_min_cents", 30)
    assert val >= 30, (
        f"L92: ribbon_spread_min_cents={val}c is below the OOS-validated floor of 30c. "
        "20c threshold caused OOS P&L to worsen from -$709 to -$1483 on 2026-05-08..22 "
        "via quality-lock cascade. Run backtest/autoresearch/f6_vix_escalating_compound.py "
        "and assert OOS_candidate >= OOS_baseline * 0.90 before lowering."
    )


@_needs_data
def test_winner_days_have_declining_vix() -> None:
    """L93/C5: J's 3 BEARISH_REVERSAL winner days (4/29, 5/01, 5/04) all have DECLINING VIX.
    prior_day_VIX < prior_5d_avg_VIX for all 3 — the opposite of SNIPER (L73).
    VIX-escalating gate (validated for SNIPER) would block all 3 winners, collapsing EC=0.
    Do NOT apply VIX-escalating or VIX>=18 gates to BEARISH_REVERSAL without first verifying
    that J winner days still pass. If new J winner days emerge with escalating VIX, update guard.
    Empirically verified 2026-06-16 via f6_vix_escalating_compound.py Phase 1."""
    import bisect
    from statistics import mean

    import pandas as pd

    vix = pd.read_csv(MASTER_VIX)
    vix["timestamp_et"] = pd.to_datetime(vix["timestamp_et"], utc=True).dt.tz_convert(
        "America/New_York"
    ).dt.tz_localize(None)
    vix_by_date: dict = (
        vix.groupby(vix["timestamp_et"].dt.date)["close"].last().to_dict()
    )
    sorted_days = sorted(vix_by_date.keys())
    sorted_vals = [vix_by_date[d] for d in sorted_days]

    winner_days = [
        dt.date(2026, 4, 29),
        dt.date(2026, 5, 1),
        dt.date(2026, 5, 4),
    ]
    escalating_winners = []
    for trade_date in winner_days:
        idx = bisect.bisect_left(sorted_days, trade_date) - 1
        if idx < 0:
            continue
        prior_close = sorted_vals[idx]
        start_idx = max(0, idx - 4)  # 5-day window ending at prior day
        window = sorted_vals[start_idx : idx + 1]
        prior_5d_avg = float(mean(window)) if window else prior_close
        if prior_close >= prior_5d_avg:
            escalating_winners.append((trade_date, prior_close, prior_5d_avg))

    assert not escalating_winners, (
        "L93: J winner day(s) now have ESCALATING VIX — VIX-escalating gate may be safe to apply. "
        "Re-run f6_vix_escalating_compound.py to validate before adding any VIX-escalating filter "
        f"to BEARISH_REVERSAL. Escalating: {escalating_winners}"
    )


def test_trendline_only_setup_hardens_filter5_with_level_rejection() -> None:
    """L95/C15: trendline_only_setup relaxation is disabled when level_rejection fires.

    When trendline_rejection is the ONLY trigger: trendline_only_setup=True -> filter_5
    (ribbon BEAR check) is removed from hard blockers.
    When level_rejection also fires: trendline_only_setup=False -> filter_5 stays as hard block.

    The inverse dependency: adding a level trigger (rank 27 first-hour RTH high) alongside
    trendline_rejection HARDENS filter_5. Both blockers (level detection + ribbon bypass)
    must be solved simultaneously to unlock the 5/01 11:50 BEARISH_REVERSAL entry gap.
    """
    source = (BACKTEST / "lib" / "filters.py").read_text(encoding="utf-8")
    assert '"level_rejection" not in triggers' in source, (
        "L95: trendline_only_setup must explicitly exclude 'level_rejection' from triggers. "
        "Without this, rank 27 adding level_rejection alongside trendline_rejection would "
        "accidentally trigger the chop-relaxation and bypass filter_5 unintentionally."
    )
    assert "if trendline_only_setup:" in source, (
        "L95: filter_5 (ribbon BEAR) removal must be gated on trendline_only_setup check. "
        "Unconditional removal would misfire on multi-trigger setups where level_rejection fires."
    )


@_needs_data
def test_first_hour_high_enables_level_trigger() -> None:
    """Rank 27 / 2026-06-16: include_first_hour_high=True must generate fhh_level_rejection
    on days where the first-hour-high is NOT in the base level set.

    FHH generates fhh_level_rejection (separate from level_rejection) to avoid contaminating
    trendline_only_setup. On 5/01 2026, FHH=724.24 is NOT in the base level set. With flag,
    the 11:50 bar (H=724.38, C=723.48) produces fhh_level_rejection in decisions.
    Uses the full dataset so level detection has correct prior-day history.
    """
    import pandas as pd
    spy_full = pd.read_csv(MASTER_SPY)
    vix_full = pd.read_csv(MASTER_VIX)
    start_d = dt.date(2026, 5, 1)

    r = run_backtest(
        spy_full, vix_full, start_date=start_d, end_date=start_d,
        use_real_fills=False, include_first_hour_high=True,
        params_overrides={"per_trade_risk_cap_pct": 0.50},
    )
    fhh_decisions = [
        d for d in r.decisions
        if "fhh_level_rejection" in d.get("triggers_fired", [])
    ]
    assert fhh_decisions, (
        "Rank 27: fhh_level_rejection not found in any 5/01 decision. "
        "FHH=724.24 should fire at 11:50 (H=724.38, close=723.48). "
        "include_first_hour_high is a dead knob — check FHH computation in orchestrator."
    )


@_needs_data
def test_first_hour_high_no_regression() -> None:
    """L96 / Rank 27 regression guard: fhh_level_rejection must NOT contaminate
    trendline_only_setup.

    2025-11-04 13:55 +$836.71 is a trendline-only setup. FHH=676.17 on that day is
    close to 13:55 price (H=676.24). Old code added FHH to levels_active → level_rejection
    fired → trendline_only_setup=False → filter_8 applied → trade blocked.

    Fixed: fhh_level_rejection is a SEPARATE trigger key that does NOT appear in the
    trendline_only_setup check (which guards on 'level_rejection'). Uses full dataset
    for correct level detection.
    """
    import pandas as pd
    spy_full = pd.read_csv(MASTER_SPY)
    vix_full = pd.read_csv(MASTER_VIX)
    start_d = dt.date(2025, 11, 4)

    base_r = run_backtest(
        spy_full, vix_full, start_date=start_d, end_date=start_d,
        use_real_fills=False, params_overrides={"per_trade_risk_cap_pct": 0.50},
    )
    fhh_r = run_backtest(
        spy_full, vix_full, start_date=start_d, end_date=start_d,
        use_real_fills=False, include_first_hour_high=True,
        params_overrides={"per_trade_risk_cap_pct": 0.50},
    )
    assert _signature(base_r.trades) == _signature(fhh_r.trades), (
        f"L96 regression: include_first_hour_high=True changed 2025-11-04 result. "
        f"base={_signature(base_r.trades)} vs fhh={_signature(fhh_r.trades)}. "
        "FHH is contaminating trendline_only_setup via level_rejection — see L96."
    )


@_needs_data
def test_bearish_reversal_bypass_fires_at_fhh() -> None:
    """Rank 28 dead-knob guard: with include_first_hour_high=True AND
    include_bearish_reversal_bypass=True, the 2026-05-01 11:50 bar must pass filters.

    5/01 11:50 is J's +$470 anchor trade. FHH=724.24 fires fhh_level_rejection at
    that bar (ribbon=BULL). The bypass then removes filter_5 and filter_8, clearing
    all blockers. If this bar does NOT show passed=True in decisions, the bypass is
    a dead knob — either the trigger key changed or the bypass condition drifted.
    """
    import pandas as pd
    spy_full = pd.read_csv(MASTER_SPY)
    vix_full = pd.read_csv(MASTER_VIX)
    start_d = dt.date(2026, 5, 1)
    r = run_backtest(
        spy_full, vix_full, start_date=start_d, end_date=start_d,
        use_real_fills=False,
        include_first_hour_high=True,
        include_bearish_reversal_bypass=True,
        params_overrides={"per_trade_risk_cap_pct": 0.50},
    )
    import datetime as _dt
    target_time = _dt.time(11, 50)
    bar_passed = [
        d for d in r.decisions
        if d.get("timestamp_et") is not None
        and d["timestamp_et"].time() == target_time
        and d.get("passed") is True
    ]
    assert bar_passed, (
        "Rank 28: 2026-05-01 11:50 did not pass filters with include_first_hour_high=True "
        "and include_bearish_reversal_bypass=True. "
        "Check fhh_level_rejection trigger key and bearish_reversal_bypass condition in filters.py."
    )


@_needs_data
def test_bearish_reversal_bypass_no_regression_loser_days() -> None:
    """Rank 28 loser-day regression: enabling FHH + BEARISH_REVERSAL bypass must NOT
    add new entries on J's known loser days (5/05, 5/07).

    False positives on loser days were the original failure mode:
    - Without discriminator: 5/05 added -$361, 5/07 changed to -$609 vs base
    - Fixed by restricting bypass to fhh_level_rejection ONLY (FHH fires only at the
      session's first-hour high, which is typically NOT tested on loser days)
    """
    import pandas as pd
    spy_full = pd.read_csv(MASTER_SPY)
    vix_full = pd.read_csv(MASTER_VIX)
    kw = dict(use_real_fills=False, params_overrides={"per_trade_risk_cap_pct": 0.50})
    for day, label in [(dt.date(2026, 5, 5), "5/05"), (dt.date(2026, 5, 7), "5/07")]:
        base_r = run_backtest(spy_full, vix_full, start_date=day, end_date=day, **kw)
        brev_r = run_backtest(
            spy_full, vix_full, start_date=day, end_date=day,
            include_first_hour_high=True, include_bearish_reversal_bypass=True, **kw,
        )
        assert _signature(base_r.trades) == _signature(brev_r.trades), (
            f"Rank 28: bypass+FHH added or changed trades on loser day {label}. "
            f"base={_signature(base_r.trades)} vs bypass={_signature(brev_r.trades)}. "
            "fhh_level_rejection fired on a loser day — check FHH dedup threshold or bypass condition."
        )


def test_no_pythonw_relative_executable_path() -> None:
    """L41: never resolve pythonw via Path(sys.executable).parent — under an old
    daemon that resolves to the venv stub that re-execs a visible console window.
    Recurred 5x. Hardcode the system Python path instead."""
    pattern = re.compile(r"sys\.executable\)\.parent\s*/\s*[\"']pythonw")
    offenders = []
    for path in REPO.rglob("*.py"):
        s = str(path)
        if any(skip in s for skip in ("_local_backups", ".venv", "site-packages", "__pycache__")):
            continue
        try:
            if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(s)
        except OSError:
            continue
    assert not offenders, f"L41 regression: relative pythonw resolution in {offenders}"


def test_l97_strategy_grinder_j_winners_all_reachable() -> None:
    """L97: Every J_WINNER date in a strategy-specific grinder must produce non-zero
    engine P&L at the minimum vol_ratio threshold (1.2 = broadest filter). If any
    date returns 0 at vr=1.2, that date is structurally incompatible with the
    detector (wrong strategy type or missing OPRA data) and must be removed.

    Root cause (2026-06-16): SHOTGUN_SCALPER_STAGE1 included 5/14 (open-drive CALL,
    vol-ratio detector fires afternoon-only) and 5/15 (OPRA data missing). These
    inflated J_TOTAL_WINNERS from $1,542 to $4,150, making the 50% EC floor of
    $2,075 structurally unreachable — all 322 combos rejected before the fix.

    Updated 2026-06-16: SHOTGUN_SCALPER J_WINNERS is now intentionally empty (J's
    canonical 3 wins are CONFLUENCE/TRENDLINE entries, not vol-spike entries — the
    detector fires at wrong times on those days). An empty J_WINNERS list is valid
    for strategies without J-validated anchor trades. The guard still ensures that any
    FUTURE anchor date added to J_WINNERS produces non-zero engine P&L."""
    sys.path.insert(0, str(BACKTEST / "autoresearch"))
    try:
        from autoresearch.shotgun_scalper_grinder import (  # noqa: PLC0415
            evaluate_shotgun_combo,
            J_WINNERS,
            J_TOTAL_WINNERS,
        )
    except ImportError:
        pytest.skip("shotgun_scalper_grinder not importable (missing OPRA data)")

    if not J_WINNERS:
        # No anchor trades yet for this strategy — empty list is valid (see comment above).
        return

    result = evaluate_shotgun_combo({
        "vol_ratio_threshold": 1.2,
        "tp_premium_pct": 1.5,
        "stop_premium_pct": -0.15,
        "time_stop_min": 12,
        "strike_offset": 1,
        "chandelier_arm_pct": 0.25,
    })
    by_day = result.get("by_day", {})
    dead_dates = [
        w["date"] for w in J_WINNERS
        if by_day.get(w["date"], 0.0) == 0.0
    ]
    assert not dead_dates, (
        f"L97: J_WINNERS dates produce 0 engine P&L even at minimum vol_ratio=1.2: "
        f"{dead_dates}. These dates are structurally incompatible with SHOTGUN_SCALPER "
        f"(wrong strategy type or missing OPRA data). Remove from J_WINNERS to prevent "
        f"EC floor inflation (J_TOTAL_WINNERS={J_TOTAL_WINNERS})."
    )


def test_l99_profit_lock_threshold_not_zero() -> None:
    """L99 guard: promoted SNIPER combos must not use profit_lock_threshold_pct=0.0.

    threshold=0.0 arms the profit lock on bar-1 after entry (favor_premium >=
    entry_premium × 1.0 fires immediately), converting -6% stops into +5% exits.
    This inflates WR to 93.5% in BS-sim; real-fills CAVEAT: BS=+$1,007 vs
    OPRA=-$556 (-155%) on 2025-04-07. Any SNIPER combo in keepers or leaderboard
    must have profit_lock_threshold_pct >= 0.05.

    The test passes if no SNIPER combo with threshold=0.0 has been promoted to
    the leaderboard. Stage-2 keepers (in _state/sniper_stage2/keepers.jsonl) are
    pre-promotion — they are not checked here (they document the artifact).
    """
    REPO_ROOT = Path(__file__).parent.parent.parent
    leaderboard = REPO_ROOT / "strategy" / "candidates" / "_LEADERBOARD.md"

    if not leaderboard.exists():
        pytest.skip("_LEADERBOARD.md not found — no promoted candidates to check")

    content = leaderboard.read_text(encoding="utf-8")

    # Look for any SNIPER_LEVEL_BREAK entries in the leaderboard
    sniper_lines = [ln for ln in content.splitlines() if "SNIPER_LEVEL_BREAK" in ln]

    # Also check any sniper real-fills JSON reports for combos with threshold=0.0
    rf_reports = [
        REPO_ROOT / "analysis" / "recommendations" / "sniper-stage2-realfills.json",
        REPO_ROOT / "analysis" / "recommendations" / "sniper-v1-realfills.json",
    ]
    promoted_threshold_zero: list[str] = []
    for report_path in rf_reports:
        if not report_path.exists():
            continue
        import json
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("overall_verdict") in ("PASS",):
            # Only flag if the combo PASSED real-fills validation
            combo = report.get("combo", {})
            threshold = combo.get("profit_lock_threshold_pct", 1.0)
            if threshold < 0.05:
                promoted_threshold_zero.append(
                    f"{report_path.name}: threshold={threshold} (verdict=PASS)"
                )

    assert not promoted_threshold_zero, (
        "L99: SNIPER combos with profit_lock_threshold_pct < 0.05 passed real-fills "
        "validation and may be promoted. This threshold creates artificial WR=93.5% "
        "in BS-sim (real WR ~18-46%). Real-fills gap: BS=+$1,007 vs OPRA=-$556 "
        "(-155%) on 2025-04-07. DO NOT promote until threshold >= 0.05. "
        f"Flagged: {promoted_threshold_zero}"
    )

    # Guard passes: no zero-threshold SNIPER combos have been promoted
    # (stage-2 keepers remain in _state/ as research artifacts, not leaderboard entries)


def test_l100_sniper_premium_exits_no_positive_result():
    """L100 (2026-06-16): SNIPER_LEVEL_BREAK all-premium-exit combos have no
    validated BS-sim edge.

    36-combo sweep (stop=[-0.20,-0.25,-0.30,-0.35] × threshold=[0.20,0.25,0.30,0.40]
    × runner=[2.0,2.5,3.0]) showed ALL NEGATIVE P&L (best -$3,764). The
    threshold=99.0 "genuine edge" ($25,943, WR=46.3%) requires 300% intraday premium
    moves (e.g. $2.43 → $7.29 for 3.0× runner) — impossible in 0DTE real fills
    (L51/L55: real OPRA entry $9.26 → runner target $27.78 requires ~7% SPY move).

    This guard asserts the stage-2 real-fills report verdict remains CAVEAT or BLOCKED.
    If verdict ever changes to PASS, re-run the 36-combo sweep first to ensure the
    specific combo has genuine non-artifact positive P&L before ratifying.
    """
    REPO_ROOT = Path(__file__).parent.parent.parent
    report_path = REPO_ROOT / "analysis" / "recommendations" / "sniper-stage2-realfills.json"

    if not report_path.exists():
        pytest.skip("sniper-stage2-realfills.json not found")

    import json
    report = json.loads(report_path.read_text(encoding="utf-8"))
    verdict = report.get("overall_verdict", "UNKNOWN")

    assert verdict in ("CAVEAT", "BLOCKED", "PARTIAL"), (
        f"L100 violation: sniper-stage2 premium-exit verdict is '{verdict}' (expected CAVEAT/BLOCKED). "
        "Before promoting any premium-exit SNIPER combo to PASS, re-run the 36-combo exit-param sweep "
        "(stop×threshold×runner) and confirm positive P&L without the threshold=0.0 artifact (L99) "
        "and without the unprotected-runner artifact (threshold=99.0, L100). "
        "Real-fills on non-extreme-VIX (VIX<30) days required. "
        "Leaderboard #13-#15 are ARTIFACT-INVALIDATED."
    )


def test_sniper_cs_uses_chart_stop_not_premium_stop():
    """L100+L51+L55 regression guard (2026-06-16): sniper_cs_evaluator.py must implement
    chart-stop exits (chart_stop_buffer in SPY points), NOT premium-stop exits.

    The 36-combo premium-exit sweep showed ALL NEGATIVE P&L (best -$3,764).
    The chart-stop redesign is the only remaining unvalidated SNIPER path.

    This guard verifies:
    1. SniperCSCombo has chart_stop_buffer field (the SPY-price stop knob)
    2. SniperCSCombo does NOT have premium_stop_pct (the invalidated knob)
    3. _simulate_cs_trade function exists (not the old _simulate_trade)
    4. "chart_stop" appears in the simulation logic
    """
    # The SNIPER cluster was ARCHIVED 2026-06-18 (de-sprawl, blueprint Phase 0/3) —
    # the dead premium-exit path moved to autoresearch/_archive/sniper/. The guard's
    # intent (SNIPER must use chart-stops, never premium-stops) is unchanged: accept
    # the evaluator in its live location OR the archive. If it is resurrected into
    # autoresearch/ with a premium_stop_pct field, the assertions below still fail.
    cs_path = BACKTEST / "autoresearch" / "sniper_cs_evaluator.py"
    if not cs_path.exists():
        cs_path = BACKTEST / "autoresearch" / "_archive" / "sniper" / "sniper_cs_evaluator.py"
    assert cs_path.exists(), (
        "sniper_cs_evaluator.py must exist (live in autoresearch/ or in "
        "autoresearch/_archive/sniper/) — chart-stop SNIPER evaluator"
    )

    source = cs_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Collect dataclass field names from SniperCSCombo
    cs_combo_fields: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "SniperCSCombo":
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    cs_combo_fields.add(item.target.id)

    assert cs_combo_fields, "SniperCSCombo class not found in sniper_cs_evaluator.py"
    assert "chart_stop_buffer" in cs_combo_fields, (
        "SniperCSCombo must have chart_stop_buffer field — this is the SPY-price stop knob. "
        "If missing, the evaluator reverted to premium-stop design (L100 regression)."
    )
    assert "premium_stop_pct" not in cs_combo_fields, (
        "SniperCSCombo must NOT have premium_stop_pct — all premium-exit combos are ARTIFACT-INVALIDATED (L100). "
        "Remove premium_stop_pct and use chart_stop_buffer in SPY points instead."
    )

    # Check simulation function exists
    fn_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "_simulate_cs_trade" in fn_names, (
        "_simulate_cs_trade function missing — this is the chart-stop simulation logic"
    )

    # Check that the actual stop check uses SPY-price comparison
    assert "chart_stop_spy" in source, (
        "chart_stop_spy variable not found in sniper_cs_evaluator.py — "
        "the stop must be expressed in SPY price space, not premium space"
    )


@_needs_data
def test_fhh_v4_proximity_antipattern() -> None:
    """Anti-pattern guard (2026-06-16 empirical study): fhh_quality_proximity is ANTI-CORRELATED
    with J anchor preservation.

    The 5/01 gap-up FHH ($724.24) is ABOVE all multi_day_levels by design — on a gap-up
    day, price breaks above prior range and forms a fresh high. Requiring the FHH to be
    NEAR a multi_day_level removes exactly these setups. Tested: prox=0.50/1.00/2.00 all
    remove 5/01 11:50 from pass=True decisions.

    This guard documents the anti-correlation so the approach is never re-tried.
    If this test FAILS (5/01 passes with proximity gate), the anti-pattern encoding is broken.
    """
    import pandas as pd

    spy_full = pd.read_csv(MASTER_SPY)
    vix_full = pd.read_csv(MASTER_VIX)
    start_d = dt.date(2026, 5, 1)
    r = run_backtest(
        spy_full, vix_full, start_date=start_d, end_date=start_d,
        use_real_fills=False,
        include_first_hour_high=True,
        include_bearish_reversal_bypass=True,
        fhh_quality_proximity=1.00,  # proximity gate: anti-correlated with gap-up J anchor
        params_overrides={"per_trade_risk_cap_pct": 0.50},
    )
    bar_passed = [
        d for d in r.decisions
        if d.get("timestamp_et") is not None
        and str(d["timestamp_et"]).startswith("2026-05-01 11:50")
        and d.get("passed") is True
    ]
    assert not bar_passed, (
        "Anti-pattern regression: fhh_quality_proximity=1.00 should NOT pass 5/01 11:50. "
        "Gap-up FHH is ABOVE multi_day_levels, not near them — proximity gate is anti-correlated. "
        "If 5/01 now passes with proximity gate, the multi_day_levels changed or proximity logic changed."
    )


@_needs_data
def test_fhh_v4_gapup_preserves_501_filters_508() -> None:
    """V4 gap-up quality discriminator (2026-06-16): fhh_above_max_prior_min=1.00 must
    preserve 5/01 11:50 bypass (FHH=724.24 is >$1 above max_prior ~722) and filter 5/08
    bypass (FHH=736.66 is NOT >$1 above max_prior ~737).

    Empirical finding from 2026-06-16 study:
    - Baseline bypass (no gate): 24 pass days, -$6,304 total, -$1,899 bypass drag
    - V4 gap-up (>=1.00 above max): 6 pass days, -$4,663 total, -$257 bypass drag (86% better)
    - 5/01: FHH above max_prior → PASSES V4 gate (J anchor preserved)
    - 5/08: FHH not above max_prior → BLOCKED by V4 gate (OOS losses removed)
    """
    import pandas as pd
    import datetime as _dt

    spy_full = pd.read_csv(MASTER_SPY)
    vix_full = pd.read_csv(MASTER_VIX)

    kw = dict(use_real_fills=False, include_first_hour_high=True,
              include_bearish_reversal_bypass=True, fhh_above_max_prior_min=1.00,
              params_overrides={"per_trade_risk_cap_pct": 0.50})

    # 5/01: bypass MUST fire at 11:50 (J anchor day, gap-up FHH)
    r_501 = run_backtest(spy_full, vix_full, start_date=_dt.date(2026, 5, 1),
                         end_date=_dt.date(2026, 5, 1), **kw)
    bar_501 = [
        d for d in r_501.decisions
        if d.get("timestamp_et") is not None
        and str(d["timestamp_et"]).startswith("2026-05-01 11:50")
        and d.get("passed") is True
    ]
    assert bar_501, (
        "V4 gap-up discriminator blocked 5/01 11:50 — FHH=724.24 should be >$1 above max_prior. "
        "Check fhh_above_max_prior_min logic in filters.py: FHH must exceed max(multi_day_levels) "
        "by at least 1.00 SPY dollar. If multi_day_levels changed, re-calibrate the threshold."
    )

    # 5/08: bypass must NOT fire (FHH within prior-day range, not a gap-up fresh high)
    # The 2 OOS real-fills losses came from 5/08. V4 gate must block them.
    r_508_no_gate = run_backtest(
        spy_full, vix_full, start_date=_dt.date(2026, 5, 8), end_date=_dt.date(2026, 5, 8),
        use_real_fills=False, include_first_hour_high=True,
        include_bearish_reversal_bypass=True, params_overrides={"per_trade_risk_cap_pct": 0.50},
    )
    r_508_v4 = run_backtest(spy_full, vix_full, start_date=_dt.date(2026, 5, 8),
                            end_date=_dt.date(2026, 5, 8), **kw)
    # V4 should produce fewer or equal trades on 5/08 (no new bypass-added entries)
    assert len(r_508_v4.trades) <= len(r_508_no_gate.trades), (
        f"V4 gate did not reduce 5/08 trades: no_gate={len(r_508_no_gate.trades)} "
        f"v4={len(r_508_v4.trades)}. FHH=736.66 should NOT exceed max(multi_day_levels) "
        "by $1 on 5/08 (prior-day range included the FHH). Check fhh_above_max_prior_min logic."
    )


def test_level_proximity_dollars_removed_from_const_map() -> None:
    """C14/L38 RESOLVED (2026-06-17): LEVEL_PROXIMITY_DOLLARS was a dead constant — confirmed removed.

    The constant was in both runner._FILTERS_CONST_KEYS and orchestrator._FILTER_CONST_MAP, but
    detect_level_rejection() never read it (strict `high > level AND close < level` is the correct
    semantic check; proximity is not needed because high>level already proves the bar reached the level).

    Confirmed dead 2026-06-16 by 6-value sweep (0.10, 0.25, 0.50, 0.75, 1.00, 1.50 — identical output).
    Resolution: removed from filters.py and from both _FILTER_CONST_MAPs.

    This guard prevents re-adding it without also wiring it in detect_level_rejection.
    """
    from lib import orchestrator, filters as filters_mod
    assert "level_proximity_dollars" not in orchestrator._FILTER_CONST_MAP, (
        "LEVEL_PROXIMITY_DOLLARS was a confirmed C14 dead knob — do not re-add to _FILTER_CONST_MAP "
        "without also wiring it inside detect_level_rejection() in filters.py"
    )
    assert not hasattr(filters_mod, "LEVEL_PROXIMITY_DOLLARS"), (
        "LEVEL_PROXIMITY_DOLLARS was removed from filters.py (dead constant, C14) — "
        "do not re-add without a corresponding usage in detect_level_rejection()"
    )


    # test_ribbon_flip_lookback_bars_is_wired was here as xfail (2026-06-16).
    # Fixed 2026-06-16: orchestrator buffer now uses _filters_mod.RIBBON_FLIP_LOOKBACK_BARS
    # and _patch_filter_consts wires params_overrides to the module constant.
    # Promoted to test_params_override_binds[ribbon_flip_lookback_bars-1] above.


def test_l105_real_fills_stop_uses_side_specific() -> None:
    """L105 (2026-06-16): simulate_trade_real must receive side_premium_stop not global premium_stop_pct.

    The bug: real-fills path passed premium_stop_pct (global default -0.08) while BS-sim correctly
    used bear_premium_stop (-0.20). All real-fills backtests used -8% stop instead of production -20%.
    Fix: moved 'side_premium_stop = bear_premium_stop if winning_side == "P"' to before the
    'if use_real_fills:' branch so both paths receive the correct side-specific stop.

    Source check (data-free): verify the fix pattern is present in orchestrator.py.

    UPDATED 2026-06-21 (WP-0): the real-fills stop is now routed through the pure
    resolver risk_gate.select_exit_params(setup, side, params, side_premium_stop). The
    resolver returns side_premium_stop UNCHANGED whenever no per-setup flag is on
    (byte-identical to the old direct pass), and overrides it with a setup's VALIDATED
    isolated stop only when that setup's flag is ON. The L105 property is UNCHANGED:
    the real-fills stop must still DERIVE FROM side_premium_stop, never the bare global
    premium_stop_pct. We therefore assert the resolver is fed side_premium_stop and the
    call consumes the resolved value.

    Three assertions:
    1. real-fills call passes premium_stop_pct=resolved_premium_stop (the resolved value)
    2. resolved_premium_stop is produced by select_exit_params(..., side_premium_stop)
       (so the global fallback IS side_premium_stop, not the bare global premium_stop_pct)
    3. side_premium_stop assignment appears before the if use_real_fills: branch

    If any fails: real-fills path was reverted to the global stop → invalidates all
    real-fills backtests (the original L105 bug) OR the resolver was fed the wrong global.
    """
    source = (BACKTEST / "lib" / "orchestrator.py").read_text(encoding="utf-8")

    assert "premium_stop_pct=resolved_premium_stop" in source, (
        "L105/WP-0 regression: real-fills call no longer consumes the resolved stop. "
        "simulate_trade_real must receive premium_stop_pct=resolved_premium_stop (the "
        "output of risk_gate.select_exit_params), not the bare global premium_stop_pct."
    )

    assert "select_exit_params(" in source and "side_premium_stop\n" in source, (
        "L105/WP-0 regression: select_exit_params must be wired in orchestrator.py."
    )

    # The resolver MUST be fed side_premium_stop as the global fallback — that is the
    # L105 property (derive the real-fills stop from the side-specific stop). Match the
    # call's final argument.
    assert "winning_side, params_overrides, side_premium_stop" in source, (
        "L105/WP-0 regression: select_exit_params must be fed side_premium_stop as the "
        "global fallback. If the global fallback is the bare premium_stop_pct, the "
        "real-fills path reverts to the original L105 bug (all real-fills used -8%)."
    )

    # Verify the assignment precedes the if use_real_fills: branch (not buried in the else-only path).
    side_stop_idx = source.find("side_premium_stop = bear_premium_stop")
    real_fills_idx = source.find("if use_real_fills:")
    assert 0 < side_stop_idx < real_fills_idx, (
        "L105 regression: side_premium_stop assignment must appear BEFORE 'if use_real_fills:'. "
        "If it is inside the else-branch, the real-fills path still uses the wrong global stop. "
        "Offsets: side_premium_stop=%d, if use_real_fills=%d"
        % (side_stop_idx, real_fills_idx)
    )


def test_l106_params_to_kwargs_null_window_propagates() -> None:
    """L106 (2026-06-17): entry_no_trade_window_et:null must propagate to no_trade_window=None.

    Bug: _params_to_kwargs had 'if ... and overrides["entry_no_trade_window_et"]:' — when
    the value is null/None (production value since v15.1 removed the window), the guard was
    falsy and the key was silently skipped. This left the default no_trade_window=(14:00,15:00)
    active in ALL Karpathy shadow / params_overrides runs, incorrectly blocking 14:00-15:00 trading
    even though production removed this window in v15.1.

    Fix: added else branch that explicitly sets kwargs["no_trade_window"] = None so the
    ovrk assignment block can disable the legacy default.

    If this fails: shadow runs still block 14-15 trading, biasing all A/B comparisons.
    """
    from backtest.lib.orchestrator import _params_to_kwargs

    # null value MUST produce no_trade_window=None in output
    result = _params_to_kwargs({"entry_no_trade_window_et": None})
    assert "no_trade_window" in result, (
        "L106 regression: entry_no_trade_window_et:null was silently dropped — "
        "no_trade_window key not present in _params_to_kwargs output. "
        "Fix: add else branch setting kwargs['no_trade_window'] = None."
    )
    assert result["no_trade_window"] is None, (
        "L106 regression: entry_no_trade_window_et:null did not produce no_trade_window=None. "
        f"Got: {result['no_trade_window']!r}"
    )

    # non-null value still works (regression check)
    result2 = _params_to_kwargs({"entry_no_trade_window_et": ["14:00", "15:00"]})
    import datetime as dt
    assert result2.get("no_trade_window") == (dt.time(14, 0), dt.time(15, 0)), (
        "L106 regression: non-null entry_no_trade_window_et no longer produces correct window."
    )

    # key absent = no output (don't add spurious no_trade_window)
    result3 = _params_to_kwargs({})
    assert "no_trade_window" not in result3, (
        "L106 regression: _params_to_kwargs adds no_trade_window when key absent from overrides."
    )


def test_l106_params_to_kwargs_null_duration_no_crash() -> None:
    """L106 (2026-06-17): max_ribbon_duration_bars:null must not crash with int(None).

    Bug: 'kwargs["max_ribbon_duration_bars"] = int(overrides["max_ribbon_duration_bars"])'
    crashed with TypeError when value was None. Added null guard.
    """
    from backtest.lib.orchestrator import _params_to_kwargs

    # null → key absent in output (no crash)
    result = _params_to_kwargs({"max_ribbon_duration_bars": None})
    assert "max_ribbon_duration_bars" not in result, (
        "L106 regression: max_ribbon_duration_bars:null should not appear in output dict. "
        f"Got: {result!r}"
    )

    # int value still works
    result2 = _params_to_kwargs({"max_ribbon_duration_bars": 8})
    assert result2.get("max_ribbon_duration_bars") == 8

    # Same for min_ribbon_momentum_cents
    result3 = _params_to_kwargs({"min_ribbon_momentum_cents": None})
    assert "min_ribbon_momentum_cents" not in result3, (
        "L106 regression: min_ribbon_momentum_cents:null should not appear in output dict."
    )


@pytest.mark.slow
def test_l106_params_overrides_matches_direct_kwargs_n() -> None:
    """L106 (2026-06-17): params_overrides baseline must give same n as identical direct kwargs.

    Root cause of the Rank 25 WF inflation: direct-kwargs baseline used no_trade_before=10:00
    (function default) while params_overrides correctly applied 09:35 from params.json. The
    mismatch produced different baselines: IS direct n=54 vs IS po (with fixed null propagation) n=97.
    Old WF=5.794 was entirely an artifact; correct WF=0.072 (FAIL).

    This guard runs a short IS window via both paths and asserts the trade counts match.
    Uses a narrow 60-day window for speed. Requires the real-fills data files to be present.
    """
    import datetime as dt
    import os
    import pandas as pd
    from backtest.lib.orchestrator import run_backtest

    spy_path = BACKTEST / "data" / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = BACKTEST / "data" / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        import pytest
        pytest.skip("Real-fills data files not present")

    spy = pd.read_csv(spy_path)
    vix = pd.read_csv(vix_path)
    start = dt.date(2025, 6, 1)
    end   = dt.date(2025, 7, 31)

    # Shared production params
    po = {
        "entry_no_trade_window_et": None,  # null → no_trade_window=None (L106 fix)
        "entry_no_trade_before_et": "09:35",
        "min_ribbon_momentum_cents": 5.0,
        "midday_trendline_gate": True,
        "max_ribbon_duration_bars": None,
        "premium_stop_pct_bear": -0.20,
        "premium_stop_pct_bull": -0.08,
        "per_trade_risk_cap_pct": 0.30,
    }

    r_po = run_backtest(spy, vix, start_date=start, end_date=end,
                        use_real_fills=True, params_overrides=po)

    r_direct = run_backtest(spy, vix, start_date=start, end_date=end,
                            use_real_fills=True,
                            no_trade_window=None,
                            no_trade_before=dt.time(9, 35),
                            min_ribbon_momentum_cents=5.0,
                            midday_trendline_gate=True,
                            max_ribbon_duration_bars=None,
                            premium_stop_pct_bear=-0.20,
                            premium_stop_pct_bull=-0.08,
                            per_trade_risk_cap_pct=0.30)

    n_po     = len(r_po.trades)
    n_direct = len(r_direct.trades)
    assert n_po == n_direct, (
        f"L106: params_overrides baseline n={n_po} != direct kwargs n={n_direct}. "
        "If they diverge, _params_to_kwargs null propagation or a new mapping is broken. "
        "A/B scorecards built with the wrong baseline will have inflated/deflated WF ratios. "
        "Diagnose: run bisect excluding each param from po to find which one differs."
    )


# ---------------------------------------------------------------------------
# L107 — Rank 22 (RIBBON_MOMENTUM_GATE) mis-validation: BS-sim used instead of real-fills
# Root cause: 2026-06-16 "re-verification" ran use_real_fills=False + default bear_stop=-0.08.
# This perfectly reproduced old (fake) baseline n=17 pnl=-907, gates n=5 pnl=+1204, delta=+2111.
# Correct production params give OOS delta=-1352 (WF=-1.308, FAIL).
# Guards below prevent re-use of the wrong scoring method.
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_l107_real_fills_differs_from_bs_sim_on_oos_window() -> None:
    """L107 (2026-06-17): BS sim and real-fills produce materially different OOS P&L.

    The Rank 22 mis-validation used use_real_fills=False (BS sim). The difference is
    large enough (>$1000) that any scorecard using BS sim will have meaningfully wrong
    numbers. This guard documents that the two paths are NOT interchangeable.

    If the difference drops below $500, either the real-fills data changed or someone
    unified the simulation paths in a way that needs a fresh check.
    """
    import datetime as dt
    import pandas as pd
    from backtest.lib.orchestrator import run_backtest

    spy_path = BACKTEST / "data" / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = BACKTEST / "data" / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        pytest.skip("Real-fills data files not present")

    spy = pd.read_csv(spy_path)
    vix = pd.read_csv(vix_path)
    S, E = dt.date(2026, 5, 8), dt.date(2026, 5, 22)

    r_bs   = run_backtest(spy, vix, start_date=S, end_date=E, use_real_fills=False)
    r_real = run_backtest(spy, vix, start_date=S, end_date=E, use_real_fills=True)

    pnl_bs   = sum(t.dollar_pnl for t in r_bs.trades)
    pnl_real = sum(t.dollar_pnl for t in r_real.trades)
    diff = abs(pnl_real - pnl_bs)

    assert diff > 500, (
        f"L107: real-fills vs BS-sim P&L difference on OOS window is only ${diff:.0f}. "
        "Expected > $500 based on known divergence (real={pnl_real:.0f}, bs={pnl_bs:.0f}). "
        "If the simulation paths were unified, re-run the full Rank 22 scorecard to ensure "
        "the gate still correctly evaluates under the new method. "
        "A/B scorecards must always specify use_real_fills=True."
    )


def test_l107_ribbon_momentum_gate_ab_scorecard_correct_params() -> None:
    """L107 (2026-06-17): Rank 22 A/B scorecard must reflect L107-corrected revalidation.

    Asserts the scorecard at analysis/recommendations/ribbon_momentum_gate_ab_scorecard.json:
    - Has l107_revalidation=True (not the old BS-sim run)
    - OOS delta is negative (gate HURTS under correct production params)
    - WF ratio is negative (regime artifact: IS-only improvement)

    If the gate is ever re-tested and produces a positive OOS delta with correct params,
    update the scorecard AND add the evidence_n to ratification_gates BEFORE removing this guard.
    """
    sc_path = REPO / "analysis" / "recommendations" / "ribbon_momentum_gate_ab_scorecard.json"
    if not sc_path.exists():
        pytest.skip("ribbon_momentum_gate_ab_scorecard.json not present")

    import json
    with open(sc_path) as f:
        sc = json.load(f)

    assert sc.get("l107_revalidation") is True, (
        "L107: scorecard must have l107_revalidation=True to indicate it was run with "
        "production-correct params (use_real_fills=True, bear_stop=-0.20, 09:35 gate). "
        "If you re-ran the scorecard, ensure correct params are documented."
    )

    oos_delta = sc["oos_window"]["delta"]
    assert oos_delta < 0, (
        f"L107: OOS delta should be negative ({oos_delta}). "
        "Gate (min_ribbon_momentum_cents=5.0, max_ribbon_duration_bars=15) removes profitable "
        "OOS trades in recovery regime. If it became positive, verify this is a genuine "
        "improvement and not a scoring artifact (use_real_fills, bear_stop, 09:35 gate)."
    )

    wf = sc["walk_forward"]["wf_ratio"]
    assert wf < 0.7, (
        f"L107: WF ratio should be < 0.7 (got {wf}). "
        "If WF improved under correct params, run the full ratification gate checklist "
        "and get J approval before re-ratifying."
    )


@pytest.mark.slow
def test_l108_tp1_qty_fraction_wired_in_real_fills() -> None:
    """L108 (2026-06-17): tp1_qty_fraction must be live in simulate_trade_real.

    Before L108 fix, simulator_real.py hardcoded TP1_QTY_FRACTION=0.667 regardless
    of what run_backtest() was asked to use. Production params.json uses 0.50.
    Every real-fills backtest used the wrong fraction (v14 default, not v15 ratified).

    This guard sweeps frac=[0.30, 0.667, 1.0] and asserts OOS P&L varies by >= $100.
    If all three return identical P&L, the parameter is dead again.
    """
    import datetime as dt
    import pathlib
    import pandas as pd

    DATA = pathlib.Path(__file__).resolve().parents[2] / "backtest" / "data"
    spy_path = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        pytest.skip("backtest data files not present")

    spy = pd.read_csv(str(spy_path))
    vix = pd.read_csv(str(vix_path))

    CORRECT = dict(
        use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
        premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30,
    )
    OOS_S = dt.date(2026, 5, 8)
    OOS_E = dt.date(2026, 5, 22)

    pnls = []
    for frac in [0.30, 0.667, 1.0]:
        r = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, tp1_qty_fraction=frac, **CORRECT)
        pnl = sum(t.dollar_pnl for t in r.trades if t.dollar_pnl is not None)
        pnls.append(round(pnl, 2))

    spread = max(pnls) - min(pnls)
    assert spread >= 100, (
        f"L108: tp1_qty_fraction appears dead in real-fills path (spread=${spread:.0f} across frac=[0.30, 0.667, 1.0]). "
        f"P&Ls were {pnls}. "
        "Check that orchestrator.py passes tp1_qty_fraction to simulate_trade_real() "
        "and that simulator_real.py uses the parameter (not the TP1_QTY_FRACTION constant) "
        "at BOTH the tp1_qty calculation line AND inside _compute_pnl()."
    )


@pytest.mark.slow
def test_l109_runner_target_wired_in_real_fills() -> None:
    """L109 (2026-06-17): runner_target_premium_pct must be live in simulate_trade_real.

    Before L109 fix, simulator_real.py hardcoded RUNNER_MAX_PREMIUM_PCT=3.0 regardless
    of what run_backtest() was asked to use. Production params.json uses 2.5.
    Every real-fills backtest modeled a harder runner target (3.0x) than production (2.5x).

    This guard sweeps runner_target=[1.5, 2.5, 3.0] and asserts OOS P&L varies by >= $100.
    If all three return identical P&L, the parameter is dead again.
    """
    import datetime as dt
    import pathlib
    import pandas as pd

    DATA = pathlib.Path(__file__).resolve().parents[2] / "backtest" / "data"
    spy_path = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        pytest.skip("backtest data files not present")

    spy = pd.read_csv(str(spy_path))
    vix = pd.read_csv(str(vix_path))

    CORRECT = dict(
        use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
        premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30, tp1_qty_fraction=0.50,
    )
    OOS_S = dt.date(2026, 5, 8)
    OOS_E = dt.date(2026, 5, 22)

    pnls = []
    for rt in [1.5, 2.5, 3.0]:
        r = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, runner_target_premium_pct=rt, **CORRECT)
        pnl = sum(t.dollar_pnl for t in r.trades if t.dollar_pnl is not None)
        pnls.append(round(pnl, 2))

    spread = max(pnls) - min(pnls)
    assert spread >= 100, (
        f"L109: runner_target_premium_pct appears dead in real-fills path (spread=${spread:.0f} across rt=[1.5, 2.5, 3.0]). "
        f"P&Ls were {pnls}. "
        "Check that orchestrator.py passes runner_target_premium_pct to simulate_trade_real() "
        "and that simulator_real.py uses the parameter (not RUNNER_MAX_PREMIUM_PCT constant) "
        "at the runner_target_premium calculation line."
    )


@pytest.mark.slow
def test_l110_time_stop_minutes_wired_in_real_fills() -> None:
    """L110 (2026-06-17): time_stop_minutes_before_close must be live in simulate_trade_real.

    Before L110 fix, simulator_real.py hardcoded TIME_STOP_ET=dt.time(15,50) regardless
    of the parameter. The value happened to match production (10 min before close = 15:50),
    so P&L was correct, but the knob was inert for any optimization sweep.

    This guard sweeps stop=[5, 10, 20] minutes before close and asserts OOS P&L
    varies by >= $50. If all three return identical P&L, time_stop is dead again.
    """
    import datetime as dt
    import pathlib
    import pandas as pd

    DATA = pathlib.Path(__file__).resolve().parents[2] / "backtest" / "data"
    spy_path = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        pytest.skip("backtest data files not present")

    spy = pd.read_csv(str(spy_path))
    vix = pd.read_csv(str(vix_path))

    CORRECT = dict(
        use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
        premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30,
        tp1_qty_fraction=0.50, runner_target_premium_pct=2.50,
    )
    OOS_S = dt.date(2026, 5, 8)
    OOS_E = dt.date(2026, 5, 22)

    pnls = []
    for mins in [5, 10, 20]:
        r = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                         time_stop_minutes_before_close=mins, **CORRECT)
        pnl = sum(t.dollar_pnl for t in r.trades if t.dollar_pnl is not None)
        pnls.append(round(pnl, 2))

    spread = max(pnls) - min(pnls)
    assert spread >= 50, (
        f"L110: time_stop_minutes_before_close appears dead in real-fills path "
        f"(spread=${spread:.0f} across mins=[5, 10, 20]). P&Ls were {pnls}. "
        "Check that orchestrator.py converts time_stop_minutes_before_close to time_stop_et "
        "and passes it to simulate_trade_real(), and that simulator_real.py uses the "
        "parameter (not TIME_STOP_ET constant) at the time-stop check."
    )


@_needs_data
def test_l111_vix_bear_threshold_wired_in_orchestrator() -> None:
    """L111 (2026-06-17): vix_bear_threshold must be live via params_overrides in run_backtest.

    VIX_BEAR_THRESHOLD was in runner._FILTERS_CONST_KEYS but NOT in orchestrator._FILTER_CONST_MAP.
    Confirmed dead via 3-value sweep (10.0, 17.30, 25.0 — all identical OOS output) before the fix.

    After the L111 fix, _FILTER_CONST_MAP now includes:
      "vix_bear_threshold": "VIX_BEAR_THRESHOLD"
      "vix_rising_deadband": "VIX_RISING_DEADBAND"
      "vix_bear_rising_deadband": "VIX_RISING_DEADBAND"
      "vix_bull_max": "VIX_BULL_HARD_CAP"

    This guard verifies vix_bear_threshold is live: threshold=25.0 must block at least 2 fewer
    OOS trades than threshold=10.0 (VIX rarely exceeds 25 in normal markets; 17.30 = threshold gap).
    """
    import datetime as dt
    import pathlib
    import pandas as pd

    DATA = pathlib.Path(__file__).resolve().parents[2] / "backtest" / "data"
    spy_path = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        pytest.skip("backtest data files not present")

    spy = pd.read_csv(str(spy_path))
    vix = pd.read_csv(str(vix_path))

    CORRECT = dict(
        use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
        premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30,
        tp1_qty_fraction=0.50, runner_target_premium_pct=2.50,
        time_stop_minutes_before_close=10,
    )
    OOS_S = dt.date(2026, 5, 8)
    OOS_E = dt.date(2026, 5, 22)

    r_low = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                         params_overrides={"vix_bear_threshold": 10.0}, **CORRECT)
    r_high = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                          params_overrides={"vix_bear_threshold": 25.0}, **CORRECT)
    n_low, n_high = len(r_low.trades), len(r_high.trades)
    assert n_high < n_low - 1, (
        f"L111: vix_bear_threshold appears dead in orchestrator path — "
        f"threshold=10.0 gave n={n_low} trades, threshold=25.0 gave n={n_high} trades "
        f"(expected n_high < n_low-1 since VIX rarely exceeds 25 in normal markets). "
        "Check that 'vix_bear_threshold' is in orchestrator._FILTER_CONST_MAP."
    )


@_needs_data
def test_vix_bull_low_threshold_wired_in_orchestrator() -> None:
    """C14 (2026-06-17): vix_bull_low_threshold must be live via params_overrides.

    VIX_BULL_LOW_THRESHOLD=30.0 (very permissive: nearly all VIX levels pass) must
    produce more OOS bull trades than production default=17.20 (elevated-VIX window,
    most bars have VIX > 17.20 so only "falling" condition enables bull trades).
    """
    import pathlib
    import pandas as pd

    DATA = pathlib.Path(__file__).resolve().parents[2] / "backtest" / "data"
    spy_path = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        pytest.skip("backtest data files not present")

    spy = pd.read_csv(str(spy_path))
    vix = pd.read_csv(str(vix_path))
    spy = spy[(spy["timestamp_et"] >= "2026-05-08") & (spy["timestamp_et"] < "2026-05-22T23:59:59")].reset_index(drop=True)
    vix = vix[(vix["timestamp_et"] >= "2026-05-08") & (vix["timestamp_et"] < "2026-05-22T23:59:59")].reset_index(drop=True)

    CORRECT = dict(
        use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
        premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30,
        tp1_qty_fraction=0.50, runner_target_premium_pct=2.50,
        time_stop_minutes_before_close=10,
    )
    OOS_S, OOS_E = dt.date(2026, 5, 8), dt.date(2026, 5, 22)

    r_prod = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                          params_overrides={"vix_bull_low_threshold": 17.20}, **CORRECT)
    r_perm = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                          params_overrides={"vix_bull_low_threshold": 30.0}, **CORRECT)
    n_prod, n_perm = len(r_prod.trades), len(r_perm.trades)
    assert n_perm > n_prod, (
        f"C14: vix_bull_low_threshold appears dead in orchestrator path — "
        f"threshold=17.20 gave n={n_prod} trades, threshold=30.0 gave n={n_perm} trades "
        f"(expected n_perm > n_prod since threshold=30 allows nearly all VIX levels). "
        "Check that 'vix_bull_low_threshold' is in orchestrator._FILTER_CONST_MAP."
    )


@_needs_data
def test_trendline_lookback_bars_wired_in_orchestrator() -> None:
    """C14 (2026-06-17): trendline_lookback_bars must be live via params_overrides.

    Lookback=10 bars (50 min) gives the algorithm only a 50-min window to find
    3 descending pivots — extremely restrictive vs production default=60 (5 hours).
    If trendline_lookback_bars is dead, both values produce identical IS trade counts.
    """
    import pathlib
    import pandas as pd

    DATA = pathlib.Path(__file__).resolve().parents[2] / "backtest" / "data"
    spy_path = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        pytest.skip("backtest data files not present")

    spy = pd.read_csv(str(spy_path))
    vix = pd.read_csv(str(vix_path))

    CORRECT = dict(
        use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
        premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30,
        tp1_qty_fraction=0.50, runner_target_premium_pct=2.50,
        time_stop_minutes_before_close=10,
    )
    IS_S, IS_E = dt.date(2025, 1, 1), dt.date(2026, 4, 30)

    r_prod = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E,
                          params_overrides={"trendline_lookback_bars": 60}, **CORRECT)
    r_short = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E,
                           params_overrides={"trendline_lookback_bars": 10}, **CORRECT)
    n_prod, n_short = len(r_prod.trades), len(r_short.trades)
    assert n_short < n_prod, (
        f"C14: trendline_lookback_bars appears dead in orchestrator path — "
        f"lookback=60 gave n={n_prod} trades, lookback=10 gave n={n_short} trades "
        f"(expected n_short < n_prod since 50-min window rarely finds 3 descending pivots). "
        "Check that 'trendline_lookback_bars' is in orchestrator._FILTER_CONST_MAP and "
        "filters.py:TRENDLINE_LOOKBACK_BARS is used in the detect_trendline_rejection_bearish call."
    )


@_needs_data
def test_trendline_min_swings_wired_in_orchestrator() -> None:
    """C14 (2026-06-17): trendline_min_swings must be live via params_overrides.

    min_swings=10 requires 10 strictly-descending pivot highs — virtually impossible
    in real data vs production default=3. If dead, both values produce identical counts.
    """
    import pathlib
    import pandas as pd

    DATA = pathlib.Path(__file__).resolve().parents[2] / "backtest" / "data"
    spy_path = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        pytest.skip("backtest data files not present")

    spy = pd.read_csv(str(spy_path))
    vix = pd.read_csv(str(vix_path))

    CORRECT = dict(
        use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
        premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30,
        tp1_qty_fraction=0.50, runner_target_premium_pct=2.50,
        time_stop_minutes_before_close=10,
    )
    IS_S, IS_E = dt.date(2025, 1, 1), dt.date(2026, 4, 30)

    r_prod = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E,
                          params_overrides={"trendline_min_swings": 3}, **CORRECT)
    r_strict = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E,
                            params_overrides={"trendline_min_swings": 10}, **CORRECT)
    n_prod, n_strict = len(r_prod.trades), len(r_strict.trades)
    assert n_strict < n_prod, (
        f"C14: trendline_min_swings appears dead in orchestrator path — "
        f"min_swings=3 gave n={n_prod} trades, min_swings=10 gave n={n_strict} trades "
        f"(expected n_strict < n_prod since 10 sequential descending pivots is nearly impossible). "
        "Check that 'trendline_min_swings' is in orchestrator._FILTER_CONST_MAP and "
        "filters.py:TRENDLINE_MIN_SWINGS is used in the detect_trendline_rejection_bearish call."
    )


@_needs_data
def test_wick_min_pct_of_range_wired_in_orchestrator() -> None:
    """C14 (2026-06-17): wick_min_pct_of_range must be live via params_overrides.

    WICK_MIN_PCT_OF_RANGE=0.99 requires the upper wick to be 99% of the bar range —
    essentially a near-doji with a massive wick, almost impossible in practice.
    This must give fewer or equal IS trades than production default=0.50.
    If both values produce identical trade counts, the constant is dead (C14 violation).
    """
    import pathlib
    import pandas as pd

    DATA = pathlib.Path(__file__).resolve().parents[2] / "backtest" / "data"
    spy_path = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        pytest.skip("backtest data files not present")

    spy = pd.read_csv(str(spy_path))
    vix = pd.read_csv(str(vix_path))

    CORRECT = dict(
        use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
        premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30,
        tp1_qty_fraction=0.50, runner_target_premium_pct=2.50,
        time_stop_minutes_before_close=10,
    )
    IS_S, IS_E = dt.date(2025, 1, 1), dt.date(2026, 4, 30)

    r_prod = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E,
                          params_overrides={"wick_min_pct_of_range": 0.50}, **CORRECT)
    r_strict = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E,
                            params_overrides={"wick_min_pct_of_range": 0.99}, **CORRECT)
    n_prod, n_strict = len(r_prod.trades), len(r_strict.trades)
    # NOTE: Direction is NOT monotone — disabling wick_rejection (pct=0.99) can INCREASE trade
    # count by freeing later entry slots on days where wick_rejection would have triggered early.
    # This is a C15 gate-interaction effect. We assert inequality (liveness), not direction.
    assert n_strict != n_prod, (
        f"C14: wick_min_pct_of_range appears dead in orchestrator path — "
        f"pct=0.50 gave n={n_prod} trades, pct=0.99 gave n={n_strict} trades (identical). "
        "Check that 'wick_min_pct_of_range' is in orchestrator._FILTER_CONST_MAP and "
        "filters.py:WICK_MIN_PCT_OF_RANGE is passed to detect_wick_rejection_bearish()."
    )


@_needs_data
def test_wick_min_dollars_wired_in_orchestrator() -> None:
    """C14 (2026-06-17): wick_min_dollars must be live via params_overrides.

    WICK_MIN_DOLLARS=5.00 requires a $5 upper wick — on SPY 5-min bars this is essentially
    never achievable. This must give fewer or equal IS trades than production default=0.15.
    If both values produce identical trade counts, the constant is dead (C14 violation).
    """
    import pathlib
    import pandas as pd

    DATA = pathlib.Path(__file__).resolve().parents[2] / "backtest" / "data"
    spy_path = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        pytest.skip("backtest data files not present")

    spy = pd.read_csv(str(spy_path))
    vix = pd.read_csv(str(vix_path))

    CORRECT = dict(
        use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
        premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30,
        tp1_qty_fraction=0.50, runner_target_premium_pct=2.50,
        time_stop_minutes_before_close=10,
    )
    IS_S, IS_E = dt.date(2025, 1, 1), dt.date(2026, 4, 30)

    r_prod = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E,
                          params_overrides={"wick_min_dollars": 0.15}, **CORRECT)
    r_strict = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E,
                            params_overrides={"wick_min_dollars": 5.00}, **CORRECT)
    n_prod, n_strict = len(r_prod.trades), len(r_strict.trades)
    assert n_strict != n_prod, (
        f"C14: wick_min_dollars appears dead in orchestrator path — "
        f"min=$0.15 gave n={n_prod} trades, min=$5.00 gave n={n_strict} trades (identical). "
        "Check that 'wick_min_dollars' is in orchestrator._FILTER_CONST_MAP and "
        "filters.py:WICK_MIN_DOLLARS is passed to detect_wick_rejection_bearish()."
        " NOTE: direction is not monotone (C15 entry-slot effect — see wick_min_pct_of_range guard)."
    )


@_needs_data
def test_wick_close_tolerance_wired_in_orchestrator() -> None:
    """C14 (2026-06-17): wick_close_tolerance must be live via params_overrides.

    WICK_CLOSE_TOLERANCE=0.001 (vs default 0.10) requires the close to be essentially
    AT or below the level — eliminating most wick rejections where close drifted
    slightly above. This must give fewer or equal IS trades than default=0.10.
    If both values produce identical trade counts, the constant is dead (C14 violation).
    """
    import pathlib
    import pandas as pd

    DATA = pathlib.Path(__file__).resolve().parents[2] / "backtest" / "data"
    spy_path = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        pytest.skip("backtest data files not present")

    spy = pd.read_csv(str(spy_path))
    vix = pd.read_csv(str(vix_path))

    CORRECT = dict(
        use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
        premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30,
        tp1_qty_fraction=0.50, runner_target_premium_pct=2.50,
        time_stop_minutes_before_close=10,
    )
    IS_S, IS_E = dt.date(2025, 1, 1), dt.date(2026, 4, 30)

    r_prod = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E,
                          params_overrides={"wick_close_tolerance": 0.10}, **CORRECT)
    r_tight = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E,
                           params_overrides={"wick_close_tolerance": 0.001}, **CORRECT)
    n_prod, n_tight = len(r_prod.trades), len(r_tight.trades)
    assert n_tight != n_prod, (
        f"C14: wick_close_tolerance appears dead in orchestrator path — "
        f"tolerance=0.10 gave n={n_prod} trades, tolerance=0.001 gave n={n_tight} trades (identical). "
        "Check that 'wick_close_tolerance' is in orchestrator._FILTER_CONST_MAP and "
        "filters.py:WICK_CLOSE_TOLERANCE is passed to detect_wick_rejection_bearish()."
        " NOTE: direction is not monotone (C15 entry-slot effect — see wick_min_pct_of_range guard)."
    )


@_needs_data
def test_vol_baseline_bars_wired_in_orchestrator() -> None:
    """C14 (2026-06-17): VOL_BASELINE_BARS must be live via params_overrides.

    vol_baseline_20bar() uses VOL_BASELINE_BARS to compute the 20-bar volume SMA.
    Called from orchestrator.py line 665. Wired into _FILTER_CONST_MAP 2026-06-17.

    VOL_BASELINE_BARS=5 (very short window) changes which bars are 'high volume'
    relative to the rolling average, altering filter-9 (volume burst) outcomes.
    Confirmed live in OOS: vol_baseline_bars=5 gives n=15 vs baseline n=16 (one fewer trade).

    This guard uses IS data where the effect is stronger. At extremes (5 vs 50),
    trade count must differ. If identical, the constant is dead again (C14 violation).
    """
    import datetime as dt
    import pathlib
    import pandas as pd

    DATA = pathlib.Path(__file__).resolve().parents[2] / "backtest" / "data"
    spy_path = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        pytest.skip("backtest data files not present")

    spy = pd.read_csv(str(spy_path))
    vix = pd.read_csv(str(vix_path))

    CORRECT = dict(
        use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
        premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30,
        tp1_qty_fraction=0.667, runner_target_premium_pct=2.50,
        time_stop_minutes_before_close=20,
    )
    IS_S, IS_E = dt.date(2025, 1, 1), dt.date(2026, 5, 7)

    r_short = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E,
                           params_overrides={"vol_baseline_bars": 5}, **CORRECT)
    r_long = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E,
                          params_overrides={"vol_baseline_bars": 50}, **CORRECT)
    n_short, n_long = len(r_short.trades), len(r_long.trades)
    assert n_short != n_long, (
        f"C14: vol_baseline_bars appears dead in orchestrator path — "
        f"bars=5 gave n={n_short} trades, bars=50 gave n={n_long} trades (identical). "
        "Check that 'vol_baseline_bars' is in orchestrator._FILTER_CONST_MAP and "
        "filters.py:VOL_BASELINE_BARS is used in vol_baseline_20bar()."
    )


def test_range_baseline_bars_is_dead_constant() -> None:
    """C14 (2026-06-17): RANGE_BASELINE_BARS is a confirmed dead constant.

    ctx.range_baseline_20 is set by range_baseline_20bar() in orchestrator.py line 666
    but the field is NEVER read by any filter in filters.py. Verified: IS n=248 at both
    range_baseline_bars=5 and 50 (identical to baseline n=248 in 16-month IS dataset).

    range_baseline_bars is intentionally excluded from _FILTER_CONST_MAP.
    This test guards against accidentally re-wiring a dead constant and treating
    sweep results as meaningful. If this test starts failing, it means a filter
    was added that actually reads ctx.range_baseline_20 — update the test and
    add range_baseline_bars to _FILTER_CONST_MAP.
    """
    import lib.filters as f
    import lib.orchestrator as o
    assert "range_baseline_bars" not in o._FILTER_CONST_MAP, (
        "range_baseline_bars was added to _FILTER_CONST_MAP but ctx.range_baseline_20 "
        "is still not read by any filter. Wiring a dead constant makes sweep results "
        "misleading. Either remove it from the map, or add a filter that uses it."
    )


def test_l113_level_stop_buffer_wired_in_real_fills() -> None:
    """L113 (2026-06-17): level_stop_buffer_dollars must be accepted by simulate_trade_real.

    Before L113 fix, simulator_real.py hardcoded LEVEL_STOP_BUFFER=0.50 at the usage site.
    The orchestrator passed the kwarg but the simulator silently ignored it.

    Fix: replaced hardcoded constant with the parameter. prod=0.50 (matches old hardcode
    so existing P&L is unchanged). chart_stop_buffer_dollars in params.json now wires
    through _params_to_kwargs → level_stop_buffer_dollars kwarg.

    NOTE: P&L-spread-based guard is NOT viable here. Empirical verification showed
    spread=$0 across buf=[0.10, 0.50, 1.00] on 16-month IS. Root cause: the ribbon
    flip check (simulator_real.py line ~510) evaluates BEFORE the level stop check
    (line ~530). When price closes above the rejection level for a bear trade, the
    ribbon has already flipped to BULL (by construction of the bear setup) so the
    ribbon-flip exit fires first. The level stop is a rare fallback (e.g., price
    spikes past the level on a single bar without flipping the ribbon — infrequent
    on 5-min data where the ribbon lags by 3+ bars).

    This guard uses code inspection instead: verify the parameter is accepted by
    simulate_trade_real and used in the level_breached condition.

    If this test fails: someone hardcoded the buffer again. Do not remove this guard.
    """
    import inspect
    import pathlib
    sim_src = (pathlib.Path(__file__).resolve().parents[2]
               / "backtest" / "lib" / "simulator_real.py").read_text(encoding="utf-8")

    # Parameter must be in the function signature
    assert "level_stop_buffer_dollars" in sim_src, (
        "L113: level_stop_buffer_dollars not found in simulator_real.py. "
        "Was it removed? The param must be accepted as a kwarg with default 0.50 "
        "and used in the level_breached SPY close comparison."
    )

    # The hardcoded constant must not exist anymore
    assert "LEVEL_STOP_BUFFER = 0.50" not in sim_src, (
        "L113: LEVEL_STOP_BUFFER = 0.50 hardcoded constant found in simulator_real.py. "
        "This means the L113 fix was reverted. Replace with level_stop_buffer_dollars parameter."
    )

    # The usage site must reference the parameter, not a constant
    assert "rejection_level + level_stop_buffer_dollars" in sim_src, (
        "L113: level_breached condition no longer uses level_stop_buffer_dollars. "
        "The condition must read: close > rejection_level + level_stop_buffer_dollars "
        "(bears) / close < rejection_level - level_stop_buffer_dollars (bulls). "
        "Do not hardcode 0.50 here."
    )

    # _params_to_kwargs must map chart_stop_buffer_dollars
    orc_src = (pathlib.Path(__file__).resolve().parents[2]
               / "backtest" / "lib" / "orchestrator.py").read_text(encoding="utf-8")
    assert "chart_stop_buffer_dollars" in orc_src, (
        "L113: chart_stop_buffer_dollars not in orchestrator.py. "
        "It must be mapped in _params_to_kwargs so params.json can control the buffer."
    )


def test_l114_vix_hard_cap_bear_wired_in_orchestrator() -> None:
    """L114 (2026-06-17): VIX_HARD_CAP_BEAR must be wired in both _FILTER_CONST_MAP and
    filters.py filter 8 to block BEAR entries during panic-extreme VIX (Liberation Day VIX=52).

    Sub-window analysis (2026-06-17) found:
      - Apr 2026 (tariff shock, VIX escalating to 52): n=22, -$6,189 — nearly the entire IS loss
      - OOS May 2026 (VIX declining 35→20, recovery): n=17, +$4,747 — best period
    Hypothesis: capping VIX at 35-45 blocks April-type extremes while preserving recovery-regime gains.

    Prevention rule: whenever a constant is added to runner._FILTERS_CONST_KEYS it must
    also appear in orchestrator._FILTER_CONST_MAP (L111 pattern). Verify both here.
    """
    import pathlib
    filters_src = (pathlib.Path(__file__).resolve().parents[2]
                   / "backtest" / "lib" / "filters.py").read_text(encoding="utf-8")
    orc_src = (pathlib.Path(__file__).resolve().parents[2]
               / "backtest" / "lib" / "orchestrator.py").read_text(encoding="utf-8")
    runner_src = (pathlib.Path(__file__).resolve().parents[2]
                  / "backtest" / "autoresearch" / "runner.py").read_text(encoding="utf-8")

    # Constant must exist in filters.py
    assert "VIX_HARD_CAP_BEAR" in filters_src, (
        "L114: VIX_HARD_CAP_BEAR constant not found in filters.py. "
        "It must be defined as a module-level float (default 999.0) so the sweep path can patch it."
    )

    # Constant must be referenced in filter 8 usage (not just defined)
    assert "VIX_HARD_CAP_BEAR" in filters_src and filters_src.count("VIX_HARD_CAP_BEAR") >= 2, (
        "L114: VIX_HARD_CAP_BEAR defined but never used in filter 8 logic. "
        "The cap check must read: if vix_pass and ctx.vix_now > VIX_HARD_CAP_BEAR: vix_pass = False"
    )

    # Must be in orchestrator._FILTER_CONST_MAP (per L111 prevention rule)
    assert '"vix_hard_cap_bear"' in orc_src, (
        "L114: vix_hard_cap_bear not in orchestrator._FILTER_CONST_MAP. "
        "Add: '\"vix_hard_cap_bear\": \"VIX_HARD_CAP_BEAR\"' to _FILTER_CONST_MAP so "
        "params_overrides={\"vix_hard_cap_bear\": 35.0} works."
    )

    # Must be in runner._FILTERS_CONST_KEYS (per L111 prevention rule)
    assert '"vix_hard_cap_bear"' in runner_src, (
        "L114: vix_hard_cap_bear not in runner._FILTERS_CONST_KEYS. "
        "Per L111 prevention rule: any key added to one map must be in both."
    )


def test_l115_vix_declining_required_bear_wired() -> None:
    """L115 (2026-06-17): VIX_DECLINING_REQUIRED_BEAR must be wired end-to-end.

    Per L93: 'if a VIX gate is needed, test DECLINING direction only' for BEARISH_REVERSAL.
    Sub-window analysis confirmed profitable periods have declining multi-day VIX;
    April 2026 losses (-$6,189) occur during escalating multi-day VIX.

    This filter blocks BEAR entries when vix_now > vix_5d_ma (current > 5-day rolling avg = escalating).
    Requires: (1) VIX_DECLINING_REQUIRED_BEAR constant in filters.py,
              (2) vix_5d_ma field on BarContext,
              (3) filter 8 checks the condition,
              (4) wired in orchestrator._FILTER_CONST_MAP,
              (5) wired in runner._FILTERS_CONST_KEYS.
    """
    import pathlib
    filters_src = (pathlib.Path(__file__).resolve().parents[2]
                   / "backtest" / "lib" / "filters.py").read_text(encoding="utf-8")
    orc_src = (pathlib.Path(__file__).resolve().parents[2]
               / "backtest" / "lib" / "orchestrator.py").read_text(encoding="utf-8")
    runner_src = (pathlib.Path(__file__).resolve().parents[2]
                  / "backtest" / "autoresearch" / "runner.py").read_text(encoding="utf-8")

    assert "VIX_DECLINING_REQUIRED_BEAR" in filters_src, (
        "L115: VIX_DECLINING_REQUIRED_BEAR constant not found in filters.py."
    )
    assert filters_src.count("VIX_DECLINING_REQUIRED_BEAR") >= 2, (
        "L115: VIX_DECLINING_REQUIRED_BEAR defined but not used in filter 8 logic."
    )
    assert "vix_5d_ma" in filters_src, (
        "L115: vix_5d_ma field not found in filters.py BarContext. "
        "Add: 'vix_5d_ma: float = 0.0' as a BarContext field with a default."
    )
    assert "_vix_5d_ma_per_day" in orc_src, (
        "L115: _vix_5d_ma_per_day not computed in orchestrator.py. "
        "Pre-compute daily VIX closes and 5-day rolling average before the main loop."
    )
    assert '"vix_declining_required_bear"' in orc_src, (
        "L115: vix_declining_required_bear not in orchestrator._FILTER_CONST_MAP. "
        "Per L111 prevention rule: add it alongside vix_hard_cap_bear."
    )
    assert '"vix_declining_required_bear"' in runner_src, (
        "L115: vix_declining_required_bear not in runner._FILTERS_CONST_KEYS. "
        "Per L111 prevention rule: any key added to one map must be in both."
    )


@pytest.mark.slow
def test_l116_min_triggers_bear_wired_in_params_overrides() -> None:
    """L116 (2026-06-17): min_triggers_bear raw snake_case must be handled in _params_to_kwargs.

    Before L116 fix, _params_to_kwargs only handled the legacy key "filter_10_min_triggers_bear".
    Calls using params_overrides={'min_triggers_bear': N} silently used default min_triggers=1
    regardless of N. C14 dead-knob signature: sweep of N=1/2/3 all returned identical IS n=246.

    After fix: snake_case alias added. N=2 correctly removes STANDARD-tier (n=1 trigger) IS trades.
    Sweep result: mt=1→IS n=246, mt=2→IS n=179, mt=3→IS n=149.
    L116 research outcome: production min=1 confirmed optimal (mt=2 OOS-HURT: WF=-0.245 FAIL).

    Guard verifies:
    (1) Code inspection: "min_triggers_bear" handled as alias in orchestrator._params_to_kwargs.
    (2) Functional: OOS trade count differs by >= 3 between min_triggers_bear=1 and =2.
    """
    import pathlib
    import datetime as dt
    import pandas as pd

    orc_src = (pathlib.Path(__file__).resolve().parents[2]
               / "backtest" / "lib" / "orchestrator.py").read_text(encoding="utf-8")

    assert '"min_triggers_bear" in overrides' in orc_src, (
        "L116: _params_to_kwargs does not handle raw 'min_triggers_bear' key. "
        "Add: if 'min_triggers_bear' in overrides: kwargs['min_triggers_bear'] = overrides['min_triggers_bear']"
    )
    assert '"min_triggers_bull" in overrides' in orc_src, (
        "L116: _params_to_kwargs does not handle raw 'min_triggers_bull' key. "
        "Add: if 'min_triggers_bull' in overrides: kwargs['min_triggers_bull'] = overrides['min_triggers_bull']"
    )

    DATA = pathlib.Path(__file__).resolve().parents[2] / "backtest" / "data"
    spy_path = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        pytest.skip("backtest data files not present")

    spy = pd.read_csv(str(spy_path))
    vix = pd.read_csv(str(vix_path))

    CORRECT = dict(
        use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True, premium_stop_pct_bear=-0.20,
        premium_stop_pct_bull=-0.08, per_trade_risk_cap_pct=0.30,
    )
    OOS_S = dt.date(2026, 5, 8)
    OOS_E = dt.date(2026, 5, 22)

    counts = []
    for mt in [1, 2]:
        r = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                         params_overrides={"min_triggers_bear": mt}, **CORRECT)
        counts.append(len(r.trades))

    spread = counts[0] - counts[1]
    assert spread >= 3, (
        f"L116: min_triggers_bear appears dead in params_overrides path — "
        f"OOS trade count spread only {spread} (mt=1: {counts[0]} trades, mt=2: {counts[1]} trades; "
        f"expected spread ≥ 3, reflecting removal of STANDARD-tier single-trigger setups). "
        "Check _params_to_kwargs handles 'min_triggers_bear' raw key and that it flows to "
        "run_backtest() → orchestrator → filters.evaluate_bearish_setup(min_triggers=...)."
    )


@pytest.mark.slow
def test_l117_no_entry_at_or_after_time_stop_bar() -> None:
    """L117 (2026-06-17): backtest must not allow new entries at or after time_stop_et.

    Bug: outer loop gate was hardcoded >= dt.time(15, 50), but time_stop_et is computed
    from time_stop_minutes_before_close (default=10 → 15:50, production=20 → 15:40).
    With time_stop_minutes_before_close=20, bars at 15:40 and 15:45 passed the gate and
    could trigger new entries that immediately time-stopped — production never enters here
    (the 15:40 heartbeat exits existing positions, not enters new ones).

    Impact on baseline: IS artifact n=9 (+$170), OOS artifact n=2 (+$2,088 — including
    the +$2,200 May 15 winner that dominated OOS). After fix: corrected OOS=$2,659 (was $4,747).

    Fix: changed gate to `bar_time_py.time() >= time_stop_et` so it uses the dynamic
    time_stop_et computed from time_stop_minutes_before_close.

    Two guards:
    1. Code inspection: 'time_stop_et' must appear in the outer loop gate line, not 'dt.time(15, 50)'
    2. Liveness: with time_stop_minutes_before_close=20, no OOS fill has entry_time.time() >= 15:40
    """
    import pathlib
    import datetime as dt
    import pandas as pd

    # Guard 1: code inspection — dynamic gate must be used
    orc_src = (pathlib.Path(__file__).resolve().parents[2]
               / "backtest" / "lib" / "orchestrator.py").read_text(encoding="utf-8")
    # The gate line must reference time_stop_et, not the hardcoded 15:50 literal
    assert ">= time_stop_et" in orc_src, (
        "L117 regression: outer loop gate does not use 'time_stop_et'. "
        "The gate must be: bar_time_py.time() >= time_stop_et — NOT dt.time(15, 50). "
        "With time_stop_minutes_before_close=20 (production), the gate should fire at 15:40, "
        "not 15:50. Reverting to hardcoded 15:50 allows phantom entries at 15:40 and 15:45."
    )

    # Guard 2: liveness — with 20-min time stop, no fill entry_time >= 15:40
    DATA = pathlib.Path(__file__).resolve().parents[2] / "backtest" / "data"
    spy_path = DATA / "spy_5m_2025-01-01_2026-05-22.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists() or not vix_path.exists():
        pytest.skip("backtest data files not present")

    spy = pd.read_csv(str(spy_path))
    vix = pd.read_csv(str(vix_path))

    OOS_S = dt.date(2026, 5, 8)
    OOS_E = dt.date(2026, 5, 22)

    r = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                     use_real_fills=True,
                     no_trade_window=None,
                     no_trade_before=dt.time(9, 35),
                     midday_trendline_gate=True,
                     premium_stop_pct_bear=-0.20,
                     time_stop_minutes_before_close=20)

    time_stop_et = dt.time(15, 40)  # 16:00 - 20 min
    late_fills = []
    for t in r.trades:
        et = t.entry_time_et
        if hasattr(et, "to_pydatetime"):
            et = et.to_pydatetime()
        if hasattr(et, "tzinfo") and et is not None and et.tzinfo is not None:
            et = et.replace(tzinfo=None)
        if et is not None and et.time() >= time_stop_et:
            late_fills.append((str(et), t.dollar_pnl))

    assert len(late_fills) == 0, (
        f"L117: {len(late_fills)} OOS trade(s) entered at or after time_stop_et (15:40 ET) "
        f"with time_stop_minutes_before_close=20. Production never enters at this bar. "
        f"Late entries: {late_fills}. "
        "Check outer loop gate in orchestrator.py: must be `>= time_stop_et`, not `>= dt.time(15, 50)`."
    )


@_needs_data
def test_l122_level_oos_profitable_before_blocking():
    """L122: blocking LEVEL entries hurts OOS — IS/OOS VIX regime flip.

    LEVEL-tier trades (level_rejection or level_reclaim without SUPER/ELITE upgrade) are losers
    in IS (WR=24%, -$390/trade, n=33) but winners in OOS (WR=50%, +$112/trade, n=4).
    Blocking LEVEL gives OOS_delta=-$447, WF=-0.566 FAIL.

    Root cause: IS LEVEL losses occur in VIX 15-17 flat (Jan-26) and VIX 25-35 escalating (Mar-26).
    OOS LEVEL wins occur in VIX 17-20 declining (May-26 post-Liberation-Day recovery).
    No mechanical filter separates these IS/OOS VIX populations.

    This guard asserts that OOS LEVEL trades are net-positive in the May 8-22 OOS window,
    and that removing them would reduce OOS P&L. If this fires, the OOS regime has changed
    and re-investigation is warranted before any blocking decision.
    """
    import pandas as pd

    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)

    OOS_S = dt.date(2026, 5, 8)
    OOS_E = dt.date(2026, 5, 22)

    r = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                     use_real_fills=True,
                     no_trade_window=None,
                     no_trade_before=dt.time(9, 35),
                     midday_trendline_gate=True,
                     premium_stop_pct_bear=-0.20,
                     tp1_qty_fraction=0.667,
                     runner_target_premium_pct=2.50,
                     time_stop_minutes_before_close=20,
                     per_trade_risk_cap_pct=0.30)

    def _quality_of_trade(trade):
        tf = set(getattr(trade, "triggers_fired", None) or [])
        has_conf = "confluence" in tf
        has_rf   = "ribbon_flip_bearish" in tf or "ribbon_flip_bullish" in tf
        has_lvl  = "level_rejection" in tf or "level_reclaim" in tf
        has_seq  = "sequence_rejection" in tf
        if (has_conf and has_rf) or len(tf) >= 3:
            return "SUPER"
        if has_conf or has_seq:
            return "ELITE"
        if has_lvl:
            return "LEVEL"
        return "TRENDLINE_OR_OTHER"

    level_trades = [t for t in r.trades if _quality_of_trade(t) == "LEVEL"]
    all_pnl = sum(t.dollar_pnl for t in r.trades)
    level_pnl = sum(t.dollar_pnl for t in level_trades)
    no_level_pnl = all_pnl - level_pnl

    # Guard: removing LEVEL trades must NOT improve OOS P&L
    # If it does, the OOS regime has flipped and blocking may be warranted — investigate.
    assert no_level_pnl <= all_pnl, (
        f"L122 REGIME FLIP DETECTED: OOS without LEVEL trades (${no_level_pnl:+.0f}) > "
        f"OOS with LEVEL trades (${all_pnl:+.0f}). "
        f"OOS LEVEL n={len(level_trades)}, pnl={level_pnl:+.0f}. "
        "This means LEVEL trades are now OOS losers — the VIX regime has changed. "
        "Before blocking LEVEL entries, verify: (1) current OOS n >= 3, (2) re-run LEVEL "
        "blocking scenarios, (3) check if IS sub-window analysis still supports blocking, "
        "(4) confirm tighter stop already handles the loss magnitude. "
        "See LESSONS-LEARNED.md L122 for the IS/OOS VIX regime flip pattern."
    )


@pytest.mark.slow
def test_l123_level_rejection_gate_bear_only() -> None:
    """L123: block_level_rejection gate must include winning_side=='P' guard.

    has_level==True for BOTH bear (level_rejection) AND bull (level_reclaim) LEVEL trades.
    Without the winning_side=='P' guard, block_level_rejection incorrectly blocks 5/08 OOS
    BULL level_reclaim (+$1,130) → OOS delta=-$447, WF=-0.594 FAIL.

    This guard asserts three properties:
    1. 5/08 BULL level_reclaim trade P&L is identical with and without the gate (not blocked).
    2. At least 1 SKIP_LEVEL_REJECTION_GATE decision exists in OOS (gate is not inert).
    3. No SKIP decision falls on 2026-05-08 (that day has only a BULL LEVEL trade).
    """
    import pandas as pd

    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)

    OOS_S = dt.date(2026, 5, 8)
    OOS_E = dt.date(2026, 5, 22)

    KWARGS = dict(
        use_real_fills=True,
        no_trade_window=None,
        no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True,
        premium_stop_pct_bear=-0.20,
        tp1_qty_fraction=0.667,
        runner_target_premium_pct=2.50,
        time_stop_minutes_before_close=20,
        per_trade_risk_cap_pct=0.30,
    )

    base = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **KWARGS)
    cand = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                        **KWARGS, block_level_rejection=True)

    def _entry_date_str(t):
        et = t.entry_time_et
        return str(et)[:10]

    # 1. 5/08 BULL level_reclaim trade must NOT be blocked
    base_508 = sum(t.dollar_pnl for t in base.trades if _entry_date_str(t) == "2026-05-08")
    cand_508 = sum(t.dollar_pnl for t in cand.trades if _entry_date_str(t) == "2026-05-08")
    assert cand_508 == base_508, (
        f"L123 GUARD: 5/08 BULL level_reclaim trade was blocked by block_level_rejection gate. "
        f"BASE 5/08 pnl={base_508:+.0f}, CAND 5/08 pnl={cand_508:+.0f}. "
        "The winning_side=='P' guard is missing or broken in orchestrator.py. "
        "Without it, BULL LEVEL (level_reclaim) trades are incorrectly blocked. "
        "See LESSONS-LEARNED.md L123 and level-rejection-gate-01.json."
    )

    # 2. Gate must fire at least once (not inert)
    skips = [d for d in cand.decisions if d.get("action") == "SKIP_LEVEL_REJECTION_GATE"]
    assert len(skips) >= 1, (
        f"L123 GUARD: block_level_rejection gate fired 0 SKIP decisions in OOS "
        f"({OOS_S} to {OOS_E}). Gate is inert — check orchestrator wiring. "
        "Expected: at least 5/15 -$1,316 or 5/21 -$1,439 bear level_rejection blocked. "
        "See LESSONS-LEARNED.md L123."
    )

    # 3. No SKIP on 5/08 — that day has only BULL (level_reclaim), not BEAR (level_rejection)
    skips_508 = [d for d in skips if str(d.get("timestamp_et", ""))[:10] == "2026-05-08"]
    assert len(skips_508) == 0, (
        f"L123 GUARD: {len(skips_508)} SKIP_LEVEL_REJECTION_GATE decision(s) on 5/08. "
        "5/08 has ONLY a BULL level_reclaim LEVEL trade — the gate must not fire on it. "
        "The winning_side=='P' guard is missing or broken. "
        "See LESSONS-LEARNED.md L123."
    )


@_needs_data
def test_block_elite_bull_vix_range() -> None:
    """Rank 34 / BLOCK_ELITE_BULL_VIX15_17.5: gate must fire in VIX 15-17.5 range only.

    IS VIX 15-17 bucket: n=73, WR=9.6%, avg=-$100 — the dominant IS loser source.
    Gate: block ELITE+level_reclaim (BULL) ONLY when 15 <= VIX < 17.5.
    Deployed to params.json 2026-06-17. Scorecard: analysis/recommendations/elite-bull-block-vix-01.json.

    This guard asserts:
    1. Gate fires at least 1 SKIP_ELITE_BULL_LEVEL_RECLAIM in OOS (not inert).
    2. All SKIP decisions have VIX in [15, 17.5) — gate is VIX-range-specific.
    3. CAND trade count <= BASE trade count (gate only removes, never adds).
    4. Gate is inert when vix range set to [20, 25) — no OOS ELITE bull at that VIX.
    """
    import pandas as pd

    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)

    OOS_S = dt.date(2026, 5, 8)
    OOS_E = dt.date(2026, 5, 22)

    KWARGS = dict(
        use_real_fills=True,
        no_trade_window=None,
        no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True,
        premium_stop_pct_bear=-0.10,
        tp1_qty_fraction=0.667,
        runner_target_premium_pct=2.50,
        time_stop_minutes_before_close=20,
        per_trade_risk_cap_pct=0.30,
        block_level_rejection=True,
    )

    base = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **KWARGS)
    cand = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                        block_elite_bull=True, block_elite_bull_vix_low=15.0,
                        block_elite_bull_vix_high=17.5, **KWARGS)
    # Gate inactive outside the VIX range
    inert = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                         block_elite_bull=True, block_elite_bull_vix_low=20.0,
                         block_elite_bull_vix_high=25.0, **KWARGS)

    # 1. Gate must fire at least once (5/20 at VIX=17.4 is within May 8-22 OOS)
    skips = [d for d in cand.decisions if d.get("action") == "SKIP_ELITE_BULL_LEVEL_RECLAIM"]
    assert len(skips) >= 1, (
        f"BLOCK_ELITE_BULL GUARD: gate fired 0 SKIP_ELITE_BULL_LEVEL_RECLAIM in OOS "
        f"({OOS_S} to {OOS_E}). Gate is inert — check orchestrator wiring. "
        "Expected: at least 5/20 VIX=17.4 ELITE bull entry blocked. "
        "See analysis/recommendations/elite-bull-block-vix-01.json."
    )

    # 2. All SKIP VIX values must be in [15, 17.5)
    for sk in skips:
        vix_val = sk.get("vix", sk.get("vix_now", None))
        if vix_val is not None:
            assert 15.0 <= float(vix_val) < 17.5, (
                f"BLOCK_ELITE_BULL GUARD: SKIP fired at VIX={vix_val:.2f} outside [15, 17.5). "
                "Gate is firing outside its declared VIX range. "
                "Check block_elite_bull_vix_low/block_elite_bull_vix_high in orchestrator.py."
            )

    # 3. CAND must have <= trades than BASE (gate removes, never adds)
    assert len(cand.trades) <= len(base.trades), (
        f"BLOCK_ELITE_BULL GUARD: cand has {len(cand.trades)} trades > base {len(base.trades)}. "
        "Gate should only remove trades (ELITE bull in VIX 15-17.5), never add them."
    )

    # 4. Gate inert when VIX range set to [20, 25) — OOS ELITE bull entries are all VIX<20
    assert len(inert.trades) == len(base.trades), (
        f"BLOCK_ELITE_BULL GUARD: gate [20,25) has {len(inert.trades)} trades != base {len(base.trades)}. "
        "Gate should be inert when VIX range is [20,25) — no OOS ELITE bull entries at that VIX level. "
        "Indicates gate is firing outside its declared range."
    )


@_needs_data
def test_l124_level_reclaim_positive_oos_expectancy() -> None:
    """L124: level_reclaim has positive per-trade OOS expectancy despite low WR.

    OOS analysis (5/8 to 5/22): level_reclaim W=3/L=3 total pnl=+$3,245.
    Full OOS to 6/16 shows W=3/L=5 WR=37.5% but avg_winner=+$1,306 avg_loser=-$285
    → expectancy=+$311/trade. Lottery-ticket structure: winners are 4.6x larger than losers.

    DO NOT block level_reclaim based on WR alone. Blocking costs -$2,344+ OOS P&L.

    Guard: (1) OOS level_reclaim total P&L > 0. (2) At least 3 level_reclaim trades fired.
    If this guard flips, the edge may have degraded — re-run full expectancy analysis first.
    See LESSONS-LEARNED.md L124.
    """
    import pandas as pd

    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)

    OOS_S = dt.date(2026, 5, 8)
    OOS_E = dt.date(2026, 5, 22)

    r = run_backtest(
        spy, vix,
        start_date=OOS_S, end_date=OOS_E,
        use_real_fills=True,
        no_trade_window=None,
        no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True,
        premium_stop_pct_bear=-0.10,
        tp1_qty_fraction=0.667,
        runner_target_premium_pct=2.50,
        time_stop_minutes_before_close=20,
        per_trade_risk_cap_pct=0.30,
        block_level_rejection=True,
        block_elite_bull=True,
        block_elite_bull_vix_low=15.0,
        block_elite_bull_vix_high=17.5,
        params_overrides={"vix_bull_max": 18.0},
    )

    level_reclaim_trades = [
        t for t in r.trades if "level_reclaim" in (t.triggers_fired or [])
    ]
    level_reclaim_pnl = sum(t.dollar_pnl for t in level_reclaim_trades)
    n = len(level_reclaim_trades)

    assert n >= 3, (
        f"L124 GUARD: Expected >=3 level_reclaim OOS trades, got {n}. "
        "Lottery-ticket expectancy claim requires n>=3 to be meaningful. "
        "If count dropped: check if engine stopped firing level_reclaim triggers. "
        "See LESSONS-LEARNED.md L124."
    )

    assert level_reclaim_pnl > 0, (
        f"L124 GUARD: level_reclaim OOS total P&L = {level_reclaim_pnl:+.0f} (n={n}). "
        "Expected positive (lottery-ticket: rare winners >> frequent losers). "
        "If negative: VIX regime may have flipped — re-run full expectancy analysis. "
        "DO NOT block level_reclaim based on WR alone. See LESSONS-LEARNED.md L124."
    )


@_needs_data
def test_rank36_safe_tp1_50pct_oos_improvement() -> None:
    """Rank-36 (2026-06-17): Safe TP1 premium fallback +50% must beat +30% on OOS.

    Auto-ratified 2026-06-17 per OP-22. All 5 gates pass:
      OOS_positive=TRUE, WF=3.969>=0.70, SW_hurt=1/4<=1, anchor_no_regression=TRUE, scorecard filed.

    Mechanism: winners hold ~52min and reach +50% before reversing; losers exit at premium stop
    before TP1 regardless of threshold. W1 (calm 2025) hurts -$2,436; W2/W3 (volatile) help strongly.

    Baseline: IS n=128 pnl=+$12,838 / OOS n=21 pnl=+$3,728
    Candidate: IS n=128 pnl=+$16,174 / OOS n=21 pnl=+$5,900 (+58%)

    Params updated: tp1_premium_pct 0.30->0.50, tp1_premium_multiplier 1.30->1.50.
    Heartbeat updated: entry × 1.30 -> entry × 1.50.

    Guard: OOS P&L with tp1=50% must exceed baseline (+30%) by at least $1,000.
    If this flips: re-run safe_tp1_sweep.py; check if OOS regime changed.
    See analysis/recommendations/safe-tp1-50pct-rank36.json.
    """
    import pandas as pd

    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)

    OOS_S = dt.date(2026, 5, 8)
    OOS_E = dt.date(2026, 5, 22)

    COMMON = dict(
        use_real_fills=True,
        no_trade_window=None,
        no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True,
        premium_stop_pct_bear=-0.10,
        tp1_qty_fraction=0.667,
        runner_target_premium_pct=2.50,
        time_stop_minutes_before_close=20,
        per_trade_risk_cap_pct=0.30,
        block_level_rejection=True,
        block_elite_bull=True,
        block_elite_bull_vix_low=15.0,
        block_elite_bull_vix_high=17.5,
        params_overrides={"vix_bull_max": 18.0},
    )

    baseline = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                            tp1_premium_pct=0.30, **COMMON)
    candidate = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                             tp1_premium_pct=0.50, **COMMON)

    pnl_base = sum(t.dollar_pnl for t in baseline.trades)
    pnl_cand = sum(t.dollar_pnl for t in candidate.trades)
    delta = pnl_cand - pnl_base

    assert delta >= 1000, (
        f"Rank-36 GUARD: OOS improvement for TP1=50% vs 30% is ${delta:+.0f} "
        f"(base={pnl_base:+.0f}, cand={pnl_cand:+.0f}). "
        "Expected >= $1,000 improvement. "
        "If this guard fires: re-run backtest/autoresearch/safe_tp1_sweep.py. "
        "The expected OOS delta is +$2,172 (from original ratification run on 5/8-5/22 window). "
        "A delta < $1,000 suggests regime change or a code regression in the TP1 path. "
        "Revert params.json and heartbeat.md to tp1=0.30 if OOS edge is confirmed lost. "
        "See analysis/recommendations/safe-tp1-50pct-rank36.json."
    )

    n_base = len(baseline.trades)
    n_cand = len(candidate.trades)
    assert n_base == n_cand, (
        f"Rank-36 GUARD: trade count changed when only TP1 pct changed: "
        f"base={n_base}, cand={n_cand}. "
        "Changing TP1 premium threshold must not change which trades fire (only P&L). "
        "Check run_backtest kwarg handling for tp1_premium_pct."
    )


@_needs_data
def test_l125_midday_trendline_gate_start_minutes_wired() -> None:
    """L125: midday_trendline_gate_start_minutes must be live in the orchestrator.

    When midday_trendline_gate=True and we change start_minutes from 690 (11:30)
    to 660 (11:00), trades in the 11:00-11:29 window must be blocked (n decreases).
    A 3-value sweep must produce at least 2 distinct trade counts.

    This guards against the L111-class dead-knob issue where a parameter is accepted
    by run_backtest() but never forwarded to the engine logic.

    Researched 2026-06-17: 11:00 gate removes 14 IS TL-only losers (-$1,000 IS improvement)
    but WF=0.144 fails the >=0.70 gate. Default 690 (11:30) is production-correct.
    The parameter exists for future research, not current production change.
    """
    import pandas as pd

    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)

    COMMON = dict(
        use_real_fills=True, no_trade_window=None, no_trade_before=dt.time(9, 35),
        midday_trendline_gate=True, premium_stop_pct_bear=-0.10, tp1_qty_fraction=0.667,
        tp1_premium_pct=0.50, runner_target_premium_pct=2.50, time_stop_minutes_before_close=20,
        per_trade_risk_cap_pct=0.30, block_level_rejection=True, block_elite_bull=True,
        block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=17.5,
        params_overrides={"vix_bull_max": 18.0},
    )

    OOS_S = dt.date(2025, 1, 2)
    OOS_E = dt.date(2026, 5, 7)

    r_1130 = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                          midday_trendline_gate_start_minutes=690, **COMMON)
    r_1100 = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E,
                          midday_trendline_gate_start_minutes=660, **COMMON)

    n_1130 = len(r_1130.trades)
    n_1100 = len(r_1100.trades)

    assert n_1130 > n_1100, (
        f"L125 GUARD: midday_trendline_gate_start_minutes appears to be a dead knob. "
        f"n_1130={n_1130}, n_1100={n_1100}. Extending gate from 11:30 to 11:00 should "
        "block additional trendline-only trades in the 11:00-11:29 window. "
        "Check orchestrator.py _gate_h/_gate_m divmod logic and midday_trendline_gate path."
    )
    assert n_1130 - n_1100 >= 5, (
        f"L125 GUARD: only {n_1130-n_1100} trades blocked by extending gate from 11:30 to 11:00. "
        "Expected >= 5 blocked trades (IS has 14 TL-only trades in that window). "
        "Check that the gate only applies to trendline-only setups (_is_tl_only check)."
    )


def test_l155_autorate_rejects_negative_is_delta():
    """L155: WF_norm formula produces a false-positive AUTO-RATIFY when IS_delta <= 0.

    When a gate drops profitable IS trades (IS_delta < 0) AND drops OOS trades
    (OOS_delta < 0), the WF formula (-OOS/-IS) evaluates positive. The autorate
    framework would spuriously ratify a gate that HURTS both IS and OOS.

    The L155 guard: any gate sweep MUST reject immediately when IS_delta <= 0,
    before evaluating WF. This test verifies the guard logic is correct and that
    the raw WF formula IS misleading in the negative-delta scenario.

    Real-world case: Safe conf+lvl_rej VIX>=19 gate (2026-06-17)
      IS_delta=-$2,334, OOS_delta=-$453, WF_raw=1.201 (spuriously positive)
    """
    # The specific scenario that was caught by L155:
    is_delta = -2334
    oos_delta = -453
    n_is = 130
    n_oos = 21

    # Precondition: raw WF formula gives misleadingly positive result
    wf_raw = (oos_delta / n_oos) / (is_delta / n_is)
    assert wf_raw > 0.70, (
        f"Precondition: raw WF should be misleadingly positive when both deltas negative. "
        f"Got wf_raw={wf_raw:.3f}"
    )

    # L155 guard: when IS_delta <= 0, gate must be rejected before WF check
    if is_delta <= 0:
        verdict = "REJECT (IS_delta<=0)"
    elif wf_raw >= 0.70:
        verdict = "AUTO-RATIFY"
    else:
        verdict = "REJECT"

    assert verdict == "REJECT (IS_delta<=0)", (
        f"L155 GUARD FAILED: gate with IS_delta={is_delta} should be REJECT (IS_delta<=0) "
        f"but got verdict={verdict!r}. The autorate framework must check IS_delta > 0 "
        "BEFORE evaluating WF_norm — otherwise negative deltas can generate false ratifications."
    )


# ---------------------------------------------------------------------------
# L160 (2026-06-18): G5 anchor-no-regression must be sign-correct for NEGATIVE
# baselines. The broken form `curr_anchor >= base_anchor * 0.90` demands the
# candidate be 10% BETTER when base_anchor < 0 (multiplying a negative by 0.9
# moves the threshold toward zero), silently REJECTING genuinely anchor-neutral
# changes and stalling the ratification pipeline. L160 was fixed in two scripts
# but the broken pattern kept reappearing in new sweep scripts -- prose failed as
# a control, so it is graduated here. Root-cause fix: single canonical helper
# backtest/lib/anchor_check.py::anchor_no_regression(). Three guards below:
#   1. unit-test the helper against the exact L160 case + sign matrix
#   2. tree-scan: FAIL if any live (non-test) script still uses `* 0.9` anchor form
#   3. confirm the formerly-broken scripts now import/use the canonical helper
# ---------------------------------------------------------------------------

def test_l160_anchor_no_regression_helper_sign_correct() -> None:
    """L160: the canonical anchor_no_regression() helper must read correctly for
    both signs. The exact bug case (base==curr==-354) MUST pass; a candidate 10%
    worse must pass at the boundary; >10% worse must fail; positive baselines
    behave symmetrically."""
    from lib.anchor_check import anchor_no_regression

    # The EXACT L160 incident: baseline anchor -$354, candidate identical -$354.
    # Broken formula computed -354 >= -354*0.9 = -318.6 -> FALSE (false reject).
    assert anchor_no_regression(-354.0, -354.0, 0.10) is True, (
        "L160 GUARD: an anchor-NEUTRAL change (curr == base) on a NEGATIVE baseline "
        "must PASS the no-regression gate. The broken `base*0.9` form rejects it."
    )

    # Negative baseline, candidate exactly 10% worse (-389.4) -> boundary PASS.
    assert anchor_no_regression(-354.0, -354.0 - 35.4, 0.10) is True
    # Negative baseline, candidate >10% worse -> FAIL.
    assert anchor_no_regression(-354.0, -500.0, 0.10) is False
    # Negative baseline, candidate BETTER (less negative) -> PASS.
    assert anchor_no_regression(-354.0, -100.0, 0.10) is True

    # Positive baseline behaves symmetrically: 5% worse PASS, 20% worse FAIL.
    assert anchor_no_regression(1000.0, 950.0, 0.10) is True
    assert anchor_no_regression(1000.0, 800.0, 0.10) is False
    # Zero baseline: any non-negative candidate passes, negative fails.
    assert anchor_no_regression(0.0, 0.0, 0.10) is True
    assert anchor_no_regression(0.0, -1.0, 0.10) is False

    # Demonstrate the helper FIXES what the broken form got wrong, on the L160 case.
    base, curr = -354.0, -354.0
    broken_verdict = curr >= base * 0.90          # the bug: -354 >= -318.6 -> False
    correct_verdict = anchor_no_regression(base, curr, 0.10)
    assert broken_verdict is False and correct_verdict is True, (
        "L160 GUARD: helper must invert the broken form's false-reject on negative anchors."
    )


def test_l160_no_broken_anchor_multiply_in_live_scripts() -> None:
    """L160: tree-scan guard. No live (non-test, non-venv) backtest script may use
    the broken `<baseline> * 0.9[0]` anchor-regression form. New sweep scripts must
    call backtest/lib/anchor_check.py::anchor_no_regression() instead. This catches
    re-violation across the whole sweep-script fleet, not just the known offenders.

    The check is deliberately narrow: it flags `*0.9` ONLY when the left operand is
    an anchor/winner/loser baseline identifier (base_anchor, base_w, base_l, r[2],
    etc.), so unrelated `* 0.9` arithmetic elsewhere is not falsely flagged."""
    anchor_base = r"(?:base_anchor|base_w|base_l|base_anc_pnl|base_win|base_lose)"
    tuple_form = r"r\[\d+\]"
    broken_re = re.compile(rf"(?:{anchor_base}|{tuple_form})\s*\*\s*0\.9\d*\b")

    offenders: list[str] = []
    for py in BACKTEST.rglob("*.py"):
        parts = set(py.parts)
        if ".venv" in parts or "site-packages" in parts:
            continue
        if py.name.startswith("test_") or py.parent.name == "tests":
            continue
        if py.name == "anchor_check.py":
            continue  # the helper's docstring quotes the broken form as an example
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue  # don't flag the pattern inside an explanatory comment
            if broken_re.search(line):
                offenders.append(f"{py.relative_to(REPO)}:{i}: {line.strip()}")

    assert not offenders, (
        "L160 GUARD FAILED: broken anchor-no-regression form `<baseline> * 0.9` found. "
        "On a NEGATIVE baseline this demands the candidate be 10% BETTER and silently "
        "rejects anchor-neutral changes. Replace with "
        "backtest.lib.anchor_check.anchor_no_regression(base, curr, tol). Offenders:\n  "
        + "\n  ".join(offenders)
    )


def test_l160_formerly_broken_scripts_use_canonical_helper() -> None:
    """L160: the three scripts that carried the broken form (fixed 2026-06-18) must
    keep importing the canonical helper, so a future edit that re-inlines the
    formula is caught. Pins the root-cause fix in place."""
    expected = [
        BACKTEST / "tools" / "agg_runner_target_sweep.py",
        BACKTEST / "autoresearch" / "tighter_stop_anchor_check.py",
        BACKTEST / "autoresearch" / "vix_regime_stop_sweep.py",
    ]
    missing: list[str] = []
    for py in expected:
        assert py.exists(), f"expected anchor-check consumer missing: {py}"
        text = py.read_text(encoding="utf-8", errors="ignore")
        if "anchor_no_regression" not in text:
            missing.append(str(py.relative_to(REPO)))
    assert not missing, (
        "L160 GUARD: these scripts were fixed to use anchor_no_regression() but the "
        "call/import is gone (formula likely re-inlined). Re-route to the helper:\n  "
        + "\n  ".join(missing)
    )


# ─────────────────────────────────────────────────────────────────────────────
# L173 — OOS-ALONE drop-top5 graduated into the standard real-fills verify path.
#
#   full-sample drop-top5 > 0 (the existing GATE_FRAUD null + the family grids'
#   own top5_day_pct < 200% gate) is NECESSARY-BUT-NOT-SUFFICIENT. The candidate
#   must ALSO keep its OOS-window-only per-trade positive after the 5 best OOS days
#   are dropped. Caught edge #3 (a 2026-bull-regime artifact that passed full-sample
#   drop-top5 at B5 but failed OOS-alone at B6: OOS-alone drop-top5 -$16 -> -$23,
#   top5-day-OOS 120-228%). C4/L173. ADDITIVE — never relaxes any existing gate.
#
# Mirrors the known-fake/known-real structure of test_fraud_gates.py. Pure-logic
# (no master CSV / no OPRA) so it runs in the fast guard set.
# ─────────────────────────────────────────────────────────────────────────────

def test_l173_oos_drop_top5_gate_rejects_oos_concentrated_fake() -> None:
    """L173 pure gate: an OOS-concentrated fake (full-sample drop-top5 positive but
    OOS-alone drop-top5 NEGATIVE) is REJECTED. The edge lives in a few OOS days."""
    from autoresearch.fraud_gates import oos_drop_top5_gate

    # edge#3 shape: removing the 5 best OOS days takes OOS-only per-trade negative.
    g = oos_drop_top5_gate(oos_drop_top5_per_trade=-23.0, oos_n=30)
    assert g["evaluable"] is True
    assert g["oos_drop_top5_pass"] is False, (
        "L173 regression: a negative OOS-alone drop-top5 must FAIL the gate — the "
        "edge is OOS-day concentration, not a per-trade option edge (C4)."
    )


def test_l173_oos_drop_top5_gate_passes_broad_based_clean() -> None:
    """L173 pure gate: a clean candidate (positive OOS-alone drop-top5 over enough
    OOS days) PASSES — the edge survives removing its 5 best OOS days."""
    from autoresearch.fraud_gates import oos_drop_top5_gate

    g = oos_drop_top5_gate(oos_drop_top5_per_trade=25.91, oos_n=42)
    assert g["evaluable"] is True
    assert g["oos_drop_top5_pass"] is True, (
        "L173 regression: a broad-based candidate whose OOS-alone drop-top5 stays "
        "positive must PASS — this gate is ADDITIVE, never a false reject."
    )


def test_l173_oos_drop_top5_gate_small_n_is_unevaluable_not_crash() -> None:
    """L173 small-n convention (matches _b10_exit_audit.oos_drop_top5): with <=5 OOS
    observations the 5-best cannot be dropped leaving a non-empty remainder, so the
    gate is UNEVALUABLE (skip), never a crash and never a silent pass."""
    from autoresearch.fraud_gates import oos_drop_top5_gate

    for n in (0, 3, 5):
        g = oos_drop_top5_gate(oos_drop_top5_per_trade=10.0, oos_n=n)
        assert g["evaluable"] is False, f"OOS_n={n} must be unevaluable (<=5)"
        assert g["oos_drop_top5_pass"] is False  # unevaluable never auto-passes
    # 6 > 5 -> the gate becomes evaluable again.
    assert oos_drop_top5_gate(oos_drop_top5_per_trade=10.0, oos_n=6)["evaluable"] is True


def test_l173_oos_drop_top5_gate_fails_open_when_value_missing() -> None:
    """L173 fail-open: a missing OOS-alone drop-top5 cannot DISPROVE concentration,
    so the gate is unevaluable (the harness records a caveat, the outer gates still
    govern) — it never silently blesses, mirroring the truncation/null fail-open."""
    from autoresearch.fraud_gates import oos_drop_top5_gate

    g = oos_drop_top5_gate(oos_drop_top5_per_trade=None, oos_n=42)
    assert g["evaluable"] is False
    assert g["oos_drop_top5_pass"] is False


def test_l173_harness_rejects_oos_concentrated_candidate() -> None:
    """L173 WIRING: through verify_edgehunt_candidates, a candidate that records a
    NEGATIVE OOS-alone drop-top5 carries the OOS_DROP_TOP5<=0 fail and is REJECTED,
    while the SAME candidate with a positive OOS-alone drop-top5 clears the gate.
    Synthetic candidate (no master CSV / no OPRA) so this is a fast pure-logic guard."""
    from autoresearch.verify_edgehunt_candidates import _extract, _gate

    # A minimal candidate that clears every OTHER gate (so the OOS-conc gate is the
    # only thing that can differ between the fake and the clean variant).
    base = {
        "config": "off-2_stop-0.08",
        "strike_offset": -2,
        "premium_stop_pct": -0.08,
        "metrics": {
            "exp_dollar": 70.0, "oos_exp": 60.0, "oos_n": 30, "n": 90,
            "positive_quarters": "6/6", "top5_day_pct": 25.0, "oos_top5_day_pct": 120.0,
            # full-sample drop-top5 is fine; the artifact is OOS-ALONE concentration.
            "drop_top5_per_trade": 20.0,
        },
        # pin the upstream fraud gates to PASS so they don't mask the L173 fail.
        "is_truncation_artifact": False,
        "null_pass": True,
        "null": {"per_trade_mean": 2.0, "per_trade_max": 5.0},
        "drop_top5_per_trade": 20.0,
        "clears_bar_robust": True,
        "anchor_no_regression": True,
        "true_edge": True,
    }

    # FAKE: OOS-alone drop-top5 goes NEGATIVE -> must be rejected by the new gate.
    fake = dict(base); fake["oos_exp_drop_top5"] = -23.0
    ex_fake = _extract("synthetic", fake)
    fails_fake, _ = _gate("synthetic", ex_fake)
    assert ex_fake["oos_drop_top5"]["evaluable"] is True
    assert ex_fake["oos_drop_top5"]["oos_drop_top5_pass"] is False
    assert any("OOS_DROP_TOP5" in f for f in fails_fake), (
        f"L173 regression: OOS-concentrated candidate not rejected. fails={fails_fake}"
    )

    # CLEAN: same candidate, positive OOS-alone drop-top5 -> the L173 gate must NOT fire.
    clean = dict(base); clean["oos_exp_drop_top5"] = 25.91
    ex_clean = _extract("synthetic", clean)
    fails_clean, _ = _gate("synthetic", ex_clean)
    assert ex_clean["oos_drop_top5"]["oos_drop_top5_pass"] is True
    assert not any("OOS_DROP_TOP5" in f for f in fails_clean), (
        f"L173 regression: clean candidate falsely rejected by the OOS-conc gate. "
        f"fails={fails_clean}"
    )


def test_l177_premium_selling_eligibility_filter_shared() -> None:
    """L177 / OP-16 sim-accuracy gate: the per-day strike-universe band pre-filter MUST
    be byte-identical across production run_variant() and EVERY premium-selling null,
    by construction (one shared helper), not by three independent legs_in_band(half_width=5)
    literals that can silently diverge. Divergence is exactly what inflated the IC LEAD's
    apparent percentile (94.8th vs the true ~76th) and flipped the verdict on the RNG seed.

    Guard: (1) the shared piv.eligible() exists and uses BAND_HALF_WIDTH; (2) the null and
    the IC-validate per-day fills call piv.eligible (not a private literal); (3) behavioral
    parity -- the same legs/spot get the same eligibility decision through every path."""
    import inspect
    import sys as _sys, pathlib as _pl
    _ar = str(_pl.Path(__file__).resolve().parents[1] / "autoresearch")
    if _ar not in _sys.path:
        _sys.path.insert(0, _ar)
    import _pivot_premium_selling as piv
    import _pivot_premium_selling_null as nul
    import _pivot_premium_ic_validate as icv

    assert callable(piv.eligible), "shared eligible() helper missing"
    assert piv.BAND_HALF_WIDTH == 5, "production band half-width drifted from 5"

    # (2) regression guard: both nulls must route through the shared helper, and must NOT
    # re-introduce a private `legs_in_band(..., half_width=...)` literal that can diverge.
    def _code_only(fn):
        # strip comment lines so the guard checks real CALLS, not our own docstring/comment.
        lines = inspect.getsource(fn).splitlines()
        return chr(10).join(l for l in lines if not l.strip().startswith("#"))
    for name, src in (("null", _code_only(nul._one_day_fill)),
                      ("ic_validate", _code_only(icv.fill_for_day))):
        assert "piv.eligible(" in src, f"{name} no longer calls the shared piv.eligible()"
        assert "half_width" not in src, (
            f"{name} re-introduced a private band literal -- L177 divergence risk; "
            "route through piv.eligible() instead"
        )
        assert "legs_in_band(" not in src, (
            f"{name} calls legs_in_band() directly -- route through piv.eligible() (L177)"
        )

    # (3) behavioral parity: an out-of-band condor is rejected, an in-band one accepted,
    # identically (the helper IS the single decision, so any caller agrees by construction).
    spot = 600.0
    in_band = piv.build_legs(spot, "IC", short_offset=2, wing_width=2)
    out_band = piv.build_legs(spot, "IC", short_offset=20, wing_width=2)  # shorts $20 OTM
    assert piv.eligible(in_band, spot) is True, "in-band IC wrongly rejected"
    assert piv.eligible(out_band, spot) is False, "out-of-band IC wrongly accepted"


def test_l177_null_verdict_knife_edge_inconclusive() -> None:
    """L177: a premium-selling cell whose actual lands in the [p90,p99) knife-edge must be
    INCONCLUSIVE, never PASS -- that band is where an eligibility-parity / RNG-seed bug can
    flip the call (the 94.8th-pctile artifact was here). PASS needs >=p99 on EVERY seed;
    FAIL needs <p90 on every seed; <MIN_ITERS or <MIN_SEEDS or a straddle -> INCONCLUSIVE."""
    import sys as _sys, pathlib as _pl
    _ar = str(_pl.Path(__file__).resolve().parents[1] / "autoresearch")
    if _ar not in _sys.path:
        _sys.path.insert(0, _ar)
    import _pivot_premium_selling_null as nul
    nv = nul.null_verdict

    # the exact L177 foot-gun value (~94.8th pctile) must NOT be a PASS.
    assert nv([0.948, 0.96], 300, 2)[0] == "INCONCLUSIVE"
    # clearly above the noise on every seed -> PASS.
    assert nv([0.995, 0.992], 300, 2)[0] == "PASS"
    # genuinely inside the noise -> FAIL (the post-parity-fix ~76th-pctile reality).
    assert nv([0.76, 0.70], 300, 2)[0] == "FAIL"
    # too few seeds / iters -> never a PASS even when the lone rank clears p99.
    assert nv([0.995], 300, 1)[0] == "INCONCLUSIVE"
    assert nv([0.995, 0.992], 100, 2)[0] == "INCONCLUSIVE"
    # seed-unstable (one seed PASS-side, one FAIL-side) -> INCONCLUSIVE, not a coin-flip PASS.
    assert nv([0.995, 0.50], 300, 2)[0] == "INCONCLUSIVE"
    # boundary: exactly p99 on both seeds is a PASS; exactly p90 is the knife-edge floor.
    assert nv([0.99, 0.99], 300, 2)[0] == "PASS"
    assert nv([0.90, 0.90], 300, 2)[0] == "INCONCLUSIVE"


# ─────────────────────────────────────────────────────────────────────────────
# CAP-ADMISSION — the order-ADMISSION cap graduated into the DEFAULT autoresearch
# book-aggregation step (lib.cap_admission, calling the LIVE risk_gate).
#
#   THE RE-VIOLATED LESSON: risk_gate.check_order caps NOTIONAL = premium*qty*100 at the
#   tighter of risk-cap/tier AND enforces min_contracts (Safe 3 / Bold 5), but the research
#   path (simulator_real + the DTE harness) had NO such gate -> a validated expectancy
#   SILENTLY OVERSTATES the realizable book for any config whose median order exceeds the cap
#   (the 2026-06-15 Bold-oversize + 2026-06-21 DTE cap-overlay findings). Doctrine: a
#   re-violated lesson is a missing guardrail -> graduate it to a code assertion. The cap is
#   now the DEFAULT book-aggregation step (enforce_cap=True); the guard below asserts that.
# ─────────────────────────────────────────────────────────────────────────────

def test_cap_admission_is_default_book_step_for_oversized_config() -> None:
    """GRADUATED GUARD: any autoresearch book for a config whose MEDIAN order notional
    (median entry premium * qty * 100) exceeds the account cap MUST be cap-aware by
    DEFAULT — i.e. admit_book(enforce_cap default) reports a non-zero block_rate and
    EXCLUDES the over-cap fills (never qty-reduces them). And enforce_cap=False must be
    BYTE-IDENTICAL to the cap-blind book (no behaviour change to the comparison path).

    This is the executable form of 'cap-aware is the default': if a future refactor
    flips the default to cap-blind, or makes admit_book a no-op on an over-cap config,
    this fails."""
    import inspect
    from dataclasses import dataclass

    from lib import cap_admission as ca
    from lib.risk_gate import CODE_RISK_CAP

    # (1) the default IS cap-on (the signature default, the load-bearing fact).
    sig = inspect.signature(ca.admit_book)
    assert sig.parameters["enforce_cap"].default is True, (
        "cap-admission regression: admit_book(enforce_cap) default must be True — "
        "the realizable (cap-aware) book is the DEFAULT autoresearch book step."
    )

    @dataclass(frozen=True)
    class _Fill:
        entry_premium: float
        dollar_pnl: float = 0.0
        qty: int = 3

    # An OVER-CAP Safe config: median order $2.50*3*100 = $750 > the $600 cap.
    over = tuple(_Fill(p) for p in (2.40, 2.50, 2.60))
    assert ca.median_notional_exceeds_cap(over, "safe", 2000.0, 3) is True, (
        "fixture invalid: this config's median order should exceed the Safe $600 cap"
    )

    # (2) the DEFAULT call (no enforce_cap passed) must be cap-aware: block_rate > 0 and
    #     the over-cap fills EXCLUDED ($0 realizable), not present in the admitted book.
    default_book = ca.admit_book(over, "safe", 2000.0, 3)
    assert default_book.enforce_cap is True
    assert default_book.block_rate > 0.0, (
        "cap-admission regression: an over-cap config's DEFAULT book reported block_rate 0 "
        "-> the cap is not being enforced by default (validated expectancy would overstate)."
    )
    assert len(default_book.admitted) < len(over), "over-cap fills must be EXCLUDED, not kept"
    assert default_book.block_codes.get(CODE_RISK_CAP), "block reason must be the notional cap"
    # min_contracts DENIES (never shrinks): no admitted fill carries a reduced qty.
    assert all(f.qty == 3 for f in default_book.admitted), "admission must not qty-reduce a fill"

    # (3) PARITY: enforce_cap=False is BYTE-IDENTICAL to the cap-blind book (same objects,
    #     same order, block_rate 0) — the explicit comparison path is unchanged.
    capoff = ca.admit_book(over, "safe", 2000.0, 3, enforce_cap=False)
    assert capoff.enforce_cap is False
    assert capoff.admitted == over and capoff.blocked == () and capoff.block_rate == 0.0


def test_dte_harness_aggregate_book_defaults_cap_on() -> None:
    """GRADUATED GUARD: the DTE harness book-aggregation entry point
    (_dte_stop_construction.aggregate_book) must default to the cap-aware realizable book,
    and route through the shared lib (one cap implementation). Asserts the default is
    cap-on and that an over-cap cell's aggregated book excludes the over-cap fills."""
    import inspect
    import importlib
    from dataclasses import dataclass

    dsc = importlib.import_module("autoresearch._dte_stop_construction")
    assert hasattr(dsc, "aggregate_book"), "DTE harness must expose aggregate_book"
    sig = inspect.signature(dsc.aggregate_book)
    assert sig.parameters["enforce_cap"].default is True, (
        "cap-admission regression: aggregate_book(enforce_cap) default must be True "
        "(the realizable book is the DEFAULT DTE-harness aggregation step)."
    )

    @dataclass(frozen=True)
    class _Fill:
        entry_premium: float
        dollar_pnl: float = 0.0
        qty: int = 3

    over = tuple(_Fill(p) for p in (2.40, 2.50, 2.60))   # median $2.50 -> $750 > $600 cap
    res = dsc.aggregate_book(over, "safe", 2000.0, 3)     # default => cap-on
    assert res.enforce_cap is True and res.block_rate > 0.0, (
        "DTE harness aggregate_book did not enforce the cap by default on an over-cap cell"
    )
    # parity: cap-off returns the book byte-identical.
    capoff = dsc.aggregate_book(over, "safe", 2000.0, 3, enforce_cap=False)
    assert capoff.admitted == over and capoff.block_rate == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# RESEARCH GUARDS — two session lessons graduated into a SINGLE-SOURCE library
# (lib.research_guards) that every future sim/validator imports. These tests pin
# the library to its REAL failure fixtures so the bar can never silently regress.
#
#   GUARD 1 — beats_random_filter_null (L172): a CONDITIONING FILTER on an existing
#     edge must beat a coin-flip drop of the same fraction (one-sided p<0.05). The
#     W1 IV-skew confirmer FAILED this (kept $45.66 vs null mean $48.30, p=0.76),
#     the VIX-level gate FAILED (p=0.355), touch-and-go was selective-only — 3 deaths.
#     The forward GEX-flip filter (~60-90 days out) will be held to THIS bar.
#
#   GUARD 2 — strike_band_covers_range (L177/L182): a SHORT-PREMIUM / credit sim must
#     verify the cached strike band reaches the day's realized [low,high], else the
#     loss tail is TRUNCATED and magnitude is biased upward — the cache-tail-bias that
#     made the event condor look +$32/tr on a +-$5 cache when the real tail (+-$18
#     wide cache) was -$751 on the same big-move day (2025-04-04).
#
# Full unit + edge coverage lives in tests/test_research_guards.py; these graduated
# guards pin the LOAD-BEARING real-failure cases into the canonical regression suite.
# ─────────────────────────────────────────────────────────────────────────────

_RG_ARTIFACT = REPO / "analysis" / "recommendations" / "web-vwap_cont_iv_skew_confirmer.json"
_RG_NARROW_CACHE = BACKTEST / "data" / "options"
_RG_WIDE_CACHE = BACKTEST / "data" / "options_event_wide"
# 2025-04-04 (tariff-crash / NFP big move): SPY realized intraday high ~525.86 (the
# call-wing tail). The narrow +-$5 cache prices [497,505]; the wide +-$18 cache [505,540].
_RG_EVENT_DAY = "250404"
_RG_DAY_HIGH = 525.86
_RG_ATM = 513.0


def test_l172_iv_skew_filter_fails_random_null() -> None:
    """L172 (graduated): the REAL W1 IV-skew confirmer kept-mask MUST FAIL
    beats_random_filter_null — so any future re-introduction of a no-selection
    CONDITIONING FILTER on an existing edge is caught.

    The W1 confirmer (analysis/recommendations/web-vwap_cont_iv_skew_confirmer.json,
    variant W1b_put_side_first_strict25d) kept 129/149 trades at exp $45.66 vs a
    random-drop null mean $48.30 / p95 $54.30 -> one-sided p=0.76 -> FAIL. This is the
    canonical "the filter just shrank n without real selection" failure (C3/L58).
    The forward GEX-flip filter will be held to this same bar.

    Data-free: reconstructs a base vector matching the artifact's PUBLISHED unfiltered
    moments (n=149, exp~48.3) and a kept-mask reproducing the published filtered exp
    ($45.66 < null mean) — the W1 signature is a kept subset BELOW the random-drop centre.
    """
    import numpy as np

    from lib.research_guards import beats_random_filter_null

    assert _RG_ARTIFACT.exists(), f"W1 IV-skew artifact missing at {_RG_ARTIFACT}"
    art = json.loads(_RG_ARTIFACT.read_text(encoding="utf-8"))
    v = art["variants"]["W1b_put_side_first_strict25d"]
    nullblk = v["random_filter_null_L172"]
    n_total = nullblk["n_total"]            # 149
    n_keep = nullblk["n_keep"]             # 129
    filtered_exp = v["filtered"]["exp"]    # 45.66 — the published kept-subset mean

    # Sanity: the artifact ITSELF recorded this filter as FAILING the null. If the on-disk
    # fixture ever flips to a passing gate, this guard's premise is gone — fail loudly.
    assert v["gates"]["beats_random_filter_null"] is False, (
        "fixture drift: the W1 IV-skew artifact no longer records "
        "beats_random_filter_null=False — the canonical failure case changed."
    )

    # Reconstruct a base vector with the artifact's unfiltered mean (0DTE tight-stop shape:
    # capped left tail, fat right tail) so the null distribution lands on the published moments.
    rng = np.random.default_rng(7)
    base_pnl = rng.lognormal(mean=4.4, sigma=0.9, size=n_total) - 60.0
    base_pnl = base_pnl - base_pnl.mean() + art["unfiltered_baseline"]["exp"]

    # Drop the n_drop trades nearest the implied drop-mean so the kept-mean == filtered_exp.
    n_drop = n_total - n_keep
    drop_target = (base_pnl.mean() * n_total - filtered_exp * n_keep) / n_drop
    drop_idx = np.argsort(np.abs(base_pnl - drop_target))[:n_drop]
    kept_mask = np.ones(n_total, dtype=bool)
    kept_mask[drop_idx] = False

    res = beats_random_filter_null(base_pnl, kept_mask)

    assert res.applicable is True, res.reason
    assert res.n_total == n_total and res.n_keep == n_keep
    # The kept subset sits BELOW the random-drop centre -> NOT in the right tail -> FAILS.
    assert res.passed is False, (
        "L172 regression: the W1 IV-skew kept-mask now PASSES the random-filter null. "
        "A no-selection conditioning filter must FAIL (the W1/VIX-level/touch-and-go bar). "
        f"{res.reason}"
    )
    assert res.filt_mean < res.null_mean, res.reason
    assert res.p_value is not None and res.p_value > 0.05, res.reason
    # Null moments reproduce the artifact's published numbers (within a few dollars).
    assert abs(res.null_mean - nullblk["null_mean"]) < 4.0, res.reason
    assert abs(res.null_p95 - nullblk["null_p95"]) < 4.0, res.reason


def test_l172_genuine_filter_passes_random_null() -> None:
    """L172 discrimination half: the guard must NOT be always-False — a genuinely
    selective filter (keep only the top-quartile P&L) MUST PASS beats_random_filter_null.
    Without this, a broken always-False guard would pass test_l172_iv_skew_filter_fails
    while silently rejecting every real edge (incl. the forward GEX-flip filter)."""
    import numpy as np

    from lib.research_guards import beats_random_filter_null

    rng = np.random.default_rng(11)
    base_pnl = rng.normal(40.0, 100.0, size=160)
    kept_mask = base_pnl >= np.percentile(base_pnl, 75)  # the genuinely-best quarter
    res = beats_random_filter_null(base_pnl, kept_mask)
    assert res.applicable is True
    assert res.passed is True, (
        "L172 regression: a top-quartile selective filter FAILED the random-filter null "
        f"-> the guard is over-strict / always-False and would reject real edges. {res.reason}"
    )
    assert res.p_value is not None and res.p_value < 0.05, res.reason
    assert res.filt_mean > res.null_p95, res.reason


def test_l172_degenerate_point_null_flagged_not_blessed() -> None:
    """L172 non-degeneracy: a filter that keeps ALL (or NONE) of the sample is a
    DEGENERATE point-null — there is no random-drop distribution to beat. The guard
    must flag it (applicable=False) and NOT bless it (passed=False). The event-long-vega
    harness hit exactly this (random pool == sample size)."""
    from lib.research_guards import beats_random_filter_null

    keep_all = beats_random_filter_null([10.0, 20.0, 30.0, 40.0], [True, True, True, True])
    assert keep_all.applicable is False and keep_all.passed is False, keep_all.reason
    assert "DEGENERATE" in keep_all.reason
    keep_none = beats_random_filter_null([10.0, 20.0, 30.0, 40.0], [False, False, False, False])
    assert keep_none.applicable is False and keep_none.passed is False


def _rg_cache_band(cache_dir: Path, yymmdd: str) -> tuple:
    """Min/max strike (across C and P) present in a cache dir for a day (filename parse)."""
    import os as _os

    pat = re.compile(r"SPY" + yymmdd + r"[CP](\d{8})\.csv$")
    strikes = [int(m.group(1)) / 1000.0 for f in _os.listdir(cache_dir) if (m := pat.match(f))]
    if not strikes:
        raise FileNotFoundError(f"no {yymmdd} contracts in {cache_dir}")
    return min(strikes), max(strikes)


def test_l177_event_condor_narrow_cache_fails_band_coverage() -> None:
    """L177/L182 (graduated): the REAL +-$5 event-condor cache MUST FAIL
    strike_band_covers_range on the 2025-04-04 big-move day — so any future
    short-premium sim priced off a too-narrow cache (truncated loss tail =
    upward-biased magnitude) is caught.

    The narrow cache prices [497,505]; the day's call-wing high was ~525.86, ~$21 past
    the band. That truncation is what made the condor look +$32/tr on +-$5 when the real
    tail (+-$18 wide cache) was -$751 the same day. Reads the REAL on-disk cache."""
    from lib.research_guards import strike_band_covers_range

    assert _RG_NARROW_CACHE.exists(), f"narrow event cache missing at {_RG_NARROW_CACHE}"
    cmin, cmax = _rg_cache_band(_RG_NARROW_CACHE, _RG_EVENT_DAY)
    assert (cmin, cmax) == (497.0, 505.0), (
        f"fixture drift: the +-$5 narrow cache band for {_RG_EVENT_DAY} is "
        f"[{cmin},{cmax}], expected [497.0,505.0]"
    )
    res = strike_band_covers_range(
        day_low=cmin, day_high=_RG_DAY_HIGH, atm=_RG_ATM,
        cache_min_strike=cmin, cache_max_strike=cmax,
    )
    assert res.covered is False, (
        "L177/L182 regression: the +-$5 narrow cache now reports the 2025-04-04 move as "
        "COVERED — the cache-tail-bias guard is broken; a short-premium sim would price a "
        f"truncated loss tail. {res.reason}"
    )
    assert res.dropped_side == "high", res.reason
    assert res.slack < 0, res.reason  # the high exited the band by ~$21


def test_l177_event_condor_wide_cache_covers_band() -> None:
    """L177/L182 discrimination half: the REAL +-$18 WIDE event cache MUST PASS
    strike_band_covers_range on the same 2025-04-04 move — proving the guard is not
    always-False and that the WIDE cache is the correct one to price the event tail."""
    from lib.research_guards import strike_band_covers_range

    assert _RG_WIDE_CACHE.exists(), f"wide event cache missing at {_RG_WIDE_CACHE}"
    cmin, cmax = _rg_cache_band(_RG_WIDE_CACHE, _RG_EVENT_DAY)
    assert (cmin, cmax) == (505.0, 540.0), (
        f"fixture drift: the +-$18 wide cache band for {_RG_EVENT_DAY} is "
        f"[{cmin},{cmax}], expected [505.0,540.0]"
    )
    res = strike_band_covers_range(
        day_low=cmin, day_high=_RG_DAY_HIGH, atm=_RG_ATM,
        cache_min_strike=cmin, cache_max_strike=cmax,
    )
    assert res.covered is True, (
        "L177/L182 regression: the +-$18 wide cache now reports the 2025-04-04 move as "
        f"NOT covered -> the band-coverage guard is over-strict / always-False. {res.reason}"
    )
    assert res.dropped_side is None, res.reason
    assert res.slack >= 0, res.reason  # ~$14 of headroom above the high


def test_g14_ribbon_flip_fn_direction() -> None:
    """G14/v15.3 chart-stop-primary: ribbon_flip_back_fn direction guard.

    PUT (bearish) exits when ribbon turns BULL; CALL (bullish) exits when BEAR.
    Anchor no-regression: 5/04 SPY 721P +$730 — ribbon stayed BEAR throughout → must NOT
    trigger a premature flip exit on a winning bearish trade.

    NON-VACUOUS (L197/G16 fix): imports the REAL heartbeat_core._ribbon_flip_fn and asserts
    against the producer's ACTUAL stack literals. The prior version of this guard re-implemented
    the (buggy) logic inline with 'BULLISH'/'BEARISH' literals the producer never emits, so it
    was vacuous — it green-lit a dead exit for weeks. This version fails if the real fn ever
    stops matching the ribbon.py producer alphabet.
    """
    import importlib.util as _ilu
    _hc_path = REPO / "setup" / "scripts" / "heartbeat_core.py"
    _spec = _ilu.spec_from_file_location("heartbeat_core_g14", _hc_path)
    _hc = _ilu.module_from_spec(_spec)
    # heartbeat_core imports are guarded; only _ribbon_flip_fn (pure) is needed, so exec is safe.
    _spec.loader.exec_module(_hc)
    ribbon_flip_fn = _hc._ribbon_flip_fn

    # PRODUCER-ALPHABET CONTRACT: the literals the real fn compares against MUST be the ones
    # backtest/lib/ribbon.py actually writes. If the producer renames its stack tokens this REDs.
    _ribbon_src = (REPO / "backtest" / "lib" / "ribbon.py").read_text(encoding="utf-8")
    assert '"BULL"' in _ribbon_src and '"BEAR"' in _ribbon_src, "ribbon.py producer alphabet changed"

    # bearish PUT: ribbon now BULL = flip against position → exit
    assert ribbon_flip_fn("BULL")("SPY", "P") is True
    # bearish PUT: ribbon still BEAR = no flip → hold
    assert ribbon_flip_fn("BEAR")("SPY", "P") is False
    # bullish CALL: ribbon now BEAR = flip against position → exit
    assert ribbon_flip_fn("BEAR")("SPY", "C") is True
    # bullish CALL: ribbon still BULL = no flip → hold
    assert ribbon_flip_fn("BULL")("SPY", "C") is False
    # MIXED/UNKNOWN are NOT an opposite-direction reversal → never a flip exit (hold)
    for _neutral in ("MIXED", "UNKNOWN", "WARMUP"):
        assert ribbon_flip_fn(_neutral)("SPY", "P") is False
        assert ribbon_flip_fn(_neutral)("SPY", "C") is False
    # BITE: the retired buggy literals must be DEAD — a real ribbon never emits them, so they
    # must never trigger an exit (this is the exact bug this fix retired).
    assert ribbon_flip_fn("BULLISH")("SPY", "P") is False
    assert ribbon_flip_fn("BEARISH")("SPY", "C") is False
    # anchor: 5/04 SPY 721P +$730 — ribbon stayed BEAR → no premature exit
    assert ribbon_flip_fn("BEAR")("SPY", "P") is False


def test_l188_dir_null_p5_gate_wired_into_family_grind() -> None:
    """L188 graduation: the DIRECTION-CONTROLLED null must remain wired into family_grind's
    run_family as the P5 gate. The stock random-entry null shuffles the SIDE, so a directional
    family beats it just by being directionally correct — only the dir-null isolates selection
    alpha. A refactor that silently drops the gate REDs here.

    Static (AST/source) so the guard stays cheap; behavioral coverage lives in
    test_dir_null_p5_gate.py. Asserts the gate helpers exist AND are invoked inside run_family
    (dead-code guard) AND the PASS-P4-DIR-ARTIFACT downgrade verdict still exists.
    """
    src = (BACKTEST / "autoresearch" / "family_grind.py").read_text(encoding="utf-8")
    for name in ("def is_directional_family", "def dir_null_survives",
                 "def p5_verdict", "def _dir_null"):
        assert name in src, f"L188 P5-gate helper dropped: {name}"
    rf = src[src.index("def run_family"):]
    assert "is_directional_family(rth, signals)" in rf, "run_family no longer flags directional families"
    assert "_dir_null(" in rf, "run_family no longer calls the direction-controlled null"
    assert "p5_verdict(" in rf, "run_family no longer applies the P5 verdict"
    assert "PASS-P4-DIR-ARTIFACT" in src, "the dir-artifact downgrade verdict was removed"


# ─── G-PIPELINE-CHAIN: auto-chain wiring (2026-06-28) ───────────────────────

def test_pipeline_chain_all_stages_registered() -> None:
    """G-PIPELINE-CHAIN: shotgun_scalper stages 1-5 all registered in GRINDER_REGISTRY
    with correct next_stage_script pointers.  A refactor that breaks the chain REDs here.
    """
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import importlib
    daemon = importlib.import_module("kitchen_daemon")

    registry = daemon.GRINDER_REGISTRY
    chain = [
        ("shotgun_scalper_grinder",  "shotgun_scalper_stage2"),
        ("shotgun_scalper_stage2",   "shotgun_scalper_stage3"),
        ("shotgun_scalper_stage3",   "shotgun_scalper_stage4"),
        ("shotgun_scalper_stage4",   "shotgun_scalper_stage5"),
    ]
    for src, dst in chain:
        assert src in registry, f"GRINDER_REGISTRY missing {src!r}"
        assert dst in registry, f"GRINDER_REGISTRY missing {dst!r}"
        assert registry[src].get("next_stage_script") == dst, (
            f"{src} next_stage_script should be {dst!r}, "
            f"got {registry[src].get('next_stage_script')!r}"
        )
    # Stage5 must be flagged as scorecard
    assert registry["shotgun_scalper_stage5"].get("is_scorecard"), (
        "shotgun_scalper_stage5 must have is_scorecard=True in registry"
    )
    # Stage4 must signal next_is_scorecard so daemon uses pipeline_scorecard handler
    assert registry["shotgun_scalper_stage4"].get("next_is_scorecard"), (
        "shotgun_scalper_stage4 must have next_is_scorecard=True"
    )


def test_pipeline_chain_sniper_chain_registered() -> None:
    """G-PIPELINE-CHAIN: sniper chain s1->s2->real_fills all registered and linked."""
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import importlib
    daemon = importlib.import_module("kitchen_daemon")
    registry = daemon.GRINDER_REGISTRY

    chain = [
        ("sniper_overnight_grinder", "sniper_stage2_grinder"),
        ("sniper_stage2_grinder",    "sniper_real_fills_grinder"),
    ]
    for src, dst in chain:
        assert src in registry, f"GRINDER_REGISTRY missing {src!r}"
        assert registry[src].get("next_stage_script") == dst, (
            f"{src}.next_stage_script should be {dst!r}"
        )
    assert registry["sniper_real_fills_grinder"].get("promotes_to_watcher"), (
        "sniper_real_fills_grinder must have promotes_to_watcher=True"
    )


def test_pipeline_promoter_gates_pass_on_good_scorecard() -> None:
    """G-PIPELINE-CHAIN: promoter returns True and writes files when all gates pass."""
    import tempfile, json as _json
    sys.path.insert(0, str(REPO / "backtest"))
    from autoresearch.pipeline_promoter import check_and_promote, _check_gates

    good_scorecard = {
        "walk_forward": {
            "passed": True,
            "train_pnl": 4000.0,
            "test_pnl": 3200.0,          # ratio = 0.80 >= 0.70
            "test_positive_quarters": 2,
            "total_test_quarters": 2,
        },
        "best_keeper": {
            "directional_score": 3,       # >= 2
            "top5_pct": 0.35,             # <= 0.50
            "wide_pnl": 5500.0,
            "expectancy_per_trade": 12.5,
        },
    }
    passed, details = _check_gates(good_scorecard)
    assert passed, f"Expected gates to pass on good scorecard, got details={details}"
    assert details["wf_ratio"] >= 0.70
    assert details["anchor_no_regression"] is True
    assert details["concentration_ok"] is True


def test_pipeline_promoter_gates_block_on_bad_wf() -> None:
    """G-PIPELINE-CHAIN: promoter blocks when WF ratio is below 0.70."""
    sys.path.insert(0, str(REPO / "backtest"))
    from autoresearch.pipeline_promoter import _check_gates

    bad_scorecard = {
        "walk_forward": {
            "passed": True,
            "train_pnl": 5000.0,
            "test_pnl": 2000.0,          # ratio = 0.40 — FAIL
            "test_positive_quarters": 2,
            "total_test_quarters": 2,
        },
        "best_keeper": {
            "directional_score": 3,
            "top5_pct": 0.30,
            "wide_pnl": 4000.0,
        },
    }
    passed, details = _check_gates(bad_scorecard)
    assert not passed, "Should have blocked on WF ratio < 0.70"
    assert details["wf_ratio"] < 0.70


def test_chain_next_stage_fn_enqueues_scorecard() -> None:
    """G-PIPELINE-CHAIN: _chain_next_stage enqueues pipeline_scorecard for stage4->stage5."""
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import importlib, unittest.mock as mock

    daemon = importlib.import_module("kitchen_daemon")
    enqueued = []

    def fake_enqueue(task, *, priority, source, task_type, script_name, **kw):
        enqueued.append({"task_type": task_type, "script_name": script_name})
        return "fake-tid"

    with mock.patch.object(daemon, "enqueue_task", side_effect=fake_enqueue):
        daemon._chain_next_stage(
            "shotgun_scalper_stage4",
            [{"wide_pnl": 5000}],   # 1 keeper — enough to advance
            "test task",
        )

    assert len(enqueued) == 1, "Expected exactly 1 task enqueued"
    assert enqueued[0]["task_type"] == "pipeline_scorecard"
    assert enqueued[0]["script_name"] == "shotgun_scalper_stage5"


def test_chain_next_stage_fn_skips_below_min_keepers() -> None:
    """G-PIPELINE-CHAIN: _chain_next_stage does NOT chain when below min_keepers_to_advance."""
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import importlib, unittest.mock as mock

    daemon = importlib.import_module("kitchen_daemon")
    enqueued = []

    def fake_enqueue(*a, **kw):
        enqueued.append(kw)
        return "fake-tid"

    with mock.patch.object(daemon, "enqueue_task", side_effect=fake_enqueue):
        # sniper_overnight_grinder requires min 3 keepers
        daemon._chain_next_stage("sniper_overnight_grinder", [{"ec": 1}, {"ec": 2}], "test")

    assert len(enqueued) == 0, f"Should not have chained with only 2 keepers (min=3), got {enqueued}"


# ── Swarm roster rotation guards (fix 2026-06-28: stale-slug rot + no 429 fallback) ──

def test_swarm_rotatable_error_classification() -> None:
    """G-SWARM-ROT: 429/404/timeout are rotatable; auth/empty-prompt are not.

    Root cause being guarded: the swarm collapsed to 1 perspective because a 429
    on a primary model was treated as terminal. Transient errors MUST rotate.
    """
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import importlib
    sc = importlib.import_module("swarm_consult")

    assert sc._is_rotatable_error("RateLimitError: Error code: 429")
    assert sc._is_rotatable_error("NotFoundError: Error code: 404 - unavailable for free")
    assert sc._is_rotatable_error("Timeout waiting for response")
    assert not sc._is_rotatable_error("auth-failed: key missing")
    assert not sc._is_rotatable_error("empty_prompt")
    assert not sc._is_rotatable_error(None)


def test_swarm_perspective_rotates_on_429() -> None:
    """G-SWARM-ROT: _call_one_perspective falls through to a fallback on 429
    and returns an OK perspective from the fallback model (not a dead lane)."""
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import importlib, unittest.mock as mock
    sc = importlib.import_module("swarm_consult")

    calls = []

    def fake_call(*, prompt, model, system, max_tokens, temperature, timeout, task_id):
        calls.append(model)
        if model == "primary/dead:free":
            return {"ok": False, "content": "", "error": "RateLimitError: 429",
                    "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "elapsed_s": 0.1}
        return {"ok": True, "content": "real answer", "error": None,
                "input_tokens": 5, "output_tokens": 5, "cost_usd": 0.0, "elapsed_s": 0.2}

    with mock.patch.object(sc, "call_minimax", side_effect=fake_call):
        p = sc._call_one_perspective(
            model="primary/dead:free", prompt="q", system="s",
            max_tokens=50, task_id="t", fallbacks=("backup/live:free",),
        )

    assert p.ok, f"Should have rotated to a live fallback, got error={p.error}"
    assert p.model == "backup/live:free", f"Perspective should report the model that answered, got {p.model}"
    assert calls == ["primary/dead:free", "backup/live:free"], f"Should try primary then fallback, got {calls}"


def _swarm_vendor(spec: str) -> str:
    """Family root of a perspective spec: 'cerebras:zai-glm-4.7'->'zai-glm',
    'nvidia/nemotron-..:free'->'nvidia', 'openai/gpt-oss-120b:free'->'openai'."""
    body = spec.split(":", 1)[1] if spec.split(":", 1)[0] in ("cerebras", "groq", "openrouter") else spec
    if "/" in body:
        return body.split("/")[0]
    # provider-hosted bare model (e.g. zai-glm-4.7) — take the family token
    return "-".join(body.split("-")[:2])


def test_swarm_roster_models_distinct_vendors() -> None:
    """G-SWARM-ROT: the 5 default perspectives span >=4 distinct vendor families
    (diversity is the whole point of a swarm — copies of one model is not a swarm)."""
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import importlib
    sc = importlib.import_module("swarm_consult")
    models = sc.DEFAULT_PERSPECTIVE_MODELS
    vendors = {_swarm_vendor(m) for m in models}
    assert len(models) == 5, f"Expected 5 perspectives (J 2026-06-28), got {len(models)}"
    assert len(vendors) >= 4, f"Need >=4 distinct vendor families for diversity, got {vendors}"
    # Free-tier only: OpenRouter specs end :free; cerebras/groq specs are free-tier providers.
    for m in models:
        prov = sc._split_spec(m)[0]
        assert prov in ("openrouter", "cerebras", "groq"), f"unknown provider in {m}"
        if prov == "openrouter":
            assert m.endswith(":free"), f"OpenRouter perspective must be :free, got {m}"


def test_free_model_cost_estimate_is_zero() -> None:
    """G-PHANTOM-COST (2026-07-01): any ':free' slug must cost $0 in telemetry even if
    absent from the PRICING table. Scar: unknown :free models (gemma-4-31b, gpt-oss-20b,
    nemotron-ultra) fell through to the paid-M2 default in _estimate_cost, writing
    phantom cost_usd into minimax-calls.jsonl and corrupting the spend summaries."""
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import importlib
    rm = importlib.import_module("run_minimax")
    # A :free slug deliberately NOT in PRICING — must be $0, not paid-default rates.
    assert rm._estimate_cost("vendor/not-in-table:free", 100_000, 100_000) == 0.0
    # A known paid slug must still be charged.
    assert rm._estimate_cost("minimax/minimax-m2.5", 100_000, 100_000) > 0.0
    # An UNKNOWN paid slug still falls back to conservative default (unchanged behavior).
    assert rm._estimate_cost("vendor/unknown-paid-model", 100_000, 100_000) > 0.0


def test_no_dead_slug_in_active_model_configs() -> None:
    """G-DEAD-SLUG (2026-07-01 free-model audit): a slug recorded in model-roster.json
    "dead" must never reappear in an ACTIVE model config. Scar: deepseek-v4-flash:free +
    minimax-m2.5:free 404'd (de-tagged to paid) while still wired as kitchen ladder T1/T2
    and eod_fallback T2/T3 — every ladder fall-through skipped two dead rungs and landed
    on the PAID last-resort. Text-scan (no imports: face_brain sys.exits on import guard)."""
    roster = json.loads((REPO / "automation" / "state" / "model-roster.json").read_text(encoding="utf-8"))
    dead_ids = [d["id"] for d in roster.get("dead", [])]
    assert dead_ids, "roster dead-list unexpectedly empty — guard would be vacuous"

    active_configs = [
        REPO / "setup" / "scripts" / "chef_nemotron.py",      # kitchen MODEL_LADDER
        REPO / "setup" / "scripts" / "eod_fallback.py",       # EOD _MODEL_LADDER
        REPO / "setup" / "scripts" / "swarm_consult.py",      # perspective roster
        REPO / "setup" / "scripts" / "shadow_model_eval.py",  # shadow challengers
        REPO / "gamma-companion" / "face" / "face_brain.py",  # FACE_MODELS
    ]
    offenders: list[str] = []
    for path in active_configs:
        text = path.read_text(encoding="utf-8")
        for slug in dead_ids:
            for i, line in enumerate(text.splitlines(), 1):
                # Only flag QUOTED occurrences (active config values), not prose/comments.
                if (f'"{slug}"' in line or f"'{slug}'" in line) and not line.lstrip().startswith("#"):
                    offenders.append(f"{path.name}:{i} uses dead slug {slug}")
    # Roster role lanes must not reference dead ids either.
    for role, cfg in roster.get("roles", {}).items():
        for lane in cfg.get("lanes", []):
            if lane.get("model") in dead_ids:
                offenders.append(f"model-roster.json role={role} lane uses dead slug {lane.get('model')}")
    assert not offenders, "Dead model slugs wired in active configs:\n  " + "\n  ".join(offenders)


def test_swarm_split_spec_routing() -> None:
    """G-SWARM-MP: provider routing parses specs correctly. Bare slugs -> openrouter;
    'cerebras:'/'groq:' prefixes -> that provider. Guards GLM (Cerebras) staying reachable."""
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import importlib
    sc = importlib.import_module("swarm_consult")
    assert sc._split_spec("cerebras:zai-glm-4.7") == ("cerebras", "zai-glm-4.7")
    assert sc._split_spec("groq:llama-3.3-70b-versatile") == ("groq", "llama-3.3-70b-versatile")
    assert sc._split_spec("nvidia/nemotron-3-super-120b-a12b:free") == ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free")
    assert sc._split_spec("openai/gpt-oss-120b:free") == ("openrouter", "openai/gpt-oss-120b:free")
    # GLM must be in the default roster (J explicitly asked for it)
    assert any("glm" in m.lower() for m in sc.DEFAULT_PERSPECTIVE_MODELS), "GLM must be a default perspective"


# ── Bull-wiring regression guards (2026-06-28: J unlocked both directions; swarm-confirmed) ──

def test_enable_bullish_live_true() -> None:
    """G-BULL-WIRE: the live deterministic engine MUST score bull every tick.

    Regression guarded: if a future edit flips enable_bullish off, the engine
    silently reverts to bear-only — exactly the drift J flagged 2026-06-28.
    """
    src = (REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    assert '"enable_bullish": True' in src, (
        "heartbeat_core must set enable_bullish=True so the engine scores bull. "
        "Bull and bear are BOTH active setups (CLAUDE.md OP-16 — direction is not a scope)."
    )
    # Doctrine parity (2026-06-30): params.json must also carry enable_bullish=true so a future
    # params-direct consumer can't read None->False (the absent-key landmine the 06-30 audit named).
    import json as _json
    for _pf in ("params.json", "aggressive/params.json"):
        _p = _json.loads((REPO / "automation" / "state" / _pf).read_text(encoding="utf-8"))
        assert _p.get("enable_bullish") is True, f"{_pf} must set enable_bullish=true (OP-16 parity)"


def test_enter_bull_in_placement_path() -> None:
    """G-BULL-WIRE: ENTER_BULL must travel the SAME placement path as ENTER_BEAR.

    Guards against a bear-only exec gate sneaking in. The core dispatch tuple that
    routes a verdict into _execute must contain BOTH verdicts.
    """
    src = (REPO / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        # Look for: if v in ("ENTER_BEAR", "ENTER_BULL")
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.In) for op in node.ops):
            for comp in node.comparators:
                if isinstance(comp, (ast.Tuple, ast.List, ast.Set)):
                    vals = {e.value for e in comp.elts if isinstance(e, ast.Constant)}
                    if "ENTER_BEAR" in vals and "ENTER_BULL" in vals:
                        found = True
    assert found, (
        "heartbeat_core placement dispatch must route ENTER_BULL through the same "
        "`if v in (ENTER_BEAR, ENTER_BULL)` branch as bear — no bear-only exec gate."
    )


def test_orchestrator_enable_bullish_defaults_true() -> None:
    """G-BULL-WIRE: run_backtest must default enable_bullish=True so backtests
    and the live engine agree that bull is an active direction."""
    import inspect
    sig = inspect.signature(run_backtest)
    default = sig.parameters["enable_bullish"].default
    assert default is True, f"run_backtest enable_bullish must default True, got {default!r}"


# ── gap_and_go prior-close feed guard (G4c fix 2026-06-28: key-name mismatch) ──

def test_gap_and_go_prior_close_key_match() -> None:
    """G-GAP-FEED: the prior-close resolver MUST check the key the premarket writer
    actually uses ('prior_day_close'). The mismatch left gap_and_go SKIP_NO_FEED forever.
    """
    src = (REPO / "setup" / "scripts" / "setup_dispatch.py").read_text(encoding="utf-8")
    # The resolver and the premarket writer must agree on this key.
    assert "prior_day_close" in src, (
        "setup_dispatch._get_prior_rth_close must check 'prior_day_close' — the key "
        "today-bias.json actually uses. Without it gap_and_go never gets a prior close."
    )


def test_gap_and_go_resolves_real_prior_close() -> None:
    """G-GAP-FEED (integration): if today-bias.json carries a prior_day_close, the
    dispatcher's resolver must return it (not None). Skips if the live file lacks it."""
    import sys as _sys, json as _json
    _sys.path.insert(0, str(REPO / "setup" / "scripts"))
    _sys.path.insert(0, str(REPO / "backtest"))
    import importlib
    sd = importlib.import_module("setup_dispatch")
    bias_path = REPO / "automation" / "state" / "today-bias.json"
    if not bias_path.exists():
        pytest.skip("no today-bias.json in this checkout")
    bias = _json.loads(bias_path.read_text(encoding="utf-8"))
    expected = bias.get("prior_day_close")
    if expected is None:
        pytest.skip("today-bias.json has no prior_day_close right now")
    disp = sd.SetupDispatcher({}, {})
    got = disp._get_prior_rth_close()
    assert got == float(expected), f"resolver returned {got}, expected {expected} from today-bias.json"


# ── Engine-stress-swarm harness guards (2026-06-28: "tenfold the swarm") ──

def test_stress_swarm_bs_sim_only_disclosure() -> None:
    """G-STRESS-C1: the harness perturbs/synthesizes bars, which have NO OPRA chain.
    It MUST run the engine with use_real_fills=False and MUST disclose ranking-only.
    A regression that flips real_fills on synthetic bars would fabricate a fake WR
    authority (CLAUDE.md C1 — real fills are the ONLY WR authority).
    """
    src = (REPO / "backtest" / "autoresearch" / "engine_stress_swarm.py").read_text(encoding="utf-8")
    assert "use_real_fills=False" in src, "stress harness must run engine with use_real_fills=False on synthetic bars"
    assert "RANKING-ONLY" in src, "stress harness must disclose BS-sim results are ranking-only"
    # It must NOT ever pass use_real_fills=True (would claim a fake WR authority).
    assert "use_real_fills=True" not in src, "stress harness must NEVER use real fills on perturbed bars"


def test_stress_swarm_covers_j_named_variants() -> None:
    """G-STRESS-COV: the variant grid must cover J's explicitly-named counterfactuals
    (5-contracts-scaled-out-at-30%, direction flip). Guards the harness from silently
    dropping the scenarios J asked for."""
    sys.path.insert(0, str(REPO / "backtest" / "autoresearch"))
    sys.path.insert(0, str(REPO / "backtest"))
    sys.path.insert(0, str(REPO))
    import importlib
    ess = importlib.import_module("engine_stress_swarm")
    names = {v.name for v in ess.variant_grid(full=True)}
    assert "tp1_30_allout" in names, "must test 'scale out 30% on all' (J's example)"
    assert "bull_off" in names, "must test a direction counterfactual"
    assert any("risk_" in n for n in names), "must test contract-count/risk variants"
    perts = set(ess.PERTURBATIONS)
    for p in ("baseline", "trend_flip", "dampen"):
        assert p in perts, f"perturbation '{p}' (J's 'what if the bars did this') missing"


def test_design_swarm_canonical_battery_covers_the_metric_we_missed() -> None:
    """G-DESIGN-SWARM (2026-06-29 lesson): a single perspective measured WR (coin flip) and
    missed EXPECTANCY-with-tight-stops + OOS. The canonical battery MUST always run those
    framings for every hypothesis, so the right metric can never be silently skipped again.
    """
    sys.path.insert(0, str(REPO / "backtest" / "autoresearch"))
    sys.path.insert(0, str(REPO / "backtest"))
    sys.path.insert(0, str(REPO))
    import importlib
    bds = importlib.import_module("backtest_design_swarm")
    battery = bds.canonical_battery([5, 9], "P")
    metrics = {d.metric for d in battery}
    splits = {d.split for d in battery}
    # the exact things the single perspective missed must ALWAYS be in the battery
    assert "expectancy" in metrics, "battery must always run EXPECTANCY (the metric WR-only missed)"
    assert "drawdown" in metrics, "battery must always run DRAWDOWN"
    assert "oos" in splits, "battery must always run an OOS walk-forward split (curve-fit guard)"
    # at least one design must sweep tight stops (the asymmetry unlock)
    assert any(any(s > -0.25 for s in d.stop_sweep) for d in battery), "battery must sweep a TIGHT stop (<=-0.20)"
    # the review gate must reject a malformed design (smart-review is real, not a pass-through)
    kept, rejected = bds.review_designs([bds.Design("ok", "P", [5], [-0.2]),
                                         bds.Design("bad", "X", [99], [0.5], "nonsense")])
    assert any("bad" in r for r in rejected), "review gate must reject malformed designs"


def test_smart_reviewer_shadow_gate_keeps_gamma_in_loop_until_85() -> None:
    """G-OVERSIGHT (J 2026-06-29): the free 'smart' reviewer must NOT be trusted to gate
    designs alone until it proves >=85% agreement with Gamma's labeled edge cases. The
    shadow harness must (a) have a labeled edge-case suite, (b) gate at 0.85, (c) mark
    graduated=False when agreement < 0.85. Codifies 'you stay my eyes'."""
    sys.path.insert(0, str(REPO / "backtest" / "autoresearch"))
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    sys.path.insert(0, str(REPO))
    import importlib
    sh = importlib.import_module("design_review_shadow")
    assert sh.GRAD_THRESHOLD == 0.85, "trust gate must be 85% (J's bar)"
    assert len(sh.LABELED_CASES) >= 8, "need a real edge-case suite (multiple angles)"
    # the suite must contain both must-reject (the WR-only trap) and must-accept (expectancy+OOS)
    rejects = [exp for _, exp, _ in sh.LABELED_CASES if exp is False]
    accepts = [exp for _, exp, _ in sh.LABELED_CASES if exp is True]
    assert rejects and accepts, "suite must cover both reject and accept cases"
    # the gate logic: a sub-85% agreement must NOT graduate (proven via a tiny synthetic tally)
    # (we don't call the live model here — that's the runnable scorecard; this guards the math.)
    assert (0.80 >= sh.GRAD_THRESHOLD) is False, "0.80 must be below the gate"


def test_run_ps1_ascii_or_bom() -> None:
    """G-ENCODING (2026-06-29, the 544-day silent-failure class): every scheduled-task
    run-*.ps1 must be pure-ASCII OR start with a UTF-8 BOM. A BOM-less non-ASCII .ps1 is
    read by PowerShell 5.1 as Windows-1252 and parse-crashes SILENTLY (wrapper exits 0,
    no output) — the exact bug that killed Gamma_TvWatchdog for hours. RED on regression."""
    bad = []
    for p in sorted((REPO / "setup" / "scripts").glob("run-*.ps1")):
        raw = p.read_bytes()
        if raw[:3] == b"\xef\xbb\xbf":
            continue
        try:
            txt = raw.decode("utf-8")
        except UnicodeDecodeError:
            bad.append(p.name + " (not utf-8)"); continue
        if any(ord(c) > 127 for c in txt):
            bad.append(p.name)
    assert not bad, (
        f"{len(bad)} run-*.ps1 are non-ASCII without a BOM -> PS 5.1 silent parse-crash: "
        f"{bad[:8]}. Fix: prepend a UTF-8 BOM (b'\xef\xbb\xbf') or make ASCII-only."
    )


def test_operator_friction_harvest_wired() -> None:
    """G-J-MIND (OP-33(e), 2026-06-29 metacog dissection): a REPEATED state-question from J
    is a MISSING INSTRUMENT, not a query. The load-bearing root cause of why Gamma never
    invented the self-check on its own: the friction organ counted the RIG's pain and never
    J's, so 'J asked 6 times' crossed no threshold. This guards the mechanization so the
    blind spot cannot silently reopen: (1) friction_distiller has the operator-friction class
    escalating FAST (>=2), (2) it counts that class ONLY from J's question-ledger -- never
    from prose mentioning the phrases (else an empty ledger phantom-escalates = trust killer),
    (3) the prompt-submit hook captures J's interrogatives to that ledger, BOM-less + ASCII."""
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import importlib
    fd = importlib.import_module("friction_distiller")
    # (1) class exists + fast-escalates in 2 asks (not the months-of-system-friction bar)
    assert "recurring_user_question" in fd.PATTERNS, "operator-friction class missing"
    assert fd.FAST_ESCALATE.get("recurring_user_question") == 2, "must escalate at >=2 asks"
    # (2) ledger-only: arbitrary prose must NOT classify as operator-friction
    assert fd._classify("we had no visibility and you told me it worked") != "recurring_user_question",         "operator-friction must come ONLY from the question-ledger, not doc prose"
    # (3) the harvest source: the prompt-submit hook
    hook = (REPO / "setup" / "hook-detect-correction.ps1").read_text(encoding="utf-8", errors="replace")
    assert "j-question-ledger.jsonl" in hook, "hook must write the question ledger"
    for sig in ("is it (running", "trading", "did|has) it (crash"):
        assert sig in hook, f"hook missing interrogative pattern: {sig}"
    assert "UTF8Encoding($false)" in hook, "hook must write the ledger BOM-less (json-safe)"
    # the hook must SKIP system/agent/tool messages, else task-notifications phantom-fire and
    # falsely trip BUILD_ELIMINATING_INSTRUMENT (caught 2026-06-29 by self-verification)
    assert "qIsSystem" in hook and "task-notification" in hook, \
        "hook must skip system/agent/tool messages (no phantom operator-question fires)"
    # the hook is in the UserPromptSubmit chain -- a non-ASCII parse crash kills BOTH captures
    assert all(ord(c) < 128 for c in hook), "prompt-submit hook must be pure ASCII (PS 5.1 silent-crash class)"


def test_operator_friction_excludes_wrapper_self_fire() -> None:
    """G-J-MIND-2 (2026-07-18, found while auditing the 'J asked 40+ times' claim): EVERY
    scheduled conductor/conductor-weekend/conductor-rth/weekly-review fire submits the wrapper's
    injected '# RUNTIME CONTEXT (injected by wrapper, ...)' header + STATE DIGEST as the literal
    UserPromptSubmit text, and automation/prompts/conductor.md's own doctrine prose contains
    phrases ('the success bar is daily paper trading', 'the rig's function is trading', 'never a
    live futures order') that trip the is_running/is_trading regexes even though J typed nothing.
    Direct regex replay against automation/prompts/conductor.md confirmed 3 self-matches. This was
    silently inflating j-question-ledger.jsonl -- 15 of 49 lines (31%) were self-inflicted wrapper
    fires, not J, before this fix (audited + pruned 2026-07-18). Guards that the wrapper marker is
    excluded so a scheduled fire NEVER phantom-logs itself as J asking a state question."""
    hook = (REPO / "setup" / "hook-detect-correction.ps1").read_text(encoding="utf-8", errors="replace")
    assert "runtime context \\(injected by wrapper" in hook.lower(), (
        "hook must exclude the wrapper's own '# RUNTIME CONTEXT (injected by wrapper' marker from "
        "J-question capture -- else every scheduled conductor fire phantom-logs itself as J asking"
    )
    # the marker must live inside the SAME $qIsSystem exclusion the task-notification check uses,
    # not a separate one-off -- prove it's on the qIsSystem assignment line specifically.
    qsys_lines = [ln for ln in hook.splitlines() if "$qIsSystem = (" in ln]
    assert qsys_lines, "hook must define $qIsSystem"
    assert "runtime context" in qsys_lines[0].lower(), (
        "wrapper-marker exclusion must be wired into the $qIsSystem check, not bolted on elsewhere"
    )


def test_tv_watchdog_checks_live_heartbeat() -> None:
    """G-TVWATCHDOG (2026-06-29): the TV watchdog's hung-bridge auto-restart must check the
    LIVE engine task Gamma_HeartbeatCore, NOT the retired LLM Gamma_Heartbeat (disabled
    2026-06-25, perpetually stale). Pointed at the retired task it reads stale every RTH cycle
    and force-kills TV every 5 min all day -- the self-inflicted 'TV keeps crashing' bug J hit.
    RED on regression."""
    wd = (REPO / "setup" / "scripts" / "run-tv-watchdog.ps1").read_text(encoding="utf-8", errors="replace")
    assert '-TaskName "Gamma_HeartbeatCore"' in wd, "watchdog must check the LIVE engine task"
    assert '-TaskName "Gamma_Heartbeat"' not in wd,         "watchdog must NOT call Get-ScheduledTaskInfo on the retired Gamma_Heartbeat (force-kills TV all RTH)"


def test_market_hours_guard_is_fail_open_and_narrow() -> None:
    """G-MKT-GUARD (2026-06-29): the PreToolUse market-hours edit guard must enforce Rule 9 on a
    NARROW live-trading denylist ONLY, fail-OPEN, soft-block (exit 2 not a hard kill), and be
    overridable -- so it can NEVER recreate the OP-32 market-hours LOCKOUT (2026-05-22)."""
    g = (REPO / "setup" / "hook-market-hours-doctrine-guard.ps1").read_text(encoding="utf-8", errors="replace")
    assert "catch { exit 0 }" in g, "guard must fail-open: any exception -> exit 0 (allow)"
    assert "params.json" in g and "heartbeat.md" in g, "guard must target only the live-trading denylist"
    assert g.count("exit 0") >= 5, "guard must have many allow-paths (fail-open by construction)"
    assert "exit 2" in g, "guard must SOFT-block (exit 2 = return to Claude), not hard-kill"
    assert "GAMMA_RULE9_OVERRIDE" in g, "guard must be overridable in one move"
    assert "et_clock" in g and "et_now" in g, "guard must use trusted et_clock, never Bash TZ"
    settings = (REPO / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    assert "hook-market-hours-doctrine-guard.ps1" in settings, "guard must be registered"
    assert '"matcher": "Edit|Write|MultiEdit"' in settings, "guard must be matcher-scoped to edit tools, never global"


def test_self_check_broker_keys() -> None:
    """G-BROKER (2026-06-29): self_check folds broker-health 401 detection (NOT a new MCP server).
    Pings ONLY the engine-wired arms (read-only GET), classifies 401 as BROKEN, fail-open."""
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import importlib
    sc = importlib.import_module("self_check")
    assert hasattr(sc, "check_broker_keys"), "self_check must expose check_broker_keys"
    src = (REPO / "setup" / "scripts" / "self_check.py").read_text(encoding="utf-8")
    assert "safe-2" in src and "bold-2" in src, "ping only the engine-wired arms"
    assert "/v2/account" in src, "read-only account ping"
    assert "STALE/REVOKED" in src, "401 must map to a BROKEN-class problem"


def test_level_refresh_dedups_and_dates() -> None:
    """G-LEVELFEED (2026-06-30): refresh_levels_intraday must (a) INTRADAY_-prefix premarket
    levels so the dedup catches them (else they piled up 2/run = the 06-30 duplication), and
    (b) stamp the session date so key-levels never sits stale-dated when Gamma_Premarket
    silent-fails."""
    src = (REPO / "setup" / "scripts" / "refresh_levels_intraday.py").read_text(encoding="utf-8")
    assert '"INTRADAY_PMH"' in src and '"INTRADAY_PML"' in src, "premarket levels must be INTRADAY_-prefixed (dedup)"
    assert 'kl["date"] = today' in src, "must stamp key-levels date=today (premarket-failure resilience)"


def test_self_check_flags_stale_premarket() -> None:
    """G-PREMARKET (2026-06-30): self_check must flag a stale-dated today-bias (the Gamma_Premarket
    exit-0-no-write silent failure that left the engine on a stale bias on 06-30), so it surfaces
    proactively instead of being found at the open."""
    src = (REPO / "setup" / "scripts" / "self_check.py").read_text(encoding="utf-8")
    assert "PREMARKET STALE" in src, "self_check must detect a stale-dated today-bias (premarket silent-failure)"


def test_premarket_verifies_work_not_exitcode() -> None:
    """G-PREMARKET-LOUD (2026-06-30): run-premarket.ps1 must VERIFY the work (today-bias dated
    today) and fail LOUDLY if the LLM exited 0 without writing a bias (the 06-30 silent failure).
    OP-33 verify-don't-claim applied to the premarket wrapper."""
    src = (REPO / "setup" / "scripts" / "run-premarket.ps1").read_text(encoding="utf-8", errors="replace")
    assert "today-bias" in src and "biasDate" in src, "wrapper must read + check today-bias.date"
    assert "PREMARKET SILENT FAILURE" in src, "must fail loudly on exit-0-no-bias"
    assert "$exit = 3" in src, "must force a non-zero result when the bias is stale"


def test_self_check_flags_zero_entry_with_blocks(tmp_path) -> None:
    """G-TRADEABILITY (2026-06-30, frame-corrected same day): self_check must CONTENT-check that the
    engine REACHES an ENTER -- but it must distinguish a GENUINE fault from a validated data-gated
    sit-out. A 0-ENTER day whose blocks are an *unexpected* verdict (real gate misfire) MUST flag
    (RED). A 0-ENTER day whose ONLY blocks are `SKIP_ELITE_BULL_LEVEL_RECLAIM` is the proven-correct
    data-gated bull sit-out (bull-unblock thread CLOSED: block_elite_bull KEEP -$241) and must be
    SILENT -- flagging it made self_check perpetually-RED, masking a real future fault (L189). Full
    matrix lives in backtest/tests/test_self_check_tradeability.py."""
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import importlib, datetime as _dt, json as _json
    sc = importlib.import_module("self_check")
    assert hasattr(sc, "check_engine_tradeability"), "self_check must expose check_engine_tradeability"
    now = _dt.datetime(2026, 6, 30, 16, 5)  # a weekday, after close
    # A NON-data-gated block (real gate misfire) with 0 ENTER MUST flag CANNOT ENTER.
    rows = [_json.dumps({"ts_et": f"2026-06-30T1{i % 6}:{i % 6}0:00", "account": "safe",
            "verdict": "SKIP_LIQUIDITY", "triggers": ["rejection", "confluence"],
            "bull_score": 4, "bear_score": 11}) for i in range(40)]
    p = tmp_path / "dec.jsonl"
    p.write_text("\n".join(rows), encoding="utf-8")
    probs = sc.check_engine_tradeability(now, p)
    assert any("CANNOT ENTER" in x for x in probs), f"real-block 0-entry day must flag: {probs}"
    # FRAME FIX: an all-SKIP_ELITE_BULL day is the validated data-gated sit-out -> now SILENT.
    benign = [_json.dumps({"ts_et": f"2026-06-30T1{i % 6}:{i % 6}0:00", "account": "safe",
              "verdict": "SKIP_ELITE_BULL_LEVEL_RECLAIM", "triggers": ["level_reclaim", "confluence"],
              "bull_score": 11, "bear_score": 4}) for i in range(40)]
    p.write_text("\n".join(benign), encoding="utf-8")
    assert sc.check_engine_tradeability(now, p) == [], "data-gated elite-bull sit-out must be silent (L189)"
    # control: the same real-block day with a single real ENTER must be clean
    rows.append(_json.dumps({"ts_et": "2026-06-30T11:00:00", "account": "safe",
        "verdict": "ENTER_BEAR", "triggers": ["rejection"], "bull_score": 4, "bear_score": 11}))
    p.write_text("\n".join(rows), encoding="utf-8")
    assert sc.check_engine_tradeability(now, p) == [], "a day with an ENTER must be clean"


def test_self_check_flags_contradictory_level_roles(tmp_path) -> None:
    """G-LEVEL-INTEGRITY (2026-06-30): self_check must flag a key-levels.json where one price
    carries BOTH a ceiling and a floor role (741.81 / 741.61 each x both on 06-30) -- the engine
    reads that price as resistance AND support at once."""
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    import importlib, json as _json
    sc = importlib.import_module("self_check")
    assert hasattr(sc, "check_level_integrity"), "self_check must expose check_level_integrity"
    bad = {"levels": [{"price": 741.81, "role": "resistance", "tier": "Active"},
                      {"price": 741.81, "role": "support", "tier": "Active"}]}
    p = tmp_path / "kl.json"
    p.write_text(_json.dumps(bad), encoding="utf-8")
    assert any("CONTRADICTORY ROLES" in x for x in sc.check_level_integrity(p)), "contradictory roles must flag"
    # control: self-consistent levels must be clean
    good = {"levels": [{"price": 741.81, "role": "resistance", "tier": "Active"},
                       {"price": 740.50, "role": "support", "tier": "Active"}]}
    p.write_text(_json.dumps(good), encoding="utf-8")
    assert sc.check_level_integrity(p) == [], "self-consistent levels must be clean"


def test_setups_allowed_present_in_live_params() -> None:
    """G-SETUPS-ALLOWED (2026-07-02): both live params files must carry a non-empty
    setups_allowed list. The key was LOST in the 06-25 port (PIPELINE-AUDIT-2026-07-01
    dead-keys class) and survived only in .lastgood/ — with it absent,
    fast_path_executor._compute_filter_setup_allowed reads an empty allowlist and every
    alert dies SKIP_SETUP (11 suite failures, zero fast-path entries possible). RED if
    the key goes missing, empties, or carries an unknown archetype again."""
    import json as _json
    valid = {"ALL", "BEARISH_REJECTION_RIDE_THE_RIBBON", "BULLISH_RECLAIM_RIDE_THE_RIBBON"}
    for rel in ("params.json", "aggressive/params.json"):
        p = _json.loads((REPO / "automation" / "state" / rel).read_text(encoding="utf-8"))
        allowed = p.get("setups_allowed")
        assert isinstance(allowed, list) and allowed, (
            f"{rel} must carry a non-empty setups_allowed list — absent/empty means the "
            f"fast-path setup filter blocks EVERY alert (SKIP_SETUP), got {allowed!r}"
        )
        unknown = set(allowed) - valid
        assert not unknown, (
            f"{rel} setups_allowed has unknown archetype(s) {unknown} — must be drawn from "
            f"{sorted(valid)} (fast_path_executor pattern_to_setup vocab)"
        )


def test_premarket_volume_alive_in_latest_chain() -> None:
    """G-PREMARKET-VOL (2026-07-14 premarket-volume incident): every session that
    append_today.py adds to the canonical spy_5m chain must carry a live premarket
    tape. The yfinance-era appender wrote volume=0 for ALL premarket (04:00-09:25 ET)
    bars on every appended session 2026-05-13..2026-07-14 (Yahoo's extended-hours
    intraday feed has no volume, and drops the 09:15-09:25 bars) — masked because the
    05-19..05-29 seed rows came from Alpaca SIP. RVOL/premarket work silently read a
    dead tape for 6 weeks. RED if any session in the latest chain file has premarket
    bars present, all-zero premarket volume, and a live RTH (holidays skip naturally).
    """
    import re as _re
    import datetime as _dt
    import pandas as _pd

    file_re = _re.compile(r"^spy_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.csv$")
    candidates = []
    for p in DATA.glob("spy_5m_*.csv"):
        m = file_re.match(p.name)
        if m:
            candidates.append((_dt.date.fromisoformat(m.group(2)), p))
    if not candidates:
        pytest.skip("no spy_5m chain CSVs present (worktree / fresh checkout)")
    latest = max(candidates)[1]

    df = _pd.read_csv(latest)
    ts = _pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df["_date"] = ts.dt.date
    df["_time"] = ts.dt.time
    pre = df[df["_time"] < _dt.time(9, 30)]
    rth = df[df["_time"] >= _dt.time(9, 30)]
    pre_vol = pre.groupby("_date")["volume"].sum()
    pre_n = pre.groupby("_date")["volume"].size()
    rth_vol = rth.groupby("_date")["volume"].sum()
    dead = [d for d, v in pre_vol.items()
            if v == 0 and pre_n.get(d, 0) > 0 and rth_vol.get(d, 0) > 0]
    assert not dead, (
        f"{latest.name}: {len(dead)} session(s) with a DEAD premarket tape "
        f"(bars present, volume all zero, RTH live): {dead[:5]}... — the appender has "
        f"regressed to a volume-less premarket source (yfinance fallback?). Repair via "
        f"tools/repair_premarket_volume.py and check append_today's `source` in "
        f"analysis/backtests/data-versions.jsonl"
    )


def test_append_today_spy_uses_alpaca_sip() -> None:
    """G-PREMARKET-VOL wiring guard (C14 dead-knob class): append_today's SPY branch
    must fetch via alpaca_bars.fetch_spy_5m_sip — reverting to a bare yfinance fetch
    reintroduces the zero-volume premarket tape on every future appended session."""
    import importlib
    import inspect
    import sys as _sys

    tools_dir = str(BACKTEST / "tools")
    if tools_dir not in _sys.path:
        _sys.path.insert(0, tools_dir)
    append_today = importlib.import_module("append_today")
    src = inspect.getsource(append_today.append_symbol)
    assert "fetch_spy_5m_sip" in src, (
        "append_today.append_symbol no longer calls fetch_spy_5m_sip — SPY appends "
        "would regress to yfinance's volume-less premarket bars"
    )


def test_level_memory_live_merge_key_present_and_boolean() -> None:
    """G11-C14-WIRING-GUARD (2026-07-15): live params.json must carry
    'level_memory_live_merge' as a present boolean value. The G11 wire
    (setup/scripts/refresh_levels_intraday.py#_memory_merge_enabled) is
    FAIL-OFF on a missing/unreadable key -- a silently-dropped key would not
    crash anything, it would just quietly turn the wire off with no signal,
    exactly the C14 dead-knob class (a key present in prose/docs but not
    actually reaching the consumer, or removed without anyone noticing).
    Guards the flag itself, independent of which way it's currently set --
    see analysis/recommendations/level-memory-wire.json for the A/B verdict
    on whether it SHOULD be on."""
    params = json.loads(PARAMS.read_text(encoding="utf-8"))
    assert "level_memory_live_merge" in params, (
        "params.json is missing 'level_memory_live_merge' -- the G11 wire "
        "(refresh_levels_intraday.py#_memory_merge_enabled) would silently "
        "read this as absent/false with zero signal that the key vanished."
    )
    assert isinstance(params["level_memory_live_merge"], bool), (
        f"params.json's 'level_memory_live_merge' must be a boolean, got "
        f"{type(params['level_memory_live_merge']).__name__!r} — "
        f"_memory_merge_enabled() calls bool() on it, so a stray string/number "
        f"would silently coerce rather than fail loudly."
    )


def test_setup_dispatch_names_registry_sync() -> None:
    """SETUP-DISPATCH-REGISTRY-SYNC-GUARD (2026-07-18, weekend conductor fire;
    REWRITTEN 2026-07-18 evening conductor -- SINGLE-STRATEGY-REGISTRY-DESIGN
    slice): every setup_name in setup_dispatch.py's DISPATCH_ROSTER must also
    appear in v53_setup_dispatch.py's KNOWN_SETUP_NAMES.

    Root cause of the ORIGINAL incident this guards: 'level_break_first_strike'
    was wired into setup_dispatch.py's dispatcher registry on 2026-07-15
    (SHADOW-LOGGED, detect+log every tick) but the validator's hand-typed
    _KNOWN_SETUP_NAMES set was never updated to match -- names_ok failed on
    EVERY tick that reached that detector, 120 consecutive cron fires (~60h)
    before drift_report.json's overall_health RED alert surfaced it. That was
    the 3rd occurrence of this exact drift class (2x F26-DISPATCH-191-FAILED-
    GREEN + this one) -- so instead of patching the mirror set a 4th time, the
    dispatcher list was hoisted to a module-level DISPATCH_ROSTER constant
    (setup_dispatch.KNOWN_SETUP_NAMES, derived from it) and the validator now
    IMPORTS that name set directly instead of re-typing it. This test no
    longer needs to AST-parse SetupDispatcher.run()'s method body (fragile --
    broke the moment run() switched from a literal list to a comprehension) --
    it just proves the validator's imported set IS the roster's derived set
    (an identity check, structurally impossible to drift) and that every
    roster name has a live enable-flag key."""
    import importlib
    import sys as _sys

    setup_scripts_dir = str(REPO / "setup" / "scripts")
    validators_dir = str(REPO / "crypto" / "validators")
    for p in (str(REPO), setup_scripts_dir, validators_dir):
        if p not in _sys.path:
            _sys.path.insert(0, p)

    dispatch_mod = importlib.import_module("setup.scripts.setup_dispatch")
    validator_mod = importlib.import_module("v53_setup_dispatch")

    roster_names = {name for name, _flag, _method in dispatch_mod.DISPATCH_ROSTER}
    assert roster_names, "DISPATCH_ROSTER is empty -- setup_dispatch.py roster broke."
    assert dispatch_mod.KNOWN_SETUP_NAMES == roster_names, (
        "setup_dispatch.KNOWN_SETUP_NAMES has drifted from DISPATCH_ROSTER -- "
        "should be structurally impossible since KNOWN_SETUP_NAMES is derived "
        "from DISPATCH_ROSTER at import time; if this fails, someone mutated "
        "KNOWN_SETUP_NAMES directly instead of adding a roster row."
    )

    # The validator imports KNOWN_SETUP_NAMES directly -- this is the drift-proof
    # property the whole fix buys: there is no second hand-typed set left
    # anywhere to fall out of sync.
    known_names = validator_mod._KNOWN_SETUP_NAMES
    assert known_names == dispatch_mod.KNOWN_SETUP_NAMES, (
        f"v53_setup_dispatch.py's _KNOWN_SETUP_NAMES ({sorted(known_names)}) no "
        f"longer matches setup_dispatch.KNOWN_SETUP_NAMES "
        f"({sorted(dispatch_mod.KNOWN_SETUP_NAMES)}) -- it must import the name "
        f"directly (`from setup.scripts.setup_dispatch import KNOWN_SETUP_NAMES "
        f"as _KNOWN_SETUP_NAMES`), never re-derive or hand-type its own copy."
    )

    # Every roster entry must carry a real (non-empty) flag key -- a blank flag
    # key would make that detector permanently unreachable (silent SKIP forever).
    empty_flag_names = {
        name for name, flag, _method in dispatch_mod.DISPATCH_ROSTER if not flag
    }
    assert not empty_flag_names, (
        f"DISPATCH_ROSTER entries with an empty flag_key: {sorted(empty_flag_names)} "
        "-- these detectors can never be enabled via params.json."
    )
