"""Watchdog for discord-bridge.py and discord-watcher.py, in Python.

REPLACES `ensure-discord-bridge-alive.ps1` to eliminate the `wscript -> powershell.exe`
chain that leaks a `WindowsTerminal -Embedding` window per 5-min fire (5/17 evening foot-gun).
Task action: `wscript //nologo run_exe_hidden.vbs <sys-pythonw> <this-file>` -- no
PowerShell anywhere in the chain.

Checks discord-bridge and discord-watcher PIDs (via .pid files). Restarts dead ones via
system pythonw.exe with venv PYTHONPATH set.

HARDENING (2026-06-28, PID-reuse scar):
- _pid_cmdline_match(): verifies the live PID's CommandLine contains the expected script
  filename via `wmic process`.  A reused PID that belongs to a different process (e.g.
  VSHelper) will NOT match and is treated as dead.  Fail-open: if wmic is unavailable
  the check is skipped so a healthy bridge is never false-restarted.
- _heartbeat_stale(): reads discord-bridge-heartbeat.json and flags the bridge as frozen
  if last_tick_at is older than BRIDGE_HEARTBEAT_STALE_MINUTES.  A frozen bridge (alive
  PID, but not polling Discord) is logged as a WARNING so the operator session can restart
  it without an automated restart causing a message flood.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "discord-watchdog.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "discord-watchdog.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_DETACHED_PROCESS = 0x00000008

REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
LOG_DIR = STATE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"discord-watchdog-{dt.date.today().isoformat()}.log"

SYS_PYTHONW = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
VENV_SITE = REPO / "backtest" / ".venv" / "Lib" / "site-packages"

# Path to the heartbeat file written by discord-bridge.py each poll cycle (~15s).
BRIDGE_HEARTBEAT_PATH = STATE_DIR / "discord-bridge-heartbeat.json"
# If the heartbeat is older than this, the bridge is considered frozen (alive PID,
# but not polling).  DO NOT auto-restart a frozen bridge to avoid message floods;
# log a WARNING so the operator session can decide.
BRIDGE_HEARTBEAT_STALE_MINUTES: int = 10

TARGETS = [
    ("discord-bridge", REPO / "setup" / "scripts" / "discord-bridge.py", STATE_DIR / "discord-bridge.pid"),
    ("discord-watcher", REPO / "setup" / "scripts" / "discord-watcher.py", STATE_DIR / "discord-watcher.pid"),
]


def _log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def _pid_alive(pid: int) -> bool:
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        ).decode("utf-8", errors="ignore")
        return str(pid) in out
    except Exception:
        return False


def _read_pid(pid_file: Path) -> int | None:
    if not pid_file.exists():
        return None
    try:
        content = pid_file.read_text(encoding="utf-8").strip()
        return int(content.split("|")[0])
    except Exception:
        return None


def _pid_cmdline_match(pid: int, script_name: str) -> bool:
    """Return True if the process with *pid* has *script_name* in its CommandLine.

    Uses ``wmic process`` to read the full command line.  If wmic is unavailable
    or returns an error the function returns True (fail-open) so a healthy bridge
    is never false-flagged as dead due to a tooling gap.

    This defends against PID reuse: a recycled PID pointing to an unrelated
    process (e.g. VSHelper) will not contain the bridge script name and will
    return False, causing the watchdog to treat it as dead.
    """
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/FORMAT:CSV"],
            stderr=subprocess.DEVNULL,
            timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        ).decode("utf-8", errors="ignore")
        # wmic CSV: first non-empty data line after the header has the CommandLine value.
        for line in out.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("node,"):
                continue
            # line is: Node,CommandLine,ProcessId  -- CommandLine is the second CSV field
            parts = line.split(",", 2)
            if len(parts) >= 2:
                cmdline = parts[1]
                return script_name in cmdline
        # wmic returned no data rows for the PID (process gone).
        return False
    except FileNotFoundError:
        # wmic not available (rare on modern Windows); fail-open.
        return True
    except subprocess.TimeoutExpired:
        return True  # fail-open
    except Exception:
        return True  # fail-open


def _heartbeat_stale(stale_minutes: int = BRIDGE_HEARTBEAT_STALE_MINUTES) -> bool:
    """Return True if the bridge heartbeat file is absent or older than *stale_minutes*.

    The bridge writes ``discord-bridge-heartbeat.json`` each poll cycle (~15 s).
    If the file hasn't been updated for *stale_minutes* the bridge is frozen: the
    PID is alive but the polling loop has stalled.  Callers should LOG a WARNING
    and NOT auto-restart (to avoid message floods) -- let the operator session
    handle the restart.
    """
    if not BRIDGE_HEARTBEAT_PATH.exists():
        return True  # absent = never started or cleaned up
    try:
        raw = BRIDGE_HEARTBEAT_PATH.read_text(encoding="utf-8").strip()
        data = json.loads(raw)
        last_tick_str = data.get("last_tick_at", "")
        if not last_tick_str:
            return True
        # last_tick_at is stored as "YYYY-MM-DDTHH:MM:SSZ" (naive UTC, trailing Z).
        last_tick_str_clean = last_tick_str.rstrip("Z")
        last_tick = dt.datetime.fromisoformat(last_tick_str_clean).replace(
            tzinfo=dt.timezone.utc
        )
        age_minutes = (dt.datetime.now(dt.timezone.utc) - last_tick).total_seconds() / 60.0
        return age_minutes > stale_minutes
    except Exception:
        # Corrupt / unreadable file → treat as stale.
        return True


def _launch(name: str, script: Path) -> int | None:
    if not SYS_PYTHONW.exists():
        _log(f"FATAL: system pythonw missing at {SYS_PYTHONW}")
        return None
    env = os.environ.copy()
    if VENV_SITE.exists():
        env["PYTHONPATH"] = str(VENV_SITE)
        env["VIRTUAL_ENV"] = str(REPO / "backtest" / ".venv")
    try:
        proc = subprocess.Popen(
            [str(SYS_PYTHONW), str(script)],
            cwd=str(REPO),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=_DETACHED_PROCESS | _CREATE_NO_WINDOW,
            close_fds=True,
        )
        _log(f"launched {name} PID={proc.pid}")
        return proc.pid
    except Exception as e:
        _log(f"FATAL: launch {name} failed: {e}")
        return None


def main() -> int:
    any_restart = False
    for name, script, pid_file in TARGETS:
        pid = _read_pid(pid_file)

        # --- primary liveness check: PID present and process alive ---
        pid_is_alive = pid is not None and _pid_alive(pid)

        if pid_is_alive:
            # --- secondary check: verify the live PID is actually our script,
            #     not a reused PID from a different process (e.g. VSHelper). ---
            script_name = script.name  # e.g. "discord-bridge.py"
            if not _pid_cmdline_match(pid, script_name):
                _log(
                    f"WARNING: {name} PID={pid} is alive but CommandLine does not contain "
                    f"'{script_name}' -- PID reuse detected; treating as dead"
                )
                pid_is_alive = False

        if pid_is_alive and name == "discord-bridge":
            # --- tertiary check (bridge only): heartbeat staleness.
            #     A stale heartbeat means the bridge polling loop is frozen.
            #     DO NOT auto-restart a frozen bridge (message-flood risk);
            #     flag for the operator session to handle. ---
            if _heartbeat_stale():
                _log(
                    f"WARNING: {name} PID={pid} appears alive but heartbeat "
                    f"'{BRIDGE_HEARTBEAT_PATH.name}' is stale (>{BRIDGE_HEARTBEAT_STALE_MINUTES} min) "
                    f"-- bridge may be frozen; operator restart required"
                )
                # Do NOT restart; continue to next target.
                continue

        if pid_is_alive:
            continue  # genuinely alive, no-op silent

        any_restart = True
        # Remove stale pid file so the freshly-launched script writes its own.
        try:
            pid_file.unlink(missing_ok=True)
        except Exception:
            pass
        new_pid = _launch(name, script)
        if new_pid is None:
            return 1
        # Give the child ~2s to write its pid file.
        time.sleep(2)
        recheck = _read_pid(pid_file)
        if recheck is not None and _pid_alive(recheck):
            _log(f"  {name} OK (pid={recheck})")
        else:
            _log(f"  {name} FAILED to start (no pid file after launch)")
    if not any_restart:
        _log("all alive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
