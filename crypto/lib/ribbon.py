"""ribbon — EMA cascade ("ribbon stack") interpretation.

Production heartbeat reads the Saty Pivot Ribbon (Fast/Pivot/Slow EMA). Generalized
here: ANY ordered list of EMA lengths gives a ribbon. Status is BULL if EMAs are in
decreasing-length order ascending (fast > pivot > slow); BEAR if reverse; MIXED otherwise.

Spread = distance between extremes, often used as a strength gate (≥30 cents on SPY).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from crypto.lib.bar import Bar
from crypto.lib.indicators import ema


@dataclass(frozen=True, slots=True)
class RibbonState:
    fast: float
    pivot: float
    slow: float
    spread: float          # |fast - slow|
    status: str            # "BULL" | "BEAR" | "MIXED"


def compute_ribbon(bars: Sequence[Bar], fast_len: int = 9, pivot_len: int = 21, slow_len: int = 55) -> list[RibbonState]:
    f = ema(bars, fast_len)
    p = ema(bars, pivot_len)
    s = ema(bars, slow_len)
    n = len(bars)
    out: list[RibbonState] = []
    nan = float("nan")
    for i in range(n):
        fi, pi, si = f[i], p[i], s[i]
        if any(x != x for x in (fi, pi, si)):  # NaN check
            out.append(RibbonState(nan, nan, nan, nan, "MIXED"))
            continue
        spread = abs(fi - si)
        if fi > pi > si:
            status = "BULL"
        elif fi < pi < si:
            status = "BEAR"
        else:
            status = "MIXED"
        out.append(RibbonState(fi, pi, si, spread, status))
    return out
