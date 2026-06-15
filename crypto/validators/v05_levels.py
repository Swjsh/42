"""v05_levels — validate key-level detection and level-event classification.

Offline tests:
  Synthetic bar series with known levels; assert detection + event labels.

Live test:
  Pull 1d of BTC 5m, compute round numbers + prior-period H/L,
  classify each closed bar's interaction with the nearest level,
  report event frequency (sanity check, not a hard pass/fail).
"""
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
from crypto.lib.levels import (
    Level,
    LevelEvent,
    LevelKind,
    classify_bar_at_level,
    nearest_levels,
    pivot_points,
    prior_period_levels,
    round_number_levels,
)


def _bar(t: datetime, o, h, l, c, v=1.0) -> Bar:
    return Bar(open_time=t, open=o, high=h, low=l, close=c, volume=v,
               granularity_seconds=300, source="synthetic")


def run_offline() -> dict:
    base = datetime(2026, 5, 16, 0, 0, 0, tzinfo=timezone.utc)
    def t(i): return base + timedelta(seconds=300 * i)

    results = []

    # T1: prior_period_levels finds the right high/low
    bars = [
        _bar(t(0), 100, 105, 99, 104),
        _bar(t(1), 104, 110, 103, 108),  # high of window = 110
        _bar(t(2), 108, 109, 95, 96),    # low of window = 95
        _bar(t(3), 96, 102, 96, 100),    # current — excluded
    ]
    lvls = prior_period_levels(bars, lookback=3)
    hi = next((L for L in lvls if L.kind == LevelKind.PRIOR_PERIOD_HIGH), None)
    lo = next((L for L in lvls if L.kind == LevelKind.PRIOR_PERIOD_LOW), None)
    results.append(("T1_prior_period_high", hi is not None and hi.price == 110, f"hi={hi}"))
    results.append(("T2_prior_period_low", lo is not None and lo.price == 95, f"lo={lo}"))

    # T3: round_number_levels around 80000 BTC, increment 1000
    lvls = round_number_levels(80050, 1000, radius=2)
    prices = sorted(L.price for L in lvls)
    results.append(("T3_round_numbers", prices == [78000, 79000, 80000, 81000, 82000], f"prices={prices}"))

    # T4: ★★★ on the 10k multiple
    eighty_k = next(L for L in lvls if L.price == 80000)
    results.append(("T4_round_strength_star3", eighty_k.strength == 3, f"strength={eighty_k.strength}"))

    # T5: classify_bar_at_level — RECLAIM
    level = Level(price=100, kind=LevelKind.ROUND_NUMBER, strength=2)
    bar = _bar(t(0), 99.0, 101.5, 98.8, 101.0)
    ev = classify_bar_at_level(bar, level, min_margin_pct=0.5)
    results.append(("T5_reclaim", ev == LevelEvent.RECLAIM, f"event={ev}"))

    # T6: classify_bar_at_level — BREAK
    bar = _bar(t(0), 101.0, 101.2, 98.5, 99.0)
    ev = classify_bar_at_level(bar, level, min_margin_pct=0.5)
    results.append(("T6_break", ev == LevelEvent.BREAK, f"event={ev}"))

    # T7: classify_bar_at_level — REJECT (touched up, closed below)
    bar = _bar(t(0), 99.0, 100.5, 98.8, 99.2)
    ev = classify_bar_at_level(bar, level, min_margin_pct=0.5)
    results.append(("T7_reject_below", ev == LevelEvent.REJECT, f"event={ev}"))

    # T8: HOLD (touched but closed in narrow band)
    bar = _bar(t(0), 100.1, 100.5, 99.6, 100.2)
    ev = classify_bar_at_level(bar, level, min_margin_pct=1.0)
    results.append(("T8_hold", ev == LevelEvent.HOLD, f"event={ev}"))

    # T9: pivot_points sanity (P = (H+L+C)/3)
    bars = [_bar(t(0), 100, 110, 90, 105)]
    pp = pivot_points(bars)
    p_level = next(L for L in pp if L.kind == LevelKind.PIVOT_P)
    expected_p = (110 + 90 + 105) / 3
    results.append(("T9_pivot_p", abs(p_level.price - expected_p) < 1e-9, f"p={p_level.price}"))

    # T10: nearest_levels returns top-N closest
    lvls = [Level(p, LevelKind.ROUND_NUMBER, 1) for p in [78000, 79000, 80000, 81000, 82000]]
    near = nearest_levels(80100, lvls, n=3)
    near_prices = sorted(L.price for L in near)
    results.append(("T10_nearest_top3", near_prices == [79000, 80000, 81000], f"near={near_prices}"))

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
        return {"mode": "live", "pass": False, "reason": "no_bars"}

    last = bars[-1]
    rounds = round_number_levels(last.close, increment=1000, radius=2)
    prior_8h = prior_period_levels(bars, lookback=min(96, len(bars) - 1))  # 8h of 5m bars
    all_levels = rounds + prior_8h
    near = nearest_levels(last.close, all_levels, n=5)

    event_counts: dict[str, int] = {}
    for bar in bars:
        for level in all_levels:
            ev = classify_bar_at_level(bar, level, min_margin_pct=0.05)
            if ev != LevelEvent.NONE:
                key = f"{level.kind.value}:{ev.value}"
                event_counts[key] = event_counts.get(key, 0) + 1

    return {
        "mode": "live",
        "symbol": symbol,
        "granularity_seconds": granularity_seconds,
        "closed_bars": len(bars),
        "last_close": last.close,
        "nearest_5_levels": [{"price": L.price, "kind": L.kind.value, "strength": L.strength, "label": L.label} for L in near],
        "event_counts": event_counts,
        "pass": True,
    }


def main(argv: list[str] | None = None) -> int:
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
        print(f"\n=== LIVE === {args.symbol} {args.granularity}s")
        live = sc["live"]
        print(f"  closed_bars: {live['closed_bars']}  last_close: {live['last_close']}")
        print(f"  nearest 5 levels:")
        for L in live["nearest_5_levels"]:
            print(f"    {L['price']:>10.2f}  ({L['kind']:>20s} s{L['strength']}) {L['label']}")
        print(f"  level event counts:")
        for k, v in sorted(live["event_counts"].items(), key=lambda x: -x[1])[:10]:
            print(f"    {k:>40s}: {v}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))

    return 0 if sc.get("offline", {}).get("all_pass", True) else 1


if __name__ == "__main__":
    sys.exit(main())
