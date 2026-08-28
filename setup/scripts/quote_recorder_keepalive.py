"""Keepalive for quote_recorder.py (Task B1's independent exit-quote side-channel).

WHY THIS EXISTS (2026-08-28 conductor fire): quote_recorder.py was BUILT and verified
2026-08-28 (the "we log NBBO on ~25 of 128 entry events and ZERO on exits; every
slippage number is an assumption" gap) but was never given an always-on scheduled
task -- its own self_check.py docstring said "arming a new always-on scheduled task
is J's call" and left it at that. It was started manually once (~17:18 ET the same
day), and the moment that manual process exited, self_check.py started flagging
QUOTE-RECORDER RED forever (the staleness check has no way to distinguish "never
armed" from "armed and died" once a status file exists at all -- see its own
SILENT-UNTIL-DEPLOYED docstring). This closes that gap the same way every other
always-on daemon in this repo is kept alive: a 5-min keepalive fire that checks
liveness via the status file's own `pid` field (cross-checked against the live
process table so a stale pid number never falsely reads "alive") and relaunches if
dead.

Not a live-money, secret, or CLAUDE.md-doctrine surface: quote_recorder.py is a
READ-ONLY market-data recorder (Alpaca REST GETs for options-chain NBBO) that writes
to analysis/quote-tape/*.jsonl and its own status file -- it places no orders and
mutates no trading-path state. Ships under the paper-infra / engine-benefit
authoring path (OP-22/OP-26), with rail-4 discipline observed anyway: guard test +
git-revert path + REVOKE report in STATUS.md.

WIRING PATTERN (matches install-window-leak-detector-keepalive.ps1 /
install-ccr-keepalive.ps1's 2026-08-08 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT migration):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> quote_recorder_keepalive.py
No PowerShell anywhere in the fire chain (OP-27 L41).

BOUNDED RECYCLE (2026-08-13 window-leak-detector lesson: process liveness is not
task liveness -- a wedged-but-alive process can look "up" forever). quote_recorder
is launched with a bounded --duration-sec so it exits cleanly on its own every
MAX_RUNTIME_S and the next 5-min keepalive fire relaunches a fresh process. This is
simpler than the window-leak-detector's summary-derived recycle (no risk of scoring
a dead process's stale counters) because quote_recorder's own --duration-sec flag
already does the bounding -- the keepalive only ever needs to ask "is a process
alive right now", never "how old is it".
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "quote-recorder-keepalive.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "quote-recorder-keepalive.stderr.log", "a", buffering=1, encoding="utf-8")
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
LOG_FILE = LOG_DIR / f"quote-recorder-keepalive-{dt.date.today().isoformat()}.log"

SYS_PYTHONW = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
RECORDER_SCRIPT = REPO / "setup" / "scripts" / "quote_recorder.py"
STATUS_FILE = STATE_DIR / "quote-recorder-status.json"

# quote_recorder.py's own duration -- bounded so the process recycles itself daily
# rather than accumulating unbounded runtime (2026-08-13 wedge-detection lesson).
MAX_RUNTIME_S = 24 * 3600


def _log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def _recorder_alive() -> tuple[bool, "int | None"]:
    """(alive?, pid). Reads the pid quote_recorder.py's own status file last wrote, then
    cross-checks it against the live process table (via wmic, CREATE_NO_WINDOW) so a stale
    pid number recycled by Windows into an unrelated process never falsely reads 'alive'."""
    if not STATUS_FILE.exists():
        return False, None
    try:
        pid = int(json.loads(STATUS_FILE.read_text(encoding="utf-8")).get("pid"))
    except Exception:
        return False, None
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/FORMAT:LIST"],
            stderr=subprocess.DEVNULL, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        ).decode("utf-8", errors="ignore")
        # "quote_recorder.py" (with extension) specifically -- a bare "quote_recorder"
        # substring also matches this keepalive's OWN filename (quote_recorder_keepalive.py)
        # and any test file naming pattern (test_quote_recorder_keepalive_*.py), which would
        # falsely read a totally unrelated live process as "the recorder is alive".
        if "quote_recorder.py" in out:
            return True, pid
        return False, pid
    except Exception:
        return False, pid


def main() -> int:
    alive, pid = _recorder_alive()
    if alive:
        _log(f"recorder alive (pid={pid})")
        return 0

    if not SYS_PYTHONW.exists():
        _log(f"FATAL: system pythonw missing at {SYS_PYTHONW}")
        return 1
    if not RECORDER_SCRIPT.exists():
        _log(f"FATAL: quote_recorder.py missing at {RECORDER_SCRIPT}")
        return 1

    env = os.environ.copy()
    venv_site = REPO / "backtest" / ".venv" / "Lib" / "site-packages"
    if venv_site.exists():
        env["PYTHONPATH"] = str(venv_site)
        env["VIRTUAL_ENV"] = str(REPO / "backtest" / ".venv")

    cmd = [str(SYS_PYTHONW), str(RECORDER_SCRIPT), "--loop", "--duration-sec", str(MAX_RUNTIME_S)]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=_DETACHED_PROCESS | _CREATE_NO_WINDOW,
            close_fds=True,
        )
        _log(f"launched quote_recorder PID={proc.pid} duration={MAX_RUNTIME_S}s (24h recycle)")
        time.sleep(2)
        return 0
    except Exception as e:  # noqa: BLE001 -- must never break the scheduled fire
        _log(f"FATAL: launch failed: {e}")
        return 1


def _main_safe() -> int:
    try:
        return main()
    except Exception as e:  # noqa: BLE001
        _log(f"FATAL unhandled exception: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(_main_safe())
