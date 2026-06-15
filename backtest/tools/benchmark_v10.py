"""Benchmark the v10 locked production config — entry/exit consistency analysis.

v10 = filter 10 ≥1 trigger + ITM-2 strike + -10% premium stop.

Reports:
  - Per-trade detail (entry/exit by time, level, candle pattern)
  - Daily P&L distribution (consistency check)
  - Hypothesis check: is the strategy concentrated on a few big days or spread?
  - $1k account scaling: 1-contract sizing + per-trade % of account
  - Key-level analysis: which levels produced winners vs losers
"""

from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.orchestrator import run_backtest  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = REPO / "data"


def main():
    spy = pd.read_csv(DATA_DIR / "spy_5m_2026-03-15_2026-05-07.csv")
    vix = pd.read_csv(DATA_DIR / "vix_5m_2026-03-15_2026-05-07.csv")

    result = run_backtest(spy, vix,
                          start_date=dt.date(2026, 3, 15),
                          end_date=dt.date(2026, 5, 7),
                          use_real_fills=True)
    trades = result.trades

    # Group by day
    by_day = defaultdict(list)
    for t in trades:
        d = pd.Timestamp(t.entry_time_et).date()
        by_day[d].append(t)

    print("\n" + "=" * 88)
    print("  v10 PRODUCTION BENCHMARK")
    print("  Config: filter 10 = >=1 trigger, ITM-2 strikes, -10% premium stop")
    print("=" * 88)

    # Top-line
    n = len(trades)
    wins = [t for t in trades if t.dollar_pnl > 0]
    losses = [t for t in trades if t.dollar_pnl < 0]
    total = sum(t.dollar_pnl for t in trades)
    avg_w = sum(t.dollar_pnl for t in wins) / max(1, len(wins))
    avg_l = sum(t.dollar_pnl for t in losses) / max(1, len(losses))
    n_days = len(by_day)
    days_with_trade = sum(1 for d, ts in by_day.items() if ts)
    days_pos = sum(1 for d, ts in by_day.items() if sum(t.dollar_pnl for t in ts) > 0)
    days_neg = sum(1 for d, ts in by_day.items() if sum(t.dollar_pnl for t in ts) < 0)

    print(f"\n  Total trades:        {n}")
    print(f"  Winners / losers:    {len(wins)}W / {len(losses)}L  ({len(wins)/n*100:.0f}% WR)")
    print(f"  Total P&L:           ${total:.0f}")
    print(f"  Avg winner / loser:  ${avg_w:.0f} / ${avg_l:.0f}")
    print(f"  W/L ratio:           {abs(avg_w/avg_l):.2f}x")
    print(f"  Expectancy:          ${total/n:.0f}/trade")
    print(f"  Best / worst trade:  ${max(t.dollar_pnl for t in trades):.0f} / ${min(t.dollar_pnl for t in trades):.0f}")
    print(f"  Trading days:        {days_with_trade} of {n_days} ({days_pos} pos, {days_neg} neg)")

    # Daily distribution — concentration check
    print(f"\n  DAILY P&L DISTRIBUTION:")
    print(f"    {'Date':<12}{'Trades':<8}{'Daily P&L':<12}{'Cumulative'}")
    cum = 0
    for d in sorted(by_day.keys()):
        day_trades = by_day[d]
        day_pnl = sum(t.dollar_pnl for t in day_trades)
        cum += day_pnl
        sign = "+" if day_pnl >= 0 else ""
        print(f"    {d}  {len(day_trades):<7} {sign}${day_pnl:<10.0f} ${cum:.0f}")

    # Concentration metric — is one day >50% of total?
    day_pnls = [(d, sum(t.dollar_pnl for t in ts)) for d, ts in by_day.items()]
    day_pnls.sort(key=lambda x: -x[1])
    top_day = day_pnls[0]
    print(f"\n  Concentration: top day {top_day[0]} = ${top_day[1]:.0f} ({top_day[1]/total*100:.0f}% of total)")
    if top_day[1] / total > 0.5:
        print(f"    !! WARNING: more than 50% of total P&L from one day — strategy is fragile.")

    # Time-of-day distribution
    by_tod = defaultdict(list)
    for t in trades:
        h = pd.Timestamp(t.entry_time_et).time().hour
        bucket = "OPEN" if h < 10 else ("MORNING" if h < 12 else ("MIDDAY" if h < 14 else ("AFTERNOON" if h < 15 else "POWER")))
        by_tod[bucket].append(t.dollar_pnl)
    print(f"\n  TIME-OF-DAY P&L:")
    for tod in ["OPEN", "MORNING", "MIDDAY", "AFTERNOON", "POWER"]:
        if tod in by_tod:
            ts = by_tod[tod]
            print(f"    {tod:<10} {len(ts):<3} trades  ${sum(ts):.0f} total  (avg ${sum(ts)/len(ts):.0f})")

    # Drawdown curve
    def _naive(ts):
        if hasattr(ts, "tz_localize") and ts.tz is not None:
            return ts.tz_localize(None)
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            return ts.replace(tzinfo=None)
        return ts
    cum, peak, max_dd, max_dd_time = 0, 0, 0, None
    for t in sorted(trades, key=lambda t: _naive(t.entry_time_et)):
        cum += t.dollar_pnl
        peak = max(peak, cum)
        dd = cum - peak
        if dd < max_dd:
            max_dd = dd
            max_dd_time = t.entry_time_et
    print(f"\n  EQUITY CURVE:")
    print(f"    Peak P&L:          ${peak:.0f}")
    print(f"    Max drawdown:      ${max_dd:.0f}  (after {pd.Timestamp(max_dd_time).date()} trades)")
    print(f"    Final P&L:         ${total:.0f}")

    # $1k account scaling
    print(f"\n  $1,000 ACCOUNT SCALING (using 1 contract per trade instead of 3):")
    pnl_1c = total / 3
    avg_w_1c = avg_w / 3
    avg_l_1c = avg_l / 3
    worst_1c = min(t.dollar_pnl for t in trades) / 3
    print(f"    Total P&L:         ${pnl_1c:.0f}  ({pnl_1c/10:.1f}% of $1k account over 53 days)")
    print(f"    Avg winner:        ${avg_w_1c:.0f}  ({avg_w_1c/10:.1f}% of account)")
    print(f"    Avg loser:         ${avg_l_1c:.0f}  ({abs(avg_l_1c)/10:.1f}% of account)")
    print(f"    Worst trade:       ${worst_1c:.0f}  ({abs(worst_1c)/10:.1f}% of account)")
    print(f"    Max drawdown:      ${max_dd/3:.0f}  ({abs(max_dd/3)/10:.1f}% of account)")

    # Per-trade table
    print(f"\n  PER-TRADE DETAIL ({n} trades):")
    print(f"    {'Date':<12}{'Time':<7}{'K':<5}{'Entry':<8}{'Exit':<8}{'PnL':<8}{'Reason':<28}{'Lvl reject'}")
    for t in trades:
        d = pd.Timestamp(t.entry_time_et).date().isoformat()
        et = pd.Timestamp(t.entry_time_et).strftime("%H:%M")
        sign = "+" if t.dollar_pnl >= 0 else ""
        rl = f"{t.rejection_level:.2f}" if t.rejection_level else "—"
        print(f"    {d}  {et:<7}{t.strike:<5}${t.entry_premium:<6.2f} ${t.runner_exit_premium:<6.2f} "
              f"{sign}${int(t.dollar_pnl):<6}{(t.exit_reason.value if t.exit_reason else 'n/a')[:26]:<28}{rl}")


if __name__ == "__main__":
    main()
