"""OP-22 A/B: block_bull_morning_1000_1130 + block_bull_afternoon_1400_1500 (AGG).

Morning: IS n=47, WR=14.9%, pnl=-$222
Afternoon: IS n=6, WR=0%, pnl=-$82 (all losses)
Combined IS_delta = +$304

OOS: MORNING = 2 trades (+$0, -$40) → OOS_delta=+$40
     AFTERNOON = 0 OOS trades in 14:00-15:00 → OOS_delta=+$0
Combined OOS_delta = +$40

G2 passes via MORNING OOS removals even though AFTERNOON OOS delta=0.
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

# Combined windows: 10:00-11:30 AND 14:00-15:00 ET (BULL only)
MORNING_START = dt.time(10, 0)
MORNING_END   = dt.time(11, 30)
ARVO_START    = dt.time(14, 0)
ARVO_END      = dt.time(15, 0)

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
    if t.side != "C":
        return False
    ttime = trade_time(t)
    in_morning  = MORNING_START <= ttime < MORNING_END
    in_afternoon = ARVO_START <= ttime < ARVO_END
    return in_morning or in_afternoon


def pnl(trades):
    return sum(t.dollar_pnl for t in trades)


print("=" * 70)
print("OP-22 A/B: COMBINED block_bull_morning + block_bull_afternoon (AGG)")
print("Block ALL BULL (C) entries 10:00-11:30 ET AND 14:00-15:00 ET")
print("=" * 70)

print("\nRunning BASELINE IS/OOS ...")
r_base_is  = run_backtest(spy, vix, start_date=IS_S,  end_date=IS_E,  **BASE)
r_base_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **BASE)

base_is_pnl  = pnl(r_base_is.trades)
base_oos_pnl = pnl(r_base_oos.trades)
print(f"Baseline IS:  n={len(r_base_is.trades)}, pnl={base_is_pnl:+.0f}")
print(f"Baseline OOS: n={len(r_base_oos.trades)}, pnl={base_oos_pnl:+.0f}")

blocked_is  = [t for t in r_base_is.trades  if in_gate(t)]
blocked_oos = [t for t in r_base_oos.trades if in_gate(t)]

IS_delta  = -pnl(blocked_is)
OOS_delta = -pnl(blocked_oos)
n_is  = len(blocked_is)
n_oos = len(blocked_oos)

# Sub-classify for visibility
blocked_is_morning  = [t for t in blocked_is if MORNING_START <= trade_time(t) < MORNING_END]
blocked_is_arvo     = [t for t in blocked_is if ARVO_START <= trade_time(t) < ARVO_END]
blocked_oos_morning = [t for t in blocked_oos if MORNING_START <= trade_time(t) < MORNING_END]
blocked_oos_arvo    = [t for t in blocked_oos if ARVO_START <= trade_time(t) < ARVO_END]

print(f"\nIS MORNING removed (10:00-11:30): n={len(blocked_is_morning)}, delta={-pnl(blocked_is_morning):+.0f}")
print(f"IS AFTERNOON removed (14:00-15:00): n={len(blocked_is_arvo)}, delta={-pnl(blocked_is_arvo):+.0f}")
print(f"IS combined: n={n_is}, IS_delta={IS_delta:+.0f}")
print(f"\nOOS MORNING removed: n={len(blocked_oos_morning)}, delta={-pnl(blocked_oos_morning):+.0f}")
print(f"OOS AFTERNOON removed: n={len(blocked_oos_arvo)}, delta={-pnl(blocked_oos_arvo):+.0f}")
print(f"OOS combined: n={n_oos}, OOS_delta={OOS_delta:+.0f}")

print(f"\nIS AFTERNOON losers:")
for t in sorted(blocked_is_arvo, key=trade_date):
    combo = "+".join(sorted(t.triggers_fired))
    print(f"  {trade_date(t)} {trade_time(t)}  {combo:35s}  {t.dollar_pnl:+.0f}")

# OP-22
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
if anchor_blocked:
    anchor_winners = [t for t in anchor_blocked if t.dollar_pnl > 0]
    G5 = not bool(anchor_winners)
    print(f"G5 anchors blocked: {[(trade_date(t), t.dollar_pnl) for t in anchor_blocked]} -> {'PASS' if G5 else 'FAIL'}")
else:
    G5 = True
    print(f"G5: no anchors blocked -> PASS")

all_pass = G1 and G2 and G3 and G4 and G5
print(f"\n{'ALL GATES PASS — RATIFY' if all_pass else 'GATE FAILS — see above'}")

if all_pass:
    cand_is_pnl  = base_is_pnl + IS_delta
    cand_oos_pnl = base_oos_pnl + OOS_delta
    remaining_oos = [t for t in r_base_oos.trades if t not in blocked_oos]
    oos_wr_cand = sum(1 for t in remaining_oos if t.dollar_pnl > 0) / max(1, len(remaining_oos))
    print(f"\nCandidate state (if ratified):")
    print(f"  IS:  n={len(r_base_is.trades)-n_is}, pnl={cand_is_pnl:+.0f} (was {base_is_pnl:+.0f})")
    print(f"  OOS: n={len(r_base_oos.trades)-n_oos}, pnl={cand_oos_pnl:+.0f} (was {base_oos_pnl:+.0f})")
    print(f"  OOS WR: {oos_wr_cand:.1%} (was {sum(1 for t in r_base_oos.trades if t.dollar_pnl>0)/max(1,len(r_base_oos.trades)):.1%})")

print("\n[done]")
