"""Tight-stop sweep — find SAFE-GROWTH configuration for $1k account.

Goal: minimize per-trade risk (max DD per trade < $150 = 15% of $1k account)
while staying profitable and capturing the big winners.

Tests combinations of:
  - Premium stop: -25%, -20%, -15%, -12%, -10%
  - Min triggers: 1 (more trades) vs 2 (fewer, higher quality)
  - All on ITM-2 strikes (held constant from v9 win)

Plus reports MAX SINGLE-TRADE LOSS for each config — the metric that matters
on a $1k account where one bad trade can wipe the day.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.orchestrator import run_backtest  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = REPO / "data"


PREMIUM_STOPS = [-0.33, -0.25, -0.20, -0.15, -0.12, -0.10]
TRIGGER_MODES = [(1, "1trig"), (2, "2trig")]


def summarize(trades):
    if not trades:
        return dict(n=0, wr=0, total=0, exp=0, avg_w=0, avg_l=0,
                    wl=0, max_dd=0, worst_trade=0, best_trade=0)
    n = len(trades)
    wins = [t for t in trades if t.dollar_pnl > 0]
    losses = [t for t in trades if t.dollar_pnl < 0]
    avg_w = sum(t.dollar_pnl for t in wins) / max(1, len(wins))
    avg_l = sum(t.dollar_pnl for t in losses) / max(1, len(losses))
    total = sum(t.dollar_pnl for t in trades)

    def _naive(ts):
        if hasattr(ts, "tz_localize") and ts.tz is not None:
            return ts.tz_localize(None)
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            return ts.replace(tzinfo=None)
        return ts
    cum, peak, max_dd = 0, 0, 0
    for t in sorted(trades, key=lambda t: _naive(t.entry_time_et)):
        cum += t.dollar_pnl
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    wr = len(wins) / n if n else 0
    wl = abs(avg_w / avg_l) if avg_l else 0
    return dict(
        n=n, wr=wr, total=total, exp=total / n if n else 0,
        avg_w=avg_w, avg_l=avg_l, wl=wl, max_dd=max_dd,
        worst_trade=min(t.dollar_pnl for t in trades),
        best_trade=max(t.dollar_pnl for t in trades),
    )


def main():
    spy = pd.read_csv(DATA_DIR / "spy_5m_2026-03-15_2026-05-07.csv")
    vix = pd.read_csv(DATA_DIR / "vix_5m_2026-03-15_2026-05-07.csv")
    start, end = dt.date(2026, 3, 15), dt.date(2026, 5, 7)

    print("\nSAFE-GROWTH SWEEP — what stop + trigger gives best risk-adjusted P&L?")
    print("Target: max single-trade loss < $150 for $1k account safety.")
    print(f"\n{'STOP':<6}{'TRIG':<6}{'N':<5}{'WR':<5}{'AvgW':<7}{'AvgL':<7}"
          f"{'W/L':<6}{'TOTAL':<9}{'EXP':<7}{'WORST':<8}{'MaxDD':<9}{'PASS'}")
    print("-" * 95)

    results = {}
    for stop in PREMIUM_STOPS:
        for trig, trig_label in TRIGGER_MODES:
            r = run_backtest(spy, vix, start_date=start, end_date=end,
                             use_real_fills=True, min_triggers=trig,
                             premium_stop_pct=stop, strike_offset=-2)
            s = summarize(r.trades)
            results[(stop, trig)] = s
            stop_label = f"{int(stop * 100)}%"
            passes = sum([
                s["n"] >= 20,
                s["wr"] >= 0.45,
                s["wl"] >= 1.5,
                s["exp"] > 0,
            ])
            safe_growth = "OK " if abs(s["worst_trade"]) <= 150 and s["total"] > 0 else "no "
            print(f"{stop_label:<6}{trig_label:<6}{s['n']:<5}{s['wr']*100:<4.0f}%"
                  f" ${s['avg_w']:<5.0f} ${s['avg_l']:<5.0f}"
                  f"{s['wl']:<5.2f} ${s['total']:<7.0f}${s['exp']:<5.0f} "
                  f"${s['worst_trade']:<6.0f}${s['max_dd']:<7.0f}{passes}/4 {safe_growth}")

    # Best-by-criteria
    profitable = {k: v for k, v in results.items() if v["total"] > 0}
    if not profitable:
        print("\n  No profitable config found.")
        return

    safe_profitable = {k: v for k, v in profitable.items() if abs(v["worst_trade"]) <= 150}

    print("\n  BEST overall (by total P&L):")
    k, v = max(profitable.items(), key=lambda x: x[1]["total"])
    print(f"    stop={int(k[0]*100)}% trig={k[1]}: ${v['total']:.0f} ({v['n']}t, {v['wr']*100:.0f}% WR, "
          f"worst trade ${v['worst_trade']:.0f})")

    if safe_profitable:
        print("\n  SAFE-GROWTH winner (worst trade <= $150 AND profitable):")
        # Best total P&L among safe configs
        k, v = max(safe_profitable.items(), key=lambda x: x[1]["total"])
        print(f"    stop={int(k[0]*100)}% trig={k[1]}: ${v['total']:.0f} ({v['n']}t, {v['wr']*100:.0f}% WR, "
              f"worst trade ${v['worst_trade']:.0f}, max DD ${v['max_dd']:.0f})")
        print(f"    -> on $1k account: avg_winner=${v['avg_w']:.0f} ({v['avg_w']/10:.1f}%), "
              f"avg_loser=${v['avg_l']:.0f} ({abs(v['avg_l'])/10:.1f}%)")
        print(f"    -> worst-case single trade = ${abs(v['worst_trade'])/10:.1f}% of $1k account")
    else:
        print("\n  NO SAFE-GROWTH config (no profitable config with worst trade <= $150).")
        print("  Even tightest stops still produce outsize losses on bad bars.")
        print("  Position sizing (fewer contracts) is the lever instead.")


if __name__ == "__main__":
    main()
