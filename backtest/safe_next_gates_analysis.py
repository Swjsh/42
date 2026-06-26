"""Next-gate research: bear TOD breakdown + confluence+level_reclaim VIX analysis.

After all current ratified gates, run post-hoc analysis to find next gateable patterns.
Current active gates: entry_bar_body_pct_min=0.20, block_level_rejection, block_elite_bull
                     (VIX 15-17.5), midday_trendline_gate, vix_bear_hard_cap=23.0,
                     block_bull_1100_1200.

Two research directions:
  A) Bear TOD breakdown — find if any time windows have structural weakness
  B) Confluence+level_reclaim VIX analysis — bulls, find if extending block_elite_bull
     to wider VIX range (beyond 17.5) can pass G1+G2
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

SW_BOUNDS = [
    (dt.date(2025,  1,  2), dt.date(2025,  5, 30)),
    (dt.date(2025,  6,  2), dt.date(2025, 10, 31)),
    (dt.date(2025, 11,  3), dt.date(2026,  5,  7)),
]
ANCHOR_DATES = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

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
    block_bull_1100_1200=True,
)

print("Running IS + OOS ...")
r_is  = run_backtest(spy, vix, start_date=IS_S,  end_date=IS_E,  **BASE)
r_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **BASE)

bears_is  = [t for t in r_is.trades  if t.side == "P"]
bears_oos = [t for t in r_oos.trades if t.side == "P"]
bulls_is  = [t for t in r_is.trades  if t.side == "C"]
bulls_oos = [t for t in r_oos.trades if t.side == "C"]

def trade_time(t):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None: ts = ts.tz_localize(None)
    return ts.time()

def trade_date(t):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None: ts = ts.tz_localize(None)
    return ts.date()

print(f"\nIS: n={len(r_is.trades)} (bears={len(bears_is)}, bulls={len(bulls_is)}), total={sum(t.dollar_pnl for t in r_is.trades):+.0f}")
print(f"OOS: n={len(r_oos.trades)} (bears={len(bears_oos)}, bulls={len(bulls_oos)}), total={sum(t.dollar_pnl for t in r_oos.trades):+.0f}")

# ============================================================
# SECTION A: Bear TOD breakdown
# ============================================================
TOD_BUCKETS = [
    ("09:35-10:00", dt.time(9, 35), dt.time(10, 0)),
    ("10:00-11:00", dt.time(10, 0), dt.time(11, 0)),
    ("11:00-12:00", dt.time(11, 0), dt.time(12, 0)),
    ("12:00-13:00", dt.time(12, 0), dt.time(13, 0)),
    ("13:00-14:00", dt.time(13, 0), dt.time(14, 0)),
    ("14:00-15:00", dt.time(14, 0), dt.time(15, 0)),
]

print(f"\n{'='*70}")
print(f"=== A. IS Bear TOD Breakdown (after all current gates) ===")
print(f"{'Bucket':15s} {'n':>4}  {'total':>8}  {'avg':>8}  {'WR':>6}  OOS_in_bucket")
print("-" * 90)
for name, lo, hi in TOD_BUCKETS:
    is_set  = [t for t in bears_is  if lo <= trade_time(t) < hi]
    oos_set = [t for t in bears_oos if lo <= trade_time(t) < hi]
    n_i = len(is_set)
    if n_i == 0 and len(oos_set) == 0:
        continue
    tot = sum(t.dollar_pnl for t in is_set)
    wr  = sum(1 for t in is_set if t.dollar_pnl > 0) / max(n_i, 1)
    oos_str = ", ".join(f"{trade_date(t)}: {t.dollar_pnl:+.0f}" for t in oos_set)
    print(f"  {name:13s} {n_i:4d}  {tot:+8.0f}  {tot/max(n_i,1):+8.0f}  {wr:6.1%}  {oos_str or '-'}")

# ============================================================
# SECTION B: Confluence+level_reclaim VIX analysis (bulls)
# ============================================================
def is_conf_lvl_rec(t):
    tf = set(t.triggers_fired)
    combo = "+".join(sorted(tf))
    return combo == "confluence+level_reclaim"

conf_lr_is  = [t for t in bulls_is  if is_conf_lvl_rec(t)]
conf_lr_oos = [t for t in bulls_oos if is_conf_lvl_rec(t)]

print(f"\n{'='*70}")
print(f"=== B. Confluence+level_reclaim Bulls — VIX distribution ===")
print(f"IS n={len(conf_lr_is)}, total={sum(t.dollar_pnl for t in conf_lr_is):+.0f}")
print(f"OOS n={len(conf_lr_oos)}, total={sum(t.dollar_pnl for t in conf_lr_oos):+.0f}")

VIX_BUCKETS = [
    ("<15",  0.0,  15.0),
    ("15-17.5", 15.0, 17.5),
    ("17.5-20", 17.5, 20.0),
    ("20-23",  20.0, 23.0),
    ("23+",    23.0, 999.0),
]

print(f"\nIS by VIX:")
print(f"{'VIX':12s} {'n':>4}  {'total':>8}  {'avg':>8}  {'WR':>6}")
for name, vlo, vhi in VIX_BUCKETS:
    # VIX at entry time: we need to check vix at the bar. We don't have it directly on TradeFill.
    # Use entry_time to find the bar in the VIX data (best effort, tz-naive lookup).
    pass

# Actually, we need to get VIX from the raw data. TradeFill doesn't carry it.
# Load VIX CSV and build a lookup.
vix_df = pd.read_csv("backtest/data/vix_5m_2025-01-01_2026-06-16.csv")
vix_df["ts"] = pd.to_datetime(vix_df["timestamp_et"], utc=True)
vix_df = vix_df.sort_values("ts").reset_index(drop=True)
vix_ts_arr = vix_df["ts"].view("int64").to_numpy()

def get_vix_at_entry(t):
    import numpy as np
    entry_ts = pd.Timestamp(t.entry_time_et)
    if entry_ts.tzinfo is None:
        entry_ts = entry_ts.tz_localize("America/New_York").tz_convert("UTC")
    else:
        entry_ts = entry_ts.tz_convert("UTC")
    ns = entry_ts.value
    pos = int(np.searchsorted(vix_ts_arr, ns))
    for idx in [pos, pos - 1, pos + 1]:
        if 0 <= idx < len(vix_ts_arr):
            return float(vix_df.iloc[idx]["close"])
    return None

print(f"\nIS confluence+level_reclaim by VIX bucket:")
print(f"{'VIX':12s} {'n':>4}  {'total':>8}  {'avg':>8}  {'WR':>6}  IS_delta_if_blocked")
for name, vlo, vhi in VIX_BUCKETS:
    bucket = []
    for t in conf_lr_is:
        v = get_vix_at_entry(t)
        if v is not None and vlo <= v < vhi:
            bucket.append((t, v))
    n = len(bucket)
    if n == 0:
        print(f"  {name:10s} {n:4d}  (no trades)")
        continue
    tot = sum(t.dollar_pnl for t, _ in bucket)
    wr  = sum(1 for t, _ in bucket if t.dollar_pnl > 0) / n
    print(f"  {name:10s} {n:4d}  {tot:+8.0f}  {tot/n:+8.0f}  {wr:6.1%}  IS_delta_if_blocked={-tot:+.0f}")

print(f"\nOOS confluence+level_reclaim (individual, with VIX):")
for t in sorted(conf_lr_oos, key=lambda x: trade_date(x)):
    v = get_vix_at_entry(t)
    v_str = f"{v:.1f}" if v is not None else "N/A"
    print(f"  {trade_date(t)} {trade_time(t)}  VIX={v_str}  pnl={t.dollar_pnl:+.0f}")

# ============================================================
# SECTION C: OP-22 feasibility check for extending block_elite_bull
# Check: block confluence+level_reclaim when VIX >= 17.5 (extending from current 15-17.5)
# ============================================================
print(f"\n{'='*70}")
print(f"=== C. OP-22 Feasibility: block_elite_bull_vix_high extended to 25.0 ===")
print("(Extends current block from VIX [15,17.5) to VIX [15,25.0))")

is_newly_blocked = []
for t in conf_lr_is:
    v = get_vix_at_entry(t)
    if v is not None and 17.5 <= v < 25.0:
        is_newly_blocked.append((t, v))

print(f"\nIS newly blocked in VIX [17.5, 25.0) (not already blocked by [15,17.5)):")
if is_newly_blocked:
    for t, v in sorted(is_newly_blocked, key=lambda x: trade_date(x[0])):
        print(f"  {trade_date(t)} {trade_time(t)}  VIX={v:.1f}  pnl={t.dollar_pnl:+.0f}")
    nb_is_delta = -sum(t.dollar_pnl for t, _ in is_newly_blocked)
    print(f"IS_delta from extending: {nb_is_delta:+.0f} (n={len(is_newly_blocked)})")
else:
    print("  None")

oos_newly_blocked = []
for t in conf_lr_oos:
    v = get_vix_at_entry(t)
    if v is not None and 17.5 <= v < 25.0:
        oos_newly_blocked.append((t, v))

print(f"\nOOS newly blocked in VIX [17.5, 25.0):")
if oos_newly_blocked:
    for t, v in sorted(oos_newly_blocked, key=lambda x: trade_date(x[0])):
        print(f"  {trade_date(t)} {trade_time(t)}  VIX={v:.1f}  pnl={t.dollar_pnl:+.0f}")
    nb_oos_delta = -sum(t.dollar_pnl for t, _ in oos_newly_blocked)
    print(f"OOS_delta from extending: {nb_oos_delta:+.0f} (n={len(oos_newly_blocked)})")
else:
    print("  None")
    nb_oos_delta = 0

if is_newly_blocked and oos_newly_blocked:
    n_is = len(is_newly_blocked)
    n_oos = len(oos_newly_blocked)
    is_d = -sum(t.dollar_pnl for t, _ in is_newly_blocked)
    oos_d = -sum(t.dollar_pnl for t, _ in oos_newly_blocked)
    wf = (oos_d / n_oos) / (is_d / n_is) if is_d != 0 else 0
    print(f"\nProvisional OP-22:")
    print(f"  G1 IS_delta >= 0: {is_d:+.0f} -> {'PASS' if is_d >= 0 else 'FAIL'}")
    print(f"  G2 OOS_delta > 0: {oos_d:+.0f} -> {'PASS' if oos_d > 0 else 'FAIL'}")
    print(f"  G3 WF >= 0.70: {wf:.3f} -> {'PASS' if wf >= 0.70 else 'FAIL'}")
elif not is_newly_blocked:
    print("\nG1 trivially PASS (n_is=0 blocks). G2 depends on OOS.")
elif not oos_newly_blocked:
    print("\nG2 FAIL: no OOS trades newly blocked in this VIX range.")

# ============================================================
# SECTION D: Bear trigger composition breakdown
# ============================================================
print(f"\n{'='*70}")
print(f"=== D. IS Bear Trigger Breakdown (after current gates) ===")
from collections import defaultdict
bear_combo_stats = defaultdict(lambda: {"n": 0, "total": 0.0, "wins": 0})
for t in bears_is:
    combo = "+".join(sorted(t.triggers_fired))
    bear_combo_stats[combo]["n"] += 1
    bear_combo_stats[combo]["total"] += t.dollar_pnl
    bear_combo_stats[combo]["wins"] += int(t.dollar_pnl > 0)

rows = sorted(bear_combo_stats.items(), key=lambda x: x[1]["total"])
print(f"{'Triggers':55s} {'n':>4}  {'total':>8}  {'avg':>8}  {'WR':>6}")
print("-" * 90)
for combo, s in rows:
    if s["n"] == 0: continue
    wr = s["wins"] / s["n"]
    print(f"  {combo[:53]:53s} {s['n']:4d}  {s['total']:+8.0f}  {s['total']/s['n']:+8.0f}  {wr:6.1%}")

# OOS bear breakdown
print(f"\n=== D2. OOS Bears (individual) ===")
for t in sorted(bears_oos, key=lambda x: trade_date(x)):
    combo = "+".join(sorted(t.triggers_fired))
    v = get_vix_at_entry(t)
    v_str = f"{v:.1f}" if v is not None else "N/A"
    print(f"  {trade_date(t)} {trade_time(t)}  VIX={v_str}  {combo[:40]:40s}  pnl={t.dollar_pnl:+.0f}")
