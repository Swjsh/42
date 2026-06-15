"""candlesticks — pattern recognition on closed bars.

Per project doctrine (OP 6 + rule 6): candlestick patterns are AWARENESS LAYER,
never entry triggers in isolation. These detectors exist to validate that our
recognition logic agrees with what J reads on the chart.

Patterns implemented:
  bullish_engulfing : red bar then green bar whose body engulfs the prior body
  bearish_engulfing : green bar then red bar whose body engulfs the prior body
  doji              : body <= doji_body_ratio * range (default 10%)
  hammer            : small body in upper third, long lower wick (>=2x body)
  shooting_star     : small body in lower third, long upper wick (>=2x body)
  inside_bar        : current bar's range entirely within prior bar's range

Each returns a list of (index, pattern_name, confidence) tuples where confidence
is in [0,1] (currently just 1.0 if pattern fires, 0.0 otherwise — placeholder
for future continuous scoring).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from crypto.lib.bar import Bar


@dataclass(frozen=True, slots=True)
class PatternHit:
    bar_index: int
    pattern: str
    confidence: float


def _body(bar: Bar) -> float:
    return abs(bar.close - bar.open)


def _range_size(bar: Bar) -> float:
    return bar.high - bar.low


def _is_green(bar: Bar) -> bool:
    return bar.close > bar.open


def _is_red(bar: Bar) -> bool:
    return bar.close < bar.open


def detect_bullish_engulfing(bars: Sequence[Bar]) -> list[PatternHit]:
    hits = []
    for i in range(1, len(bars)):
        prev, cur = bars[i - 1], bars[i]
        if (
            _is_red(prev) and _is_green(cur)
            and cur.open <= prev.close
            and cur.close >= prev.open
            and _body(cur) > _body(prev)
        ):
            hits.append(PatternHit(i, "bullish_engulfing", 1.0))
    return hits


def detect_bearish_engulfing(bars: Sequence[Bar]) -> list[PatternHit]:
    hits = []
    for i in range(1, len(bars)):
        prev, cur = bars[i - 1], bars[i]
        if (
            _is_green(prev) and _is_red(cur)
            and cur.open >= prev.close
            and cur.close <= prev.open
            and _body(cur) > _body(prev)
        ):
            hits.append(PatternHit(i, "bearish_engulfing", 1.0))
    return hits


def detect_doji(bars: Sequence[Bar], body_ratio: float = 0.10) -> list[PatternHit]:
    hits = []
    for i, b in enumerate(bars):
        rng = _range_size(b)
        if rng == 0:
            continue
        if _body(b) / rng <= body_ratio:
            hits.append(PatternHit(i, "doji", 1.0))
    return hits


def detect_hammer(bars: Sequence[Bar], wick_ratio: float = 2.0) -> list[PatternHit]:
    hits = []
    for i, b in enumerate(bars):
        body = _body(b)
        if body == 0:
            continue
        upper_wick = b.high - max(b.open, b.close)
        lower_wick = min(b.open, b.close) - b.low
        if (
            lower_wick >= wick_ratio * body
            and upper_wick <= body * 0.5
            and lower_wick > upper_wick
        ):
            hits.append(PatternHit(i, "hammer", 1.0))
    return hits


def detect_shooting_star(bars: Sequence[Bar], wick_ratio: float = 2.0) -> list[PatternHit]:
    hits = []
    for i, b in enumerate(bars):
        body = _body(b)
        if body == 0:
            continue
        upper_wick = b.high - max(b.open, b.close)
        lower_wick = min(b.open, b.close) - b.low
        if (
            upper_wick >= wick_ratio * body
            and lower_wick <= body * 0.5
            and upper_wick > lower_wick
        ):
            hits.append(PatternHit(i, "shooting_star", 1.0))
    return hits


def detect_inside_bar(bars: Sequence[Bar]) -> list[PatternHit]:
    hits = []
    for i in range(1, len(bars)):
        prev, cur = bars[i - 1], bars[i]
        if cur.high <= prev.high and cur.low >= prev.low:
            hits.append(PatternHit(i, "inside_bar", 1.0))
    return hits


ALL_DETECTORS = {
    "bullish_engulfing": detect_bullish_engulfing,
    "bearish_engulfing": detect_bearish_engulfing,
    "doji": detect_doji,
    "hammer": detect_hammer,
    "shooting_star": detect_shooting_star,
    "inside_bar": detect_inside_bar,
}


def detect_all(bars: Sequence[Bar]) -> list[PatternHit]:
    out: list[PatternHit] = []
    for fn in ALL_DETECTORS.values():
        out.extend(fn(bars))
    return sorted(out, key=lambda h: (h.bar_index, h.pattern))
