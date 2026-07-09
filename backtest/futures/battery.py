"""battery.py -- canonical battery statistics for the Phase-1 swing seeds.

Implements FUTURES-REVIVAL-PLAN section 2f Phase 1's battery discipline:
  - IS/OOS split at a fixed cutoff date.
  - Random-entry null, SAME hold horizon + stop shape, SAME bars (>=100
    resamples), bootstrap p-value + the seed's percentile vs the null.
  - Both directions reported separately (never pooled).
  - BH-FDR across every (combo x direction x horizon) cell tested, per seed.
  - Expectancy in $ per contract AFTER commission+slippage (swing_sim.py's
    cost_per_side_usd, charged on nulls and buy-and-hold too -- apples to apples).
  - Per-regime split (VIX >=/< 17.5).
  - Buy-and-hold-same-horizon comparison (rules out "just rode the uptrend").

PASS gate (pre-registered, matches the work order verbatim): a CELL clears iff
  oos_mean > 0  AND  bh_fdr_survivor (alpha=0.05)  AND  oos_mean > buy_and_hold_mean.
A SEED's verdict is PASS iff >=1 cell clears; otherwise KILL. Cells with
OOS n < MIN_OOS_N are excluded from the BH-FDR family (reported, never a PASS)
-- pre-committed threshold, not a post-hoc filter chosen after seeing results.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd

try:                              # package import (backtest/ on sys.path)
    from futures.swing_sim import wilder_atr, simulate_swing, simulate_buy_and_hold, SwingResult
except ImportError:               # script import (backtest/futures/ itself on sys.path)
    from swing_sim import wilder_atr, simulate_swing, simulate_buy_and_hold, SwingResult

MIN_OOS_N = 5
VIX_REGIME_THRESHOLD = 17.5
DEFAULT_STOP_MULT = 1.5
DEFAULT_TARGET_MULT = 3.0
DEFAULT_COST_PER_SIDE_USD = 2.50
N_NULL_POOL = 300
BOOTSTRAP_B = 2000


def bh_fdr(pvalues: list[float], alpha: float = 0.05) -> list[bool]:
    """Benjamini-Hochberg step-up FDR. Returns a same-length list of booleans
    (True = survives at this alpha). NaN p-values never survive."""
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: (np.inf if pd.isna(pvalues[i]) else pvalues[i]))
    survive = [False] * m
    threshold_rank = 0
    for rank, idx in enumerate(order, start=1):
        p = pvalues[idx]
        if pd.isna(p):
            continue
        if p <= (rank / m) * alpha:
            threshold_rank = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= threshold_rank:
            survive[idx] = True
    return survive


def bootstrap_null_pvalue(observed_mean: float, null_pool: list[float], n_obs: int,
                           B: int = BOOTSTRAP_B, rng: Optional[np.random.Generator] = None) -> tuple[float, float]:
    """One-sided bootstrap p-value: P(null bootstrap mean >= observed mean).
    Returns (p_value, null_mean_of_pool). +1/(B+1) smoothing (never exactly 0)."""
    if rng is None:
        rng = np.random.default_rng(42)
    pool = np.asarray(null_pool, dtype=float)
    if len(pool) == 0 or n_obs <= 0:
        return float("nan"), float("nan")
    draws = rng.choice(pool, size=(B, n_obs), replace=True)
    boot_means = draws.mean(axis=1)
    ge = int(np.sum(boot_means >= observed_mean))
    p = (ge + 1) / (B + 1)
    return float(p), float(pool.mean())


def build_null_pool(
    bars: pd.DataFrame, atr: pd.Series, eligible_idx: list[int], direction: str,
    instrument, *, stop_mult: float, target_mult: Optional[float], max_hold_bars: int,
    cost_per_side_usd: float, n_pool: int = N_NULL_POOL,
    rng: Optional[np.random.Generator] = None,
) -> list[float]:
    """Random-entry null: same direction, SAME exit shape (stop/target/hold),
    SAME bars -- only the entry bar is randomized. Sampled WITH replacement
    from `eligible_idx` (indices with a known causal ATR and >=1 future bar)."""
    if rng is None:
        rng = np.random.default_rng(7)
    if not eligible_idx:
        return []
    picks = rng.choice(eligible_idx, size=n_pool, replace=True)
    out = []
    for i in picks:
        a = float(atr.iloc[i])
        if not np.isfinite(a) or a <= 0:
            continue
        entry_idx = i + 1
        if entry_idx >= len(bars):
            continue
        r = simulate_swing(direction, entry_idx, bars, a, instrument,
                            stop_mult=stop_mult, target_mult=target_mult,
                            max_hold_bars=max_hold_bars, cost_per_side_usd=cost_per_side_usd)
        out.append(r.pnl_usd)
    return out


def _run_signal_trades(
    signals: pd.DataFrame, bars: pd.DataFrame, atr: pd.Series, instrument, *,
    stop_mult: float, target_mult: Optional[float], max_hold_bars: int,
    cost_per_side_usd: float,
) -> list[dict]:
    """Walk every signal row through simulate_swing. entry_idx = signal_bar_idx+1
    (next-bar-open, no look-ahead); ATR is read at the signal bar (causal --
    known at the signal bar's own close, before the entry bar opens)."""
    trades = []
    for row in signals.itertuples(index=False):
        sidx = int(row.signal_bar_idx)
        entry_idx = sidx + 1
        if entry_idx >= len(bars) or sidx < 0 or sidx >= len(atr):
            continue
        a = float(atr.iloc[sidx])
        if not np.isfinite(a) or a <= 0:
            continue
        r = simulate_swing(row.direction, entry_idx, bars, a, instrument,
                            stop_mult=stop_mult, target_mult=target_mult,
                            max_hold_bars=max_hold_bars, cost_per_side_usd=cost_per_side_usd)
        entry_date = bars["date"].iloc[entry_idx] if "date" in bars.columns else None
        trades.append({"signal_bar_idx": sidx, "entry_idx": entry_idx,
                        "entry_date": entry_date, "direction": row.direction,
                        "pnl_usd": r.pnl_usd, "pnl_pts": r.pnl_pts, "reason": r.reason,
                        "gapped": r.gapped, "hold_bars": r.hold_bars})
    return trades


def _stats(pnls: list[float]) -> dict:
    n = len(pnls)
    if n == 0:
        return {"n": 0, "sum": 0.0, "mean": None, "wr": None}
    arr = np.asarray(pnls, dtype=float)
    return {"n": n, "sum": round(float(arr.sum()), 2), "mean": round(float(arr.mean()), 2),
            "wr": round(float((arr > 0).mean()), 4)}


def _regime_split(trades: list[dict], vix_by_date: dict) -> dict:
    lo, hi = [], []
    for t in trades:
        v = vix_by_date.get(t["entry_date"])
        if v is None:
            continue
        (lo if v < VIX_REGIME_THRESHOLD else hi).append(t["pnl_usd"])
    return {"vix_lt_17.5": _stats(lo), "vix_gte_17.5": _stats(hi)}


def _drop_top_n(pnls: list[float], n: int = 3) -> float:
    if len(pnls) <= n:
        return 0.0
    sorted_desc = sorted(pnls, reverse=True)
    return round(float(sum(sorted_desc[n:])), 2)


def run_cell(
    seed_name: str, combo: dict, direction: str, horizon_label: str, horizon_bars: int,
    signals: pd.DataFrame, bars: pd.DataFrame, atr: pd.Series, instrument,
    oos_cut: dt.date, vix_by_date: dict, *,
    stop_mult: float = DEFAULT_STOP_MULT, target_mult: Optional[float] = DEFAULT_TARGET_MULT,
    cost_per_side_usd: float = DEFAULT_COST_PER_SIDE_USD, rng_seed: int = 42,
) -> dict:
    """Compute the full metrics for ONE (combo, direction, horizon) cell."""
    dir_signals = signals[signals["direction"] == direction]
    trades = _run_signal_trades(dir_signals, bars, atr, instrument, stop_mult=stop_mult,
                                 target_mult=target_mult, max_hold_bars=horizon_bars,
                                 cost_per_side_usd=cost_per_side_usd)
    is_trades = [t for t in trades if t["entry_date"] is not None and t["entry_date"] < oos_cut]
    oos_trades = [t for t in trades if t["entry_date"] is not None and t["entry_date"] >= oos_cut]

    is_pnls = [t["pnl_usd"] for t in is_trades]
    oos_pnls = [t["pnl_usd"] for t in oos_trades]
    is_stats, oos_stats = _stats(is_pnls), _stats(oos_pnls)

    # Random-entry null (scoped to the OOS window -- apples to apples with oos_stats).
    warmup = int(atr.first_valid_index() or 0) if hasattr(atr, "first_valid_index") else 0
    oos_start_idx = None
    for idx in range(len(bars)):
        d = bars["date"].iloc[idx] if "date" in bars.columns else None
        if d is not None and d >= oos_cut:
            oos_start_idx = idx
            break
    eligible_idx = []
    if oos_start_idx is not None:
        eligible_idx = [i for i in range(max(warmup, oos_start_idx), len(bars) - 1)
                        if np.isfinite(atr.iloc[i]) and atr.iloc[i] > 0]
    rng = np.random.default_rng(rng_seed)
    null_pool = build_null_pool(bars, atr, eligible_idx, direction, instrument,
                                 stop_mult=stop_mult, target_mult=target_mult,
                                 max_hold_bars=horizon_bars, cost_per_side_usd=cost_per_side_usd,
                                 n_pool=N_NULL_POOL, rng=rng)
    obs_mean = oos_stats["mean"] if oos_stats["mean"] is not None else float("nan")
    p_null, null_mean = bootstrap_null_pvalue(obs_mean, null_pool, len(oos_pnls),
                                               B=BOOTSTRAP_B, rng=np.random.default_rng(rng_seed + 1))
    percentile_vs_null = round(100.0 * (1.0 - p_null), 2) if np.isfinite(p_null) else None

    # Buy-and-hold-same-horizon benchmark on the SAME OOS entry bars/direction.
    bnh_pnls = []
    for t in oos_trades:
        r = simulate_buy_and_hold(direction, t["entry_idx"], bars, instrument,
                                   hold_bars=horizon_bars, cost_per_side_usd=cost_per_side_usd)
        bnh_pnls.append(r.pnl_usd)
    bnh_stats = _stats(bnh_pnls)
    beats_buy_and_hold = (oos_stats["mean"] is not None and bnh_stats["mean"] is not None
                          and oos_stats["mean"] > bnh_stats["mean"])

    regime = _regime_split(oos_trades, vix_by_date)
    drop_top3 = _drop_top_n(oos_pnls, 3)

    return {
        "seed": seed_name, "combo_id": combo.get("combo_id"), "combo": combo,
        "direction": direction, "horizon_label": horizon_label, "horizon_bars": horizon_bars,
        "stop_mult": stop_mult, "target_mult": target_mult,
        "is": is_stats, "oos": oos_stats,
        "null": {"n_pool": len(null_pool), "null_mean": (round(null_mean, 2) if np.isfinite(null_mean) else None),
                 "p_value": (round(p_null, 4) if np.isfinite(p_null) else None),
                 "percentile_vs_null": percentile_vs_null},
        "buy_and_hold": bnh_stats, "beats_buy_and_hold": bool(beats_buy_and_hold),
        "regime_split": regime, "drop_top3_oos_pnl": drop_top3,
        "oos_n_sufficient": len(oos_trades) >= MIN_OOS_N,
        "exit_reasons_oos": pd.Series([t["reason"] for t in oos_trades]).value_counts().to_dict() if oos_trades else {},
        "gap_fills_oos": sum(1 for t in oos_trades if t["gapped"]),
    }


def score_seed(
    seed_name: str, grid: list[dict], signals: pd.DataFrame, bars: pd.DataFrame,
    instrument, horizons: list[tuple[int, str]], oos_cut: dt.date, vix_by_date: dict,
    *, atr_period: int = 14, alpha: float = 0.05,
) -> dict:
    """Run every (combo x direction x horizon) cell for one seed, BH-FDR the
    OOS-eligible p-values, and return the full scorecard dict (pre-JSON)."""
    atr = wilder_atr(bars, period=atr_period)
    cells = []
    for combo in grid:
        combo_id = combo["combo_id"] if "combo_id" in combo else str(combo)
        combo_signals = signals[signals["combo_id"] == combo_id] if "combo_id" in signals.columns else signals
        for direction in ("long", "short"):
            for horizon_bars, horizon_label in horizons:
                cell = run_cell(seed_name, {"combo_id": combo_id, **{k: v for k, v in combo.items() if k != "combo_id"}},
                                 direction, horizon_label, horizon_bars, combo_signals, bars, atr,
                                 instrument, oos_cut, vix_by_date)
                cells.append(cell)

    eligible = [c for c in cells if c["oos_n_sufficient"] and c["null"]["p_value"] is not None]
    pvals = [c["null"]["p_value"] for c in eligible]
    survivors = bh_fdr(pvals, alpha=alpha)
    for c, surv in zip(eligible, survivors):
        c["bh_fdr_survivor"] = bool(surv)
    for c in cells:
        c.setdefault("bh_fdr_survivor", False)

    for c in cells:
        c["clears"] = bool(
            c["oos_n_sufficient"] and c["oos"]["mean"] is not None and c["oos"]["mean"] > 0
            and c["bh_fdr_survivor"] and c["beats_buy_and_hold"]
        )

    n_clear = sum(1 for c in cells if c["clears"])
    verdict = "PASS" if n_clear > 0 else "KILL"
    return {
        "seed": seed_name, "n_cells_tested": len(cells), "n_bh_fdr_eligible": len(eligible),
        "alpha": alpha, "min_oos_n": MIN_OOS_N,
        "n_clearing_cells": n_clear, "verdict": verdict,
        "cells": cells,
    }
