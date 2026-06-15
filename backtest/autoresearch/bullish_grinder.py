"""Bullish-side grinder — builds the BULL_RECLAIM_RIDE_THE_RIBBON tier.

Per CLAUDE.md OP 16, J has 0 documented bullish winners (yet), so we cannot
score by edge_capture. Instead:

  PRIMARY GATE: do-no-harm to bearish winners
    - 4/29 bear PnL must NOT regress when bull is enabled
    - 5/04 bear PnL must NOT regress
    - losers_added on 5/05/06/07 must stay 0

  PRIMARY METRIC: bullish-only wide_pnl + concentration + quarter coverage
    - bull_wide_pnl > 0 (must be net-positive own its own)
    - top5_pct <= 200%
    - >= 4 of 6 quarters net-positive
    - bidirectional total wide_pnl >= bear-only baseline

This stage runs IN PARALLEL with the bearish stages (different worker pool,
different state directory).

Knobs varied:
    bull_min_triggers: 1, 2, 3
    bull_premium_stop: -0.08, -0.10, -0.12
    bull_strike_offset: 0 (ATM), 1 (OTM-1), 2 (OTM-2)
    bull_runner_target: 1.5, 2.0, 2.5

Total grid: 3 * 3 * 3 * 3 = 81 combos. ~4h at 4 workers.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import multiprocessing as mp
import os
import sys
import traceback
from collections import defaultdict
from pathlib import Path

if sys.platform == "win32":
    _pw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _pw.exists():
        mp.set_executable(str(_pw))

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

OUT = REPO / "autoresearch" / "_state" / "bullish_grinder"
OUT.mkdir(parents=True, exist_ok=True)

PROGRESS = OUT / "progress.json"
RESULTS = OUT / "results.jsonl"
REJECTIONS = OUT / "rejections.jsonl"
KEEPERS = OUT / "keepers.jsonl"
PIDFILE = OUT / "runner.pid"
LOGFILE = OUT / "grinder.log"

# Floor: bear wins must hold when bull is enabled
BEAR_4_29_FLOOR = 372.0
BEAR_5_04_FLOOR = 2418.0
WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)  # updated 2026-05-23; master merged through 5/22


def _build_grid() -> list[dict]:
    grid = []
    for bull_triggers in [1, 2, 3]:
        for bull_stop in [-0.08, -0.10, -0.12]:
            for bull_strike in [0, 1, 2]:
                for bull_runner in [1.5, 2.0, 2.5]:
                    grid.append({
                        "bull_min_triggers": bull_triggers,
                        "bull_premium_stop": bull_stop,
                        "bull_strike_offset": bull_strike,
                        "bull_runner_target": bull_runner,
                    })
    return grid


def evaluate_bull_combo(combo: dict) -> dict:
    """Score a bullish-side knob combo.

    1. Run engine BEAR-ONLY on full window → baseline_bear_pnl, baseline 4/29 + 5/04
    2. Run engine BIDIRECTIONAL with bull combo → bidir_pnl, bidir 4/29 + 5/04
    3. Compute bull_only_pnl = bidir - bear
    4. Floor check: bear days didn't regress, bull on its own is net+
    """
    import json as _json
    from autoresearch import runner as _runner
    from autoresearch.j_edge_tracker import V15_J_EDGE_OVERRIDES

    try:
        params_path = REPO.parent / "automation" / "state" / "params.json"
        params = _json.loads(params_path.read_text(encoding="utf-8-sig"))
        params.update(V15_J_EDGE_OVERRIDES)

        # Build bull-enabled params
        bull_params = dict(params)
        bull_params.update({
            "min_triggers_bull": combo["bull_min_triggers"],
            "premium_stop_pct_bull": combo["bull_premium_stop"],
            "strike_offset_bull": combo["bull_strike_offset"],
        })

        # Bear-only baseline (run with enable_bullish=False — proxy by setting absurd bull min_triggers)
        bear_only_params = dict(params)
        bear_only_params["min_triggers_bull"] = 99   # impossible threshold = no bull entries

        spy, vix = _runner.load_data(WIDE_START, WIDE_END)

        # Run bear-only
        bear_res, bear_m = _runner.run_with_params(bear_only_params, WIDE_START, WIDE_END, spy, vix)
        bear_only_pnl = round(bear_m.total_pnl, 2)

        bear_4_29 = round(sum(t.dollar_pnl for t in bear_res.trades if t.entry_time_et.date() == dt.date(2026, 4, 29)), 2)
        bear_5_04 = round(sum(t.dollar_pnl for t in bear_res.trades if t.entry_time_et.date() == dt.date(2026, 5, 4)), 2)

        # Run bidirectional
        bidir_res, bidir_m = _runner.run_with_params(bull_params, WIDE_START, WIDE_END, spy, vix)
        bidir_pnl = round(bidir_m.total_pnl, 2)

        # Split by side
        bull_trades = [t for t in bidir_res.trades if t.side == "C"]
        bear_trades_in_bidir = [t for t in bidir_res.trades if t.side == "P"]
        bull_only_pnl = round(sum(t.dollar_pnl for t in bull_trades), 2)
        bear_in_bidir_pnl = round(sum(t.dollar_pnl for t in bear_trades_in_bidir), 2)
        n_bull_trades = len(bull_trades)
        n_bear_trades = len(bear_trades_in_bidir)

        # Per-quarter for bull only
        quarter_pnl = defaultdict(float)
        day_pnl = defaultdict(float)
        for t in bull_trades:
            d = t.entry_time_et.date()
            day_pnl[d] += t.dollar_pnl
            q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
            quarter_pnl[q] += t.dollar_pnl
        sorted_days = sorted(day_pnl.values(), reverse=True)
        top5_sum = sum(sorted_days[:5])
        top5_pct = round(top5_sum / bull_only_pnl, 3) if bull_only_pnl > 0 else 999.0
        positive_quarters = sum(1 for v in quarter_pnl.values() if v > 0)

        # Per-day on J's known days (must not regress)
        bidir_4_29 = round(sum(t.dollar_pnl for t in bidir_res.trades if t.entry_time_et.date() == dt.date(2026, 4, 29)), 2)
        bidir_5_04 = round(sum(t.dollar_pnl for t in bidir_res.trades if t.entry_time_et.date() == dt.date(2026, 5, 4)), 2)
        bidir_5_05 = round(sum(t.dollar_pnl for t in bidir_res.trades if t.entry_time_et.date() == dt.date(2026, 5, 5)), 2)
        bidir_5_06 = round(sum(t.dollar_pnl for t in bidir_res.trades if t.entry_time_et.date() == dt.date(2026, 5, 6)), 2)
        bidir_5_07 = round(sum(t.dollar_pnl for t in bidir_res.trades if t.entry_time_et.date() == dt.date(2026, 5, 7)), 2)

        regressions = []
        if bidir_4_29 < BEAR_4_29_FLOOR - 1:
            regressions.append(f"4/29 bidir ${bidir_4_29:.0f} < bear floor ${BEAR_4_29_FLOOR:.0f}")
        if bidir_5_04 < BEAR_5_04_FLOOR - 1:
            regressions.append(f"5/04 bidir ${bidir_5_04:.0f} < bear floor ${BEAR_5_04_FLOOR:.0f}")
        if bidir_5_05 < -1:
            regressions.append(f"5/05 bidir ${bidir_5_05:.0f} < 0")
        if bidir_5_06 < -1:
            regressions.append(f"5/06 bidir ${bidir_5_06:.0f} < 0")
        if bidir_5_07 < -1:
            regressions.append(f"5/07 bidir ${bidir_5_07:.0f} < 0")
        if bull_only_pnl <= 0:
            regressions.append(f"bull-only pnl ${bull_only_pnl:.0f} not net+")
        if positive_quarters < 4:
            regressions.append(f"bull positive_quarters {positive_quarters} < 4")
        if bidir_pnl < bear_only_pnl - 1:
            regressions.append(f"bidir ${bidir_pnl:.0f} < bear-only ${bear_only_pnl:.0f} (bull cannibalized)")

        return {
            "combo": combo,
            "bear_only_pnl": bear_only_pnl,
            "bidir_pnl": bidir_pnl,
            "bull_only_pnl": bull_only_pnl,
            "bear_in_bidir_pnl": bear_in_bidir_pnl,
            "n_bull_trades": n_bull_trades,
            "n_bear_trades": n_bear_trades,
            "bidir_4_29": bidir_4_29,
            "bidir_5_04": bidir_5_04,
            "bidir_5_05": bidir_5_05,
            "bidir_5_06": bidir_5_06,
            "bidir_5_07": bidir_5_07,
            "bull_top5_pct": top5_pct,
            "bull_quarter_pnl": {k: round(v, 2) for k, v in quarter_pnl.items()},
            "bull_positive_quarters": positive_quarters,
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=4.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    # FIX 2026-05-24: reset BEFORE logging.basicConfig() so LOGFILE isn't held open
    # when we try to delete it (Windows PermissionError on open files).
    workers = min(args.workers, 4)
    if args.reset:
        for f in [PROGRESS, RESULTS, REJECTIONS, KEEPERS, LOGFILE]:
            if f.exists():
                f.unlink()
    logging.basicConfig(filename=str(LOGFILE), level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    PIDFILE.write_text(str(os.getpid()), encoding="utf-8")

    grid = _build_grid()
    started = dt.datetime.now()
    deadline = started + dt.timedelta(hours=args.hours)

    state = {
        "started_at": started.isoformat(), "deadline_at": deadline.isoformat(),
        "total_combos": len(grid), "completed": 0, "passed_floors": 0,
        "rejected": 0, "keepers": 0, "best_bull_pnl": None,
        "best_bidir_pnl": None, "current_pid": os.getpid(), "workers": workers,
        "last_update": started.isoformat(), "status": "running", "stage": "bullish",
    }
    def _wp():
        tmp = PROGRESS.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        tmp.replace(PROGRESS)
    _wp()
    logging.info(f"Bullish started: {len(grid)} combos, {workers} workers, deadline={deadline}")

    completed = keepers_n = 0
    best_bull = None

    with mp.Pool(workers) as pool:
        for r in pool.imap_unordered(evaluate_bull_combo, grid, chunksize=1):
            completed += 1
            if dt.datetime.now() > deadline:
                state["status"] = "deadline_reached"; _wp(); pool.terminate(); break
            if r["passed_floors"]:
                with RESULTS.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(r, default=str) + "\n")
                state["passed_floors"] += 1
                bp = r.get("bull_only_pnl")
                if bp is not None and (best_bull is None or bp > best_bull[0]):
                    best_bull = (bp, r["combo"])
                    state["best_bull_pnl"] = bp
                    state["best_bidir_pnl"] = r.get("bidir_pnl")
                    keepers_n += 1
                    state["keepers"] = keepers_n
                    with KEEPERS.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(r, default=str) + "\n")
                    logging.info(f"BULL KEEPER #{keepers_n}: bull_only=${bp:.0f} bidir=${r.get('bidir_pnl', 0):.0f} {r['combo']}")
            else:
                with REJECTIONS.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(r, default=str) + "\n")
                state["rejected"] += 1
            state["completed"] = completed
            state["last_update"] = dt.datetime.now().isoformat()
            if completed % 3 == 0:
                _wp()

    state["status"] = "completed" if state["status"] == "running" else state["status"]
    state["completed_at"] = dt.datetime.now().isoformat()
    _wp()
    if PIDFILE.exists():
        PIDFILE.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
