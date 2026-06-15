"""Overnight grinder monitor — hourly check-in via scheduled task.

Reads autoresearch/_state/overnight_grinder/progress.json and:
  1. Verifies the grinder PID is still alive.
  2. If dead before deadline, restarts the grinder (silent, pythonw.exe).
  3. Appends a heartbeat row to monitor.jsonl.
  4. Writes monitor.json snapshot.

Designed for Windows Task Scheduler hourly trigger. Idempotent.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

# CREATE_NO_WINDOW = 0x08000000 — suppress conhost on Windows subprocess spawns. OP-27 L41.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "autoresearch" / "_state" / "overnight_grinder"
OUT_DIR.mkdir(parents=True, exist_ok=True)
STAGE2_DIR = REPO / "autoresearch" / "_state" / "stage2_grinder"
STAGE2_DIR.mkdir(parents=True, exist_ok=True)
STAGE3_DIR = REPO / "autoresearch" / "_state" / "stage3_grinder"
STAGE3_DIR.mkdir(parents=True, exist_ok=True)
STAGE4_DIR = REPO / "autoresearch" / "_state" / "stage4_grinder"
STAGE4_DIR.mkdir(parents=True, exist_ok=True)

PROGRESS = OUT_DIR / "progress.json"
PIDFILE = OUT_DIR / "runner.pid"
MONITOR_LOG = OUT_DIR / "monitor.jsonl"
MONITOR_SNAP = OUT_DIR / "monitor.json"
GRINDER_LAUNCHER = REPO.parent / "setup" / "scripts" / "launch-overnight-grinder.ps1"
STAGE2_LAUNCHER = REPO.parent / "setup" / "scripts" / "launch-stage2-grinder.ps1"
STAGE3_LAUNCHER = REPO.parent / "setup" / "scripts" / "launch-stage3-grinder.ps1"
STAGE4_LAUNCHER = REPO.parent / "setup" / "scripts" / "launch-stage4-grinder.ps1"
STAGE5_RATIFY = REPO.parent / "setup" / "scripts" / "run-stage5-ratify.ps1"
STAGE2_PROGRESS = STAGE2_DIR / "progress.json"
STAGE2_PIDFILE = STAGE2_DIR / "runner.pid"
STAGE3_PROGRESS = STAGE3_DIR / "progress.json"
STAGE3_PIDFILE = STAGE3_DIR / "runner.pid"
STAGE4_PROGRESS = STAGE4_DIR / "progress.json"
STAGE4_PIDFILE = STAGE4_DIR / "runner.pid"
STAGE5_OUTPUT = REPO.parent / "analysis" / "recommendations" / "v15-final.json"


def _is_pid_alive(pid: int) -> bool:
    """Check if a Windows PID is alive."""
    try:
        # tasklist outputs an empty line if not found
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL,
            timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        ).decode("utf-8", errors="ignore")
        return f"{pid}" in out
    except Exception:
        return False


def _read_progress() -> dict:
    if not PROGRESS.exists():
        return {}
    try:
        return json.loads(PROGRESS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _restart_grinder() -> dict:
    """Launch the grinder via the silent ps1 wrapper. Returns launch metadata."""
    if not GRINDER_LAUNCHER.exists():
        return {"launched": False, "reason": "launcher_missing", "path": str(GRINDER_LAUNCHER)}
    try:
        # ps1 launcher uses Start-Process -WindowStyle Hidden so no flash.
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(GRINDER_LAUNCHER)],
            capture_output=True, text=True, timeout=30,
            creationflags=_CREATE_NO_WINDOW,
        )
        return {
            "launched": True,
            "stdout": result.stdout[:500],
            "stderr": result.stderr[:500],
            "returncode": result.returncode,
        }
    except Exception as exc:
        return {"launched": False, "reason": "launch_exception", "error": repr(exc)}


def _stage1_finished(progress: dict) -> bool:
    """Stage 1 considered finished when status is completed/deadline_reached."""
    return progress.get("status") in ("completed", "deadline_reached")


def _stage2_state() -> tuple[bool, dict]:
    """Returns (alive, progress_dict) for stage 2 grinder."""
    if not STAGE2_PROGRESS.exists():
        return False, {}
    try:
        s2_progress = json.loads(STAGE2_PROGRESS.read_text(encoding="utf-8"))
    except Exception:
        return False, {}
    pid_str = STAGE2_PIDFILE.read_text(encoding="utf-8").strip() if STAGE2_PIDFILE.exists() else None
    if pid_str and pid_str.isdigit():
        return _is_pid_alive(int(pid_str)), s2_progress
    return False, s2_progress


def _launch_stage2() -> dict:
    """Launch stage 2 grinder via ps1 wrapper."""
    if not STAGE2_LAUNCHER.exists():
        return {"launched": False, "reason": "stage2_launcher_missing", "path": str(STAGE2_LAUNCHER)}
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(STAGE2_LAUNCHER)],
            capture_output=True, text=True, timeout=30,
            creationflags=_CREATE_NO_WINDOW,
        )
        return {"launched": True, "stdout": result.stdout[:500], "stderr": result.stderr[:500], "returncode": result.returncode}
    except Exception as exc:
        return {"launched": False, "reason": "launch_exception", "error": repr(exc)}


def _stage3_state() -> tuple[bool, dict]:
    if not STAGE3_PROGRESS.exists():
        return False, {}
    try:
        s3 = json.loads(STAGE3_PROGRESS.read_text(encoding="utf-8"))
    except Exception:
        return False, {}
    pid_str = STAGE3_PIDFILE.read_text(encoding="utf-8").strip() if STAGE3_PIDFILE.exists() else None
    if pid_str and pid_str.isdigit():
        return _is_pid_alive(int(pid_str)), s3
    return False, s3


def _launch_stage3() -> dict:
    if not STAGE3_LAUNCHER.exists():
        return {"launched": False, "reason": "stage3_launcher_missing", "path": str(STAGE3_LAUNCHER)}
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(STAGE3_LAUNCHER)],
            capture_output=True, text=True, timeout=30,
            creationflags=_CREATE_NO_WINDOW,
        )
        return {"launched": True, "stdout": result.stdout[:500], "stderr": result.stderr[:500], "returncode": result.returncode}
    except Exception as exc:
        return {"launched": False, "reason": "launch_exception", "error": repr(exc)}


def _stage4_state() -> tuple[bool, dict]:
    if not STAGE4_PROGRESS.exists():
        return False, {}
    try:
        s4 = json.loads(STAGE4_PROGRESS.read_text(encoding="utf-8"))
    except Exception:
        return False, {}
    pid_str = STAGE4_PIDFILE.read_text(encoding="utf-8").strip() if STAGE4_PIDFILE.exists() else None
    if pid_str and pid_str.isdigit():
        return _is_pid_alive(int(pid_str)), s4
    return False, s4


def _launch_stage4() -> dict:
    if not STAGE4_LAUNCHER.exists():
        return {"launched": False, "reason": "stage4_launcher_missing"}
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(STAGE4_LAUNCHER)],
            capture_output=True, text=True, timeout=30,
            creationflags=_CREATE_NO_WINDOW,
        )
        return {"launched": True, "stdout": result.stdout[:500], "stderr": result.stderr[:500], "returncode": result.returncode}
    except Exception as exc:
        return {"launched": False, "reason": "launch_exception", "error": repr(exc)}


def _run_stage5_ratify() -> dict:
    """Stage 5 is a one-shot ratification script (not a long-running grinder)."""
    if not STAGE5_RATIFY.exists():
        return {"ran": False, "reason": "stage5_script_missing"}
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(STAGE5_RATIFY)],
            capture_output=True, text=True, timeout=120,
            creationflags=_CREATE_NO_WINDOW,
        )
        return {"ran": True, "stdout": result.stdout[:500], "stderr": result.stderr[:500], "returncode": result.returncode}
    except Exception as exc:
        return {"ran": False, "reason": "exception", "error": repr(exc)}


def main() -> int:
    now = dt.datetime.now()
    progress = _read_progress()
    pid_str = PIDFILE.read_text(encoding="utf-8").strip() if PIDFILE.exists() else None
    pid_alive = False
    pid_int = None
    if pid_str and pid_str.isdigit():
        pid_int = int(pid_str)
        pid_alive = _is_pid_alive(pid_int)

    deadline_passed = False
    deadline_str = progress.get("deadline_at")
    if deadline_str:
        try:
            deadline = dt.datetime.fromisoformat(deadline_str)
            deadline_passed = now > deadline
        except Exception:
            pass

    s2_alive, s2_progress = _stage2_state()
    s3_alive, s3_progress = _stage3_state()
    s4_alive, s4_progress = _stage4_state()

    s2_done = s2_progress.get("status") in ("completed", "deadline_reached")
    s3_done = s3_progress.get("status") in ("completed", "deadline_reached")
    s4_done = s4_progress.get("status") in ("completed", "deadline_reached")
    s5_done = STAGE5_OUTPUT.exists()

    snap = {
        "checked_at": now.isoformat(),
        "grinder_pid": pid_int,
        "grinder_alive": pid_alive,
        "deadline_passed": deadline_passed,
        "progress": progress,
        "stage2_alive": s2_alive,
        "stage2_progress": s2_progress,
        "stage3_alive": s3_alive,
        "stage3_progress": s3_progress,
        "stage4_alive": s4_alive,
        "stage4_progress": s4_progress,
        "stage5_done": s5_done,
        "action": None,
    }

    # Stage 1 restart logic
    if not pid_alive and not deadline_passed and progress.get("status") == "running":
        relaunch = _restart_grinder()
        snap["action"] = "restart_stage1"
        snap["relaunch"] = relaunch
    elif not pid_alive and progress.get("status") in (None, ""):
        relaunch = _restart_grinder()
        snap["action"] = "cold_start_stage1"
        snap["relaunch"] = relaunch
    elif pid_alive:
        snap["action"] = "stage1_alive"
    # Stage 2 launch/restart
    elif _stage1_finished(progress) and not s2_alive and not s2_progress:
        relaunch = _launch_stage2()
        snap["action"] = "auto_launch_stage2"
        snap["relaunch"] = relaunch
    elif _stage1_finished(progress) and not s2_alive and s2_progress.get("status") == "running":
        relaunch = _launch_stage2()
        snap["action"] = "restart_stage2"
        snap["relaunch"] = relaunch
    elif s2_alive:
        snap["action"] = "stage2_alive"
    # Stage 3 launch/restart (NEW — chain after stage 2)
    elif s2_done and not s3_alive and not s3_progress:
        relaunch = _launch_stage3()
        snap["action"] = "auto_launch_stage3"
        snap["relaunch"] = relaunch
    elif s2_done and not s3_alive and s3_progress.get("status") == "running":
        relaunch = _launch_stage3()
        snap["action"] = "restart_stage3"
        snap["relaunch"] = relaunch
    elif s3_alive:
        snap["action"] = "stage3_alive"
    # Stage 4 launch/restart (chained after stage 3)
    elif s3_done and not s4_alive and not s4_progress:
        relaunch = _launch_stage4()
        snap["action"] = "auto_launch_stage4"
        snap["relaunch"] = relaunch
    elif s3_done and not s4_alive and s4_progress.get("status") == "running":
        relaunch = _launch_stage4()
        snap["action"] = "restart_stage4"
        snap["relaunch"] = relaunch
    elif s4_alive:
        snap["action"] = "stage4_alive"
    # Stage 5 (one-shot ratification, runs once after stage 4 done)
    elif s4_done and not s5_done:
        relaunch = _run_stage5_ratify()
        snap["action"] = "run_stage5_ratify"
        snap["relaunch"] = relaunch
    elif s5_done:
        snap["action"] = "all_stages_done_ratification_ready"
    else:
        snap["action"] = "no_action"

    MONITOR_SNAP.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
    with MONITOR_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snap, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
