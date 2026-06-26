"""Aggressive account baseline analysis + gate candidate identification.

Runs IS/OOS backtest with ALL currently ratified Aggressive gates active, then
breaks down remaining trades by direction, trigger combo, and TOD bucket to
surface next OP-22 gate candidates.

Read-only on production state. Does not call any Alpaca tool or order function.
"""
import sys, datetime as dt, numpy as np
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

# All currently ratified Aggressive gates active (agg/params.json as of 2026-06-18)
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


def trigger_combo(t):
    return "+".join(sorted(t.triggers_fired))


def tod_bucket(t_time):
    if t_time < dt.time(10, 0):
        return "OPEN_DRIVE"
    elif t_time < dt.time(11, 30):
        return "MORNING"
    elif t_time < dt.time(14, 0):
        return "MIDDAY"
    elif t_time < dt.time(15, 0):
        return "AFTERNOON"
    else:
        return "POWER_HOUR"


def pnl(r):
    return sum(t.dollar_pnl for t in r.trades)


print("=" * 70)
print("AGGRESSIVE ACCOUNT BASELINE — all ratified gates active")
print("IS: 2025-01-02 to 2026-05-07 | OOS: 2026-05-08 to 2026-06-15")
print("ITM-2 | 50% risk cap | bear stop -7% | bull stop -5% | TP1 +75%")
print("=" * 70)

print("\nRunning IS ...")
r_is  = run_backtest(spy, vix, start_date=IS_S,  end_date=IS_E,  **BASE)
print("Running OOS ...")
r_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **BASE)

is_pnl  = pnl(r_is)
oos_pnl = pnl(r_oos)
is_wr   = sum(1 for t in r_is.trades  if t.dollar_pnl > 0) / max(1, len(r_is.trades))
oos_wr  = sum(1 for t in r_oos.trades if t.dollar_pnl > 0) / max(1, len(r_oos.trades))

print(f"\n--- BASELINE ---")
print(f"IS:  n={len(r_is.trades):3d}, pnl={is_pnl:+7.0f}, WR={is_wr:.1%}, avg={is_pnl/max(1,len(r_is.trades)):+.0f}/trade")
print(f"OOS: n={len(r_oos.trades):3d}, pnl={oos_pnl:+7.0f}, WR={oos_wr:.1%}, avg={oos_pnl/max(1,len(r_oos.trades)):+.0f}/trade")

# ── Split by direction ──────────────────────────────────────────────────────
for label, trades in [("IS", r_is.trades), ("OOS", r_oos.trades)]:
    bears = [t for t in trades if t.side == "P"]
    bulls = [t for t in trades if t.side == "C"]
    print(f"\n{label} by direction:")
    for name, sub in [("BEARS(P)", bears), ("BULLS(C)", bulls)]:
        if not sub:
            print(f"  {name}: n=0")
            continue
        sub_wr = sum(1 for t in sub if t.dollar_pnl > 0) / len(sub)
        print(f"  {name}: n={len(sub)}, pnl={sum(t.dollar_pnl for t in sub):+.0f}, WR={sub_wr:.1%}")

# ── Section A: TOD breakdown (bears) ───────────────────────────────────────
print("\n" + "=" * 70)
print("SECTION A — IS Bear TOD breakdown (all remaining bears)")
print("=" * 70)
is_bears = [t for t in r_is.trades if t.side == "P"]
tod_data = {}
for t in is_bears:
    bkt = tod_bucket(trade_time(t))
    if bkt not in tod_data:
        tod_data[bkt] = []
    tod_data[bkt].append(t)

print(f"{'Bucket':15s} {'n':>4}  {'pnl':>8}  {'WR':>7}  {'avg':>7}")
for bkt in ["OPEN_DRIVE", "MORNING", "MIDDAY", "AFTERNOON", "POWER_HOUR"]:
    sub = tod_data.get(bkt, [])
    if not sub:
        print(f"  {bkt:13s}  n=0")
        continue
    sub_pnl = sum(t.dollar_pnl for t in sub)
    sub_wr  = sum(1 for t in sub if t.dollar_pnl > 0) / len(sub)
    print(f"  {bkt:13s}  {len(sub):3d}  {sub_pnl:+8.0f}  {sub_wr:6.1%}  {sub_pnl/len(sub):+7.0f}")

# ── Section B: TOD breakdown (bulls) ───────────────────────────────────────
print("\n" + "=" * 70)
print("SECTION B — IS Bull TOD breakdown (all remaining bulls)")
print("=" * 70)
is_bulls = [t for t in r_is.trades if t.side == "C"]
bull_tod_data = {}
for t in is_bulls:
    bkt = tod_bucket(trade_time(t))
    if bkt not in bull_tod_data:
        bull_tod_data[bkt] = []
    bull_tod_data[bkt].append(t)

print(f"{'Bucket':15s} {'n':>4}  {'pnl':>8}  {'WR':>7}  {'avg':>7}")
for bkt in ["OPEN_DRIVE", "MORNING", "MIDDAY", "AFTERNOON", "POWER_HOUR"]:
    sub = bull_tod_data.get(bkt, [])
    if not sub:
        print(f"  {bkt:13s}  n=0")
        continue
    sub_pnl = sum(t.dollar_pnl for t in sub)
    sub_wr  = sum(1 for t in sub if t.dollar_pnl > 0) / len(sub)
    print(f"  {bkt:13s}  {len(sub):3d}  {sub_pnl:+8.0f}  {sub_wr:6.1%}  {sub_pnl/len(sub):+7.0f}")

# ── Section C: trigger combo breakdown ────────────────────────────────────
print("\n" + "=" * 70)
print("SECTION C — IS Trigger combo breakdown (all directions)")
print("=" * 70)
combo_data = {}
for t in r_is.trades:
    combo = trigger_combo(t)
    if combo not in combo_data:
        combo_data[combo] = []
    combo_data[combo].append(t)

combos_sorted = sorted(combo_data.items(), key=lambda x: sum(t.dollar_pnl for t in x[1]))
print(f"{'Combo':40s} {'n':>4}  {'pnl':>8}  {'WR':>7}  {'avg':>7}")
for combo, sub in combos_sorted:
    sub_pnl = sum(t.dollar_pnl for t in sub)
    sub_wr  = sum(1 for t in sub if t.dollar_pnl > 0) / len(sub)
    print(f"  {combo:38s}  {len(sub):3d}  {sub_pnl:+8.0f}  {sub_wr:6.1%}  {sub_pnl/len(sub):+7.0f}")

# ── Section D: OOS detail ──────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SECTION D — OOS trade detail")
print("=" * 70)
for t in sorted(r_oos.trades, key=lambda x: trade_date(x)):
    combo = trigger_combo(t)
    bkt   = tod_bucket(trade_time(t))
    print(f"  {trade_date(t)} {trade_time(t)}  {'P' if t.side=='P' else 'C'}  {combo:35s}  {bkt:12s}  {t.dollar_pnl:+.0f}")

oos_bears = [t for t in r_oos.trades if t.side == "P"]
oos_bulls = [t for t in r_oos.trades if t.side == "C"]
print(f"\nOOS bears: n={len(oos_bears)}, pnl={sum(t.dollar_pnl for t in oos_bears):+.0f}, WR={sum(1 for t in oos_bears if t.dollar_pnl>0)/max(1,len(oos_bears)):.1%}")
print(f"OOS bulls: n={len(oos_bulls)}, pnl={sum(t.dollar_pnl for t in oos_bulls):+.0f}, WR={sum(1 for t in oos_bulls if t.dollar_pnl>0)/max(1,len(oos_bulls)):.1%}")

# ── Section E: VIX distribution for bears ────────────────────────────────
print("\n" + "=" * 70)
print("SECTION E — IS Bear VIX distribution")
print("=" * 70)
vix_df = pd.read_csv("backtest/data/vix_5m_2025-01-01_2026-06-16.csv")
vix_df["ts_utc"] = pd.to_datetime(vix_df["timestamp_et"], utc=True)
vix_df = vix_df.sort_values("ts_utc").reset_index(drop=True)
vix_ts = vix_df["ts_utc"].view("int64").to_numpy()


def get_vix(t):
    entry_ts = pd.Timestamp(t.entry_time_et)
    if entry_ts.tzinfo is None:
        entry_ts = entry_ts.tz_localize("America/New_York").tz_convert("UTC")
    else:
        entry_ts = entry_ts.tz_convert("UTC")
    pos = int(np.searchsorted(vix_ts, entry_ts.value))
    for idx in [pos, pos - 1]:
        if 0 <= idx < len(vix_ts):
            return float(vix_df.iloc[idx]["close"])
    return None


# VIX buckets for bears
vix_buckets_bear = {"<15": [], "15-20": [], "20-23": [], "23-25": [], "25+": []}
for t in is_bears:
    v = get_vix(t)
    if v is None:
        continue
    if v < 15:
        vix_buckets_bear["<15"].append(t)
    elif v < 20:
        vix_buckets_bear["15-20"].append(t)
    elif v < 23:
        vix_buckets_bear["20-23"].append(t)
    elif v < 25:
        vix_buckets_bear["23-25"].append(t)
    else:
        vix_buckets_bear["25+"].append(t)

print(f"{'VIX Bucket':12s}  {'n':>4}  {'pnl':>8}  {'WR':>7}  {'avg':>7}")
for bkt, sub in vix_buckets_bear.items():
    if not sub:
        print(f"  {bkt:10s}   n=0")
        continue
    sub_pnl = sum(t.dollar_pnl for t in sub)
    sub_wr  = sum(1 for t in sub if t.dollar_pnl > 0) / len(sub)
    print(f"  {bkt:10s}  {len(sub):3d}  {sub_pnl:+8.0f}  {sub_wr:6.1%}  {sub_pnl/len(sub):+7.0f}")

# ── Section F: trigger breakdown by side + combo ───────────────────────────
print("\n" + "=" * 70)
print("SECTION F — IS breakdown by DIRECTION + COMBO + TOD")
print("=" * 70)
for side_label, side_key in [("BEAR(P)", "P"), ("BULL(C)", "C")]:
    sub_trades = [t for t in r_is.trades if t.side == side_key]
    if not sub_trades:
        print(f"\n{side_label}: no trades")
        continue
    print(f"\n{side_label} (n={len(sub_trades)}, pnl={sum(t.dollar_pnl for t in sub_trades):+.0f}):")
    print(f"  {'combo':38s} {'TOD':12s} {'n':>4} {'pnl':>8} {'WR':>7}")
    # Group by combo+tod
    from collections import defaultdict
    cg = defaultdict(list)
    for t in sub_trades:
        key = (trigger_combo(t), tod_bucket(trade_time(t)))
        cg[key].append(t)
    for (combo, bkt), items in sorted(cg.items(), key=lambda x: sum(t.dollar_pnl for t in x[1])):
        sub_pnl = sum(t.dollar_pnl for t in items)
        sub_wr  = sum(1 for t in items if t.dollar_pnl > 0) / len(items)
        print(f"  {combo:38s} {bkt:12s} {len(items):3d} {sub_pnl:+8.0f} {sub_wr:6.1%}")

# ── Section G: sub-window health ──────────────────────────────────────────
print("\n" + "=" * 70)
print("SECTION G — IS sub-window health (4 quarters check)")
print("=" * 70)
sw_4 = [
    (dt.date(2025,  1,  2), dt.date(2025,  5, 30)),
    (dt.date(2025,  6,  2), dt.date(2025, 10, 31)),
    (dt.date(2025, 11,  3), dt.date(2026,  2, 28)),
    (dt.date(2026,  3,  1), dt.date(2026,  5,  7)),
]
print(f"{'Window':30s}  {'n':>4}  {'pnl':>8}  {'WR':>7}")
for sw_s, sw_e in sw_4:
    sub = [t for t in r_is.trades if sw_s <= trade_date(t) <= sw_e]
    if not sub:
        print(f"  {str(sw_s)}..{str(sw_e)}   n=0")
        continue
    sub_pnl = sum(t.dollar_pnl for t in sub)
    sub_wr  = sum(1 for t in sub if t.dollar_pnl > 0) / len(sub)
    print(f"  {str(sw_s)}..{str(sw_e)}  {len(sub):3d}  {sub_pnl:+8.0f}  {sub_wr:6.1%}")

print("\n" + "=" * 70)
print("DONE — review Sections A-G to identify next gate candidates")
print("=" * 70)
