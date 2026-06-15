"""Hill-climb refinement around seed 6 (the v15 winner).

Replaces the crashed PHASE 2 with a multiprocessing.Pool pattern (proven
reliable in PHASE 0). Each worker takes a (knob, direction) proposal,
runs train+validate, returns the result. Main process runs the
keep/revert decision logic and feeds the next batch of proposals.

Strategy:
1. Start state = seed 6 params (the v15 winner)
2. For N iterations:
   - Generate K proposals (one knob change each, mix of CORE + SECONDARY)
   - Run all K in parallel (4 workers max)
   - Pick the best proposal IF it improves objective vs current
   - KEEP: update state. REVERT: discard.
3. Save final refined state to _state/seed6_refined/state.json
4. Compare refined vs raw seed 6, write report

CLI:
    python -m autoresearch.seed6_climb_parallel
    python -m autoresearch.seed6_climb_parallel --iterations 30 --proposals-per-iter 8
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import multiprocessing as mp
import os
import sys
import random
import sys
import time

# Use pythonw.exe (no console flash on workers).
if sys.platform == 'win32':
    _pw = __import__('pathlib').Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _pw.exists():
        mp.set_executable(str(_pw))
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import config, runner, random_eval

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "autoresearch" / "_state" / "seed6_refined"
MAX_PARALLEL = 4

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Proposal:
    iter_num: int
    proposal_id: int
    knob: str
    old_value: Any
    new_value: Any
    params: dict[str, Any] = field(hash=False, compare=False)


_WORKER_SPY = None
_WORKER_VIX = None


def _worker_init(train_start: str, val_end: str) -> None:
    global _WORKER_SPY, _WORKER_VIX
    s = dt.date.fromisoformat(train_start)
    e = dt.date.fromisoformat(val_end)
    _WORKER_SPY, _WORKER_VIX = runner.load_data(s, e)


def _worker_run(p: Proposal) -> dict:
    train_start = dt.date.fromisoformat(config.DEFAULT_TRAIN_START)
    train_end = dt.date.fromisoformat(config.DEFAULT_TRAIN_END)
    val_start = dt.date.fromisoformat(config.DEFAULT_VALIDATE_START)
    val_end = dt.date.fromisoformat(config.DEFAULT_VALIDATE_END)
    try:
        _, train_m = runner.run_with_params(p.params, train_start, train_end, _WORKER_SPY, _WORKER_VIX)
        _, val_m = runner.run_with_params(p.params, val_start, val_end, _WORKER_SPY, _WORKER_VIX)
        return {
            "iter": p.iter_num, "proposal_id": p.proposal_id,
            "knob": p.knob, "old": p.old_value, "new": p.new_value,
            "train": train_m.to_dict(), "validate": val_m.to_dict(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"iter": p.iter_num, "proposal_id": p.proposal_id,
                "knob": p.knob, "error": repr(exc)}


def generate_proposals(current_params: dict, iter_num: int, k: int, rng: random.Random) -> list[Proposal]:
    """Sample K (knob, alternative-value) proposals from SEARCH_SPACE."""
    knobs = sorted(config.CORE_KNOBS | config.SECONDARY_ENTRY_KNOBS | config.SECONDARY_EXIT_KNOBS)
    knobs = [k for k in knobs if k in config.SEARCH_SPACE]
    proposals = []
    for pid in range(k):
        knob = rng.choice(knobs)
        space = list(config.SEARCH_SPACE[knob])
        current = current_params.get(knob)
        alternatives = [v for v in space if v != current]
        if not alternatives:
            continue
        new_value = rng.choice(alternatives)
        new_params = dict(current_params)
        new_params[knob] = new_value
        # No-trade window constraint
        s = new_params.get("no_trade_window_start")
        e = new_params.get("no_trade_window_end")
        if s and e and isinstance(s, str) and isinstance(e, str) and s >= e:
            new_params["no_trade_window_end"] = None
        proposals.append(Proposal(iter_num, pid, knob, current, new_value, new_params))
    return proposals


def score(metrics: dict, train_metrics: dict) -> float:
    """Combined score: validate P&L (primary), penalised by negative train sharpe."""
    val_pnl = metrics.get("total_pnl", 0)
    train_sh = train_metrics.get("sharpe_daily", 0)
    train_n = train_metrics.get("n_trades", 0)
    n_factor = min(1.0, train_n / 30.0)
    sign = 1.0 if train_sh > 0 else (-1.0 if train_sh < 0 else 0.0)
    return val_pnl * sign * n_factor


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=20)
    ap.add_argument("--proposals-per-iter", type=int, default=8)
    ap.add_argument("--workers", type=int, default=MAX_PARALLEL)
    ap.add_argument("--seed", type=int, default=6, help="Starting seed (default: 6 = v15 winner)")
    ap.add_argument("--rng-seed", type=int, default=42, help="RNG seed for reproducible proposals")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    history_path = OUT_DIR / "history.jsonl"

    # Start from seed 6's params
    current_params = random_eval.generate_params(args.seed)
    logger.info("Refining from seed=%d (v15 winner)", args.seed)

    train_start = dt.date.fromisoformat(config.DEFAULT_TRAIN_START)
    train_end = dt.date.fromisoformat(config.DEFAULT_TRAIN_END)
    val_start = dt.date.fromisoformat(config.DEFAULT_VALIDATE_START)
    val_end = dt.date.fromisoformat(config.DEFAULT_VALIDATE_END)

    # Compute baseline
    logger.info("Loading data + computing baseline...")
    spy, vix = runner.load_data(train_start, val_end)
    _, base_train = runner.run_with_params(current_params, train_start, train_end, spy, vix)
    _, base_val = runner.run_with_params(current_params, val_start, val_end, spy, vix)
    current_score = score(base_val.to_dict(), base_train.to_dict())
    logger.info("Baseline: train_pnl=%+.0f train_sh=%+.2f val_pnl=%+.0f val_sh=%+.2f score=%+.0f",
                base_train.total_pnl, base_train.sharpe_daily, base_val.total_pnl, base_val.sharpe_daily, current_score)

    rng = random.Random(args.rng_seed)
    keeps = 0
    reverts = 0
    ctx = mp.get_context("spawn")

    for it in range(1, args.iterations + 1):
        proposals = generate_proposals(current_params, it, args.proposals_per_iter, rng)
        logger.info("[iter %d/%d] generating %d proposals", it, args.iterations, len(proposals))
        t0 = time.time()
        results = []
        with ctx.Pool(processes=args.workers, initializer=_worker_init,
                      initargs=(train_start.isoformat(), val_end.isoformat())) as pool:
            for r in pool.imap_unordered(_worker_run, proposals, chunksize=1):
                results.append(r)
        elapsed = time.time() - t0

        # Pick best from this iteration
        best = None
        best_score = current_score
        for r in results:
            if "error" in r:
                continue
            s = score(r["validate"], r["train"])
            if s > best_score:
                best_score = s
                best = r

        if best is not None:
            keeps += 1
            knob = best["knob"]
            current_params[knob] = best["new"]
            improvement = best_score - current_score
            logger.info("[iter %d] KEEP %s: %s -> %s  score %+.0f -> %+.0f (Δ %+.0f)  (%.1fs)",
                        it, knob, best["old"], best["new"], current_score, best_score, improvement, elapsed)
            current_score = best_score
            with history_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"iter": it, "decision": "KEEP", **best}) + "\n")
        else:
            reverts += 1
            logger.info("[iter %d] all %d proposals REVERTED (%.1fs)", it, len(results), elapsed)
            with history_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"iter": it, "decision": "REVERT", "n_proposals": len(results), "elapsed_s": round(elapsed, 1)}) + "\n")

    # Final: save refined params + comparison
    final_path = OUT_DIR / "refined_params.json"
    final_path.write_text(json.dumps({
        "starting_seed": args.seed,
        "iterations": args.iterations,
        "keeps": keeps,
        "reverts": reverts,
        "starting_baseline": {"train": base_train.to_dict(), "validate": base_val.to_dict()},
        "refined_params": current_params,
        "final_score": current_score,
    }, indent=2), encoding="utf-8")
    logger.info("=" * 60)
    logger.info("DONE: keeps=%d reverts=%d  score %+.0f -> %+.0f",
                keeps, reverts, score(base_val.to_dict(), base_train.to_dict()), current_score)
    logger.info("Refined params saved to: %s", final_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
