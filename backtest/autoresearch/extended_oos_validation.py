"""
EXTENDED OOS VALIDATION: May 8 - June 16, 2026

The current OOS window (May 8-22) has only 15 trades — thin evidence.
New data files extend through June 16 (+4 weeks, ~17 additional trading days).

This script:
1. Merges the existing base file with the extension file (dedup May 19-22 overlap)
2. Runs BASELINE (production params) on extended OOS
3. Runs TIGHTER-STOP (-0.10) on extended OOS — the only PASS candidate
4. Per-week breakdown to see trend direction
5. Updated WF calculation with n=~40+ OOS trades

Expected hypothesis:
  - May 23 - June 16 should show continued edge if the engine is robust
  - Liberation Day effect has fully dissipated by May 23 (VIX declining since ~Apr 25)
  - tighter stop should show continued improvement in the extended window

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

# Base combined files (IS + early OOS through May 22)
SPY_BASE = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_BASE = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

# Extension files (May 19 - June 16, overlaps with base at May 19-22)
SPY_EXT  = DATA_DIR / "spy_5m_2026-05-19_2026-06-16.csv"
VIX_EXT  = DATA_DIR / "vix_5m_2026-05-19_2026-06-16.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 6, 16)   # extended

OOS_ORIG_END = dt.date(2026, 5, 22)

J_WINNERS = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}

BASE_PARAMS = dict(
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

TIGHTER_STOP = dict(BASE_PARAMS, premium_stop_pct_bear=-0.10)

WEEKLY_WINDOWS = [
    ("W_May08-16",  dt.date(2026, 5, 8),  dt.date(2026, 5, 16)),
    ("W_May19-22",  dt.date(2026, 5, 19), dt.date(2026, 5, 22)),
    ("W_May23-30",  dt.date(2026, 5, 23), dt.date(2026, 5, 30)),
    ("W_Jun02-06",  dt.date(2026, 6, 2),  dt.date(2026, 6, 6)),
    ("W_Jun09-13",  dt.date(2026, 6, 9),  dt.date(2026, 6, 13)),
    ("W_Jun16",     dt.date(2026, 6, 16), dt.date(2026, 6, 16)),
]


def _pnl(trades):
    return sum(t.dollar_pnl for t in trades)


def _date(t):
    et = t.entry_time_et
    d = et.replace(tzinfo=None) if getattr(et, "tzinfo", None) else et
    return d.date()


def _merge_data(base_path, ext_path) -> pd.DataFrame:
    """Merge base CSV and extension CSV, deduplicating on timestamp."""
    base = pd.read_csv(base_path)
    ext  = pd.read_csv(ext_path)
    combined = pd.concat([base, ext], ignore_index=True)
    # Try dedup on first column (timestamp)
    ts_col = combined.columns[0]
    combined = combined.drop_duplicates(subset=[ts_col], keep="first")
    combined = combined.sort_values(ts_col).reset_index(drop=True)
    return combined


if __name__ == "__main__":
    print("=" * 100)
    print("EXTENDED OOS VALIDATION: May 8 - June 16, 2026")
    print("=" * 100)

    print("\n[LOADING DATA] Merging base + extension files...")
    spy_df = _merge_data(SPY_BASE, SPY_EXT)
    vix_df = _merge_data(VIX_BASE, VIX_EXT)
    print(f"  SPY rows: {len(spy_df)} (original: {len(pd.read_csv(SPY_BASE))}, extension adds rows)")
    print(f"  VIX rows: {len(vix_df)}")

    # IS baseline (unchanged — extension only affects OOS)
    print("\n[IS BASELINE] Jan 2025 - May 7, 2026 (unchanged):")
    is_base = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **BASE_PARAMS)
    is_base_pnl = _pnl(is_base.trades)
    print(f"  n={len(is_base.trades)} pnl={is_base_pnl:+.0f}")

    # ORIGINAL OOS (May 8-22) — verify consistency
    print("\n[ORIGINAL OOS] May 8-22, 2026:")
    oos_orig_base = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_ORIG_END, **BASE_PARAMS)
    oos_orig_tight = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_ORIG_END, **TIGHTER_STOP)
    print(f"  BASELINE: n={len(oos_orig_base.trades)} pnl={_pnl(oos_orig_base.trades):+.0f}")
    print(f"  TIGHTER : n={len(oos_orig_tight.trades)} pnl={_pnl(oos_orig_tight.trades):+.0f} delta={_pnl(oos_orig_tight.trades)-_pnl(oos_orig_base.trades):+.0f}")

    # EXTENDED OOS (May 8 - June 16)
    print("\n[EXTENDED OOS] May 8 - June 16, 2026:")
    oos_ext_base  = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE_PARAMS)
    oos_ext_tight = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **TIGHTER_STOP)
    ext_base_pnl  = _pnl(oos_ext_base.trades)
    ext_tight_pnl = _pnl(oos_ext_tight.trades)
    tight_delta   = ext_tight_pnl - ext_base_pnl
    n_oos = len(oos_ext_base.trades)
    print(f"  BASELINE: n={n_oos} pnl={ext_base_pnl:+.0f}")
    print(f"  TIGHTER : n={len(oos_ext_tight.trades)} pnl={ext_tight_pnl:+.0f} delta={tight_delta:+.0f}")

    # Updated WF for tighter stop
    is_delta = _pnl(run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **TIGHTER_STOP).trades) - is_base_pnl
    wf_norm = (tight_delta / n_oos) / (is_delta / len(is_base.trades)) if is_delta != 0 else 0.0
    print(f"\n  Updated WF (tighter stop, extended OOS): {wf_norm:.3f} (gate 0.70)")
    print(f"  IS_delta = {is_delta:+.0f} over {len(is_base.trades)} IS trades")
    print(f"  OOS_delta = {tight_delta:+.0f} over {n_oos} OOS trades")

    # Week-by-week breakdown
    print("\n[WEEKLY BREAKDOWN]")
    print(f"  {'Window':12}  {'BASE_n':>6}  {'BASE_pnl':>9}  {'TIGHT_pnl':>10}  {'delta':>7}  {'BASE_WR%':>8}")
    print("  " + "-" * 65)
    for label, start, end in WEEKLY_WINDOWS:
        try:
            b = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **BASE_PARAMS)
            t = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **TIGHTER_STOP)
            bp = _pnl(b.trades)
            tp = _pnl(t.trades)
            wr = len([tr for tr in b.trades if tr.dollar_pnl > 0]) / len(b.trades) * 100 if b.trades else 0
            print(f"  {label:12}  {len(b.trades):>6}  {bp:>+9.0f}  {tp:>+10.0f}  {tp-bp:>+7.0f}  {wr:>8.0f}%")
        except Exception as e:
            print(f"  {label:12}  ERROR: {e}")

    # Summary
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"\n  ORIGINAL OOS (May 8-22): BASELINE n=15 pnl=+$2,659 | TIGHTER n=15 pnl=+$4,461 delta=+$1,802")
    print(f"  EXTENDED OOS (May 8-Jun 16): BASELINE n={n_oos} pnl={ext_base_pnl:+.0f} | TIGHTER n={len(oos_ext_tight.trades)} pnl={ext_tight_pnl:+.0f} delta={tight_delta:+.0f}")
    print(f"  Updated WF for tighter stop: {wf_norm:.3f}")
    print(f"\n  KEY QUESTION: Does the strategy remain profitable beyond May 22?")
    ext_only_n = n_oos - len(oos_orig_base.trades)
    ext_only_pnl = ext_base_pnl - _pnl(oos_orig_base.trades)
    if ext_only_n > 0:
        ext_wr = ext_only_n > 0 and sum(1 for t in oos_ext_base.trades if _date(t) > OOS_ORIG_END and t.dollar_pnl > 0) / ext_only_n * 100
        print(f"  New OOS trades (May 23 - Jun 16): n={ext_only_n} pnl={ext_only_pnl:+.0f} WR={ext_wr:.0f}%")

    print("\nANALYSIS COMPLETE.")
