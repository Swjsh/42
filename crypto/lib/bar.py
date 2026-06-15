"""Bar — immutable OHLCV value type.

The atomic primitive of everything in `crypto.lib`. Always tz-aware UTC internally.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True, slots=True)
class Bar:
    """A single OHLCV bar.

    `open_time` is the START of the bar (when the bar opened).
    `close_time = open_time + granularity_seconds` (computed, not stored).
    A bar is CLOSED iff `close_time <= now`.
    """
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    granularity_seconds: int
    source: str

    def __post_init__(self) -> None:
        if self.open_time.tzinfo is None:
            raise ValueError("Bar.open_time must be tz-aware (UTC preferred)")
        if self.high < self.low:
            raise ValueError(f"Bar invariant violated: high {self.high} < low {self.low}")
        if self.granularity_seconds <= 0:
            raise ValueError(f"Bar.granularity_seconds must be positive, got {self.granularity_seconds}")

    @property
    def close_time(self) -> datetime:
        return self.open_time + timedelta(seconds=self.granularity_seconds)

    def is_closed_at(self, now: datetime) -> bool:
        if now.tzinfo is None:
            raise ValueError("`now` must be tz-aware")
        return self.close_time <= now

    def seconds_until_close(self, now: datetime) -> float:
        return (self.close_time - now).total_seconds()


@dataclass(frozen=True, slots=True)
class BarSeries:
    """A list of Bars with consistent symbol, granularity, source.

    Stored in chronological order (oldest first). Constructor enforces invariants.
    """
    symbol: str
    granularity_seconds: int
    source: str
    bars: tuple[Bar, ...]

    def __post_init__(self) -> None:
        if not self.bars:
            return
        for i, bar in enumerate(self.bars):
            if bar.granularity_seconds != self.granularity_seconds:
                raise ValueError(
                    f"Bar {i} granularity {bar.granularity_seconds} != series {self.granularity_seconds}"
                )
            if bar.source != self.source:
                raise ValueError(f"Bar {i} source {bar.source!r} != series source {self.source!r}")
            if i > 0:
                prev = self.bars[i - 1]
                if bar.open_time <= prev.open_time:
                    raise ValueError(
                        f"Bars not in chronological order at index {i}: "
                        f"{prev.open_time.isoformat()} -> {bar.open_time.isoformat()}"
                    )

    def __len__(self) -> int:
        return len(self.bars)

    def __iter__(self):
        return iter(self.bars)

    def __getitem__(self, idx):
        return self.bars[idx]

    @property
    def first(self) -> Bar:
        return self.bars[0]

    @property
    def last(self) -> Bar:
        return self.bars[-1]
