"""OP-22 A/B test: add vix_bull_hard_cap to orchestrator for SAFE.

Context: heartbeat already has bull_hard_cap=18.0 in vix_entry_thresholds.
Orchestrator has vix_bear_hard_cap but no equivalent for bulls.
If OOS losers fire at VIX>=18, orchestrator overcounts trades vs live.

Post-hoc: single-position, no cascade. VIX lookup from orchestrator's own vix_now
(no TZ issue — orchestrator reads VIX from aligned VIX bars).

Test thresholds: 18.0, 19.0, 20.0 (sweep to find the OP-22 sweet spot).
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

BASE = dict(
    use_real_fills=True,
    no_trade_before=dt.time(9, 35), no_trade_window=None,
    midday_trendline_gate=True,
    premium_stop_pct=-0.08, premium_stop_pct_bear=-0.10,
    tp1_premium_pct=0.50, tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50, time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True, block_elite_bull_vix_low=0.0, block_elite_bull_vix_high=25.0,
    entry_bar_body_pct_min=0.20, vix_bear_hard_cap=23.0,
    min_triggers_bear=1, min_triggers_bull=2,
    profit_lock_threshold_pct=0.05, profit_lock_mode="trailing", profit_lock_trail_pct=0.20,
    initial_equity=2000.0, strike_offset=2,
    block_bull_1100_1200=True,
)


def trade_date(t):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None: ts = ts.tz_localize(None)
    return ts.date()


def trade_time(t):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None: ts = ts.tz_localize(None)
    return ts.time()


def pnl(r):
    return sum(t.dollar_pnl for t in r.trades)


print("Running BASELINE IS/OOS ...")
r_base_is  = run_backtest(spy, vix, start_date=IS_S,  end_date=IS_E,  **BASE)
r_base_oos = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **BASE)
base_is_pnl  = pnl(r_base_is)
base_oos_pnl = pnl(r_base_oos)
print(f"Baseline IS: n={len(r_base_is.trades)}, pnl={base_is_pnl:+.0f}")
print(f"Baseline OOS: n={len(r_base_oos.trades)}, pnl={base_oos_pnl:+.0f}")

# Note: we pass vix_bull_hard_cap via params_overrides since no explicit kwarg yet.
# For now, do post-hoc analysis: identify IS/OOS bull trades by VIX from the backtest's
# decision log (or re-run with a gate if parameter exists in orchestrator).
# Since orchestrator already has vix_bear_hard_cap, we need to check if vix_bull_hard_cap exists.

# Check if parameter exists by looking at decisions for BULL entries with vix info
def analyze_bull_vix(trades, label):
    # We don't have VIX directly on TradeFill — use VIX CSV lookup
    import numpy as np
    vix_df_raw = pd.read_csv("backtest/data/vix_5m_2025-01-01_2026-06-16.csv")
    vix_df_raw["ts_utc"] = pd.to_datetime(vix_df_raw["timestamp_et"], utc=True)
    vix_df_raw = vix_df_raw.sort_values("ts_utc").reset_index(drop=True)
    vix_ts = vix_df_raw["ts_utc"].view("int64").to_numpy()

    def get_vix(t):
        entry_ts = pd.Timestamp(t.entry_time_et)
        if entry_ts.tzinfo is None:
            entry_ts = entry_ts.tz_localize("America/New_York").tz_convert("UTC")
        else:
            entry_ts = entry_ts.tz_convert("UTC")
        pos = int(np.searchsorted(vix_ts, entry_ts.value))
        for idx in [pos, pos - 1]:
            if 0 <= idx < len(vix_ts):
                return float(vix_df_raw.iloc[idx]["close"])
        return None

    bulls = [t for t in trades if t.side == "C"]
    print(f"\n{label} bulls (n={len(bulls)}, pnl={sum(t.dollar_pnl for t in bulls):+.0f}):")
    print(f"{'Date':12s} {'Time':8s} {'VIX':>6}  {'triggers':35s}  pnl")
    for t in sorted(bulls, key=lambda x: trade_date(x)):
        v = get_vix(t)
        vs = f"{v:.1f}" if v else "N/A"
        combo = "+".join(sorted(t.triggers_fired))[:35]
        print(f"  {trade_date(t)} {trade_time(t)}  {vs:>6}  {combo:35s}  {t.dollar_pnl:+.0f}")
    return [(t, get_vix(t)) for t in bulls]


print("\n=== IS Bulls with VIX ===")
is_bulls_vix = analyze_bull_vix(r_base_is.trades, "IS")
print("\n=== OOS Bulls with VIX ===")
oos_bulls_vix = analyze_bull_vix(r_base_oos.trades, "OOS")

# For each threshold, compute G1/G2
print("\n\n=== Threshold Sweep ===")
print(f"{'Cap':>8}  {'IS_n_rm':>8}  {'IS_d':>8}  {'OOS_n_rm':>9}  {'OOS_d':>8}  {'WF':>7}  G1  G2  G3")
for cap in [18.0, 19.0, 20.0, 21.0, 22.0]:
    is_blocked  = [(t, v) for t, v in is_bulls_vix  if v is not None and v >= cap]
    oos_blocked = [(t, v) for t, v in oos_bulls_vix if v is not None and v >= cap]
    is_d  = -sum(t.dollar_pnl for t, _ in is_blocked)
    oos_d = -sum(t.dollar_pnl for t, _ in oos_blocked)
    n_is  = len(is_blocked)
    n_oos = len(oos_blocked)
    g1 = is_d >= 0
    g2 = oos_d > 0
    wf = (oos_d / n_oos) / (is_d / n_is) if (n_is > 0 and n_oos > 0 and is_d != 0) else (float("inf") if n_is == 0 else 0.0)
    g3 = wf >= 0.70
    wf_s = f"{wf:.3f}" if wf != float("inf") else "  inf"
    g1s = "P" if g1 else "F"
    g2s = "P" if g2 else "F"
    g3s = "P" if g3 else "F"
    print(f"  VIX>={cap:.0f}  {n_is:8d}  {is_d:+8.0f}  {n_oos:9d}  {oos_d:+8.0f}  {wf_s:>7}  {g1s}   {g2s}   {g3s}")

# Focus on VIX>=18
print(f"\n=== Focus: VIX>= 18 ===")
is_bl_18  = [(t, v) for t, v in is_bulls_vix  if v is not None and v >= 18.0]
oos_bl_18 = [(t, v) for t, v in oos_bulls_vix if v is not None and v >= 18.0]
if is_bl_18:
    print(f"IS blocked ({len(is_bl_18)} trades):")
    for t, v in sorted(is_bl_18, key=lambda x: trade_date(x[0])):
        combo = "+".join(sorted(t.triggers_fired))[:40]
        print(f"  {trade_date(t)} {trade_time(t)} VIX={v:.1f}  {combo:40s}  pnl={t.dollar_pnl:+.0f}  {'WIN' if t.dollar_pnl>0 else 'LOSS'}")
else:
    print("IS: no bulls at VIX>=18")

if oos_bl_18:
    print(f"OOS blocked ({len(oos_bl_18)} trades):")
    for t, v in sorted(oos_bl_18, key=lambda x: trade_date(x[0])):
        combo = "+".join(sorted(t.triggers_fired))[:40]
        print(f"  {trade_date(t)} {trade_time(t)} VIX={v:.1f}  {combo:40s}  pnl={t.dollar_pnl:+.0f}  {'WIN' if t.dollar_pnl>0 else 'LOSS'}")
else:
    print("OOS: no bulls at VIX>=18")

# G4 sub-window for best threshold
is_d_18 = -sum(t.dollar_pnl for t, _ in is_bl_18)
oos_d_18 = -sum(t.dollar_pnl for t, _ in oos_bl_18)
if is_bl_18:
    print(f"\nG4 sub-windows for VIX>=18:")
    sw_fail = 0
    for sw_s, sw_e in SW_BOUNDS:
        sw_blocked = [(t, v) for t, v in is_bl_18 if sw_s <= trade_date(t) <= sw_e]
        sw_d = -sum(t.dollar_pnl for t, _ in sw_blocked)
        sw_p = sw_d >= 0
        if not sw_p: sw_fail += 1
        print(f"  {sw_s}..{sw_e}: n={len(sw_blocked)}, delta={sw_d:+.0f} -> {'PASS' if sw_p else 'FAIL'}")
    g4 = sw_fail <= 1
    print(f"SW hurt: {sw_fail}/3 -> G4 {'PASS' if g4 else 'FAIL'}")

    anchor_bl = [(t, v) for t, v in is_bl_18 if trade_date(t) in ANCHOR_DATES]
    if anchor_bl:
        print(f"G5: ANCHOR BLOCKED! {[(trade_date(t), t.dollar_pnl) for t, _ in anchor_bl]} -> FAIL")
    else:
        print("G5: No anchor blocked -> PASS")
