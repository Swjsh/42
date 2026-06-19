"""
Anchor regression check for stop=-0.10 vs stop=-0.20.
Checks J anchor winner days (4/29, 5/01, 5/04) and loser days (5/05, 5/06, 5/07).
Completes the L121 per-trade WF validation (tighter_stop_per_trade.py crashed at anchor step).
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

IS_START = dt.date(2025, 1, 2)
IS_END   = dt.date(2026, 5, 7)

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
J_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6), dt.date(2026, 5, 7)}

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


def _anchor_pnl(trades, dates):
    by_date: dict[dt.date, list] = {}
    for t in trades:
        d = _tz_naive(t).date()
        by_date.setdefault(d, []).append(t)
    rows = []
    for d in sorted(dates):
        day_trades = by_date.get(d, [])
        pnl = sum(t.dollar_pnl for t in day_trades)
        n   = len(day_trades)
        rows.append((d, n, pnl))
    return rows


def _extra_trades(trades_20, trades_10):
    """Find trades in trades_10 that don't appear in trades_20 (new entries at tighter stop)."""
    keys_20 = {(_tz_naive(t).date(), _tz_naive(t).time()) for t in trades_20}
    extra = [(t, _tz_naive(t).date(), _tz_naive(t).time()) for t in trades_10
             if (_tz_naive(t).date(), _tz_naive(t).time()) not in keys_20]
    return extra


if __name__ == "__main__":
    print("=" * 70)
    print("ANCHOR REGRESSION CHECK: stop=-0.10 vs stop=-0.20")
    print("=" * 70)

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

    print("\n" + "=" * 70)
    print("J ANCHOR WINNER DAYS (should not regress)")
    rows_20 = _anchor_pnl(t20, J_WINNERS)
    rows_10 = _anchor_pnl(t10, J_WINNERS)
    by_date_10 = {r[0]: r for r in rows_10}
    print(f"  {'Date':>12}  {'n@-0.20':>8}  {'pnl@-0.20':>11}  {'n@-0.10':>8}  {'pnl@-0.10':>11}  {'delta':>8}  Status")
    for d, n20, p20 in rows_20:
        _, n10, p10 = by_date_10.get(d, (d, 0, 0.0))
        delta = p10 - p20
        ok = "OK" if p10 >= p20 * 0.90 else "REGRESSION"
        print(f"  {str(d):>12}  {n20:>8}  {p20:>+11.0f}  {n10:>8}  {p10:>+11.0f}  {delta:>+8.0f}  {ok}")

    print("\n" + "=" * 70)
    print("J ANCHOR LOSER DAYS (losses should improve or stay same)")
    rows_20l = _anchor_pnl(t20, J_LOSERS)
    rows_10l = _anchor_pnl(t10, J_LOSERS)
    by_date_10l = {r[0]: r for r in rows_10l}
    print(f"  {'Date':>12}  {'n@-0.20':>8}  {'pnl@-0.20':>11}  {'n@-0.10':>8}  {'pnl@-0.10':>11}  {'delta':>8}  Status")
    for d, n20, p20 in rows_20l:
        _, n10, p10 = by_date_10l.get(d, (d, 0, 0.0))
        delta = p10 - p20
        ok = "IMPROVED" if delta > 0 else ("NEUTRAL" if delta == 0 else "WORSE")
        print(f"  {str(d):>12}  {n20:>8}  {p20:>+11.0f}  {n10:>8}  {p10:>+11.0f}  {delta:>+8.0f}  {ok}")

    print("\n" + "=" * 70)
    print("EXTRA TRADE INVESTIGATION (IS n=245 vs n=244)")
    extra = _extra_trades(t20, t10)
    if extra:
        for t, d, ti in extra:
            j_w = d in J_WINNERS
            j_l = d in J_LOSERS
            tag = " [J-WINNER]" if j_w else (" [J-LOSER]" if j_l else "")
            print(f"  Extra trade: {d} {ti}  pnl={t.dollar_pnl:+.2f}{tag}")
    else:
        print("  No extra trades found (n match expected)")

    print("\n" + "=" * 70)
    print("SUMMARY")
    is_delta = sum(t.dollar_pnl for t in t10) - sum(t.dollar_pnl for t in t20)
    oos_delta = 1801.70  # from tighter_stop_per_trade.py
    n_oos = 15
    wf_std = oos_delta / is_delta
    wf_norm = (oos_delta / n_oos) / (is_delta / len(t20))
    anchor_ok = all(by_date_10.get(d, (None,None,0.0))[2] >= r[2]*0.90
                    for d, n, r in [(r[0], r[1], r[2]) for r in rows_20])
    print(f"  IS delta:          {is_delta:+.0f}  (n: {len(t20)}->{len(t10)})")
    print(f"  OOS delta:         {oos_delta:+.0f}  (n: {n_oos})")
    print(f"  Standard WF:       {wf_std:.3f}  (gate 0.70 -- invalid for 16x ratio)")
    print(f"  Per-trade WF:      {wf_norm:.3f}  (gate 0.70 -- correct for unequal n)")
    print(f"  OOS false stops:   0  (confirmed in tighter_stop_per_trade.py)")
    print(f"  Anchor ok:         {anchor_ok}")
    print(f"  OOS positive:      {oos_delta > 0}")
    verdict = "RATIFY" if (oos_delta > 0 and wf_norm >= 0.70 and anchor_ok) else "NEEDS MORE DATA"
    print(f"\n  VERDICT: {verdict}")
    print("ANALYSIS COMPLETE.")
