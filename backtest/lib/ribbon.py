"""Saty Pivot Ribbon — Fast / Pivot / Slow EMAs.

Periods fingerprinted from the live indicator on J's chart (see lib/ribbon_config.json):
  Fast EMA = 13
  Pivot EMA = 20
  Slow EMA = 48

EMA seeded with SMA over the first `period` bars, then standard recursion. This matches
TradingView's `ta.ema()` behavior within ~0.05 cents on SPY 5-min closes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


CONFIG_PATH = Path(__file__).parent / "ribbon_config.json"


@dataclass(frozen=True)
class RibbonState:
    """Snapshot of the ribbon at a single bar."""
    fast: float
    pivot: float
    slow: float
    spread_cents: float       # max - min across (fast, pivot, slow)
    stack: str                # 'BULL' | 'BEAR' | 'MIXED'

    @property
    def is_bull_stacked(self) -> bool:
        return self.stack == "BULL"

    @property
    def is_bear_stacked(self) -> bool:
        return self.stack == "BEAR"


def load_periods() -> dict[str, int]:
    """Load fingerprinted EMA periods from ribbon_config.json."""
    cfg = json.loads(CONFIG_PATH.read_text())
    return cfg["periods"]


def ema(closes: pd.Series | np.ndarray, period: int) -> np.ndarray:
    """Standard EMA, SMA-seeded for the first `period` bars.

    Returns float array of len(closes); the first (period - 1) values are NaN.
    Matches TradingView's `ta.ema()` to ~0.01-0.05 cents on SPY 5-min closes.
    """
    arr = np.asarray(closes, dtype=float)
    n = len(arr)
    if n < period:
        return np.full(n, np.nan)
    alpha = 2.0 / (period + 1.0)
    out = np.full(n, np.nan)
    out[period - 1] = arr[:period].mean()
    for i in range(period, n):
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out


def compute_ribbon(closes: pd.Series, periods: dict[str, int] | None = None) -> pd.DataFrame:
    """Compute the full ribbon state for every bar.

    Args:
        closes: pandas Series of close prices, indexed by bar (timestamp or int).
        periods: optional override of {fast_ema, pivot_ema, slow_ema}. Defaults to fingerprinted config.

    Returns:
        DataFrame with columns: fast, pivot, slow, spread_cents, stack
        Indexed identically to `closes`. Bars with insufficient warmup return NaN/'WARMUP'.
    """
    if periods is None:
        periods = load_periods()

    fast = ema(closes, periods["fast_ema"])
    pivot = ema(closes, periods["pivot_ema"])
    slow = ema(closes, periods["slow_ema"])

    df = pd.DataFrame({
        "fast": fast,
        "pivot": pivot,
        "slow": slow,
    }, index=closes.index)

    # Spread = max - min of the 3 EMAs (in dollars)
    triple_max = df[["fast", "pivot", "slow"]].max(axis=1)
    triple_min = df[["fast", "pivot", "slow"]].min(axis=1)
    df["spread_cents"] = (triple_max - triple_min) * 100.0

    # Stack classification — strict ordering required for BULL/BEAR; otherwise MIXED.
    df["stack"] = "WARMUP"
    valid = df[["fast", "pivot", "slow"]].notna().all(axis=1)
    bull = valid & (df["fast"] > df["pivot"]) & (df["pivot"] > df["slow"])
    bear = valid & (df["fast"] < df["pivot"]) & (df["pivot"] < df["slow"])
    mixed = valid & ~(bull | bear)
    df.loc[bull, "stack"] = "BULL"
    df.loc[bear, "stack"] = "BEAR"
    df.loc[mixed, "stack"] = "MIXED"
    return df


def ribbon_at(ribbon_df: pd.DataFrame, idx) -> RibbonState | None:
    """Return RibbonState at a specific index, or None if not yet warmed up."""
    row = ribbon_df.loc[idx]
    if row["stack"] == "WARMUP" or pd.isna(row["fast"]):
        return None
    return RibbonState(
        fast=float(row["fast"]),
        pivot=float(row["pivot"]),
        slow=float(row["slow"]),
        spread_cents=float(row["spread_cents"]),
        stack=str(row["stack"]),
    )
