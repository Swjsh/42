"""
Aggressive Account Premium Stop Sweep.

Aggressive production: premium_stop_pct_bear=-0.10.
Safe also uses -0.10 (Rank-31 deployed).

Kitchen cook proposed a sweep to validate this.
Sweep: premium_stop_pct_bear in [-0.06, -0.07, -0.08, -0.09, -0.10, -0.12, -0.15]

Key context:
- L51/L55: premium stops misfire on first-strike entries in VIX spike environments
- Aggressive uses ITM-2 strikes (delta ~0.72) → less premium volatility per SPY-point
- -0.10 confirmed for Safe (Rank-31); Aggressive may be different

Gate: OOS_positive AND WF_norm >= 0.70 AND SW_hurt <= 1
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

PROD_STOP = -0.10

AGG_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
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
        "vix_bull_max": 30.0,
    },
)

STOPS = [-0.06, -0.07, -0.08, -0.09, -0.10, -0.12, -0.15]


def run(stop, start, end, spy_df, vix_df):
    result = run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        premium_stop_pct_bear=stop,
        **AGG_BASE,
    )
    trades = result.trades
    pnl = sum(t.dollar_pnl for t in trades)
    n = len(trades)
    wr = sum(1 for t in trades if t.dollar_pnl > 0) / n if n else 0
    return n, pnl, wr


def wf_norm(is_d, n_is, oos_d, n_oos):
    if not (n_is and n_oos and is_d != 0):
        return float("nan")
    return (oos_d / n_oos) / (is_d / n_is)


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")

    print(f"\nBaseline (stop={PROD_STOP})...")
    base_is = run(PROD_STOP, IS_START, IS_END, spy_df, vix_df)
    base_oos = run(PROD_STOP, OOS_START, OOS_END, spy_df, vix_df)
    print(f"  IS  n={base_is[0]}  pnl={base_is[1]:+,.0f}  WR={base_is[2]:.1%}")
    print(f"  OOS n={base_oos[0]}  pnl={base_oos[1]:+,.0f}  WR={base_oos[2]:.1%}")

    sw_base = {w: run(PROD_STOP, s, e, spy_df, vix_df) for w, s, e in SUBWINDOWS}

    print(f"\n{'Stop':>7} {'IS_n':>5} {'IS_pnl':>10} {'IS_d':>8} {'OOS_n':>6} {'OOS_pnl':>10} {'OOS_d':>8} {'WF':>7} {'SW_hurt':>8} {'VERDICT':>14}")
    print("-" * 95)

    for stop in STOPS:
        ci = run(stop, IS_START, IS_END, spy_df, vix_df)
        co = run(stop, OOS_START, OOS_END, spy_df, vix_df)
        is_d = ci[1] - base_is[1]
        oos_d = co[1] - base_oos[1]
        w = wf_norm(is_d, ci[0], oos_d, co[0])

        sw_hurt = 0
        sw_details = []
        for wname, ws, we in SUBWINDOWS:
            wr = run(stop, ws, we, spy_df, vix_df)
            wd = wr[1] - sw_base[wname][1]
            direction = "HELP" if wd > 50 else "HURT" if wd < -50 else "FLAT"
            if direction == "HURT":
                sw_hurt += 1
            sw_details.append(f"{wname[:6]}:{direction}({wd:+.0f})")

        if stop == PROD_STOP:
            v = "BASELINE"
        elif co[1] > 0 and not (w != w) and w >= 0.70 and sw_hurt <= 1:
            v = "RATIFIABLE"
        elif co[1] > 0 and not (w != w) and w >= 0.70:
            v = "WF_PASS_SW_FAIL"
        elif co[1] > 0:
            v = "OOS_POS_WF_FAIL"
        else:
            v = "OOS_NEG"

        print(f"  {stop:>5.2f}  {ci[0]:>5}  {ci[1]:>+10,.0f}  {is_d:>+8,.0f}  "
              f"{co[0]:>6}  {co[1]:>+10,.0f}  {oos_d:>+8,.0f}  {w:>7.3f}  {sw_hurt:>8}  {v:>14}")
        if stop != PROD_STOP:
            print(f"          SW: {' | '.join(sw_details)}")


if __name__ == "__main__":
    main()
