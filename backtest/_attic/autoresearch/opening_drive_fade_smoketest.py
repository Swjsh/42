"""Smoke test for OPENING_DRIVE_FADE detector + evaluator.

Verifies:
  1. Default combo evaluates without crashing
  2. Output dict has the expected schema fields (matches overnight_grinder)
  3. Per-day reset_state isolates days
  4. A custom synthetic stall sequence triggers detect_opening_drive_fade

Run:
    cd backtest
    python -m autoresearch.opening_drive_fade_smoketest
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from lib.opening_drive_fade_detector import (  # noqa: E402
    OpeningDriveFadeParams,
    detect_opening_drive_fade,
    reset_all_state,
    reset_state,
)
from autoresearch.opening_drive_fade_evaluator import (  # noqa: E402
    OpeningDriveFadeCombo,
    evaluate_opening_drive_fade_combo,
)


def _synth_bar(ts: dt.datetime, o: float, h: float, l: float, c: float, v: float) -> pd.Series:
    return pd.Series({"timestamp_et": ts, "open": o, "high": h, "low": l, "close": c, "volume": v})


def smoketest_detector_hod_fade() -> bool:
    """Build a synthetic 5m bar sequence that should trigger HOD fade.

    Sequence (all in [09:35, 11:00]):
      09:35 thrust UP bar (body $0.50, vol 1_000_000): HOD = 100.50
      09:40 stall bar 1: high 100.48, low 100.40, vol 600_000 (< 0.70 * 1M = 700k)
      09:45 stall bar 2: high 100.47, low 100.40, vol 500_000
      09:50 entry bar: close 100.35 (within $0.20 of HOD on fade side)

    Expected: signal fires at 09:50 with direction='short', extreme=100.50.
    """
    reset_all_state()
    params = OpeningDriveFadeParams(
        thrust_bar_min_dollars=0.40,
        stall_bars_required=2,
        stall_proximity_dollars=0.20,
        vol_decline_ratio=0.70,
        time_window_start=dt.time(9, 35),
        time_window_end=dt.time(10, 30),
        entry_window_end=dt.time(11, 0),
    )

    date = dt.date(2026, 5, 13)
    bars = [
        _synth_bar(dt.datetime.combine(date, dt.time(9, 35)), 100.00, 100.50, 100.00, 100.50, 1_000_000),
        _synth_bar(dt.datetime.combine(date, dt.time(9, 40)), 100.45, 100.48, 100.40, 100.42, 600_000),
        _synth_bar(dt.datetime.combine(date, dt.time(9, 45)), 100.42, 100.47, 100.40, 100.41, 500_000),
        _synth_bar(dt.datetime.combine(date, dt.time(9, 50)), 100.41, 100.45, 100.30, 100.35, 700_000),
    ]
    df = pd.DataFrame(bars)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])

    fired_signal = None
    for i, bar in df.iterrows():
        sig = detect_opening_drive_fade(bar, i, df, params)
        if sig is not None:
            fired_signal = sig
            break

    if fired_signal is None:
        print("FAIL: HOD-fade synthetic sequence did not fire any signal")
        return False
    if fired_signal.direction != "short":
        print(f"FAIL: expected direction='short', got '{fired_signal.direction}'")
        return False
    if abs(fired_signal.extreme_price - 100.50) > 0.01:
        print(f"FAIL: expected extreme=100.50, got {fired_signal.extreme_price}")
        return False
    print(f"PASS: HOD-fade fired at {fired_signal.timestamp.time()} direction={fired_signal.direction} "
          f"extreme={fired_signal.extreme_price:.2f} stall_bars={fired_signal.stall_bar_count}")
    return True


def smoketest_detector_lod_fade() -> bool:
    """Symmetric LOD-fade test -> direction='long' (calls)."""
    reset_all_state()
    params = OpeningDriveFadeParams()

    date = dt.date(2026, 5, 13)
    bars = [
        _synth_bar(dt.datetime.combine(date, dt.time(9, 35)), 100.00, 100.00, 99.50, 99.50, 1_000_000),  # thrust down
        _synth_bar(dt.datetime.combine(date, dt.time(9, 40)), 99.55, 99.60, 99.52, 99.58, 600_000),  # stall 1
        _synth_bar(dt.datetime.combine(date, dt.time(9, 45)), 99.58, 99.60, 99.53, 99.59, 500_000),  # stall 2
        _synth_bar(dt.datetime.combine(date, dt.time(9, 50)), 99.59, 99.70, 99.55, 99.65, 700_000),  # entry
    ]
    df = pd.DataFrame(bars)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])

    fired_signal = None
    for i, bar in df.iterrows():
        sig = detect_opening_drive_fade(bar, i, df, params)
        if sig is not None:
            fired_signal = sig
            break

    if fired_signal is None:
        print("FAIL: LOD-fade synthetic sequence did not fire")
        return False
    if fired_signal.direction != "long":
        print(f"FAIL: expected direction='long', got '{fired_signal.direction}'")
        return False
    print(f"PASS: LOD-fade fired at {fired_signal.timestamp.time()} direction={fired_signal.direction} "
          f"extreme={fired_signal.extreme_price:.2f} stall_bars={fired_signal.stall_bar_count}")
    return True


def smoketest_state_isolation() -> bool:
    """reset_state(date) clears that day's state without touching others."""
    reset_all_state()
    params = OpeningDriveFadeParams()
    date1 = dt.date(2026, 5, 1)
    date2 = dt.date(2026, 5, 4)

    # Fire HOD-fade on date1
    bars_d1 = [
        _synth_bar(dt.datetime.combine(date1, dt.time(9, 35)), 100.00, 100.50, 100.00, 100.50, 1_000_000),
        _synth_bar(dt.datetime.combine(date1, dt.time(9, 40)), 100.45, 100.48, 100.40, 100.42, 600_000),
        _synth_bar(dt.datetime.combine(date1, dt.time(9, 45)), 100.42, 100.47, 100.40, 100.41, 500_000),
        _synth_bar(dt.datetime.combine(date1, dt.time(9, 50)), 100.41, 100.45, 100.30, 100.35, 700_000),
    ]
    df1 = pd.DataFrame(bars_d1)
    df1["timestamp_et"] = pd.to_datetime(df1["timestamp_et"])
    fired_d1 = False
    for i, bar in df1.iterrows():
        if detect_opening_drive_fade(bar, i, df1, params):
            fired_d1 = True
            break
    if not fired_d1:
        print("FAIL: date1 setup didn't fire (state isolation prereq)")
        return False

    # Now feed date2 bars: should fire (fresh state)
    bars_d2 = [
        _synth_bar(dt.datetime.combine(date2, dt.time(9, 35)), 200.00, 200.50, 200.00, 200.50, 1_000_000),
        _synth_bar(dt.datetime.combine(date2, dt.time(9, 40)), 200.45, 200.48, 200.40, 200.42, 600_000),
        _synth_bar(dt.datetime.combine(date2, dt.time(9, 45)), 200.42, 200.47, 200.40, 200.41, 500_000),
        _synth_bar(dt.datetime.combine(date2, dt.time(9, 50)), 200.41, 200.45, 200.30, 200.35, 700_000),
    ]
    df2 = pd.DataFrame(bars_d2)
    df2["timestamp_et"] = pd.to_datetime(df2["timestamp_et"])
    fired_d2 = False
    for i, bar in df2.iterrows():
        if detect_opening_drive_fade(bar, i, df2, params):
            fired_d2 = True
            break
    if not fired_d2:
        print("FAIL: date2 did not fire after date1 — state pollution suspected")
        return False

    # reset_state(date1) should not break date1 re-eval ability (state cleared)
    reset_state(date1.isoformat())
    fired_d1_again = False
    for i, bar in df1.iterrows():
        if detect_opening_drive_fade(bar, i, df1, params):
            fired_d1_again = True
            break
    if not fired_d1_again:
        print("FAIL: date1 didn't re-fire after reset_state")
        return False

    print("PASS: state isolation works (date1, date2, date1-after-reset all fired independently)")
    return True


def smoketest_evaluator_default_combo() -> bool:
    """Evaluator runs without crashing on default combo + returns expected schema."""
    reset_all_state()
    default = OpeningDriveFadeCombo()
    combo_dict = {f: getattr(default, f) for f in default.__dataclass_fields__}
    result = evaluate_opening_drive_fade_combo(combo_dict)

    if "error" in result:
        print(f"FAIL: evaluator crashed with: {result['error']}")
        print(result.get("trace", "")[:1000])
        return False

    required_keys = {
        "combo", "by_day", "winners_capture", "losers_added", "edge_capture",
        "wide_pnl", "wide_n_trades", "wide_wr", "top5_pct",
        "quarter_pnl", "positive_quarters", "quarter_count",
        "max_drawdown", "passed_floors", "regressions",
    }
    missing = required_keys - set(result.keys())
    if missing:
        print(f"FAIL: evaluator result missing keys: {missing}")
        return False

    print(
        f"PASS: evaluator default combo: "
        f"wide_pnl=${result['wide_pnl']:.0f} "
        f"wide_n={result['wide_n_trades']} wr={result['wide_wr']:.2f} "
        f"edge=${result['edge_capture']:.0f} "
        f"passed_floors={result['passed_floors']} "
        f"regressions={result['regressions']}"
    )
    return True


def main() -> int:
    tests = [
        ("detector_hod_fade", smoketest_detector_hod_fade),
        ("detector_lod_fade", smoketest_detector_lod_fade),
        ("state_isolation", smoketest_state_isolation),
        ("evaluator_default_combo", smoketest_evaluator_default_combo),
    ]
    failed = 0
    for name, fn in tests:
        print(f"--- {name} ---")
        try:
            ok = fn()
        except Exception as exc:
            import traceback
            print(f"FAIL: {name} raised: {exc!r}")
            traceback.print_exc()
            ok = False
        if not ok:
            failed += 1
    print()
    print(f"=== {len(tests) - failed}/{len(tests)} passed ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
