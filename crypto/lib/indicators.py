"""indicators — RSI / EMA / VWAP / ATR.

Implementations match TradingView Pine v5 conventions so values cross-validate
against the chart we read via the TradingView MCP.

  RSI (Wilder)  : alpha = 1/length             (NOT 2/(length+1))
  EMA           : alpha = 2/(length+1)
  ATR (Wilder)  : true-range smoothed with Wilder alpha
  VWAP          : sum(typical_price * volume) / sum(volume) over anchor window;
                  default anchor = whole input window (session-anchored VWAP
                  is the caller's responsibility — anchor by passing only
                  the session's bars)

All functions accept a sequence of Bar and return a list aligned to the input
(length matches; leading values may be NaN until enough data has accumulated).
"""
from __future__ import annotations

import math
from typing import Sequence

from crypto.lib.bar import Bar


def rsi(bars: Sequence[Bar], length: int = 14) -> list[float]:
    """Wilder RSI. First length-1 values are NaN; value at index `length` is the seed."""
    n = len(bars)
    out = [float("nan")] * n
    if n <= length:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, length + 1):
        change = bars[i].close - bars[i - 1].close
        if change >= 0:
            gains += change
        else:
            losses += -change
    avg_gain = gains / length
    avg_loss = losses / length
    out[length] = _rsi_from(avg_gain, avg_loss)
    for i in range(length + 1, n):
        change = bars[i].close - bars[i - 1].close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = (avg_gain * (length - 1) + gain) / length
        avg_loss = (avg_loss * (length - 1) + loss) / length
        out[i] = _rsi_from(avg_gain, avg_loss)
    return out


def _rsi_from(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def ema(bars: Sequence[Bar], length: int) -> list[float]:
    n = len(bars)
    out = [float("nan")] * n
    if n < length:
        return out
    # Seed with SMA of first `length` closes (TV Pine convention for ta.ema)
    seed = sum(bars[i].close for i in range(length)) / length
    out[length - 1] = seed
    alpha = 2.0 / (length + 1)
    for i in range(length, n):
        out[i] = bars[i].close * alpha + out[i - 1] * (1 - alpha)
    return out


def true_range(bars: Sequence[Bar]) -> list[float]:
    n = len(bars)
    out = [float("nan")] * n
    if n == 0:
        return out
    out[0] = bars[0].high - bars[0].low
    for i in range(1, n):
        h, l, pc = bars[i].high, bars[i].low, bars[i - 1].close
        out[i] = max(h - l, abs(h - pc), abs(l - pc))
    return out


def atr(bars: Sequence[Bar], length: int = 14) -> list[float]:
    n = len(bars)
    out = [float("nan")] * n
    if n < length:
        return out
    tr = true_range(bars)
    seed = sum(tr[1 : length + 1]) / length if n > length else float("nan")
    if math.isnan(seed):
        return out
    out[length] = seed
    for i in range(length + 1, n):
        out[i] = (out[i - 1] * (length - 1) + tr[i]) / length
    return out


def vwap(bars: Sequence[Bar]) -> list[float]:
    """Anchored VWAP across the entire input window.

    Typical-price weighted: tp = (H+L+C)/3. To compute session VWAP, slice
    `bars` to the session's bars before calling.
    """
    n = len(bars)
    out = [float("nan")] * n
    cum_vp = 0.0
    cum_v = 0.0
    for i, b in enumerate(bars):
        tp = (b.high + b.low + b.close) / 3.0
        cum_vp += tp * b.volume
        cum_v += b.volume
        out[i] = cum_vp / cum_v if cum_v > 0 else float("nan")
    return out
