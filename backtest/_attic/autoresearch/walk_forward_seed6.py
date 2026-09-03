"""Walk-forward analysis for seed 6 (v15 winner).

Tests the strategy across rolling time windows to detect regime-dependence.
For each window step:
  - Run the engine with seed 6 params
  - Record P&L, sharpe, n_trades

This validates that v15 isn't just lucky in one quarter -- it should
produce CONSISTENT positive expectancy across most rolling windows.

Output: analysis/recommendations/v15-walk-forward.json
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import multiprocessing as mp
import os
import sys
import sys

# Use pythonw.exe (no console flash on workers).
if sys.platform == 'win32':
    _pw = __import__('pathlib').Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _pw.exists():
        mp.set_executable(str(_pw))
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import config, runner, random_eval

REPO = Path(__file__).resolve().parent.parent
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "v15-walk-forward.json"
MAX_PARALLEL = 4

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Walk-forward windows. 30-day rolling tests across 16 months of data.
# Each window is independent so the engine sees a fresh slice without overlap.
WINDOWS = []
data_start = dt.date(2025, 1, 1)
data_end = dt.date(2026, 5, 7)
window_size_days = 30
step_days = 30  # non-overlapping; change to 15 for overlapping windows
cur = data_start
while cur + dt.timedelta(days=window_size_days) <= data_end:
    end = cur + dt.timedelta(days=window_size_days)
    WINDOWS.append({"start": cur.isoformat(), "end": end.isoformat()})
    cur = cur + dt.timedelta(days=step_days)


@dataclass(frozen=True)
class WindowJob:
    start_iso: str
    end_iso: str


_WORKER_SPY = None
_WORKER_VIX = None


def _worker_init() -> None:
    global _WORKER_SPY, _WORKER_VIX
    _WORKER_SPY, _WORKER_VIX = runner.load_data(data_start, data_end)


def _worker_run(job: WindowJob) -> dict:
    params = random_eval.generate_params(6)
    s = dt.date.fromisoformat(job.start_iso)
    e = dt.date.fromisoformat(job.end_iso)
    try:
        _, m = runner.run_with_params(params, s, e, _WORKER_SPY, _WORKER_VIX)
        return {
            "start": job.start_iso, "end": job.end_iso,
            "n_trades": m.n_trades, "win_rate": round(m.win_rate, 4),
            "total_pnl": round(m.total_pnl, 2), "sharpe": round(m.sharpe_daily, 3),
            "wl_ratio": round(m.wl_ratio, 2) if m.wl_ratio else None,
            "max_drawdown": round(m.max_drawdown, 2),
            "n_days_traded": m.n_days_traded,
        }
    except Exception as exc:  # noqa: BLE001
        return {"start": job.start_iso, "end": job.end_iso, "error": repr(exc)}


def main() -> int:
    logger.info("Walk-forward analysis: %d windows x %d-day each (seed 6)",
                len(WINDOWS), window_size_days)

    jobs = [WindowJob(w["start"], w["end"]) for w in WINDOWS]
    results = []
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=MAX_PARALLEL, initializer=_worker_init) as pool:
        for r in pool.imap_unordered(_worker_run, jobs, chunksize=1):
            results.append(r)
            if "error" in r:
                logger.error("[%s..%s] ERROR: %s", r["start"], r["end"], r["error"])
            else:
                logger.info("[%s..%s] n=%d pnl=$%+.0f sh=%+.2f wr=%d%%",
                            r["start"], r["end"], r["n_trades"], r["total_pnl"],
                            r["sharpe"], int(r["win_rate"] * 100))

    # Sort by start date
    results.sort(key=lambda x: x.get("start", ""))

    # Aggregate
    valid = [r for r in results if "error" not in r]
    n_pos_pnl = sum(1 for r in valid if r["total_pnl"] > 0)
    n_pos_sh = sum(1 for r in valid if r["sharpe"] > 0)
    avg_pnl = sum(r["total_pnl"] for r in valid) / len(valid) if valid else 0
    total_pnl = sum(r["total_pnl"] for r in valid)
    total_trades = sum(r["n_trades"] for r in valid)

    summary = {
        "candidate": "v15-seed6",
        "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "n_windows": len(WINDOWS),
        "window_size_days": window_size_days,
        "step_days": step_days,
        "n_pos_pnl": n_pos_pnl,
        "n_pos_sharpe": n_pos_sh,
        "pos_pnl_pct": round(n_pos_pnl / len(valid), 3) if valid else 0,
        "avg_window_pnl": round(avg_pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "total_trades": total_trades,
        "by_window": results,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("=" * 60)
    logger.info("WALK-FORWARD DONE: %d/%d windows positive PnL (%.0f%%), %d/%d positive sharpe",
                n_pos_pnl, len(valid), summary["pos_pnl_pct"] * 100, n_pos_sh, len(valid))
    logger.info("  Avg window P&L: $%+.0f  | Total P&L: $%+.0f  | Total trades: %d",
                avg_pnl, total_pnl, total_trades)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
