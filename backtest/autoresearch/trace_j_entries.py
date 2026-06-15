"""Bar-by-bar trace of engine state on J's winning trade days.

For each of J's winners, shows:
- The 5m bar around J's entry time (price, ribbon, vol, VIX)
- Engine's setup-eval result on that bar (passed/blocked filters)
- What strike the engine WOULD pick vs what J picked
- Why entry timing diverged

Goal: identify the SPECIFIC filters/params that block the engine from
matching J's edge.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from autoresearch import runner
from lib import ribbon as ribbon_mod
from lib import filters as filters_mod
from lib import levels as levels_mod
from lib.orchestrator import _precompute_htf_15m_stacks


# J's winner entries (from trades.csv)
J_WINNERS = [
    {"date": "2026-04-29", "time_et": "10:25:51", "strike": 710, "side": "P",
     "qty": 6, "entry_premium": 1.67, "exit_time": "12:37:41", "exit_premium": 2.24,
     "pnl": 342, "note": "Clean entry on 711.4 rejection + ribbon flip"},
    {"date": "2026-05-01", "time_et": "13:36:00", "strike": 721, "side": "P",
     "qty": 20, "entry_premium": 0.325, "exit_time": "14:47:55", "exit_premium": 0.56,
     "pnl": 470, "note": "Leg #2 at 13:36 was real trendline-rejection trigger (leg #1 was anticipation)"},
    {"date": "2026-05-04", "time_et": "10:27:50", "strike": 721, "side": "P",
     "qty": 10, "entry_premium": 0.85, "exit_time": "11:18:29", "exit_premium": 1.58,
     "pnl": 730, "note": "Confluence: premarket level + multi-day trendline + ribbon flip"},
]


def find_bar_at_time(spy_df: pd.DataFrame, date: dt.date, time_et_str: str) -> int | None:
    """Return DataFrame row index for the 5m bar that BRACKETS the given time."""
    target_h, target_m, _ = (int(p) for p in time_et_str.split(":"))
    target_min = target_h * 60 + target_m
    # Bars are 5min boundaries. Find bar whose CLOSE is closest to but <= target_min.
    target_bar_min = (target_min // 5) * 5
    for idx, row in spy_df.iterrows():
        ts = row["timestamp_et"]
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        if ts.date() != date:
            continue
        bar_min = ts.hour * 60 + ts.minute
        if bar_min == target_bar_min:
            return idx
    return None


def trace_one(spy_df: pd.DataFrame, vix_df: pd.DataFrame, w: dict) -> None:
    date = dt.date.fromisoformat(w["date"])
    print()
    print("=" * 80)
    print(f"  {w['date']} J entered SPY {w['strike']}{w['side']} @ {w['time_et']}")
    print(f"  J: ${w['entry_premium']:.3f} -> ${w['exit_premium']:.3f}  ({w['pnl']:+}$)")
    print(f"  note: {w['note']}")
    print("=" * 80)

    # Slice to the day. timestamp_et may be tz-aware datetime or string -- normalize.
    ts_col = pd.to_datetime(spy_df["timestamp_et"], utc=True, errors="coerce")
    spy_day = spy_df[ts_col.dt.tz_convert("US/Eastern").dt.date == date].copy()
    if spy_day.empty:
        print(f"  NO SPY DATA FOR {date}")
        return
    spy_day["_ts"] = pd.to_datetime(spy_day["timestamp_et"], utc=True).dt.tz_convert("US/Eastern")
    spy_day = spy_day.reset_index(drop=True)

    # Find J's entry bar
    target_h, target_m, _ = (int(p) for p in w["time_et"].split(":"))
    target_min = target_h * 60 + target_m
    target_bar_close_min = ((target_min // 5) + 1) * 5  # bar that CLOSES at the 5m boundary AFTER J entered

    # Show 6 bars: 4 before J's entry + entry bar + 1 after
    print(f"\n  5m bars around J's entry (entry was during bar that closed at {target_bar_close_min // 60:02d}:{target_bar_close_min % 60:02d}):")
    print(f"  {'time':<8} {'open':>8} {'high':>8} {'low':>8} {'close':>8} {'vol':>9}  {'rng':>6}")
    rows_shown = 0
    for idx, row in spy_day.iterrows():
        ts = row["_ts"]
        bar_close_min = ts.hour * 60 + ts.minute
        if bar_close_min < target_bar_close_min - 30:
            continue
        if bar_close_min > target_bar_close_min + 15:
            break
        marker = ">>" if abs(bar_close_min - target_bar_close_min) <= 5 else "  "
        rng = row["high"] - row["low"]
        time_str = ts.strftime('%H:%M')
        print(f"  {marker}{time_str:<6} {row['open']:>8.2f} {row['high']:>8.2f} {row['low']:>8.2f} {row['close']:>8.2f} {row['volume']:>9.0f}  {rng:>5.2f}")
        rows_shown += 1

    # Pull engine state at J's entry bar
    # Find bar in dataframe
    target_idx = None
    for idx, row in spy_day.iterrows():
        ts = row["_ts"]
        bar_min = ts.hour * 60 + ts.minute
        if bar_min == target_bar_close_min:
            target_idx = idx
            break
    if target_idx is None:
        print(f"\n  COULD NOT FIND BAR FOR {w['time_et']} -- target close min = {target_bar_close_min}")
        return

    bar = spy_day.iloc[target_idx]
    print(f"\n  Engine state AT J's entry bar (close {bar['_ts'].strftime('%H:%M')}):")
    print(f"    SPY: {bar['close']:.2f}  range: {bar['high']-bar['low']:.2f}  vol: {bar['volume']:.0f}")
    if "fast_ema" in spy_day.columns and "slow_ema" in spy_day.columns:
        print(f"    Fast EMA: {bar.get('fast_ema', 'n/a'):.2f}  Slow EMA: {bar.get('slow_ema', 'n/a'):.2f}")

    # What strike WOULD engine pick? Currently strike_offset_itm=2 means $2 above spot for puts.
    eng_strike_2itm = round(bar['close']) + 2  # ITM-2 for puts
    eng_strike_atm  = round(bar['close'])
    eng_strike_1otm = round(bar['close']) - 1
    eng_strike_2otm = round(bar['close']) - 2
    print(f"\n  Strike comparison (SPY ~{bar['close']:.2f}):")
    print(f"    ITM-2 puts (engine v14): {eng_strike_2itm}P  -- offset = +2 from spot")
    print(f"    ATM puts:                {eng_strike_atm}P   -- offset =  0 from spot")
    print(f"    1-OTM puts:              {eng_strike_1otm}P  -- offset = -1 from spot")
    print(f"    2-OTM puts:              {eng_strike_2otm}P  -- offset = -2 from spot")
    print(f"    J actually picked:       {w['strike']}P     -- offset = {w['strike'] - round(bar['close']):+d} from spot")


def main() -> int:
    train_start = dt.date(2026, 4, 1)
    train_end = dt.date(2026, 5, 7)
    print(f"Loading SPY/VIX from {train_start} to {train_end}...")
    spy, vix = runner.load_data(train_start, train_end)
    print(f"Loaded {len(spy)} SPY bars, {len(vix)} VIX bars")

    for w in J_WINNERS:
        trace_one(spy, vix, w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
