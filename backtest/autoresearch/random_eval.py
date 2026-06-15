"""Random parameter search across the knob space.

Generates N random param sets within SEARCH_SPACE bounds, evaluates each
on TRAIN + VALIDATE windows, writes ranked results to disk.

Unlike loop.py (hill-climbing from a fixed starting point), this does
broad random sampling — useful when the local search space is exhausted
or when we want to escape regime-specific local optima.

Each batch is identified by a string id (A, B, C, ...) and processes a
disjoint range of seeds so multiple batches can run in parallel without
state-file conflicts.

CLI:
    python -m autoresearch.random_eval --batch-id A --seed-start 0  --seed-end 9
    python -m autoresearch.random_eval --batch-id B --seed-start 10 --seed-end 19
    python -m autoresearch.random_eval --batch-id C --seed-start 20 --seed-end 29

Output:
    backtest/autoresearch/_state/random_search/batch_<id>.jsonl       (one record per seed)
    backtest/autoresearch/_state/random_search/batch_<id>_progress.json (live progress)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import random
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

# Allow `python -m autoresearch.random_eval` from backtest/ root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import config, runner

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "autoresearch" / "_state" / "random_search"

# Knobs we sample randomly. NOISE_PRONE excluded by default (VIX) to keep
# results interpretable — they get tested separately if a candidate looks
# good. SECONDARY_ENTRY + SECONDARY_EXIT included so we explore broadly.
SAMPLED_KNOBS: frozenset[str] = frozenset(
    config.CORE_KNOBS | config.SECONDARY_ENTRY_KNOBS | config.SECONDARY_EXIT_KNOBS
)


def generate_params(seed: int) -> dict[str, Any]:
    """Build a random param set from SEARCH_SPACE using `seed` for reproducibility.

    Starts from BASELINE_PARAMS and overrides each sampled knob with a random
    choice from its SEARCH_SPACE list. Same seed always produces the same
    params — so a session can be resumed and reproduced exactly.
    """
    rng = random.Random(seed)
    params: dict[str, Any] = dict(config.BASELINE_PARAMS)
    for knob in sorted(SAMPLED_KNOBS):  # sorted for deterministic ordering
        if knob in config.SEARCH_SPACE:
            params[knob] = rng.choice(config.SEARCH_SPACE[knob])

    # Constraint: if both ends of no_trade_window are set, start must be < end.
    # If broken, neutralize the window (set end to None).
    s = params.get("no_trade_window_start")
    e = params.get("no_trade_window_end")
    if s is not None and e is not None and isinstance(s, str) and isinstance(e, str) and s >= e:
        params["no_trade_window_end"] = None

    return params


def evaluate_one(
    seed: int,
    params: dict[str, Any],
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    train_start: dt.date,
    train_end: dt.date,
    val_start: dt.date,
    val_end: dt.date,
) -> dict[str, Any]:
    """Run TRAIN + VALIDATE backtests with `params`, return the result record."""
    t0 = time.time()
    _, train_m = runner.run_with_params(params, train_start, train_end, spy_df, vix_df)
    _, val_m = runner.run_with_params(params, val_start, val_end, spy_df, vix_df)
    elapsed = time.time() - t0

    return {
        "seed": seed,
        "params": params,
        "train_metrics": train_m.to_dict(),
        "validate_metrics": val_m.to_dict(),
        "elapsed_seconds": round(elapsed, 2),
        "evaluated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def _read_done_seeds(path: Path) -> set[int]:
    """Parse a batch JSONL and return the set of seeds already evaluated."""
    if not path.exists():
        return set()
    done: set[int] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                seed = rec.get("seed")
                if isinstance(seed, int):
                    done.add(seed)
            except json.JSONDecodeError:
                continue
    return done


def _write_progress(path: Path, payload: dict[str, Any]) -> None:
    """Atomic-ish progress write so the dashboard never reads a half-flushed file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def run_batch(
    batch_id: str,
    seed_start: int,
    seed_end: int,
    train_start: dt.date,
    train_end: dt.date,
    val_start: dt.date,
    val_end: dt.date,
) -> None:
    """Run all seeds in [seed_start, seed_end] inclusive, append to batch JSONL.

    Resumable: if the batch file already exists, skip seeds whose results are
    already there.
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"batch_{batch_id}.jsonl"
    progress_path = OUT_DIR / f"batch_{batch_id}_progress.json"

    seeds_done = _read_done_seeds(out_path)
    if seeds_done:
        logger.info("[%s] resuming — %d seeds already done", batch_id, len(seeds_done))

    total = seed_end - seed_start + 1
    seeds_to_run = [s for s in range(seed_start, seed_end + 1) if s not in seeds_done]

    started_at = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    _write_progress(progress_path, {
        "batch_id": batch_id,
        "seed_range": f"{seed_start}-{seed_end}",
        "total": total,
        "completed": len(seeds_done),
        "current_seed": None,
        "started_at": started_at,
        "finished_at": None,
    })

    logger.info("[%s] loading data %s..%s", batch_id, train_start, val_end)
    spy_df, vix_df = runner.load_data(train_start, val_end)
    logger.info("[%s] loaded: %d SPY 5m bars, %d VIX 5m bars", batch_id, len(spy_df), len(vix_df))

    for i, seed in enumerate(seeds_to_run, 1):
        completed = len(seeds_done) + i - 1
        _write_progress(progress_path, {
            "batch_id": batch_id,
            "seed_range": f"{seed_start}-{seed_end}",
            "total": total,
            "completed": completed,
            "current_seed": seed,
            "started_at": started_at,
            "finished_at": None,
        })

        params = generate_params(seed)
        try:
            rec = evaluate_one(
                seed, params, spy_df, vix_df,
                train_start, train_end, val_start, val_end,
            )
        except Exception as exc:
            logger.exception("[%s] seed=%d FAILED: %s", batch_id, seed, exc)
            rec = {
                "seed": seed,
                "params": params,
                "error": repr(exc),
                "evaluated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }

        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

        if "validate_metrics" in rec:
            vm = rec["validate_metrics"]
            tm = rec["train_metrics"]
            logger.info(
                "[%s] seed=%d val_pnl=$%+.0f val_wr=%.0f%% val_sh=%+.2f train_sh=%+.2f train_n=%d val_n=%d (%.1fs)",
                batch_id, seed,
                vm.get("total_pnl", 0), vm.get("win_rate", 0) * 100,
                vm.get("sharpe_daily", 0), tm.get("sharpe_daily", 0),
                tm.get("n_trades", 0), vm.get("n_trades", 0),
                rec.get("elapsed_seconds", 0),
            )

    _write_progress(progress_path, {
        "batch_id": batch_id,
        "seed_range": f"{seed_start}-{seed_end}",
        "total": total,
        "completed": total,
        "current_seed": None,
        "started_at": started_at,
        "finished_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    })

    logger.info("[%s] BATCH COMPLETE — %d seeds evaluated, results in %s",
                batch_id, total, out_path.name)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    ap = argparse.ArgumentParser(description="Random parameter search batch runner.")
    ap.add_argument("--batch-id", required=True,
                    help="Batch identifier (e.g., A, B, C). Determines output filenames.")
    ap.add_argument("--seed-start", type=int, required=True,
                    help="First seed to evaluate (inclusive).")
    ap.add_argument("--seed-end", type=int, required=True,
                    help="Last seed to evaluate (inclusive).")
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
    logger.info("RANDOM SEARCH — batch %s, seeds %d..%d (%d total)",
                args.batch_id, args.seed_start, args.seed_end,
                args.seed_end - args.seed_start + 1)
    logger.info("Train:    %s..%s", train_start, train_end)
    logger.info("Validate: %s..%s", val_start, val_end)
    logger.info("Sampled knobs (%d): %s", len(SAMPLED_KNOBS),
                ", ".join(sorted(SAMPLED_KNOBS)))
    logger.info("=" * 60)

    run_batch(
        args.batch_id, args.seed_start, args.seed_end,
        train_start, train_end, val_start, val_end,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
