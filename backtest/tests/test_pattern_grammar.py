"""Tests for backtest/lib/patterns/* — the pattern-grammar C6 safety net.

Four required guard categories (per the pattern-grammar build spec):
  1. C6 bite       -- a future bar mutated into a predicate's blind spot must NOT
                       change that predicate's result (and the harness itself must
                       provably CATCH a violation when one is deliberately introduced).
  2. Determinism   -- same bars -> same fires, every time.
  3. Registry schema -- the 11 seeded rules are well-formed and exactly the intended set.
  4. Predicate unit tests -- a representative sample of the 15 domain predicates on
                       hand-built fixtures with known true/false outcomes.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_pattern_grammar.py -q
"""
from __future__ import annotations

import datetime as dt
import random
import sys
from pathlib import Path
from typing import Optional

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backtest"))

from crypto.lib.bar import Bar  # noqa: E402
from lib.patterns import (  # noqa: E402
    LevelLike,
    PatternContext,
    PatternRule,
    REGISTRY,
    REGISTRY_BY_NAME,
    RULE_DIRECTIONS,
    all_of,
    evaluate_rule,
    evaluate_rule_over_range,
    level_matches_role,
    within_n_bars_after,
)
from lib.patterns.grammar import RULE_TIERS  # noqa: E402
from lib.patterns.combinators import Predicate, negate, then_break  # noqa: E402
from lib.patterns.predicates import (  # noqa: E402
    close_above,
    close_below,
    compression,
    engulfing,
    gap_event,
    inside_bar,
    level_proximity,
    near_vwap,
    swing_label,
    volume_expansion,
    wick_rejection,
)

EXPECTED_RULE_NAMES = {
    "failed_break_spring",
    "double_top_bottom_at_level",
    "neckline_base_break",
    "triangle_ascending",
    "triangle_descending",
    "flag_pullback_continuation",
    "rectangle_range_break",
    "inside_day_nr7_break",
    "wedge_rising_into_resistance",
    "engulfing_at_level",
    "island_reversal",
}


# ── bar-building helpers ───────────────────────────────────────────────────────

def _mk_bar(day: dt.date, minute_offset: int, o: float, h: float, l: float, c: float,
            v: float = 10_000.0) -> Bar:
    t0 = dt.datetime.combine(day, dt.time(9, 30), tzinfo=dt.timezone.utc)
    return Bar(open_time=t0 + dt.timedelta(minutes=5 * minute_offset),
               open=o, high=h, low=l, close=c, volume=v, granularity_seconds=300, source="test")


def _trading_days(n: int, base: dt.date = dt.date(2025, 1, 6)) -> list[dt.date]:
    out: list[dt.date] = []
    d = 0
    while len(out) < n:
        day = base + dt.timedelta(days=d)
        d += 1
        if day.weekday() < 5:
            out.append(day)
    return out


def _multi_day(days: int, bars_per_day: int, *, seed: int = 1234567, seed_price: float = 735.0) -> list[Bar]:
    """A reasonably realistic, fully-deterministic multi-day random-walk bar sequence
    (local `random.Random(seed)` instance -- never touches the global `random` module,
    so this can never interfere with / be interfered with by other tests)."""
    rng = random.Random(seed)
    bars: list[Bar] = []
    price = seed_price
    for day in _trading_days(days):
        if rng.random() < 0.3:
            price *= 1 + rng.uniform(-0.006, 0.006)
        o = price
        for i in range(bars_per_day):
            drift = rng.uniform(-0.15, 0.15)
            if rng.random() < 0.05:
                drift *= 4
            c = max(1.0, o + drift)
            h = max(o, c) + abs(rng.uniform(0, 0.10))
            l = min(o, c) - abs(rng.uniform(0, 0.10))
            v = rng.uniform(5000, 20000)
            if rng.random() < 0.03:
                v *= rng.uniform(2, 5)
            bars.append(_mk_bar(day, i, round(o, 2), round(h, 2), round(l, 2), round(c, 2), round(v, 0)))
            o = c
        price = o
    return bars


def _fixed_levels_by_date(bars: list[Bar], *, below: float = 3.0, above: float = 3.0) -> dict:
    """Deterministic, bars-independent-ish level set: two levels per session date,
    `below`/`above` dollars from that day's own first bar open. Held FIXED across a C6
    mutation (same dict reused for both the original and every mutated context) so the
    C6 tests isolate exactly what they claim to: predicate reads of ctx.bars/.structure/
    .vwap/.bandwidth, not level-building causality (a separate, already-documented
    concern -- see context.py's module docstring)."""
    dates = sorted({b.open_time.date() for b in bars})
    first_open_by_date = {}
    for b in bars:
        d = b.open_time.date()
        if d not in first_open_by_date:
            first_open_by_date[d] = b.open
    out = {}
    for i, d in enumerate(dates):
        base = first_open_by_date[d]
        out[d] = (
            LevelLike(price=round(base - below, 2), role="support", role_flips=1 if i % 2 == 0 else 0),
            LevelLike(price=round(base + above, 2), role="resistance", role_flips=1 if i % 3 == 0 else 0),
        )
    return out


def _mutate_tail(bars: list[Bar], *, keep_upto: int, extreme: str) -> list[Bar]:
    """New bars list identical to `bars` through index `keep_upto`, with every bar AFTER
    it replaced by an adversarial extreme (huge volume spike to $5000 or crash to $1) --
    the "future bar in a predicate REDs" mutation used by the C6 tests below."""
    out = list(bars[: keep_upto + 1])
    for i in range(keep_upto + 1, len(bars)):
        old = bars[i]
        level = 5000.0 if extreme == "up" else 1.0
        out.append(Bar(
            open_time=old.open_time, open=level, high=level + 0.5, low=max(0.01, level - 0.5),
            close=level, volume=old.volume * 50, granularity_seconds=old.granularity_seconds,
            source=old.source,
        ))
    return out


# ── shared fixtures (module-scoped: built once, reused across all 11 parametrized rules) ──

@pytest.fixture(scope="module")
def c6_bars() -> list[Bar]:
    return _multi_day(20, 30)


@pytest.fixture(scope="module")
def c6_levels(c6_bars) -> dict:
    return _fixed_levels_by_date(c6_bars)


@pytest.fixture(scope="module")
def c6_ctx_orig(c6_bars, c6_levels) -> PatternContext:
    return PatternContext.build(c6_bars, levels_by_date=c6_levels)


CHECK_POINTS = [60, 150, 240, 330, 420, 510]


@pytest.fixture(scope="module")
def c6_ctx_mutants(c6_bars, c6_levels) -> dict:
    out = {}
    for t in CHECK_POINTS:
        if t >= len(c6_bars) - 1:
            continue
        for extreme in ("up", "down"):
            mutated = _mutate_tail(c6_bars, keep_upto=t, extreme=extreme)
            out[(t, extreme)] = PatternContext.build(mutated, levels_by_date=c6_levels)
    return out


# ── 1. C6 bite ─────────────────────────────────────────────────────────────────

class TestC6NoLookahead:
    def test_harness_has_teeth_on_a_deliberately_broken_predicate(self, c6_bars, c6_levels, c6_ctx_orig):
        """Prove the mutate-tail harness actually CATCHES a look-ahead violation before
        trusting it to clear the real registry below."""
        t = CHECK_POINTS[2]

        def _peeks_ahead(ctx: PatternContext, tt: int) -> Optional[dict]:
            if tt + 3 >= len(ctx.bars):
                return None
            return {"future_close": ctx.bars[tt + 3].close}  # illegal: reads beyond tt

        r_orig = _peeks_ahead(c6_ctx_orig, t)
        mutated = _mutate_tail(c6_bars, keep_upto=t, extreme="up")
        ctx_mut = PatternContext.build(mutated, levels_by_date=c6_levels)
        r_mut = _peeks_ahead(ctx_mut, t)
        assert r_orig != r_mut, "mutate-tail harness failed to catch a future-peeking predicate"

    @pytest.mark.parametrize("rule", REGISTRY, ids=[r.name for r in REGISTRY])
    def test_registry_rules_are_lookahead_safe(self, rule, c6_bars, c6_ctx_orig, c6_ctx_mutants):
        for t in CHECK_POINTS:
            if t >= len(c6_bars) - 1:
                continue
            r_orig = evaluate_rule(rule, c6_ctx_orig, t, timeframe="5m")
            for extreme in ("up", "down"):
                ctx_mut = c6_ctx_mutants[(t, extreme)]
                r_mut = evaluate_rule(rule, ctx_mut, t, timeframe="5m")
                assert r_orig == r_mut, (
                    f"{rule.name} @ t={t} ({extreme}-mutated future bars): LOOK-AHEAD VIOLATION.\n"
                    f"  orig={r_orig}\n  mutated={r_mut}"
                )


# ── 2. determinism ─────────────────────────────────────────────────────────────

class TestDeterminism:
    @pytest.mark.parametrize("rule", REGISTRY, ids=[r.name for r in REGISTRY])
    def test_same_bars_same_fires(self, rule, c6_bars, c6_levels):
        ctx_a = PatternContext.build(c6_bars, levels_by_date=c6_levels)
        ctx_b = PatternContext.build(c6_bars, levels_by_date=c6_levels)
        hits_a = evaluate_rule_over_range(rule, ctx_a, timeframe="5m")
        hits_b = evaluate_rule_over_range(rule, ctx_b, timeframe="5m")
        assert hits_a == hits_b
        # re-run a third time from the SAME already-built context to catch any
        # predicate that mutates something (e.g. a stray module-level cache).
        hits_c = evaluate_rule_over_range(rule, ctx_a, timeframe="5m")
        assert hits_a == hits_c


# ── 3. registry schema ─────────────────────────────────────────────────────────

class TestRegistrySchema:
    def test_exactly_eleven_rules_with_the_expected_names(self):
        assert len(REGISTRY) == 11
        assert {r.name for r in REGISTRY} == EXPECTED_RULE_NAMES

    def test_names_unique(self):
        names = [r.name for r in REGISTRY]
        assert len(names) == len(set(names))
        assert REGISTRY_BY_NAME.keys() == set(names)

    @pytest.mark.parametrize("rule", REGISTRY, ids=[r.name for r in REGISTRY])
    def test_every_rule_well_formed(self, rule):
        assert rule.tier in RULE_TIERS
        assert rule.direction in RULE_DIRECTIONS
        assert len(rule.timeframes) > 0
        assert set(rule.timeframes).issubset({"5m", "15m", "30m"})
        assert callable(rule.predicate)
        assert isinstance(rule.thresholds, dict) and len(rule.thresholds) > 0
        assert isinstance(rule.citation, str) and len(rule.citation) > 20
        assert isinstance(rule.description, str) and len(rule.description) > 10

    def test_tier_split_matches_intraday_applicability_design(self):
        """Locks the Tier-1 (7) / Tier-2 (4) split documented in
        markdown/research/PATTERN-GRAMMAR.md sec 2 -- a change here should be a
        deliberate doc-and-code edit together, not a silent drift."""
        tier1 = {r.name for r in REGISTRY if r.tier == 1}
        tier2 = {r.name for r in REGISTRY if r.tier == 2}
        assert tier1 == {
            "failed_break_spring", "neckline_base_break", "triangle_ascending",
            "triangle_descending", "flag_pullback_continuation", "rectangle_range_break",
            "engulfing_at_level",
        }
        assert tier2 == {
            "double_top_bottom_at_level", "inside_day_nr7_break",
            "wedge_rising_into_resistance", "island_reversal",
        }

    def test_bidirectional_rule_predicate_must_supply_bias(self, c6_bars, c6_levels):
        """Runtime contract check (grammar.py::evaluate_rule): a bidirectional rule
        whose predicate fires WITHOUT a resolved bias is an authoring bug, not a
        silent None -- must raise loudly."""
        broken = PatternRule(
            name="_test_broken_bidirectional", tier=1, timeframes=("5m",),
            direction="bidirectional",
            predicate=lambda ctx, t: {"trigger_level": 1.0},  # missing "bias"
            citation="test-only", thresholds={"x": 1}, description="test-only",
        )
        ctx = PatternContext.build(c6_bars, levels_by_date=c6_levels)
        with pytest.raises(ValueError, match="bias"):
            evaluate_rule(broken, ctx, 50, timeframe="5m")

    def test_bad_tier_rejected(self):
        with pytest.raises(ValueError):
            PatternRule(name="x", tier=3, timeframes=("5m",), direction="bullish",
                        predicate=lambda ctx, t: None, citation="c", thresholds={"a": 1}, description="d")

    def test_missing_thresholds_rejected(self):
        with pytest.raises(ValueError):
            PatternRule(name="x", tier=1, timeframes=("5m",), direction="bullish",
                        predicate=lambda ctx, t: None, citation="c", thresholds={}, description="d")


# ── 4. predicate unit tests (representative sample, hand-built fixtures) ───────

class TestPredicateUnits:
    def test_volume_expansion_fires_only_above_mult(self):
        day = _trading_days(1)[0]
        bars = [_mk_bar(day, i, 100, 100.5, 99.5, 100, v=1000.0) for i in range(10)]
        bars.append(_mk_bar(day, 10, 100, 100.5, 99.5, 100, v=1600.0))  # 1.6x avg(1000)
        ctx = PatternContext.build(bars)
        pred = volume_expansion(lookback=10, mult=1.5)
        assert pred(ctx, 10) is not None
        assert pred(ctx, 10)["volume_mult"] == pytest.approx(1.6, abs=0.01)
        assert pred(ctx, 9) is None  # only 9 prior bars -- insufficient lookback

    def test_engulfing_bullish_requires_containment_and_color_flip(self):
        day = _trading_days(1)[0]
        # bar0: red, small body 100.3->100.0; bar1: green, body 99.8->100.6 (contains bar0's body)
        bars = [
            _mk_bar(day, 0, 100.3, 100.4, 99.9, 100.0, v=1000),
            _mk_bar(day, 1, 99.8, 100.7, 99.7, 100.6, v=1000),
        ]
        ctx = PatternContext.build(bars)
        pred = engulfing(direction="bullish")
        assert pred(ctx, 1) is not None
        assert engulfing(direction="bearish")(ctx, 1) is None

        # same-color bars (no flip) must NOT fire
        bars2 = [
            _mk_bar(day, 0, 100.0, 100.4, 99.9, 100.3, v=1000),  # green
            _mk_bar(day, 1, 99.8, 100.7, 99.7, 100.6, v=1000),   # green -- no bearish->bullish flip
        ]
        ctx2 = PatternContext.build(bars2)
        assert engulfing(direction="bullish")(ctx2, 1) is None

    def test_inside_bar_containment(self):
        day = _trading_days(1)[0]
        bars = [
            _mk_bar(day, 0, 100.0, 101.0, 99.0, 100.5, v=1000),
            _mk_bar(day, 1, 100.2, 100.8, 99.3, 100.4, v=1000),  # inside bar0's [99,101] range
            _mk_bar(day, 2, 100.2, 101.5, 99.3, 100.4, v=1000),  # high breaks bar1's range -- NOT inside
        ]
        ctx = PatternContext.build(bars)
        assert inside_bar()(ctx, 1) is not None
        assert inside_bar()(ctx, 2) is None

    def test_gap_event_thresholds_and_direction(self):
        d1, d2 = _trading_days(2)
        prior = [_mk_bar(d1, i, 100, 100.2, 99.8, 100.0, v=1000) for i in range(3)]
        # 0.5% gap up -> qualifies (default band 0.25%-1.5%)
        gap_up = [_mk_bar(d2, 0, 100.5, 100.6, 100.4, 100.5, v=1000)]
        bars_up = prior + gap_up
        ctx_up = PatternContext.build(bars_up)
        r = gap_event()(ctx_up, len(bars_up) - 1)
        assert r is not None and r["gap_direction"] == "up"
        assert gap_event(direction="down")(ctx_up, len(bars_up) - 1) is None

        # 0.05% gap -- too small, must NOT fire
        gap_tiny = [_mk_bar(d2, 0, 100.05, 100.1, 100.0, 100.05, v=1000)]
        ctx_tiny = PatternContext.build(prior + gap_tiny)
        assert gap_event()(ctx_tiny, len(prior + gap_tiny) - 1) is None

        # mid-session bar (not a session boundary) must NOT fire even if the OHLC would qualify
        assert gap_event()(ctx_up, 1) is None

    def test_close_above_requires_fresh_cross_by_default(self):
        day = _trading_days(1)[0]
        levels = {day: (LevelLike(price=100.0, role="support"),)}
        bars = [
            _mk_bar(day, 0, 99.0, 99.5, 98.8, 99.5, v=1000),   # below level
            _mk_bar(day, 1, 99.6, 100.6, 99.5, 100.5, v=1000),  # fresh cross above 100.0
            _mk_bar(day, 2, 100.5, 100.8, 100.3, 100.6, v=1000),  # already above -- not a fresh cross
        ]
        ctx = PatternContext.build(bars, levels_by_date=levels)
        assert close_above(level_role="support")(ctx, 1) is not None
        assert close_above(level_role="support")(ctx, 2) is None
        # require_cross=False: bar 2 should count as "currently above"
        assert close_above(level_role="support", require_cross=False)(ctx, 2) is not None

    def test_close_above_flipped_support_filters_by_role_flips(self):
        day = _trading_days(1)[0]
        levels = {day: (
            LevelLike(price=100.0, role="support", role_flips=0),
            LevelLike(price=100.0, role="resistance", role_flips=2),  # wrong role -- shouldn't matter here
        )}
        bars = [
            _mk_bar(day, 0, 99.0, 99.5, 98.8, 99.5, v=1000),
            _mk_bar(day, 1, 99.6, 100.6, 99.5, 100.5, v=1000),
        ]
        ctx = PatternContext.build(bars, levels_by_date=levels)
        # role_flips=0 support does NOT qualify as "flipped_support"
        assert close_above(level_role="flipped_support")(ctx, 1) is None
        assert close_above(level_role="support")(ctx, 1) is not None

    def test_wick_rejection_level_anchored_requires_pierce_and_reclaim(self):
        day = _trading_days(1)[0]
        levels = {day: (LevelLike(price=100.0, role="support"),)}
        # low pierces below 100.0, closes back above -- qualifying spring
        bars = [_mk_bar(day, 0, 100.3, 100.4, 99.7, 100.2, v=1000)]
        ctx = PatternContext.build(bars, levels_by_date=levels)
        pred = wick_rejection(side="lower", min_wick_frac=0.1, at_level_role="support", max_level_distance=0.5)
        r = pred(ctx, 0)
        assert r is not None and r["trigger_level"] == 100.0

        # closes BELOW the level (no reclaim) -- must not fire the level-anchored branch
        bars_no_reclaim = [_mk_bar(day, 0, 100.1, 100.2, 99.7, 99.9, v=1000)]
        ctx2 = PatternContext.build(bars_no_reclaim, levels_by_date=levels)
        assert pred(ctx2, 0) is None

    def test_compression_ranks_low_bandwidth_bars(self):
        day = _trading_days(1)[0]
        rng = random.Random(7)
        bars = []
        price = 100.0
        # bandwidth_period=5 warms up fast (valid from index 4). 24 wide-bandwidth bars,
        # then 1 very tight bar at index 24 -- the tight one should rank near the bottom
        # of its trailing 15-sample window (indices [10,24], all past warmup).
        for i in range(24):
            c = price + rng.uniform(-1.0, 1.0)
            bars.append(_mk_bar(day, i, price, max(price, c) + 0.3, min(price, c) - 0.3, c, v=1000))
            price = c
        bars.append(_mk_bar(day, 24, price, price + 0.01, price - 0.01, price, v=1000))
        ctx = PatternContext.build(bars, bandwidth_period=5)
        r = compression(percentile_lookback=15, percentile_threshold=20.0)(ctx, 24)
        assert r is not None
        assert r["bandwidth_pct_rank"] <= 20.0

    def test_near_vwap_distance_gate(self):
        day = _trading_days(1)[0]
        bars = [_mk_bar(day, i, 100.0, 100.1, 99.9, 100.0, v=1000) for i in range(5)]
        ctx = PatternContext.build(bars)
        assert near_vwap(max_distance=0.05)(ctx, 4) is not None  # flat session -> vwap == close
        bars2 = list(bars)
        bars2[4] = _mk_bar(day, 4, 100.0, 105.0, 100.0, 105.0, v=1000)
        ctx2 = PatternContext.build(bars2)
        assert near_vwap(max_distance=0.05)(ctx2, 4) is None

    def test_within_n_bars_after_sequencing(self):
        """A predicate is TRUE at bars {2, 5}; another is TRUE only at bar 0. Composed
        with within_n_bars_after(n=3), the LATER predicate must fire only where an
        EARLIER-predicate bar exists within the trailing 3 bars."""
        day = _trading_days(1)[0]
        bars = [_mk_bar(day, i, 100, 100.5, 99.5, 100, v=1000) for i in range(8)]
        ctx = PatternContext.build(bars)

        def earlier_at_bar0(c: PatternContext, t: int) -> Optional[dict]:
            return {"e": True} if t == 0 else None

        def later_at_2_and_5(c: PatternContext, t: int) -> Optional[dict]:
            return {"l": True} if t in (2, 5) else None

        composed = within_n_bars_after(later=later_at_2_and_5, earlier=earlier_at_bar0, n=3)
        assert composed(ctx, 2) is not None       # 0 is within [2-3, 2] = [0,2] -- fires
        assert composed(ctx, 5) is None            # 0 is NOT within [5-3, 5] = [2,5] -- must not fire
        assert composed(ctx, 3) is None            # later predicate doesn't hold at 3 at all

    def test_then_break_chains_a_computed_level(self):
        day = _trading_days(1)[0]
        bars = [
            _mk_bar(day, 0, 100.0, 100.5, 99.5, 99.5, v=1000),   # below 100
            _mk_bar(day, 1, 99.6, 100.6, 99.5, 100.5, v=1000),    # closes above 100 (fresh cross)
        ]
        ctx = PatternContext.build(bars)

        def base(c: PatternContext, t: int) -> Optional[dict]:
            return {"trigger_level": 100.0}

        chained = then_break(base=base, side="above", require_cross=True)
        assert chained(ctx, 0) is None   # bar0 close (99.5) is BELOW the level
        assert chained(ctx, 1) is not None

    def test_negate_and_all_of(self):
        day = _trading_days(1)[0]
        bars = [_mk_bar(day, 0, 100, 100.5, 99.5, 100, v=1000)]
        ctx = PatternContext.build(bars)
        always_true: Predicate = lambda c, t: {"a": 1}
        always_false: Predicate = lambda c, t: None
        assert negate(always_false)(ctx, 0) == {}
        assert negate(always_true)(ctx, 0) is None
        assert all_of(always_true, always_true)(ctx, 0) == {"a": 1}
        assert all_of(always_true, always_false)(ctx, 0) is None


class TestLevelRoleMatching:
    def test_flipped_roles_require_role_flips_ge_1(self):
        support0 = LevelLike(price=100.0, role="support", role_flips=0)
        support1 = LevelLike(price=100.0, role="support", role_flips=1)
        resistance1 = LevelLike(price=100.0, role="resistance", role_flips=1)
        assert level_matches_role(support0, "support") is True
        assert level_matches_role(support0, "flipped_support") is False
        assert level_matches_role(support1, "flipped_support") is True
        assert level_matches_role(resistance1, "flipped_support") is False
        assert level_matches_role(resistance1, "flipped_resistance") is True
        assert level_matches_role(support0, "any") is True

    def test_unknown_role_raises(self):
        with pytest.raises(ValueError):
            level_matches_role(LevelLike(price=1.0, role="support"), "sideways")
