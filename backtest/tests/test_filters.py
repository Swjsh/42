"""Unit tests for filters — chart-anatomy numerical definitions."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.filters import (  # noqa: E402
    FVG,
    breakdown_bar_bearish,
    detect_confluence,
    detect_fvg,
    detect_level_rejection,
    detect_ribbon_flip_bearish,
    is_decisive_bar,
    range_baseline_20bar,
    vix_direction,
    vol_baseline_20bar,
    volume_divergence_failed,
)
from lib.ribbon import RibbonState  # noqa: E402


# ---------------- vix_direction ----------------

def test_vix_rising_above_deadband():
    assert vix_direction(17.45, 17.30) == "rising"

def test_vix_flat_within_deadband():
    assert vix_direction(17.32, 17.30) == "flat"
    assert vix_direction(17.28, 17.30) == "flat"

def test_vix_falling_below_deadband():
    assert vix_direction(17.10, 17.30) == "falling"


# ---------------- breakdown_bar_bearish ----------------

def _bar(o, h, l, c, v):
    return pd.Series({"open": o, "high": h, "low": l, "close": c, "volume": v})

def test_breakdown_bar_classic():
    """Red body, close < fast EMA, body in lower 40%, volume 1.3x baseline."""
    bar = _bar(100.0, 100.5, 98.5, 99.0, 50000)
    fast_ema = 99.5
    vol_baseline = 30000  # 50K / 30K = 1.67x — passes 1.3x threshold
    assert breakdown_bar_bearish(bar, fast_ema, vol_baseline) is True

def test_breakdown_rejected_green_body():
    bar = _bar(99.0, 100.5, 98.5, 100.0, 50000)
    assert breakdown_bar_bearish(bar, 99.5, 30000) is False

def test_breakdown_close_above_fast_NOW_PASSES():
    """RELAXED 2026-05-07: filter 9 no longer cares about Fast EMA. A red bar
    with above-avg vol passes regardless of close-vs-Fast-EMA. This is the fix
    for the missed 11:50/12:00 735.40 rejection."""
    bar = _bar(100.0, 100.5, 98.5, 99.7, 50000)  # red, vol 1.67x → seller pressure
    assert breakdown_bar_bearish(bar, 99.5, 30000) is True

def test_breakdown_rejected_low_volume():
    """Filter 9 still requires vol >= 1.3x avg."""
    bar = _bar(100.0, 100.5, 98.5, 99.0, 30000)  # red bar, vol 1.0x baseline → no
    assert breakdown_bar_bearish(bar, 99.5, 30000) is False

def test_breakdown_body_shape_NOW_IGNORED():
    """RELAXED 2026-05-07: body-shape clause dropped. A red bar with body in upper
    portion of range still passes if vol is sufficient. This unlocks wick-rejection
    candles that were vetoed by the body-shape clause."""
    bar = _bar(100.5, 101.0, 99.0, 100.4, 50000)  # red bar with body in upper 70%, vol 1.67x
    assert breakdown_bar_bearish(bar, 100.45, 30000) is True


# ---------------- volume_divergence_failed ----------------

def test_no_divergence_when_recovery_volume_low():
    # bar 0 = breakdown (red, vol 50K); bar 1 = recovery green but vol 30K (< breakdown)
    df = pd.DataFrame({
        "open": [100, 99],
        "high": [100.5, 99.6],
        "low": [98.5, 98.9],
        "close": [99, 99.3],   # bar 0 red, bar 1 green
        "volume": [50000, 30000],
    })
    assert volume_divergence_failed(df, 1) is False

def test_divergence_when_recovery_volume_exceeds_breakdown():
    df = pd.DataFrame({
        "open": [100, 99],
        "high": [100.5, 99.8],
        "low": [98.5, 98.9],
        "close": [99, 99.7],
        "volume": [50000, 70000],
    })
    # idx=1 examines bars 0, 1, 2 — but with only 2 bars, function returns False (idx < 3)
    # We need at least 3 bars; let's add one
    df = pd.DataFrame({
        "open": [101, 100, 99],
        "high": [101.5, 100.5, 99.8],
        "low": [100.5, 98.5, 98.9],
        "close": [101, 99, 99.7],
        "volume": [40000, 50000, 70000],
    })
    # bar 1 is breakdown (red, vol 50K), bar 2 is recovery green vol 70K > 50K → divergence
    assert volume_divergence_failed(df, 2) is True


# ---------------- vol/range baselines ----------------

def test_vol_baseline_20():
    df = pd.DataFrame({"volume": [10_000] * 25, "high": [1.0] * 25, "low": [0.5] * 25})
    assert vol_baseline_20bar(df, 22) == pytest.approx(10_000)

def test_range_baseline_20():
    df = pd.DataFrame({"volume": [10_000] * 25, "high": [1.0] * 25, "low": [0.5] * 25})
    assert range_baseline_20bar(df, 22) == pytest.approx(0.5)


# ---------------- triggers ----------------

def test_level_rejection_detected():
    """A bar with high > level and close < level should be flagged as rejecting that level."""
    bar = _bar(720.0, 721.6, 719.5, 720.4, 50000)
    levels = [721.40, 715.0]
    assert detect_level_rejection(bar, levels) == 721.40

def test_level_rejection_picks_highest_when_multiple():
    bar = _bar(720.0, 721.8, 719.5, 720.4, 50000)
    levels = [721.40, 721.60]
    assert detect_level_rejection(bar, levels) == 721.60

def test_no_rejection_when_close_above_level():
    bar = _bar(720.0, 721.6, 719.5, 721.5, 50000)
    levels = [721.40]
    assert detect_level_rejection(bar, levels) is None


def test_ribbon_flip_detected():
    """If recent stacks were [BULL, BULL, MIXED, BEAR], flip to BEAR fired."""
    history = [
        RibbonState(fast=100.5, pivot=100.4, slow=100.3, spread_cents=20, stack="BULL"),
        RibbonState(fast=100.5, pivot=100.4, slow=100.3, spread_cents=20, stack="BULL"),
        RibbonState(fast=100.3, pivot=100.4, slow=100.5, spread_cents=20, stack="MIXED"),
        RibbonState(fast=100.2, pivot=100.4, slow=100.5, spread_cents=30, stack="BEAR"),
    ]
    assert detect_ribbon_flip_bearish(history) is True

def test_no_flip_when_already_bearish():
    history = [
        RibbonState(fast=100.2, pivot=100.4, slow=100.5, spread_cents=30, stack="BEAR"),
        RibbonState(fast=100.2, pivot=100.4, slow=100.5, spread_cents=30, stack="BEAR"),
        RibbonState(fast=100.2, pivot=100.4, slow=100.5, spread_cents=30, stack="BEAR"),
    ]
    assert detect_ribbon_flip_bearish(history) is False


def test_confluence_match():
    assert detect_confluence(721.40, [711.40, 721.50, 730.00]) == 721.50

def test_no_confluence_when_far_from_multi_day():
    assert detect_confluence(721.40, [710.00, 730.00]) is None


# ---------------- is_decisive_bar (T59) ----------------

def test_decisive_bar_body_dominated():
    """Body=0.40, range=0.50 → ratio=0.80 ≥ 0.50 → decisive."""
    bar = _bar(100.0, 100.50, 99.60, 100.40, 1000)  # green, body=0.40, range=0.90
    # body = |100.40-100.00| = 0.40, range = 100.50-99.60 = 0.90 → ratio 0.44
    # Adjust: use tighter range to get clear 0.80 body_pct
    bar = _bar(100.0, 100.50, 100.00, 100.40, 1000)  # body=0.40, range=0.50 → ratio=0.80
    assert is_decisive_bar(bar) is True

def test_decisive_bar_wick_dominated():
    """Body=$0.10, range=$0.60 → ratio=0.17 < 0.50 → indecisive."""
    bar = _bar(100.0, 100.50, 99.90, 100.10, 1000)  # body=0.10, range=0.60 → ratio=0.167
    assert is_decisive_bar(bar) is False

def test_decisive_bar_exactly_at_threshold():
    """Body=range/2 exactly → ratio=0.50 → passes."""
    bar = _bar(100.0, 100.60, 100.00, 100.30, 1000)  # body=0.30, range=0.60 → ratio=0.50
    assert is_decisive_bar(bar) is True

def test_decisive_bar_doji_returns_false():
    """Doji (range=0) → no conviction → returns False."""
    bar = _bar(100.0, 100.0, 100.0, 100.0, 1000)
    assert is_decisive_bar(bar) is False

def test_decisive_bar_custom_threshold():
    """Custom 0.75 threshold: body=0.40/range=0.60 (0.67) fails, body=0.55/range=0.60 (0.92) passes."""
    bar_fail = _bar(100.0, 100.60, 100.00, 100.40, 1000)  # body=0.40, ratio=0.67
    bar_pass = _bar(100.0, 100.60, 100.00, 100.55, 1000)  # body=0.55, ratio=0.92
    assert is_decisive_bar(bar_fail, min_body_ratio=0.75) is False
    assert is_decisive_bar(bar_pass, min_body_ratio=0.75) is True

def test_decisive_bar_red_body():
    """Red bar with decisive body still passes (direction-agnostic)."""
    bar = _bar(100.40, 100.50, 100.00, 100.00, 1000)  # red, body=0.40, range=0.50 → 0.80
    assert is_decisive_bar(bar) is True


# ---------------- detect_fvg (ERL→IRL primitive, 2026-06-14) ----------------

def _ohlc(rows):
    """rows = list of (o,h,l,c). volume filled with a constant."""
    return pd.DataFrame(
        [{"open": o, "high": h, "low": l, "close": c, "volume": 1000} for (o, h, l, c) in rows]
    )


def test_fvg_bullish_detected():
    """low[2]=101.20 > high[0]=100.50 → bullish gap of 0.70."""
    df = _ohlc([
        (100.0, 100.50, 99.80, 100.30),   # candle 0
        (100.30, 101.40, 100.30, 101.30),  # candle 1 = displacement up
        (101.30, 101.80, 101.20, 101.60),  # candle 2 (low 101.20 > high0 100.50)
    ])
    fvg = detect_fvg(df, 2, "bullish", min_gap_dollars=0.10)
    assert fvg is not None
    assert fvg.direction == "bullish"
    assert fvg.gap_bottom == pytest.approx(100.50)
    assert fvg.gap_top == pytest.approx(101.20)
    assert fvg.gap_size == pytest.approx(0.70)
    assert fvg.formed_at_idx == 2


def test_fvg_bearish_detected():
    """high[2]=99.00 < low[0]=99.70 → bearish gap of 0.70."""
    df = _ohlc([
        (100.0, 100.20, 99.70, 99.80),    # candle 0
        (99.80, 99.80, 98.70, 98.80),     # candle 1 = displacement down
        (98.80, 99.00, 98.50, 98.70),     # candle 2 (high 99.00 < low0 99.70)
    ])
    fvg = detect_fvg(df, 2, "bearish", min_gap_dollars=0.10)
    assert fvg is not None
    assert fvg.direction == "bearish"
    assert fvg.gap_bottom == pytest.approx(99.00)
    assert fvg.gap_top == pytest.approx(99.70)
    assert fvg.gap_size == pytest.approx(0.70)


def test_fvg_none_when_overlap():
    """No gap: candle 2 low overlaps candle 0 high → None."""
    df = _ohlc([
        (100.0, 100.50, 99.80, 100.30),
        (100.30, 100.90, 100.10, 100.70),
        (100.70, 101.00, 100.40, 100.80),  # low 100.40 < high0 100.50 → no bullish gap
    ])
    assert detect_fvg(df, 2, "bullish") is None


def test_fvg_respects_min_gap():
    """Gap of 0.05 is below the 0.10 floor → None."""
    df = _ohlc([
        (100.0, 100.50, 99.80, 100.30),
        (100.30, 100.90, 100.40, 100.80),
        (100.80, 101.00, 100.55, 100.90),  # low 100.55 - high0 100.50 = 0.05
    ])
    assert detect_fvg(df, 2, "bullish", min_gap_dollars=0.10) is None
    assert detect_fvg(df, 2, "bullish", min_gap_dollars=0.04) is not None


def test_fvg_guards_index_bounds():
    df = _ohlc([(100.0, 100.5, 99.8, 100.3), (100.3, 101.4, 100.3, 101.3)])
    assert detect_fvg(df, 1, "bullish") is None   # idx < 2
    assert detect_fvg(df, 5, "bullish") is None   # idx out of range


def test_fvg_dataclass_is_frozen():
    fvg = FVG("bullish", 100.5, 101.2, 0.7, 2)
    with pytest.raises(Exception):
        fvg.gap_top = 999.0  # frozen dataclass
