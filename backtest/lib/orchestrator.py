"""Orchestrator — wires data + ribbon + filters + pricing + simulator into a backtest run.

Public API:
    run_backtest(spy_df, vix_df, start_date, end_date) -> BacktestResult

Algorithm:
    For each 5-min bar in spy_df between start_date and end_date:
      1. If insufficient ribbon warmup → skip.
      2. Build BarContext (ribbon state, vix, levels, htf alignment).
      3. Evaluate BEARISH_REJECTION_RIDE_THE_RIBBON filters.
      4. If passed → simulate the bracket trade forward.
      5. After exit, jump bar pointer past the exit bar (no re-entry until flat).
      6. Always log the per-bar decision (action, scores, blockers) for analysis.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .ribbon import compute_ribbon, ribbon_at, RibbonState
from .filters import (
    BarContext, evaluate_bearish_setup, evaluate_bullish_setup,
    vol_baseline_20bar, range_baseline_20bar,
    LevelState,
)
from .levels import _detect_from_history, LevelSet
from .simulator import simulate_trade, TradeFill
from .simulator_real import simulate_trade_real


def _update_level_states(
    level_states: dict,
    levels_active: list[float],
    bar: pd.Series,
    bar_idx: int,
    break_threshold: float = 0.10,
    retest_proximity: float = 0.30,
) -> None:
    """Maintain per-level role + bounce_history across bars (NEW 2026-05-07).

    Mutates level_states in place. Called per-bar before evaluate_bearish_setup
    so the sequence_rejection trigger has live data.

    Algorithm:
      For each level price L active this bar:
        - Ensure LevelState exists in level_states (create if missing).
        - If level is currently `role: None` (untouched/intact):
          * If bar.close < (L - break_threshold): role flips to broken_to_resistance,
            broken_at_bar_idx = bar_idx, bounce_history reset to [].
          * If bar.close > (L + break_threshold): role flips to broken_to_support
            (mirror), broken_at_bar_idx = bar_idx, bounce_history reset to [].
        - If level is currently `role: broken_to_resistance` (price below it now):
          * If bar.high reaches within retest_proximity of L from below
            (i.e., bar.high > L - retest_proximity AND bar.close <= L):
            append a bounce entry {bar_idx, high_reached: bar.high,
            outcome: "rejected_close_below" or "broken_back_through" if close > L}.
          * If bar.close > L + break_threshold (definitive reclaim from below):
            role flips back to None or to broken_to_support if continues higher.
        - Mirror for broken_to_support.
    """
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])

    for L in levels_active:
        key = f"{L:.4f}"
        if key not in level_states:
            level_states[key] = LevelState(price=float(L))
        st = level_states[key]

        if st.role is None:
            # Intact level — check for break
            if close < L - break_threshold:
                st.role = "broken_to_resistance"
                st.broken_at_bar_idx = bar_idx
                st.bounce_history = []
            elif close > L + break_threshold:
                st.role = "broken_to_support"
                st.broken_at_bar_idx = bar_idx
                st.bounce_history = []
        elif st.role == "broken_to_resistance":
            # Price below the level — track retests from below
            if high > L - retest_proximity:
                outcome = (
                    "broken_back_through" if close > L + break_threshold
                    else "rejected_close_below"
                )
                # Only append if last entry isn't this exact bar (idempotent)
                last = st.bounce_history[-1] if st.bounce_history else None
                if last is None or last.get("bar_idx") != bar_idx:
                    st.bounce_history.append({
                        "bar_idx": bar_idx,
                        "high_reached": high,
                        "outcome": outcome,
                    })
                if outcome == "broken_back_through":
                    # Definitive reclaim — role resets
                    st.role = None
                    st.broken_at_bar_idx = None
                    st.bounce_history = []
        elif st.role == "broken_to_support":
            # Price above the level — track retests from above
            if low < L + retest_proximity:
                outcome = (
                    "broken_back_through" if close < L - break_threshold
                    else "rejected_close_above"
                )
                last = st.bounce_history[-1] if st.bounce_history else None
                if last is None or last.get("bar_idx") != bar_idx:
                    st.bounce_history.append({
                        "bar_idx": bar_idx,
                        "low_reached": low,
                        "outcome": outcome,
                    })
                if outcome == "broken_back_through":
                    st.role = None
                    st.broken_at_bar_idx = None
                    st.bounce_history = []


@dataclass
class BacktestResult:
    """Aggregated output of a backtest run."""
    trades: list[TradeFill]
    decisions: list[dict]  # one row per bar evaluated (filter scores, action)
    metadata: dict


def _align_vix_to_spy(spy_df: pd.DataFrame, vix_df: pd.DataFrame) -> pd.Series:
    """Reindex VIX bars onto SPY's bar timestamps (forward-fill).

    Sometimes VIX has fewer bars (different trading hours). We forward-fill so each
    SPY bar has a VIX value.

    Defensive dedup: data CSVs occasionally contain duplicate rows with
    subtly-different timezone format strings (`-04:00` vs `-0400`); dedup
    before reindex prevents `cannot reindex on an axis with duplicate labels`.
    autoresearch.runner.load_data dedupes upstream, but run.py's raw CSV
    loader doesn't, so we belt-and-suspenders here.
    """
    spy_ts = pd.to_datetime(spy_df["timestamp_et"], utc=True)
    vix_ts = pd.to_datetime(vix_df["timestamp_et"], utc=True)
    vix_indexed = pd.Series(vix_df["close"].values, index=vix_ts)
    if not vix_indexed.index.is_unique:
        vix_indexed = vix_indexed[~vix_indexed.index.duplicated(keep="first")]
    if not spy_ts.is_unique:
        spy_ts = spy_ts.drop_duplicates(keep="first")
    aligned = vix_indexed.reindex(spy_ts, method="ffill")
    aligned.index = range(len(aligned))
    return aligned


def _compute_htf_15m_stack(spy_5m: pd.DataFrame, idx_5m: int) -> Optional[str]:
    """Approximate the 15-min ribbon stack at 5-min bar index `idx_5m`.

    Build a 15-min bar series from 5-min bars (every 3 bars), compute ribbon, return stack.
    Returns None if insufficient data.

    NOTE (2026-05-08): This per-bar implementation is O(n) per call → O(n²) over a
    full backtest. `_precompute_htf_15m_stacks(spy_df)` is the vectorised version
    used inside `run_backtest`. This function is kept for direct callers
    that pass single bar indices and for backward compatibility.
    """
    # Identify which 15-min bar this 5-min bar belongs to
    if idx_5m < 60:  # need warmup
        return None
    sub = spy_5m.iloc[:idx_5m + 1].copy()
    sub["ts"] = pd.to_datetime(sub["timestamp_et"])
    # Resample to 15-min by grouping every 3 bars (ET-aligned)
    # Simpler: floor to 15-min boundary and aggregate
    sub.set_index("ts", inplace=True)
    bars_15m = sub.resample("15min", label="left", closed="left").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
    }).dropna()
    if len(bars_15m) < 50:  # need warmup for slow EMA(48)
        return None
    ribbon_15m = compute_ribbon(bars_15m["close"])
    last_state = ribbon_at(ribbon_15m, ribbon_15m.index[-1])
    return last_state.stack if last_state is not None else None


def _precompute_htf_15m_stacks(spy_df: pd.DataFrame) -> list[Optional[str]]:
    """Precompute the 15-min ribbon stack for every 5-min bar in spy_df.

    Vectorised replacement for `_compute_htf_15m_stack`. Returns a list of
    length `len(spy_df)` where `stacks[i]` is the 15-min ribbon stack value
    visible AT (or BEFORE) 5-min bar i. None when insufficient warmup.

    Speed: O(n log n) total vs O(n²) for repeated calls to the per-bar version.
    On 30,000 bars this changes baseline backtest time from ~20 min to ~5 sec.
    """
    n = len(spy_df)
    stacks: list[Optional[str]] = [None] * n
    if n < 60:
        return stacks
    df = spy_df.copy()
    df["ts"] = pd.to_datetime(df["timestamp_et"])
    df_indexed = df.set_index("ts")
    bars_15m = df_indexed.resample("15min", label="left", closed="left").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
    }).dropna()
    if len(bars_15m) < 50:
        return stacks
    ribbon_15m = compute_ribbon(bars_15m["close"])

    # For each 5-min bar, find the most recent 15-min bar at or before it.
    spy_ts = pd.to_datetime(df["timestamp_et"]).values
    bars_15m_ts = bars_15m.index.values
    # Bulk searchsorted (vectorised) — gives position of each 5m ts in the 15m index.
    positions = np.searchsorted(bars_15m_ts, spy_ts, side="right") - 1
    # Cache stack values per 15m bar to avoid repeated dataframe lookups.
    stack_cache: dict[int, Optional[str]] = {}
    for i in range(60, n):
        pos = int(positions[i])
        if pos < 49:  # 50-bar warmup for slow EMA(48)
            continue
        if pos in stack_cache:
            stacks[i] = stack_cache[pos]
            continue
        state = ribbon_at(ribbon_15m, bars_15m.index[pos])
        stack_val = state.stack if state is not None else None
        stack_cache[pos] = stack_val
        stacks[i] = stack_val
    return stacks


def _params_to_kwargs(overrides: dict, account_equity: Optional[float] = None) -> dict:
    """Translate a params.json-shaped overrides dict to run_backtest kwargs.

    Used by Karpathy shadow mode (lib/shadow.py) and any tool that wants to
    override production params with a single dict argument. The mapping is
    intentionally one-way (params.json key → orchestrator kwarg) so the public
    config surface (params.json) stays canonical.

    Unknown keys are silently ignored — overrides that target params.json
    fields the orchestrator doesn't consume (e.g., dashboard polling rate)
    are no-ops here, not errors.

    account_equity: when provided alongside a params dict that contains
        ``v15_strike_offset_per_tier``, the per-tier table is used to pick
        the correct strike offset for the simulated equity level (T-09 fix).
        Without this, the static ``strike_offset_itm`` field is used (legacy
        behaviour, always ITM-2 regardless of account size).
    """
    if not overrides:
        return {}
    kwargs: dict = {}
    if "premium_stop_pct" in overrides:
        kwargs["premium_stop_pct"] = overrides["premium_stop_pct"]
    if "tp1_premium_pct" in overrides:
        kwargs["tp1_premium_pct"] = overrides["tp1_premium_pct"]
    if "tp1_qty_fraction" in overrides:
        kwargs["tp1_qty_fraction"] = overrides["tp1_qty_fraction"]
    if "runner_max_premium_pct" in overrides:
        kwargs["runner_target_premium_pct"] = overrides["runner_max_premium_pct"]
    if "filter_9_vol_multiplier" in overrides:
        kwargs["f9_vol_mult"] = overrides["filter_9_vol_multiplier"]
    if "filter_10_min_triggers_bear" in overrides:
        kwargs["min_triggers_bear"] = overrides["filter_10_min_triggers_bear"]
    if "filter_10_min_triggers_bull" in overrides:
        kwargs["min_triggers_bull"] = overrides["filter_10_min_triggers_bull"]
    # --- T-09 (2026-05-18): per-tier equity-based strike selection ---
    # params_safe.json / params_bold.json carry v15_strike_offset_per_tier with the
    # per-equity-tier OTM/ITM ladder.  When account_equity is supplied, use that table
    # so backtests model the CORRECT strike for the account size being simulated.
    # Falls back to static strike_offset_itm when the table is absent or equity unknown.
    if "v15_strike_offset_per_tier" in overrides and account_equity is not None:
        from crypto.lib.strike_selection import StrikeTier, pick_tier  # noqa: PLC0415
        tiers = tuple(
            StrikeTier(
                equity_min=float(t["equity_min"]),
                equity_max=float(t["equity_max"]),
                strike_offset=int(t["strike_offset"]),
                label=str(t.get("label", "")),
            )
            for t in overrides["v15_strike_offset_per_tier"]
        )
        tier = pick_tier(account_equity, tiers)
        # simulator_real.py uses opposite sign convention (atm - offset for puts),
        # so negate: crypto/lib/strike_selection positive=ITM → simulator negative=ITM
        kwargs["strike_offset"] = -tier.strike_offset
    elif "strike_offset_itm" in overrides:
        # Legacy path: single static value from params.json (always used when no equity
        # or no per-tier table). params.json uses positive offset for ITM (2 = $2 ITM);
        # orchestrator passes negative to simulator (strike_offset=-2 = ITM-2 for puts).
        kwargs["strike_offset"] = -abs(overrides["strike_offset_itm"])
    if "entry_no_trade_before_et" in overrides:
        hh, mm = overrides["entry_no_trade_before_et"].split(":")
        kwargs["no_trade_before"] = dt.time(int(hh), int(mm))
    if "entry_no_trade_window_et" in overrides and overrides["entry_no_trade_window_et"]:
        s, e = overrides["entry_no_trade_window_et"]
        sh, sm = s.split(":")
        eh, em = e.split(":")
        kwargs["no_trade_window"] = (dt.time(int(sh), int(sm)), dt.time(int(eh), int(em)))
    # v15.3 RIBBON CONVICTION GATE — mapped from params.json via params_overrides
    if "min_ribbon_momentum_cents" in overrides:
        kwargs["min_ribbon_momentum_cents"] = float(overrides["min_ribbon_momentum_cents"])
    if "max_ribbon_duration_bars" in overrides:
        kwargs["max_ribbon_duration_bars"] = int(overrides["max_ribbon_duration_bars"])
    if "midday_trendline_gate" in overrides:
        kwargs["midday_trendline_gate"] = bool(overrides["midday_trendline_gate"])
    # Asymmetric premium stops (v15: bear -20% / bull -8%). Bugfix 2026-06-14:
    # premium_stop_pct_bear/bull were never mapped, so params.json's bear stop
    # could not reach the engine (same dead-knob class as the ribbon gates).
    if "premium_stop_pct_bear" in overrides:
        kwargs["premium_stop_pct_bear"] = overrides["premium_stop_pct_bear"]
    if "premium_stop_pct_bull" in overrides:
        kwargs["premium_stop_pct_bull"] = overrides["premium_stop_pct_bull"]
    return kwargs


def run_backtest(
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    start_date: Optional[dt.date] = None,
    end_date: Optional[dt.date] = None,
    setup: str = "BEARISH_REJECTION_RIDE_THE_RIBBON",
    disable_filters: Optional[list[int]] = None,
    use_real_fills: bool = False,
    min_triggers: int = 1,            # legacy / fallback when asymmetric not provided
    # --- MIDDAY_TRENDLINE_GATE 2026-05-31 (VALIDATED, kwarg-gated, prod unchanged) ---
    # Blocks 1-trig trendline_rejection in 11:30-14:00 ET. +3.8->+7.2/c per-trade on 307 OOS.
    # Default=False. Enable via params.json "midday_trendline_gate": true after J ratifies (Rule 9).
    midday_trendline_gate: bool = False,
    # --- RIBBON_MOMENTUM_GATE 2026-05-31 (VALIDATED, kwarg-gated, prod unchanged) ---
    # Require ribbon spread widening >= this many cents over last 3 bars.
    # rmom>=10: WR 0.43, +20.2/c on 77 OOS trades (vs base 0.30, +3.7/c, n=312).
    # None = disabled. Ratify via params.json "min_ribbon_momentum_cents": 10 (Rule 9).
    min_ribbon_momentum_cents: Optional[float] = None,
    # --- RIBBON_DURATION_GATE 2026-05-31 (VALIDATED, kwarg-gated, prod unchanged) ---
    # Require ribbon has been stacked <= this many bars (fresh > stale).
    # rdur<=20 + rmom>=10: WR 0.44, +23.6/c on 68 OOS trades.
    # None = disabled. Ratify via params.json "max_ribbon_duration_bars": 20 (Rule 9).
    max_ribbon_duration_bars: Optional[int] = None,
    vix_soft_mode: bool = False,
    allow_one_blocker: bool = False,
    allow_one_blocker_min_spread_cents: int = 0,
    premium_stop_pct: float = -0.08,  # legacy / fallback when asymmetric not provided
    strike_offset: int = -2,          # legacy / fallback when asymmetric not provided
    no_trade_before: Optional[dt.time] = dt.time(10, 0),    # RATIFIED v11
    no_trade_window: Optional[tuple] = (dt.time(14, 0), dt.time(15, 0)),  # RATIFIED v11
    f9_vol_mult: float = 0.7,                                # RATIFIED v11
    enable_bullish: bool = True,                             # RATIFIED v12 — symmetric setup hunting
    # --- NEW 2026-05-09: asymmetric bear/bull params ---
    min_triggers_bear: Optional[int] = None,
    min_triggers_bull: Optional[int] = None,
    premium_stop_pct_bear: Optional[float] = None,
    premium_stop_pct_bull: Optional[float] = None,
    strike_offset_bear: Optional[int] = None,
    strike_offset_bull: Optional[int] = None,
    # --- NEW 2026-05-09: parameterised exits ---
    tp1_premium_pct: float = 0.30,
    tp1_qty_fraction: float = 0.667,
    runner_target_premium_pct: float = 3.0,
    level_stop_buffer_dollars: float = 0.0,
    time_stop_minutes_before_close: int = 10,   # 16:00 ET - this many min = forced exit
    # --- NEW 2026-05-13 v14_enhanced: profit-lock (winners-never-negative) ---
    profit_lock_threshold_pct: float = 0.0,     # 0=off; e.g. 0.10 arm at +10% favorable premium
    profit_lock_stop_offset_pct: float = 0.0,   # where to raise stop when armed (e.g. 0.05 = entry+5%)
    profit_lock_mode: str = "fixed",             # NEW T50b 2026-05-13: 'fixed' | 'trailing' | 'stepped'
    profit_lock_trail_pct: float = 0.0,          # NEW T50b: chandelier trail (e.g. 0.20 = 20% off HWM)
    # --- NEW 2026-05-09: Karpathy shadow mode overrides ---
    params_overrides: Optional[dict] = None,
    # --- NEW 2026-05-18 T-09: initial account equity for per-tier strike selection ---
    # When params_overrides includes v15_strike_offset_per_tier, this value determines
    # which OTM/ITM tier to simulate.  Default 25_000 preserves legacy behaviour
    # (picks the ITM-2 top tier, matching all pre-T-09 scorecards).
    initial_equity: float = 25_000.0,
    # --- NEW: BEARISH_SWEEP_BLOCKER gate (strategy/candidates/2026-05-16-bearish-sweep-blocker.md) ---
    # When True, evaluates sweep patterns on the trigger level and hard-blocks entries
    # where the level was recently swept in the counter-direction (5/14 09:58 misfire class).
    # Default False = no change to existing behavior.
    sweep_blocker_enabled: bool = False,
    sweep_min_wick_pct: float = 0.0003,
    sweep_min_close_back_pct: float = 0.0005,
    sweep_block_window_bars: int = 3,
    sweep_clean_prior_bars: int = 3,
) -> BacktestResult:
    """Run the playbook over historical bars. Returns BacktestResult.

    Args:
        spy_df: SPY 5-min bars. May include premarket (04:00-09:30 ET) — those bars are
            used for level detection (PMH/PML) but NOT for ribbon/baselines (which are
            RTH-only to match the live TradingView indicator).
        vix_df: VIX 5-min bars (any session).
        disable_filters: filter IDs to skip (auto-pass). Use [8] when testing pre-2026-05-05
            historical trades that pre-date the VIX>17.30 rule.
        params_overrides: dict of params.json-shaped overrides. Translated to kwargs
            via _params_to_kwargs and applied AFTER the explicit kwargs (so explicit
            kwargs win over overrides — caller intent is preserved). Used by Karpathy
            shadow mode (lib/shadow.py) to A/B test param changes without editing
            params.json on disk.
    """
    # Apply Karpathy shadow overrides (translates params.json keys to kwargs).
    # Overrides only fill in values that the explicit kwargs left at their default —
    # explicit caller kwargs always win, but defaults can be replaced by an overrides dict.
    if params_overrides:
        ovrk = _params_to_kwargs(params_overrides, account_equity=initial_equity)
        # Only apply override if caller didn't pass an explicit non-default value
        # (best-effort heuristic: compare against orchestrator's own defaults)
        if "premium_stop_pct" in ovrk and premium_stop_pct == -0.08:
            premium_stop_pct = ovrk["premium_stop_pct"]
        if "tp1_premium_pct" in ovrk and tp1_premium_pct == 0.30:
            tp1_premium_pct = ovrk["tp1_premium_pct"]
        if "tp1_qty_fraction" in ovrk and tp1_qty_fraction == 0.667:
            tp1_qty_fraction = ovrk["tp1_qty_fraction"]
        if "runner_target_premium_pct" in ovrk and runner_target_premium_pct == 3.0:
            runner_target_premium_pct = ovrk["runner_target_premium_pct"]
        if "f9_vol_mult" in ovrk and f9_vol_mult == 0.7:
            f9_vol_mult = ovrk["f9_vol_mult"]
        if "min_triggers_bear" in ovrk and min_triggers_bear is None:
            min_triggers_bear = ovrk["min_triggers_bear"]
        if "min_triggers_bull" in ovrk and min_triggers_bull is None:
            min_triggers_bull = ovrk["min_triggers_bull"]
        if "strike_offset" in ovrk and strike_offset == -2:
            strike_offset = ovrk["strike_offset"]
        if "no_trade_before" in ovrk and no_trade_before == dt.time(10, 0):
            no_trade_before = ovrk["no_trade_before"]
        if "no_trade_window" in ovrk and no_trade_window == (dt.time(14, 0), dt.time(15, 0)):
            no_trade_window = ovrk["no_trade_window"]
        # v15.3 ribbon-conviction gates. Bugfix 2026-06-14: these were translated by
        # _params_to_kwargs but never assigned here, so params_overrides could not
        # enable them — backtests silently ran WITHOUT the v15.3 gates that production
        # claims, and the Karpathy shadow A/B could not test them. Now applied (only
        # when the caller left the kwarg at its default, same heuristic as above).
        if "min_ribbon_momentum_cents" in ovrk and min_ribbon_momentum_cents is None:
            min_ribbon_momentum_cents = ovrk["min_ribbon_momentum_cents"]
        if "max_ribbon_duration_bars" in ovrk and max_ribbon_duration_bars is None:
            max_ribbon_duration_bars = ovrk["max_ribbon_duration_bars"]
        if "midday_trendline_gate" in ovrk and midday_trendline_gate is False:
            midday_trendline_gate = ovrk["midday_trendline_gate"]
        if "premium_stop_pct_bear" in ovrk and premium_stop_pct_bear is None:
            premium_stop_pct_bear = ovrk["premium_stop_pct_bear"]
        if "premium_stop_pct_bull" in ovrk and premium_stop_pct_bull is None:
            premium_stop_pct_bull = ovrk["premium_stop_pct_bull"]

    # Resolve asymmetric overrides → fall back to shared values when not provided.
    bear_min_triggers = min_triggers_bear if min_triggers_bear is not None else min_triggers
    bull_min_triggers = min_triggers_bull if min_triggers_bull is not None else max(2, min_triggers)
    bear_premium_stop = premium_stop_pct_bear if premium_stop_pct_bear is not None else premium_stop_pct
    bull_premium_stop = premium_stop_pct_bull if premium_stop_pct_bull is not None else premium_stop_pct
    bear_strike_off = strike_offset_bear if strike_offset_bear is not None else strike_offset
    bull_strike_off = strike_offset_bull if strike_offset_bull is not None else strike_offset

    # Convert time_stop_minutes_before_close → dt.time
    _close_minute = 16 * 60 - time_stop_minutes_before_close
    time_stop_et = dt.time(_close_minute // 60, _close_minute % 60)

    spy_df_full = spy_df.copy()
    spy_df_full["timestamp_et"] = pd.to_datetime(spy_df_full["timestamp_et"])
    spy_df_full["date"] = spy_df_full["timestamp_et"].dt.date

    if spy_df_full.empty:
        return BacktestResult(trades=[], decisions=[], metadata={"reason": "no_data"})

    # Split: RTH-only (>= 09:30, < 16:00) for ribbon + baselines + evaluation.
    rth_mask = (
        (spy_df_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_df_full["timestamp_et"].dt.time < dt.time(16, 0))
    )
    spy_df = spy_df_full.loc[rth_mask].reset_index(drop=True)
    if spy_df.empty:
        return BacktestResult(trades=[], decisions=[], metadata={"reason": "no_rth_data"})

    # Compute ribbon on RTH-only bars (matches the live indicator computation).
    ribbon_df = compute_ribbon(spy_df["close"])
    vix_aligned = _align_vix_to_spy(spy_df, vix_df)
    # Precompute 15-min HTF stack lookup once (was O(n²) per-bar before 2026-05-08).
    htf_stacks_precomputed = _precompute_htf_15m_stacks(spy_df)

    # PERF FIX 2026-05-24: level-per-day cache.
    # _detect_from_history is O(n) per call and was called for EVERY bar, giving O(n²)
    # total — the overnight_grinder ran 43+ min/combo on a 17-month window.
    # Levels are constant within a day (based on prior days + today's premarket only,
    # not today's RTH bars), so computing once per day and caching is semantically
    # identical. Gives ~78× speedup on wide-window sweeps (~10 min → ~8 sec/combo).
    _level_per_day: dict[dt.date, "LevelSet"] = {}

    trades: list[TradeFill] = []
    decisions: list[dict] = []
    skip_until_idx = -1   # while in a trade, skip evaluation until exit bar passed
    level_states: dict = {}  # NEW 2026-05-07: per-level state across bars (role + bounce_history)
    # NEW 2026-05-10 (CLAUDE.md OP 17 GRIND-UNTIL-DONE): per-day, per-setup quality
    # escalation lock. Naive "first-entry blocks all" regressed 5/04 from +$820 to
    # -$51 because a small early trigger blocked the BIG confluence+ribbon_flip trade
    # later. Solution: allow re-entry only on STRICTLY HIGHER QUALITY trigger sets.
    # Maps (date, setup_name) -> quality rank of the highest trade taken today.
    # Quality ranking (numeric, higher is better):
    #   0 = NONE        (no entry yet)
    #   1 = TRENDLINE   (single trigger: trendline_rejection alone)
    #   2 = LEVEL       (single trigger: level_rejection / level_reclaim alone)
    #   3 = ELITE       (2 triggers including confluence OR sequence_rejection)
    #   4 = SUPER       (3+ triggers including confluence + ribbon_flip)
    # Re-entry blocked unless new entry's quality > prior entry's quality.
    setup_quality_taken_today: dict[tuple[dt.date, str], int] = {}
    # Track whether the last fill on this setup STOPPED OUT (didn't hit TP1).
    # Used by leg-2 detection: a stop-out leaves the setup zone confirmed but the
    # timing wrong; the next trigger fire on the same setup is the "leg #2 was
    # real trigger" pattern (J's 5/01 note). Allows same-quality re-entry only
    # when the prior fill stopped — a winner doesn't get a free re-entry.
    setup_last_stopped_today: dict[tuple[dt.date, str], bool] = {}
    # Tracks the timestamp of the most recent exit per (date, setup) for the
    # leg-2 minimum-gap gate (45min between trendline trades).
    setup_last_exit_time_today: dict[tuple[dt.date, str], pd.Timestamp] = {}
    last_seen_date: dt.date | None = None

    for idx in range(len(spy_df)):
        if idx <= skip_until_idx:
            continue

        bar = spy_df.iloc[idx]
        bar_time = bar["timestamp_et"]
        bar_time_py = bar_time.to_pydatetime() if hasattr(bar_time, "to_pydatetime") else bar_time

        # Date filter (applied here, AFTER ribbon was computed on full warmup)
        bar_date = bar_time_py.date()
        if start_date is not None and bar_date < start_date:
            continue
        if end_date is not None and bar_date > end_date:
            continue

        # Day-boundary cleanup (free memory + fresh slate per day)
        if last_seen_date is not None and bar_date != last_seen_date:
            for k in [k for k in setup_quality_taken_today if k[0] == last_seen_date]:
                setup_quality_taken_today.pop(k, None)
            for k in [k for k in setup_last_stopped_today if k[0] == last_seen_date]:
                setup_last_stopped_today.pop(k, None)
            for k in [k for k in setup_last_exit_time_today if k[0] == last_seen_date]:
                setup_last_exit_time_today.pop(k, None)
        last_seen_date = bar_date

        # Skip if outside our trading window
        if bar_time_py.time() < dt.time(9, 35) or bar_time_py.time() >= dt.time(15, 50):
            continue

        # Need ribbon warmed up
        ribbon_state = ribbon_at(ribbon_df, idx)
        if ribbon_state is None:
            continue

        # Pull ribbon history for flip detection
        ribbon_history = []
        for j in range(max(0, idx - 4), idx + 1):
            ribbon_history.append(ribbon_at(ribbon_df, j))

        # VIX
        vix_now = float(vix_aligned.iloc[idx])
        vix_prior = float(vix_aligned.iloc[idx - 1]) if idx > 0 else vix_now

        # Baselines
        vol_baseline = vol_baseline_20bar(spy_df, idx)
        range_baseline = range_baseline_20bar(spy_df, idx)

        # Levels — use FULL data (including premarket) so PMH/PML are detected.
        # PERF FIX 2026-05-24: cache per day (levels constant within session).
        if bar_date not in _level_per_day:
            full_history = spy_df_full[spy_df_full["timestamp_et"] <= bar_time]
            _level_per_day[bar_date] = _detect_from_history(full_history, bar_date)
        level_set = _level_per_day[bar_date]

        # Update per-level state (role + bounce_history) — feeds sequence_rejection trigger
        _update_level_states(level_states, level_set.active, bar, idx)

        # HTF 15m stack — O(1) lookup from precomputed table.
        htf_stack = htf_stacks_precomputed[idx]

        ctx = BarContext(
            bar_idx=idx,
            timestamp_et=bar_time_py,
            bar=bar,
            prior_bars=spy_df,
            ribbon_now=ribbon_state,
            ribbon_history=ribbon_history,
            vix_now=vix_now,
            vix_prior=vix_prior,
            vol_baseline_20=vol_baseline,
            range_baseline_20=range_baseline,
            levels_active=level_set.active,
            multi_day_levels=level_set.multi_day,
            htf_15m_stack=htf_stack,
            level_states=level_states,
        )

        result = evaluate_bearish_setup(
            ctx,
            disable_filters=disable_filters,
            min_triggers=bear_min_triggers,
            vix_soft_mode=vix_soft_mode,
            allow_one_blocker=allow_one_blocker,
            allow_one_blocker_min_spread_cents=allow_one_blocker_min_spread_cents,
            no_trade_before=no_trade_before,
            no_trade_window=no_trade_window,
            f9_vol_mult=f9_vol_mult,
            sweep_blocker_enabled=sweep_blocker_enabled,
            sweep_min_wick_pct=sweep_min_wick_pct,
            sweep_min_close_back_pct=sweep_min_close_back_pct,
            sweep_block_window_bars=sweep_block_window_bars,
            sweep_clean_prior_bars=sweep_clean_prior_bars,
        )

        # ASYMMETRIC TRIGGER REQUIREMENT (RATIFIED 2026-05-07): bear can fire on
        # ≥1 trigger (level_rejection alone has 54% WR, profitable). Bull needs
        # ≥2 triggers (level_reclaim alone is only 22% WR; confluence + reclaim = 50%).
        bull_result = None
        if enable_bullish:
            bull_result = evaluate_bullish_setup(
                ctx,
                disable_filters=disable_filters,
                min_triggers=bull_min_triggers,
                no_trade_before=no_trade_before,
                no_trade_window=no_trade_window,
                f10_vol_mult=f9_vol_mult,
                sweep_blocker_enabled=sweep_blocker_enabled,
                sweep_min_wick_pct=sweep_min_wick_pct,
                sweep_min_close_back_pct=sweep_min_close_back_pct,
                sweep_block_window_bars=sweep_block_window_bars,
                sweep_clean_prior_bars=sweep_clean_prior_bars,
            )

        # Always log the decision
        decisions.append({
            "bar_idx": idx,
            "timestamp_et": bar_time,
            "spy_close": float(bar["close"]),
            "vix": vix_now,
            "ribbon_stack": ribbon_state.stack,
            "ribbon_spread_cents": ribbon_state.spread_cents,
            "htf_15m_stack": htf_stack,
            "bear_score": result.bear_score,
            "blockers": result.blockers,
            "triggers_fired": result.triggers_fired,
            "rejection_level": result.rejection_level,
            "passed": result.passed,
        })

        # ── Decision routing — bear vs bull ──────────────────────────────
        # If both passed (rare — they're directionally exclusive given filter 5),
        # take the higher-trigger-count side. If equal, skip (conflict).
        bear_passed = result.passed
        bull_passed = bull_result is not None and bull_result.passed
        winning_side = None  # "P" or "C"
        winning_triggers = []
        winning_level = None

        if bear_passed and bull_passed:
            if len(result.triggers_fired) > len(bull_result.triggers_fired):
                winning_side = "P"
                winning_triggers = result.triggers_fired
                winning_level = result.rejection_level
            elif len(bull_result.triggers_fired) > len(result.triggers_fired):
                winning_side = "C"
                winning_triggers = bull_result.triggers_fired
                winning_level = bull_result.reclaim_level
            # tied: skip
        elif bear_passed:
            winning_side = "P"
            winning_triggers = result.triggers_fired
            winning_level = result.rejection_level
        elif bull_passed:
            winning_side = "C"
            winning_triggers = bull_result.triggers_fired
            winning_level = bull_result.reclaim_level

        # If a side won → check quality tier and apply position multiplier
        if winning_side is not None:
            setup_name = (
                "BEARISH_REJECTION_RIDE_THE_RIBBON" if winning_side == "P"
                else "BULLISH_RECLAIM_RIDE_THE_RIBBON"
            )

            # ── QUALITY TIER + QTY + ESCALATION LOCK (CLAUDE.md OP 17 GRIND 2026-05-10) ──
            # Three coupled mechanisms that together implement J's pattern of:
            #   "size up on conviction, hold one trade per setup, but allow a strictly
            #   stronger trigger to supersede a weaker one earlier in the day."
            #
            # 1) Quality scoring — numeric rank for the trigger set:
            #      4 SUPER     confluence + ribbon_flip (or 3+ triggers)
            #      3 ELITE     confluence OR sequence_rejection (2 triggers)
            #      2 LEVEL     level_rejection / level_reclaim alone
            #      1 TRENDLINE trendline_rejection alone
            # 2) Qty scaling — qty=10/6/5/3 by quality. J trades 6-20 contracts on his
            #    real winners; the prior 3/5 hardcode left $861 on the table for 5/4
            #    Trade 2 (confluence+ribbon_flip ran 1.30→3.91, qty=5 → +$861 with qty=10
            #    that's ~+$1722). We don't match J's 20-contract days because position
            #    risk caps still apply via per_trade_risk_cap_pct (50% of equity).
            # 3) Escalation lock — block re-entry on this setup today unless the new
            #    trigger set's quality_rank > the highest quality entered today on this
            #    setup. Prevents the churn pattern (3-6 small trendline trades on 5/4
            #    that net to roughly zero) while letting a SUPER trigger supersede an
            #    earlier ELITE/LEVEL/TRENDLINE entry. Naive "first entry locks all" was
            #    tried and rejected — it killed 5/4's BIG confluence+ribbon_flip trade
            #    when an early small trigger fired and locked the rest of the day.
            level_tied_trig = "level_reclaim" if winning_side == "C" else "level_rejection"
            seq_trig = "sequence_reclaim" if winning_side == "C" else "sequence_rejection"
            has_level = level_tied_trig in winning_triggers
            has_confluence = "confluence" in winning_triggers
            has_sequence = seq_trig in winning_triggers
            has_ribbon_flip = "ribbon_flip" in winning_triggers
            has_trendline = "trendline_rejection" in winning_triggers
            n_triggers = len(winning_triggers)

            lock_key = (bar_date, setup_name)
            prior_quality = setup_quality_taken_today.get(lock_key, 0)
            prior_stopped = setup_last_stopped_today.get(lock_key, False)

            if (has_confluence and has_ribbon_flip) or n_triggers >= 3:
                quality_rank, quality_tier, trade_qty = 4, "SUPER", 15
            elif has_confluence or has_sequence:
                quality_rank, quality_tier, trade_qty = 3, "ELITE", 10
            elif has_level:
                _qty_override = globals().get("_grinder_overrides", {}) or {}
                quality_rank, quality_tier, trade_qty = 2, "LEVEL", _qty_override.get("level_qty", 22)
            elif has_trendline:
                # Leg-2 detection: when the prior fill on this setup STOPPED OUT today
                # (didn't hit TP1) and the next trigger is also trendline-only, treat
                # this as the "leg #2 was real trigger" pattern (J's 5/01 note). Same
                # rank, but bigger qty since the first stop confirmed the setup zone.
                # MIN-GAP gate (OP 17 GRIND 2026-05-10): leg-2 must be at least 45min
                # after the prior stop. Back-to-back trendline stops (5/01 13:35 +
                # 13:50) just compound losses; J's "leg 2 was real trigger" comment
                # was about a setup that re-fired LATER in the day, not immediately.
                last_exit_ts = setup_last_exit_time_today.get(lock_key)
                if last_exit_ts is None:
                    gap_ok = True
                else:
                    bt = pd.Timestamp(bar_time)
                    le = pd.Timestamp(last_exit_ts)
                    if bt.tz is not None and le.tz is None:
                        le = le.tz_localize(bt.tz)
                    elif bt.tz is None and le.tz is not None:
                        bt = bt.tz_localize(le.tz)
                    gap_ok = (bt - le).total_seconds() >= 45 * 60
                if prior_stopped and prior_quality == 1 and gap_ok:
                    quality_rank, quality_tier, trade_qty = 1, "TRENDLINE_LEG2", 20
                else:
                    quality_rank, quality_tier, trade_qty = 1, "TRENDLINE", 3
            else:
                # Should not occur (filter requires level_tied trigger), defensive default.
                quality_rank, quality_tier, trade_qty = 1, "BASE", 3

            # Per-day quality escalation lock with leg-2 exemption.
            #   - quality > prior:                                ENTER (escalation)
            #   - quality == prior AND prior_stopped AND gap_ok:   ENTER (leg-2)
            #   - quality == prior AND prior_stopped AND gap fail: BLOCK (no churn)
            #   - quality == prior AND prior won (TP1 hit):        BLOCK (no churn)
            #   - quality < prior:                                 BLOCK (no downgrade)
            #
            # gap_ok: at least 45 minutes since the prior exit. Prevents
            # back-to-back stop-then-stop on TRENDLINE setups (5/01 problem).
            same_quality_gap_ok = True
            if quality_rank == prior_quality and prior_stopped:
                last_exit_ts = setup_last_exit_time_today.get(lock_key)
                if last_exit_ts is not None:
                    # Defensively normalise tz-awareness so we can subtract.
                    bt = pd.Timestamp(bar_time)
                    le = pd.Timestamp(last_exit_ts)
                    if bt.tz is not None and le.tz is None:
                        le = le.tz_localize(bt.tz)
                    elif bt.tz is None and le.tz is not None:
                        bt = bt.tz_localize(le.tz)
                    gap_seconds = (bt - le).total_seconds()
                    same_quality_gap_ok = gap_seconds >= 45 * 60
            allow_entry = (
                quality_rank > prior_quality
                or (quality_rank == prior_quality and prior_stopped and same_quality_gap_ok)
            )
            if not allow_entry:
                # Match the schema of the standard decision row (added a few lines
                # above this branch by the bear-eval block) so audit code that
                # iterates decisions[] doesn't KeyError on our skip rows. The
                # standard row was already appended with passed=True; we add an
                # extra key recording why we skipped despite passing filters.
                decisions.append({
                    "bar_idx": idx,
                    "timestamp_et": bar_time,
                    "spy_close": float(bar["close"]),
                    "vix": vix_now,
                    "ribbon_stack": ribbon_state.stack,
                    "ribbon_spread_cents": ribbon_state.spread_cents,
                    "htf_15m_stack": htf_stack,
                    "bear_score": result.bear_score,
                    "blockers": result.blockers,
                    "triggers_fired": winning_triggers,
                    "rejection_level": winning_level,
                    "passed": True,
                    "action": "SKIP_QUALITY_LOCK",
                    "setup": setup_name,
                    "quality_tier": quality_tier,
                    "quality_rank": quality_rank,
                    "prior_quality": prior_quality,
                    "prior_stopped": prior_stopped,
                    "reason": "blocked by quality lock (downgrade or same-quality after winner)",
                })
                continue
            setup_quality_taken_today[lock_key] = max(prior_quality, quality_rank)

            # RIBBON_MOMENTUM_GATE: spread widening >= threshold over 3 bars.
            # "Ribbon spreading apart = trend accelerating" — what J sees on the chart.
            if min_ribbon_momentum_cents is not None and idx >= 3:
                _prev_st = ribbon_at(ribbon_df, idx - 3)
                if _prev_st is not None:
                    _rmom = ribbon_state.spread_cents - _prev_st.spread_cents
                    if _rmom < min_ribbon_momentum_cents:
                        decisions.append({
                            "bar_idx": idx, "timestamp_et": bar_time,
                            "spy_close": float(bar["close"]), "vix": vix_now,
                            "ribbon_stack": ribbon_state.stack,
                            "ribbon_spread_cents": ribbon_state.spread_cents,
                            "htf_15m_stack": htf_stack, "bear_score": result.bear_score,
                            "blockers": ["RIBBON_MOMENTUM_GATE"],
                            "triggers_fired": winning_triggers,
                            "rejection_level": winning_level, "passed": False,
                            "action": "SKIP_RIBBON_MOMENTUM_GATE", "setup": setup_name,
                        })
                        continue

            # RIBBON_DURATION_GATE: ribbon stack age <= max bars.
            # "Fresh flip = edge, stale 2-hour trend = near exhaustion" — what J sees.
            if max_ribbon_duration_bars is not None:
                _rdur = 0
                for _j in range(idx, max(0, idx - max_ribbon_duration_bars - 2), -1):
                    _st2 = ribbon_at(ribbon_df, _j)
                    if _st2 is None or _st2.stack != ribbon_state.stack:
                        break
                    _rdur += 1
                if _rdur > max_ribbon_duration_bars:
                    decisions.append({
                        "bar_idx": idx, "timestamp_et": bar_time,
                        "spy_close": float(bar["close"]), "vix": vix_now,
                        "ribbon_stack": ribbon_state.stack,
                        "ribbon_spread_cents": ribbon_state.spread_cents,
                        "htf_15m_stack": htf_stack, "bear_score": result.bear_score,
                        "blockers": ["RIBBON_DURATION_GATE"],
                        "triggers_fired": winning_triggers,
                        "rejection_level": winning_level, "passed": False,
                        "action": "SKIP_RIBBON_DURATION_GATE", "setup": setup_name,
                    })
                    continue

            # MIDDAY_TRENDLINE_GATE (kwarg-gated, default False, prod unchanged until ratified)
            if midday_trendline_gate:
                _is_mid = dt.time(11, 30) <= bar_time.time() < dt.time(14, 0)
                _is_tl_only = (
                    len(winning_triggers) == 1 and "trendline_rejection" in winning_triggers
                )
                if _is_mid and _is_tl_only:
                    decisions.append({
                        "bar_idx": idx, "timestamp_et": bar_time,
                        "spy_close": float(bar["close"]), "vix": vix_now,
                        "ribbon_stack": ribbon_state.stack,
                        "ribbon_spread_cents": ribbon_state.spread_cents,
                        "htf_15m_stack": htf_stack, "bear_score": result.bear_score,
                        "blockers": ["MIDDAY_TRENDLINE_GATE"],
                        "triggers_fired": winning_triggers,
                        "rejection_level": winning_level, "passed": False,
                        "action": "SKIP_MIDDAY_TRENDLINE_GATE", "setup": setup_name,
                    })
                    continue

            if use_real_fills:
                fill = simulate_trade_real(
                    entry_bar_idx=idx,
                    entry_bar=bar,
                    spy_df=spy_df,
                    ribbon_df=ribbon_df,
                    rejection_level=winning_level,
                    triggers_fired=winning_triggers,
                    side=winning_side,
                    setup=setup_name,
                    levels_active=level_set.active,
                    levels_carry=level_set.multi_day,
                    premium_stop_pct=premium_stop_pct,
                    strike_offset=strike_offset,
                    qty=trade_qty,   # NEW v13 — quality-tiered sizing
                    profit_lock_threshold_pct=profit_lock_threshold_pct,    # NEW T41 2026-05-13: parity with BS path
                    profit_lock_stop_offset_pct=profit_lock_stop_offset_pct,  # NEW T41 2026-05-13: parity with BS path
                    profit_lock_mode=profit_lock_mode,                       # NEW T50b 2026-05-13: trailing/stepped support
                    profit_lock_trail_pct=profit_lock_trail_pct,             # NEW T50b 2026-05-13
                )
                if fill is not None:
                    fill.entry_vix = vix_now
                    fill.entry_iv = vix_now / 100.0
                if fill is None:
                    # Cache miss — fall back to BS only for puts (BS sim is puts-only)
                    if winning_side == "P":
                        fill = simulate_trade(
                            entry_bar_idx=idx,
                            entry_bar=bar,
                            spy_df=spy_df,
                            vix_aligned=vix_aligned,
                            ribbon_df=ribbon_df,
                            rejection_level=winning_level,
                            triggers_fired=winning_triggers,
                            setup=setup_name,
                        )
                        fill.setup = fill.setup + "::BS_FALLBACK"
            else:
                # BS sim handles both sides; exit knobs parameterised 2026-05-09.
                side_premium_stop = bear_premium_stop if winning_side == "P" else bull_premium_stop
                # 2026-05-09 evening: pass asymmetric strike offset to BS sim too.
                # bear/bull strike offsets fall through from kwargs (default = strike_offset).
                side_strike_off = bear_strike_off if winning_side == "P" else bull_strike_off
                # ── PER-QUALITY EXIT KNOBS (CLAUDE.md OP 17 GRIND 2026-05-10) ──
                # The seed10095 doctrine knobs (tp1=+75%, stop=-20%) are tuned for
                # SUPER setups (5/4's 3-trigger confluence held through -12% intraday
                # before reversing, then ran to runner target). Applying them broadly
                # regressed:
                #   - 4/29's level_rejection trade: TP1 target $2.10 never hit because
                #     premium peaked at $1.56 then reversed. With tp1=+30%, TP1 fires
                #     at $1.56 and locks the win.
                #   - 4/29's trendline trade: -20% stop held 80 minutes blocking the
                #     subsequent better LEVEL trigger from firing.
                # Per-quality knobs let weak triggers bail/take-profit fast and let
                # SUPER setups ride to the doctrine target.
                # OVERNIGHT GRINDER HOOK (2026-05-10): module-level _grinder_overrides
                # dict can monkey-patch any per-quality knob from a sweep worker. None
                # value or missing key means use the doctrine default. Workers in
                # autoresearch.overnight_grinder set this via _patch_orchestrator().
                _go = globals().get("_grinder_overrides", None)
                if quality_tier == "TRENDLINE":
                    # 2026-05-10: tried widening to -25% to ride 5/01 13:50 wick.
                    # Result: 4/29 regressed from $+372 to $+60 because the wider
                    # stop held the 12:10 trendline trade open through the 12:25
                    # LEVEL trigger window, blocking the bigger LEVEL win. Tight
                    # -8% stop is the right knob: it eats a quick $20 5/01 loss
                    # but unlocks 4/29's $400 LEVEL re-entry. Net +$380 over the
                    # widened-stop alternative. KEEP -8%.
                    quality_stop = (_go or {}).get("trendline_stop", -0.08)
                    quality_tp1 = 0.30
                elif quality_tier == "TRENDLINE_LEG2":
                    quality_stop = (_go or {}).get("trendline_stop", -0.08)
                    quality_tp1 = 0.30
                elif quality_tier == "LEVEL":
                    quality_stop = (_go or {}).get("level_stop", -0.10)
                    quality_tp1 = (_go or {}).get("level_tp1", 0.30)
                elif quality_tier == "ELITE":
                    quality_stop = -0.15
                    quality_tp1 = 0.50
                elif quality_tier == "SUPER":
                    # SUPER honours caller doctrine OR grinder override if set
                    if _go and "super_stop" in _go:
                        quality_stop = _go["super_stop"]
                    else:
                        quality_stop = side_premium_stop
                    if _go and "super_tp1" in _go:
                        quality_tp1 = _go["super_tp1"]
                    else:
                        quality_tp1 = tp1_premium_pct
                else:
                    quality_stop = side_premium_stop
                    quality_tp1 = tp1_premium_pct
                # GRINDER: runner_target override
                if _go and "runner_target" in _go:
                    runner_target_premium_pct = _go["runner_target"]
                # Use the TIGHTER of (caller, quality) for stops — never relax beyond
                # caller intent. Use the SMALLER of (caller, quality) for TP1 — never
                # set TP1 further than caller intent (so SUPER can use 0.75 if caller).
                effective_premium_stop = max(side_premium_stop, quality_stop)
                effective_tp1 = min(tp1_premium_pct, quality_tp1) if quality_tier != "SUPER" else tp1_premium_pct
                # 2026-05-10 OTM-2 forcing for TRENDLINE TRIED + REVERTED.
                # Made 4/29 regress: P708 (deeper OTM) plus wide stop held
                # the trendline trade open all day, blocking the later P710
                # LEVEL re-entry that won the day. Caller's strike_offset wins.
                effective_strike_off = side_strike_off
                fill = simulate_trade(
                    entry_bar_idx=idx,
                    entry_bar=bar,
                    spy_df=spy_df,
                    vix_aligned=vix_aligned,
                    ribbon_df=ribbon_df,
                    rejection_level=winning_level,
                    triggers_fired=winning_triggers,
                    setup=setup_name,
                    side=winning_side,
                    qty=trade_qty,
                    premium_stop_pct=effective_premium_stop,
                    tp1_premium_pct=effective_tp1,
                    runner_target_premium_pct=runner_target_premium_pct,
                    tp1_qty_fraction=tp1_qty_fraction,
                    time_stop_et=time_stop_et,
                    level_stop_buffer_dollars=level_stop_buffer_dollars,
                    strike_offset=effective_strike_off,
                    profit_lock_threshold_pct=profit_lock_threshold_pct,
                    profit_lock_stop_offset_pct=profit_lock_stop_offset_pct,
                )

                # ── MIN ENTRY PREMIUM GATE for LEVEL+ tiers (OP 17 GRIND 2026-05-10) ──
                # Late-day/deep-OTM LEVEL trades with sub-$0.50 premium have poor
                # expected value (5/07 15:20 LEVEL@$0.36 lost $71 with qty=20). Skip
                # the trade and undo the escalation-lock state so a later, better
                # trigger can still fire today. TRENDLINE tier exempt: small entries
                # are exploration with small qty, no need to gate.
                MIN_PREMIUM_FOR_LEVEL_TIERS = 0.50
                if (
                    fill is not None
                    and quality_tier in ("LEVEL", "ELITE", "SUPER")
                    and fill.entry_premium < MIN_PREMIUM_FOR_LEVEL_TIERS
                ):
                    # Schema-compatible audit row (matches the standard decision
                    # row shape so iterators don't KeyError on missing keys).
                    decisions.append({
                        "bar_idx": idx,
                        "timestamp_et": bar_time,
                        "spy_close": float(bar["close"]),
                        "vix": vix_now,
                        "ribbon_stack": ribbon_state.stack,
                        "ribbon_spread_cents": ribbon_state.spread_cents,
                        "htf_15m_stack": htf_stack,
                        "bear_score": result.bear_score,
                        "blockers": result.blockers,
                        "triggers_fired": winning_triggers,
                        "rejection_level": winning_level,
                        "passed": True,
                        "action": "SKIP_MIN_PREMIUM",
                        "setup": setup_name,
                        "quality_tier": quality_tier,
                        "entry_premium": fill.entry_premium,
                        "min_required": MIN_PREMIUM_FOR_LEVEL_TIERS,
                        "reason": "entry premium below minimum for level-tied tiers (OP 17 EV gate)",
                    })
                    fill = None
                    # Roll back the escalation lock so a higher-quality trigger can
                    # still fire today (we never actually placed the trade).
                    if prior_quality > 0:
                        setup_quality_taken_today[lock_key] = prior_quality
                    else:
                        setup_quality_taken_today.pop(lock_key, None)

            if fill is not None:
                trades.append(fill)
                # Record whether this fill stopped out (for leg-2 detection on the
                # next trigger fire on the same setup today). A "stop" means the
                # trade exited without ever hitting TP1 -- the setup zone may have
                # been right but the timing was wrong.
                exit_reason_str = str(fill.exit_reason) if fill.exit_reason else ""
                stopped_without_tp1 = (
                    fill.tp1_time_et is None and (
                        "PREMIUM_STOP" in exit_reason_str
                        or "TIME_STOP" in exit_reason_str
                        or "LEVEL_STOP" in exit_reason_str
                    )
                )
                setup_last_stopped_today[lock_key] = stopped_without_tp1
                if fill.runner_exit_time_et is not None:
                    setup_last_exit_time_today[lock_key] = fill.runner_exit_time_et

            # Skip subsequent bars until we've passed the exit
            if fill is not None and fill.runner_exit_time_et is not None:
                # Find the bar idx of the exit time and skip up to + including it
                exit_ts = fill.runner_exit_time_et
                exit_match = spy_df[spy_df["timestamp_et"] == exit_ts]
                if not exit_match.empty:
                    skip_until_idx = int(exit_match.index[0])
                else:
                    skip_until_idx = idx + 5  # safety fallback

    metadata = {
        "setup": setup,
        "bars_evaluated": len(decisions),
        "trades_fired": len(trades),
        "start_date": str(spy_df["date"].min()),
        "end_date": str(spy_df["date"].max()),
    }
    return BacktestResult(trades=trades, decisions=decisions, metadata=metadata)
