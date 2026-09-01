"""Keepalive for market_hours_keepawake.py -- the daemon that holds the box awake in RTH.

WHY THIS EXISTS (J 2026-08-31). market_hours_keepawake.py is launched ONCE per day by
Gamma_MarketKeepAwake at 07:45 ET and is expected to run unattended to 16:10 ET. On
2026-08-31 it died silently at 09:23 ET -- 99 ticks in, empty stderr, process gone,
`api_failures: 0`. Nothing noticed and nothing restarted it; the gap was found by hand at
09:34 ET only because a session happened to read engine-health.json. Between 09:23 and the
manual restart at 09:36 the box was free to idle-sleep mid-session, which is precisely the
2026-08-14 failure that cost -$1,569 (see market_hours_keepawake.py's own docstring).

ROOT CAUSE OF THE OUTAGE IS STILL UNKNOWN and this file does not claim to fix it. Ruled out
on the day: the _shared.ps1 reaper (the daemon is in $EXEMPT_DAEMONS), the window-leak
detector (`leaks_total: 0`), quiet_mode (`quiet_active: false`), the circuit breaker
(untripped). What this file fixes is the SECOND failure -- that a death was unrecoverable
for the rest of the session. Prevention is layer 1; this is layer 4, recovery.

MECHANISM. Every fire: if we are inside the daemon's own operating window, assert that
(a) a live process with market_hours_keepawake.py in its command line exists AND
(b) keepawake-heartbeat.json was written within STALE_AFTER_MIN. Either failing means the
daemon is dead or wedged -> relaunch it via the same system-pythonw + run_exe_hidden.vbs
chain the scheduled task uses, and log the restart. Outside the window it is a no-op.

Restarting is SAFE to do redundantly: the daemon's only side effect is
SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED), the OS scopes that flag to the
calling thread and clears it automatically when the process dies, and the daemon exits on its
own at 16:10 ET. A duplicate would assert the same flag and expire the same way -- but the
liveness check makes a duplicate unlikely anyway.

FAIL-OPEN: if process enumeration itself errors we return NO pids but also skip the restart
(unknown liveness must never trigger a blind spawn loop) -- see main()'s `enum_ok` guard.

Stdlib only + system pythonw + run_exe_hidden.vbs, no PowerShell in the spawn chain (C8/L41:
headless Windows spawn = system-pythonw + CREATE_NO_WINDOW, and a powershell.exe hop leaks a
WindowsTerminal -Embedding window per fire).
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
import os as _os
import sys as _sys
from pathlib import Path as _Path

if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "keepawake-keepalive.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "keepawake-keepalive.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
LOG_DIR = STATE / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

BEAT = STATE / "keepawake-heartbeat.json"
STATUS = STATE / "keepawake-keepalive-status.json"
DAEMON = REPO / "setup" / "scripts" / "market_hours_keepawake.py"
VBS = REPO / "setup" / "scripts" / "run_exe_hidden.vbs"
SYS_PYTHONW = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")

# The daemon's own window, minus a grace minute at each edge so we never fight its
# self-scheduled launch (07:45 ET) or its self-exit (16:10 ET).
WINDOW_OPEN = dt.time(7, 47)
WINDOW_CLOSE = dt.time(16, 8)
STALE_AFTER_MIN = 5.0          # daemon ticks every 60s; 5 missed ticks is unambiguous
MARKER = "market_hours_keepawake"

sys.path.insert(0, str(REPO / "setup" / "scripts"))
try:
    from et_clock import et_now   # DST-aware; the ONLY sanctioned ET source (never Bash TZ)
except Exception:  # noqa: BLE001
    def et_now() -> dt.datetime:
        return dt.datetime.now() + dt.timedelta(hours=2)   # box runs Mountain; ET = local+2


def _log(msg: str) -> None:
    line = f"{et_now().isoformat(timespec='seconds')} {msg}"
    print(line)
    try:
        with open(LOG_DIR / f"keepawake-keepalive-{et_now().date().isoformat()}.log", "a",
                  encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def daemon_pids() -> tuple[list[int], bool]:
    """(pids, enumeration_ok). WMI, not tasklist -- we need the CommandLine to match on."""
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | "
        "Where-Object { $_.CommandLine -match '" + MARKER + "' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                             capture_output=True, text=True, timeout=60,
                             creationflags=_CREATE_NO_WINDOW)
    except Exception as exc:  # noqa: BLE001
        _log(f"WARN could not enumerate processes: {exc}")
        return [], False
    if out.returncode != 0:
        _log(f"WARN process enumeration rc={out.returncode}: {out.stderr.strip()[:200]}")
        return [], False
    return [int(t) for t in out.stdout.split() if t.strip().isdigit()], True


def heartbeat_age_min(now: dt.datetime) -> float | None:
    """Minutes since the daemon last wrote its beat. None = absent/unreadable."""
    try:
        raw = json.loads(BEAT.read_text(encoding="utf-8"))
        last = dt.datetime.fromisoformat(str(raw["last_assert_et"]))
    except Exception:  # noqa: BLE001
        return None
    if last.tzinfo is not None and now.tzinfo is None:
        last = last.replace(tzinfo=None)
    elif last.tzinfo is None and now.tzinfo is not None:
        last = last.replace(tzinfo=now.tzinfo)
    return (now - last).total_seconds() / 60.0


def relaunch() -> bool:
    for p in (SYS_PYTHONW, VBS, DAEMON):
        if not p.exists():
            _log(f"CANNOT RESTART: missing {p}")
            return False
    try:
        subprocess.Popen(["wscript.exe", "//nologo", str(VBS), str(SYS_PYTHONW), str(DAEMON)],
                         cwd=str(REPO), creationflags=_CREATE_NO_WINDOW)
        return True
    except Exception as exc:  # noqa: BLE001
        _log(f"RESTART FAILED: {exc}")
        return False


def main() -> int:
    now = et_now()
    state: dict = {"checked_at_et": now.isoformat(timespec="seconds"), "action": "noop",
                   "reason": "", "pids": [], "heartbeat_age_min": None}

    if now.weekday() >= 5 or not (WINDOW_OPEN <= now.time() <= WINDOW_CLOSE):
        state["reason"] = "outside daemon window (weekdays 07:47-16:08 ET)"
        STATUS.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return 0

    pids, enum_ok = daemon_pids()
    age = heartbeat_age_min(now)
    state["pids"] = pids
    state["heartbeat_age_min"] = None if age is None else round(age, 2)

    if not enum_ok:
        # Fail OPEN. We cannot prove death, so we do not spawn. Loud, not silent.
        state["action"] = "skipped_unknown_liveness"
        state["reason"] = "process enumeration failed -- refusing a blind restart"
        _log("SKIP: process enumeration failed; not restarting on unknown liveness")
        STATUS.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return 0

    why: list[str] = []
    if not pids:
        why.append("no live process")
    if age is None:
        why.append("heartbeat unreadable")
    elif age > STALE_AFTER_MIN:
        why.append(f"heartbeat stale {age:.1f}m > {STALE_AFTER_MIN}m")

    if why:
        reason = "; ".join(why)
        _log(f"KEEPAWAKE DOWN ({reason}) -- restarting")
        ok = relaunch()
        state["action"] = "restarted" if ok else "restart_failed"
        state["reason"] = reason
        if ok:
            _log("restart issued")
    else:
        state["reason"] = f"alive (pid {pids[0]}, beat {age:.1f}m old)"

    STATUS.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
