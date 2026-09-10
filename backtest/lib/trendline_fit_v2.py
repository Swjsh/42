"""trendline_fit_v2 -- pivot-anchored trendline fitter encoding canon rules 1-7,
SHADOW ONLY (work order: markdown/0dte/KEY-LEVELS-CHART-READING-HANDOFF.md #9.5 row C).

Built 2026-09-09. `backtest/autoresearch/trendline_engine.py` (v1) is UNTOUCHED --
this is a new, separate module. Nothing in this file gates a trade; the
`filters.py::detect_trendline_rejection_bearish` live trigger is frozen until
2026-10-30 per the work order boundaries.

WHY V1 IS WRONG (verified defects the handoff names, each fixed here):
  1. v1 scores "touches" against every RAW BAR within max($0.10, 0.15%*price) of
     the line, with PIVOT_K=1 (nearly every bar is a pivot) -- touch counts are
     inflated by construction. FIX: touches are scored against PIVOTS ONLY (rule 1),
     tolerance is an ATR fraction, not a % of price (rule 2).
  2. v1 penalizes a close-through by -5 in score but never disqualifies it. FIX:
     zero closes through the line between the first anchor and the query bar is a
     HARD, disqualifying constraint (rule 3) -- not a score term.
  3. v1 (`fetch_spy_5m`) and `compute_trendlines.py` both drop premarket bars, so
     an 08:30 ET anchor structurally cannot exist. FIX: bars are loaded 04:00-16:00
     ET (rule 5); the RTH-only convention is preserved only for break/status
     logic per rule 8 (this module does not change break semantics, see below).
  4. v1's `_fit` requires SUPPORT to strictly ascend (`p2 <= p1: continue`), so a
     descending support (the lower rail of a falling wedge/channel) cannot be
     produced. FIX: no directional constraint on either kind (rule 6) -- support
     may descend, resistance may ascend.

CANON RULES ENCODED (handoff #9.4, cited there against
`markdown/research/TRENDLINE-BREAK-LITERATURE-2026-07-14.md` Part 2 and
`markdown/research/INTRADAY-LEVELS-CANON.md`):
  1. Pivots first -- ATR-scaled-prominence zigzag/fractal extrema; lines are fit
     through PIVOTS ONLY, never scored against raw bars.
  2. Touch tolerance = an ATR fraction (~0.15-0.25 x 5m ATR), not a % of price.
     Every line carries its `touch_ledger` (actual bar timestamps counted).
  3. Hard constraint: ZERO closes through the line from the first anchor to the
     query bar. A wick beyond tolerance is fine; a CLOSE beyond tolerance
     disqualifies the candidate outright.
  4. 2 pivots = DRAFT, a 3rd (or later) touch = CONFIRMED. Only CONFIRMED lines
     are meant to be drawn (this module still returns DRAFT candidates when asked
     -- see `require_confirmed` -- because the validation harness needs to see
     near-misses, but `detect_trendlines_v2`'s default is CONFIRMED-only).
  5. Bars span 04:00-16:00 ET (premarket included) for pivot/anchor detection.
     Break/status logic is unchanged from the RTH-only convention (rule 8).
  6. Support may descend, resistance may ascend (channels/wedges exist). No
     directional constraint is imposed on either kind's slope.
  7. Wick-vs-body: a line's pivots are ALL wick XOR ALL body, never mixed --
     structural (the pivot search runs against one bar view per family), same
     technique as v1 and `backtest/lib/trendline_detector.py`.
  8. Break = a body CLOSE beyond the line (+ tolerance buffer). This module
     computes `break_state` (intact/testing/broken) with the same formula
     `backtest/lib/trendline_detector.py::_build_line_state` already uses (which
     itself documents mirroring v1's INTACT/TESTING/BROKEN convention) -- NOTE:
     `backtest/lib/trendlines.py` (the file the work order names for this reuse)
     has no status/break field at all; `trendline_detector.py` is the actual
     existing home of this logic in `backtest/lib/`, so that is what is reused
     here. Flagged so the discrepancy is visible rather than silently papered
     over.

NOT encoded here (out of scope for this module, per the work order):
  - Rule 9 (levels-as-zones merge width) -- that is level-set logic, not
    trendline logic; belongs to WS-E.
  - Rule 10 (indicator minimalism) -- an Opus/J layout decision (WS-F.5).

DESIGN
  Pure functions over an immutable `BarV2` tuple, oldest first. No I/O in the
  detection path; loading (`load_bars_multi_source`) is the one place this
  module touches disk, and it only ever READS already-fetched CSV/JSON caches
  under backtest/data/ -- it does not call Alpaca/yfinance itself (task
  boundary: "do not build a second data reader").

PUBLIC API
  BarV2, PivotV2, TouchV2, ChannelRailV2, TrendlineV2
  compute_atr(bars, period, end_index) -> float
  atr_zone_width_study(bars, fractions, period) -> dict   (WS-F(3) input)
  generate_all_candidates(bars, pivots, kind, tolerance_dollars, ...) -> list[_Candidate]
      (the FULL valid-candidate universe -- used by the validation harness so it
      can check reproduction against every geometrically valid line, not just the
      few that would win the draw-eligibility contest)
  detect_trendlines_v2(bars, ...) -> tuple[TrendlineV2, ...]
      (the production/shadow-facing API -- CONFIRMED-only, top-N per kind/family)
  load_bars_multi_source(dates) -> list[BarV2]
  make_line_id(...)
"""
from __future__ import annotations

import glob
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional, Sequence

import numpy as np
from scipy.signal import find_peaks

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "backtest" / "data"
SIP_CACHE_DIR = DATA_DIR / "spy_sip_cache"

SETUP_SCRIPTS = REPO / "setup" / "scripts"
if str(SETUP_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SETUP_SCRIPTS))
from et_clock import et_offset_hours  # noqa: E402 -- the ONE DST-aware ET source on this rig

__all__ = [
    "DETECTOR_VERSION",
    "BarV2", "PivotV2", "TouchV2", "ChannelRailV2", "TrendlineV2",
    "compute_atr", "atr_zone_width_study",
    "generate_all_candidates", "detect_trendlines_v2",
    "load_bars_multi_source", "make_line_id",
]

DETECTOR_VERSION = "2.0.0"

# --------------------------------------------------------------------------- #
# Defaults. Each is cited to a precedent already in this repo, or explicitly
# flagged as a new design choice this module introduces (not canon-cited).
# --------------------------------------------------------------------------- #
ATR_PERIOD = 14                        # Wilder's standard ATR window -- textbook default,
                                        # not hand-tuned for this problem.
PIVOT_WINDOW = 2                       # matches backtest/lib/trendline_detector.py's
                                        # DEFAULT_PIVOT_WINDOW (cites crypto/lib/market_structure
                                        # .DEFAULT_WINDOW=2, the calibrated SPY-5m default).
PROMINENCE_ATR_FRACTION = 0.5          # NEW design choice (not canon-cited): a pivot must stand
                                        # out from its neighborhood by >= 0.5x ATR to count as a
                                        # swing at all. This is what actually fixes v1's
                                        # "PIVOT_K=1 makes nearly every bar a pivot" defect --
                                        # unverified/untuned, flagged for Opus review (WS-F.3
                                        # covers the TOUCH tolerance constant; this prominence
                                        # constant is a sibling knob this module also needs and
                                        # the work order does not separately name).
MIN_DISTANCE_BARS = 3                  # minimum bar spacing between two pivots of the same kind
                                        # (scipy find_peaks `distance`) -- matches v1's MIN_SPAN
                                        # order of magnitude.
MIN_SPAN_BARS = 6                      # anchor pair must span >= this many bars -- matches
                                        # trendline_detector.py's DEFAULT_MIN_SPAN_BARS (cites the
                                        # Tori-method "6+ candles between taps" convergence).
MIN_BARS_BETWEEN_TOUCHES = 6           # matches trendline_detector.py's
                                        # DEFAULT_MIN_BARS_BETWEEN_TOUCHES (Tori method).
DEFAULT_TOLERANCE_ATR_FRACTION = 0.20  # midpoint of the handoff's cited 0.15-0.25x range;
                                        # `atr_zone_width_study` reports the full distribution
                                        # for all three so Opus can pick from data (WS-F.3).
TOLERANCE_ATR_FRACTIONS_STUDIED = (0.15, 0.20, 0.25)

# Wick-vs-body anchor family (J's rule, ported verbatim from
# backtest/autoresearch/trendline_engine.py -- same threshold, same rationale: a bar whose
# wick is a rounding artifact, not a real rejection, must not qualify as a WICK pivot).
WICK_MIN_FRACTION = 0.10
WICK_MIN_CENTS = 0.05


# --------------------------------------------------------------------------- #
# Bar / pivot / line value types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class BarV2:
    ts_unix: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True, slots=True)
class PivotV2:
    bar_index: int
    ts_unix: int
    price: float
    kind: Literal["swing_high", "swing_low"]
    family: Literal["wick", "body"]


@dataclass(frozen=True, slots=True)
class TouchV2:
    bar_index: int
    ts_unix: int
    et: str
    price: float

    def to_dict(self) -> dict:
        return {"bar_index": self.bar_index, "ts_unix": self.ts_unix, "et": self.et,
                "price": round(self.price, 4)}


@dataclass(frozen=True, slots=True)
class ChannelRailV2:
    """The parallel opposite rail (rule 6): same slope as the parent line, offset
    through the single most-extreme opposite-kind pivot in [parent.i1, query_idx].
    Never an independent fit."""
    kind: Literal["support", "resistance"]
    anchor_bar_index: int
    anchor_ts_unix: int
    anchor_et: str
    anchor_price: float
    slope_per_bar: float
    current_value: float

    def to_dict(self) -> dict:
        return {"kind": self.kind, "anchor_bar_index": self.anchor_bar_index,
                "anchor_ts_unix": self.anchor_ts_unix, "anchor_et": self.anchor_et,
                "anchor_price": round(self.anchor_price, 4),
                "slope_per_bar": round(self.slope_per_bar, 5),
                "current_value": round(self.current_value, 4)}


@dataclass(frozen=True, slots=True)
class TrendlineV2:
    line_id: str
    kind: Literal["support", "resistance"]
    anchor_family: Literal["wick", "body"]
    direction: Literal["rising", "falling", "flat"]
    anchors: tuple[TouchV2, TouchV2]
    slope_per_bar: float
    slope_per_hour: float
    touch_ledger: tuple[TouchV2, ...]      # ALL touches incl. anchors, chronological
    n_touches: int
    status: Literal["DRAFT", "CONFIRMED"]  # rule 4
    break_state: Literal["intact", "testing", "broken"]  # rule 8
    current_value: float
    query_ts_unix: int
    tolerance_dollars: float
    tolerance_atr_fraction: float
    atr_dollars: float
    channel_rail: Optional[ChannelRailV2] = None

    def to_dict(self) -> dict:
        return {
            "line_id": self.line_id, "kind": self.kind, "anchor_family": self.anchor_family,
            "direction": self.direction,
            "anchors": [a.to_dict() for a in self.anchors],
            "slope_per_bar": round(self.slope_per_bar, 5),
            "slope_per_hour": round(self.slope_per_hour, 4),
            "touch_ledger": [t.to_dict() for t in self.touch_ledger],
            "n_touches": self.n_touches, "status": self.status, "break_state": self.break_state,
            "current_value": round(self.current_value, 4), "query_ts_unix": self.query_ts_unix,
            "tolerance_dollars": round(self.tolerance_dollars, 4),
            "tolerance_atr_fraction": self.tolerance_atr_fraction,
            "atr_dollars": round(self.atr_dollars, 4),
            "channel_rail": self.channel_rail.to_dict() if self.channel_rail else None,
        }


def make_line_id(symbol: str, timeframe: str, kind: str, family: str, first_anchor_ts: int) -> str:
    dir_tag = "SUP" if kind == "support" else "RES"
    fam_tag = "W" if family == "wick" else "B"
    return f"TL2-{symbol}-{timeframe}-{dir_tag}-{fam_tag}-{int(first_anchor_ts)}"


# --------------------------------------------------------------------------- #
# ET time helpers -- et_clock.et_offset_hours is the ONE DST-aware ET source.
# --------------------------------------------------------------------------- #
def _et_str(ts_unix: int) -> str:
    dt_utc = datetime.fromtimestamp(ts_unix, tz=timezone.utc)
    off = et_offset_hours(dt_utc)
    et_dt = dt_utc + timedelta(hours=off)
    return et_dt.strftime("%Y-%m-%d %H:%M")


def _et_naive_to_unix(dt_naive_et: datetime) -> int:
    """Convert a NAIVE Eastern-time datetime (e.g. from the SIP cache's 't' field,
    which carries no offset) to a unix timestamp, DST-aware. Two-pass: guess EDT
    (-4h), check which regime that UTC instant actually falls in via
    et_offset_hours, and correct once if the guess was wrong (mirrors et_clock's
    own stated tolerance -- DST regime is a date-level fact, not an hour-level
    one, so one correction pass always converges)."""
    guess_utc = dt_naive_et.replace(tzinfo=timezone.utc) + timedelta(hours=4)
    off = et_offset_hours(guess_utc)
    utc_dt = dt_naive_et.replace(tzinfo=timezone.utc) - timedelta(hours=off)
    off2 = et_offset_hours(utc_dt)
    if off2 != off:
        utc_dt = dt_naive_et.replace(tzinfo=timezone.utc) - timedelta(hours=off2)
    return int(utc_dt.timestamp())


# --------------------------------------------------------------------------- #
# ATR
# --------------------------------------------------------------------------- #
def compute_atr(bars: Sequence[BarV2], period: int = ATR_PERIOD, end_index: Optional[int] = None) -> float:
    """Simple (non-Wilder-smoothed) mean True Range over the trailing `period`
    bars ending at `end_index` (inclusive). No look-ahead: never reads past
    `end_index`."""
    end_index = len(bars) - 1 if end_index is None else end_index
    start = max(1, end_index - period + 1)
    trs = []
    for i in range(start, end_index + 1):
        h, l, pc = bars[i].high, bars[i].low, bars[i - 1].close
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        b = bars[end_index]
        return max(b.high - b.low, 0.01)
    return sum(trs) / len(trs)


def atr_zone_width_study(
    bars: Sequence[BarV2],
    fractions: tuple[float, ...] = TOLERANCE_ATR_FRACTIONS_STUDIED,
    period: int = ATR_PERIOD,
    sample_stride: int = 1,
) -> dict:
    """WS-F(3) input: the distribution of (fraction x 5m ATR) in dollars AND as a
    % of price, sampled across every bar (or every `sample_stride`'th bar) in the
    given series. Lets Opus pick the touch-tolerance constant from data rather
    than by assertion, per the work order."""
    per_fraction: dict[float, dict[str, list[float]]] = {f: {"dollars": [], "pct": []} for f in fractions}
    for i in range(period, len(bars), sample_stride):
        atr = compute_atr(bars, period=period, end_index=i)
        price = bars[i].close
        for f in fractions:
            width = f * atr
            per_fraction[f]["dollars"].append(width)
            if price:
                per_fraction[f]["pct"].append(100.0 * width / price)

    def _pctile(sorted_arr: list[float], q: float) -> float:
        if not sorted_arr:
            return 0.0
        idx = min(len(sorted_arr) - 1, int(q * len(sorted_arr)))
        return sorted_arr[idx]

    summary = {}
    for f in fractions:
        d = per_fraction[f]["dollars"]
        p = per_fraction[f]["pct"]
        if not d:
            continue
        d_sorted, p_sorted = sorted(d), sorted(p)
        summary[str(f)] = {
            "n": len(d),
            "mean_dollars": round(sum(d) / len(d), 4),
            "median_dollars": round(_pctile(d_sorted, 0.5), 4),
            "p10_dollars": round(_pctile(d_sorted, 0.10), 4),
            "p90_dollars": round(_pctile(d_sorted, 0.90), 4),
            "mean_pct": round(sum(p) / len(p), 5) if p else None,
            "median_pct": round(_pctile(p_sorted, 0.5), 5) if p_sorted else None,
        }
    return summary


# --------------------------------------------------------------------------- #
# Wick-vs-body family (rule 7) -- ported verbatim from trendline_engine.py
# --------------------------------------------------------------------------- #
def _body_extreme(bar: BarV2, kind: str) -> float:
    return min(bar.open, bar.close) if kind == "support" else max(bar.open, bar.close)


def _wick_len(bar: BarV2, kind: str) -> float:
    return (min(bar.open, bar.close) - bar.low) if kind == "support" else (bar.high - max(bar.open, bar.close))


def _has_protruding_wick(bar: BarV2, kind: str) -> bool:
    rng = bar.high - bar.low
    if rng <= 0:
        return False
    return _wick_len(bar, kind) >= max(WICK_MIN_CENTS, WICK_MIN_FRACTION * rng)


# --------------------------------------------------------------------------- #
# Pivots (rule 1: ATR-scaled prominence, pivots not raw bars)
# --------------------------------------------------------------------------- #
def _find_pivots(
    bars: Sequence[BarV2],
    family: Literal["wick", "body"],
    atr_dollars: float,
    prominence_fraction: float = PROMINENCE_ATR_FRACTION,
    distance: int = MIN_DISTANCE_BARS,
) -> list[PivotV2]:
    if family == "wick":
        highs = np.array([b.high for b in bars], dtype=float)
        lows = np.array([b.low for b in bars], dtype=float)
    elif family == "body":
        highs = np.array([max(b.open, b.close) for b in bars], dtype=float)
        lows = np.array([min(b.open, b.close) for b in bars], dtype=float)
    else:
        raise ValueError(f"family must be 'wick' or 'body', got {family!r}")

    prominence = max(prominence_fraction * atr_dollars, 0.01)
    hi_idx, _ = find_peaks(highs, prominence=prominence, distance=distance)
    lo_idx, _ = find_peaks(-lows, prominence=prominence, distance=distance)

    pivots: list[PivotV2] = []
    for i in hi_idx:
        i = int(i)
        if family == "wick" and not _has_protruding_wick(bars[i], "resistance"):
            continue
        pivots.append(PivotV2(i, bars[i].ts_unix, float(highs[i]), "swing_high", family))
    for i in lo_idx:
        i = int(i)
        if family == "wick" and not _has_protruding_wick(bars[i], "support"):
            continue
        pivots.append(PivotV2(i, bars[i].ts_unix, float(lows[i]), "swing_low", family))
    return pivots


# --------------------------------------------------------------------------- #
# Candidate fitting -- rules 1-4, 6
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class _Candidate:
    i1: int
    i2: int
    p1: float
    p2: float
    slope: float                          # $ per bar
    touches: tuple[tuple[int, float], ...]  # (bar_index, price) pairs, sorted, anchors included
    n_touches: int
    status: Literal["DRAFT", "CONFIRMED"]
    score: float


def generate_all_candidates(
    bars: Sequence[BarV2],
    pivots: Sequence[PivotV2],
    kind: Literal["support", "resistance"],
    tolerance_dollars: float,
    min_span_bars: int = MIN_SPAN_BARS,
    min_bars_between_touches: int = MIN_BARS_BETWEEN_TOUCHES,
    query_idx: Optional[int] = None,
) -> list[_Candidate]:
    """The FULL valid-candidate universe: every same-kind pivot pair that clears
    the hard zero-violation constraint (rule 3), with >= 2 touches (DRAFT) or
    >= 3 (CONFIRMED). No directional constraint (rule 6) -- support may descend,
    resistance may ascend. No top-N truncation here; callers that want the
    drawable subset use `detect_trendlines_v2`, which truncates."""
    query_idx = len(bars) - 1 if query_idx is None else query_idx
    want_kind = "swing_high" if kind == "resistance" else "swing_low"
    pool = sorted([p for p in pivots if p.kind == want_kind], key=lambda p: p.bar_index)

    out: list[_Candidate] = []
    for a in range(len(pool)):
        for b in range(a + 1, len(pool)):
            pa, pb = pool[a], pool[b]
            i1, i2 = pa.bar_index, pb.bar_index
            if i2 > query_idx or i2 - i1 < min_span_bars:
                continue
            slope = (pb.price - pa.price) / (i2 - i1)

            # HARD CONSTRAINT (rule 3): zero CLOSES through the line, i1..query_idx.
            violated = False
            for k in range(i1, query_idx + 1):
                proj = pa.price + slope * (k - i1)
                close = bars[k].close
                if kind == "support" and close < proj - tolerance_dollars:
                    violated = True
                    break
                if kind == "resistance" and close > proj + tolerance_dollars:
                    violated = True
                    break
            if violated:
                continue

            # Touches: PIVOTS ONLY (rule 1), spaced (avoid one reaction counting thrice).
            touches: list[tuple[int, float]] = []
            for p in pool:
                if p.bar_index < i1 or p.bar_index > query_idx:
                    continue
                proj = pa.price + slope * (p.bar_index - i1)
                if abs(p.price - proj) > tolerance_dollars:
                    continue
                if touches and (p.bar_index - touches[-1][0]) < min_bars_between_touches:
                    continue
                touches.append((p.bar_index, p.price))
            touch_idx = {t[0] for t in touches}
            if i1 not in touch_idx:
                touches.append((i1, pa.price))
            if i2 not in touch_idx:
                touches.append((i2, pb.price))
            touches.sort(key=lambda t: t[0])
            n = len(touches)
            if n < 2:
                continue
            status: Literal["DRAFT", "CONFIRMED"] = "CONFIRMED" if n >= 3 else "DRAFT"
            score = n + (i2 - i1) * 0.1
            out.append(_Candidate(i1, i2, pa.price, pb.price, slope, tuple(touches), n, status, score))
    return out


def _build_channel_rail(
    bars: Sequence[BarV2], pivots: Sequence[PivotV2], kind: str, i1: int, slope: float, query_idx: int,
) -> Optional[ChannelRailV2]:
    """Rule 6's second rail: parallel to the parent line, through the single
    most-extreme OPPOSITE-kind pivot in [i1, query_idx]. Never an independent fit."""
    if kind == "support":
        opp_kind, opp_role = "swing_high", "resistance"
    else:
        opp_kind, opp_role = "swing_low", "support"
    candidates = [p for p in pivots if p.kind == opp_kind and i1 <= p.bar_index <= query_idx]
    if not candidates:
        return None
    extreme = max(candidates, key=lambda p: p.price) if opp_role == "resistance" \
        else min(candidates, key=lambda p: p.price)
    current_value = extreme.price + slope * (query_idx - extreme.bar_index)
    return ChannelRailV2(opp_role, extreme.bar_index, extreme.ts_unix, _et_str(extreme.ts_unix),
                          extreme.price, slope, current_value)


def _build_trendline_v2(
    c: _Candidate, kind: str, family: str, bars: Sequence[BarV2], pivots: Sequence[PivotV2],
    query_idx: int, tolerance_dollars: float, tolerance_atr_fraction: float, atr_dollars: float,
    symbol: str, timeframe: str,
) -> TrendlineV2:
    touch_ledger = tuple(TouchV2(bi, bars[bi].ts_unix, _et_str(bars[bi].ts_unix), price)
                          for bi, price in c.touches)
    anchors = (touch_ledger[0] if touch_ledger[0].bar_index == c.i1 else
               TouchV2(c.i1, bars[c.i1].ts_unix, _et_str(bars[c.i1].ts_unix), c.p1),
               next((t for t in touch_ledger if t.bar_index == c.i2),
                    TouchV2(c.i2, bars[c.i2].ts_unix, _et_str(bars[c.i2].ts_unix), c.p2)))
    current_value = c.p1 + c.slope * (query_idx - c.i1)
    last_bar = bars[query_idx]
    if kind == "support":
        broken = last_bar.close < current_value - tolerance_dollars
        testing = (not broken) and last_bar.low <= current_value + tolerance_dollars
    else:
        broken = last_bar.close > current_value + tolerance_dollars
        testing = (not broken) and last_bar.high >= current_value - tolerance_dollars
    break_state: Literal["intact", "testing", "broken"] = (
        "broken" if broken else ("testing" if testing else "intact")
    )
    direction: Literal["rising", "falling", "flat"] = (
        "rising" if c.slope > 1e-9 else ("falling" if c.slope < -1e-9 else "flat")
    )
    rail = _build_channel_rail(bars, pivots, kind, c.i1, c.slope, query_idx)
    return TrendlineV2(
        line_id=make_line_id(symbol, timeframe, kind, family, bars[c.i1].ts_unix),
        kind=kind, anchor_family=family, direction=direction, anchors=anchors,
        slope_per_bar=c.slope, slope_per_hour=c.slope * 12.0,
        touch_ledger=touch_ledger, n_touches=c.n_touches, status=c.status, break_state=break_state,
        current_value=current_value, query_ts_unix=bars[query_idx].ts_unix,
        tolerance_dollars=tolerance_dollars, tolerance_atr_fraction=tolerance_atr_fraction,
        atr_dollars=atr_dollars, channel_rail=rail,
    )


def detect_trendlines_v2(
    bars: Sequence[BarV2],
    *,
    families: tuple[str, ...] = ("wick", "body"),
    kinds: tuple[str, ...] = ("support", "resistance"),
    query_index: Optional[int] = None,
    pivot_window: int = PIVOT_WINDOW,          # kept for API symmetry with trendline_detector;
                                                # unused directly (scipy find_peaks drives spacing
                                                # via `distance` instead of a fixed +/-k window).
    prominence_atr_fraction: float = PROMINENCE_ATR_FRACTION,
    min_span_bars: int = MIN_SPAN_BARS,
    min_bars_between_touches: int = MIN_BARS_BETWEEN_TOUCHES,
    tolerance_atr_fraction: float = DEFAULT_TOLERANCE_ATR_FRACTION,
    atr_period: int = ATR_PERIOD,
    max_lines_per_kind_family: int = 3,
    require_confirmed: bool = True,            # rule 4: only CONFIRMED lines are draw-eligible
    symbol: str = "SPY",
    timeframe: str = "5m",
) -> tuple[TrendlineV2, ...]:
    """The production/shadow-facing API: best-scoring, draw-eligible lines,
    evaluated as of the last bar (or `query_index`). For checking whether a
    SPECIFIC geometry (e.g. reproducing a hand-drawn line) is achievable at all,
    use `generate_all_candidates` directly -- it returns the full valid universe,
    not just the top-N winners."""
    bars = list(bars)
    if not bars:
        return ()
    query_idx = len(bars) - 1 if query_index is None else query_index
    atr = compute_atr(bars, period=atr_period, end_index=query_idx)
    tol = max(tolerance_atr_fraction * atr, 0.01)

    out: list[TrendlineV2] = []
    for family in families:
        pivots = _find_pivots(bars, family, atr, prominence_atr_fraction, MIN_DISTANCE_BARS)
        for kind in kinds:
            cands = generate_all_candidates(bars, pivots, kind, tol, min_span_bars,
                                             min_bars_between_touches, query_idx)
            if require_confirmed:
                cands = [c for c in cands if c.status == "CONFIRMED"]
            cands.sort(key=lambda c: c.score, reverse=True)
            picked: list[_Candidate] = []
            seen_start: set[int] = set()
            for c in cands:
                if c.i1 in seen_start:
                    continue
                seen_start.add(c.i1)
                picked.append(c)
                if len(picked) >= max_lines_per_kind_family:
                    break
            for c in picked:
                out.append(_build_trendline_v2(c, kind, family, bars, pivots, query_idx,
                                                tol, tolerance_atr_fraction, atr, symbol, timeframe))
    return tuple(out)


# --------------------------------------------------------------------------- #
# Bar loading -- reads ONLY already-fetched caches under backtest/data/. Never
# calls Alpaca/yfinance itself (task boundary: no second data reader/fetcher).
#
# WHY TWO SOURCES: `backtest/data/spy_sip_cache/spy_5m_{date}.json` (one file per
# trading day, 04:00-20:00 ET, SIP feed) covers nearly every date needed for the
# J-drawn-lines validation (2026-05-08 onward) with full premarket. Two dates in
# the validation set (2026-07-14, 2026-08-31) are missing from that cache; for
# those this falls back to scanning the cumulative `spy_5m_*.csv` files written
# by `backtest/tools/fetch_data.py` (also premarket-inclusive by default),
# picking the smallest file whose embedded date range covers the day and whose
# first bar for that date starts at 04:00 (confirms premarket is actually present
# in that particular cumulative file, since not all of them agree -- see
# `trendline_shadow.py::load_bars`'s own naive/aware-stratum warning).
# --------------------------------------------------------------------------- #
def _load_day_from_sip_cache(date_str: str) -> list[BarV2]:
    path = SIP_CACHE_DIR / f"spy_5m_{date_str}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    bars = []
    for b in data.get("bars", []):
        dt_naive = datetime.fromisoformat(b["t"])
        ts = _et_naive_to_unix(dt_naive)
        bars.append(BarV2(ts, float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])))
    return bars


_CSV_RANGE_RE = re.compile(r"spy_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.csv$")


def _load_day_from_csv_glob(date_str: str) -> list[BarV2]:
    candidates = []
    for f in glob.glob(str(DATA_DIR / "spy_5m_*.csv")):
        m = _CSV_RANGE_RE.search(f)
        if not m:
            continue
        start_s, end_s = m.group(1), m.group(2)
        if start_s <= date_str <= end_s:
            candidates.append(f)
    candidates.sort(key=lambda p: Path(p).stat().st_size)  # try smaller/faster files first
    for f in candidates:
        bars: list[BarV2] = []
        first_hour: Optional[str] = None
        with open(f, encoding="utf-8") as fh:
            fh.readline()  # header
            for line in fh:
                if not line.startswith(date_str):
                    continue
                parts = line.rstrip("\n").split(",")
                ts_str = parts[0]
                if first_hour is None:
                    first_hour = ts_str[11:13]
                dt = datetime.fromisoformat(ts_str)
                bars.append(BarV2(int(dt.timestamp()), float(parts[1]), float(parts[2]),
                                   float(parts[3]), float(parts[4])))
        if bars and first_hour == "04":  # confirms premarket is actually present for this date
            bars.sort(key=lambda b: b.ts_unix)
            return bars
    return []


def load_bars_multi_source(dates: Sequence[str]) -> list[BarV2]:
    """Merge, dedup (by ts_unix), and sort 04:00-16:00-ET-inclusive 5m bars for
    the given ET calendar dates ('YYYY-MM-DD'), preferring the per-day SIP cache
    and falling back to the cumulative CSVs. Bars past 16:00 ET (the cache goes
    to 20:00) are kept too -- rule 5 only requires premarket INCLUSION, it does
    not require post-market EXCLUSION for this fitter's own use, and the extra
    tail bars are harmless (RTH-only stays the convention for break/status per
    rule 8's note above, which this module already implements identically to the
    RTH case since 16:00-20:00 bars simply become extra context, not new anchors
    unless a real pivot forms there)."""
    seen: dict[int, BarV2] = {}
    for d in sorted(set(dates)):
        day_bars = _load_day_from_sip_cache(d)
        if not day_bars:
            day_bars = _load_day_from_csv_glob(d)
        for b in day_bars:
            seen[b.ts_unix] = b
    return sorted(seen.values(), key=lambda b: b.ts_unix)
