"""
Rolling Walk-Forward Validation (FUTURE-IMPROVEMENTS #4).

Train on expanding IS windows, validate on rolling 30-day OOS windows.
Gives a more robust picture of strategy generalization across regimes.

Methodology:
  - Data: 2025-01-02 to 2026-05-22
  - Minimum IS: 6 months (before first OOS window)
  - OOS: each calendar month from Aug-2025 onwards (~30 trading days)
  - IS: all data before OOS start (expanding window)
  - Per-trade normalized WF: (oos_delta/n_oos) / (is_delta/n_is)
  - Gate: WF_norm >= 0.70 AND OOS pnl > 0

Output: per-window table + aggregate stats (OOS+%, median WF, robust WF estimate)

Security: read-only. No Alpaca calls.
"""
from __future__ import annotations
import sys
import pathlib
import datetime as dt
from typing import List, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

DATA_START = dt.date(2025, 1, 2)
DATA_END   = dt.date(2026, 5, 22)

# Minimum IS period before first OOS window
MIN_IS_MONTHS = 6  # first OOS window starts 2025-07-01

BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
)


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _add_months(d: dt.date, months: int) -> dt.date:
    m = d.month + months
    y = d.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    import calendar
    day = min(d.day, calendar.monthrange(y, m)[1])
    return dt.date(y, m, day)


def _first_trading_day_of_month(year: int, month: int, spy_dates: set) -> dt.date | None:
    """First date in spy_dates that falls in given year/month."""
    for day in range(1, 32):
        try:
            d = dt.date(year, month, day)
        except ValueError:
            break
        if d in spy_dates:
            return d
    return None


def _last_trading_day_of_month(year: int, month: int, spy_dates: set) -> dt.date | None:
    """Last date in spy_dates that falls in given year/month."""
    result = None
    for day in range(1, 32):
        try:
            d = dt.date(year, month, day)
        except ValueError:
            break
        if d in spy_dates:
            result = d
    return result


def _wf_norm(is_delta: float, n_is: int, oos_delta: float, n_oos: int) -> float:
    if n_is == 0 or n_oos == 0 or is_delta == 0:
        return 0.0
    return (oos_delta / n_oos) / (is_delta / n_is)


if __name__ == "__main__":
    print("=" * 100)
    print("ROLLING WALK-FORWARD VALIDATION")
    print(f"Data: {DATA_START} -> {DATA_END}")
    print(f"Minimum IS: {MIN_IS_MONTHS} months")
    print(f"OOS window: rolling 1-month each step")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    # Get set of trading dates from SPY data
    if "timestamp" in spy_df.columns:
        spy_dates = set(pd.to_datetime(spy_df["timestamp"]).dt.date)
    elif "date" in spy_df.columns:
        spy_dates = set(pd.to_datetime(spy_df["date"]).dt.date)
    else:
        # Try first column
        spy_dates = set(pd.to_datetime(spy_df.iloc[:, 0]).dt.date)

    # Build list of OOS months (expanding IS from 6mo onward)
    # First OOS start = July 2025 (6 months after Jan 2025)
    oos_windows: List[Tuple[dt.date, dt.date, dt.date, dt.date]] = []
    oos_year, oos_month = 2025, 7
    while True:
        oos_start = _first_trading_day_of_month(oos_year, oos_month, spy_dates)
        oos_end   = _last_trading_day_of_month(oos_year, oos_month, spy_dates)
        if oos_start is None or oos_end is None or oos_start > DATA_END:
            break
        oos_end = min(oos_end, DATA_END)
        is_start = DATA_START
        # IS ends one trading day before OOS starts
        is_trading_days = sorted(d for d in spy_dates if is_start <= d < oos_start)
        if not is_trading_days:
            break
        is_end = is_trading_days[-1]
        oos_windows.append((is_start, is_end, oos_start, oos_end))
        # Advance to next month
        oos_month += 1
        if oos_month > 12:
            oos_month = 1
            oos_year += 1

    print(f"\n{len(oos_windows)} OOS windows planned.")
    print(f"\n{'Window':12}  {'IS_end':12}  {'IS_n':>5}  {'IS_pnl':>9}  {'OOS_start':11}  {'OOS_end':11}  {'OOS_n':>5}  {'OOS_pnl':>9}  {'WF_norm':>8}  {'Verdict'}")
    print("-" * 110)

    results = []
    full_is_pnl = None
    full_is_n = None

    for is_start, is_end, oos_start, oos_end in oos_windows:
        label = f"{oos_start.strftime('%Y-%m')}"
        is_r  = run_backtest(spy_df, vix_df, start_date=is_start,  end_date=is_end,  **BASE)
        oos_r = run_backtest(spy_df, vix_df, start_date=oos_start, end_date=oos_end, **BASE)
        is_p  = _pnl(is_r.trades)
        oos_p = _pnl(oos_r.trades)
        n_is  = len(is_r.trades)
        n_oos = len(oos_r.trades)

        # Delta vs a baseline full-IS run (use first window's full IS as reference)
        if full_is_pnl is None:
            full_is_pnl = is_p
            full_is_n   = n_is

        is_d  = is_p - full_is_pnl if full_is_pnl is not None else 0
        wf    = _wf_norm(is_p, n_is, oos_p, n_oos) if is_p != 0 else 0.0
        verdict = "OOS+" if oos_p > 0 else "OOS-"

        print(f"  {label:12}  {is_end!s:12}  {n_is:>5}  {is_p:>+9.0f}  {oos_start!s:11}  {oos_end!s:11}  "
              f"{n_oos:>5}  {oos_p:>+9.0f}  {wf:>+8.3f}  {verdict}")
        results.append((label, is_start, is_end, n_is, is_p, oos_start, oos_end, n_oos, oos_p, wf, verdict))

    print("\n" + "=" * 100)
    print("AGGREGATE SUMMARY")
    print("=" * 100)

    n_windows = len(results)
    n_oos_pos = sum(1 for r in results if r[8] > 0)
    n_oos_neg = n_windows - n_oos_pos
    total_oos_pnl = sum(r[8] for r in results)
    oos_pnls = [r[8] for r in results]
    oos_wfs  = [r[9] for r in results if r[7] > 0]

    print(f"\n  Total OOS windows:     {n_windows}")
    print(f"  OOS+ windows:          {n_oos_pos} / {n_windows}  ({100*n_oos_pos/n_windows:.0f}%)")
    print(f"  OOS- windows:          {n_oos_neg}")
    print(f"  Sum OOS P&L:           ${total_oos_pnl:+.0f}")
    print(f"  Avg OOS P&L/window:    ${total_oos_pnl/n_windows:+.0f}")

    if oos_wfs:
        import statistics
        print(f"\n  Median WF_norm:        {statistics.median(oos_wfs):+.3f}")
        print(f"  Mean WF_norm:          {sum(oos_wfs)/len(oos_wfs):+.3f}")
        pass_wfs = [w for w in oos_wfs if w >= 0.70]
        print(f"  WF_norm >= 0.70:       {len(pass_wfs)} / {len(oos_wfs)} windows")

    print(f"\n  Best OOS window:  {max(results, key=lambda r: r[8])[0]} ({max(results, key=lambda r: r[8])[8]:+.0f})")
    print(f"  Worst OOS window: {min(results, key=lambda r: r[8])[0]} ({min(results, key=lambda r: r[8])[8]:+.0f})")

    # Monthly breakdown by IS length
    print(f"\n  IS length effect (OOS performance vs IS window size):")
    print(f"  {'Window':12}  {'IS_months':>10}  {'IS_n':>5}  {'OOS_pnl':>9}  {'WF_norm':>8}")
    for r in results:
        label, is_start, is_end, n_is, is_p, oos_start, oos_end, n_oos, oos_p, wf, verdict = r
        months = (is_end.year - is_start.year) * 12 + (is_end.month - is_start.month) + 1
        print(f"  {label:12}  {months:>10}  {n_is:>5}  {oos_p:>+9.0f}  {wf:>+8.3f}")

    # Regime context: which months are profitable vs not
    print(f"\n  VERDICT:")
    if n_oos_pos / n_windows >= 0.60:
        print(f"  STRATEGY IS ROBUST: {100*n_oos_pos/n_windows:.0f}% of OOS windows positive (gate >= 60%)")
    elif n_oos_pos / n_windows >= 0.45:
        print(f"  STRATEGY IS BORDERLINE: {100*n_oos_pos/n_windows:.0f}% of OOS windows positive")
    else:
        print(f"  STRATEGY IS NOT ROBUST: only {100*n_oos_pos/n_windows:.0f}% of OOS windows positive")

    print("\nANALYSIS COMPLETE.")
