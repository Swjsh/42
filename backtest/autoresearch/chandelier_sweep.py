"""
Chandelier Parameter Sweep - Safe + Aggressive baselines.

Motivation: chandelier_baseline_check.py confirmed LARGE_DELTA (L130):
  Safe: chandelier ON vs OFF = IS -$2,896, OOS -$4,131
  Production chandelier (arm=5%, floor=10%, trail=20%) is hurting performance.

Research question: is chandelier OFF optimal, or is there a looser chandelier
setting that beats both production ON and full OFF?

BASELINE for Safe: production chandelier ON (arm=5%, floor=10%, trail=20%)
BASELINE for Agg: production chandelier OFF (no profit_lock params)
Candidates: chandelier OFF (Safe only), arm=0.10/0.15/0.20, trail=0.25/0.30/0.40

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

# --- SAFE production base (chandelier ON = production config) ---
# All other params match production (from automation/state/params.json)
SAFE_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    midday_trendline_gate_start_minutes=690,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    tp1_premium_pct=0.50,
    runner_target_premium_pct=2.5,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
    # Production chandelier ON (L130 fix: include ALL production params)
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.10,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.20,
)

# --- AGGRESSIVE production base (chandelier OFF = production config) ---
# L130/L131 fix: production Aggressive has NO profit_lock params in
# automation/state/aggressive/params.json and NO chandelier code in
# automation/prompts/aggressive/heartbeat.md. Confirmed via grep 2026-06-17.
# AGG candidates test whether adding chandelier ON *helps* Aggressive.
AGG_BASE = dict(
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
    # Chandelier OFF (production): no profit_lock params
    profit_lock_threshold_pct=0.0,
    profit_lock_stop_offset_pct=0.0,
    profit_lock_mode="fixed",
    profit_lock_trail_pct=0.0,
)

# --- Candidate configurations to sweep ---
# Format: (label, overrides_dict)
# Each override dict is merged onto the account base to produce the candidate config.
SAFE_CANDIDATES = [
    # Primary question: is chandelier OFF better than production ON?
    ("OFF",           dict(profit_lock_threshold_pct=0.0, profit_lock_stop_offset_pct=0.0,
                           profit_lock_mode="fixed", profit_lock_trail_pct=0.0)),
    # Looser arm: arm later, miss fewer genuine winners
    ("arm=0.10",      dict(profit_lock_threshold_pct=0.10, profit_lock_stop_offset_pct=0.10,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.20)),
    ("arm=0.15",      dict(profit_lock_threshold_pct=0.15, profit_lock_stop_offset_pct=0.15,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.20)),
    ("arm=0.20",      dict(profit_lock_threshold_pct=0.20, profit_lock_stop_offset_pct=0.20,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.20)),
    # Looser trail: trail further off HWM, fewer early chandelier exits
    ("trail=0.25",    dict(profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.25)),
    ("trail=0.30",    dict(profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.30)),
    ("trail=0.40",    dict(profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.40)),
    # Looser arm + looser trail combo
    ("arm=0.10,t=30", dict(profit_lock_threshold_pct=0.10, profit_lock_stop_offset_pct=0.10,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.30)),
    ("arm=0.15,t=40", dict(profit_lock_threshold_pct=0.15, profit_lock_stop_offset_pct=0.15,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.40)),
]

AGG_CANDIDATES = [
    ("OFF",           dict(profit_lock_threshold_pct=0.0, profit_lock_stop_offset_pct=0.0,
                           profit_lock_mode="fixed", profit_lock_trail_pct=0.0)),
    ("arm=0.10",      dict(profit_lock_threshold_pct=0.10, profit_lock_stop_offset_pct=0.10,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.20)),
    ("arm=0.15",      dict(profit_lock_threshold_pct=0.15, profit_lock_stop_offset_pct=0.15,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.20)),
    ("arm=0.20",      dict(profit_lock_threshold_pct=0.20, profit_lock_stop_offset_pct=0.20,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.20)),
    ("trail=0.25",    dict(profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.25)),
    ("trail=0.30",    dict(profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.30)),
    ("trail=0.40",    dict(profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.40)),
    ("arm=0.10,t=30", dict(profit_lock_threshold_pct=0.10, profit_lock_stop_offset_pct=0.10,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.30)),
    ("arm=0.15,t=40", dict(profit_lock_threshold_pct=0.15, profit_lock_stop_offset_pct=0.15,
                           profit_lock_mode="trailing", profit_lock_trail_pct=0.40)),
]


def run(params, start, end, spy_df, vix_df):
    result = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **params)
    trades = result.trades
    pnl = sum(t.dollar_pnl for t in trades)
    n = len(trades)
    return n, pnl


def sweep_account(name, base, candidates, spy_df, vix_df):
    print(f"\n{'='*80}")
    print(f"ACCOUNT: {name}")
    print(f"{'='*80}")

    base_is_n, base_is_pnl  = run(base, IS_START, IS_END, spy_df, vix_df)
    base_oos_n, base_oos_pnl = run(base, OOS_START, OOS_END, spy_df, vix_df)
    baseline_desc = "chandelier ON, prod settings" if name == "SAFE" else "chandelier OFF, prod settings"
    print(f"Baseline ({baseline_desc}):  IS n={base_is_n}  pnl=${base_is_pnl:+,.0f}  |  OOS n={base_oos_n}  pnl=${base_oos_pnl:+,.0f}")
    print()

    hdr = f"  {'Label':<15}  {'IS_n':>5}  {'IS_pnl':>10}  {'IS_d':>8}  {'OOS_n':>5}  {'OOS_pnl':>10}  {'OOS_d':>8}  {'WF':>7}  {'SW_h':>4}  VERDICT"
    print(hdr)
    print("-" * len(hdr))

    ratifiable = []

    for label, overrides in candidates:
        cand = {**base, **overrides}
        c_is_n, c_is_pnl   = run(cand, IS_START, IS_END, spy_df, vix_df)
        c_oos_n, c_oos_pnl = run(cand, OOS_START, OOS_END, spy_df, vix_df)

        is_d  = c_is_pnl  - base_is_pnl
        oos_d = c_oos_pnl - base_oos_pnl

        n_is  = base_is_n  if base_is_n  else 1
        n_oos = base_oos_n if base_oos_n else 1
        wf = (oos_d / n_oos) / (is_d / n_is) if is_d != 0 else float("nan")

        sw_results = []
        sw_hurt = 0
        for wname, ws, we in SUBWINDOWS:
            _, base_sw = run(base, ws, we, spy_df, vix_df)
            _, cand_sw = run(cand, ws, we, spy_df, vix_df)
            sw_d = cand_sw - base_sw
            tag = "HELP" if sw_d > 50 else ("HURT" if sw_d < -50 else "FLAT")
            if tag == "HURT":
                sw_hurt += 1
            sw_results.append(f"{wname}:{tag}({sw_d:+,.0f})")

        oos_pos = oos_d > 0
        wf_ok   = (not (wf != wf)) and wf >= 0.70  # not nan and >= 0.70
        sw_ok   = sw_hurt <= 1

        if oos_pos and wf_ok and sw_ok:
            verdict = "RATIFIABLE"
            ratifiable.append((label, oos_d, wf))
        elif not oos_pos:
            verdict = "OOS_NEG"
        elif oos_pos and not wf_ok:
            verdict = f"WF_FAIL({wf:.3f})"
        else:
            verdict = f"SW_FAIL(hurt={sw_hurt})"

        wf_str = f"{wf:.3f}" if wf == wf else "  nan"
        print(f"  {label:<15}  {c_is_n:>5}  {c_is_pnl:>+10,.0f}  {is_d:>+8,.0f}  {c_oos_n:>5}  {c_oos_pnl:>+10,.0f}  {oos_d:>+8,.0f}  {wf_str:>7}  {sw_hurt:>4}  {verdict}")
        print(f"         SW: {' | '.join(sw_results)}")

    print()
    if ratifiable:
        for r in ratifiable:
            print(f"  *** RATIFIABLE: {r[0]}  OOS_d={r[1]:+,.0f}  WF={r[2]:.3f} ***")
    else:
        print("  No ratifiable candidate found. Baseline (chandelier ON production) remains optimal.")


def main():
    print("Loading data...")
    spy_df = pd.read_csv(MASTER_SPY)
    vix_df = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy_df)} rows  VIX {len(vix_df)} rows")
    print()
    print("Chandelier parameter sweep - baseline = production chandelier ON")
    print("Candidates: OFF, looser arm, looser trail")
    print("Gate: OOS_positive AND WF_norm >= 0.70 AND SW_hurt <= 1")
    print()

    sweep_account("SAFE",       SAFE_BASE, SAFE_CANDIDATES, spy_df, vix_df)
    sweep_account("AGGRESSIVE", AGG_BASE,  AGG_CANDIDATES,  spy_df, vix_df)

    print("\nDONE.")


if __name__ == "__main__":
    main()
