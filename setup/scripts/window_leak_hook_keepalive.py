"""Keepalive for window_leak_hook.py -- the EVENT-DRIVEN (pre-paint) console-window hider.

WHY THIS EXISTS (2026-08-30, J: "first priority is stopping all popups"):
  window_leak_hook.py was shipped 2026-07-23 for J's "STOP ALL POPUPS NOW" because the
  0.5s poller (window-leak-detector.py) leaves a leaked console-host window on screen for
  up to half a second -- long enough to see, and long enough to yank focus out of a game.
  The hook closes that to imperceptible via SetWinEventHook(EVENT_OBJECT_SHOW).

  It then DIED on 2026-08-10 and stayed dead for 20 days. Verified this session: pid 9036
  from window-leak-hook.pid was not running, the last window-leak-hook-*.log was dated
  2026-08-10, and `Get-ScheduledTask Gamma*` had ZERO actions referencing window_leak_hook
  -- nothing on this box had ever been responsible for restarting it. Meanwhile the poller
  (which DOES have a keepalive) logged 29 leaks that day, every one `mitigated: true` --
  i.e. hidden late, after being visible. Those are the flashes J was seeing.

  This is the THIRD occurrence of the same monitor-of-monitors shape on this exact
  subsystem: the detector went dark ~2 months (2026-05-23 -> 2026-07-14) with nothing
  flagging it, which is why IT got a keepalive; the hook then shipped without one and
  repeated the failure verbatim. A mitigation that can silently die is not a fix.

DELIBERATELY NOT INCLUDED -- a bounded age-recycle.
  window_leak_detector_keepalive.py recycles the detector every 6h because a wedged poller
  was observed live (2026-08-13) and "polls advancing" could not distinguish wedged from
  quiet. No equivalent wedge has been observed for the hook, and an unmotivated recycle is
  not free: the detector's own recycle logic caused a 43-hour kill-relaunch thrash loop
  (see _detector_runtime_s). Restart-if-dead is the smallest change that addresses the
  failure actually observed. If a wedged hook is ever demonstrated, add the recycle then,
  with the evidence.

Task action (no PowerShell anywhere in the chain -- a .ps1 link would itself leak a window):
  wscript //nologo run_exe_hidden.vbs <sys-pythonw> run_cmd_hidden.py --cwd <repo>
    -- <sys-pythonw> window_leak_hook_keepalive.py
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "wlhk-keepalive.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "wlhk-keepalive.stderr.log", "a", buffering=1, encoding="utf-8")
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
LOG_FILE = LOG_DIR / f"window-leak-hook-keepalive-{dt.date.today().isoformat()}.log"

SYS_PYTHONW = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
HOOK_SCRIPT = REPO / "setup" / "scripts" / "window_leak_hook.py"
PID_FILE = STATE_DIR / "window-leak-hook.pid"

# The marker that must appear in the live process's command line. Guards against PID reuse:
# a recycled PID belonging to some unrelated process must NOT read as "hook alive".
_CMDLINE_MARKER = "window_leak_hook"


def _log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def _hook_alive() -> "tuple[bool, int | None]":
    """(alive, pid). Alive requires BOTH a live PID and that PID's command line naming the
    hook script -- process liveness alone is a PID-reuse foot-gun."""
    if not PID_FILE.exists():
        return False, None
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return False, None
    try:
        out = subprocess.check_output(
            ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/FORMAT:LIST"],
            stderr=subprocess.DEVNULL, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        ).decode("utf-8", errors="ignore")
        return (_CMDLINE_MARKER in out), pid
    except Exception:
        return False, pid


def main() -> int:
    alive, pid = _hook_alive()
    if alive:
        _log(f"hook alive (pid={pid})")
        return 0

    _log(f"hook DEAD (last pid={pid}) -- relaunching")

    if not SYS_PYTHONW.exists():
        _log(f"FATAL: system pythonw missing at {SYS_PYTHONW}")
        return 1
    if not HOOK_SCRIPT.exists():
        _log(f"FATAL: hook script missing at {HOOK_SCRIPT}")
        return 1

    try:
        # The hook is stdlib-only (ctypes). No PYTHONPATH/VIRTUAL_ENV needed -- and NOT
        # pointing it at the backtest venv keeps a heavyweight import off a process whose
        # whole job is to respond to a window-show event within a frame.
        proc = subprocess.Popen(
            [str(SYS_PYTHONW), str(HOOK_SCRIPT)],
            cwd=str(REPO),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=_DETACHED_PROCESS | _CREATE_NO_WINDOW,
            close_fds=True,
        )
        _log(f"launched hook PID={proc.pid}")
    except Exception as e:
        _log(f"FATAL: launch failed: {e}")
        return 1

    # The hook writes its OWN pid after acquiring its singleton mutex. Confirm that
    # happened rather than trusting Popen -- a hook that exited on "sibling already
    # running" is a legitimate no-op, but a hook that died on import is not.
    time.sleep(2)
    alive2, pid2 = _hook_alive()
    if alive2:
        _log(f"  relaunch OK (pid={pid2})")
        return 0
    _log("  relaunch FAILED -- hook did not come up; see window-leak-hook.stderr.log")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
