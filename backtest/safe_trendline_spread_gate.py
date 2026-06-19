"""Ribbon spread gate for TRENDLINE bears: gate on spread_cents at entry.

Hypothesis: TRENDLINE-only bears with tight ribbon (spread < N cents) are lower WR.
Requiring a minimum spread improves bear quality without removing ELITE/SUPER.

TRENDLINE IS bears: n=40, WR=27.5%, avg=+$1. OOS: n=5, WR=60%, avg=+$109.
Small qty (3 contracts after $600 cap), so P&L impact is bounded.
"""
import sys, datetime as dt
sys.path.insert(0, "backtest")
import pandas as pd
from lib.orchestrator import run_backtest
from lib.ribbon import compute_ribbon, ribbon_at

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

print("Computing ribbon and running IS + OOS ...")
ribbon_df = compute_ribbon(spy["close"])

# Build fast timestamp lookup
spy_ts = pd.to_datetime(spy["timestamp_et"], utc=True)
spy_ts_arr = spy_ts.values  # numpy array for searchsorted

r_is  = run_backtest(spy, vix, start_date=IS_S,  end_date=IS_E,  **BASE)
r_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **BASE)

bears_is  = [t for t in r_is.trades  if t.side == "P"]
bears_oos = [t for t in r_oos.trades if t.side == "P"]

tl_is  = [t for t in bears_is  if t.triggers_fired == ["trendline_rejection"]]
tl_oos = [t for t in bears_oos if t.triggers_fired == ["trendline_rejection"]]

print(f"\nTrendline-only IS bears: n={len(tl_is)}   OOS: n={len(tl_oos)}")


def get_spread(trade, ribbon_df, spy_ts_arr):
    """Binary search for ribbon spread_cents at the bar closest to entry_time_et."""
    import numpy as np
    entry_ts = pd.Timestamp(trade.entry_time_et)
    if entry_ts.tzinfo is None:
        # entry_time_et is naive ET (option CSV convention) -- declare ET THEN
        # convert to UTC. tz_localize("UTC") here would mislabel "15:40 ET" as
        # "15:40 UTC" (= 10:40 ET) and hit a premarket bar. See L161 / CONTEXT-94.
        entry_ts = entry_ts.tz_localize("America/New_York").tz_convert("UTC")
    else:
        entry_ts = entry_ts.tz_convert("UTC")
    entry_ns = entry_ts.value  # nanoseconds since epoch
    pos = np.searchsorted(spy_ts_arr, entry_ns)
    for idx in [pos, pos - 1]:
        if 0 <= idx < len(spy_ts_arr):
            state = ribbon_at(ribbon_df, idx)
            if state is not None:
                return state.spread_cents
    return None


# Get spreads for all TRENDLINE IS bears
tl_is_spreads = []
for t in tl_is:
    sp = get_spread(t, ribbon_df, spy_ts_arr)
    if sp is not None:
        tl_is_spreads.append((sp, t.dollar_pnl, t.dollar_pnl > 0))

print(f"\nSpread data available: {len(tl_is_spreads)}/{len(tl_is)}")

# Bucket analysis: spread < 30 vs >= 30 vs >= 50
print()
print("=== IS Trendline Bears by Ribbon Spread at Entry ===")
print(f"{'Bucket':20s} {'n':>4}  {'total':>8}  {'avg':>8}  {'WR':>6}")
print("-" * 60)

# Compute spread distribution
spreads = sorted(set(int(s[0]) for s in tl_is_spreads))
print(f"  spread range: {min(s[0] for s in tl_is_spreads):.0f}c - {max(s[0] for s in tl_is_spreads):.0f}c")
print()

for label, lo, hi in [
    ("spread < 20c",  -999, 20),
    ("spread 20-30c",   20, 30),
    ("spread 30-40c",   30, 40),
    ("spread 40-50c",   40, 50),
    ("spread >= 50c",   50, 9999),
]:
    subset = [(s, p, w) for s, p, w in tl_is_spreads if lo <= s < hi]
    n = len(subset)
    if n == 0:
        continue
    tot = sum(p for _, p, _ in subset)
    wins = sum(1 for _, _, w in subset if w)
    print(f"  {label:18s} {n:4d}  {tot:+8.0f}  {tot/n:+8.0f}  {wins/n:6.1%}")

# Gate test: would require_spread_N gates help?
print()
print("=== Potential Gate: min_trendline_spread_cents (IS only) ===")
total_is_tl_pnl = sum(t.dollar_pnl for t in tl_is)
print(f"  All TRENDLINE IS bears: n={len(tl_is)} total={total_is_tl_pnl:+.0f}")
for threshold in [15, 20, 25, 30, 35, 40]:
    blocked = [(s, p, w) for s, p, w in tl_is_spreads if s < threshold]
    allowed = [(s, p, w) for s, p, w in tl_is_spreads if s >= threshold]
    n_blocked = len(blocked)
    pnl_blocked = sum(p for _, p, _ in blocked)
    n_allowed = len(allowed)
    pnl_allowed = sum(p for _, p, _ in allowed)
    delta = -pnl_blocked  # removing blocked trades = IS_delta
    print(f"  min_spread>={threshold}c: block {n_blocked:2d} bears (pnl={pnl_blocked:+.0f}) "
          f"-> IS_delta={delta:+.0f}  allow {n_allowed:2d} (pnl={pnl_allowed:+.0f})")

# OOS check (much smaller)
print()
print("=== OOS Trendline Bears spread distribution ===")
tl_oos_spreads = []
for t in tl_oos:
    sp = get_spread(t, ribbon_df, spy_ts_arr)
    if sp is not None:
        tl_oos_spreads.append((sp, t.dollar_pnl))
        print(f"  {t.entry_time_et.date()}  spread={sp:.0f}c  pnl={t.dollar_pnl:+.0f}")
