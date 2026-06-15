"""Dump bar OHLC + computed levels at a specific timestamp for deep debugging."""

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.levels import _detect_from_history

REPO = Path(__file__).resolve().parents[1]


def main():
    if len(sys.argv) < 3:
        print("usage: python tools/dump_bar_data.py YYYY-MM-DD HH:MM [HH:MM_end]")
        return 1
    date_str = sys.argv[1]
    hhmm_start = sys.argv[2]
    hhmm_end = sys.argv[3] if len(sys.argv) > 3 else hhmm_start

    spy = pd.read_csv(REPO / "fixtures" / f"spy_5m_{date_str}_with_warmup.csv")
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    target = dt.date.fromisoformat(date_str)

    target_day = spy[spy["timestamp_et"].dt.date == target]
    print(f"Total bars on {date_str}: {len(target_day)}")
    print(f"Window: {hhmm_start} to {hhmm_end}\n")

    start_t = dt.datetime.strptime(hhmm_start, "%H:%M").time()
    end_t = dt.datetime.strptime(hhmm_end, "%H:%M").time()

    rows = target_day[
        (target_day["timestamp_et"].dt.time >= start_t)
        & (target_day["timestamp_et"].dt.time <= end_t)
    ]
    if rows.empty:
        print(f"  no bars in window")
        return 0

    print(f"{'Time':<8} {'Open':>8} {'High':>8} {'Low':>8} {'Close':>8} {'Volume':>10}")
    print("-" * 60)
    for _, r in rows.iterrows():
        print(
            f"{r['timestamp_et'].strftime('%H:%M'):<8} "
            f"{r['open']:>8.2f} {r['high']:>8.2f} {r['low']:>8.2f} "
            f"{r['close']:>8.2f} {r['volume']:>10.0f}"
        )

    print(f"\nLevels detected at {hhmm_start} on {date_str}:")
    bar_ts = rows.iloc[0]["timestamp_et"]
    history = spy[spy["timestamp_et"] <= bar_ts]
    levels = _detect_from_history(history, target)
    print(f"  active: {sorted(levels.active)}")
    print(f"  multi_day: {sorted(levels.multi_day)}")

    # Also show the candidate rejection check: which active levels had bar.high > level AND bar.close < level?
    print(f"\nLevel-rejection candidates for the {hhmm_start} bar:")
    bar = rows.iloc[0]
    for lvl in sorted(levels.active):
        high_above = bar["high"] > lvl
        close_below = bar["close"] < lvl
        match = "REJECT" if high_above and close_below else (
            "high>" if high_above else ("close<" if close_below else "")
        )
        if high_above or close_below:
            print(f"  {lvl:.2f}: high {bar['high']:.2f} {('>' if high_above else '<=')} L; "
                  f"close {bar['close']:.2f} {('<' if close_below else '>=')} L -> {match}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
