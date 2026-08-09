"""trendline_detector — pivot-anchored, deterministic trendline detection.

Built 2026-08-09 per J's ask ("full trendline implementation ... labels, engine
awareness, chart drawing capabilities, what time frame do we draw them on for
which markets"). This module owns the DETECTOR CORE + LABELS + ENGINE AWARENESS
pieces. Chart drawing and bull-side live graduation are a sibling agent's lane —
this module is a pure, read-only library with no chart/order/exit side effects.

WHY A NEW MODULE, GIVEN THREE ALREADY EXIST
--------------------------------------------
This repo already has three trendline implementations, and none of them is the
right foundation to generalize from:

  1. `backtest/lib/filters.py::detect_trendline_rejection_bearish` (line 601) —
     the LIVE, load-bearing bear trigger (per `analysis/deep-research/
     EOD-2026-08-06.md`: fired on all 8 ENTER_BEAR verdicts 2026-08-06, 100% of
     that day's P&L). Single-bar-contract, no persistent line objects, SPY-5m-
     specific constants baked in. NOT touched by this module — "build around it,
     not revive it" per the task brief. `detect_trendline_reclaim_bullish` (line
     944) is its shadow-only bull mirror, also untouched.
  2. `backtest/lib/trendlines.py` — a general scipy `find_peaks` two-directional
     detector. Reusable in principle, but pivot IDENTITY comes from a different
     algorithm family than the rest of the engine's structure-reading (market
     structure / HH-HL-LH-LL), and it has no anchor_mode (wick/body) concept.
  3. `backtest/autoresearch/trendline_engine.py` — the most feature-complete
     (wick/body families, respect/violation scoring, status) but it is a
     standalone SCRIPT: it fetches its own Alpaca data, is SPY-hardcoded, and
     lives in `autoresearch/` (research scratch space, not an importable
     library contract). Shadow-only; zero decision consumers.

This module is the first PIVOT-ANCHORED detector in `backtest/lib/` (the
importable, cross-consumer location) built on top of the one primitive the
task brief explicitly named as the right foundation: `crypto/lib/
market_structure.py`'s swing-pivot machinery — "instrument-agnostic despite
the folder" (it operates on the plain `Bar` value type, no SPY/Alpaca coupling,
already proven reusable from `backtest/lib` — see `backtest/lib/watchers/
market_structure_watcher.py`, the existing precedent for exactly this cross-
package import).

DESIGN
------
- Pure functions over `tuple[Bar, ...]` (closed bars, oldest first) — no I/O, no
  global state, no LLM, no chart/order side effects. Frozen dataclasses
  (immutability, per house style).
- Pivot IDENTIFICATION reuses `crypto.lib.trendlines.find_swing_points` — the
  exact primitive `crypto.lib.market_structure.analyze_structure` itself calls
  to derive HH/HL/LH/LL. This module also runs `label_swings` so every anchor
  carries its HH/HL/LH/LL context as a diagnostic (not a gate — see
  `TrendlineAnchor.structure_label`).
- ANCHOR MODE (wick | body) is never mixed within one line — not just an
  assert tripwire (though one exists, belt-and-suspenders), but STRUCTURAL: a
  `anchor_mode="body"` call transforms the bar view ONCE (high := body-top,
  low := body-bottom, open/close preserved) before pivot search even runs, so
  the wick fields never enter the body-mode computation at all. Mirrors the
  documented trick in `backtest/lib/trendlines.py`'s own docstring ("pre-
  process bars to set high=max(open,close) and low=min(open,close)") — not a
  new invention, the established technique in this exact codebase.
- Zero look-ahead (C6): callers may pre-truncate `bars` themselves (the
  `filters.py` convention), or pass the full series plus `as_of_index` — this
  module truncates internally BEFORE any computation in that case, never after.
- Levels-are-zones (J directive, 2026-07-17): touches are scored against a
  tolerance BAND (`touch_tolerance_dollars`), not an exact price match.

PUBLIC API
----------
  detect_trendlines(bars, ...)               -> tuple[TrendlineState, ...]
  bars_from_dataframe(df, ...)                -> tuple[Bar, ...]
  trendline_state_for_decision_row(lines, symbol=..., timeframe=...) -> dict
  annotate_decisions_with_trendline_state(decisions, spy_df, ...) -> list[dict]
  make_line_id(...)                           -> str

See `analysis/deep-research/TRENDLINE-ENGINE-2026-08-09.md` for the validation
program (timeframe matrix + 0DTE backtest cells) run against this module.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.trendlines import SwingPoint, find_swing_points  # noqa: E402
from crypto.lib.market_structure import LabeledSwing, label_swings  # noqa: E402

__all__ = [
    "TrendlineAnchor",
    "TrendlineState",
    "AnchorMode",
    "LineKind",
    "detect_trendlines",
    "bars_from_dataframe",
    "make_line_id",
    "trendline_state_for_decision_row",
    "annotate_decisions_with_trendline_state",
    "DETECTOR_VERSION",
]

DETECTOR_VERSION = "1.0.0"

AnchorMode = Literal["wick", "body"]
LineKind = Literal["resistance", "support"]  # resistance = fit through swing highs;
                                              # support = fit through swing lows
                                              # (naming matches backtest/lib/trendlines.py's
                                              # existing vocabulary in this same package).

# ---------------------------------------------------------------------------
# Defaults — cited precedent, not hand-picked (C25 / no-hand-tuning discipline).
# ---------------------------------------------------------------------------

# Touch tolerance: reuses backtest/lib/trendlines.py's TOUCH_TOLERANCE_USD ($0.20) — an
# already-established, doctrine-adjacent trendline-touch band in this SAME lib/ package,
# not a fresh number invented for this module. "Levels are zones, not prices" (J,
# 2026-07-17) — this IS the zone width.
DEFAULT_TOUCH_TOLERANCE_DOLLARS: float = 0.20

# Pivot fractal window: matches crypto/lib/market_structure.DEFAULT_WINDOW (2) — the
# already-calibrated SPY-5m default cited by backtest/lib/watchers/market_structure_watcher.py.
DEFAULT_PIVOT_WINDOW: int = 2

DEFAULT_MIN_TOUCHES: int = 3                 # "a trendline needs 3 points" — matches BOTH
                                              # filters.py's TRENDLINE_MIN_SWINGS and the
                                              # independently-converging Tori-method research
                                              # (analysis/deep-research/TORI-TRENDLINE-RESEARCH-
                                              # 2026-08-09.md): "3 or more taps" both sources.
DEFAULT_MIN_BARS_BETWEEN_TOUCHES: int = 6    # Tori method: "6+ candles between taps" — filters
                                              # out one reaction masquerading as 3 touches.
                                              # Independently converges with filters.py's own
                                              # MIN_BAR_SEPARATION=10 (5m bars, ~2x this scale);
                                              # kept as its own named, configurable param rather
                                              # than copying either source's number verbatim.
DEFAULT_MIN_SPAN_BARS: int = 6               # anchor pair must span >= this many bars — matches
                                              # trendline_engine.py's MIN_SPAN=3 order of
                                              # magnitude, doubled to line up with the touch-
                                              # spacing default above (a span shorter than one
                                              # touch-spacing gap cannot host 3 spaced touches).

# Candidate scoring weights — ported verbatim from backtest/autoresearch/trendline_engine.py's
# `_fit` (`score = respect - 5*violations + span*0.1`), the one battle-tested formula this exact
# problem (SPY intraday pivot-trendline scoring) already has in this codebase. Not re-derived.
VIOLATION_PENALTY: float = 5.0
SPAN_BONUS_WEIGHT: float = 0.1


@dataclass(frozen=True, slots=True)
class TrendlineAnchor:
    """One anchor point of a fitted line."""
    bar_index: int
    bar_time_unix: float
    price: float
    structure_label: Optional[str] = None  # HH|HL|LH|LL|H|L from market_structure.label_swings,
                                            # diagnostic only — NEVER gates candidate selection
                                            # (keeps this module's recall close to the proven
                                            # live detector's simple "strictly decreasing pivots"
                                            # behavior; the label rides along for visibility).


@dataclass(frozen=True, slots=True)
class TrendlineState:
    """A detected trendline, evaluated as of the LAST bar in the sequence passed to
    `detect_trendlines` (i.e. "now"). Re-running `detect_trendlines` on a longer bar
    sequence re-evaluates every field fresh — this is a snapshot, not a mutable object.
    """
    line_id: str
    kind: LineKind
    anchor_mode: AnchorMode
    anchors: tuple[TrendlineAnchor, ...]       # >= 2, chronological, the anchor PAIR the
                                                # winning candidate was fit through (NOT every
                                                # touch — see touch_count for that count)
    touch_count: int                           # anchors + every additional respected touch
    violation_count: int                       # bars whose CLOSE broke through the line
    slope_per_bar: float                       # $ per bar (raw, human/chart-facing)
    slope_pct_per_bar: float                   # slope_per_bar / first-anchor price — the
                                                # cross-instrument-comparable form
    created_bar_index: int                     # bar index at which touch_count first reached
                                                # min_touches (when the line first "exists")
    last_touch_bar_index: int
    query_bar_index: int                       # the "as of" bar this snapshot evaluates at
    current_value: float                       # line projected to query_bar_index
    distance_to_price: float                   # query close - current_value (signed, $)
    distance_pct: float                        # distance_to_price / query close
    side: Literal["above", "below"]            # is query close above or below current_value
    status: Literal["intact", "testing", "broken"]
    just_broken: bool                          # status=="broken" AND this is the FIRST bar
                                                # the line was ever broken on
    just_retested: bool                        # a touch landed exactly on query_bar_index and
                                                # it is not the line's own defining touch
    age_bars: int                              # query_bar_index - created_bar_index

    def to_dict(self) -> dict:
        return {
            "line_id": self.line_id,
            "kind": self.kind,
            "anchor_mode": self.anchor_mode,
            "anchors": [
                {"bar_index": a.bar_index, "bar_time_unix": a.bar_time_unix,
                 "price": a.price, "structure_label": a.structure_label}
                for a in self.anchors
            ],
            "touch_count": self.touch_count,
            "violation_count": self.violation_count,
            "slope_per_bar": round(self.slope_per_bar, 5),
            "slope_pct_per_bar": round(self.slope_pct_per_bar, 6),
            "created_bar_index": self.created_bar_index,
            "last_touch_bar_index": self.last_touch_bar_index,
            "query_bar_index": self.query_bar_index,
            "current_value": round(self.current_value, 4),
            "distance_to_price": round(self.distance_to_price, 4),
            "distance_pct": round(self.distance_pct, 6),
            "side": self.side,
            "status": self.status,
            "just_broken": self.just_broken,
            "just_retested": self.just_retested,
            "age_bars": self.age_bars,
        }


# ---------------------------------------------------------------------------
# Bar-view transform — the structural (not just assert-guarded) anchor_mode
# no-mixing guarantee: body-mode pivot search NEVER sees a wick field.
# ---------------------------------------------------------------------------

def _body_view(bars: Sequence[Bar]) -> tuple[Bar, ...]:
    """Bars with high/low replaced by body extremes (open/close preserved).

    Documented trick, not a new invention — `backtest/lib/trendlines.py`'s own
    docstring: "If you want body-only trendlines, pre-process bars to set
    high=max(open,close) and low=min(open,close) before passing in." Doing the
    swap ONCE here, before any pivot search runs, is what makes anchor_mode
    "body" structurally incapable of picking up a wick value — not merely
    caught by an assert after the fact.
    """
    out = []
    for b in bars:
        top = max(b.open, b.close)
        bot = min(b.open, b.close)
        out.append(Bar(
            open_time=b.open_time, open=b.open, high=top, low=bot, close=b.close,
            volume=b.volume, granularity_seconds=b.granularity_seconds, source=b.source,
        ))
    return tuple(out)


def _view_for_mode(bars: Sequence[Bar], anchor_mode: AnchorMode) -> tuple[Bar, ...]:
    if anchor_mode == "wick":
        return tuple(bars)
    if anchor_mode == "body":
        return _body_view(bars)
    raise ValueError(f"anchor_mode must be 'wick' or 'body', got {anchor_mode!r}")


# ---------------------------------------------------------------------------
# Candidate line fitting
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _Candidate:
    anchor_a: SwingPoint
    anchor_b: SwingPoint
    slope: float
    intercept_price: float
    intercept_bar_index: int
    touch_bar_indices: tuple[int, ...]         # ALL accepted touches, chronological, anchors
                                                # included (spacing-filtered per
                                                # min_bars_between_touches)
    violation_bar_indices: tuple[int, ...]     # every bar whose CLOSE broke the line
    score: float


def _project(slope: float, intercept_price: float, intercept_bar_index: int, bar_index: int) -> float:
    return intercept_price + slope * (bar_index - intercept_bar_index)


def _fit_candidate(
    anchor_a: SwingPoint,
    anchor_b: SwingPoint,
    *,
    kind: LineKind,
    view_bars: tuple[Bar, ...],
    same_kind_swings: Sequence[SwingPoint],
    touch_tolerance_dollars: float,
    min_bars_between_touches: int,
    min_touches: int,
    require_slope: Literal["any", "rising", "falling"],
) -> Optional[_Candidate]:
    i1, i2 = anchor_a.bar_index, anchor_b.bar_index
    p1, p2 = anchor_a.price, anchor_b.price
    if i2 == i1:
        return None
    slope = (p2 - p1) / (i2 - i1)
    if require_slope == "rising" and slope <= 0:
        return None
    if require_slope == "falling" and slope >= 0:
        return None

    # Touches: walk every same-kind swing point from anchor_a onward (never before it —
    # C6 no-look-ahead-into-the-past-before-the-line-existed is not the concern here, the
    # concern is not projecting a line BACKWARD before its own first anchor and crediting
    # touches that could not have confirmed it), accept greedily with spacing enforcement.
    touches: list[int] = []
    for sp in same_kind_swings:
        if sp.bar_index < i1:
            continue
        projected = _project(slope, p1, i1, sp.bar_index)
        if abs(sp.price - projected) > touch_tolerance_dollars:
            continue
        if touches and (sp.bar_index - touches[-1]) < min_bars_between_touches:
            continue  # too close to the previous accepted touch -- one reaction, not a new test
        touches.append(sp.bar_index)
    if i1 not in touches or i2 not in touches:
        # anchors themselves must always count as touches (they define the line)
        touches = sorted(set(touches) | {i1, i2})

    # PERFORMANCE: reject on touch-count BEFORE the O(n_bars) violation scan below. Most
    # random pivot-pairs never reach min_touches, so this ordering keeps detect_trendlines
    # usable at population scale (thousands of calls) instead of O(pivots^2 * n_bars) always.
    if len(touches) < min_touches:
        return None

    # Violations: every CLOSED bar from anchor_a onward whose CLOSE broke through the line.
    violations: list[int] = []
    for idx in range(i1, len(view_bars)):
        projected = _project(slope, p1, i1, idx)
        close = view_bars[idx].close
        broke = (close < projected - touch_tolerance_dollars) if kind == "support" \
            else (close > projected + touch_tolerance_dollars)
        if broke:
            violations.append(idx)

    score = len(touches) - VIOLATION_PENALTY * len(violations) + (i2 - i1) * SPAN_BONUS_WEIGHT
    return _Candidate(
        anchor_a=anchor_a, anchor_b=anchor_b, slope=slope, intercept_price=p1,
        intercept_bar_index=i1, touch_bar_indices=tuple(touches),
        violation_bar_indices=tuple(violations), score=score,
    )


def _label_lookup(labeled: Sequence[LabeledSwing]) -> dict[tuple[int, str], str]:
    return {(ls.bar_index, ls.kind): ls.label for ls in labeled}


def _build_line_state(
    cand: _Candidate,
    *,
    kind: LineKind,
    anchor_mode: AnchorMode,
    view_bars: tuple[Bar, ...],
    query_bar_index: int,
    min_touches: int,
    touch_tolerance_dollars: float,
    labels: dict[tuple[int, str], str],
    swing_kind: str,
    symbol: str,
    timeframe: str,
) -> TrendlineState:
    a = cand.anchor_a
    b = cand.anchor_b
    anchors = (
        TrendlineAnchor(a.bar_index, a.bar_time_unix, a.price, labels.get((a.bar_index, swing_kind))),
        TrendlineAnchor(b.bar_index, b.bar_time_unix, b.price, labels.get((b.bar_index, swing_kind))),
    )
    current_value = _project(cand.slope, cand.intercept_price, cand.intercept_bar_index, query_bar_index)
    query_close = view_bars[query_bar_index].close
    distance = query_close - current_value
    ref_price = a.price if a.price else 1.0
    slope_pct = cand.slope / ref_price if ref_price else 0.0

    # created_bar_index: the bar at which touch_count first reached min_touches (chronological
    # nth touch). touch_bar_indices is already sorted ascending (anchors + accepted touches).
    sorted_touches = sorted(cand.touch_bar_indices)
    created_bar_index = sorted_touches[min_touches - 1] if len(sorted_touches) >= min_touches \
        else sorted_touches[-1]

    # status: mirrors trendline_engine.py's INTACT/TESTING/BROKEN convention.
    last_bar = view_bars[query_bar_index]
    tol = touch_tolerance_dollars
    if kind == "support":
        broken = last_bar.close < current_value - tol
        testing = (not broken) and last_bar.low <= current_value + tol
    else:
        broken = last_bar.close > current_value + tol
        testing = (not broken) and last_bar.high >= current_value - tol
    status: Literal["intact", "testing", "broken"] = "broken" if broken else ("testing" if testing else "intact")

    first_violation = cand.violation_bar_indices[0] if cand.violation_bar_indices else None
    just_broken = status == "broken" and first_violation == query_bar_index

    just_retested = (
        query_bar_index in cand.touch_bar_indices
        and query_bar_index not in (a.bar_index, b.bar_index)
        and query_bar_index != sorted_touches[0]
    )

    return TrendlineState(
        line_id=make_line_id(symbol, timeframe, kind, anchor_mode, a.bar_time_unix),
        kind=kind, anchor_mode=anchor_mode, anchors=anchors,
        touch_count=len(cand.touch_bar_indices), violation_count=len(cand.violation_bar_indices),
        slope_per_bar=cand.slope, slope_pct_per_bar=slope_pct,
        created_bar_index=created_bar_index, last_touch_bar_index=sorted_touches[-1],
        query_bar_index=query_bar_index, current_value=current_value,
        distance_to_price=distance, distance_pct=(distance / query_close if query_close else 0.0),
        side=("above" if query_close >= current_value else "below"),
        status=status, just_broken=just_broken, just_retested=just_retested,
        age_bars=query_bar_index - created_bar_index,
    )


def make_line_id(
    symbol: str, timeframe: str, kind: LineKind, anchor_mode: AnchorMode, first_anchor_unix: float,
) -> str:
    """Stable line identity: TL-{symbol}-{timeframe}-{RES|SUP}-{W|B}-{first_anchor_unix}.

    Keyed on the FIRST anchor's timestamp (not a positional bar index) so the SAME physical
    line keeps the SAME id as it accrues more touches over time, is re-detected from a
    different slice window, or is looked up across sessions/logs/chart labels — a positional
    bar index is only meaningful within one contiguous in-memory bar array and would silently
    collide/drift across runs. The id itself encodes direction + anchor flavor so a reader
    (or J) can state "what kind of line is this" without a lookup — per the standing rule
    that a line's flavor (wick vs body) must always be stated when describing it.
    """
    dir_tag = "RES" if kind == "resistance" else "SUP"
    mode_tag = "W" if anchor_mode == "wick" else "B"
    return f"TL-{symbol}-{timeframe}-{dir_tag}-{mode_tag}-{int(first_anchor_unix)}"


def detect_trendlines(
    bars: Sequence[Bar],
    *,
    as_of_index: Optional[int] = None,
    kinds: tuple[LineKind, ...] = ("resistance", "support"),
    anchor_mode: AnchorMode = "wick",
    pivot_window: int = DEFAULT_PIVOT_WINDOW,
    min_touches: int = DEFAULT_MIN_TOUCHES,
    min_bars_between_touches: int = DEFAULT_MIN_BARS_BETWEEN_TOUCHES,
    min_span_bars: int = DEFAULT_MIN_SPAN_BARS,
    max_slope_pct_per_bar: Optional[float] = None,
    touch_tolerance_dollars: float = DEFAULT_TOUCH_TOLERANCE_DOLLARS,
    require_slope: Literal["any", "rising", "falling"] = "any",
    max_lines_per_kind: int = 1,
    symbol: str = "SPY",
    timeframe: str = "5m",
) -> tuple[TrendlineState, ...]:
    """Detect the best-scoring trendline(s), evaluated as of the last bar.

    Zero look-ahead (C6): if `as_of_index` is given, `bars` is truncated to
    `bars[:as_of_index + 1]` BEFORE any pivot search or fit — never after. If
    `as_of_index` is None, the caller is trusted to have already truncated
    `bars` themselves (the `filters.py` convention: `prior_bars`/`bar_idx`).

    anchor_mode ("wick" | "body") is NEVER mixed within one call: the entire
    pivot search + fit runs against ONE bar view (see `_view_for_mode`) chosen
    once at the top of this function.

    `require_slope`: "any" (default, general-purpose) | "rising" | "falling" —
    an optional convenience constraint for callers who want to replicate a
    specific doctrine pattern (e.g. filters.py's bearish detector requires a
    strictly-descending resistance line). Default "any" imposes no directional
    bias — this is a general-purpose library, not a copy of any one trigger.

    Returns up to `max_lines_per_kind` lines per requested `kind`, highest-score
    first, only for candidates that clear `min_touches` / `min_span_bars` /
    `max_slope_pct_per_bar`. Returns an empty tuple if nothing qualifies (never
    raises for "no line found" — that is the normal, common case).
    """
    if anchor_mode not in ("wick", "body"):
        raise ValueError(f"anchor_mode must be 'wick' or 'body', got {anchor_mode!r}")
    bars = tuple(bars)
    if as_of_index is not None:
        bars = bars[: as_of_index + 1]
    if len(bars) < max(5, min_span_bars + 2):
        return ()
    query_bar_index = len(bars) - 1

    view = _view_for_mode(bars, anchor_mode)
    # Structural guard (belt-and-suspenders on top of the by-construction view swap above):
    # every "high" fed to the pivot search below must equal EXACTLY this view's own high
    # field for its own anchor_mode -- i.e. never the other mode's accessor value smuggled
    # in some other way. Mirrors trendline_engine.py's per-family assert convention.
    if anchor_mode == "wick":
        assert all(view[i].high == bars[i].high and view[i].low == bars[i].low for i in range(len(bars))), \
            "wick anchor_mode must use the RAW bar high/low, never a transformed view"
    else:
        assert all(
            view[i].high == max(bars[i].open, bars[i].close)
            and view[i].low == min(bars[i].open, bars[i].close)
            for i in range(len(bars))
        ), "body anchor_mode must use max/min(open,close), never the raw wick"

    swings = find_swing_points(view, window=pivot_window, inclusive_right=True)
    labeled = label_swings(swings)
    labels = _label_lookup(labeled)

    highs = sorted([s for s in swings if s.kind == "swing_high"], key=lambda s: s.bar_index)
    lows = sorted([s for s in swings if s.kind == "swing_low"], key=lambda s: s.bar_index)

    out: list[TrendlineState] = []
    for kind in kinds:
        pool = highs if kind == "resistance" else lows
        best: list[_Candidate] = []
        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                a, b = pool[i], pool[j]
                if b.bar_index - a.bar_index < min_span_bars:
                    continue
                cand = _fit_candidate(
                    a, b, kind=kind, view_bars=view, same_kind_swings=pool,
                    touch_tolerance_dollars=touch_tolerance_dollars,
                    min_bars_between_touches=min_bars_between_touches,
                    min_touches=min_touches,
                    require_slope=require_slope,
                )
                if cand is None:
                    continue
                if max_slope_pct_per_bar is not None:
                    ref = a.price if a.price else 1.0
                    if abs(cand.slope / ref) > max_slope_pct_per_bar:
                        continue
                best.append(cand)
        best.sort(key=lambda c: c.score, reverse=True)

        # Dedup near-identical winners (same anchor pair start) before truncating to
        # max_lines_per_kind, mirroring backtest/lib/trendlines.py's dedup philosophy.
        seen_starts: set[int] = set()
        picked: list[_Candidate] = []
        for c in best:
            if c.anchor_a.bar_index in seen_starts:
                continue
            seen_starts.add(c.anchor_a.bar_index)
            picked.append(c)
            if len(picked) >= max_lines_per_kind:
                break

        swing_kind = "swing_high" if kind == "resistance" else "swing_low"
        for c in picked:
            out.append(_build_line_state(
                c, kind=kind, anchor_mode=anchor_mode, view_bars=view,
                query_bar_index=query_bar_index, min_touches=min_touches,
                touch_tolerance_dollars=touch_tolerance_dollars,
                labels=labels, swing_kind=swing_kind, symbol=symbol, timeframe=timeframe,
            ))
    return tuple(out)


# ---------------------------------------------------------------------------
# DataFrame adapter (backtest engine bars are pandas, not crypto.lib.Bar)
# ---------------------------------------------------------------------------

def bars_from_dataframe(
    df,
    *,
    ts_col: str = "timestamp_et",
    open_col: str = "open",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    volume_col: str = "volume",
    granularity_seconds: int = 300,
    source: str = "spy_backtest_df",
) -> tuple[Bar, ...]:
    """Convert a backtest-engine-shaped DataFrame (columns: timestamp_et, open,
    high, low, close[, volume]) into an immutable `Bar` tuple, oldest first.

    Mirrors the conversion pattern already proven in `backtest/lib/watchers/
    market_structure_watcher.py::_build_bars_from_context`, generalized to a
    timestamp COLUMN (this module's callers carry `timestamp_et` as a column,
    not a DataFrame index).
    """
    import datetime as _dt
    import pandas as _pd

    if df is None or len(df) == 0:
        return ()
    ts = _pd.to_datetime(df[ts_col], utc=True)
    out = []
    vol_present = volume_col in df.columns
    for i in range(len(df)):
        t = ts.iloc[i]
        open_time = t.to_pydatetime()
        if open_time.tzinfo is None:
            open_time = open_time.replace(tzinfo=_dt.timezone.utc)
        row = df.iloc[i]
        out.append(Bar(
            open_time=open_time,
            open=float(row[open_col]), high=float(row[high_col]),
            low=float(row[low_col]), close=float(row[close_col]),
            volume=float(row[volume_col]) if vol_present else 0.0,
            granularity_seconds=granularity_seconds, source=source,
        ))
    return tuple(out)


# ---------------------------------------------------------------------------
# Engine awareness -- additive decision-row annotation (never touches verdicts)
# ---------------------------------------------------------------------------

def trendline_state_for_decision_row(lines: Sequence[TrendlineState]) -> dict:
    """Flatten a set of detected lines into the additive shape a decision row
    carries: nearest line overall, plus the nearest resistance/support
    separately (a bar can be simultaneously near a resistance AND a support).

    Pure formatting — takes already-detected lines, never calls the detector
    itself and never touches bars/verdicts. Returns `{}` (not None) when no
    lines are given, so a consumer can always safely do `row.get("trendline_state", {})`.
    """
    if not lines:
        return {}
    by_abs_distance = sorted(lines, key=lambda ln: abs(ln.distance_to_price))
    nearest = by_abs_distance[0]

    def _pick(kind: LineKind) -> Optional[TrendlineState]:
        cands = [ln for ln in lines if ln.kind == kind]
        return min(cands, key=lambda ln: abs(ln.distance_to_price)) if cands else None

    nearest_res = _pick("resistance")
    nearest_sup = _pick("support")
    return {
        "detector_version": DETECTOR_VERSION,
        "n_lines": len(lines),
        "nearest_line_id": nearest.line_id,
        "nearest_distance": round(nearest.distance_to_price, 4),
        "nearest_distance_pct": round(nearest.distance_pct, 6),
        "nearest_side": nearest.side,
        "nearest_status": nearest.status,
        "nearest_just_broken": nearest.just_broken,
        "nearest_just_retested": nearest.just_retested,
        "resistance": nearest_res.to_dict() if nearest_res else None,
        "support": nearest_sup.to_dict() if nearest_sup else None,
    }


def annotate_decisions_with_trendline_state(
    decisions: Sequence[dict],
    spy_df,
    *,
    bar_idx_key: str = "bar_idx",
    output_key: str = "trendline_state",
    lookback_bars: int = 240,
    **detect_kwargs,
) -> list[dict]:
    """Return a NEW list of decision-row dicts (immutability rule — the input
    list and its dicts are never mutated) with an additive `trendline_state`
    key computed independently from `spy_df`.

    This is the "engine can see them" wiring: it runs strictly AFTER
    `decisions` already exist (e.g. `BacktestResult.decisions` from
    `backtest/lib/orchestrator.run_backtest`, or the live `core-decisions.jsonl`
    ledger loaded into memory) and never re-derives or alters `action` /
    `triggers_fired` / any existing key — it only ever ADDS `output_key`. A row
    with no `bar_idx_key` (or an unresolvable one) is passed through unchanged
    plus `output_key: {}`, never dropped, never raising (C7 — never silently
    swallow, but a missing bar index is not itself an error worth crashing a
    whole annotation pass over).
    """
    bars_full = bars_from_dataframe(spy_df)
    out: list[dict] = []
    for row in decisions:
        new_row = dict(row)  # shallow copy -- never mutate caller's dict
        idx = row.get(bar_idx_key)
        if idx is None or not isinstance(idx, int) or idx < 0 or idx >= len(bars_full):
            new_row[output_key] = {}
            out.append(new_row)
            continue
        window_start = max(0, idx - lookback_bars)
        window = bars_full[window_start: idx + 1]
        lines = detect_trendlines(window, **detect_kwargs)
        new_row[output_key] = trendline_state_for_decision_row(lines)
        out.append(new_row)
    return out
