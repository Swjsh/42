"""OP-22 A/B test: block ALL bull (CALL) entries from 11:00-12:00 ET.

IS signal: 11:00-12:00 IS bulls n=11, total=-$89, WR=9.1% (worst TOD bucket).
OOS: 2026-05-20 11:20 confluence+level_reclaim -$42.

Post-hoc filter is valid: all bull trades are min-qty (block_elite_bull already active,
entry_bar_body_pct_min=0.20 applied). Single-position sizing, no cascade.

TZ note: entry_time_et stores naive ET strings (option CSV convention).
Use tz_localize('America/New_York') — NOT tz_localize('UTC') (see CONTEXT-94 / TZ bug lesson).
TOD filtering uses .time() directly on naive ET timestamp — correct (no tz math needed).
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

SW_BOUNDS = [
    (dt.date(2025,  1,  2), dt.date(2025,  5, 30)),
    (dt.date(2025,  6,  2), dt.date(2025, 10, 31)),
    (dt.date(2025, 11,  3), dt.date(2026,  5,  7)),
]
ANCHOR_DATES = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

GATE_START = dt.time(11, 0)
GATE_END   = dt.time(12, 0)

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


def trade_date(t):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.date()


def trade_time(t):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.time()


def is_bull(t):
    return t.side == "C"


def in_gate_window(t):
    return GATE_START <= trade_time(t) < GATE_END


def is_blocked(t):
    return is_bull(t) and in_gate_window(t)


print("Running IS ...")
r_is = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E, **BASE)

print("Running OOS ...")
r_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **BASE)

# IS analysis
bulls_is = [t for t in r_is.trades if is_bull(t)]
blocked_is = [t for t in bulls_is if in_gate_window(t)]
is_delta = -sum(t.dollar_pnl for t in blocked_is)
n_is_removed = len(blocked_is)

print(f"\n=== IS Bulls ({GATE_START}-{GATE_END} block) ===")
print(f"All bulls: n={len(bulls_is)}, pnl={sum(t.dollar_pnl for t in bulls_is):+.0f}")
print(f"Blocked ({GATE_START}-{GATE_END}): n={n_is_removed}, pnl={sum(t.dollar_pnl for t in blocked_is):+.0f}")
print(f"IS_delta = {is_delta:+.0f}")
print(f"\nBlocked IS bulls (detail):")
for t in sorted(blocked_is, key=lambda x: trade_date(x)):
    tf = "+".join(sorted(t.triggers_fired))
    print(f"  {trade_date(t)} {trade_time(t)}  {tf[:40]:40s}  pnl={t.dollar_pnl:+.0f}  {'WIN' if t.dollar_pnl > 0 else 'LOSS'}")

# OOS analysis
bulls_oos = [t for t in r_oos.trades if is_bull(t)]
blocked_oos = [t for t in bulls_oos if in_gate_window(t)]
oos_delta = -sum(t.dollar_pnl for t in blocked_oos)
n_oos_removed = len(blocked_oos)

print(f"\n=== OOS Bulls ===")
print(f"All bulls: n={len(bulls_oos)}, pnl={sum(t.dollar_pnl for t in bulls_oos):+.0f}")
for t in sorted(bulls_oos, key=lambda x: trade_date(x)):
    blocked_mark = " [BLOCKED]" if is_blocked(t) else ""
    tf = "+".join(sorted(t.triggers_fired))
    print(f"  {trade_date(t)} {trade_time(t)}  {tf[:40]:40s}  pnl={t.dollar_pnl:+.0f}{blocked_mark}")
print(f"OOS_delta = {oos_delta:+.0f}")

# OP-22 gates
g1 = is_delta >= 0
g2 = oos_delta > 0
if n_is_removed > 0 and n_oos_removed > 0:
    wf = (oos_delta / n_oos_removed) / (is_delta / n_is_removed)
elif n_oos_removed == 0:
    wf = float("inf")
else:
    wf = 0.0
g3 = wf >= 0.70

print(f"\n=== OP-22 Gates ===")
print(f"G1 IS_delta >= 0:   {is_delta:+.0f}  -> {'PASS' if g1 else 'FAIL'}")
print(f"G2 OOS_delta > 0:   {oos_delta:+.0f}  -> {'PASS' if g2 else 'FAIL'}")
wf_str = f"{wf:.3f}" if wf != float("inf") else "inf"
print(f"G3 WF >= 0.70:      {wf_str}  -> {'PASS' if g3 else 'FAIL'}")

# G4: Sub-window stability
print(f"\n=== G4 Sub-window stability ===")
sw_fail_count = 0
for sw_s, sw_e in SW_BOUNDS:
    sw_blocked = [t for t in blocked_is if sw_s <= trade_date(t) <= sw_e]
    sw_delta = -sum(t.dollar_pnl for t in sw_blocked)
    sw_pass = sw_delta >= 0
    if not sw_pass:
        sw_fail_count += 1
    print(f"  {sw_s}..{sw_e}: n_removed={len(sw_blocked)}, delta={sw_delta:+.0f} -> {'PASS' if sw_pass else 'FAIL'}")

g4 = sw_fail_count <= 1
print(f"SW hurt: {sw_fail_count}/3 -> G4 {'PASS' if g4 else 'FAIL'}")

# G5: Anchor no-regression (anchors are all PUT/BEAR trades — this gate only affects CALLS)
anchor_blocked = [t for t in blocked_is if trade_date(t) in ANCHOR_DATES]
if anchor_blocked:
    print(f"\nG5: ANCHOR BLOCKED: {[(trade_date(t), t.dollar_pnl) for t in anchor_blocked]} -> FAIL")
    g5 = False
else:
    print(f"\nG5: No anchor dates blocked (gate is BULL-only; anchors are PUT trades) -> PASS")
    g5 = True

# Verdict
print(f"\n{'='*60}")
print(f"=== VERDICT: block_bull_{GATE_START.strftime('%H%M')}_{GATE_END.strftime('%H%M')} ===")
gates = {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5}
for g, v in gates.items():
    print(f"  {g}: {'PASS' if v else 'FAIL'}")
verdict = "RATIFY" if all(gates.values()) else "REJECT"
print(f"\n  -> {verdict}")
if not all(gates.values()):
    failed = [g for g, v in gates.items() if not v]
    print(f"  Failed: {', '.join(failed)}")

# TOD analysis to evaluate adjacent windows
print(f"\n=== IS Bull TOD breakdown (all windows, for context) ===")
tod_buckets = {
    "09:35-10:00": (dt.time(9,35), dt.time(10,0)),
    "10:00-11:00": (dt.time(10,0), dt.time(11,0)),
    "11:00-12:00": (dt.time(11,0), dt.time(12,0)),
    "12:00-13:00": (dt.time(12,0), dt.time(13,0)),
    "13:00-14:00": (dt.time(13,0), dt.time(14,0)),
    "14:00-15:00": (dt.time(14,0), dt.time(15,0)),
}
print(f"{'Bucket':15s} {'n':>4}  {'total':>8}  {'avg':>8}  {'WR':>6}  OOS_in_bucket")
for name, (lo, hi) in tod_buckets.items():
    is_set = [t for t in bulls_is if lo <= trade_time(t) < hi]
    oos_set = [t for t in bulls_oos if lo <= trade_time(t) < hi]
    n_i = len(is_set)
    if n_i == 0 and len(oos_set) == 0:
        continue
    tot = sum(t.dollar_pnl for t in is_set)
    wr = sum(1 for t in is_set if t.dollar_pnl > 0) / max(n_i, 1)
    oos_str = ", ".join(f"{trade_date(t)}: {t.dollar_pnl:+d}" for t in oos_set)
    print(f"  {name:13s} {n_i:4d}  {tot:+8.0f}  {tot/max(n_i,1):+8.0f}  {wr:6.1%}  {oos_str or '-'}")
