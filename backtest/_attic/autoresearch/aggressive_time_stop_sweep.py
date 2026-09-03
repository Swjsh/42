"""
Aggressive Account Time Stop Sweep.

L110 finding for SAFE account: time_stop_minutes_before_close=20 (15:40 ET) is optimal
(WF=0.86, all 4 sub-windows HELP). Mechanism: 0DTE theta crush in final 15 minutes.

This sweep validates the same finding for Aggressive account (ITM-2 strikes, stop=-0.07).
Aggressive baseline: IS n=270 pnl=+$19,566 OOS n=28 pnl=+$2,590 (post-stop-ratification).

Sweep: time_stop_minutes_before_close in [10, 15, 20, 25, 30]
 - 10 min = exit at 15:50 ET (very late, max theta exposure)
 - 20 min = exit at 15:40 ET (current production)
 - 30 min = exit at 15:30 ET (earlier, less theta risk)
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

PROD_STOP_MIN = 20

AGG_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
    tp1_qty_fraction=0.667,
    tp1_premium_pct=0.75,
    runner_target_premium_pct=5.0,
    premium_stop_pct_bear=-0.07,   # newly ratified
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={
        "vix_bull_max": 30.0,
        "vix_bear_threshold": 15.0,
        "strike_offset_itm": 2,
    },
)


def run(time_stop: int, start: dt.date, end: dt.date, spy_df, vix_df):
    result = run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        time_stop_minutes_before_close=time_stop,
        **AGG_BASE,
    )
    trades = result.trades
    pnl = sum(t.dollar_pnl for t in trades)
    n = len(trades)
    return n, pnl


def wf_norm(is_d, n_is, oos_d, n_oos):
    if not (n_is and n_oos and is_d != 0):
        return float("nan")
    return (oos_d / n_oos) / (is_d / n_is)


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")

    print(f"\nBaseline (time_stop={PROD_STOP_MIN}min)...")
    base_is_n, base_is_pnl = run(PROD_STOP_MIN, IS_START, IS_END, spy_df, vix_df)
    base_oos_n, base_oos_pnl = run(PROD_STOP_MIN, OOS_START, OOS_END, spy_df, vix_df)
    print(f"  IS  n={base_is_n}  pnl={base_is_pnl:+,.0f}")
    print(f"  OOS n={base_oos_n}  pnl={base_oos_pnl:+,.0f}")

    SWEEPS = [10, 15, 20, 25, 30]
    print(f"\n{'StpMin':>6}  {'IS_n':>5}  {'IS_pnl':>10}  {'IS_d':>8}  {'OOS_n':>5}  {'OOS_pnl':>10}  {'OOS_d':>8}  {'WF':>8}  {'SW_hurt':>8}  {'VERDICT'}")
    print("-" * 115)

    for tmin in SWEEPS:
        if tmin == PROD_STOP_MIN:
            is_d = 0
            oos_d = 0
            wf = float("nan")
            sw_hurt = 0
            verdict = "BASELINE"
            print(f"  {tmin:>4}  {base_is_n:>5}  {base_is_pnl:>+10,.0f}  {is_d:>+8,.0f}  {base_oos_n:>5}  {base_oos_pnl:>+10,.0f}  {oos_d:>+8,.0f}  {'nan':>8}  {sw_hurt:>8}  {verdict}")
            continue

        g_is_n, g_is_pnl = run(tmin, IS_START, IS_END, spy_df, vix_df)
        g_oos_n, g_oos_pnl = run(tmin, OOS_START, OOS_END, spy_df, vix_df)
        is_d = g_is_pnl - base_is_pnl
        oos_d = g_oos_pnl - base_oos_pnl
        wf = wf_norm(is_d, g_is_n, oos_d, g_oos_n)

        sw_hurt = 0
        sw_lines = []
        for wname, ws, we in SUBWINDOWS:
            base_sw = run(PROD_STOP_MIN, ws, we, spy_df, vix_df)
            gate_sw = run(tmin, ws, we, spy_df, vix_df)
            sw_d = gate_sw[1] - base_sw[1]
            direction = "HELP" if sw_d > 50 else "HURT" if sw_d < -50 else "FLAT"
            if direction == "HURT":
                sw_hurt += 1
            sw_lines.append(f"{wname}:{direction}({sw_d:+,.0f})")

        if oos_d > 0 and (wf == wf) and wf >= 0.70 and sw_hurt <= 1:
            verdict = "RATIFIABLE"
        elif oos_d > 0 and (wf == wf) and wf >= 0.70 and sw_hurt > 1:
            verdict = "WF_PASS_SW_FAIL"
        elif oos_d > 0:
            verdict = "OOS_POS_WF_FAIL"
        else:
            verdict = "OOS_NEG"

        wf_str = f"{wf:.3f}" if wf == wf else "nan"
        print(f"  {tmin:>4}  {g_is_n:>5}  {g_is_pnl:>+10,.0f}  {is_d:>+8,.0f}  {g_oos_n:>5}  {g_oos_pnl:>+10,.0f}  {oos_d:>+8,.0f}  {wf_str:>8}  {sw_hurt:>8}  {verdict}")
        print(f"          SW: {' | '.join(sw_lines)}")


if __name__ == "__main__":
    main()
