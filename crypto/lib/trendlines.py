"""trendlines — swing-point detection + linear trendline fitting.

Swing point: a bar whose high (low) exceeds the surrounding `window` bars'
highs (lows). The fewer surrounding bars considered, the more swings detected
(noisier); the more bars, the more major-only swings.

Trendline: a straight line through ≥ 2 swing points of the same type.
Quality = number of swing-point touches (within `touch_tolerance_pct`).

A trendline projected to a future bar yields an expected price level. Bars
crossing that level are "trendline events" (similar to level events).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from crypto.lib.bar import Bar


@dataclass(frozen=True, slots=True)
class SwingPoint:
    bar_index: int
    bar_time_unix: float
    price: float
    kind: str  # "swing_high" | "swing_low"


@dataclass(frozen=True, slots=True)
class Trendline:
    slope: float           # price units per second
    intercept: float       # price at time=0 unix (informational)
    swing_points: tuple[SwingPoint, ...]
    kind: str              # "resistance" (highs) | "support" (lows)

    def price_at(self, time_unix: float) -> float:
        return self.intercept + self.slope * time_unix


def find_swing_points(bars: Sequence[Bar], window: int = 3) -> list[SwingPoint]:
    """Find swing highs/lows. A swing high at index i requires
    bars[i].high > all of bars[i-window:i].high and bars[i+1:i+window+1].high."""
    out: list[SwingPoint] = []
    n = len(bars)
    for i in range(window, n - window):
        h = bars[i].high
        l = bars[i].low
        is_swing_high = all(bars[j].high < h for j in range(i - window, i)) and all(
            bars[j].high < h for j in range(i + 1, i + window + 1)
        )
        is_swing_low = all(bars[j].low > l for j in range(i - window, i)) and all(
            bars[j].low > l for j in range(i + 1, i + window + 1)
        )
        if is_swing_high:
            out.append(SwingPoint(i, bars[i].open_time.timestamp(), h, "swing_high"))
        if is_swing_low:
            out.append(SwingPoint(i, bars[i].open_time.timestamp(), l, "swing_low"))
    return out


def fit_trendline(points: Sequence[SwingPoint], kind: str) -> Trendline | None:
    """Fit a least-squares line through swing points of the given kind."""
    filtered = [sp for sp in points if sp.kind == ("swing_high" if kind == "resistance" else "swing_low")]
    if len(filtered) < 2:
        return None
    xs = [sp.bar_time_unix for sp in filtered]
    ys = [sp.price for sp in filtered]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return None
    slope = num / den
    intercept = mean_y - slope * mean_x
    return Trendline(slope=slope, intercept=intercept, swing_points=tuple(filtered), kind=kind)


def trendline_touches(bars: Sequence[Bar], line: Trendline, tolerance_pct: float = 0.10) -> int:
    """Count bars whose high (resistance) or low (support) is within tolerance of the projected line."""
    n = 0
    for bar in bars:
        projected = line.price_at(bar.open_time.timestamp())
        if projected <= 0:
            continue
        tol = projected * tolerance_pct / 100.0
        target = bar.high if line.kind == "resistance" else bar.low
        if abs(target - projected) <= tol:
            n += 1
    return n
