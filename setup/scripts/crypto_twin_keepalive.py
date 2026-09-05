"""Keepalive for crypto_twin_health.py's RESIDENT --loop (GOAL-SILENT-RIG-2026-09-05 R2).

WHY THIS EXISTS: Gamma_CryptoTwin used to spawn a fresh `crypto_twin_health.py --live` python
process every single minute, 24/7 -- 1,440 process launches/day, the largest remaining
off-hours load on J's box ("this is a recurring thing it has to stop... i can't have my pc
bogged down", GOAL-SILENT-RIG-2026-09-05 open note). crypto_twin_health.py gained a `--loop`
mode (same file, same run_tick_with_health() tick function, same 1-min cadence, same outputs
-- decisions.jsonl/twin-health.json/soak-log.jsonl -- process SHAPE change only, doctrine
unchanged) so ONE long-lived process now does what 1,440 short-lived ones used to do. This
keepalive replaces the old Gamma_CryptoTwin 1-min task: it fires every 5 min, checks whether
the resident loop process is still alive, and relaunches it if not -- copied directly from
quote_recorder_keepalive.py's proven pattern (same pid-in-status-file + wmic cross-check
liveness test, same bounded--duration-sec daily recycle, same system-pythonw + PYTHONPATH
launch shape).

Not a live-money, secret, or CLAUDE.md-doctrine surface: crypto_twin_health.py is the SAME
gym-only paper twin that has run under Gamma_CryptoTwin since 2026-08-07 (crypto is gym-only
per CLAUDE.md "What I will refuse" -- crypto trading loop is retired outside the twin/gym
harness); this keepalive changes HOW that existing paper process is launched, never its
strategy, its cadence, or the FROZEN_TRADING_PATH files. Ships under the paper-infra /
engine-benefit authoring path (OP-22/OP-26).

WIRING PATTERN (matches quote_recorder_keepalive.py / install-window-leak-detector-keepalive.ps1's
2026-08-08 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT migration):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> crypto_twin_keepalive.py
No PowerShell anywhere in the fire chain (OP-27 L41).

LIVENESS CHECK: crypto_twin_health.py's `--loop` mode does not maintain its own pid-bearing
status file the way quote_recorder.py does (twin-health.json already has an established
schema this file deliberately does not touch -- see crypto_twin_health.py's module docstring
for why twin-health.json's shape is a hard contract for other readers). Instead this keepalive
maintains ITS OWN pid file (crypto-twin-loop.pid, written on every successful launch) and
cross-checks that pid against the live process table (via wmic, CREATE_NO_WINDOW) for the
literal `crypto_twin_health.py --loop` command line -- the same "never trust a bare pid
number, a stale one can be recycled by Windows into an unrelated process" discipline
quote_recorder_keepalive.py's own docstring documents.

BOUNDED RECYCLE (2026-08-13 window-leak-detector lesson: process liveness is not task
liveness -- a wedged-but-alive process can look 'up' forever). crypto_twin_health.py --loop is
launched with a bounded --duration-sec (24h, matching its own DEFAULT_LOOP_DURATION_SEC) so it
exits cleanly on its own every day and the next 5-min keepalive fire relaunches a fresh
process -- identical bounded-recycle shape to quote_recorder_keepalive.py's MAX_RUNTIME_S.

Guard: backtest/tests/test_crypto_twin_keepalive_2026_09_05.py (pure-logic relaunch-decision
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
    _sys.stdout = open(_log_dir / f"crypto-twin-keepalive-{_log_date}.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / f"crypto-twin-keepalive-{_log_date}.stderr.log", "a", buffering=1, encoding="utf-8")
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
LOG_FILE = LOG_DIR / f"crypto-twin-keepalive-{dt.date.today().isoformat()}.log"

SYS_PYTHONW = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
TWIN_HEALTH_SCRIPT = REPO / "setup" / "scripts" / "crypto_twin_health.py"
PID_FILE = STATE_DIR / "crypto-twin-loop.pid"

# The literal marker this keepalive greps a process's own command line for -- specific enough
# to never match this keepalive's OWN filename (crypto_twin_keepalive.py) or a test file
# (test_crypto_twin_keepalive_*.py, test_crypto_twin_health_loop_*.py), which a bare
# "crypto_twin" substring would (same false-positive class quote_recorder_keepalive.py's own
# docstring calls out for its "quote_recorder.py" vs "quote_recorder_keepalive.py" check).
COMMAND_LINE_MARKER = "crypto_twin_health.py"
LOOP_FLAG_MARKER = "--loop"

# crypto_twin_health.py's own DEFAULT_LOOP_DURATION_SEC (24h) -- kept as a literal constant
# here rather than imported, per this file's own zero-import-coupling-with-the-tick-path
# discipline (this is a launcher, not a consumer of the twin's tick logic).
MAX_RUNTIME_S = 24 * 3600


def _log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def _read_pid_file(pid_file: Path = PID_FILE) -> Optional[int]:
    if not pid_file.exists():
        return None
    try:
        return int(json.loads(pid_file.read_text(encoding="utf-8")).get("pid"))
    except Exception:  # noqa: BLE001 -- a malformed/missing pid file just means "unknown", not fatal
        return None


def _write_pid_file(pid: int, pid_file: Path = PID_FILE) -> None:
    try:
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(json.dumps({"pid": pid, "launched_at": dt.datetime.now().isoformat()}),
                            encoding="utf-8")
    except OSError:
        pass  # fail-open: a pid-file write failure just means the NEXT fire re-launches too


def _live_process_lines() -> str:
    """Real process-table read via wmic (CREATE_NO_WINDOW, no console flash). Isolated into
    its own function so the pure relaunch-decision logic below (`should_relaunch`) never
    needs a real subprocess call to be unit tested."""
    return subprocess.check_output(
        ["wmic", "process", "get", "ProcessId,CommandLine", "/FORMAT:LIST"],
        stderr=subprocess.DEVNULL, timeout=10, creationflags=_CREATE_NO_WINDOW,
    ).decode("utf-8", errors="ignore")


def is_loop_process_line(line: str) -> bool:
    """PURE: does one process-table line (a full wmic CommandLine value) belong to a live
    `crypto_twin_health.py --loop` process? Requires BOTH markers so a plain
    `crypto_twin_health.py --live` one-shot (the OLD per-minute task action, which might
    briefly coexist while Fable stages the cutover) is never mistaken for the new resident
    loop being alive."""
    return COMMAND_LINE_MARKER in line and LOOP_FLAG_MARKER in line


def find_loop_pid(process_table_text: str) -> Optional[int]:
    """PURE: parse a wmic '/FORMAT:LIST' CommandLine+ProcessId dump (blank-line-delimited
    records) and return the ProcessId of the first record whose CommandLine matches
    is_loop_process_line, or None if no such record exists. Mirrors
    quote_recorder_keepalive.py's own inline wmic-LIST parsing shape (see that file's
    `_recorder_alive`) but pulled out as a pure function so it is directly unit-testable
    without any real subprocess call."""
    current: dict[str, str] = {}
    for raw in process_table_text.splitlines():
        line = raw.strip()
        if not line:
            if is_loop_process_line(current.get("CommandLine", "")):
                try:
                    return int(current.get("ProcessId", ""))
                except ValueError:
                    pass
            current = {}
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            current[k.strip()] = v.strip()
    if is_loop_process_line(current.get("CommandLine", "")):
        try:
            return int(current.get("ProcessId", ""))
        except ValueError:
            pass
    return None


def should_relaunch(process_table_text: str) -> "tuple[bool, Optional[int]]":
    """PURE: (relaunch?, live_pid_or_None). relaunch is True iff no live
    `crypto_twin_health.py --loop` process is found in the given process-table text.
    This is the ENTIRE relaunch decision -- deliberately not dependent on PID_FILE contents
    at all, so a keepalive fire is correct even the very first time it ever runs (no pid file
    written yet) and self-heals if the pid file is ever deleted/corrupted -- the live process
    table is the only source of truth for 'is it alive', exactly like
    quote_recorder_keepalive.py's own `_recorder_alive` cross-check discipline."""
    pid = find_loop_pid(process_table_text)
    return (pid is None), pid


def launch_loop() -> "tuple[bool, Optional[int]]":
    """Launches crypto_twin_health.py --loop via system pythonw + venv PYTHONPATH, bounded to
    MAX_RUNTIME_S so it recycles daily. Returns (launched_ok, pid). Never raises -- a launch
    failure is logged and returns (False, None), same fail-open contract as
    quote_recorder_keepalive.py's own main()."""
    if not SYS_PYTHONW.exists():
        _log(f"FATAL: system pythonw missing at {SYS_PYTHONW}")
        return False, None
    if not TWIN_HEALTH_SCRIPT.exists():
        _log(f"FATAL: crypto_twin_health.py missing at {TWIN_HEALTH_SCRIPT}")
        return False, None

    env = os.environ.copy()
    venv_site = REPO / "backtest" / ".venv" / "Lib" / "site-packages"
    if venv_site.exists():
        env["PYTHONPATH"] = str(venv_site)
        env["VIRTUAL_ENV"] = str(REPO / "backtest" / ".venv")

    # --live (not --once): the OLD Gamma_CryptoTwin task action ran crypto_twin_health.py
    # --live every minute -- the resident loop must place the SAME real (paper) orders on the
    # SAME cadence, never silently downgrade to watch-only as a side effect of this rewiring.
    cmd = [str(SYS_PYTHONW), str(TWIN_HEALTH_SCRIPT), "--live", "--loop",
           "--duration-sec", str(MAX_RUNTIME_S)]
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(REPO), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            creationflags=_DETACHED_PROCESS | _CREATE_NO_WINDOW, close_fds=True,
        )
        _log(f"launched crypto_twin_health.py --live --loop PID={proc.pid} "
             f"duration={MAX_RUNTIME_S}s (24h recycle)")
        _write_pid_file(proc.pid)
        time.sleep(2)
        return True, proc.pid
    except Exception as e:  # noqa: BLE001 -- must never break the scheduled fire
        _log(f"FATAL: launch failed: {e}")
        return False, None


def main() -> int:
    try:
        process_table_text = _live_process_lines()
    except Exception as e:  # noqa: BLE001 -- a wmic read failure must not crash the keepalive;
        # treat it as "unknown" and attempt a launch anyway (fail toward availability, not
        # toward silently leaving the twin dead because one wmic call hiccuped).
        _log(f"WARN: process-table read failed ({e}); attempting launch anyway")
        process_table_text = ""

    relaunch, pid = should_relaunch(process_table_text)
    if not relaunch:
        _log(f"loop alive (pid={pid})")
        return 0

    ok, new_pid = launch_loop()
    return 0 if ok else 1


def _main_safe() -> int:
    try:
        return main()
    except Exception as e:  # noqa: BLE001
        _log(f"FATAL unhandled exception: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(_main_safe())
