"""Parallel backtest fleet — one process per leaderboard candidate.

Spawns all backtest jobs simultaneously using pythonw.exe with CREATE_NO_WINDOW
per OP-27 L41. Each job writes its own log to automation/state/logs/ and results
to analysis/backtests/{slug}/.

Usage:
    python backtest/autoresearch/backtest_fleet.py              # launch all
    python backtest/autoresearch/backtest_fleet.py --status     # poll status
    python backtest/autoresearch/backtest_fleet.py --slug f8    # launch one

Jobs (per leaderboard as of 2026-05-21):
  orb-gate       — ORB direction+range gate analysis (pure data, ~30s)
  v14e-bear      — V14E bear-only gate analysis (pure data, ~30s)
  sweep-retune   — Sweep blocker stage3 re-run with confluence carve-out (~10min)
  f8-vix         — F8 flat-VIX unblock full engine backtest (~10min)
  nlwb-walkfwd   — NLWB walk-forward validation (~5min)
  nlwb-fills     — NLWB full real-fills validation (~8min)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent          # .../backtest/
ROOT = REPO.parent                                      # .../42/
AUTORESEARCH = REPO / "autoresearch"
VENV_PYTHON = REPO / ".venv" / "Scripts" / "python.exe"
VENV_SITE = REPO / ".venv" / "Lib" / "site-packages"
SYS_PYTHONW = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
LOG_DIR = ROOT / "automation" / "state" / "logs"
FLEET_STATE = ROOT / "analysis" / "backtests" / "fleet-state.json"

LOG_DIR.mkdir(parents=True, exist_ok=True)
(ROOT / "analysis" / "backtests").mkdir(parents=True, exist_ok=True)

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# ---------------------------------------------------------------------------
# Job definitions
# ---------------------------------------------------------------------------
JOBS: dict[str, dict] = {
    "orb-gate": {
        "script": AUTORESEARCH / "orb_gate_analysis.py",
        "args": [],
        "description": "ORB direction + OR-range gate analysis (leaderboard #4/#5)",
        "output_file": ROOT / "analysis" / "backtests" / "orb-gate-analysis" / "results.json",
        "est_minutes": 1,
    },
    "v14e-bear": {
        "script": AUTORESEARCH / "v14e_bear_gate_analysis.py",
        "args": [],
        "description": "V14E bear-only gate analysis (leaderboard #3)",
        "output_file": ROOT / "analysis" / "backtests" / "v14e-bear-gate" / "results.json",
        "est_minutes": 1,
    },
    "sweep-retune": {
        "script": AUTORESEARCH / "sweep_blocker_stage3.py",
        "args": ["--quick"],
        "description": "Sweep blocker stage3 re-run with confluence carve-out (#1)",
        "output_file": ROOT / "analysis" / "recommendations" / "sweep-blocker-stage3.json",
        "est_minutes": 10,
    },
    "f8-vix": {
        "script": AUTORESEARCH / "f8_flat_vix_engine_backtest.py",
        "args": [],
        "description": "F8 flat-VIX unblock full engine backtest (leaderboard #6)",
        "output_file": ROOT / "analysis" / "recommendations" / f"f8-flat-vix-backtest-{datetime.now().strftime('%Y-%m-%d')}.json",
        "est_minutes": 10,
    },
    "nlwb-walkfwd": {
        "script": AUTORESEARCH / "nlwb_walk_forward.py",
        "args": [],
        "description": "NLWB walk-forward validation (leaderboard #8)",
        "output_file": ROOT / "analysis" / "backtests" / "nlwb-chart-stop" / "walk-forward.json",
        "est_minutes": 5,
    },
    "nlwb-fills": {
        "script": AUTORESEARCH / "nlwb_full_real_fills_validate.py",
        "args": [],
        "description": "NLWB full real-fills validation (leaderboard #8)",
        "output_file": ROOT / "analysis" / "backtests" / "nlwb-chart-stop" / "real-fills.json",
        "est_minutes": 8,
    },
}


def _log_path(slug: str) -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    return LOG_DIR / f"fleet-{slug}-{date_str}.log"


def _spawn_job(slug: str, job: dict) -> dict:
    """Spawn one job as system pythonw.exe + PYTHONPATH per OP-27 L41.

    System pythonw.exe is GUI-subsystem — guaranteed no console/conhost allocation.
    Venv site-packages added via PYTHONPATH so imports resolve correctly.
    CREATE_NO_WINDOW also set for belt-and-suspenders (prevents any grandchild windows).
    """
    import os

    script = job["script"]
    if not script.exists():
        return {"slug": slug, "status": "MISSING_SCRIPT", "script": str(script)}

    log_file = _log_path(slug)
    log_fh = open(log_file, "a", encoding="utf-8")  # noqa: WPS515

    # OP-27 L41: venv python.exe + CREATE_NO_WINDOW.
    # These are SHORT-LIVED backtests (not daemons), so python.exe is correct here.
    # CREATE_NO_WINDOW (0x08000000) prevents the console window from appearing even
    # though python.exe is console-subsystem. Different from long-running daemons that
    # MUST use pythonw.exe (system) to avoid conhost for their full lifetime.
    if VENV_PYTHON.exists():
        exe = str(VENV_PYTHON)
    else:
        exe = sys.executable

    env = dict(os.environ)  # inherit parent env (includes PYTHONPATH if set)

    cmd = [exe, "-u", str(script)] + job["args"]  # -u = unbuffered so log writes flush immediately

    proc = subprocess.Popen(
        cmd,
        stdout=log_fh,
        stderr=log_fh,
        cwd=str(REPO),
        env=env,
        creationflags=_CREATE_NO_WINDOW,
    )
    started_at = datetime.now(timezone.utc).isoformat()
    print(f"  [fleet] STARTED  {slug:15s}  pid={proc.pid}  log={log_file.name}")
    return {
        "slug": slug,
        "pid": proc.pid,
        "status": "running",
        "started_at": started_at,
        "log": str(log_file),
        "output_file": str(job["output_file"]),
        "est_minutes": job["est_minutes"],
        "description": job["description"],
    }


def _poll_status(state: list[dict]) -> list[dict]:
    """Poll all running jobs, update status."""
    import os
    updated = []
    for entry in state:
        if entry.get("status") not in ("running",):
            updated.append(entry)
            continue
        pid = entry.get("pid")
        # Check if PID still alive (Windows: tasklist)
        try:
            import ctypes
            PROCESS_QUERY_INFORMATION = 0x0400
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
            if handle:
                exit_code = ctypes.c_ulong(0)
                ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                ctypes.windll.kernel32.CloseHandle(handle)
                still_active = exit_code.value == 259  # STILL_ACTIVE
                if still_active:
                    updated.append(dict(entry, status="running"))
                else:
                    out_file = Path(entry.get("output_file", ""))
                    success = out_file.exists()
                    updated.append(dict(
                        entry,
                        status="completed" if success else "failed",
                        exit_code=exit_code.value,
                        finished_at=datetime.now(timezone.utc).isoformat(),
                    ))
            else:
                updated.append(dict(entry, status="unknown_pid"))
        except Exception:
            updated.append(dict(entry, status="unknown"))
    return updated


def launch(slugs: list[str] | None = None) -> None:
    jobs = {k: v for k, v in JOBS.items() if (slugs is None or k in slugs)}
    print(f"\n[backtest_fleet] Launching {len(jobs)} job(s)...")
    state = []
    for slug, job in jobs.items():
        entry = _spawn_job(slug, job)
        state.append(entry)

    FLEET_STATE.parent.mkdir(parents=True, exist_ok=True)
    FLEET_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"\n[backtest_fleet] Fleet launched — state: {FLEET_STATE}")
    print(f"[backtest_fleet] All PIDs: {[e.get('pid') for e in state]}")
    print(f"\n[backtest_fleet] Monitor: python backtest/autoresearch/backtest_fleet.py --status")


def status() -> None:
    if not FLEET_STATE.exists():
        print("[fleet] No fleet state found. Run --launch first.")
        return
    state = json.loads(FLEET_STATE.read_text(encoding="utf-8"))
    state = _poll_status(state)
    FLEET_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"\n{'SLUG':20s} {'STATUS':12s} {'PID':8s} {'EST':5s} DESCRIPTION")
    print("-" * 90)
    for e in state:
        pid = str(e.get("pid", "-"))
        status = e.get("status", "?")
        slug = e.get("slug", "?")
        est = str(e.get("est_minutes", "?")) + "min"
        desc = e.get("description", "")[:50]
        icon = "OK" if status == "completed" else "!!" if status == "failed" else "->"
        print(f"{slug:20s} {icon} {status:10s} {pid:8s} {est:5s} {desc}")
    done = sum(1 for e in state if e.get("status") == "completed")
    running = sum(1 for e in state if e.get("status") == "running")
    failed = sum(1 for e in state if e.get("status") == "failed")
    print(f"\n  {done} completed / {running} running / {failed} failed / {len(state)} total")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parallel backtest fleet coordinator")
    parser.add_argument("--status", action="store_true", help="Poll status of running fleet")
    parser.add_argument("--slug", help="Launch a specific job by slug")
    args = parser.parse_args()

    if args.status:
        status()
    elif args.slug:
        if args.slug not in JOBS:
            print(f"Unknown slug '{args.slug}'. Available: {list(JOBS)}")
            sys.exit(1)
        launch([args.slug])
    else:
        launch()


if __name__ == "__main__":
    main()
