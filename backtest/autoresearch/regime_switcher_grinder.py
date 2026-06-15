"""REGIME_SWITCHER Stage 1 grinder.

Mirrors sniper_overnight_grinder.py / vwap_overnight_grinder.py. Since the
switcher's per-combo evaluation is O(N_days) lookups against the pre-built
strategy P&L matrix (~5 seconds), the full 1,296-combo grid runs in ~27 min
with 4 workers.

DEPENDENCY: the pre-pass cache MUST exist at
  backtest/autoresearch/_state/regime_switcher_stage1/strategy_pnl_matrix.json
  backtest/autoresearch/_state/regime_switcher_stage1/regime_inputs.json
before this grinder starts. Run regime_switcher_prepass.py first.

Output (under autoresearch/_state/regime_switcher_stage1/):
    progress.json        live progress meter
    results.jsonl        every (passed-the-floors) candidate
    rejections.jsonl     every (broke-a-floor) candidate
    keepers.jsonl        candidates that improved wide_pnl over prior best
    runner.pid           current process PID
    grinder.log          structured log

CLI:
    pythonw.exe -m autoresearch.regime_switcher_grinder --hours 1 --workers 4

Constraints (CLAUDE.md):
  - OP 15: MAX_PARALLEL_RESEARCH_WORKERS = 4 (multiprocessing.Pool, NOT threads)
  - OP 16: edge_capture is PRIMARY; aggregate is secondary
  - OP 19: every result row carries top5_pct, quarter_pnl, positive_quarters, max_drawdown
  - OP 11/13: pure Python, no LLM in the loop
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

OUT_DIR = REPO / "autoresearch" / "_state" / "regime_switcher_stage1"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROGRESS = OUT_DIR / "progress.json"
RESULTS = OUT_DIR / "results.jsonl"
REJECTIONS = OUT_DIR / "rejections.jsonl"
KEEPERS = OUT_DIR / "keepers.jsonl"
PIDFILE = OUT_DIR / "runner.pid"
LOGFILE = OUT_DIR / "grinder.log"

MATRIX_PATH = OUT_DIR / "strategy_pnl_matrix.json"
INPUTS_PATH = OUT_DIR / "regime_inputs.json"


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
    """Stage 1 grid (UPDATED 2026-05-13 evening — SNIPER excluded).

    SNIPER removed from chop_default_strategy options (T42-full real-fills
    invalidated SNIPER 0/432 keepers). Chop default is now deterministic VWAP.
    To keep combo count meaningful we expand range_chop_thresh + add gap_chop
    independence.

    Locked (NOT swept):
      - vix_jump_thresh = 1.5
      - macro_proximity_hr = 24
      - chop_default_strategy = VWAP (SNIPER excluded)

    Sweeps (6 knobs):
      - vix_high_thresh:        4 values (18, 20, 22, 24)
      - vix_low_thresh:         3 values (15, 17, 19)
      - vix_chop_thresh:        3 values (18, 20, 22)
      - gap_thresh:             3 values (0.75, 1.00, 1.25); gap_chop mirrors
      - range_thresh:           3 values (4.0, 5.0, 6.0)
      - range_chop_thresh:      3 values (3.0, 4.0, 5.0)

    Total: 4 * 3 * 3 * 3 * 3 * 3 = 972 combos.
    """
    grid: list[dict] = []
    for vix_high_thresh in [18.0, 20.0, 22.0, 24.0]:
        for vix_low_thresh in [15.0, 17.0, 19.0]:
            for vix_chop_thresh in [18.0, 20.0, 22.0]:
                for gap_thresh in [0.75, 1.00, 1.25]:
                    for range_thresh in [4.0, 5.0, 6.0]:
                        for range_chop_thresh in [3.0, 4.0, 5.0]:
                            grid.append({
                                "vix_high_thresh": vix_high_thresh,
                                "vix_low_thresh": vix_low_thresh,
                                "vix_chop_thresh": vix_chop_thresh,
                                "gap_thresh": gap_thresh,
                                "gap_chop_thresh": gap_thresh,  # spec §7: mirror
                                "range_thresh": range_thresh,
                                "range_chop_thresh": range_chop_thresh,
                                "chop_default_strategy": "VWAP",  # SNIPER excluded
                                "vix_jump_thresh": 1.5,
                                "macro_proximity_hr": 24.0,
                            })
    return grid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=1.0,
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

    # Pre-pass sanity: refuse to start if cache missing
    if not MATRIX_PATH.exists() or not INPUTS_PATH.exists():
        msg = (
            f"REFUSE TO START: missing pre-pass cache.\n"
            f"  expected: {MATRIX_PATH}\n"
            f"            {INPUTS_PATH}\n"
            f"Run `python -m autoresearch.regime_switcher_prepass` first."
        )
        logging.error(msg)
        sys.stderr.write(msg + "\n")
        return 2

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
        f"regime_switcher Stage 1 started: {len(grid)} combos, "
        f"{workers} workers, deadline={deadline}"
    )

    from autoresearch.regime_switcher_evaluator import evaluate_regime_combo  # noqa: E402

    completed = 0
    keepers_n = 0
    best_wide: tuple[float, dict] | None = None

    with mp.Pool(workers) as pool:
        for result in pool.imap_unordered(evaluate_regime_combo, grid, chunksize=1):
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
                        f"anchor_correct={result['anchor_classification_correct']}/7 "
                        f"combo={result['combo']}"
                    )

                if result["edge_capture"] > state["best_edge_capture"]:
                    state["best_edge_capture"] = result["edge_capture"]
            else:
                _append_jsonl(REJECTIONS, result)
                state["rejected"] += 1

            state["completed"] = completed
            state["last_update"] = dt.datetime.now().isoformat()
            if completed % 25 == 0:
                _write_progress(state)
                logging.info(
                    f"progress: {completed}/{len(grid)} "
                    f"passed={state['passed_floors']} keepers={keepers_n}"
                )

    state["status"] = "completed" if state["status"] == "running" else state["status"]
    state["completed_at"] = dt.datetime.now().isoformat()
    _write_progress(state)

    if PIDFILE.exists():
        try:
            PIDFILE.unlink()
        except Exception:
            pass

    if best_wide:
        logging.info(
            f"regime_switcher Stage 1 done: {completed}/{len(grid)} "
            f"passed={state['passed_floors']} keepers={keepers_n} "
            f"best_wide=${best_wide[0]:.0f}"
        )
    else:
        logging.info(
            f"regime_switcher Stage 1 done: {completed}/{len(grid)} "
            f"passed={state['passed_floors']} no keepers"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
