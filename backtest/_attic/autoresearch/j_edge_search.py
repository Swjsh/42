"""J-edge focused search — optimize edge_capture per CLAUDE.md operating principle 16.

Random sample from a knob space tightly focused on J's BEARISH_REJECTION setup.
For each candidate:
  1. Score primary = edge_capture (winners captured - losers added)
  2. Score secondary = sum of validate-window total_pnl  (tiebreaker only)
  3. KEEP only if edge_capture > current best

Knob space (focused on J's pattern):
  - strike_offset_bear:        [0, 1, 2, 3]    (ATM, OTM-1, OTM-2, OTM-3)
  - min_triggers_bear:         [1, 2, 3]
  - premium_stop_pct_bear:     [-0.05, -0.10, -0.15, -0.20]
  - tp1_premium_pct:           [0.30, 0.50, 0.75, 1.00]
  - tp1_qty_fraction:          [0.50, 0.67, 0.80, 1.00]
  - runner_target_premium_pct: [1.0, 2.0, 3.0, 5.0]
  - ribbon_spread_min_cents:   [20, 30, 40, 50, 60]
  - f9_vol_mult:               [0.4, 0.5, 0.6, 0.7, 0.8]

Output: backtest/autoresearch/_state/j_edge_search/results.jsonl
        analysis/recommendations/v15-j-edge.json (winning candidate, if any)
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
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# Use pythonw.exe (no console) for multiprocessing workers on Windows.
# Otherwise each worker spawns a python.exe with a brief console window flash
# that steals focus. pythonw is identical to python except no console allocation.
if sys.platform == "win32":
    _venv_pythonw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _venv_pythonw.exists():
        mp.set_executable(str(_venv_pythonw))

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner, j_edge_tracker

OUT_DIR = REPO / "autoresearch" / "_state" / "j_edge_search"
SCORECARD_PATH = REPO.parent / "analysis" / "recommendations" / "v15-j-edge.json"
PARAMS_BASE_PATH = REPO.parent / "automation" / "state" / "params.json"

MAX_PARALLEL = 4

# Tight knob space focused on J's edge.
SEARCH_SPACE = {
    "strike_offset_bear":          [0, 1, 2, 3],
    "min_triggers_bear":           [1, 2, 3],
    "premium_stop_pct_bear":       [-0.05, -0.10, -0.15, -0.20, -0.30],
    "tp1_premium_pct":             [0.30, 0.50, 0.75, 1.00],
    "tp1_qty_fraction":            [0.33, 0.50, 0.67, 0.80, 1.00],
    "runner_target_premium_pct":   [1.0, 2.0, 3.0, 5.0],
    "ribbon_spread_min_cents":     [20, 30, 40, 50, 60],
    "f9_vol_mult":                 [0.4, 0.5, 0.6, 0.7, 0.8],
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Candidate:
    seed: int


_BASE = None
_SPY = None
_VIX = None
_SPY_VAL = None
_VIX_VAL = None


def _worker_init(base_params: dict, j_min: str, j_max: str, val_start: str, val_end: str) -> None:
    global _BASE, _SPY, _VIX, _SPY_VAL, _VIX_VAL
    _BASE = base_params
    _SPY, _VIX = runner.load_data(dt.date.fromisoformat(j_min), dt.date.fromisoformat(j_max))
    _SPY_VAL, _VIX_VAL = runner.load_data(dt.date.fromisoformat(val_start), dt.date.fromisoformat(val_end))


def generate_params_from_seed(seed: int) -> dict:
    """Deterministic param sample from SEARCH_SPACE."""
    rng = random.Random(seed)
    p = dict(_BASE)
    for knob, choices in SEARCH_SPACE.items():
        p[knob] = rng.choice(choices)
    # Force scope lock: bear setups only (drop bull side knobs to defaults)
    p.pop("strike_offset_itm", None)
    return p


def _worker_eval(c: Candidate) -> dict:
    p = generate_params_from_seed(c.seed)
    try:
        edge = j_edge_tracker.score_candidate(p, _SPY, _VIX)
        # Secondary: full validate-window pnl (tiebreak only)
        val_start = dt.date.fromisoformat("2026-02-14")
        val_end = dt.date.fromisoformat("2026-05-07")
        _, m_val = runner.run_with_params(p, val_start, val_end, _SPY_VAL, _VIX_VAL)
        return {
            "seed": c.seed,
            "params_diff": {k: p[k] for k in SEARCH_SPACE if p[k] != _BASE.get(k)},
            "edge_capture": edge["edge_capture"],
            "winners_capture": edge["winners_capture"],
            "winners_capture_pct": edge["winners_capture_pct"],
            "losers_added": edge["losers_added"],
            "by_day": [{"date": d["date"], "pnl": d.get("total_pnl", 0), "n": d.get("n_trades", 0)} for d in edge["by_day"]],
            "validate_pnl": round(m_val.total_pnl, 2),
            "validate_sharpe": round(m_val.sharpe_daily, 3),
            "validate_n": m_val.n_trades,
            "validate_wr": round(m_val.win_rate, 4),
        }
    except Exception as exc:  # noqa: BLE001
        return {"seed": c.seed, "error": repr(exc)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-seeds", type=int, default=200)
    ap.add_argument("--seed-start", type=int, default=10000)
    ap.add_argument("--workers", type=int, default=MAX_PARALLEL)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results_path = OUT_DIR / "results.jsonl"
    if results_path.exists():
        results_path.unlink()  # fresh search

    base = json.loads(PARAMS_BASE_PATH.read_text(encoding="utf-8-sig"))
    j_min = min(t["date"] for t in j_edge_tracker.J_WINNERS + j_edge_tracker.J_LOSERS)
    j_max = max(t["date"] for t in j_edge_tracker.J_WINNERS + j_edge_tracker.J_LOSERS)

    # Score baseline first
    logger.info("Loading data + scoring baseline (v14 production)...")
    spy, vix = runner.load_data(dt.date.fromisoformat(j_min), dt.date.fromisoformat(j_max))
    base_edge = j_edge_tracker.score_candidate(base, spy, vix)
    logger.info("BASELINE v14: edge_capture=$%+.0f winners_capture=%.0f%%",
                base_edge["edge_capture"], base_edge["winners_capture_pct"] * 100)

    jobs = [Candidate(seed=s) for s in range(args.seed_start, args.seed_start + args.n_seeds)]
    logger.info("Searching %d candidates with %d workers (knob space: %d combos total)",
                len(jobs), args.workers,
                __import__("math").prod(len(v) for v in SEARCH_SPACE.values()))

    best_score = base_edge["edge_capture"]
    best_record = None
    completed = 0
    t0 = time.time()

    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=args.workers, initializer=_worker_init,
                  initargs=(base, j_min, j_max, "2026-02-14", "2026-05-07")) as pool:
        for r in pool.imap_unordered(_worker_eval, jobs, chunksize=1):
            completed += 1
            with results_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(r) + "\n")
            if "error" in r:
                logger.warning("seed=%d ERROR", r["seed"])
                continue
            tag = ""
            if r["edge_capture"] > best_score:
                best_score = r["edge_capture"]
                best_record = r
                tag = " *** NEW BEST ***"
            if completed % 10 == 0 or tag:
                logger.info("[%3d/%d] seed=%d edge=$%+.0f cap=%.0f%% loss_added=$%.0f val_pnl=$%+.0f%s",
                            completed, len(jobs), r["seed"],
                            r["edge_capture"], r["winners_capture_pct"] * 100,
                            r["losers_added"], r["validate_pnl"], tag)

    elapsed = time.time() - t0
    logger.info("=" * 80)
    logger.info("DONE in %.1f min. Baseline=%+.0f  best=%+.0f", elapsed / 60, base_edge["edge_capture"], best_score)

    if best_record:
        # Build final scorecard
        final_params = dict(base)
        for k, v in best_record["params_diff"].items():
            final_params[k] = v
        final_params.pop("strike_offset_itm", None)
        scorecard = {
            "rule_id": "v15-j-edge",
            "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "verdict": "candidate_proposed",
            "method": "j_edge_search optimizing edge_capture (CLAUDE.md operating principle 16)",
            "baseline_v14_edge_capture": base_edge["edge_capture"],
            "winner_seed": best_record["seed"],
            "winner_edge_capture": best_record["edge_capture"],
            "winner_winners_capture_pct": best_record["winners_capture_pct"],
            "winner_losers_added": best_record["losers_added"],
            "winner_validate_pnl": best_record["validate_pnl"],
            "winner_validate_sharpe": best_record["validate_sharpe"],
            "params_diff_from_v14": best_record["params_diff"],
            "full_proposed_params": final_params,
            "by_day": best_record["by_day"],
            "n_candidates_searched": completed,
        }
        SCORECARD_PATH.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
        logger.info("Scorecard written: %s", SCORECARD_PATH)
    else:
        logger.warning("NO candidate beat baseline. Stay on v14.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
