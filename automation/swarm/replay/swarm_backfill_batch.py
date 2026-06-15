"""
Idempotent swarm backfill batch — runs N days of replay per invocation.

Designed for overnight wake fires. Each fire calls:
  python swarm_backfill_batch.py --batch-size 12

State lives in: analysis/swarm-benchmark/backfill-state.json
Target: 63 trading days 2026-02-09 → 2026-05-10 (5/11-5/15 already done via live grader).

Cost: ~$0.07/day (4 Haiku specialist + 1 Haiku validator + 1 Sonnet synthesis).
Budget: $6 total cap (63 days × $0.07 ≈ $4.41).
Per fire: 12 days × $0.07 ≈ $0.84 (5-6 fires to complete full backfill).

Safety:
  - Never touches automation/state/* or automation/swarm/state/*
  - Idempotent: skips days with existing replay-{date}-0600/swarm_output.json
  - Exits cleanly if batch-size exhausted or budget cap reached
  - Writes progress to backfill-state.json after each day

Usage:
  python swarm_backfill_batch.py                     # run 12 days
  python swarm_backfill_batch.py --batch-size 5      # run 5 days
  python swarm_backfill_batch.py --list-remaining    # show undone days
  python swarm_backfill_batch.py --grade-only        # just re-grade, no replay
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# CREATE_NO_WINDOW = 0x08000000 — suppress conhost on Windows subprocess spawns. OP-27 L41.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

WORK_DIR = Path(__file__).parent.parent.parent.parent.resolve()
BENCHMARK_BASE = WORK_DIR / "analysis" / "swarm-benchmark"
STATE_FILE = BENCHMARK_BASE / "backfill-state.json"
RUNNER = Path(__file__).parent / "runner_replay.py"
GRADER = Path(__file__).parent / "grader_replay.py"
SPY_CSV = WORK_DIR / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-15.csv"

# All trading days to backfill (2026-02-09 → 2026-05-10).
# Already-done live days (5/11-5/15) are excluded — they have replay dirs already.
AS_OF = "06:00"
BUDGET_CAP_USD = 6.00   # total budget guard across all fires
COST_PER_DAY = 0.07    # approximate

# Days already completed by the live swarm grader
LIVE_DONE_DAYS = {
    "2026-05-11", "2026-05-12", "2026-05-13", "2026-05-14", "2026-05-15",
}


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[backfill {ts}] {msg}", flush=True)


def _get_trading_days() -> list[str]:
    """Return sorted list of trading days from SPY CSV in target range."""
    try:
        import pandas as pd
    except ImportError:
        _log("ERROR: pandas not available")
        return []
    df = pd.read_csv(str(SPY_CSV), usecols=["timestamp_et"])
    df["ts"] = pd.to_datetime(df["timestamp_et"])
    df["date"] = df["ts"].dt.date.astype(str)
    days = sorted(df[
        (df["date"] >= "2026-02-09") & (df["date"] <= "2026-05-10")
    ]["date"].unique())
    return days


def _load_state() -> dict:
    """Load backfill state (or create fresh)."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "completed_days": [],
        "failed_days": [],
        "total_cost_usd": 0.0,
        "started_at": None,
        "last_updated": None,
    }


def _save_state(state: dict) -> None:
    BENCHMARK_BASE.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _is_done(date_et: str) -> bool:
    """Return True if replay output exists for this date."""
    safe_asof = AS_OF.replace(":", "")
    replay_dir = BENCHMARK_BASE / f"replay-{date_et}-{safe_asof}"
    return (replay_dir / "swarm_output.json").exists()


def _run_day(date_et: str) -> tuple[bool, float]:
    """Run runner_replay.py for one date. Returns (success, cost_est)."""
    _log(f"Running replay for {date_et}")
    start = time.monotonic()
    cmd = [sys.executable, str(RUNNER), "--date", date_et, "--as-of", AS_OF]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(WORK_DIR),
            capture_output=False,
            timeout=600,  # 10 min max per day
            creationflags=_CREATE_NO_WINDOW,
        )
        elapsed = time.monotonic() - start
        safe_asof = AS_OF.replace(":", "")
        replay_dir = BENCHMARK_BASE / f"replay-{date_et}-{safe_asof}"
        success = result.returncode == 0 and (replay_dir / "swarm_output.json").exists()
        cost = COST_PER_DAY if success else 0.01  # best-effort estimate
        _log(f"  {date_et}: {'PASS' if success else 'FAIL'} in {elapsed:.0f}s (cost est ${cost:.2f})")
        return success, cost
    except subprocess.TimeoutExpired:
        _log(f"  {date_et}: TIMEOUT after 600s")
        return False, 0.01
    except Exception as e:
        _log(f"  {date_et}: ERROR {e}")
        return False, 0.0


def _run_grader() -> dict:
    """Run grader_replay.py --grade-all, return aggregate."""
    _log("Running grader --grade-all")
    cmd = [sys.executable, str(GRADER), "--grade-all"]
    try:
        subprocess.run(cmd, cwd=str(WORK_DIR), timeout=120, check=True, capture_output=False, creationflags=_CREATE_NO_WINDOW)
    except Exception as e:
        _log(f"  Grader error: {e}")
    # Read aggregate
    agg_path = BENCHMARK_BASE / "aggregate.json"
    if agg_path.exists():
        return json.loads(agg_path.read_text(encoding="utf-8"))
    return {}


def main(batch_size: int = 12, list_remaining: bool = False, grade_only: bool = False) -> int:
    all_days = _get_trading_days()
    if not all_days:
        _log("ERROR: no trading days found — check SPY CSV path")
        return 1

    state = _load_state()
    if state["started_at"] is None:
        state["started_at"] = datetime.now(timezone.utc).isoformat()

    # Done = live days + replay output exists + state records
    completed_set = set(state.get("completed_days", [])) | LIVE_DONE_DAYS
    failed_set = set(state.get("failed_days", []))
    total_cost = state.get("total_cost_usd", 0.0)

    # Remaining = not done, not failed
    remaining = [d for d in all_days if d not in completed_set and d not in failed_set
                 or (_is_done(d) and d not in completed_set)]
    # Also mark as done any that have swarm_output.json already
    newly_detected_done = [d for d in all_days if d not in completed_set and _is_done(d)]
    if newly_detected_done:
        _log(f"Detected {len(newly_detected_done)} already-done days via replay output")
        completed_set.update(newly_detected_done)
        state["completed_days"] = sorted(completed_set - LIVE_DONE_DAYS)
        _save_state(state)

    remaining = [d for d in all_days if d not in completed_set and d not in failed_set]

    _log(f"Status: {len(completed_set)} done ({len(LIVE_DONE_DAYS)} live + {len(completed_set)-len(LIVE_DONE_DAYS)} replay), {len(remaining)} remaining, {len(failed_set)} failed")
    _log(f"Budget used: ${total_cost:.2f} / ${BUDGET_CAP_USD:.2f}")

    if list_remaining:
        for d in remaining:
            print(d)
        return 0

    if grade_only:
        agg = _run_grader()
        _log(f"Grade-only complete: {agg.get('n_days_graded', '?')} days graded, accuracy {agg.get('direction', {}).get('accuracy_pct', '?')}%")
        return 0

    if total_cost >= BUDGET_CAP_USD:
        _log(f"BUDGET CAP REACHED (${total_cost:.2f} >= ${BUDGET_CAP_USD:.2f}). Run complete.")
        return 0

    if not remaining:
        _log("All days complete! Running final grade.")
        agg = _run_grader()
        n_graded = agg.get("n_days_graded", 0)
        accuracy = agg.get("direction", {}).get("accuracy_pct", 0)
        _log(f"BACKFILL COMPLETE: {n_graded} days graded, direction accuracy {accuracy:.1f}%")
        if accuracy < 55:
            _log("WARNING: direction accuracy < 55% — swarm regression flag")
        return 0

    # Process batch
    batch = remaining[:batch_size]
    _log(f"Processing batch of {len(batch)} days: {batch[0]} ... {batch[-1]}")
    session_cost = 0.0
    session_done = []
    session_failed = []

    for date_et in batch:
        if total_cost + session_cost >= BUDGET_CAP_USD:
            _log(f"Budget cap hit mid-batch (${total_cost + session_cost:.2f}). Stopping.")
            break
        success, cost = _run_day(date_et)
        session_cost += cost
        if success:
            session_done.append(date_et)
        else:
            session_failed.append(date_et)
        # Save state after each day (idempotent on crash)
        state["completed_days"] = sorted(
            (completed_set | set(session_done)) - LIVE_DONE_DAYS
        )
        state["failed_days"] = sorted(failed_set | set(session_failed))
        state["total_cost_usd"] = round(total_cost + session_cost, 3)
        _save_state(state)

    # Re-grade after batch
    agg = _run_grader()
    n_graded = agg.get("n_days_graded", 0)
    accuracy = agg.get("direction", {}).get("accuracy_pct", 0)

    _log(f"Batch done: {len(session_done)} new, {len(session_failed)} failed. "
         f"Total graded: {n_graded}. Accuracy: {accuracy:.1f}%. "
         f"Session cost: ${session_cost:.2f}. Cumulative: ${total_cost + session_cost:.2f}.")

    if accuracy < 55 and n_graded >= 20:
        _log("RED: direction accuracy < 55% over 20+ days — swarm regression")
    if n_graded >= 60:
        _log("DONE: backfill target of 60+ days reached")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Swarm backfill batch runner")
    parser.add_argument("--batch-size", type=int, default=12,
                        help="Days to process per run (default 12)")
    parser.add_argument("--list-remaining", action="store_true",
                        help="Print remaining days and exit")
    parser.add_argument("--grade-only", action="store_true",
                        help="Re-run grader only, no replay")
    args = parser.parse_args()
    sys.exit(main(
        batch_size=args.batch_size,
        list_remaining=args.list_remaining,
        grade_only=args.grade_only,
    ))
