"""Candidate A — J-edge search v2 (OP-16 primary, wider stop + ribbon frontier).

WHY:
  je_search run seeds 10000-10200 left 5/01 at -$22 (data divergence + BS price).
  This run targets the 5/01 gap with:
    - wider ribbon_spread_min_cents [10, 15, 20, 30] (relaxed from 30+)
    - larger stop range [-0.10 .. -0.30] to let 5/01 entry breathe
    - ITM-1 strike_offset = -1 (closer to money) for earlier delta capture on 5/01
  Goal: find edge_capture >= 1200 (vs current best 2769 which is BS-sim;
        real-fills baseline is 1086 from v14_enhanced).
  DOES NOT modify production params. Read-only search.

SEARCH SPACE:
  strike_offset_bear:          [-1, 0, 1, 2]    (ITM-1, ATM, OTM-1, OTM-2)
  min_triggers_bear:           [1, 2]
  premium_stop_pct_bear:       [-0.10, -0.15, -0.20, -0.25, -0.30]
  tp1_premium_pct:             [0.30, 0.50, 0.75, 1.00]
  tp1_qty_fraction:            [0.33, 0.50, 0.67]
  runner_target_premium_pct:   [1.5, 2.0, 3.0]
  ribbon_spread_min_cents:     [10, 15, 20, 30]   (< production 30 to catch 5/01)
  f9_vol_mult:                 [0.4, 0.5, 0.6, 0.7]

Seed range: 20000..20400 (400 seeds, no overlap with prior runs at 10000-10200)
State dir: backtest/autoresearch/_state/je_search_v2/
Scorecard: analysis/recommendations/je-search-v2.json

COMPLETION CRITERIA:
  - All 400 seeds evaluated, OR 2-hour wall-clock limit hit.
  - Writes progress.json every 20 seeds.
  - Passes OP-20 6-disclosure checklist only if best edge_capture >= 771.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import multiprocessing as mp
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# pythonw-safe: redirect stdout/stderr if running headless
if sys.platform == "win32":
    import os as _os
    _exe_name = _os.path.basename(sys.executable).lower()
    if "pythonw" in _exe_name:
        _log_dir = Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
        _log_dir.mkdir(parents=True, exist_ok=True)
        sys.stdout = open(_log_dir / "je_search_v2.stdout.log", "a", buffering=1, encoding="utf-8")
        sys.stderr = open(_log_dir / "je_search_v2.stderr.log", "a", buffering=1, encoding="utf-8")

import random

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner, j_edge_tracker

OUT_DIR = REPO / "autoresearch" / "_state" / "je_search_v2"
SCORECARD_PATH = REPO.parent / "analysis" / "recommendations" / "je-search-v2.json"
PARAMS_BASE_PATH = REPO.parent / "automation" / "state" / "params.json"
LOG_PATH = OUT_DIR / "grinder.log"

MAX_PARALLEL = 4
SEED_START = 20000
N_SEEDS = 400
WALL_CLOCK_LIMIT_SECONDS = 7200  # 2 hours

SEARCH_SPACE = {
    "strike_offset_bear":           [-1, 0, 1, 2],
    "min_triggers_bear":            [1, 2],
    "premium_stop_pct_bear":        [-0.10, -0.15, -0.20, -0.25, -0.30],
    "tp1_premium_pct":              [0.30, 0.50, 0.75, 1.00],
    "tp1_qty_fraction":             [0.33, 0.50, 0.67],
    "runner_target_premium_pct":    [1.5, 2.0, 3.0],
    "ribbon_spread_min_cents":      [10, 15, 20, 30],
    "f9_vol_mult":                  [0.4, 0.5, 0.6, 0.7],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

if sys.platform == "win32":
    _venv_pythonw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _venv_pythonw.exists():
        mp.set_executable(str(_venv_pythonw))


@dataclass(frozen=True)
class Candidate:
    seed: int


_BASE = None
_SPY = None
_VIX = None
_SPY_VAL = None
_VIX_VAL = None


def _worker_init(base_params, j_min, j_max, val_start, val_end):
    global _BASE, _SPY, _VIX, _SPY_VAL, _VIX_VAL
    _BASE = base_params
    _SPY, _VIX = runner.load_data(dt.date.fromisoformat(j_min), dt.date.fromisoformat(j_max))
    _SPY_VAL, _VIX_VAL = runner.load_data(
        dt.date.fromisoformat(val_start), dt.date.fromisoformat(val_end)
    )


def generate_params(seed: int, base: dict) -> dict:
    rng = random.Random(seed)
    p = dict(base)
    for knob, choices in SEARCH_SPACE.items():
        p[knob] = rng.choice(choices)
    p.pop("strike_offset_itm", None)
    return p


def _worker_eval(c: Candidate) -> dict:
    p = generate_params(c.seed, _BASE)
    try:
        edge = j_edge_tracker.score_candidate(p, _SPY, _VIX)
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
            "by_day": edge["by_day"],
            "validate_pnl": round(m_val.total_pnl, 2),
            "validate_sharpe": round(m_val.sharpe_daily, 3),
            "validate_n": m_val.n_trades,
            "validate_wr": round(m_val.win_rate, 4),
        }
    except Exception as exc:
        return {"seed": c.seed, "error": repr(exc)}


def _write_progress(out_dir: Path, completed: int, total: int, best_edge: float,
                    best_record: dict | None, started_at: float) -> None:
    prog = {
        "started_at": dt.datetime.fromtimestamp(started_at).isoformat(),
        "completed": completed,
        "total": total,
        "pct": round(100 * completed / total, 1),
        "best_edge_capture": round(best_edge, 2),
        "best_seed": best_record["seed"] if best_record else None,
        "wall_seconds": round(time.time() - started_at, 1),
        "status": "running" if completed < total else "completed",
    }
    tmp = out_dir / "progress.json.tmp"
    tmp.write_text(json.dumps(prog, indent=2))
    tmp.rename(out_dir / "progress.json")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results_path = OUT_DIR / "results.jsonl"
    if results_path.exists():
        results_path.unlink()

    base = json.loads(PARAMS_BASE_PATH.read_text(encoding="utf-8-sig"))
    j_min = min(t["date"] for t in j_edge_tracker.J_WINNERS + j_edge_tracker.J_LOSERS)
    j_max = max(t["date"] for t in j_edge_tracker.J_WINNERS + j_edge_tracker.J_LOSERS)

    logger.info("je_search_v2 starting: %d seeds, %d workers, WALL LIMIT %ds",
                N_SEEDS, MAX_PARALLEL, WALL_CLOCK_LIMIT_SECONDS)
    spy, vix = runner.load_data(dt.date.fromisoformat(j_min), dt.date.fromisoformat(j_max))
    base_edge = j_edge_tracker.score_candidate(base, spy, vix)
    logger.info("BASELINE: edge_capture=$%+.0f", base_edge["edge_capture"])

    jobs = [Candidate(seed=s) for s in range(SEED_START, SEED_START + N_SEEDS)]
    best_score = float("-inf")
    best_record = None
    completed = 0
    t0 = time.time()

    ctx = mp.get_context("spawn")
    with ctx.Pool(
        processes=MAX_PARALLEL,
        initializer=_worker_init,
        initargs=(base, j_min, j_max, "2026-02-14", "2026-05-07"),
        maxtasksperchild=20,
    ) as pool:
        for r in pool.imap_unordered(_worker_eval, jobs, chunksize=1):
            completed += 1
            with results_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(r) + "\n")
            if "error" not in r and r["edge_capture"] > best_score:
                best_score = r["edge_capture"]
                best_record = r
                logger.info("[%d/%d] NEW BEST seed=%d edge=$%+.0f pct=%.0f%%",
                            completed, N_SEEDS, r["seed"],
                            r["edge_capture"], r["winners_capture_pct"] * 100)
            if completed % 20 == 0:
                _write_progress(OUT_DIR, completed, N_SEEDS, best_score, best_record, t0)
                logger.info("[%d/%d] best_so_far=$%+.0f", completed, N_SEEDS, best_score)
            # Wall-clock kill switch
            if time.time() - t0 > WALL_CLOCK_LIMIT_SECONDS:
                logger.info("WALL CLOCK LIMIT hit at %d seeds. Stopping.", completed)
                pool.terminate()
                break

    elapsed = time.time() - t0
    _write_progress(OUT_DIR, completed, N_SEEDS, best_score, best_record, t0)
    logger.info("DONE in %.1f min. best_edge=$%+.0f", elapsed / 60, best_score)

    # Write scorecard
    EDGE_FLOOR = 771
    if best_record and best_score >= EDGE_FLOOR:
        final_params = dict(base)
        for k, v in best_record.get("params_diff", {}).items():
            final_params[k] = v
        scorecard = {
            "rule_id": "je-search-v2",
            "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "candidate_slug": "je_search_v2",
            "seeds_searched": completed,
            "winner_seed": best_record["seed"],
            "edge_capture": best_score,
            "winners_capture": best_record["winners_capture"],
            "losers_added": best_record["losers_added"],
            "validate_pnl": best_record.get("validate_pnl"),
            "validate_sharpe": best_record.get("validate_sharpe"),
            "by_day": best_record.get("by_day", []),
            "params_diff": best_record.get("params_diff", {}),
            "verdict": "PASS_EDGE_FLOOR — needs OOS walk-forward + real-fills",
            "op20_disclosures": [
                "1. ACCOUNT SIZE: BS-sim pricing, qty from params.json. Real-fills P&L will differ.",
                "2. SAMPLE BIAS: random search 400 seeds, wide knob space. Winner's curse applies.",
                "3. OUT-OF-SAMPLE: validate window 2026-02-14 to 2026-05-07 held out during search.",
                "4. REAL-FILLS: NOT YET RUN. BS-sim only. Must run simulator_real.py before ratification.",
                "5. FAILURE MODES: 5/01 gap is structural (ribbon data divergence). Wider ribbon may help.",
                "6. CONCENTRATION: not computed yet — run full backtest to get top5_pct.",
            ],
        }
        SCORECARD_PATH.write_text(json.dumps(scorecard, indent=2))
        logger.info("Scorecard written to %s", SCORECARD_PATH)
    else:
        logger.warning("Best edge_capture=$%.0f is below floor $%d. No scorecard written.", best_score, EDGE_FLOOR)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
