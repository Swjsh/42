"""station_presence.py -- PC-input-idle presence for the Station "TV face"
(GOAL-GAMMA-STATION-2026-09-13 item 4/6 re-scope: J dropped the Wyze-camera
presence plan -- "why do I need a Raspberry Pi" -- in favor of reading THIS
PC's own idle time via the Windows GetLastInputInfo API).

PRIVACY: reads only a single timestamp (the OS's own record of the last
mouse/keyboard event) -- never keystrokes, never mouse coordinates, never a
screenshot of any monitor. There is no way to reconstruct WHAT J typed or
clicked from this API; it can only ever answer "how long since anything
happened system-wide."

Writes automation/state/station/presence.json:
    {present: bool (idle_s < 300), idle_s, ts_et, transitions_today}

On an absent -> present transition (J just came back to the keyboard) between
06:00 and 09:15 ET, plays the latest morning-brief wav ONCE per day -- capped
at 2 greetings/day, logged to presence-ledger.jsonl.

PLAYER NOTE (verified, not assumed): the spec asked to reuse "the existing
player in gamma_speak.py" -- that file (and daily_brief.py, its only caller)
was read in full; neither one plays audio locally. gamma_speak.py only
SYNTHESIZES a wav (for Discord attachment / dashboard <audio> playback);
there is no PlaySound/winsound/SoundPlayer call anywhere in this repo (grepped
for all three, zero hits). Rather than invent a call that doesn't exist, this
module plays the EXISTING wav files that pipeline already produces via
Python's own stdlib `winsound` module (ships with Windows Python, zero new
pip dependencies -- not a new "audio library" in the sense the spec meant to
forbid).

Wired into the SAME 5-min Gamma_StationKiosk fire as the kiosk launcher
(station_kiosk.ps1 -Start calls this --once BEFORE its own kiosk check) --
no new scheduled task.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
STATION_DIR = STATE / "station"
PRESENCE_PATH = STATION_DIR / "presence.json"
LEDGER_PATH = STATION_DIR / "presence-ledger.jsonl"
INTERNAL_STATE_PATH = STATION_DIR / ".presence-internal.json"

PRESENCE_THRESHOLD_S = 300.0  # < 5 min idle = present
GREETING_START_HHMM = (6, 0)
GREETING_END_HHMM = (9, 15)
MAX_GREETINGS_PER_DAY = 2

sys.path.insert(0, str(Path(__file__).resolve().parent))
import station_board  # noqa: E402 -- reuse read_json_or_none / atomic_write_text / append_jsonl
from et_clock import et_now, et_today_str  # noqa: E402


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def get_idle_seconds() -> Optional[float]:
    """Windows GetLastInputInfo -> seconds since the last keyboard/mouse event
    system-wide. Returns None (never raises) on a non-Windows platform or any
    API failure -- fail-open, same contract as every other system probe in
    this build (station_loop.py's _gpu_util_pct, gamma_cockpit_station.py's
    _gpu_util_pct)."""
    if sys.platform != "win32":
        return None
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):  # type: ignore[attr-defined]
            return None
        tick_count = ctypes.windll.kernel32.GetTickCount()  # type: ignore[attr-defined]
        idle_ms = tick_count - info.dwTime
        if idle_ms < 0:
            # GetTickCount wraps roughly every 49.7 days -- a negative diff means
            # it just wrapped; treat as "just active" rather than a huge bogus value.
            return 0.0
        return idle_ms / 1000.0
    except Exception:  # noqa: BLE001
        return None


def _play_wav_async(path: Path) -> bool:
    """Fire-and-forget playback via stdlib winsound (Windows only) -- never
    blocks the 5-min kiosk fire waiting for a ~30-90s brief to finish playing.
    Returns False (never raises) if winsound is unavailable or playback fails
    to start."""
    if sys.platform != "win32":
        return False
    try:
        import winsound
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except Exception:  # noqa: BLE001
        return False


def _latest_morning_brief_wav() -> Optional[Path]:
    """Most recently modified automation/state/gamma-voice-brief-*-morning.wav
    (daily_brief.py's exact naming convention, verified against real files on
    disk -- gamma-voice-brief-YYYYMMDD-morning.wav) -- "latest" per the spec's
    own wording, not strictly required to be today's, so a greeting fired
    slightly before/after the brief's own generation still finds something to
    play."""
    try:
        candidates = sorted(
            STATE.glob("gamma-voice-brief-*-morning.wav"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
    except OSError:
        return None
    return candidates[0] if candidates else None


def _in_greeting_window(now_et: datetime) -> bool:
    hhmm = (now_et.hour, now_et.minute)
    return GREETING_START_HHMM <= hhmm <= GREETING_END_HHMM


def _read_internal_state() -> dict:
    data = station_board.read_json_or_none(INTERNAL_STATE_PATH)
    return data if isinstance(data, dict) else {}


def _write_internal_state(state: dict) -> None:
    station_board.atomic_write_text(INTERNAL_STATE_PATH, json.dumps(state, ensure_ascii=False))


def run_once(*, now_utc: Optional[datetime] = None,
             idle_fn: Optional[Callable[[], Optional[float]]] = None,
             play_fn: Optional[Callable[[Path], bool]] = None,
             latest_wav_fn: Optional[Callable[[], Optional[Path]]] = None) -> dict:
    """One presence tick. Every dependency is injectable so tests never touch
    a real Windows API, a real audio device, or real ledger/state files under
    the repo -- see backtest/tests/test_station_presence.py."""
    idle_fn = idle_fn or get_idle_seconds
    play_fn = play_fn or _play_wav_async
    latest_wav_fn = latest_wav_fn or _latest_morning_brief_wav
    now_utc = now_utc or datetime.now(timezone.utc)
    now_et = et_now(now_utc=now_utc)
    today = et_today_str(now_utc=now_utc)

    idle_s = idle_fn()
    present = (idle_s is not None) and (idle_s < PRESENCE_THRESHOLD_S)

    internal = _read_internal_state()
    if internal.get("date") != today:
        internal = {"date": today, "transitions_today": 0, "greetings_today": 0, "last_present": False}

    was_present = bool(internal.get("last_present", False))
    transitioned_to_present = present and not was_present
    if transitioned_to_present:
        internal["transitions_today"] = int(internal.get("transitions_today", 0)) + 1

    greeted = False
    ledger_rows = []
    if transitioned_to_present and _in_greeting_window(now_et):
        if int(internal.get("greetings_today", 0)) >= MAX_GREETINGS_PER_DAY:
            ledger_rows.append({"ts_et": now_et.strftime("%Y-%m-%d %H:%M:%S ET"),
                                "event": "greeting_capped", "greetings_today": internal.get("greetings_today", 0)})
        else:
            wav = latest_wav_fn()
            if wav is None:
                ledger_rows.append({"ts_et": now_et.strftime("%Y-%m-%d %H:%M:%S ET"),
                                    "event": "greeting_skipped_no_wav"})
            elif play_fn(wav):
                internal["greetings_today"] = int(internal.get("greetings_today", 0)) + 1
                greeted = True
                ledger_rows.append({"ts_et": now_et.strftime("%Y-%m-%d %H:%M:%S ET"),
                                    "event": "greeted", "wav": str(wav)})
            else:
                ledger_rows.append({"ts_et": now_et.strftime("%Y-%m-%d %H:%M:%S ET"),
                                    "event": "greeting_play_failed", "wav": str(wav)})

    if transitioned_to_present:
        ledger_rows.insert(0, {"ts_et": now_et.strftime("%Y-%m-%d %H:%M:%S ET"),
                               "event": "present", "greeted": greeted})

    internal["last_present"] = present
    _write_internal_state(internal)

    presence = {
        "present": present,
        "idle_s": round(idle_s, 1) if idle_s is not None else None,
        "ts_et": now_et.strftime("%Y-%m-%d %H:%M:%S ET"),
        "transitions_today": internal["transitions_today"],
    }
    station_board.atomic_write_text(PRESENCE_PATH, json.dumps(presence, ensure_ascii=False))
    if ledger_rows:
        station_board.append_jsonl(LEDGER_PATH, ledger_rows)
    return presence


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(description="Station presence -- PC input idle time.")
    ap.add_argument("--once", action="store_true", help="run a single tick (the only mode)")
    ap.parse_args(argv)
    row = run_once()
    print(json.dumps(row, ensure_ascii=False))
    return 0  # never nonzero -- a probe failure degrades to present:false, never a scheduler alarm


if __name__ == "__main__":
    raise SystemExit(main())
