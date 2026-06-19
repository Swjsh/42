"""
TP1_QTY_FRACTION + RUNNER_TARGET_PREMIUM_PCT SWEEP

Both knobs were dead until L108/L109 fixes (2026-06-17). Production:
  tp1_qty_fraction=0.667 (close 2/3 at TP1, keep 1/3 runner)
  runner_target_premium_pct=2.50 (runner exits at 2.5x entry premium)

This is the first proper optimization sweep of both.

Phase 1: tp1_qty_fraction sweep (runner held at 2.50)
Phase 2: runner_target sweep (tp1 held at 0.667 = production)
Phase 3: composition of best tp1 + best runner

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

# Production BASE — matches params.json exactly
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

TP1_VALUES    = [0.30, 0.40, 0.50, 0.55, 0.60, 0.667, 0.75, 0.80]
RUNNER_VALUES = [1.25, 1.50, 2.00, 2.50, 3.00, 3.50, 4.00]


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _by_date(trades):
    result = {}
    for t in trades:
        d = _date(t)
        result[d] = result.get(d, 0.0) + t.dollar_pnl
    return result


def _anchor_ok(by_date, base_bd):
    for d in J_WINNERS:
        bp = base_bd.get(d, 0.0)
        cp = by_date.get(d, 0.0)
        if bp > 0 and cp < bp * 0.90:
            return False
    return True


def _wf(oos_d, n_oos, is_d, n_is):
    if is_d == 0:
        return 0.0
    return (oos_d / n_oos) / (is_d / n_is)


def _verdict(oos_d, wf, anchor):
    if oos_d > 0 and wf >= 0.70 and anchor:
        return "PASS"
    reasons = []
    if oos_d <= 0:
        reasons.append(f"OOS_delta={oos_d:+.0f}")
    if wf < 0.70:
        reasons.append(f"WF={wf:.3f}")
    if not anchor:
        reasons.append("ANCHOR_FAIL")
    return "FAIL(" + ",".join(reasons) + ")"


if __name__ == "__main__":
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("=" * 95)
    print("TP1_QTY_FRACTION + RUNNER_TARGET_PREMIUM_PCT SWEEP (L108+L109 activation)")
    print("=" * 95)

    # ── BASELINE ──────────────────────────────────────────────────────────────────────────
    is_base  = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **BASE)
    oos_base = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)
    is_bp  = _pnl(is_base.trades)
    oos_bp = _pnl(oos_base.trades)
    is_bd  = _by_date(is_base.trades)
    n_is   = len(is_base.trades)
    n_oos  = len(oos_base.trades)
    print(f"\n[BASELINE] IS n={n_is} pnl={is_bp:+.0f}  OOS n={n_oos} pnl={oos_bp:+.0f}")
    print(f"  Production: tp1_qty_fraction=0.667  runner_target_premium_pct=2.50")

    # ── PHASE 1: tp1_qty_fraction sweep ───────────────────────────────────────────────────
    print(f"\n{'=' * 95}")
    print("PHASE 1: tp1_qty_fraction SWEEP (runner_target held at 2.50)")
    print(f"{'=' * 95}")
    print(f"  {'tp1_frac':>10}  {'IS_n':>5}  {'IS_delta':>9}  {'OOS_delta':>9}  {'WF':>7}  {'anchor':>7}  {'verdict'}")
    print("  " + "-" * 75)
    best_tp1_val = 0.667
    best_tp1_oos = 0.0
    best_tp1_verdict = "BASELINE"
    for tp1 in TP1_VALUES:
        params = dict(BASE, tp1_qty_fraction=tp1)
        is_r  = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **params)
        oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **params)
        is_d  = _pnl(is_r.trades) - is_bp
        oos_d = _pnl(oos_r.trades) - oos_bp
        wf    = _wf(oos_d, n_oos, is_d, n_is)
        anc   = _anchor_ok(_by_date(is_r.trades), is_bd)
        tag   = " *PROD*" if tp1 == 0.667 else ""
        verd  = _verdict(oos_d, wf, anc)
        print(f"  {tp1:>10.3f}  {len(is_r.trades):>5}  {is_d:>+9.0f}  {oos_d:>+9.0f}  {wf:>7.3f}  {'OK' if anc else 'FAIL':>7}  {verd}{tag}")
        if oos_d > best_tp1_oos and verd.startswith("PASS"):
            best_tp1_oos = oos_d
            best_tp1_val = tp1
            best_tp1_verdict = verd

    # ── PHASE 2: runner_target_premium_pct sweep ──────────────────────────────────────────
    print(f"\n{'=' * 95}")
    print("PHASE 2: runner_target_premium_pct SWEEP (tp1_qty_fraction held at 0.667)")
    print(f"{'=' * 95}")
    print(f"  {'runner_tgt':>10}  {'IS_n':>5}  {'IS_delta':>9}  {'OOS_delta':>9}  {'WF':>7}  {'anchor':>7}  {'verdict'}")
    print("  " + "-" * 75)
    best_runner_val = 2.50
    best_runner_oos = 0.0
    best_runner_verdict = "BASELINE"
    for rval in RUNNER_VALUES:
        params = dict(BASE, runner_target_premium_pct=rval)
        is_r  = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **params)
        oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **params)
        is_d  = _pnl(is_r.trades) - is_bp
        oos_d = _pnl(oos_r.trades) - oos_bp
        wf    = _wf(oos_d, n_oos, is_d, n_is)
        anc   = _anchor_ok(_by_date(is_r.trades), is_bd)
        tag   = " *PROD*" if rval == 2.50 else ""
        verd  = _verdict(oos_d, wf, anc)
        print(f"  {rval:>10.2f}  {len(is_r.trades):>5}  {is_d:>+9.0f}  {oos_d:>+9.0f}  {wf:>7.3f}  {'OK' if anc else 'FAIL':>7}  {verd}{tag}")
        if oos_d > best_runner_oos and verd.startswith("PASS"):
            best_runner_oos = oos_d
            best_runner_val = rval
            best_runner_verdict = verd

    # ── PHASE 3: Best combination ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 95}")
    print(f"PHASE 3: BEST COMBINATION (tp1={best_tp1_val}, runner={best_runner_val})")
    print(f"{'=' * 95}")
    if best_tp1_val == 0.667 and best_runner_val == 2.50:
        print("  Production defaults are optimal — no change needed.")
    else:
        params = dict(BASE, tp1_qty_fraction=best_tp1_val, runner_target_premium_pct=best_runner_val)
        is_r  = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **params)
        oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **params)
        is_d  = _pnl(is_r.trades) - is_bp
        oos_d = _pnl(oos_r.trades) - oos_bp
        wf    = _wf(oos_d, n_oos, is_d, n_is)
        anc   = _anchor_ok(_by_date(is_r.trades), is_bd)
        verd  = _verdict(oos_d, wf, anc)
        print(f"  IS n={len(is_r.trades)} delta={is_d:+.0f}  OOS delta={oos_d:+.0f}  WF={wf:.3f}  anchor={'OK' if anc else 'FAIL'}")
        print(f"  Status: {verd}")
        # Additivity check
        expected_oos = best_tp1_oos + best_runner_oos
        overlap_oos  = expected_oos - oos_d
        print(f"  Additivity: expected OOS (sum)={expected_oos:+.0f}, actual={oos_d:+.0f}, overlap={overlap_oos:+.0f}")
        if abs(overlap_oos) < 200:
            print("  -> NEAR-INDEPENDENT")
        else:
            print("  -> INTERACTION detected")

    print("\n[SUMMARY]")
    print(f"  Best tp1_qty_fraction: {best_tp1_val} (OOS_delta vs baseline: {best_tp1_oos:+.0f})")
    print(f"  Best runner_target: {best_runner_val} (OOS_delta vs baseline: {best_runner_oos:+.0f})")
    print(f"  Production values: tp1=0.667 runner=2.50")
    if best_tp1_val != 0.667 or best_runner_val != 2.50:
        print(f"  -> IMPROVEMENT FOUND: test sub-window stability before ratifying")
    else:
        print(f"  -> Production defaults confirmed optimal")

    print("\nANALYSIS COMPLETE.")
