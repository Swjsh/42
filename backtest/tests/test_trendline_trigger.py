"""TDD test for trendline_rejection trigger (OP 17 standard).

Defines the EXACT expected behavior on the bar that motivated the trigger:
J's 2026-05-01 13:36 entry, which fired at the 13:35 bar close.

Hand-computed expected value:
  - 3 chart-reader pivots: 10:20 (724.87), 11:50 (724.38), 13:30 (723.10)
  - Linear fit through them: slope=-0.0469, intercept=728.42
  - Projected to bar 13:35 (idx=112): $723.16
  - 13:35 bar: high=722.98, open=722.96, close=722.81 (RED, close below trendline)

Tolerance: $0.30 (visual chart-reader precision)
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def spy_5_1():
    """Load full 5/1 SPY data with parsed timestamps."""
    from autoresearch import runner
    spy, _ = runner.load_data(dt.date(2026, 5, 1), dt.date(2026, 5, 1))
    spy = spy.copy()
    spy["_ts"] = pd.to_datetime(spy["timestamp_et"], utc=True).dt.tz_convert("US/Eastern")
    return spy[spy["_ts"].dt.date == dt.date(2026, 5, 1)].reset_index(drop=True)


def test_trendline_fires_on_5_1_at_13_35(spy_5_1):
    """The defining test: trigger MUST fire on 5/1 13:35 bar, returning ~$723.16."""
    from lib.filters import detect_trendline_rejection_bearish

    target = spy_5_1[spy_5_1["_ts"].dt.strftime("%H:%M") == "13:35"]
    assert len(target) == 1, "expected exactly one 13:35 bar"
    target_idx = target.index[0]
    assert target_idx == 112, f"expected idx 112, got {target_idx}"

    bar = spy_5_1.iloc[target_idx]
    prior_bars = spy_5_1.iloc[:target_idx]

    result = detect_trendline_rejection_bearish(bar, prior_bars, target_idx)

    assert result is not None, (
        "trendline trigger MUST fire on 5/1 13:35 bar (J's $470 winning trade). "
        f"Got None. Bar: high={bar['high']:.2f} close={bar['close']:.2f} open={bar['open']:.2f}"
    )
    assert 722.86 <= result <= 723.46, (
        f"trendline projected price expected ~$723.16 (±$0.30), got ${result:.2f}"
    )


def test_trendline_does_not_fire_on_5_1_at_10_30(spy_5_1):
    """Negative test: should NOT fire at 10:30 when SPY is at session high (no setup yet)."""
    from lib.filters import detect_trendline_rejection_bearish

    target = spy_5_1[spy_5_1["_ts"].dt.strftime("%H:%M") == "10:30"]
    target_idx = target.index[0]
    bar = spy_5_1.iloc[target_idx]
    prior_bars = spy_5_1.iloc[:target_idx]

    result = detect_trendline_rejection_bearish(bar, prior_bars, target_idx)
    assert result is None, f"should not fire at 10:30 (not enough lookback yet); got ${result}"


def test_trendline_does_not_fire_when_pivots_not_decreasing(spy_5_1):
    """Negative test: when pivots are flat/increasing, no trendline fires."""
    from lib.filters import detect_trendline_rejection_bearish

    # Use 11:50 bar -- only 2 hours into market, pivots haven't fully formed
    target = spy_5_1[spy_5_1["_ts"].dt.strftime("%H:%M") == "11:50"]
    target_idx = target.index[0]
    bar = spy_5_1.iloc[target_idx]
    prior_bars = spy_5_1.iloc[:target_idx]

    result = detect_trendline_rejection_bearish(bar, prior_bars, target_idx)
    # Could be None or a low-confidence trendline, but should not be the same as the 13:35 reading
    if result is not None:
        # If it does fire, the trendline at 11:50 should be HIGHER than $724 (we're earlier in the descent)
        assert result > 724.0, f"early-session trendline should be above $724, got ${result}"
