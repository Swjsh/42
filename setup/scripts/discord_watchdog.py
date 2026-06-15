"""Watchdog for discord-bridge.py and discord-watcher.py, in Python.

REPLACES `ensure-discord-bridge-alive.ps1` to eliminate the `wscript -> powershell.exe`
chain that leaks a `WindowsTerminal -Embedding` window per 5-min fire (5/17 evening foot-gun).
Task action: `wscript //nologo run_exe_hidden.vbs <sys-pythonw> <this-file>` -- no
PowerShell anywhere in the chain.

Checks discord-bridge and discord-watcher PIDs (via .pid files). Restarts dead ones via
system pythonw.exe with venv PYTHONPATH set.
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
        if pid is not None and _pid_alive(pid):
            continue  # alive, no-op silent
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
