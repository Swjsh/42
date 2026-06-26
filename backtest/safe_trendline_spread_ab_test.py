"""OP-22 A/B test: min_trendline_bear_spread_cents=35 for SAFE TRENDLINE-only bears.

Hypothesis: TRENDLINE-only bears (triggers_fired == ['trendline_rejection']) with
ribbon spread < 35c at entry are structural losers in IS. Filter removes them.

Post-hoc filter is valid because:
- TRENDLINE-only bears = 3 contracts (minimum, $600 risk cap at $2K)
- Blocking 1 trade does not cascade to resize any concurrent or subsequent trade
- Ribbon spread is observable at entry bar — no look-ahead

CONTEXT-93 baseline (IS n=53 bears, OOS n=12 bears):
  IS total_bears = +2353 (SUPER+ELITE+TRENDLINE tier)
  OOS total_bears = +644

Gate target: trendline_rejection-ONLY bears with spread_cents < 35
"""
import sys, datetime as dt
sys.path.insert(0, "backtest")
import pandas as pd
import numpy as np
from lib.orchestrator import run_backtest
from lib.ribbon import compute_ribbon, ribbon_at

spy = pd.read_csv("backtest/data/spy_5m_2025-01-01_2026-06-16.csv")
vix = pd.read_csv("backtest/data/vix_5m_2025-01-01_2026-06-16.csv")

IS_S  = dt.date(2025, 1, 2)
IS_E  = dt.date(2026, 5, 7)
OOS_S = dt.date(2026, 5, 8)
OOS_E = dt.date(2026, 6, 15)

SW_BOUNDS = [
    (dt.date(2025,  1,  2), dt.date(2025,  5, 30)),
    (dt.date(2025,  6,  2), dt.date(2025, 10, 31)),
    (dt.date(2025, 11,  3), dt.date(2026,  5,  7)),
]
ANCHOR_DATES = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}
THRESHOLD = 35

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

print("Computing ribbon ...")
ribbon_df = compute_ribbon(spy["close"])
spy_ts = pd.to_datetime(spy["timestamp_et"], utc=True)
spy_ts_arr = spy_ts.values  # numpy int64 nanoseconds


def get_spread(trade):
    entry_ts = pd.Timestamp(trade.entry_time_et)
    if entry_ts.tzinfo is None:
        # entry_time_et is naive ET (option CSV stores ET naive, not UTC).
        # Localize to ET first, then convert to UTC to match spy_ts_arr (UTC-aware).
        entry_ts = entry_ts.tz_localize("America/New_York").tz_convert("UTC")
    else:
        entry_ts = entry_ts.tz_convert("UTC")
    entry_ns = entry_ts.value
    pos = int(np.searchsorted(spy_ts_arr, entry_ns))
    for idx in [pos, pos - 1]:
        if 0 <= idx < len(spy_ts_arr):
            state = ribbon_at(ribbon_df, idx)
            if state is not None:
                return state.spread_cents
    return None


def is_tl_only(t):
    tf = list(t.triggers_fired)
    return t.side == "P" and tf == ["trendline_rejection"]


def trade_date(t):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.date()


def trade_ts_naive(t):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts


print("Running IS ...")
r_is = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E, **BASE)

print("Running OOS ...")
r_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **BASE)

# --- IS analysis ---
tl_is = [t for t in r_is.trades if is_tl_only(t)]
tl_is_spreads = {id(t): get_spread(t) for t in tl_is}
blocked_is = [t for t in tl_is if tl_is_spreads[id(t)] is not None and tl_is_spreads[id(t)] < THRESHOLD]

is_delta = -sum(t.dollar_pnl for t in blocked_is)
n_is_removed = len(blocked_is)

print(f"\n=== IS Trendline-only bears (triggers_fired==['trendline_rejection']) ===")
print(f"Total: n={len(tl_is)}, pnl={sum(t.dollar_pnl for t in tl_is):+.0f}")
print(f"Blocked (spread<{THRESHOLD}c): n={n_is_removed}, pnl={-is_delta:+.0f}")
print(f"Allowed (spread>={THRESHOLD}c): n={len(tl_is)-n_is_removed}, "
      f"pnl={sum(t.dollar_pnl for t in tl_is if t not in blocked_is):+.0f}")
print(f"IS_delta = +{is_delta:.0f}" if is_delta >= 0 else f"IS_delta = {is_delta:.0f}")

print(f"\nBlocked IS bears (detail):")
for t in sorted(blocked_is, key=trade_ts_naive):
    sp = tl_is_spreads[id(t)]
    print(f"  {trade_date(t)}  spread={sp:.0f}c  pnl={t.dollar_pnl:+.0f}  {'WIN' if t.dollar_pnl > 0 else 'LOSS'}")

# --- OOS analysis ---
tl_oos = [t for t in r_oos.trades if is_tl_only(t)]
tl_oos_spreads = {id(t): get_spread(t) for t in tl_oos}
blocked_oos = [t for t in tl_oos if tl_oos_spreads[id(t)] is not None and tl_oos_spreads[id(t)] < THRESHOLD]

oos_delta = -sum(t.dollar_pnl for t in blocked_oos)
n_oos_removed = len(blocked_oos)

print(f"\n=== OOS Trendline-only bears ===")
print(f"Total: n={len(tl_oos)}, pnl={sum(t.dollar_pnl for t in tl_oos):+.0f}")
for t in sorted(tl_oos, key=trade_ts_naive):
    sp = tl_oos_spreads[id(t)]
    tag = " [BLOCKED]" if t in blocked_oos else ""
    print(f"  {trade_date(t)}  spread={sp:.0f}c  pnl={t.dollar_pnl:+.0f}{tag}")
print(f"Blocked: n={n_oos_removed}, pnl={-oos_delta:+.0f}")
print(f"OOS_delta = {oos_delta:+.0f}")

# --- OP-22 gate evaluation ---
g1 = is_delta >= 0
g2 = oos_delta > 0

if n_is_removed > 0 and n_oos_removed > 0:
    is_per_trade = is_delta / n_is_removed
    oos_per_trade = oos_delta / n_oos_removed
    wf = oos_per_trade / is_per_trade if is_per_trade != 0 else float("inf")
elif n_oos_removed == 0:
    wf = float("inf")  # gate removes IS losers, harms no OOS trade
    oos_per_trade = 0
    is_per_trade = is_delta / n_is_removed if n_is_removed > 0 else 0
else:
    wf = 0.0
    is_per_trade = 0
    oos_per_trade = oos_delta / n_oos_removed

g3 = wf >= 0.70

print(f"\n=== OP-22 Gates ===")
print(f"G1 IS_delta >= 0:   {is_delta:+.0f}  -> {'PASS' if g1 else 'FAIL'}")
print(f"G2 OOS_delta > 0:   {oos_delta:+.0f}  -> {'PASS' if g2 else 'FAIL'}")
wf_str = f"{wf:.3f}" if wf != float("inf") else "inf"
print(f"G3 WF >= 0.70:      {wf_str}  (IS/trade={is_per_trade:.1f}, OOS/trade={oos_per_trade:.1f})  -> {'PASS' if g3 else 'FAIL'}")
print(f"   NOTE: n_oos_removed={n_oos_removed} — WF confidence LOW (single data point)")

# G4: Sub-window stability
print(f"\n=== G4 Sub-window stability ===")
sw_pass_count = 0
sw_fail_count = 0
for sw_s, sw_e in SW_BOUNDS:
    sw_blocked = [t for t in blocked_is if sw_s <= trade_date(t) <= sw_e]
    sw_delta = -sum(t.dollar_pnl for t in sw_blocked)
    sw_pass = sw_delta >= 0
    if sw_pass:
        sw_pass_count += 1
    else:
        sw_fail_count += 1
    print(f"  {sw_s}..{sw_e}: n_removed={len(sw_blocked)}, delta={sw_delta:+.0f} -> {'PASS' if sw_pass else 'FAIL'}")

g4 = sw_fail_count <= 1
print(f"SW hurt: {sw_fail_count}/3 -> G4 {'PASS' if g4 else 'FAIL'}")

# G5: Anchor no-regression
print(f"\n=== G5 Anchor dates check ===")
anchor_blocked = [t for t in blocked_is if trade_date(t) in ANCHOR_DATES]
if anchor_blocked:
    for t in anchor_blocked:
        sp = tl_is_spreads[id(t)]
        print(f"  BLOCKED ANCHOR: {trade_date(t)}  spread={sp:.0f}c  pnl={t.dollar_pnl:+.0f}")
    g5 = False
else:
    print(f"  No anchor-date trades blocked. PASS")
    g5 = True

# Also verify anchor trades survive (they should be ELITE/SUPER, not trendline-only)
print(f"  Anchor date bears (all tiers):")
for t in r_is.trades:
    if t.side == "P" and trade_date(t) in ANCHOR_DATES:
        tf = sorted(t.triggers_fired)
        print(f"    {trade_date(t)}: pnl={t.dollar_pnl:+.0f}, triggers={tf}")

# --- Final verdict ---
print(f"\n{'='*60}")
print(f"=== VERDICT: min_trendline_bear_spread_cents={THRESHOLD} ===")
gate_results = {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5}
for g, v in gate_results.items():
    print(f"  {g}: {'PASS' if v else 'FAIL'}")

all_pass = all(gate_results.values())
verdict = "RATIFY" if all_pass else "REJECT"
print(f"\n  -> {verdict}")
if not all_pass:
    failed = [g for g, v in gate_results.items() if not v]
    print(f"  Failed gates: {', '.join(failed)}")

# Report implementation note
print(f"\n=== Implementation note ===")
print(f"This gate requires adding min_trendline_bear_spread_cents param to orchestrator.")
print(f"Pre-compute ribbon_df before bar loop, gate TRENDLINE-only bear entries on spread_cents.")
print(f"Impact: ~{n_is_removed/16:.1f} trades/month removed IS, {n_oos_removed} removed OOS (n=38 days)")
