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

import contextlib
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

import numpy as np
import pandas as pd

from .ribbon import compute_ribbon, ribbon_at, RibbonState
from .filters import (
    BarContext, evaluate_bearish_setup, evaluate_bullish_setup,
    vol_baseline_20bar, range_baseline_20bar,
    LevelState, _bar_geometry,
)
from . import filters as _filters_mod  # dynamic attribute access for runner-patched constants
from .levels import _detect_from_history, LevelSet
from .simulator import simulate_trade, TradeFill
from .simulator_real import simulate_trade_real
from .risk_gate import check_order as _risk_check_order
from .engine import score_bar as _engine_score_bar
from .engine import (
    GateContext as _GateContext,
    evaluate_gates as _engine_evaluate_gates,
)

import os as _os

# Risk-gate assert-agree toggle (Phase 0c). On by default so backtest-risk is
# continuously checked against the single-source-of-truth gate; set
# GAMMA_RISK_GATE_ASSERT=0 to skip the per-trade assertion on perf-sensitive
# sweeps. Read once at import (cheap, no per-bar env lookups).
_RISK_GATE_ASSERT = _os.environ.get("GAMMA_RISK_GATE_ASSERT", "1") != "0"

# Engine-score assert-agree toggle (Phase 1, shared-decision-library migration —
# markdown/specs/SHARED-DECISION-LIBRARY-MIGRATION.md). On by default so the scoring done
# via the new engine.score interface is continuously proven byte-identical to the
# orchestrator's direct filters.evaluate_* calls (the "assert-agree before
# replace" discipline, same move as the risk gate above). Set
# GAMMA_ENGINE_SCORE_ASSERT=0 to skip the per-bar assertion on perf-sensitive
# sweeps. Read once at import (cheap, no per-bar env lookups).
_ENGINE_SCORE_ASSERT = _os.environ.get("GAMMA_ENGINE_SCORE_ASSERT", "1") != "0"

# Engine-gates assert-agree toggle (Phase 2, shared-decision-library migration —
# markdown/specs/SHARED-DECISION-LIBRARY-MIGRATION.md §3 Phase 2). On by default so the 15
# entry gates now also evaluated via engine.evaluate_gates are continuously proven
# to fire the SAME first SKIP (or allow) the orchestrator's inline gate cascade
# does — the same "assert-agree before replace" discipline as the risk gate and
# the score oracle above. Set GAMMA_ENGINE_GATES_ASSERT=0 to skip the per-bar
# assertion on perf-sensitive sweeps. Read once at import (no per-bar env lookups).
_ENGINE_GATES_ASSERT = _os.environ.get("GAMMA_ENGINE_GATES_ASSERT", "1") != "0"


# Keys in params_overrides that control lib.filters module-level constants.
# Patching here mirrors what runner._patched_filter_constants does so that
# run_backtest(params_overrides={"ribbon_flip_lookback_bars": 1}) works the
# same way as run_with_params({"ribbon_flip_lookback_bars": 1}).
_FILTER_CONST_MAP: dict[str, str] = {
    "ribbon_flip_lookback_bars": "RIBBON_FLIP_LOOKBACK_BARS",
    "ribbon_spread_min_cents": "RIBBON_SPREAD_MIN_CENTS",
    "confluence_tolerance_dollars": "CONFLUENCE_TOLERANCE_DOLLARS",
    # VIX thresholds — were in runner._FILTERS_CONST_KEYS but missing here (L111 dead-knob fix 2026-06-17)
    "vix_bear_threshold": "VIX_BEAR_THRESHOLD",
    "vix_rising_deadband": "VIX_RISING_DEADBAND",
    "vix_bear_rising_deadband": "VIX_RISING_DEADBAND",    # asymmetric alias, same target
    "vix_bull_max": "VIX_BULL_HARD_CAP",
    # L114 (2026-06-17): block BEAR entries when VIX > cap (panic-extreme tariff-shock blocker)
    "vix_hard_cap_bear": "VIX_HARD_CAP_BEAR",
    # L115 (2026-06-17): require multi-day VIX declining for BEAR entries (L93 recommendation)
    "vix_declining_required_bear": "VIX_DECLINING_REQUIRED_BEAR",
    # Trendline detection knobs (2026-06-17: promoted from hardcoded defaults to sweepable constants)
    "trendline_lookback_bars": "TRENDLINE_LOOKBACK_BARS",
    "trendline_min_swings": "TRENDLINE_MIN_SWINGS",
    # Bull VIX gate (2026-06-17: VIX_BULL_LOW_THRESHOLD live but unwired — C14 fix)
    "vix_bull_low_threshold": "VIX_BULL_LOW_THRESHOLD",
    # Wick rejection thresholds (2026-06-17: C14 fix — were hardcoded function defaults)
    "wick_min_pct_of_range": "WICK_MIN_PCT_OF_RANGE",
    "wick_min_dollars": "WICK_MIN_DOLLARS",
    "wick_close_tolerance": "WICK_CLOSE_TOLERANCE",
    # Volume baseline window (2026-06-17: C14 fix — used in vol_baseline_20bar called at orchestrator:665;
    # confirmed LIVE: bars=5 vs 50 gives different IS trade count.
    # NOTE: range_baseline_bars intentionally excluded — ctx.range_baseline_20 is never read by
    # any filter (dead field), so RANGE_BASELINE_BARS has no effect on backtest output.
    "vol_baseline_bars": "VOL_BASELINE_BARS",
}


@contextlib.contextmanager
def _patch_filter_consts(overrides: Optional[dict]) -> Iterator[None]:
    """Temporarily swap lib.filters module constants during a single run."""
    saved: dict[str, Any] = {}
    if overrides:
        for key, attr in _FILTER_CONST_MAP.items():
            if key in overrides:
                saved[attr] = getattr(_filters_mod, attr)
                setattr(_filters_mod, attr, overrides[key])
    try:
        yield
    finally:
        for attr, val in saved.items():
            setattr(_filters_mod, attr, val)


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
    if "min_triggers_bear" in overrides:  # L116: raw snake_case alias for params_overrides path
        kwargs["min_triggers_bear"] = overrides["min_triggers_bear"]
    if "filter_10_min_triggers_bull" in overrides:
        kwargs["min_triggers_bull"] = overrides["filter_10_min_triggers_bull"]
    if "min_triggers_bull" in overrides:  # L116: raw snake_case alias
        kwargs["min_triggers_bull"] = overrides["min_triggers_bull"]
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
    if "entry_no_trade_window_et" in overrides:
        if overrides["entry_no_trade_window_et"]:
            s, e = overrides["entry_no_trade_window_et"]
            sh, sm = s.split(":")
            eh, em = e.split(":")
            kwargs["no_trade_window"] = (dt.time(int(sh), int(sm)), dt.time(int(eh), int(em)))
        else:
            # null/None → explicitly disable the legacy v11 (14:00-15:00) default so
            # Karpathy shadow runs match production (entry_no_trade_window_et=null since v15.1)
            kwargs["no_trade_window"] = None
    # v15.3 RIBBON CONVICTION GATE — mapped from params.json via params_overrides
    if "min_ribbon_momentum_cents" in overrides and overrides["min_ribbon_momentum_cents"] is not None:
        kwargs["min_ribbon_momentum_cents"] = float(overrides["min_ribbon_momentum_cents"])
    if "max_ribbon_duration_bars" in overrides and overrides["max_ribbon_duration_bars"] is not None:
        kwargs["max_ribbon_duration_bars"] = int(overrides["max_ribbon_duration_bars"])
    if "midday_trendline_gate" in overrides:
        kwargs["midday_trendline_gate"] = bool(overrides["midday_trendline_gate"])
    if "midday_trendline_gate_start_minutes" in overrides and overrides["midday_trendline_gate_start_minutes"] is not None:
        kwargs["midday_trendline_gate_start_minutes"] = int(overrides["midday_trendline_gate_start_minutes"])
    if "block_conf_lvl_rec_afternoon" in overrides:
        kwargs["block_conf_lvl_rec_afternoon"] = bool(overrides["block_conf_lvl_rec_afternoon"])
    if "block_conf_lvl_rej_midday_afternoon" in overrides:
        kwargs["block_conf_lvl_rej_midday_afternoon"] = bool(overrides["block_conf_lvl_rej_midday_afternoon"])
    # Asymmetric premium stops (v15: bear -20% / bull -8%). Bugfix 2026-06-14:
    # premium_stop_pct_bear/bull were never mapped, so params.json's bear stop
    # could not reach the engine (same dead-knob class as the ribbon gates).
    if "premium_stop_pct_bear" in overrides:
        kwargs["premium_stop_pct_bear"] = overrides["premium_stop_pct_bear"]
    if "premium_stop_pct_bull" in overrides:
        kwargs["premium_stop_pct_bull"] = overrides["premium_stop_pct_bull"]
    if "per_trade_risk_cap_pct" in overrides:
        kwargs["per_trade_risk_cap_pct"] = float(overrides["per_trade_risk_cap_pct"])
    # L113 2026-06-17: chart_stop_buffer_dollars in params.json → level_stop_buffer_dollars kwarg.
    # prod=0.50 (was hardcoded 0.50 in simulator_real.py; now wirable).
    if "chart_stop_buffer_dollars" in overrides:
        kwargs["level_stop_buffer_dollars"] = float(overrides["chart_stop_buffer_dollars"])
    # LEVEL_REJECTION_GATE 2026-06-17: block LEVEL-tier level_rejection entries.
    if "block_level_rejection" in overrides:
        kwargs["block_level_rejection"] = bool(overrides["block_level_rejection"])
    # TRENDLINE_RIBBON_FLIP_REQUIRED 2026-06-17: block TRENDLINE entries without ribbon_flip.
    if "trendline_requires_ribbon_flip" in overrides:
        kwargs["trendline_requires_ribbon_flip"] = bool(overrides["trendline_requires_ribbon_flip"])
    # BLOCK_ELITE_BULL 2026-06-17: block ELITE confluence+level_reclaim (BULL) entries.
    if "block_elite_bull" in overrides:
        kwargs["block_elite_bull"] = bool(overrides["block_elite_bull"])
    if "block_elite_bull_vix_low" in overrides:
        kwargs["block_elite_bull_vix_low"] = float(overrides["block_elite_bull_vix_low"])
    if "block_elite_bull_vix_high" in overrides:
        kwargs["block_elite_bull_vix_high"] = float(overrides["block_elite_bull_vix_high"])
    # BLOCK_BULL_RIBBON_FLIP 2026-06-17: block BULLISH_RECLAIM entries with ribbon_flip trigger.
    if "block_bull_ribbon_flip" in overrides and overrides["block_bull_ribbon_flip"] is not None:
        kwargs["block_bull_ribbon_flip"] = bool(overrides["block_bull_ribbon_flip"])
    # VIX_BEAR_HARD_CAP 2026-06-18: block BEAR entries when VIX >= threshold.
    if "vix_bear_hard_cap" in overrides and overrides["vix_bear_hard_cap"] is not None:
        kwargs["vix_bear_hard_cap"] = float(overrides["vix_bear_hard_cap"])
    # ENTRY_BAR_BODY_PCT_MIN 2026-06-18: block BEAR entries on doji/wick-dominant bars.
    # Bugfix 2026-06-18: was NOT translated here, so the params-path (params_overrides /
    # walk-forward) silently dropped this ratified gate. Now mapped (C14 dead-knob class).
    if "entry_bar_body_pct_min" in overrides and overrides["entry_bar_body_pct_min"] is not None:
        kwargs["entry_bar_body_pct_min"] = float(overrides["entry_bar_body_pct_min"])
    # BLOCK_BULL_1100_1200 2026-06-18: block ALL BULL entries in 11:00-12:00 ET window.
    if "block_bull_1100_1200" in overrides and overrides["block_bull_1100_1200"] is not None:
        kwargs["block_bull_1100_1200"] = bool(overrides["block_bull_1100_1200"])
    if "block_bull_morning_agg" in overrides and overrides["block_bull_morning_agg"] is not None:
        kwargs["block_bull_morning_agg"] = bool(overrides["block_bull_morning_agg"])
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
    # Start time for midday_trendline_gate in minutes after midnight (default 690 = 11:30 ET).
    # Sweep: 660=11:00 removes 14 IS TL losers (+$1,000 IS improvement) — Rank-37 candidate.
    midday_trendline_gate_start_minutes: int = 690,
    # --- BLOCK_CONF_LVL_REC_AFTERNOON 2026-06-17 (AUTO-RATIFIED, IS+412 OOS+176 WF=2.644) ---
    # Blocks conf+level_reclaim entries in 14:00-15:55 ET. IS 100% stop rate n=5; OOS 100% stop n=1.
    # Default=False. Enabled via params.json "block_conf_lvl_rec_afternoon": true.
    block_conf_lvl_rec_afternoon: bool = False,
    # --- BLOCK_CONF_LVL_REJ_MIDDAY_AFTERNOON 2026-06-17 (AGG, IS+566 OOS+230 WF=2.368) ---
    # Blocks conf+level_rejection entries in 11:30-15:55 ET (midday+afternoon). AGG only.
    # IS n=11 dropped (all stops: midday avg=-$1, afternoon avg=-$186). OOS n=2 dropped (both stops).
    # Default=False. Enabled via aggressive/params.json "block_conf_lvl_rej_midday_afternoon": true.
    block_conf_lvl_rej_midday_afternoon: bool = False,
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
    # L113 2026-06-17: was 0.0 and ignored (simulator_real hardcoded 0.50). Now wired.
    # prod=0.50. Default matches production so existing callers see identical behaviour.
    level_stop_buffer_dollars: float = 0.50,
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
    # --- Per-trade risk cap (mirrors live heartbeat Rule 6 enforcement) ---
    # Notional cost = entry_premium * qty * 100 must not exceed initial_equity * cap.
    # When exceeded, qty is scaled down to the cap floor (min 3 contracts).
    # Default 0.50 = Bold account (50% of equity). Safe = 0.30.
    # P&L scaling is exact: option P&L is linear in qty for bracketed trades.
    per_trade_risk_cap_pct: float = 0.50,
    # --- NEW: BEARISH_SWEEP_BLOCKER gate (strategy/candidates/2026-05-16-bearish-sweep-blocker.md) ---
    # When True, evaluates sweep patterns on the trigger level and hard-blocks entries
    # where the level was recently swept in the counter-direction (5/14 09:58 misfire class).
    # Default False = no change to existing behavior.
    sweep_blocker_enabled: bool = False,
    sweep_min_wick_pct: float = 0.0003,
    sweep_min_close_back_pct: float = 0.0005,
    sweep_block_window_bars: int = 3,
    sweep_clean_prior_bars: int = 3,
    # --- RIBBON_FLIP_PRICE_CONFIRM 2026-06-16 (threads to simulator_real) ---
    # Default False = existing behavior. True = require price reversal past entry_spot
    # before EXIT_ALL_RIBBON_FLIP_BACK fires. Needs J Rule 9 ratification to enable.
    ribbon_flip_price_confirm: bool = False,
    # --- LEVEL FLAGS: A/B testing of level-set changes (level_shadow_ab.py) ---
    # Dict of kwargs forwarded to _detect_from_history(). Default None = no change.
    # Example: {"exclude_intraday_hl": True} removes today's session H/L levels.
    # DEFAULT UNCHANGED — existing code never passes this arg.
    level_flags: Optional[dict] = None,
    # --- RANK 27: First-hour RTH high level (2026-06-16) ---
    # When True, adds max(09:30-09:55 bars high) to levels_active after 10:05 ET.
    # Supplemental dynamic level — NOT part of _level_per_day cache (which is frozen
    # at 09:35 first bar). Separate _first_hour_high_per_day cache computed at 10:05+.
    # Motivation: 5/01 11:50 BEARISH_REVERSAL blocked because 724.24 not in level set.
    # Feature-flagged off by default; A/B test with run_backtest(..., include_first_hour_high=True).
    include_first_hour_high: bool = False,
    # --- RANK 28: BEARISH_REVERSAL filter bypass (2026-06-16) ---
    # When True, evaluate_bearish_setup skips filter_5 (ribbon stack) and filter_8 (VIX gate)
    # for setups where ribbon=BULL + level_rejection fires without a trendline trigger.
    # The 5/01 11:50 J anchor (+$470 EC). DEFAULT FALSE — Rule 9 flag.
    # A/B test with run_backtest(..., include_bearish_reversal_bypass=True).
    include_bearish_reversal_bypass: bool = False,
    # V4 quality discriminators (study 2026-06-16). See filters.py for anti-correlation warning.
    # fhh_quality_proximity: proximity gate (anti-correlated with J anchor, do not use for
    #   the 5/01-style gap-up setup). fhh_above_max_prior_min: gap-up discriminator.
    fhh_quality_proximity: Optional[float] = None,
    fhh_above_max_prior_min: Optional[float] = None,
    # --- OP-17 EV GATE: minimum entry premium for LEVEL/ELITE/SUPER tiers ---
    # Sub-$0.50 LEVEL trades have poor EV (5/07 15:20 LEVEL@$0.36 lost $71 at qty=20).
    # Hardcoded 0.50 previously. Now wirable for sweep.
    min_premium_for_level_tiers: float = 0.50,
    # --- LEVEL_REJECTION_GATE (2026-06-17): block all LEVEL-tier level_rejection entries ---
    # Motivation: IS level_rejection trades (n=22) avg -$584/trade vs level_reclaim avg +$73.
    # Post-hoc analysis: IS delta=+$13,389, OOS delta=+$682, WF=0.829.
    # Default False = no change. Set True to enable gate (params.json key: block_level_rejection).
    block_level_rejection: bool = False,
    # --- TRENDLINE_RIBBON_FLIP_REQUIRED (2026-06-17): block TRENDLINE entries without ribbon_flip ---
    # IS analysis: pure trendline_rejection n=58 WR=27.6% avg=-$34; ribbon_flip+trendline n=6 WR=50% avg=+$312.
    # Gate removes 58 losing trades (-$1,970), keeps 6 profitable (+$1,870). IS delta=+$1,970.
    # Default False = no change. Set True to enable.
    trendline_requires_ribbon_flip: bool = False,
    # --- BLOCK_ELITE_BULL (2026-06-17): block ELITE-tier level_reclaim (BULL) entries ---
    # IS analysis: confluence+level_reclaim n=105 WR=14.3% avg=-$34 (-$3,618 total);
    # By VIX bucket: <15 n=17 WR=23.5% avg=+$112 (winners); 15-17 n=73 WR=9.6% avg=-$100 (losers);
    #                17-20 n=14 WR=21.4% avg=+$88 (winners); 20+ winners.
    # VIX-range variant: block ONLY when block_elite_bull_vix_low <= vix < block_elite_bull_vix_high.
    # Default False = no change. Set True to enable. VIX range defaults = all VIX.
    block_elite_bull: bool = False,
    block_elite_bull_vix_low: float = 0.0,
    block_elite_bull_vix_high: float = 999.0,
    # --- BLOCK_BULL_RIBBON_FLIP (2026-06-17): block BULLISH_RECLAIM entries with ribbon_flip ---
    # IS analysis: ribbon_flip BULLISH_RECLAIM n=21 WR=10% avg=-$106 total=-$2,222.
    # Non-ribbon_flip BULLISH_RECLAIM n=24 WR=29% avg=+$288 total=+$6,901.
    # The ribbon_flip signal in a BULLISH_RECLAIM context is a lagging momentum confirmation
    # that fires AFTER the move has started — by the time ribbon flips to BULL, the reclaim
    # attempt is already reversing and the entry is chasing, not leading.
    # Default False = no change. Set True to enable.
    block_bull_ribbon_flip: bool = False,
    # --- REQUIRE_BEARISH_FILL_BAR (2026-06-17): skip BEARISH_REJECTION when fill bar (N+1) is bullish ---
    # Post-hoc analysis (entry_bar_pnl_split.py): bearish fill bar WR=41.1% avg=+$225 (n=56 IS);
    # bullish fill bar WR=3.4% avg=-$39 (n=29 IS). IS delta=+$1,124, OOS delta=+$424, WF_norm=1.908.
    # IMPORTANT: this is a LOOK-AHEAD gate (checks bar idx+1 which is unknown at signal time).
    # Valid for backtest research to measure upper bound of one-bar confirmation delay strategy.
    # Production implementation requires actual one-bar delay (enter at N+2 open after confirming N+1 close).
    # Default False = no change. Set True to measure look-ahead bound.
    require_bearish_fill_bar: bool = False,
    # --- ENTRY_BAR_BODY_PCT_MIN (2026-06-18): block BEAR entries on doji/wick-dominant bars ---
    # Post-hoc A/B (safe_entry_body_gate.py): body<0.20 IS n=16 WR=31.2% total=-$466 (negative!);
    # OOS n=3 WR=0.0% total=-$293. IS_delta=+$466, OOS_delta=+$293, WF_per_trade=3.35, SW_hurt=1/3.
    # All 5 OP-22 gates PASS. Auto-ratified 2026-06-18 per OP-22 + J standing "no blocker" directive.
    # Scorecard: analysis/recommendations/safe_entry_body_gate.json. Revert: set 0.0.
    # Only applies to BEAR entries. BULL entries not yet analyzed.
    entry_bar_body_pct_min: float = 0.0,
    # --- ENTRY_BAR_BODY_PCT_MIN_BULL (2026-06-18): same gate for BULL (C) entries ---
    # Hypothesis: doji/wick-dominant entry bars lack directional conviction for bulls too.
    # A/B test pending (safe_entry_body_gate_bull.py). Default 0.0 = disabled.
    entry_bar_body_pct_min_bull: float = 0.0,
    # --- V_PULLBACK (2026-06-18): wait for price to pull back to level before entering ---
    # After a trigger fires, instead of entering immediately, scan up to v_pullback_window_bars
    # for price to touch within v_pullback_level_tolerance of the rejection/reclaim level.
    # Enter on that pullback bar (better entry, lower premium). If no pullback in window,
    # skip the trade (SKIP_NO_PULLBACK). Default False = disabled (no change to baseline).
    # Hypothesis: pullback entries reduce whipsaws for level-rejection triggers (C29 aware).
    v_pullback_enabled: bool = False,
    v_pullback_level_tolerance: float = 0.20,
    v_pullback_window_bars: int = 6,
    # --- VIX_BEAR_HARD_CAP (2026-06-18): block BEAR (P) entries when VIX >= threshold ---
    # A/B result (SAFE): IS n=9 blocked WR=0% total=-$790; OOS n=6 WR=17% total=-$420.
    # WF_per_trade=0.797, SW_hurt=0/3. All 5 OP-22 gates PASS. Ratified 2026-06-18.
    # Scorecard: analysis/recommendations/safe_vix_bear_hard_cap.json. Revert: set to None.
    vix_bear_hard_cap: Optional[float] = None,
    # --- MIN_TRENDLINE_BEAR_SPREAD_CENTS: REJECTED 2026-06-18 ---
    # Hypothesis: TRENDLINE-only BEAR entries with tight ribbon at entry are structural losers.
    # A/B test REJECTED: G1 FAIL (IS_delta=-11; blocked 14 IS bears incl. 2025-02-24 +$92 winner).
    # Root cause: original A/B test had TZ bug — tz_localize("UTC") on naive ET timestamps looked
    # up premarket ribbon (~5h offset) instead of actual entry-time ribbon. With correct
    # tz_localize("America/New_York"), the gate removes winners. No threshold between 1c-100c
    # passes G1 AND G2 simultaneously. Lesson: always validate with tz_localize("America/New_York")
    # when entry_time_et is naive ET (option CSV convention).
    # Kept as dormant knob (default 0.0 = disabled) — do not enable in production.
    min_trendline_bear_spread_cents: float = 0.0,
    # --- BLOCK_BULL_1100_1200 (2026-06-18): block ALL BULL (C) entries 11:00-12:00 ET ---
    # IS: 11:00-12:00 bulls n=11, total=-$89, WR=9.1% (worst TOD bucket, 10/11 losers).
    # OOS: n=1 blocked (2026-05-20 11:20 confluence+level_reclaim -$42).
    # OP-22: IS_delta=+89, OOS_delta=+42, WF=5.22, SW_hurt=1/3, anchor unaffected.
    # All 5 OP-22 gates PASS. Auto-ratified 2026-06-18 per OP-22 + J standing directive.
    # Scorecard: analysis/recommendations/safe_bull_1100_1200_gate.json. Revert: set False.
    block_bull_1100_1200: bool = False,
    # --- BLOCK_BULL_MORNING_AGG (2026-06-18): block ALL BULL (C) entries 10:00-11:30 ET AND 14:00-15:00 ET ---
    # Aggressive account only. MORNING IS: n=47, WR=14.9%, total=-$222. AFTERNOON IS: n=6, WR=0%, total=-$82.
    # Combined: IS_delta=+304 (n=53 removed), OOS_delta=+40 (n=2: 2026-05-26 +$0, 2026-05-28 -$40).
    # OP-22: WF=3.493, SW_hurt=1/3 (SW3 -$36), G5=PASS (anchors are bears). All 5 gates PASS.
    # Auto-ratified 2026-06-18 per OP-22 + J standing directive. Revert: set False.
    # Scorecard: analysis/recommendations/agg_block_bull_morning_afternoon.json.
    block_bull_morning_agg: bool = False,
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
    # Patch filter module constants from params_overrides (ribbon_flip_lookback_bars, etc.)
    # This mirrors runner._patched_filter_constants so run_backtest(params_overrides={...})
    # behaves identically to run_with_params({...}) for module-level filter constants.
    _filter_const_saved: dict[str, Any] = {}
    if params_overrides:
        for _fk, _fa in _FILTER_CONST_MAP.items():
            if _fk in params_overrides:
                _filter_const_saved[_fa] = getattr(_filters_mod, _fa)
                setattr(_filters_mod, _fa, params_overrides[_fk])

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
        if "block_conf_lvl_rec_afternoon" in ovrk and block_conf_lvl_rec_afternoon is False:
            block_conf_lvl_rec_afternoon = ovrk["block_conf_lvl_rec_afternoon"]
        if "block_conf_lvl_rej_midday_afternoon" in ovrk and block_conf_lvl_rej_midday_afternoon is False:
            block_conf_lvl_rej_midday_afternoon = ovrk["block_conf_lvl_rej_midday_afternoon"]
        if "premium_stop_pct_bear" in ovrk and premium_stop_pct_bear is None:
            premium_stop_pct_bear = ovrk["premium_stop_pct_bear"]
        if "premium_stop_pct_bull" in ovrk and premium_stop_pct_bull is None:
            premium_stop_pct_bull = ovrk["premium_stop_pct_bull"]
        if "per_trade_risk_cap_pct" in ovrk and per_trade_risk_cap_pct == 0.50:
            per_trade_risk_cap_pct = ovrk["per_trade_risk_cap_pct"]
        # L113 2026-06-17: level_stop_buffer_dollars from chart_stop_buffer_dollars in params.json
        if "level_stop_buffer_dollars" in ovrk and level_stop_buffer_dollars == 0.50:
            level_stop_buffer_dollars = ovrk["level_stop_buffer_dollars"]
        if "block_level_rejection" in ovrk and block_level_rejection is False:
            block_level_rejection = bool(ovrk["block_level_rejection"])
        if "trendline_requires_ribbon_flip" in ovrk and trendline_requires_ribbon_flip is False:
            trendline_requires_ribbon_flip = bool(ovrk["trendline_requires_ribbon_flip"])
        if "block_elite_bull" in ovrk and block_elite_bull is False:
            block_elite_bull = bool(ovrk["block_elite_bull"])
        if "block_elite_bull_vix_low" in ovrk and block_elite_bull_vix_low == 0.0:
            block_elite_bull_vix_low = float(ovrk["block_elite_bull_vix_low"])
        if "block_elite_bull_vix_high" in ovrk and block_elite_bull_vix_high == 999.0:
            block_elite_bull_vix_high = float(ovrk["block_elite_bull_vix_high"])
        if "block_bull_1100_1200" in ovrk and block_bull_1100_1200 is False:
            block_bull_1100_1200 = bool(ovrk["block_bull_1100_1200"])
        if "block_bull_morning_agg" in ovrk and block_bull_morning_agg is False:
            block_bull_morning_agg = bool(ovrk["block_bull_morning_agg"])
        # Bugfix 2026-06-18: vix_bear_hard_cap + entry_bar_body_pct_min were translated by
        # _params_to_kwargs but never assigned here, so params_overrides (and the
        # walk-forward params-path) silently dropped these two ratified gates — the
        # L38/L72/C14 "translated-but-unapplied" dead-knob class. Now applied (same
        # default-guard heuristic as the four gates above; default None / 0.0).
        if "vix_bear_hard_cap" in ovrk and vix_bear_hard_cap is None:
            vix_bear_hard_cap = float(ovrk["vix_bear_hard_cap"])
        if "entry_bar_body_pct_min" in ovrk and entry_bar_body_pct_min == 0.0:
            entry_bar_body_pct_min = float(ovrk["entry_bar_body_pct_min"])

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
        for _fa, _v in _filter_const_saved.items():
            setattr(_filters_mod, _fa, _v)
        return BacktestResult(trades=[], decisions=[], metadata={"reason": "no_data"})

    # Split: RTH-only (>= 09:30, < 16:00) for ribbon + baselines + evaluation.
    rth_mask = (
        (spy_df_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_df_full["timestamp_et"].dt.time < dt.time(16, 0))
    )
    spy_df = spy_df_full.loc[rth_mask].reset_index(drop=True)
    if spy_df.empty:
        for _fa, _v in _filter_const_saved.items():
            setattr(_filters_mod, _fa, _v)
        return BacktestResult(trades=[], decisions=[], metadata={"reason": "no_rth_data"})

    # Compute ribbon on RTH-only bars (matches the live indicator computation).
    ribbon_df = compute_ribbon(spy_df["close"])
    vix_aligned = _align_vix_to_spy(spy_df, vix_df)

    # L115: Pre-compute daily VIX closes for multi-day trend filter (5-day rolling avg of prior closes).
    # Groups raw vix_df by calendar date, takes last close each day, computes 5-day lag-1 rolling mean.
    # Result: _vix_5d_ma_per_day[date] = avg of prior 5 daily VIX closes (no look-ahead).
    _vix_5d_ma_per_day: dict = {}
    _vix_raw = vix_df.copy()
    _vix_raw_ts = pd.to_datetime(_vix_raw["timestamp_et"], utc=True)
    _vix_raw["_date"] = _vix_raw_ts.dt.date
    _vix_close_by_day = _vix_raw.groupby("_date")["close"].last()
    _vix_dates_sorted = sorted(_vix_close_by_day.index)
    _vix_20d_ma_per_day: dict = {}
    for _di, _d in enumerate(_vix_dates_sorted):
        if _di >= 5:
            _prior5 = [_vix_close_by_day[_vix_dates_sorted[_di - 5 + _j]] for _j in range(5)]
            _vix_5d_ma_per_day[_d] = sum(_prior5) / 5.0
        if _di >= 20:
            _prior20 = [_vix_close_by_day[_vix_dates_sorted[_di - 20 + _j]] for _j in range(20)]
            _vix_20d_ma_per_day[_d] = sum(_prior20) / 20.0

    # Precompute 15-min HTF stack lookup once (was O(n²) per-bar before 2026-05-08).
    htf_stacks_precomputed = _precompute_htf_15m_stacks(spy_df)

    # PERF FIX 2026-05-24: level-per-day cache.
    # _detect_from_history is O(n) per call and was called for EVERY bar, giving O(n²)
    # total — the overnight_grinder ran 43+ min/combo on a 17-month window.
    # Levels are constant within a day (based on prior days + today's premarket only,
    # not today's RTH bars), so computing once per day and caching is semantically
    # identical. Gives ~78× speedup on wide-window sweeps (~10 min → ~8 sec/combo).
    _level_per_day: dict[dt.date, "LevelSet"] = {}
    # Rank 27: supplemental first-hour RTH high per day (computed lazily at 10:05+).
    # None value = level already covered by existing active set (dedup).
    _first_hour_high_per_day: dict[dt.date, "float | None"] = {}

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

        # Skip if outside our trading window.
        # L117 2026-06-17: upper bound uses time_stop_et (computed from time_stop_minutes_before_close)
        # rather than hardcoded 15:50 — production never enters at or after the time stop bar,
        # but old code used a fixed 15:50 gate while time_stop_et could be earlier (e.g. 15:40 with 20min).
        if bar_time_py.time() < dt.time(9, 35) or bar_time_py.time() >= time_stop_et:
            continue

        # Need ribbon warmed up
        ribbon_state = ribbon_at(ribbon_df, idx)
        if ribbon_state is None:
            continue

        # Pull ribbon history for flip detection.
        # Buffer size tracks RIBBON_FLIP_LOOKBACK_BARS so the runner can tune it.
        _rlb = _filters_mod.RIBBON_FLIP_LOOKBACK_BARS
        ribbon_history = []
        for j in range(max(0, idx - _rlb - 1), idx + 1):
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
            _level_per_day[bar_date] = _detect_from_history(
                full_history, bar_date, **(level_flags or {})
            )
        level_set = _level_per_day[bar_date]

        # Rank 27: first-hour RTH high as supplemental dynamic level (2026-06-16).
        # Computed lazily at 10:05+ ET from 09:30-09:55 bars. Separate from
        # _level_per_day cache (which is frozen at 09:35 first bar).
        effective_levels = level_set.active
        fhh_supplement = None  # safe default — assigned in block below when include_first_hour_high=True
        if include_first_hour_high:
            if bar_time_py.time() >= dt.time(10, 5) and bar_date not in _first_hour_high_per_day:
                fh_mask = (
                    (spy_df_full["date"] == bar_date)
                    & (spy_df_full["timestamp_et"].dt.time >= dt.time(9, 30))
                    & (spy_df_full["timestamp_et"].dt.time <= dt.time(9, 55))
                )
                fh_bars = spy_df_full[fh_mask]
                if not fh_bars.empty:
                    fhh = float(fh_bars["high"].max())
                    if any(abs(fhh - lv) < 0.01 for lv in level_set.active):
                        _first_hour_high_per_day[bar_date] = None  # already covered by existing level
                    else:
                        _first_hour_high_per_day[bar_date] = fhh
                else:
                    _first_hour_high_per_day[bar_date] = None
            fhh_supplement = _first_hour_high_per_day.get(bar_date)
            if fhh_supplement is not None:
                effective_levels = level_set.active + [fhh_supplement]

        # Update per-level state (role + bounce_history) — feeds sequence_rejection trigger
        _update_level_states(level_states, effective_levels, bar, idx)

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
            fhh_level=fhh_supplement if include_first_hour_high else None,
            vix_5d_ma=_vix_5d_ma_per_day.get(bar_date, 0.0),
            vix_20d_ma=_vix_20d_ma_per_day.get(bar_date, 0.0),
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
            bearish_reversal_bypass=include_bearish_reversal_bypass,
            fhh_quality_proximity=fhh_quality_proximity,
            fhh_above_max_prior_min=fhh_above_max_prior_min,
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

        # ── ENGINE-SCORE ASSERT-AGREE (Phase 1, 2026-06-18) ──
        # The scoring layer is being relocated behind ONE shared interface,
        # backtest/lib/engine.score_bar (the same surface the live heartbeat will
        # call via a shell-out shim in Phase 3-4). Here we do NOT yet replace the
        # evaluate_* calls above; we run engine.score_bar as an independent oracle
        # on the SAME ctx + the SAME kwargs and assert it returns field-identical
        # results, proving the extraction is faithful with zero behaviour change
        # before any call site depends on it (mirrors the risk-gate assert-agree).
        # Opt-out via GAMMA_ENGINE_SCORE_ASSERT=0 for perf-sensitive sweeps.
        if _ENGINE_SCORE_ASSERT:
            _eng = _engine_score_bar(
                ctx,
                enable_bullish=enable_bullish,
                bear_kwargs=dict(
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
                    bearish_reversal_bypass=include_bearish_reversal_bypass,
                    fhh_quality_proximity=fhh_quality_proximity,
                    fhh_above_max_prior_min=fhh_above_max_prior_min,
                ),
                bull_kwargs=dict(
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
                ),
            )
            assert (
                _eng.bear.passed == result.passed
                and _eng.bear.bear_score == result.bear_score
                and _eng.bear.blockers == result.blockers
                and _eng.bear.triggers_fired == result.triggers_fired
                and _eng.bear.rejection_level == result.rejection_level
            ), (
                "engine.score_bar disagrees with orchestrator bear scoring at "
                f"bar {idx} {bar_time}: engine(passed={_eng.bear.passed}, "
                f"score={_eng.bear.bear_score}, blockers={_eng.bear.blockers}) vs "
                f"orchestrator(passed={result.passed}, score={result.bear_score}, "
                f"blockers={result.blockers})"
            )
            if bull_result is None:
                assert _eng.bull is None, (
                    f"engine.score_bar returned a bull result at bar {idx} "
                    f"{bar_time} but the orchestrator did not (enable_bullish "
                    f"mismatch)"
                )
            else:
                assert (
                    _eng.bull is not None
                    and _eng.bull.passed == bull_result.passed
                    and _eng.bull.bull_score == bull_result.bull_score
                    and _eng.bull.blockers == bull_result.blockers
                    and _eng.bull.triggers_fired == bull_result.triggers_fired
                    and _eng.bull.reclaim_level == bull_result.reclaim_level
                ), (
                    "engine.score_bar disagrees with orchestrator bull scoring at "
                    f"bar {idx} {bar_time}"
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
            # ── ENGINE-GATES ASSERT-AGREE (Phase 2, 2026-06-18) ──
            # The 15 entry gates below are being relocated behind ONE shared
            # interface, backtest/lib/engine.evaluate_gates (the same surface the
            # live heartbeat will call via the engine_cli.py shell-out shim in
            # Phase 3-4). We do NOT yet replace the inline blocks; we run
            # evaluate_gates on the SAME loop locals as an independent oracle and
            # assert it fires the SAME first SKIP action (or allow) the inline
            # cascade does — proving the extraction is faithful with zero
            # behaviour change before any call site depends on it (mirrors the
            # risk-gate + engine.score asserts). Opt-out: GAMMA_ENGINE_GATES_ASSERT=0.
            #
            # The oracle is captured HERE (before gate 1) because all 15 lifted
            # gates are pure over these locals and none reads the
            # setup_quality_taken_today mutation at ~line 1376; the inline cascade
            # then runs as before. ``_assert_gate(action)`` is called just before
            # each inline gate's ``continue`` to assert the engine agreed on that
            # exact SKIP; the entry-reached point asserts the engine returned None.
            if _ENGINE_GATES_ASSERT:
                _eng_gate = _engine_evaluate_gates(
                    _GateContext(
                        winning_side=winning_side,
                        winning_triggers=winning_triggers,
                        quality_tier=quality_tier,
                        has_level=has_level,
                        bar=bar,
                        bar_idx=idx,
                        bar_time=bar_time,
                        vix_now=vix_now,
                        ribbon_spread_cents=ribbon_state.spread_cents,
                        ribbon_stack=ribbon_state.stack,
                        spy_df=spy_df,
                        ribbon_df=ribbon_df,
                    ),
                    params={
                        "block_level_rejection": block_level_rejection,
                        "trendline_requires_ribbon_flip": trendline_requires_ribbon_flip,
                        "block_elite_bull": block_elite_bull,
                        "block_elite_bull_vix_low": block_elite_bull_vix_low,
                        "block_elite_bull_vix_high": block_elite_bull_vix_high,
                        "block_bull_ribbon_flip": block_bull_ribbon_flip,
                        "block_bull_1100_1200": block_bull_1100_1200,
                        "block_bull_morning_agg": block_bull_morning_agg,
                        "require_bearish_fill_bar": require_bearish_fill_bar,
                        "min_ribbon_momentum_cents": min_ribbon_momentum_cents,
                        "max_ribbon_duration_bars": max_ribbon_duration_bars,
                        "midday_trendline_gate": midday_trendline_gate,
                        "midday_trendline_gate_start_minutes": midday_trendline_gate_start_minutes,
                        "block_conf_lvl_rej_midday_afternoon": block_conf_lvl_rej_midday_afternoon,
                        "block_conf_lvl_rec_afternoon": block_conf_lvl_rec_afternoon,
                        "entry_bar_body_pct_min": entry_bar_body_pct_min,
                        "entry_bar_body_pct_min_bull": entry_bar_body_pct_min_bull,
                        "vix_bear_hard_cap": vix_bear_hard_cap,
                    },
                )

                def _assert_gate(_action: str) -> None:
                    assert _eng_gate is not None and _eng_gate.action == _action, (
                        "engine.evaluate_gates disagrees with orchestrator inline "
                        f"gate at bar {idx} {bar_time}: inline fired {_action!r} but "
                        f"engine returned {(_eng_gate.action if _eng_gate else None)!r}"
                    )
            else:
                _eng_gate = None

                def _assert_gate(_action: str) -> None:
                    return None

            # LEVEL_REJECTION_GATE: block all BEAR-side LEVEL-tier level_rejection entries.
            # Must come BEFORE quality lock so blocked trades don't consume the day's LEVEL slot.
            # Specifically targets PUT trades with level_rejection trigger (has_level==True for bears);
            # winning_side=="P" guard ensures BULL level_reclaim LEVEL trades are NOT blocked.
            # WF=0.829 (post-hoc), IS +$13,389 (n=22 bear), OOS +$682 (n=3). Anchor OK.
            if block_level_rejection and quality_tier == "LEVEL" and has_level and winning_side == "P":
                _assert_gate("SKIP_LEVEL_REJECTION_GATE")
                decisions.append({
                    "bar_idx": idx, "timestamp_et": bar_time,
                    "spy_close": float(bar["close"]), "vix": vix_now,
                    "ribbon_stack": ribbon_state.stack,
                    "ribbon_spread_cents": ribbon_state.spread_cents,
                    "htf_15m_stack": htf_stack, "bear_score": result.bear_score,
                    "blockers": ["LEVEL_REJECTION_GATE"],
                    "triggers_fired": winning_triggers,
                    "rejection_level": winning_level, "passed": False,
                    "action": "SKIP_LEVEL_REJECTION_GATE", "setup": setup_name,
                })
                continue

            # TRENDLINE_RIBBON_FLIP_REQUIRED: block TRENDLINE entries lacking ribbon_flip.
            # IS: pure trendline_rejection (n=58, WR=27.6%, avg=-$34) vs ribbon_flip+trendline (n=6, WR=50%, avg=+$312).
            # Gate before quality lock: blocked trades do not consume the TRENDLINE slot.
            if trendline_requires_ribbon_flip and quality_tier == "TRENDLINE":
                _has_rf = "ribbon_flip" in winning_triggers
                if not _has_rf:
                    _assert_gate("SKIP_TRENDLINE_NO_RIBBON_FLIP")
                    decisions.append({
                        "bar_idx": idx, "timestamp_et": bar_time,
                        "spy_close": float(bar["close"]), "vix": vix_now,
                        "ribbon_stack": ribbon_state.stack,
                        "ribbon_spread_cents": ribbon_state.spread_cents,
                        "htf_15m_stack": htf_stack, "bear_score": result.bear_score,
                        "blockers": ["TRENDLINE_RIBBON_FLIP_REQUIRED"],
                        "triggers_fired": winning_triggers,
                        "rejection_level": winning_level, "passed": False,
                        "action": "SKIP_TRENDLINE_NO_RIBBON_FLIP", "setup": setup_name,
                    })
                    continue

            # BLOCK_ELITE_BULL: block ELITE entries where level_reclaim is present (BULL confluence).
            # VIX 15-17 bucket IS n=73 WR=9.6% avg=-$100; VIX <15 and 17+ are winners.
            # Optional block_elite_bull_vix_low/high restrict the gate to a VIX sub-range.
            # Gate before quality lock: blocked ELITE does NOT consume the day's ELITE slot.
            if (block_elite_bull and quality_tier == "ELITE"
                    and "level_reclaim" in winning_triggers
                    and block_elite_bull_vix_low <= vix_now < block_elite_bull_vix_high):
                _assert_gate("SKIP_ELITE_BULL_LEVEL_RECLAIM")
                decisions.append({
                    "bar_idx": idx, "timestamp_et": bar_time,
                    "spy_close": float(bar["close"]), "vix": vix_now,
                    "ribbon_stack": ribbon_state.stack,
                    "ribbon_spread_cents": ribbon_state.spread_cents,
                    "htf_15m_stack": htf_stack, "bear_score": result.bear_score,
                    "blockers": ["BLOCK_ELITE_BULL"],
                    "triggers_fired": winning_triggers,
                    "rejection_level": winning_level, "passed": False,
                    "action": "SKIP_ELITE_BULL_LEVEL_RECLAIM", "setup": setup_name,
                })
                continue

            # BLOCK_BULL_RIBBON_FLIP 2026-06-17: block BULLISH_RECLAIM when ribbon_flip fires.
            # IS: ribbon_flip bull n=21 WR=10% avg=-$106; non-flip bull n=24 WR=29% avg=+$288.
            # ribbon_flip lags the reclaim move — fires after price has already extended.
            if (block_bull_ribbon_flip and winning_side == "C"
                    and "ribbon_flip" in winning_triggers):
                _assert_gate("SKIP_BULL_RIBBON_FLIP")
                decisions.append({
                    "bar_idx": idx, "timestamp_et": bar_time,
                    "spy_close": float(bar["close"]), "vix": vix_now,
                    "ribbon_stack": ribbon_state.stack,
                    "ribbon_spread_cents": ribbon_state.spread_cents,
                    "htf_15m_stack": htf_stack, "bear_score": result.bear_score,
                    "blockers": ["BLOCK_BULL_RIBBON_FLIP"],
                    "triggers_fired": winning_triggers,
                    "rejection_level": winning_level, "passed": False,
                    "action": "SKIP_BULL_RIBBON_FLIP", "setup": setup_name,
                })
                continue

            # BLOCK_BULL_1100_1200 2026-06-18: block ALL BULL entries in 11:00-12:00 ET window.
            # IS: n=11 WR=9.1% total=-$89 (10/11 losers). OOS: n=1 blocked (-$42).
            # OP-22 ratified: IS_delta=+89, OOS_delta=+42, WF=5.22, SW_hurt=1/3, G5 pass.
            if (block_bull_1100_1200 and winning_side == "C"
                    and dt.time(11, 0) <= bar_time_py.time() < dt.time(12, 0)):
                _assert_gate("SKIP_BULL_1100_1200")
                decisions.append({
                    "bar_idx": idx, "timestamp_et": bar_time,
                    "spy_close": float(bar["close"]), "vix": vix_now,
                    "ribbon_stack": ribbon_state.stack,
                    "ribbon_spread_cents": ribbon_state.spread_cents,
                    "htf_15m_stack": htf_stack, "bear_score": result.bear_score,
                    "blockers": ["BLOCK_BULL_1100_1200"],
                    "triggers_fired": winning_triggers,
                    "rejection_level": winning_level, "passed": False,
                    "action": "SKIP_BULL_1100_1200", "setup": setup_name,
                })
                continue

            # BLOCK_BULL_MORNING_AGG 2026-06-18: block ALL BULL (C) entries 10:00-11:30 ET
            # AND >=14:00 ET (covers AFTERNOON + POWER_HOUR). Aggressive account only.
            # MORNING IS: n=47 WR=14.9% -$222. AFTERNOON IS: n=6 WR=0% -$82.
            # POWER_HOUR IS: n=3 WR=33% -$45 (aligns with live entry_no_trade_after_et=15:00).
            # Ratified 2026-06-18. Scorecard: analysis/recommendations/agg_block_bull_morning_afternoon.json.
            if (block_bull_morning_agg and winning_side == "C" and (
                    dt.time(10, 0) <= bar_time_py.time() < dt.time(11, 30)
                    or bar_time_py.time() >= dt.time(14, 0))):
                _assert_gate("SKIP_BULL_MORNING_AGG")
                decisions.append({
                    "bar_idx": idx, "timestamp_et": bar_time,
                    "spy_close": float(bar["close"]), "vix": vix_now,
                    "ribbon_stack": ribbon_state.stack,
                    "ribbon_spread_cents": ribbon_state.spread_cents,
                    "htf_15m_stack": htf_stack, "bear_score": result.bear_score,
                    "blockers": ["BLOCK_BULL_MORNING_AGG"],
                    "triggers_fired": winning_triggers,
                    "rejection_level": winning_level, "passed": False,
                    "action": "SKIP_BULL_MORNING_AGG", "setup": setup_name,
                })
                continue

            # REQUIRE_BEARISH_FILL_BAR: look-ahead gate checking fill bar (idx+1) direction.
            # Fill bar is bearish = immediate follow-through with trade direction (WR=41.1%).
            # Fill bar is bullish = counter-trend bounce at entry (WR=3.4% avg=-$39).
            # NOTE: look-ahead gate (idx+1 unknown at signal time); valid for backtest upper-bound only.
            if require_bearish_fill_bar and winning_side == "P":
                _fill_idx = min(idx + 1, len(spy_df) - 1)
                _fill_bar = spy_df.iloc[_fill_idx]
                _fill_body = float(_fill_bar["close"]) - float(_fill_bar["open"])
                if _fill_body >= 0:  # bullish or doji fill bar — skip
                    _assert_gate("SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY")
                    decisions.append({
                        "bar_idx": idx, "timestamp_et": bar_time,
                        "spy_close": float(bar["close"]), "vix": vix_now,
                        "ribbon_stack": ribbon_state.stack,
                        "ribbon_spread_cents": ribbon_state.spread_cents,
                        "htf_15m_stack": htf_stack, "bear_score": result.bear_score,
                        "blockers": ["REQUIRE_BEARISH_FILL_BAR"],
                        "triggers_fired": winning_triggers,
                        "rejection_level": winning_level, "passed": False,
                        "action": "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY", "setup": setup_name,
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
                        _assert_gate("SKIP_RIBBON_MOMENTUM_GATE")
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
                    _assert_gate("SKIP_RIBBON_DURATION_GATE")
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
                _gate_h, _gate_m = divmod(midday_trendline_gate_start_minutes, 60)
                _is_mid = dt.time(_gate_h, _gate_m) <= bar_time.time() < dt.time(14, 0)
                _is_tl_only = (
                    len(winning_triggers) == 1 and "trendline_rejection" in winning_triggers
                )
                if _is_mid and _is_tl_only:
                    _assert_gate("SKIP_MIDDAY_TRENDLINE_GATE")
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

            # BLOCK_CONF_LVL_REJ_MIDDAY_AFTERNOON (auto-ratified 2026-06-17 AGG, IS+566 OOS+230 WF=2.368)
            if block_conf_lvl_rej_midday_afternoon:
                _is_midday_or_aft = bar_time.time() >= dt.time(11, 30)
                _is_conf_rej = (
                    "confluence" in winning_triggers and "level_rejection" in winning_triggers
                )
                if _is_midday_or_aft and _is_conf_rej:
                    _assert_gate("SKIP_CONF_LVL_REJ_MIDDAY_AFTERNOON")
                    decisions.append({
                        "bar_idx": idx, "timestamp_et": bar_time,
                        "spy_close": float(bar["close"]), "vix": vix_now,
                        "ribbon_stack": ribbon_state.stack,
                        "ribbon_spread_cents": ribbon_state.spread_cents,
                        "htf_15m_stack": htf_stack, "bear_score": result.bear_score,
                        "blockers": ["BLOCK_CONF_LVL_REJ_MIDDAY_AFTERNOON"],
                        "triggers_fired": winning_triggers,
                        "rejection_level": winning_level, "passed": False,
                        "action": "SKIP_CONF_LVL_REJ_MIDDAY_AFTERNOON", "setup": setup_name,
                    })
                    continue

            # BLOCK_CONF_LVL_REC_AFTERNOON (auto-ratified 2026-06-17, IS+412 OOS+176 WF=2.644)
            if block_conf_lvl_rec_afternoon:
                _is_afternoon = bar_time.time() >= dt.time(14, 0)
                _is_conf_rec = (
                    "confluence" in winning_triggers and "level_reclaim" in winning_triggers
                )
                if _is_afternoon and _is_conf_rec:
                    _assert_gate("SKIP_CONF_LVL_REC_AFTERNOON")
                    decisions.append({
                        "bar_idx": idx, "timestamp_et": bar_time,
                        "spy_close": float(bar["close"]), "vix": vix_now,
                        "ribbon_stack": ribbon_state.stack,
                        "ribbon_spread_cents": ribbon_state.spread_cents,
                        "htf_15m_stack": htf_stack, "bear_score": result.bear_score,
                        "blockers": ["BLOCK_CONF_LVL_REC_AFTERNOON"],
                        "triggers_fired": winning_triggers,
                        "rejection_level": winning_level, "passed": False,
                        "action": "SKIP_CONF_LVL_REC_AFTERNOON", "setup": setup_name,
                    })
                    continue

            # Resolve asymmetric stop + strike for both real-fills and BS-sim paths.
            # Bug fix 2026-06-16: real-fills path previously passed the GLOBAL premium_stop_pct
            # (-0.08 default) instead of the side-specific bear/bull stop. This meant all
            # real-fills backtests used a -8% stop regardless of premium_stop_pct_bear=-0.20
            # in params.json — a C14/L38-class mismatch between simulation and production.
            side_premium_stop = bear_premium_stop if winning_side == "P" else bull_premium_stop
            side_strike_off = bear_strike_off if winning_side == "P" else bull_strike_off

            # ENTRY_BAR_BODY_PCT_MIN: block BEAR entries on doji/wick-dominant bars.
            if entry_bar_body_pct_min > 0.0 and winning_side == "P":
                _entry_geo = _bar_geometry(bar)
                if _entry_geo["body_pct"] < entry_bar_body_pct_min:
                    _assert_gate("SKIP_DOJI_ENTRY_BAR")
                    decisions.append({
                        "bar_idx": idx, "timestamp_et": bar_time,
                        "spy_close": float(bar["close"]), "vix": vix_now,
                        "ribbon_stack": ribbon_state.stack,
                        "ribbon_spread_cents": ribbon_state.spread_cents,
                        "htf_15m_stack": htf_stack,
                        "blockers": ["ENTRY_BAR_BODY_PCT_GATE"],
                        "triggers_fired": winning_triggers,
                        "rejection_level": winning_level, "passed": False,
                        "action": "SKIP_DOJI_ENTRY_BAR",
                        "setup": setup_name,
                    })
                    continue

            # ENTRY_BAR_BODY_PCT_MIN_BULL: same gate for BULL (C) entries.
            if entry_bar_body_pct_min_bull > 0.0 and winning_side == "C":
                _entry_geo_c = _bar_geometry(bar)
                if _entry_geo_c["body_pct"] < entry_bar_body_pct_min_bull:
                    _assert_gate("SKIP_DOJI_ENTRY_BAR_BULL")
                    decisions.append({
                        "bar_idx": idx, "timestamp_et": bar_time,
                        "spy_close": float(bar["close"]), "vix": vix_now,
                        "ribbon_stack": ribbon_state.stack,
                        "ribbon_spread_cents": ribbon_state.spread_cents,
                        "htf_15m_stack": htf_stack,
                        "blockers": ["ENTRY_BAR_BODY_PCT_GATE_BULL"],
                        "triggers_fired": winning_triggers,
                        "rejection_level": winning_level, "passed": False,
                        "action": "SKIP_DOJI_ENTRY_BAR_BULL",
                        "setup": setup_name,
                    })
                    continue

            # VIX_BEAR_HARD_CAP gate: block BEAR entries when VIX is at or above the cap.
            if vix_bear_hard_cap is not None and winning_side == "P" and vix_now >= vix_bear_hard_cap:
                _assert_gate("SKIP_VIX_BEAR_HIGH")
                decisions.append({
                    "bar_idx": idx, "timestamp_et": bar_time,
                    "spy_close": float(bar["close"]), "vix": vix_now,
                    "ribbon_stack": ribbon_state.stack,
                    "ribbon_spread_cents": ribbon_state.spread_cents,
                    "htf_15m_stack": htf_stack,
                    "blockers": ["VIX_BEAR_HARD_CAP"],
                    "triggers_fired": winning_triggers,
                    "rejection_level": winning_level, "passed": False,
                    "action": "SKIP_VIX_BEAR_HIGH",
                    "setup": setup_name,
                })
                continue

            # ── ENGINE-GATES ASSERT-AGREE: allow side (Phase 2) ──
            # Reaching here means the inline cascade passed ALL 15 lifted gates.
            # The engine oracle (captured before gate 1) must therefore have
            # returned None (allow). The two non-lifted skips that can still fire
            # below — SKIP_NO_PULLBACK (V_PULLBACK) and downstream sizing skips —
            # are deliberately NOT part of evaluate_gates' scope, so None here is
            # the correct, faithful agreement.
            if _ENGINE_GATES_ASSERT:
                assert _eng_gate is None, (
                    "engine.evaluate_gates disagrees with orchestrator inline gates "
                    f"at bar {idx} {bar_time}: inline ALLOWED (passed all 15 gates) "
                    f"but engine returned SKIP {_eng_gate.action!r}"
                )

            # V_PULLBACK gate: scan forward for a pullback to the level before entering.
            actual_entry_idx = idx
            actual_entry_bar = bar
            if v_pullback_enabled and winning_level is not None:
                _pb_found = None
                _scan_end = min(idx + 1 + v_pullback_window_bars, len(spy_df))
                for _k in range(idx + 1, _scan_end):
                    _pb = spy_df.iloc[_k]
                    if winning_side == "C":
                        _touched = float(_pb["low"]) <= winning_level + v_pullback_level_tolerance
                    else:
                        _touched = float(_pb["high"]) >= winning_level - v_pullback_level_tolerance
                    if _touched and _k + 1 < len(spy_df):
                        _pb_found = _k
                        break
                if _pb_found is None:
                    decisions.append({
                        "bar_idx": idx, "timestamp_et": bar_time,
                        "spy_close": float(bar["close"]), "vix": vix_now,
                        "ribbon_stack": ribbon_state.stack,
                        "ribbon_spread_cents": ribbon_state.spread_cents,
                        "htf_15m_stack": htf_stack,
                        "blockers": [],
                        "triggers_fired": winning_triggers,
                        "rejection_level": winning_level, "passed": False,
                        "action": "SKIP_NO_PULLBACK",
                        "setup": setup_name,
                    })
                    continue
                actual_entry_idx = _pb_found
                actual_entry_bar = spy_df.iloc[_pb_found]

            if use_real_fills:
                fill = simulate_trade_real(
                    entry_bar_idx=actual_entry_idx,
                    entry_bar=actual_entry_bar,
                    spy_df=spy_df,
                    ribbon_df=ribbon_df,
                    rejection_level=winning_level,
                    triggers_fired=winning_triggers,
                    side=winning_side,
                    setup=setup_name,
                    levels_active=level_set.active,
                    levels_carry=level_set.multi_day,
                    premium_stop_pct=side_premium_stop,
                    strike_offset=side_strike_off,
                    qty=trade_qty,   # NEW v13 — quality-tiered sizing
                    profit_lock_threshold_pct=profit_lock_threshold_pct,    # NEW T41 2026-05-13: parity with BS path
                    profit_lock_stop_offset_pct=profit_lock_stop_offset_pct,  # NEW T41 2026-05-13: parity with BS path
                    profit_lock_mode=profit_lock_mode,                       # NEW T50b 2026-05-13: trailing/stepped support
                    profit_lock_trail_pct=profit_lock_trail_pct,             # NEW T50b 2026-05-13
                    ribbon_flip_price_confirm=ribbon_flip_price_confirm,     # NEW 2026-06-16: price gate before flip-back exit
                    tp1_qty_fraction=tp1_qty_fraction,                       # L108 2026-06-17: was missing, hardcoded 0.667 in real-fills path
                    runner_target_premium_pct=runner_target_premium_pct,     # L109 2026-06-17: was missing, hardcoded 3.0 in real-fills path (prod=2.5)
                    tp1_premium_pct=tp1_premium_pct,                         # L110 2026-06-17: was missing, hardcoded 0.30 in real-fills path (effective_tp1 is BS-sim-only quality override)
                    time_stop_et=time_stop_et,                               # L110 2026-06-17: was missing, hardcoded 15:50 in real-fills path (values matched, future-proof)
                )
                if fill is not None:
                    fill.entry_vix = vix_now
                    fill.entry_iv = vix_now / 100.0
                if fill is None:
                    # Cache miss — fall back to BS only for puts (BS sim is puts-only)
                    if winning_side == "P":
                        fill = simulate_trade(
                            entry_bar_idx=actual_entry_idx,
                            entry_bar=actual_entry_bar,
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
                # side_premium_stop / side_strike_off already computed above.
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
                if (
                    fill is not None
                    and quality_tier in ("LEVEL", "ELITE", "SUPER")
                    and fill.entry_premium < min_premium_for_level_tiers
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
                        "min_required": min_premium_for_level_tiers,
                        "reason": "entry premium below minimum for level-tied tiers (OP 17 EV gate)",
                    })
                    fill = None
                    # Roll back the escalation lock so a higher-quality trigger can
                    # still fire today (we never actually placed the trade).
                    if prior_quality > 0:
                        setup_quality_taken_today[lock_key] = prior_quality
                    else:
                        setup_quality_taken_today.pop(lock_key, None)

            # Per-trade risk cap: mirrors live heartbeat Rule 6 enforcement.
            # Scale qty down linearly when notional cost exceeds cap.
            # Exit timing is unaffected; option P&L is linear in qty.
            if fill is not None and initial_equity > 0 and per_trade_risk_cap_pct > 0:
                max_cost = initial_equity * per_trade_risk_cap_pct
                fill_cost = fill.entry_premium * fill.qty * 100
                if fill_cost > max_cost and fill.entry_premium > 0:
                    # int() truncates toward zero (conservative — never exceeds cap).
                    # max(3, ...) matches Rule 6 minimum: 2-TP + 1-runner. When even
                    # 3 contracts exceed cap (small account + high premium), the 3-
                    # contract floor intentionally overrides the pct cap — same as
                    # live heartbeat behaviour.
                    capped_qty = max(3, int(max_cost / (fill.entry_premium * 100)))
                    if capped_qty < fill.qty:
                        fill.dollar_pnl = fill.dollar_pnl * (capped_qty / fill.qty)
                        fill.qty = capped_qty
                        # Recompute explicitly — pct_return is mathematically
                        # unchanged by linear scaling, but make the invariant
                        # explicit so future non-linear changes don't silently
                        # produce stale return metrics.
                        if fill.entry_premium > 0 and fill.qty > 0:
                            fill.pct_return_on_premium = (
                                fill.dollar_pnl / (fill.entry_premium * fill.qty * 100)
                            )

                # ── RISK-GATE ASSERT-AGREE (Phase 0c, 2026-06-18) ──
                # The canonical pre-order risk logic now lives in ONE place:
                # backtest/lib/risk_gate.check_order (the same function the live
                # heartbeat will call). We don't REPLACE the linear qty-scaling
                # above (scaling is a backtest convenience — live denies rather
                # than auto-resizes), but we ASSERT the engine's FINAL qty agrees
                # with the gate's per-trade risk cap so backtest-risk can never
                # silently diverge from live-risk-intent. The gate is an
                # independent oracle: feed it the post-scaling order and confirm
                # it does NOT flag RISK_CAP — unless the documented min-contracts
                # floor (max(3,...) above) intentionally overrode the pct cap on
                # a small account, which the gate reports as MIN_CONTRACTS/allows.
                # Opt-out via GAMMA_RISK_GATE_ASSERT=0 for perf-sensitive sweeps.
                if fill is not None and _RISK_GATE_ASSERT and per_trade_risk_cap_pct > 0:
                    _gate_params = {
                        "per_trade_risk_cap_pct": per_trade_risk_cap_pct,
                        # Backtest models a single mid-session entry; these gates
                        # are exercised directly in test_risk_gate.py, so here we
                        # neutralise them (flat, no kill, no prior stop, no PDT)
                        # and assert ONLY the sizing agreement, which is what the
                        # orchestrator itself enforces at this point.
                        "daily_loss_kill_switch_pct": 0.999,
                        "min_contracts": 3,
                        "first_entry_after_stop_blocked": False,
                    }
                    # Label is for the gate's message only; infer from the cap
                    # (Safe 30% / Bold 50%) since the orchestrator isn't told the
                    # alias directly.
                    _acct_label = (
                        "Gamma-Bold" if per_trade_risk_cap_pct >= 0.50 else "Gamma-Safe"
                    )
                    _gate_dec = _risk_check_order(
                        _acct_label,
                        equity=float(initial_equity),
                        start_of_day_equity=float(initial_equity),
                        proposed_qty=int(fill.qty),
                        premium=float(fill.entry_premium),
                        setup_name=setup_name,
                        current_position_status="flat",
                        day_trades_used_5d=0,
                        kill_switch_tripped=False,
                        prior_stops_today=(),
                        params=_gate_params,
                    )
                    # Engine's final qty must NEVER be a risk-cap violation. The
                    # only way notional can exceed the cap is the min-3 floor on a
                    # tiny account (premium so high that even 3 contracts breach
                    # the pct) — that override is intentional and identical in the
                    # live heartbeat, so we allow it explicitly.
                    _floor_override = (
                        int(fill.qty) <= 3
                        and fill.entry_premium * fill.qty * 100
                        > float(initial_equity) * per_trade_risk_cap_pct
                    )
                    assert _gate_dec.code != "RISK_CAP" or _floor_override, (
                        "risk_gate disagrees with orchestrator sizing: final qty "
                        f"{fill.qty} @ ${fill.entry_premium:.2f} on equity "
                        f"${initial_equity:,.0f} (cap {per_trade_risk_cap_pct:.0%}) "
                        f"-> gate says {_gate_dec.code}: {_gate_dec.reason}"
                    )

            if fill is not None:
                trades.append(fill)
                # Record whether this fill stopped out (for leg-2 detection on the
                # next trigger fire on the same setup today). A "stop" means the
                # trade exited without ever hitting TP1 -- the setup zone may have
                # been right but the timing was wrong.
                exit_reason_str = str(fill.exit_reason) if fill.exit_reason else ""
                # A profitable profit-lock exit (tp1=None but pnl>0) is NOT a stop —
                # it means the trade was right but captured only a partial move.
                # Allowing TRENDLINE_LEG2 on a profitable exit caused 4/29 -$414:
                # 12:15 profit-lock exit (+$94, qty=3) triggered LEG2 re-entry at
                # qty=20, then 13:45 bad entry wiped -$508. Only count as stopped
                # when the trade actually lost money (pnl <= 0).
                stopped_without_tp1 = (
                    fill.tp1_time_et is None
                    and (fill.dollar_pnl or 0.0) <= 0.0
                    and (
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
    # Restore any filter module constants patched above.
    for _fa, _v in _filter_const_saved.items():
        setattr(_filters_mod, _fa, _v)
    return BacktestResult(trades=trades, decisions=decisions, metadata=metadata)
