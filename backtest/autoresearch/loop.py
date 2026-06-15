"""Main autoresearch loop.

One iteration:
    1. Load state (or build from defaults / mode starting point).
    2. If baselines empty, run baseline backtest on TRAIN + VALIDATE windows.
    3. Propose ONE single-parameter modification (proposer.propose).
    4. Run the backtest with the modification on BOTH windows.
    5. Decide keep vs revert (decider.decide_with_validation).
       - KEEP if train sharpe improves AND validate sharpe doesn't regress.
       - REVERT otherwise.
    6. If keep: replace state.current_params + state.{train,validate}_baseline.
       If revert: state stays the same (only history.jsonl gains a row).
    7. Append to history.jsonl, save state.

CLI:
    # single mode
    python -m autoresearch.loop --mode balanced --iterations 10
    # all three modes (sequential)
    python -m autoresearch.loop --modes strict balanced aggressive --iterations 30 --reset
    # status
    python -m autoresearch.loop --status --mode strict
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

# Allow `python -m autoresearch.loop` from backtest/ root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import config, decider, proposer, runner, state as state_mod
from autoresearch.metrics import TradeMetrics, compute_metrics

logger = logging.getLogger(__name__)


def _run_window(
    params: dict[str, Any], start: dt.date, end: dt.date,
    spy_df: pd.DataFrame, vix_df: pd.DataFrame,
) -> TradeMetrics:
    """Run a backtest over one window with the given params; return metrics only."""
    _, metrics = runner.run_with_params(params, start, end, spy_df=spy_df, vix_df=vix_df)
    return metrics


def _ensure_baselines(
    s: state_mod.State, spy_df: pd.DataFrame, vix_df: pd.DataFrame
) -> None:
    """Run baseline backtests on TRAIN + VALIDATE windows if not yet present.

    Performs PRE-FLIGHT GATE SANITY CHECK after baselines are computed
    (added 2026-05-09 after the gate-bug retrospective). Logs warnings
    when KEEP_THRESHOLDS look unreachable; does NOT refuse to proceed
    (mode-only sweeps may legitimately have sparse baselines).
    """
    if s.baseline_metrics and s.validate_baseline_metrics:
        return
    train_start = dt.date.fromisoformat(s.training_window["start"])
    train_end = dt.date.fromisoformat(s.training_window["end"])
    val_start = dt.date.fromisoformat(s.validate_window["start"])
    val_end = dt.date.fromisoformat(s.validate_window["end"])

    logger.info("baseline TRAIN %s..%s", train_start, train_end)
    t0 = time.time()
    train_m = _run_window(s.current_params, train_start, train_end, spy_df, vix_df)
    logger.info("  TRAIN: %d trades, sharpe=%.3f, pnl=$%.0f, wr=%.0f%% (%.1fs)",
                train_m.n_trades, train_m.sharpe_daily, train_m.total_pnl,
                train_m.win_rate * 100, time.time() - t0)
    state_mod.update_baseline(s, train_m)

    logger.info("baseline VALIDATE %s..%s", val_start, val_end)
    t0 = time.time()
    val_m = _run_window(s.current_params, val_start, val_end, spy_df, vix_df)
    logger.info("  VALIDATE: %d trades, sharpe=%.3f, pnl=$%.0f, wr=%.0f%% (%.1fs)",
                val_m.n_trades, val_m.sharpe_daily, val_m.total_pnl,
                val_m.win_rate * 100, time.time() - t0)
    state_mod.update_validate_baseline(s, val_m)

    # Pre-flight gate sanity check.
    warnings = config.validate_gates_against_baseline(s.baseline_metrics)
    if warnings:
        logger.warning("[%s/%s] PRE-FLIGHT GATE WARNINGS:", s.mode or "default", s.experiment or "full")
        for w in warnings:
            logger.warning("  ! %s", w)
        logger.warning("Iterations may auto-revert. Lower KEEP_THRESHOLDS or relax mode params if so.")


def _one_iteration(
    s: state_mod.State, spy_df: pd.DataFrame, vix_df: pd.DataFrame
) -> dict | None:
    """One propose/run-train/run-validate/decide cycle. Returns the history record."""
    s.iteration += 1
    p = proposer.propose(s)
    if p is None:
        return None

    train_start = dt.date.fromisoformat(s.training_window["start"])
    train_end = dt.date.fromisoformat(s.training_window["end"])
    val_start = dt.date.fromisoformat(s.validate_window["start"])
    val_end = dt.date.fromisoformat(s.validate_window["end"])
    candidate_params = dict(s.current_params)
    # Apply ALL proposed changes (single or multi-knob).
    for param, _old, new in p.changes:
        candidate_params[param] = new

    t0 = time.time()
    train_m = _run_window(candidate_params, train_start, train_end, spy_df, vix_df)
    val_m = _run_window(candidate_params, val_start, val_end, spy_df, vix_df)
    elapsed = time.time() - t0

    d = decider.decide_with_validation(
        train_m, s.baseline_metrics, val_m, s.validate_baseline_metrics,
        objective=getattr(s, "objective", config.DEFAULT_OBJECTIVE),
    )

    record = {
        "iteration": s.iteration,
        "session_id": s.session_id,
        "mode": s.mode,
        "experiment": s.experiment,
        "proposal": p.to_dict(),
        "train_metrics": train_m.to_dict(),
        "validate_metrics": val_m.to_dict(),
        "decision": d.to_dict(),
        "elapsed_seconds": round(elapsed, 2),
    }

    s.touch_param(p.param)
    if d.keep:
        s.modifications_kept += 1
        for param, _old, new in p.changes:
            s.current_params[param] = new
        state_mod.update_baseline(s, train_m)
        state_mod.update_validate_baseline(s, val_m)
        logger.info(
            "KEEP iter=%d [%s/%s] %s | train sharpe %+.3f, train pnl $%+.0f, val sharpe %+.3f",
            s.iteration, s.mode or "default", s.experiment or "full",
            p.rationale, d.delta_sharpe, d.delta_pnl,
            val_m.sharpe_daily - float(s.validate_baseline_metrics.get("sharpe_daily", 0)),
        )
    else:
        s.modifications_reverted += 1
        logger.info(
            "REVERT iter=%d [%s/%s] %s | %s",
            s.iteration, s.mode or "default", s.experiment or "full",
            p.rationale, d.reason,
        )

    return record


def run_loop(
    iterations: int,
    train_start: dt.date, train_end: dt.date,
    validate_start: dt.date, validate_end: dt.date,
    mode: str | None = None,
    experiment: str = "full",
    reset: bool = False,
    objective: str = config.DEFAULT_OBJECTIVE,
) -> None:
    """Run `iterations` autoresearch cycles for one (mode, experiment) pair."""
    s = state_mod.load_state(mode=mode)
    if reset or s is None:
        if reset and s is not None:
            logger.info(
                "[%s/%s] resetting state (was at iter %d, %d kept / %d reverted)",
                mode or "default", experiment, s.iteration,
                s.modifications_kept, s.modifications_reverted,
            )
        # Pick starting params from mode
        starting_params = (
            dict(config.MODES[mode]) if mode and mode in config.MODES
            else dict(config.BASELINE_PARAMS)
        )
        s = state_mod.fresh_state(
            train_start, train_end, validate_start, validate_end,
            mode=mode, starting_params=starting_params, experiment=experiment,
            objective=objective,
        )
    else:
        # Update experiment if the user changed it.
        if s.experiment != experiment:
            logger.info("[%s] experiment %s -> %s", mode or "default", s.experiment, experiment)
            s.experiment = experiment
        # Update objective if the user changed it.
        if getattr(s, "objective", config.DEFAULT_OBJECTIVE) != objective:
            logger.info("[%s] objective %s -> %s", mode or "default",
                        getattr(s, "objective", config.DEFAULT_OBJECTIVE), objective)
            s.objective = objective
        # Re-anchor windows if they changed.
        new_train = {"start": train_start.isoformat(), "end": train_end.isoformat()}
        new_val = {"start": validate_start.isoformat(), "end": validate_end.isoformat()}
        if s.training_window != new_train or s.validate_window != new_val:
            logger.info("[%s] windows changed; recomputing baselines", mode or "default")
            s.training_window = new_train
            s.validate_window = new_val
            s.baseline_metrics = {}
            s.validate_baseline_metrics = {}

    spy_df, vix_df = runner.load_data(train_start, validate_end)
    logger.info("[%s] loaded data: %d SPY 5m bars, %d VIX 5m bars",
                mode or "default", len(spy_df), len(vix_df))

    _ensure_baselines(s, spy_df, vix_df)
    state_mod.save_state(s)

    for i in range(iterations):
        rec = _one_iteration(s, spy_df, vix_df)
        if rec is None:
            logger.info("[%s] no proposal — stopping", mode or "default")
            break
        state_mod.append_history(rec, mode=mode)
        state_mod.save_state(s)

    print_status(s)


def run_modes(
    modes: list[str],
    iterations: int,
    train_start: dt.date, train_end: dt.date,
    validate_start: dt.date, validate_end: dt.date,
    experiment: str = "full",
    reset: bool = False,
    objective: str = config.DEFAULT_OBJECTIVE,
) -> None:
    """Run autoresearch for multiple modes sequentially under one experiment."""
    for mode in modes:
        if mode not in config.MODES:
            logger.error("unknown mode '%s'; choices: %s", mode, list(config.MODES))
            continue
        logger.info("=" * 60)
        logger.info("STARTING MODE: %s | EXPERIMENT: %s | OBJECTIVE: %s",
                    mode.upper(), experiment.upper(), objective.upper())
        logger.info("=" * 60)
        run_loop(iterations, train_start, train_end, validate_start, validate_end,
                 mode=mode, experiment=experiment, reset=reset, objective=objective)
        logger.info("=" * 60)
        logger.info("FINISHED MODE: %s", mode.upper())
        logger.info("=" * 60)


def print_status(s: state_mod.State) -> None:
    """Print a concise summary of current state."""
    print("\n" + "=" * 60)
    print(f"AUTORESEARCH STATUS [{s.mode or 'default'}]")
    print("=" * 60)
    print(f"Session:               {s.session_id}")
    print(f"Train window:          {s.training_window['start']} -> {s.training_window['end']}")
    print(f"Validate window:       {s.validate_window['start']} -> {s.validate_window['end']}")
    print(f"Iterations:            {s.iteration}")
    print(f"Modifications kept:    {s.modifications_kept}")
    print(f"Modifications reverted:{s.modifications_reverted}")
    if s.iteration > 0:
        print(f"Keep rate:             {100 * s.modifications_kept / s.iteration:.1f}%")
    print(f"Last modified:         {s.last_param_modified} at {s.last_modification_at}")
    print()
    print("Current parameters:")
    base = config.MODES.get(s.mode or "", config.BASELINE_PARAMS)
    for k, v in s.current_params.items():
        delta = " (mode default)" if v == base.get(k) else f" (was {base.get(k)})"
        print(f"  {k:<32} = {v!r:<22}{delta}")
    print()
    print("TRAIN baseline metrics:")
    for k, v in s.baseline_metrics.items():
        print(f"  {k:<20} = {v}")
    print()
    print("VALIDATE baseline metrics:")
    for k, v in s.validate_baseline_metrics.items():
        print(f"  {k:<20} = {v}")
    print()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=1)
    ap.add_argument("--mode", choices=list(config.MODES.keys()), default=None,
                    help="Single-mode run")
    ap.add_argument("--modes", nargs="+", choices=list(config.MODES.keys()),
                    help="Multi-mode run (sequential)")
    ap.add_argument("--train-start", default=config.DEFAULT_TRAIN_START)
    ap.add_argument("--train-end", default=config.DEFAULT_TRAIN_END)
    ap.add_argument("--validate-start", default=config.DEFAULT_VALIDATE_START)
    ap.add_argument("--validate-end", default=config.DEFAULT_VALIDATE_END)
    ap.add_argument("--experiment", default="full",
                    choices=list(config.EXPERIMENTS.keys()),
                    help="Knob tier scope (lean=core only, full=core+secondary, etc.)")
    ap.add_argument("--objective", default=config.DEFAULT_OBJECTIVE,
                    choices=list(config.OBJECTIVES),
                    help="Optimization target: train_sharpe (default) | validate_sharpe | validate_pnl | validate_expectancy")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--status", action="store_true",
                    help="Print state and exit (no iterations).")
    args = ap.parse_args()

    train_start = dt.date.fromisoformat(args.train_start)
    train_end = dt.date.fromisoformat(args.train_end)
    val_start = dt.date.fromisoformat(args.validate_start)
    val_end = dt.date.fromisoformat(args.validate_end)

    if args.status:
        if args.modes:
            for m in args.modes:
                s = state_mod.load_state(mode=m)
                if s is None:
                    print(f"[{m}] no state yet")
                else:
                    print_status(s)
        else:
            s = state_mod.load_state(mode=args.mode)
            if s is None:
                print(f"[{args.mode or 'default'}] no state yet")
            else:
                print_status(s)
        return 0

    if args.modes:
        run_modes(args.modes, args.iterations, train_start, train_end,
                  val_start, val_end, experiment=args.experiment, reset=args.reset,
                  objective=args.objective)
    else:
        run_loop(args.iterations, train_start, train_end, val_start, val_end,
                 mode=args.mode, experiment=args.experiment, reset=args.reset,
                 objective=args.objective)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
