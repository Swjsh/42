"""Robustness + micro-iteration sweep on v13b.

1. Sub-window stability: split 53 days in half, run v13b on each, compare.
2. Parameter micro-sweeps:
   - Premium stop: -8% / -10% / -12% / -15%
   - F9 vol threshold: 0.5x / 0.7x / 1.0x / 1.3x
   - Spread minimum: 30c / 40c / 50c
   - ELITE multiplier: qty=3 (no upsize) / 4 / 5 / 6 / 8

Goal: identify what generalizes vs what's tuned to specific window.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.orchestrator import run_backtest  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"


def summarize(trades):
    if not trades:
        return dict(n=0, wr=0, total=0, exp=0, wl=0, max_dd=0, worst=0)
    n = len(trades)
    wins = [t for t in trades if t.dollar_pnl > 0]
    losses = [t for t in trades if t.dollar_pnl < 0]
    avg_w = sum(t.dollar_pnl for t in wins) / max(1, len(wins))
    avg_l = sum(t.dollar_pnl for t in losses) / max(1, len(losses))
    total = sum(t.dollar_pnl for t in trades)

    def _naive(ts):
        if hasattr(ts, "tz_localize") and ts.tz is not None: return ts.tz_localize(None)
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None: return ts.replace(tzinfo=None)
        return ts
    cum, peak, max_dd = 0, 0, 0
    for t in sorted(trades, key=lambda x: _naive(x.entry_time_et)):
        cum += t.dollar_pnl
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    return dict(
        n=n, wr=len(wins)/n if n else 0,
        total=total, exp=total/n if n else 0,
        wl=abs(avg_w/avg_l) if avg_l else 0,
        max_dd=max_dd, worst=min(t.dollar_pnl for t in trades),
    )


def passes(s):
    return sum([s["n"] >= 20, s["wr"] >= 0.45, s["wl"] >= 1.5, s["exp"] > 0])


def main():
    spy = pd.read_csv(DATA / "spy_5m_2026-03-15_2026-05-07.csv")
    vix = pd.read_csv(DATA / "vix_5m_2026-03-15_2026-05-07.csv")
    full_start = dt.date(2026, 3, 15)
    full_end = dt.date(2026, 5, 7)
    half_split = dt.date(2026, 4, 11)  # ~midpoint

    print("\n" + "=" * 95)
    print("  STRESS TEST: Sub-Window Stability (does v13b hold across halves?)")
    print("=" * 95)
    for label, (s, e) in [
        ("Full 53d", (full_start, full_end)),
        ("First half 3/15-4/10", (full_start, half_split - dt.timedelta(days=1))),
        ("Second half 4/11-5/7", (half_split, full_end)),
    ]:
        r = run_backtest(spy, vix, start_date=s, end_date=e, use_real_fills=True)
        st = summarize(r.trades)
        print(f"  {label:<25}  {st['n']:<3}t  WR={st['wr']*100:.0f}%  "
              f"W/L={st['wl']:.2f}x  total ${st['total']:.0f}  "
              f"DD ${st['max_dd']:.0f}  worst ${st['worst']:.0f}  {passes(st)}/4")

    # Micro-sweep 1: premium stops
    print("\n" + "=" * 95)
    print("  MICRO-SWEEP 1: Premium Stop Tightness (default -10%)")
    print("=" * 95)
    for ps in [-0.08, -0.10, -0.12, -0.15]:
        r = run_backtest(spy, vix, start_date=full_start, end_date=full_end,
                         use_real_fills=True, premium_stop_pct=ps)
        st = summarize(r.trades)
        print(f"  stop={int(ps*100)}%  {st['n']:<3}t  WR={st['wr']*100:.0f}%  "
              f"W/L={st['wl']:.2f}x  total ${st['total']:.0f}  "
              f"DD ${st['max_dd']:.0f}  worst ${st['worst']:.0f}  {passes(st)}/4")

    # Micro-sweep 2: F9 volume threshold
    print("\n" + "=" * 95)
    print("  MICRO-SWEEP 2: Filter 9 Volume Threshold (default 0.7x)")
    print("=" * 95)
    for vol in [0.5, 0.7, 0.85, 1.0, 1.3]:
        r = run_backtest(spy, vix, start_date=full_start, end_date=full_end,
                         use_real_fills=True, f9_vol_mult=vol)
        st = summarize(r.trades)
        print(f"  f9_vol>={vol}x  {st['n']:<3}t  WR={st['wr']*100:.0f}%  "
              f"W/L={st['wl']:.2f}x  total ${st['total']:.0f}  "
              f"DD ${st['max_dd']:.0f}  worst ${st['worst']:.0f}  {passes(st)}/4")


if __name__ == "__main__":
    main()
