"""v14_ENHANCED Stage 1 grinder.

Mirrors `overnight_grinder.py` but for the v14_enhanced strategy: original v14
BEARISH_REJECTION + the 2 SNIPER innovations (drop 10:00 gate, add profit-lock).

NEW vs overnight_grinder:
  - J anchor list extended with 2026-05-12 (the day v14 was BLIND to because of
    the 10:00 gate; v14_enhanced MUST catch it).
  - Knob grid focused on the 2 new knobs + their interactions with v14 exits.
  - Uses V15_J_EDGE_OVERRIDES as base (locked OP 17 doctrine knobs).

Output (under autoresearch/_state/v14_enhanced_stage1/):
    progress.json        live progress meter
    results.jsonl        candidates that passed floors
    rejections.jsonl     candidates that broke a floor
    keepers.jsonl        candidates with improving wide_pnl
    runner.pid           current process PID
    grinder.log          structured log

CLI:
    pythonw.exe -m autoresearch.v14_enhanced_grinder --hours 2 --workers 4

Constraints (CLAUDE.md):
  - OP 15: max 4 parallel workers (process-based, multiprocessing.Pool)
  - OP 16: edge_capture is PRIMARY
  - OP 11/13: pure Python, no LLM in the loop
"""

from __future__ import annotations

import argparse
import datetime as dt
import gc
import json
import logging
import multiprocessing as mp
import os
import random
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

OUT_DIR = REPO / "autoresearch" / "_state" / "v14_enhanced_stage1"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROGRESS = OUT_DIR / "progress.json"
RESULTS = OUT_DIR / "results.jsonl"
REJECTIONS = OUT_DIR / "rejections.jsonl"
KEEPERS = OUT_DIR / "keepers.jsonl"
PIDFILE = OUT_DIR / "runner.pid"
LOGFILE = OUT_DIR / "grinder.log"

# v14_enhanced anchor days. Adds 2026-05-12 to the original 3 winners.
V14E_J_WINNERS = [
    {"date": "2026-04-29", "j_pnl": 342, "side": "P", "strike": 710, "floor_pnl": 200},
    {"date": "2026-05-01", "j_pnl": 470, "side": "P", "strike": 721, "floor_pnl": 300},
    {"date": "2026-05-04", "j_pnl": 730, "side": "P", "strike": 721, "floor_pnl": 500},
    {"date": "2026-05-12", "j_pnl": 400, "side": "P", "strike": 733, "floor_pnl": 200,
     "note": "NEW anchor — the day v14 was blind to because of the 10:00 gate"},
]
V14E_J_LOSERS = [
    {"date": "2026-05-05", "j_pnl": -260},
    {"date": "2026-05-06", "j_pnl": -300},
    {"date": "2026-05-07", "j_pnl": -45},
]

WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 22)  # updated 2026-05-23; master merged through 5/22

# Locked OP 17 doctrine exit knobs (v15-j-edge config) — base for every combo
LOCKED_OVERRIDES = {
    "strike_offset_bear": 0,           # ATM (proven J-edge config)
    "min_triggers_bear": 1,            # asymmetric
    "premium_stop_pct_bear": -0.20,    # locked OP 17 doctrine
    "tp1_qty_fraction": 0.5,           # locked OP 17 doctrine
}


def _setup_logging() -> None:
    logging.basicConfig(
        filename=str(LOGFILE),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _write_progress(state: dict) -> None:
    tmp = PROGRESS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(PROGRESS)


def _append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _build_param_grid() -> list[dict]:
    """540 v14_enhanced combos. Sweeps the 2 NEW knobs + 3 exit knobs.

    Locked (per OP 17 + v15-j-edge): strike_offset_bear=0, min_triggers_bear=1,
    premium_stop_pct_bear=-0.20, tp1_qty_fraction=0.5.
    """
    grid: list[dict] = []
    for no_trade_before in ["09:35", "09:45", "09:55", "10:00"]:
        for profit_lock_threshold_pct in [0.0, 0.05, 0.10, 0.15, 0.20]:
            for profit_lock_stop_offset_pct in [0.0, 0.05, 0.10]:
                for tp1_premium_pct in [0.30, 0.50, 0.75]:
                    for runner_target_premium_pct in [1.5, 2.0, 2.5]:
                        combo = dict(LOCKED_OVERRIDES)
                        combo.update({
                            "no_trade_before": no_trade_before,
                            "profit_lock_threshold_pct": profit_lock_threshold_pct,
                            "profit_lock_stop_offset_pct": profit_lock_stop_offset_pct,
                            "tp1_premium_pct": tp1_premium_pct,
                            "runner_target_premium_pct": runner_target_premium_pct,
                        })
                        grid.append(combo)
    return grid


def evaluate_v14_enhanced_combo(combo: dict) -> dict:
    """Run J-edge (4 winners + 3 losers) + wide-window aggregate + OP 19 metrics.

    Output schema matches overnight_grinder.evaluate_combo for downstream tooling.

    IMPORTANT: loads params.json as the base then merges the combo on top so that
    all production parameters (VIX thresholds, position sizing, filter constants,
    etc.) are present. Without this merge the engine runs with only the 9 swept
    knobs and produces garbage results (L-GRINDER-PARAMS-BASE-MISSING).
    """
    try:
        import json as _json
        from autoresearch import runner as _runner

        # Load production base params — merged with combo so VIX thresholds,
        # position sizing, filter constants, etc. are all present.
        _params_path = REPO.parent / "automation" / "state" / "params.json"
        params = _json.loads(_params_path.read_text(encoding="utf-8-sig"))
        params.update(combo)  # combo knobs override base params

        # ---- J anchor days ----
        all_dates = [t["date"] for t in V14E_J_WINNERS + V14E_J_LOSERS]
        min_d = dt.date.fromisoformat(min(all_dates))
        max_d = dt.date.fromisoformat(max(all_dates))
        # 60d warmup before the first anchor day so ribbon/EMAs are formed (without it
        # 4/29 fires nothing). J-anchor capture is measured under REAL fills (recalibrated
        # 2026-06-14) to match production; the wide window below stays BS for speed.
        spy_j, vix_j = _runner.load_data(min_d - dt.timedelta(days=60), max_d)

        by_day: dict[str, float] = {}
        for w in V14E_J_WINNERS:
            d = dt.date.fromisoformat(w["date"])
            _, m = _runner.run_with_params({**params, "use_real_fills": True}, d, d, spy_j, vix_j)
            by_day[w["date"]] = round(m.total_pnl, 2)
        for l in V14E_J_LOSERS:
            d = dt.date.fromisoformat(l["date"])
            _, m = _runner.run_with_params({**params, "use_real_fills": True}, d, d, spy_j, vix_j)
            by_day[l["date"]] = round(m.total_pnl, 2)

        winners_capture = sum(by_day.get(w["date"], 0) for w in V14E_J_WINNERS)
        losers_added = 0.0
        for l in V14E_J_LOSERS:
            pnl = by_day.get(l["date"], 0.0)
            if pnl < 0:
                losers_added += -pnl
        edge_capture = winners_capture - losers_added

        pnl_4_29 = by_day.get("2026-04-29", 0.0)
        pnl_5_04 = by_day.get("2026-05-04", 0.0)
        pnl_5_12 = by_day.get("2026-05-12", 0.0)

        # ---- Wide window 2025-01-01 .. WIDE_END ----
        spy_w, vix_w = _runner.load_data(WIDE_START, WIDE_END)
        res, m_wide = _runner.run_with_params(params, WIDE_START, WIDE_END, spy_w, vix_w)
        wide_pnl = round(m_wide.total_pnl, 2)
        wide_n = m_wide.n_trades
        wide_wr = (m_wide.n_winners / m_wide.n_trades) if m_wide.n_trades else 0.0

        # OP 19 default regime-robustness metrics
        day_pnl: dict = defaultdict(float)
        quarter_pnl: dict = defaultdict(float)
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

        # ---- Floors (J-anchor edge gate RE-ENABLED + recalibrated 2026-06-14) ----
        # edge_capture is now measured under REAL fills WITH 60d warmup (above).
        # Production v15.3 baseline = +774 across the 7 anchor days.
        # IMPORTANT empirical caveat: edge_capture is ~INVARIANT across this grinder's
        # search space — exit knobs AND the ribbon gates do not change which J-anchor
        # trades fire (the firing trades exit on time/level stops insensitive to the
        # swept knobs). So this floor is cheap degenerate-case insurance, NOT the
        # primary discriminator: the concentration + per-quarter gates below do the
        # real anti-overfit work. Tightening those is the lever for stronger overfit
        # control (see PROGRESS-2026-06-14.md "OP-16").
        EDGE_CAPTURE_FLOOR = 0.0  # was BS-era 771 (unreachable under real fills); now reject only combos that NET-DESTROY J-anchor edge
        regressions = []
        if edge_capture < EDGE_CAPTURE_FLOOR:
            regressions.append(f"edge_capture ${edge_capture:.0f} < ${EDGE_CAPTURE_FLOOR:.0f} floor (J-anchor real-fills)")

        # Aggregate: real signal over 16-month window (primary filter)
        if wide_pnl < 5000:
            regressions.append(f"wide_pnl ${wide_pnl:.0f} < $5000 floor")

        # Aggregate: concentration check (relaxed for Stage 1 — tighten in Stage 3+)
        if top5_pct > 0.90:
            regressions.append(f"top5_pct {top5_pct:.2f} > 0.90 ceiling")

        # Aggregate: regime stability (at least 3-of-6 quarters — Stage 1 permissive)
        if positive_quarters < 3:
            regressions.append(f"positive_quarters {positive_quarters}/{quarter_count} < 3 floor")

        result = {
            "combo": combo,
            "pnl_4_29": pnl_4_29,
            "pnl_5_04": pnl_5_04,
            "pnl_5_12": pnl_5_12,
            "by_day": by_day,
            "winners_capture": round(winners_capture, 2),
            "losers_added": round(losers_added, 2),
            "edge_capture": round(edge_capture, 2),
            "wide_pnl": wide_pnl,
            "wide_n_trades": wide_n,
            "wide_wr": round(wide_wr, 3),
            "top5_pct": top5_pct,
            "quarter_pnl": {k: round(v, 2) for k, v in quarter_pnl.items()},
            "positive_quarters": positive_quarters,
            "quarter_count": quarter_count,
            "max_drawdown": round(max_dd, 2),
            "passed_floors": len(regressions) == 0,
            "regressions": regressions,
        }
        # T72: force GC between combos to release per-combo allocations
        # (SimResults, trade lists, DataFrames). Prevents memory fragmentation
        # growth that led to silent OOM kills on Windows pythonw — supplements
        # T70's maxtasksperchild=10 worker recycle. ~10ms overhead.
        gc.collect()
        return result
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
    parser.add_argument("--hours", type=float, default=2.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    # FIX 2026-05-24: reset BEFORE _setup_logging() so LOGFILE isn't held open
    # when we try to delete it (Windows PermissionError on open files).
    workers = min(args.workers, 4)

    if args.reset:
        for f in [PROGRESS, RESULTS, REJECTIONS, KEEPERS, LOGFILE]:
            if f.exists():
                f.unlink()

    _setup_logging()

    PIDFILE.write_text(str(os.getpid()), encoding="utf-8")

    started = dt.datetime.now()
    deadline = started + dt.timedelta(hours=args.hours)
    grid = _build_param_grid()
    random.Random(2028).shuffle(grid)

    state = {
        "started_at": started.isoformat(),
        "deadline_at": deadline.isoformat(),
        "total_combos": len(grid),
        "completed": 0,
        "passed_floors": 0,
        "rejected": 0,
        "keepers": 0,
        "best_edge_capture": 0.0,
        "best_wide_pnl": None,
        "current_pid": os.getpid(),
        "workers": workers,
        "last_update": started.isoformat(),
        "status": "running",
    }
    _write_progress(state)
    logging.info(f"v14_enhanced Stage 1 started: {len(grid)} combos, {workers} workers, deadline={deadline}")

    completed = 0
    keepers_n = 0
    best_wide: tuple[float, dict] | None = None

    # T70 (Fire #24 2026-05-14): maxtasksperchild=10 forces worker recycle every
    # 10 combos. Bounds memory commit (each worker re-loads master CSV on import,
    # ~150MB). Combined with pythonw GUI subsystem on Windows, prior runs hit
    # silent OOM kill ~50 combos in. Cost: ~5% throughput hit from worker startup
    # overhead. Benefit: predictable memory ceiling.
    # See docs/T39-V14E-GRINDER-SILENT-DEATH-2026-05-14.md
    with mp.Pool(workers, maxtasksperchild=10) as pool:
        for result in pool.imap_unordered(evaluate_v14_enhanced_combo, grid, chunksize=1):
            completed += 1

            if dt.datetime.now() > deadline:
                logging.info("Deadline reached, terminating pool")
                state["status"] = "deadline_reached"
                _write_progress(state)
                pool.terminate()
                break

            if result["passed_floors"]:
                _append_jsonl(RESULTS, result)
                state["passed_floors"] += 1

                wp = result.get("wide_pnl")
                if wp is not None and (best_wide is None or wp > best_wide[0]):
                    best_wide = (wp, result["combo"])
                    state["best_wide_pnl"] = wp
                    keepers_n += 1
                    state["keepers"] = keepers_n
                    _append_jsonl(KEEPERS, result)
                    logging.info(
                        f"KEEPER #{keepers_n}: wide_pnl=${wp:.0f} "
                        f"edge=${result['edge_capture']:.0f} "
                        f"5/12=${result['pnl_5_12']:.0f} "
                        f"combo={result['combo']}"
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
                # T73: flush all logging handlers every 5 combos so the last
                # logged lines survive a SIGKILL / Windows OOM termination.
                # Prevents partial log lines when the process is killed mid-write.
                for _h in logging.getLogger().handlers:
                    try:
                        _h.flush()
                    except Exception:
                        pass

    state["status"] = "completed" if state["status"] == "running" else state["status"]
    state["completed_at"] = dt.datetime.now().isoformat()
    _write_progress(state)

    if PIDFILE.exists():
        PIDFILE.unlink()

    if best_wide:
        logging.info(
            f"v14_enhanced Stage 1 done: {completed}/{len(grid)} "
            f"passed={state['passed_floors']} keepers={keepers_n} "
            f"best_wide=${best_wide[0]:.0f}"
        )
    else:
        logging.info(
            f"v14_enhanced Stage 1 done: {completed}/{len(grid)} "
            f"passed={state['passed_floors']} no keepers"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
