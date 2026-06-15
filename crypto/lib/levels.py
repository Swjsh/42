"""levels — key price-level detection.

Three families:
  1. Prior-period H/L  — most recent N bars' highest high / lowest low
  2. Round numbers     — psychological levels at fixed price increments
  3. Pivot points      — classical pivot from prior-period H+L+C

Each Level carries a strength tier (★★★/★★/★) and provenance.

Level events on closed bars:
  - reclaim    : bar.open below level, bar.close above level (with min margin)
  - break      : bar.open above level, bar.close below level (with min margin)
  - reject     : bar.high crosses level, bar.close on origin side (with min margin)
  - holds      : level touched intra-bar, closed on origin side cleanly
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from crypto.lib.bar import Bar


class LevelKind(str, Enum):
    PRIOR_PERIOD_HIGH = "prior_period_high"
    PRIOR_PERIOD_LOW = "prior_period_low"
    ROUND_NUMBER = "round_number"
    PIVOT_P = "pivot_p"
    PIVOT_R1 = "pivot_r1"
    PIVOT_S1 = "pivot_s1"


class LevelEvent(str, Enum):
    RECLAIM = "reclaim"
    BREAK = "break"
    REJECT = "reject"
    HOLD = "hold"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Level:
    price: float
    kind: LevelKind
    strength: int           # 1=★, 2=★★, 3=★★★
    label: str = ""

    def __lt__(self, other: "Level") -> bool:
        return self.price < other.price


def prior_period_levels(bars: Sequence[Bar], lookback: int) -> list[Level]:
    """Return high and low of the last `lookback` closed bars (excluding the most recent)."""
    if len(bars) < lookback + 1:
        return []
    window = bars[-(lookback + 1) : -1]  # exclude the very last bar (current)
    hi = max(b.high for b in window)
    lo = min(b.low for b in window)
    return [
        Level(price=hi, kind=LevelKind.PRIOR_PERIOD_HIGH, strength=2, label=f"Prior-{lookback}-bar H"),
        Level(price=lo, kind=LevelKind.PRIOR_PERIOD_LOW, strength=2, label=f"Prior-{lookback}-bar L"),
    ]


def round_number_levels(reference_price: float, increment: float, radius: int = 3) -> list[Level]:
    """Round numbers within `radius` increments of `reference_price`."""
    base = round(reference_price / increment) * increment
    out = []
    for i in range(-radius, radius + 1):
        p = base + i * increment
        if p <= 0:
            continue
        # ★★★ if exactly on a higher-order round (e.g., for BTC at $1k increment, $10k multiples = ★★★)
        is_major = abs((p / (increment * 10)) - round(p / (increment * 10))) < 1e-9
        strength = 3 if is_major else 1
        out.append(Level(price=p, kind=LevelKind.ROUND_NUMBER, strength=strength, label=f"Round {p:.0f}"))
    return out


def pivot_points(reference_bars: Sequence[Bar]) -> list[Level]:
    """Classical floor-trader pivot from H+L+C of the reference period."""
    if not reference_bars:
        return []
    hi = max(b.high for b in reference_bars)
    lo = min(b.low for b in reference_bars)
    cl = reference_bars[-1].close
    p = (hi + lo + cl) / 3.0
    r1 = 2 * p - lo
    s1 = 2 * p - hi
    return [
        Level(price=p, kind=LevelKind.PIVOT_P, strength=2, label="Pivot P"),
        Level(price=r1, kind=LevelKind.PIVOT_R1, strength=2, label="Pivot R1"),
        Level(price=s1, kind=LevelKind.PIVOT_S1, strength=2, label="Pivot S1"),
    ]


def classify_bar_at_level(
    bar: Bar,
    level: Level,
    min_margin_pct: float = 0.05,
) -> LevelEvent:
    """Classify how a single closed bar interacted with a level.

    min_margin_pct: minimum body-margin past the level to count as a clean break/reclaim,
                   expressed as % of level price. 0.05% on BTC@80k = ~$40.
    """
    margin = level.price * min_margin_pct / 100.0
    o, c, h, l = bar.open, bar.close, bar.high, bar.low

    crossed_up = h >= level.price
    crossed_down = l <= level.price

    if o < level.price - margin and c > level.price + margin:
        return LevelEvent.RECLAIM
    if o > level.price + margin and c < level.price - margin:
        return LevelEvent.BREAK
    if crossed_up and c < level.price - margin and o < level.price:
        return LevelEvent.REJECT  # touched/exceeded then closed back below
    if crossed_down and c > level.price + margin and o > level.price:
        return LevelEvent.REJECT  # touched below then closed back above (from a resistance-as-support flip)
    if (crossed_up or crossed_down) and not (c < level.price - margin or c > level.price + margin):
        return LevelEvent.HOLD
    return LevelEvent.NONE


def nearest_levels(price: float, levels: Sequence[Level], n: int = 3) -> list[Level]:
    return sorted(levels, key=lambda L: abs(L.price - price))[:n]
