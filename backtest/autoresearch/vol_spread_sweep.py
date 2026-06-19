"""
C14 BATCH 6: f9_vol_mult + ribbon_spread_min_cents sweep.

f9_vol_mult: production=0.7 (ratified at v11 from 1.3 too-strict).
  Higher = more confirmation required = fewer entries = higher quality?
  C15 note: wick constants non-monotone (tighter -> MORE trades). Test vol too.

ribbon_spread_min_cents: production=30 cents (gap between fast and slow EMA).
  Tighter spread = entry before ribbon fully opens. Higher = wait for conviction.

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


def _anchor_check(trades, j_winners, base_by_date):
    ok = True
    for d in sorted(j_winners):
        base_p = base_by_date.get(d, 0.0)
        cand_p = sum(t.dollar_pnl for t in trades if _date(t) == d)
        if base_p > 0 and cand_p < base_p * 0.90:
            ok = False
    return ok


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _per_trade_wf(is_delta, n_is, oos_delta, n_oos):
    if is_delta == 0 or n_oos == 0 or n_is == 0:
        return 0.0
    return (oos_delta / n_oos) / (is_delta / n_is)


if __name__ == "__main__":
    print("=" * 100)
    print("C14 BATCH 6: f9_vol_mult AND ribbon_spread_min_cents SWEEP")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n[0] Loading BASELINE (f9=0.7, spread=30c)...")
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

    # ============================================================
    # PART 1: f9_vol_mult sweep
    # ============================================================
    print("\n" + "=" * 100)
    print("PART 1: f9_vol_mult sweep [0.3, 0.5, 0.7(baseline), 1.0, 1.3]")
    print("Note: was 1.3 at v11 (too strict); dropped to 0.7. Testing if sweet spot exists.")
    print(f"\n  {'f9_vol':>8}  {'IS_n':>5}  {'IS_pnl':>9}  {'IS_delta':>9}  {'OOS_n':>5}  {'OOS_pnl':>9}  {'OOS_delta':>10}  {'WF_norm':>8}  {'anchor':>7}  Verdict")
    print("  " + "-" * 88)

    f9_results = []
    for vol in [0.3, 0.5, 0.7, 1.0, 1.3]:
        ovr = {"filter_9_vol_multiplier": vol}
        is_r = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                            params_overrides=ovr, **BASE)
        oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                             params_overrides=ovr, **BASE)
        is_p = _pnl(is_r.trades)
        oos_p = _pnl(oos_r.trades)
        is_d = is_p - base_is_pnl
        oos_d = oos_p - base_oos_pnl
        wf = _per_trade_wf(is_d, len(base_is.trades), oos_d, len(base_oos.trades))
        anchor = _anchor_check(is_r.trades, J_WINNERS, base_by_date)
        verdict = "PASS" if (oos_d > 0 and wf >= 0.70 and anchor) else ("OOS+" if oos_d > 0 else "FAIL")
        baseline_tag = " <-- baseline" if vol == 0.7 else ""
        print(f"  {vol:>8.1f}  {len(is_r.trades):>5}  {is_p:>+9.0f}  {is_d:>+9.0f}  "
              f"{len(oos_r.trades):>5}  {oos_p:>+9.0f}  {oos_d:>+10.0f}  {wf:>8.3f}  "
              f"{'OK' if anchor else 'FAIL':>7}  {verdict}{baseline_tag}")
        f9_results.append((vol, is_d, oos_d, wf, anchor, verdict))

    # ============================================================
    # PART 2: ribbon_spread_min_cents sweep
    # ============================================================
    print("\n" + "=" * 100)
    print("PART 2: ribbon_spread_min_cents sweep [10, 20, 30(baseline), 40, 50]")
    print("Note: tighter spread = earlier entry; wider = more confirmation.")
    print(f"\n  {'spread_c':>9}  {'IS_n':>5}  {'IS_pnl':>9}  {'IS_delta':>9}  {'OOS_n':>5}  {'OOS_pnl':>9}  {'OOS_delta':>10}  {'WF_norm':>8}  {'anchor':>7}  Verdict")
    print("  " + "-" * 88)

    spread_results = []
    for spread in [10, 20, 30, 40, 50]:
        ovr = {"ribbon_spread_min_cents": spread}
        is_r = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                            params_overrides=ovr, **BASE)
        oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                             params_overrides=ovr, **BASE)
        is_p = _pnl(is_r.trades)
        oos_p = _pnl(oos_r.trades)
        is_d = is_p - base_is_pnl
        oos_d = oos_p - base_oos_pnl
        wf = _per_trade_wf(is_d, len(base_is.trades), oos_d, len(base_oos.trades))
        anchor = _anchor_check(is_r.trades, J_WINNERS, base_by_date)
        verdict = "PASS" if (oos_d > 0 and wf >= 0.70 and anchor) else ("OOS+" if oos_d > 0 else "FAIL")
        baseline_tag = " <-- baseline" if spread == 30 else ""
        print(f"  {spread:>9}  {len(is_r.trades):>5}  {is_p:>+9.0f}  {is_d:>+9.0f}  "
              f"{len(oos_r.trades):>5}  {oos_p:>+9.0f}  {oos_d:>+10.0f}  {wf:>8.3f}  "
              f"{'OK' if anchor else 'FAIL':>7}  {verdict}{baseline_tag}")
        spread_results.append((spread, is_d, oos_d, wf, anchor, verdict))

    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n" + "=" * 100)
    print("SUMMARY")
    f9_pass = [r for r in f9_results if r[5] == "PASS"]
    spread_pass = [r for r in spread_results if r[5] == "PASS"]
    print(f"\n  f9_vol_mult PASS candidates: {len(f9_pass)}")
    for r in f9_pass:
        print(f"    vol={r[0]:.1f}: IS_delta={r[1]:+.0f} OOS_delta={r[2]:+.0f} WF={r[3]:.3f}")
    print(f"\n  ribbon_spread_min_cents PASS candidates: {len(spread_pass)}")
    for r in spread_pass:
        print(f"    spread={r[0]}c: IS_delta={r[1]:+.0f} OOS_delta={r[2]:+.0f} WF={r[3]:.3f}")

    if f9_pass:
        best_f9 = max(f9_pass, key=lambda r: r[2])
        print(f"\n  BEST f9_vol_mult: {best_f9[0]:.1f} (OOS delta={best_f9[2]:+.0f})")
    if spread_pass:
        best_sp = max(spread_pass, key=lambda r: r[2])
        print(f"  BEST ribbon_spread: {best_sp[0]}c (OOS delta={best_sp[2]:+.0f})")
    if not f9_pass and not spread_pass:
        print("\n  No PASS candidates for either knob. Production defaults confirmed.")

    print("\nANALYSIS COMPLETE.")
