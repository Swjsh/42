"""
VIX_BEAR_THRESHOLD sweep — L111 wired but not swept.

Filter 8: vix_pass = vix_now > VIX_BEAR_THRESHOLD AND vix_direction == "rising"
Production: VIX_BEAR_THRESHOLD = 17.30

Lower threshold = more permissive (allow entries when VIX is lower)
Higher threshold = more selective (require elevated VIX baseline)

From CHANGELOG: "After fix: threshold=25.0 blocks 6 fewer OOS trades, confirming knob is live."
Expected: higher threshold = more OOS trades blocked (vix_now must exceed higher bar).

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


def _anchor_pnl(trades, dates):
    by_date = {}
    for t in trades:
        d = _date(t)
        by_date[d] = by_date.get(d, 0.0) + t.dollar_pnl
    return {d: by_date.get(d, 0.0) for d in dates}


def _anchor_ok(trades, j_winners, base_by_date):
    ap = _anchor_pnl(trades, j_winners)
    for d in j_winners:
        base_p = base_by_date.get(d, 0.0)
        cand_p = ap.get(d, 0.0)
        if base_p > 0 and cand_p < base_p * 0.90:
            return False
    return True


def _per_trade_wf(is_delta, n_is, oos_delta, n_oos):
    if is_delta == 0 or n_oos == 0 or n_is == 0:
        return 0.0
    return (oos_delta / n_oos) / (is_delta / n_is)


if __name__ == "__main__":
    print("=" * 90)
    print("VIX_BEAR_THRESHOLD SWEEP — L111 KNOB VALIDATION")
    print("=" * 90)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n[0] Loading BASELINE (threshold=17.30 production)...")
    base_is = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **BASE)
    base_oos = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)
    base_is_pnl = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    base_by_date = {}
    for t in base_is.trades:
        d = _date(t)
        base_by_date[d] = base_by_date.get(d, 0.0) + t.dollar_pnl
    print(f"  IS n={len(base_is.trades)} pnl={base_is_pnl:+.0f}")
    print(f"  OOS n={len(base_oos.trades)} pnl={base_oos_pnl:+.0f}")

    THRESHOLDS = [10.0, 14.0, 15.5, 17.30, 18.5, 20.0, 22.0, 25.0]

    print(f"\n  {'threshold':>10}  {'IS_n':>5}  {'IS_pnl':>9}  {'IS_delta':>9}  "
          f"{'OOS_n':>5}  {'OOS_pnl':>9}  {'OOS_delta':>10}  {'WF_norm':>8}  {'anchor':>7}  Verdict")
    print("  " + "-" * 90)

    results = []
    for thr in THRESHOLDS:
        ovr = {"vix_bear_threshold": thr}
        is_r = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                            params_overrides=ovr, **BASE)
        oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                             params_overrides=ovr, **BASE)
        is_p = _pnl(is_r.trades)
        oos_p = _pnl(oos_r.trades)
        is_d = is_p - base_is_pnl
        oos_d = oos_p - base_oos_pnl
        wf = _per_trade_wf(is_d, len(base_is.trades), oos_d, len(base_oos.trades))
        anchor = _anchor_ok(is_r.trades, J_WINNERS, base_by_date)
        verdict = "PASS" if (oos_d > 0 and wf >= 0.70 and anchor) else (
            "OOS+" if oos_d > 0 else ("BASELINE" if is_d == 0 and oos_d == 0 else "FAIL"))
        baseline_tag = " <-- production" if thr == 17.30 else ""
        print(f"  {thr:>10.2f}  {len(is_r.trades):>5}  {is_p:>+9.0f}  {is_d:>+9.0f}  "
              f"{len(oos_r.trades):>5}  {oos_p:>+9.0f}  {oos_d:>+10.0f}  {wf:>8.3f}  "
              f"{'OK' if anchor else 'FAIL':>7}  {verdict}{baseline_tag}")
        results.append((thr, len(is_r.trades), is_p, is_d, len(oos_r.trades), oos_p, oos_d, wf, anchor, verdict))

    print("\n" + "=" * 90)
    print("ANCHOR DETAIL (J winner days at each threshold)")
    print(f"\n  {'threshold':>10}  {'4/29 IS':>10}  {'5/01 IS':>10}  {'5/04 IS':>10}  {'5/04 pnl':>10}")
    print("  " + "-" * 56)
    for thr in THRESHOLDS:
        ovr = {"vix_bear_threshold": thr}
        is_r = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                            params_overrides=ovr, **BASE)
        by_date = {}
        for t in is_r.trades:
            d = _date(t)
            by_date[d] = by_date.get(d, 0.0) + t.dollar_pnl
        p429 = by_date.get(dt.date(2026, 4, 29), 0.0)
        p501 = by_date.get(dt.date(2026, 5, 1), 0.0)
        p504 = by_date.get(dt.date(2026, 5, 4), 0.0)
        baseline_tag = " <--" if thr == 17.30 else ""
        print(f"  {thr:>10.2f}  {p429:>+10.0f}  {p501:>+10.0f}  {p504:>+10.0f}{baseline_tag}")

    print("\n" + "=" * 90)
    print("VERDICT SUMMARY")
    pass_results = [(thr, is_d, oos_d, wf) for thr, _, _, is_d, _, _, oos_d, wf, anchor, verdict in results if verdict == "PASS"]
    if pass_results:
        print(f"\n  PASS candidates:")
        for thr, is_d, oos_d, wf in pass_results:
            print(f"    threshold={thr:.2f}: IS_delta={is_d:+.0f} OOS_delta={oos_d:+.0f} WF={wf:.3f}")
        best = max(pass_results, key=lambda r: r[2])
        print(f"\n  BEST: threshold={best[0]:.2f} (OOS delta={best[2]:+.0f})")
    else:
        print("\n  No PASS candidates. Production threshold=17.30 confirmed.")
        # Show if OOS+ candidates exist for conditional application
        oos_pos = [(thr, is_d, oos_d, wf) for thr, _, _, is_d, _, _, oos_d, wf, anchor, verdict in results
                   if oos_d > 0 and (thr, is_d, oos_d, wf) not in [(r[0],r[1],r[2],r[3]) for r in pass_results]]
        if oos_pos:
            print(f"\n  OOS-positive but WF<0.70 (insufficient evidence):")
            for thr, is_d, oos_d, wf in oos_pos:
                print(f"    threshold={thr:.2f}: IS_delta={is_d:+.0f} OOS_delta={oos_d:+.0f} WF={wf:.3f}")

    print("\nANALYSIS COMPLETE.")
