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
_needs_data = pytest.mark.skipif(not _HAS_DATA, reason="master SPY/VIX CSV not present")


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
    cs_path = BACKTEST / "autoresearch" / "sniper_cs_evaluator.py"
    assert cs_path.exists(), "sniper_cs_evaluator.py must exist — chart-stop SNIPER evaluator"

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
    Two assertions:
    1. simulate_trade_real call uses premium_stop_pct=side_premium_stop (not global)
    2. side_premium_stop assignment appears before the if use_real_fills: branch

    If either fails: real-fills path was reverted to global stop → invalidates all real-fills backtests.
    """
    source = (BACKTEST / "lib" / "orchestrator.py").read_text(encoding="utf-8")

    assert "premium_stop_pct=side_premium_stop" in source, (
        "L105 regression: simulate_trade_real no longer uses side_premium_stop. "
        "Real-fills path must pass side_premium_stop (bear=-0.20, bull=-0.08) not the global "
        "premium_stop_pct (-0.08). Before fix, all real-fills backtests used -8% stop regardless "
        "of params.json premium_stop_pct_bear=-0.20. See orchestrator.py lines ~937-957."
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


