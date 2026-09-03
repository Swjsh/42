"""Sniper-entry sweep — find entry config that catches J's morning rejections.

Tests two key levers on top of v10 production rules:
  1. Filter 9 (volume 1.3x): keep / drop / soften to 1.0x / disabled
  2. Filter 8 (VIX > 17.30 + rising): keep / soft modifier / disabled

PLUS adds the user-requested time windows:
  - no_trade_before: 10:00 ET (skip the 9:35-10:00 chop)
  - no_trade_window: 14:00-15:00 ET (loser window per benchmark)

All on top of: ITM-2 strikes, -10% premium stop, ≥1 trigger.

Goal: engine fires on J's morning rejection bars (e.g. 5/4 10:25 entry)
without losing safety.
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


CONFIGS = [
    # (label, disable_filters, vix_soft, no_trade_before, no_trade_window)
    ("V10_BASELINE",     None,  False, None, None),
    ("TIME_FILTERS",     None,  False, dt.time(10, 0), (dt.time(14, 0), dt.time(15, 0))),
    ("F9_DISABLED",      [9],   False, dt.time(10, 0), (dt.time(14, 0), dt.time(15, 0))),
    ("F8_SOFT_F9_OFF",   [9],   True,  dt.time(10, 0), (dt.time(14, 0), dt.time(15, 0))),
    ("F8_OFF_F9_OFF",    [8, 9], False, dt.time(10, 0), (dt.time(14, 0), dt.time(15, 0))),
]


def summarize(trades):
    if not trades:
        return dict(n=0, wr=0, total=0, exp=0, avg_w=0, avg_l=0, wl=0,
                    max_dd=0, worst=0, best=0, j_morning=0)
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

    # Count "J-morning" entries — trades fired between 10:00-11:00 ET
    j_morning = sum(1 for t in trades
                    if dt.time(10, 0) <= pd.Timestamp(t.entry_time_et).time() < dt.time(11, 0))

    wr = len(wins) / n if n else 0
    wl = abs(avg_w / avg_l) if avg_l else 0
    return dict(n=n, wr=wr, total=total, exp=total / n if n else 0,
                avg_w=avg_w, avg_l=avg_l, wl=wl, max_dd=max_dd,
                worst=min(t.dollar_pnl for t in trades),
                best=max(t.dollar_pnl for t in trades),
                j_morning=j_morning)


def main():
    spy = pd.read_csv(DATA_DIR / "spy_5m_2026-03-15_2026-05-07.csv")
    vix = pd.read_csv(DATA_DIR / "vix_5m_2026-03-15_2026-05-07.csv")
    start, end = dt.date(2026, 3, 15), dt.date(2026, 5, 7)

    print("\nSNIPER-ENTRY SWEEP — catching J's morning rejection window")
    print(f"\n{'CONFIG':<20}{'N':<5}{'WR':<5}{'AvgW':<7}{'AvgL':<7}{'W/L':<6}"
          f"{'TOTAL':<9}{'EXP':<7}{'WORST':<8}{'MaxDD':<9}{'10-11AM':<9}{'PASS'}")
    print("-" * 105)

    results = {}
    for label, disable, vix_soft, ntb, ntw in CONFIGS:
        r = run_backtest(spy, vix, start_date=start, end_date=end,
                         use_real_fills=True, min_triggers=1,
                         disable_filters=disable,
                         vix_soft_mode=vix_soft,
                         no_trade_before=ntb, no_trade_window=ntw)
        s = summarize(r.trades)
        results[label] = s
        passes = sum([s["n"] >= 20, s["wr"] >= 0.45, s["wl"] >= 1.5, s["exp"] > 0])
        print(f"{label:<20}{s['n']:<5}{s['wr']*100:<4.0f}%"
              f" ${s['avg_w']:<5.0f} ${s['avg_l']:<5.0f}"
              f"{s['wl']:<5.2f} ${s['total']:<7.0f}${s['exp']:<5.0f} "
              f"${s['worst']:<6.0f}${s['max_dd']:<7.0f}{s['j_morning']:<8} {passes}/4")

    # Best
    profitable = {k: v for k, v in results.items() if v["total"] > 0}
    if profitable:
        best = max(profitable.items(), key=lambda x: x[1]["total"])
        print(f"\n  BEST: {best[0]} -> ${best[1]['total']:.0f} "
              f"({best[1]['n']} trades, {best[1]['wr']*100:.0f}% WR, "
              f"{best[1]['j_morning']} morning entries)")


if __name__ == "__main__":
    main()
