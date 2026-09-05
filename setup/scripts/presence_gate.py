"""presence_gate.py -- shared presence-awareness gate for background grinders
(GOAL-SILENT-RIG-2026-09-05 L2).

J's PC must not bog down while he is at the keyboard or in a fullscreen app
(game, video, presentation). This module gives every grinder/keepalive ONE
place to ask "is J actively using this box right now?" before spawning a
worker process or continuing a sweep iteration.

Two independent signals, either one is enough to say "present":
  1. quiet-presence.json (written by quiet_mode.py's `_remember_presence`) shows
     a fullscreen app was foreground within the last FULLSCREEN_WINDOW_S.
  2. Windows' own idle-time counter (GetLastInputInfo) shows keyboard/mouse
     activity within the last IDLE_THRESHOLD_S.

Both checks fail open (return "not present" / large idle) on any error --
a grinder that can't determine presence should default to running, not silently
never running (OP-25 fail-open discipline), while a grinder that positively
detects presence must yield (that's the whole point of this module).

CLI smoke test:
    python setup/scripts/presence_gate.py
    -> prints "PRESENT: <reasons>" or "CLEAR" plus the raw signal readings.
"""
from __future__ import annotations

import ctypes
import datetime as dt
import json
import sys
from pathlib import Path
from typing import NamedTuple, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
PRESENCE_FILE = REPO_ROOT / "automation" / "state" / "quiet-presence.json"

# Defaults per GOAL-SILENT-RIG-2026-09-05 L2: fullscreen within 10 min, or
# keyboard/mouse input within 5 min -> box is "in use", grinders yield.
FULLSCREEN_WINDOW_S = 600
IDLE_THRESHOLD_S = 300


class PresenceCheck(NamedTuple):
    present: bool
    reasons: tuple[str, ...]
    fullscreen_age_s: Optional[float]
    idle_s: Optional[float]


def _fullscreen_age_s(
    presence_file: Path = PRESENCE_FILE, now: Optional[dt.datetime] = None
) -> Optional[float]:
    """Seconds since the last recorded fullscreen-foreground event, or None if
    the file is missing/unparseable/stale-format -- fails open (no signal)."""
    if not presence_file.exists():
        return None
    try:
        data = json.loads(presence_file.read_text(encoding="utf-8"))
        seen = dt.datetime.fromisoformat(data["last_fullscreen_at"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None
    now = now or dt.datetime.now(seen.tzinfo or dt.timezone.utc)
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=now.tzinfo)
    return (now - seen).total_seconds()


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_idle_seconds() -> Optional[float]:
    """Seconds since the last keyboard/mouse input, via Win32 GetLastInputInfo.

    Returns None on any failure (non-Windows, API error) -- fails open, the
    caller treats None as "no signal" rather than "definitely idle".
    """
    if sys.platform != "win32":
        return None
    try:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):  # type: ignore[attr-defined]
            return None
        tick_count = ctypes.windll.kernel32.GetTickCount()  # type: ignore[attr-defined]
        # Both are 32-bit millisecond counters that wrap; handle wraparound by
        # treating a negative delta as "just happened" (0s idle) rather than
        # raising or returning a huge bogus idle time.
        idle_ms = tick_count - lii.dwTime
        if idle_ms < 0:
            idle_ms = 0
        return idle_ms / 1000.0
    except Exception:  # noqa: BLE001 -- fail-open, any ctypes surprise = no signal
        return None


def check_presence(
    *,
    presence_file: Path = PRESENCE_FILE,
    fullscreen_window_s: float = FULLSCREEN_WINDOW_S,
    idle_threshold_s: float = IDLE_THRESHOLD_S,
    now: Optional[dt.datetime] = None,
    idle_seconds_override: Optional[float] = None,
) -> PresenceCheck:
    """The one gate every grinder/keepalive should call before spawning work.

    `idle_seconds_override` lets tests (and non-Windows CI) inject a fake idle
    reading without touching ctypes.
    """
    reasons: list[str] = []

    fs_age = _fullscreen_age_s(presence_file, now=now)
    if fs_age is not None and fs_age < fullscreen_window_s:
        reasons.append(f"fullscreen app foreground {fs_age:.0f}s ago (<{fullscreen_window_s:.0f}s)")

    idle_s = idle_seconds_override if idle_seconds_override is not None else get_idle_seconds()
    if idle_s is not None and idle_s < idle_threshold_s:
        reasons.append(f"last input {idle_s:.0f}s ago (<{idle_threshold_s:.0f}s)")

    return PresenceCheck(
        present=bool(reasons), reasons=tuple(reasons), fullscreen_age_s=fs_age, idle_s=idle_s
    )


def should_yield(**kwargs) -> bool:
    """Convenience boolean wrapper around check_presence() for call sites that
    just need a yes/no ('should I skip/pause this iteration?')."""
    return check_presence(**kwargs).present


def main(argv=None) -> int:
    result = check_presence()
    if result.present:
        print(f"PRESENT: {'; '.join(result.reasons)}")
    else:
        print("CLEAR")
    print(f"  fullscreen_age_s={result.fullscreen_age_s} idle_s={result.idle_s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
