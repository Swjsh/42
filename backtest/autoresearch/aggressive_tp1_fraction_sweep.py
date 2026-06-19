"""
Aggressive TP1 Fraction Sweep.

Safe uses tp1_qty_fraction=0.667 (deployed via L108 fix + Rank-29 status).
The 0.667 fraction was validated for Safe in the L108 dead-knob fix sweep.
For Aggressive (TP1=+75% vs Safe TP1=+50%), the optimal fraction may differ.

Hypothesis: with a higher TP1 bar (+75%), fewer trades hit TP1 before reversing.
If the runner succeeds more often at Aggressive's aggressive TP1=+75% setup,
keeping more contracts as runners (lower fraction) could be better.

Sweep: tp1_qty_fraction in [0.333, 0.50, 0.667, 0.80]
  0.333 = 1/3 TP1, 2/3 runners (very aggressive runner book)
  0.50  = 50/50 split
  0.667 = current production (2/3 TP1, 1/3 runner)
  0.80  = 4/5 TP1, 1/5 runner (conservative, lower variance)

Gate: OOS_positive AND WF_norm >= 0.70 AND SW_hurt <= 1
"""
import datetime as dt
import sys
from pathlib import Path
from statistics import mean

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

PRODUCTION_FRACTION = 0.667

AGG_BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
    premium_stop_pct_bear=-0.10,
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

FRACTIONS = [0.333, 0.50, 0.667, 0.80]


def run_with_frac(frac: float, start: dt.date, end: dt.date, spy_df, vix_df):
    result = run_backtest(
        spy_df,
        vix_df,
        start_date=start,
        end_date=end,
        tp1_qty_fraction=frac,
        **AGG_BASE_KWARGS,
    )
    trades = result.trades
    pnl = sum(t.dollar_pnl for t in trades)
    n = len(trades)
    wins = sum(1 for t in trades if t.dollar_pnl > 0)
    wr = wins / n if n else 0
    return n, pnl, wr


def wf_norm(is_delta, n_is, oos_delta, n_oos):
    if n_is == 0 or n_oos == 0 or is_delta == 0:
        return float("nan")
    return (oos_delta / n_oos) / (is_delta / n_is)


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")

    print(f"\nBaseline (tp1_qty_fraction={PRODUCTION_FRACTION})...")
    base_n_is, base_pnl_is, base_wr_is = run_with_frac(PRODUCTION_FRACTION, IS_START, IS_END, spy_df, vix_df)
    base_n_oos, base_pnl_oos, base_wr_oos = run_with_frac(PRODUCTION_FRACTION, OOS_START, OOS_END, spy_df, vix_df)
    print(f"  IS  n={base_n_is}  pnl={base_pnl_is:+,.0f}  WR={base_wr_is:.1%}")
    print(f"  OOS n={base_n_oos}  pnl={base_pnl_oos:+,.0f}  WR={base_wr_oos:.1%}")

    sw_base = {}
    for wname, wstart, wend in SUBWINDOWS:
        n, pnl, _ = run_with_frac(PRODUCTION_FRACTION, wstart, wend, spy_df, vix_df)
        sw_base[wname] = (n, pnl)

    print(f"\n{'Fraction':>10} {'IS_pnl':>10} {'IS_delta':>10} {'OOS_pnl':>10} {'OOS_delta':>10} "
          f"{'WF':>7} {'SW_hurt':>8} {'VERDICT':>14}")
    print("-" * 90)

    for frac in FRACTIONS:
        if frac == PRODUCTION_FRACTION:
            cn_is, cp_is, cw_is = base_n_is, base_pnl_is, base_wr_is
            cn_oos, cp_oos, cw_oos = base_n_oos, base_pnl_oos, base_wr_oos
        else:
            cn_is, cp_is, cw_is = run_with_frac(frac, IS_START, IS_END, spy_df, vix_df)
            cn_oos, cp_oos, cw_oos = run_with_frac(frac, OOS_START, OOS_END, spy_df, vix_df)

        is_delta = cp_is - base_pnl_is
        oos_delta = cp_oos - base_pnl_oos
        wf = wf_norm(is_delta, cn_is, oos_delta, cn_oos)

        sw_hurt = 0
        sw_parts = []
        for wname, wstart, wend in SUBWINDOWS:
            if frac == PRODUCTION_FRACTION:
                wdelta = 0
                direction = "BASELINE"
            else:
                _, wpnl, _ = run_with_frac(frac, wstart, wend, spy_df, vix_df)
                wdelta = wpnl - sw_base[wname][1]
                direction = "HELP" if wdelta > 50 else "HURT" if wdelta < -50 else "FLAT"
                if direction == "HURT":
                    sw_hurt += 1
            sw_parts.append(f"{wname[:6]}:{direction}({wdelta:+.0f})")

        if frac == PRODUCTION_FRACTION:
            verdict = "BASELINE"
        elif cp_oos > 0 and not (wf != wf) and wf >= 0.70 and sw_hurt <= 1:
            verdict = "RATIFIABLE"
        elif cp_oos > 0 and not (wf != wf) and wf >= 0.70:
            verdict = "WF_PASS_SW_FAIL"
        elif cp_oos > 0:
            verdict = "OOS_POS_WF_FAIL"
        else:
            verdict = "OOS_NEG"

        print(f"  {frac:>8.3f}  {cp_is:>+10,.0f}  {is_delta:>+10,.0f}  {cp_oos:>+10,.0f}  "
              f"{oos_delta:>+10,.0f}  {wf:>7.3f}  {sw_hurt:>8}  {verdict:>14}")
        if frac != PRODUCTION_FRACTION:
            print(f"            SW: {' | '.join(sw_parts)}")


if __name__ == "__main__":
    main()
