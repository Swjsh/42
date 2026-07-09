"""registry.py — the seeded Tier-1/2 pattern-grammar rules.

11 rules total (the brief's 10-item list names "triangle_ascending/descending" via a
slash, which TA-PATTERN-REFERENCE.md sec C.3/C.4 treats as two genuinely different
patterns — different bias, different Bulkowski stats, different predicate composition —
so this registry seeds BOTH as separate entries; every other brief item maps 1:1).

Full citation table + Tier-1/2 rationale + the "why 15 predicates not exactly 10-14, why
these 11 rules, what's deliberately excluded (harmonics/Elliott)" design discussion lives
in markdown/research/PATTERN-GRAMMAR.md sec 2. This file is the executable contract; the
doc is the reasoning.

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
