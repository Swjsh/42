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

SSR-v1 ADDENDUM (backtest/futures/analysis/SSR-battery/DESIGN.md, "SSR-v1
ADDENDUM" section) adds two OPT-IN behaviors, both defaulted OFF/unchanged so
v0 callers get byte-identical output:

  h4_anchor ('1800' default | '2000'): shifts ONLY the 4H block grid (feeds
  PREV_4H_HIGH/LOW + H4_OPEN). '2000' anchors block starts at wall-clock
  20/00/04/08/12/16 ET instead of 18/22/02/06/10/14. Because the trading-day
  roll is FIXED at 17:00 ET regardless of anchor, a '2000' grid does not line
  up with the day boundary the way '1800' does (v0's anchor coincides with
  the day start, which is why v0 never needed this generalization). Rather
  than let one wall-clock block silently straddle two different trading
  days' worth of bars (a real bug we caught while designing this: bars
  18:00-20:00 of trading day D and bars 16:00-17:00 of trading day D+1 both
  floor-divide into the SAME wall-clock '20:00-anchored' block index, yet
  belong to different trading days 21+ hours apart), each trading day gets
  its OWN independent block SEQUENCE, numbered from that day's own start
  (18:00 D-1), snapping to the anchor grid:
    - if the anchor coincides with the day start (offset 0, i.e. '1800'):
      block_seq = minutes_since_day_start // 240 -- identical to v0.
    - otherwise (offset > 0, i.e. '2000'): a short LEADING block covers
      [day_start, first_anchor_boundary) (block_seq 0; for '2000' this is
      the 2h window 18:00-20:00), then 5 full 4h blocks (block_seq 1..5:
      20-00, 00-04, 04-08, 08-12, 12-16), then a short TRAILING block
      covering [16:00, day_end=17:00) (block_seq 6, 1h -- "last block
      16:00-17:00 short then 17-18 halt" per the addendum). Every block_seq
      is unique within its own trading day, so no two disjoint wall-clock
      windows ever share one in-progress aggregator.

  include_running (bool, default False): adds RUN_DAY_HIGH/LOW and
  RUN_ASIA/LONDON/NY_HIGH/LOW -- the running extreme of the CURRENT
  (in-progress, not yet completed) day/session period, computed ONLY from
  bars strictly before bar i (the [period_start, bar i-1] rule, C6). A
  RUN_* field is None until >= 8 bars of that period have elapsed; the three
  session RUN_* fields are ADDITIONALLY None whenever bar i's own session is
  not that named session (a session's running level only exists DURING that
  session -- day's running level, by contrast, is the only "current" period
  of its kind all day, so it never gets that second gate). Because these are
  live, growing-during-the-period values (unlike every v0 field, which is
  frozen once its period completes), detector.py locks the RUN_* reference
  price at the sweep's pierce bar and never re-reads a later, larger running
  value for that episode's geometry -- see detector.py's own docstring.
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
    also floor-divide into block 5, which is harmless (no bars there).

    This is the v0 (h4_anchor='1800') block grid, kept as its own named
    function for backward compatibility. `_h4_block_seq` below generalizes
    it to arbitrary anchors and is what build_levels actually calls."""
    return _minutes_since_1800(ts) // BLOCK_MINUTES


_H4_ANCHOR_HOURS = {"1800": 18, "2000": 20}


def _parse_h4_anchor(h4_anchor: str) -> int:
    try:
        return _H4_ANCHOR_HOURS[h4_anchor]
    except (KeyError, TypeError):
        raise ValueError(
            f"build_levels: unsupported h4_anchor={h4_anchor!r}; "
            f"expected one of {sorted(_H4_ANCHOR_HOURS)}"
        ) from None


def _h4_block_seq(ts: pd.Timestamp, first_boundary_offset_min: int) -> int:
    """Per-trading-day block sequence number for the 4H grid anchored at
    `first_boundary_offset_min` minutes after the 18:00 ET day start (0 for
    h4_anchor='1800', 120 for '2000' -- see module docstring's ADDENDUM
    section for why this is keyed per-day rather than as a raw wall-clock
    floor-div, and why offset==0 must reduce to exactly `block_index`'s
    m // BLOCK_MINUTES)."""
    m = _minutes_since_1800(ts)
    if first_boundary_offset_min == 0:
        return m // BLOCK_MINUTES
    if m < first_boundary_offset_min:
        return 0
    return 1 + (m - first_boundary_offset_min) // BLOCK_MINUTES


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
    # -- SSR-v1 ADDENDUM: opt-in running-extreme fields (include_running=True
    # only). Default None so constructing a LevelSnapshot without them
    # (every pre-existing v0 call site + test) still works unchanged.
    run_day_high: Optional[float] = None
    run_day_low: Optional[float] = None
    run_asia_high: Optional[float] = None
    run_asia_low: Optional[float] = None
    run_london_high: Optional[float] = None
    run_london_low: Optional[float] = None
    run_ny_high: Optional[float] = None
    run_ny_low: Optional[float] = None

    def sweepable_highs(self) -> list[tuple[str, float]]:
        """Extremes only (SSR-PIVOT-LIQUIDITY-STRATEGY.md section 4) -- opens
        are magnets, never sweep targets, so they are excluded here. RUN_*
        names are included only when their field is non-None (v1 addendum)."""
        pairs = (
            ("PDH", self.prev_day_high),
            ("PWH", self.prev_week_high),
            ("PREV_4H_HIGH", self.prev_4h_high),
            ("ASIA_HIGH", self.asia_high),
            ("LONDON_HIGH", self.london_high),
            ("NY_HIGH", self.ny_high),
            ("RUN_DAY_HIGH", self.run_day_high),
            ("RUN_ASIA_HIGH", self.run_asia_high),
            ("RUN_LONDON_HIGH", self.run_london_high),
            ("RUN_NY_HIGH", self.run_ny_high),
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
            ("RUN_DAY_LOW", self.run_day_low),
            ("RUN_ASIA_LOW", self.run_asia_low),
            ("RUN_LONDON_LOW", self.run_london_low),
            ("RUN_NY_LOW", self.run_ny_low),
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


_RUN_MIN_BARS = 8  # addendum: "None until >= 8 bars of that period have elapsed"


def build_levels(
    bars: pd.DataFrame,
    *,
    h4_anchor: str = "1800",
    include_running: bool = False,
) -> list[Optional[LevelSnapshot]]:
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

    `h4_anchor` ('1800' default | '2000') and `include_running` (default
    False) are the SSR-v1 ADDENDUM opt-ins -- see module docstring. Both
    default to their v0 values, so `build_levels(bars)` is byte-identical to
    the pre-addendum implementation.
    """
    if bars is None or bars.empty:
        raise RuntimeError("build_levels: bars is empty")

    first_boundary_offset = (_parse_h4_anchor(h4_anchor) * 60 - 18 * 60) % MINUTES_PER_DAY

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
    day_bar_count = 0

    cur_week_key: Optional[tuple[int, int]] = None
    cur_week_high = cur_week_low = None

    cur_block_key: Optional[tuple[dt.date, int]] = None
    cur_block_open: Optional[float] = None
    cur_block_high = cur_block_low = None

    cur_session_key: Optional[tuple[dt.date, str]] = None
    cur_session_name: Optional[str] = None
    cur_session_high = cur_session_low = None
    session_bar_count = 0

    out: list[Optional[LevelSnapshot]] = []

    for i in range(n):
        ts = ts_col.iloc[i]
        o, h, l = float(opens[i]), float(highs[i]), float(lows[i])

        day = trading_day(ts)
        week = _iso_week(day)
        blk = (day, _h4_block_seq(ts, first_boundary_offset))
        sess_nm = session_name(ts)
        sess = (day, sess_nm)

        # -- running-extreme snapshot, BEFORE bar i is folded into any
        # in-progress aggregator below (C6: [period start, bar i-1] only).
        run_day_high = run_day_low = None
        run_asia_high = run_asia_low = None
        run_london_high = run_london_low = None
        run_ny_high = run_ny_low = None
        if include_running:
            if day == cur_day_key and day_bar_count >= _RUN_MIN_BARS:
                run_day_high, run_day_low = cur_day_high, cur_day_low
            if sess == cur_session_key and session_bar_count >= _RUN_MIN_BARS:
                if sess_nm == ASIA:
                    run_asia_high, run_asia_low = cur_session_high, cur_session_low
                elif sess_nm == LONDON:
                    run_london_high, run_london_low = cur_session_high, cur_session_low
                elif sess_nm == NY:
                    run_ny_high, run_ny_low = cur_session_high, cur_session_low

        if day != cur_day_key:
            if cur_day_key is not None:
                last_day = _PeriodAgg(cur_day_high, cur_day_low)
            cur_day_key, cur_day_open = day, o
            cur_day_high, cur_day_low = h, l
            day_bar_count = 1
        else:
            cur_day_high = max(cur_day_high, h)
            cur_day_low = min(cur_day_low, l)
            day_bar_count += 1

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
            session_bar_count = 1
        else:
            cur_session_high = max(cur_session_high, h)
            cur_session_low = min(cur_session_low, l)
            session_bar_count += 1

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
            run_day_high=run_day_high,
            run_day_low=run_day_low,
            run_asia_high=run_asia_high,
            run_asia_low=run_asia_low,
            run_london_high=run_london_high,
            run_london_low=run_london_low,
            run_ny_high=run_ny_high,
            run_ny_low=run_ny_low,
        ))

    return out
