"""
Trendline-only time-of-day breakdown.

The midday gate already blocks TL-only from 11:30-14:00 ET.
Question: are afternoon TL-only (14:00+) uniformly negative in IS?
If so AND if OOS has no afternoon TL-only, an afternoon extension might work.

Quick diagnostic — no full A/B sweep. Just the breakdown.
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.orchestrator import run_backtest

MASTER_SPY = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
MASTER_VIX = ROOT / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-16.csv"

IS_S = dt.date(2025, 1, 2)
IS_E = dt.date(2026, 5, 7)
OOS_S = dt.date(2026, 5, 8)
OOS_E = dt.date(2026, 6, 16)

BASE_KWARGS = dict(
    use_real_fills=True,
    no_trade_window=None,
    no_trade_before=dt.time(9, 35),
    midday_trendline_gate=True,
    premium_stop_pct_bear=-0.10,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.50,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.30,
    block_level_rejection=True,
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    params_overrides={"vix_bull_max": 18.0},
)


def tod_bucket(entry_time):
    """Bucket entry time into session windows."""
    if entry_time is None:
        return "unknown"
    if hasattr(entry_time, "hour"):
        h, m = entry_time.hour, entry_time.minute
    else:
        try:
            t = pd.to_datetime(entry_time)
            h, m = t.hour, t.minute
        except Exception:
            return "unknown"
    total_min = h * 60 + m
    if total_min < 9 * 60 + 35:
        return "pre-09:35"
    elif total_min < 10 * 60:
        return "09:35-10:00"
    elif total_min < 11 * 60:
        return "10:00-11:00"
    elif total_min < 11 * 60 + 30:
        return "11:00-11:30"
    elif total_min < 14 * 60:
        return "11:30-14:00 (midday-blocked)"
    elif total_min < 15 * 60:
        return "14:00-15:00"
    else:
        return "15:00-15:50"


def analyze(spy_df, vix_df, start, end, label):
    result = run_backtest(spy_df, vix_df, start_date=start, end_date=end, **BASE_KWARGS)
    n = len(result.trades)
    total_pnl = sum(t.dollar_pnl for t in result.trades)
    print(f"\n=== {label}: n={n} pnl={total_pnl:+.0f} ===")

    tl_only = []
    for t in result.trades:
        triggers = getattr(t, "triggers_fired", None) or []
        if len(triggers) == 1 and any("trendline_rejection" in str(tr) for tr in triggers):
            tl_only.append(t)

    other = [t for t in result.trades if t not in tl_only]
    tl_pnl = sum(t.dollar_pnl for t in tl_only)
    other_pnl = sum(t.dollar_pnl for t in other)
    print(f"  TL-only:  n={len(tl_only):3d} pnl={tl_pnl:+.0f}")
    print(f"  non-TL:   n={len(other):3d} pnl={other_pnl:+.0f}")

    print(f"\n  TL-only by time-of-day:")
    buckets = {}
    for t in tl_only:
        et = getattr(t, "entry_time_et", None)
        bkt = tod_bucket(et)
        buckets.setdefault(bkt, []).append(t)

    bkt_order = ["09:35-10:00", "10:00-11:00", "11:00-11:30",
                 "11:30-14:00 (midday-blocked)", "14:00-15:00", "15:00-15:50", "unknown"]
    for bkt in bkt_order:
        trades = buckets.get(bkt, [])
        if not trades:
            continue
        bkt_pnl = sum(t.dollar_pnl for t in trades)
        wins = sum(1 for t in trades if t.dollar_pnl > 0)
        wr = wins / len(trades)
        print(f"    {bkt:<35}: n={len(trades):3d} WR={wr:.0%} pnl={bkt_pnl:+.0f} avg={bkt_pnl/len(trades):+.0f}")

    print(f"\n  non-TL-only by time-of-day:")
    buckets2 = {}
    for t in other:
        et = getattr(t, "entry_time_et", None)
        bkt = tod_bucket(et)
        buckets2.setdefault(bkt, []).append(t)
    for bkt in bkt_order:
        trades = buckets2.get(bkt, [])
        if not trades:
            continue
        bkt_pnl = sum(t.dollar_pnl for t in trades)
        wins = sum(1 for t in trades if t.dollar_pnl > 0)
        wr = wins / len(trades)
        print(f"    {bkt:<35}: n={len(trades):3d} WR={wr:.0%} pnl={bkt_pnl:+.0f} avg={bkt_pnl/len(trades):+.0f}")

    return result, tl_only, other


def main():
    print("Loading data...")
    spy = pd.read_csv(MASTER_SPY)
    vix = pd.read_csv(MASTER_VIX)
    print(f"SPY {len(spy)} rows, VIX {len(vix)} rows")

    analyze(spy, vix, IS_S, IS_E, "IS")
    analyze(spy, vix, OOS_S, OOS_E, "OOS")


if __name__ == "__main__":
    main()
