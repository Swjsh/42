"""v15.3 Full window backtest — runs 16-month window and quarterly breakdown.

Produces quarterly P&L, sharpe, concentration, and OOS test result.
Writes to analysis/recommendations/v15_3_window_check.json.
"""
from __future__ import annotations
import datetime as dt
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner
from autoresearch.metrics import compute_metrics, daily_pnl_series

PARAMS_V151 = {
    "premium_stop_pct_bear": -0.20,
    "premium_stop_pct_bull": -0.08,
    "tp1_premium_pct": 0.75,
    "tp1_qty_fraction": 0.50,
    "runner_target_premium_pct": 2.50,
    "f9_vol_mult": 0.7,
    "min_triggers_bear": 1,
    "min_triggers_bull": 2,
    "strike_offset_bear": -2,
    "strike_offset_bull": -2,
    "vix_bear_threshold": 17.30,
    "ribbon_spread_min_cents": 30,
    "profit_lock_threshold_pct": 0.05,
    "profit_lock_stop_offset_pct": 0.20,
}

FULL_START = dt.date(2025, 1, 1)
FULL_END = dt.date(2026, 5, 15)
TRAIN_END = dt.date(2025, 12, 31)
TEST_START = dt.date(2026, 1, 1)


def quarterly_pnl(trades) -> dict:
    by_q = defaultdict(float)
    for t in trades:
        ts = t.entry_time_et
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        if hasattr(ts, "tzinfo") and ts.tzinfo:
            ts = ts.replace(tzinfo=None)
        q = f"{ts.year}-Q{(ts.month-1)//3+1}"
        by_q[q] += float(t.dollar_pnl)
    return {k: round(v, 2) for k, v in sorted(by_q.items())}


def top5_concentration(trades) -> float:
    if not trades:
        return 0.0
    daily = daily_pnl_series(trades)
    total = sum(daily.values())
    if total <= 0:
        return float("inf")
    top5 = sum(sorted(daily.values(), reverse=True)[:5])
    return round(top5 / total * 100, 1)


def main():
    print("="*72)
    print("v15.3 Full Window Check")
    print("="*72)

    spy, vix = runner.load_data(FULL_START, FULL_END)
    print(f"Data loaded: {len(spy):,} SPY rows, {len(vix):,} VIX rows")

    results = {}

    print("\n--- Full window (2025-01-01 to 2026-05-15) ---")
    r_full, m_full = runner.run_with_params(PARAMS_V151, FULL_START, FULL_END, spy, vix)
    print(f"  n_trades={m_full.n_trades}  pnl=${m_full.total_pnl:.0f}  "
          f"sharpe={m_full.sharpe_daily:.3f}  wr={m_full.win_rate:.2%}  dd=${m_full.max_drawdown:.0f}")
    q_full = quarterly_pnl(r_full.trades)
    conc = top5_concentration(r_full.trades)
    for q, p in q_full.items():
        print(f"  {q}: ${p:+.0f}")
    print(f"  top-5 concentration: {conc:.1f}%")

    results["full"] = {
        "n_trades": m_full.n_trades, "total_pnl": round(m_full.total_pnl, 2),
        "sharpe": round(m_full.sharpe_daily, 4), "win_rate": round(m_full.win_rate, 4),
        "max_drawdown": round(m_full.max_drawdown, 2), "top5_pct": conc,
        "quarterly": q_full,
    }

    print("\n--- Train window (2025-01-01 to 2025-12-31) ---")
    r_train, m_train = runner.run_with_params(PARAMS_V151, FULL_START, TRAIN_END, spy, vix)
    print(f"  n_trades={m_train.n_trades}  pnl=${m_train.total_pnl:.0f}  "
          f"sharpe={m_train.sharpe_daily:.3f}")
    results["train"] = {
        "n_trades": m_train.n_trades, "total_pnl": round(m_train.total_pnl, 2),
        "sharpe": round(m_train.sharpe_daily, 4),
    }

    print("\n--- Test window (2026-01-01 to 2026-05-15) ---")
    r_test, m_test = runner.run_with_params(PARAMS_V151, TEST_START, FULL_END, spy, vix)
    print(f"  n_trades={m_test.n_trades}  pnl=${m_test.total_pnl:.0f}  "
          f"sharpe={m_test.sharpe_daily:.3f}")
    results["test"] = {
        "n_trades": m_test.n_trades, "total_pnl": round(m_test.total_pnl, 2),
        "sharpe": round(m_test.sharpe_daily, 4),
    }

    out_path = ROOT / "analysis" / "recommendations" / "v15_3_window_check.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"generated_at": dt.datetime.now().isoformat(),
                                     "results": results}, indent=2), encoding="utf-8")
    print(f"\nWrote: {out_path}")

    # Gate checks
    quarters_needed = ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1"]
    gate2 = all(q_full.get(q, -999) > 0 for q in quarters_needed)
    gate1 = m_test.total_pnl > 0
    print(f"\nGate 1 (OOS test positive): {'PASS' if gate1 else 'FAIL'}  (${m_test.total_pnl:.0f})")
    print(f"Gate 2 (all 5 quarters positive): {'PASS' if gate2 else 'FAIL'}")
    for q in quarters_needed:
        p = q_full.get(q, None)
        ok = p is not None and p > 0
        print(f"  {q}: ${p:+.0f}  {'ok' if ok else 'NEGATIVE'}")
    print(f"Gate 5 (concentration < 200%): {'PASS' if conc < 200 else 'WARN'}  ({conc:.1f}%)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
