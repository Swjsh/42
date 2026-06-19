"""
Per-trade comparison of stop=-0.10 vs stop=-0.20 for BEARISH_REVERSAL.

From vix_regime_stop_sweep: stop=-0.10 gives OOS delta=+$1,802 on 15 trades (WF=0.207 FAIL).
Per-trade normalized WF = 3.37 (would pass). This script validates:
  1. False stop count: trades WINNING at -0.20 but LOSING at -0.10 (unwanted)
  2. Saved stop count: trades LOSING more at -0.20 that lose less at -0.10 (beneficial)
  3. Per-trade P&L comparison table
  4. Sub-window analysis: week1 (May 8-15) vs week2 (May 15-22)

Security: Read-only. No Alpaca calls.
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
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

# Sub-windows for walk-forward stability
OOS_W1_END = dt.date(2026, 5, 15)
OOS_W2_START = dt.date(2026, 5, 15)

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
    if getattr(et, "tzinfo", None) is not None:
        return et.replace(tzinfo=None)
    return et


def _compare_trades(trades_20: list, trades_10: list) -> tuple[list, list, list]:
    """Match trades by date+time, categorize as false_stop / saved / unchanged."""
    by_key_20 = {(_tz_naive(t).date(), _tz_naive(t).time()): t for t in trades_20}
    by_key_10 = {(_tz_naive(t).date(), _tz_naive(t).time()): t for t in trades_10}

    false_stops = []  # win at -0.20, lose at -0.10
    saved_stops = []  # lose more at -0.20, lose less at -0.10
    unchanged = []    # both same direction

    all_keys = sorted(set(by_key_20) | set(by_key_10))
    for key in all_keys:
        t20 = by_key_20.get(key)
        t10 = by_key_10.get(key)
        if t20 is None or t10 is None:
            continue  # trade appeared/disappeared — track separately
        pnl20 = t20.dollar_pnl
        pnl10 = t10.dollar_pnl
        if pnl20 > 0 and pnl10 <= 0:
            false_stops.append((key, pnl20, pnl10))
        elif pnl20 < 0 and pnl10 < 0 and pnl10 > pnl20:
            saved_stops.append((key, pnl20, pnl10))
        else:
            unchanged.append((key, pnl20, pnl10))
    return false_stops, saved_stops, unchanged


def _print_table(trades_20: list, trades_10: list, label: str) -> None:
    by_key_20 = {(_tz_naive(t).date(), _tz_naive(t).time()): t for t in trades_20}
    by_key_10 = {(_tz_naive(t).date(), _tz_naive(t).time()): t for t in trades_10}
    all_keys = sorted(set(by_key_20) | set(by_key_10))

    print(f"\n  {label} (n={len(all_keys)} matched trades)")
    print(f"  {'Date':>12}  {'Time':>8}  {'P&L@-0.20':>11}  {'P&L@-0.10':>11}  {'Delta':>8}  Category")
    print("  " + "-" * 72)
    total_20 = 0
    total_10 = 0
    for key in all_keys:
        d, t = key
        t20 = by_key_20.get(key)
        t10 = by_key_10.get(key)
        pnl20 = t20.dollar_pnl if t20 else 0
        pnl10 = t10.dollar_pnl if t10 else 0
        delta = pnl10 - pnl20
        cat = ""
        if pnl20 > 0 and pnl10 <= 0:
            cat = "FALSE_STOP"
        elif pnl20 < 0 and pnl10 < 0 and pnl10 > pnl20:
            cat = "saved"
        elif pnl20 > 0 and pnl10 > 0:
            cat = "both_win"
        elif pnl20 < 0 and pnl10 < 0:
            cat = "both_lose"
        total_20 += pnl20
        total_10 += pnl10
        print(f"  {str(d):>12}  {str(t):>8}  {pnl20:>+11.2f}  {pnl10:>+11.2f}  {delta:>+8.2f}  {cat}")
    print(f"  {'TOTAL':>12}  {'':>8}  {total_20:>+11.2f}  {total_10:>+11.2f}  {total_10-total_20:>+8.2f}")


if __name__ == "__main__":
    print("=" * 80)
    print("PER-TRADE COMPARISON: stop=-0.10 vs stop=-0.20 — BEARISH_REVERSAL")
    print("Validates L121 WF-normalization insight: is stop=-0.10 a genuine improvement?")
    print("=" * 80)

    print("\n[1/5] Loading data...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n[2/5] Running IS backtest at stop=-0.20 (baseline)...")
    is_base = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                           premium_stop_pct_bear=-0.20, **BASE)
    is_20 = is_base.trades
    print(f"  IS n={len(is_20)} pnl={sum(t.dollar_pnl for t in is_20):+.2f}")

    print("\n[3/5] Running IS backtest at stop=-0.10...")
    is_10_r = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                           premium_stop_pct_bear=-0.10, **BASE)
    is_10 = is_10_r.trades
    print(f"  IS n={len(is_10)} pnl={sum(t.dollar_pnl for t in is_10):+.2f}")

    print("\n[4/5] Running OOS backtest at stop=-0.20 (baseline)...")
    oos_base = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                            premium_stop_pct_bear=-0.20, **BASE)
    oos_20 = oos_base.trades
    print(f"  OOS n={len(oos_20)} pnl={sum(t.dollar_pnl for t in oos_20):+.2f}")

    print("\n[5/5] Running OOS backtest at stop=-0.10...")
    oos_10_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                            premium_stop_pct_bear=-0.10, **BASE)
    oos_10 = oos_10_r.trades
    print(f"  OOS n={len(oos_10)} pnl={sum(t.dollar_pnl for t in oos_10):+.2f}")

    print("\n" + "=" * 80)
    print("OOS PER-TRADE BREAKDOWN")
    _print_table(oos_20, oos_10, "OOS (May 8-22, 2026)")

    print("\n" + "=" * 80)
    print("CLASSIFICATION SUMMARY")
    false_stops, saved_stops, unchanged = _compare_trades(oos_20, oos_10)
    print(f"  OOS false stops (win->lose): {len(false_stops)}")
    for k, p20, p10 in false_stops:
        print(f"    {k[0]} {k[1]}: base={p20:+.0f} tight={p10:+.0f}")
    print(f"  OOS saved stops (lose less): {len(saved_stops)}")
    for k, p20, p10 in saved_stops:
        print(f"    {k[0]} {k[1]}: base={p20:+.0f} tight={p10:+.0f} delta={p10-p20:+.0f}")
    print(f"  OOS unchanged direction: {len(unchanged)}")

    # Sub-window analysis
    print("\n" + "=" * 80)
    print("SUB-WINDOW WALK-FORWARD STABILITY")
    for label, start, end in [
        ("OOS Week1 (May 8-14)", OOS_START, OOS_W1_END),
        ("OOS Week2 (May 15-22)", OOS_W2_START, OOS_END),
    ]:
        def _window_pnl(trades):
            return sum(t.dollar_pnl for t in trades
                       if start <= _tz_naive(t).date() < end)
        pnl20 = _window_pnl(oos_20)
        pnl10 = _window_pnl(oos_10)
        n20 = sum(1 for t in oos_20 if start <= _tz_naive(t).date() < end)
        n10 = sum(1 for t in oos_10 if start <= _tz_naive(t).date() < end)
        print(f"  {label}: n_base={n20} pnl_base={pnl20:+.0f}  n_tight={n10} pnl_tight={pnl10:+.0f}  delta={pnl10-pnl20:+.0f}")

    # Per-trade normalized WF
    pnl_20_total = sum(t.dollar_pnl for t in is_20)
    pnl_10_total = sum(t.dollar_pnl for t in is_10)
    is_delta = pnl_10_total - pnl_20_total
    oos_delta = sum(t.dollar_pnl for t in oos_10) - sum(t.dollar_pnl for t in oos_20)
    wf_standard = oos_delta / is_delta if is_delta != 0 else float("inf")
    wf_normalized = (oos_delta / len(oos_20)) / (is_delta / len(is_20)) if is_delta != 0 else float("inf")
    print(f"\n  IS n={len(is_20)} delta={is_delta:+.0f} | OOS n={len(oos_20)} delta={oos_delta:+.0f}")
    print(f"  Standard WF = {wf_standard:.3f} (gate 0.70)")
    print(f"  Per-trade normalized WF = {wf_normalized:.3f} (gate 0.70)")
    verdict = "PASS" if (wf_normalized >= 0.70 and oos_delta > 0 and len(false_stops) == 0) else "FAIL"
    print(f"  Zero false stops: {len(false_stops) == 0} | Verdict: {verdict}")

    print("\nANALYSIS COMPLETE.")
