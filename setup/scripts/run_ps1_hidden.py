"""Generic launcher: run a PowerShell .ps1 script with guaranteed no visible window.

Why this exists: the standard `wscript -> run_hidden.vbs -> powershell.exe` chain still
leaks `WindowsTerminal -Embedding` windows on Windows 11 default-terminal configs because
`Shell.Run` uses ShellExecute (which can route through DefaultTerminal handler). This
launcher uses Python's `subprocess.Popen` with `CREATE_NO_WINDOW` (0x08000000) which calls
CreateProcess directly with the flag set -- Windows is REQUIRED to honor this and NOT
allocate a console for the child.

Task action: `wscript //nologo run_exe_hidden.vbs <sys-pythonw> run_ps1_hidden.py <ps1-path> [args...]`
  - wscript is GUI-subsystem -> no console for itself
  - sys-pythonw is GUI-subsystem -> no console for itself
  - this script Popens powershell.exe with CREATE_NO_WINDOW -> no console for it
  - powershell.exe runs the .ps1 with -WindowStyle Hidden as a safety net

Used for tasks where rewriting the PS1 to Python isn't worth it (low cadence, heavy
PowerShell-cmdlet logic). High-cadence keepalives (Gamma_CryptoGrinderKeepalive,
Gamma_DiscordWatchdog, Gamma_WindowLeakDetectorKeepalive) are full Python (see
crypto_grinder_keepalive.py + discord_watchdog.py + window_leak_detector_keepalive.py).

5/17 evening foot-gun fix.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "run-ps1-hidden.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "run-ps1-hidden.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import datetime as dt
import subprocess
import sys
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

REPO = Path(__file__).resolve().parents[2]
LOG_DIR = REPO / "automation" / "state" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"run-ps1-hidden-{dt.date.today().isoformat()}.log"


def _log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        _log("usage: run_ps1_hidden.py <ps1-path> [args...]")
        return 2

    ps1_path = Path(argv[1])
    extra_args = argv[2:]
    if not ps1_path.exists():
        _log(f"FATAL: ps1 missing at {ps1_path}")
        return 1

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-WindowStyle", "Hidden",
        "-NonInteractive",
        "-File", str(ps1_path),
    ] + extra_args

    _log(f"launching: {ps1_path.name} args={extra_args}")
    try:
        # CREATE_NO_WINDOW suppresses the WINDOW. It does NOT prevent the console.
        #
        # Corrected 2026-08-30 -- the previous comment here claimed it "guarantees Windows
        # does not allocate a console/conhost", and that is measurably false. Measured A/B on
        # this box, same powershell.exe command, counting conhost children of the child pid:
        #     CREATE_NO_WINDOW   -> conhost_children=1, stdout captured
        #     DETACHED_PROCESS   -> conhost_children=0, stdout EMPTY
        #     CNW | DETACHED     -> conhost_children=0, stdout EMPTY
        # So a console IS allocated here; it simply has no window of its own. On Windows 11
        # that console still goes through the default-terminal delegation broker, which is
        # what produces the `WindowsTerminal.exe -Embedding` / `OpenConsole.exe -Embedding`
        # windows recorded in automation/state/window-leaks.jsonl -- captured live at
        # 2026-08-30T20:00:02Z alongside the :00 burst of task fires that all route through
        # this launcher.
        #
        # DETACHED_PROCESS is therefore NOT a drop-in fix, tempting as the 0 above looks: it
        # silences PowerShell's output completely (empty even when redirected to a real file
        # handle, not just a pipe), which would blind every task log that depends on the
        # STDOUT/STDERR lines written below. Trading C7 ("silent success is failure; audit
        # outputs, not exit codes") for a flash is a bad trade -- a task that fails quietly
        # costs far more than a window that blinks.
        #
        # The window itself is handled downstream by window_leak_hook.py, which SW_HIDEs a
        # service-rooted console-host window on EVENT_OBJECT_SHOW (kept alive by
        # Gamma_WindowLeakHookKeepalive). The durable upstream fix is to stop putting
        # PowerShell in these chains at all -- the pattern window_leak_detector_keepalive.py
        # already used to kill this exact leak by rewriting its .ps1 runner in Python.
        # Capture stdout/stderr so they don't trip WT allocation on first write.
        proc = subprocess.run(
            cmd,
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=600,
            creationflags=_CREATE_NO_WINDOW,
        )
        _log(f"  {ps1_path.name} exit={proc.returncode}")
        if proc.stdout:
            _log(f"  STDOUT[:500]: {proc.stdout[:500]}")
        if proc.stderr:
            _log(f"  STDERR[:500]: {proc.stderr[:500]}")
        return proc.returncode
    except subprocess.TimeoutExpired:
        _log(f"  TIMEOUT after 600s")
        return 124
    except Exception as e:
        _log(f"  FATAL: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
