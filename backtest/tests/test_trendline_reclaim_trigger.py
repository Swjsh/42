"""TDD test for trendline_reclaim trigger (bull mirror of trendline_rejection, OP 17).

GEOMETRY (see detect_trendline_reclaim_bullish's docstring in lib/filters.py for the
full reasoning): this is the SAME descending-high-pivot line detect_trendline_rejection_bearish
fits, but instead of price rejecting off it (close below, red), price BREAKS ABOVE it
(close above, green) -- the direct complement of the bear pattern, matching playbook.md's
CANDIDATE `TRENDLINE_BREAK_VOLUME` pattern's "CALLS on descending break" geometry.

No real J-anchor trade exists for this newly-built pattern (unlike the bear trigger's
5/1 trade), so the positive fixture is synthetic -- hand-constructed so the SEQUENTIAL
DESCENDING PEAKS pivot search (identical algorithm to the bear function) discovers
exactly 3 decreasing pivots, then a final bar breaks out above the fitted line.

Fixture construction (verified by hand + against the real function, see test bodies):
  - 62-bar `prior_bars`: 2 filler rows, then a 60-bar window with baseline highs ~95.20
    and three elevated pivots at window-relative positions 5/20/35 = highs 100.00/99.00/98.00
    (exactly collinear: slope -1/15 per bar).
  - Fitted descending line projects to $96.3333 at the test bar (window length 60).
  - Test bar O=96.00 H=96.60 L=95.90 C=96.45: high reaches the line (96.60 >= 96.60-ish
    proximity), closes ABOVE it (96.45 > 96.33), and is GREEN (96.45 > 96.00) -> fires,
    returns $96.33.

Also negative tests:
  - Same pivots, but the test bar closes red / below the line -> no fire (rejection
    shape, not breakout -- proves the function discriminates outcome, not just approach).
  - Insufficient lookback (too early) -> no fire.
  - Mutual-exclusivity cross-check on REAL data: the bear trigger's own defining fixture
    (5/1 13:35, J's $470 winning trade) is a REJECTION bar (red, closes below the line) --
    trendline_reclaim must NOT fire on it.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _build_descending_pivot_window(pivots: dict[int, float], n: int = 62,
                                    baseline_high: float = 95.20) -> pd.DataFrame:
    """62-row prior_bars: 2 filler rows (outside the 60-bar lookback window), then 60
    rows at window-relative positions 0..59 (= prior_bars rows 2..61). `pivots` maps
    window-relative position -> the bar's high; all other rows sit at `baseline_high`
    (well below every pivot, so the sequential-max search finds exactly the pivots)."""
    rows = []
    for i in range(n):
        if i < 2:
            rows.append({"open": 90.0, "high": 90.3, "low": 89.8, "close": 90.1, "volume": 100000})
            continue
        wpos = i - 2
        if wpos in pivots:
            hv = pivots[wpos]
            rows.append({"open": hv - 0.5, "high": hv, "low": hv - 0.7, "close": hv - 0.3, "volume": 100000})
        else:
            rows.append({"open": 94.9, "high": baseline_high, "low": 94.7, "close": 94.9, "volume": 100000})
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def descending_pivot_fixture():
    """3 exactly-collinear descending pivots at window-relative 5/20/35 = 100.00/99.00/98.00.
    Fitted line projects to $96.3333 at bar_idx=62 (window length 60)."""
    prior_bars = _build_descending_pivot_window({5: 100.00, 20: 99.00, 35: 98.00})
    return prior_bars, 62


def test_trendline_reclaim_fires_on_synthetic_breakout_bar(descending_pivot_fixture):
    """The defining test: a green bar that reaches the fitted descending line and
    closes above it must fire, returning the projected trendline price (~$96.33)."""
    from lib.filters import detect_trendline_reclaim_bullish

    prior_bars, bar_idx = descending_pivot_fixture
    bar = pd.Series({"open": 96.00, "high": 96.60, "low": 95.90, "close": 96.45, "volume": 500000})

    result = detect_trendline_reclaim_bullish(bar, prior_bars, bar_idx)

    assert result is not None, (
        "trendline_reclaim MUST fire on a green bar that breaks above the fitted "
        f"descending line. Got None. Bar: high={bar['high']:.2f} close={bar['close']:.2f} "
        f"open={bar['open']:.2f}"
    )
    assert 96.03 <= result <= 96.63, (
        f"trendline projected price expected ~$96.33 (+/-$0.30), got ${result:.2f}"
    )


def test_trendline_reclaim_does_not_fire_on_red_rejection_bar(descending_pivot_fixture):
    """Negative: same pivots/line, but the bar is RED and closes back below the line
    (a rejection, not a breakout) -- must NOT fire. Proves the function discriminates
    the terminal outcome, not just the approach to the line."""
    from lib.filters import detect_trendline_reclaim_bullish

    prior_bars, bar_idx = descending_pivot_fixture
    bar_red = pd.Series({"open": 96.50, "high": 96.60, "low": 96.00, "close": 96.10, "volume": 500000})

    result = detect_trendline_reclaim_bullish(bar_red, prior_bars, bar_idx)
    assert result is None, f"should not fire on a red bar closing below the line; got ${result}"


def test_trendline_reclaim_does_not_fire_with_insufficient_lookback(descending_pivot_fixture):
    """Negative: too early in the session (bar_idx < lookback_bars + 2) -- no fire."""
    from lib.filters import detect_trendline_reclaim_bullish

    prior_bars, _ = descending_pivot_fixture
    bar = pd.Series({"open": 96.00, "high": 96.60, "low": 95.90, "close": 96.45, "volume": 500000})

    result = detect_trendline_reclaim_bullish(bar, prior_bars.iloc[:30], 30)
    assert result is None, f"should not fire with only 30 bars of lookback; got ${result}"


def test_trendline_reclaim_does_not_fire_on_real_5_1_rejection_bar():
    """Mutual-exclusivity cross-check on REAL data: the bear trigger's OWN defining
    fixture (5/1 13:35, J's $470 winning trade) is a rejection (red, closes below the
    fitted descending line). trendline_reclaim must NOT fire on the same bar."""
    from lib.filters import detect_trendline_reclaim_bullish, detect_trendline_rejection_bearish
    from autoresearch import runner

    spy, _ = runner.load_data(dt.date(2026, 5, 1), dt.date(2026, 5, 1))
    spy = spy.copy()
    spy["_ts"] = pd.to_datetime(spy["timestamp_et"], utc=True).dt.tz_convert("US/Eastern")
    spy_5_1 = spy[spy["_ts"].dt.date == dt.date(2026, 5, 1)].reset_index(drop=True)

    target = spy_5_1[spy_5_1["_ts"].dt.strftime("%H:%M") == "13:35"]
    target_idx = target.index[0]
    bar = spy_5_1.iloc[target_idx]
    prior_bars = spy_5_1.iloc[:target_idx]

    bear_result = detect_trendline_rejection_bearish(bar, prior_bars, target_idx)
    bull_result = detect_trendline_reclaim_bullish(bar, prior_bars, target_idx)

    assert bear_result is not None, "sanity: the bear trigger must still fire on its own anchor bar"
    assert bull_result is None, (
        f"trendline_reclaim must NOT fire on the SAME bar the bear trigger fires a "
        f"rejection on (mutually exclusive outcomes on one bar). Got bull={bull_result}, "
        f"bear={bear_result}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
