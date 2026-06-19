"""
Chandelier Baseline Check — quantify production vs backtest config gap.

Production heartbeat uses:
  profit_lock_threshold_pct = 0.05  (arm at +5% entry premium)
  profit_lock_stop_offset_pct = 0.10 (floor at +10% entry premium)
  profit_lock_mode = "trailing"
  profit_lock_trail_pct = 0.20       (trail 20% off HWM)

Current sweep SAFE_BASE / AGG_BASE do NOT set these (default = 0.0 = OFF).

This script runs both baselines (chandelier OFF vs ON) and shows the delta.
If delta is small, existing sweep results are valid for relative comparisons.
If large, future sweeps should include chandelier parameters.
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)

SUBWINDOWS = [
    ("W1_2025H1",  dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2_2025Q3",  dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
    ("W3_2025Q4",  dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("W4_2026H1",  dt.date(2026, 1, 2),  dt.date(2026, 5, 7)),
]

COMMON = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    midday_trendline_gate_start_minutes=690,
    tp1_qty_fraction=0.667,
    tp1_premium_pct=0.50,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
)

SAFE_CHANDELIER_OFF = dict(**COMMON,
    premium_stop_pct_bear=-0.10,
    profit_lock_threshold_pct=0.0,    # OFF
    profit_lock_stop_offset_pct=0.0,  # OFF
    profit_lock_mode="fixed",
    profit_lock_trail_pct=0.0,        # OFF
)

SAFE_CHANDELIER_ON = dict(**COMMON,
    premium_stop_pct_bear=-0.10,
    profit_lock_threshold_pct=0.05,   # ON — arm at +5%
    profit_lock_stop_offset_pct=0.10, # ON — floor at +10%
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.20,       # ON — trail 20% off HWM
)

AGG_COMMON = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    midday_trendline_gate_start_minutes=690,
    premium_stop_pct_bear=-0.07,
    tp1_qty_fraction=0.667,
    tp1_premium_pct=0.75,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
)

AGG_CHANDELIER_OFF = dict(**AGG_COMMON,
    profit_lock_threshold_pct=0.0,
    profit_lock_stop_offset_pct=0.0,
    profit_lock_mode="fixed",
    profit_lock_trail_pct=0.0,
)

AGG_CHANDELIER_ON = dict(**AGG_COMMON,
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.10,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.20,
)


def run(params, start, end, spy_df, vix_df):
    result = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **params)
    trades = result.trades
    pnl = sum(t.dollar_pnl for t in trades)
    n = len(trades)
    return n, pnl


def check_account(name, off_params, on_params, spy_df, vix_df):
    print(f"\n{'='*80}")
    print(f"ACCOUNT: {name}")
    print(f"{'='*80}")

    off_is_n, off_is_pnl = run(off_params, IS_START, IS_END, spy_df, vix_df)
    off_oos_n, off_oos_pnl = run(off_params, OOS_START, OOS_END, spy_df, vix_df)
    on_is_n, on_is_pnl = run(on_params, IS_START, IS_END, spy_df, vix_df)
    on_oos_n, on_oos_pnl = run(on_params, OOS_START, OOS_END, spy_df, vix_df)

    is_delta = on_is_pnl - off_is_pnl
    oos_delta = on_oos_pnl - off_oos_pnl

    print(f"  Config        IS_n  IS_pnl       OOS_n  OOS_pnl")
    print(f"  Chandelier OFF  {off_is_n:4d}  ${off_is_pnl:+10,.0f}  {off_oos_n:4d}  ${off_oos_pnl:+10,.0f}")
    print(f"  Chandelier ON   {on_is_n:4d}  ${on_is_pnl:+10,.0f}  {on_oos_n:4d}  ${on_oos_pnl:+10,.0f}")
    print(f"  Delta (ON-OFF)        ${is_delta:+10,.0f}        ${oos_delta:+10,.0f}")

    if abs(is_delta) < 500 and abs(oos_delta) < 200:
        verdict = "SMALL_DELTA — existing sweep baselines (chandelier OFF) are valid for relative comparisons"
    else:
        verdict = "LARGE_DELTA — sweeps should be rerun with chandelier ON for production-accurate results"
    print(f"\n  VERDICT: {verdict}")

    print(f"\n  Sub-window breakdown (chandelier ON vs OFF):")
    for wname, ws, we in SUBWINDOWS:
        _, off_sw_pnl = run(off_params, ws, we, spy_df, vix_df)
        _, on_sw_pnl = run(on_params, ws, we, spy_df, vix_df)
        sw_delta = on_sw_pnl - off_sw_pnl
        print(f"    {wname}: OFF=${off_sw_pnl:+,.0f}  ON=${on_sw_pnl:+,.0f}  d=${sw_delta:+,.0f}")


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")
    print()
    print("Comparing chandelier OFF (current sweep baselines) vs ON (production config)")
    print("Small IS delta (<$500) + small OOS delta (<$200) = backtest gap is acceptable")

    check_account("SAFE", SAFE_CHANDELIER_OFF, SAFE_CHANDELIER_ON, spy_df, vix_df)
    check_account("AGGRESSIVE", AGG_CHANDELIER_OFF, AGG_CHANDELIER_ON, spy_df, vix_df)


if __name__ == "__main__":
    main()
