"""futures_session.py -- the CME equity-index session model (MES/MNQ/ES/NQ).

WHY THIS EXISTS (2026-08-09): every futures component before this one carried an
implicit RTH assumption inherited from the SPY engine (09:30-16:00 ET, weekdays).
Futures do not work that way -- they trade ~23h/day from Sunday 18:00 ET to Friday
17:00 ET with a 17:00-18:00 ET maintenance break Mon-Thu. A staleness watchdog, a
liveness alarm, a "flatten before the break" rule and a "should this tick even run"
gate ALL need one shared, tested answer to "is the market open right now" -- and a
wrong answer is expensive in both directions (a false CLOSED goes blind through a
real session; a false OPEN fires stale-data alarms all weekend).

Hours are the documented ones from markdown/futures/SESSIONS-ROLLOVER-TAX.md sec 1,
which sources CME Group directly:

    weekly open      Sunday 18:00 ET
    weekly close     Friday  17:00 ET
    maintenance      17:00-18:00 ET, Mon-Thu (no execution on any CME product)
    daily settlement 17:00 ET
    RTH              09:30-16:00 ET (the cash-equity window; where our evidence lives)

TIME DISCIPLINE: every entry point takes an explicit ET datetime or asks et_clock for
one. This box runs Mountain time and Bash `TZ` returns UTC here (CLAUDE.md scar) --
there is no naive `datetime.now()` anywhere in this module.

HOLIDAYS: reuses engine_health's cached loader (same source the SPY-side monitors
use). Fails OPEN to "no holidays known" -- for a session gate, wrongly believing the
market is open costs a skipped tick with a logged reason, while wrongly believing it
is closed would silently suppress a real trading session.
"""
from __future__ import annotations

import datetime as dt
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]

# Session boundaries (ET wall clock).
WEEKLY_OPEN_DOW = 6            # Sunday (Python: Mon=0 .. Sun=6)
WEEKLY_OPEN_TIME = dt.time(18, 0)
WEEKLY_CLOSE_DOW = 4           # Friday
WEEKLY_CLOSE_TIME = dt.time(17, 0)
MAINTENANCE_START = dt.time(17, 0)
MAINTENANCE_END = dt.time(18, 0)
RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)


def et_now() -> dt.datetime:
    """Naive ET wall clock via the repo's DST-aware clock. Never a raw local read."""
    p = str(REPO / "setup" / "scripts")
    if p not in sys.path:
        sys.path.insert(0, p)
    from et_clock import et_now as _et_now  # noqa: PLC0415

    return _et_now().replace(tzinfo=None)


@lru_cache(maxsize=1)
def _holidays() -> frozenset:
    """US market holiday dates ('YYYY-MM-DD'). Fails open to empty -- see module docstring."""
    try:
        p = str(REPO / "setup" / "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)
        from engine_health import _load_holidays  # noqa: PLC0415

        return frozenset(_load_holidays() or ())
    except Exception:  # noqa: BLE001 -- session gate fails open, by design
        return frozenset()


def is_holiday(when_et: dt.datetime) -> bool:
    return when_et.strftime("%Y-%m-%d") in _holidays()


def is_maintenance_break(when_et: dt.datetime) -> bool:
    """17:00-18:00 ET Mon-Thu: CME processes settlement, nothing executes."""
    if when_et.weekday() > 3:  # Fri/Sat/Sun handled by the weekly-close logic
        return False
    return MAINTENANCE_START <= when_et.time() < MAINTENANCE_END


def is_session_open(when_et: Optional[dt.datetime] = None) -> bool:
    """True when CME equity-index futures are executing orders at `when_et` (ET).

    The week is one continuous session broken by the daily maintenance hour:
    opens Sunday 18:00, closes Friday 17:00.
    """
    when_et = when_et or et_now()
    dow, tod = when_et.weekday(), when_et.time()

    if dow == 5:                                   # Saturday: always closed
        return False
    if dow == WEEKLY_OPEN_DOW:                     # Sunday: opens at 18:00
        return tod >= WEEKLY_OPEN_TIME
    if dow == WEEKLY_CLOSE_DOW:                    # Friday: closes at 17:00
        return tod < WEEKLY_CLOSE_TIME
    if is_maintenance_break(when_et):              # Mon-Thu 17:00-18:00
        return False
    if is_holiday(when_et):
        return False
    return True


def is_rth(when_et: Optional[dt.datetime] = None) -> bool:
    """True during the cash-equity window (09:30-16:00 ET) on a real session day.

    This is where every piece of our validated evidence lives -- the engine trades
    RTH only until an overnight edge is separately validated (SESSIONS doc sec 1).
    """
    when_et = when_et or et_now()
    if when_et.weekday() > 4 or is_holiday(when_et):
        return False
    return RTH_START <= when_et.time() < RTH_END


def session_phase(when_et: Optional[dt.datetime] = None) -> str:
    """One-word phase for logs/state: RTH | GLOBEX | MAINTENANCE | WEEKEND | HOLIDAY."""
    when_et = when_et or et_now()
    if is_holiday(when_et):
        return "HOLIDAY"
    if not is_session_open(when_et):
        dow, tod = when_et.weekday(), when_et.time()
        weekend = (
            dow == 5
            or (dow == WEEKLY_OPEN_DOW and tod < WEEKLY_OPEN_TIME)
            or (dow == WEEKLY_CLOSE_DOW and tod >= WEEKLY_CLOSE_TIME)
        )
        return "WEEKEND" if weekend else "MAINTENANCE"
    return "RTH" if is_rth(when_et) else "GLOBEX"


def next_open(when_et: Optional[dt.datetime] = None) -> dt.datetime:
    """The next instant the session is open at or after `when_et`.

    Minute-resolution scan bounded to 8 days -- enough to clear a weekend plus a
    holiday, and it terminates rather than looping if the calendar is odd.
    """
    cur = (when_et or et_now()).replace(second=0, microsecond=0)
    limit = cur + dt.timedelta(days=8)
    while cur < limit:
        if is_session_open(cur):
            return cur
        cur += dt.timedelta(minutes=1)
    return cur


def seconds_since_open(when_et: Optional[dt.datetime] = None) -> Optional[int]:
    """Seconds the current session has been running, or None when closed.

    Used by the staleness watchdog: a feed cannot be judged stale until the session
    has been open long enough to have produced a bar.
    """
    when_et = when_et or et_now()
    if not is_session_open(when_et):
        return None
    cur = when_et.replace(second=0, microsecond=0)
    elapsed = 0
    limit = 24 * 60  # a session segment never exceeds 23h; bound the scan
    while elapsed < limit:
        prev = cur - dt.timedelta(minutes=1)
        if not is_session_open(prev):
            break
        cur = prev
        elapsed += 1
    return int((when_et - cur).total_seconds())


__all__ = [
    "et_now", "is_holiday", "is_maintenance_break", "is_session_open", "is_rth",
    "session_phase", "next_open", "seconds_since_open",
    "RTH_START", "RTH_END", "MAINTENANCE_START", "MAINTENANCE_END",
]
