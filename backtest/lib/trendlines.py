"""Auto-trendline detection — finds ascending and descending trendlines in OHLCV bars.

Algorithm
---------
1. Identify swing highs and swing lows via `scipy.signal.find_peaks` with prominence
   and minimum-distance constraints.
2. For every pair of swing-highs, fit a candidate descending trendline. For every
   pair of swing-lows, fit a candidate ascending trendline.
3. Score each candidate by counting how many *other* swing points sit within
   `tolerance_usd` of the line. A candidate is kept iff `touch_count >= min_touches`
   (default 3 — the standard "trendline needs three points" rule).
4. Deduplicate near-identical lines (same direction, similar slope, similar intercept
   at the midpoint of the bar range).

Why this design
---------------
- Pure pandas + scipy + numpy. No external API dependency. Runs the same way
  in backtest and at runtime in the premarket task.
- `find_peaks` (not local-max windowing) lets us tune sensitivity via prominence,
  which matters: SPY at $735 wiggles ±$0.30 constantly, but a $0.15 prominence
  threshold weeds out micro-swings.
- All-pairs candidate generation is O(N^2) on swing points. With 2-3 sessions of
  5m bars (~150 bars) yielding ~20-30 swings, that's ~600 candidates — fast enough
  to run in premarket.

Touch tolerance
---------------
$0.20 default. For SPY 0DTE at ~$735 that's 0.027% — tight enough to mean
"the bar actually tagged the line" rather than "happened to be in the
neighborhood." Tunable per-call.

Caveats
-------
- This detector runs on bar HIGHS and LOWS. Wicks count. If you want body-only
  trendlines, pre-process bars to set high=max(open,close) and low=min(open,close)
  before passing in.
- Detected lines DO NOT include manually-drawn trendlines from the TradingView
  chart. Those come from `read_chart_drawings.js` via the runtime path. The
  premarket script merges both sources before writing `trendlines.json`.
- The detector intentionally does not promote lines to entry triggers. Operating
  principle 6 (no doctrine without backtest evidence) requires a separate
  backtest before the heartbeat scores trendline breaks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

TOUCH_TOLERANCE_USD: float = 0.20
MIN_PROMINENCE_USD: float = 0.15
MIN_DISTANCE_BARS: int = 3
MIN_TOUCHES: int = 3
MIN_SLOPE_USD_PER_HOUR: float = 0.05  # below this, the "line" is really a horizontal level


@dataclass(frozen=True)
class Trendline:
    """A trendline fit through swing points.

    `price_at(ts)` projects the line to any unix timestamp.
    """

    direction: Literal["ascending", "descending"]
    slope_per_sec: float
    intercept_price: float
    intercept_timestamp: int
    anchor_points: tuple[tuple[int, float], ...] = field(default_factory=tuple)
    touch_count: int = 0
    last_touched_at: int = 0
    r_squared: float = 0.0

    def price_at(self, ts_unix: int | float) -> float:
        return float(
            self.intercept_price
            + self.slope_per_sec * (float(ts_unix) - self.intercept_timestamp)
        )

    def slope_per_hour(self) -> float:
        return self.slope_per_sec * 3600.0

    def to_dict(self) -> dict:
        return {
            "direction": self.direction,
            "slope_per_sec": self.slope_per_sec,
            "slope_per_hour_dollars": self.slope_per_hour(),
            "intercept_price": self.intercept_price,
            "intercept_timestamp": self.intercept_timestamp,
            "anchor_points": [{"time": int(t), "price": float(p)} for t, p in self.anchor_points],
            "touch_count": self.touch_count,
            "last_touched_at": self.last_touched_at,
            "r_squared": self.r_squared,
        }


def _find_swing_indices(
    prices: np.ndarray,
    kind: Literal["high", "low"],
    prominence: float,
    distance: int,
) -> np.ndarray:
    series = prices if kind == "high" else -prices
    peaks, _ = find_peaks(series, prominence=prominence, distance=distance)
    return peaks


def _fit_line(t1: float, p1: float, t2: float, p2: float) -> tuple[float, float]:
    """Returns (slope_per_sec, intercept_at_t1)."""
    if t2 == t1:
        return 0.0, p1
    slope = (p2 - p1) / (t2 - t1)
    return slope, p1


def _r_squared(slope: float, t0: float, p0: float, ts: np.ndarray, ps: np.ndarray) -> float:
    if len(ts) < 2:
        return 0.0
    predicted = p0 + slope * (ts - t0)
    ss_res = float(np.sum((ps - predicted) ** 2))
    ss_tot = float(np.sum((ps - ps.mean()) ** 2))
    if ss_tot == 0:
        return 1.0 if ss_res == 0 else 0.0
    return max(0.0, 1.0 - ss_res / ss_tot)


def _candidate_from_pair(
    swing_idx_a: int,
    swing_idx_b: int,
    timestamps: np.ndarray,
    prices: np.ndarray,
    direction: Literal["ascending", "descending"],
    tolerance_usd: float,
    min_touches: int,
    swing_indices: np.ndarray,
) -> Trendline | None:
    t1, t2 = float(timestamps[swing_idx_a]), float(timestamps[swing_idx_b])
    p1, p2 = float(prices[swing_idx_a]), float(prices[swing_idx_b])
    slope, p0 = _fit_line(t1, p1, t2, p2)

    slope_per_hour = abs(slope) * 3600.0
    if slope_per_hour < MIN_SLOPE_USD_PER_HOUR:
        return None
    if direction == "ascending" and slope <= 0:
        return None
    if direction == "descending" and slope >= 0:
        return None

    swing_ts = timestamps[swing_indices].astype(float)
    swing_ps = prices[swing_indices].astype(float)
    line_ps = p0 + slope * (swing_ts - t1)
    diffs = np.abs(swing_ps - line_ps)
    touch_mask = diffs <= tolerance_usd
    touch_count = int(touch_mask.sum())
    if touch_count < min_touches:
        return None

    touched_ts = swing_ts[touch_mask].astype(int)
    touched_ps = swing_ps[touch_mask]
    last_touched = int(touched_ts.max())
    anchors = tuple((int(t), float(p)) for t, p in zip(touched_ts, touched_ps))
    r2 = _r_squared(slope, t1, p1, touched_ts.astype(float), touched_ps)

    return Trendline(
        direction=direction,
        slope_per_sec=slope,
        intercept_price=p1,
        intercept_timestamp=int(t1),
        anchor_points=anchors,
        touch_count=touch_count,
        last_touched_at=last_touched,
        r_squared=r2,
    )


def _dedupe(
    candidates: list[Trendline],
    timestamps: np.ndarray,
    tolerance_usd: float,
) -> list[Trendline]:
    if not candidates:
        return []
    candidates = sorted(
        candidates,
        key=lambda c: (c.touch_count, c.r_squared, c.last_touched_at),
        reverse=True,
    )
    mid_t = int((float(timestamps[0]) + float(timestamps[-1])) / 2)
    deduped: list[Trendline] = []
    for c in candidates:
        cp = c.price_at(mid_t)
        is_dup = False
        for d in deduped:
            if d.direction != c.direction:
                continue
            if abs(cp - d.price_at(mid_t)) <= tolerance_usd * 2:
                is_dup = True
                break
        if not is_dup:
            deduped.append(c)
    return deduped


def detect_trendlines(
    bars: pd.DataFrame,
    min_touches: int = MIN_TOUCHES,
    tolerance_usd: float = TOUCH_TOLERANCE_USD,
    prominence_usd: float = MIN_PROMINENCE_USD,
    distance_bars: int = MIN_DISTANCE_BARS,
    timestamp_col: str = "timestamp_unix",
    high_col: str = "high",
    low_col: str = "low",
) -> list[Trendline]:
    """Detect ascending and descending trendlines in a bar history.

    Args:
        bars: DataFrame with `timestamp_col` (unix seconds), `high_col`, `low_col`.
        min_touches: minimum number of swing-point touches required.
        tolerance_usd: max distance from line for a swing point to count as a touch.
        prominence_usd: minimum prominence for a bar to be considered a swing point.
        distance_bars: minimum bar separation between swing points.

    Returns:
        Deduplicated, score-sorted list of Trendline objects (highest touch_count first).
    """
    if len(bars) < 5:
        return []

    timestamps = bars[timestamp_col].astype(np.int64).to_numpy()
    highs = bars[high_col].astype(float).to_numpy()
    lows = bars[low_col].astype(float).to_numpy()

    high_swings = _find_swing_indices(highs, "high", prominence_usd, distance_bars)
    low_swings = _find_swing_indices(lows, "low", prominence_usd, distance_bars)

    candidates: list[Trendline] = []

    for i in range(len(high_swings)):
        for j in range(i + 1, len(high_swings)):
            line = _candidate_from_pair(
                high_swings[i], high_swings[j],
                timestamps, highs, "descending",
                tolerance_usd, min_touches, high_swings,
            )
            if line is not None:
                candidates.append(line)

    for i in range(len(low_swings)):
        for j in range(i + 1, len(low_swings)):
            line = _candidate_from_pair(
                low_swings[i], low_swings[j],
                timestamps, lows, "ascending",
                tolerance_usd, min_touches, low_swings,
            )
            if line is not None:
                candidates.append(line)

    return _dedupe(candidates, timestamps, tolerance_usd)


def trendline_from_two_points(
    t1: int, p1: float, t2: int, p2: float, label: str = "manual",
) -> Trendline:
    """Construct a Trendline from two raw points (e.g. a J-drawn line from chart_drawings.json)."""
    slope, _ = _fit_line(float(t1), p1, float(t2), p2)
    direction: Literal["ascending", "descending"] = "ascending" if slope >= 0 else "descending"
    return Trendline(
        direction=direction,
        slope_per_sec=slope,
        intercept_price=p1,
        intercept_timestamp=int(t1),
        anchor_points=((int(t1), float(p1)), (int(t2), float(p2))),
        touch_count=2,
        last_touched_at=int(max(t1, t2)),
        r_squared=1.0,
    )
