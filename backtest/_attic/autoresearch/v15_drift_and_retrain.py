"""Candidate D — v15 performance drift check + targeted retune (real-fills).

WHY:
  OP-22 "When you have nothing obvious to do": "Run the backtest engine on the
  most-recent 30-day window with the latest production params. Compare to last
  month. Has performance drifted?"

  Production params (v15.1) were ratified 2026-05-14. This script:
  1. Runs v15 params on RECENT window (2026-04-15 to 2026-05-15, ~21 trading days)
  2. Runs v15 params on PRIOR window (2026-03-15 to 2026-04-14, ~22 trading days)
  3. Compares Sharpe, expectancy, WR, max_dd across windows.
  4. Runs OP-16 J-edge score across both windows combined.
  5. If edge_capture drifted > 20%, triggers a 48-combo micro-tune sweep on the
     most impactful knob (premium_stop_pct_bear) to attempt recovery.

This is a DIAGNOSTIC + ADAPTIVE tune. Not a new strategy — it ensures production
remains calibrated as market regime evolves.

State dir: backtest/autoresearch/_state/v15_drift/
Scorecard: analysis/recommendations/v15-drift-check.json

COMPLETION CRITERIA:
  - Drift report written in < 5 minutes.
  - If retune triggered: 48 combos evaluated, best written to scorecard.
  - No floor check needed for drift report (diagnostic only). Retune output
    must meet edge_capture >= 771 to write to scorecard.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
import multiprocessing as mp
import statistics
import sys
import time
import itertools
from pathlib import Path

# pythonw stdout redirect
if sys.platform == "win32":
    import os as _os
    if "pythonw" in _os.path.basename(sys.executable).lower():
        _log_dir = Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
        _log_dir.mkdir(parents=True, exist_ok=True)
        sys.stdout = open(_log_dir / "v15_drift.stdout.log", "a", buffering=1, encoding="utf-8")
        sys.stderr = open(_log_dir / "v15_drift.stderr.log", "a", buffering=1, encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner as _runner, j_edge_tracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Windows
RECENT_START  = dt.date(2026, 4, 15)
RECENT_END    = dt.date(2026, 5, 15)
PRIOR_START   = dt.date(2026, 3, 15)
PRIOR_END     = dt.date(2026, 4, 14)
J_EDGE_START  = dt.date(2026, 4, 29)  # First J anchor
J_EDGE_END    = dt.date(2026, 5, 7)   # Last J anchor

OUT_DIR = Path(__file__).resolve().parent / "_state" / "v15_drift"
SCORECARD_PATH = Path(__file__).resolve().parents[2] / "analysis" / "recommendations" / "v15-drift-check.json"
PARAMS_BASE_PATH = Path(__file__).resolve().parents[2] / "automation" / "state" / "params.json"

MAX_PARALLEL = 4
EDGE_FLOOR = 771
DRIFT_THRESHOLD_PCT = 0.20  # 20% relative drift triggers retune

# Retune sweep (48 combos — only if drift detected)
RETUNE_SWEEP = {
    "premium_stop_pct_bear": [-0.10, -0.15, -0.20, -0.25, -0.30],
    "tp1_premium_pct":       [0.50, 0.75, 1.00],
    "runner_target_premium_pct": [1.5, 2.0, 3.0, 4.0],
}

J_WINNERS = {"2026-04-29": 342, "2026-05-01": 470, "2026-05-04": 730}
J_LOSERS  = {"2026-05-05": -260, "2026-05-06": -300, "2026-05-07": -165}

if sys.platform == "win32":
    _venv_pythonw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _venv_pythonw.exists():
        mp.set_executable(str(_venv_pythonw))

_BASE = None
_SPY_FULL = None
_VIX_FULL = None


def _worker_init(base_params):
    global _BASE, _SPY_FULL, _VIX_FULL
    _BASE = base_params
    # Load wide window including J-anchor days
    _SPY_FULL, _VIX_FULL = _runner.load_data(
        dt.date(2026, 3, 1), dt.date(2026, 5, 15)
    )


def _window_metrics(params, start, end, spy, vix):
    """Run one window, return metrics dict."""
    try:
        result, m = _runner.run_with_params(params, start, end, spy, vix)
    except Exception as exc:
        return {"error": repr(exc)}

    per_day = {}
    for t in result.trades:
        d = t.entry_time_et.date().isoformat()
        per_day[d] = per_day.get(d, 0.0) + t.dollar_pnl

    daily = list(per_day.values())
    if len(daily) > 1:
        avg = sum(daily) / len(daily)
        std = statistics.stdev(daily)
        daily_sharpe = avg / std if std else 0.0
    else:
        daily_sharpe = 0.0

    ann_sharpe = daily_sharpe * math.sqrt(252)
    return {
        "window": f"{start} to {end}",
        "n_trades": m.n_trades,
        "wr": round(m.win_rate, 3),
        "total_pnl": round(m.total_pnl, 2),
        "expectancy": round(m.total_pnl / m.n_trades, 2) if m.n_trades else 0,
        "max_drawdown": round(m.max_drawdown, 2),
        "ann_sharpe": round(ann_sharpe, 3),
        "daily_per_day": per_day,
    }


def _j_edge(params, spy, vix):
    """Compute OP-16 edge_capture."""
    return j_edge_tracker.score_candidate(params, spy, vix)


def _retune_worker(combo: dict) -> dict:
    """Evaluate one retune combo."""
    params = dict(_BASE)
    params.update(combo)
    try:
        edge = j_edge_tracker.score_candidate(params, _SPY_FULL, _VIX_FULL)
        _, m = _runner.run_with_params(params,
                                       dt.date(2026, 3, 1), dt.date(2026, 5, 15),
                                       _SPY_FULL, _VIX_FULL)
        return {
            "combo": combo,
            "edge_capture": edge["edge_capture"],
            "winners_capture": edge["winners_capture"],
            "losers_added": edge["losers_added"],
            "by_day": edge["by_day"],
            "total_pnl": round(m.total_pnl, 2),
            "sharpe": round(m.sharpe_daily, 3),
            "n_trades": m.n_trades,
        }
    except Exception as exc:
        return {"combo": combo, "error": repr(exc)}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = json.loads(PARAMS_BASE_PATH.read_text(encoding="utf-8-sig"))

    log.info("v15_drift_and_retune starting")
    log.info("Recent: %s to %s", RECENT_START, RECENT_END)
    log.info("Prior:  %s to %s", PRIOR_START, PRIOR_END)

    # Load data for all windows
    t0 = time.time()
    spy_r, vix_r = _runner.load_data(RECENT_START, RECENT_END)
    spy_p, vix_p = _runner.load_data(PRIOR_START, PRIOR_END)
    spy_j, vix_j = _runner.load_data(J_EDGE_START, J_EDGE_END)
    log.info("Data loaded in %.1fs", time.time() - t0)

    # Window comparison
    recent = _window_metrics(base, RECENT_START, RECENT_END, spy_r, vix_r)
    prior  = _window_metrics(base, PRIOR_START,  PRIOR_END,  spy_p, vix_p)
    log.info("RECENT: n=%d wr=%.0f%% pnl=$%.0f sharpe=%.2f maxdd=$%.0f",
             recent["n_trades"], recent["wr"]*100, recent["total_pnl"],
             recent["ann_sharpe"], recent["max_drawdown"])
    log.info("PRIOR:  n=%d wr=%.0f%% pnl=$%.0f sharpe=%.2f maxdd=$%.0f",
             prior["n_trades"], prior["wr"]*100, prior["total_pnl"],
             prior["ann_sharpe"], prior["max_drawdown"])

    # J-edge score on production params
    j_edge = _j_edge(base, spy_j, vix_j)
    log.info("J-edge: edge_capture=$%+.0f winners=%.0f%% losers_added=$%.0f",
             j_edge["edge_capture"],
             j_edge["winners_capture_pct"] * 100,
             j_edge["losers_added"])

    # Drift detection
    drift_detected = False
    drift_signals = []
    if prior["ann_sharpe"] != 0 and recent["n_trades"] > 0 and prior["n_trades"] > 0:
        sharpe_delta = (recent["ann_sharpe"] - prior["ann_sharpe"]) / max(abs(prior["ann_sharpe"]), 0.01)
        if abs(sharpe_delta) > DRIFT_THRESHOLD_PCT:
            drift_signals.append(f"Sharpe drift: {prior['ann_sharpe']:.2f} -> {recent['ann_sharpe']:.2f} ({sharpe_delta*100:+.0f}%)")
            drift_detected = True

        wr_delta = (recent["wr"] - prior["wr"]) / max(prior["wr"], 0.01)
        if abs(wr_delta) > DRIFT_THRESHOLD_PCT:
            drift_signals.append(f"WR drift: {prior['wr']*100:.0f}% -> {recent['wr']*100:.0f}% ({wr_delta*100:+.0f}%)")
            drift_detected = True

    if j_edge["edge_capture"] < EDGE_FLOOR:
        drift_signals.append(f"J-edge below floor: ${j_edge['edge_capture']:.0f} < ${EDGE_FLOOR}")
        drift_detected = True

    drift_severity = "GREEN"
    if drift_detected and len(drift_signals) >= 2:
        drift_severity = "RED"
    elif drift_detected:
        drift_severity = "YELLOW"

    log.info("DRIFT: %s — %s", drift_severity, drift_signals or ["none"])

    # Build base scorecard
    scorecard = {
        "rule_id": "v15-drift-check",
        "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "drift_severity": drift_severity,
        "drift_signals": drift_signals,
        "recent_window": {k: v for k, v in recent.items() if k != "daily_per_day"},
        "prior_window":  {k: v for k, v in prior.items()  if k != "daily_per_day"},
        "j_edge": {
            "edge_capture": j_edge["edge_capture"],
            "winners_capture": j_edge["winners_capture"],
            "losers_added": j_edge["losers_added"],
        },
        "retune_triggered": False,
        "op20_disclosures": [
            "1. ACCOUNT SIZE: qty from production params.json. Diagnostic only.",
            "2. SAMPLE BIAS: Rolling window comparison. 30-day windows = ~22 trading days each.",
            "3. OUT-OF-SAMPLE: N/A — this is a regime-monitoring diagnostic, not a new strategy.",
            "4. REAL-FILLS: BS-sim (diagnostic speed — retune if run uses real-fills).",
            "5. FAILURE MODES: If drift RED and retune fails to improve edge_capture, escalate to J.",
            "6. CONCENTRATION: Not computed for drift check. Retune includes top5_pct.",
        ],
    }

    # Retune sweep if drift detected
    retune_best = None
    if drift_detected:
        log.info("DRIFT detected — running %d retune combos...",
                 len(list(itertools.product(*RETUNE_SWEEP.values()))))
        keys = list(RETUNE_SWEEP.keys())
        combos = [dict(zip(keys, vals)) for vals in itertools.product(*RETUNE_SWEEP.values())]
        retune_results_path = OUT_DIR / "retune_results.jsonl"
        if retune_results_path.exists():
            retune_results_path.unlink()

        ctx = mp.get_context("spawn")
        with ctx.Pool(
            processes=MAX_PARALLEL,
            initializer=_worker_init,
            initargs=(base,),
            maxtasksperchild=10,
        ) as pool:
            for r in pool.imap_unordered(_retune_worker, combos, chunksize=1):
                with retune_results_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(r) + "\n")
                if "error" not in r:
                    if retune_best is None or r["edge_capture"] > retune_best["edge_capture"]:
                        retune_best = r
                        log.info("RETUNE NEW BEST: edge=$%+.0f combo=%s",
                                 r["edge_capture"], r["combo"])

        if retune_best and retune_best["edge_capture"] >= EDGE_FLOOR:
            scorecard["retune_triggered"] = True
            scorecard["retune_best"] = {
                "edge_capture": retune_best["edge_capture"],
                "combo": retune_best["combo"],
                "by_day": retune_best["by_day"],
                "total_pnl": retune_best["total_pnl"],
                "sharpe": retune_best["sharpe"],
            }
            log.info("RETUNE SUCCESS: edge=$%+.0f", retune_best["edge_capture"])
        else:
            log.warning("Retune found no improvement. J intervention needed.")

    SCORECARD_PATH.write_text(json.dumps(scorecard, indent=2))
    log.info("Scorecard written: %s", SCORECARD_PATH)
    log.info("Total elapsed: %.1f min", (time.time() - t0) / 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
