"""SNIPER CS OOS monthly breakdown.

Break down the SNIPER CS BASELINE performance month-by-month across the full
IS + OOS window to identify which months drive the OOS failure (-$3,291 baseline).

IS:  2025-01-01 to 2025-10-31
OOS: 2025-11-01 to 2026-05-22

Usage:
    python backtest/autoresearch/sniper_cs_monthly_breakdown.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

from autoresearch.runner import load_data
from autoresearch.sniper_cs_evaluator import SniperCSCombo, run_sniper_cs_day

import datetime as dt
import pandas as pd


BEST_COMBO = SniperCSCombo(
    chart_stop_buffer=1.0,
    tp1_r=2.5,
    runner_r=3.0,
    strike_offset=0,
    vix_min=0.0,
    vix_trending=False,
)


def monthly_breakdown(start: dt.date, end: dt.date, spy_df: pd.DataFrame, vix_df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    spy_df = spy_df.copy()
    spy_df["_date"] = spy_df["timestamp_et"].dt.date
    trading_dates = sorted(spy_df["_date"].unique())
    trading_dates = [d for d in trading_dates if start <= d <= end]

    month_trades: dict[str, list] = {}
    for d in trading_dates:
        day_trades = run_sniper_cs_day(d, spy_df, vix_df, BEST_COMBO)
        if not day_trades:
            continue
        key = d.strftime("%Y-%m")
        month_trades.setdefault(key, []).extend(day_trades)

    for key in sorted(month_trades):
        trades = month_trades[key]
        pnl = sum(t.dollar_pnl for t in trades)
        n = len(trades)
        wins = sum(1 for t in trades if t.dollar_pnl > 0)
        rows.append({"month": key, "n": n, "pnl": round(pnl, 2), "wr": round(wins / n, 3) if n else 0})

    return rows


def _parse_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["timestamp_et"] = (
        pd.to_datetime(df["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    return df


def main():
    spy_raw, vix_raw = load_data(dt.date(2025, 1, 1), dt.date(2026, 5, 22))
    spy = _parse_timestamps(spy_raw)
    vix = _parse_timestamps(vix_raw)

    IS_START = dt.date(2025, 1, 1)
    IS_END = dt.date(2025, 10, 31)
    OOS_START = dt.date(2025, 11, 1)
    OOS_END = dt.date(2026, 5, 22)

    print("=== IS MONTHLY BREAKDOWN (2025-01 to 2025-10) ===")
    is_rows = monthly_breakdown(IS_START, IS_END, spy, vix)
    is_total_pnl = 0.0
    is_total_n = 0
    for r in is_rows:
        print(f"  {r['month']}  n={r['n']:3d}  pnl={r['pnl']:>8.0f}  WR={r['wr']:.0%}")
        is_total_pnl += r["pnl"]
        is_total_n += r["n"]
    print(f"  IS TOTAL: n={is_total_n}  pnl=${is_total_pnl:.0f}")

    print()
    print("=== OOS MONTHLY BREAKDOWN (2025-11 to 2026-05) ===")
    oos_rows = monthly_breakdown(OOS_START, OOS_END, spy, vix)
    oos_total_pnl = 0.0
    oos_total_n = 0
    for r in oos_rows:
        flag = " << LOSS" if r["pnl"] < -500 else (" << MARGINAL" if r["pnl"] < 0 else "")
        print(f"  {r['month']}  n={r['n']:3d}  pnl={r['pnl']:>8.0f}  WR={r['wr']:.0%}{flag}")
        oos_total_pnl += r["pnl"]
        oos_total_n += r["n"]
    print(f"  OOS TOTAL: n={oos_total_n}  pnl=${oos_total_pnl:.0f}")

    out = {
        "combo": {"chart_stop_buffer": BEST_COMBO.chart_stop_buffer, "tp1_r": BEST_COMBO.tp1_r,
                  "runner_r": BEST_COMBO.runner_r, "strike_offset": BEST_COMBO.strike_offset},
        "is_months": is_rows,
        "oos_months": oos_rows,
        "is_total": {"n": is_total_n, "pnl": round(is_total_pnl, 2)},
        "oos_total": {"n": oos_total_n, "pnl": round(oos_total_pnl, 2)},
    }
    out_path = ROOT / "analysis" / "recommendations" / "sniper-cs-baseline-monthly.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
