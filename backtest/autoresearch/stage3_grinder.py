"""Stage-3 grinder — regime-robust refinement around stage 2 winners.

Adds two new gates beyond stage 1/2:

  1. CONCENTRATION GATE: top-5 winning days must NOT exceed 200% of total P&L
     (anything > 200% means losing days net wipe out > half the headline P&L,
     i.e. strategy depends on the top-5 days for survival).

  2. QUARTER-COVERAGE GATE: at least 4 of 6 quarters (2025 Q1-Q4 + 2026 Q1-Q2)
     must be net-positive. Forces the strategy to make money across regimes,
     not just in high-vol months.

Plus standard floor protection (4/29 + 5/04 + losers_added=0).

Reads stage-2 keepers + stage-1 keepers, picks top combined, refines neighborhoods.

Usage:
    pythonw.exe -m autoresearch.stage3_grinder --hours 4 --workers 4
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

STAGE1_DIR = REPO / "autoresearch" / "_state" / "overnight_grinder"
STAGE2_DIR = REPO / "autoresearch" / "_state" / "stage2_grinder"
OUT_DIR = REPO / "autoresearch" / "_state" / "stage3_grinder"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROGRESS = OUT_DIR / "progress.json"
RESULTS = OUT_DIR / "results.jsonl"
REJECTIONS = OUT_DIR / "rejections.jsonl"
KEEPERS = OUT_DIR / "keepers.jsonl"
PIDFILE = OUT_DIR / "runner.pid"
LOGFILE = OUT_DIR / "grinder.log"

BASELINE_4_29 = 372.0
BASELINE_5_04 = 2418.0
WIDE_START = dt.date(2025, 1, 1)
WIDE_END = dt.date(2026, 5, 7)
MAX_TOP5_PCT = 2.0   # top-5 days must be <= 200% of total P&L
MIN_POSITIVE_QUARTERS = 4   # of 6


def _load_seeds(top_n: int = 10) -> list[dict]:
    """Pool stage-1 + stage-2 keepers, dedupe, take top by combined rank."""
    rows = []
    for path in [STAGE1_DIR / "keepers.jsonl", STAGE2_DIR / "keepers.jsonl"]:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
    if not rows:
        raise SystemExit("no keepers from stage 1 or 2 yet")
    seen = set()
    deduped = []
    for r in rows:
        key = json.dumps(r["combo"], sort_keys=True)
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    edge_rank = {id(r): i for i, r in enumerate(sorted(deduped, key=lambda r: -r.get("edge_capture", 0)))}
    wide_rank = {id(r): i for i, r in enumerate(sorted(deduped, key=lambda r: -r.get("wide_pnl", 0)))}
    deduped.sort(key=lambda r: edge_rank[id(r)] + wide_rank[id(r)])
    return [r["combo"] for r in deduped[:top_n]]


def _refine_combo(seed: dict) -> list[dict]:
    """Wider refinement than stage 2 — explores ±2 steps on each axis."""
    combos = []
    super_stops = [seed["super_stop"], seed["super_stop"] - 0.05, seed["super_stop"] + 0.05]
    super_tp1s = [seed["super_tp1"], seed["super_tp1"] - 0.10, seed["super_tp1"] + 0.10]
    runner_targets = [seed["runner_target"], seed["runner_target"] - 0.50, seed["runner_target"] + 0.50]
    level_qtys = [seed["level_qty"], seed["level_qty"] - 3, seed["level_qty"] + 3]
    level_stops = [seed["level_stop"], seed["level_stop"] - 0.02, seed["level_stop"] + 0.02]
    level_tp1s = [seed["level_tp1"], seed["level_tp1"] - 0.05, seed["level_tp1"] + 0.05]
    trendline_stops = [seed["trendline_stop"]]
    for ss in super_stops:
        if ss < -0.30 or ss > -0.10: continue
        for stp in super_tp1s:
            if stp < 0.40 or stp > 1.20: continue
            for rt in runner_targets:
                if rt < 1.5 or rt > 3.5: continue
                for lq in level_qtys:
                    if lq < 15 or lq > 35: continue
                    for ls in level_stops:
                        if ls < -0.20 or ls > -0.06: continue
                        for ltp in level_tp1s:
                            if ltp < 0.20 or ltp > 0.60: continue
                            for ts in trendline_stops:
                                combos.append({
                                    "super_stop": round(ss, 3),
                                    "super_tp1": round(stp, 3),
                                    "runner_target": round(rt, 3),
                                    "level_qty": int(lq),
                                    "level_stop": round(ls, 3),
                                    "level_tp1": round(ltp, 3),
                                    "trendline_stop": ts,
                                })
    return combos


def _build_grid(top_n: int) -> list[dict]:
    seeds = _load_seeds(top_n)
    seen = set()
    grid = []
    for s in seeds:
        for c in _refine_combo(s):
            key = json.dumps(c, sort_keys=True)
            if key not in seen:
                seen.add(key)
                grid.append(c)
    return grid


def evaluate_combo_robust(combo: dict) -> dict:
    """Stage 3 evaluator: standard floors + concentration + quarter coverage."""
    import json as _json
    import datetime as _dt
    from autoresearch import runner as _runner
    from autoresearch.j_edge_tracker import V15_J_EDGE_OVERRIDES, J_WINNERS, J_LOSERS
    from autoresearch.overnight_grinder import _patch_orchestrator

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
            losers_added = sum(-by_day.get(l["date"], 0) for l in J_LOSERS if by_day.get(l["date"], 0) < 0)
            edge_capture = winners_capture - losers_added

            spy_w, vix_w = _runner.load_data(WIDE_START, WIDE_END)
            res, m_wide = _runner.run_with_params(params, WIDE_START, WIDE_END, spy_w, vix_w)
            wide_pnl = round(m_wide.total_pnl, 2)
            wide_n = m_wide.n_trades
            wide_wr = (m_wide.n_winners / m_wide.n_trades) if m_wide.n_trades else 0.0

            # Per-day + per-quarter aggregation
            day_pnl = defaultdict(float)
            quarter_pnl = defaultdict(float)
            for t in res.trades:
                d = t.entry_time_et.date()
                day_pnl[d] += t.dollar_pnl
                q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
                quarter_pnl[q] += t.dollar_pnl
            sorted_days = sorted(day_pnl.values(), reverse=True)
            top5_sum = sum(sorted_days[:5])
            top5_pct = (top5_sum / wide_pnl) if wide_pnl > 0 else 999.0
            positive_quarters = sum(1 for v in quarter_pnl.values() if v > 0)
            quarter_count = len(quarter_pnl)

        regressions = []
        if pnl_4_29 < BASELINE_4_29 - 1:
            regressions.append(f"4/29 ${pnl_4_29:.0f} < baseline ${BASELINE_4_29:.0f}")
        if pnl_5_04 < BASELINE_5_04 - 1:
            regressions.append(f"5/04 ${pnl_5_04:.0f} < baseline ${BASELINE_5_04:.0f}")
        if losers_added > 1:
            regressions.append(f"losers_added ${losers_added:.0f} > 0")
        # Stage 3 ADDED gates:
        if top5_pct > MAX_TOP5_PCT:
            regressions.append(f"top5_pct {top5_pct*100:.0f}% > {MAX_TOP5_PCT*100:.0f}% (concentrated)")
        if positive_quarters < MIN_POSITIVE_QUARTERS:
            regressions.append(f"positive_quarters {positive_quarters}/{quarter_count} < {MIN_POSITIVE_QUARTERS}")

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
            "top5_pct": round(top5_pct, 3),
            "positive_quarters": positive_quarters,
            "quarter_pnl": {k: round(v, 2) for k, v in quarter_pnl.items()},
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
    parser.add_argument("--hours", type=float, default=6.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--top-seeds", type=int, default=10)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    workers = min(args.workers, 4)
    if args.reset:
        for f in [PROGRESS, RESULTS, REJECTIONS, KEEPERS, LOGFILE]:
            if f.exists():
                f.unlink()
    PIDFILE.write_text(str(os.getpid()), encoding="utf-8")
    logging.basicConfig(filename=str(LOGFILE), level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")

    grid = _build_grid(args.top_seeds)
    started = dt.datetime.now()
    deadline = started + dt.timedelta(hours=args.hours)

    state = {
        "started_at": started.isoformat(), "deadline_at": deadline.isoformat(),
        "total_combos": len(grid), "completed": 0, "passed_floors": 0,
        "rejected": 0, "keepers": 0, "best_edge_capture": None,
        "best_wide_pnl": None, "best_top5_pct": None, "best_positive_quarters": None,
        "current_pid": os.getpid(), "workers": workers,
        "last_update": started.isoformat(), "status": "running", "stage": 3,
        "top_seeds_used": args.top_seeds,
    }

    def _wp():
        tmp = PROGRESS.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        tmp.replace(PROGRESS)
    _wp()
    logging.info(f"S3 started: {len(grid)} combos, {workers} workers, deadline={deadline}")

    completed = 0
    keepers_n = 0
    best_wide = None

    with mp.Pool(workers) as pool:
        for r in pool.imap_unordered(evaluate_combo_robust, grid, chunksize=1):
            completed += 1
            if dt.datetime.now() > deadline:
                state["status"] = "deadline_reached"
                _wp()
                pool.terminate()
                break
            if r["passed_floors"]:
                with RESULTS.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(r, default=str) + "\n")
                state["passed_floors"] += 1
                wp = r.get("wide_pnl")
                if wp is not None and (best_wide is None or wp > best_wide[0]):
                    best_wide = (wp, r["combo"])
                    state["best_wide_pnl"] = wp
                    state["best_top5_pct"] = r["top5_pct"]
                    state["best_positive_quarters"] = r["positive_quarters"]
                    keepers_n += 1
                    state["keepers"] = keepers_n
                    with KEEPERS.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(r, default=str) + "\n")
                    logging.info(f"S3 KEEPER #{keepers_n}: wide=${wp:.0f} edge=${r['edge_capture']:.0f} top5%={r['top5_pct']*100:.0f}% Q+={r['positive_quarters']}")
                if state["best_edge_capture"] is None or r["edge_capture"] > state["best_edge_capture"]:
                    state["best_edge_capture"] = r["edge_capture"]
            else:
                with REJECTIONS.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(r, default=str) + "\n")
                state["rejected"] += 1
            state["completed"] = completed
            state["last_update"] = dt.datetime.now().isoformat()
            if completed % 5 == 0:
                _wp()

    state["status"] = "completed" if state["status"] == "running" else state["status"]
    state["completed_at"] = dt.datetime.now().isoformat()
    _wp()
    if PIDFILE.exists():
        PIDFILE.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
