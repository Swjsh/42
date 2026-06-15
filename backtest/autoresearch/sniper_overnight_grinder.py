"""SNIPER_LEVEL_BREAK Stage 1 grinder.

Mirrors autoresearch/overnight_grinder.py for the existing v15 J-edge work.
This is a separate process so it doesn't interfere with v15 grinder state.

Output (under autoresearch/_state/sniper_stage1/):
    progress.json        live progress meter
    results.jsonl        every (passed-the-floors) candidate
    rejections.jsonl     every (broke-a-floor) candidate
    keepers.jsonl        candidates that improved wide_pnl over prior best
    runner.pid           current process PID
    grinder.log          structured log

CLI:
    pythonw.exe -m autoresearch.sniper_overnight_grinder --hours 4 --workers 4

Constraints (CLAUDE.md):
  - OP 15: MAX_PARALLEL_RESEARCH_WORKERS = 4 (process-based, NOT threads)
  - OP 16: edge_capture is PRIMARY; aggregate is secondary
  - OP 19: every result row has top5_pct, quarter_pnl, positive_quarters,
    max_drawdown by default
  - OP 11/13: pure Python, no LLM in the loop
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import logging
import multiprocessing as mp
import os
import random
import sys
from pathlib import Path

if sys.platform == "win32":
    _pw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _pw.exists():
        mp.set_executable(str(_pw))

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "autoresearch" / "_state" / "sniper_stage1"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROGRESS = OUT_DIR / "progress.json"
RESULTS = OUT_DIR / "results.jsonl"
REJECTIONS = OUT_DIR / "rejections.jsonl"
KEEPERS = OUT_DIR / "keepers.jsonl"
PIDFILE = OUT_DIR / "runner.pid"
LOGFILE = OUT_DIR / "grinder.log"


def _setup_logging() -> None:
    logging.basicConfig(
        filename=str(LOGFILE),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _write_progress(state: dict) -> None:
    """Atomic write of progress meter."""
    tmp = PROGRESS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(PROGRESS)


def _append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _build_param_grid() -> list[dict]:
    """864 SNIPER combos. v2 knob set per J 2026-05-12:
      - No time gate (trade all RTH; 09:30-15:50)
      - Profit-lock added: arm at +X%, stop floor moves to entry+Y%
      - Qty=10 to match J's actual sizing on 5/11 + 5/12
    """
    grid: list[dict] = []
    for vol_mult in [1.3, 1.5, 1.8]:
        for body_min_cents in [0.05, 0.10]:
            for min_stars in [2, 3]:
                for strike_offset in [0, 2]:
                    for premium_stop_pct in [-0.08, -0.12]:
                        for tp1_premium_pct in [0.30, 0.40]:
                            for runner_target_pct in [1.0, 1.5, 2.5]:
                                for profit_lock_threshold_pct in [0.0, 0.10, 0.20]:
                                    for profit_lock_stop_offset_pct in [0.0, 0.05]:
                                        grid.append({
                                            "vol_mult": vol_mult,
                                            "body_min_cents": body_min_cents,
                                            "min_stars": min_stars,
                                            "strike_offset": strike_offset,
                                            "premium_stop_pct": premium_stop_pct,
                                            "tp1_premium_pct": tp1_premium_pct,
                                            "runner_target_pct": runner_target_pct,
                                            "profit_lock_threshold_pct": profit_lock_threshold_pct,
                                            "profit_lock_stop_offset_pct": profit_lock_stop_offset_pct,
                                            "tp1_qty_fraction": 0.667,
                                            "qty": 10,
                                            "proximity_dollars": 1.5,
                                            "require_break_above_open": True,
                                        })
    return grid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=4.0,
                        help="Run for N hours then stop gracefully")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel workers (cap=4 per CLAUDE.md OP 15)")
    parser.add_argument("--reset", action="store_true",
                        help="Reset progress + results from prior run")
    args = parser.parse_args()

    # FIX 2026-05-24: reset BEFORE _setup_logging() so LOGFILE isn't held open
    # when we try to delete it (Windows PermissionError on open files).
    workers = min(args.workers, 4)

    if args.reset:
        for f in [PROGRESS, RESULTS, REJECTIONS, KEEPERS, LOGFILE]:
            if f.exists():
                f.unlink()

    _setup_logging()

    PIDFILE.write_text(str(os.getpid()), encoding="utf-8")

    started = dt.datetime.now()
    deadline = started + dt.timedelta(hours=args.hours)
    grid = _build_param_grid()
    random.Random(2026).shuffle(grid)

    state = {
        "started_at": started.isoformat(),
        "deadline_at": deadline.isoformat(),
        "total_combos": len(grid),
        "completed": 0,
        "passed_floors": 0,
        "rejected": 0,
        "keepers": 0,
        "best_edge_capture": 0.0,
        "best_wide_pnl": None,
        "current_pid": os.getpid(),
        "workers": workers,
        "last_update": started.isoformat(),
        "status": "running",
    }
    _write_progress(state)
    logging.info(f"Sniper Stage 1 grinder started: {len(grid)} combos, {workers} workers, deadline={deadline}")

    # Import here so each Pool child re-imports cleanly
    from autoresearch.sniper_evaluator import evaluate_sniper_combo

    completed = 0
    keepers_n = 0
    best_wide: tuple[float, dict] | None = None

    with mp.Pool(workers) as pool:
        for result in pool.imap_unordered(evaluate_sniper_combo, grid, chunksize=1):
            completed += 1

            if dt.datetime.now() > deadline:
                logging.info("Deadline reached, terminating pool")
                state["status"] = "deadline_reached"
                _write_progress(state)
                pool.terminate()
                break

            if result["passed_floors"]:
                _append_jsonl(RESULTS, result)
                state["passed_floors"] += 1

                wp = result.get("wide_pnl")
                if wp is not None and (best_wide is None or wp > best_wide[0]):
                    best_wide = (wp, result["combo"])
                    state["best_wide_pnl"] = wp
                    keepers_n += 1
                    state["keepers"] = keepers_n
                    _append_jsonl(KEEPERS, result)
                    logging.info(
                        f"KEEPER #{keepers_n}: wide_pnl=${wp:.0f} "
                        f"edge=${result['edge_capture']:.0f} "
                        f"trades={result['wide_n_trades']} wr={result['wide_wr']:.2f} "
                        f"combo={result['combo']}"
                    )

                if result["edge_capture"] > state["best_edge_capture"]:
                    state["best_edge_capture"] = result["edge_capture"]
            else:
                _append_jsonl(REJECTIONS, result)
                state["rejected"] += 1

            state["completed"] = completed
            state["last_update"] = dt.datetime.now().isoformat()
            if completed % 5 == 0:
                _write_progress(state)
                logging.info(
                    f"progress: {completed}/{len(grid)} "
                    f"passed={state['passed_floors']} keepers={keepers_n}"
                )

    state["status"] = "completed" if state["status"] == "running" else state["status"]
    state["completed_at"] = dt.datetime.now().isoformat()
    _write_progress(state)

    if PIDFILE.exists():
        PIDFILE.unlink()

    if best_wide:
        logging.info(
            f"Sniper Stage 1 done: {completed}/{len(grid)} "
            f"passed={state['passed_floors']} keepers={keepers_n} "
            f"best_wide=${best_wide[0]:.0f}"
        )
    else:
        logging.info(
            f"Sniper Stage 1 done: {completed}/{len(grid)} "
            f"passed={state['passed_floors']} no keepers"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
