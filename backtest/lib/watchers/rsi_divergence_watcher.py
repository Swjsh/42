"""RSI_DIVERGENCE_BULL watcher (WATCH-ONLY per OP-21).

Detects bullish RSI divergence on the 5-minute SPY chart — price makes a new lower
swing low while RSI makes a higher low. Classic momentum exhaustion signal.

Stage-1 scan results (2026-05-21, 16-month SPY 5m backfill):
  - BULL divergence: N=42, WR=81.0%, 41 distinct dates (no concentration)
  - VIX MODERATE (15-20): WR=85.2%, N=27 — primary edge regime
  - OOS walk-forward (75/25 chronological): IS=83.9% vs OOS=72.7%, ratio=0.867 — PASS
  - BEAR divergence: WR=47.6% (no edge — excluded)
  - Failure mode: strong trend months (April 2025/2026) — divergence fails during cascades
  - OP-16 edge_capture: ZERO standalone (no J anchor day coverage)

Usage: complementary signal. Primary value as:
  (a) Exit enhancer for active bear positions (BULL divergence = potential reversal warning)
  (b) Bull setup trigger if/when BULLISH_RECLAIM gets J ratification

OP-21 live gates NOT yet passed:
  - 0/15 live BULL observations
  - 0/3 J-confirmed wins
DO NOT wire into production heartbeat.md until gates pass per OP-21.

Source: backtest/autoresearch/rsi_divergence_scan.py
        analysis/backtests/rsi-divergence-scan/results.json
        strategy/candidates/2026-05-21-rsi-divergence-bull-watcher.md
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd

from . import WatcherSignal
from ..filters import BarContext

# ── Parameters ────────────────────────────────────────────────────────────────
RSI_PERIOD: int = 14
SWING_LOOKBACK: int = 5           # bars for swing detection
MIN_SWING_SIZE: float = 0.30      # minimum price swing ($SPY)
MIN_RSI_DIVERGENCE: float = 2.0   # RSI must diverge ≥ 2 points
ENTRY_TIME_START: dt.time = dt.time(9, 40)
ENTRY_TIME_END: dt.time = dt.time(15, 0)
_COOLDOWN_BARS: int = 10

# ── Exit knobs (OP-21 watch-only defaults) ─────────────────────────────────────
DEFAULT_PREMIUM_STOP_PCT: float = -0.10   # standard watch-only stop
DEFAULT_TP1_PREMIUM_PCT: float = 0.30
DEFAULT_RUNNER_TARGET_PCT: float = 1.5

# Module-level state (warm up required per L35 ORB lesson)
_last_signal_bar_idx: int = -_COOLDOWN_BARS


def _rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _find_prior_swing_low(lows: pd.Series, rsi: pd.Series, current_iloc: int) -> tuple[float, float] | None:
    """Find the most recent swing low in lows and its RSI value.

    Returns (prior_low_price, prior_low_rsi) or None if none found.
    Only considers bars at least SWING_LOOKBACK+1 back from current.
    """
    start = max(0, current_iloc - SWING_LOOKBACK * 3)
    end = current_iloc - (SWING_LOOKBACK + 1)
    if end <= start:
        return None
    window_lows = lows.iloc[start:end + 1]
    if len(window_lows) < 1:
        return None
    prior_idx = window_lows.idxmin()
    return lows.loc[prior_idx], rsi.loc[prior_idx]


def detect_rsi_divergence_bull(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect bullish RSI divergence on the current bar.

    Fires when:
    1. Current bar makes a lower close vs a prior swing low (price LL)
    2. RSI at current bar is HIGHER than RSI at that prior swing low (RSI HL)
    3. Divergence thresholds met: price diff >= MIN_SWING_SIZE, RSI diff >= MIN_RSI_DIVERGENCE
    4. Time window: 09:40-15:00 ET
    5. Cooldown: >= COOLDOWN_BARS since last signal

    Returns WatcherSignal with direction="long" or None.
    """
    global _last_signal_bar_idx

    bar_time = ctx.timestamp_et.time()
    if not (ENTRY_TIME_START <= bar_time <= ENTRY_TIME_END):
        return None

    if ctx.bar_idx - _last_signal_bar_idx < _COOLDOWN_BARS:
        return None

    prior = ctx.prior_bars
    if len(prior) < RSI_PERIOD + SWING_LOOKBACK + 3:
        return None

    close_series = prior["close"].reset_index(drop=True)
    rsi_series = _rsi(close_series)

    current_iloc = len(close_series) - 1
    current_close = close_series.iloc[current_iloc]
    current_rsi = rsi_series.iloc[current_iloc]

    if pd.isna(current_rsi):
        return None

    result = _find_prior_swing_low(close_series, rsi_series, current_iloc)
    if result is None:
        return None
    prior_low, prior_rsi = result

    if pd.isna(prior_rsi):
        return None

    # Price makes LOWER LOW
    if current_close >= prior_low - MIN_SWING_SIZE:
        return None

    # RSI makes HIGHER LOW (divergence)
    if current_rsi <= prior_rsi + MIN_RSI_DIVERGENCE:
        return None

    price_div = round(prior_low - current_close, 2)
    rsi_div = round(current_rsi - prior_rsi, 1)

    confidence = "low"
    if rsi_div >= 5.0 and ctx.vix_now < 20:
        confidence = "high"
    elif rsi_div >= 3.0 or ctx.vix_now < 20:
        confidence = "medium"

    entry = float(ctx.bar["close"])
    stop = entry - MIN_SWING_SIZE  # chart stop: SPY drops $0.30 below entry
    tp1 = entry + 0.25             # minimal initial target
    runner = entry + 0.75

    _last_signal_bar_idx = ctx.bar_idx

    return WatcherSignal(
        watcher_name="rsi_divergence_watcher",
        setup_name="RSI_DIVERGENCE_BULL",
        direction="long",
        entry_price=entry,
        stop_price=stop,
        tp1_price=tp1,
        runner_price=runner,
        confidence=confidence,
        reason=(
            f"Bull RSI divergence: price LL ({current_close:.2f} vs prior {prior_low:.2f}, "
            f"diff={price_div:.2f}$), RSI HL ({current_rsi:.1f} vs prior {prior_rsi:.1f}, "
            f"div={rsi_div:.1f}pts)"
        ),
        triggers_fired=["rsi_divergence", "price_lower_low", "rsi_higher_low"],
        metadata={
            "rsi_divergence_pts": rsi_div,
            "price_divergence_usd": price_div,
            "prior_low": prior_low,
            "prior_rsi": round(prior_rsi, 1),
            "vix": ctx.vix_now,
        },
    )
