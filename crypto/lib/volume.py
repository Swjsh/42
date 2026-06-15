"""volume — volume-confirmation primitives.

Production heartbeat uses volume confirmation as a trigger gate (e.g., "level
break requires volume >= 1.5x 20-bar average"). The math is asset-agnostic.

Functions return ratios, not absolute volumes — so the same primitive works
for SPY shares + BTC base currency + ETH base currency.
"""
from __future__ import annotations

from typing import Sequence

from crypto.lib.bar import Bar


def rolling_mean_volume(bars: Sequence[Bar], length: int) -> list[float]:
    n = len(bars)
    out = [float("nan")] * n
    if n < length:
        return out
    s = sum(b.volume for b in bars[:length])
    out[length - 1] = s / length
    for i in range(length, n):
        s += bars[i].volume - bars[i - length].volume
        out[i] = s / length
    return out


def volume_ratio(bars: Sequence[Bar], length: int = 20) -> list[float]:
    """ratio = current bar volume / rolling mean of last `length` bars (excluding current)."""
    n = len(bars)
    out = [float("nan")] * n
    if n <= length:
        return out
    for i in range(length, n):
        window = bars[i - length : i]  # excludes current
        avg = sum(b.volume for b in window) / length
        out[i] = bars[i].volume / avg if avg > 0 else float("nan")
    return out


def is_volume_confirmed(bar: Bar, prior_bars: Sequence[Bar], threshold: float = 1.5, length: int = 20) -> bool:
    if len(prior_bars) < length:
        return False
    avg = sum(b.volume for b in prior_bars[-length:]) / length
    return avg > 0 and bar.volume / avg >= threshold
