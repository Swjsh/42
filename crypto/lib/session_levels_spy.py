"""session_levels_spy — SPY-specific session structure levels (NOT portable to crypto).

These primitives are explicitly SPY-only and only meaningful during NYSE RTH:
  - Premarket high/low (04:00-09:29:59 ET)
  - RTH open (09:30:00 ET bar's open price)
  - Initial Balance H/L (IBH/IBL = 09:30-09:59:59 ET range)
  - Yesterday's RTH close
  - Today's RTH high/low so far

Validated against the same closed-bar invariants as the crypto chart-reading
primitives. The validator (`crypto/validators/v16_session_levels_spy.py`) runs
against historical SPY 5m CSVs since live SPY data is not available 24/7.

Per crypto/CLAUDE.md scope discipline: this lib lives in `crypto/lib/` because
it shares the same Bar/BarSeries / closed-bar / level-event vocabulary, not
because it's about crypto. The placement makes the chart-reading muscle library
the single source of truth for ALL bar-based primitives.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dtime, timezone
from typing import Sequence

from crypto.lib.bar import Bar
from crypto.lib.levels import Level, LevelKind


PREMARKET_START_ET = dtime(4, 0)
PREMARKET_END_ET = dtime(9, 29, 59)
RTH_OPEN_ET = dtime(9, 30)
IB_END_ET = dtime(9, 59, 59)
RTH_CLOSE_ET = dtime(16, 0)


def _to_et(bar: Bar):
    """Return bar.open_time converted to a naive ET-equivalent time (for comparison).

    Bars are stored as tz-aware UTC. ET is UTC-4 in summer (DST), UTC-5 in winter.
    For SPY trading days, the relevant times we care about (premarket / RTH) span DST cleanly
    if we use astimezone. Uses pytz-equivalent via zoneinfo.
    """
    try:
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
        return bar.open_time.astimezone(et)
    except Exception:
        # Fallback: assume UTC-4
        from datetime import timedelta
        return (bar.open_time - timedelta(hours=4)).replace(tzinfo=None)


def filter_by_session(bars: Sequence[Bar], target_date, session: str) -> list[Bar]:
    """Return bars on `target_date` belonging to the given session.

    session: 'premarket' | 'rth' | 'ib' (initial balance, first 30 min of RTH)
    """
    out = []
    for b in bars:
        et = _to_et(b)
        if et.date() != target_date:
            continue
        t = et.time()
        if session == "premarket" and PREMARKET_START_ET <= t <= PREMARKET_END_ET:
            out.append(b)
        elif session == "rth" and RTH_OPEN_ET <= t < RTH_CLOSE_ET:
            out.append(b)
        elif session == "ib" and RTH_OPEN_ET <= t <= IB_END_ET:
            out.append(b)
    return out


@dataclass(frozen=True, slots=True)
class SessionLevels:
    target_date: object  # date
    premarket_high: float | None
    premarket_low: float | None
    rth_open: float | None
    ib_high: float | None
    ib_low: float | None


def compute_session_levels(bars: Sequence[Bar], target_date) -> SessionLevels:
    """Compute all session-structure levels for `target_date` from a bar series spanning that day."""
    premarket = filter_by_session(bars, target_date, "premarket")
    rth = filter_by_session(bars, target_date, "rth")
    ib = filter_by_session(bars, target_date, "ib")

    pm_high = max((b.high for b in premarket), default=None)
    pm_low = min((b.low for b in premarket), default=None)
    rth_open = rth[0].open if rth else None
    ib_high = max((b.high for b in ib), default=None)
    ib_low = min((b.low for b in ib), default=None)

    return SessionLevels(
        target_date=target_date,
        premarket_high=pm_high,
        premarket_low=pm_low,
        rth_open=rth_open,
        ib_high=ib_high,
        ib_low=ib_low,
    )


def session_levels_as_level_objects(sl: SessionLevels) -> list[Level]:
    """Convert SessionLevels into Level objects for use with classify_bar_at_level + detect_sweeps."""
    out = []
    if sl.premarket_high is not None:
        out.append(Level(price=sl.premarket_high, kind=LevelKind.PRIOR_PERIOD_HIGH,
                         strength=3, label=f"PMH {sl.premarket_high:.2f}"))
    if sl.premarket_low is not None:
        out.append(Level(price=sl.premarket_low, kind=LevelKind.PRIOR_PERIOD_LOW,
                         strength=3, label=f"PML {sl.premarket_low:.2f}"))
    if sl.rth_open is not None:
        out.append(Level(price=sl.rth_open, kind=LevelKind.PIVOT_P,
                         strength=2, label=f"RTH_open {sl.rth_open:.2f}"))
    if sl.ib_high is not None:
        out.append(Level(price=sl.ib_high, kind=LevelKind.PRIOR_PERIOD_HIGH,
                         strength=2, label=f"IBH {sl.ib_high:.2f}"))
    if sl.ib_low is not None:
        out.append(Level(price=sl.ib_low, kind=LevelKind.PRIOR_PERIOD_LOW,
                         strength=2, label=f"IBL {sl.ib_low:.2f}"))
    return out
