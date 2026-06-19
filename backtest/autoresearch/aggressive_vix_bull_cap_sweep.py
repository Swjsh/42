"""
Aggressive VIX Bull Hard Cap Sweep.

Rank-35 lowered SAFE vix_bull_max from 22→18 (implemented).
SAFE production: vix_entry_thresholds.bull_hard_cap=18.
Aggressive production: vix_entry_thresholds.bull_hard_cap=30.

The Rank-35 rationale: VIX 18-22 BULL entries are net losers on Safe.
Does this apply to Aggressive too?

Note: Aggressive has much broader bull cap (30 vs 18/22).
VIX 18-30 bull entries in Aggressive may behave differently because:
(a) Aggressive uses ITM-2 strikes → higher delta coverage
(b) Aggressive has 50% risk cap → more contracts 
(c) Aggressive's ELITE bull block (VIX 15-17.5) is already in place

Sweep: vix_bull_max in [18.0, 20.0, 22.0, 25.0, 30.0]
Baseline: current production (vix_bull_max=30.0 for Aggressive)
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

PROD_CAP = 30.0

AGG_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    tp1_premium_pct=0.75,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={
        "vix_bear_threshold": 15.0,
    },
)

CAPS = [18.0, 20.0, 22.0, 25.0, 30.0]


def run(cap, start, end, spy_df, vix_df):
    p = dict(**AGG_BASE)
    p["params_overrides"] = dict(**AGG_BASE["params_overrides"], vix_bull_max=cap)
    result = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **p)
    trades = result.trades
    pnl = sum(t.dollar_pnl for t in trades)
    n = len(trades)
    wr = sum(1 for t in trades if t.dollar_pnl > 0) / n if n else 0
    return n, pnl, wr


def wf(is_d, n_is, oos_d, n_oos):
    if not (n_is and n_oos and is_d != 0):
        return float("nan")
    return (oos_d / n_oos) / (is_d / n_is)


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")

    print(f"\nBaseline (vix_bull_max={PROD_CAP})...")
    base_is = run(PROD_CAP, IS_START, IS_END, spy_df, vix_df)
    base_oos = run(PROD_CAP, OOS_START, OOS_END, spy_df, vix_df)
    print(f"  IS  n={base_is[0]}  pnl={base_is[1]:+,.0f}  WR={base_is[2]:.1%}")
    print(f"  OOS n={base_oos[0]}  pnl={base_oos[1]:+,.0f}  WR={base_oos[2]:.1%}")

    sw_base = {w: run(PROD_CAP, s, e, spy_df, vix_df) for w, s, e in SUBWINDOWS}

    print(f"\n{'Cap':>6} {'IS_n':>5} {'IS_pnl':>10} {'IS_d':>8} {'OOS_n':>6} {'OOS_pnl':>10} {'OOS_d':>8} {'WF':>7} {'SW_hurt':>8} {'VERDICT':>12}")
    print("-" * 88)

    for cap in CAPS:
        ci = run(cap, IS_START, IS_END, spy_df, vix_df)
        co = run(cap, OOS_START, OOS_END, spy_df, vix_df)
        is_d = ci[1] - base_is[1]
        oos_d = co[1] - base_oos[1]
        w = wf(is_d, ci[0], oos_d, co[0])

        sw_hurt = 0
        for wname, ws, we in SUBWINDOWS:
            wr = run(cap, ws, we, spy_df, vix_df)
            wd = wr[1] - sw_base[wname][1]
            if wd < -50:
                sw_hurt += 1

        if cap == PROD_CAP:
            v = "BASELINE"
        elif co[1] > 0 and not (w != w) and w >= 0.70 and sw_hurt <= 1:
            v = "RATIFIABLE"
        elif co[1] > 0 and not (w != w) and w >= 0.70:
            v = "WF_PASS_SW_FAIL"
        elif co[1] > 0:
            v = "OOS_POS_WF_FAIL"
        else:
            v = "OOS_NEG"

        print(f"  {cap:>4.0f}  {ci[0]:>5}  {ci[1]:>+10,.0f}  {is_d:>+8,.0f}  "
              f"{co[0]:>6}  {co[1]:>+10,.0f}  {oos_d:>+8,.0f}  {w:>7.3f}  {sw_hurt:>8}  {v:>12}")


if __name__ == "__main__":
    main()
