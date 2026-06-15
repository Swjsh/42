"""Finish PHASE 3 (sub-window stability test) and PHASE 4 (synthesize v15)
in one Python process when the PowerShell driver crashed.

Uses multiprocessing.Pool (same pattern as parallel_eval.py) so process
isolation handles lib.filters mutation safely. CLI accepts a list of seeds.

Usage:
    python -m autoresearch.finish_phases --seeds 6 231 55 23 210 222 240 239
    python -m autoresearch.finish_phases  # defaults to top-8 from random_search_summary
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import multiprocessing as mp
import os
import sys
import sys

# Use pythonw.exe (no console flash on workers).
if sys.platform == 'win32':
    _pw = __import__('pathlib').Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _pw.exists():
        mp.set_executable(str(_pw))
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import config, sub_window_test, runner, random_eval

REPO = Path(__file__).resolve().parent.parent
SUMMARY_PATH = REPO / "autoresearch" / "_state" / "random_search" / "random_search_summary.json"
SUB_WINDOW_DIR = REPO / "autoresearch" / "_state" / "random_search"
MAX_PARALLEL = 4

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubWindowJob:
    seed: int


_WORKER_SPY = None
_WORKER_VIX = None


def _worker_init() -> None:
    global _WORKER_SPY, _WORKER_VIX
    # sub_window_test SUB_WINDOWS span 2025-01-01 .. 2026-05-07 -- load that range.
    start = dt.date(2025, 1, 1)
    end = dt.date(2026, 5, 7)
    _WORKER_SPY, _WORKER_VIX = runner.load_data(start, end)


def _worker_run(job: SubWindowJob) -> dict:
    """Replay sub_window_test.run_for_seed but using already-loaded dataframes."""
    # sub_window_test.run_for_seed loads its own data; we want to reuse the worker's
    # cached data. Easiest: just call run_for_seed -- it loads data once which is fine.
    try:
        return sub_window_test.run_for_seed(job.seed, _WORKER_SPY, _WORKER_VIX)
    except Exception as exc:  # noqa: BLE001
        logger.exception("sub_window seed=%d FAILED", job.seed)
        return {"seed": job.seed, "error": repr(exc)}


def get_top_seeds(top_n: int = 8) -> list[int]:
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(f"summary missing: {SUMMARY_PATH} -- run aggregate_random first")
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    return [int(r["seed"]) for r in summary["top_candidates"][:top_n]]


def run_phase3(seeds: list[int], workers: int = MAX_PARALLEL) -> None:
    logger.info("PHASE 3 (sub-window) starting -- seeds=%s workers=%d", seeds, workers)
    jobs = [SubWindowJob(seed=s) for s in seeds]

    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=workers, initializer=_worker_init) as pool:
        for result in pool.imap_unordered(_worker_run, jobs, chunksize=1):
            seed = result.get("seed")
            if "error" in result:
                logger.error("seed=%d FAILED: %s", seed, result["error"])
            else:
                # sub_window_test.run_for_seed returns dict with key "stability"
                # (NOT "stability_summary"). Schema: n_total_windows, n_positive_pnl,
                # n_positive_sharpe, is_robust, verdict.
                stab = result.get("stability", {})
                verdict = stab.get("verdict", "?")
                n_pos_pnl = stab.get("n_positive_pnl", 0)
                n_pos_sh = stab.get("n_positive_sharpe", 0)
                logger.info(
                    "seed=%d verdict=%s pos_pnl=%d/5 pos_sh=%d/5",
                    seed, verdict, n_pos_pnl, n_pos_sh,
                )

    logger.info("PHASE 3 done")


def run_phase4() -> int:
    logger.info("PHASE 4 (synthesize v15) starting")
    from autoresearch import synthesize_v15
    return synthesize_v15.main()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+",
                    help="Seeds to sub-window test (default: top 8 from summary)")
    ap.add_argument("--workers", type=int, default=MAX_PARALLEL)
    ap.add_argument("--skip-phase3", action="store_true",
                    help="Skip sub-window test (already done) and go straight to synthesize")
    args = ap.parse_args()

    if not args.skip_phase3:
        seeds = args.seeds if args.seeds else get_top_seeds(8)
        run_phase3(seeds, args.workers)

    return run_phase4()


if __name__ == "__main__":
    raise SystemExit(main())
