"""v06_trendlines — validate swing-point detection and trendline fitting."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar import Bar
from crypto.lib.bar_reader import closed_bars_only
from crypto.lib.data_sources import fetch_bars, now_utc
from crypto.lib.trendlines import find_swing_points, fit_trendline, trendline_touches


def _bar(t: datetime, o, h, l, c) -> Bar:
    return Bar(open_time=t, open=o, high=h, low=l, close=c, volume=1.0,
               granularity_seconds=300, source="synthetic")


def run_offline() -> dict:
    base = datetime(2026, 5, 16, 0, 0, 0, tzinfo=timezone.utc)
    def t(i): return base + timedelta(seconds=300 * i)
    results = []

    # T1: V-shape — should find 1 swing low at the center
    prices = [105, 103, 101, 99, 97, 95, 97, 99, 101, 103, 105]
    bars = [_bar(t(i), p, p + 0.5, p - 0.5, p) for i, p in enumerate(prices)]
    swings = find_swing_points(bars, window=2)
    lows = [s for s in swings if s.kind == "swing_low"]
    results.append(("T1_v_shape_swing_low", len(lows) == 1 and lows[0].bar_index == 5, f"swings={swings}"))

    # T2: ascending highs — swing highs at peaks
    prices = [100, 102, 101, 103, 102, 104, 103, 105, 104, 106]
    bars = [_bar(t(i), p, p + 0.5, p - 0.5, p) for i, p in enumerate(prices)]
    swings = find_swing_points(bars, window=1)
    highs = [s for s in swings if s.kind == "swing_high"]
    results.append(("T2_ascending_peaks", len(highs) >= 3, f"n_highs={len(highs)}"))

    # T3: fit_trendline through 2 known points yields correct slope
    # Build bars with swing highs at t=0 and t=10 with values 100 and 110
    bars = [_bar(t(i), 100, 100 + i, 99 + i, 100 + i) for i in range(11)]
    swings = find_swing_points(bars, window=3)  # too strict — should be empty
    # Use synthetic swings directly
    from crypto.lib.trendlines import SwingPoint
    sp1 = SwingPoint(0, t(0).timestamp(), 100, "swing_high")
    sp2 = SwingPoint(10, t(10).timestamp(), 110, "swing_high")
    line = fit_trendline([sp1, sp2], "resistance")
    # slope per second: (110-100) / (10 * 300s) = 0.00333...
    expected_slope = (110 - 100) / (10 * 300)
    results.append(("T3_fit_two_points", line is not None and abs(line.slope - expected_slope) < 1e-9, f"slope={line.slope if line else None}"))

    # T4: project trendline forward
    if line:
        future_t = t(20).timestamp()
        projected = line.price_at(future_t)
        # linear: 100 at t(0)=0s offset, slope 0.00333/s, t(20) is 6000s later → 100 + 20 = 120
        results.append(("T4_project_forward", abs(projected - 120.0) < 1e-6, f"projected={projected}"))

    # T5: insufficient points → None
    results.append(("T5_single_point_none", fit_trendline([sp1], "resistance") is None, "None expected"))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note[:80]} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live(symbol: str, granularity_seconds: int, count: int) -> dict:
    now = now_utc()
    raw = fetch_bars("coinbase", symbol, granularity_seconds, count)
    series = closed_bars_only(raw, now)
    bars = list(series)
    if not bars:
        return {"mode": "live", "pass": False}

    swings = find_swing_points(bars, window=3)
    resistance = fit_trendline(swings, "resistance")
    support = fit_trendline(swings, "support")

    r_touches = trendline_touches(bars, resistance, tolerance_pct=0.10) if resistance else 0
    s_touches = trendline_touches(bars, support, tolerance_pct=0.10) if support else 0

    last_t = bars[-1].open_time.timestamp()
    last_close = bars[-1].close

    return {
        "mode": "live",
        "closed_bars": len(bars),
        "swing_highs": sum(1 for s in swings if s.kind == "swing_high"),
        "swing_lows": sum(1 for s in swings if s.kind == "swing_low"),
        "resistance_slope_per_hr": resistance.slope * 3600 if resistance else None,
        "resistance_projected_at_last_bar": resistance.price_at(last_t) if resistance else None,
        "resistance_touches": r_touches,
        "support_slope_per_hr": support.slope * 3600 if support else None,
        "support_projected_at_last_bar": support.price_at(last_t) if support else None,
        "support_touches": s_touches,
        "last_close": last_close,
        "pass": True,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    p.add_argument("--symbol", default="BTC-USD")
    p.add_argument("--granularity", type=int, default=300)
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    sc = {}
    if args.mode in ("offline", "both"):
        sc["offline"] = run_offline()
        print(f"=== OFFLINE === {sc['offline']['passed']}/{sc['offline']['total']} pass")
        for t in sc["offline"]["tests"]:
            mark = "PASS" if t["pass"] else "FAIL"
            print(f"  [{mark}] {t['name']:30s} {t['note']}")
    if args.mode in ("live", "both"):
        sc["live"] = run_live(args.symbol, args.granularity, args.count)
        live = sc["live"]
        print(f"\n=== LIVE === {args.symbol} {args.granularity}s on {live['closed_bars']} bars")
        print(f"  swing_highs={live['swing_highs']}  swing_lows={live['swing_lows']}")
        if live.get("resistance_projected_at_last_bar"):
            print(f"  resistance slope/hr: {live['resistance_slope_per_hr']:+.2f}  projected@last: {live['resistance_projected_at_last_bar']:.2f}  touches: {live['resistance_touches']}")
        if live.get("support_projected_at_last_bar"):
            print(f"  support slope/hr:    {live['support_slope_per_hr']:+.2f}  projected@last: {live['support_projected_at_last_bar']:.2f}  touches: {live['support_touches']}")
        print(f"  last close:          {live['last_close']:.2f}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))

    return 0 if sc.get("offline", {}).get("all_pass", True) else 1


if __name__ == "__main__":
    sys.exit(main())
