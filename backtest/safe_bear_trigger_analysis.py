"""Bear trigger composition analysis for SAFE IS + OOS.

Analyzes which trigger combos produce profitable vs unprofitable bears.
Identifies candidates for a more granular bear quality gate.
"""
import sys, datetime as dt
sys.path.insert(0, "backtest")
import pandas as pd
from lib.orchestrator import run_backtest
from collections import defaultdict

spy = pd.read_csv("backtest/data/spy_5m_2025-01-01_2026-06-16.csv")
vix = pd.read_csv("backtest/data/vix_5m_2025-01-01_2026-06-16.csv")

IS_S  = dt.date(2025, 1, 2)
IS_E  = dt.date(2026, 5, 7)
OOS_S = dt.date(2026, 5, 8)
OOS_E = dt.date(2026, 6, 15)

BASE = dict(
    use_real_fills=True,
    no_trade_before=dt.time(9, 35), no_trade_window=None,
    midday_trendline_gate=True,
    premium_stop_pct=-0.08, premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50, time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True, block_elite_bull=True,
    block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=17.5,
    entry_bar_body_pct_min=0.20, vix_bear_hard_cap=23.0,
    min_triggers_bear=1, min_triggers_bull=2,
    profit_lock_threshold_pct=0.05, profit_lock_mode="trailing", profit_lock_trail_pct=0.20,
    initial_equity=2000.0, strike_offset=2,
)

print("Running IS and OOS ...")
r_is  = run_backtest(spy, vix, start_date=IS_S,  end_date=IS_E,  **BASE)
r_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **BASE)

bears_is  = [t for t in r_is.trades  if t.side == "P"]
bears_oos = [t for t in r_oos.trades if t.side == "P"]


def categorize(trade):
    tf = set(trade.triggers_fired)
    has_seq  = "sequence_rejection" in tf
    has_conf = "confluence" in tf
    has_lvl  = "level_rejection" in tf
    has_tl   = "trendline_rejection" in tf
    has_rf   = "ribbon_flip" in tf
    n = len(tf)
    # Reconstruct tier
    if (has_conf and has_rf) or n >= 3:
        tier = "SUPER"
    elif has_conf or has_seq:
        tier = "ELITE"
    elif has_lvl:
        tier = "LEVEL"
    elif has_tl:
        tier = "TRENDLINE"
    else:
        tier = "BASE"
    # Trigger combo label
    parts = sorted(tf)
    combo = "+".join(parts) if parts else "none"
    return tier, combo, frozenset(tf)


def analyze(bears, label):
    combo_stats = defaultdict(lambda: {"n": 0, "total": 0.0, "wins": 0})
    tier_stats  = defaultdict(lambda: {"n": 0, "total": 0.0, "wins": 0})
    for t in bears:
        tier, combo, _ = categorize(t)
        pnl = t.dollar_pnl
        for d in [combo_stats[combo], tier_stats[tier]]:
            d["n"] += 1
            d["total"] += pnl
            d["wins"] += int(pnl > 0)
    print(f"\n=== {label} Bear Tier Breakdown ===")
    print(f"{'Tier':12s} {'n':>4}  {'total':>8}  {'avg':>8}  {'WR':>6}")
    print("-" * 50)
    for tier in ["SUPER", "ELITE", "TRENDLINE", "BASE", "LEVEL"]:
        s = tier_stats.get(tier)
        if not s or s["n"] == 0:
            continue
        print(f"  {tier:10s} {s['n']:4d}  {s['total']:+8.0f}  {s['total']/s['n']:+8.0f}  {s['wins']/s['n']:6.1%}")

    print(f"\n=== {label} Bear Combo Breakdown ===")
    print(f"{'Triggers':55s} {'n':>4}  {'total':>8}  {'avg':>8}  {'WR':>6}")
    print("-" * 85)
    rows = sorted(combo_stats.items(), key=lambda x: -abs(x[1]["total"]))
    for combo, s in rows:
        if s["n"] == 0:
            continue
        avg = s["total"] / s["n"]
        wr  = s["wins"]  / s["n"]
        mark = " *** NEGATIVE ***" if avg < -20 else ""
        print(f"  {combo[:53]:53s} {s['n']:4d}  {s['total']:+8.0f}  {avg:+8.0f}  {wr:6.1%}{mark}")


analyze(bears_is,  "IS")
analyze(bears_oos, "OOS")

# Summary: has_sequence vs not
print("\n=== IS Bears: has_sequence_rejection vs not ===")
with_seq    = [t for t in bears_is if "sequence_rejection" in t.triggers_fired]
without_seq = [t for t in bears_is if "sequence_rejection" not in t.triggers_fired]
print(f"  has_sequence:   n={len(with_seq):3d}  total={sum(t.dollar_pnl for t in with_seq):+.0f}"
      f"  WR={sum(1 for t in with_seq if t.dollar_pnl>0)/max(1,len(with_seq)):.1%}")
print(f"  no_sequence:    n={len(without_seq):3d}  total={sum(t.dollar_pnl for t in without_seq):+.0f}"
      f"  WR={sum(1 for t in without_seq if t.dollar_pnl>0)/max(1,len(without_seq)):.1%}")

print("\n=== OOS Bears: has_sequence_rejection vs not ===")
with_seq    = [t for t in bears_oos if "sequence_rejection" in t.triggers_fired]
without_seq = [t for t in bears_oos if "sequence_rejection" not in t.triggers_fired]
print(f"  has_sequence:   n={len(with_seq):3d}  total={sum(t.dollar_pnl for t in with_seq):+.0f}"
      f"  WR={sum(1 for t in with_seq if t.dollar_pnl>0)/max(1,len(with_seq)):.1%}")
print(f"  no_sequence:    n={len(without_seq):3d}  total={sum(t.dollar_pnl for t in without_seq):+.0f}"
      f"  WR={sum(1 for t in without_seq if t.dollar_pnl>0)/max(1,len(without_seq)):.1%}")
