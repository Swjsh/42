"""Bear trade time-of-day (TOD) analysis for SAFE.

Goal: find if bears in a specific time window underperform enough to warrant a gate.
If any TOD bucket has IS_delta > 0 when removed AND OOS_delta > 0, it's a candidate.

Uses full IS period (2025-01-02 to 2026-05-07) matching CONTEXT-92 baseline.
"""
import sys, datetime as dt
sys.path.insert(0, "backtest")
import pandas as pd
from lib.orchestrator import run_backtest

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

print("Running full IS and OOS ...")
r_is  = run_backtest(spy, vix, start_date=IS_S,  end_date=IS_E,  **BASE)
r_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **BASE)

bears_is  = [t for t in r_is.trades  if t.side == "P"]
bears_oos = [t for t in r_oos.trades if t.side == "P"]

print(f"\nIS  bears: n={len(bears_is)}   OOS bears: n={len(bears_oos)}")
print()

# Time buckets
BUCKETS = [
    ("09:35-10:00", dt.time(9,35), dt.time(10, 0)),
    ("10:00-11:00", dt.time(10, 0), dt.time(11, 0)),
    ("11:00-12:00", dt.time(11, 0), dt.time(12, 0)),
    ("12:00-13:00", dt.time(12, 0), dt.time(13, 0)),
    ("13:00-14:00", dt.time(13, 0), dt.time(14, 0)),
    ("14:00-15:00", dt.time(14, 0), dt.time(15, 0)),
]

print("=== IS Bear TOD Profile ===")
print(f"{'Bucket':20s} {'n':>4}  {'total':>8}  {'avg':>8}  {'WR':>6}  {'n_wins':>6}")
print("-" * 65)
for label, t_start, t_end in BUCKETS:
    subset = [t for t in bears_is
              if t_start <= t.entry_time_et.time() < t_end]
    n = len(subset)
    if n == 0:
        print(f"  {label:18s} {n:4d}")
        continue
    tot  = sum(t.dollar_pnl for t in subset)
    avg  = tot / n
    wins = sum(1 for t in subset if t.dollar_pnl > 0)
    wr   = wins / n
    print(f"  {label:18s} {n:4d}  {tot:+8.0f}  {avg:+8.0f}  {wr:6.1%}  {wins:6d}")

print()
print("=== OOS Bear TOD Profile ===")
print(f"{'Bucket':20s} {'n':>4}  {'total':>8}  {'avg':>8}  {'WR':>6}  {'n_wins':>6}")
print("-" * 65)
for label, t_start, t_end in BUCKETS:
    subset = [t for t in bears_oos
              if t_start <= t.entry_time_et.time() < t_end]
    n = len(subset)
    if n == 0:
        print(f"  {label:18s} {n:4d}")
        continue
    tot  = sum(t.dollar_pnl for t in subset)
    avg  = tot / n
    wins = sum(1 for t in subset if t.dollar_pnl > 0)
    wr   = wins / n
    print(f"  {label:18s} {n:4d}  {tot:+8.0f}  {avg:+8.0f}  {wr:6.1%}  {wins:6d}")

# Quality tier analysis
print()
print("=== IS Bear Quality Tier ===")
tiers = {}
for t in bears_is:
    tier = getattr(t, "quality_tier", "UNKNOWN")
    if tier not in tiers:
        tiers[tier] = []
    tiers[tier].append(t.dollar_pnl)
for tier, pnls in sorted(tiers.items()):
    n = len(pnls)
    tot = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    print(f"  {tier:15s}: n={n:3d}  total={tot:+.0f}  WR={wins/n:.1%}  avg={tot/n:+.0f}")
