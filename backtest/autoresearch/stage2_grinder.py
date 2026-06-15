"""Stage-2 grinder — refine around stage-1 top-5 keepers.

Reads keepers.jsonl from the stage-1 grinder, picks the top 5 by combined rank
(edge_capture rank + wide_pnl rank), and generates a tighter parameter
neighborhood around each. Same evaluation pipeline (J-edge + 16mo aggregate),
same floor protection.

This is meant to be launched MANUALLY in the morning after stage-1 finishes,
not by the hourly monitor. Because it depends on stage-1 results.

Usage:
    pythonw.exe -m autoresearch.stage2_grinder --hours 4 --workers 4

Per CLAUDE.md OP 17: GRIND-UNTIL-DONE. Stage 2 keeps grinding after stage 1
without asking permission.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import multiprocessing as mp
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    _pw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _pw.exists():
        mp.set_executable(str(_pw))

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "autoresearch" / "_state" / "overnight_grinder"
STAGE2_DIR = REPO / "autoresearch" / "_state" / "stage2_grinder"
STAGE2_DIR.mkdir(parents=True, exist_ok=True)

PROGRESS = STAGE2_DIR / "progress.json"
RESULTS = STAGE2_DIR / "results.jsonl"
REJECTIONS = STAGE2_DIR / "rejections.jsonl"
KEEPERS = STAGE2_DIR / "keepers.jsonl"
PIDFILE = STAGE2_DIR / "runner.pid"
LOGFILE = STAGE2_DIR / "grinder.log"

BASELINE_4_29 = 372.0
BASELINE_5_04 = 2418.0


def _load_top_keepers(top_n: int = 5) -> list[dict]:
    """Pick top-N keepers from stage 1 by combined edge+wide rank."""
    keepers_path = OUT_DIR / "keepers.jsonl"
    if not keepers_path.exists():
        raise SystemExit("stage 1 keepers.jsonl missing — run stage 1 first")
    rows = []
    for line in keepers_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    if not rows:
        raise SystemExit("no keepers in stage 1 yet — wait for stage 1 to find some")
    edge_rank = {id(r): i for i, r in enumerate(sorted(rows, key=lambda r: -r.get("edge_capture", 0)))}
    wide_rank = {id(r): i for i, r in enumerate(sorted(rows, key=lambda r: -r.get("wide_pnl", 0)))}
    rows.sort(key=lambda r: edge_rank[id(r)] + wide_rank[id(r)])
    return [r["combo"] for r in rows[:top_n]]


def _refine_combo(seed: dict) -> list[dict]:
    """Generate a small neighborhood of variations around a seed combo.

    Each numeric knob varies by ±1 step on a tight grid. Categorical knobs
    (none here) would enumerate.
    """
    combos = []
    super_stops = [seed["super_stop"], seed["super_stop"] - 0.025, seed["super_stop"] + 0.025]
    super_tp1s = [seed["super_tp1"], seed["super_tp1"] - 0.10, seed["super_tp1"] + 0.10]
    runner_targets = [seed["runner_target"], seed["runner_target"] - 0.25, seed["runner_target"] + 0.25]
    level_qtys = [seed["level_qty"], seed["level_qty"] - 2, seed["level_qty"] + 2]
    level_stops = [seed["level_stop"]]   # already explored well in stage 1
    level_tp1s = [seed["level_tp1"]]
    trendline_stops = [seed["trendline_stop"]]

    for ss in super_stops:
        if ss < -0.30 or ss > -0.10: continue   # preserve range
        for stp1 in super_tp1s:
            if stp1 < 0.40 or stp1 > 1.20: continue
            for rt in runner_targets:
                if rt < 1.5 or rt > 3.5: continue
                for lq in level_qtys:
                    if lq < 15 or lq > 30: continue
                    for ls in level_stops:
                        for ltp in level_tp1s:
                            for ts in trendline_stops:
                                combo = {
                                    "super_stop": round(ss, 3),
                                    "super_tp1": round(stp1, 3),
                                    "runner_target": round(rt, 3),
                                    "level_qty": int(lq),
                                    "level_stop": ls,
                                    "level_tp1": ltp,
                                    "trendline_stop": ts,
                                }
                                combos.append(combo)
    return combos


def _build_grid(top_n: int) -> list[dict]:
    seeds = _load_top_keepers(top_n)
    seen = set()
    grid = []
    for s in seeds:
        for c in _refine_combo(s):
            key = json.dumps(c, sort_keys=True)
            if key not in seen:
                seen.add(key)
                grid.append(c)
    return grid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=4.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--top-seeds", type=int, default=5)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    workers = min(args.workers, 4)

    if args.reset:
        for f in [PROGRESS, RESULTS, REJECTIONS, KEEPERS, LOGFILE]:
            if f.exists():
                f.unlink()

    PIDFILE.write_text(str(os.getpid()), encoding="utf-8")
    logging.basicConfig(
        filename=str(LOGFILE),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    grid = _build_grid(args.top_seeds)
    started = dt.datetime.now()
    deadline = started + dt.timedelta(hours=args.hours)

    state = {
        "started_at": started.isoformat(),
        "deadline_at": deadline.isoformat(),
        "total_combos": len(grid),
        "completed": 0,
        "passed_floors": 0,
        "rejected": 0,
        "keepers": 0,
        "best_edge_capture": None,
        "best_wide_pnl": None,
        "current_pid": os.getpid(),
        "workers": workers,
        "last_update": started.isoformat(),
        "status": "running",
        "stage": 2,
        "top_seeds_used": args.top_seeds,
    }

    def _write_progress():
        tmp = PROGRESS.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        tmp.replace(PROGRESS)

    _write_progress()
    logging.info(f"Stage 2 started: {len(grid)} combos, {workers} workers, deadline={deadline}")

    from autoresearch.overnight_grinder import evaluate_combo

    completed = 0
    keepers_n = 0
    best_wide = None

    with mp.Pool(workers) as pool:
        for result in pool.imap_unordered(evaluate_combo, grid, chunksize=1):
            completed += 1
            if dt.datetime.now() > deadline:
                state["status"] = "deadline_reached"
                _write_progress()
                pool.terminate()
                break

            if result["passed_floors"]:
                with RESULTS.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(result, default=str) + "\n")
                state["passed_floors"] += 1
                wp = result.get("wide_pnl")
                if wp is not None and (best_wide is None or wp > best_wide[0]):
                    best_wide = (wp, result["combo"])
                    state["best_wide_pnl"] = wp
                    keepers_n += 1
                    state["keepers"] = keepers_n
                    with KEEPERS.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(result, default=str) + "\n")
                    logging.info(f"S2 KEEPER #{keepers_n}: wide=${wp:.0f} edge=${result['edge_capture']:.0f}")
                if state["best_edge_capture"] is None or result["edge_capture"] > state["best_edge_capture"]:
                    state["best_edge_capture"] = result["edge_capture"]
            else:
                with REJECTIONS.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(result, default=str) + "\n")
                state["rejected"] += 1

            state["completed"] = completed
            state["last_update"] = dt.datetime.now().isoformat()
            if completed % 5 == 0:
                _write_progress()

    state["status"] = "completed" if state["status"] == "running" else state["status"]
    state["completed_at"] = dt.datetime.now().isoformat()
    _write_progress()
    if PIDFILE.exists():
        PIDFILE.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
