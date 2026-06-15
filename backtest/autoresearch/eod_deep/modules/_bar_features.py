"""Bar-feature extraction — single source of truth for "what was the state at bar N?"

Used by forensics + detection + technical so they all use the same numbers.
Vectorized where possible — designed to run over 16mo (78K bars) in <30s after the
ribbon_df cache is built (which itself is ~1s for 78K rows via pandas ewm).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Any

import numpy as np
import pandas as pd


@dataclass
class BarFeatures:
    """Snapshot of market state at a specific 5m bar."""
    bar_idx: int = -1
    timestamp_et: str = ""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    body_pct_of_range: float = -1.0  # |close-open|/(high-low)
    vol_mult_20bar: float = -1.0     # bar_vol / prior_20_bar_avg
    ribbon_stack: str = ""           # BULL | BEAR | MIXED
    ribbon_spread_cents: float = -1.0
    ribbon_fast: float = -1.0
    ribbon_pivot: float = -1.0
    ribbon_slow: float = -1.0
    nearest_level_price: float = -1.0
    nearest_level_distance: float = -1.0   # signed: positive = price above level
    nearest_level_role: str = ""           # active | carry | none
    time_of_day_min_from_open: int = -1    # minutes from 09:30 ET
    is_rth: bool = False


def _ema_series(closes: pd.Series, period: int) -> pd.Series:
    """Standard EMA (Saty Pivot Ribbon uses Wilder EMA variant; this is plain EMA)."""
    return closes.ewm(span=period, adjust=False).mean()


def compute_ribbon_cached(spy_df: pd.DataFrame) -> pd.DataFrame:
    """Compute Saty Pivot Ribbon EMAs over the full df once. Returns df with
    columns: fast / pivot / slow + ribbon_spread + ribbon_stack."""
    if "close" not in spy_df.columns:
        return pd.DataFrame()

    # Standard Saty periods (matches lib/ribbon.load_periods defaults)
    fast_p = 13
    pivot_p = 28
    slow_p = 36

    df = pd.DataFrame(index=spy_df.index)
    df["fast"] = _ema_series(spy_df["close"], fast_p)
    df["pivot"] = _ema_series(spy_df["close"], pivot_p)
    df["slow"] = _ema_series(spy_df["close"], slow_p)
    df["ribbon_spread_cents"] = ((df["fast"] - df["slow"]).abs() * 100).round(1)

    # Stack: BULL if fast>pivot>slow; BEAR if fast<pivot<slow; else MIXED
    bull_stack = (df["fast"] > df["pivot"]) & (df["pivot"] > df["slow"])
    bear_stack = (df["fast"] < df["pivot"]) & (df["pivot"] < df["slow"])
    df["ribbon_stack"] = np.where(bull_stack, "BULL",
                                  np.where(bear_stack, "BEAR", "MIXED"))
    # Alias `stack` for compatibility with lib/simulator_real.py and lib/ribbon.py
    df["stack"] = df["ribbon_stack"]
    return df


def compute_vol_baseline(volumes: pd.Series, window: int = 20) -> pd.Series:
    """20-bar rolling volume baseline. Returns series aligned to input index."""
    return volumes.rolling(window=window, min_periods=1).mean().shift(1)


def _time_min_from_open(ts: Any) -> int:
    """Minutes between 09:30 ET and the bar's time (negative if before open)."""
    try:
        hh = int(ts.hour) if hasattr(ts, "hour") else int(str(ts)[11:13])
        mm = int(ts.minute) if hasattr(ts, "minute") else int(str(ts)[14:16])
        return (hh - 9) * 60 + mm - 30
    except Exception:
        return -1


def compute_bar_features(
    spy_df: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    vol_baseline: pd.Series,
    bar_idx: int,
    levels: Optional[list[dict]] = None,
) -> BarFeatures:
    """Extract full feature snapshot for a single bar.

    Args:
        spy_df: master CSV with timestamp_et, open, high, low, close, volume
        ribbon_df: output of compute_ribbon_cached (same length as spy_df)
        vol_baseline: output of compute_vol_baseline (same length)
        bar_idx: integer position in spy_df
        levels: list of dicts like [{"price": 740.73, "role": "carry"}, ...]
                If None, level fields stay -1/empty.

    Returns:
        BarFeatures dataclass with all populated fields.
    """
    if bar_idx < 0 or bar_idx >= len(spy_df):
        return BarFeatures()

    bar = spy_df.iloc[bar_idx]
    rib = ribbon_df.iloc[bar_idx] if (ribbon_df is not None and not ribbon_df.empty
                                     and bar_idx < len(ribbon_df)) else None

    fb = BarFeatures()
    fb.bar_idx = bar_idx
    fb.timestamp_et = str(bar.get("timestamp_et", ""))
    fb.open = float(bar.get("open", 0))
    fb.high = float(bar.get("high", 0))
    fb.low = float(bar.get("low", 0))
    fb.close = float(bar.get("close", 0))
    fb.volume = int(bar.get("volume", 0))

    # body / range
    bar_range = fb.high - fb.low
    if bar_range > 0:
        fb.body_pct_of_range = round(abs(fb.close - fb.open) / bar_range, 3)

    # vol_mult
    if vol_baseline is not None and bar_idx < len(vol_baseline):
        baseline = float(vol_baseline.iloc[bar_idx]) if not pd.isna(vol_baseline.iloc[bar_idx]) else 0
        if baseline > 0 and fb.volume > 0:
            fb.vol_mult_20bar = round(fb.volume / baseline, 3)

    # ribbon
    if rib is not None:
        fb.ribbon_fast = round(float(rib.get("fast", 0)), 4)
        fb.ribbon_pivot = round(float(rib.get("pivot", 0)), 4)
        fb.ribbon_slow = round(float(rib.get("slow", 0)), 4)
        fb.ribbon_spread_cents = round(float(rib.get("ribbon_spread_cents", 0)), 1)
        fb.ribbon_stack = str(rib.get("ribbon_stack", ""))

    # time of day
    ts = bar.get("timestamp_et")
    fb.time_of_day_min_from_open = _time_min_from_open(ts)
    fb.is_rth = (0 <= fb.time_of_day_min_from_open <= 390)  # 09:30-16:00

    # nearest level
    if levels:
        try:
            close_price = fb.close
            best_dist = float("inf")
            best_level = None
            for lvl in levels:
                if not isinstance(lvl, dict):
                    continue
                p = float(lvl.get("price", 0))
                if p <= 0:
                    continue
                dist = close_price - p  # signed
                if abs(dist) < best_dist:
                    best_dist = abs(dist)
                    best_level = lvl
            if best_level is not None:
                fb.nearest_level_price = float(best_level["price"])
                fb.nearest_level_distance = round(close_price - fb.nearest_level_price, 4)
                fb.nearest_level_role = str(best_level.get("role", "")
                                              or best_level.get("tier", "")).lower()
        except Exception:
            pass

    return fb


def vectorized_features_for_all_bars(
    spy_df: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    vol_baseline: pd.Series,
) -> pd.DataFrame:
    """Build a feature DataFrame for EVERY bar in spy_df — used by tight
    fingerprint matching to filter without per-bar Python overhead.

    Returns columns: bar_idx, vol_mult_20bar, ribbon_stack, ribbon_spread_cents,
    body_pct_of_range, time_of_day_min_from_open, is_rth.
    """
    n = len(spy_df)
    if n == 0:
        return pd.DataFrame()

    out = pd.DataFrame(index=spy_df.index)
    out["bar_idx"] = np.arange(n)

    # body pct of range
    bar_range = (spy_df["high"] - spy_df["low"]).replace(0, np.nan)
    out["body_pct_of_range"] = ((spy_df["close"] - spy_df["open"]).abs() / bar_range).round(3)

    # vol_mult
    safe_baseline = vol_baseline.replace(0, np.nan)
    out["vol_mult_20bar"] = (spy_df["volume"] / safe_baseline).round(3)

    # ribbon (already in ribbon_df)
    if not ribbon_df.empty:
        out["ribbon_stack"] = ribbon_df["ribbon_stack"].values
        out["ribbon_spread_cents"] = ribbon_df["ribbon_spread_cents"].values
    else:
        out["ribbon_stack"] = ""
        out["ribbon_spread_cents"] = -1.0

    # time-of-day
    try:
        ts = pd.to_datetime(spy_df["timestamp_et"])
        out["time_of_day_min_from_open"] = (ts.dt.hour - 9) * 60 + ts.dt.minute - 30
    except Exception:
        out["time_of_day_min_from_open"] = -1

    out["is_rth"] = (out["time_of_day_min_from_open"] >= 0) & (out["time_of_day_min_from_open"] <= 390)
    return out
