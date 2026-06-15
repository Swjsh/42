"""Stage-4 grinder — sub-window stability validation around stage 3 keepers.

Tests each candidate against 6 separate sub-windows:
    2025-Q1 / 2025-Q2 / 2025-Q3 / 2025-Q4 / 2026-Q1 / 2026-Q2

Gates (in addition to stage 1/2/3):
  - ALL 6 sub-windows must have positive P&L (regime-robust across every quarter)
  - Min trades per quarter >= 3 (avoid statistical noise)

This is the strictest gate yet. Only candidates that work in EVERY quarter
make it through.

Reads stage-3 keepers as seeds; falls back to stage-2/stage-1 keepers if
stage-3 hasn't produced any.
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

S1 = REPO / "autoresearch" / "_state" / "overnight_grinder"
S2 = REPO / "autoresearch" / "_state" / "stage2_grinder"
S3 = REPO / "autoresearch" / "_state" / "stage3_grinder"
OUT = REPO / "autoresearch" / "_state" / "stage4_grinder"
OUT.mkdir(parents=True, exist_ok=True)

PROGRESS = OUT / "progress.json"
RESULTS = OUT / "results.jsonl"
REJECTIONS = OUT / "rejections.jsonl"
KEEPERS = OUT / "keepers.jsonl"
PIDFILE = OUT / "runner.pid"
LOGFILE = OUT / "grinder.log"

BASELINE_4_29 = 372.0
BASELINE_5_04 = 2418.0
SUB_WINDOWS = [
    ("2025-Q1", dt.date(2025, 1, 1), dt.date(2025, 3, 31)),
    ("2025-Q2", dt.date(2025, 4, 1), dt.date(2025, 6, 30)),
    ("2025-Q3", dt.date(2025, 7, 1), dt.date(2025, 9, 30)),
    ("2025-Q4", dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("2026-Q1", dt.date(2026, 1, 1), dt.date(2026, 3, 31)),
    ("2026-Q2", dt.date(2026, 4, 1), dt.date(2026, 5, 7)),
]
MIN_TRADES_PER_QUARTER = 3
WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 7)


def _load_seeds(top_n: int = 8) -> list[dict]:
    pool = []
    for path in [S3 / "keepers.jsonl", S2 / "keepers.jsonl", S1 / "keepers.jsonl"]:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        pool.append(json.loads(line))
                    except Exception:
                        pass
        if pool:
            break  # Use first non-empty source
    if not pool:
        raise SystemExit("no keepers from any prior stage")
    seen = set()
    deduped = []
    for r in pool:
        key = json.dumps(r["combo"], sort_keys=True)
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    edge_rank = {id(r): i for i, r in enumerate(sorted(deduped, key=lambda r: -r.get("edge_capture", 0)))}
    wide_rank = {id(r): i for i, r in enumerate(sorted(deduped, key=lambda r: -r.get("wide_pnl", 0)))}
    deduped.sort(key=lambda r: edge_rank[id(r)] + wide_rank[id(r)])
    return [r["combo"] for r in deduped[:top_n]]


def evaluate_combo_subwindow(combo: dict) -> dict:
    """Stage 4 evaluator: floor + per-sub-window positive + per-quarter min-trades."""
    import json as _json
    from autoresearch import runner as _runner
    from autoresearch.j_edge_tracker import V15_J_EDGE_OVERRIDES, J_WINNERS, J_LOSERS
    from autoresearch.overnight_grinder import _patch_orchestrator

    try:
        params_path = REPO.parent / "automation" / "state" / "params.json"
        params = _json.loads(params_path.read_text(encoding="utf-8-sig"))
        params.update(V15_J_EDGE_OVERRIDES)

        with _patch_orchestrator(combo):
            min_d = dt.date.fromisoformat(min(t["date"] for t in J_WINNERS + J_LOSERS))
            max_d = dt.date.fromisoformat(max(t["date"] for t in J_WINNERS + J_LOSERS))
            spy_j, vix_j = _runner.load_data(min_d, max_d)
            by_day = {}
            for w in J_WINNERS:
                d = dt.date.fromisoformat(w["date"])
                _, m = _runner.run_with_params(params, d, d, spy_j, vix_j)
                by_day[w["date"]] = round(m.total_pnl, 2)
            for l in J_LOSERS:
                d = dt.date.fromisoformat(l["date"])
                _, m = _runner.run_with_params(params, d, d, spy_j, vix_j)
                key = l["date"]
                by_day[key + "_2" if key in by_day else key] = round(m.total_pnl, 2)

            pnl_4_29 = by_day.get("2026-04-29", 0)
            pnl_5_04 = by_day.get("2026-05-04", 0)
            losers_added = sum(-by_day.get(l["date"], 0) for l in J_LOSERS if by_day.get(l["date"], 0) < 0)
            winners_capture = sum(by_day.get(w["date"], 0) for w in J_WINNERS)
            edge_capture = winners_capture - losers_added

            spy_w, vix_w = _runner.load_data(WIDE_START, WIDE_END)
            res, m_wide = _runner.run_with_params(params, WIDE_START, WIDE_END, spy_w, vix_w)
            wide_pnl = round(m_wide.total_pnl, 2)
            wide_n = m_wide.n_trades

            # Per-sub-window
            sub_window_results = {}
            for label, ws, we in SUB_WINDOWS:
                trades_in_window = [t for t in res.trades if ws <= t.entry_time_et.date() <= we]
                pnl_in_window = round(sum(t.dollar_pnl for t in trades_in_window), 2)
                n_in_window = len(trades_in_window)
                sub_window_results[label] = {"pnl": pnl_in_window, "n": n_in_window}

        regressions = []
        if pnl_4_29 < BASELINE_4_29 - 1:
            regressions.append(f"4/29 ${pnl_4_29:.0f} < baseline ${BASELINE_4_29:.0f}")
        if pnl_5_04 < BASELINE_5_04 - 1:
            regressions.append(f"5/04 ${pnl_5_04:.0f} < baseline ${BASELINE_5_04:.0f}")
        if losers_added > 1:
            regressions.append(f"losers_added ${losers_added:.0f} > 0")
        # Stage 4 ADDED: every sub-window must be positive AND have >= MIN trades
        for label, sw in sub_window_results.items():
            if sw["pnl"] <= 0:
                regressions.append(f"{label} pnl ${sw['pnl']:.0f} <= 0")
            if sw["n"] < MIN_TRADES_PER_QUARTER:
                regressions.append(f"{label} only {sw['n']} trades (< {MIN_TRADES_PER_QUARTER})")

        return {
            "combo": combo,
            "pnl_4_29": pnl_4_29,
            "pnl_5_04": pnl_5_04,
            "winners_capture": round(winners_capture, 2),
            "losers_added": round(losers_added, 2),
            "edge_capture": round(edge_capture, 2),
            "wide_pnl": wide_pnl,
            "wide_n_trades": wide_n,
            "sub_window_pnls": sub_window_results,
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
    parser.add_argument("--top-seeds", type=int, default=8)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    workers = min(args.workers, 4)
    if args.reset:
        for f in [PROGRESS, RESULTS, REJECTIONS, KEEPERS, LOGFILE]:
            if f.exists():
                f.unlink()
    PIDFILE.write_text(str(os.getpid()), encoding="utf-8")
    logging.basicConfig(filename=str(LOGFILE), level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    grid = _load_seeds(args.top_seeds)  # Stage 4 evaluates seeds DIRECTLY (no neighborhood — they're already refined)
    started = dt.datetime.now()
    deadline = started + dt.timedelta(hours=args.hours)

    state = {
        "started_at": started.isoformat(), "deadline_at": deadline.isoformat(),
        "total_combos": len(grid), "completed": 0, "passed_floors": 0,
        "rejected": 0, "keepers": 0, "best_edge_capture": None,
        "best_wide_pnl": None, "current_pid": os.getpid(), "workers": workers,
        "last_update": started.isoformat(), "status": "running", "stage": 4,
        "top_seeds_used": args.top_seeds,
    }
    def _wp():
        tmp = PROGRESS.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        tmp.replace(PROGRESS)
    _wp()
    logging.info(f"S4 started: {len(grid)} seeds, {workers} workers")

    completed = keepers_n = 0
    best_wide = None
    with mp.Pool(workers) as pool:
        for r in pool.imap_unordered(evaluate_combo_subwindow, grid, chunksize=1):
            completed += 1
            if dt.datetime.now() > deadline:
                state["status"] = "deadline_reached"; _wp(); pool.terminate(); break
            if r["passed_floors"]:
                with RESULTS.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(r, default=str) + "\n")
                state["passed_floors"] += 1
                wp_v = r.get("wide_pnl")
                if wp_v is not None and (best_wide is None or wp_v > best_wide[0]):
                    best_wide = (wp_v, r["combo"])
                    state["best_wide_pnl"] = wp_v
                    keepers_n += 1
                    state["keepers"] = keepers_n
                    with KEEPERS.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(r, default=str) + "\n")
                    logging.info(f"S4 KEEPER #{keepers_n}: wide=${wp_v:.0f}")
                if state["best_edge_capture"] is None or r["edge_capture"] > state["best_edge_capture"]:
                    state["best_edge_capture"] = r["edge_capture"]
            else:
                with REJECTIONS.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(r, default=str) + "\n")
                state["rejected"] += 1
            state["completed"] = completed
            state["last_update"] = dt.datetime.now().isoformat()
            _wp()

    state["status"] = "completed" if state["status"] == "running" else state["status"]
    state["completed_at"] = dt.datetime.now().isoformat()
    _wp()
    if PIDFILE.exists():
        PIDFILE.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
