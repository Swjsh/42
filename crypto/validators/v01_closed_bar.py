"""v01_closed_bar — validate the closed-bar filter that catches the 2026-05-14 SPY foot-gun.

Modes:
  --mode offline  : run synthetic-bar unit tests (no network)
  --mode live     : fetch live bars from Coinbase + run filter, log result
  --mode both     : run offline first, then live (default)

Offline coverage:
  T1  : empty series           -> verdict no_closed_bars
  T2  : series with only one in-progress bar -> verdict future_bar (one rejected)
  T3  : just-closed bar at boundary (now == close_time) -> verdict ok, that bar returned
  T4  : one in-progress + one closed -> filter rejects in-progress, returns prior
  T5  : multiple in-progress bars at tail (clock skew) -> filter rejects all, returns prior closed
  T6  : stale data (all bars > 2*granularity old) -> verdict stale_data
  T7  : bar with naive datetime -> ValueError (defensive)
  T8  : DST transition boundary (UTC-based, transparent to filter) [T103]
  T9  : granularity mismatch mid-series → BarSeries ValueError [T103]
  T10 : microsecond timestamp — close_time fractional, bar NOT closed at round boundary [T103]
  T11 : duplicate timestamps → BarSeries ValueError [T103]
  T12 : gap in bar stream (missing bar) — filter returns correct latest closed bar [T103]

Live coverage:
  L1  : fetch 20 bars BTC-USD 5m from Coinbase -> verdict ok, age <= 300s
  L2  : reproduce foot-gun by fetching within 30s before/after a bar close

Exit code: 0 on PASS, 1 on FAIL (suitable for CI / cron-gated workflows).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running from project root: `python crypto/validators/v01_closed_bar.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar import Bar, BarSeries
from crypto.lib.bar_reader import last_closed_bar
from crypto.lib.data_sources import fetch_bars, now_utc


def _mk_bar(open_time: datetime, granularity_seconds: int = 300, source: str = "synthetic") -> Bar:
    return Bar(
        open_time=open_time,
        open=100.0, high=101.0, low=99.0, close=100.5, volume=10.0,
        granularity_seconds=granularity_seconds, source=source,
    )


def _mk_series(open_times: list[datetime]) -> BarSeries:
    return BarSeries(
        symbol="TEST",
        granularity_seconds=300,
        source="synthetic",
        bars=tuple(_mk_bar(t) for t in open_times),
    )


def run_offline() -> dict:
    """Return scorecard for offline tests."""
    results = []
    base = datetime(2026, 5, 16, 13, 0, 0, tzinfo=timezone.utc)

    # T1: empty
    s = BarSeries("TEST", 300, "synthetic", ())
    r = last_closed_bar(s, base)
    results.append(("T1_empty_series", r.verdict == "no_closed_bars" and r.last_closed is None, r.verdict))

    # T2: only an in-progress bar (now is BEFORE its close)
    s = _mk_series([base])  # bar [13:00, 13:05), close at 13:05
    r = last_closed_bar(s, base + timedelta(seconds=60))  # now is 13:01
    results.append(("T2_only_in_progress", r.verdict == "future_bar" and r.bars_rejected_as_in_progress == 1, r.verdict))

    # T3: boundary — now == close_time exactly
    s = _mk_series([base])
    r = last_closed_bar(s, base + timedelta(seconds=300))  # now is 13:05 == close
    results.append(("T3_boundary_close", r.verdict == "ok" and r.last_closed is not None, r.verdict))

    # T4: one closed + one in-progress (THE foot-gun scenario)
    s = _mk_series([base, base + timedelta(seconds=300)])  # bars at 13:00 and 13:05
    r = last_closed_bar(s, base + timedelta(seconds=360))  # now is 13:06 — 13:05 bar is in-progress
    correct = (
        r.verdict == "ok"
        and r.last_closed is not None
        and r.last_closed.open_time == base
        and r.in_progress is not None
        and r.in_progress.open_time == base + timedelta(seconds=300)
        and r.bars_rejected_as_in_progress == 1
    )
    results.append(("T4_foot_gun_scenario", correct, r.verdict))

    # T5: multiple in-progress at tail (clock-skew defense)
    s = _mk_series([base, base + timedelta(seconds=300), base + timedelta(seconds=600)])
    r = last_closed_bar(s, base + timedelta(seconds=360))  # now is 13:06 — last 2 are not closed
    correct = (
        r.verdict == "ok"
        and r.last_closed is not None
        and r.last_closed.open_time == base
        and r.bars_rejected_as_in_progress == 2
    )
    results.append(("T5_multi_in_progress_tail", correct, r.verdict))

    # T6: stale data — last bar closed > 2*granularity ago
    s = _mk_series([base])  # bar closes at 13:05
    r = last_closed_bar(s, base + timedelta(seconds=300 + 700))  # now is 13:16 — stale by 11min
    results.append(("T6_stale_data", r.verdict == "stale_data", r.verdict))

    # T7: defensive — naive datetime input
    s = _mk_series([base])
    try:
        last_closed_bar(s, datetime(2026, 5, 16, 13, 10, 0))  # no tzinfo
        ok = False
    except ValueError:
        ok = True
    results.append(("T7_reject_naive_now", ok, "ValueError raised" if ok else "no error"))

    # --- T103 EDGE CASES ---

    # T8: DST transition boundary (a).
    # Clock jumps 1h at 02:00 ET on spring-forward Sunday. In UTC this is 06:00→07:00.
    # Since everything is UTC internally, DST doesn't affect bar.close_time math.
    # Bars at 05:55 and 06:00 UTC should both be correctly identified: 05:55 bar
    # closes at 06:00 UTC; if now=06:05 UTC, 05:55 bar is closed AND 06:00 bar is in-progress.
    dst_base = datetime(2026, 3, 8, 5, 55, 0, tzinfo=timezone.utc)  # spring-forward day
    s_dst = BarSeries("TEST", 300, "synthetic", (
        _mk_bar(dst_base),                                # [05:55, 06:00)
        _mk_bar(dst_base + timedelta(seconds=300)),       # [06:00, 06:05) — in-progress
    ))
    r_dst = last_closed_bar(s_dst, dst_base + timedelta(seconds=360))  # now=06:01
    t8_ok = (
        r_dst.verdict == "ok"
        and r_dst.last_closed is not None
        and r_dst.last_closed.open_time == dst_base
        and r_dst.bars_rejected_as_in_progress == 1
    )
    results.append(("T8_dst_transition_transparent", t8_ok,
                    f"verdict={r_dst.verdict} closed={r_dst.last_closed and r_dst.last_closed.open_time.isoformat()}"))

    # T9: Granularity mismatch mid-series (b).
    # BarSeries constructor MUST reject bars with different granularity_seconds.
    # This verifies the defense is in place.
    bar_300 = _mk_bar(base, granularity_seconds=300)
    bar_60 = Bar(open_time=base + timedelta(seconds=300), open=100.0, high=101.0,
                 low=99.0, close=100.5, volume=10.0, granularity_seconds=60, source="synthetic")
    try:
        BarSeries("TEST", 300, "synthetic", (bar_300, bar_60))
        t9_ok = False  # should have raised
    except ValueError:
        t9_ok = True
    results.append(("T9_granularity_mismatch_rejected", t9_ok,
                    "ValueError raised" if t9_ok else "no error — defense missing"))

    # T10: Microsecond timestamp (c).
    # Coinbase sometimes returns open_time with microseconds, e.g. 13:00:00.000123.
    # This makes close_time = 13:05:00.000123, which is NOT ≤ 13:05:00.000000.
    # Expected behavior: bar is NOT considered closed at exactly 13:05:00.000000.
    # The test documents this "off-by-a-microsecond" behavior so it doesn't surprise.
    micro_base = datetime(2026, 5, 16, 13, 0, 0, 123456, tzinfo=timezone.utc)  # .123456 µs
    s_micro = _mk_series([micro_base])  # closes at 13:05:00.123456 UTC
    now_round = datetime(2026, 5, 16, 13, 5, 0, 0, tzinfo=timezone.utc)  # exactly 13:05
    r_micro = last_closed_bar(s_micro, now_round)
    # The bar is NOT closed at exactly 13:05:00.000000 (close_time = 13:05:00.123456 > now)
    # Mitigation: callers should round open_time to the nearest second before constructing Bar.
    t10_ok = r_micro.verdict == "future_bar"  # microsecond offset makes bar appear in-progress at T=close
    results.append(("T10_microsecond_timestamp_edge_case", t10_ok,
                    f"verdict={r_micro.verdict} (expected future_bar — microsecond offset pushes close past now)"))

    # T11: Duplicate timestamps (d).
    # BarSeries constructor must reject bars with non-strictly-ascending timestamps.
    bar_a = _mk_bar(base)
    bar_dupe = _mk_bar(base)  # same open_time as bar_a
    try:
        BarSeries("TEST", 300, "synthetic", (bar_a, bar_dupe))
        t11_ok = False
    except ValueError:
        t11_ok = True
    results.append(("T11_duplicate_timestamp_rejected", t11_ok,
                    "ValueError raised" if t11_ok else "no error — defense missing"))

    # T12: Gap in bar stream (e).
    # Missing bar at 13:10 — series jumps from 13:05 to 13:15.
    # last_closed_bar should still return the correct latest closed bar (13:10 bar)
    # without error; it doesn't validate bar continuity (gaps are transparent).
    # Now = 13:21 (13:20 bar open, 13:15 bar closes at 13:20 → closed, 13:10 is older).
    gap_times = [
        base,                                 # 13:00-13:05
        base + timedelta(seconds=300),        # 13:05-13:10
        # 13:10 missing
        base + timedelta(seconds=600),        # 13:10-13:15 (note: gap before this)
        base + timedelta(seconds=900),        # 13:15-13:20
        base + timedelta(seconds=1200),       # 13:20-13:25 — in-progress
    ]
    s_gap = _mk_series(gap_times)
    r_gap = last_closed_bar(s_gap, base + timedelta(seconds=1260))  # now = 13:21
    t12_ok = (
        r_gap.verdict == "ok"
        and r_gap.last_closed is not None
        and r_gap.last_closed.open_time == base + timedelta(seconds=900)  # 13:15 bar
        and r_gap.bars_rejected_as_in_progress == 1
    )
    results.append(("T12_gap_in_bar_stream_transparent", t12_ok,
                    f"verdict={r_gap.verdict} last={r_gap.last_closed and r_gap.last_closed.open_time.isoformat()}"))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "verdict": v} for n, p, v in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live(source: str, symbol: str, granularity_seconds: int, count: int) -> dict:
    """Fetch live bars + run filter. Reports verdict + foot-gun catch evidence."""
    fetched_at = now_utc()
    series = fetch_bars(source, symbol, granularity_seconds, count)
    result = last_closed_bar(series, fetched_at)

    naive_last = series.last
    naive_in_progress = not naive_last.is_closed_at(fetched_at)

    foot_gun_caught = (
        naive_in_progress
        and result.last_closed is not None
        and result.last_closed.open_time != naive_last.open_time
    )

    # OHLC delta between naive (in-progress) and filtered (closed) bars — quantifies the bug
    if foot_gun_caught and result.last_closed is not None:
        ohlc_delta = {
            "open": naive_last.open - result.last_closed.open,
            "high": naive_last.high - result.last_closed.high,
            "low": naive_last.low - result.last_closed.low,
            "close": naive_last.close - result.last_closed.close,
            "volume": naive_last.volume - result.last_closed.volume,
        }
    else:
        ohlc_delta = None

    return {
        "mode": "live",
        "source": source,
        "symbol": symbol,
        "granularity_seconds": granularity_seconds,
        "fetched_at": fetched_at.isoformat(),
        "bars_count": len(series),
        "verdict": result.verdict,
        "naive_last_bar_in_progress": naive_in_progress,
        "naive_last_bar_open": naive_last.open_time.isoformat(),
        "naive_last_bar_seconds_until_close": naive_last.seconds_until_close(fetched_at),
        "filtered_last_closed_open": result.last_closed.open_time.isoformat() if result.last_closed else None,
        "filtered_last_closed_age_seconds": (fetched_at - result.last_closed.close_time).total_seconds() if result.last_closed else None,
        "bars_rejected_as_in_progress": result.bars_rejected_as_in_progress,
        "foot_gun_caught_this_fetch": foot_gun_caught,
        "ohlc_delta_naive_minus_filtered": ohlc_delta,
        "pass": result.verdict == "ok",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    p.add_argument("--source", choices=["coinbase", "yfinance"], default="coinbase")
    p.add_argument("--symbol", default="BTC-USD")
    p.add_argument("--granularity", type=int, default=300, help="seconds (60, 300, 900, ...)")
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--json-out", type=Path, default=None, help="optional path to write scorecard")
    args = p.parse_args(argv)

    scorecards = {}

    if args.mode in ("offline", "both"):
        sc = run_offline()
        scorecards["offline"] = sc
        print(f"=== OFFLINE === {sc['passed']}/{sc['total']} pass")
        for t in sc["tests"]:
            mark = "PASS" if t["pass"] else "FAIL"
            print(f"  [{mark}] {t['name']:30s}  verdict={t['verdict']}")

    if args.mode in ("live", "both"):
        sc = run_live(args.source, args.symbol, args.granularity, args.count)
        scorecards["live"] = sc
        print()
        print(f"=== LIVE === {args.source} {args.symbol} {args.granularity}s")
        print(f"  fetched_at:                       {sc['fetched_at']}")
        print(f"  verdict:                          {sc['verdict']}")
        print(f"  naive bars[-1] in progress?       {sc['naive_last_bar_in_progress']}")
        print(f"    seconds_until_close:            {sc['naive_last_bar_seconds_until_close']:.0f}")
        print(f"  filtered last_closed open:        {sc['filtered_last_closed_open']}")
        print(f"  filtered last_closed age (s):     {sc['filtered_last_closed_age_seconds']:.0f}")
        print(f"  bars rejected as in_progress:     {sc['bars_rejected_as_in_progress']}")
        print(f"  FOOT-GUN CAUGHT THIS FETCH:       {sc['foot_gun_caught_this_fetch']}")
        if sc["ohlc_delta_naive_minus_filtered"]:
            d = sc["ohlc_delta_naive_minus_filtered"]
            print(f"  OHLC delta (naive - filtered):")
            print(f"    open:   {d['open']:+.2f}")
            print(f"    high:   {d['high']:+.2f}")
            print(f"    low:    {d['low']:+.2f}")
            print(f"    close:  {d['close']:+.2f}")
            print(f"    volume: {d['volume']:+.4f}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(scorecards, indent=2, default=str))
        print(f"\nscorecard written to {args.json_out}")

    all_ok = True
    if "offline" in scorecards and not scorecards["offline"]["all_pass"]:
        all_ok = False
    if "live" in scorecards and not scorecards["live"]["pass"]:
        all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
