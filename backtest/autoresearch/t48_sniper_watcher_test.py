"""T48b - end-to-end SNIPER WATCHER test on 5/13 with proper multi_day_rth.

Goal: confirm sniper_watcher.detect_sniper_setup() returns a WatcherSignal
when called on the 5/13 12:20 ET bar. If yes -> production wiring is the bug.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd
from lib.watchers.sniper_watcher import detect_sniper_setup

MASTER_FULL = ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-12.csv"
TODAY_FILE = ROOT / "backtest" / "data" / "spy_5m_2026-05-08_2026-05-13.csv"
TARGET_DATE = "2026-05-13"
TARGET_TIME = "12:20"


def main():
    print("=== T48b SNIPER WATCHER END-TO-END TEST on 5/13 12:20 ET ===\n")

    # Load full master + today's bars, concat
    full = pd.read_csv(MASTER_FULL)
    today = pd.read_csv(TODAY_FILE)

    for df in (full, today):
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
        if df["timestamp_et"].dt.tz is not None:
            df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)

    today["date"] = today["timestamp_et"].dt.date.astype(str)
    today_only = today[today["date"] == TARGET_DATE].drop(columns=["date"])

    # multi_day_rth: full master + today's RTH (filtered to 09:30-16:00)
    combined = pd.concat([full, today_only], ignore_index=True).sort_values("timestamp_et").reset_index(drop=True)
    multi_day_rth = combined[
        (combined["timestamp_et"].dt.time >= pd.Timestamp("09:30").time())
        & (combined["timestamp_et"].dt.time < pd.Timestamp("16:00").time())
    ].reset_index(drop=True)

    print(f"multi_day_rth bars: {len(multi_day_rth)}")
    print(f"date range: {multi_day_rth['timestamp_et'].min()} to {multi_day_rth['timestamp_et'].max()}")
    print()

    # Find the 12:20 bar within multi_day_rth
    target_ts = pd.Timestamp(f"{TARGET_DATE} {TARGET_TIME}:00")
    matching = multi_day_rth.index[multi_day_rth["timestamp_et"] == target_ts]
    if len(matching) == 0:
        print(f"!! 12:20 bar not found in multi_day_rth")
        # Try fuzzy match
        candidates = multi_day_rth[multi_day_rth["timestamp_et"].dt.date == pd.Timestamp(TARGET_DATE).date()]
        print(f"5/13 bars in multi_day_rth: {len(candidates)}")
        if not candidates.empty:
            print(candidates[["timestamp_et"]].head(20))
        return
    bar_idx = int(matching[-1])
    bar = multi_day_rth.iloc[bar_idx]
    print(f"Found 12:20 bar at index {bar_idx}: {bar['timestamp_et']}, O={bar['open']:.2f}, C={bar['close']:.2f}")
    print()

    # Call sniper_watcher
    print("Calling sniper_watcher.detect_sniper_setup()...")
    try:
        signal = detect_sniper_setup(bar, bar_idx, multi_day_rth)
        if signal is None:
            print("  -> NO SIGNAL (returned None)")
        else:
            print(f"  -> SIGNAL FIRED:")
            print(f"     watcher_name: {signal.watcher_name}")
            print(f"     setup_name: {signal.setup_name}")
            print(f"     direction: {signal.direction}")
            print(f"     entry_price: {signal.entry_price:.4f}")
            print(f"     stop_price: {signal.stop_price:.4f}")
            print(f"     tp1_price: {signal.tp1_price:.4f}")
            print(f"     runner_price: {signal.runner_price:.4f}")
            print(f"     confidence: {signal.confidence}")
            print(f"     reason: {signal.reason}")
            print(f"     metadata level_label: {signal.metadata.get('level_label')}")
            print(f"     metadata level_price: {signal.metadata.get('level_price')}")
            print(f"     metadata level_stars: {signal.metadata.get('level_stars')}")
            print(f"     metadata vol_ratio: {signal.metadata.get('vol_ratio'):.2f}")
            print(f"     metadata body_dollars: {signal.metadata.get('body_dollars'):.2f}")
    except Exception as e:
        print(f"  -> EXCEPTION: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
