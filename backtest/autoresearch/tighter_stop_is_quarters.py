"""
IS quarterly breakdown for stop=-0.10 vs stop=-0.20.

Splits the 16-month IS period into 6 sub-windows to test robustness.
The OOS sub-window showed all improvement concentrated in Week2 (May 15-22).
This script tests whether IS improvement is spread across all quarters
or also concentrated in catastrophic months (Apr-26, Mar-26, etc.).

If improvement is spread: robust mechanism.
If concentrated in catastrophic months only: regime-bet, not durable.
"""
from __future__ import annotations
import sys
import pathlib
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START = dt.date(2025, 1, 2)
IS_END   = dt.date(2026, 5, 7)

QUARTERS = [
    ("Q1-2025", dt.date(2025, 1, 1),  dt.date(2025, 4, 1)),
    ("Q2-2025", dt.date(2025, 4, 1),  dt.date(2025, 7, 1)),
    ("Q3-2025", dt.date(2025, 7, 1),  dt.date(2025, 10, 1)),
    ("Q4-2025", dt.date(2025, 10, 1), dt.date(2026, 1, 1)),
    ("Q1-2026", dt.date(2026, 1, 1),  dt.date(2026, 4, 1)),
    ("Apr-26",  dt.date(2026, 4, 1),  dt.date(2026, 5, 8)),  # catastrophic month
]

CAT_MONTHS = {"2026-04", "2026-03", "2025-11", "2026-01", "2025-05", "2025-03"}

BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
)


def _tz_naive(t):
    et = t.entry_time_et
    return et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et


def _split(trades, start, end):
    return [t for t in trades if start <= _tz_naive(t).date() < end]


if __name__ == "__main__":
    print("=" * 90)
    print("IS QUARTERLY BREAKDOWN: stop=-0.10 vs stop=-0.20 BEARISH_REVERSAL")
    print("=" * 90)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n[1/2] IS@-0.20 baseline...")
    r20 = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                       premium_stop_pct_bear=-0.20, **BASE)
    t20 = r20.trades
    print(f"  n={len(t20)}  pnl={sum(t.dollar_pnl for t in t20):+.2f}")

    print("\n[2/2] IS@-0.10 candidate...")
    r10 = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                       premium_stop_pct_bear=-0.10, **BASE)
    t10 = r10.trades
    print(f"  n={len(t10)}  pnl={sum(t.dollar_pnl for t in t10):+.2f}")

    print("\n" + "=" * 90)
    print("QUARTERLY BREAKDOWN")
    print(f"\n  {'Quarter':>10}  {'n@-0.20':>8}  {'pnl@-0.20':>11}  {'n@-0.10':>8}  {'pnl@-0.10':>11}  {'delta':>9}  Cat")
    print("  " + "-" * 72)

    total_delta_cat = 0
    total_delta_norm = 0
    for label, qstart, qend in QUARTERS:
        q20 = _split(t20, qstart, qend)
        q10 = _split(t10, qstart, qend)
        pnl20 = sum(t.dollar_pnl for t in q20)
        pnl10 = sum(t.dollar_pnl for t in q10)
        delta = pnl10 - pnl20
        n20   = len(q20)
        n10   = len(q10)
        # Is this quarter mostly catastrophic months?
        cat_months_in_q = [
            _tz_naive(t).date().strftime("%Y-%m")
            for t in q20
            if (_tz_naive(t).date().strftime("%Y-%m")) in CAT_MONTHS
        ]
        is_cat = len(cat_months_in_q) > len(q20) // 2 if q20 else False
        cat_label = "CAT" if is_cat else ""
        print(f"  {label:>10}  {n20:>8}  {pnl20:>+11.0f}  {n10:>8}  {pnl10:>+11.0f}  {delta:>+9.0f}  {cat_label}")
        if is_cat:
            total_delta_cat += delta
        else:
            total_delta_norm += delta

    pnl20_total = sum(t.dollar_pnl for t in t20)
    pnl10_total = sum(t.dollar_pnl for t in t10)
    delta_total  = pnl10_total - pnl20_total
    print(f"  {'TOTAL':>10}  {len(t20):>8}  {pnl20_total:>+11.0f}  {len(t10):>8}  {pnl10_total:>+11.0f}  {delta_total:>+9.0f}")

    print(f"\n  Delta from CAT quarters: {total_delta_cat:+.0f}")
    print(f"  Delta from NORM quarters: {total_delta_norm:+.0f}")
    pct_from_cat = total_delta_cat / delta_total * 100 if delta_total else 0
    print(f"  CAT % of total delta: {pct_from_cat:.0f}%")

    print("\n" + "=" * 90)
    print("VERDICT")
    if pct_from_cat < 70:
        print("  ROBUST: improvement spread across both CAT and NORM quarters (< 70% in CAT).")
        print("  Tighter stop saves money in normal conditions, not just catastrophic ones.")
    else:
        print(f"  REGIME-BET: {pct_from_cat:.0f}% of improvement from CAT quarters only.")
        print("  Tighter stop primarily helps during catastrophic drawdowns — not a universal improvement.")
        print("  Consider: VIX-conditional stop (tighter when VIX is elevated) instead of global change.")

    print("\nANALYSIS COMPLETE.")
