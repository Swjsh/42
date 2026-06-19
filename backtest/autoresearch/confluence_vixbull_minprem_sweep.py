"""
C14 BATCH 8: Three independent 1D sweeps for remaining unswept knobs.

1. confluence_tolerance_dollars (prod=0.30) — in _FILTER_CONST_MAP
2. vix_bull_max / VIX_BULL_HARD_CAP (prod=22.0) — in _FILTER_CONST_MAP as vix_bull_max
3. min_premium_for_level_tiers (prod=0.50) — direct kwarg to run_backtest()

Security: read-only. No Alpaca calls.
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

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _anchor_ok(trades, base_by_date):
    by_date = {}
    for t in trades:
        d = _date(t)
        by_date[d] = by_date.get(d, 0.0) + t.dollar_pnl
    for d in J_WINNERS:
        bp = base_by_date.get(d, 0.0)
        cp = by_date.get(d, 0.0)
        if bp > 0 and cp < bp * 0.90:
            return False
    return True


def _wf(is_delta, n_is, oos_delta, n_oos):
    if is_delta == 0 or n_oos == 0 or n_is == 0:
        return 0.0
    return (oos_delta / n_oos) / (is_delta / n_is)


def _header():
    return (f"  {'value':>10}  {'IS_n':>5}  {'IS_pnl':>9}  {'IS_delta':>9}  "
            f"{'OOS_n':>5}  {'OOS_pnl':>9}  {'OOS_delta':>10}  {'WF_norm':>8}  {'anchor':>6}  Verdict")


def _sweep(spy_df, vix_df, label, values, baseline, base_is_pnl, base_oos_pnl,
           n_is, n_oos, base_by_date, param_key=None, kwarg_key=None):
    """param_key → passed via params_overrides; kwarg_key → passed as direct kwarg."""
    assert param_key or kwarg_key, "must specify param_key or kwarg_key"
    print(_header())
    print("  " + "-" * 87)
    results = []
    for val in values:
        if param_key:
            is_r = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                                params_overrides={param_key: val}, **BASE)
            oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                                 params_overrides={param_key: val}, **BASE)
        else:
            is_r = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                                **{**BASE, kwarg_key: val})
            oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                                 **{**BASE, kwarg_key: val})
        is_p = _pnl(is_r.trades)
        oos_p = _pnl(oos_r.trades)
        is_d = is_p - base_is_pnl
        oos_d = oos_p - base_oos_pnl
        wf = _wf(is_d, n_is, oos_d, n_oos)
        anchor = _anchor_ok(is_r.trades, base_by_date)
        verdict = "PASS" if (oos_d > 0 and wf >= 0.70 and anchor) else ("OOS+" if oos_d > 0 else "FAIL")
        tag = " <-- prod" if val == baseline else ""
        print(f"  {val:>10.3f}  {len(is_r.trades):>5}  {is_p:>+9.0f}  {is_d:>+9.0f}  "
              f"{len(oos_r.trades):>5}  {oos_p:>+9.0f}  {oos_d:>+10.0f}  {wf:>8.3f}  "
              f"{'OK' if anchor else 'FAIL':>6}  {verdict}{tag}")
        results.append((val, len(is_r.trades), is_p, is_d, len(oos_r.trades), oos_p, oos_d, wf, anchor, verdict))
    return results


if __name__ == "__main__":
    print("=" * 100)
    print("C14 BATCH 8: confluence_tolerance_dollars / vix_bull_max / min_premium_for_level_tiers SWEEP")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n[0] BASELINE (confluence=0.30, vix_bull_max=22.0, min_prem_level=0.50)...")
    base_is  = run_backtest(spy_df, vix_df, start_date=IS_START,  end_date=IS_END,  **BASE)
    base_oos = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    base_by_date = {}
    for t in base_is.trades:
        d = _date(t)
        base_by_date[d] = base_by_date.get(d, 0.0) + t.dollar_pnl
    n_is  = len(base_is.trades)
    n_oos = len(base_oos.trades)
    print(f"  IS n={n_is} pnl={base_is_pnl:+.0f}")
    print(f"  OOS n={n_oos} pnl={base_oos_pnl:+.0f}")

    print("\n" + "=" * 100)
    print("SWEEP 1: confluence_tolerance_dollars (prod=0.30)")
    print("  Mechanism: how far 'confluence' triggers may be from a named level and still count.")
    print("  Tighter (lower) = stricter entry; wider (higher) = more confluence hits.")
    r1 = _sweep(spy_df, vix_df, "confluence_tolerance_dollars",
                [0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.75],
                baseline=0.30,
                base_is_pnl=base_is_pnl, base_oos_pnl=base_oos_pnl,
                n_is=n_is, n_oos=n_oos, base_by_date=base_by_date,
                param_key="confluence_tolerance_dollars")

    print("\n" + "=" * 100)
    print("SWEEP 2: vix_bull_max / VIX_BULL_HARD_CAP (prod=22.0)")
    print("  Mechanism: bull entries blocked when VIX_NOW > vix_bull_max.")
    print("  Lower cap = block bull entries in higher-VIX regimes.")
    r2 = _sweep(spy_df, vix_df, "vix_bull_max",
                [16.0, 18.0, 20.0, 22.0, 25.0, 30.0],
                baseline=22.0,
                base_is_pnl=base_is_pnl, base_oos_pnl=base_oos_pnl,
                n_is=n_is, n_oos=n_oos, base_by_date=base_by_date,
                param_key="vix_bull_max")

    print("\n" + "=" * 100)
    print("SWEEP 3: min_premium_for_level_tiers (prod=0.50)")
    print("  Mechanism: LEVEL/ELITE/SUPER entries skipped if entry premium < threshold.")
    print("  Higher = skip cheap sub-$0.50 LEVEL entries (5/07 15:20 loss case).")
    r3 = _sweep(spy_df, vix_df, "min_premium_for_level_tiers",
                [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80],
                baseline=0.50,
                base_is_pnl=base_is_pnl, base_oos_pnl=base_oos_pnl,
                n_is=n_is, n_oos=n_oos, base_by_date=base_by_date,
                kwarg_key="min_premium_for_level_tiers")

    print("\n" + "=" * 100)
    print("SUMMARY")
    all_pass = []
    for label, results in [("confluence_tolerance_dollars", r1),
                            ("vix_bull_max", r2),
                            ("min_premium_for_level_tiers", r3)]:
        for val, _, _, is_d, _, _, oos_d, wf, anchor, verdict in results:
            if verdict == "PASS":
                all_pass.append((label, val, is_d, oos_d, wf))

    if all_pass:
        print(f"\n  PASS candidates ({len(all_pass)} total):")
        for label, val, is_d, oos_d, wf in all_pass:
            print(f"    {label}={val}: IS_delta={is_d:+.0f} OOS_delta={oos_d:+.0f} WF={wf:.3f}")
        best = max(all_pass, key=lambda r: r[3])
        print(f"\n  BEST: {best[0]}={best[1]} (OOS_delta={best[3]:+.0f})")
    else:
        print("\n  No PASS candidates. All three production defaults confirmed.")
        oos_pos = [(label, val, is_d, oos_d, wf)
                   for label, results in [("confluence_tolerance_dollars", r1),
                                           ("vix_bull_max", r2),
                                           ("min_premium_for_level_tiers", r3)]
                   for val, _, _, is_d, _, _, oos_d, wf, anchor, verdict in results
                   if oos_d > 0]
        if oos_pos:
            print(f"\n  OOS+ but WF<0.70 (informational, top 5):")
            for label, val, is_d, oos_d, wf in sorted(oos_pos, key=lambda r: r[3], reverse=True)[:5]:
                print(f"    {label}={val}: IS_delta={is_d:+.0f} OOS_delta={oos_d:+.0f} WF={wf:.3f}")

    print("\nANALYSIS COMPLETE.")
