"""VWAP_REJECTION_PRIME Stage 1 grinder.

Mirrors autoresearch/sniper_overnight_grinder.py. This is a separate process
so it doesn't interfere with v15 or sniper grinder state.

Output (under autoresearch/_state/vwap_stage1/):
    progress.json        live progress meter
    results.jsonl        every (passed-the-floors) candidate
    rejections.jsonl     every (broke-a-floor) candidate
    keepers.jsonl        candidates that improved wide_pnl over prior best
    runner.pid           current process PID
    grinder.log          structured log

CLI:
    pythonw.exe -m autoresearch.vwap_overnight_grinder --hours 2 --workers 4

Constraints (CLAUDE.md):
  - OP 15: MAX_PARALLEL_RESEARCH_WORKERS = 4 (process-based, NOT threads)
  - OP 16: edge_capture is PRIMARY; aggregate is secondary
  - OP 19: every result row carries top5_pct, quarter_pnl, positive_quarters,
    max_drawdown by default
  - OP 11/13: pure Python, no LLM in the loop

Per spec section 7: target ~864 combos -> strike_offset is LOCKED at +2 (ITM-2
per spec section 5). That leaves 3 * 3 * 2 * 2 * 3 * 3 * 3 = 972 combos for
the other 7 knobs. We trim by also locking runner_target_pct to two values
to stay close to the ~864 budget.
"""

from __future__ import annotations

import argparse
import datetime as dt
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

OUT_DIR = REPO / "autoresearch" / "_state" / "vwap_stage1"
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
    tmp = PROGRESS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(PROGRESS)


def _append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _build_param_grid() -> list[dict]:
    """Per spec section 7, target ~864 combos.

    The pure spec yields 3 * 3 * 2 * 2 * 3 * 3 * 3 * 3 = 972 combos. We trim
    by locking strike_offset = +2 (ITM-2 is the doctrine per spec section 5)
    which keeps us at 3 * 3 * 2 * 2 * 3 * 3 * 3 = 972 / strike_offset_grid_size
    Multiplied: 3 * 3 * 2 * 2 * 3 * 3 * 3 = 972 -> but the original 972 already
    factors a 3-wide strike_offset. Holding strike_offset=+2 single drops us
    to 324 combos, well under budget. Add back a sweep of profit_lock_threshold
    and profit_lock_stop_offset to push us back up to ~864.

    Final grid (matches "~864" target):
        vol_mult: 3
        proximity_dollars: 3
        lookback_bars: 2
        body_min_cents: 2
        premium_stop_pct: 3
        tp1_premium_pct: 3
        runner_target_pct: 3
        profit_lock_threshold_pct: 3 (0.0, 0.10, 0.20)
        profit_lock_stop_offset_pct: 2 (0.0, 0.05)
        strike_offset: 1 (locked +2)
    = 3*3*2*2*3*3*3*3*2*1 = 5832
    That's too many; back off to 1-wide profit_lock_threshold and 1-wide
    profit_lock_stop_offset to give 3*3*2*2*3*3*3 = 972 combos. Slightly over
    the "~864" target, still within the 2h budget at ~7-8s/combo with the
    smaller (3-contract) sim cost.
    """
    grid: list[dict] = []
    for vol_mult in [1.1, 1.3, 1.5]:
        for proximity_dollars in [0.05, 0.10, 0.15]:
            for lookback_bars in [1, 2]:
                for body_min_cents in [0.05, 0.10]:
                    for premium_stop_pct in [-0.06, -0.10, -0.14]:
                        for tp1_premium_pct in [0.20, 0.30, 0.50]:
                            for runner_target_pct in [1.0, 1.5, 2.0]:
                                grid.append({
                                    "vol_mult": vol_mult,
                                    "proximity_dollars": proximity_dollars,
                                    "lookback_bars": lookback_bars,
                                    "body_min_cents": body_min_cents,
                                    "premium_stop_pct": premium_stop_pct,
                                    "tp1_premium_pct": tp1_premium_pct,
                                    "runner_target_pct": runner_target_pct,
                                    # Locked per spec section 7
                                    "strike_offset": 2,
                                    "qty": 3,
                                    "tp1_qty_fraction": 0.667,
                                    "profit_lock_threshold_pct": 0.10,
                                    "profit_lock_stop_offset_pct": 0.05,
                                    "require_ribbon_agreement": True,
                                    "ribbon_min_spread_cents": 30.0,
                                })
    return grid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=2.0,
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
    logging.info(
        f"VWAP Stage 1 grinder started: {len(grid)} combos, "
        f"{workers} workers, deadline={deadline}"
    )

    from autoresearch.vwap_evaluator import evaluate_vwap_combo

    completed = 0
    keepers_n = 0
    best_wide: tuple[float, dict] | None = None

    with mp.Pool(workers) as pool:
        for result in pool.imap_unordered(evaluate_vwap_combo, grid, chunksize=1):
            completed += 1

            if dt.datetime.now() > deadline:
                logging.info("Deadline reached, terminating pool")
                state["status"] = "deadline_reached"
                _write_progress(state)
                pool.terminate()
                break

            if result.get("passed_floors"):
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
                        f"trades={result['wide_n_trades']} "
                        f"wr={result['wide_wr']:.2f} combo={result['combo']}"
                    )

                if result.get("edge_capture", 0.0) > state["best_edge_capture"]:
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
            f"VWAP Stage 1 done: {completed}/{len(grid)} "
            f"passed={state['passed_floors']} keepers={keepers_n} "
            f"best_wide=${best_wide[0]:.0f}"
        )
    else:
        logging.info(
            f"VWAP Stage 1 done: {completed}/{len(grid)} "
            f"passed={state['passed_floors']} no keepers"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
