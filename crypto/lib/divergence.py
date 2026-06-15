"""divergence — RSI vs price divergence detection at swing points.

Bearish (regular): price makes a HIGHER high, RSI makes a LOWER high — exhaustion.
Bullish (regular): price makes a LOWER low, RSI makes a HIGHER low — capitulation done.

Only flags divergence on confirmed swing points within `lookback` bars.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from crypto.lib.bar import Bar
from crypto.lib.indicators import rsi
from crypto.lib.trendlines import find_swing_points


@dataclass(frozen=True, slots=True)
class DivergenceHit:
    kind: str          # "bearish_regular" | "bullish_regular"
    first_idx: int
    second_idx: int
    price_first: float
    price_second: float
    rsi_first: float
    rsi_second: float


def find_divergences(bars: Sequence[Bar], rsi_length: int = 14, swing_window: int = 3, lookback: int = 40) -> list[DivergenceHit]:
    if len(bars) < rsi_length + swing_window * 2 + 5:
        return []
    r = rsi(bars, rsi_length)
    swings = find_swing_points(bars, swing_window)

    highs = [s for s in swings if s.kind == "swing_high" and not _is_nan(r[s.bar_index])]
    lows = [s for s in swings if s.kind == "swing_low" and not _is_nan(r[s.bar_index])]

    hits: list[DivergenceHit] = []
    # Bearish: consecutive swing highs with price higher but RSI lower
    for i in range(1, len(highs)):
        a, b = highs[i - 1], highs[i]
        if b.bar_index - a.bar_index > lookback:
            continue
        if b.price > a.price and r[b.bar_index] < r[a.bar_index]:
            hits.append(DivergenceHit("bearish_regular", a.bar_index, b.bar_index,
                                      a.price, b.price, r[a.bar_index], r[b.bar_index]))
    for i in range(1, len(lows)):
        a, b = lows[i - 1], lows[i]
        if b.bar_index - a.bar_index > lookback:
            continue
        if b.price < a.price and r[b.bar_index] > r[a.bar_index]:
            hits.append(DivergenceHit("bullish_regular", a.bar_index, b.bar_index,
                                      a.price, b.price, r[a.bar_index], r[b.bar_index]))
    return hits


def _is_nan(x) -> bool:
    return x != x
