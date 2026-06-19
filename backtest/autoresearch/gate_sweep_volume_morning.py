"""Gate sweep: volume-compensated (B1-B6) and morning-window (F1-F5) entry relaxation.

Tests whether relaxing the 10/10 filter requirement is safe when volume OR morning-window
conditions provide additional confirmation. Designed to expand the J winner day hits without
opening the flood gates on loser days.

Scenarios:
  Category B (volume-compensated):
    B1: bear_score >= 9 AND vol_ratio >= 2.0
    B2: bear_score >= 8 AND vol_ratio >= 2.0
    B3: bear_score >= 7 AND vol_ratio >= 4.0 (blowoff/panic bar)
    B4: bear_score >= 8 AND vol_ratio >= 2.0 AND time 09:35-10:15
    B5: bear_score >= 8 AND vol_ratio >= 3.0 AND ribbon_spread >= 60 cents
    B6: bull_score >= 9 AND vol_ratio >= 2.0 (bullish mirror)

  Category F (morning window):
    F1: bear_score >= 8 AND time 09:35-10:00
    F2: bear_score >= 7 AND time 09:35-10:15 AND within $0.30 of any active level
    F3: bear_score >= 7 AND time 09:35-10:00 AND gap (today open > prior close by > $0.30)
    F4: bear_score >= 6 AND time 09:35-09:55 AND vol_ratio >= 4.0 AND any level within $0.40
    F5: bear_score >= 7 AND time 09:35-10:15 AND vol_ratio >= 2.0 (morning + volume)

Baseline: 10/10 production (result.passed == True with standard params)

Output: analysis/recommendations/gate_sweep_volume_morning.json
Cost: $0 (pure Python)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from lib.ribbon import compute_ribbon, ribbon_at
from lib.filters import (
    BarContext, SetupResult, BullishSetupResult,
    evaluate_bearish_setup, evaluate_bullish_setup,
    vol_baseline_20bar, range_baseline_20bar,
    LevelState,
)
from lib.orchestrator import (
    _align_vix_to_spy,
    _precompute_htf_15m_stacks,
    _update_level_states,
    _FILTER_CONST_MAP,
    BacktestResult,
)
from lib.levels import _detect_from_history, LevelSet
from lib.simulator_real import simulate_trade_real
from lib.ribbon import compute_ribbon as _compute_ribbon_df
import lib.filters as _filters_mod


# ──────────────────────────────────────────────────────────────────────────────
# J edge reference (OP-16)
# ──────────────────────────────────────────────────────────────────────────────

J_WINNERS = {"2026-04-29": 342, "2026-05-01": 470, "2026-05-04": 730}
J_LOSERS  = {"2026-05-05": -260, "2026-05-06": -300, "2026-05-07": -165}
OP16_FLOOR = 771
MAX_POSSIBLE = 1542
ALL_J_DAYS = list(J_WINNERS) + list(J_LOSERS)

# ──────────────────────────────────────────────────────────────────────────────
# v15 production params baseline
# ──────────────────────────────────────────────────────────────────────────────

BASE_PARAMS = dict(
    premium_stop_pct_bear=-0.10,
    premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.50,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5,
    f9_vol_mult=0.7,
    profit_lock_mode="trailing",
    profit_lock_threshold_pct=0.05,
    profit_lock_trail_pct=0.20,
)

# Quality tier qty (mirrors orchestrator)
QUALITY_QTY = {4: 15, 3: 10, 2: 22, 1: 3}


# ──────────────────────────────────────────────────────────────────────────────
# Extra condition predicates
# ──────────────────────────────────────────────────────────────────────────────

def _vol_ratio(bar, vol_baseline_20: float) -> float:
    if vol_baseline_20 <= 0:
        return 0.0
    return float(bar["volume"]) / vol_baseline_20


def _near_level(bar, levels_active: list, proximity: float) -> bool:
    if not levels_active:
        return False
    close = float(bar["close"])
    return any(abs(close - lv) <= proximity for lv in levels_active)


def _ribbon_spread(ribbon_now) -> float:
    if ribbon_now is None:
        return 0.0
    return ribbon_now.spread_cents


# ──────────────────────────────────────────────────────────────────────────────
# Scenario definitions
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Scenario:
    id: str
    name: str
    side: str            # "bear" | "bull"
    score_min: int       # minimum bear_score / bull_score to trigger
    extra_fn: object     # callable(ctx, result) -> bool (extra condition beyond score)

    def check(self, ctx: BarContext, result, prior_day_close: Optional[float]) -> bool:
        if self.side == "bear":
            score = result.bear_score
        else:
            score = result.bull_score
        if score < self.score_min:
            return False
        # Must have at least one trigger fired to be meaningful
        if not result.triggers_fired:
            return False
        return self.extra_fn(ctx, result, prior_day_close)


def _make_scenarios() -> list[Scenario]:
    TIME_0935 = dt.time(9, 35)
    TIME_0955 = dt.time(9, 55)
    TIME_1000 = dt.time(10, 0)
    TIME_1015 = dt.time(10, 15)

    def b1(ctx, r, _pdc):
        t = ctx.timestamp_et.time()
        return t >= TIME_0935 and _vol_ratio(ctx.bar, ctx.vol_baseline_20) >= 2.0

    def b2(ctx, r, _pdc):
        t = ctx.timestamp_et.time()
        return t >= TIME_0935 and _vol_ratio(ctx.bar, ctx.vol_baseline_20) >= 2.0

    def b3(ctx, r, _pdc):
        t = ctx.timestamp_et.time()
        return t >= TIME_0935 and _vol_ratio(ctx.bar, ctx.vol_baseline_20) >= 4.0

    def b4(ctx, r, _pdc):
        t = ctx.timestamp_et.time()
        return (TIME_0935 <= t <= TIME_1015
                and _vol_ratio(ctx.bar, ctx.vol_baseline_20) >= 2.0)

    def b5(ctx, r, _pdc):
        t = ctx.timestamp_et.time()
        return (t >= TIME_0935
                and _vol_ratio(ctx.bar, ctx.vol_baseline_20) >= 3.0
                and _ribbon_spread(ctx.ribbon_now) >= 60.0)

    def b6(ctx, r, _pdc):
        t = ctx.timestamp_et.time()
        return t >= TIME_0935 and _vol_ratio(ctx.bar, ctx.vol_baseline_20) >= 2.0

    def f1(ctx, r, _pdc):
        t = ctx.timestamp_et.time()
        return TIME_0935 <= t < TIME_1000

    def f2(ctx, r, _pdc):
        t = ctx.timestamp_et.time()
        return (TIME_0935 <= t <= TIME_1015
                and _near_level(ctx.bar, ctx.levels_active, 0.30))

    def f3(ctx, r, pdc):
        t = ctx.timestamp_et.time()
        if not (TIME_0935 <= t < TIME_1000):
            return False
        if pdc is None:
            return False
        today_open = float(ctx.prior_bars.iloc[0]["open"]) if len(ctx.prior_bars) > 0 else None
        if today_open is None:
            return False
        return (today_open - pdc) > 0.30

    def f4(ctx, r, _pdc):
        t = ctx.timestamp_et.time()
        return (TIME_0935 <= t < TIME_0955
                and _vol_ratio(ctx.bar, ctx.vol_baseline_20) >= 4.0
                and _near_level(ctx.bar, ctx.levels_active, 0.40))

    def f5(ctx, r, _pdc):
        t = ctx.timestamp_et.time()
        return (TIME_0935 <= t <= TIME_1015
                and _vol_ratio(ctx.bar, ctx.vol_baseline_20) >= 2.0)

    return [
        Scenario("B1", "bear_score>=9 + vol>=2x",            "bear", 9,  b1),
        Scenario("B2", "bear_score>=8 + vol>=2x",            "bear", 8,  b2),
        Scenario("B3", "bear_score>=7 + vol>=4x (panic)",    "bear", 7,  b3),
        Scenario("B4", "bear_score>=8 + vol>=2x + AM-window","bear", 8,  b4),
        Scenario("B5", "bear_score>=8 + vol>=3x + spread>=60c","bear",8, b5),
        Scenario("B6", "bull_score>=9 + vol>=2x",            "bull", 9,  b6),
        Scenario("F1", "bear_score>=8 + AM 09:35-10:00",     "bear", 8,  f1),
        Scenario("F2", "bear_score>=7 + AM + near_level $0.30","bear",7, f2),
        Scenario("F3", "bear_score>=7 + AM + gap >$0.30",    "bear", 7,  f3),
        Scenario("F4", "bear_score>=6 + 09:35-09:55 + vol4x + level $0.40","bear",6,f4),
        Scenario("F5", "bear_score>=7 + AM + vol>=2x",       "bear", 7,  f5),
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Quality tier computation (mirrors orchestrator)
# ──────────────────────────────────────────────────────────────────────────────

def _quality_from_triggers(triggers: list[str], side: str) -> tuple[int, int]:
    """Returns (quality_rank, trade_qty)."""
    level_tied_trig = "level_reclaim" if side == "C" else "level_rejection"
    seq_trig = "sequence_reclaim" if side == "C" else "sequence_rejection"
    has_level = level_tied_trig in triggers or "fhh_level_rejection" in triggers
    has_confluence = "confluence" in triggers
    has_sequence = seq_trig in triggers
    has_ribbon_flip = "ribbon_flip" in triggers
    has_trendline = "trendline_rejection" in triggers
    n_triggers = len(triggers)

    if (has_confluence and has_ribbon_flip) or n_triggers >= 3:
        return 4, QUALITY_QTY[4]
    elif has_confluence or has_sequence:
        return 3, QUALITY_QTY[3]
    elif has_level:
        return 2, QUALITY_QTY[2]
    elif has_trendline:
        return 1, QUALITY_QTY[1]
    else:
        return 1, QUALITY_QTY[1]


# ──────────────────────────────────────────────────────────────────────────────
# Mini-orchestrator for a single day
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TradeRecord:
    date: str
    entry_time: str
    side: str       # "P" or "C"
    pnl: float
    triggers: list[str]
    quality_tier: str
    bear_score: int
    vol_ratio: float
    bar_time: dt.time


def _run_day_scenario(
    spy_df_full: pd.DataFrame,
    spy_df_rth: pd.DataFrame,
    vix_aligned: pd.Series,
    ribbon_df: pd.DataFrame,
    htf_stacks: list,
    level_cache: dict,
    date: dt.date,
    scenario: Scenario,
    prior_day_close: Optional[float],
    level_states_in: dict,     # shared across scenarios for same day
) -> list[TradeRecord]:
    """Run the mini-orchestrator for one day under one scenario. Returns trades."""
    trades_out: list[TradeRecord] = []
    level_states: dict = dict(level_states_in)  # per-scenario copy for isolation

    # Quality escalation lock (day-level, per scenario)
    quality_taken = 0    # highest quality rank traded today
    in_trade = False
    skip_until_idx = -1
    date_str = date.isoformat()

    for idx in range(len(spy_df_rth)):
        if idx <= skip_until_idx:
            continue

        bar = spy_df_rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        bar_time_py = bar_time.to_pydatetime() if hasattr(bar_time, "to_pydatetime") else bar_time

        if bar_time_py.date() != date:
            continue
        if bar_time_py.time() < dt.time(9, 35) or bar_time_py.time() >= dt.time(15, 50):
            continue

        ribbon_state = ribbon_at(ribbon_df, idx)
        if ribbon_state is None:
            continue

        _rlb = _filters_mod.RIBBON_FLIP_LOOKBACK_BARS
        ribbon_history = [ribbon_at(ribbon_df, j) for j in range(max(0, idx - _rlb - 1), idx + 1)]

        vix_now = float(vix_aligned.iloc[idx])
        vix_prior = float(vix_aligned.iloc[idx - 1]) if idx > 0 else vix_now
        vol_baseline = vol_baseline_20bar(spy_df_rth, idx)
        range_baseline = range_baseline_20bar(spy_df_rth, idx)

        # Levels — from cache
        level_set = level_cache.get(date)
        if level_set is None:
            full_hist_mask = spy_df_full["timestamp_et"] <= bar_time
            full_history = spy_df_full[full_hist_mask]
            level_set = _detect_from_history(full_history, date)
            level_cache[date] = level_set

        _update_level_states(level_states, level_set.active, bar, idx)
        htf_stack = htf_stacks[idx]

        ctx = BarContext(
            bar_idx=idx,
            timestamp_et=bar_time_py,
            bar=bar,
            prior_bars=spy_df_rth,
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

        # Evaluate both setups — we need scores regardless of scenario side
        bear_result = evaluate_bearish_setup(
            ctx,
            f9_vol_mult=BASE_PARAMS["f9_vol_mult"],
        )
        bull_result = evaluate_bullish_setup(
            ctx,
            f10_vol_mult=BASE_PARAMS["f9_vol_mult"],
        )

        # Select the right result for the scenario
        if scenario.side == "bear":
            active_result = bear_result
        else:
            active_result = bull_result  # type: ignore[assignment]

        # Check scenario gate
        if not scenario.check(ctx, active_result, prior_day_close):
            continue

        # Need at least one trigger
        if not active_result.triggers_fired:
            continue

        # Quality escalation lock
        side_char = "C" if scenario.side == "bull" else "P"
        quality_rank, trade_qty = _quality_from_triggers(active_result.triggers_fired, side_char)
        if quality_rank <= quality_taken:
            continue

        # Simulate trade
        vol_r = _vol_ratio(ctx.bar, vol_baseline)
        entry_level = (
            active_result.rejection_level if scenario.side == "bear"
            else getattr(active_result, "reclaim_level", None)
        )
        # rejection_level=None falls back to entry_spot in simulator_real (level-stop disabled)
        effective_entry_level = entry_level if entry_level is not None else float(bar["close"])

        try:
            fill = simulate_trade_real(
                entry_bar_idx=idx,
                entry_bar=bar,
                spy_df=spy_df_rth,
                ribbon_df=ribbon_df,
                rejection_level=effective_entry_level,
                triggers_fired=list(active_result.triggers_fired),
                side=side_char,
                qty=trade_qty,
                premium_stop_pct=(
                    BASE_PARAMS["premium_stop_pct_bear"] if side_char == "P"
                    else BASE_PARAMS["premium_stop_pct_bull"]
                ),
                tp1_premium_pct=BASE_PARAMS["tp1_premium_pct"],
                tp1_qty_fraction=BASE_PARAMS["tp1_qty_fraction"],
                runner_target_premium_pct=BASE_PARAMS["runner_target_premium_pct"],
                profit_lock_mode=BASE_PARAMS["profit_lock_mode"],
                profit_lock_threshold_pct=BASE_PARAMS["profit_lock_threshold_pct"],
                profit_lock_trail_pct=BASE_PARAMS["profit_lock_trail_pct"],
            )
        except Exception:
            continue

        if fill is None:
            continue

        skip_until_idx = idx + fill.bars_held if fill.bars_held > 0 else idx
        quality_taken = quality_rank
        tier_name = {4: "SUPER", 3: "ELITE", 2: "LEVEL", 1: "TRENDLINE"}.get(quality_rank, "BASE")

        trades_out.append(TradeRecord(
            date=date_str,
            entry_time=bar_time_py.strftime("%H:%M"),
            side=side_char,
            pnl=float(fill.dollar_pnl),
            triggers=list(active_result.triggers_fired),
            quality_tier=tier_name,
            bear_score=active_result.bear_score if scenario.side == "bear" else active_result.bull_score,
            vol_ratio=round(vol_r, 2),
            bar_time=bar_time_py.time(),
        ))

    return trades_out


# ──────────────────────────────────────────────────────────────────────────────
# Baseline: production 10/10 run (result.passed == True)
# ──────────────────────────────────────────────────────────────────────────────

def _run_day_baseline(
    spy_df_full: pd.DataFrame,
    spy_df_rth: pd.DataFrame,
    vix_aligned: pd.Series,
    ribbon_df,
    htf_stacks: list,
    level_cache: dict,
    date: dt.date,
    level_states_in: dict,
) -> list[TradeRecord]:
    """Run baseline (passed==True) for one day."""
    trades_out: list[TradeRecord] = []
    level_states: dict = dict(level_states_in)
    quality_taken = 0
    skip_until_idx = -1
    date_str = date.isoformat()

    for idx in range(len(spy_df_rth)):
        if idx <= skip_until_idx:
            continue

        bar = spy_df_rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        bar_time_py = bar_time.to_pydatetime() if hasattr(bar_time, "to_pydatetime") else bar_time

        if bar_time_py.date() != date:
            continue
        if bar_time_py.time() < dt.time(9, 35) or bar_time_py.time() >= dt.time(15, 50):
            continue

        ribbon_state = ribbon_at(ribbon_df, idx)
        if ribbon_state is None:
            continue

        _rlb = _filters_mod.RIBBON_FLIP_LOOKBACK_BARS
        ribbon_history = [ribbon_at(ribbon_df, j) for j in range(max(0, idx - _rlb - 1), idx + 1)]

        vix_now = float(vix_aligned.iloc[idx])
        vix_prior = float(vix_aligned.iloc[idx - 1]) if idx > 0 else vix_now
        vol_baseline = vol_baseline_20bar(spy_df_rth, idx)
        range_baseline = range_baseline_20bar(spy_df_rth, idx)

        level_set = level_cache.get(date)
        if level_set is None:
            full_hist_mask = spy_df_full["timestamp_et"] <= bar_time
            full_history = spy_df_full[full_hist_mask]
            level_set = _detect_from_history(full_history, date)
            level_cache[date] = level_set

        _update_level_states(level_states, level_set.active, bar, idx)
        htf_stack = htf_stacks[idx]

        ctx = BarContext(
            bar_idx=idx,
            timestamp_et=bar_time_py,
            bar=bar,
            prior_bars=spy_df_rth,
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

        bear_result = evaluate_bearish_setup(ctx, f9_vol_mult=BASE_PARAMS["f9_vol_mult"])
        bull_result = evaluate_bullish_setup(ctx, f10_vol_mult=BASE_PARAMS["f9_vol_mult"])

        # Standard production: only take when passed
        bear_passed = bear_result.passed
        bull_passed = bull_result.passed

        if not bear_passed and not bull_passed:
            continue

        # Direction selection: higher trigger count wins
        if bear_passed and bull_passed:
            if len(bear_result.triggers_fired) >= len(bull_result.triggers_fired):
                bull_passed = False
            else:
                bear_passed = False

        active_result = bear_result if bear_passed else bull_result
        side_char = "P" if bear_passed else "C"

        quality_rank, trade_qty = _quality_from_triggers(active_result.triggers_fired, side_char)
        if quality_rank <= quality_taken:
            continue

        vol_r = _vol_ratio(ctx.bar, vol_baseline)
        entry_level = (
            active_result.rejection_level if side_char == "P"
            else getattr(active_result, "reclaim_level", None)
        )
        effective_entry_level = entry_level if entry_level is not None else float(bar["close"])

        try:
            fill = simulate_trade_real(
                entry_bar_idx=idx,
                entry_bar=bar,
                spy_df=spy_df_rth,
                ribbon_df=ribbon_df,
                rejection_level=effective_entry_level,
                triggers_fired=list(active_result.triggers_fired),
                side=side_char,
                qty=trade_qty,
                premium_stop_pct=(
                    BASE_PARAMS["premium_stop_pct_bear"] if side_char == "P"
                    else BASE_PARAMS["premium_stop_pct_bull"]
                ),
                tp1_premium_pct=BASE_PARAMS["tp1_premium_pct"],
                tp1_qty_fraction=BASE_PARAMS["tp1_qty_fraction"],
                runner_target_premium_pct=BASE_PARAMS["runner_target_premium_pct"],
                profit_lock_mode=BASE_PARAMS["profit_lock_mode"],
                profit_lock_threshold_pct=BASE_PARAMS["profit_lock_threshold_pct"],
                profit_lock_trail_pct=BASE_PARAMS["profit_lock_trail_pct"],
            )
        except Exception:
            continue

        if fill is None:
            continue

        skip_until_idx = idx + fill.bars_held if fill.bars_held > 0 else idx
        quality_taken = quality_rank
        tier_name = {4: "SUPER", 3: "ELITE", 2: "LEVEL", 1: "TRENDLINE"}.get(quality_rank, "BASE")

        trades_out.append(TradeRecord(
            date=date_str,
            entry_time=bar_time_py.strftime("%H:%M"),
            side=side_char,
            pnl=float(fill.dollar_pnl),
            triggers=list(active_result.triggers_fired),
            quality_tier=tier_name,
            bear_score=(
                active_result.bear_score if side_char == "P"
                else active_result.bull_score
            ),
            vol_ratio=round(vol_r, 2),
            bar_time=bar_time_py.time(),
        ))

    return trades_out


# ──────────────────────────────────────────────────────────────────────────────
# Edge capture computation
# ──────────────────────────────────────────────────────────────────────────────

def _compute_edge(trades_by_day: dict[str, list[TradeRecord]]) -> dict:
    """Compute OP-16 edge_capture from a dict of {date_str: [TradeRecord]}."""
    winner_pnl = 0.0
    loser_exposure = 0.0
    for day, j_val in J_WINNERS.items():
        day_trades = trades_by_day.get(day, [])
        day_pnl = sum(t.pnl for t in day_trades)
        winner_pnl += day_pnl

    for day, j_val in J_LOSERS.items():
        day_trades = trades_by_day.get(day, [])
        day_pnl = sum(t.pnl for t in day_trades)
        loser_exposure += max(0.0, -day_pnl)

    edge_capture = winner_pnl - loser_exposure
    return {
        "winner_pnl": round(winner_pnl, 2),
        "loser_exposure": round(loser_exposure, 2),
        "edge_capture": round(edge_capture, 2),
        "edge_pct_of_max": round(edge_capture / MAX_POSSIBLE * 100, 1),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Full backtest run for a scenario across J days
# ──────────────────────────────────────────────────────────────────────────────

def _run_scenario_j_days(
    scenario: Scenario,
    spy_df_full: pd.DataFrame,
    spy_df_rth: pd.DataFrame,
    vix_aligned: pd.Series,
    ribbon_df,
    htf_stacks: list,
    level_cache: dict,
    baseline_trades_by_day: dict,  # {date_str: [TradeRecord]} from baseline run
) -> dict:
    """Run scenario on all J days. Return per-day P&L and edge metrics."""
    trades_by_day: dict[str, list[TradeRecord]] = {}
    prior_day_close: dict[str, Optional[float]] = {}

    # Pre-compute prior day closes from RTH data
    spy_df_rth_copy = spy_df_rth.copy()
    spy_df_rth_copy["_date"] = spy_df_rth_copy["timestamp_et"].dt.date
    for day_str in ALL_J_DAYS:
        d = dt.date.fromisoformat(day_str)
        # Find prior trading day's last close
        prior_bars = spy_df_rth_copy[spy_df_rth_copy["_date"] < d]
        if not prior_bars.empty:
            prior_day_close[day_str] = float(prior_bars.iloc[-1]["close"])
        else:
            prior_day_close[day_str] = None

    level_states_shared: dict = {}

    for day_str in ALL_J_DAYS:
        d = dt.date.fromisoformat(day_str)
        pdc = prior_day_close.get(day_str)
        day_trades = _run_day_scenario(
            spy_df_full=spy_df_full,
            spy_df_rth=spy_df_rth,
            vix_aligned=vix_aligned,
            ribbon_df=ribbon_df,
            htf_stacks=htf_stacks,
            level_cache=level_cache,
            date=d,
            scenario=scenario,
            prior_day_close=pdc,
            level_states_in={},  # fresh per day
        )
        trades_by_day[day_str] = day_trades

    # Per-day P&L
    per_day_pnl = {d: round(sum(t.pnl for t in ts), 2) for d, ts in trades_by_day.items()}
    baseline_pnl = {d: round(sum(t.pnl for t in ts), 2) for d, ts in baseline_trades_by_day.items()}

    edge = _compute_edge(trades_by_day)
    baseline_edge = _compute_edge(baseline_trades_by_day)

    # Marginal trades = trades that fired in scenario but NOT in baseline (on J days)
    marginal_trades = []
    for day_str, s_trades in trades_by_day.items():
        b_trades = baseline_trades_by_day.get(day_str, [])
        b_times = {t.entry_time for t in b_trades}
        for t in s_trades:
            if t.entry_time not in b_times:
                marginal_trades.append({
                    "date": day_str,
                    "entry_time": t.entry_time,
                    "side": t.side,
                    "pnl": t.pnl,
                    "bear_score": t.bear_score,
                    "vol_ratio": t.vol_ratio,
                    "triggers": t.triggers,
                    "quality_tier": t.quality_tier,
                })

    marginal_pnl = sum(m["pnl"] for m in marginal_trades)
    marginal_n = len(marginal_trades)
    marginal_wr = (
        sum(1 for m in marginal_trades if m["pnl"] > 0) / marginal_n
        if marginal_n > 0 else 0.0
    )

    # Verdict
    if marginal_pnl < 0:
        verdict = "REJECT"
    elif marginal_wr >= 0.45 and marginal_pnl > 0:
        verdict = "PROMOTE"
    else:
        verdict = "VALIDATE"

    op16 = "PASS" if edge["edge_capture"] >= OP16_FLOOR else "fail"

    n_trades_total = sum(len(ts) for ts in trades_by_day.values())
    n_wins = sum(1 for ts in trades_by_day.values() for t in ts if t.pnl > 0)
    wr = n_wins / n_trades_total if n_trades_total > 0 else 0.0
    total_pnl = sum(t.pnl for ts in trades_by_day.values() for t in ts)

    return {
        "id": scenario.id,
        "name": scenario.name,
        "gate": f"{scenario.side}_score>={scenario.score_min} + {scenario.id.lower()}_conditions",
        "n_trades": n_trades_total,
        "wr": round(wr, 3),
        "total_pnl": round(total_pnl, 2),
        "edge_capture": edge["edge_capture"],
        "edge_pct_of_max": edge["edge_pct_of_max"],
        "op16": op16,
        "winner_pnl": edge["winner_pnl"],
        "loser_exposure": edge["loser_exposure"],
        "per_day_pnl": per_day_pnl,
        "marginal_trades": marginal_trades,
        "marginal_n": marginal_n,
        "marginal_pnl": round(marginal_pnl, 2),
        "marginal_wr": round(marginal_wr, 3),
        "verdict": verdict,
        "baseline_edge": baseline_edge["edge_capture"],
        "delta_vs_baseline": round(edge["edge_capture"] - baseline_edge["edge_capture"], 2),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    data_dir = REPO / "data"

    # Use the merged 16-month file (preferred)
    spy_path = data_dir / "spy_5m_2025-01-01_2026-06-16.csv"
    vix_path = data_dir / "vix_5m_2025-01-01_2026-06-16.csv"

    # Fallback chain
    if not spy_path.exists():
        spy_path = data_dir / "spy_5m_2025-01-01_2026-05-22.csv"
        vix_path = data_dir / "vix_5m_2025-01-01_2026-05-22.csv"
    if not spy_path.exists():
        for f in sorted(data_dir.glob("spy_5m_2025-01-01_*.csv"), reverse=True):
            spy_path = f
            break
        for f in sorted(data_dir.glob("vix_5m_2025-01-01_*.csv"), reverse=True):
            vix_path = f
            break

    print(f"Loading {spy_path.name} ...")
    spy_df_full = pd.read_csv(spy_path)
    vix_df = pd.read_csv(vix_path)
    spy_df_full["timestamp_et"] = pd.to_datetime(spy_df_full["timestamp_et"])
    spy_df_full["date"] = spy_df_full["timestamp_et"].dt.date
    print(f"  SPY rows: {len(spy_df_full):,}  VIX rows: {len(vix_df):,}")

    # RTH-only slice for ribbon + evaluation
    rth_mask = (
        (spy_df_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_df_full["timestamp_et"].dt.time < dt.time(16, 0))
    )
    spy_df_rth = spy_df_full.loc[rth_mask].reset_index(drop=True)
    print(f"  RTH rows: {len(spy_df_rth):,}")

    # Precompute ribbon + VIX + HTF stacks once
    print("Precomputing ribbon, VIX alignment, HTF stacks ...")
    ribbon_df = compute_ribbon(spy_df_rth["close"])
    vix_aligned = _align_vix_to_spy(spy_df_rth, vix_df)
    htf_stacks = _precompute_htf_15m_stacks(spy_df_rth)
    print("  Done.")

    level_cache: dict = {}  # shared across scenarios (same per-day result)
    scenarios = _make_scenarios()

    # ── Baseline run on J days ──
    print("\nRunning BASELINE (10/10 production) on J days ...")
    baseline_trades_by_day: dict[str, list[TradeRecord]] = {}
    for day_str in ALL_J_DAYS:
        d = dt.date.fromisoformat(day_str)
        baseline_trades_by_day[day_str] = _run_day_baseline(
            spy_df_full=spy_df_full,
            spy_df_rth=spy_df_rth,
            vix_aligned=vix_aligned,
            ribbon_df=ribbon_df,
            htf_stacks=htf_stacks,
            level_cache=level_cache,
            date=d,
            level_states_in={},
        )
        bt = baseline_trades_by_day[day_str]
        day_pnl = sum(t.pnl for t in bt)
        print(f"  {day_str}: {len(bt)} trades  P&L=${day_pnl:.0f}")

    baseline_edge_data = _compute_edge(baseline_trades_by_day)
    print(f"\n  Baseline edge_capture: ${baseline_edge_data['edge_capture']:.0f} "
          f"({baseline_edge_data['edge_pct_of_max']:.1f}% of max)")
    print(f"  OP-16: {'PASS' if baseline_edge_data['edge_capture'] >= OP16_FLOOR else 'fail'}\n")

    # Print header
    print(f"{'ID':>4}  {'name':<42}  {'N':>4}  {'WR':>5}  {'PnL':>8}  "
          f"{'EC':>8}  {'EC%':>5}  {'marg_n':>6}  {'marg_wr':>7}  {'marg_pnl':>9}  "
          f"{'OP16':>5}  verdict")
    print("-" * 130)

    # ── Scenario runs ──
    results = []
    for sc in scenarios:
        print(f"  Running {sc.id}: {sc.name} ...", end="", flush=True)
        res = _run_scenario_j_days(
            scenario=sc,
            spy_df_full=spy_df_full,
            spy_df_rth=spy_df_rth,
            vix_aligned=vix_aligned,
            ribbon_df=ribbon_df,
            htf_stacks=htf_stacks,
            level_cache=level_cache,
            baseline_trades_by_day=baseline_trades_by_day,
        )
        results.append(res)
        print(f"\r  {res['id']:>4}  {res['name']:<42}  {res['n_trades']:>4}  "
              f"{res['wr']:>5.3f}  {res['total_pnl']:>8.0f}  "
              f"{res['edge_capture']:>8.0f}  {res['edge_pct_of_max']:>5.1f}%  "
              f"{res['marginal_n']:>6}  {res['marginal_wr']:>7.3f}  "
              f"{res['marginal_pnl']:>9.0f}  "
              f"{res['op16']:>5}  {res['verdict']}")

    print("\n" + "=" * 130)
    print(f"J max possible: ${MAX_POSSIBLE}  |  OP-16 floor: ${OP16_FLOOR}")
    print(f"Baseline edge_capture: ${baseline_edge_data['edge_capture']:.0f} "
          f"({baseline_edge_data['edge_pct_of_max']:.1f}%)")

    # Per-day breakdown for J days
    print("\n--- Baseline per-day P&L on J days ---")
    for day_str in ALL_J_DAYS:
        label = "WINNER" if day_str in J_WINNERS else "LOSER"
        bt = baseline_trades_by_day.get(day_str, [])
        pnl = sum(t.pnl for t in bt)
        print(f"  {day_str} [{label}]: {len(bt)} trades, P&L=${pnl:.0f}")

    print("\n--- Top marginal trades across all scenarios ---")
    all_marginal = []
    for res in results:
        for m in res["marginal_trades"]:
            all_marginal.append({**m, "scenario_id": res["id"]})
    all_marginal.sort(key=lambda x: x["pnl"], reverse=True)
    for m in all_marginal[:20]:
        tag = "WINNER-DAY" if m["date"] in J_WINNERS else "LOSER-DAY"
        print(f"  [{m['scenario_id']}] {m['date']} {m['entry_time']} "
              f"({tag}) side={m['side']} score={m['bear_score']} "
              f"vol={m['vol_ratio']:.1f}x pnl=${m['pnl']:.0f} "
              f"triggers={m['triggers']} tier={m['quality_tier']}")

    # Build output
    baseline_section = {
        "id": "baseline_10_10",
        "name": "production 10/10 all-filters-must-pass",
        "edge_capture": baseline_edge_data["edge_capture"],
        "edge_pct_of_max": baseline_edge_data["edge_pct_of_max"],
        "winner_pnl": baseline_edge_data["winner_pnl"],
        "loser_exposure": baseline_edge_data["loser_exposure"],
        "per_day_pnl": {
            d: round(sum(t.pnl for t in ts), 2)
            for d, ts in baseline_trades_by_day.items()
        },
        "op16": "PASS" if baseline_edge_data["edge_capture"] >= OP16_FLOOR else "fail",
    }

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": (
            "Volume-compensated (B1-B6) and morning-window (F1-F5) gate relaxation sweep. "
            "Tests whether bear_score < 10 entries with extra vol/time confirmation "
            "improve edge_capture on J's winning days without hurt on losing days."
        ),
        "op16_floor": OP16_FLOOR,
        "max_possible": MAX_POSSIBLE,
        "base_params": BASE_PARAMS,
        "baseline_10_10": baseline_section,
        "scenarios": results,
        "verdict_summary": {
            "PROMOTE": [r["id"] for r in results if r["verdict"] == "PROMOTE"],
            "VALIDATE": [r["id"] for r in results if r["verdict"] == "VALIDATE"],
            "REJECT": [r["id"] for r in results if r["verdict"] == "REJECT"],
        },
    }

    out_dir = REPO.parent / "analysis" / "recommendations"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "gate_sweep_volume_morning.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote: {out_path}")

    # Summary verdict
    promotes = out["verdict_summary"]["PROMOTE"]
    print(f"\nPROMOTE candidates: {promotes if promotes else 'none'}")
    print(f"VALIDATE candidates: {out['verdict_summary']['VALIDATE']}")
    print(f"REJECT candidates:  {out['verdict_summary']['REJECT']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
