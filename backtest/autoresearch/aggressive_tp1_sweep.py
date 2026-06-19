"""
Aggressive TP1 target sweep: is +75% (current) optimal?

From OOS analysis:
  - TP1_THEN_RUNNER_* = 100% winners (11 trades), avg +$246
  - EXIT_ALL_PREMIUM_STOP = 100% losers (12 trades), avg -$219
  - Runner exits are ALL via ribbon flip / time, NEVER hit 5x target
    → runner_target is effectively irrelevant; TP1 target is the lever

Q: Would +40%, +50%, +60%, +75%(current), +100% improve OOS?

Post-Rank35 Aggressive baseline (correct production params):
  IS n=261 pnl=+9959 | OOS n=28 pnl=+3272
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

IS_S  = dt.date(2025, 1, 2)
IS_E  = dt.date(2026, 5, 7)
OOS_S = dt.date(2026, 5, 8)
OOS_E = dt.date(2026, 6, 16)

SUB_WINDOWS = [
    ("W1_2025H1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2_2025H2", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3_Q12026", dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
    ("W4_Apr26",  dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]

AGG_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=5.0,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.50,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bear_threshold": 15.0, "vix_bull_max": 30.0},
)

# TP1 targets to sweep (as decimal fractions, i.e., 0.75 = +75%)
# Maps to params_overrides["tp1_premium_pct"] if wired, else use tp1_pct arg directly
# In the orchestrator, tp1_pct is the tp1_premium_pct arg.
TP1_CANDIDATES = [0.30, 0.40, 0.50, 0.60, 0.75, 1.00, 1.25]


def run_with_tp1(spy, vix, tp1_pct, start, end, **extra):
    """Run backtest with given TP1 target. tp1_pct is the fractional increase (0.75 = +75%)."""
    kwargs = dict(AGG_BASE)
    kwargs.update(extra)
    # tp1_premium_pct is a direct kwarg on run_backtest
    kwargs["tp1_premium_pct"] = tp1_pct
    return run_backtest(spy, vix, start_date=start, end_date=end, **kwargs)


def wf_norm(oos_d, n_oos, is_d, n_is):
    if is_d == 0 or n_is == 0 or n_oos == 0:
        return None
    return (oos_d / n_oos) / (is_d / n_is)


def run():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    # Baseline (tp1=0.75, current production)
    base_is  = run_with_tp1(spy, vix, 0.75, IS_S,  IS_E)
    base_oos = run_with_tp1(spy, vix, 0.75, OOS_S, OOS_E)
    base_is_pnl  = sum(t.dollar_pnl for t in base_is.trades)
    base_oos_pnl = sum(t.dollar_pnl for t in base_oos.trades)
    n_is  = len(base_is.trades)
    n_oos = len(base_oos.trades)
    print(f"\nBASELINE (TP1=+75%): IS n={n_is} pnl={base_is_pnl:+,.0f} | OOS n={n_oos} pnl={base_oos_pnl:+,.0f}")

    print(f"\n{'TP1':>6} {'IS_pnl':>10} {'IS_delta':>10} {'OOS_pnl':>10} {'OOS_delta':>10} "
          f"{'WF':>7} {'SW_hurt':>8} {'VERDICT'}")
    print("-" * 90)

    results = []
    for tp1 in TP1_CANDIDATES:
        is_r  = run_with_tp1(spy, vix, tp1, IS_S,  IS_E)
        oos_r = run_with_tp1(spy, vix, tp1, OOS_S, OOS_E)
        is_pnl  = sum(t.dollar_pnl for t in is_r.trades)
        oos_pnl = sum(t.dollar_pnl for t in oos_r.trades)
        is_d  = is_pnl  - base_is_pnl
        oos_d = oos_pnl - base_oos_pnl
        wf    = wf_norm(oos_d, n_oos, is_d, n_is)

        hurt = 0
        sw_details = []
        for sw_name, sw_s, sw_e in SUB_WINDOWS:
            sw_base = run_with_tp1(spy, vix, 0.75, sw_s, sw_e)
            sw_cand = run_with_tp1(spy, vix, tp1,  sw_s, sw_e)
            sw_d = sum(t.dollar_pnl for t in sw_cand.trades) - sum(t.dollar_pnl for t in sw_base.trades)
            verdict_sw = "HELP" if sw_d > 50 else "FLAT" if abs(sw_d) <= 50 else "HURT"
            if verdict_sw == "HURT":
                hurt += 1
            sw_details.append(f"{sw_name}:{sw_d:+.0f}")

        wf_str = f"{wf:.3f}" if wf is not None else " N/A "
        oos_pos = oos_d > 0
        is_pos  = is_d > 0
        sw_ok   = hurt <= 1
        wf_pass = wf is not None and wf >= 0.70

        if tp1 == 0.75:
            verdict = "BASELINE"
        elif oos_pos and (wf_pass or (wf is not None and wf < 0 and oos_pos)):
            if wf_pass and sw_ok:
                verdict = "CANDIDATE"
            elif not wf_pass:
                verdict = f"OOS+_WF{wf:.2f}"
            else:
                verdict = f"SW_HURT_{hurt}"
        elif not oos_pos:
            verdict = "OOS_NEG"
        else:
            verdict = "REJECT"

        print(f"{tp1*100:>5.0f}% {is_pnl:>10,.0f} {is_d:>+10,.0f} {oos_pnl:>10,.0f} {oos_d:>+10,.0f} "
              f"{wf_str:>7} {hurt:>8}/4  {verdict}")
        print(f"       SW: {', '.join(sw_details)}")

        results.append({
            "tp1": tp1, "is_pnl": is_pnl, "oos_pnl": oos_pnl,
            "is_d": is_d, "oos_d": oos_d, "wf": wf, "hurt": hurt,
            "oos_pos": oos_pos, "verdict": verdict,
        })

    print("\n=== SUMMARY ===")
    best_oos = max(results, key=lambda r: r["oos_pnl"])
    best_wf  = max((r for r in results if r["wf"] is not None and r["oos_d"] > 0),
                   key=lambda r: r["wf"], default=None)
    print(f"Best OOS P&L:  TP1={best_oos['tp1']*100:.0f}% pnl={best_oos['oos_pnl']:+,.0f} "
          f"WF={best_oos['wf']:.3f if best_oos['wf'] else 'N/A'}")
    if best_wf:
        print(f"Best WF (OOS+): TP1={best_wf['tp1']*100:.0f}% WF={best_wf['wf']:.3f} "
              f"OOS_delta={best_wf['oos_d']:+,.0f}")


if __name__ == "__main__":
    run()
