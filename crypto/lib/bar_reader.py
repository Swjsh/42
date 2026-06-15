"""bar_reader — closed-bar filter.

THE primitive that catches the 2026-05-14 SPY heartbeat foot-gun (OP 25 / L34 / R4).

Foot-gun definition:
  External market-data APIs (TradingView `data_get_ohlcv`, Coinbase `/candles`,
  yfinance `download`) return a series whose LAST element is typically the
  CURRENTLY-IN-PROGRESS bar. Trading logic that scores `series[-1]` reads
  evolving OHLC + accumulating volume — not a closed bar. Decisions made on
  an in-progress bar may flip when the bar actually closes.

The fix (single source of truth here):
  Filter to bars where `close_time <= now`. Use the LATEST such bar as
  "last closed bar." Reject series where no bar is closed yet.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from crypto.lib.bar import Bar, BarSeries


@dataclass(frozen=True, slots=True)
class ClosedBarResult:
    last_closed: Optional[Bar]
    in_progress: Optional[Bar]
    now: datetime
    bars_rejected_as_in_progress: int
    verdict: str  # "ok" | "no_closed_bars" | "stale_data" | "future_bar"

    @property
    def ok(self) -> bool:
        return self.verdict == "ok"


def last_closed_bar(series: BarSeries, now: datetime) -> ClosedBarResult:
    """Return the most recent bar whose close_time <= now.

    Also returns the in-progress bar (if any) for transparency, and counts
    how many bars at the tail were rejected as in-progress.
    """
    if now.tzinfo is None:
        raise ValueError("`now` must be tz-aware")
    if len(series) == 0:
        return ClosedBarResult(None, None, now, 0, "no_closed_bars")

    # Walk newest-first, find first bar where close_time <= now
    in_progress: Optional[Bar] = None
    rejected = 0
    last_closed: Optional[Bar] = None
    for bar in reversed(series.bars):
        if bar.is_closed_at(now):
            last_closed = bar
            break
        if in_progress is None:
            in_progress = bar
        rejected += 1

    if last_closed is None:
        # All bars are in the future relative to `now` — clock skew or test data
        return ClosedBarResult(None, in_progress, now, rejected, "future_bar")

    # Staleness: closed-bar should be no older than 2× granularity behind now
    age_seconds = (now - last_closed.close_time).total_seconds()
    if age_seconds > 2 * series.granularity_seconds:
        return ClosedBarResult(last_closed, in_progress, now, rejected, "stale_data")

    return ClosedBarResult(last_closed, in_progress, now, rejected, "ok")


def closed_bars_only(series: BarSeries, now: datetime) -> BarSeries:
    """Return a new BarSeries containing only bars closed at `now`."""
    closed = tuple(bar for bar in series.bars if bar.is_closed_at(now))
    return BarSeries(
        symbol=series.symbol,
        granularity_seconds=series.granularity_seconds,
        source=series.source,
        bars=closed,
    )
