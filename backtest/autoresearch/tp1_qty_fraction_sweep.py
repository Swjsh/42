"""
TP1 Qty Fraction Sweep -- Safe + Aggressive baselines.

tp1_qty_fraction determines how many contracts are sold at TP1 (first profit target).
This parameter was a dead knob before L108 fix. This is the FIRST sweep with the working
simulator. Both accounts use 0.667 in production.

Research question: is 0.667 optimal, or should we sell more (lock gains) or less (run more)?

Sweep: [0.30, 0.40, 0.50, 0.60, 0.667, 0.70, 0.80]
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

FRACTIONS = [0.30, 0.40, 0.50, 0.60, 0.667, 0.70, 0.80]

# Current production Safe baseline
SAFE_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    midday_trendline_gate_start_minutes=690,
    premium_stop_pct_bear=-0.10,
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

# Current production Aggressive baseline
AGG_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    midday_trendline_gate_start_minutes=690,
    premium_stop_pct_bear=-0.07,
    tp1_premium_pct=0.75,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
)


def run(base, frac, start, end, spy_df, vix_df):
    result = run_backtest(
        spy_df, vix_df,
        start_date=start, end_date=end,
        tp1_qty_fraction=frac,
        **base,
    )
    trades = result.trades
    pnl = sum(t.dollar_pnl for t in trades)
    n = len(trades)
    return n, pnl


def wf_norm(is_d, n_is, oos_d, n_oos):
    if not (n_is and n_oos and is_d != 0):
        return float("nan")
    return (oos_d / n_oos) / (is_d / n_is)


def sweep_account(name, base, spy_df, vix_df):
    print(f"\n{'='*80}")
    print(f"ACCOUNT: {name}")
    print(f"{'='*80}")

    # Baseline (0.667)
    base_is_n, base_is_pnl = run(base, 0.667, IS_START, IS_END, spy_df, vix_df)
    base_oos_n, base_oos_pnl = run(base, 0.667, OOS_START, OOS_END, spy_df, vix_df)
    print(f"Baseline (frac=0.667):  IS n={base_is_n}  pnl=${base_is_pnl:+,.0f}  |  OOS n={base_oos_n}  pnl=${base_oos_pnl:+,.0f}")
    print()
    print(f"{'Frac':>7}  {'IS_n':>6}  {'IS_pnl':>10}  {'IS_d':>8}  {'OOS_n':>6}  {'OOS_pnl':>10}  {'OOS_d':>8}  {'WF':>8}  {'SW_hurt':>7}  VERDICT")
    print("-" * 110)

    best = None
    best_oos_d = -999999

    for frac in FRACTIONS:
        is_n, is_pnl = run(base, frac, IS_START, IS_END, spy_df, vix_df)
        oos_n, oos_pnl = run(base, frac, OOS_START, OOS_END, spy_df, vix_df)

        is_d = is_pnl - base_is_pnl
        oos_d = oos_pnl - base_oos_pnl
        wf = wf_norm(is_d, is_n, oos_d, oos_n)

        sw_hurt = 0
        sw_parts = []
        for wname, ws, we in SUBWINDOWS:
            base_sw_n, base_sw_pnl = run(base, 0.667, ws, we, spy_df, vix_df)
            cand_sw_n, cand_sw_pnl = run(base, frac, ws, we, spy_df, vix_df)
            sw_d = cand_sw_pnl - base_sw_pnl
            direction = "HELP" if sw_d > 50 else "HURT" if sw_d < -50 else "FLAT"
            if direction == "HURT":
                sw_hurt += 1
            sw_parts.append(f"{wname}:{direction}({sw_d:+,.0f})")

        is_flag = " " if abs(frac - 0.667) < 0.001 else ""

        oos_pos = oos_d > 0
        wf_pass = (wf == wf) and wf >= 0.70
        sw_pass = sw_hurt <= 1

        if abs(frac - 0.667) < 0.001:
            verdict = "BASELINE"
        elif oos_pos and wf_pass and sw_pass:
            verdict = "RATIFIABLE"
            if oos_d > best_oos_d:
                best = frac
                best_oos_d = oos_d
        elif not oos_pos:
            verdict = "OOS_NEG"
        elif not wf_pass:
            wf_str = f"{wf:.3f}" if wf == wf else "nan"
            verdict = f"WF_FAIL({wf_str})"
        else:
            verdict = f"SW_FAIL({sw_hurt}/4)"

        wf_str = f"{wf:.3f}" if wf == wf else "  nan"
        print(f"{frac:>7.3f}  {is_n:>6}  {is_pnl:>+10,.0f}  {is_d:>+8,.0f}  {oos_n:>6}  {oos_pnl:>+10,.0f}  {oos_d:>+8,.0f}  {wf_str:>8}  {sw_hurt:>7}  {verdict}")
        print(f"         SW: {' | '.join(sw_parts)}")

    if best is not None:
        print(f"\n  *** BEST RATIFIABLE: frac={best:.3f} (OOS delta={best_oos_d:+,.0f}) ***")
    else:
        print(f"\n  No ratifiable candidate found. Baseline (0.667) remains optimal.")


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")

    sweep_account("SAFE", SAFE_BASE, spy_df, vix_df)
    sweep_account("AGGRESSIVE", AGG_BASE, spy_df, vix_df)


if __name__ == "__main__":
    main()
