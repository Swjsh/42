"""Parallel batch executor for random parameter search.

Wraps random_eval.evaluate_one in a multiprocessing.Pool so N seeds evaluate
concurrently across CPU cores. Single-writer pattern: workers stream results
back to the main process via imap_unordered, main process appends to the batch
JSONL — no file locks, no interleave risk.

WHY MULTIPROCESSING (not threading):
    runner._patched_filter_constants mutates module-level constants in
    backtest/lib/filters.py via contextmanager. That mutation is NOT
    thread-safe and NOT reentrant. Process-based parallelism gives each
    worker its own copy of lib.filters via fresh import (Windows spawn
    semantics), which is the only safe model.

CONCURRENCY CAP:
    MAX_PARALLEL_WORKERS = 4 (Windows + 16GB RAM headroom). Hard cap from
    CLAUDE.md operating principle 15. Exceeding this on this hardware
    causes thrashing and net throughput regression.

CLI:
    python -m autoresearch.parallel_eval --batch-id A --seed-start 0 --seed-end 29 --workers 4
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
import time

# Use pythonw.exe (no console flash on workers).
if sys.platform == 'win32':
    _pw = __import__('pathlib').Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _pw.exists():
        mp.set_executable(str(_pw))
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import config, random_eval, runner

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "autoresearch" / "_state" / "random_search"

MAX_PARALLEL_WORKERS: int = 4


@dataclass(frozen=True)
class WorkerJob:
    """Single seed evaluation work item — passed across process boundary."""

    seed: int
    train_start_iso: str
    train_end_iso: str
    val_start_iso: str
    val_end_iso: str


# Per-worker globals populated by _worker_init.
_WORKER_SPY_DF: pd.DataFrame | None = None
_WORKER_VIX_DF: pd.DataFrame | None = None


def _worker_init(train_start_iso: str, val_end_iso: str) -> None:
    """Pool initializer — runs once per worker process at startup.

    Loads SPY/VIX dataframes into module globals so subsequent evaluate calls
    don't re-pay the CSV read tax. On Windows (spawn), each worker also gets
    its own fresh import of lib.filters — safe for contextmanager patching.
    """
    global _WORKER_SPY_DF, _WORKER_VIX_DF
    train_start = dt.date.fromisoformat(train_start_iso)
    val_end = dt.date.fromisoformat(val_end_iso)
    _WORKER_SPY_DF, _WORKER_VIX_DF = runner.load_data(train_start, val_end)


def _worker_eval(job: WorkerJob) -> dict[str, Any]:
    """Worker entry point — generate params from seed and run TRAIN+VAL backtests."""
    if _WORKER_SPY_DF is None or _WORKER_VIX_DF is None:
        raise RuntimeError("Worker not initialized — _worker_init must run first")

    train_start = dt.date.fromisoformat(job.train_start_iso)
    train_end = dt.date.fromisoformat(job.train_end_iso)
    val_start = dt.date.fromisoformat(job.val_start_iso)
    val_end = dt.date.fromisoformat(job.val_end_iso)

    params = random_eval.generate_params(job.seed)
    try:
        return random_eval.evaluate_one(
            job.seed, params, _WORKER_SPY_DF, _WORKER_VIX_DF,
            train_start, train_end, val_start, val_end,
        )
    except Exception as exc:  # noqa: BLE001 — capture full failure mode in record
        logger.exception("worker seed=%d FAILED", job.seed)
        return {
            "seed": job.seed,
            "params": params,
            "error": repr(exc),
            "evaluated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }


def run_parallel_batch(
    batch_id: str,
    seed_start: int,
    seed_end: int,
    train_start: dt.date,
    train_end: dt.date,
    val_start: dt.date,
    val_end: dt.date,
    workers: int = MAX_PARALLEL_WORKERS,
) -> None:
    """Run [seed_start, seed_end] inclusive across `workers` processes.

    Resumable: skips seeds already present in batch_<id>.jsonl. Streams results
    via imap_unordered (any-order completion → faster fail-fast on first crash).
    Main process is sole writer of the JSONL file.
    """
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")
    if workers > MAX_PARALLEL_WORKERS:
        logger.warning(
            "workers=%d capped to MAX_PARALLEL_WORKERS=%d (CLAUDE.md op-principle 15)",
            workers, MAX_PARALLEL_WORKERS,
        )
        workers = MAX_PARALLEL_WORKERS

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"batch_{batch_id}.jsonl"
    progress_path = OUT_DIR / f"batch_{batch_id}_progress.json"

    seeds_done = random_eval._read_done_seeds(out_path)
    if seeds_done:
        logger.info("[%s] resuming — %d seeds already done", batch_id, len(seeds_done))

    total = seed_end - seed_start + 1
    seeds_to_run = [s for s in range(seed_start, seed_end + 1) if s not in seeds_done]
    if not seeds_to_run:
        logger.info("[%s] nothing to do — all %d seeds already evaluated", batch_id, total)
        return

    started_at = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    random_eval._write_progress(progress_path, {
        "batch_id": batch_id,
        "seed_range": f"{seed_start}-{seed_end}",
        "total": total,
        "completed": len(seeds_done),
        "current_seed": None,
        "workers": workers,
        "started_at": started_at,
        "finished_at": None,
        "mode": "parallel",
    })

    jobs = [
        WorkerJob(
            seed=s,
            train_start_iso=train_start.isoformat(),
            train_end_iso=train_end.isoformat(),
            val_start_iso=val_start.isoformat(),
            val_end_iso=val_end.isoformat(),
        )
        for s in seeds_to_run
    ]

    logger.info(
        "[%s] launching %d workers for %d seeds (skipping %d already done)",
        batch_id, workers, len(jobs), len(seeds_done),
    )

    completed = len(seeds_done)
    wall_t0 = time.time()

    ctx = mp.get_context("spawn")  # explicit spawn for Windows determinism
    with ctx.Pool(
        processes=workers,
        initializer=_worker_init,
        initargs=(train_start.isoformat(), val_end.isoformat()),
    ) as pool:
        for rec in pool.imap_unordered(_worker_eval, jobs, chunksize=1):
            with out_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")

            completed += 1
            random_eval._write_progress(progress_path, {
                "batch_id": batch_id,
                "seed_range": f"{seed_start}-{seed_end}",
                "total": total,
                "completed": completed,
                "current_seed": rec.get("seed"),
                "workers": workers,
                "started_at": started_at,
                "finished_at": None,
                "mode": "parallel",
            })

            if "validate_metrics" in rec:
                vm = rec["validate_metrics"]
                tm = rec["train_metrics"]
                logger.info(
                    "[%s] seed=%d val_pnl=$%+.0f val_wr=%.0f%% val_sh=%+.2f "
                    "train_sh=%+.2f train_n=%d val_n=%d (%.1fs) [%d/%d]",
                    batch_id, rec["seed"],
                    vm.get("total_pnl", 0), vm.get("win_rate", 0) * 100,
                    vm.get("sharpe_daily", 0), tm.get("sharpe_daily", 0),
                    tm.get("n_trades", 0), vm.get("n_trades", 0),
                    rec.get("elapsed_seconds", 0),
                    completed, total,
                )
            else:
                logger.error("[%s] seed=%d FAILED: %s", batch_id, rec.get("seed"), rec.get("error"))

    wall_elapsed = time.time() - wall_t0
    random_eval._write_progress(progress_path, {
        "batch_id": batch_id,
        "seed_range": f"{seed_start}-{seed_end}",
        "total": total,
        "completed": total,
        "current_seed": None,
        "workers": workers,
        "started_at": started_at,
        "finished_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "wall_elapsed_seconds": round(wall_elapsed, 1),
        "mode": "parallel",
    })

    speedup = (len(jobs) * 1.5) / max(wall_elapsed, 0.1)  # rough: serial baseline ~1.5s/seed
    logger.info(
        "[%s] PARALLEL BATCH COMPLETE — %d seeds in %.1fs (~%.1fx speedup vs serial)",
        batch_id, len(jobs), wall_elapsed, speedup,
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    ap = argparse.ArgumentParser(
        description="Parallel multiprocessing random param search batch runner.",
    )
    ap.add_argument("--batch-id", required=True)
    ap.add_argument("--seed-start", type=int, required=True)
    ap.add_argument("--seed-end", type=int, required=True)
    ap.add_argument("--workers", type=int, default=MAX_PARALLEL_WORKERS,
                    help=f"Pool size (default={MAX_PARALLEL_WORKERS}, hard cap={MAX_PARALLEL_WORKERS})")
    ap.add_argument("--train-start", default=config.DEFAULT_TRAIN_START)
    ap.add_argument("--train-end", default=config.DEFAULT_TRAIN_END)
    ap.add_argument("--validate-start", default=config.DEFAULT_VALIDATE_START)
    ap.add_argument("--validate-end", default=config.DEFAULT_VALIDATE_END)
    args = ap.parse_args()

    if args.seed_end < args.seed_start:
        ap.error(f"--seed-end ({args.seed_end}) must be >= --seed-start ({args.seed_start})")

    train_start = dt.date.fromisoformat(args.train_start)
    train_end = dt.date.fromisoformat(args.train_end)
    val_start = dt.date.fromisoformat(args.validate_start)
    val_end = dt.date.fromisoformat(args.validate_end)

    logger.info("=" * 60)
    logger.info(
        "PARALLEL RANDOM SEARCH — batch %s, seeds %d..%d (%d total), workers=%d",
        args.batch_id, args.seed_start, args.seed_end,
        args.seed_end - args.seed_start + 1, args.workers,
    )
    logger.info("Train:    %s..%s", train_start, train_end)
    logger.info("Validate: %s..%s", val_start, val_end)
    logger.info("=" * 60)

    run_parallel_batch(
        args.batch_id, args.seed_start, args.seed_end,
        train_start, train_end, val_start, val_end,
        workers=args.workers,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
