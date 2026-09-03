"""Candidate B — v14_enhanced 5/01 rescue sweep (real-fills, OP-16 J-edge scored).

WHY:
  v14_enhanced candidate_1 real-fills J-edge = $1,086 (PASS floor).
  The ONLY gap: 5/01 engine=$3 vs J=$470 (-99% capture).
  Root cause confirmed in v15-j-edge.json: ribbon data divergence on 13:30-13:55
  bar (engine sees BULL/MIXED, J's TV shows BEAR). Two potential fixes:
    (A) Tighten no_trade_before to catch earlier bear setups on 5/01
    (B) Relax ribbon_spread_min_cents so 5/01 mixed-spread bars qualify
    (C) Add min_triggers_bear=2 (confluence filter selects cleaner setups)
    (D) Change strike_offset_bear to OTM-1 (different delta profile on 5/01)

  This script sweeps a 4-axis grid on v14_enhanced base config with FULL
  REAL FILLS (OPRA) on the 16-month window. No BS sim.

GRID (108 combos = 3 x 4 x 3 x 3):
  no_trade_before:          [09:35, 09:45, 09:55]
  ribbon_spread_min_cents:  [10, 15, 20, 30]
  tp1_premium_pct:          [0.30, 0.50, 0.75]
  runner_target_premium_pct: [1.5, 2.0, 3.0]

Locked:
  strike_offset_bear = 0, min_triggers_bear = 1,
  premium_stop_pct_bear = -0.20, tp1_qty_fraction = 0.5

State dir: backtest/autoresearch/_state/v14e_501_rescue/
Scorecard: analysis/recommendations/v14e-501-rescue.json

COMPLETION CRITERIA:
  - All 108 combos evaluated (no wall-clock limit, ~30-60 min total).
  - Best candidate by OP-16 edge_capture, require edge_capture >= 1086 (must improve).
  - Writes progress.json every 10 combos.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import itertools
import json
import logging
import math
import multiprocessing as mp
import statistics
import sys
import time
from pathlib import Path
from typing import Iterator

# pythonw stdout redirect
if sys.platform == "win32":
    import os as _os
    if "pythonw" in _os.path.basename(sys.executable).lower():
        _log_dir = Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
        _log_dir.mkdir(parents=True, exist_ok=True)
        sys.stdout = open(_log_dir / "v14e_501_rescue.stdout.log", "a", buffering=1, encoding="utf-8")
        sys.stderr = open(_log_dir / "v14e_501_rescue.stderr.log", "a", buffering=1, encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner as _runner
from lib import simulator_real as _sim_real

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 15)  # Extended to include post-T30 OPRA coverage

OUT_DIR = Path(__file__).resolve().parent / "_state" / "v14e_501_rescue"
SCORECARD_PATH = Path(__file__).resolve().parents[2] / "analysis" / "recommendations" / "v14e-501-rescue.json"
PARAMS_BASE_PATH = Path(__file__).resolve().parents[2] / "automation" / "state" / "params.json"

MAX_PARALLEL = 4
PRIOR_BEST_EDGE = 1086  # Must improve over existing v14_enhanced result

# J anchor days — canonical per CLAUDE.md OP-16
J_WINNERS = {"2026-04-29": 342, "2026-05-01": 470, "2026-05-04": 730}
J_LOSERS  = {"2026-05-05": -260, "2026-05-06": -300, "2026-05-07": -165}

# Fixed base values (locked doctrine knobs)
LOCKED = {
    "strike_offset_bear": 0,
    "min_triggers_bear": 1,
    "premium_stop_pct_bear": -0.20,
    "tp1_qty_fraction": 0.5,
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.10,
}

# Grid to sweep
SWEEP = {
    "no_trade_before":          ["09:35", "09:45", "09:55"],
    "ribbon_spread_min_cents":  [10, 15, 20, 30],
    "tp1_premium_pct":          [0.30, 0.50, 0.75],
    "runner_target_premium_pct": [1.5, 2.0, 3.0],
}

if sys.platform == "win32":
    _venv_pythonw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _venv_pythonw.exists():
        mp.set_executable(str(_venv_pythonw))

# Module-level globals for worker pool
_BASE = None
_SPY = None
_VIX = None


def _worker_init(base_params):
    global _BASE, _SPY, _VIX
    _BASE = base_params
    _SPY, _VIX = _runner.load_data(WIDE_START, WIDE_END)


@contextlib.contextmanager
def _patch_sim_real(tp1_pct: float, runner_pct: float, tp1_qty: float) -> Iterator[None]:
    orig_tp1 = _sim_real.TP1_PREMIUM_PCT
    orig_run = _sim_real.RUNNER_MAX_PREMIUM_PCT
    orig_qty = _sim_real.TP1_QTY_FRACTION
    try:
        _sim_real.TP1_PREMIUM_PCT = tp1_pct
        _sim_real.RUNNER_MAX_PREMIUM_PCT = runner_pct
        _sim_real.TP1_QTY_FRACTION = tp1_qty
        yield
    finally:
        _sim_real.TP1_PREMIUM_PCT = orig_tp1
        _sim_real.RUNNER_MAX_PREMIUM_PCT = orig_run
        _sim_real.TP1_QTY_FRACTION = orig_qty


def _eval_combo(combo: dict) -> dict:
    """Evaluate one combo with real fills. Returns per-day P&L + metrics."""
    params = dict(_BASE)
    params.update(LOCKED)
    params.update(combo)

    try:
        with _patch_sim_real(combo["tp1_premium_pct"],
                             combo["runner_target_premium_pct"],
                             LOCKED["tp1_qty_fraction"]):
            result, m = _runner.run_backtest(
                params, WIDE_START, WIDE_END, _SPY, _VIX,
                use_real_fills=True
            )
    except Exception as exc:
        return {"combo": combo, "error": repr(exc)}

    # Per-day P&L for J anchors
    per_day: dict[str, float] = {}
    for t in result.trades:
        d_str = t.entry_time_et.date().isoformat()
        per_day[d_str] = per_day.get(d_str, 0.0) + t.dollar_pnl

    # OP-16 edge_capture
    w_capture = sum(per_day.get(d, 0.0) for d in J_WINNERS)
    l_added = sum(max(0.0, -per_day.get(d, 0.0)) for d in J_LOSERS)
    edge_capture = w_capture - l_added

    # Quarter P&L for sub-window stability
    q_pnl: dict[str, float] = {}
    for t in result.trades:
        q = f"{t.entry_time_et.year}-Q{(t.entry_time_et.month - 1) // 3 + 1}"
        q_pnl[q] = q_pnl.get(q, 0.0) + t.dollar_pnl
    positive_q = sum(1 for v in q_pnl.values() if v > 0)

    # Approx daily sharpe from per-day P&L
    daily_pnls = list(per_day.values())
    if len(daily_pnls) > 1:
        avg = sum(daily_pnls) / len(daily_pnls)
        std = statistics.stdev(daily_pnls)
        daily_sharpe = avg / std if std else 0.0
        ann_sharpe = daily_sharpe * math.sqrt(252)
    else:
        ann_sharpe = 0.0

    # Top5 concentration
    if len(daily_pnls) >= 5:
        top5 = sum(sorted(daily_pnls, reverse=True)[:5])
        top5_pct = top5 / m.total_pnl if m.total_pnl > 0 else 1.0
    else:
        top5_pct = 1.0

    # J anchor detail
    j_detail = {
        d: {"engine_pnl": round(per_day.get(d, 0.0), 2), "j_pnl": j}
        for d, j in {**J_WINNERS, **J_LOSERS}.items()
    }

    return {
        "combo": combo,
        "edge_capture": round(edge_capture, 2),
        "w_capture": round(w_capture, 2),
        "l_added": round(l_added, 2),
        "j_detail": j_detail,
        "wide_pnl": round(m.total_pnl, 2),
        "wide_n_trades": m.n_trades,
        "wide_wr": round(m.win_rate, 4),
        "ann_sharpe": round(ann_sharpe, 3),
        "positive_quarters": positive_q,
        "quarter_pnl": {k: round(v, 2) for k, v in q_pnl.items()},
        "top5_pct": round(top5_pct, 3),
        "max_drawdown": round(m.max_drawdown, 2),
        "bs_fallback_count": sum(1 for t in result.trades if "BS_FALLBACK" in getattr(t, "setup", "")),
    }


def _write_progress(completed: int, total: int, best_edge: float, t0: float) -> None:
    prog = {
        "completed": completed, "total": total,
        "pct": round(100 * completed / total, 1),
        "best_edge_capture": round(best_edge, 2),
        "wall_seconds": round(time.time() - t0, 1),
        "status": "running" if completed < total else "completed",
    }
    tmp = OUT_DIR / "progress.json.tmp"
    tmp.write_text(json.dumps(prog, indent=2))
    tmp.rename(OUT_DIR / "progress.json")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results_path = OUT_DIR / "results.jsonl"
    if results_path.exists():
        results_path.unlink()

    base = json.loads(PARAMS_BASE_PATH.read_text(encoding="utf-8-sig"))

    # Build combo list
    keys = list(SWEEP.keys())
    values = list(SWEEP.values())
    combos = [dict(zip(keys, vals)) for vals in itertools.product(*values)]
    log.info("v14e_501_rescue: %d combos, %d workers", len(combos), MAX_PARALLEL)

    best_edge = float("-inf")
    best_result = None
    completed = 0
    t0 = time.time()

    ctx = mp.get_context("spawn")
    with ctx.Pool(
        processes=MAX_PARALLEL,
        initializer=_worker_init,
        initargs=(base,),
        maxtasksperchild=10,
    ) as pool:
        for r in pool.imap_unordered(_eval_combo, combos, chunksize=1):
            completed += 1
            with results_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(r) + "\n")
            if "error" in r:
                log.warning("COMBO ERROR: %s", r["error"])
                continue
            if r["edge_capture"] > best_edge:
                best_edge = r["edge_capture"]
                best_result = r
                log.info("[%d/%d] NEW BEST edge=$%+.0f combo=%s",
                         completed, len(combos), best_edge, r["combo"])
            if completed % 10 == 0:
                _write_progress(completed, len(combos), best_edge, t0)
                log.info("[%d/%d] best_edge=$%+.0f", completed, len(combos), best_edge)

    _write_progress(completed, len(combos), best_edge, t0)
    elapsed = time.time() - t0
    log.info("DONE in %.1f min. best_edge=$%+.0f (prior best=$%+.0f)",
             elapsed / 60, best_edge, PRIOR_BEST_EDGE)

    # Write scorecard if improvement
    if best_result and best_edge >= PRIOR_BEST_EDGE:
        sc = {
            "rule_id": "v14e-501-rescue",
            "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "prior_best_edge": PRIOR_BEST_EDGE,
            "best_edge_capture": round(best_edge, 2),
            "delta_edge": round(best_edge - PRIOR_BEST_EDGE, 2),
            "combo": best_result["combo"],
            "j_detail": best_result["j_detail"],
            "wide_pnl": best_result["wide_pnl"],
            "wide_wr": best_result["wide_wr"],
            "ann_sharpe": best_result["ann_sharpe"],
            "positive_quarters": best_result["positive_quarters"],
            "quarter_pnl": best_result["quarter_pnl"],
            "top5_pct": best_result["top5_pct"],
            "max_drawdown": best_result["max_drawdown"],
            "verdict": "IMPROVED — needs walk-forward + real-fills OOS confirmation",
            "op20_disclosures": [
                "1. ACCOUNT SIZE: Uses qty from base params.json. P&L scales with qty.",
                "2. SAMPLE BIAS: 108-combo grid sweep from a 4-axis neighborhood of v14_enhanced.",
                "3. OUT-OF-SAMPLE: No held-out window. Walk-forward required before ratification.",
                "4. REAL-FILLS: YES — all trades use OPRA 5-min bars (BS-sim fallback logged).",
                "5. FAILURE MODES: 5/01 miss may remain structural (ribbon data divergence).",
                "6. CONCENTRATION: top5_pct=" + str(round(best_result.get("top5_pct", 1.0), 3)),
            ],
        }
        SCORECARD_PATH.write_text(json.dumps(sc, indent=2))
        log.info("Scorecard written to %s", SCORECARD_PATH)
    else:
        log.warning("best_edge=$%.0f did not improve over prior best $%.0f. No scorecard.", best_edge, PRIOR_BEST_EDGE)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
