"""dojo/clock.py — TradingView replay cursor <-> engine bar-time mapping (pure, no I/O).

The lockstep invariant depends on this: TV replay reports a `current_date` epoch; the engine
is fed OUR historical bars. This module maps the cursor epoch to the ET timestamp of the latest
CLOSED 5-min RTH bar at/before the cursor -- the bar the engine scores (mirrors
heartbeat_core._build_payload's trig_idx = n-2 "trigger is the last CLOSED bar" convention).

Pure functions only. All datetimes tz-aware ET. No pandas, no file reads.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
BAR_MINUTES = 5


def resolve_cursor(current_date_epoch: int) -> datetime:
    """TV replay `current_date` (Unix epoch seconds, UTC) -> tz-aware ET datetime.

    TradingView reports the replay cursor as a Unix timestamp. We convert through UTC so DST is
    handled by zoneinfo (never a fixed offset -- this box runs Mountain time; see the project
    TZ scar). Raises on a non-positive epoch (a malformed / uninitialised cursor).
    """
    if not isinstance(current_date_epoch, (int, float)) or current_date_epoch <= 0:
        raise ValueError(f"current_date_epoch must be a positive epoch, got {current_date_epoch!r}")
    return datetime.fromtimestamp(int(current_date_epoch), tz=timezone.utc).astimezone(ET)


def is_rth(cursor_et: datetime) -> bool:
    """True iff cursor is within regular trading hours [09:30, 16:00) ET on a weekday.

    The engine (_build_payload) is RTH-only; a pre-market / after-hours / weekend cursor means
    the engine is idle, which the whisper reports as such -- correct behaviour, not an error.
    """
    _require_aware(cursor_et)
    et = cursor_et.astimezone(ET)
    if et.weekday() >= 5:  # Sat/Sun
        return False
    return RTH_OPEN <= et.timetz().replace(tzinfo=None) < RTH_CLOSE


def latest_closed_5m_bar_et(cursor_et: datetime) -> datetime | None:
    """ET timestamp (bar CLOSE time) of the latest 5-min RTH bar closed at/before the cursor.

    5-min RTH bars close at 09:35, 09:40, ..., 16:00. "Latest closed at/before cursor" = the
    largest 5-min grid time <= cursor, clamped into the session:
      - cursor before 09:35 ET on a trading day -> None (no RTH bar has closed yet; engine idle).
      - cursor at/after 16:00 -> the 16:00 close (last bar of the day).
      - weekend / holiday cursor -> None.
    Returned time is the bar's CLOSE; engine_step slices its bar store to timestamps <= this.
    """
    _require_aware(cursor_et)
    et = cursor_et.astimezone(ET)
    if et.weekday() >= 5:
        return None
    day = et.date()
    first_close = datetime.combine(day, time(9, 35), tzinfo=ET)
    last_close = datetime.combine(day, RTH_CLOSE, tzinfo=ET)
    if et < first_close:
        return None
    if et >= last_close:
        return last_close
    # floor to the previous 5-min grid mark relative to the 09:35 first close
    delta_min = (et - first_close).total_seconds() / 60.0
    steps = int(delta_min // BAR_MINUTES)
    return first_close + timedelta(minutes=BAR_MINUTES * steps)


def _require_aware(dt: datetime) -> None:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("cursor datetime must be timezone-aware")
