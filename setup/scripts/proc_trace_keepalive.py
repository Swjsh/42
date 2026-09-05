"""Keepalive for proc_trace.py's resident process-creation tracer (GOAL-SILENT-RIG-2026-09-05
R4a). Modeled directly on crypto_twin_keepalive.py's proven pattern (pid-file +
process-table cross-check liveness, system pythonw launch, DETACHED_PROCESS|CREATE_NO_WINDOW).

WHY A KEEPALIVE: proc_trace.py is meant to run continuously (it is the thing
window_leak_hook.py's attribution reads for "what was created in the last 2s" -- a gap in
the trace is a gap in the next incident's evidence). Its own child (the hidden PowerShell
CIM subscription) can die independently of the Python parent (a WMI provider restart, a
transient CIM error) -- this keepalive fires every 5 min via Gamma_ProcTraceKeepalive,
checks the live process table for a `proc_trace.py` process, and relaunches if none is
found.

LIVENESS CHECK: cross-checks the live process table (wmic, CREATE_NO_WINDOW) for the literal
`proc_trace.py` command-line marker -- never trusts a bare PID_FILE number alone (a stale pid
can be recycled by Windows into an unrelated process), matching
crypto_twin_keepalive.py/quote_recorder_keepalive.py's shared discipline.

Guard: backtest/tests/test_proc_trace_keepalive_2026_09_05.py (pure-logic relaunch-decision
tests over a fake process-list function -- no real wmic/subprocess call, no real launch).
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
import os as _os
import sys as _sys
import datetime as _dt
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_date = _dt.date.today().isoformat()
    _sys.stdout = open(_log_dir / f"proc-trace-keepalive-{_log_date}.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / f"proc-trace-keepalive-{_log_date}.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_DETACHED_PROCESS = 0x00000008

REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
LOG_DIR = STATE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"proc-trace-keepalive-{dt.date.today().isoformat()}.log"

SYS_PYTHONW = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
PROC_TRACE_SCRIPT = REPO / "setup" / "scripts" / "proc_trace.py"
PID_FILE = STATE_DIR / "proc-trace.pid"

# Specific enough to never match this keepalive's OWN filename (proc_trace_keepalive.py) or
# a test file (test_proc_trace_*.py) -- same false-positive class crypto_twin_keepalive.py's
# own docstring calls out for "crypto_twin_health.py" vs "crypto_twin_keepalive.py".
COMMAND_LINE_MARKER = "proc_trace.py"
EXCLUDE_MARKER = "proc_trace_keepalive.py"


def _log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def _write_pid_file(pid: int, pid_file: Path = PID_FILE) -> None:
    try:
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(json.dumps({"pid": pid, "launched_at": dt.datetime.now().isoformat()}),
                            encoding="utf-8")
    except OSError:
        pass  # fail-open: a pid-file write failure just means the NEXT fire re-launches too


def _live_process_lines() -> str:
    """Real process-table read via wmic (CREATE_NO_WINDOW, no console flash). Isolated so
    the pure relaunch-decision logic below never needs a real subprocess call to be tested."""
    return subprocess.check_output(
        ["wmic", "process", "get", "ProcessId,CommandLine", "/FORMAT:LIST"],
        stderr=subprocess.DEVNULL, timeout=10, creationflags=_CREATE_NO_WINDOW,
    ).decode("utf-8", errors="ignore")


def is_tracer_process_line(line: str) -> bool:
    """PURE: does one process-table CommandLine value belong to a live proc_trace.py
    process? Requires the marker AND excludes this keepalive's own filename, so
    `proc_trace_keepalive.py` (which itself contains the substring `proc_trace`) is never
    mistaken for the tracer being alive."""
    return COMMAND_LINE_MARKER in line and EXCLUDE_MARKER not in line


def find_tracer_pid(process_table_text: str) -> Optional[int]:
    """PURE: parse a wmic '/FORMAT:LIST' CommandLine+ProcessId dump (blank-line-delimited
    records) and return the ProcessId of the first record whose CommandLine matches
    is_tracer_process_line, or None if no such record exists."""
    current: dict[str, str] = {}
    # wmic LIST ends every line with \r\r\n; str.splitlines() treats the lone \r as a line
    # break and splits every record before ProcessId (2026-09-05: 12 tracers spawned).
    for raw in process_table_text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            if is_tracer_process_line(current.get("CommandLine", "")):
                try:
                    return int(current.get("ProcessId", ""))
                except ValueError:
                    pass
            current = {}
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            current[k.strip()] = v.strip()
    if is_tracer_process_line(current.get("CommandLine", "")):
        try:
            return int(current.get("ProcessId", ""))
        except ValueError:
            pass
    return None


def should_relaunch(process_table_text: str) -> "tuple[bool, Optional[int]]":
    """PURE: (relaunch?, live_pid_or_None). relaunch is True iff no live proc_trace.py
    process is found in the given process-table text -- the live process table is the only
    source of truth, never PID_FILE contents alone (same discipline as
    crypto_twin_keepalive.should_relaunch)."""
    pid = find_tracer_pid(process_table_text)
    return (pid is None), pid


def launch_tracer() -> "tuple[bool, Optional[int]]":
    """Launches proc_trace.py via system pythonw + venv PYTHONPATH, detached and hidden.
    Returns (launched_ok, pid). Never raises -- a launch failure is logged and returns
    (False, None)."""
    if not SYS_PYTHONW.exists():
        _log(f"FATAL: system pythonw missing at {SYS_PYTHONW}")
        return False, None
    if not PROC_TRACE_SCRIPT.exists():
        _log(f"FATAL: proc_trace.py missing at {PROC_TRACE_SCRIPT}")
        return False, None

    env = os.environ.copy()
    venv_site = REPO / "backtest" / ".venv" / "Lib" / "site-packages"
    if venv_site.exists():
        env["PYTHONPATH"] = str(venv_site)
        env["VIRTUAL_ENV"] = str(REPO / "backtest" / ".venv")

    cmd = [str(SYS_PYTHONW), str(PROC_TRACE_SCRIPT)]
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(REPO), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            creationflags=_DETACHED_PROCESS | _CREATE_NO_WINDOW, close_fds=True,
        )
        _log(f"launched proc_trace.py PID={proc.pid}")
        _write_pid_file(proc.pid)
        time.sleep(2)
        return True, proc.pid
    except Exception as e:  # noqa: BLE001 -- must never break the scheduled fire
        _log(f"FATAL: launch failed: {e}")
        return False, None


def main() -> int:
    try:
        process_table_text = _live_process_lines()
    except Exception as e:  # noqa: BLE001 -- treat a wmic hiccup as "unknown", attempt launch
        _log(f"WARN: process-table read failed ({e}); attempting launch anyway")
        process_table_text = ""

    relaunch, pid = should_relaunch(process_table_text)
    if not relaunch:
        _log(f"tracer alive (pid={pid})")
        return 0

    ok, new_pid = launch_tracer()
    return 0 if ok else 1


def _main_safe() -> int:
    try:
        return main()
    except Exception as e:  # noqa: BLE001
        _log(f"FATAL unhandled exception: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(_main_safe())
