"""TDD test for wick_reclaim trigger (bull mirror of wick_rejection, CLAUDE.md OP 17).

Fires when a bar pierces BELOW a support level with a significant lower wick AND
closes back near/above the level, even if close is technically still below it.

Mirror of test_wick_rejection_trigger.py's J 4/29 10:25 fixture, reflected for the
bull side: level 711.40 acting as SUPPORT, bar low pierces to 711.15 (0.25 below,
mirroring the bear fixture's high piercing 0.25 above), close recovers to 711.32
(0.08 below the level, mirroring the bear fixture's close ending 0.08 above),
lower wick = close - low = 0.17 = 54.8% of the $0.31 range (identical wick
magnitude/pct to the bear fixture's upper wick).

Hand-computed expected behavior:
  Given bar O=711.18 H=711.46 L=711.15 C=711.32 and active level 711.40:
    - bar.low (711.15) < level (711.40)              touched, pierced below
    - wick = close - low = 0.17, range = 0.31, wick_pct = 54.8%    significant
    - close (711.32) within tolerance of level (allow 0.10 below)  reclaimed
    -> TRIGGER FIRES, returns the level price (711.40)

Also negative tests (each mirrors the corresponding bear negative test):
  - Bar that doesn't touch the level
  - Bar with tiny wick (no reclaim signal)
  - Bar that closes far below the level (breakdown continuation, not reclaim)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _make_bar(o: float, h: float, l: float, c: float) -> pd.Series:
    return pd.Series({"open": o, "high": h, "low": l, "close": c, "volume": 100000})


def test_wick_reclaim_fires_on_mirrored_4_29_fixture():
    """The defining test: mirror of J's 4/29 10:25 bar, reflected onto a support level."""
    from lib.filters import detect_wick_reclaim_bullish

    bar = _make_bar(o=711.18, h=711.46, l=711.15, c=711.32)
    levels = [711.40]
    result = detect_wick_reclaim_bullish(bar, levels)

    assert result == 711.40, (
        f"wick_reclaim MUST fire on the mirrored 4/29-style bar at level 711.40. "
        f"Got {result}."
    )


def test_wick_reclaim_does_not_fire_when_no_level_touched():
    """Negative: bar that doesn't reach any level (entirely above it)."""
    from lib.filters import detect_wick_reclaim_bullish

    bar = _make_bar(o=712.3, h=712.6, l=712.1, c=712.4)  # bar.low 712.1 > level 711.40
    levels = [711.40]
    assert detect_wick_reclaim_bullish(bar, levels) is None


def test_wick_reclaim_does_not_fire_with_tiny_wick():
    """Negative: bar pierces level but barely retraces (continuation down, not reclaim)."""
    from lib.filters import detect_wick_reclaim_bullish

    # Bar that pushed through level and closed near the low (not a reclaim)
    bar = _make_bar(o=711.40, h=711.50, l=711.28, c=711.32)  # wick = 0.04 = 18% of range
    levels = [711.40]
    assert detect_wick_reclaim_bullish(bar, levels) is None


def test_wick_reclaim_does_not_fire_when_close_far_below_level():
    """Negative: bar pierces support and closes solidly below (breakdown continuation)."""
    from lib.filters import detect_wick_reclaim_bullish

    bar = _make_bar(o=711.40, h=711.50, l=710.30, c=710.50)  # close 0.90 below level
    levels = [711.40]
    assert detect_wick_reclaim_bullish(bar, levels) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
