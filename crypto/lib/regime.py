"""regime — classify bars into trend / chop / breakout.

Definitions:
  - TREND_UP   : close > EMA(20), ATR(14) > median ATR of last 50 bars * 0.8
  - TREND_DOWN : close < EMA(20), ATR sane
  - CHOP       : ATR < 0.5 * median ATR (low volatility)
  - BREAKOUT   : ATR > 1.5 * median ATR AND |close - EMA(20)| > 1.5 * ATR
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Sequence

from crypto.lib.bar import Bar
from crypto.lib.indicators import atr, ema


@dataclass(frozen=True, slots=True)
class RegimeState:
    regime: str  # TREND_UP | TREND_DOWN | CHOP | BREAKOUT | UNKNOWN
    close: float
    ema_20: float
    atr_14: float
    median_atr_50: float


def classify_regimes(bars: Sequence[Bar]) -> list[RegimeState]:
    n = len(bars)
    e = ema(bars, 20)
    a = atr(bars, 14)
    out: list[RegimeState] = []
    for i in range(n):
        c = bars[i].close
        ei = e[i]
        ai = a[i]
        if any(x != x for x in (ei, ai)):
            out.append(RegimeState("UNKNOWN", c, ei, ai, float("nan")))
            continue
        window_start = max(0, i - 50)
        window_atr = [v for v in a[window_start:i + 1] if v == v]  # filter NaN
        if not window_atr:
            out.append(RegimeState("UNKNOWN", c, ei, ai, float("nan")))
            continue
        med = median(window_atr)
        regime = "UNKNOWN"
        if ai > 1.5 * med and abs(c - ei) > 1.5 * ai:
            regime = "BREAKOUT"
        elif ai < 0.5 * med:
            regime = "CHOP"
        elif c > ei and ai >= 0.8 * med:
            regime = "TREND_UP"
        elif c < ei and ai >= 0.8 * med:
            regime = "TREND_DOWN"
        else:
            regime = "CHOP"
        out.append(RegimeState(regime, c, ei, ai, med))
    return out
