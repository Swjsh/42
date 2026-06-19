"""
NEGATIVE ROLLING WF WINDOWS DEEP DIVE

From rolling_walk_forward.py, 4 windows were OOS-negative:
  Nov-25: OOS n=10 pnl=-1089
  Jan-26: OOS n=24 pnl=-624
  Mar-26: OOS n=15 pnl=-3004
  Apr-26: OOS n=22 pnl=-6189 (Liberation Day -- understood, VIX escalating)

This script focuses on the 3 NON-LIBERATION-DAY negatives to find unifying patterns.

For each negative window, runs backtest and characterizes:
  - VIX bucket distribution (where do losses cluster?)
  - Trigger/quality tier breakdown
  - Time of day
  - Win rate by sub-group
  - Compares to the positive windows (Jul-25, Aug-25, Sep-25, Oct-25, Dec-25, Feb-26, May-26)

Goal: identify if there's a mechanical gate that could avoid these losses without harming positive windows.

Security: read-only. No Alpaca calls. Free-tier only.
"""
from __future__ import annotations
import sys
import pathlib
import datetime as dt
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE  = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE  = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

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

NEGATIVE_WINDOWS = [
    ("Nov-25", dt.date(2025, 11, 3), dt.date(2025, 11, 28)),
    ("Jan-26", dt.date(2026, 1, 2),  dt.date(2026, 1, 30)),
    ("Mar-26", dt.date(2026, 3, 2),  dt.date(2026, 3, 31)),
]

POSITIVE_WINDOWS = [
    ("Jul-25", dt.date(2025, 7, 1),  dt.date(2025, 7, 31)),
    ("Sep-25", dt.date(2025, 9, 2),  dt.date(2025, 9, 30)),
    ("Feb-26", dt.date(2026, 2, 2),  dt.date(2026, 2, 27)),
    ("May-26", dt.date(2026, 5, 1),  dt.date(2026, 5, 22)),
]


def _quality(triggers: list) -> str:
    tf = set(triggers or [])
    has_conf = "confluence" in tf
    has_rf   = "ribbon_flip_bearish" in tf or "ribbon_flip_bullish" in tf
    has_lvl  = "level_rejection" in tf or "level_reclaim" in tf
    has_seq  = "sequence_rejection" in tf
    has_tl   = "trendline_rejection" in tf
    n        = len(tf)
    if (has_conf and has_rf) or n >= 3:
        return "SUPER"
    if has_conf or has_seq:
        return "ELITE"
    if has_lvl:
        return "LEVEL"
    if has_tl:
        return "TRENDLINE"
    return "OTHER"


def _vix_bucket(vix: float) -> str:
    if vix < 15:
        return "<15"
    if vix < 17:
        return "15-17"
    if vix < 20:
        return "17-20"
    if vix < 25:
        return "20-25"
    if vix < 35:
        return "25-35"
    return "35+"


def _tod(entry_time) -> str:
    h = entry_time.hour
    if h < 11:
        return "morning (<11)"
    if h < 13:
        return "midday (11-13)"
    return "afternoon (13+)"


def _analyze(trades, label: str):
    if not trades:
        print(f"  {label}: NO TRADES")
        return

    total_pnl = sum(t.dollar_pnl for t in trades)
    wins = [t for t in trades if t.dollar_pnl > 0]
    losses = [t for t in trades if t.dollar_pnl <= 0]
    wr = len(wins) / len(trades) * 100

    print(f"\n  [{label}] n={len(trades)} pnl={total_pnl:+.0f} WR={wr:.0f}%")

    # VIX bucket
    by_vix = defaultdict(list)
    for t in trades:
        by_vix[_vix_bucket(getattr(t, 'entry_vix', 0))].append(t)

    print(f"    VIX buckets:")
    for bucket in ["<15", "15-17", "17-20", "20-25", "25-35", "35+"]:
        ts = by_vix[bucket]
        if ts:
            bp = sum(t.dollar_pnl for t in ts)
            bw = len([t for t in ts if t.dollar_pnl > 0])
            bwr = bw / len(ts) * 100
            print(f"      {bucket:8}: n={len(ts):3} pnl={bp:+7.0f} WR={bwr:.0f}%")

    # Quality tier
    by_qual = defaultdict(list)
    for t in trades:
        q = _quality(getattr(t, 'triggers_fired', []))
        by_qual[q].append(t)

    print(f"    Quality tiers:")
    for q in ["SUPER", "ELITE", "LEVEL", "TRENDLINE", "OTHER"]:
        ts = by_qual[q]
        if ts:
            qp = sum(t.dollar_pnl for t in ts)
            qw = len([t for t in ts if t.dollar_pnl > 0])
            qwr = qw / len(ts) * 100
            print(f"      {q:12}: n={len(ts):3} pnl={qp:+7.0f} WR={qwr:.0f}%")


if __name__ == "__main__":
    print("=" * 100)
    print("NEGATIVE ROLLING WF WINDOWS DEEP DIVE")
    print("=" * 100)

    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)

    print("\n" + "=" * 60)
    print("NEGATIVE WINDOWS (non-Liberation-Day losses)")
    print("=" * 60)

    neg_all_trades = []
    for label, start, end in NEGATIVE_WINDOWS:
        result = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **BASE)
        _analyze(result.trades, f"OOS-NEG {label} {start} to {end}")
        neg_all_trades.extend(result.trades)

    print("\n--- POOLED NEGATIVE (3 windows combined) ---")
    _analyze(neg_all_trades, "ALL 3 NEG WINDOWS POOLED")

    print("\n" + "=" * 60)
    print("POSITIVE WINDOWS (control group)")
    print("=" * 60)

    pos_all_trades = []
    for label, start, end in POSITIVE_WINDOWS:
        result = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **BASE)
        _analyze(result.trades, f"OOS-POS {label} {start} to {end}")
        pos_all_trades.extend(result.trades)

    print("\n--- POOLED POSITIVE (4 windows combined) ---")
    _analyze(pos_all_trades, "ALL 4 POS WINDOWS POOLED")

    # Cross-window comparison
    print("\n" + "=" * 100)
    print("CROSS-WINDOW COMPARISON: NEG vs POS VIX BUCKET DISTRIBUTION")
    print("=" * 100)

    neg_by_vix = defaultdict(list)
    for t in neg_all_trades:
        neg_by_vix[_vix_bucket(getattr(t, 'entry_vix', 0))].append(t)

    pos_by_vix = defaultdict(list)
    for t in pos_all_trades:
        pos_by_vix[_vix_bucket(getattr(t, 'entry_vix', 0))].append(t)

    print(f"\n  {'VIX':8}  {'NEG_n':>6}  {'NEG_WR%':>8}  {'NEG_$/trade':>12}  | "
          f"{'POS_n':>6}  {'POS_WR%':>8}  {'POS_$/trade':>12}")
    print("  " + "-" * 75)
    for bucket in ["<15", "15-17", "17-20", "20-25", "25-35", "35+"]:
        nt = neg_by_vix[bucket]
        pt = pos_by_vix[bucket]
        if nt or pt:
            nwr = len([t for t in nt if t.dollar_pnl > 0]) / len(nt) * 100 if nt else 0
            pwr = len([t for t in pt if t.dollar_pnl > 0]) / len(pt) * 100 if pt else 0
            nppt = sum(t.dollar_pnl for t in nt) / len(nt) if nt else 0
            pppt = sum(t.dollar_pnl for t in pt) / len(pt) if pt else 0
            print(f"  {bucket:8}  {len(nt):>6}  {nwr:>8.0f}%  {nppt:>+12.0f}  | "
                  f"{len(pt):>6}  {pwr:>8.0f}%  {pppt:>+12.0f}")

    print("\n" + "=" * 100)
    print("CROSS-WINDOW COMPARISON: NEG vs POS QUALITY TIER")
    print("=" * 100)

    neg_by_q = defaultdict(list)
    for t in neg_all_trades:
        neg_by_q[_quality(getattr(t, 'triggers_fired', []))].append(t)

    pos_by_q = defaultdict(list)
    for t in pos_all_trades:
        pos_by_q[_quality(getattr(t, 'triggers_fired', []))].append(t)

    print(f"\n  {'Quality':12}  {'NEG_n':>6}  {'NEG_WR%':>8}  {'NEG_$/trade':>12}  | "
          f"{'POS_n':>6}  {'POS_WR%':>8}  {'POS_$/trade':>12}")
    print("  " + "-" * 75)
    for q in ["SUPER", "ELITE", "LEVEL", "TRENDLINE", "OTHER"]:
        nt = neg_by_q[q]
        pt = pos_by_q[q]
        if nt or pt:
            nwr = len([t for t in nt if t.dollar_pnl > 0]) / len(nt) * 100 if nt else 0
            pwr = len([t for t in pt if t.dollar_pnl > 0]) / len(pt) * 100 if pt else 0
            nppt = sum(t.dollar_pnl for t in nt) / len(nt) if nt else 0
            pppt = sum(t.dollar_pnl for t in pt) / len(pt) if pt else 0
            print(f"  {q:12}  {len(nt):>6}  {nwr:>8.0f}%  {nppt:>+12.0f}  | "
                  f"{len(pt):>6}  {pwr:>8.0f}%  {pppt:>+12.0f}")

    print("\nANALYSIS COMPLETE.")
