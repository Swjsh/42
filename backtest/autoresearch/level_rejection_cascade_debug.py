"""
Debug: which trades differ between BASE and CANDIDATE on OOS days?
Especially 5/08 where BASE has +$1130 but CANDIDATE loses it.
"""
import sys
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR  = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

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


def get_entry_date(t):
    et = t.entry_time_et
    if hasattr(et, 'date'):
        return et.date()
    return dt.date.fromisoformat(str(et)[:10])


def main():
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("Running BASE OOS...")
    base = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)

    print("Running CANDIDATE OOS (block_level_rejection=True)...")
    cand = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                        **BASE, block_level_rejection=True)

    # Group trades by date
    from collections import defaultdict
    base_by_day = defaultdict(list)
    cand_by_day = defaultdict(list)

    for t in base.trades:
        base_by_day[get_entry_date(t)].append(t)
    for t in cand.trades:
        cand_by_day[get_entry_date(t)].append(t)

    # All days that appear in either
    all_days = sorted(set(base_by_day.keys()) | set(cand_by_day.keys()))

    print(f"\n{'='*80}")
    print("PER-DAY OOS TRADE COMPARISON (BASE vs CANDIDATE)")
    print(f"{'='*80}")

    for d in all_days:
        b_trades = base_by_day.get(d, [])
        c_trades = cand_by_day.get(d, [])
        b_pnl = sum(t.dollar_pnl for t in b_trades)
        c_pnl = sum(t.dollar_pnl for t in c_trades)
        delta = c_pnl - b_pnl

        if delta != 0 or b_trades or c_trades:
            print(f"\n  {d}  BASE_n={len(b_trades)} BASE_pnl={b_pnl:+,.0f}  "
                  f"CAND_n={len(c_trades)} CAND_pnl={c_pnl:+,.0f}  delta={delta:+,.0f}")
            for t in b_trades:
                et = t.entry_time_et
                ts = str(et)[:16] if hasattr(et, '__str__') else str(et)
                print(f"    BASE: {ts}  pnl={t.dollar_pnl:+,.0f}  qty={t.qty}  "
                      f"premium={t.entry_premium:.2f}  trigs={t.triggers_fired}")
            for t in c_trades:
                et = t.entry_time_et
                ts = str(et)[:16] if hasattr(et, '__str__') else str(et)
                print(f"    CAND: {ts}  pnl={t.dollar_pnl:+,.0f}  qty={t.qty}  "
                      f"premium={t.entry_premium:.2f}  trigs={t.triggers_fired}")

    # Also check decisions for blocked entries
    print(f"\n{'='*80}")
    print("SKIP decisions in CANDIDATE (level_rejection gate)")
    print(f"{'='*80}")

    for d in base.decisions:
        if d.get("action") == "SKIP_LEVEL_REJECTION_GATE":
            ts = str(d.get("timestamp_et", ""))[:16]
            print(f"  {ts}  vix={d.get('vix',0):.2f}  trigs={d.get('triggers_fired')}  "
                  f"spy={d.get('spy_close',0):.2f}")

    # Find SKIP_LEVEL_REJECTION_GATE in candidate
    print(f"\nSKIPs in candidate:")
    for d in cand.decisions:
        if d.get("action") == "SKIP_LEVEL_REJECTION_GATE":
            ts = str(d.get("timestamp_et", ""))[:16]
            print(f"  {ts}  vix={d.get('vix',0):.2f}  trigs={d.get('triggers_fired')}  "
                  f"spy={d.get('spy_close',0):.2f}")

    print("\n[ANALYSIS COMPLETE]")


if __name__ == "__main__":
    main()
