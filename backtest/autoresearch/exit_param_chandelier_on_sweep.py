"""
Exit Parameter Sweep - Safe account with chandelier ON baseline.

Motivation (L130): All prior exit param sweeps used chandelier OFF baseline
(IS n=130, OOS n=21 $+5,900). Production Safe uses chandelier ON
(IS n=124, OOS n=21 $+1,770). This sweep validates the Rank-36 and
other exit param conclusions against the production-accurate baseline.

Sweeps:
  1. tp1_premium_pct: [0.30, 0.40, 0.50, 0.60, 0.70, 0.80] vs baseline 0.50
  2. tp1_qty_fraction: [0.30, 0.40, 0.50, 0.60, 0.667, 0.70, 0.80] vs baseline 0.667
  3. runner_target: [1.5, 2.0, 2.5, 3.0, 3.5, 4.0] vs baseline 2.5

Gates: OOS_positive AND WF_norm >= 0.70 AND SW_hurt <= 1

Security note: read-only on production state. Never imports Alpaca tools.
Cost ceiling: $0 (free tier, no OpenRouter calls in this script).
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

# Production Safe baseline WITH chandelier ON (matches production params.json)
SAFE_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    midday_trendline_gate_start_minutes=690,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,        # current production
    tp1_premium_pct=0.50,          # Rank-36 ratified
    runner_target_premium_pct=2.5, # production
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
    # Chandelier ON (production)
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.10,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.20,
)

SWEEPS = [
    {
        "name": "tp1_premium_pct",
        "baseline_key": "tp1_premium_pct",
        "baseline_val": 0.50,
        "candidates": [0.30, 0.40, 0.60, 0.70, 0.80],
    },
    {
        "name": "tp1_qty_fraction",
        "baseline_key": "tp1_qty_fraction",
        "baseline_val": 0.667,
        "candidates": [0.30, 0.40, 0.50, 0.60, 0.70, 0.80],
    },
    {
        "name": "runner_target",
        "baseline_key": "runner_target_premium_pct",
        "baseline_val": 2.5,
        "candidates": [1.5, 2.0, 3.0, 3.5, 4.0],
    },
]


def run(params, start, end, spy_df, vix_df):
    result = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **params)
    trades = result.trades
    pnl = sum(t.dollar_pnl for t in trades)
    n = len(trades)
    return n, pnl


def run_sweep(sweep_cfg, spy_df, vix_df):
    name = sweep_cfg["name"]
    key  = sweep_cfg["baseline_key"]
    bval = sweep_cfg["baseline_val"]

    print(f"\n{'='*80}")
    print(f"SWEEP: {name}")
    print(f"{'='*80}")

    base_is_n,  base_is_pnl  = run(SAFE_BASE, IS_START,  IS_END,  spy_df, vix_df)
    base_oos_n, base_oos_pnl = run(SAFE_BASE, OOS_START, OOS_END, spy_df, vix_df)
    print(f"Baseline ({key}={bval}):  IS n={base_is_n}  pnl=${base_is_pnl:+,.0f}  |  OOS n={base_oos_n}  pnl=${base_oos_pnl:+,.0f}")
    print()

    hdr = f"  {'Value':<8}  {'IS_n':>5}  {'IS_pnl':>10}  {'IS_d':>8}  {'OOS_n':>5}  {'OOS_pnl':>10}  {'OOS_d':>8}  {'WF':>7}  {'SW_h':>4}  VERDICT"
    print(hdr)
    print("-" * len(hdr))

    ratifiable = []

    for val in sweep_cfg["candidates"]:
        cand = {**SAFE_BASE, key: val}
        c_is_n,  c_is_pnl  = run(cand, IS_START,  IS_END,  spy_df, vix_df)
        c_oos_n, c_oos_pnl = run(cand, OOS_START, OOS_END, spy_df, vix_df)

        is_d  = c_is_pnl  - base_is_pnl
        oos_d = c_oos_pnl - base_oos_pnl

        n_is  = base_is_n  if base_is_n  else 1
        n_oos = base_oos_n if base_oos_n else 1
        wf = (oos_d / n_oos) / (is_d / n_is) if is_d != 0 else float("nan")

        sw_results = []
        sw_hurt = 0
        for wname, ws, we in SUBWINDOWS:
            _, base_sw = run(SAFE_BASE, ws, we, spy_df, vix_df)
            _, cand_sw = run(cand,      ws, we, spy_df, vix_df)
            sw_d = cand_sw - base_sw
            tag = "HELP" if sw_d > 50 else ("HURT" if sw_d < -50 else "FLAT")
            if tag == "HURT":
                sw_hurt += 1
            sw_results.append(f"{wname}:{tag}({sw_d:+,.0f})")

        oos_pos = oos_d > 0
        wf_ok   = (wf == wf) and wf >= 0.70
        sw_ok   = sw_hurt <= 1

        if oos_pos and wf_ok and sw_ok:
            verdict = "RATIFIABLE"
            ratifiable.append((val, oos_d, wf))
        elif not oos_pos:
            verdict = "OOS_NEG"
        elif not wf_ok:
            verdict = f"WF_FAIL({wf:.3f})"
        else:
            verdict = f"SW_FAIL(hurt={sw_hurt})"

        wf_str = f"{wf:.3f}" if wf == wf else "  nan"
        print(f"  {val:<8}  {c_is_n:>5}  {c_is_pnl:>+10,.0f}  {is_d:>+8,.0f}  {c_oos_n:>5}  {c_oos_pnl:>+10,.0f}  {oos_d:>+8,.0f}  {wf_str:>7}  {sw_hurt:>4}  {verdict}")
        print(f"         SW: {' | '.join(sw_results)}")

    print()
    if ratifiable:
        best = max(ratifiable, key=lambda x: x[1])
        print(f"  *** RATIFIABLE: {key}={best[0]}  OOS_d={best[1]:+,.0f}  WF={best[2]:.3f} ***")
    else:
        print(f"  No ratifiable candidate found. Baseline ({key}={bval}) remains optimal vs chandelier ON baseline.")


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")
    print()
    print("Exit Parameter Sweep - Safe account, chandelier ON baseline (production)")
    print("Gates: OOS_positive AND WF>=0.70 AND SW_hurt<=1")
    print()

    for sweep_cfg in SWEEPS:
        run_sweep(sweep_cfg, spy_df, vix_df)

    print("\nDONE.")


if __name__ == "__main__":
    main()
