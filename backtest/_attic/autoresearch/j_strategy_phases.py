"""J-strategy backtest, all 4 phases in ONE process. SILENT.

CLAUDE.md operating principle 16: optimize edge_capture (encode J's edge),
NOT aggregate sharpe. Bear-only setups. No drift.

Single-process design:
  - One pythonw.exe parent (no console).
  - multiprocessing.Pool inherits pythonw -- NO console flashes.
  - All phases run sequentially in main(). No subprocess.Popen of new pythons.
  - All logging to file (stdout/stderr captured by cmd /B redirection).

PHASE 0: random search (N seeds, 4 workers, score = edge_capture)
PHASE 1: aggregate + rank top candidates by edge_capture
PHASE 2: hill-climb the top 4 candidates (refine within knob neighborhood)
PHASE 3: sub-window stability test on top 8 (across 5 historical quarters)
PHASE 4: synthesize -> analysis/recommendations/v15-j-edge.json

Run via:
    pythonw.exe -m autoresearch.j_strategy_phases > logfile 2>&1
or via the cmd launcher: setup\run-j-strategy.cmd
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import multiprocessing as mp
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Force pythonw.exe for ALL multiprocessing workers so they inherit no-console.
# Done at module import so worker processes also pick it up.
if sys.platform == "win32":
    _venv_pythonw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _venv_pythonw.exists():
        mp.set_executable(str(_venv_pythonw))

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner, j_edge_tracker

OUT_DIR = REPO / "autoresearch" / "_state" / "j_strategy"
SCORECARD_PATH = REPO.parent / "analysis" / "recommendations" / "v15-j-edge.json"
PROGRESS_PATH = OUT_DIR / "progress.json"
PARAMS_BASE_PATH = REPO.parent / "automation" / "state" / "params.json"
NOTIFY_HELPER = REPO.parent / "setup" / "scripts" / "gamma-notify.ps1"

MAX_PARALLEL = 4

# Knob space focused tightly on J's bear setup (CLAUDE.md operating principle 16).
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

# Sub-window quarters for PHASE 3.
SUB_WINDOWS = [
    ("2025-Q1", "2025-01-01", "2025-03-31"),
    ("2025-Q2", "2025-04-01", "2025-06-30"),
    ("2025-Q3", "2025-07-01", "2025-09-30"),
    ("2025-Q4", "2025-10-01", "2025-12-31"),
    ("2026-VAL", "2026-02-14", "2026-05-07"),
]


# Set up logging to file
def _setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(fh)
    return root


logger = logging.getLogger(__name__)


def _write_progress(payload: dict) -> None:
    """Atomic write of progress JSON for monitoring."""
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PROGRESS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(PROGRESS_PATH)


def _notify_discord(message: str) -> None:
    """Append to discord-outbox via gamma-notify (best-effort, silent on fail)."""
    try:
        import subprocess
        # Use CREATE_NO_WINDOW (0x08000000) so the powershell helper doesn't flash.
        creationflags = 0x08000000 if sys.platform == "win32" else 0
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
             "-File", str(NOTIFY_HELPER), "-Message", message],
            creationflags=creationflags,
            timeout=10, check=False,
        )
    except Exception:
        pass  # notification failure is non-fatal


# ============================================================================
# PHASE 0: random search
# ============================================================================

@dataclass(frozen=True)
class P0Job:
    seed: int


_P0_BASE = None
_P0_SPY = None
_P0_VIX = None
_P0_SPY_VAL = None
_P0_VIX_VAL = None


def _p0_init(base_params_json: str, j_min: str, j_max: str, val_start: str, val_end: str) -> None:
    global _P0_BASE, _P0_SPY, _P0_VIX, _P0_SPY_VAL, _P0_VIX_VAL
    _P0_BASE = json.loads(base_params_json)
    _P0_SPY, _P0_VIX = runner.load_data(dt.date.fromisoformat(j_min), dt.date.fromisoformat(j_max))
    _P0_SPY_VAL, _P0_VIX_VAL = runner.load_data(dt.date.fromisoformat(val_start), dt.date.fromisoformat(val_end))


def _p0_generate_params(seed: int, base: dict) -> dict:
    rng = random.Random(seed)
    p = dict(base)
    for knob, choices in SEARCH_SPACE.items():
        p[knob] = rng.choice(choices)
    p.pop("strike_offset_itm", None)
    return p


def _p0_eval(job: P0Job) -> dict:
    p = _p0_generate_params(job.seed, _P0_BASE)
    try:
        edge = j_edge_tracker.score_candidate(p, _P0_SPY, _P0_VIX)
        val_start = dt.date.fromisoformat("2026-02-14")
        val_end = dt.date.fromisoformat("2026-05-07")
        _, m_val = runner.run_with_params(p, val_start, val_end, _P0_SPY_VAL, _P0_VIX_VAL)
        return {
            "seed": job.seed,
            "params_diff": {k: p[k] for k in SEARCH_SPACE if p[k] != _P0_BASE.get(k)},
            "params": {k: p[k] for k in SEARCH_SPACE},
            "edge_capture": edge["edge_capture"],
            "winners_capture": edge["winners_capture"],
            "winners_capture_pct": edge["winners_capture_pct"],
            "losers_added": edge["losers_added"],
            "validate_pnl": round(m_val.total_pnl, 2),
            "validate_sharpe": round(m_val.sharpe_daily, 3),
            "validate_n": m_val.n_trades,
        }
    except Exception as exc:  # noqa: BLE001
        return {"seed": job.seed, "error": repr(exc)}


def run_phase0(n_seeds: int, base: dict, workers: int = MAX_PARALLEL) -> list[dict]:
    j_min = min(t["date"] for t in j_edge_tracker.J_WINNERS + j_edge_tracker.J_LOSERS)
    j_max = max(t["date"] for t in j_edge_tracker.J_WINNERS + j_edge_tracker.J_LOSERS)
    val_start = "2026-02-14"
    val_end = "2026-05-07"
    base_json = json.dumps(base)

    jobs = [P0Job(seed=s) for s in range(10000, 10000 + n_seeds)]
    p0_results_path = OUT_DIR / "p0_results.jsonl"
    p0_results_path.parent.mkdir(parents=True, exist_ok=True)
    if p0_results_path.exists():
        p0_results_path.unlink()

    results = []
    best_score = -float("inf")
    completed = 0
    t0 = time.time()

    if workers <= 1:
        # SERIAL MODE -- single process, no Pool, no spawned workers, no window flashes.
        _p0_init(base_json, j_min, j_max, val_start, val_end)
        for job in jobs:
            r = _p0_eval(job)
            completed += 1
            with p0_results_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(r) + "\n")
            results.append(r)
            if "error" not in r and r["edge_capture"] > best_score:
                best_score = r["edge_capture"]
                logger.info("[P0 %3d/%d] seed=%d edge=$%+.0f cap=%.0f%% loss_add=$%.0f val=$%+.0f *** NEW BEST ***",
                            completed, len(jobs), r["seed"], r["edge_capture"],
                            r["winners_capture_pct"] * 100, r["losers_added"], r["validate_pnl"])
            elif completed % 10 == 0:
                logger.info("[P0 %3d/%d] best so far: $%+.0f (%.1f min elapsed)",
                            completed, len(jobs), best_score, (time.time() - t0) / 60)
            _write_progress({
                "phase": "P0", "completed": completed, "total": len(jobs),
                "best_edge_capture": best_score,
                "elapsed_minutes": round((time.time() - t0) / 60, 1),
            })
    else:
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=workers, initializer=_p0_init,
                      initargs=(base_json, j_min, j_max, val_start, val_end)) as pool:
            for r in pool.imap_unordered(_p0_eval, jobs, chunksize=1):
                completed += 1
                with p0_results_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(r) + "\n")
                results.append(r)
                if "error" not in r and r["edge_capture"] > best_score:
                    best_score = r["edge_capture"]
                    logger.info("[P0 %3d/%d] seed=%d edge=$%+.0f cap=%.0f%% loss_add=$%.0f val=$%+.0f *** NEW BEST ***",
                                completed, len(jobs), r["seed"], r["edge_capture"],
                                r["winners_capture_pct"] * 100, r["losers_added"], r["validate_pnl"])
                elif completed % 25 == 0:
                    logger.info("[P0 %3d/%d] best so far: $%+.0f", completed, len(jobs), best_score)
                _write_progress({
                    "phase": "P0", "completed": completed, "total": len(jobs),
                    "best_edge_capture": best_score,
                    "elapsed_minutes": round((time.time() - t0) / 60, 1),
                })

    elapsed = time.time() - t0
    logger.info("PHASE 0 done: %d candidates in %.1f min, best=$%+.0f", completed, elapsed/60, best_score)
    return results


# ============================================================================
# PHASE 1: aggregate + rank
# ============================================================================

def run_phase1(p0_results: list[dict]) -> list[dict]:
    valid = [r for r in p0_results if "error" not in r]
    valid.sort(key=lambda r: (r["edge_capture"], r["validate_pnl"]), reverse=True)
    n_pos_edge = sum(1 for r in valid if r["edge_capture"] > 0)
    n_skipped_losers = sum(1 for r in valid if r["losers_added"] == 0)
    logger.info("PHASE 1: %d candidates, %d with positive edge_capture, %d perfectly skipped J's losers",
                len(valid), n_pos_edge, n_skipped_losers)
    summary = {
        "phase": "P1",
        "n_candidates": len(valid),
        "n_positive_edge": n_pos_edge,
        "n_skipped_all_losers": n_skipped_losers,
        "top_20": valid[:20],
    }
    (OUT_DIR / "p1_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return valid


# ============================================================================
# PHASE 2: hill-climb top candidates (each starts from a seed's params)
# ============================================================================

@dataclass(frozen=True)
class P2Job:
    base_seed: int
    proposal_id: int
    params: dict


_P2_BASE = None
_P2_SPY = None
_P2_VIX = None
_P2_SPY_VAL = None
_P2_VIX_VAL = None


def _p2_init(base_params_json: str, j_min: str, j_max: str, val_start: str, val_end: str) -> None:
    global _P2_BASE, _P2_SPY, _P2_VIX, _P2_SPY_VAL, _P2_VIX_VAL
    _P2_BASE = json.loads(base_params_json)
    _P2_SPY, _P2_VIX = runner.load_data(dt.date.fromisoformat(j_min), dt.date.fromisoformat(j_max))
    _P2_SPY_VAL, _P2_VIX_VAL = runner.load_data(dt.date.fromisoformat(val_start), dt.date.fromisoformat(val_end))


def _p2_eval(job: P2Job) -> dict:
    try:
        edge = j_edge_tracker.score_candidate(job.params, _P2_SPY, _P2_VIX)
        val_start = dt.date.fromisoformat("2026-02-14")
        val_end = dt.date.fromisoformat("2026-05-07")
        _, m_val = runner.run_with_params(job.params, val_start, val_end, _P2_SPY_VAL, _P2_VIX_VAL)
        return {
            "base_seed": job.base_seed, "proposal_id": job.proposal_id,
            "params_diff": {k: job.params[k] for k in SEARCH_SPACE if job.params[k] != _P2_BASE.get(k)},
            "edge_capture": edge["edge_capture"],
            "validate_pnl": round(m_val.total_pnl, 2),
            "validate_sharpe": round(m_val.sharpe_daily, 3),
        }
    except Exception as exc:  # noqa: BLE001
        return {"base_seed": job.base_seed, "proposal_id": job.proposal_id, "error": repr(exc)}


def _p2_neighborhood_proposals(start_params: dict, base_params: dict, k: int, rng: random.Random) -> list[dict]:
    """Single-knob neighbor changes around start_params."""
    proposals = []
    for _ in range(k):
        knob = rng.choice(list(SEARCH_SPACE.keys()))
        choices = list(SEARCH_SPACE[knob])
        cur = start_params.get(knob)
        alts = [v for v in choices if v != cur]
        if not alts:
            continue
        new_val = rng.choice(alts)
        p = dict(start_params)
        p[knob] = new_val
        proposals.append(p)
    return proposals


def run_phase2(top_seeds: list[dict], base: dict, iterations: int = 12, k_per_iter: int = 6, workers: int = MAX_PARALLEL) -> list[dict]:
    j_min = min(t["date"] for t in j_edge_tracker.J_WINNERS + j_edge_tracker.J_LOSERS)
    j_max = max(t["date"] for t in j_edge_tracker.J_WINNERS + j_edge_tracker.J_LOSERS)
    val_start = "2026-02-14"
    val_end = "2026-05-07"
    base_json = json.dumps(base)

    refined = []
    rng = random.Random(2026)

    if workers <= 1:
        # Init globals once for serial mode
        _p2_init(base_json, j_min, j_max, val_start, val_end)

    for top in top_seeds:
        seed = top["seed"]
        cur_params = dict(base)
        for k, v in top["params_diff"].items():
            cur_params[k] = v
        cur_params.pop("strike_offset_itm", None)
        cur_score = top["edge_capture"]
        kept = 0

        logger.info("[P2 seed=%d] starting climb from edge=$%+.0f", seed, cur_score)

        for it in range(1, iterations + 1):
            proposals = _p2_neighborhood_proposals(cur_params, base, k_per_iter, rng)
            jobs = [P2Job(base_seed=seed, proposal_id=i, params=p) for i, p in enumerate(proposals)]
            if workers <= 1:
                results = [_p2_eval(j) for j in jobs]
            else:
                ctx = mp.get_context("spawn")
                with ctx.Pool(processes=workers, initializer=_p2_init,
                              initargs=(base_json, j_min, j_max, val_start, val_end)) as pool:
                    results = list(pool.imap_unordered(_p2_eval, jobs, chunksize=1))

            best_r = None
            best_s = cur_score
            for r in results:
                if "error" in r:
                    continue
                if r["edge_capture"] > best_s:
                    best_s = r["edge_capture"]
                    best_r = r
            if best_r is not None:
                # apply diff to current
                for k, v in best_r["params_diff"].items():
                    cur_params[k] = v
                kept += 1
                cur_score = best_s
                logger.info("[P2 seed=%d iter=%d] KEEP edge=$%+.0f", seed, it, cur_score)
            _write_progress({"phase": "P2", "current_seed": seed, "iter": it, "kept": kept, "score": cur_score})

        refined.append({
            "starting_seed": seed,
            "starting_edge": top["edge_capture"],
            "refined_edge": cur_score,
            "improvement": cur_score - top["edge_capture"],
            "iterations": iterations,
            "kept": kept,
            "refined_params": cur_params,
        })
        logger.info("[P2 seed=%d] DONE -- starting=$%+.0f refined=$%+.0f kept=%d/%d",
                    seed, top["edge_capture"], cur_score, kept, iterations)

    (OUT_DIR / "p2_refined.json").write_text(json.dumps(refined, indent=2), encoding="utf-8")
    refined.sort(key=lambda r: r["refined_edge"], reverse=True)
    return refined


# ============================================================================
# PHASE 3: sub-window stability
# ============================================================================

@dataclass(frozen=True)
class P3Job:
    candidate_id: str
    params: dict
    label: str
    start_iso: str
    end_iso: str


_P3_SPY = None
_P3_VIX = None


def _p3_init() -> None:
    global _P3_SPY, _P3_VIX
    _P3_SPY, _P3_VIX = runner.load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 7))


def _p3_eval(job: P3Job) -> dict:
    s = dt.date.fromisoformat(job.start_iso)
    e = dt.date.fromisoformat(job.end_iso)
    try:
        _, m = runner.run_with_params(job.params, s, e, _P3_SPY, _P3_VIX)
        return {
            "candidate_id": job.candidate_id, "label": job.label,
            "n_trades": m.n_trades, "total_pnl": round(m.total_pnl, 2),
            "sharpe": round(m.sharpe_daily, 3), "win_rate": round(m.win_rate, 4),
        }
    except Exception as exc:  # noqa: BLE001
        return {"candidate_id": job.candidate_id, "label": job.label, "error": repr(exc)}


def run_phase3(refined: list[dict], workers: int = MAX_PARALLEL) -> list[dict]:
    """Test top N refined candidates across 5 historical quarters."""
    top = refined[:8]  # top 8
    jobs = []
    for r in top:
        cid = f"seed{r['starting_seed']}"
        for label, s, e in SUB_WINDOWS:
            jobs.append(P3Job(candidate_id=cid, params=r["refined_params"], label=label, start_iso=s, end_iso=e))

    results_by_candidate: dict[str, list[dict]] = {}
    if workers <= 1:
        _p3_init()
        for job in jobs:
            r = _p3_eval(job)
            results_by_candidate.setdefault(r["candidate_id"], []).append(r)
            logger.info("[P3 %s %s] pnl=$%+.0f sh=%+.2f n=%d",
                        r["candidate_id"], r["label"], r.get("total_pnl", 0), r.get("sharpe", 0), r.get("n_trades", 0))
    else:
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=workers, initializer=_p3_init) as pool:
            for r in pool.imap_unordered(_p3_eval, jobs, chunksize=1):
                results_by_candidate.setdefault(r["candidate_id"], []).append(r)
                logger.info("[P3 %s %s] pnl=$%+.0f sh=%+.2f n=%d",
                            r["candidate_id"], r["label"], r.get("total_pnl", 0), r.get("sharpe", 0), r.get("n_trades", 0))

    stability = []
    for cid, windows in results_by_candidate.items():
        valid = [w for w in windows if "error" not in w]
        n_pos = sum(1 for w in valid if w["total_pnl"] > 0)
        is_robust = n_pos >= 3
        stability.append({
            "candidate_id": cid, "n_windows": len(valid), "n_positive": n_pos,
            "is_robust": is_robust, "windows": windows,
        })
    (OUT_DIR / "p3_stability.json").write_text(json.dumps(stability, indent=2), encoding="utf-8")
    return stability


# ============================================================================
# PHASE 4: synthesize
# ============================================================================

def run_phase4(refined: list[dict], stability: list[dict], base: dict) -> dict:
    stab_by_id = {s["candidate_id"]: s for s in stability}
    pool = []
    for r in refined:
        cid = f"seed{r['starting_seed']}"
        st = stab_by_id.get(cid, {})
        pool.append({
            "starting_seed": r["starting_seed"],
            "refined_edge": r["refined_edge"],
            "is_robust": st.get("is_robust", False),
            "sub_window_pos": st.get("n_positive", 0),
            "refined_params": r["refined_params"],
        })

    # Winner = highest edge_capture among ROBUST candidates
    robust = [c for c in pool if c["is_robust"] and c["refined_edge"] > 0]
    if robust:
        winner = max(robust, key=lambda c: c["refined_edge"])
        verdict = "candidate_proposed_robust"
    else:
        # Fall back to best edge if nothing robust
        candidates = [c for c in pool if c["refined_edge"] > 0]
        if candidates:
            winner = max(candidates, key=lambda c: c["refined_edge"])
            verdict = "candidate_proposed_nonrobust"
        else:
            winner = None
            verdict = "no_improvement_keep_v14"

    baseline_score = j_edge_tracker.J_TOTAL_WINNERS  # max possible
    base_edge_path = OUT_DIR / "p0_results.jsonl"
    scorecard = {
        "rule_id": "v15-j-edge",
        "method": "j_strategy_phases (CLAUDE.md operating principle 16)",
        "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "verdict": verdict,
        "max_possible_edge": baseline_score,
        "winner": winner,
        "candidate_pool_size": len(pool),
        "n_robust_candidates": sum(1 for c in pool if c["is_robust"]),
    }
    SCORECARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCORECARD_PATH.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    return scorecard


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-seeds", type=int, default=200)
    ap.add_argument("--top-for-climb", type=int, default=4)
    ap.add_argument("--climb-iterations", type=int, default=12)
    ap.add_argument("--workers", type=int, default=MAX_PARALLEL)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUT_DIR / "phases.log"
    _setup_logging(log_path)

    logger.info("=" * 80)
    logger.info("J-STRATEGY PHASES — silent run (pythonw, single process)")
    logger.info("=" * 80)
    logger.info("PID: %d", __import__("os").getpid())

    base = json.loads(PARAMS_BASE_PATH.read_text(encoding="utf-8-sig"))
    t_overall = time.time()

    _notify_discord(
        f"🤖 **J-strategy phases launched (silent, single process)**\n"
        f"- {args.n_seeds} P0 seeds → top {args.top_for_climb} climbed → top 8 sub-window → synth\n"
        f"- ETA ~2 hr\n"
        f"- log: `backtest/autoresearch/_state/j_strategy/phases.log`"
    )

    # PHASE 0
    logger.info(">>> PHASE 0: random search (%d seeds)", args.n_seeds)
    p0 = run_phase0(args.n_seeds, base, workers=args.workers)
    p0_t = (time.time() - t_overall) / 60
    _notify_discord(f"✅ PHASE 0 done in {p0_t:.0f} min — {len(p0)} candidates evaluated")

    # PHASE 1
    logger.info(">>> PHASE 1: aggregate + rank")
    ranked = run_phase1(p0)
    if not ranked:
        logger.error("No valid candidates from P0 — aborting")
        _notify_discord("❌ PHASE 1: no valid candidates from P0. Aborting.")
        return 1
    top = ranked[:args.top_for_climb]
    _notify_discord(
        f"✅ PHASE 1 done — top {len(top)} for climb: " +
        ", ".join(f"seed {t['seed']} (${t['edge_capture']:+.0f})" for t in top)
    )

    # PHASE 2
    logger.info(">>> PHASE 2: hill-climb top %d", len(top))
    refined = run_phase2(top, base, iterations=args.climb_iterations, workers=args.workers)
    p2_t = (time.time() - t_overall) / 60
    best_after = max(refined, key=lambda r: r["refined_edge"])
    _notify_discord(
        f"✅ PHASE 2 done in {p2_t:.0f} min — best after climb: seed {best_after['starting_seed']} "
        f"= ${best_after['refined_edge']:+.0f}"
    )

    # PHASE 3
    logger.info(">>> PHASE 3: sub-window stability")
    stability = run_phase3(refined, workers=args.workers)
    n_robust = sum(1 for s in stability if s["is_robust"])
    _notify_discord(f"✅ PHASE 3 done — {n_robust}/{len(stability)} candidates ROBUST across 5 quarters")

    # PHASE 4
    logger.info(">>> PHASE 4: synthesize")
    scorecard = run_phase4(refined, stability, base)
    total_t = (time.time() - t_overall) / 60
    if scorecard["winner"]:
        w = scorecard["winner"]
        _notify_discord(
            f"📊 **J-strategy phases COMPLETE in {total_t:.0f} min**\n"
            f"- verdict: `{scorecard['verdict']}`\n"
            f"- winner: seed **{w['starting_seed']}**\n"
            f"- refined edge: **${w['refined_edge']:+.0f}** of max ${scorecard['max_possible_edge']}\n"
            f"- robust: {w['is_robust']} ({w['sub_window_pos']}/5 quarters positive)\n"
            f"- file: `analysis/recommendations/v15-j-edge.json`"
        )
    else:
        _notify_discord(
            f"⚠️ **J-strategy phases done in {total_t:.0f} min** — no candidate beat baseline. Stay v14."
        )

    logger.info("DONE in %.1f min", total_t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
