"""
REMAINING C14 FILTER CONSTANT SWEEP

Sweeps filter constants that were wired in C14 but not yet evaluated:
  - confluence_tolerance_dollars (CONFLUENCE_TOLERANCE_DOLLARS = 0.30)
  - vol_baseline_bars (VOL_BASELINE_BARS = 20)
  - ribbon_flip_lookback_bars (RIBBON_FLIP_LOOKBACK_BARS = 3)
  - wick_min_pct_of_range (WICK_MIN_PCT_OF_RANGE = 0.50)
  - wick_min_dollars (WICK_MIN_DOLLARS = 0.15)
  - wick_close_tolerance (WICK_CLOSE_TOLERANCE = 0.10)

Security: read-only. No Alpaca calls. Free-tier only.
All pass through params_overrides (filter-const style, not direct kwargs).
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

# Production BASE — matches params.json exactly (same as C14 authoritative baseline)
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

SWEEPS = [
    {
        "key": "confluence_tolerance_dollars",
        "prod": 0.30,
        "values": [0.10, 0.20, 0.30, 0.40, 0.50, 0.75, 1.00],
        "label": "CONFLUENCE_TOLERANCE_DOLLARS (multi-day touch window)",
    },
    {
        "key": "vol_baseline_bars",
        "prod": 20,
        "values": [10, 15, 20, 25, 30, 40],
        "label": "VOL_BASELINE_BARS (volume SMA window)",
    },
    {
        "key": "ribbon_flip_lookback_bars",
        "prod": 3,
        "values": [1, 2, 3, 4, 5, 6],
        "label": "RIBBON_FLIP_LOOKBACK_BARS (ribbon flip lookback)",
    },
    {
        "key": "wick_min_pct_of_range",
        "prod": 0.50,
        "values": [0.25, 0.35, 0.40, 0.50, 0.60, 0.70],
        "label": "WICK_MIN_PCT_OF_RANGE (min wick % of bar range)",
    },
    {
        "key": "wick_min_dollars",
        "prod": 0.15,
        "values": [0.05, 0.10, 0.15, 0.20, 0.30, 0.40],
        "label": "WICK_MIN_DOLLARS (min wick size in $)",
    },
    {
        "key": "wick_close_tolerance",
        "prod": 0.10,
        "values": [0.00, 0.05, 0.10, 0.15, 0.20, 0.30],
        "label": "WICK_CLOSE_TOLERANCE (close leniency above level $)",
    },
]


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
    print("REMAINING C14 FILTER CONSTANT SWEEP")
    print("=" * 95)

    # Shared baseline
    is_base  = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **BASE)
    oos_base = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)
    is_bp  = _pnl(is_base.trades)
    oos_bp = _pnl(oos_base.trades)
    is_bd  = _by_date(is_base.trades)
    n_is   = len(is_base.trades)
    n_oos  = len(oos_base.trades)

    print(f"\n[BASELINE] IS n={n_is} pnl={is_bp:+.0f}  OOS n={n_oos} pnl={oos_bp:+.0f}")
    print()

    for sweep in SWEEPS:
        key  = sweep["key"]
        prod = sweep["prod"]
        vals = sweep["values"]

        print(f"{'=' * 95}")
        print(f"SWEEP: {sweep['label']}")
        print(f"{'=' * 95}")
        print(f"  {'value':>10}  {'IS_n':>5}  {'IS_delta':>9}  {'OOS_delta':>9}  {'WF':>7}  {'anchor':>7}  {'verdict'}")
        print("  " + "-" * 75)

        best_val = prod
        best_oos = 0.0
        best_verdict = "BASELINE"

        for v in vals:
            is_r  = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END,
                                 params_overrides={key: v}, **BASE)
            oos_r = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END,
                                 params_overrides={key: v}, **BASE)
            is_d  = _pnl(is_r.trades) - is_bp
            oos_d = _pnl(oos_r.trades) - oos_bp
            wf    = _wf(oos_d, n_oos, is_d, n_is)
            anc   = _anchor_ok(_by_date(is_r.trades), is_bd)
            tag   = " *PROD*" if v == prod else ""
            verd  = _verdict(oos_d, wf, anc)
            print(f"  {v:>10}  {len(is_r.trades):>5}  {is_d:>+9.0f}  {oos_d:>+9.0f}  {wf:>7.3f}  {'OK' if anc else 'FAIL':>7}  {verd}{tag}")
            if oos_d > best_oos and verd.startswith("PASS"):
                best_oos = oos_d
                best_val = v
                best_verdict = verd

        if best_val != prod:
            print(f"\n  -> IMPROVEMENT: {key}={best_val} (OOS_delta={best_oos:+.0f}) — run sub-window before ratifying")
        else:
            print(f"\n  -> Production default confirmed optimal or no PASS found")
        print()

    print("ANALYSIS COMPLETE.")
