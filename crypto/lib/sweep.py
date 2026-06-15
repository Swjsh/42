"""sweep — liquidity-grab / failed-breakout pattern detector.

A SWEEP is a specific intra-bar pattern:
  - The bar's HIGH (or LOW) takes out a key level by at least `min_wick_pct`
  - The bar's CLOSE is back on the ORIGINAL side of the level by at least `min_close_back_pct`
  - Optionally: prior `clean_prior` bars did NOT close past the level

The 2026-05-14 09:55 SPY bar is the canonical example:
  - Bar high 745.47 was ABOVE PMH 745.43 (sweep up by 4 cents)
  - Bar close 744.43 was BELOW PMH 745.43 by $1.00 (closed back below)
  - Pre-bar context: 09:50 close 745.02 was below PMH (clean prior)
  - Verdict: BEARISH SWEEP / FAILED BREAKOUT UP

The heartbeat naively reading the in-progress bar's "high above PMH" saw a
RECLAIM trigger. The correct closed-bar reading would have seen this SWEEP
pattern and either rejected entry or fired bearish.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from crypto.lib.bar import Bar
from crypto.lib.levels import Level


@dataclass(frozen=True, slots=True)
class SweepHit:
    bar_index: int
    level_price: float
    direction: str               # "up" (swept high then closed back below) or "down"
    wick_excess_pct: float       # how far the wick exceeded the level (% of level)
    close_back_pct: float        # how far the close was back from the level (% of level)


def detect_sweeps(
    bars: Sequence[Bar],
    levels: Sequence[Level],
    min_wick_pct: float = 0.02,
    min_close_back_pct: float = 0.05,
    clean_prior: int = 3,
) -> list[SweepHit]:
    """Detect bearish (up-sweep) and bullish (down-sweep) liquidity grabs at each level."""
    out: list[SweepHit] = []
    for i, bar in enumerate(bars):
        if i < clean_prior:
            continue
        for L in levels:
            wick_threshold = L.price * min_wick_pct / 100.0
            close_threshold = L.price * min_close_back_pct / 100.0

            # Up-sweep (bearish): high exceeds level, close back below
            high_exceed = bar.high - L.price
            close_below = L.price - bar.close
            if high_exceed >= wick_threshold and close_below >= close_threshold:
                # Prior bars must have closed BELOW the level (clean setup)
                clean = all(bars[j].close < L.price for j in range(max(0, i - clean_prior), i))
                if clean:
                    out.append(SweepHit(i, L.price, "up", high_exceed / L.price * 100, close_below / L.price * 100))
                    continue  # don't double-count same level both directions

            # Down-sweep (bullish): low pierces level, close back above
            low_pierce = L.price - bar.low
            close_above = bar.close - L.price
            if low_pierce >= wick_threshold and close_above >= close_threshold:
                clean = all(bars[j].close > L.price for j in range(max(0, i - clean_prior), i))
                if clean:
                    out.append(SweepHit(i, L.price, "down", low_pierce / L.price * 100, close_above / L.price * 100))
    return out
