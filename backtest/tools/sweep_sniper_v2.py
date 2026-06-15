"""Sniper-entry sweep v2 — finer-grained filter 9 volume thresholds.

Each config has time filters baked in (no pre-10am, no 14:00-15:00 entries).
Tests filter 9 volume requirement at: 1.3x (baseline) / 1.0x / 0.7x / disabled.
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
    # (label, f9_vol_mult, vix_soft, disable_filters)
    ("F9_1.3x_BASELINE",  1.3, False, None),
    ("F9_1.0x",            1.0, False, None),
    ("F9_0.7x",            0.7, False, None),
    ("F9_OFF",             1.3, False, [9]),     # disable filter 9 entirely
    ("F9_1.0x_F8_SOFT",    1.0, True,  None),
    ("F9_0.7x_F8_SOFT",    0.7, True,  None),
]


def summarize(trades):
    if not trades:
        return dict(n=0, wr=0, total=0, exp=0, avg_w=0, avg_l=0, wl=0,
                    max_dd=0, worst=0, j_morning=0, j_4_29=0, j_5_4=0)
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

    j_morning = sum(1 for t in trades
                    if dt.time(10, 0) <= pd.Timestamp(t.entry_time_et).time() < dt.time(11, 0))
    # Did we catch entries on J's specific days near his entry times?
    j_4_29 = sum(1 for t in trades
                 if pd.Timestamp(t.entry_time_et).date() == dt.date(2026, 4, 29)
                 and dt.time(10, 0) <= pd.Timestamp(t.entry_time_et).time() < dt.time(11, 0))
    j_5_4 = sum(1 for t in trades
                if pd.Timestamp(t.entry_time_et).date() == dt.date(2026, 5, 4)
                and dt.time(10, 0) <= pd.Timestamp(t.entry_time_et).time() < dt.time(11, 0))

    wr = len(wins) / n if n else 0
    wl = abs(avg_w / avg_l) if avg_l else 0
    return dict(n=n, wr=wr, total=total, exp=total / n if n else 0,
                avg_w=avg_w, avg_l=avg_l, wl=wl, max_dd=max_dd,
                worst=min(t.dollar_pnl for t in trades),
                j_morning=j_morning, j_4_29=j_4_29, j_5_4=j_5_4)


def main():
    spy = pd.read_csv(DATA_DIR / "spy_5m_2026-03-15_2026-05-07.csv")
    vix = pd.read_csv(DATA_DIR / "vix_5m_2026-03-15_2026-05-07.csv")
    start, end = dt.date(2026, 3, 15), dt.date(2026, 5, 7)

    # Time filters always on (per user spec)
    ntb = dt.time(10, 0)
    ntw = (dt.time(14, 0), dt.time(15, 0))

    print("\nSNIPER v2 — varying filter 9 volume threshold (time filters always on)")
    print(f"\n{'CONFIG':<22}{'N':<5}{'WR':<5}{'AvgW':<7}{'AvgL':<7}{'W/L':<6}"
          f"{'TOTAL':<9}{'EXP':<7}{'WORST':<8}{'MaxDD':<9}{'10-11':<7}{'4/29':<6}{'5/4':<5}{'PASS'}")
    print("-" * 115)

    results = {}
    for label, vol_mult, vix_soft, disable in CONFIGS:
        r = run_backtest(spy, vix, start_date=start, end_date=end,
                         use_real_fills=True, min_triggers=1,
                         f9_vol_mult=vol_mult,
                         vix_soft_mode=vix_soft,
                         disable_filters=disable,
                         no_trade_before=ntb, no_trade_window=ntw)
        s = summarize(r.trades)
        results[label] = s
        passes = sum([s["n"] >= 20, s["wr"] >= 0.45, s["wl"] >= 1.5, s["exp"] > 0])
        print(f"{label:<22}{s['n']:<5}{s['wr']*100:<4.0f}%"
              f" ${s['avg_w']:<5.0f} ${s['avg_l']:<5.0f}"
              f"{s['wl']:<5.2f} ${s['total']:<7.0f}${s['exp']:<5.0f} "
              f"${s['worst']:<6.0f}${s['max_dd']:<7.0f}{s['j_morning']:<6} "
              f"{s['j_4_29']:<5} {s['j_5_4']:<5}{passes}/4")

    # Best by total P&L AND 4/4 PASS
    profitable = {k: v for k, v in results.items() if v["total"] > 0}
    pass_4 = {k: v for k, v in profitable.items()
              if v["n"] >= 20 and v["wr"] >= 0.45 and v["wl"] >= 1.5 and v["exp"] > 0}
    if pass_4:
        best = max(pass_4.items(), key=lambda x: x[1]["total"])
        print(f"\n  BEST 4/4 PASS: {best[0]} -> ${best[1]['total']:.0f}, "
              f"max DD ${best[1]['max_dd']:.0f}, {best[1]['j_morning']} morning entries")
    if profitable:
        best = max(profitable.items(), key=lambda x: x[1]["total"])
        print(f"  BEST any:      {best[0]} -> ${best[1]['total']:.0f}")


if __name__ == "__main__":
    main()
