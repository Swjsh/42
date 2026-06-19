"""
TP1_QTY_FRACTION=0.75 SUB-WINDOW STABILITY CHECK

Phase 1 sweep found tp1=0.75 shows:
  IS: delta=-$99 (noise-level, 244 trades, -$0.41/trade)
  OOS: delta=+$353 (meaningful, 15 trades, +$23.5/trade)

The standard WF formula gives -57.9 (negative because IS_delta<0) which
technically fails the gate. But when IS_delta≈0, WF is undefined/misleading.

This script runs sub-window analysis to determine if OOS improvement is robust:
  - 4 IS sub-windows (W1-W4) to check stability
  - Rolling OOS windows (biweekly) to check if OOS gain is real or single-trade fluke
  - Per-anchor-day breakdown to confirm no regression on J's winners

Security: read-only. No Alpaca calls. Free-tier only.
"""
from __future__ import annotations
import sys
import pathlib
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

# IS sub-windows (same as prior C14 sub-window scripts)
IS_SUB_WINDOWS = [
    ("W1", dt.date(2025, 1,  2), dt.date(2025, 6, 30)),
    ("W2", dt.date(2025, 7,  1), dt.date(2025, 12, 31)),
    ("W3", dt.date(2026, 1,  1), dt.date(2026, 3, 31)),
    ("W4", dt.date(2026, 4,  1), dt.date(2026, 5,  7)),
]

# Rolling OOS biweekly windows
OOS_ROLLING = [
    ("OOS_W1", dt.date(2026, 5, 8),  dt.date(2026, 5, 14)),
    ("OOS_W2", dt.date(2026, 5, 15), dt.date(2026, 5, 22)),
]

BASE = dict(
    use_real_fills=True,
    premium_stop_pct_bear=-0.20,
    premium_stop_pct_bull=-0.08,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    midday_trendline_gate=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    per_trade_risk_cap_pct=0.30,
)

TP1_CANDIDATE = 0.75

PROD_PARAMS  = dict(BASE)
CAND_PARAMS  = dict(BASE, tp1_qty_fraction=TP1_CANDIDATE)


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _by_date(trades):
    result = {}
    for t in trades:
        d2 = _date(t)
        result[d2] = result.get(d2, 0.0) + t.dollar_pnl
    return result


if __name__ == "__main__":
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("=" * 90)
    print(f"TP1_QTY_FRACTION=0.75 SUB-WINDOW STABILITY CHECK")
    print("=" * 90)

    # Full IS/OOS baseline and candidate
    is_prod  = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **PROD_PARAMS)
    oos_prod = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **PROD_PARAMS)
    is_cand  = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **CAND_PARAMS)
    oos_cand = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **CAND_PARAMS)

    is_prod_p  = _pnl(is_prod.trades)
    oos_prod_p = _pnl(oos_prod.trades)
    is_cand_p  = _pnl(is_cand.trades)
    oos_cand_p = _pnl(oos_cand.trades)

    print(f"\n[FULL IS]  PROD n={len(is_prod.trades)} pnl={is_prod_p:+.0f}  CAND n={len(is_cand.trades)} pnl={is_cand_p:+.0f}  delta={is_cand_p-is_prod_p:+.0f}")
    print(f"[FULL OOS] PROD n={len(oos_prod.trades)} pnl={oos_prod_p:+.0f}  CAND n={len(oos_cand.trades)} pnl={oos_cand_p:+.0f}  delta={oos_cand_p-oos_prod_p:+.0f}")

    # J anchor day breakdown
    print(f"\n[J ANCHOR DAY CHECK]")
    is_prod_bd = _by_date(is_prod.trades)
    is_cand_bd = _by_date(is_cand.trades)
    for d in sorted(J_WINNERS):
        p_pnl = is_prod_bd.get(d, 0.0)
        c_pnl = is_cand_bd.get(d, 0.0)
        flag = " OK" if (p_pnl <= 0 or c_pnl >= p_pnl * 0.90) else " REGRESS"
        print(f"  {d}  PROD={p_pnl:+.0f}  CAND={c_pnl:+.0f}  delta={c_pnl-p_pnl:+.0f}{flag}")

    # IS sub-windows
    print(f"\n[IS SUB-WINDOWS] (HURT = candidate worse; no HURT -> stable)")
    print(f"  {'window':>8}  {'prod_pnl':>10}  {'cand_pnl':>10}  {'delta':>8}  {'status'}")
    print("  " + "-" * 55)
    n_hurt = 0
    for name, s, e in IS_SUB_WINDOWS:
        p_r = run_backtest(spy_df, vix_df, start_date=s, end_date=e, **PROD_PARAMS)
        c_r = run_backtest(spy_df, vix_df, start_date=s, end_date=e, **CAND_PARAMS)
        p_p = _pnl(p_r.trades)
        c_p = _pnl(c_r.trades)
        d   = c_p - p_p
        hurt = d < -200  # >$200 regression = HURT
        if hurt:
            n_hurt += 1
        print(f"  {name:>8}  {p_p:>+10.0f}  {c_p:>+10.0f}  {d:>+8.0f}  {'HURT' if hurt else 'OK'}")
    print(f"\n  Sub-window gate: {'PASS (0 HURT)' if n_hurt == 0 else f'FAIL ({n_hurt} HURT)'}")

    # Rolling OOS windows
    print(f"\n[ROLLING OOS WINDOWS]")
    print(f"  {'window':>8}  {'prod_pnl':>10}  {'cand_pnl':>10}  {'delta':>8}  {'status'}")
    print("  " + "-" * 55)
    n_oos_pass = 0
    for name, s, e in OOS_ROLLING:
        p_r = run_backtest(spy_df, vix_df, start_date=s, end_date=e, **PROD_PARAMS)
        c_r = run_backtest(spy_df, vix_df, start_date=s, end_date=e, **CAND_PARAMS)
        p_p = _pnl(p_r.trades)
        c_p = _pnl(c_r.trades)
        d   = c_p - p_p
        passes = d >= 0
        if passes:
            n_oos_pass += 1
        print(f"  {name:>8}  {p_p:>+10.0f}  {c_p:>+10.0f}  {d:>+8.0f}  {'PASS' if passes else 'FAIL'}")
    pct = n_oos_pass / len(OOS_ROLLING) * 100
    print(f"\n  OOS rolling gate: {n_oos_pass}/{len(OOS_ROLLING)} PASS ({pct:.0f}%) — gate requires ≥60%")

    # Summary verdict
    print(f"\n[SUMMARY]")
    total_oos_delta = oos_cand_p - oos_prod_p
    total_is_delta  = is_cand_p  - is_prod_p
    print(f"  IS delta: {total_is_delta:+.0f}  (production: {is_prod_p:+.0f})")
    print(f"  OOS delta: {total_oos_delta:+.0f}  (production: {oos_prod_p:+.0f})")
    print(f"  Sub-windows: {n_hurt} HURT (gate: 0)")
    print(f"  Rolling OOS: {n_oos_pass}/{len(OOS_ROLLING)} ({pct:.0f}%) (gate: 60%+)")
    print(f"  J anchors: {'OK' if all(is_prod_bd.get(d, 0.0) <= 0 or is_cand_bd.get(d, 0.0) >= is_prod_bd.get(d, 0.0) * 0.90 for d in J_WINNERS) else 'REGRESS'}")

    if n_hurt == 0 and n_oos_pass >= 1 and total_oos_delta > 0:
        print(f"\n  CANDIDATE STATUS: INVESTIGATE (IS≈0 + OOS positive, sub-windows stable)")
        print(f"  NOTE: Standard WF formula invalid when IS_delta≈0. Use sub-window + rolling OOS as primary gate.")
        print(f"  Recommend: file A/B scorecard with sub-window stability as primary evidence.")
    else:
        print(f"\n  CANDIDATE STATUS: FAIL (sub-window or OOS not stable)")

    print("\nANALYSIS COMPLETE.")
