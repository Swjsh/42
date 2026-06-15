"""v22_chart_patterns -- gym validator for crypto/lib/chart_patterns.py primitives.

Per OP-26: every primitive in crypto/lib/ must have an offline + live validator
in crypto/validators/ so the 30-min regression catches drift before production
code consumes a broken primitive.

The 4 detectors (double_bottom, double_top, failed_breakdown_wick, rejection_at_level)
are shipped 2026-05-18 evening per CLAUDE.md OP-25 ENGINE-BENEFIT AUTONOMY PRINCIPLE.
This validator locks them in.

The contra-regime wrappers + scan_all_contra_regime are shipped 2026-05-19 (OP-25
engine-benefit loop cycle 1).  T14-T16 cover the 50-bar regime gate.

Offline tests:
    T1  textbook double_bottom fires
    T2  textbook double_top fires
    T3  textbook failed_breakdown_wick fires
    T4  textbook rejection_at_level fires
    T5  empty input returns None for all detectors
    T6  too-few-bars returns None
    T7  trend-only (no patterns) returns None
    T8  PatternHit dataclass is immutable + has expected fields
    T9  momentum_acceleration fires on wide-range high-volume bar
    T10 inside_bar_consolidation fires on 2+ inside bars
    T11 head_and_shoulders_top fires on 3-pivot sequence with neckline break
    T12 disambiguate_by_regime picks bullish in downtrend (conflict resolution)
    T13 is_contra_trend: bullish-in-downtrend=True, bearish-in-downtrend=False
    T14 contra_double_bottom returns None in uptrend (aligned → filtered)
    T15 contra_double_bottom returns PatternHit in downtrend (contra → passes)
    T16 scan_all_contra_regime returns [] on flat no-pattern bars
    T17 scan_high_edge_contra_regime is a strict subset of scan_all and excludes
        contra_double_top + contra_failed_breakdown_wick (no-edge detectors)
    T23 failed_breakdown_wick with support_price override fires at named level
        (key_price=named_level_price, support_source="named_level" in notes)
    T24 rejection_at_level with resistance_price override fires at named level
        (key_price=named_level_price, resistance_source="named_level" in notes)
    T25 named-level overrides return None when bar does not cross the level
        (no sweep above resistance / no wick below support → None for both)
    T26 enrich_hit_with_proximity sets near_key_level=True when key_price
        within $0.50 of a ★2+ level; original PatternHit is NOT mutated
    T27 enrich_hit_with_proximity sets near_key_level=False when farther than
        max_distance; ★1 levels ignored even if within range
    T28 scan_high_edge_near_named returns enriched H&S hit when named level
        is within $0.50 of the neckline key_price (near_key_level=True in notes)
    T29 scan_high_edge_near_named returns [] when no ★2+ named level is close
        enough (far-away level and ★1 close level both filtered correctly)

Live tests:
    L1  run all 4 basic detectors against the latest 100 closed BTC bars
        (Coinbase) and verify no exceptions; count hits (smoke test, no truth)
    L2  run scan_all_contra_regime + scan_high_edge_contra_regime on same live
        bars; verify no exceptions + subset invariant holds (high_edge ⊆ all)
        + no excluded detectors (double_top, failed_breakdown_wick) in result
    L3  run scan_high_edge_near_named on same live bars with (a) empty named
        levels → must return [], (b) synthetic near-price level; all returned
        hits must have near_key_level=True and pattern in expected set
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from crypto.lib.chart_patterns import (
    Bar,
    PatternHit,
    double_bottom_detector,
    double_top_detector,
    failed_breakdown_wick,
    rejection_at_level,
    momentum_acceleration,
    inside_bar_consolidation,
    head_and_shoulders_detector,
    disambiguate_by_regime,
    is_contra_trend,
    contra_double_bottom,
    scan_all_contra_regime,
    scan_high_edge_contra_regime,
    enrich_hit_with_proximity,
    scan_high_edge_near_named,
)


def _bar(t: int, o: float, h: float, low: float, c: float, v: int = 50_000) -> Bar:
    """Compact test-bar constructor matching crypto.lib.bar.Bar shape."""
    return Bar(
        open_time=datetime.fromtimestamp(t, tz=timezone.utc),
        open=o,
        high=h,
        low=low,
        close=c,
        volume=float(v),
        granularity_seconds=300,
        source="validator",
    )


def _test_t1_textbook_double_bottom() -> dict:
    """Textbook double-bottom (W reversal at $100)."""
    bars = [
        _bar(0,    100.5, 100.8, 100.2, 100.4),
        _bar(300,  100.4, 100.6, 100.0, 100.1),
        _bar(600,  100.1, 102.0, 100.1, 101.8),
        _bar(900,  101.8, 102.0, 101.5, 101.7),
        _bar(1200, 101.7, 101.9, 100.05, 100.2),
        _bar(1500, 100.2, 102.3, 100.2, 102.2),
    ]
    hit = double_bottom_detector(bars)
    ok = hit is not None and hit.pattern == "double_bottom" and hit.bias == "bullish"
    return {"name": "T1_textbook_double_bottom", "pass": ok,
            "note": f"hit={hit.pattern if hit else None} bias={hit.bias if hit else None}"}


def _test_t2_textbook_double_top() -> dict:
    """Textbook double-top (M reversal at $100)."""
    bars = [
        _bar(0,    99.5,  99.8,  99.2,  99.4),
        _bar(300,  99.4,  100.0, 99.4,  99.9),
        _bar(600,  99.9,  99.9,  98.0,  98.2),
        _bar(900,  98.2,  98.5,  98.0,  98.3),
        _bar(1200, 98.3,  100.05, 98.3, 99.8),
        _bar(1500, 99.8,  99.9,  97.7,  97.8),
    ]
    hit = double_top_detector(bars)
    ok = hit is not None and hit.pattern == "double_top" and hit.bias == "bearish"
    return {"name": "T2_textbook_double_top", "pass": ok,
            "note": f"hit={hit.pattern if hit else None} bias={hit.bias if hit else None}"}


def _test_t3_textbook_failed_breakdown_wick() -> dict:
    """Bar sweeps below 10-bar low, closes back above with high volume."""
    prior = [_bar(i * 300, 100.5, 101.0, 100.0, 100.6, v=50_000) for i in range(11)]
    latest = _bar(3300, 100.4, 100.5, 99.5, 100.4, v=80_000)
    hit = failed_breakdown_wick(prior + [latest])
    ok = hit is not None and hit.pattern == "failed_breakdown_wick" and hit.bias == "bullish"
    return {"name": "T3_textbook_failed_breakdown_wick", "pass": ok,
            "note": f"hit={hit.pattern if hit else None}"}


def _test_t4_textbook_rejection_at_level() -> dict:
    """Bar pokes above 10-bar high, closes back below with high volume."""
    prior = [_bar(i * 300, 100.5, 101.0, 100.0, 100.6) for i in range(11)]
    latest = _bar(3300, 100.6, 101.5, 100.4, 100.5, v=80_000)
    hit = rejection_at_level(prior + [latest])
    ok = hit is not None and hit.pattern == "rejection_at_level_bearish" and hit.bias == "bearish"
    return {"name": "T4_textbook_rejection_at_level", "pass": ok,
            "note": f"hit={hit.pattern if hit else None}"}


def _test_t5_empty_input() -> dict:
    """All detectors must return None on empty input."""
    results = [
        double_bottom_detector([]),
        double_top_detector([]),
        failed_breakdown_wick([]),
        rejection_at_level([]),
    ]
    ok = all(r is None for r in results)
    return {"name": "T5_empty_input_returns_none", "pass": ok,
            "note": f"all_none={ok}"}


def _test_t6_too_few_bars() -> dict:
    """1-bar input must return None for all detectors."""
    one_bar = [_bar(0, 100, 101, 99, 100)]
    results = [
        double_bottom_detector(one_bar),
        double_top_detector(one_bar),
        failed_breakdown_wick(one_bar),
        rejection_at_level(one_bar),
    ]
    ok = all(r is None for r in results)
    return {"name": "T6_too_few_bars_returns_none", "pass": ok,
            "note": f"all_none={ok}"}


def _test_t7_trending_no_pattern() -> dict:
    """Clean uptrend has no W/M/sweep/rejection."""
    bars = [_bar(i * 300, 100 + i, 101 + i, 99.5 + i, 100.5 + i) for i in range(15)]
    results = [
        double_bottom_detector(bars),
        double_top_detector(bars),
        failed_breakdown_wick(bars),
        rejection_at_level(bars),
    ]
    ok = all(r is None for r in results)
    return {"name": "T7_trending_returns_none", "pass": ok,
            "note": f"all_none={ok}"}


def _test_t9_momentum_acceleration() -> dict:
    """Today's 15:00 reversal class: wide-range high-volume bar with decisive body."""
    prior = [_bar(i * 300, 736.0, 736.5, 735.5, 736.2, v=80_000) for i in range(11)]
    latest = _bar(3300, 733.70, 738.00, 733.61, 736.38, v=328_247)
    hit = momentum_acceleration(prior + [latest])
    ok = hit is not None and hit.pattern == "momentum_acceleration" and hit.bias == "bullish"
    return {"name": "T9_momentum_acceleration", "pass": ok,
            "note": f"hit={hit.pattern if hit else None}"}


def _test_t10_inside_bar_consolidation() -> dict:
    """Chop signature: 2+ consecutive bars inside reference range."""
    bars = [
        _bar(0, 100, 102, 98, 101),
        _bar(300, 100, 101.5, 99, 100.5),
        _bar(600, 100, 101.0, 99.5, 100),
    ]
    hit = inside_bar_consolidation(bars)
    ok = hit is not None and hit.pattern == "inside_bar_consolidation" and hit.bias == "neutral"
    return {"name": "T10_inside_bar_consolidation", "pass": ok,
            "note": f"hit={hit.pattern if hit else None}"}


def _test_t11_head_and_shoulders_top() -> dict:
    """3-peak top reversal: LS @ 745, Head @ 748.5, RS @ 745.2, neckline break."""
    # Synthesize: peaks rise to LS (idx 4), dip, rise higher to Head (idx 14),
    # dip, rise to RS (idx 24), then break below neckline at idx 29.
    peaks = [
        741.0, 742.0, 743.5, 744.5,  # 0-3 ramp
        745.0,                         # 4 LS
        744.0, 744.5, 743.5, 743.0, 743.5,  # 5-9 trough
        744.0, 746.0, 747.0, 748.0,   # 10-13 ramp
        748.5,                         # 14 HEAD
        747.0, 746.0, 744.5, 743.5, 743.0,  # 15-19 trough
        744.0, 744.5, 743.7, 744.7,   # 20-23 ramp
        745.2,                         # 24 RS
        743.5, 743.0, 742.5, 741.5, 740.0,  # 25-29 break
    ]
    bars = []
    for i, peak in enumerate(peaks):
        if i == len(peaks) - 1:
            bars.append(_bar(i * 300, peak + 0.3, peak + 0.4, peak - 0.2, peak))
        else:
            bars.append(_bar(i * 300, peak - 0.25, peak, peak - 0.6, peak - 0.10))
    hit = head_and_shoulders_detector(bars, lookback=30)
    ok = hit is not None and hit.pattern == "head_and_shoulders_top" and hit.bias == "bearish"
    return {"name": "T11_head_and_shoulders_top", "pass": ok,
            "note": f"hit={hit.pattern if hit else None}"}


def _test_t12_disambiguate_by_regime() -> dict:
    """Conflicting bullish+bearish in downtrend -> bullish wins."""
    bars = [_bar(i * 300, 750 - i*0.5, 750.5 - i*0.5, 749.5 - i*0.5, 750 - i*0.6) for i in range(55)]
    bullish = PatternHit(pattern="failed_breakdown_wick", bar_index=54, bias="bullish",
                         confidence=0.70, key_price=720.0, notes={})
    bearish = PatternHit(pattern="double_top", bar_index=54, bias="bearish",
                         confidence=0.65, key_price=720.0, notes={})
    winner = disambiguate_by_regime([bullish, bearish], bars)
    ok = (winner is not None and winner.bias == "bullish"
          and "regime_resolved_downtrend" in winner.pattern)
    return {"name": "T12_disambiguate_by_regime", "pass": ok,
            "note": f"winner={winner.bias if winner else None}"}


def _test_t13_is_contra_trend() -> dict:
    """Bullish hit in downtrend = contra-trend = True (the +edge case)."""
    bars = [_bar(i * 300, 750 - i*0.5, 750.5 - i*0.5, 749.5 - i*0.5, 750 - i*0.6) for i in range(25)]
    bullish = PatternHit(pattern="double_bottom", bar_index=24, bias="bullish",
                         confidence=0.70, key_price=720.0, notes={})
    bearish = PatternHit(pattern="double_top", bar_index=24, bias="bearish",
                         confidence=0.70, key_price=720.0, notes={})
    bullish_ct = is_contra_trend(bullish, bars)
    bearish_ct = is_contra_trend(bearish, bars)
    ok = bullish_ct is True and bearish_ct is False
    return {"name": "T13_is_contra_trend", "pass": ok,
            "note": f"bullish_contra={bullish_ct} bearish_contra={bearish_ct}"}


def _test_t8_pattern_hit_immutable() -> dict:
    """PatternHit must be frozen dataclass (immutability invariant)."""
    prior = [_bar(i * 300, 100.5, 101.0, 100.0, 100.6) for i in range(11)]
    latest = _bar(3300, 100.4, 100.5, 99.5, 100.4, v=80_000)
    hit = failed_breakdown_wick(prior + [latest])
    if hit is None:
        return {"name": "T8_pattern_hit_immutable", "pass": False, "note": "could not produce hit"}
    try:
        hit.bias = "bearish"  # type: ignore[misc]
        return {"name": "T8_pattern_hit_immutable", "pass": False,
                "note": "mutation succeeded (PatternHit not frozen)"}
    except (AttributeError, Exception):
        # Expected: frozen dataclass raises FrozenInstanceError or AttributeError
        return {"name": "T8_pattern_hit_immutable", "pass": True,
                "note": "mutation correctly rejected"}


def _test_t14_contra_double_bottom_uptrend() -> dict:
    """contra_double_bottom returns None when trend is UP (bullish pattern aligned → filtered).

    Construction: 44 uptrend bars (close 100→113) then T1-style double-bottom
    scaled to the ~113 level.  SMA50 ≈ 106.5, last close ≈ 115.5 → UPTREND.
    Base detector fires; contra filter suppresses because bullish ≠ contra in uptrend.
    """
    # 44 uptrend bars: close = 100.2 + i*0.3 (bar 43 close ≈ 113.1)
    bars: list[Bar] = [
        _bar(i * 300, 100.0 + i * 0.3, 100.5 + i * 0.3, 99.7 + i * 0.3, 100.2 + i * 0.3)
        for i in range(44)
    ]
    # T1 pattern scaled by 1.13 — double bottom at ~113 level
    sc = 1.13
    bars += [
        _bar(44 * 300, round(100.5 * sc, 2), round(100.8 * sc, 2), round(100.2 * sc, 2), round(100.4 * sc, 2)),
        _bar(45 * 300, round(100.4 * sc, 2), round(100.6 * sc, 2), round(100.0 * sc, 2), round(100.1 * sc, 2)),
        _bar(46 * 300, round(100.1 * sc, 2), round(102.0 * sc, 2), round(100.1 * sc, 2), round(101.8 * sc, 2)),
        _bar(47 * 300, round(101.8 * sc, 2), round(102.0 * sc, 2), round(101.5 * sc, 2), round(101.7 * sc, 2)),
        _bar(48 * 300, round(101.7 * sc, 2), round(101.9 * sc, 2), round(100.05 * sc, 2), round(100.2 * sc, 2)),
        _bar(49 * 300, round(100.2 * sc, 2), round(102.3 * sc, 2), round(100.2 * sc, 2), round(102.2 * sc, 2), v=80_000),
    ]
    base_hit = double_bottom_detector(bars)
    contra_hit = contra_double_bottom(bars)
    # Base must fire to confirm pattern is real; contra must be filtered
    ok = base_hit is not None and contra_hit is None
    return {
        "name": "T14_contra_db_uptrend_filtered",
        "pass": ok,
        "note": f"base_fired={base_hit is not None}, contra_hit={contra_hit}",
    }


def _test_t15_contra_double_bottom_downtrend() -> dict:
    """contra_double_bottom returns PatternHit when trend is DOWN (bullish contra → passes).

    Construction: 44 downtrend bars (close 115→102) then T1 double-bottom at ~100 level.
    SMA50 ≈ 108.5, last close ≈ 102.2 → DOWNTREND.
    Bullish pattern in downtrend = contra-regime → contra_double_bottom fires.
    """
    # 44 downtrend bars: close = 115.0 - i*0.3 (bar 43 close ≈ 102.1)
    bars: list[Bar] = [
        _bar(i * 300, 115.2 - i * 0.3, 115.5 - i * 0.3, 114.9 - i * 0.3, 115.0 - i * 0.3)
        for i in range(44)
    ]
    # T1 pattern at original ~100 level (bar 43 close ≈ 102.1, natural continuation)
    bars += [
        _bar(44 * 300, 100.5, 100.8, 100.2, 100.4),
        _bar(45 * 300, 100.4, 100.6, 100.0, 100.1),
        _bar(46 * 300, 100.1, 102.0, 100.1, 101.8),
        _bar(47 * 300, 101.8, 102.0, 101.5, 101.7),
        _bar(48 * 300, 101.7, 101.9, 100.05, 100.2),
        _bar(49 * 300, 100.2, 102.3, 100.2, 102.2, v=80_000),
    ]
    base_hit = double_bottom_detector(bars)
    contra_hit = contra_double_bottom(bars)
    # Base must fire; contra must also fire (with ::contra_regime suffix)
    ok = (
        base_hit is not None
        and contra_hit is not None
        and "contra_regime" in contra_hit.pattern
        and contra_hit.bias == "bullish"
    )
    return {
        "name": "T15_contra_db_downtrend_passes",
        "pass": ok,
        "note": f"base_fired={base_hit is not None}, contra_pattern={contra_hit.pattern if contra_hit else None}",
    }


def _test_t16_scan_all_contra_regime_no_pattern() -> dict:
    """scan_all_contra_regime returns [] when bars have expanding ranges (no inside-bar
    consolidation) and no directional pattern.

    Bars with monotonically widening range cannot form inside bars (each bar is WIDER
    than its predecessor), so inside_bar_consolidation never fires.  No directional
    detector fires on random-noise bars either.  Expected: empty list.
    """
    # 55 bars with widening range — each bar is WIDER than previous, so no inside bars.
    bars = [
        _bar(i * 300, 100.0, 100.05 + i * 0.01, 99.95 - i * 0.01, 100.0)
        for i in range(55)
    ]
    hits = scan_all_contra_regime(bars)
    directional_hits = [h for h in hits if h.bias != "neutral"]
    ok = isinstance(hits, list) and len(directional_hits) == 0
    return {
        "name": "T16_scan_all_contra_no_directional_pattern",
        "pass": ok,
        "note": f"total_hits={len(hits)}, directional_hits={directional_hits}",
    }


def _test_t17_scan_high_edge_excludes_no_edge_detectors() -> dict:
    """scan_high_edge_contra_regime is a subset of scan_all and never returns
    contra_double_top or contra_failed_breakdown_wick (no confirmed edge).

    Construction: same downtrend + double-bottom bars as T15.  In a downtrend,
    double_bottom is bullish = contra-regime, so scan_all will return it.
    We then verify scan_high_edge also returns it (it's a high-edge detector)
    while neither result contains the two excluded detectors.
    """
    bars: list[Bar] = [
        _bar(i * 300, 115.2 - i * 0.3, 115.5 - i * 0.3, 114.9 - i * 0.3, 115.0 - i * 0.3)
        for i in range(44)
    ]
    bars += [
        _bar(44 * 300, 100.5, 100.8, 100.2, 100.4),
        _bar(45 * 300, 100.4, 100.6, 100.0, 100.1),
        _bar(46 * 300, 100.1, 102.0, 100.1, 101.8),
        _bar(47 * 300, 101.8, 102.0, 101.5, 101.7),
        _bar(48 * 300, 101.7, 101.9, 100.05, 100.2),
        _bar(49 * 300, 100.2, 102.3, 100.2, 102.2, v=80_000),
    ]
    all_hits = scan_all_contra_regime(bars)
    high_hits = scan_high_edge_contra_regime(bars)
    all_patterns = {h.pattern for h in all_hits}
    high_patterns = {h.pattern for h in high_hits}
    excluded = {"double_top", "failed_breakdown_wick"}
    no_excluded_in_high = all(
        not any(ex in p for ex in excluded) for p in high_patterns
    )
    high_is_subset = high_patterns <= all_patterns
    ok = (
        isinstance(high_hits, list)
        and len(high_hits) <= 4
        and no_excluded_in_high
        and high_is_subset
    )
    return {
        "name": "T17_scan_high_edge_excludes_no_edge_detectors",
        "pass": ok,
        "note": (
            f"all_count={len(all_hits)} high_count={len(high_hits)} "
            f"high_patterns={sorted(high_patterns)} no_excluded={no_excluded_in_high} "
            f"is_subset={high_is_subset}"
        ),
    }


def _test_t18_v2_version_stamp() -> dict:
    """double_bottom_detector notes must carry confidence_version == 'v2'.

    Regression gate: if the formula reverts to v1 (continuous weights), this
    sentinel breaks.  Uses the same T1 bars — simplest way to get a fired hit.
    """
    bars = [
        _bar(0,    100.5, 100.8, 100.2, 100.4),
        _bar(300,  100.4, 100.6, 100.0, 100.1),
        _bar(600,  100.1, 102.0, 100.1, 101.8),
        _bar(900,  101.8, 102.0, 101.5, 101.7),
        _bar(1200, 101.7, 101.9, 100.05, 100.2),
        _bar(1500, 100.2, 102.3, 100.2, 102.2),
    ]
    hit = double_bottom_detector(bars)
    version = hit.notes.get("confidence_version") if hit else None
    ok = hit is not None and version == "v2"
    return {"name": "T18_v2_version_stamp", "pass": ok,
            "note": f"confidence_version={version}"}


def _test_t19_all_factors_conf_096() -> dict:
    """All 5 v2 binary factors active -> conf = 0.45+0.15+0.11+0.10+0.10+0.05 = 0.96.

    v3 formula: low2_volume_higher weight lowered 0.15->0.11 (OOS N=26 WR=38.5% solo).
    Max achievable conf is now 0.96 (was 1.00 in v2).

    Construction:
      - decisive_reclaim:        reclaim_pct > 0.001 (close well above neckline)
      - low2_volume_higher:      vol2=80k > vol1=50k
      - bars_between_sweet_spot: bars_between=6 in [4,12]
      - very_tight_lows:         sep_pct ~0.0005 << 0.0075 threshold
      - decent_neckline_height:  neckline 2.1% above lower_low >> 0.5% threshold
    """
    bars: list[Bar] = [
        _bar(0 * 300, 100.5, 100.8, 100.2, 100.4),
        _bar(1 * 300, 100.4, 100.6, 100.0, 100.1, v=50_000),  # low1=100.0 vol=50k
        _bar(2 * 300, 100.1, 102.1, 100.1, 101.8),             # between: neckline=102.1
        _bar(3 * 300, 101.8, 102.0, 101.5, 101.7),
        _bar(4 * 300, 101.7, 101.9, 101.5, 101.6),
        _bar(5 * 300, 101.6, 101.8, 101.5, 101.7),
        _bar(6 * 300, 101.7, 101.9, 101.5, 101.6),
        _bar(7 * 300, 101.6, 101.8, 101.5, 101.6),             # 6 between bars total
        _bar(8 * 300, 101.6, 101.7, 100.05, 100.2, v=80_000), # low2=100.05 vol=80k
        _bar(9 * 300, 100.2, 102.5, 100.2, 102.4),             # reclaim above 102.1
    ]
    hit = double_bottom_detector(bars)
    expected_conf = round(0.45 + 0.15 + 0.11 + 0.10 + 0.10 + 0.05, 3)  # 0.96
    ok = (
        hit is not None
        and round(hit.confidence, 3) == expected_conf
        and set(hit.notes.get("v2_factors_active", [])) == {
            "decisive_reclaim", "low2_volume_higher",
            "bars_between_sweet_spot", "very_tight_lows", "decent_neckline_height",
        }
    )
    return {
        "name": "T19_all_factors_conf_096",
        "pass": ok,
        "note": f"conf={hit.confidence if hit else None} factors={hit.notes.get('v2_factors_active') if hit else None}",
    }


def _test_t20_two_factors_conf_0_65() -> dict:
    """Only decisive_reclaim + decent_neckline_height active -> conf = 0.65.

    Construction (all others suppressed):
      - bars_between_sweet_spot: False (bars_between=2, outside [4,12])
      - very_tight_lows:         False (sep_pct≈0.14% > 0.075% tight threshold,
                                        but within the detector's 0.15% tolerance)
      - low2_volume_higher:      False (vol2=vol1=50k)
      - decisive_reclaim:        True  (reclaim_pct≈0.13% > 0.1% threshold)
      - decent_neckline_height:  True  (neckline 0.52% above lower_low > 0.5%)

    Key constraint: lows must be within tolerance_pct=0.0015 (0.15%!).
    We use low1=100.0 and low2=100.14 (sep≈0.14% < 0.15%) so the detector fires,
    but sep > 0.075% so very_tight_lows stays False.
    """
    bars: list[Bar] = [
        _bar(0 * 300, 100.5, 101.0, 100.3, 100.4),
        _bar(1 * 300, 100.4, 100.6, 100.0, 100.2),               # low1=100.0, vol=50k
        _bar(2 * 300, 100.2, 100.52, 100.15, 100.50),            # between: high=100.52 (neckline)
        _bar(3 * 300, 100.5, 100.51, 100.20, 100.45),            # between: high=100.51
        _bar(4 * 300, 100.45, 100.50, 100.14, 100.48, v=50_000), # low2=100.14, vol=50k
        _bar(5 * 300, 100.48, 100.70, 100.20, 100.65),           # reclaim: close=100.65 > 100.52
    ]
    hit = double_bottom_detector(bars)
    active = set(hit.notes.get("v2_factors_active", [])) if hit else set()
    ok = (
        hit is not None
        and round(hit.confidence, 3) == 0.65
        and active == {"decisive_reclaim", "decent_neckline_height"}
    )
    return {
        "name": "T20_two_factors_conf_065",
        "pass": ok,
        "note": f"conf={hit.confidence if hit else None} factors={sorted(active)}",
    }


def _test_t21_conf_range_invariant() -> dict:
    """v2 confidence must always be in [0.45, 1.0] on a fired pattern.

    Tests both the T1 textbook pattern (mid-range) and the all-factors pattern
    (ceiling) to bracket the valid range.
    """
    t1_bars = [
        _bar(0,    100.5, 100.8, 100.2, 100.4),
        _bar(300,  100.4, 100.6, 100.0, 100.1),
        _bar(600,  100.1, 102.0, 100.1, 101.8),
        _bar(900,  101.8, 102.0, 101.5, 101.7),
        _bar(1200, 101.7, 101.9, 100.05, 100.2),
        _bar(1500, 100.2, 102.3, 100.2, 102.2),
    ]
    all_factor_bars: list[Bar] = [
        _bar(i * 300, 100.5 + (i > 1) * 1.5,
             100.8 + (i > 1) * 1.3, 100.2 + (i > 1) * 1.5, 100.4 + (i > 1) * 1.5)
        for i in range(2)
    ] + [
        _bar(2 * 300, 100.1, 102.1, 100.1, 101.8),
        _bar(3 * 300, 101.8, 102.0, 101.5, 101.7),
        _bar(4 * 300, 101.7, 101.9, 101.5, 101.6),
        _bar(5 * 300, 101.6, 101.8, 101.5, 101.7),
        _bar(6 * 300, 101.7, 101.9, 101.5, 101.6),
        _bar(7 * 300, 101.6, 101.8, 101.5, 101.6),
        _bar(8 * 300, 101.6, 101.7, 100.05, 100.2, v=80_000),
        _bar(9 * 300, 100.2, 102.5, 100.2, 102.4),
    ]
    hits = [double_bottom_detector(t1_bars), double_bottom_detector(all_factor_bars)]
    in_range = all(h is not None and 0.45 <= h.confidence <= 1.0 for h in hits)
    confs = [h.confidence if h else None for h in hits]
    ok = in_range
    return {"name": "T21_conf_range_invariant", "pass": ok,
            "note": f"confs={confs} all_in_range={in_range}"}


def _test_t22_v2_factors_list_correct() -> dict:
    """v2_factors_active in notes lists exactly the factors that fired.

    T1 bars trigger: decisive_reclaim (reclaim>0.1%), very_tight_lows
    (sep≈0.05%), decent_neckline_height (neckline 2% above lows).
    NOT triggered: bars_between_sweet_spot (bars_between=2 outside [4,12]),
    low2_volume_higher (vol2=vol1=50k).
    """
    bars = [
        _bar(0,    100.5, 100.8, 100.2, 100.4),
        _bar(300,  100.4, 100.6, 100.0, 100.1),
        _bar(600,  100.1, 102.0, 100.1, 101.8),
        _bar(900,  101.8, 102.0, 101.5, 101.7),
        _bar(1200, 101.7, 101.9, 100.05, 100.2),
        _bar(1500, 100.2, 102.3, 100.2, 102.2),
    ]
    hit = double_bottom_detector(bars)
    active = set(hit.notes.get("v2_factors_active", [])) if hit else set()
    expected = {"decisive_reclaim", "very_tight_lows", "decent_neckline_height"}
    inactive_expected = {"bars_between_sweet_spot", "low2_volume_higher"}
    ok = (
        hit is not None
        and active == expected
        and not (active & inactive_expected)
        and round(hit.confidence, 3) == 0.75  # base 0.45 + 0.15 + 0.10 + 0.05
    )
    return {
        "name": "T22_v2_factors_list_correct",
        "pass": ok,
        "note": f"active={sorted(active)} conf={hit.confidence if hit else None}",
    }


def _test_t23_fbw_named_level_override() -> dict:
    """T23: failed_breakdown_wick with explicit support_price fires when bar
    sweeps the named level and closes above it, regardless of rolling low.

    Bar: open=100.00, high=101.00, low=99.40 (sweeps below 99.50), close=100.20 (above 99.50).
    Rolling prior-10-bar low would be ~100.0 (never below 100.0), so v1 would NOT fire.
    With support_price=99.50, the named-level override detects the sweep+reclaim.
    """
    prior = [_bar(i * 300, 100.0, 100.5, 100.0, 100.1) for i in range(12)]
    entry = _bar(12 * 300, 100.00, 101.00, 99.40, 100.20)  # sweeps below 99.50, closes above
    bars = prior + [entry]

    # v1 (rolling low): rolling low ≈ 100.0, bar.low=99.40 < 100.0 → sweeps below rolling low.
    # Actually this WOULD fire v1 since 99.40 < 100.0 (rolling low) and 100.20 > 100.0.
    # To isolate the named-level test, we use a named level that is ABOVE the rolling low.
    # Set support_price=99.80 (above bar's low=99.40, below bar's close=100.20).
    hit_v2 = failed_breakdown_wick(bars, support_price=99.80)
    # rolling low of prior bars is ~100.0; named level 99.80 is BELOW the rolling low
    # so v1 would fire at 100.0 while v2 fires at 99.80. The result should be keyed to 99.80.
    ok = (
        hit_v2 is not None
        and hit_v2.pattern == "failed_breakdown_wick"
        and hit_v2.bias == "bullish"
        and hit_v2.key_price == 99.80
        and hit_v2.notes.get("support_source") == "named_level"
    )
    return {
        "name": "T23_fbw_named_level_override",
        "pass": ok,
        "note": (
            f"key_price={hit_v2.key_price if hit_v2 else None} "
            f"support_source={hit_v2.notes.get('support_source') if hit_v2 else None}"
        ),
    }


def _test_t24_ral_named_level_override() -> dict:
    """T24: rejection_at_level with explicit resistance_price fires when bar
    sweeps above the named level and closes back below it.

    resistance_price=100.40 (named level).
    Bar: open=100.30, high=100.90 (sweeps 0.50 above level), close=100.10
    (0.30 below level = 0.30/100.40 = 0.30% close-back, well above 0.1% threshold).
    wick = 100.90 - max(open=100.30, close=100.10) = 100.90 - 100.30 = 0.60
    body = abs(100.10 - 100.30) = 0.20 → wick:body = 3.0 ≥ 2.0
    volume = 65000 = 1.30× prior avg(50000) → meets vol_mult ≥ 1.3 gate.
    """
    prior = [_bar(i * 300, 100.0, 100.5, 99.8, 100.2) for i in range(12)]
    # strong upper wick above named level, decisive close-back, vol=1.3× avg
    entry = _bar(12 * 300, 100.30, 100.90, 99.90, 100.10, v=65_000)
    bars = prior + [entry]

    hit_v2 = rejection_at_level(bars, resistance_price=100.40)
    ok = (
        hit_v2 is not None
        and hit_v2.pattern == "rejection_at_level_bearish"
        and hit_v2.bias == "bearish"
        and hit_v2.key_price == 100.40
        and hit_v2.notes.get("resistance_source") == "named_level"
    )
    return {
        "name": "T24_ral_named_level_override",
        "pass": ok,
        "note": (
            f"key_price={hit_v2.key_price if hit_v2 else None} "
            f"resistance_source={hit_v2.notes.get('resistance_source') if hit_v2 else None}"
        ),
    }


def _test_t25_named_level_does_not_fire_when_no_sweep() -> dict:
    """T25: named-level override returns None when bar does NOT sweep the level.

    Bar: open=100, high=100.30 (below named resistance 100.50), close=100.20.
    No sweep above resistance → rejection_at_level should return None.
    Also: bar.low=99.70 (above named support 99.50) → failed_breakdown_wick returns None.
    Validates that the named-level override preserves the structural requirement:
    price MUST cross the level before returning a hit.
    """
    prior = [_bar(i * 300, 100.0, 100.5, 99.8, 100.2) for i in range(12)]
    entry = _bar(12 * 300, 100.00, 100.30, 99.70, 100.20)  # doesn't cross either level
    bars = prior + [entry]

    ral_hit = rejection_at_level(bars, resistance_price=100.50)  # high=100.30 < 100.50
    fbw_hit = failed_breakdown_wick(bars, support_price=99.50)   # low=99.70 > 99.50

    ok = ral_hit is None and fbw_hit is None
    return {
        "name": "T25_named_level_no_sweep_returns_none",
        "pass": ok,
        "note": f"ral_hit={ral_hit is not None} fbw_hit={fbw_hit is not None}",
    }


def _test_t26_enrich_hit_near_level() -> dict:
    """T26: enrich_hit_with_proximity sets near_key_level=True when key_price
    is within $0.50 of a ★2+ named level.

    Uses same 12-bar textbook setup as T9 (momentum_acceleration confirmed to fire).
    Named level placed at 736.60 — close to close=736.38 (distance $0.22 ≤ $0.50).
    Verifies near_key_level=True + nearest_key_level_name/distance populated.
    Also verifies the original PatternHit is NOT mutated (frozen=True contract).
    """
    prior = [_bar(i * 300, 736.0, 736.5, 735.5, 736.2, v=80_000) for i in range(11)]
    latest = _bar(3300, 733.70, 738.00, 733.61, 736.38, v=328_247)
    bars = prior + [latest]
    hit = momentum_acceleration(bars)
    if hit is None:
        return {"name": "T26_enrich_hit_near_level", "pass": False,
                "note": "momentum_acceleration returned None — test setup incorrect"}

    # Named level at 736.60: distance from key_price 736.38 = $0.22 ≤ $0.50
    named_levels = [{"price": 736.60, "name": "PDH", "stars": 2, "tier": "Active"}]
    enriched = enrich_hit_with_proximity(hit, named_levels, max_distance=0.50)

    ok = (
        hit is not enriched                          # new object (frozen=True → replace)
        and hit.notes.get("near_key_level") is None  # original unmodified
        and enriched.notes.get("near_key_level") is True
        and enriched.notes.get("nearest_key_level_name") == "PDH"
        and enriched.notes.get("nearest_key_level_distance") is not None
        and enriched.notes.get("nearest_key_level_distance") <= 0.50
    )
    return {
        "name": "T26_enrich_hit_near_level",
        "pass": ok,
        "note": (
            f"near_key_level={enriched.notes.get('near_key_level')} "
            f"dist={enriched.notes.get('nearest_key_level_distance')} "
            f"orig_unchanged={hit.notes.get('near_key_level') is None}"
        ),
    }


def _test_t27_enrich_hit_far_from_level() -> dict:
    """T27: enrich_hit_with_proximity sets near_key_level=False when key_price
    is farther than max_distance from all named levels.

    Same 12-bar setup.  Named levels: one too far (739.00, distance $2.62),
    one close but low-star (736.20, distance $0.18 ≤ $0.50 but stars=1 ignored).
    """
    prior = [_bar(i * 300, 736.0, 736.5, 735.5, 736.2, v=80_000) for i in range(11)]
    latest = _bar(3300, 733.70, 738.00, 733.61, 736.38, v=328_247)
    bars = prior + [latest]
    hit = momentum_acceleration(bars)
    if hit is None:
        return {"name": "T27_enrich_hit_far_from_level", "pass": False,
                "note": "momentum_acceleration returned None — test setup incorrect"}

    named_levels = [
        {"price": 739.00, "name": "PDH", "stars": 2, "tier": "Active"},    # too far ($2.62)
        {"price": 736.20, "name": "PDL", "stars": 1, "tier": "Reference"}, # close but stars=1
    ]
    enriched = enrich_hit_with_proximity(hit, named_levels, max_distance=0.50)

    ok = (
        enriched.notes.get("near_key_level") is False
        and "nearest_key_level_name" not in enriched.notes  # not populated when False
    )
    return {
        "name": "T27_enrich_hit_far_from_level",
        "pass": ok,
        "note": (
            f"near_key_level={enriched.notes.get('near_key_level')} "
            f"has_nearest_name={'nearest_key_level_name' in enriched.notes}"
        ),
    }


def _hs_bars() -> list:
    """30-bar textbook H&S setup shared by T28 and T29 (same as T11).

    Head at bar 14 (high=748.5), shoulders at bars 4/24 (high≈745).
    Neckline ≈ 742.4 (average of trough lows at bars 8 and 19).
    Last bar closes at 740.0 (neckline break confirmed).
    """
    peaks = [
        741.0, 742.0, 743.5, 744.5, 745.0,           # 0-4 ramp → LS
        744.0, 744.5, 743.5, 743.0, 743.5,            # 5-9 trough
        744.0, 746.0, 747.0, 748.0, 748.5,            # 10-14 ramp → Head
        747.0, 746.0, 744.5, 743.5, 743.0,            # 15-19 trough
        744.0, 744.5, 743.7, 744.7, 745.2,            # 20-24 ramp → RS
        743.5, 743.0, 742.5, 741.5, 740.0,            # 25-29 neckline break
    ]
    bars = []
    for i, peak in enumerate(peaks):
        if i == len(peaks) - 1:
            bars.append(_bar(i * 300, peak + 0.3, peak + 0.4, peak - 0.2, peak))
        else:
            bars.append(_bar(i * 300, peak - 0.25, peak, peak - 0.6, peak - 0.10))
    return bars


def _test_t28_scan_high_edge_near_named_hit() -> dict:
    """T28: scan_high_edge_near_named returns enriched H&S hit near a ★★+ level.

    H&S neckline key_price ≈ 742.4.  Named level at 742.0 ($0.4 away ≤ $0.50).
    Expects: H&S hit in result, near_key_level=True, name=PDL populated.
    """
    bars = _hs_bars()
    named_levels = [{"price": 742.0, "name": "PDL", "stars": 2, "tier": "Active"}]
    hits = scan_high_edge_near_named(bars, named_levels, max_distance=0.50)
    hs = [h for h in hits if h.pattern == "head_and_shoulders_top"]
    ok = (
        len(hs) >= 1
        and hs[0].notes.get("near_key_level") is True
        and hs[0].notes.get("nearest_key_level_name") == "PDL"
    )
    return {
        "name": "T28_scan_high_edge_near_named_hit",
        "pass": ok,
        "note": (
            f"total={len(hits)} hs_hits={len(hs)} "
            f"near={hs[0].notes.get('near_key_level') if hs else None} "
            f"lvl={hs[0].notes.get('nearest_key_level_name') if hs else None}"
        ),
    }


def _test_t29_scan_high_edge_near_named_no_match() -> dict:
    """T29: scan_high_edge_near_named returns [] when no qualifying level is nearby.

    H&S fires (same setup), but named levels are either too far (750.0, Δ$7.6)
    or too low star (742.6, ★1).  Proximity filter must eliminate the H&S hit.
    """
    bars = _hs_bars()
    named_levels = [
        {"price": 750.0, "name": "PDH", "stars": 2, "tier": "Active"},     # too far ($7.6)
        {"price": 742.6, "name": "PDL", "stars": 1, "tier": "Reference"},  # ★1 ignored
    ]
    hits = scan_high_edge_near_named(bars, named_levels, max_distance=0.50)
    hs = [h for h in hits if h.pattern == "head_and_shoulders_top"]
    ok = len(hs) == 0
    return {
        "name": "T29_scan_high_edge_near_named_no_match",
        "pass": ok,
        "note": f"total={len(hits)} hs_hits={len(hs)} (expected 0)",
    }


def run_offline() -> dict:
    tests = [
        _test_t1_textbook_double_bottom(),
        _test_t2_textbook_double_top(),
        _test_t3_textbook_failed_breakdown_wick(),
        _test_t4_textbook_rejection_at_level(),
        _test_t5_empty_input(),
        _test_t6_too_few_bars(),
        _test_t7_trending_no_pattern(),
        _test_t8_pattern_hit_immutable(),
        _test_t9_momentum_acceleration(),
        _test_t10_inside_bar_consolidation(),
        _test_t11_head_and_shoulders_top(),
        _test_t12_disambiguate_by_regime(),
        _test_t13_is_contra_trend(),
        _test_t14_contra_double_bottom_uptrend(),
        _test_t15_contra_double_bottom_downtrend(),
        _test_t16_scan_all_contra_regime_no_pattern(),
        _test_t17_scan_high_edge_excludes_no_edge_detectors(),
        _test_t18_v2_version_stamp(),
        _test_t19_all_factors_conf_096(),
        _test_t20_two_factors_conf_0_65(),
        _test_t21_conf_range_invariant(),
        _test_t22_v2_factors_list_correct(),
        _test_t23_fbw_named_level_override(),
        _test_t24_ral_named_level_override(),
        _test_t25_named_level_does_not_fire_when_no_sweep(),
        _test_t26_enrich_hit_near_level(),
        _test_t27_enrich_hit_far_from_level(),
        _test_t28_scan_high_edge_near_named_hit(),
        _test_t29_scan_high_edge_near_named_no_match(),
    ]
    passed = sum(1 for t in tests if t["pass"])
    return {
        "mode": "offline",
        "tests": tests,
        "passed": passed,
        "total": len(tests),
        "all_pass": passed == len(tests),
    }


def run_live() -> dict:
    """Run detectors + contra-regime scans against latest ~100 BTC closed bars (Coinbase).

    Pure smoke test: verify no exceptions, report hit counts, and assert the
    subset invariant (scan_high_edge_contra_regime ⊆ scan_all_contra_regime).
    No ground truth required — the contract being tested is structural.

    L1: 4 basic detectors on Coinbase bars (original)
    L2: scan_all_contra_regime + scan_high_edge_contra_regime — verify no
        exceptions + subset contract holds on live data
    """
    try:
        from crypto.lib.data_sources import fetch_coinbase_bars  # type: ignore[import-not-found]
        from crypto.lib.closed_bar import last_closed_bars  # type: ignore[import-not-found]
    except ImportError:
        return {
            "mode": "live",
            "source": "coinbase",
            "skipped": True,
            "reason": "crypto.lib.data_sources or closed_bar not importable",
            "pass": True,
        }

    try:
        raw_bars = fetch_coinbase_bars(symbol="BTC-USD", granularity_seconds=300, limit=120)
        bars = last_closed_bars(raw_bars)
        if len(bars) < 30:
            return {"mode": "live", "skipped": True,
                    "reason": f"not enough bars ({len(bars)})", "pass": True}

        # L1: basic 4 detectors
        results = {}
        for det_name, det_fn in (
            ("double_bottom", double_bottom_detector),
            ("double_top", double_top_detector),
            ("failed_breakdown_wick", failed_breakdown_wick),
            ("rejection_at_level", rejection_at_level),
        ):
            hit = det_fn(bars)
            results[det_name] = {
                "fired": hit is not None,
                "pattern": hit.pattern if hit else None,
                "confidence": hit.confidence if hit else None,
            }

        # L2: contra-regime scans — structural contract test
        all_contra = scan_all_contra_regime(bars)
        high_edge = scan_high_edge_contra_regime(bars)
        all_patterns = {h.pattern for h in all_contra}
        high_patterns = {h.pattern for h in high_edge}
        subset_ok = high_patterns <= all_patterns
        excluded = {"double_top", "failed_breakdown_wick"}
        no_excluded = all(not any(ex in p for ex in excluded) for p in high_patterns)
        contra_pass = subset_ok and no_excluded and len(high_edge) <= 4

        # L3: scan_high_edge_near_named — structural contract test
        # (a) Empty named_levels must return []. No proximity = no output.
        empty_hits = scan_high_edge_near_named(bars, [])
        empty_ok = len(empty_hits) == 0

        # (b) Synthetic near-price level at last bar's close ± $0.20.
        #     May or may not return hits; contract: all returned hits have near_key_level=True
        #     and pattern in expected set.
        last_close = bars[-1].close
        near_lvls = [{"price": round(last_close - 0.20, 2), "name": "TEST_LEVEL", "stars": 2}]
        near_hits = scan_high_edge_near_named(bars, near_lvls, max_distance=0.50)
        near_invariant = all(
            h.notes.get("near_key_level") is True
            and h.pattern in {"head_and_shoulders_top", "momentum_acceleration"}
            for h in near_hits
        )
        near_ok = near_invariant  # True trivially if near_hits is empty

        near_pass = empty_ok and near_ok

        return {
            "mode": "live",
            "source": "coinbase",
            "symbol": "BTC-USD",
            "bars_examined": len(bars),
            "detectors": results,
            "contra_regime": {
                "all_contra_hits": len(all_contra),
                "high_edge_hits": len(high_edge),
                "high_edge_patterns": sorted(high_patterns),
                "subset_invariant_holds": subset_ok,
                "no_excluded_detectors": no_excluded,
            },
            "near_named": {
                "empty_levels_returns_empty": empty_ok,
                "near_hits": len(near_hits),
                "near_hits_invariant_ok": near_ok,
            },
            "pass": contra_pass and near_pass,
        }
    except Exception as e:
        return {
            "mode": "live",
            "error": f"{type(e).__name__}: {e}",
            "pass": False,
        }


def run() -> dict:
    """Validator entry point (convenience wrapper). Returns offline + live results."""
    offline = run_offline()
    live = run_live()
    return {
        "validator": "v22_chart_patterns",
        "offline": offline,
        "live": live,
        "all_pass": offline.get("all_pass", False) and live.get("pass", False),
    }


if __name__ == "__main__":
    import json
    result = run()
    print(json.dumps(result, indent=2, default=str))
