"""TDD test for wick_rejection trigger (CLAUDE.md OP 17).

Fires when a bar pierces a level with a significant upper wick AND closes
back near the level, even if close is technically above the level.

Encodes J's 4/29 10:25 entry: bar high=711.65 (touched 711.4), close=711.48
(0.08 above 711.4), upper wick = 711.65 - 711.48 = $0.17 = 55% of bar range.
J read this as rejection of the 711.4 level. Engine's close-below-level
trigger missed it.

Hand-computed expected behavior:
  Given bar O=711.37 H=711.65 L=711.34 C=711.48 and active level 711.40:
    - bar.high (711.65) > level (711.40)  ✓ touched
    - wick = 0.17, range = 0.31, wick_pct = 55%  ✓ significant
    - close (711.48) within tolerance of level (allow 0.20 above)  ✓
    -> TRIGGER FIRES, returns the level price (711.40)

Also negative tests:
  - Bar that doesn't touch the level
  - Bar with tiny wick (no rejection signal)
  - Bar that closes far above the level (price still rallying through)
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _make_bar(o: float, h: float, l: float, c: float) -> pd.Series:
    return pd.Series({"open": o, "high": h, "low": l, "close": c, "volume": 100000})


def test_wick_rejection_fires_on_4_29_at_10_25():
    """The defining test: 4/29 10:25 bar with level 711.40 must trigger."""
    from lib.filters import detect_wick_rejection_bearish

    bar = _make_bar(o=711.37, h=711.65, l=711.34, c=711.48)
    levels = [711.40]
    result = detect_wick_rejection_bearish(bar, levels)

    assert result == 711.40, (
        f"wick_rejection MUST fire for 4/29 10:25 bar at level 711.40 "
        f"(J's actual entry bar). Got {result}."
    )


def test_wick_rejection_does_not_fire_when_no_level_touched():
    """Negative: bar that doesn't reach any level."""
    from lib.filters import detect_wick_rejection_bearish

    bar = _make_bar(o=710.5, h=710.8, l=710.3, c=710.6)
    levels = [711.40]  # bar.high 710.8 < level 711.40
    assert detect_wick_rejection_bearish(bar, levels) is None


def test_wick_rejection_does_not_fire_with_tiny_wick():
    """Negative: bar pierces level but barely retraces (continuation, not rejection)."""
    from lib.filters import detect_wick_rejection_bearish

    # Bar that pushed through level and closed near the high (not a rejection)
    bar = _make_bar(o=711.40, h=711.65, l=711.38, c=711.62)  # wick = 0.03 = 11% of range
    levels = [711.40]
    assert detect_wick_rejection_bearish(bar, levels) is None


def test_wick_rejection_does_not_fire_when_close_far_above_level():
    """Negative: bar pierces level and closes solidly above (continuation up)."""
    from lib.filters import detect_wick_rejection_bearish

    bar = _make_bar(o=711.40, h=712.50, l=711.30, c=712.30)  # close 0.90 above level
    levels = [711.40]
    assert detect_wick_rejection_bearish(bar, levels) is None
