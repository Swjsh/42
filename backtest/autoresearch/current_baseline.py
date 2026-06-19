"""
CURRENT PRODUCTION BASELINE after all 2026-06-17 changes:
- block_level_rejection=True (Rank 32)
- premium_stop_pct_bear=-0.10 (Rank 33, TIGHTER_STOP)
- tp1_qty_fraction=0.667 (Rank 31)
- time_stop_minutes_before_close=20 (Rank 31)

This is the new CORRECT RESEARCH BASELINE for all future work.
"""
import sys
import datetime as dt
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR  = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-06-16.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
J_LOSERS  = {dt.date(2026, 5, 5), dt.date(2026, 5, 6), dt.date(2026, 5, 7)}

IS_SUB_WINDOWS = [
    ("W1-2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2-2025H2", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3-Q12026", dt.date(2026, 1, 1),  dt.date(2026, 3, 31)),
    ("W4-Apr26",  dt.date(2026, 4, 1),  dt.date(2026, 5,  7)),
]

PROD = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.10,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
)


def get_entry_date(t):
    et = t.entry_time_et
    if hasattr(et, "date"):
        return et.date()
    return dt.date.fromisoformat(str(et)[:10])


def pnl_window(trades, s, e):
    return sum(t.dollar_pnl for t in trades if s <= get_entry_date(t) <= e)


def main():
    print("Loading data...")
    spy = pd.read_csv(SPY_FILE)
    vix = pd.read_csv(VIX_FILE)

    print("Running IS + OOS with CURRENT PRODUCTION PARAMS...")
    is_r  = run_backtest(spy, vix, start_date=IS_START,  end_date=IS_END,  **PROD)
    oos_r = run_backtest(spy, vix, start_date=OOS_START, end_date=OOS_END, **PROD)

    is_pnl  = sum(t.dollar_pnl for t in is_r.trades)
    oos_pnl = sum(t.dollar_pnl for t in oos_r.trades)
    is_n    = len(is_r.trades)
    oos_n   = len(oos_r.trades)
    is_wr   = sum(1 for t in is_r.trades if t.dollar_pnl > 0) / is_n if is_n else 0
    oos_wr  = sum(1 for t in oos_r.trades if t.dollar_pnl > 0) / oos_n if oos_n else 0

    print(f"\n{'='*72}")
    print("CURRENT PRODUCTION BASELINE (2026-06-17)")
    print(f"  block_level_rejection=True, premium_stop_pct_bear=-0.10")
    print(f"  tp1_qty_fraction=0.667, time_stop_minutes_before_close=20")
    print(f"{'='*72}")
    print(f"  IS:  n={is_n:4d}  pnl={is_pnl:+,.0f}  WR={is_wr:.1%}  avg={is_pnl/is_n:+,.0f}/trade")
    print(f"  OOS: n={oos_n:4d}  pnl={oos_pnl:+,.0f}  WR={oos_wr:.1%}  avg={oos_pnl/oos_n:+,.0f}/trade")

    print(f"\n  IS Sub-windows:")
    for name, s, e in IS_SUB_WINDOWS:
        t_pnl = pnl_window(is_r.trades, s, e)
        t_n   = sum(1 for t in is_r.trades if s <= get_entry_date(t) <= e)
        t_wr  = (sum(1 for t in is_r.trades if s <= get_entry_date(t) <= e and t.dollar_pnl > 0)
                 / t_n if t_n else 0)
        print(f"    {name:<14s}  n={t_n:4d}  pnl={t_pnl:+,.0f}  WR={t_wr:.1%}")

    print(f"\n  J anchor days:")
    for d in sorted(J_WINNERS):
        p = pnl_window(is_r.trades, d, d)
        print(f"    {d}  pnl={p:+,.0f}")

    # Quality tier breakdown
    def get_quality(t):
        tf = set(t.triggers_fired or [])
        has_conf = "confluence" in tf
        has_rf   = "ribbon_flip" in tf
        has_lvl  = any(x in tf for x in ["level_rejection", "level_reclaim"])
        has_seq  = "sequence_rejection" in tf
        if (has_conf and has_rf) or len(tf) >= 3:
            return "SUPER"
        if has_conf or has_seq:
            return "ELITE"
        if has_lvl:
            return "LEVEL"
        return "TRENDLINE"

    from collections import defaultdict
    tiers = defaultdict(lambda: {"n": 0, "pnl": 0, "wins": 0})
    for t in is_r.trades:
        q = get_quality(t)
        tiers[q]["n"] += 1
        tiers[q]["pnl"] += t.dollar_pnl
        if t.dollar_pnl > 0:
            tiers[q]["wins"] += 1

    print(f"\n  IS Quality tier breakdown:")
    for tier in ["SUPER", "ELITE", "LEVEL", "TRENDLINE"]:
        d = tiers[tier]
        n = d["n"]
        if n:
            wr = d["wins"] / n
            avg = d["pnl"] / n
            print(f"    {tier:<10s}  n={n:4d}  pnl={d['pnl']:+,.0f}  WR={wr:.1%}  avg={avg:+,.0f}/trade")

    print(f"\n[BASELINE COMPLETE — save these as the new research baseline]")
    print(f"baseline = dict(is_n={is_n}, is_pnl={is_pnl:.0f}, oos_n={oos_n}, oos_pnl={oos_pnl:.0f})")


if __name__ == "__main__":
    main()
