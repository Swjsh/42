"""Bull trigger composition analysis for SAFE IS + OOS.

OOS bulls (n=8) are -$173 total. Which trigger combos are driving OOS losses?
block_elite_bull is already active (blocks confluence+level_reclaim in VIX 15-17.5).
This analyzes remaining bulls to find any IS+OOS negative combos.

TZ FIX: entry_time_et is naive ET (option CSV). Use tz_localize('America/New_York'),
NOT tz_localize('UTC'). See CONTEXT-94 / safe_trendline_bear_spread_gate.json for lesson.
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

bulls_is  = [t for t in r_is.trades  if t.side == "C"]
bulls_oos = [t for t in r_oos.trades if t.side == "C"]

print(f"\nIS bulls: n={len(bulls_is)}, total={sum(t.dollar_pnl for t in bulls_is):+.0f}")
print(f"OOS bulls: n={len(bulls_oos)}, total={sum(t.dollar_pnl for t in bulls_oos):+.0f}")


def categorize(trade):
    tf = set(trade.triggers_fired)
    has_seq  = "sequence_rejection" in tf
    has_conf = "confluence" in tf
    has_lvl  = "level_reclaim" in tf or "level_rejection" in tf
    has_tl   = "trendline_rejection" in tf
    has_rf   = "ribbon_flip" in tf
    n = len(tf)
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
    combo = "+".join(sorted(tf)) if tf else "none"
    return tier, combo


def analyze_bulls(bulls, label, vix_data=None):
    combo_stats = defaultdict(lambda: {"n": 0, "total": 0.0, "wins": 0})
    tier_stats  = defaultdict(lambda: {"n": 0, "total": 0.0, "wins": 0})
    for t in bulls:
        tier, combo = categorize(t)
        pnl = t.dollar_pnl
        for d in [combo_stats[combo], tier_stats[tier]]:
            d["n"] += 1
            d["total"] += pnl
            d["wins"] += int(pnl > 0)

    print(f"\n=== {label} Bull Tier Breakdown ===")
    print(f"{'Tier':12s} {'n':>4}  {'total':>8}  {'avg':>8}  {'WR':>6}")
    print("-" * 50)
    for tier in ["SUPER", "ELITE", "TRENDLINE", "BASE", "LEVEL"]:
        s = tier_stats.get(tier)
        if not s or s["n"] == 0:
            continue
        print(f"  {tier:10s} {s['n']:4d}  {s['total']:+8.0f}  {s['total']/s['n']:+8.0f}  {s['wins']/s['n']:6.1%}")

    print(f"\n=== {label} Bull Combo Breakdown ===")
    print(f"{'Triggers':55s} {'n':>4}  {'total':>8}  {'avg':>8}  {'WR':>6}")
    print("-" * 85)
    rows = sorted(combo_stats.items(), key=lambda x: x[1]["total"])
    for combo, s in rows:
        if s["n"] == 0:
            continue
        avg = s["total"] / s["n"]
        wr  = s["wins"]  / s["n"]
        mark = " *** NEGATIVE ***" if avg < -10 else ""
        print(f"  {combo[:53]:53s} {s['n']:4d}  {s['total']:+8.0f}  {avg:+8.0f}  {wr:6.1%}{mark}")


analyze_bulls(bulls_is,  "IS")
analyze_bulls(bulls_oos, "OOS")

# VIX profile of OOS bulls
print(f"\n=== OOS Bulls (individual) ===")
print(f"{'Date':12s} {'Time':8s} {'triggers':45s} {'pnl':>8}")
print("-" * 80)
for t in sorted(bulls_oos, key=lambda x: x.dollar_pnl):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    _, combo = categorize(t)
    print(f"  {ts.date()} {ts.time()}  {combo[:43]:43s} {t.dollar_pnl:+8.0f}")

# Time-of-day breakdown (IS bulls)
print(f"\n=== IS Bull Time-of-Day Breakdown ===")
tod_stats = defaultdict(lambda: {"n": 0, "total": 0.0, "wins": 0})
for t in bulls_is:
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    h = ts.hour
    if h < 10:
        bucket = "09:35-10:00"
    elif h < 11:
        bucket = "10:00-11:00"
    elif h < 12:
        bucket = "11:00-12:00"
    elif h < 13:
        bucket = "12:00-13:00"
    elif h < 14:
        bucket = "13:00-14:00"
    else:
        bucket = "14:00-15:00"
    tod_stats[bucket]["n"] += 1
    tod_stats[bucket]["total"] += t.dollar_pnl
    tod_stats[bucket]["wins"] += int(t.dollar_pnl > 0)

print(f"{'Bucket':15s} {'n':>4}  {'total':>8}  {'avg':>8}  {'WR':>6}")
for bucket in ["09:35-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00"]:
    s = tod_stats.get(bucket)
    if not s or s["n"] == 0:
        continue
    print(f"  {bucket:13s} {s['n']:4d}  {s['total']:+8.0f}  {s['total']/s['n']:+8.0f}  {s['wins']/s['n']:6.1%}")

# Summary: has_ribbon_flip bulls
print(f"\n=== IS Bulls: has_ribbon_flip vs not ===")
with_rf    = [t for t in bulls_is if "ribbon_flip" in t.triggers_fired]
without_rf = [t for t in bulls_is if "ribbon_flip" not in t.triggers_fired]
def fmt(lst):
    n = len(lst)
    if n == 0:
        return "n=0"
    tot = sum(t.dollar_pnl for t in lst)
    wr = sum(1 for t in lst if t.dollar_pnl > 0) / n
    return f"n={n} total={tot:+.0f} WR={wr:.1%}"
print(f"  has_ribbon_flip: {fmt(with_rf)}")
print(f"  no_ribbon_flip:  {fmt(without_rf)}")
