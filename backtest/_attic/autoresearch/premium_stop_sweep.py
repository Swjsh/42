"""
Premium stop threshold sweep: is -10% (current) optimal for BOTH accounts?

From OOS analysis:
  Safe:  10/10 losers via STOP_PREMIUM_STOP avg -$219. Winners hold 58min.
  Aggressive: 12/14 losers via STOP_PREMIUM_STOP avg -$219. Winners hold 52min.

Key Q: Does -8% reduce losses while creating false stops on eventual winners?
  False stop = winner would have recovered if given a wider stop.
  The OOS data shows losers have 12-31% genuine adverse moves (all real, not noise).
  BUT intraday dips on winner trades could trigger -8% before recovering.

Sweep range: -0.06, -0.07, -0.08, -0.09, -0.10 (baseline), -0.12, -0.15, -0.20
For each:
  1. OOS P&L vs baseline
  2. IS P&L vs baseline
  3. WF_norm
  4. Sub-window stability
  Both Safe and Aggressive accounts.
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
    ("W1", dt.date(2025, 1, 2),  dt.date(2025, 6, 30)),
    ("W2", dt.date(2025, 7, 1),  dt.date(2025, 12, 31)),
    ("W3", dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
    ("W4", dt.date(2026, 4, 1),  dt.date(2026, 5, 7)),
]

SAFE_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
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

AGG_BASE = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=False,
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

STOP_CANDIDATES = [-0.06, -0.07, -0.08, -0.09, -0.10, -0.12, -0.15, -0.20]
SAFE_BASELINE_STOP = -0.10
AGG_BASELINE_STOP  = -0.10


def sweep_account(spy, vix, base_kwargs, baseline_stop, label):
    print(f"\n{'='*60}")
    print(f"=== {label} PREMIUM STOP SWEEP (baseline={baseline_stop*100:.0f}%) ===")
    print(f"{'='*60}")

    # Compute baseline
    kw_base = dict(base_kwargs)
    kw_base["premium_stop_pct_bear"] = baseline_stop
    is_base  = run_backtest(spy, vix, start_date=IS_S,  end_date=IS_E,  **kw_base)
    oos_base = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **kw_base)
    is_b_pnl  = sum(t.dollar_pnl for t in is_base.trades)
    oos_b_pnl = sum(t.dollar_pnl for t in oos_base.trades)
    n_is  = len(is_base.trades)
    n_oos = len(oos_base.trades)
    print(f"BASELINE (stop={baseline_stop*100:.0f}%): IS n={n_is} pnl={is_b_pnl:+,.0f} | "
          f"OOS n={n_oos} pnl={oos_b_pnl:+,.0f}")

    print(f"\n{'STOP':>6} {'IS_pnl':>10} {'IS_d':>8} {'OOS_pnl':>10} {'OOS_d':>8} "
          f"{'WF':>7} {'SW':>5} {'n_IS':>5} {'n_OOS':>6} {'VERDICT'}")
    print("-" * 85)

    results = []
    for stop in STOP_CANDIDATES:
        kw = dict(base_kwargs)
        kw["premium_stop_pct_bear"] = stop
        is_r  = run_backtest(spy, vix, start_date=IS_S,  end_date=IS_E,  **kw)
        oos_r = run_backtest(spy, vix, start_date=OOS_S, end_date=OOS_E, **kw)
        is_p  = sum(t.dollar_pnl for t in is_r.trades)
        oos_p = sum(t.dollar_pnl for t in oos_r.trades)
        is_d  = is_p  - is_b_pnl
        oos_d = oos_p - oos_b_pnl

        wf = None
        if is_d != 0 and n_is > 0 and n_oos > 0:
            wf = (oos_d / n_oos) / (is_d / n_is)

        hurt = 0
        for sw_name, sw_s, sw_e in SUB_WINDOWS:
            sw_b  = run_backtest(spy, vix, start_date=sw_s, end_date=sw_e, **kw_base)
            sw_c  = run_backtest(spy, vix, start_date=sw_s, end_date=sw_e, **kw)
            sw_d  = sum(t.dollar_pnl for t in sw_c.trades) - sum(t.dollar_pnl for t in sw_b.trades)
            if sw_d < -50:
                hurt += 1

        wf_str = f"{wf:.3f}" if wf is not None else " N/A "
        oos_pos = oos_d > 0
        wf_pass = wf is not None and wf >= 0.70
        sw_ok   = hurt <= 1

        if abs(stop - baseline_stop) < 0.001:
            verdict = "BASELINE"
        elif oos_pos and wf_pass and sw_ok:
            verdict = "CANDIDATE"
        elif oos_pos and wf_pass and not sw_ok:
            verdict = f"SW_HURT_{hurt}"
        elif oos_pos and not wf_pass:
            wf_val = f"{wf:.2f}" if wf else "N/A"
            verdict = f"OOS+_WF{wf_val}"
        else:
            verdict = "OOS_NEG"

        n_diff = len(oos_r.trades) - n_oos
        n_diff_str = f"{n_diff:+d}" if n_diff != 0 else "  0"
        print(f"{stop*100:>5.0f}% {is_p:>10,.0f} {is_d:>+8,.0f} {oos_p:>10,.0f} {oos_d:>+8,.0f} "
              f"{wf_str:>7} {hurt:>2}/4 {n_is:>5} {n_oos+n_diff:>6} {verdict}")

        results.append({
            "stop": stop, "is_pnl": is_p, "oos_pnl": oos_p,
            "is_d": is_d, "oos_d": oos_d, "wf": wf,
            "hurt": hurt, "verdict": verdict,
        })

    best_oos = max(results, key=lambda r: r["oos_pnl"])
    candidates = [r for r in results if r["verdict"] == "CANDIDATE"]
    print(f"\nBest OOS P&L: stop={best_oos['stop']*100:.0f}% pnl={best_oos['oos_pnl']:+,.0f} "
          f"WF={best_oos['wf']:.3f if best_oos['wf'] else 'N/A'}")
    if candidates:
        for c in candidates:
            print(f"CANDIDATE: stop={c['stop']*100:.0f}% OOS_delta={c['oos_d']:+,.0f} WF={c['wf']:.3f}")
    else:
        neg_oos = [r for r in results if r.get("oos_d", 0) < 0]
        pos_oos = [r for r in results if r.get("oos_d", 0) > 0]
        print(f"OOS+ (no WF pass): {[r['stop']*100 for r in pos_oos]}")
        print(f"OOS- (degraded):   {[r['stop']*100 for r in neg_oos]}")
    return results


def run():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    safe_results = sweep_account(spy, vix, SAFE_BASE, SAFE_BASELINE_STOP, "SAFE")
    agg_results  = sweep_account(spy, vix, AGG_BASE,  AGG_BASELINE_STOP,  "AGGRESSIVE")

    print("\n=== CROSS-ACCOUNT SUMMARY ===")
    print("SAFE best OOS stops: ", sorted([r for r in safe_results if r.get("oos_d", 0) > 0],
                                          key=lambda r: -r["oos_pnl"])[:3])
    print("AGG  best OOS stops: ", sorted([r for r in agg_results  if r.get("oos_d", 0) > 0],
                                          key=lambda r: -r["oos_pnl"])[:3])

    print("\n=== PREMIUM STOP SWEEP COMPLETE ===")


if __name__ == "__main__":
    run()
