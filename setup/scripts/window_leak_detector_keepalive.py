"""Keepalive for window-leak-detector.py, in Python.

REPLACES `run-window-leak-detector-keepalive.ps1` to eliminate the `wscript -> powershell.exe`
chain that leaks a `WindowsTerminal -Embedding` window per 5-min fire (5/17 evening foot-gun).
Task action: `wscript //nologo run_exe_hidden.vbs <sys-pythonw> <this-file>` -- no
PowerShell anywhere in the chain.

Checks window-leak-detector.pid, restarts the detector via system pythonw if dead.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "wlda-keepalive.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "wlda-keepalive.stderr.log", "a", buffering=1, encoding="utf-8")
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
LOG_FILE = LOG_DIR / f"window-leak-detector-keepalive-{dt.date.today().isoformat()}.log"

SYS_PYTHONW = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
DETECTOR_SCRIPT = REPO / "setup" / "scripts" / "window-leak-detector.py"
PID_FILE = STATE_DIR / "window-leak-detector.pid"


def _log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def _detector_alive() -> tuple[bool, int | None]:
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
        if "window-leak-detector" in out:
            return True, pid
        return False, pid
    except Exception:
        return False, pid


SUMMARY_FILE = STATE_DIR / "window-leak-summary.json"

# A detector process older than this is RECYCLED even while "alive" (2026-08-13).
#
# WHY. On 2026-08-13 J reported console windows flashing all morning. The detector process
# (pid 8840) was alive and polling -- window-leak-summary.json read polls_total 3,180,000 with
# leaks_total 0, and window-leaks.jsonl had logged nothing since 2026-07-14. Restarting it
# produced 37 detections in the next 8 minutes, spread across the whole window (only 2 in the
# first poll, so NOT a startup enumeration artifact). At ~4.6 leaks/min the old process should
# have logged tens of thousands over its 88-hour life. It had silently stopped detecting while
# continuing to poll and to write summaries.
#
# This keepalive only ever asked "is the PID alive?", which was TRUE the entire time. Process
# liveness is not detection liveness -- the same distinction that let `exit=0` mean "nothing
# raised" rather than "the work happened" elsewhere in this repo on the same day.
#
# A bounded recycle is the honest mitigation: the wedge's mechanism is not understood, and
# "polls are advancing" cannot distinguish a wedged detector from a genuinely quiet screen.
# Recycling costs one process restart per MAX_AGE and removes the failure's ability to persist.
MAX_DETECTOR_AGE_S = 6 * 3600


def _detector_runtime_s(live_pid: "int | None" = None) -> "float | None":
    """Runtime derived from the detector's OWN counters (polls_total * poll_interval_s).
    Returns None if unreadable -- and an unreadable summary must NOT trigger a recycle, or a
    transient read error would restart the detector on every fire.

    ...AND NOT IF IT BELONGS TO A DIFFERENT PROCESS (fixed 2026-08-15). The original guarded
    only the UNREADABLE case, but a STALE summary is worse than an unreadable one: it is
    confidently wrong, and it created a self-perpetuating recycle loop that ran for ~43 hours.

    THE LOOP, measured live: the summary was frozen at polls_total=43800 x 0.5s = 21,900s =
    6.083h, permanently above MAX_DETECTOR_AGE_S (21,600s). Every 5-minute fire read those
    DEAD counters, concluded the freshly-launched detector had "run 6.1h", and killed it --
    before it lived long enough to overwrite the summary with its own counters. So the file
    stayed frozen, so the next fire read 6.1h again. The keepalive built to prevent a wedge
    became the wedge: 43h of kill-relaunch thrash, zero polls recorded, and
    window-leak-summary.json 43h stale (which is how the unattended tile finally caught it).

    The summary already stamps the pid that wrote it, so the fix needs no new state: if that
    pid is not the process we are scoring, these counters describe someone else's lifetime and
    the honest answer is "unknown", which the caller already treats as do-not-recycle.
    """
    try:
        import json
        d = json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))
        if live_pid is not None:
            summary_pid = d.get("pid")
            if summary_pid is None or int(summary_pid) != int(live_pid):
                return None
        return float(d["polls_total"]) * float(d["poll_interval_s"])
    except Exception:
        return None


def _kill(pid: int) -> bool:
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=10, creationflags=_CREATE_NO_WINDOW)
        return True
    except Exception:
        return False


def main() -> int:
    alive, pid = _detector_alive()
    if alive:
        # Scope the runtime to THIS pid -- counters written by a previous detector are not
        # this one's age (see _detector_runtime_s for the 43h thrash loop that caused).
        age = _detector_runtime_s(live_pid=pid)
        if age is not None and age > MAX_DETECTOR_AGE_S and pid:
            _log(f"detector pid={pid} has run {age/3600:.1f}h (> {MAX_DETECTOR_AGE_S/3600:.0f}h) "
                 f"-- RECYCLING to clear a possible detection wedge (2026-08-13 incident)")
            if _kill(pid):
                time.sleep(1)
                # fall through to the relaunch path below
            else:
                _log(f"  taskkill failed for pid={pid}; leaving it alive")
                return 0
        else:
            _log(f"detector alive (pid={pid}, runtime={age/3600:.1f}h)" if age is not None
                 else f"detector alive (pid={pid}, runtime unknown)")
            return 0

    if not SYS_PYTHONW.exists():
        _log(f"FATAL: system pythonw missing at {SYS_PYTHONW}")
        return 1
    if not DETECTOR_SCRIPT.exists():
        _log(f"FATAL: detector script missing at {DETECTOR_SCRIPT}")
        return 1

    env = os.environ.copy()
    venv_site = REPO / "backtest" / ".venv" / "Lib" / "site-packages"
    if venv_site.exists():
        env["PYTHONPATH"] = str(venv_site)
        env["VIRTUAL_ENV"] = str(REPO / "backtest" / ".venv")

    try:
        proc = subprocess.Popen(
            [str(SYS_PYTHONW), str(DETECTOR_SCRIPT)],
            cwd=str(REPO),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=_DETACHED_PROCESS | _CREATE_NO_WINDOW,
            close_fds=True,
        )
        _log(f"launched detector PID={proc.pid}")
        # Give it 2s to write its own pid file.
        time.sleep(2)
        if PID_FILE.exists():
            written_pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            _log(f"  detector wrote pid={written_pid}")
        return 0
    except Exception as e:
        _log(f"FATAL: launch failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
