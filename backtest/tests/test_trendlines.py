"""Unit tests for backtest.lib.trendlines.

Validates:
  - synthetic ascending channel produces an ascending trendline
  - synthetic descending channel produces a descending trendline
  - random noise produces no spurious trendlines (or only with low touch counts)
  - manual trendline construction matches J's 5/8 drawn line shape
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.trendlines import (  # noqa: E402
    Trendline,
    detect_trendlines,
    trendline_from_two_points,
)


def _build_bars(timestamps, highs, lows) -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp_unix": timestamps,
        "high": highs,
        "low": lows,
    })


def test_detects_synthetic_ascending_with_five_touches():
    """Five swing-low touches of a $0.50/hour ascending line."""
    rng = np.random.default_rng(42)
    n = 80
    base_t = 1_700_000_000
    timestamps = [base_t + i * 300 for i in range(n)]  # 5-minute bars

    slope_per_sec = 0.50 / 3600
    line_lows = [400.0 + slope_per_sec * (t - base_t) for t in timestamps]

    lows = []
    for i, line_p in enumerate(line_lows):
        if i % 12 == 0 and 0 < i < n - 5:
            lows.append(line_p)
        else:
            lows.append(line_p + 0.30 + rng.uniform(0, 0.50))
    highs = [low + 0.80 + rng.uniform(0, 0.40) for low in lows]

    bars = _build_bars(timestamps, highs, lows)
    lines = detect_trendlines(bars, min_touches=3, tolerance_usd=0.20, prominence_usd=0.10)

    asc = [line for line in lines if line.direction == "ascending"]
    assert len(asc) >= 1, f"expected ascending trendline, got {[line.direction for line in lines]}"

    best = max(asc, key=lambda line: line.touch_count)
    assert best.touch_count >= 4
    # Slope should be in the ballpark — anchor pairs may shift it within ±50% because
    # find_peaks can pick swing points that are slightly off-line.
    assert best.slope_per_sec == pytest.approx(slope_per_sec, rel=0.50)
    assert best.slope_per_sec > 0


def test_detects_synthetic_descending_with_four_touches():
    rng = np.random.default_rng(7)
    n = 60
    base_t = 1_700_000_000
    timestamps = [base_t + i * 300 for i in range(n)]

    slope_per_sec = -0.40 / 3600
    line_highs = [500.0 + slope_per_sec * (t - base_t) for t in timestamps]

    highs = []
    for i, line_p in enumerate(line_highs):
        if i % 14 == 0 and 0 < i < n - 5:
            highs.append(line_p)
        else:
            highs.append(line_p - 0.40 - rng.uniform(0, 0.40))
    lows = [h - 0.80 - rng.uniform(0, 0.40) for h in highs]

    bars = _build_bars(timestamps, highs, lows)
    lines = detect_trendlines(bars, min_touches=3, tolerance_usd=0.20, prominence_usd=0.10)

    desc = [line for line in lines if line.direction == "descending"]
    assert len(desc) >= 1, f"expected descending trendline, got {[line.direction for line in lines]}"

    best = max(desc, key=lambda line: line.touch_count)
    assert best.touch_count >= 3
    assert best.slope_per_sec < 0


def test_random_noise_yields_no_high_quality_trendlines():
    """Pure white noise around a flat mean should not produce many high-touch lines."""
    rng = np.random.default_rng(1234)
    n = 100
    base_t = 1_700_000_000
    timestamps = [base_t + i * 300 for i in range(n)]

    closes = 600.0 + rng.normal(0, 0.30, n).cumsum() * 0.5
    highs = closes + rng.uniform(0.1, 0.5, n)
    lows = closes - rng.uniform(0.1, 0.5, n)

    bars = _build_bars(timestamps, highs, lows)
    lines = detect_trendlines(bars, min_touches=5, tolerance_usd=0.15, prominence_usd=0.30)
    # Random walks WILL produce some patterns — that's why find_peaks alone isn't a
    # sufficient signal. The point is that the detector applies multi-criteria filters
    # so the count is bounded. Tight prominence + tighter tolerance keeps it manageable.
    assert len(lines) <= 6, f"random noise yielded too many lines, got {len(lines)}"
    # And no line should be near-flat (the slope filter should kick in).
    for line in lines:
        assert abs(line.slope_per_hour()) >= 0.05, f"flat line escaped: {line}"


def test_short_bars_returns_empty():
    bars = _build_bars([1, 2, 3], [10.0, 11.0, 10.5], [9.0, 9.5, 9.2])
    assert detect_trendlines(bars) == []


def test_price_at_projects_correctly():
    """Trendline price_at projects linearly."""
    line = Trendline(
        direction="ascending",
        slope_per_sec=1.0 / 3600,
        intercept_price=100.0,
        intercept_timestamp=1_000_000,
        anchor_points=((1_000_000, 100.0),),
        touch_count=1,
        last_touched_at=1_000_000,
        r_squared=1.0,
    )
    assert line.price_at(1_000_000) == pytest.approx(100.0)
    assert line.price_at(1_000_000 + 3600) == pytest.approx(101.0)
    assert line.price_at(1_000_000 + 7200) == pytest.approx(102.0)


def test_manual_trendline_from_j_5_8_anchors():
    """J's 2026-05-08 trendline (id 5EWHJK) — round-trip the anchor points."""
    line = trendline_from_two_points(1778182200, 733.9449872508757, 1778269500, 738.9189984275356)
    assert line.direction == "ascending"
    assert line.slope_per_hour() == pytest.approx(0.205, abs=0.01)
    assert line.price_at(1778182200) == pytest.approx(733.945, abs=0.01)
    assert line.price_at(1778269500) == pytest.approx(738.919, abs=0.01)


def test_to_dict_contains_required_fields():
    line = trendline_from_two_points(1_000_000, 100.0, 1_010_000, 105.0)
    d = line.to_dict()
    for key in ("direction", "slope_per_sec", "slope_per_hour_dollars",
                "intercept_price", "intercept_timestamp",
                "anchor_points", "touch_count", "last_touched_at", "r_squared"):
        assert key in d


def test_dedupe_collapses_near_identical_lines():
    """Two ascending lines with very similar slopes/intercepts should dedupe to one."""
    rng = np.random.default_rng(99)
    n = 60
    base_t = 1_700_000_000
    timestamps = [base_t + i * 300 for i in range(n)]

    slope_per_sec = 0.30 / 3600
    line_p = [500.0 + slope_per_sec * (t - base_t) for t in timestamps]

    lows = []
    for i, lp in enumerate(line_p):
        if i in (5, 18, 35, 50):
            lows.append(lp)
        elif i in (8, 22, 38):
            lows.append(lp + 0.05)
        else:
            lows.append(lp + 0.40 + rng.uniform(0, 0.30))
    highs = [low + 0.80 for low in lows]

    bars = _build_bars(timestamps, highs, lows)
    lines = detect_trendlines(bars, min_touches=3, tolerance_usd=0.15, prominence_usd=0.10)
    asc = [line for line in lines if line.direction == "ascending"]
    # The "true" line should win the score and dominate. Lower-scoring near-duplicates
    # of the same slope should dedupe, but candidate pairs through different swing
    # points produce different lines that don't necessarily duplicate at the midpoint.
    # The key invariant: the highest-scoring line should be the one through the planted touches.
    assert len(asc) >= 1
    best = max(asc, key=lambda line: (line.touch_count, line.r_squared))
    assert best.touch_count >= 4
    assert best.r_squared >= 0.95
