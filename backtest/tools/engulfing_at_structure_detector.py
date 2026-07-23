"""engulfing_at_structure_detector.py -- the causal ENGULFING-AT-STRUCTURE-TRIGGER detector.

WHY THIS EXISTS (root cause, not vibes -- see automation/overnight/queue.md
ENGULFING-AT-STRUCTURE-TRIGGER for the full trail): J called an engulfing candle
reacting at a fresh intraday double-top/double-bottom shelf live on two mirror-symmetric
days (2026-07-21 bullish, 2026-07-23 bearish); the engine had zero trigger both times.
A first attempt (backtest/lib/patterns/registry.py::engulfing_at_swing_shelf, commit
31c5089e) composed the existing `engulfing` predicate with the existing
`flat_side(kind=..., n_touches=2)` primitive over `crypto.lib.market_structure`'s
labeled_swings -- and was PROVEN (via backtest/tools/pattern_anchor_verify.py, both
anchors declared expected_fire=False in that registry entry) to NOT fire on either
exhibit. Root cause, pinned directly against the real cached bars (not asserted):
labeled_swings' pivot confirmation requires `window` (2) bars on BOTH sides of a
candidate pivot before it counts as a confirmed swing -- but in both exhibits the
SECOND touch of the shelf IS the reaction/engulfing bar itself (bar t), which by
definition has zero bars after it at evaluation time. A swing-pivot primitive can
never confirm its own trigger bar as a touch in time to fire on it; every rule
composed on `flat_side`/`labeled_swings` inherits that same blind spot structurally,
not as a tuning miss.

THE NEW PRIMITIVE this module ships (`find_shelf_touch`) is deliberately NOT a
2-sided-fractal pivot detector. It is a ONE-SIDED rolling local-extreme check
(`is_rolling_extreme`): bar i's low/high only needs to be the min/max of itself and a
short window of PRECEDING bars (no future bars required), so a touch can be confirmed
using ONLY bars <= t -- including t itself as the second touch. This is the "rolling
K-bar local-extreme-cluster, no formal reversal-pivot confirmation lag" primitive named
as the required next step in queue.md's own falsification writeup.

VERIFIED AGAINST REAL CACHED BARS (backtest/data/spy_5m_2026-05-19_2026-07-23.csv)
before this module's grid was frozen -- see
analysis/recommendations/engulfing-at-structure-prereg-2026-07-23.json for the disclosed
arithmetic:
  2026-07-23 10:40 (bearish): shelf touch = 10:35's high (740.51), reaction = 10:40's own
    high (740.64), touch_spread=$0.13, 1 bar apart. Needs zone_band >= $0.15 to admit.
  2026-07-21 11:05 (bullish): NEAREST shelf touch = 11:00's low (745.83), reaction =
    11:05's own low (745.85), touch_spread=$0.02, 1 bar apart -- admits at every grid
    band. A second, farther qualifying touch also exists at 10:40's low (745.77),
    touch_spread=$0.08, 5 bars apart (this is the pair J's own live read cited).

C6 CONTRACT: every function here reads index <= t only (direct array access at t/t-1, or
a backward-only window `[t-side_window, t]`). `find_shelf_touch`'s search loop walks
STRICTLY BACKWARD from `t - min_bars_apart` and never touches an index > t.
backtest/tests/test_engulfing_at_structure.py::test_causal_c6_* is the enforcement
harness (mutates bars strictly after t, asserts the result at t is unchanged).

NO WIRING: pure research module. Not imported by the live engine, setup_dispatch, or any
watcher. Consumed by backtest/tools/edge_matrix_engulfing_at_structure.py (the real-fills
replay runner) and its own guard tests only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

# ── structural constants (disclosed, NOT tuned grid knobs) ────────────────────────────
EXTREME_SIDE_WINDOW = 2
# Backward-only local-extreme window width. Matches crypto.lib.market_structure.
# DEFAULT_WINDOW's fractal width (2 bars/side) in MAGNITUDE only -- applied here as a
# ONE-SIDED (backward) check, which is the structural change that lets a same-bar
# reaction (t itself) qualify as a touch. Not swept in the grid: this module's whole
# point is that the shelf-touch definition should NOT need a tunable confirmation lag;
# widening/narrowing this window is a second-order refinement, out of scope for the
# falsification this build was commissioned to run.

SHELF_LOOKBACK_BARS = 12
# ~60 minutes on 5m bars. Generous vs both exhibits (max observed bars_apart = 5); a
# structural cap so the search never walks arbitrarily far back, not a tuned knob.

DIRECTIONS: tuple[str, ...] = ("bullish", "bearish")


@dataclass(frozen=True)
class Cell:
    """One pre-registered grid cell. `zone_band`/`body_floor`/`min_bars_apart` are the
    3 tuned numeric knobs; direction is NOT a 4th grid axis -- it is structurally
    matched by construction (bearish engulfing only ever pairs with a HIGH shelf -> put;
    bullish only with a LOW shelf -> call), evaluated together every cell."""
    zone_band: float
    body_floor: float
    min_bars_apart: int

    def cell_id(self) -> str:
        return f"band{self.zone_band:.2f}|body{self.body_floor:.2f}|nbar{self.min_bars_apart}"

    def to_dict(self) -> dict:
        return {"zone_band_dollars": self.zone_band, "body_floor_pct": self.body_floor,
                "min_bars_apart": self.min_bars_apart}


def build_grid(axes: dict) -> list[Cell]:
    return [
        Cell(zone_band=float(b), body_floor=float(f), min_bars_apart=int(n))
        for b in axes["zone_band_dollars"]
        for f in axes["body_floor_pct"]
        for n in axes["min_bars_apart"]
    ]


# ── the new primitive ──────────────────────────────────────────────────────────────────

def is_rolling_extreme(values: np.ndarray, i: int, *, kind: str,
                        side_window: int = EXTREME_SIDE_WINDOW) -> bool:
    """True iff values[i] is the min (kind="low") / max (kind="high") of
    values[max(0, i-side_window) : i+1] -- backward-only, no future bars. C6-safe: only
    ever reads indices <= i."""
    if kind not in ("low", "high"):
        raise ValueError(f"kind must be 'low' or 'high', got {kind!r}")
    lo = max(0, i - side_window)
    window = values[lo:i + 1]
    if kind == "low":
        return bool(values[i] <= window.min())
    return bool(values[i] >= window.max())


def find_shelf_touch(
    lows: np.ndarray, highs: np.ndarray, t: int, *, kind: str,
    zone_band: float, min_bars_apart: int,
    lookback_bars: int = SHELF_LOOKBACK_BARS, side_window: int = EXTREME_SIDE_WINDOW,
) -> Optional[dict]:
    """Is bar t reacting AT a recent rolling-extreme shelf? kind="high" for a double-top
    shelf (bearish reaction), kind="low" for a double-bottom shelf (bullish reaction).
    Bar t's OWN extreme is the second touch -- it does NOT need to independently pass
    is_rolling_extreme itself (requiring that would reject genuine retests where the
    reaction bar's wick sits a few cents inside the prior extreme -- exactly the
    2026-07-21 11:05 exhibit, where 11:00's low sits 2c BELOW 11:05's own low). Searches
    STRICTLY BACKWARD from `t - min_bars_apart`, returns the NEAREST qualifying touch
    (or None). C6-safe: never reads an index > t.
    """
    if kind not in ("low", "high"):
        raise ValueError(f"kind must be 'low' or 'high', got {kind!r}")
    src = lows if kind == "low" else highs
    extreme_t = float(src[t])
    lo_search = max(0, t - lookback_bars)
    hi_search = t - min_bars_apart
    for i in range(hi_search, lo_search - 1, -1):
        if i < 0:
            break
        if not is_rolling_extreme(src, i, kind=kind, side_window=side_window):
            continue
        extreme_i = float(src[i])
        if abs(extreme_i - extreme_t) > zone_band:
            continue
        return {
            "shelf_bar_offset": t - i,
            "shelf_price": round(extreme_i, 4),
            "touch_price": round(extreme_t, 4),
            "touch_spread": round(abs(extreme_i - extreme_t), 4),
            "trigger_level": round((extreme_i + extreme_t) / 2.0, 2),
        }
    return None


# ── engulfing geometry (standard OHLC; same math as backtest/lib/patterns/predicates.py
#    ::engulfing, re-expressed on raw open/close arrays -- see module docstring for why
#    this is kept local rather than imported) ────────────────────────────────────────

def is_engulfing(opens: np.ndarray, closes: np.ndarray, t: int, *, direction: str) -> bool:
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
    if t < 1:
        return False
    cur_o, cur_c = float(opens[t]), float(closes[t])
    prev_o, prev_c = float(opens[t - 1]), float(closes[t - 1])
    cur_hi, cur_lo = max(cur_o, cur_c), min(cur_o, cur_c)
    prev_hi, prev_lo = max(prev_o, prev_c), min(prev_o, prev_c)
    if not (cur_hi >= prev_hi and cur_lo <= prev_lo):
        return False
    cur_green, prev_green = cur_c > cur_o, prev_c > prev_o
    if direction == "bullish":
        return cur_green and not prev_green
    return (not cur_green) and prev_green


def body_pct(highs: np.ndarray, lows: np.ndarray, opens: np.ndarray, closes: np.ndarray,
             t: int) -> float:
    rng = float(highs[t] - lows[t])
    if rng <= 0:
        return 0.0
    return abs(float(closes[t] - opens[t])) / rng


# ── composite trigger ───────────────────────────────────────────────────────────────────

def detect_bar(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    t: int, cell: Cell,
) -> Optional[dict]:
    """TRIGGER = engulfing(direction) AND body_pct(t) >= cell.body_floor AND a
    matching-direction shelf touch within cell.zone_band / cell.min_bars_apart.
    Bearish-eng-at-swing-high -> put; bullish-eng-at-swing-low -> call (direction-matched
    by construction, not an independent grid axis). A bar can fire at most one direction
    (engulfing geometry is mutually exclusive: cur_green XOR not-cur_green)."""
    if t < 1:
        return None
    bp = body_pct(highs, lows, opens, closes, t)
    if bp < cell.body_floor:
        return None
    if is_engulfing(opens, closes, t, direction="bearish"):
        shelf = find_shelf_touch(lows, highs, t, kind="high", zone_band=cell.zone_band,
                                  min_bars_apart=cell.min_bars_apart)
        if shelf is not None:
            return {"bias": "bearish", "body_pct": round(bp, 4), **shelf}
        return None
    if is_engulfing(opens, closes, t, direction="bullish"):
        shelf = find_shelf_touch(lows, highs, t, kind="low", zone_band=cell.zone_band,
                                  min_bars_apart=cell.min_bars_apart)
        if shelf is not None:
            return {"bias": "bullish", "body_pct": round(bp, 4), **shelf}
        return None
    return None


def detect_cell_day(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    gidxs: np.ndarray, cell: Cell,
) -> list[dict]:
    """One day, one cell (day-local arrays; gidxs maps local index -> global row index).
    Mirrors edge_matrix_bear_level_rejection.py::detect_cell_day's per-day convention."""
    out: list[dict] = []
    n = len(gidxs)
    for i in range(1, n):
        hit = detect_bar(opens, highs, lows, closes, i, cell)
        if hit is not None:
            out.append({"local_i": i, "gidx": int(gidxs[i]), **hit})
    return out
