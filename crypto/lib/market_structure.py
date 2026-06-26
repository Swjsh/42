"""market_structure -- the swing-SEQUENCE layer the engine was missing.

Project Gamma reads *trend* from the EMA ribbon stack + regime classifier, never
from price structure. So the engine had no answer to J's literal question:
"are we making higher highs and lower lows?" Swing pivots were computed
transiently inside trendlines.py / levels.py but never LABELED or surfaced.

This module closes that gap. Market structure is a SEQUENCE, not a snapshot
(TA-PATTERN-REFERENCE.md A.2-A.4), so the read is computed by WALKING the bars and
maintaining a working trend that flips only on a confirmed structure break:

    BOS  (Break of Structure)  -- a CLOSE beyond the most recent swing IN the
                                  working-trend direction. Continuation.
    CHoCH (Change of Character) -- the FIRST close beyond a swing AGAINST the
                                  working trend. It FLIPS the working trend; the
                                  next with-trend break is again a BOS. CHoCH is
                                  the single earliest reversal hint -- so it must
                                  fire once per flip, which a snapshot cannot do.

Design:
    - Pure functions over `Sequence[Bar]` (closed bars, oldest first). No
      DataFrames, no global state, no LLM.
    - Swing detection is INJECTABLE (`swing_finder`) so the LIVE engine can feed
      its own pivot primitive (backtest/lib/trendlines scipy) without forking the
      structure logic -- the drift the autonomy blueprint warns about. Default
      reuses crypto.lib.trendlines.find_swing_points with the equal-level tie-break.
    - Frozen dataclasses (immutability). CLOSED bars only (caller filters first).

NOTE (live-wiring blocker): this lives in crypto/lib for gym validation + the
read-only chart-read skill. Wiring structure into the LIVE fleet must (a) inject
backtest/lib's swing primitive via `swing_finder`, and (b) emit a WatcherSignal
(see `signal_tier`). Until then this is telemetry only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Sequence

from crypto.lib.bar import Bar
from crypto.lib.trendlines import SwingPoint, find_swing_points

Trend = Literal["uptrend", "downtrend", "range", "unknown"]
SwingFinder = Callable[[Sequence[Bar]], list[SwingPoint]]

DEFAULT_WINDOW = 2  # bars-per-side fractal; SPY 5m default (see gym calibration)


@dataclass(frozen=True, slots=True)
class LabeledSwing:
    bar_index: int
    price: float
    kind: str       # "swing_high" | "swing_low"
    label: str      # "HH" | "HL" | "LH" | "LL" | "H" | "L"


@dataclass(frozen=True, slots=True)
class StructureEvent:
    kind: Literal["BOS", "CHoCH"]
    direction: Literal["bullish", "bearish"]
    broken_price: float
    swing_index: int
    break_index: int


@dataclass(frozen=True, slots=True)
class MarketStructureRead:
    trend: str
    trend_basis: str                         # "structure_breaks" | "labels" | "insufficient"
    labeled_swings: tuple[LabeledSwing, ...]
    events: tuple[StructureEvent, ...]       # every BOS/CHoCH found, in time order
    last_event: StructureEvent | None
    last_swing_high: float | None
    last_swing_low: float | None
    confidence: float                        # HEURISTIC, NOT outcome-calibrated
    notes: dict


def _swing_sort_key(s: SwingPoint) -> tuple[int, int]:
    # Total order: by bar, then high-before-low so a dual-kind (outside) bar is deterministic.
    return (s.bar_index, 0 if s.kind == "swing_high" else 1)


def label_swings(swings: Sequence[SwingPoint]) -> tuple[LabeledSwing, ...]:
    """Label each swing vs the prior swing OF THE SAME KIND (HH/HL/LH/LL; seed H/L)."""
    ordered = sorted(swings, key=_swing_sort_key)
    out: list[LabeledSwing] = []
    last_high: float | None = None
    last_low: float | None = None
    for s in ordered:
        if s.kind == "swing_high":
            label = "H" if last_high is None else ("HH" if s.price > last_high else "LH")
            last_high = s.price
        else:
            label = "L" if last_low is None else ("HL" if s.price > last_low else "LL")
            last_low = s.price
        out.append(LabeledSwing(s.bar_index, s.price, s.kind, label))
    return tuple(out)


def classify_trend(labeled: Sequence[LabeledSwing]) -> Trend:
    """Tentative trend from the last TWO highs and last TWO lows jointly (a run,
    not a single label -- robust to one noisy swing). Used as the fallback before
    any confirmed structure break; `walk_structure` gives the authoritative trend.

    uptrend   = last two highs non-decreasing AND last two lows non-decreasing
    downtrend = mirror
    range     = mixed (>=2 of each but not jointly directional)
    unknown   = < 2 of either kind
    """
    highs = [s for s in labeled if s.kind == "swing_high"]
    lows = [s for s in labeled if s.kind == "swing_low"]
    if len(highs) < 2 or len(lows) < 2:
        return "unknown"
    highs_up = highs[-1].price >= highs[-2].price
    lows_up = lows[-1].price >= lows[-2].price
    highs_dn = highs[-1].price <= highs[-2].price
    lows_dn = lows[-1].price <= lows[-2].price
    if highs_up and lows_up:
        return "uptrend"
    if highs_dn and lows_dn:
        return "downtrend"
    return "range"


def walk_structure(
    bars: Sequence[Bar], swings: Sequence[SwingPoint], window: int
) -> tuple[Trend, tuple[StructureEvent, ...]]:
    """Walk bars chronologically, maintaining a working trend that flips on each
    confirmed structure break. This is the authoritative BOS/CHoCH state machine.

    A swing becomes a breakable reference only `window` bars after its pivot
    (confirmation lag -- no look-ahead). A CLOSE beyond the active reference is a
    break: with the working trend = BOS, against it = CHoCH (which flips the trend).
    """
    by_confirm: dict[int, list[SwingPoint]] = {}
    for s in sorted(swings, key=_swing_sort_key):
        by_confirm.setdefault(s.bar_index + window, []).append(s)

    working: Trend = "unknown"
    events: list[StructureEvent] = []
    ref_high: SwingPoint | None = None
    ref_low: SwingPoint | None = None

    for i in range(len(bars)):
        c = bars[i].close
        # 1) break check (close-based, per TA-PATTERN-REFERENCE.md A.3/A.4)
        if ref_high is not None and c > ref_high.price:
            kind = "CHoCH" if working == "downtrend" else "BOS"
            events.append(StructureEvent(kind, "bullish", ref_high.price, ref_high.bar_index, i))
            working = "uptrend"
            ref_high = None  # consumed; wait for the next confirmed swing high
        elif ref_low is not None and c < ref_low.price:
            kind = "CHoCH" if working == "uptrend" else "BOS"
            events.append(StructureEvent(kind, "bearish", ref_low.price, ref_low.bar_index, i))
            working = "downtrend"
            ref_low = None
        # 2) bring newly-confirmed swings into scope AFTER the break check, so a
        #    swing can never break itself on its own confirmation bar.
        for s in by_confirm.get(i, []):
            if s.kind == "swing_high":
                ref_high = s
            else:
                ref_low = s

    return working, tuple(events)


def detect_structure_break(
    bars: Sequence[Bar], swings: Sequence[SwingPoint], trend: Trend
) -> StructureEvent | None:
    """SNAPSHOT helper: did the FINAL bar's close break the most-recent swing,
    given `trend`? Kept for the "right now, this tick" question. For the
    authoritative sequence read use `walk_structure` / `analyze_structure`.
    """
    if not bars or not swings:
        return None
    last_close = bars[-1].close
    break_index = len(bars) - 1
    highs = [s for s in swings if s.kind == "swing_high"]
    lows = [s for s in swings if s.kind == "swing_low"]
    last_high = highs[-1] if highs else None
    last_low = lows[-1] if lows else None
    if last_high is not None and last_close > last_high.price and last_high.bar_index < break_index:
        kind = "CHoCH" if trend == "downtrend" else "BOS"
        return StructureEvent(kind, "bullish", last_high.price, last_high.bar_index, break_index)
    if last_low is not None and last_close < last_low.price and last_low.bar_index < break_index:
        kind = "CHoCH" if trend == "uptrend" else "BOS"
        return StructureEvent(kind, "bearish", last_low.price, last_low.bar_index, break_index)
    return None


def _confidence(trend: Trend, labeled: Sequence[LabeledSwing], events: Sequence[StructureEvent]) -> float:
    """HEURISTIC confidence (NOT outcome-calibrated -- do not gate on it).
    Rewards a directional trend, a confirmed break, and label agreement; penalises range/unknown.
    """
    if trend in ("unknown", "range"):
        base = 0.20 + 0.05 * min(len(labeled), 4)
        return round(min(base, 0.50), 3)
    base = 0.45
    if events:
        base += 0.15
    want_high = "HH" if trend == "uptrend" else "LH"
    want_low = "HL" if trend == "uptrend" else "LL"
    recent_highs = [s.label for s in labeled if s.kind == "swing_high"][-3:]
    recent_lows = [s.label for s in labeled if s.kind == "swing_low"][-3:]
    agree = recent_highs.count(want_high) + recent_lows.count(want_low)
    total = len(recent_highs) + len(recent_lows)
    if total:
        base += 0.40 * (agree / total)
    return round(min(base, 1.0), 3)


def analyze_structure(
    bars: Sequence[Bar],
    *,
    window: int = DEFAULT_WINDOW,
    swing_finder: SwingFinder | None = None,
) -> MarketStructureRead:
    """bars -> swings -> labels -> working trend (state machine) -> structure read.

    swing_finder: inject a different pivot primitive (e.g. the live engine's) to
    keep ONE structure implementation across gym + live. Default reuses
    crypto.lib.trendlines with the equal-level tie-break.
    """
    if swing_finder is None:
        swings = find_swing_points(bars, window=window, inclusive_right=True)
    else:
        swings = swing_finder(bars)

    labeled = label_swings(swings)
    working, events = walk_structure(bars, swings, window)
    label_trend = classify_trend(labeled)
    if working != "unknown":
        trend, basis = working, "structure_breaks"
    elif label_trend != "unknown":
        trend, basis = label_trend, "labels"
    else:
        trend, basis = "unknown", "insufficient"

    highs = [s for s in labeled if s.kind == "swing_high"]
    lows = [s for s in labeled if s.kind == "swing_low"]
    last_idx = (len(bars) - 1) if bars else 0
    last_swing_idx = max((s.bar_index for s in swings), default=None)
    bars_since_last_swing = (last_idx - last_swing_idx) if last_swing_idx is not None else None

    notes = {
        "n_swings": len(swings),
        "n_swing_highs": len(highs),
        "n_swing_lows": len(lows),
        "n_events": len(events),
        "window": window,
        "bars_since_last_swing": bars_since_last_swing,
        "last_event_bars_ago": (last_idx - events[-1].break_index) if events else None,
        "recent_label_sequence": [s.label for s in labeled[-6:]],
        "confidence_is_heuristic": True,
    }
    return MarketStructureRead(
        trend=trend,
        trend_basis=basis,
        labeled_swings=labeled,
        events=events,
        last_event=events[-1] if events else None,
        last_swing_high=highs[-1].price if highs else None,
        last_swing_low=lows[-1].price if lows else None,
        confidence=_confidence(trend, labeled, events),
        notes=notes,
    )


def signal_tier(confidence: float) -> str:
    """Map heuristic 0..1 confidence onto the WatcherSignal tier vocabulary
    ("low"|"medium"|"high"). The bridge for a future market-structure watcher to
    emit the canonical Insight contract (backtest/lib/watchers.WatcherSignal)
    instead of a new output shape.
    """
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.55:
        return "medium"
    return "low"
