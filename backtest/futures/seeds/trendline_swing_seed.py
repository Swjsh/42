"""Trendline swing seed -- MES 4h-of-RTH bars, wick-anchored trendline geometry from
`backtest/futures/trendline_geometry.py`. The ONE untested cell in the futures-swing kill
pile (see `analysis/deep-research/TRENDLINE-SWING-MES-PREREG-2026-08-09.md` for the full
grammar, grid, gate, and every disclosed operationalization -- this module implements that
document verbatim; read it first).

`backtest/futures/battery.py` and `swing_sim.py` are NOT edited by this module -- both are
imported and reused exactly as the prior 3 seeds use them. The `atr` stop-shape combos call
`battery.run_cell` directly, unmodified. The `safety_line` stop-shape combos need a parallel
cell function (`run_cell_variable_stop`, below) because the stop distance is PER-SIGNAL (a
property of which specific trendline fired), not a single shared per-bar Series the way ATR
is -- `battery.run_cell`'s bar-indexed `atr.iloc[sidx]` lookup can't represent "two different
signals on the same bar with two different risk distances," so reusing it verbatim for this
half of the grid would risk silently wrong per-trade stops. `run_cell_variable_stop` mirrors
`run_cell`'s statistics EXACTLY (same IS/OOS split, same bootstrap-null shape, same
buy-and-hold benchmark, same BH-FDR-eligibility contract) and calls the same PUBLIC
`swing_sim`/`battery` primitives (`simulate_swing`, `simulate_buy_and_hold`,
`bootstrap_null_pvalue`, `bh_fdr`) -- only the null-pool construction differs, disclosed
below (`_build_null_pool_variable_stop`), because a fair null for a signal-dependent risk
size must also randomize the risk draw, not just the entry bar.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
for _p in (str(_REPO), str(_REPO / "backtest")):   # repo root (crypto.lib.*) + backtest/ (futures.*)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto.lib.indicators import ema  # noqa: E402
from crypto.lib.trendlines import find_swing_points  # noqa: E402
from futures import battery  # noqa: E402
from futures.swing_sim import wilder_atr, simulate_swing, simulate_buy_and_hold  # noqa: E402
from futures.trendline_geometry import (  # noqa: E402
    TrendLine, bars_df_to_bar_objects, find_trendlines, find_opposing_safety_line,
    TOUCH_TOLERANCE_PCT, MIN_STOP_DISTANCE_PTS, BREAK_RETEST_LOOKAHEAD_BARS,
)

WINDOWS = (2, 3)
ENTRY_TRIGGERS = ("bounce", "break", "break_retest")
STOP_SHAPES = ("atr", "safety_line")
ATR_STOP_MULT, ATR_TARGET_MULT = battery.DEFAULT_STOP_MULT, battery.DEFAULT_TARGET_MULT  # 1.5 / 3.0, unchanged
SAFETY_STOP_MULT, SAFETY_TARGET_MULT = 1.0, 2.0   # stop AT the line; target = her stated "2R or better" floor
DAILY_EMA_LEN = 20
DAILY_EMA_SLOPE_LOOKBACK = 5


def build_grid() -> list[dict]:
    grid = []
    for w in WINDOWS:
        for trig in ENTRY_TRIGGERS:
            for shape in STOP_SHAPES:
                grid.append({"window": w, "entry_trigger": trig, "stop_shape": shape})
    assert len(grid) == 12
    return grid


# ─── Daily bias filter (frozen ON for the official battery; prereg) ────────────

def _daily_bias_lookup(daily_bars: pd.DataFrame) -> dict:
    """date -> {"long_ok": bool, "short_ok": bool}, using ONLY that date's own bar and
    earlier (the EMA is causal at each row by construction). A 4h bar during session d
    reads the entry for the PRIOR traded session (see `_bias_ok_for_h4_row`) -- never its
    own still-forming daily bar, matching e2_context_seed's own bars[i-1] convention."""
    if len(daily_bars) == 0:
        return {}
    bar_objs = bars_df_to_bar_objects(daily_bars)
    ema_vals = ema(bar_objs, DAILY_EMA_LEN)
    closes = daily_bars["close"].tolist()
    dates = daily_bars["date"].tolist()
    out = {}
    for i, d in enumerate(dates):
        if i < DAILY_EMA_SLOPE_LOOKBACK or not np.isfinite(ema_vals[i]) or not np.isfinite(ema_vals[i - DAILY_EMA_SLOPE_LOOKBACK]):
            out[d] = {"long_ok": None, "short_ok": None}
            continue
        e_now, e_prev, c_now = ema_vals[i], ema_vals[i - DAILY_EMA_SLOPE_LOOKBACK], closes[i]
        out[d] = {"long_ok": bool(c_now > e_now and e_now > e_prev),
                   "short_ok": bool(c_now < e_now and e_now < e_prev)}
    return out


def _bias_ok_for_h4_row(direction: str, h4_date, date_to_daily_idx: dict, daily_dates: list,
                         bias_lookup: dict) -> Optional[bool]:
    idx = date_to_daily_idx.get(h4_date)
    if idx is None or idx == 0:
        return None  # no prior session known -- can't evaluate, conservative exclude
    prior_date = daily_dates[idx - 1]
    entry = bias_lookup.get(prior_date)
    if entry is None:
        return None
    key = "long_ok" if direction == "long" else "short_ok"
    return entry[key]


# ─── Trendline entry-trigger walk (one pass per confirmed line) ────────────────

def _walk_line_events(line: TrendLine, bars: pd.DataFrame, tolerance_pct: float) -> list[dict]:
    """Every bounce/break/break_retest event this ONE line produces, in chronological
    order. A line stops producing events after its first break (support/resistance that
    has been closed through is no longer support/resistance in any technical-analysis
    convention -- a geometric fact about the line, not the disputed "one trade attempt"
    re-entry rule, which this seed deliberately does NOT apply, see prereg)."""
    n = len(bars)
    opens = bars["open"].to_numpy(dtype=float)
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)
    events: list[dict] = []
    start = line.confirmed_idx + 1
    if start >= n:
        return events
    for i in range(start, n):
        lp = line.price_at(i)
        tol = tolerance_pct * abs(lp)
        if line.kind == "support":
            if lows[i] <= lp + tol and closes[i] > lp + tol:
                events.append({"bar_idx": i, "event_type": "bounce", "direction": "long", "line": line})
            if closes[i] < lp - tol:
                events.append({"bar_idx": i, "event_type": "break", "direction": "short", "line": line})
                for j in range(i + 1, min(i + 1 + BREAK_RETEST_LOOKAHEAD_BARS, n)):
                    lp_j = line.price_at(j)
                    tol_j = tolerance_pct * abs(lp_j)
                    if highs[j] >= lp_j - tol_j and closes[j] < lp_j - tol_j:
                        events.append({"bar_idx": j, "event_type": "break_retest", "direction": "short", "line": line})
                        break
                break  # line is broken -- no further events from it
        else:  # resistance
            if highs[i] >= lp - tol and closes[i] < lp - tol:
                events.append({"bar_idx": i, "event_type": "bounce", "direction": "short", "line": line})
            if closes[i] > lp + tol:
                events.append({"bar_idx": i, "event_type": "break", "direction": "long", "line": line})
                for j in range(i + 1, min(i + 1 + BREAK_RETEST_LOOKAHEAD_BARS, n)):
                    lp_j = line.price_at(j)
                    tol_j = tolerance_pct * abs(lp_j)
                    if lows[j] <= lp_j + tol_j and closes[j] > lp_j + tol_j:
                        events.append({"bar_idx": j, "event_type": "break_retest", "direction": "long", "line": line})
                        break
                break
    return events


def _stop_dist_for_event(ev: dict, bars: pd.DataFrame, entry_idx: int,
                          swings_by_window_kind: dict) -> Optional[float]:
    """Safety-Line-implied stop distance in points for ONE event (prereg: action line
    itself for bounce; parallel opposing-swing channel for break/break_retest). Returns
    None if unavailable (break/break_retest with no opposing swing point in span) -- the
    caller drops that row from `safety_line` combos only, per prereg."""
    line: TrendLine = ev["line"]
    entry_px = float(bars["open"].iloc[entry_idx])
    if ev["event_type"] == "bounce":
        dist = abs(entry_px - line.price_at(entry_idx))
        return max(dist, MIN_STOP_DISTANCE_PTS)
    opposing_kind = "swing_high" if line.kind == "support" else "swing_low"
    swings_opp_all = swings_by_window_kind.get((line.window, opposing_kind), [])
    confirmed = [s for s in swings_opp_all if s.bar_index + line.window <= ev["bar_idx"]]
    safety = find_opposing_safety_line(line, confirmed, ev["bar_idx"])
    if safety is None:
        return None
    dist = abs(entry_px - safety.price_at(entry_idx))
    return max(dist, MIN_STOP_DISTANCE_PTS)


def generate_signals(h4_bars: pd.DataFrame, daily_bars: pd.DataFrame,
                      grid: list[dict] | None = None,
                      apply_bias_filter: bool = True,
                      tolerance_pct: float = TOUCH_TOLERANCE_PCT) -> pd.DataFrame:
    """h4_bars: `data.resample_4h_rth` schema. daily_bars: `data.resample_daily` schema
    (bias-filter context only). One row per (combo, direction, fired bar); `stop_dist_pts`
    is populated for `safety_line` rows (NaN for `atr` rows, which use the real Wilder ATR
    Series in the battery step instead -- see `score_trendline_seed`)."""
    if grid is None:
        grid = build_grid()
    cols = ["combo_id", "window", "entry_trigger", "stop_shape", "signal_bar_idx",
            "direction", "action_line_kind", "stop_dist_pts"]
    if len(h4_bars) == 0:
        return pd.DataFrame(columns=cols)

    bias_lookup = _daily_bias_lookup(daily_bars) if apply_bias_filter else {}
    date_to_daily_idx = {d: i for i, d in enumerate(daily_bars["date"])} if apply_bias_filter else {}
    daily_dates = daily_bars["date"].tolist() if apply_bias_filter else []
    h4_dates = h4_bars["date"].tolist()

    rows = []
    for window in WINDOWS:
        atr = wilder_atr(h4_bars, period=14)
        lines = find_trendlines(h4_bars, window, atr, tolerance_pct=tolerance_pct)
        bar_objs = bars_df_to_bar_objects(h4_bars)
        swings_all = find_swing_points(bar_objs, window=window, inclusive_right=True)
        swings_by_window_kind = {
            (window, "swing_high"): [s for s in swings_all if s.kind == "swing_high"],
            (window, "swing_low"): [s for s in swings_all if s.kind == "swing_low"],
        }

        events: list[dict] = []
        for line in lines:
            events.extend(_walk_line_events(line, h4_bars, tolerance_pct))

        for ev in events:
            i = ev["bar_idx"]
            entry_idx = i + 1
            if entry_idx >= len(h4_bars):
                continue
            if apply_bias_filter:
                ok = _bias_ok_for_h4_row(ev["direction"], h4_dates[i], date_to_daily_idx, daily_dates, bias_lookup)
                if not ok:
                    continue
            safety_dist = _stop_dist_for_event(ev, h4_bars, entry_idx, swings_by_window_kind)
            for shape in STOP_SHAPES:
                if shape == "safety_line" and safety_dist is None:
                    continue  # excluded -- disclosed, not silently substituted (prereg)
                combo_id = f"tl_w{window}_{ev['event_type']}_{shape}"
                rows.append({
                    "combo_id": combo_id, "window": window, "entry_trigger": ev["event_type"],
                    "stop_shape": shape, "signal_bar_idx": i, "direction": ev["direction"],
                    "action_line_kind": ev["line"].kind,
                    "stop_dist_pts": (safety_dist if shape == "safety_line" else float("nan")),
                })
    df = pd.DataFrame(rows, columns=cols)
    if len(df) == 0:
        return df
    # PSEUDO-REPLICATION GUARD: within one (window, entry_trigger, stop_shape) combo, MANY
    # geometrically-valid-but-overlapping trendlines routinely fire the identical
    # (direction, signal_bar_idx) event -- discovered 2026-08-09 when a first real-data run
    # showed one bar counted 9x within a single combo (820 raw rows -> 458 distinct events).
    # Counting each as a separate "trade" is pseudo-replication: it inflates n past
    # MIN_OOS_N, and both the bootstrap-null p-value and BH-FDR assume independent draws,
    # which duplicate-of-the-same-bar rows are NOT -- a real trader/engine places ONE order
    # on a bar regardless of how many redundant lines agree. Collapsed to one row per
    # (combo_id, direction, signal_bar_idx), keeping the highest-touch-count line's version
    # (rows are appended in `lines`' own touch-count-descending order from
    # `find_trendlines`/`_dedupe_lines`, so `keep="first"` is a principled tie-break, not
    # an arbitrary one). See `TestNoDoubleCounting` in test_trendline_swing_seed.py.
    df = df.drop_duplicates(subset=["combo_id", "direction", "signal_bar_idx"], keep="first")
    return df.reset_index(drop=True)


# ─── Variable-stop (safety_line) cell scoring -- mirrors battery.run_cell exactly ──

def _stats(pnls: list[float]) -> dict:
    """Verbatim copy of battery._stats (private helper; duplicated rather than reaching
    into another module's underscore-prefixed namespace -- see module docstring)."""
    n = len(pnls)
    if n == 0:
        return {"n": 0, "sum": 0.0, "mean": None, "wr": None}
    arr = np.asarray(pnls, dtype=float)
    return {"n": n, "sum": round(float(arr.sum()), 2), "mean": round(float(arr.mean()), 2),
            "wr": round(float((arr > 0).mean()), 4)}


def _run_signal_trades_variable_stop(dir_signals: pd.DataFrame, bars: pd.DataFrame, instrument, *,
                                      stop_mult: float, target_mult: Optional[float],
                                      max_hold_bars: int, cost_per_side_usd: float) -> list[dict]:
    trades = []
    for row in dir_signals.itertuples(index=False):
        sidx = int(row.signal_bar_idx)
        entry_idx = sidx + 1
        if entry_idx >= len(bars) or sidx < 0:
            continue
        dist = float(row.stop_dist_pts)
        if not np.isfinite(dist) or dist <= 0:
            continue
        r = simulate_swing(row.direction, entry_idx, bars, dist, instrument,
                            stop_mult=stop_mult, target_mult=target_mult,
                            max_hold_bars=max_hold_bars, cost_per_side_usd=cost_per_side_usd)
        entry_date = bars["date"].iloc[entry_idx] if "date" in bars.columns else None
        trades.append({"signal_bar_idx": sidx, "entry_idx": entry_idx, "entry_date": entry_date,
                        "direction": row.direction, "pnl_usd": r.pnl_usd, "pnl_pts": r.pnl_pts,
                        "reason": r.reason, "gapped": r.gapped, "hold_bars": r.hold_bars,
                        "stop_dist_pts": dist})
    return trades


def _build_null_pool_variable_stop(bars: pd.DataFrame, eligible_idx: list[int], dist_pool: list[float],
                                    direction: str, instrument, *, stop_mult: float,
                                    target_mult: Optional[float], max_hold_bars: int,
                                    cost_per_side_usd: float, n_pool: int = battery.N_NULL_POOL,
                                    rng: Optional[np.random.Generator] = None) -> list[float]:
    """Random-entry null for a SIGNAL-DEPENDENT risk size: randomizes both the entry bar
    (from `eligible_idx`, same causal-window contract as battery.build_null_pool) AND,
    independently, the risk distance (drawn WITH replacement from this cell's own OOS
    `stop_dist_pts` population) -- a fair null must not assume a fixed ATR-scale risk when
    the real strategy's risk is itself signal-dependent. Same exit SHAPE (stop_mult/
    target_mult) as the real cell, matching battery.build_null_pool's "same shape, only
    entry randomized" discipline, extended to also randomize the shape's SIZE input."""
    if rng is None:
        rng = np.random.default_rng(7)
    if not eligible_idx or not dist_pool:
        return []
    entry_picks = rng.choice(eligible_idx, size=n_pool, replace=True)
    dist_picks = rng.choice(np.asarray(dist_pool, dtype=float), size=n_pool, replace=True)
    out = []
    for i, d in zip(entry_picks, dist_picks):
        entry_idx = int(i) + 1
        if entry_idx >= len(bars) or not np.isfinite(d) or d <= 0:
            continue
        r = simulate_swing(direction, entry_idx, bars, float(d), instrument,
                            stop_mult=stop_mult, target_mult=target_mult,
                            max_hold_bars=max_hold_bars, cost_per_side_usd=cost_per_side_usd)
        out.append(r.pnl_usd)
    return out


def run_cell_variable_stop(seed_name: str, combo: dict, direction: str, horizon_label: str,
                            horizon_bars: int, signals: pd.DataFrame, bars: pd.DataFrame,
                            instrument, oos_cut: dt.date, vix_by_date: dict, *,
                            stop_mult: float = SAFETY_STOP_MULT, target_mult: Optional[float] = SAFETY_TARGET_MULT,
                            cost_per_side_usd: float = battery.DEFAULT_COST_PER_SIDE_USD,
                            rng_seed: int = 42) -> dict:
    """Mirrors `battery.run_cell` field-for-field (same IS/OOS split, same bootstrap-null
    p-value shape, same buy-and-hold benchmark, same BH-FDR-eligibility contract via
    `oos_n_sufficient`) so cells from this function and cells from `battery.run_cell` can
    be combined into ONE BH-FDR family with no difference in what "clears" means."""
    dir_signals = signals[signals["direction"] == direction]
    trades = _run_signal_trades_variable_stop(dir_signals, bars, instrument, stop_mult=stop_mult,
                                               target_mult=target_mult, max_hold_bars=horizon_bars,
                                               cost_per_side_usd=cost_per_side_usd)
    is_trades = [t for t in trades if t["entry_date"] is not None and t["entry_date"] < oos_cut]
    oos_trades = [t for t in trades if t["entry_date"] is not None and t["entry_date"] >= oos_cut]
    is_pnls = [t["pnl_usd"] for t in is_trades]
    oos_pnls = [t["pnl_usd"] for t in oos_trades]
    is_stats, oos_stats = _stats(is_pnls), _stats(oos_pnls)

    oos_start_idx = None
    for idx in range(len(bars)):
        d = bars["date"].iloc[idx] if "date" in bars.columns else None
        if d is not None and d >= oos_cut:
            oos_start_idx = idx
            break
    eligible_idx = list(range(oos_start_idx, len(bars) - 1)) if oos_start_idx is not None else []
    dist_pool = [t["stop_dist_pts"] for t in oos_trades]

    rng = np.random.default_rng(rng_seed)
    null_pool = _build_null_pool_variable_stop(bars, eligible_idx, dist_pool, direction, instrument,
                                                stop_mult=stop_mult, target_mult=target_mult,
                                                max_hold_bars=horizon_bars, cost_per_side_usd=cost_per_side_usd,
                                                rng=rng)
    obs_mean = oos_stats["mean"] if oos_stats["mean"] is not None else float("nan")
    p_null, null_mean = battery.bootstrap_null_pvalue(obs_mean, null_pool, len(oos_pnls),
                                                        B=battery.BOOTSTRAP_B, rng=np.random.default_rng(rng_seed + 1))
    percentile_vs_null = round(100.0 * (1.0 - p_null), 2) if np.isfinite(p_null) else None

    bnh_pnls = []
    for t in oos_trades:
        r = simulate_buy_and_hold(direction, t["entry_idx"], bars, instrument,
                                   hold_bars=horizon_bars, cost_per_side_usd=cost_per_side_usd)
        bnh_pnls.append(r.pnl_usd)
    bnh_stats = _stats(bnh_pnls)
    beats_buy_and_hold = (oos_stats["mean"] is not None and bnh_stats["mean"] is not None
                          and oos_stats["mean"] > bnh_stats["mean"])

    lo, hi = [], []
    for t in oos_trades:
        v = vix_by_date.get(t["entry_date"])
        if v is None:
            continue
        (lo if v < battery.VIX_REGIME_THRESHOLD else hi).append(t["pnl_usd"])
    regime = {"vix_lt_17.5": _stats(lo), "vix_gte_17.5": _stats(hi)}

    return {
        "seed": seed_name, "combo_id": combo.get("combo_id"), "combo": combo,
        "direction": direction, "horizon_label": horizon_label, "horizon_bars": horizon_bars,
        "stop_mult": stop_mult, "target_mult": target_mult, "stop_basis": "safety_line",
        "is": is_stats, "oos": oos_stats,
        "null": {"n_pool": len(null_pool), "null_mean": (round(null_mean, 2) if np.isfinite(null_mean) else None),
                 "p_value": (round(p_null, 4) if np.isfinite(p_null) else None),
                 "percentile_vs_null": percentile_vs_null},
        "buy_and_hold": bnh_stats, "beats_buy_and_hold": bool(beats_buy_and_hold),
        "regime_split": regime,
        "oos_n_sufficient": len(oos_trades) >= battery.MIN_OOS_N,
        "exit_reasons_oos": pd.Series([t["reason"] for t in oos_trades]).value_counts().to_dict() if oos_trades else {},
        "gap_fills_oos": sum(1 for t in oos_trades if t["gapped"]),
        "mean_stop_dist_pts_oos": (round(float(np.mean(dist_pool)), 3) if dist_pool else None),
    }


# ─── Top-level seed scoring (combines both stop-shape paths into ONE BH-FDR family) ──

def score_trendline_seed(h4_bars: pd.DataFrame, daily_bars: pd.DataFrame, instrument,
                          horizons: list[tuple[int, str]], oos_cut: dt.date, vix_by_date: dict,
                          *, apply_bias_filter: bool = True, alpha: float = 0.05,
                          informational_only: bool = False) -> dict:
    """Runs all 12 official combos x 2 directions x len(horizons) through the appropriate
    cell function (battery.run_cell for `atr`, run_cell_variable_stop for `safety_line`),
    then applies BH-FDR across ALL resulting cells TOGETHER (verbatim reproduction of
    `battery.score_seed`'s aggregation tail -- same `bh_fdr` call, same `clears` predicate:
    oos_mean>0 AND bh_fdr_survivor AND beats_buy_and_hold), so this seed's PASS/KILL bar is
    IDENTICAL to the prior three seeds'. `informational_only=True` (used for the disclosed
    bias-filter-OFF robustness re-run) still computes every field but is excluded from the
    seed's headline verdict by the caller -- kept in the same shape for easy comparison."""
    grid = build_grid()
    signals = generate_signals(h4_bars, daily_bars, grid, apply_bias_filter=apply_bias_filter)
    atr_series = wilder_atr(h4_bars, period=14)

    cells = []
    for combo in grid:
        combo_id = f"tl_w{combo['window']}_{combo['entry_trigger']}_{combo['stop_shape']}"
        combo_signals = signals[signals["combo_id"] == combo_id]
        for direction in ("long", "short"):
            for horizon_bars, horizon_label in horizons:
                if combo["stop_shape"] == "atr":
                    cell = battery.run_cell(
                        "trendline_swing", {"combo_id": combo_id, **combo}, direction, horizon_label,
                        horizon_bars, combo_signals, h4_bars, atr_series, instrument, oos_cut, vix_by_date,
                        stop_mult=ATR_STOP_MULT, target_mult=ATR_TARGET_MULT,
                        cost_per_side_usd=battery.DEFAULT_COST_PER_SIDE_USD,
                    )
                    cell["stop_basis"] = "atr"
                else:
                    cell = run_cell_variable_stop(
                        "trendline_swing", {"combo_id": combo_id, **combo}, direction, horizon_label,
                        horizon_bars, combo_signals, h4_bars, instrument, oos_cut, vix_by_date,
                        stop_mult=SAFETY_STOP_MULT, target_mult=SAFETY_TARGET_MULT,
                        cost_per_side_usd=battery.DEFAULT_COST_PER_SIDE_USD,
                    )
                cell["bias_filter_applied"] = apply_bias_filter
                cell["informational_only"] = informational_only
                cells.append(cell)

    eligible = [c for c in cells if c["oos_n_sufficient"] and c["null"]["p_value"] is not None]
    pvals = [c["null"]["p_value"] for c in eligible]
    survivors = battery.bh_fdr(pvals, alpha=alpha)
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
    verdict = "PASS" if (n_clear > 0 and not informational_only) else "KILL"
    return {
        "seed": "trendline_swing", "n_cells_tested": len(cells), "n_bh_fdr_eligible": len(eligible),
        "alpha": alpha, "min_oos_n": battery.MIN_OOS_N,
        "n_clearing_cells": n_clear, "verdict": verdict,
        "n_signals_total": int(len(signals)), "bias_filter_applied": apply_bias_filter,
        "informational_only": informational_only,
        "cells": cells,
    }


__all__ = ["build_grid", "generate_signals", "score_trendline_seed", "run_cell_variable_stop",
           "WINDOWS", "ENTRY_TRIGGERS", "STOP_SHAPES", "ATR_STOP_MULT", "ATR_TARGET_MULT",
           "SAFETY_STOP_MULT", "SAFETY_TARGET_MULT"]
