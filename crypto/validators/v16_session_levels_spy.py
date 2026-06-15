"""v16_session_levels_spy — SPY-specific session-structure level validator.

Validates `crypto.lib.session_levels_spy` against historical SPY 5m CSVs.
Unlike the crypto-asset validators which run live 24/7, this runs against
historical SPY data (since live SPY is closed most of the time).

Offline tests:
  T1: synthetic bars across one trading day -> premarket H/L correct
  T2: RTH_open is the open price of the 09:30 5m bar
  T3: IB_high/low covers first 30 min of RTH only
  T4: filter_by_session correctly partitions bars

Live test (against historical CSV):
  Pick the most recent trading day in the SPY CSV, compute session levels,
  verify they're sensible (PMH > PML, IBH > IBL, etc.) and report.

  This is the FINAL primitive for the SPY engine's chart-reading muscle.
  Once ratified, heartbeat.md should reference these levels in addition to
  the carry/prior-day levels it already uses.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar import Bar, BarSeries
from crypto.lib.session_levels_spy import (
    SessionLevels, compute_session_levels, filter_by_session,
    session_levels_as_level_objects,
)


def _bar(ts_utc: datetime, o: float, h: float, l: float, c: float, v: float = 1.0) -> Bar:
    return Bar(open_time=ts_utc, open=o, high=h, low=l, close=c, volume=v,
               granularity_seconds=300, source="synthetic")


def run_offline() -> dict:
    # Build one trading day of synthetic bars covering 04:00-16:00 ET
    # ET is UTC-4 in May. So 04:00 ET = 08:00 UTC, 16:00 ET = 20:00 UTC.
    target = date(2026, 5, 14)
    base = datetime(2026, 5, 14, 8, 0, 0, tzinfo=timezone.utc)  # 04:00 ET

    # Premarket (04:00-09:30 ET = 08:00-13:30 UTC): 11 bars at 5m each
    # 09:30 ET = 13:30 UTC; 16:00 ET = 20:00 UTC; 78 5m bars in RTH
    bars = []
    # Premarket — climbing 745 -> 747
    for i in range(66):  # 04:00-09:30 ET = 5.5 hours = 66 5m bars
        t = base + timedelta(seconds=300 * i)
        p = 745 + (i / 66) * 2  # 745 -> 747
        bars.append(_bar(t, p, p + 0.2, p - 0.2, p + 0.1))
    # RTH — wider range
    rth_start = datetime(2026, 5, 14, 13, 30, 0, tzinfo=timezone.utc)  # 09:30 ET
    for i in range(78):  # 78 5m bars in RTH
        t = rth_start + timedelta(seconds=300 * i)
        # Vol higher in IB (first 6 bars)
        p = 747 + (i / 78) * 3  # climbing toward 750
        h = p + (0.5 if i < 6 else 0.3)  # higher highs in IB
        l = p - (0.5 if i < 6 else 0.3)
        bars.append(_bar(t, p, h, l, p + 0.15))

    sl = compute_session_levels(bars, target)
    results = []

    # T1: premarket high computed correctly
    expected_pmh = 745 + (65 / 66) * 2 + 0.2  # last premarket bar high
    results.append(("T1_premarket_high", sl.premarket_high is not None and abs(sl.premarket_high - expected_pmh) < 0.1,
                    f"pmh={sl.premarket_high:.4f}  expected~{expected_pmh:.4f}"))

    # T2: RTH open is the open of the 09:30 ET bar
    results.append(("T2_rth_open_matches_0930", sl.rth_open is not None and abs(sl.rth_open - 747.0) < 0.01,
                    f"rth_open={sl.rth_open}"))

    # T3: IB high covers first 30 min (6 bars) of RTH
    # IB bars 0-5: each has high = p + 0.5
    # Last IB bar (i=5): p = 747 + (5/78)*3 = 747.192, h = 747.692
    expected_ibh = 747 + (5/78)*3 + 0.5
    results.append(("T3_ib_high_first_30min", sl.ib_high is not None and abs(sl.ib_high - expected_ibh) < 0.1,
                    f"ib_high={sl.ib_high:.4f}  expected~{expected_ibh:.4f}"))

    # T4: IB has exactly 6 bars
    ib_bars = filter_by_session(bars, target, "ib")
    results.append(("T4_ib_has_6_bars", len(ib_bars) == 6, f"ib={len(ib_bars)} bars"))

    # T5: Premarket has 66 bars
    pm_bars = filter_by_session(bars, target, "premarket")
    results.append(("T5_premarket_66_bars", len(pm_bars) == 66, f"pm={len(pm_bars)} bars"))

    # T6: RTH has 78 bars
    rth_bars = filter_by_session(bars, target, "rth")
    results.append(("T6_rth_78_bars", len(rth_bars) == 78, f"rth={len(rth_bars)} bars"))

    # T7: Empty session
    empty_sl = compute_session_levels([], target)
    results.append(("T7_empty_session", empty_sl.premarket_high is None and empty_sl.rth_open is None,
                    "all None on empty input"))

    # T8: session_levels_as_level_objects yields 5 levels (PMH, PML, RTH_open, IBH, IBL)
    levels = session_levels_as_level_objects(sl)
    results.append(("T8_5_levels_produced", len(levels) == 5, f"got {len(levels)} levels"))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note[:80]} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live(csv_path: Path, target_date_str: str | None = None) -> dict:
    """Run against historical SPY CSV. Pick the most recent trading day if not specified."""
    df = pd.read_csv(csv_path)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    df = df.sort_values("timestamp_et").reset_index(drop=True)

    if target_date_str is None:
        target_date = df["timestamp_et"].dt.date.max()
    else:
        target_date = datetime.fromisoformat(target_date_str).date()

    bars = []
    for _, row in df.iterrows():
        ts_et = row["timestamp_et"]
        ts_utc = ts_et.tz_convert("UTC") if ts_et.tzinfo is not None else ts_et.tz_localize("UTC")
        bars.append(Bar(
            open_time=ts_utc.to_pydatetime(), open=float(row["open"]), high=float(row["high"]),
            low=float(row["low"]), close=float(row["close"]), volume=float(row["volume"]),
            granularity_seconds=300, source="spy_csv",
        ))

    sl = compute_session_levels(bars, target_date)
    pm_bars = filter_by_session(bars, target_date, "premarket")
    rth_bars = filter_by_session(bars, target_date, "rth")
    ib_bars = filter_by_session(bars, target_date, "ib")

    # Sanity checks
    sane = True
    notes = []
    if sl.premarket_high is not None and sl.premarket_low is not None:
        if sl.premarket_high < sl.premarket_low:
            sane = False
            notes.append("PMH < PML (invariant violated)")
    if sl.ib_high is not None and sl.ib_low is not None:
        if sl.ib_high < sl.ib_low:
            sane = False
            notes.append("IBH < IBL (invariant violated)")

    return {
        "mode": "live",
        "target_date": target_date.isoformat(),
        "premarket_bars": len(pm_bars),
        "rth_bars": len(rth_bars),
        "ib_bars": len(ib_bars),
        "session_levels": {
            "premarket_high": sl.premarket_high,
            "premarket_low": sl.premarket_low,
            "rth_open": sl.rth_open,
            "ib_high": sl.ib_high,
            "ib_low": sl.ib_low,
        },
        "sanity_passed": sane,
        "notes": notes,
        "pass": sane,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    p.add_argument("--spy-csv", type=Path, default=Path("backtest/data/spy_5m_2025-01-01_2026-05-15.csv"))
    p.add_argument("--target-date", default=None)
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    sc = {}
    if args.mode in ("offline", "both"):
        sc["offline"] = run_offline()
        print(f"=== OFFLINE === {sc['offline']['passed']}/{sc['offline']['total']} pass")
        for t in sc["offline"]["tests"]:
            print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:30s} {t['note']}")
    if args.mode in ("live", "both"):
        sc["live"] = run_live(args.spy_csv, args.target_date)
        live = sc["live"]
        print(f"\n=== LIVE === SPY {live['target_date']}")
        print(f"  premarket bars: {live['premarket_bars']}")
        print(f"  RTH bars:       {live['rth_bars']}")
        print(f"  IB bars:        {live['ib_bars']}")
        print(f"  session levels:")
        for k, v in live["session_levels"].items():
            print(f"    {k:<20s} {v}")
        print(f"  sanity:         {live['sanity_passed']}")
        if live["notes"]:
            for n in live["notes"]:
                print(f"    - {n}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))

    all_ok = True
    if "offline" in sc and not sc["offline"]["all_pass"]:
        all_ok = False
    if "live" in sc and not sc["live"]["pass"]:
        all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
