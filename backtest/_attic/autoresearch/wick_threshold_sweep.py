"""
C14 BATCH 7: Wick threshold parameter sweep (3 independent 1D sweeps).

WICK_MIN_PCT_OF_RANGE = 0.50  (wick >= 50% of bar range)
WICK_MIN_DOLLARS = 0.15       (wick >= $0.15 absolute)
WICK_CLOSE_TOLERANCE = 0.10   (close within $0.10 of open = small body)

C15 finding: "wick constants are non-monotone (tighter wick -> MORE trades via entry-slot freeing)"
Mechanism: fewer bars qualify as wick rejections -> quality-lock state changes -> different entries allowed.

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

IS_START = dt.date(2025, 1, 2)
IS_END   = dt.date(2026, 5, 7)
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


def _anchor_ok(trades, j_winners, base_by_date):
    by_date = {}
    for t in trades:
        d = _date(t)
        by_date[d] = by_date.get(d, 0.0) + t.dollar_pnl
    for d in j_winners:
        base_p = base_by_date.get(d, 0.0)
        cand_p = by_date.get(d, 0.0)
        if base_p > 0 and cand_p < base_p * 0.90:
            return False
    return True


def _per_trade_wf(is_delta, n_is, oos_delta, n_oos):
    if is_delta == 0 or n_oos == 0 or n_is == 0:
        return 0.0
    return (oos_delta / n_oos) / (is_delta / n_is)


def _sweep_1d(spy_df, vix_df, param_key, values, baseline_value, base_is_pnl, base_oos_pnl,
              n_is, n_oos, base_by_date, label_width=22):
    print(f"\n  {param_key} sweep (baseline={baseline_value})")
    header = (f"  {'value':>12}  {'IS_n':>5}  {'IS_pnl':>9}  {'IS_delta':>9}  "
              f"{'OOS_n':>5}  {'OOS_pnl':>9}  {'OOS_delta':>10}  {'WF_norm':>8}  {'anchor':>7}  Verdict")
    print(header)
    print("  " + "-" * 88)
    results = []
    for val in values:
        ovr = {param_key: val}
        is_r = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                            params_overrides=ovr, **BASE)
        oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                             params_overrides=ovr, **BASE)
        is_p = _pnl(is_r.trades)
        oos_p = _pnl(oos_r.trades)
        is_d = is_p - base_is_pnl
        oos_d = oos_p - base_oos_pnl
        wf = _per_trade_wf(is_d, n_is, oos_d, n_oos)
        anchor = _anchor_ok(is_r.trades, J_WINNERS, base_by_date)
        verdict = "PASS" if (oos_d > 0 and wf >= 0.70 and anchor) else ("OOS+" if oos_d > 0 else "FAIL")
        baseline_tag = " <-- prod" if val == baseline_value else ""
        print(f"  {val:>12.3f}  {len(is_r.trades):>5}  {is_p:>+9.0f}  {is_d:>+9.0f}  "
              f"{len(oos_r.trades):>5}  {oos_p:>+9.0f}  {oos_d:>+10.0f}  {wf:>8.3f}  "
              f"{'OK' if anchor else 'FAIL':>7}  {verdict}{baseline_tag}")
        results.append((val, len(is_r.trades), is_p, is_d, len(oos_r.trades), oos_p, oos_d, wf, anchor, verdict))
    return results


if __name__ == "__main__":
    print("=" * 100)
    print("C14 BATCH 7: WICK THRESHOLD SWEEP (3 independent 1D sweeps)")
    print("Note: C15 finding — wick constants non-monotone (tighter -> more entries via quality-lock cascade)")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n[0] Loading BASELINE (WICK_MIN_PCT=0.50, WICK_MIN_DOLLARS=0.15, WICK_CLOSE_TOL=0.10)...")
    base_is = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **BASE)
    base_oos = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)
    base_is_pnl = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    base_by_date = {}
    for t in base_is.trades:
        d = _date(t)
        base_by_date[d] = base_by_date.get(d, 0.0) + t.dollar_pnl
    n_is = len(base_is.trades)
    n_oos = len(base_oos.trades)
    print(f"  IS n={n_is} pnl={base_is_pnl:+.0f}")
    print(f"  OOS n={n_oos} pnl={base_oos_pnl:+.0f}")

    print("\n" + "=" * 100)
    print("SWEEP 1: wick_min_pct_of_range (production=0.50)")
    r1 = _sweep_1d(spy_df, vix_df, "wick_min_pct_of_range",
                   [0.30, 0.40, 0.50, 0.60, 0.70, 0.80],
                   baseline_value=0.50,
                   base_is_pnl=base_is_pnl, base_oos_pnl=base_oos_pnl,
                   n_is=n_is, n_oos=n_oos, base_by_date=base_by_date)

    print("\n" + "=" * 100)
    print("SWEEP 2: wick_min_dollars (production=0.15)")
    r2 = _sweep_1d(spy_df, vix_df, "wick_min_dollars",
                   [0.05, 0.10, 0.15, 0.20, 0.30, 0.50],
                   baseline_value=0.15,
                   base_is_pnl=base_is_pnl, base_oos_pnl=base_oos_pnl,
                   n_is=n_is, n_oos=n_oos, base_by_date=base_by_date)

    print("\n" + "=" * 100)
    print("SWEEP 3: wick_close_tolerance (production=0.10)")
    r3 = _sweep_1d(spy_df, vix_df, "wick_close_tolerance",
                   [0.05, 0.10, 0.15, 0.20, 0.30, 0.50],
                   baseline_value=0.10,
                   base_is_pnl=base_is_pnl, base_oos_pnl=base_oos_pnl,
                   n_is=n_is, n_oos=n_oos, base_by_date=base_by_date)

    print("\n" + "=" * 100)
    print("SUMMARY")
    all_pass = [(pname, val, is_d, oos_d, wf)
                for pname, results in [("wick_min_pct_of_range", r1),
                                        ("wick_min_dollars", r2),
                                        ("wick_close_tolerance", r3)]
                for val, _, _, is_d, _, _, oos_d, wf, anchor, verdict in results
                if verdict == "PASS"]
    if all_pass:
        print(f"\n  PASS candidates ({len(all_pass)} total):")
        for pname, val, is_d, oos_d, wf in all_pass:
            print(f"    {pname}={val}: IS_delta={is_d:+.0f} OOS_delta={oos_d:+.0f} WF={wf:.3f}")
        best = max(all_pass, key=lambda r: r[3])
        print(f"\n  BEST: {best[0]}={best[1]} (OOS_delta={best[3]:+.0f})")
    else:
        print("\n  No PASS candidates. Production wick thresholds confirmed.")
        oos_pos = [(pname, val, is_d, oos_d, wf)
                   for pname, results in [("wick_min_pct_of_range", r1),
                                           ("wick_min_dollars", r2),
                                           ("wick_close_tolerance", r3)]
                   for val, _, _, is_d, _, _, oos_d, wf, anchor, verdict in results
                   if oos_d > 0]
        if oos_pos:
            print(f"\n  OOS-positive but insufficient WF (informational):")
            for pname, val, is_d, oos_d, wf in sorted(oos_pos, key=lambda r: r[3], reverse=True)[:5]:
                print(f"    {pname}={val}: IS_delta={is_d:+.0f} OOS_delta={oos_d:+.0f} WF={wf:.3f}")

    print("\nANALYSIS COMPLETE.")
