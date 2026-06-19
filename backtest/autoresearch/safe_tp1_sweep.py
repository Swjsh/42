"""
Safe account TP1 target sweep: is +30% (current) optimal post-Rank35?

Safe baseline: IS n=128 pnl=+$12,838 (100% BEAR), OOS n=21 pnl=+$3,728
Current: tp1_premium_pct=0.30, tp1_qty_fraction=0.667, runner=2.5x

Q: Would +20%, +25%, +30%(baseline), +40%, +50%, +60% TP1 improve OOS?

Context from OOS analysis:
  - 5 OOS winners exit via TP1_THEN_RUNNER (runner via ribbon/time)
  - 6 OOS winners exit via TP1_THEN_RUNNER_BE_STOP or TP1_THEN_RUNNER_TIME
  - 10 OOS losers exit via STOP_PREMIUM_STOP (never reach TP1)
  - Changing TP1 target doesn't affect the 10 losers (they stop out first)
  - Lower TP1 (+20%) = lock in gains sooner on the 11 winners
  - Higher TP1 (+50%) = need bigger move to fire TP1; some winners might stop out

Post-Rank35 Safe baseline (correct production params):
  IS n=128 pnl=+12838 | OOS n=21 pnl=+3728
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

SAFE_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
)

TP1_CANDIDATES = [0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.75]
BASELINE_TP1 = 0.30


def run_with_tp1(spy, vix, tp1_pct, start, end):
    kwargs = dict(SAFE_BASE)
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

    base_is  = run_with_tp1(spy, vix, BASELINE_TP1, IS_S,  IS_E)
    base_oos = run_with_tp1(spy, vix, BASELINE_TP1, OOS_S, OOS_E)
    base_is_pnl  = sum(t.dollar_pnl for t in base_is.trades)
    base_oos_pnl = sum(t.dollar_pnl for t in base_oos.trades)
    n_is  = len(base_is.trades)
    n_oos = len(base_oos.trades)
    print(f"\nBASELINE (TP1=+{BASELINE_TP1*100:.0f}%): IS n={n_is} pnl={base_is_pnl:+,.0f} | "
          f"OOS n={n_oos} pnl={base_oos_pnl:+,.0f}")

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
            sw_base = run_with_tp1(spy, vix, BASELINE_TP1, sw_s, sw_e)
            sw_cand = run_with_tp1(spy, vix, tp1, sw_s, sw_e)
            sw_d = (sum(t.dollar_pnl for t in sw_cand.trades)
                    - sum(t.dollar_pnl for t in sw_base.trades))
            verdict_sw = "HELP" if sw_d > 50 else "FLAT" if abs(sw_d) <= 50 else "HURT"
            if verdict_sw == "HURT":
                hurt += 1
            sw_details.append(f"{sw_name}:{sw_d:+.0f}")

        wf_str = f"{wf:.3f}" if wf is not None else " N/A "
        oos_pos  = oos_d > 0
        wf_pass  = wf is not None and wf >= 0.70
        sw_ok    = hurt <= 1

        if tp1 == BASELINE_TP1:
            verdict = "BASELINE"
        elif oos_pos and wf_pass and sw_ok:
            verdict = "CANDIDATE"
        elif oos_pos and not wf_pass:
            verdict = f"OOS+_WF{wf:.2f}" if wf else "OOS+_WF_NA"
        elif not oos_pos:
            verdict = "OOS_NEG"
        else:
            verdict = "REJECT"

        print(f"{tp1*100:>5.0f}% {is_pnl:>10,.0f} {is_d:>+10,.0f} {oos_pnl:>10,.0f} {oos_d:>+10,.0f} "
              f"{wf_str:>7} {hurt:>8}/4  {verdict}")
        print(f"       SW: {', '.join(sw_details)}")

        results.append({
            "tp1": tp1, "is_pnl": is_pnl, "oos_pnl": oos_pnl,
            "is_d": is_d, "oos_d": oos_d, "wf": wf, "hurt": hurt, "verdict": verdict,
        })

    print("\n=== SUMMARY ===")
    best_oos = max(results, key=lambda r: r["oos_pnl"])
    candidates = [r for r in results if r["verdict"] == "CANDIDATE"]
    print(f"Best OOS P&L: TP1={best_oos['tp1']*100:.0f}% pnl={best_oos['oos_pnl']:+,.0f}")
    if candidates:
        for c in candidates:
            print(f"CANDIDATE: TP1={c['tp1']*100:.0f}% OOS_delta={c['oos_d']:+,.0f} WF={c['wf']:.3f}")
    else:
        print("No candidates pass all gates.")

    # TP1 fraction companion sweep (0.50 vs 0.667 vs 0.80) at current TP1=0.30
    print("\n=== TP1 QTY FRACTION SWEEP (TP1=+30%) ===")
    for frac in [0.40, 0.50, 0.667, 0.75, 0.80]:
        kw = dict(SAFE_BASE)
        kw["tp1_qty_fraction"] = frac
        kw["tp1_premium_pct"]  = 0.30
        is_f  = run_backtest(spy, vix, start_date=IS_S, end_date=IS_E, **kw)
        oos_f = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **kw)
        is_fp  = sum(t.dollar_pnl for t in is_f.trades)
        oos_fp = sum(t.dollar_pnl for t in oos_f.trades)
        is_fd  = is_fp  - base_is_pnl
        oos_fd = oos_fp - base_oos_pnl
        wf_f   = wf_norm(oos_fd, n_oos, is_fd, n_is) if is_fd != 0 else None
        tag = "BASELINE" if abs(frac - 0.667) < 0.001 else ""
        wf_s = f"{wf_f:.3f}" if wf_f is not None else "N/A"
        print(f"  frac={frac:.3f}: IS={is_fp:+,.0f} ({is_fd:+.0f}) OOS={oos_fp:+,.0f} ({oos_fd:+.0f}) "
              f"WF={wf_s}  {tag}")

    print("\n=== SAFE TP1 SWEEP COMPLETE ===")


if __name__ == "__main__":
    run()
