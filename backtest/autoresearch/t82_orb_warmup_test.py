"""T82 — ORB warmup-fix prototype validation.

Validates the proposed fix BEFORE patching watcher_live.py:
  Hypothesis: walking today's bars sequentially BEFORE the latest-bar call
  builds up stateful detector state machines. The latest bar then fires
  correctly (instead of seeing fresh state every time).

Test scenario: 2026-05-14 RTH bars. Today's ORB fires at 10:30 (per T80 diag).
Verify:
  PROD-CURRENT (no warmup): bar at 10:30 fires None
  PROD-T82 (with warmup): bar at 10:30 fires ORB_RETEST_LONG medium

If both scenarios match expectation, T82 fix is validated.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "backtest"))

from lib.watchers.orb_watcher import detect_orb_break, _orb_state


def reset_state():
    for k in list(_orb_state.keys()):
        del _orb_state[k]


def main():
    today_csv = REPO / "backtest" / "data" / "spy_5m_2026-05-08_2026-05-14.csv"
    df = pd.read_csv(today_csv)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    if df["timestamp_et"].dt.tz is not None:
        df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)

    today_rth = df[
        (df["timestamp_et"].dt.date == pd.Timestamp("2026-05-14").date())
        & (df["timestamp_et"].dt.time >= dt.time(9, 30))
        & (df["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    today_rth = today_rth[today_rth["volume"] > 0].reset_index(drop=True)
    print(f"Today RTH bars: {len(today_rth)}")

    # Find the 10:30 bar idx (where ORB fires per T80)
    target_ts = pd.Timestamp("2026-05-14 10:30:00")
    target_idx = int(today_rth.index[today_rth["timestamp_et"] == target_ts][0])
    print(f"Target bar (10:30 ORB entry): idx={target_idx}")

    vol_baseline = 500_000.0  # rough baseline

    # === SCENARIO A — PROD-CURRENT (no warmup): just call on 10:30 with fresh state ===
    print()
    print("=== SCENARIO A: PROD-CURRENT (no warmup, fresh state) ===")
    reset_state()
    bar = today_rth.iloc[target_idx]
    sig = detect_orb_break(bar, today_rth, target_idx, vol_baseline)
    print(f"  Result: {sig}")
    print(f"  _orb_state after call: {dict(_orb_state)}")

    # === SCENARIO B — T82 PROPOSED (warmup all prior bars, then call on 10:30) ===
    print()
    print("=== SCENARIO B: T82 PROPOSED (warmup bars 0..29, then 10:30) ===")
    reset_state()
    # Warmup pass — walk bars 0 through target_idx-1
    for warmup_idx in range(target_idx):
        warmup_bar = today_rth.iloc[warmup_idx]
        try:
            _ = detect_orb_break(warmup_bar, today_rth, warmup_idx, vol_baseline)
        except Exception as e:
            print(f"    warmup err at {warmup_idx}: {e}")
    print(f"  After warmup: _orb_state = {dict(_orb_state)}")
    # Now call on 10:30
    sig = detect_orb_break(bar, today_rth, target_idx, vol_baseline)
    print(f"  Result on 10:30 bar: {sig}")
    if sig is not None:
        print(f"    -> setup={sig.setup_name} direction={sig.direction} confidence={sig.confidence}")
        print(f"    -> reason={sig.reason[:120]}")

    # === SCENARIO C — overhead measurement: how long does warmup take? ===
    print()
    print("=== SCENARIO C: Overhead measurement (78 bars) ===")
    reset_state()
    import time
    t0 = time.time()
    for warmup_idx in range(len(today_rth)):
        warmup_bar = today_rth.iloc[warmup_idx]
        try:
            _ = detect_orb_break(warmup_bar, today_rth, warmup_idx, vol_baseline)
        except Exception:
            pass
    elapsed_ms = (time.time() - t0) * 1000
    print(f"  78-bar full warmup: {elapsed_ms:.1f}ms")
    print(f"  Per-bar: {elapsed_ms / len(today_rth):.2f}ms")
    print(f"  Acceptable? {'YES' if elapsed_ms < 1000 else 'NO — too slow'}")


if __name__ == "__main__":
    main()
