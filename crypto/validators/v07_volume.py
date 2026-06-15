"""v07_volume — validate volume-confirmation primitives."""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar import Bar
from crypto.lib.bar_reader import closed_bars_only
from crypto.lib.data_sources import fetch_bars, now_utc
from crypto.lib.volume import is_volume_confirmed, rolling_mean_volume, volume_ratio


def _bar(t, vol) -> Bar:
    return Bar(open_time=t, open=100, high=100.5, low=99.5, close=100.0, volume=vol,
               granularity_seconds=300, source="synthetic")


def run_offline() -> dict:
    base = datetime(2026, 5, 16, 0, 0, 0, tzinfo=timezone.utc)
    def t(i): return base + timedelta(seconds=300 * i)
    results = []

    # T1: rolling mean of constant volume == constant
    bars = [_bar(t(i), 100.0) for i in range(30)]
    m = rolling_mean_volume(bars, length=10)
    results.append(("T1_rolling_constant", abs(m[-1] - 100.0) < 1e-9, f"m[-1]={m[-1]}"))

    # T2: ratio of doubled volume bar to baseline = 2.0
    bars = [_bar(t(i), 100.0) for i in range(20)] + [_bar(t(20), 200.0)]
    r = volume_ratio(bars, length=20)
    results.append(("T2_ratio_2x", abs(r[-1] - 2.0) < 1e-9, f"ratio={r[-1]}"))

    # T3: ratio of half-volume bar = 0.5
    bars = [_bar(t(i), 100.0) for i in range(20)] + [_bar(t(20), 50.0)]
    r = volume_ratio(bars, length=20)
    results.append(("T3_ratio_half", abs(r[-1] - 0.5) < 1e-9, f"ratio={r[-1]}"))

    # T4: is_volume_confirmed at 1.5x threshold
    bars = [_bar(t(i), 100.0) for i in range(20)]
    confirmed_at_150 = is_volume_confirmed(_bar(t(20), 150.0), bars, threshold=1.5, length=20)
    confirmed_at_149 = is_volume_confirmed(_bar(t(20), 149.0), bars, threshold=1.5, length=20)
    results.append(("T4_threshold_150", confirmed_at_150 is True and confirmed_at_149 is False,
                    f"150={confirmed_at_150} 149={confirmed_at_149}"))

    # T5: ratio NaN before warmup
    bars = [_bar(t(i), 100.0) for i in range(10)]
    r = volume_ratio(bars, length=20)
    results.append(("T5_nan_before_warmup", all(math.isnan(v) for v in r), "all NaN"))

    # T6: window excludes current bar (prevent double-count)
    bars = [_bar(t(i), 100.0) for i in range(20)] + [_bar(t(20), 10000.0)]
    r = volume_ratio(bars, length=20)
    # If included, mean would be skewed up by 10000/21=476, ratio=21. If excluded properly, ratio=100.
    results.append(("T6_excludes_current", abs(r[-1] - 100.0) < 1e-9, f"ratio={r[-1]}"))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note[:80]} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live(symbol, granularity_seconds, count) -> dict:
    now = now_utc()
    raw = fetch_bars("coinbase", symbol, granularity_seconds, count)
    series = closed_bars_only(raw, now)
    bars = list(series)
    if len(bars) < 25:
        return {"mode": "live", "pass": False, "reason": "not_enough_bars"}

    ratios = volume_ratio(bars, length=20)
    valid = [r for r in ratios if not math.isnan(r)]
    above_15 = sum(1 for r in valid if r >= 1.5)
    above_20 = sum(1 for r in valid if r >= 2.0)
    above_30 = sum(1 for r in valid if r >= 3.0)
    return {
        "mode": "live",
        "closed_bars": len(bars),
        "ratios_valid": len(valid),
        "ratio_min": min(valid) if valid else None,
        "ratio_max": max(valid) if valid else None,
        "ratio_mean": sum(valid) / len(valid) if valid else None,
        "bars_above_1_5x": above_15,
        "bars_above_2x": above_20,
        "bars_above_3x": above_30,
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
        print(f"\n=== LIVE === {args.symbol} {args.granularity}s on {live.get('closed_bars','?')} bars")
        if live.get("pass"):
            print(f"  ratio range:  {live['ratio_min']:.2f} - {live['ratio_max']:.2f}  mean: {live['ratio_mean']:.2f}")
            print(f"  >= 1.5x: {live['bars_above_1_5x']}  >= 2x: {live['bars_above_2x']}  >= 3x: {live['bars_above_3x']}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))

    return 0 if sc.get("offline", {}).get("all_pass", True) else 1


if __name__ == "__main__":
    sys.exit(main())
