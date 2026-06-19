"""SNIPER full pipeline orchestrator — Stage 1 → 2 → 3+4+5.

Idempotent. Polls Stage 1 progress.json until done (or timeout), then launches
Stage 2 grinder, waits for that, then runs Stages 3+4+5 filter+ratify in-process.

Designed to be launched ONCE in the evening after Stage 1 starts; it sleeps
through Stage 1's run, then drives the rest of the pipeline autonomously
overnight. Pure Python; zero LLM cost.

CLI:
    python -m autoresearch.sniper_pipeline [--max-wait-hours 8] [--stage2-hours 2]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

STAGE1_DIR = REPO / "autoresearch" / "_state" / "sniper_stage1"
STAGE2_DIR = REPO / "autoresearch" / "_state" / "sniper_stage2"
PIPELINE_DIR = REPO / "autoresearch" / "_state" / "sniper_pipeline"
PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
PIPELINE_LOG = PIPELINE_DIR / "pipeline.log"
PIPELINE_PID = PIPELINE_DIR / "pipeline.pid"


def _log(msg: str) -> None:
    ts = dt.datetime.now().isoformat(timespec="seconds")
    line = f"{ts} [pipeline] {msg}\n"
    with PIPELINE_LOG.open("a", encoding="utf-8") as f:
        f.write(line)


def _read_progress(d: Path) -> dict | None:
    p = d / "progress.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _wait_for_stage(d: Path, name: str, max_wait_hours: float) -> bool:
    """Poll progress.json until status != running. Returns True if completed/deadline_reached."""
    started = dt.datetime.now()
    deadline = started + dt.timedelta(hours=max_wait_hours)
    while dt.datetime.now() < deadline:
        prog = _read_progress(d)
        if prog is None:
            _log(f"{name}: progress.json not yet present, waiting...")
            time.sleep(60)
            continue
        status = prog.get("status", "?")
        completed = prog.get("completed", 0)
        total = prog.get("total_combos", 0)
        keepers = prog.get("keepers", 0)
        passed = prog.get("passed_floors", 0)
        if status in ("completed", "deadline_reached"):
            _log(f"{name} DONE: status={status} completed={completed}/{total} passed={passed} keepers={keepers}")
            return True
        _log(f"{name} progress: {completed}/{total} passed={passed} keepers={keepers} status={status}")
        time.sleep(120)  # poll every 2 min
    _log(f"{name} TIMEOUT after {max_wait_hours}h — proceeding with whatever keepers exist")
    return False


def _launch_stage2(hours: float) -> int:
    """Launch sniper_stage2_grinder.py via subprocess. Returns child PID."""
    py = sys.executable
    pyw = Path(py).parent / "pythonw.exe"
    exe = str(pyw) if pyw.exists() else py
    cmd = [exe, "-m", "autoresearch.sniper_stage2_grinder", "--hours", str(hours), "--workers", "4", "--top-n", "5"]
    _log(f"Launching Stage 2: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, cwd=str(REPO), creationflags=0x08000000 if sys.platform == "win32" else 0)
    _log(f"Stage 2 launched: PID {proc.pid}")
    return proc.pid


def _run_stages345() -> int:
    """Run sniper_stages345.py in-process (synchronously)."""
    from autoresearch.sniper_stages345 import main as stages345_main
    _log("Running Stages 3+4+5 in-process")
    rc = stages345_main()
    _log(f"Stages 3+4+5 complete: rc={rc}")
    return rc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-wait-hours", type=float, default=8.0,
                        help="Max hours to wait for each stage before timing out")
    parser.add_argument("--stage2-hours", type=float, default=2.0,
                        help="Stage 2 deadline (hours)")
    args = parser.parse_args()

    import os
    PIPELINE_PID.write_text(str(os.getpid()), encoding="utf-8")
    _log(f"Pipeline started: PID={os.getpid()} max_wait={args.max_wait_hours}h")

    # Stage 1 (waits)
    _wait_for_stage(STAGE1_DIR, "Stage 1", args.max_wait_hours)

    # Has Stage 1 produced any keepers?
    s1_kp = STAGE1_DIR / "keepers.jsonl"
    if not s1_kp.exists() or s1_kp.stat().st_size == 0:
        _log("Stage 1 has NO keepers. Skipping Stage 2; running Stages 3+4+5 on empty input.")
        rc = _run_stages345()
        if PIPELINE_PID.exists(): PIPELINE_PID.unlink()
        return rc

    # Launch Stage 2 + wait
    _launch_stage2(args.stage2_hours)
    _wait_for_stage(STAGE2_DIR, "Stage 2", args.max_wait_hours)

    # Run Stages 3+4+5 (filter+ratify; cheap)
    rc = _run_stages345()
    _log("Pipeline complete.")
    if PIPELINE_PID.exists(): PIPELINE_PID.unlink()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
