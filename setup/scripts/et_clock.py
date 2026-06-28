"""et_clock.py -- single source of truth for Eastern Time on this rig.

WHY THIS EXISTS (TZ-SYSTEMIC, 2026-06-26): the machine moved Ohio (Eastern) ->
Colorado (Mountain). Any code using naive datetime.now() or timezone(timedelta(hours=-4))
AS IF it were ET is now WRONG by 2h at day-level and silently wrong on DST transitions.

CORRECT PATTERN: derive ET from UTC using the DST-aware formula -- this is what
engine_health.py:_et_now() and _et_offset_hours() already do. Those two functions are
extracted here VERBATIM and promoted to the canonical shared clock.

USAGE:
    from et_clock import et_now, et_today_str, ET_TZ

    now_et = et_now()            # naive ET datetime (same semantics as engine_health._et_now)
    today  = et_today_str()      # 'YYYY-MM-DD' in ET
    aware  = datetime.now(ET_TZ) # aware ET datetime (tzinfo = ET_TZ)

NEVER again hardcode -4 or -5. Never derive ET from local time.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional


def _et_offset_hours(dt_utc: datetime) -> int:
    """DST-aware ET offset from UTC.  EDT = -4  (2nd Sun Mar .. 1st Sun Nov).
                                      EST = -5  (otherwise).

    Extracted verbatim from engine_health.py:_et_offset_hours so there is exactly
    ONE implementation.  The rule: US EDT starts on the SECOND Sunday in March
    (02:00 local -> 03:00) and ends on the FIRST Sunday in November (02:00 local ->
    01:00).  We test the UTC instant -- close enough for any scheduling/logging use
    (the ambiguous wall-clock hour around transitions is not a trading concern).
    """
    year = dt_utc.year

    # Second Sunday in March -> DST start
    march_first = datetime(year, 3, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - march_first.weekday()) % 7
    second_sunday_march = march_first + timedelta(days=days_to_sun + 7)
    dst_start = second_sunday_march.replace(hour=7)  # 02:00 ET = 07:00 UTC (pre-DST, EST)

    # First Sunday in November -> DST end
    nov_first = datetime(year, 11, 1, tzinfo=timezone.utc)
    days_to_sun_nov = (6 - nov_first.weekday()) % 7
    first_sunday_nov = nov_first + timedelta(days=days_to_sun_nov)
    dst_end = first_sunday_nov.replace(hour=6)  # 02:00 ET = 06:00 UTC (in DST, EDT)

    if dst_start <= dt_utc < dst_end:
        return -4  # EDT
    return -5  # EST


def et_now(now_utc: Optional[datetime] = None) -> datetime:
    """Return the current moment as a NAIVE Eastern Time datetime.

    Matches the semantics of engine_health.py:_et_now() (which is the CORRECT donor
    pattern) -- naive because the rest of the codebase treats ET timestamps as naive.

    Pass now_utc for deterministic testing (e.g., test Nov-1 DST end).
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    offset = _et_offset_hours(now_utc)
    return (now_utc + timedelta(hours=offset)).replace(tzinfo=None)


def et_offset_hours(dt_utc: datetime) -> int:
    """Public alias for _et_offset_hours -- returns -4 (EDT) or -5 (EST)."""
    return _et_offset_hours(dt_utc)


def et_today_str(now_utc: Optional[datetime] = None) -> str:
    """Return today's date string 'YYYY-MM-DD' in Eastern Time."""
    return et_now(now_utc=now_utc).strftime("%Y-%m-%d")


class _EasternTZ(tzinfo):
    """A DST-aware tzinfo for Eastern Time.

    `timezone` (the built-in fixed-offset class) is a C type and cannot be subclassed.
    We subclass the abstract `tzinfo` base instead.

    Use as:  datetime.now(ET_TZ)  or  utc_dt.astimezone(ET_TZ).
    """

    def utcoffset(self, dt: Optional[datetime]) -> timedelta:
        if dt is None:
            return timedelta(hours=-5)
        # dt may be naive (from aware arithmetic) or already aware.
        # RECURSION GUARD (2026-06-28): if dt is aware *in this very zone* (tzinfo is self),
        # we MUST NOT call dt.astimezone(utc) -- astimezone needs dt.utcoffset(), which re-
        # enters THIS method -> infinite recursion (the confirmed Monday-open fleet-producer
        # crash: build_shared_signal.build()'s default now = datetime.now(utc).astimezone(ET)
        # then strftime("%z") triggered it). For an ET_TZ-aware dt the wall clock already IS
        # the ET local time, so its wall-clock components feed the DST lookup identically to
        # the naive branch (same approximation test_et_clock validates). Only a *foreign*-zone
        # aware dt needs a real astimezone conversion (that tzinfo's utcoffset never calls back).
        if dt.tzinfo is None or dt.tzinfo is self:
            # Naive OR aware-in-ET: treat wall clock as ET-local, approximate UTC for DST lookup.
            utc_approx = datetime(dt.year, dt.month, dt.day,
                                  dt.hour, dt.minute, dt.second, tzinfo=timezone.utc)
        else:
            utc_approx = dt.astimezone(timezone.utc).replace(tzinfo=timezone.utc)
        return timedelta(hours=_et_offset_hours(utc_approx))

    def tzname(self, dt: Optional[datetime]) -> str:
        off = self.utcoffset(dt)
        return "EDT" if off == timedelta(hours=-4) else "EST"

    def dst(self, dt: Optional[datetime]) -> timedelta:
        off = self.utcoffset(dt)
        return timedelta(hours=1) if off == timedelta(hours=-4) else timedelta(0)

    def fromutc(self, dt: datetime) -> datetime:
        # datetime.astimezone() calls fromutc internally; dt arrives as aware-UTC.
        if dt.tzinfo is not self:
            raise ValueError("fromutc: dt.tzinfo is not ET_TZ")
        off = timedelta(hours=_et_offset_hours(dt.replace(tzinfo=timezone.utc)))
        return (dt.replace(tzinfo=None) + off).replace(tzinfo=self)

    def __repr__(self) -> str:
        return "ET_TZ"


# The canonical ET tzinfo object -- use as timezone argument to datetime.now(ET_TZ)
ET_TZ = _EasternTZ()


def et_weekday(now_utc: Optional[datetime] = None) -> int:
    """Return the current weekday in Eastern Time (Monday=0, Sunday=6).

    Use instead of datetime.now().weekday() when the local machine is NOT Eastern.
    """
    return et_now(now_utc=now_utc).weekday()
