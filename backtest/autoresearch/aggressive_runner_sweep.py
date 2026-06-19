"""
Aggressive Account Runner Target Sweep.

Context: production Aggressive params.json has runner_max_premium_pct=5.0 (5x entry premium).
On a 0DTE OTM/ITM option, a 5x runner target is very rarely reachable in a single session.
This means Aggressive runners almost always close at the time_stop (15:40 ET, Rank-31 deployed),
not at the runner target.

Compare: Safe uses runner_max_premium_pct=2.5 (Rank-31) with confirmed WF=1.08.

If lowering the runner target to 2.5x also improves Aggressive, we should deploy it.

L109 fix context: simulate_trade_real() previously hardcoded RUNNER_MAX_PREMIUM_PCT=3.0
regardless of params — now the knob is live and correctly wired.

Sweep: runner_max_premium_pct in [1.5, 2.0, 2.5, 3.0, 3.5, 5.0]
Gate: OOS_positive AND WF_norm >= 0.70 AND SW_hurt <= 1

Aggressive CORRECT baseline params (from context-10 analysis):
- vix_bear_threshold=15.0 (vix_entry_thresholds.bear_min_exclusive=15.0)
- vix_bull_max=30.0 (vix_entry_thresholds.bull_hard_cap=30.0)
- tp1_premium_pct=0.75, tp1_qty_fraction=0.667
- time_stop=20min (Rank-31 deployed)
- premium_stop_pct_bear=-0.10 (Rank-31 deployed)
- block_level_rejection=True, block_elite_bull=True (15-17.5)
- midday_trendline_gate=False (tested and rejected for Aggressive, context-10)
- per_trade_risk_cap_pct=0.50
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

# Sub-windows for stability check
SUBWINDOWS = [
    ("W1_2025H1",  dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2_2025Q3",  dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
    ("W3_2025Q4",  dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
    ("W4_2026H1",  dt.date(2026, 1, 2),  dt.date(2026, 5, 7)),
]

PRODUCTION_RUNNER = 5.0  # current Aggressive production value

AGG_BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    tp1_premium_pct=0.75,
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

RUNNER_VALUES = [1.5, 2.0, 2.5, 3.0, 3.5, 5.0]


def run_with_runner(runner: float, start: dt.date, end: dt.date, spy_df, vix_df):
    result = run_backtest(
        spy_df,
        vix_df,
        start_date=start,
        end_date=end,
        runner_target_premium_pct=runner,
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

    # Baseline (production runner=5.0)
    print(f"\nEstablishing BASELINE (runner={PRODUCTION_RUNNER}x)...")
    base_n_is, base_pnl_is, base_wr_is = run_with_runner(PRODUCTION_RUNNER, IS_START, IS_END, spy_df, vix_df)
    base_n_oos, base_pnl_oos, base_wr_oos = run_with_runner(PRODUCTION_RUNNER, OOS_START, OOS_END, spy_df, vix_df)
    print(f"  IS  n={base_n_is}  pnl={base_pnl_is:+,.0f}  WR={base_wr_is:.1%}")
    print(f"  OOS n={base_n_oos}  pnl={base_pnl_oos:+,.0f}  WR={base_wr_oos:.1%}")

    # Sub-window baseline
    sw_base = {}
    for wname, wstart, wend in SUBWINDOWS:
        n, pnl, _ = run_with_runner(PRODUCTION_RUNNER, wstart, wend, spy_df, vix_df)
        sw_base[wname] = (n, pnl)

    print(f"\n{'Runner':>8} {'IS_n':>6} {'IS_pnl':>10} {'IS_del':>10} {'OOS_n':>6} {'OOS_pnl':>10} {'OOS_del':>10} {'WF':>7} {'SW_hurt':>8} {'VERDICT':>12}")
    print("-" * 100)

    results = []
    for runner in RUNNER_VALUES:
        if runner == PRODUCTION_RUNNER:
            cand_n_is, cand_pnl_is, cand_wr_is = base_n_is, base_pnl_is, base_wr_is
            cand_n_oos, cand_pnl_oos, cand_wr_oos = base_n_oos, base_pnl_oos, base_wr_oos
        else:
            cand_n_is, cand_pnl_is, cand_wr_is = run_with_runner(runner, IS_START, IS_END, spy_df, vix_df)
            cand_n_oos, cand_pnl_oos, cand_wr_oos = run_with_runner(runner, OOS_START, OOS_END, spy_df, vix_df)

        is_delta = cand_pnl_is - base_pnl_is
        oos_delta = cand_pnl_oos - base_pnl_oos

        # n should be same (runner doesn't affect entries)
        wf = wf_norm(is_delta, cand_n_is, oos_delta, cand_n_oos)

        # Sub-window stability
        sw_hurt = 0
        sw_details = []
        for wname, wstart, wend in SUBWINDOWS:
            wn, wpnl, _ = run_with_runner(runner, wstart, wend, spy_df, vix_df)
            wdelta = wpnl - sw_base[wname][1]
            direction = "HELP" if wdelta > 50 else "HURT" if wdelta < -50 else "FLAT"
            if direction == "HURT":
                sw_hurt += 1
            sw_details.append(f"{wname}:{direction}({wdelta:+.0f})")

        oos_pos = cand_pnl_oos > 0
        wf_pass = not (wf != wf) and wf >= 0.70
        sw_pass = sw_hurt <= 1

        if runner == PRODUCTION_RUNNER:
            verdict = "BASELINE"
        elif oos_pos and wf_pass and sw_pass:
            verdict = "RATIFIABLE"
        elif oos_pos and wf_pass:
            verdict = "WF_PASS_SW_FAIL"
        elif oos_pos:
            verdict = "OOS_POS_WF_FAIL"
        else:
            verdict = "OOS_NEG"

        results.append((runner, cand_n_is, cand_pnl_is, is_delta, cand_n_oos, cand_pnl_oos, oos_delta, wf, sw_hurt, verdict))
        print(f"  {runner:>6.1f}x  {cand_n_is:>6}  {cand_pnl_is:>+10,.0f}  {is_delta:>+10,.0f}  "
              f"{cand_n_oos:>6}  {cand_pnl_oos:>+10,.0f}  {oos_delta:>+10,.0f}  "
              f"{wf:>7.3f}  {sw_hurt:>8}  {verdict:>12}")
        if runner != PRODUCTION_RUNNER:
            print(f"         Sub-windows: {' | '.join(sw_details)}")

    # Best candidate
    candidates = [(r, wf, oos_d) for r, _, _, _, _, _, oos_d, wf, sw_h, v in results
                  if v == "RATIFIABLE"]
    if candidates:
        best_r, best_wf, best_oos = max(candidates, key=lambda x: x[2])
        print(f"\nBEST CANDIDATE: runner={best_r}x  WF={best_wf:.3f}  OOS_delta={best_oos:+.0f}")
        print("ACTION: deploy to aggressive/params.json runner_max_premium_pct")
    else:
        print("\nNO RATIFIABLE CANDIDATES. Production runner=5.0x confirmed or no better option.")


if __name__ == "__main__":
    main()
