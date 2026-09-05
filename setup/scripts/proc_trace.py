"""proc_trace.py -- event-driven process-creation tracer (GOAL-SILENT-RIG-2026-09-05 R4a).

WHY THIS EXISTS: window_leak_hook.py's own attribution (S3, 2026-09-05) can only name
processes that are STILL ALIVE in the toolhelp snapshot it takes right after a hide -- a
short-lived process whose PARENT has already exited by the time the hide fires is invisible
to it ("recent_procs=[... (parent=?)]" in the 14:00:0x incident log is exactly this: 4
pythonw.exe processes whose parent could not be named because it was already gone). This
tracer closes that gap by recording EVERY process creation the instant it happens, with its
parent's name/cmdline looked up IMMEDIATELY (so a parent that dies a heartbeat later is still
named in the record) -- window_leak_hook.py's attribution can then cross-reference this file
instead of a live (and by definition already-stale) toolhelp snapshot.

ARCHITECTURE -- event-driven, NOT polling:
    proc_trace.py (this file, run under SYSTEM pythonw)
        -> spawns a HIDDEN child powershell.exe (CREATE_NO_WINDOW, stdout piped)
           running proc_trace_watcher.ps1, which does
               Register-CimIndicationEvent -Query
                 "SELECT * FROM __InstanceCreationEvent WITHIN 0.2
                  WHERE TargetInstance ISA 'Win32_Process'"
           -- WMI's own eventing subsystem delivers a notification the moment a process is
           created (polled internally by WMI at the 0.2s WITHIN granularity, but this
           process never polls the process table itself -- it blocks on Wait-Event until WMI
           delivers). The watcher looks up the new process's parent via Get-CimInstance
           immediately (same event tick) and emits ONE compact JSON line per process to its
           own stdout.
    this file reads the child's stdout line-by-line and writes each parsed row to
    automation/state/logs/proc-trace-<date>.jsonl (rotates at local midnight, capped at
    PROC_TRACE_CAP_BYTES per day -- writes silently stop once the cap is hit for the day, a
    daily rotation clears it).

A pure-ctypes ETW consumer would avoid the powershell hop entirely, but ETW session/consumer
setup (NT Kernel Logger or a manifest-based provider, ring-buffer callback marshaling) is a
much larger, much more fragile surface for a Windows-only, single-box tool than shelling out
once to a battle-tested WMI eventing query -- the spec explicitly allows either approach, and
this repo already trusts wmic-based process-table reads (crypto_twin_keepalive.py,
quote_recorder_keepalive.py) as its Windows-process-introspection primitive, so a
Register-CimIndicationEvent child is the lower-risk, easier-to-verify choice here.

BOUNDED, NEVER BLOCKS A HIDE: window_leak_hook.py's read of this file is a plain file-tail
(open, seek near the end, read a bounded number of recent lines) wrapped in its own
try/except -- this tracer's own health (spawn failure, a stalled watcher, a full log dir) can
never delay or crash a window hide.

Guard: backtest/tests/test_proc_trace_2026_09_05.py -- drives every pure function
(_parse_trace_line, _log_path_for_date, _within_cap, write_trace_row, run_watcher_loop) with
fixture text, never spawns a real powershell.exe/CIM subscription.
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
    _sys.stdout = open(_log_dir / f"proc-trace-runner-{_log_date}.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / f"proc-trace-runner-{_log_date}.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
LOG_DIR = STATE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
RUNNER_LOG_FILE = LOG_DIR / f"proc-trace-runner-{dt.date.today().isoformat()}.log"
PID_FILE = STATE_DIR / "proc-trace.pid"

WATCHER_PS1 = Path(__file__).resolve().parent / "proc_trace_watcher.ps1"

# Bounded, per-day cap (spec: "cap 20 MB"). Rotation is daily (a new file name each day);
# once the CURRENT day's file reaches this size, further rows for that day are dropped
# rather than growing the file unbounded -- exactly the same "bounded, exclude nothing else"
# shape as window_leak_hook.py's own log growth discipline.
PROC_TRACE_CAP_BYTES = 20 * 1024 * 1024

REQUIRED_FIELDS = ("ts_local", "pid", "ppid", "name", "cmdline", "parent_name",
                   "parent_cmdline", "session_id")


def _runner_log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with RUNNER_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def _log_path_for_date(d: dt.date, log_dir: Path = LOG_DIR) -> Path:
    """PURE: the daily-rotated trace file path for a given date."""
    return log_dir / f"proc-trace-{d.isoformat()}.jsonl"


def _parse_trace_line(line: str) -> Optional[dict]:
    """PURE: parse one JSON line emitted by proc_trace_watcher.ps1 into a normalized dict,
    or None if the line is blank / not valid JSON / missing a required field. Never raises --
    a single malformed line from the watcher must never crash the whole tracer."""
    line = line.strip()
    if not line:
        return None
    try:
        row = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(row, dict):
        return None
    if not all(k in row for k in REQUIRED_FIELDS):
        return None
    try:
        return {
            "ts_local": int(row["ts_local"]),
            "pid": int(row["pid"]),
            "ppid": int(row["ppid"]),
            "name": str(row["name"] or ""),
            "cmdline": str(row["cmdline"] or ""),
            "parent_name": (str(row["parent_name"]) if row["parent_name"] else None),
            "parent_cmdline": (str(row["parent_cmdline"]) if row["parent_cmdline"] else None),
            "session_id": int(row["session_id"]),
        }
    except (TypeError, ValueError):
        return None


def _within_cap(path: Path, cap_bytes: int = PROC_TRACE_CAP_BYTES) -> bool:
    """PURE (aside from the one stat() call): True iff writing one more row to `path` would
    stay under the daily cap. A file that doesn't exist yet is always under cap."""
    try:
        return path.stat().st_size < cap_bytes
    except OSError:
        return True


def write_trace_row(row: dict, log_dir: Path = LOG_DIR,
                     cap_bytes: int = PROC_TRACE_CAP_BYTES,
                     today: Optional[dt.date] = None) -> Optional[Path]:
    """Append one normalized row (as produced by _parse_trace_line) to today's rotated
    trace file as one compact JSON line, unless the file is already at/over cap for the day
    (silently dropped -- matches window_leak_hook.py's own fail-open discipline: a full log
    must never crash the tracer). Returns the path written, or None if capped/failed."""
    today = today or dt.date.today()
    path = _log_path_for_date(today, log_dir=log_dir)
    if not _within_cap(path, cap_bytes=cap_bytes):
        return None
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
        return path
    except OSError:
        return None


def run_watcher_loop(
    lines: Iterable[str],
    write_fn: Callable[[dict], Optional[Path]] = write_trace_row,
    stop_check: Optional[Callable[[], bool]] = None,
) -> int:
    """PURE(ish) core loop: consume an iterable of raw lines (real: the watcher child's
    stdout; test: a fixture list), parse each with _parse_trace_line, write valid rows via
    write_fn. Returns the count of rows written. `stop_check` (if given) is polled once per
    line and breaks the loop when it returns True -- lets tests bound an otherwise-infinite
    real stdout iterator without needing a real subprocess.

    Never raises on a single bad line: a parse failure or write failure for one line must
    never stop the tracer from processing the next one (window_leak_hook.py depends on this
    file staying alive across a long uptime, exactly like the window-leak hook's own
    per-event try/except)."""
    written = 0
    for raw in lines:
        if stop_check is not None and stop_check():
            break
        try:
            row = _parse_trace_line(raw)
            if row is None:
                continue
            if write_fn(row) is not None:
                written += 1
        except Exception as ex:  # noqa: BLE001 -- one bad line must never kill the loop
            _runner_log(f"line error (skipped): {ex}")
            continue
    return written


def _spawn_watcher() -> "subprocess.Popen | None":
    """Spawn the hidden PowerShell watcher child (CREATE_NO_WINDOW, stdout piped). Returns
    None (logged) rather than raising if powershell.exe or the watcher script is missing --
    this must fail open, never crash the parent process."""
    powershell = "powershell.exe"
    if not WATCHER_PS1.exists():
        _runner_log(f"FATAL: watcher script missing at {WATCHER_PS1}")
        return None
    try:
        return subprocess.Popen(
            [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(WATCHER_PS1)],
            cwd=str(REPO),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW,
            text=True, bufsize=1, encoding="utf-8", errors="ignore",
        )
    except Exception as ex:  # noqa: BLE001
        _runner_log(f"FATAL: failed to spawn watcher: {ex}")
        return None


def _child_stdout_lines(proc: "subprocess.Popen") -> Iterator[str]:
    """Real (non-test) line source: iterate the watcher child's stdout forever."""
    assert proc.stdout is not None
    for line in proc.stdout:
        yield line


def main() -> int:
    PID_FILE.write_text(str(_os.getpid()), encoding="utf-8")
    proc = _spawn_watcher()
    if proc is None:
        return 1
    _runner_log(f"watcher spawned pid={proc.pid}")
    try:
        run_watcher_loop(_child_stdout_lines(proc))
    except Exception as ex:  # noqa: BLE001 -- never let the outer loop crash unlogged
        _runner_log(f"FATAL: watcher loop crashed: {ex}")
        return 1
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
    _runner_log("watcher child exited -- proc_trace.py stopping")
    return 0


if __name__ == "__main__":
    sys.exit(main())
