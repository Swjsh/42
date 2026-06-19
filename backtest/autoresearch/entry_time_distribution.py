"""
Entry Time-of-Day Distribution — BEARISH_REVERSAL

Analyzes WHEN (time of day) IS trades fire, split by:
  - Catastrophic months (Apr-26, Mar-26, Nov-25, Jan-26, Mar-25, May-25)
  - Normal IS months
  - OOS May-26

Key question: Do catastrophic-month entries cluster at different times than normal/OOS entries?
If yes, a time-of-day gate could help differentiate them.

Security: Read-only on all production state. No Alpaca calls.
"""
from __future__ import annotations
import sys
import pathlib
import datetime as dt
import collections

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from backtest.lib.orchestrator import run_backtest

DATA_DIR = ROOT / "backtest" / "data"
SPY_FILE = DATA_DIR / "spy_5m_2025-01-01_2026-05-22.csv"
VIX_FILE = DATA_DIR / "vix_5m_2025-01-01_2026-05-22.csv"

IS_START  = dt.date(2025, 1, 2)
IS_END    = dt.date(2026, 5, 7)
OOS_START = dt.date(2026, 5, 8)
OOS_END   = dt.date(2026, 5, 22)

CAT_MONTHS = {"2026-04", "2026-03", "2025-11", "2026-01", "2025-05", "2025-03"}

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

TIME_BUCKETS = [
    ("09:35-10:00", dt.time(9, 35), dt.time(9, 59)),
    ("10:00-10:30", dt.time(10, 0), dt.time(10, 29)),
    ("10:30-11:00", dt.time(10, 30), dt.time(10, 59)),
    ("11:00-11:30", dt.time(11, 0), dt.time(11, 29)),
    ("11:30-12:00", dt.time(11, 30), dt.time(11, 59)),
    ("12:00-13:00", dt.time(12, 0), dt.time(12, 59)),
    ("13:00-14:00", dt.time(13, 0), dt.time(13, 59)),
    ("14:00-15:00", dt.time(14, 0), dt.time(14, 59)),
    ("15:00-15:40", dt.time(15, 0), dt.time(15, 40)),
]


def _tz_naive(t):
    et = t.entry_time_et
    if getattr(et, "tzinfo", None) is not None:
        return et.replace(tzinfo=None)
    return et


def _bucket(entry_time: dt.datetime) -> str:
    t = entry_time.time()
    for label, start, end in TIME_BUCKETS:
        if start <= t <= end:
            return label
    return "other"


def _is_catastrophic(t) -> bool:
    d = _tz_naive(t).date()
    return d.strftime("%Y-%m") in CAT_MONTHS


def _analyze(trades: list, label: str) -> None:
    if not trades:
        print(f"\n  {label}: no trades")
        return

    cat = [t for t in trades if _is_catastrophic(t)]
    norm = [t for t in trades if not _is_catastrophic(t)]

    print(f"\n  {label}: n={len(trades)}  cat={len(cat)}  norm={len(norm)}")
    print(f"\n  {'Bucket':>14}  {'CAT n':>7}  {'CAT WR':>7}  {'CAT pnl':>9}  |  {'NORM n':>7}  {'NORM WR':>7}  {'NORM pnl':>9}")
    print("  " + "-" * 70)

    all_buckets = [label for label, _, _ in TIME_BUCKETS]
    cat_by_b: dict[str, list] = collections.defaultdict(list)
    norm_by_b: dict[str, list] = collections.defaultdict(list)
    for t in cat:
        cat_by_b[_bucket(_tz_naive(t))].append(t)
    for t in norm:
        norm_by_b[_bucket(_tz_naive(t))].append(t)

    for bkt in all_buckets:
        c_trades = cat_by_b[bkt]
        n_trades = norm_by_b[bkt]
        c_n = len(c_trades)
        n_n = len(n_trades)
        c_wr = sum(1 for t in c_trades if t.dollar_pnl > 0) / c_n if c_n else 0
        n_wr = sum(1 for t in n_trades if t.dollar_pnl > 0) / n_n if n_n else 0
        c_pnl = sum(t.dollar_pnl for t in c_trades)
        n_pnl = sum(t.dollar_pnl for t in n_trades)
        print(f"  {bkt:>14}  {c_n:>7}  {c_wr:>7.0%}  {c_pnl:>+9.0f}  |  {n_n:>7}  {n_wr:>7.0%}  {n_pnl:>+9.0f}")

    # Summary stats
    c_wr_total = sum(1 for t in cat if t.dollar_pnl > 0) / len(cat) if cat else 0
    n_wr_total = sum(1 for t in norm if t.dollar_pnl > 0) / len(norm) if norm else 0
    c_pnl_total = sum(t.dollar_pnl for t in cat)
    n_pnl_total = sum(t.dollar_pnl for t in norm)
    print(f"  {'TOTAL':>14}  {len(cat):>7}  {c_wr_total:>7.0%}  {c_pnl_total:>+9.0f}  |  {len(norm):>7}  {n_wr_total:>7.0%}  {n_pnl_total:>+9.0f}")

    # Time-of-day concentration: what % of cat trades are in morning vs midday vs afternoon
    morning = [t for t in cat if _tz_naive(t).time() < dt.time(11, 0)]
    midday  = [t for t in cat if dt.time(11, 0) <= _tz_naive(t).time() < dt.time(14, 0)]
    afternoon = [t for t in cat if _tz_naive(t).time() >= dt.time(14, 0)]
    print(f"\n  CAT concentration: morning(09:35-10:59)={len(morning)}/{len(cat)} ({len(morning)/max(1,len(cat)):.0%}) "
          f"midday(11:00-13:59)={len(midday)}/{len(cat)} ({len(midday)/max(1,len(cat)):.0%}) "
          f"afternoon(14:00+)={len(afternoon)}/{len(cat)} ({len(afternoon)/max(1,len(cat)):.0%})")

    morning_n = [t for t in norm if _tz_naive(t).time() < dt.time(11, 0)]
    midday_n  = [t for t in norm if dt.time(11, 0) <= _tz_naive(t).time() < dt.time(14, 0)]
    afternoon_n = [t for t in norm if _tz_naive(t).time() >= dt.time(14, 0)]
    print(f"  NORM concentration: morning={len(morning_n)}/{len(norm)} ({len(morning_n)/max(1,len(norm)):.0%}) "
          f"midday={len(midday_n)}/{len(norm)} ({len(midday_n)/max(1,len(norm)):.0%}) "
          f"afternoon={len(afternoon_n)}/{len(norm)} ({len(afternoon_n)/max(1,len(norm)):.0%})")


if __name__ == "__main__":
    print("=" * 90)
    print("ENTRY TIME-OF-DAY DISTRIBUTION — BEARISH_REVERSAL")
    print("Question: Do catastrophic-month entries cluster at different times than normal months?")
    print("=" * 90)

    print("\n[1/2] Running IS backtest...")
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)
    is_result = run_backtest(spy_df, vix_df, start_date=IS_START, end_date=IS_END, **BASE)
    is_trades = is_result.trades
    print(f"  IS n={len(is_trades)} pnl={sum(t.dollar_pnl for t in is_trades):+.2f}")

    print("\n[2/2] Running OOS backtest...")
    oos_result = run_backtest(spy_df, vix_df, start_date=OOS_START, end_date=OOS_END, **BASE)
    oos_trades = oos_result.trades
    print(f"  OOS n={len(oos_trades)} pnl={sum(t.dollar_pnl for t in oos_trades):+.2f}")

    print("\n" + "=" * 90)
    print("TIME-OF-DAY DISTRIBUTION")
    _analyze(is_trades, "IS (2025-01-02 to 2026-05-07)")
    _analyze(oos_trades, "OOS (2026-05-08 to 2026-05-22)")

    print("\n" + "=" * 90)
    print("GATE VIABILITY TEST: if morning (09:35-10:59) entries are disproportionately BAD in CAT months...")
    print("  then a time gate (delay entry) could help -- but OOS must not be hurt proportionally.")
    print("ANALYSIS COMPLETE.")
