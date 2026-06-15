"""Hill-climb autoresearch from a specific random_eval seed as starting point.

Bridges the random search (broad exploration) and hill-climbing (local
refinement) stages of the search pipeline. After random_eval surfaces a
strong candidate, this script seeds the autoresearch loop with that
candidate's params and runs hill-climbing to refine further.

State is stored in `_state/seed{N}_climb/` so it doesn't collide with
the regular mode-named state directories.

CLI:
    python -m autoresearch.seed_climb --seed 6 --iterations 25 --objective validate_pnl
    python -m autoresearch.seed_climb --seed 9 --iterations 25 --reset
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import config, runner, state as state_mod
from autoresearch.loop import _ensure_baselines, _one_iteration, print_status
from autoresearch.random_eval import generate_params

logger = logging.getLogger(__name__)


def run_seed_climb(
    seed: int,
    iterations: int,
    train_start: dt.date,
    train_end: dt.date,
    val_start: dt.date,
    val_end: dt.date,
    experiment: str = "full",
    objective: str = "validate_pnl",
    reset: bool = False,
) -> None:
    """Run hill-climbing iterations from random_eval seed `seed` as starting point.

    The mode name passed to state_mod is `seed{seed}_climb`, which gives this
    sweep its own state directory and avoids polluting the main mode states.
    """
    mode_name = f"seed{seed}_climb"
    starting_params = generate_params(seed)

    s = state_mod.load_state(mode=mode_name)
    if reset or s is None:
        if reset and s is not None:
            logger.info(
                "[%s] resetting state (was at iter %d, %d kept / %d reverted)",
                mode_name, s.iteration,
                s.modifications_kept, s.modifications_reverted,
            )
        s = state_mod.fresh_state(
            train_start, train_end, val_start, val_end,
            mode=mode_name,
            starting_params=starting_params,
            experiment=experiment,
            objective=objective,
        )
    else:
        # Update objective / experiment if changed
        if s.experiment != experiment:
            logger.info("[%s] experiment %s -> %s", mode_name, s.experiment, experiment)
            s.experiment = experiment
        if getattr(s, "objective", config.DEFAULT_OBJECTIVE) != objective:
            logger.info("[%s] objective %s -> %s", mode_name,
                        getattr(s, "objective", config.DEFAULT_OBJECTIVE), objective)
            s.objective = objective

    spy_df, vix_df = runner.load_data(train_start, val_end)
    logger.info("[%s] loaded data: %d SPY 5m bars, %d VIX 5m bars",
                mode_name, len(spy_df), len(vix_df))

    _ensure_baselines(s, spy_df, vix_df)
    state_mod.save_state(s)

    logger.info("[%s] STARTING HILL-CLIMB from seed %d", mode_name, seed)
    logger.info("[%s] starting baseline: train_pnl=$%+.0f train_sharpe=%+.3f val_pnl=$%+.0f val_sharpe=%+.3f",
                mode_name,
                s.baseline_metrics.get("total_pnl", 0),
                s.baseline_metrics.get("sharpe_daily", 0),
                s.validate_baseline_metrics.get("total_pnl", 0),
                s.validate_baseline_metrics.get("sharpe_daily", 0))

    for i in range(iterations):
        rec = _one_iteration(s, spy_df, vix_df)
        if rec is None:
            logger.info("[%s] no proposal — stopping at iter %d", mode_name, s.iteration)
            break
        state_mod.append_history(rec, mode=mode_name)
        state_mod.save_state(s)

    print_status(s)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True,
                    help="random_eval seed whose params seed the hill-climb")
    ap.add_argument("--iterations", type=int, default=25)
    ap.add_argument("--train-start", default=config.DEFAULT_TRAIN_START)
    ap.add_argument("--train-end", default=config.DEFAULT_TRAIN_END)
    ap.add_argument("--validate-start", default=config.DEFAULT_VALIDATE_START)
    ap.add_argument("--validate-end", default=config.DEFAULT_VALIDATE_END)
    ap.add_argument("--experiment", default="full",
                    choices=list(config.EXPERIMENTS.keys()))
    ap.add_argument("--objective", default="validate_pnl",
                    choices=list(config.OBJECTIVES))
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    train_start = dt.date.fromisoformat(args.train_start)
    train_end = dt.date.fromisoformat(args.train_end)
    val_start = dt.date.fromisoformat(args.validate_start)
    val_end = dt.date.fromisoformat(args.validate_end)

    run_seed_climb(
        args.seed, args.iterations,
        train_start, train_end, val_start, val_end,
        experiment=args.experiment,
        objective=args.objective,
        reset=args.reset,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
