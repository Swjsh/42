"""SSR battery causal session/day/week/4H level engine.

Definitions frozen per backtest/futures/analysis/SSR-battery/DESIGN.md section 3:

  Trading day: 18:00 ET (D-1) -> 17:00 ET (D).
  Sessions:    Asia 18:00-03:00, London 03:00-09:30, New York 09:30-17:00 ET.
  4H blocks:   anchored 18:00 ET -- 18/22/02/06/10/14 (last block 14:00-17:00, 3h).

Every level is CAUSAL: the snapshot attached to bar i derives only from bars
strictly before bar i's own timestamp_et, and only from COMPLETED periods (a
period counts only once its end <= bar i's open time). Session/day/week/4H
highs and lows are the most recently COMPLETED instance of that period type
-- which may be from earlier the same trading day (e.g. Asia's high is known
all through London and New York once Asia has closed).

Implementation is a single forward pass (O(n) in bar count): for each period
type (day, ISO week, 4H block, each of the three named sessions) we track a
"current, in-progress" high/low aggregator and a "last completed" one. A
period transition is detected by comparing consecutive bars' period keys; on
transition the in-progress aggregator (built exclusively from bars strictly
before the transition bar) is finalized into "last completed" BEFORE that
transition bar's own snapshot is built -- so a snapshot never sees its own
bar's contribution to a period it's still inside. This one-pass structure is
what makes the causality mutation test trivially true: bar i's snapshot is a
pure function of bars[0:i+1] read in order, never of anything after i.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd

DAY_ROLL_TIME = dt.time(17, 0)   # trading day D ends here; D+1 begins at 18:00
MINUTES_PER_DAY = 24 * 60
BLOCK_MINUTES = 4 * 60
ASIA, LONDON, NY = "asia", "london", "ny"

# Session-start offsets expressed as minutes-since-18:00 (the trading-day
# anchor), so both session_name and block_index share one clock frame:
#   Asia   starts at minute 0    (18:00)
#   London starts at minute 540  (03:00 next calendar date = 18:00 + 9h)
#   New York starts at minute 930 (09:30 next calendar date = 18:00 + 15.5h)
_LONDON_START_MIN = 9 * 60          # 540
_NY_START_MIN = 15 * 60 + 30        # 930


def _minutes_since_1800(ts: pd.Timestamp) -> int:
    t = ts.time()
    return (t.hour * 60 + t.minute - 18 * 60) % MINUTES_PER_DAY


def trading_day(ts: pd.Timestamp) -> dt.date:
    """The calendar date D of the trading day [D-1 18:00, D 17:00) containing ts.

    Bars at/after 17:00 ET (this also covers the 17:00-18:00 Globex
    maintenance gap, where no bars are ever expected) belong to the NEXT
    trading day's calendar date."""
    d = ts.date()
    return d + dt.timedelta(days=1) if ts.time() >= DAY_ROLL_TIME else d


def session_name(ts: pd.Timestamp) -> str:
    """Asia [18:00,03:00) / London [03:00,09:30) / New York [09:30,17:00).
    Anything from 17:00-18:00 (the dead zone, no bars expected) reads as "ny"
    -- harmless, since real data never lands there."""
    m = _minutes_since_1800(ts)
    if m < _LONDON_START_MIN:
        return ASIA
    if m < _NY_START_MIN:
        return LONDON
    return NY


def block_index(ts: pd.Timestamp) -> int:
    """0..5 for the 4H blocks anchored 18:00 ET (18/22/02/06/10/14); block 5
    nominally spans only 14:00-17:00 (3h) -- the trailing 17:00-18:00 minutes
    also floor-divide into block 5, which is harmless (no bars there)."""
    return _minutes_since_1800(ts) // BLOCK_MINUTES


def _iso_week(d: dt.date) -> tuple[int, int]:
    iso = d.isocalendar()
    return (iso[0], iso[1])


@dataclass(frozen=True)
class LevelSnapshot:
    prev_day_high: Optional[float]
    prev_day_low: Optional[float]
    prev_week_high: Optional[float]
    prev_week_low: Optional[float]
    prev_4h_high: Optional[float]
    prev_4h_low: Optional[float]
    asia_high: Optional[float]
    asia_low: Optional[float]
    london_high: Optional[float]
    london_low: Optional[float]
    ny_high: Optional[float]
    ny_low: Optional[float]
    day_open: Optional[float]
    h4_open: Optional[float]

    def sweepable_highs(self) -> list[tuple[str, float]]:
        """Extremes only (SSR-PIVOT-LIQUIDITY-STRATEGY.md section 4) -- opens
        are magnets, never sweep targets, so they are excluded here."""
        pairs = (
            ("PDH", self.prev_day_high),
            ("PWH", self.prev_week_high),
            ("PREV_4H_HIGH", self.prev_4h_high),
            ("ASIA_HIGH", self.asia_high),
            ("LONDON_HIGH", self.london_high),
            ("NY_HIGH", self.ny_high),
        )
        return [(name, price) for name, price in pairs if price is not None]

    def sweepable_lows(self) -> list[tuple[str, float]]:
        pairs = (
            ("PDL", self.prev_day_low),
            ("PWL", self.prev_week_low),
            ("PREV_4H_LOW", self.prev_4h_low),
            ("ASIA_LOW", self.asia_low),
            ("LONDON_LOW", self.london_low),
            ("NY_LOW", self.ny_low),
        )
        return [(name, price) for name, price in pairs if price is not None]

    def all_levels(self) -> list[tuple[str, float]]:
        opens = [
            (name, price) for name, price in
            (("DAY_OPEN", self.day_open), ("H4_OPEN", self.h4_open))
            if price is not None
        ]
        return self.sweepable_highs() + self.sweepable_lows() + opens


@dataclass
class _PeriodAgg:
    high: float
    low: float


def build_levels(bars: pd.DataFrame) -> list[Optional[LevelSnapshot]]:
    """One causal LevelSnapshot per row of `bars` (ascending, tz-aware ET
    timestamp_et). Raises RuntimeError on empty input (C7 -- no silent
    empty-in/empty-out).

    Every returned entry is a real LevelSnapshot from index 0 onward --
    day_open/h4_open are always knowable from a bar's own (in-progress)
    period, so there is never a genuine warmup gap at the list level. The
    Optional[LevelSnapshot] in the return type is defensive typing per the
    builder contract; individual FIELDS inside each snapshot are None until
    their own period (day/week/4H block/session) has completed at least once
    -- that is where "None until enough history" actually shows up.
    """
    if bars is None or bars.empty:
        raise RuntimeError("build_levels: bars is empty")

    ts_col = bars["timestamp_et"]
    opens = bars["open"].astype(float).to_numpy()
    highs = bars["high"].astype(float).to_numpy()
    lows = bars["low"].astype(float).to_numpy()
    n = len(bars)

    last_day: Optional[_PeriodAgg] = None
    last_week: Optional[_PeriodAgg] = None
    last_block: Optional[_PeriodAgg] = None
    last_session: dict[str, _PeriodAgg] = {}

    cur_day_key: Optional[dt.date] = None
    cur_day_open: Optional[float] = None
    cur_day_high = cur_day_low = None

    cur_week_key: Optional[tuple[int, int]] = None
    cur_week_high = cur_week_low = None

    cur_block_key: Optional[tuple[dt.date, int]] = None
    cur_block_open: Optional[float] = None
    cur_block_high = cur_block_low = None

    cur_session_key: Optional[tuple[dt.date, str]] = None
    cur_session_name: Optional[str] = None
    cur_session_high = cur_session_low = None

    out: list[Optional[LevelSnapshot]] = []

    for i in range(n):
        ts = ts_col.iloc[i]
        o, h, l = float(opens[i]), float(highs[i]), float(lows[i])

        day = trading_day(ts)
        week = _iso_week(day)
        blk = (day, block_index(ts))
        sess_nm = session_name(ts)
        sess = (day, sess_nm)

        if day != cur_day_key:
            if cur_day_key is not None:
                last_day = _PeriodAgg(cur_day_high, cur_day_low)
            cur_day_key, cur_day_open = day, o
            cur_day_high, cur_day_low = h, l
        else:
            cur_day_high = max(cur_day_high, h)
            cur_day_low = min(cur_day_low, l)

        if week != cur_week_key:
            if cur_week_key is not None:
                last_week = _PeriodAgg(cur_week_high, cur_week_low)
            cur_week_key = week
            cur_week_high, cur_week_low = h, l
        else:
            cur_week_high = max(cur_week_high, h)
            cur_week_low = min(cur_week_low, l)

        if blk != cur_block_key:
            if cur_block_key is not None:
                last_block = _PeriodAgg(cur_block_high, cur_block_low)
            cur_block_key, cur_block_open = blk, o
            cur_block_high, cur_block_low = h, l
        else:
            cur_block_high = max(cur_block_high, h)
            cur_block_low = min(cur_block_low, l)

        if sess != cur_session_key:
            if cur_session_key is not None:
                last_session[cur_session_name] = _PeriodAgg(cur_session_high, cur_session_low)
            cur_session_key, cur_session_name = sess, sess_nm
            cur_session_high, cur_session_low = h, l
        else:
            cur_session_high = max(cur_session_high, h)
            cur_session_low = min(cur_session_low, l)

        asia = last_session.get(ASIA)
        london = last_session.get(LONDON)
        ny = last_session.get(NY)

        out.append(LevelSnapshot(
            prev_day_high=last_day.high if last_day else None,
            prev_day_low=last_day.low if last_day else None,
            prev_week_high=last_week.high if last_week else None,
            prev_week_low=last_week.low if last_week else None,
            prev_4h_high=last_block.high if last_block else None,
            prev_4h_low=last_block.low if last_block else None,
            asia_high=asia.high if asia else None,
            asia_low=asia.low if asia else None,
            london_high=london.high if london else None,
            london_low=london.low if london else None,
            ny_high=ny.high if ny else None,
            ny_low=ny.low if ny else None,
            day_open=cur_day_open,
            h4_open=cur_block_open,
        ))

    return out
