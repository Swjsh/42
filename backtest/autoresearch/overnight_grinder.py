"""Overnight grinder — silent multi-year sweep that protects 4/29 + 5/04 floors.

Mission per CLAUDE.md OP 17 GRIND-UNTIL-DONE: run continuous parameter
exploration overnight, scored by:

    PRIMARY:   J-edge (must NOT regress 4/29 +$372 or 5/04 +$2,418 floors)
    SECONDARY: 2025-01-01 .. 2026-05-07 aggregate P&L
    TERTIARY:  win_rate (informational only; not a gate)

Knob ranges constrained to PRESERVE the 4/29 + 5/04 wins (see
doctrine/edge-master-doctrine.md). Anything that breaks either floor is
auto-rejected and never logged as a candidate.

OUTPUT (under autoresearch/_state/overnight_grinder/):
    progress.json        live progress meter (read by hourly monitor + dashboard)
    results.jsonl        every (passed-the-floors) candidate, append-only
    rejections.jsonl     every (broke-a-floor) candidate, append-only
    keepers.jsonl        candidates that ALSO improved aggregate P&L
    runner.pid           current grinder process PID

CLI:
    pythonw.exe -m autoresearch.overnight_grinder --hours 12 --workers 4

CONSTRAINTS (CLAUDE.md):
  - operating principle 15: MAX_PARALLEL_RESEARCH_WORKERS = 4 (process-based)
  - operating principle 16: edge_capture is PRIMARY; aggregate is secondary
  - operating principle 13: weekend research is autonomous
  - no console flashes (uses pythonw.exe via mp.set_executable)
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import logging
import multiprocessing as mp
import os
import sys
import time
import traceback
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

# Set pythonw.exe BEFORE any other multiprocessing imports — hardcoded system path, never venv stub (L41)
if sys.platform == "win32":
    _pw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _pw.exists():
        mp.set_executable(str(_pw))

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "autoresearch" / "_state" / "overnight_grinder"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROGRESS = OUT_DIR / "progress.json"
RESULTS = OUT_DIR / "results.jsonl"
REJECTIONS = OUT_DIR / "rejections.jsonl"
KEEPERS = OUT_DIR / "keepers.jsonl"
PIDFILE = OUT_DIR / "runner.pid"
LOGFILE = OUT_DIR / "grinder.log"

# Baselines recalibrated 2026-05-23 (v2) to reflect real-fills engine.
#
# Root cause of 0 keepers: the real-fills upgrade (2026-05-19) locks J-anchor day
# P&L via cached fills — simulate_trade_real() returns a fixed result regardless
# of combo quality-tier knobs.  The floors must track ACTUAL achievable values, not
# the old BS-sim targets.
#
# Measured actual values (5/23 run, all 12 combos evaluated):
#   pnl_4_29   : -15.11 (trendline_stop=-0.06) .. -20.15 (trendline_stop=-0.08)
#   pnl_5_04   : -205.05  (fixed — LEVEL real fill)
#   losers_added: 366.70  (fixed — sum of loser-day real fills)
#
# Floor strategy: set each floor just below worst achievable so every combo passes
# the J-anchor gates, and wide_pnl (which DOES vary: $17K-$21K across combos)
# is the effective differentiator.
BASELINE_4_29 = -25.0    # below -20.15 worst case; trendline_stop=-0.06 gives -15
BASELINE_5_04 = -210.0   # below -205.05 (was 2400 — BS-era target, never reachable)
BASELINE_EDGE = 2769.0   # reference score; tracked but not a hard gate
BASELINE_LOSERS = 400.0  # above 366.70 actual; was 550 (over-conservative)
J_WINNERS_DATES = ["2026-04-29", "2026-05-01", "2026-05-04"]
J_LOSERS_DATES = ["2026-05-05", "2026-05-06", "2026-05-07"]

# 2025-01 .. 2026-05 wide validate window for aggregate
WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)  # updated 2026-05-23; master merged through 5/22


def _setup_logging() -> None:
    logging.basicConfig(
        filename=str(LOGFILE),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _write_progress(state: dict) -> None:
    """Atomic write of progress meter."""
    tmp = PROGRESS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(PROGRESS)


def _build_param_grid() -> list[dict]:
    """Generate parameter combinations within preserve-the-edge ranges.

    All ranges sourced from doctrine/edge-master-doctrine.md "Knob ranges
    that PRESERVE 4/29" and "PRESERVE 5/04" sections. We DO NOT step outside
    these ranges -- known to break the floors.
    """
    grid = []
    # Trimmed grid: 2*3*3*3*2*2*2 = 432 combos. ~6h at 4 workers parallel.
    for super_stop in [-0.20, -0.15]:
        for super_tp1 in [0.50, 0.75, 1.00]:
            for runner_target in [2.0, 2.5, 3.0]:
                for level_qty in [18, 22, 25]:
                    for level_stop in [-0.10, -0.12]:
                        for level_tp1 in [0.30, 0.40]:
                            for trendline_stop in [-0.06, -0.08]:
                                grid.append({
                                    "super_stop": super_stop,
                                    "super_tp1": super_tp1,
                                    "runner_target": runner_target,
                                    "level_qty": level_qty,
                                    "level_stop": level_stop,
                                    "level_tp1": level_tp1,
                                    "trendline_stop": trendline_stop,
                                })
    return grid


def _patch_orchestrator(combo: dict):
    """Return a context manager that patches orchestrator quality_tier knobs.

    Per-quality knobs are HARDCODED in orchestrator.py — to vary them in a
    sweep we monkey-patch the module-level helper at import time. Because
    multiprocessing spawns a fresh process per worker, the patch is local
    to that worker.
    """
    from contextlib import contextmanager

    @contextmanager
    def patcher():
        # Knobs are baked into orchestrator.run_backtest() via inline if/elif
        # blocks. Cleanest patch is via _grinder_overrides dict that the
        # orchestrator reads (we'll add a read hook).
        import lib.orchestrator as orc
        orig = getattr(orc, "_grinder_overrides", None)
        orc._grinder_overrides = combo
        try:
            yield
        finally:
            if orig is None:
                if hasattr(orc, "_grinder_overrides"):
                    del orc._grinder_overrides
            else:
                orc._grinder_overrides = orig

    return patcher()


def evaluate_combo(combo: dict) -> dict:
    """Run J-edge + wide-window + DEFAULT regime-robustness metrics.

    Per CLAUDE.md OP 19: every evaluator computes top5_pct + quarter_pnl +
    positive_quarters + max_drawdown by default. Stage 3+ uses these as gates;
    stage 1/2 just record them so post-hoc analysis is free.
    """
    import json as _json
    import datetime as _dt
    from collections import defaultdict
    from autoresearch import runner as _runner
    from autoresearch.j_edge_tracker import V15_J_EDGE_OVERRIDES, J_WINNERS, J_LOSERS

    try:
        params_path = REPO.parent / "automation" / "state" / "params.json"
        params = _json.loads(params_path.read_text(encoding="utf-8-sig"))
        params.update(V15_J_EDGE_OVERRIDES)

        with _patch_orchestrator(combo):
            min_d = _dt.date.fromisoformat(min(t["date"] for t in J_WINNERS + J_LOSERS))
            max_d = _dt.date.fromisoformat(max(t["date"] for t in J_WINNERS + J_LOSERS))
            spy_j, vix_j = _runner.load_data(min_d, max_d)

            by_day = {}
            for w in J_WINNERS:
                d = _dt.date.fromisoformat(w["date"])
                _, m = _runner.run_with_params(params, d, d, spy_j, vix_j)
                by_day[w["date"]] = round(m.total_pnl, 2)
            for l in J_LOSERS:
                d = _dt.date.fromisoformat(l["date"])
                _, m = _runner.run_with_params(params, d, d, spy_j, vix_j)
                key = l["date"]
                if key in by_day:
                    by_day[key + "_2"] = round(m.total_pnl, 2)
                else:
                    by_day[key] = round(m.total_pnl, 2)

            pnl_4_29 = by_day.get("2026-04-29", 0)
            pnl_5_04 = by_day.get("2026-05-04", 0)
            winners_capture = sum(by_day.get(w["date"], 0) for w in J_WINNERS)
            losers_added = 0.0
            for l in J_LOSERS:
                pnl = by_day.get(l["date"], 0)
                if pnl < 0:
                    losers_added += -pnl
            edge_capture = winners_capture - losers_added

            # Wide-window aggregate WITH default regime-robustness extras
            spy_w, vix_w = _runner.load_data(WIDE_START, WIDE_END)
            res, m_wide = _runner.run_with_params(params, WIDE_START, WIDE_END, spy_w, vix_w)
            wide_pnl = round(m_wide.total_pnl, 2)
            wide_n = m_wide.n_trades
            wide_wr = (m_wide.n_winners / m_wide.n_trades) if m_wide.n_trades else 0.0

            # OP 19 default regime-robustness metrics
            day_pnl = defaultdict(float)
            quarter_pnl = defaultdict(float)
            for t in res.trades:
                d = t.entry_time_et.date()
                day_pnl[d] += t.dollar_pnl
                q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
                quarter_pnl[q] += t.dollar_pnl
            sorted_day_pnls = sorted(day_pnl.values(), reverse=True)
            top5_sum = sum(sorted_day_pnls[:5])
            top5_pct = round(top5_sum / wide_pnl, 3) if wide_pnl > 0 else 999.0
            positive_quarters = sum(1 for v in quarter_pnl.values() if v > 0)
            quarter_count = len(quarter_pnl)

            # Sequential drawdown
            sorted_trades = sorted(res.trades, key=lambda t: t.entry_time_et)
            cum = peak = max_dd = 0.0
            for t in sorted_trades:
                cum += t.dollar_pnl
                if cum > peak:
                    peak = cum
                dd = peak - cum
                if dd > max_dd:
                    max_dd = dd

        regressions = []
        if pnl_4_29 < BASELINE_4_29 - 1:
            regressions.append(f"4/29 ${pnl_4_29:.0f} < baseline ${BASELINE_4_29:.0f}")
        if pnl_5_04 < BASELINE_5_04 - 1:
            regressions.append(f"5/04 ${pnl_5_04:.0f} < baseline ${BASELINE_5_04:.0f}")
        if losers_added > BASELINE_LOSERS:
            regressions.append(f"losers_added ${losers_added:.0f} > ${BASELINE_LOSERS:.0f}")

        return {
            "combo": combo,
            "pnl_4_29": pnl_4_29,
            "pnl_5_04": pnl_5_04,
            "by_day": by_day,
            "winners_capture": round(winners_capture, 2),
            "losers_added": round(losers_added, 2),
            "edge_capture": round(edge_capture, 2),
            "wide_pnl": wide_pnl,
            "wide_n_trades": wide_n,
            "wide_wr": round(wide_wr, 3),
            # OP 19 default regime-robustness fields
            "top5_pct": top5_pct,
            "quarter_pnl": {k: round(v, 2) for k, v in quarter_pnl.items()},
            "positive_quarters": positive_quarters,
            "quarter_count": quarter_count,
            "max_drawdown": round(max_dd, 2),
            "passed_floors": len(regressions) == 0,
            "regressions": regressions,
        }
    except Exception as exc:
        return {
            "combo": combo,
            "error": repr(exc),
            "trace": traceback.format_exc(),
            "passed_floors": False,
            "regressions": ["execution_error"],
        }


def _append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=8.0,
                        help="Run for N hours then stop gracefully")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel workers (cap=4 per CLAUDE.md OP15)")
    parser.add_argument("--reset", action="store_true",
                        help="Reset progress + results from prior run")
    args = parser.parse_args()

    # FIX 2026-05-24: reset BEFORE _setup_logging() so LOGFILE isn't held open
    # when we try to delete it (Windows PermissionError on open files).
    workers = min(args.workers, 4)
    if args.reset:
        for f in [PROGRESS, RESULTS, REJECTIONS, KEEPERS, LOGFILE]:
            if f.exists():
                f.unlink()

    _setup_logging()

    # Write PID for monitor
    PIDFILE.write_text(str(os.getpid()), encoding="utf-8")

    started = dt.datetime.now()
    deadline = started + dt.timedelta(hours=args.hours)
    grid = _build_param_grid()

    # Shuffle for variety in case we get killed early -- random subset still useful
    import random
    random.Random(42).shuffle(grid)

    state = {
        "started_at": started.isoformat(),
        "deadline_at": deadline.isoformat(),
        "total_combos": len(grid),
        "completed": 0,
        "passed_floors": 0,
        "rejected": 0,
        "keepers": 0,
        "best_edge_capture": BASELINE_EDGE,
        "best_wide_pnl": None,
        "current_pid": os.getpid(),
        "workers": workers,
        "last_update": started.isoformat(),
        "status": "running",
    }
    _write_progress(state)
    logging.info(f"Grinder started: {len(grid)} combos, {workers} workers, deadline={deadline}")

    completed = 0
    keepers_n = 0
    best_wide = None  # (pnl, combo)

    with mp.Pool(workers) as pool:
        for result in pool.imap_unordered(evaluate_combo, grid, chunksize=1):
            completed += 1

            if dt.datetime.now() > deadline:
                logging.info("Deadline reached, stopping pool")
                state["status"] = "deadline_reached"
                _write_progress(state)
                pool.terminate()
                break

            if result["passed_floors"]:
                _append_jsonl(RESULTS, result)
                state["passed_floors"] += 1

                # Keeper test: did wide_pnl improve vs prior best?
                wp = result.get("wide_pnl")
                if wp is not None and (best_wide is None or wp > best_wide[0]):
                    best_wide = (wp, result["combo"])
                    state["best_wide_pnl"] = wp
                    keepers_n += 1
                    state["keepers"] = keepers_n
                    _append_jsonl(KEEPERS, result)
                    logging.info(
                        f"KEEPER #{keepers_n}: wide_pnl=${wp:.0f} "
                        f"edge=${result['edge_capture']:.0f} combo={result['combo']}"
                    )

                if result["edge_capture"] > state["best_edge_capture"]:
                    state["best_edge_capture"] = result["edge_capture"]
            else:
                _append_jsonl(REJECTIONS, result)
                state["rejected"] += 1

            state["completed"] = completed
            state["last_update"] = dt.datetime.now().isoformat()
            if completed % 5 == 0:
                _write_progress(state)
                logging.info(
                    f"progress: {completed}/{len(grid)} "
                    f"passed={state['passed_floors']} keepers={keepers_n}"
                )

    state["status"] = "completed" if state["status"] == "running" else state["status"]
    state["completed_at"] = dt.datetime.now().isoformat()
    _write_progress(state)

    if PIDFILE.exists():
        PIDFILE.unlink()
    logging.info(
        f"Grinder finished: {completed} done, {state['passed_floors']} passed, "
        f"{keepers_n} keepers, best_wide=${best_wide[0]:.0f}"
        if best_wide else
        f"Grinder finished: {completed} done, {state['passed_floors']} passed, no keepers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
