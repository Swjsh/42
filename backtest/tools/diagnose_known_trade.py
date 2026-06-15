"""Diagnose why a known trade didn't fire in the backtest.

Usage:
    python tools/diagnose_known_trade.py 2026-05-04 10:25 10:35
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytz

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.orchestrator import run_backtest

REPO = Path(__file__).resolve().parents[1]


def main():
    if len(sys.argv) < 4:
        print("usage: python tools/diagnose_known_trade.py YYYY-MM-DD HH:MM HH:MM")
        return 1
    date_str = sys.argv[1]
    win_start = sys.argv[2]
    win_end = sys.argv[3]

    spy = pd.read_csv(REPO / "fixtures" / f"spy_5m_{date_str}_with_warmup.csv")
    vix = pd.read_csv(REPO / "fixtures" / f"vix_5m_{date_str}_with_warmup.csv")
    target = dt.date.fromisoformat(date_str)

    result = run_backtest(spy, vix, start_date=target, end_date=target)

    print(f"Bars evaluated: {result.metadata['bars_evaluated']}")
    print(f"Trades fired:   {result.metadata['trades_fired']}")
    print()

    win_start_t = dt.datetime.strptime(win_start, "%H:%M").time()
    win_end_t = dt.datetime.strptime(win_end, "%H:%M").time()

    print(f"Decisions in window {win_start} - {win_end} on {date_str}:")
    print("-" * 100)

    found_any = False
    for d in result.decisions:
        ts = pd.Timestamp(d["timestamp_et"])
        if ts.date() != target:
            continue
        if ts.time() < win_start_t or ts.time() > win_end_t:
            continue
        found_any = True
        print(
            f"  {ts.strftime('%H:%M')} spy={d['spy_close']:.2f} vix={d['vix']:.2f} "
            f"stack={d['ribbon_stack']:>5} spread={d['ribbon_spread_cents']:.1f}c "
            f"htf15={str(d['htf_15m_stack']):>5} score={d['bear_score']}/10 "
            f"blockers={d['blockers']} triggers={d['triggers_fired']} "
            f"reject_lvl={d['rejection_level']}"
        )
    if not found_any:
        print("  (no decisions logged in this window — bars may have been filtered by time/warmup)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
