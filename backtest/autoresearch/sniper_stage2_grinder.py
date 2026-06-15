"""SNIPER Stage 2 grinder — refine around Stage 1 top keepers.

Reads keepers.jsonl from sniper_stage1, picks top-N by combined edge_capture +
wide_pnl rank, generates ±1-step neighborhood around each. Uses the same
evaluate_sniper_combo evaluator so floors + OP 19 default metrics carry through.

CLI:
    pythonw.exe -m autoresearch.sniper_stage2_grinder --hours 3 --workers 4 --top-n 5
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import multiprocessing as mp
import os
import random
import sys
from pathlib import Path

if sys.platform == "win32":
    _pw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _pw.exists():
        mp.set_executable(str(_pw))

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

STAGE1_DIR = REPO / "autoresearch" / "_state" / "sniper_stage1"
OUT_DIR = REPO / "autoresearch" / "_state" / "sniper_stage2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROGRESS = OUT_DIR / "progress.json"
RESULTS = OUT_DIR / "results.jsonl"
REJECTIONS = OUT_DIR / "rejections.jsonl"
KEEPERS = OUT_DIR / "keepers.jsonl"
PIDFILE = OUT_DIR / "runner.pid"
LOGFILE = OUT_DIR / "grinder.log"


def _setup_logging() -> None:
    logging.basicConfig(
        filename=str(LOGFILE), level=logging.INFO,
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


def _load_top_keepers(top_n: int = 5) -> list[dict]:
    """Pick top-N Stage-1 keepers by combined edge_capture + wide_pnl rank."""
    kp = STAGE1_DIR / "keepers.jsonl"
    if not kp.exists():
        raise SystemExit("sniper_stage1/keepers.jsonl missing — run Stage 1 first")
    rows: list[dict] = []
    for line in kp.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    if not rows:
        raise SystemExit("no keepers in Stage 1 — wait for one")
    edge_rank = {id(r): i for i, r in enumerate(sorted(rows, key=lambda r: -r.get("edge_capture", 0)))}
    wide_rank = {id(r): i for i, r in enumerate(sorted(rows, key=lambda r: -r.get("wide_pnl", 0)))}
    rows.sort(key=lambda r: edge_rank[id(r)] + wide_rank[id(r)])
    return [r["combo"] for r in rows[:top_n]]


def _refine_combo(seed: dict) -> list[dict]:
    """Generate ±1-step variations around a seed combo. Numeric knobs only."""
    out: list[dict] = []
    vol_mults = sorted(set([seed["vol_mult"], seed["vol_mult"] - 0.2, seed["vol_mult"] + 0.2]))
    body_cents = sorted(set([seed["body_min_cents"], max(0.02, seed["body_min_cents"] - 0.03), seed["body_min_cents"] + 0.03]))
    stops = sorted(set([seed["premium_stop_pct"], seed["premium_stop_pct"] - 0.02, seed["premium_stop_pct"] + 0.02]))
    tp1s = sorted(set([seed["tp1_premium_pct"], seed["tp1_premium_pct"] - 0.05, seed["tp1_premium_pct"] + 0.05]))
    runners = sorted(set([seed["runner_target_pct"], seed["runner_target_pct"] - 0.25, seed["runner_target_pct"] + 0.5]))
    lock_thr = sorted(set([seed["profit_lock_threshold_pct"], max(0.0, seed["profit_lock_threshold_pct"] - 0.05), seed["profit_lock_threshold_pct"] + 0.05]))
    lock_off = sorted(set([seed["profit_lock_stop_offset_pct"], max(-0.02, seed["profit_lock_stop_offset_pct"] - 0.02), seed["profit_lock_stop_offset_pct"] + 0.03]))

    for vm in vol_mults:
        if vm < 1.0 or vm > 2.5: continue
        for bc in body_cents:
            if bc < 0.02 or bc > 0.25: continue
            for st in stops:
                if st < -0.20 or st > -0.04: continue
                for tp in tp1s:
                    if tp < 0.20 or tp > 0.60: continue
                    for rt in runners:
                        if rt < 0.5 or rt > 4.0: continue
                        for lt in lock_thr:
                            if lt > 0.40: continue
                            for lo in lock_off:
                                if lo < -0.05 or lo > 0.15: continue
                                out.append({
                                    "vol_mult": round(vm, 3),
                                    "body_min_cents": round(bc, 3),
                                    "min_stars": seed["min_stars"],
                                    "strike_offset": seed["strike_offset"],
                                    "premium_stop_pct": round(st, 3),
                                    "tp1_premium_pct": round(tp, 3),
                                    "runner_target_pct": round(rt, 3),
                                    "profit_lock_threshold_pct": round(lt, 3),
                                    "profit_lock_stop_offset_pct": round(lo, 3),
                                    "tp1_qty_fraction": seed.get("tp1_qty_fraction", 0.667),
                                    "qty": seed.get("qty", 10),
                                    "proximity_dollars": seed.get("proximity_dollars", 1.5),
                                    "require_break_above_open": seed.get("require_break_above_open", True),
                                })
    return out


def _build_grid(top_n: int) -> list[dict]:
    seeds = _load_top_keepers(top_n)
    seen: set[str] = set()
    grid: list[dict] = []
    for s in seeds:
        for c in _refine_combo(s):
            k = json.dumps(c, sort_keys=True)
            if k not in seen:
                seen.add(k)
                grid.append(c)
    return grid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=3.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--top-n", type=int, default=5)
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
    grid = _build_grid(args.top_n)
    random.Random(2027).shuffle(grid)

    from autoresearch.sniper_evaluator import evaluate_sniper_combo

    started = dt.datetime.now()
    deadline = started + dt.timedelta(hours=args.hours)
    state = {
        "started_at": started.isoformat(), "deadline_at": deadline.isoformat(),
        "total_combos": len(grid), "completed": 0, "passed_floors": 0,
        "rejected": 0, "keepers": 0, "best_edge_capture": 0.0,
        "best_wide_pnl": None, "current_pid": os.getpid(), "workers": workers,
        "last_update": started.isoformat(), "status": "running",
    }
    _write_progress(state)
    logging.info(f"Sniper Stage 2 started: {len(grid)} combos, {workers} workers, deadline={deadline}")

    completed = 0; keepers_n = 0; best_wide: tuple[float, dict] | None = None
    with mp.Pool(workers) as pool:
        for result in pool.imap_unordered(evaluate_sniper_combo, grid, chunksize=1):
            completed += 1
            if dt.datetime.now() > deadline:
                state["status"] = "deadline_reached"; _write_progress(state); pool.terminate(); break
            if result["passed_floors"]:
                _append_jsonl(RESULTS, result); state["passed_floors"] += 1
                wp = result.get("wide_pnl")
                if wp is not None and (best_wide is None or wp > best_wide[0]):
                    best_wide = (wp, result["combo"]); state["best_wide_pnl"] = wp
                    keepers_n += 1; state["keepers"] = keepers_n
                    _append_jsonl(KEEPERS, result)
                    logging.info(f"KEEPER #{keepers_n} wide=${wp:.0f} edge=${result['edge_capture']:.0f} combo={result['combo']}")
                if result["edge_capture"] > state["best_edge_capture"]:
                    state["best_edge_capture"] = result["edge_capture"]
            else:
                _append_jsonl(REJECTIONS, result); state["rejected"] += 1
            state["completed"] = completed
            state["last_update"] = dt.datetime.now().isoformat()
            if completed % 5 == 0: _write_progress(state)
    state["status"] = "completed" if state["status"] == "running" else state["status"]
    state["completed_at"] = dt.datetime.now().isoformat()
    _write_progress(state)
    if PIDFILE.exists(): PIDFILE.unlink()
    logging.info(f"Sniper Stage 2 done: {completed}/{len(grid)} passed={state['passed_floors']} keepers={keepers_n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
