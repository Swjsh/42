"""
C14 FINAL BATCH: ribbon_flip_lookback_bars / vix_rising_deadband / vix_hard_cap_bear

These are the 3 remaining un-swept constants in orchestrator._FILTER_CONST_MAP.

  ribbon_flip_lookback_bars (default=3): how many bars back the ribbon flip is detected.
    Larger = can enter further from the flip (more flexible).
    Smaller = must enter close to the flip (tighter recency).

  vix_rising_deadband (default=0.05): bar-to-bar VIX change < deadband is treated as "flat".
    Larger deadband = VIX must rise more sharply to trigger the "rising" classification.
    Tighter deadband = even tiny VIX bumps count as "rising".

  vix_hard_cap_bear (default=999 = off): block BEAR entries when VIX > cap.
    Tests whether blocking panic-regime entries (Liberation Day VIX=52) improves OOS.
    Expected: IS improves (removes Apr 2026 panic losses), OOS neutral (post-Apr May-OOS VIX was <=30).

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


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _anchor_ok(by_date, base_by_date):
    for d in J_WINNERS:
        bp = base_by_date.get(d, 0.0)
        cp = by_date.get(d, 0.0)
        if bp > 0 and cp < bp * 0.90:
            return False
    return True


def _by_date(trades):
    result = {}
    for t in trades:
        d = _date(t)
        result[d] = result.get(d, 0.0) + t.dollar_pnl
    return result


def sweep(spy_df, vix_df, base_is, base_oos, base_is_pnl, base_oos_pnl, base_bd,
          key: str, label: str, values: list, prod_val):
    print(f"\n{'=' * 100}")
    print(f"SWEEP: {key} (production={prod_val})")
    print(f"  {label}")
    hdr = f"  {'value':>12}  {'IS_n':>6}  {'IS_pnl':>8}  {'IS_delta':>9}  "
    hdr += f"{'OOS_n':>5}  {'OOS_pnl':>8}  {'OOS_delta':>9}  {'WF_norm':>8}  {'anchor':>6}  Verdict"
    print(hdr)
    print("  " + "-" * 96)
    passes = []
    for v in values:
        is_r  = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                             params_overrides={key: v}, **BASE)
        oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                             params_overrides={key: v}, **BASE)
        is_pnl   = _pnl(is_r.trades)
        oos_pnl  = _pnl(oos_r.trades)
        n_is     = len(base_is.trades)
        n_oos    = len(base_oos.trades)
        is_d     = is_pnl - base_is_pnl
        oos_d    = oos_pnl - base_oos_pnl
        wf = (oos_d / n_oos) / (is_d / n_is) if is_d != 0 else 0.0
        bd       = _by_date(is_r.trades)
        anchor   = _anchor_ok(bd, base_bd)
        is_pass  = oos_d > 0 and wf >= 0.70 and anchor
        tag = "<-- prod" if v == prod_val else ""
        verdict  = "PASS" if is_pass else ("OOS+" if oos_d > 0 else "FAIL")
        print(f"  {str(v):>12}  {len(is_r.trades):>6}  {is_pnl:>+8.0f}  {is_d:>+9.0f}  "
              f"{len(oos_r.trades):>5}  {oos_pnl:>+8.0f}  {oos_d:>+9.0f}  "
              f"{wf:>8.3f}  {'OK' if anchor else 'FAIL':>6}  {verdict} {tag}")
        if is_pass:
            passes.append((v, is_d, oos_d, wf))
    return passes


if __name__ == "__main__":
    print("=" * 100)
    print("C14 FINAL BATCH: ribbon_flip_lookback_bars / vix_rising_deadband / vix_hard_cap_bear")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n[BASELINE]")
    base_is  = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **BASE)
    base_oos = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)
    base_is_pnl  = _pnl(base_is.trades)
    base_oos_pnl = _pnl(base_oos.trades)
    base_bd      = _by_date(base_is.trades)
    print(f"  IS n={len(base_is.trades)} pnl={base_is_pnl:+.0f}")
    print(f"  OOS n={len(base_oos.trades)} pnl={base_oos_pnl:+.0f}")

    all_passes = []

    p = sweep(spy_df, vix_df, base_is, base_oos, base_is_pnl, base_oos_pnl, base_bd,
              key="ribbon_flip_lookback_bars",
              label="How many bars back a ribbon flip counts as 'recent'. Larger = wider time window to enter after flip.",
              values=[1, 2, 3, 4, 5, 7, 10],
              prod_val=3)
    all_passes.extend(("ribbon_flip_lookback_bars", v, d_i, d_o, w) for v, d_i, d_o, w in p)

    p = sweep(spy_df, vix_df, base_is, base_oos, base_is_pnl, base_oos_pnl, base_bd,
              key="vix_rising_deadband",
              label="Minimum bar-to-bar VIX change classified as 'rising'. Below deadband = 'flat'. "
                    "Larger = suppress more VIX micro-noise.",
              values=[0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30],
              prod_val=0.05)
    all_passes.extend(("vix_rising_deadband", v, d_i, d_o, w) for v, d_i, d_o, w in p)

    p = sweep(spy_df, vix_df, base_is, base_oos, base_is_pnl, base_oos_pnl, base_bd,
              key="vix_hard_cap_bear",
              label="Block BEAR entries when VIX > cap. Default=999 (off). "
                    "Tests whether blocking Liberation Day panic (VIX~52) improves performance.",
              values=[30.0, 35.0, 40.0, 45.0, 50.0, 60.0, 999.0],
              prod_val=999.0)
    all_passes.extend(("vix_hard_cap_bear", v, d_i, d_o, w) for v, d_i, d_o, w in p)

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    if all_passes:
        print(f"\n  PASS candidates ({len(all_passes)} total):")
        for item in all_passes:
            print(f"    {item[0]}={item[1]}: IS_delta={item[2]:+.0f} OOS_delta={item[3]:+.0f} WF={item[4]:.3f}")
    else:
        print("\n  No PASS candidates. Production defaults confirmed for all 3 constants.")
        print("  C14 sweep campaign COMPLETE across all _FILTER_CONST_MAP keys.")

    print("\nANALYSIS COMPLETE.")
