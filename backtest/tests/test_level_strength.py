"""Unit tests for level_strength module."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.level_strength import (  # noqa: E402
    PivotLevels,
    OpeningRange,
    TouchStats,
    StrengthComponents,
    VWAPSnapshot,
    VolumeProfile,
    floor_trader_pivots,
    opening_range,
    count_touches,
    score_level,
    find_confluences,
    filter_by_distance,
    compute_vwap,
    compute_volume_profile,
)


# Floor Trader Pivots

def test_floor_trader_pivots_classic_formula():
    """Worked example: H=750, L=730, C=740 → P=740, R1=750, S1=730, etc."""
    p = floor_trader_pivots(prior_high=750.0, prior_low=730.0, prior_close=740.0)
    assert p.P == pytest.approx(740.0)
    assert p.R1 == pytest.approx(750.0)
    assert p.S1 == pytest.approx(730.0)
    assert p.R2 == pytest.approx(760.0)
    assert p.S2 == pytest.approx(720.0)
    assert p.R3 == pytest.approx(770.0)
    assert p.S3 == pytest.approx(710.0)


def test_floor_trader_pivots_5_8_actual():
    """Compute pivots for 5/9 from 5/8 RTH HLC.

    5/8 RTH: high $738.10 (14:00 spike), low $734.58 (09:40), close ~$737.54.
    These are tomorrow's pivot levels.
    """
    p = floor_trader_pivots(738.10, 734.58, 737.54)
    assert p.P == pytest.approx(736.74, abs=0.01)
    # Sanity checks
    assert p.S1 < p.P < p.R1
    assert p.S2 < p.S1 and p.R1 < p.R2


def test_pivots_as_list_in_order():
    p = floor_trader_pivots(750.0, 730.0, 740.0)
    items = p.as_list()
    prices = [v for _, v in items]
    assert prices == sorted(prices, reverse=True)
    labels = [k for k, _ in items]
    assert labels == ["R3", "R2", "R1", "P", "S1", "S2", "S3"]


# Opening Range

def test_opening_range_first_30min():
    bars = pd.DataFrame({
        "timestamp_et": pd.to_datetime([
            "2026-05-08 09:30", "2026-05-08 09:35", "2026-05-08 09:40",
            "2026-05-08 09:45", "2026-05-08 09:50", "2026-05-08 09:55",
            "2026-05-08 10:00",  # this one is at the cutoff, not included
        ]),
        "high": [735.32, 735.45, 735.30, 736.29, 736.37, 736.65, 736.89],
        "low":  [734.70, 734.86, 734.58, 735.29, 735.86, 735.86, 736.24],
    })
    orh = opening_range(bars, minutes=30)
    assert orh is not None
    assert orh.high == pytest.approx(736.65)
    assert orh.low == pytest.approx(734.58)
    assert orh.minutes == 30


def test_opening_range_returns_none_with_too_few_bars():
    bars = pd.DataFrame({
        "timestamp_et": pd.to_datetime(["2026-05-08 09:30", "2026-05-08 09:35"]),
        "high": [735.32, 735.45], "low": [734.70, 734.86],
    })
    assert opening_range(bars, minutes=30) is None


# Touch counting

def test_count_touches_simple_hold_pattern():
    """Build 3 bars that touch level 100.0 from above and close back above."""
    bars = pd.DataFrame({
        "timestamp_et": pd.to_datetime(["2026-05-08 10:00", "2026-05-08 10:05", "2026-05-08 10:10"]),
        "open":  [100.50, 100.40, 100.30],
        "high":  [100.60, 100.50, 100.40],
        "low":   [99.95,  99.95,  99.92],
        "close": [100.45, 100.35, 100.30],
        "volume": [1000, 1500, 1200],
    })
    stats = count_touches(bars, level_price=100.0, tolerance_usd=0.10)
    assert stats.touch_count == 3
    assert stats.held_count == 3
    assert stats.broken_count == 0


def test_count_touches_break_pattern():
    bars = pd.DataFrame({
        "timestamp_et": pd.to_datetime(["2026-05-08 10:00", "2026-05-08 10:05"]),
        "open":  [100.20, 100.10],
        "high":  [100.30, 100.15],
        "low":   [99.50,  99.20],
        "close": [99.50,  99.20],
        "volume": [2000, 3000],
    })
    stats = count_touches(bars, level_price=100.0, tolerance_usd=0.10)
    assert stats.touch_count == 2
    assert stats.broken_count == 2


def test_count_touches_volume_aggregation():
    bars = pd.DataFrame({
        "timestamp_et": pd.to_datetime(["2026-05-08 10:00", "2026-05-08 10:05"]),
        "open": [100.5, 100.4], "high": [100.6, 100.5],
        "low": [99.9, 99.9], "close": [100.4, 100.3],
        "volume": [5000, 7500],
    })
    stats = count_touches(bars, level_price=100.0, tolerance_usd=0.20)
    assert stats.volume_at_touches == 12500


# Strength scoring

def test_score_3star_classic():
    """5+ touches, recent, multi-tf, with volume → 3-star."""
    s = score_level(touch_count=5, recency_days=0.5, mtf_agreement=3,
                    volume_at_touches=200_000, avg_volume=80_000)
    assert s.stars() == 3
    assert s.total_points() >= 5


def test_score_1star_weak():
    """Single touch, old, single TF, no volume → 1-star."""
    s = score_level(touch_count=1, recency_days=10, mtf_agreement=1,
                    volume_at_touches=10_000, avg_volume=80_000)
    assert s.stars() == 1


def test_score_2star_medium():
    # T54 2026-05-17: log2 curve. Old step gave touch_count=3 a score of 2.0,
    # which pushed total to 3 pts → 2★. New log2 gives touch=3 → 1.0.
    # Genuine 2-star needs 3.0-4.9 pts. Use: touch=7 (1.5) + recent (2) + vol (1) = 4.5 pts.
    s = score_level(touch_count=7, recency_days=1.5, mtf_agreement=1,
                    volume_at_touches=130_000, avg_volume=80_000)
    assert s.stars() == 2
    assert 3.0 <= s.total_points() < 5.0


def test_score_confluence_bumps_score():
    base = score_level(touch_count=2, recency_days=1, mtf_agreement=1,
                       volume_at_touches=20_000, avg_volume=80_000,
                       confluent_with_count=0)
    with_conf = score_level(touch_count=2, recency_days=1, mtf_agreement=1,
                            volume_at_touches=20_000, avg_volume=80_000,
                            confluent_with_count=2)
    assert with_conf.total_points() > base.total_points()


# Confluence detection

def test_find_confluences_groups_nearby_levels():
    levels = [
        {"price": 736.11, "entity_id": "a"},
        {"price": 736.14, "entity_id": "b"},  # 0.03 from a — clusters
        {"price": 730.94, "entity_id": "c"},  # 0.94 from d — does NOT cluster
        {"price": 730.00, "entity_id": "d"},  # 0.25 from e — clusters
        {"price": 729.75, "entity_id": "e"},
        {"price": 720.00, "entity_id": "f"},  # standalone
    ]
    groups = find_confluences(levels, proximity_usd=0.30)
    # Two groups: {a,b} (∆ 0.03) and {d,e} (∆ 0.25). c, f isolated.
    assert len(groups) == 2
    assert sum(len(g.member_ids) for g in groups) == 4


def test_find_confluences_skips_isolated():
    levels = [
        {"price": 100.0, "entity_id": "a"},
        {"price": 105.0, "entity_id": "b"},
        {"price": 110.0, "entity_id": "c"},
    ]
    assert find_confluences(levels, proximity_usd=0.30) == []


# Distance filter

def test_vwap_simple():
    """VWAP of equal-volume bars at known typical prices."""
    bars = pd.DataFrame({
        "high":  [101.0, 102.0, 100.0],
        "low":   [99.0,  100.0, 98.0],
        "close": [100.0, 101.0, 99.0],
        "volume": [1000, 1000, 1000],
    })
    snap = compute_vwap(bars)
    assert snap is not None
    # typical = (h+l+c)/3 = [100, 101, 99] equal-weighted → vwap = 100
    assert snap.vwap == pytest.approx(100.0)
    assert snap.upper_1sigma > snap.vwap
    assert snap.lower_1sigma < snap.vwap


def test_vwap_volume_weighted():
    """Heavy bar at higher price should pull VWAP toward it."""
    bars = pd.DataFrame({
        "high":  [100.0, 105.0],
        "low":   [99.0,  104.0],
        "close": [99.5,  104.5],
        "volume": [100, 9000],
    })
    snap = compute_vwap(bars)
    # heavy bar dominates → VWAP should be near 104.5
    assert snap.vwap > 103.0


def test_volume_profile_basic():
    """A bar with 1000 volume distributed across $99-101 → POC near 100."""
    bars = pd.DataFrame({
        "high":  [101.0, 100.5, 100.2],
        "low":   [99.0,  99.8,  99.8],
        "close": [100.0, 100.0, 100.0],
        "volume": [3000, 5000, 4000],
    })
    vp = compute_volume_profile(bars, bucket_size_usd=0.10)
    assert vp is not None
    assert vp.val <= vp.poc <= vp.vah
    # POC should fall in the 99.8-100.2 range where all bars overlap heavily
    assert 99.5 <= vp.poc <= 100.5


def test_filter_by_distance_drops_far_active():
    levels = [
        {"price": 738.0, "tier": "Active"},
        {"price": 720.0, "tier": "Active"},   # > $5 away from 737
        {"price": 725.0, "tier": "Carry"},    # also far, but Carry is preserved
    ]
    kept, dropped = filter_by_distance(levels, spot=737.0, limit_usd=5.0)
    assert len(kept) == 2  # 738 + 725 (Carry survives)
    assert len(dropped) == 1
    assert dropped[0]["price"] == 720.0
