"""Keepalive for the crypto live grinder, in Python.

REPLACES `run-crypto-grinder-keepalive.ps1` to eliminate the `wscript -> powershell.exe`
chain that leaks a `WindowsTerminal -Embedding` window per fire (5/17 evening foot-gun).
Task action: `wscript //nologo run_exe_hidden.vbs <sys-pythonw> <this-file>` -- no
PowerShell anywhere in the chain.

Fires every 5 min via Gamma_CryptoGrinderKeepalive.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "crypto-grinder-keepalive.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "crypto-grinder-keepalive.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

# CREATE_NO_WINDOW = 0x08000000 — every subprocess spawn from this script must pass it.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

REPO = Path(__file__).resolve().parents[2]
LOG_DIR = REPO / "automation" / "state" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"crypto-grinder-keepalive-{dt.date.today().isoformat()}.log"

SYS_PYTHONW = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
GRINDER_SCRIPT = REPO / "crypto" / "benchmarks" / "live_grinder.py"
GRINDER_ARGS = ["--interval", "120", "--duration", "43200", "--symbol", "BTC-USD", "--granularity", "300"]


def _log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def _grinder_alive() -> tuple[bool, str]:
    """Return (alive?, pid). Uses WMIC (creationflags=CREATE_NO_WINDOW)."""
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where",
             "(Name='python.exe' OR Name='pythonw.exe')",
             "get", "ProcessId,CommandLine", "/FORMAT:LIST"],
            stderr=subprocess.DEVNULL, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        ).decode("utf-8", errors="ignore")
        current: dict[str, str] = {}
        for raw in out.splitlines():
            line = raw.strip()
            if not line:
                if current.get("CommandLine", "").find("live_grinder") >= 0:
                    return True, current.get("ProcessId", "?")
                current = {}
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                current[k.strip()] = v.strip()
        if current.get("CommandLine", "").find("live_grinder") >= 0:
            return True, current.get("ProcessId", "?")
        return False, ""
    except Exception as e:
        _log(f"WMIC check failed: {e}")
        return False, ""


def main() -> int:
    alive, pid = _grinder_alive()
    if alive:
        _log(f"grinder alive (PID={pid})")
        return 0

    if not SYS_PYTHONW.exists():
        _log(f"FATAL: system pythonw missing at {SYS_PYTHONW}")
        return 1
    if not GRINDER_SCRIPT.exists():
        _log(f"FATAL: grinder script missing at {GRINDER_SCRIPT}")
        return 1

    # Launch grinder via system pythonw with venv PYTHONPATH.
    env = os.environ.copy()
    venv_site = REPO / "backtest" / ".venv" / "Lib" / "site-packages"
    if venv_site.exists():
        env["PYTHONPATH"] = str(venv_site)
        env["VIRTUAL_ENV"] = str(REPO / "backtest" / ".venv")

    cmd = [str(SYS_PYTHONW), str(GRINDER_SCRIPT)] + GRINDER_ARGS
    try:
        # DETACHED_PROCESS (0x00000008) + CREATE_NO_WINDOW (0x08000000) -- detach so the
        # grinder outlives this keepalive process and never gets a console.
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=0x00000008 | 0x08000000,  # DETACHED_PROCESS | CREATE_NO_WINDOW
            close_fds=True,
        )
        _log(f"launched grinder PID={proc.pid} duration=12h interval=2m")
        return 0
    except Exception as e:
        _log(f"FATAL: launch failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
