"""Hold the box awake through market hours -- the rig cannot trade while asleep.

THE INCIDENT (2026-08-14). One 5h19m hole in the launcher log: 02:27:06 -> 07:46:00 local
(04:27-09:46 ET). The box slept. No premarket, no level refresh (322m stale), no watcher feed,
no 09:30-09:45 ticks -- then a wake-storm at 09:46 in which the scheduler backlog and the
self-healer raced two engine processes into a double entry, and the engine's first look at the
day (stale levels, no warmup) bought the top of a 1.1-point range: -$1,569.

Three independent layers now cover this failure:
  1. THIS DAEMON  -- prevention: hold ES_SYSTEM_REQUIRED so the box cannot idle-sleep during
                     RTH. Registered task carries WakesToRun=true so a box already asleep is
                     woken at 09:10 ET (CAVEAT: WakeToRun needs wake timers permitted by the
                     active power plan; if disallowed the wake silently fails -- which is why
                     layers 2 and 3 exist and this file does not claim to be sufficient).
  2. cold-open guard (heartbeat_core) -- damage control: an engine dark during RTH must
                     observe before it may buy.
  3. healer liveness check (heal-engine.ps1) -- no re-fire of an order-placing process that
                     is already alive.

MECHANISM. SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) -- the documented
Windows API for "I am doing work, do not idle-sleep". It does NOT keep the display on
(deliberately: no ES_DISPLAY_REQUIRED -- J's screen may sleep freely), does NOT block a manual
sleep/lid-close, and clears itself automatically if this process dies (the OS scopes the flag
to the thread). Exits on its own at 16:10 ET.

Stdlib only ON PURPOSE: no pandas/numpy import means no WindowsTerminal -Embedding console
allocation under pythonw (the 2026-08-13 popup root cause), so this is safe on the system
pythonw + wscript hidden chain. Reaper-exempt via _shared.ps1 $EXEMPT_DAEMONS ('by design a
long-running RTH daemon').
"""

from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
import os as _os
import sys as _sys
from pathlib import Path as _Path

if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "keepawake.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "keepawake.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import ctypes
import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
BEAT = STATE / "keepawake-heartbeat.json"

sys.path.insert(0, str(REPO / "setup" / "scripts"))
try:
    from et_clock import et_now  # DST-aware; the ONLY sanctioned ET source (never Bash TZ)
except Exception:  # noqa: BLE001 -- degraded fallback documented in project_tz_systemic_fix
    def et_now() -> dt.datetime:
        return dt.datetime.now() + dt.timedelta(hours=2)   # box runs Mountain; ET = local+2

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
END_ET = dt.time(16, 10)
TICK_S = 60


def _assert_awake() -> bool:
    """Re-assert every tick (defensive: some power managers honor only recent assertions).
    Returns False if the API call itself failed -- logged, never fatal."""
    try:
        prev = ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        return bool(prev)
    except Exception:  # noqa: BLE001
        return False


def _clear() -> None:
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    started = et_now()
    ticks = 0
    api_fail = 0
    while True:
        now = et_now()
        if now.time() >= END_ET or now.weekday() >= 5:
            break
        if not _assert_awake():
            api_fail += 1
        ticks += 1
        # Liveness surface: engine-health-style consumers can verify this daemon actually
        # held the flag through the session rather than assuming it (built != running).
        try:
            BEAT.write_text(json.dumps({
                "started_et": started.isoformat(timespec="seconds"),
                "last_assert_et": now.isoformat(timespec="seconds"),
                "ticks": ticks, "api_failures": api_fail,
                "ends_at_et": f"{now.date()}T{END_ET.isoformat()}",
            }), encoding="utf-8")
        except OSError:
            pass
        time.sleep(TICK_S)
    _clear()
    return 0


if __name__ == "__main__":
    sys.exit(main())
