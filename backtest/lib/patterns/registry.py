"""registry.py — the seeded Tier-1/2 pattern-grammar rules.

11 seed rules (the brief's 10-item list names "triangle_ascending/descending" via a
slash, which TA-PATTERN-REFERENCE.md sec C.3/C.4 treats as two genuinely different
patterns — different bias, different Bulkowski stats, different predicate composition —
so this registry seeds BOTH as separate entries; every other brief item maps 1:1) PLUS
two live-tape-driven additions filed the same day from queue.md
ENGULFING-AT-STRUCTURE-TRIGGER: engulfing_at_swing_shelf (an engulfing-candle-at-a-
fresh-intraday-swing-shelf composition J called live on two mirror-symmetric days that
neither engulfing_at_level (named-level anchor) nor double_top_bottom_at_level
(neckline-break resolution, not a same-bar reaction) covers — but which ITSELF turned
out not to fire on either exhibit, see its anchors) and its direct follow-up
engulfing_at_local_cluster (same 2 exhibits, swaps the swing-pivot anchor for the new
no-confirmation-lag local_extreme_cluster primitive — VERIFIED to fire on both via
pattern_anchor_verify.py) — 13 rules total as of that addition.

Full citation table + Tier-1/2 rationale + the "why 15 predicates not exactly 10-14, why
these 11 seed rules, what's deliberately excluded (harmonics/Elliott)" design discussion
lives in markdown/research/PATTERN-GRAMMAR.md sec 2 (engulfing_at_swing_shelf's own
rationale is inline on its PatternRule + _engulfing_at_swing_shelf_predicate below;
engulfing_at_local_cluster's is inline on its own PatternRule +
_engulfing_at_local_cluster_predicate). This file is the executable contract; the doc
is the reasoning.

NO WIRING: nothing here is imported by the live engine, setup_dispatch, or any watcher.
This registry is consumed ONLY by backtest/tools/pattern_prescreen.py (frequency/
objectivity screen) and, per the handoff in PATTERN-GRAMMAR.md sec 3, by a future
discovery_shadow_ledger.py / backtest_design_swarm.py run for any rule the prescreen
marks TESTABLE.
"""
from __future__ import annotations

from typing import Optional

from .combinators import Predicate, all_of, then_break, within_n_bars_after
from .context import PatternContext, level_matches_role
from .grammar import PatternRule
from .predicates import (
    close_above,
    compression,
    engulfing,
    flat_side,
    gap_event,
    inside_bar,
    level_proximity,
    local_extreme_cluster,
    monotone_swings,
    near_vwap,
    pullback_depth,
    swing_label,
    volume_expansion,
    wick_rejection,
)

TIMEFRAMES_ALL: tuple[str, ...] = ("5m", "15m", "30m")

# ── objective, disclosed thresholds (TA-PATTERN-REFERENCE.md discipline: cite a
#    published number verbatim where one exists; otherwise say so plainly — never invent
#    a failure-rate stat) ──────────────────────────────────────────────────────────────
LEVEL_PROXIMITY_DOLLARS = 0.30      # matches backtest/lib/level_strength.py CONFLUENCE_PROXIMITY_USD
WICK_MIN_FRAC = 0.33
VOLUME_EXPANSION_MULT = 1.5
FLAT_TOLERANCE_DOLLARS = 0.20       # matches backtest/lib/watchers/level_memory.py TOUCH_TOL
FLAG_MAX_PULLBACK_PCT = 0.38        # common continuation heuristic -- NOT a Bulkowski stat (C.1: flags carry no rank)
FLAG_IMPULSE_VOL_MULT = 2.0
FLAG_SEQUENCE_BARS = 8
GAP_MIN_PCT = 0.0025                # matches backtest/lib/watchers/gap_and_go_watcher.py MIN_GAP
GAP_MAX_PCT = 0.015                 # matches backtest/lib/watchers/gap_and_go_watcher.py MAX_GAP
NR7_LOOKBACK = 7                    # Toby Crabel's "narrowest range of 7" -- no published failure-rate stat
NR7_BREAK_WINDOW = 6
VWAP_PROXIMITY_DOLLARS = 0.15
LOCAL_CLUSTER_TOLERANCE_DOLLARS = 0.20  # matches FLAT_TOLERANCE_DOLLARS -- same "same level" convention
LOCAL_CLUSTER_LOOKBACK_BARS = 8         # 40min on 5m bars -- covers both 07-21 (6-bar span) and 07-23 (7-bar span) anchors
LOCAL_CLUSTER_MIN_TOUCHES = 3           # C27 prescreen forced this up from 2 (NOISE-KILL, 100%days/8.5 fires-day) --
                                         # both anchors independently carry exactly 3 touches at this tolerance/lookback
                                         # (grid-searched: n_touches=3 is the MAX achievable while both anchors still
                                         # fire -- the bearish anchor's 3rd touch needs tolerance>=0.13, and even the
                                         # loosest still-anchor-passing config stayed NOISE-KILL on pct_days alone, so
                                         # n_touches was necessary-but-not-sufficient; see MIN_BODY_DOLLARS below)
LOCAL_CLUSTER_MIN_BODY_DOLLARS = 0.40   # engulfing()'s own geometry has NO minimum body size -- a large fraction of
                                         # its fires are small-body noise-band flips. Grid-searched discriminator: both
                                         # anchors' real bodies (0.769 bullish / 1.40 bearish) clear this with margin,
                                         # and it is what actually pushes pct_days_fired under the C27 80% NOISE-KILL
                                         # line (touches=3 alone stayed 91-99% NOISE-KILL across every tolerance tried)


# ── rule-local predicates (geometry specific enough to one rule that decomposing it
#    into the shared predicates.py library would strain "small and orthogonal" — see
#    PATTERN-GRAMMAR.md sec 2 note on this design choice) ──────────────────────────────

def _double_top_bottom_predicate(ctx: PatternContext, t: int) -> Optional[dict]:
    """Double bottom (bullish) / double top (bearish), anchored to a named level.
    Reuses ctx.structure.labeled_swings (the shared market-structure primitive) instead
    of re-scanning for local extrema the way crypto/lib/chart_patterns.py's
    double_bottom_detector/double_top_detector do internally — same geometry
    (2 swings within tolerance, neckline = extreme between them, close breaks the
    neckline), expressed over the grammar's shared swing read."""
    w = ctx.swing_window
    bar = ctx.bars[t]
    if t < 1:
        return None
    lows = [s for s in ctx.structure.labeled_swings if s.kind == "swing_low" and s.bar_index + w <= t]
    if len(lows) >= 2:
        l1, l2 = lows[-2], lows[-1]
        if l2.bar_index > l1.bar_index and abs(l1.price - l2.price) <= FLAT_TOLERANCE_DOLLARS:
            between = [b.high for b in ctx.bars[l1.bar_index + 1: l2.bar_index]]
            if between:
                neckline = max(between)
                near = any(
                    level_matches_role(lv, "support")
                    and abs(lv.price - min(l1.price, l2.price)) <= LEVEL_PROXIMITY_DOLLARS
                    for lv in ctx.levels_for(t)
                )
                if near and bar.close > neckline and ctx.bars[t - 1].close <= neckline:
                    return {
                        "bias": "bullish", "trigger_level": round(neckline, 2),
                        "low1": round(l1.price, 2), "low2": round(l2.price, 2),
                    }
    highs = [s for s in ctx.structure.labeled_swings if s.kind == "swing_high" and s.bar_index + w <= t]
    if len(highs) >= 2:
        h1, h2 = highs[-2], highs[-1]
        if h2.bar_index > h1.bar_index and abs(h1.price - h2.price) <= FLAT_TOLERANCE_DOLLARS:
            between = [b.low for b in ctx.bars[h1.bar_index + 1: h2.bar_index]]
            if between:
                neckline = min(between)
                near = any(
                    level_matches_role(lv, "resistance")
                    and abs(lv.price - max(h1.price, h2.price)) <= LEVEL_PROXIMITY_DOLLARS
                    for lv in ctx.levels_for(t)
                )
                if near and bar.close < neckline and ctx.bars[t - 1].close >= neckline:
                    return {
                        "bias": "bearish", "trigger_level": round(neckline, 2),
                        "high1": round(h1.price, 2), "high2": round(h2.price, 2),
                    }
    return None


def _rectangle_predicate(ctx: PatternContext, t: int) -> Optional[dict]:
    """Both sides flat (top AND bottom) -> a range; fires on a decisive break of
    EITHER side. Needs both levels simultaneously (to report the untouched side as
    context) so it composes as one rule-local function rather than all_of() branches
    that can't see each other's evidence."""
    if t < 1:
        return None
    top = flat_side(kind="swing_high", n_touches=2, tolerance=FLAT_TOLERANCE_DOLLARS)(ctx, t)
    bot = flat_side(kind="swing_low", n_touches=2, tolerance=FLAT_TOLERANCE_DOLLARS)(ctx, t)
    if top is None or bot is None:
        return None
    c0, c1 = ctx.bars[t].close, ctx.bars[t - 1].close
    if c0 > top["trigger_level"] and c1 <= top["trigger_level"]:
        return {"bias": "bullish", "trigger_level": top["trigger_level"], "range_floor": bot["trigger_level"]}
    if c0 < bot["trigger_level"] and c1 >= bot["trigger_level"]:
        return {"bias": "bearish", "trigger_level": bot["trigger_level"], "range_ceiling": top["trigger_level"]}
    return None


def _nr7_break_predicate(ctx: PatternContext, t: int) -> Optional[dict]:
    """NR7 (narrowest range of the trailing NR7_LOOKBACK bars) followed, within
    NR7_BREAK_WINDOW bars, by a decisive close beyond that narrow bar's own high/low.
    Mechanical/objective (Toby Crabel); TA-PATTERN-REFERENCE.md publishes no failure-rate
    stat for it (same "no published stat" treatment as sec C.8 price channels)."""
    lo_search = max(NR7_LOOKBACK - 1, t - NR7_BREAK_WINDOW)
    for s in range(t - 1, lo_search - 1, -1):
        window = ctx.bars[s - NR7_LOOKBACK + 1: s + 1]
        if len(window) < NR7_LOOKBACK:
            continue
        ranges = [b.high - b.low for b in window]
        if ranges[-1] != min(ranges):
            continue
        nr_bar = ctx.bars[s]
        c0 = ctx.bars[t].close
        if c0 > nr_bar.high:
            return {"bias": "bullish", "trigger_level": round(nr_bar.high, 2),
                    "nr7_bar_index": s, "bars_since_nr7": t - s}
        if c0 < nr_bar.low:
            return {"bias": "bearish", "trigger_level": round(nr_bar.low, 2),
                    "nr7_bar_index": s, "bars_since_nr7": t - s}
    return None


def _engulfing_at_level_predicate(ctx: PatternContext, t: int) -> Optional[dict]:
    """Bullish engulfing at support OR bearish engulfing at resistance — the two
    branches share zero state, so plain composition (engulfing + level_proximity per
    branch) is enough; kept as one rule-local function only to pick the matching
    branch's level_role rather than testing both roles against both directions."""
    bull = engulfing(direction="bullish")(ctx, t)
    if bull is not None:
        near = level_proximity(max_distance=LEVEL_PROXIMITY_DOLLARS, level_role="support")(ctx, t)
        if near is not None:
            return {"bias": "bullish", **near, **bull}
    bear = engulfing(direction="bearish")(ctx, t)
    if bear is not None:
        near = level_proximity(max_distance=LEVEL_PROXIMITY_DOLLARS, level_role="resistance")(ctx, t)
        if near is not None:
            return {"bias": "bearish", **near, **bear}
    return None


def _engulfing_at_swing_shelf_predicate(ctx: PatternContext, t: int) -> Optional[dict]:
    """Bullish engulfing at a 2-touch swing-LOW shelf, or bearish engulfing at a 2-touch
    swing-HIGH shelf -- DELIBERATELY DISTINCT from engulfing_at_level (which anchors to
    a NAMED daily support/resistance level from key-levels.json). This rule anchors to
    the INTRADAY swing structure itself (ctx.structure.labeled_swings via flat_side,
    the same double-top/bottom-neckline primitive double_top_bottom_at_level uses) --
    the exact vocabulary gap ENGULFING-AT-STRUCTURE-TRIGGER (queue.md, filed
    2026-07-23) named: J called an engulfing candle at a fresh intraday double-bottom/
    double-top shelf live on 2026-07-21 (bullish) and 2026-07-23 (bearish), and neither
    the plain engulfing_at_level rule (anchored to daily levels, not the intraday
    shelf) nor double_top_bottom_at_level (requires a neckline BREAK, not a same-bar
    engulfing reaction AT the shelf) covers that exact composition. Same
    zero-shared-state two-branch shape as _engulfing_at_level_predicate."""
    bar = ctx.bars[t]
    bull = engulfing(direction="bullish")(ctx, t)
    if bull is not None:
        shelf = flat_side(kind="swing_low", n_touches=2, tolerance=FLAT_TOLERANCE_DOLLARS)(ctx, t)
        if shelf is not None and abs(bar.close - shelf["trigger_level"]) <= LEVEL_PROXIMITY_DOLLARS:
            return {"bias": "bullish", "touch_spread": shelf["touch_spread"], **shelf, **bull}
    bear = engulfing(direction="bearish")(ctx, t)
    if bear is not None:
        shelf = flat_side(kind="swing_high", n_touches=2, tolerance=FLAT_TOLERANCE_DOLLARS)(ctx, t)
        if shelf is not None and abs(bar.close - shelf["trigger_level"]) <= LEVEL_PROXIMITY_DOLLARS:
            return {"bias": "bearish", "touch_spread": shelf["touch_spread"], **shelf, **bear}
    return None


def _engulfing_at_local_cluster_predicate(ctx: PatternContext, t: int) -> Optional[dict]:
    """Bullish engulfing at a rolling-K-bar LOW cluster, or bearish engulfing at a
    rolling-K-bar HIGH cluster -- the follow-up primitive named in
    engulfing_at_swing_shelf's own anchor notes (queue.md ENGULFING-AT-STRUCTURE-
    TRIGGER, 2026-07-23): flat_side()/labeled_swings' pivot-confirmation timescale
    cannot see J's two exhibits (both resolve in 1-5 bars, ~8 cents apart); this rule
    swaps that anchor for local_extreme_cluster(), which reads raw ctx.bars[<=t]
    directly with zero confirmation lag. Same zero-shared-state two-branch shape as
    _engulfing_at_swing_shelf_predicate/_engulfing_at_level_predicate."""
    bar = ctx.bars[t]
    bull = engulfing(direction="bullish")(ctx, t)
    if bull is not None and bull["engulfed_body_dollars"] >= LOCAL_CLUSTER_MIN_BODY_DOLLARS:
        cluster = local_extreme_cluster(
            kind="low", n_touches=LOCAL_CLUSTER_MIN_TOUCHES, tolerance=LOCAL_CLUSTER_TOLERANCE_DOLLARS, lookback=LOCAL_CLUSTER_LOOKBACK_BARS,
        )(ctx, t)
        # NOTE: proximity is checked against the bar's LOW (the wick that touches the
        # cluster), not its close -- an engulfing reversal bar's close is, BY
        # DEFINITION, on the far side of the level from the wick that reacted to it
        # (same reasoning as wick_rejection's own near-level convention). Checking
        # close here (as engulfing_at_swing_shelf/engulfing_at_level both do, since
        # their anchor is a NAMED level the bar merely needs to be "at", not
        # necessarily wick into) silently fails the exact reversal-wick shape this
        # rule targets -- found via this fire's own anchor falsification, not assumed.
        if cluster is not None and abs(bar.low - cluster["trigger_level"]) <= LEVEL_PROXIMITY_DOLLARS:
            return {"bias": "bullish", **cluster, **bull}
    bear = engulfing(direction="bearish")(ctx, t)
    if bear is not None and bear["engulfed_body_dollars"] >= LOCAL_CLUSTER_MIN_BODY_DOLLARS:
        cluster = local_extreme_cluster(
            kind="high", n_touches=LOCAL_CLUSTER_MIN_TOUCHES, tolerance=LOCAL_CLUSTER_TOLERANCE_DOLLARS, lookback=LOCAL_CLUSTER_LOOKBACK_BARS,
        )(ctx, t)
        if cluster is not None and abs(bar.high - cluster["trigger_level"]) <= LEVEL_PROXIMITY_DOLLARS:
            return {"bias": "bearish", **cluster, **bear}
    return None


def _island_reversal_predicate(ctx: PatternContext, t: int, *, isolation_bars: int = 12) -> Optional[dict]:
    """Gap AWAY from a level (island forms) -> isolated for up to `isolation_bars` ->
    gap BACK the other way. The loosest-defined rule in this registry by design (real
    intraday gaps are rare outside the session open — TA-PATTERN-REFERENCE.md sec D.1/D.2
    caveat) -- expect TOO-RARE on the prescreen; that is a legitimate, expected finding,
    not a design failure (see PATTERN-GRAMMAR.md sec 2)."""
    later = gap_event(min_gap_pct=GAP_MIN_PCT, max_gap_pct=GAP_MAX_PCT * 3, direction="any")(ctx, t)
    if later is None:
        return None
    later_dir = later["gap_direction"]
    opposite = "down" if later_dir == "up" else "up"
    lo = max(0, t - isolation_bars)
    for s in range(t - 1, lo - 1, -1):
        earlier = gap_event(min_gap_pct=GAP_MIN_PCT, max_gap_pct=GAP_MAX_PCT * 3, direction=opposite)(ctx, s)
        if earlier is None:
            continue
        island_lo = min(b.low for b in ctx.bars[s:t])
        island_hi = max(b.high for b in ctx.bars[s:t])
        if ctx.bars[t].open > island_hi or ctx.bars[t].open < island_lo:
            return {
                "bias": "bearish" if later_dir == "down" else "bullish",
                "trigger_level": earlier["trigger_level"],
                "island_start_bar": s, "island_low": round(island_lo, 2), "island_high": round(island_hi, 2),
                "gap_out_pct": later["gap_pct"], "gap_in_pct": earlier["gap_pct"],
            }
    return None


def _flag_pullback_predicate() -> Predicate:
    return within_n_bars_after(
        later=all_of(
            pullback_depth(max_pct=FLAG_MAX_PULLBACK_PCT, lookback=12),
            near_vwap(max_distance=VWAP_PROXIMITY_DOLLARS),
        ),
        earlier=volume_expansion(mult=FLAG_IMPULSE_VOL_MULT, lookback=10),
        n=FLAG_SEQUENCE_BARS,
    )


# ── the registry ────────────────────────────────────────────────────────────────────

REGISTRY: tuple[PatternRule, ...] = (
    PatternRule(
        name="failed_break_spring",
        tier=1,
        timeframes=TIMEFRAMES_ALL,
        direction="bullish",
        predicate=wick_rejection(
            side="lower", min_wick_frac=WICK_MIN_FRAC,
            at_level_role="support", max_level_distance=LEVEL_PROXIMITY_DOLLARS,
        ),
        citation="TA-PATTERN-REFERENCE.md sec D.4 (pin bar geometry) + crypto/lib/chart_patterns.py"
                 "::failed_breakdown_wick (existing named-level-anchored wick-reject primitive)."
                 " 'Spring' is standard Wyckoff vocabulary for a failed breakdown at support;"
                 " no failure-rate stat is published or invented here.",
        thresholds={"level_proximity_dollars": LEVEL_PROXIMITY_DOLLARS, "wick_min_frac": WICK_MIN_FRAC},
        description="Bar wicks below a support level (within $0.30) and closes back above it with "
                    "a lower wick >=33% of the bar's range -- a failed breakdown / Wyckoff spring.",
    ),
    PatternRule(
        name="double_top_bottom_at_level",
        tier=2,
        timeframes=TIMEFRAMES_ALL,
        direction="bidirectional",
        predicate=_double_top_bottom_predicate,
        citation="TA-PATTERN-REFERENCE.md sec B.1 (double top geometry + Bulkowski BE-failure 25%"
                 " Adam&Adam / 20% Eve&Eve, explicitly flagged 'Marginal' intraday applicability --"
                 " that stat is NOT claimed here, daily-only) + crypto/lib/chart_patterns.py"
                 "::double_bottom_detector/double_top_detector (same neckline-reclaim geometry,"
                 " re-expressed over the shared market-structure swing read instead of a bespoke"
                 " local-extrema scan).",
        thresholds={"swing_tolerance_dollars": FLAT_TOLERANCE_DOLLARS, "level_proximity_dollars": LEVEL_PROXIMITY_DOLLARS},
        description="Two swing lows (or highs) within $0.20 of each other, near a named support "
                    "(or resistance) level, with a decisive close through the neckline between them.",
    ),
    PatternRule(
        name="neckline_base_break",
        tier=1,
        timeframes=TIMEFRAMES_ALL,
        direction="bullish",
        predicate=all_of(
            flat_side(kind="swing_low", n_touches=3, tolerance=FLAT_TOLERANCE_DOLLARS),
            close_above(level_role="any", require_cross=True, max_distance=LEVEL_PROXIMITY_DOLLARS * 2),
            volume_expansion(mult=VOLUME_EXPANSION_MULT),
        ),
        citation="TA-PATTERN-REFERENCE.md sec B.2 (inverse H&S neckline + StockCharts' mandatory"
                 " volume-expansion-on-breakout rule for bottoming patterns) + sec C.3 (ascending"
                 " triangle's >=3-touch flat-side convention).",
        thresholds={
            "base_touches": 3, "flat_tolerance_dollars": FLAT_TOLERANCE_DOLLARS,
            "level_proximity_dollars": LEVEL_PROXIMITY_DOLLARS * 2, "volume_mult": VOLUME_EXPANSION_MULT,
        },
        description="3+ roughly-equal swing lows form a base under a named level; a volume-backed "
                    "(>=1.5x) close breaks above that level.",
    ),
    PatternRule(
        name="triangle_ascending",
        tier=1,
        timeframes=TIMEFRAMES_ALL,
        direction="bullish",
        predicate=then_break(
            base=all_of(
                flat_side(kind="swing_high", n_touches=2, tolerance=FLAT_TOLERANCE_DOLLARS),
                monotone_swings(kind="swing_low", non_decreasing=True, n=2),
            ),
            side="above",
        ),
        citation="TA-PATTERN-REFERENCE.md sec C.3 (flat top + rising lows; Bulkowski BE-failure 17%"
                 " up / 38% down, the best up-breakout in sec C; breaks up 63% of the time).",
        thresholds={"flat_tolerance_dollars": FLAT_TOLERANCE_DOLLARS, "min_touches": 2},
        description="A flat swing-high ceiling (<=2 touches within $0.20) with rising swing lows, "
                    "resolved by a close above the ceiling.",
    ),
    PatternRule(
        name="triangle_descending",
        tier=1,
        timeframes=TIMEFRAMES_ALL,
        direction="bearish",
        predicate=then_break(
            base=all_of(
                flat_side(kind="swing_low", n_touches=2, tolerance=FLAT_TOLERANCE_DOLLARS),
                monotone_swings(kind="swing_high", non_decreasing=False, n=2),
            ),
            side="below",
        ),
        citation="TA-PATTERN-REFERENCE.md sec C.4 (flat bottom + falling highs; Bulkowski BE-failure"
                 " 22% up / 23% down; usually breaks down).",
        thresholds={"flat_tolerance_dollars": FLAT_TOLERANCE_DOLLARS, "min_touches": 2},
        description="A flat swing-low floor (<=2 touches within $0.20) with falling swing highs, "
                    "resolved by a close below the floor.",
    ),
    PatternRule(
        name="flag_pullback_continuation",
        tier=1,
        timeframes=TIMEFRAMES_ALL,
        direction="bidirectional",
        predicate=_flag_pullback_predicate(),
        citation="TA-PATTERN-REFERENCE.md sec C.1 (bull/bear flag; Bulkowski BE-failure 44%/45%,"
                 " 'not ranked' -- explicitly flagged 'Strong' for intraday applicability, the"
                 " primary Section-C candidate for a 0DTE detector).",
        thresholds={
            "impulse_volume_mult": FLAG_IMPULSE_VOL_MULT, "max_pullback_pct": FLAG_MAX_PULLBACK_PCT,
            "vwap_proximity_dollars": VWAP_PROXIMITY_DOLLARS, "sequence_window_bars": FLAG_SEQUENCE_BARS,
        },
        description="A volume-backed (>=2x) impulse bar, followed within 8 bars by a <=38% pullback "
                    "that lands within $0.15 of session VWAP.",
    ),
    PatternRule(
        name="rectangle_range_break",
        tier=1,
        timeframes=TIMEFRAMES_ALL,
        direction="bidirectional",
        predicate=_rectangle_predicate,
        citation="TA-PATTERN-REFERENCE.md sec C.8 (price channel / flat-channel-as-rectangle cross-"
                 "reference) + StockCharts' Rectangle page (both sides flat, breaks either way)."
                 " Bulkowski publishes NO stat for channels -- none is claimed here.",
        thresholds={"flat_tolerance_dollars": FLAT_TOLERANCE_DOLLARS, "min_touches_per_side": 2},
        description="Both a flat swing-high ceiling AND a flat swing-low floor are present; fires "
                    "on a decisive close through either side.",
    ),
    PatternRule(
        name="inside_day_nr7_break",
        tier=2,
        timeframes=TIMEFRAMES_ALL,
        direction="bidirectional",
        predicate=_nr7_break_predicate,
        citation="Toby Crabel's NR7 ('narrowest range of the last 7 bars') -- standard, purely"
                 " mechanical intraday-compression vocabulary. No published failure-rate stat"
                 " (same treatment as TA-PATTERN-REFERENCE.md sec C.8's price channel: disclosed"
                 " as unmeasured rather than invented).",
        thresholds={"nr7_lookback": NR7_LOOKBACK, "break_window_bars": NR7_BREAK_WINDOW},
        description="A bar with the narrowest range of its own trailing 7 bars, followed within 6 "
                    "bars by a decisive close beyond that narrow bar's high/low.",
    ),
    PatternRule(
        name="wedge_rising_into_resistance",
        tier=2,
        timeframes=TIMEFRAMES_ALL,
        direction="bearish",
        predicate=then_break(
            # NOTE: all_of merges evidence via dict.update() in argument order -- listing
            # swing_high first then swing_low means swing_low's trigger_level (the rising
            # SUPPORT line's current point) wins the "trigger_level" key, which is exactly
            # the level then_break(side="below") needs to check (see combinators.py).
            base=all_of(
                monotone_swings(kind="swing_high", non_decreasing=True, n=3),
                monotone_swings(kind="swing_low", non_decreasing=True, n=2),
            ),
            side="below",
        ),
        citation="TA-PATTERN-REFERENCE.md sec C.6 (rising wedge -- BEARISH bias despite the upward"
                 " slope; Bulkowski BE-failure 19% up / 51% down -- explicitly flagged as his"
                 " WORST-ranked pattern (36/36) for the down-breakout; doc: 'do not over-weight a"
                 " wedge break intraday; require corroboration'). This rule fires on that exact"
                 " down-break, so the 51% failure-rate caveat is disclosed prominently in the doc,"
                 " not silently dropped.",
        thresholds={"min_swing_highs": 3, "min_swing_lows": 2},
        description="Both swing highs AND swing lows rising (a converging, upward-tilted channel), "
                    "resolved bearish by a close below the most recent rising swing low.",
    ),
    PatternRule(
        name="engulfing_at_level",
        tier=1,
        timeframes=TIMEFRAMES_ALL,
        direction="bidirectional",
        predicate=_engulfing_at_level_predicate,
        citation="Standard OHLC engulfing-candle geometry (not yet a TA-PATTERN-REFERENCE.md"
                 " subsection; closest documented cousin is sec D.3 Harami -- opposite containment"
                 " direction) + level_proximity, matching the existing named-level-anchored"
                 " convention crypto/lib/chart_patterns.py::rejection_at_level established.",
        thresholds={"level_proximity_dollars": LEVEL_PROXIMITY_DOLLARS},
        description="A bullish engulfing candle within $0.30 of a support level, or a bearish "
                    "engulfing candle within $0.30 of a resistance level.",
    ),
    PatternRule(
        name="engulfing_at_swing_shelf",
        tier=2,
        timeframes=TIMEFRAMES_ALL,
        direction="bidirectional",
        predicate=_engulfing_at_swing_shelf_predicate,
        citation="Standard OHLC engulfing-candle geometry (see engulfing_at_level's citation) +"
                 " the same intraday 2-touch flat-swing-shelf primitive"
                 " double_top_bottom_at_level/rectangle_range_break/triangle_* use"
                 " (flat_side over ctx.structure.labeled_swings) -- composed here as an ANCHOR"
                 " for the candle instead of a neckline-break level. Filed from a live-tape"
                 " gap: queue.md ENGULFING-AT-STRUCTURE-TRIGGER (2026-07-23), J called this"
                 " exact composition on 2 separate days, mirror-symmetric, both directions.",
        thresholds={
            "flat_tolerance_dollars": FLAT_TOLERANCE_DOLLARS,
            "shelf_proximity_dollars": LEVEL_PROXIMITY_DOLLARS,
        },
        description="A bullish engulfing candle within $0.30 of a fresh 2-touch intraday swing-low "
                    "shelf, or a bearish engulfing candle within $0.30 of a fresh 2-touch intraday "
                    "swing-high shelf -- an engulfing candle reacting AT the shelf itself, not a "
                    "named daily level and not a neckline break.",
        anchors=(
            {
                "date": "2026-07-21", "time_et": "11:05", "bias": "bullish",
                "expected_fire": False,
                "note": "J's original bullish exhibit this rule was built to cover. VERIFIED "
                        "(post-ship OP-33 falsification, same day): does NOT fire. Root cause "
                        "pinned, not vibes -- flat_side()/labeled_swings (the shared swing "
                        "primitive every swing-family rule composes on) never registers J's tight "
                        "touch cluster (~$0.08 apart, 5min apart) as 2+ DISTINCT confirmed pivots "
                        "at its current confirmation timescale. Follow-up: a new rolling-K-bar "
                        "local-extreme-cluster primitive (queue.md ENGULFING-AT-STRUCTURE-TRIGGER, "
                        "_lesson-inbox/2026-07-23-swing-primitive-timescale-bounds-every-composed-"
                        "rule.md) must be falsified against this exact bar BEFORE any pre-reg is "
                        "built on it.",
            },
            {
                "date": "2026-07-23", "time_et": "10:40", "bias": "bearish",
                "expected_fire": False,
                "note": "J's mirror-symmetric bearish exhibit, same day this rule shipped. Same "
                        "root cause as the 07-21 anchor above -- see that note.",
            },
        ),
    ),
    PatternRule(
        name="engulfing_at_local_cluster",
        tier=2,
        timeframes=TIMEFRAMES_ALL,
        direction="bidirectional",
        predicate=_engulfing_at_local_cluster_predicate,
        citation="Standard OHLC engulfing-candle geometry (see engulfing_at_level's citation) +"
                 " local_extreme_cluster (predicates.py sec 12b, NEW 2026-07-23 -- no published"
                 " TA-PATTERN-REFERENCE.md citation; a raw-OHLC rolling-window cluster check built"
                 " specifically because flat_side()/labeled_swings' pivot-confirmation timescale"
                 " cannot see fast/tight double-top-or-bottom clusters). Filed as the direct"
                 " follow-up engulfing_at_swing_shelf's own anchor notes named: queue.md"
                 " ENGULFING-AT-STRUCTURE-TRIGGER (2026-07-23), same 2 live-tape exhibits. The"
                 " min-body-dollars floor is a grid-searched discriminator (this fire), not a"
                 " published stat -- disclosed as such, see LOCAL_CLUSTER_MIN_BODY_DOLLARS comment.",
        thresholds={
            "local_cluster_tolerance_dollars": LOCAL_CLUSTER_TOLERANCE_DOLLARS,
            "local_cluster_lookback_bars": LOCAL_CLUSTER_LOOKBACK_BARS,
            "local_cluster_min_touches": LOCAL_CLUSTER_MIN_TOUCHES,
            "local_cluster_min_body_dollars": LOCAL_CLUSTER_MIN_BODY_DOLLARS,
            "shelf_proximity_dollars": LEVEL_PROXIMITY_DOLLARS,
        },
        description="A bullish engulfing candle (body >= $0.40) within $0.30 of a rolling 8-bar LOW "
                    "cluster (>=3 bars within $0.20 of bar t's own low), or a bearish engulfing "
                    "candle (body >= $0.40) within $0.30 of a rolling 8-bar HIGH cluster -- the "
                    "no-pivot-confirmation-lag sibling of engulfing_at_swing_shelf, built to catch "
                    "fast/tight double-tops and double-bottoms the swing-pivot family structurally "
                    "cannot see. min_touches=3 and min_body=$0.40 are BOTH load-bearing: the bare "
                    "engulfing+cluster composition (2 touches, no body floor) is C27 NOISE-KILL "
                    "(fires 92-99% of days across every tolerance tried) -- these are the tightest "
                    "settings found (grid search, this fire) that still keep BOTH live-tape anchors "
                    "firing.",
        anchors=(
            {
                "date": "2026-07-21", "time_et": "11:05", "bias": "bullish",
                "expected_fire": True,
                "note": "J's original bullish exhibit (see engulfing_at_swing_shelf's matching "
                        "anchor for the full falsification history of WHY the swing-pivot version "
                        "doesn't fire here). VERIFIED this fire (pattern_anchor_verify.py, before "
                        "committing): local_extreme_cluster(kind='low', lookback=8, tolerance=0.20) "
                        "DOES register the 10:40/11:00/11:05 tri-touch cluster (~8c apart) that "
                        "flat_side's confirmed-pivot read misses -- fires as declared.",
            },
            {
                "date": "2026-07-23", "time_et": "10:40", "bias": "bearish",
                "expected_fire": True,
                "note": "J's mirror-symmetric bearish exhibit. VERIFIED this fire "
                        "(pattern_anchor_verify.py, before committing): local_extreme_cluster"
                        "(kind='high', lookback=8, tolerance=0.20) registers the adjacent-bar "
                        "10:35/10:40 double-top (~8c apart) -- fires as declared.",
            },
        ),
        # C27 PRESCREEN VERDICT (this fire, full history 2025-01-02..2026-07-22, 5m):
        # TESTABLE -- 33.3% days, 0.460 fires/day, 9.66/month, recent-90d stable (no
        # drift). Reached only AFTER adding local_cluster_min_touches=3 (from 2) +
        # local_cluster_min_body_dollars=0.40 (from none) -- the bare composition was
        # C27 NOISE-KILL (92-99% days across every tolerance grid-searched). Next step
        # (not this fire, per rail 3): a frozen pre-reg + real-fills replay through
        # exit_manager_walk, per the item's original BUILD spec (queue.md
        # ENGULFING-AT-STRUCTURE-TRIGGER).
    ),
    PatternRule(
        name="island_reversal",
        tier=2,
        timeframes=TIMEFRAMES_ALL,
        direction="bidirectional",
        predicate=_island_reversal_predicate,
        citation="Standard 'island reversal' vocabulary (two gaps in opposite directions isolating a"
                 " small range) + backtest/lib/watchers/gap_and_go_watcher.py's gap math/thresholds."
                 " TA-PATTERN-REFERENCE.md sec D (candlestick preface) explicitly notes literal"
                 " intraday gaps are rare except at the session open -- disclosed here as the"
                 " reason this rule is expected to be the registry's rarest firer.",
        thresholds={
            "gap_min_pct": GAP_MIN_PCT, "gap_max_pct_island": GAP_MAX_PCT * 3, "isolation_window_bars": 12,
        },
        description="A session-open gap away from a level, an isolated run of sessions that never "
                    "trade back through that gap, then a later opposite-direction gap back through it.",
    ),
)


REGISTRY_BY_NAME: dict = {rule.name: rule for rule in REGISTRY}

assert len(REGISTRY_BY_NAME) == len(REGISTRY), "registry.py: duplicate rule name"
