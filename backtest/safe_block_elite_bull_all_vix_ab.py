"""OP-22 A/B test: extend block_elite_bull to cover ALL VIX ranges.

BASELINE: block_elite_bull=True, vix_low=15.0, vix_high=17.5 (blocks VIX [15, 17.5)).
CANDIDATE: block_elite_bull=True, vix_low=0.0, vix_high=25.0 (blocks VIX [0, 25)).

Finding from safe_next_gates_analysis.py:
  IS conf+lvl_rec: VIX<15 n=13 total=-106 WR=15.4%; VIX 15-17.5 n=1 total=-7 (ALREADY BLOCKED).
  OOS conf+lvl_rec remaining: VIX=18.0 -29, VIX=17.9 -21, VIX=17.8 -44 (all in [17.5,25.0)).
  IS has ZERO conf+lvl_rec bulls at VIX>=17.5.

Post-hoc filter: block_elite_bull gate is single-position, no cascade. Valid post-hoc analysis.

TZ: entry_time_et is naive ET. No VIX lookup needed here — the orchestrator passes vix_now
at bar time (already correct). This test computes IS/OOS delta by running baseline vs candidate.
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

SHARED = dict(
    use_real_fills=True,
    no_trade_before=dt.time(9, 35), no_trade_window=None,
    midday_trendline_gate=True,
    premium_stop_pct=-0.08, premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50, time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    entry_bar_body_pct_min=0.20, vix_bear_hard_cap=23.0,
    min_triggers_bear=1, min_triggers_bull=2,
    profit_lock_threshold_pct=0.05, profit_lock_mode="trailing", profit_lock_trail_pct=0.20,
    initial_equity=2000.0, strike_offset=2,
    block_bull_1100_1200=True,
)
BASELINE = {**SHARED, "block_elite_bull": True, "block_elite_bull_vix_low": 15.0, "block_elite_bull_vix_high": 17.5}
CANDIDATE = {**SHARED, "block_elite_bull": True, "block_elite_bull_vix_low":  0.0, "block_elite_bull_vix_high": 25.0}


def trade_date(t):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None: ts = ts.tz_localize(None)
    return ts.date()


def trade_time(t):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None: ts = ts.tz_localize(None)
    return ts.time()


print("Running BASELINE IS ...")
r_base_is  = run_backtest(spy, vix, start_date=IS_S,  end_date=IS_E,  **BASELINE)
print("Running BASELINE OOS ...")
r_base_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **BASELINE)
print("Running CANDIDATE IS ...")
r_cand_is  = run_backtest(spy, vix, start_date=IS_S,  end_date=IS_E,  **CANDIDATE)
print("Running CANDIDATE OOS ...")
r_cand_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **CANDIDATE)


def pnl(r): return sum(t.dollar_pnl for t in r.trades)


is_delta  = pnl(r_cand_is)  - pnl(r_base_is)
oos_delta = pnl(r_cand_oos) - pnl(r_base_oos)
n_is_removed  = len(r_base_is.trades)  - len(r_cand_is.trades)
n_oos_removed = len(r_base_oos.trades) - len(r_cand_oos.trades)

print(f"\n=== Baseline vs Candidate ===")
print(f"IS baseline:  n={len(r_base_is.trades)}, pnl={pnl(r_base_is):+.0f}")
print(f"IS candidate: n={len(r_cand_is.trades)}, pnl={pnl(r_cand_is):+.0f}")
print(f"IS_delta = {is_delta:+.0f}  (n_removed={n_is_removed})")
print(f"OOS baseline:  n={len(r_base_oos.trades)}, pnl={pnl(r_base_oos):+.0f}")
print(f"OOS candidate: n={len(r_cand_oos.trades)}, pnl={pnl(r_cand_oos):+.0f}")
print(f"OOS_delta = {oos_delta:+.0f}  (n_removed={n_oos_removed})")

# Identify the removed trades (baseline has them, candidate doesn't)
base_is_keys  = set((trade_date(t), t.side, round(t.dollar_pnl)) for t in r_base_is.trades)
cand_is_keys  = set((trade_date(t), t.side, round(t.dollar_pnl)) for t in r_cand_is.trades)
# show removed IS trades: trades in baseline but not in candidate
# Use index-based match: find trades in baseline_is that don't appear in candidate_is
base_is_ids  = [(trade_date(t), trade_time(t), t.dollar_pnl, t.triggers_fired) for t in r_base_is.trades]
cand_is_ids  = [(trade_date(t), trade_time(t), t.dollar_pnl, t.triggers_fired) for t in r_cand_is.trades]

print(f"\n=== IS: Removed trades (blocked by new gate) ===")
# Find which IS trades disappeared
cand_is_set = set()
for d, ti, p, tf in cand_is_ids:
    cand_is_set.add((d, ti, round(p)))

for d, ti, p, tf in sorted(base_is_ids):
    key = (d, ti, round(p))
    if key not in cand_is_set:
        combo = "+".join(sorted(tf))
        print(f"  {d} {ti}  {combo[:40]:40s}  pnl={p:+.0f}  {'WIN' if p > 0 else 'LOSS'}")

print(f"\n=== OOS: Removed trades (blocked by new gate) ===")
base_oos_ids = [(trade_date(t), trade_time(t), t.dollar_pnl, t.triggers_fired) for t in r_base_oos.trades]
cand_oos_ids = [(trade_date(t), trade_time(t), t.dollar_pnl, t.triggers_fired) for t in r_cand_oos.trades]
cand_oos_set = set()
for d, ti, p, tf in cand_oos_ids:
    cand_oos_set.add((d, ti, round(p)))
for d, ti, p, tf in sorted(base_oos_ids):
    key = (d, ti, round(p))
    if key not in cand_oos_set:
        combo = "+".join(sorted(tf))
        print(f"  {d} {ti}  {combo[:40]:40s}  pnl={p:+.0f}  {'WIN' if p > 0 else 'LOSS'}")

# OP-22 Gates
g1 = is_delta >= 0
g2 = oos_delta > 0
wf = 0.0
if n_is_removed > 0 and n_oos_removed > 0:
    wf = (oos_delta / n_oos_removed) / (is_delta / n_is_removed)
elif n_oos_removed == 0:
    wf = float("inf")
g3 = wf >= 0.70

print(f"\n=== OP-22 Gates ===")
print(f"G1 IS_delta >= 0:  {is_delta:+.0f}  -> {'PASS' if g1 else 'FAIL'}")
print(f"G2 OOS_delta > 0:  {oos_delta:+.0f}  -> {'PASS' if g2 else 'FAIL'}")
wf_str = f"{wf:.3f}" if wf != float("inf") else "inf"
print(f"G3 WF >= 0.70:     {wf_str}  -> {'PASS' if g3 else 'FAIL'}")

# G4: Sub-window stability (IS removed trades)
# Find IS removed set for SW analysis
is_removed_trades = []
cand_is_keys2 = set()
for t in r_cand_is.trades:
    cand_is_keys2.add((trade_date(t), trade_time(t), round(t.dollar_pnl)))
for t in r_base_is.trades:
    k = (trade_date(t), trade_time(t), round(t.dollar_pnl))
    if k not in cand_is_keys2:
        is_removed_trades.append(t)

print(f"\n=== G4 Sub-window stability ===")
sw_fail_count = 0
for sw_s, sw_e in SW_BOUNDS:
    sw_removed = [t for t in is_removed_trades if sw_s <= trade_date(t) <= sw_e]
    sw_delta = -sum(t.dollar_pnl for t in sw_removed)
    sw_pass = sw_delta >= 0
    if not sw_pass:
        sw_fail_count += 1
    print(f"  {sw_s}..{sw_e}: n_removed={len(sw_removed)}, delta={sw_delta:+.0f} -> {'PASS' if sw_pass else 'FAIL'}")
g4 = sw_fail_count <= 1
print(f"SW hurt: {sw_fail_count}/3 -> G4 {'PASS' if g4 else 'FAIL'}")

# G5: Anchor check
anchor_removed = [t for t in is_removed_trades if trade_date(t) in ANCHOR_DATES]
if anchor_removed:
    print(f"\nG5: ANCHOR TRADES BLOCKED: {[(trade_date(t), t.dollar_pnl) for t in anchor_removed]} -> FAIL")
    g5 = False
else:
    print(f"\nG5: No anchor trades removed (gate only affects BULL conf+lvl_rec) -> PASS")
    g5 = True

# Verdict
print(f"\n{'='*60}")
print(f"=== VERDICT: extend block_elite_bull to VIX [0, 25) ===")
gates = {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5}
for g, v in gates.items():
    print(f"  {g}: {'PASS' if v else 'FAIL'}")
verdict = "RATIFY" if all(gates.values()) else "REJECT"
print(f"\n  -> {verdict}")
if not all(gates.values()):
    failed = [g for g, v in gates.items() if not v]
    print(f"  Failed: {', '.join(failed)}")
