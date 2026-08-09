"""trendline_geometry.py -- LOCAL wick-anchored trendline detection for the MES 4h swing
battery (`backtest/futures/seeds/trendline_swing_seed.py` is the consumer).

FILE-OWNERSHIP NOTE: `backtest/lib/trendline_detector.py` is reserved for a sibling agent
and did not exist when this module was written (verified before starting). Per the work
order, this geometry lives LOCALLY here instead of that path. Some conceptual overlap with
`backtest/lib/trendlines.py` (the live SPY 0DTE detector, scipy-`find_peaks`-based) and
`crypto/lib/trendlines.py` (a simpler window-fractal swing-point primitive, REUSED directly
below rather than re-implemented) is expected and disclosed, not an oversight -- flagged
for later consolidation, per the work order's instruction.

Validity grammar and its source (the exact rules encoded below):
`analysis/deep-research/TRENDLINE-SWING-MES-PREREG-2026-08-09.md`.

Design, in one paragraph: swing points are found ONCE over the full bar array (safe --
same precedent as `structure_seed.py`'s use of `walk_structure`, see
`test_trendline_swing_seed.py::TestNoLookahead`), but a swing point at `bar_index` is only
CONSUMABLE starting at `bar_index + window` (the earliest bar at which `find_swing_points`
could have confirmed it using only bars up to that point -- causal by construction). Every
same-kind PAIR of confirmed swing points is a line candidate; a candidate is kept iff it
clears every rule in the prereg table (>=3 touches within tolerance, >=6 bars between
consecutive touches, >=30 bar span, ATR-normalized slope < 1.0 i.e. "<45 degrees"). Kept
candidates are deduplicated (near-identical slope+level = the same real line found via a
different anchor pair). Each surviving `TrendLine` is "live" from `confirmed_idx + 1`
until either a break bar occurs (tracked via `broken_at_idx`) or the bar data ends.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.trendlines import find_swing_points, SwingPoint  # noqa: E402

# ─── Frozen validity rules (prereg, NOT gridded) ───────────────────────────────
MIN_TOUCHES = 3
MIN_TOUCH_SPACING_BARS = 6
MIN_SPAN_BARS = 30
TOUCH_TOLERANCE_PCT = 0.0010          # 0.10% -- matches the live SPY bear detector's proximity_pct
MIN_STOP_DISTANCE_PTS = 0.25           # 1 MES tick floor, avoids a degenerate near-zero stop
BREAK_RETEST_LOOKAHEAD_BARS = 10


@dataclass(frozen=True, slots=True)
class TrendLine:
    kind: str                          # "support" (fit through lows) | "resistance" (highs)
    slope: float                       # price points per bar
    intercept: float                   # price at bar_index=0 (line: intercept + slope*i)
    touch_indices: tuple[int, ...]     # bar indices of every swing point counted as a touch, sorted
    first_touch_idx: int
    last_touch_idx: int
    confirmed_idx: int                 # last_touch's own swing-confirmation bar (last_touch_idx + window)
    window: int

    def price_at(self, bar_index: int) -> float:
        return self.intercept + self.slope * bar_index


def bars_df_to_bar_objects(bars: pd.DataFrame) -> list[Bar]:
    """4h-of-RTH (or daily) OHLCV frame -> tz-aware-UTC crypto.lib.bar.Bar objects.
    Duplicates `structure_seed.bars_df_to_bar_objects` deliberately (kept import-free of
    a sibling seed module so this geometry module has no seed-layer dependency)."""
    from datetime import timezone
    out = []
    for row in bars.itertuples(index=False):
        ts = row.timestamp_et
        ts_utc = ts.tz_convert(timezone.utc) if ts.tzinfo is not None else ts.tz_localize(timezone.utc)
        out.append(Bar(open_time=ts_utc, open=float(row.open), high=float(row.high),
                        low=float(row.low), close=float(row.close),
                        volume=float(getattr(row, "volume", 0) or 0),
                        granularity_seconds=4 * 3600, source="mes_4h_rth"))
    return out


def _atr_lookup(bars: pd.DataFrame, atr: pd.Series) -> np.ndarray:
    return atr.reindex(range(len(bars))).to_numpy(dtype=float)


def _mean_atr_over_span(atr_arr: np.ndarray, lo: int, hi: int) -> Optional[float]:
    seg = atr_arr[lo:hi + 1]
    seg = seg[np.isfinite(seg) & (seg > 0)]
    if len(seg) == 0:
        return None
    return float(seg.mean())


def _dedupe_lines(candidates: list[TrendLine], bars_len: int, tolerance_pct: float) -> list[TrendLine]:
    """Two candidates with near-identical slope AND near-identical projected price at the
    domain midpoint are the SAME real line found via a different anchor pair -- keep only
    the one with the most touches (ties: the one confirmed earliest, so it's usable sooner).
    Mirrors the same "cluster then keep best" shape as backtest/lib/trendlines.py::_dedupe
    (a different implementation -- that one is scipy/find_peaks based -- but the same idea)."""
    if not candidates:
        return []
    mid = bars_len / 2.0
    ordered = sorted(candidates, key=lambda c: (-len(c.touch_indices), c.confirmed_idx))
    kept: list[TrendLine] = []
    for c in ordered:
        cp = c.price_at(mid)
        is_dup = False
        for k in kept:
            if k.kind != c.kind:
                continue
            kp = k.price_at(mid)
            tol = max(abs(kp), abs(cp)) * tolerance_pct * 4  # loose: dedupe near-parallel near-level lines
            if abs(cp - kp) <= tol and abs(c.slope - k.slope) <= (abs(k.slope) * 0.5 + 1e-9):
                is_dup = True
                break
        if not is_dup:
            kept.append(c)
    return kept


def find_trendlines(bars: pd.DataFrame, window: int, atr: pd.Series,
                     tolerance_pct: float = TOUCH_TOLERANCE_PCT,
                     min_touches: int = MIN_TOUCHES,
                     min_spacing_bars: int = MIN_TOUCH_SPACING_BARS,
                     min_span_bars: int = MIN_SPAN_BARS) -> list[TrendLine]:
    """All valid support/resistance lines over the full bar array, each carrying its own
    `confirmed_idx` (the bar index at which a causal walk may first use it -- see module
    docstring). Bars: RangeIndex 0..n-1 OHLC frame (4h-of-RTH). `atr`: Wilder ATR(14) Series
    aligned to `bars` (used only for the slope/"45 degree" cap, per the prereg)."""
    bar_objs = bars_df_to_bar_objects(bars)
    swings = find_swing_points(bar_objs, window=window, inclusive_right=True)
    atr_arr = _atr_lookup(bars, atr)

    out: list[TrendLine] = []
    for kind, sk in (("resistance", "swing_high"), ("support", "swing_low")):
        pts: list[SwingPoint] = sorted((s for s in swings if s.kind == sk), key=lambda s: s.bar_index)
        n = len(pts)
        for i in range(n):
            Q = pts[i]
            for j in range(i + 1, n):
                P = pts[j]
                span = P.bar_index - Q.bar_index
                if span < min_span_bars:
                    continue
                slope = (P.price - Q.price) / span
                intercept = Q.price - slope * Q.bar_index
                in_range = [s for s in pts if Q.bar_index <= s.bar_index <= P.bar_index]
                touches = [s for s in in_range
                           if abs(s.price - (intercept + slope * s.bar_index))
                           <= tolerance_pct * (intercept + slope * s.bar_index)]
                if len(touches) < min_touches:
                    continue
                touches_sorted = sorted(touches, key=lambda s: s.bar_index)
                gaps = [touches_sorted[k + 1].bar_index - touches_sorted[k].bar_index
                        for k in range(len(touches_sorted) - 1)]
                if gaps and min(gaps) < min_spacing_bars:
                    continue
                mean_atr = _mean_atr_over_span(atr_arr, Q.bar_index, P.bar_index)
                if mean_atr is None or abs(slope) >= mean_atr:
                    continue  # fails the ATR-normalized "<45 degree" cap, or no ATR data yet (warmup)
                out.append(TrendLine(
                    kind=kind, slope=slope, intercept=intercept,
                    touch_indices=tuple(s.bar_index for s in touches_sorted),
                    first_touch_idx=touches_sorted[0].bar_index,
                    last_touch_idx=touches_sorted[-1].bar_index,
                    confirmed_idx=P.bar_index + window, window=window,
                ))
    return _dedupe_lines(out, len(bars), tolerance_pct)


def find_opposing_safety_line(action_line: TrendLine,
                               swings_opposing_kind: list[SwingPoint],
                               signal_bar_idx: int) -> Optional[TrendLine]:
    """Parallel-channel construction of the "Safety Line" for a break/break_retest trade
    (prereg: "same slope as the Action Line, anchored through the most extreme opposing-
    kind swing point within the Action Line's own touch span"). Returns None if no
    opposing-kind swing point exists in [action_line.first_touch_idx, signal_bar_idx] --
    caller must exclude the signal from safety_line cells in that case (pre-registered,
    not silently substituted)."""
    lo, hi = action_line.first_touch_idx, signal_bar_idx
    candidates = [s for s in swings_opposing_kind if lo <= s.bar_index <= hi]
    if not candidates:
        return None
    # "most extreme": highest price for an opposing-highs search (action=support), lowest
    # for an opposing-lows search (action=resistance) -- opposing kind is always the OTHER
    # side, so "most extreme" always means "furthest from the action line," i.e. max price
    # when opposing kind is swing_high, min price when opposing kind is swing_low.
    opposing_kind = candidates[0].kind
    anchor = max(candidates, key=lambda s: s.price) if opposing_kind == "swing_high" \
        else min(candidates, key=lambda s: s.price)
    intercept = anchor.price - action_line.slope * anchor.bar_index
    return TrendLine(
        kind=("resistance" if action_line.kind == "support" else "support"),
        slope=action_line.slope, intercept=intercept,
        touch_indices=(anchor.bar_index,), first_touch_idx=anchor.bar_index,
        last_touch_idx=anchor.bar_index, confirmed_idx=anchor.bar_index + action_line.window,
        window=action_line.window,
    )


__all__ = ["TrendLine", "bars_df_to_bar_objects", "find_trendlines", "find_opposing_safety_line",
           "MIN_TOUCHES", "MIN_TOUCH_SPACING_BARS", "MIN_SPAN_BARS", "TOUCH_TOLERANCE_PCT",
           "MIN_STOP_DISTANCE_PTS", "BREAK_RETEST_LOOKAHEAD_BARS"]
