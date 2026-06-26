"""OP-22 A/B test: block_bull_morning_1000_1130 for Aggressive account.

Hypothesis: IS MORNING bulls (10:00-11:30 ET) WR=14.9%, n=47, total=-$222.
Blocking all BULL entries during 10:00-11:30 ET should show:
- IS_delta = +$222 (remove -$222 P&L bucket)
- OOS_delta: 2 OOS morning bulls visible (2026-05-26 +$0, 2026-05-28 -$40)

Gate is BULL-only (bears in MORNING are excellent: WR=56.2%, +$1,090).

Read-only on production state. No Alpaca calls. $0 cost.
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

GATE_START = dt.time(10, 0)
GATE_END   = dt.time(11, 30)

BASE = dict(
    use_real_fills=True,
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,
    midday_trendline_gate=True,
    premium_stop_pct=-0.07,
    premium_stop_pct_bear=-0.07,
    premium_stop_pct_bull=-0.05,
    tp1_premium_pct=0.75,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=18.0,
    entry_bar_body_pct_min=0.0,
    vix_bear_hard_cap=None,
    min_triggers_bear=1,
    min_triggers_bull=1,
    profit_lock_threshold_pct=0.05,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.20,
    initial_equity=2000.0,
    strike_offset=-2,
    block_conf_lvl_rec_afternoon=True,
    block_conf_lvl_rej_midday_afternoon=True,
    require_bearish_fill_bar=True,
    block_bull_1100_1200=False,
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


def in_gate(t):
    return t.side == "C" and GATE_START <= trade_time(t) < GATE_END


def pnl(trades):
    return sum(t.dollar_pnl for t in trades)


print("=" * 70)
print("OP-22 A/B: block_bull_morning_1000_1130 (AGGRESSIVE)")
print("Block ALL BULL (C) entries 10:00-11:30 ET")
print("Baseline: all current Aggressive gates active (IS n=169, OOS n=21)")
print("=" * 70)

print("\nRunning BASELINE IS/OOS ...")
r_base_is  = run_backtest(spy, vix, start_date=IS_S,  end_date=IS_E,  **BASE)
r_base_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **BASE)

base_is_pnl  = pnl(r_base_is.trades)
base_oos_pnl = pnl(r_base_oos.trades)
print(f"Baseline IS:  n={len(r_base_is.trades)}, pnl={base_is_pnl:+.0f}")
print(f"Baseline OOS: n={len(r_base_oos.trades)}, pnl={base_oos_pnl:+.0f}")

# Identify gated trades in baseline (post-hoc: trades that would be blocked)
blocked_is  = [t for t in r_base_is.trades  if in_gate(t)]
blocked_oos = [t for t in r_base_oos.trades if in_gate(t)]

IS_delta  = -pnl(blocked_is)
OOS_delta = -pnl(blocked_oos)
n_is  = len(blocked_is)
n_oos = len(blocked_oos)

print(f"\nGated IS trades (BULL 10:00-11:30 ET):")
print(f"{'Date':12s} {'Time':8s} {'Combo':35s} {'pnl':>8}  {'W/L'}")
for t in sorted(blocked_is, key=trade_date):
    combo = "+".join(sorted(t.triggers_fired))
    wl = "WIN" if t.dollar_pnl > 0 else ("EVEN" if t.dollar_pnl == 0 else "LOSS")
    print(f"  {trade_date(t)} {trade_time(t)}  {combo:35s}  {t.dollar_pnl:+.0f}  {wl}")
print(f"  n_blocked={n_is}, IS_delta={IS_delta:+.0f}")

print(f"\nGated OOS trades (BULL 10:00-11:30 ET):")
for t in sorted(blocked_oos, key=trade_date):
    combo = "+".join(sorted(t.triggers_fired))
    wl = "WIN" if t.dollar_pnl > 0 else ("EVEN" if t.dollar_pnl == 0 else "LOSS")
    print(f"  {trade_date(t)} {trade_time(t)}  {combo:35s}  {t.dollar_pnl:+.0f}  {wl}")
print(f"  n_blocked={n_oos}, OOS_delta={OOS_delta:+.0f}")

# OP-22 gates
print(f"\n--- OP-22 Gate Evaluation ---")

G1 = IS_delta >= 0
print(f"G1 IS_delta >= 0:   {IS_delta:+.0f} -> {'PASS' if G1 else 'FAIL'}")

G2 = OOS_delta > 0
print(f"G2 OOS_delta > 0:   {OOS_delta:+.0f} -> {'PASS' if G2 else 'FAIL'}")

if n_is > 0 and n_oos > 0 and IS_delta != 0:
    WF = (OOS_delta / n_oos) / (IS_delta / n_is)
elif n_is == 0:
    WF = float("inf")
else:
    WF = 0.0
G3 = WF >= 0.70
print(f"G3 WF >= 0.70:      WF={WF:.3f} -> {'PASS' if G3 else 'FAIL'}")

sw_hurt = 0
print(f"G4 sub-windows:")
for sw_s, sw_e in SW_BOUNDS:
    sw_blocked = [t for t in blocked_is if sw_s <= trade_date(t) <= sw_e]
    sw_delta = -pnl(sw_blocked)
    sw_pass = sw_delta >= 0
    if not sw_pass:
        sw_hurt += 1
    print(f"  {sw_s}..{sw_e}: n={len(sw_blocked)}, delta={sw_delta:+.0f} -> {'PASS' if sw_pass else 'FAIL'}")
G4 = sw_hurt <= 1
print(f"  SW hurt: {sw_hurt}/3 -> G4 {'PASS' if G4 else 'FAIL'}")

anchor_blocked = [t for t in blocked_is if trade_date(t) in ANCHOR_DATES]
G5 = not any(t for t in anchor_blocked if t.dollar_pnl > 0)
print(f"G5 anchor regression: {'anchors blocked: ' + str([(trade_date(t), t.dollar_pnl) for t in anchor_blocked]) if anchor_blocked else 'no anchors blocked'} -> {'PASS' if G5 else 'FAIL'}")

all_pass = G1 and G2 and G3 and G4 and G5
print(f"\n{'ALL GATES PASS — RATIFY' if all_pass else 'GATE FAILS — REJECT'}")

# Candidate summary if pass
if all_pass:
    cand_is_pnl  = base_is_pnl  + IS_delta
    cand_oos_pnl = base_oos_pnl + OOS_delta
    print(f"\nCandidate state (if ratified):")
    print(f"  IS:  n={len(r_base_is.trades)-n_is}, pnl={cand_is_pnl:+.0f} (was {base_is_pnl:+.0f})")
    print(f"  OOS: n={len(r_base_oos.trades)-n_oos}, pnl={cand_oos_pnl:+.0f} (was {base_oos_pnl:+.0f})")
    oos_wr_cand = sum(1 for t in r_base_oos.trades if t not in blocked_oos and t.dollar_pnl > 0) / max(1, len(r_base_oos.trades) - n_oos)
    print(f"  OOS WR (approx): {oos_wr_cand:.1%}")

print("\n[done]")
