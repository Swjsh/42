"""breakout — composite primitive: level break + close margin + volume confirmation.

A "quality breakout" requires ALL of:
  1. Bar's close is past the level by >= `min_close_margin_pct`
  2. Bar's volume is >= `volume_threshold` * 20-bar avg
  3. (Optional) prior N bars did NOT close past the level (genuine break, not chop)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from crypto.lib.bar import Bar
from crypto.lib.levels import Level
from crypto.lib.volume import is_volume_confirmed


@dataclass(frozen=True, slots=True)
class BreakoutHit:
    bar_index: int
    level_price: float
    close: float
    direction: str        # "up" | "down"
    margin_pct: float
    volume_ratio: float


def detect_quality_breakouts(
    bars: Sequence[Bar],
    levels: Sequence[Level],
    min_close_margin_pct: float = 0.05,
    volume_threshold: float = 1.5,
    volume_length: int = 20,
    require_clean_prior: int = 0,
) -> list[BreakoutHit]:
    out: list[BreakoutHit] = []
    for i, bar in enumerate(bars):
        if i < volume_length:
            continue
        prior_bars = bars[i - volume_length : i]
        avg_vol = sum(b.volume for b in prior_bars) / volume_length
        vol_ratio = bar.volume / avg_vol if avg_vol > 0 else 0
        for L in levels:
            margin = L.price * min_close_margin_pct / 100.0
            direction = None
            if bar.close > L.price + margin:
                direction = "up"
            elif bar.close < L.price - margin:
                direction = "down"
            if direction is None:
                continue
            if not is_volume_confirmed(bar, prior_bars, threshold=volume_threshold, length=volume_length):
                continue
            if require_clean_prior > 0:
                window = bars[max(0, i - require_clean_prior) : i]
                if direction == "up":
                    if any(b.close > L.price for b in window):
                        continue
                else:
                    if any(b.close < L.price for b in window):
                        continue
            actual_margin_pct = abs(bar.close - L.price) / L.price * 100
            out.append(BreakoutHit(i, L.price, bar.close, direction, actual_margin_pct, vol_ratio))
    return out
