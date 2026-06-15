"""v04_candlesticks — validate candlestick pattern detectors.

Offline:
  Hand-crafted bars where each pattern SHOULD fire (positive examples) and
  similar bars where each pattern should NOT fire (negative examples).

Live:
  Run all detectors on 100 live BTC 5m closed bars; report what fired + bar timestamps.
  This is a SANITY check (not a correctness gate) — output is informational.
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
from crypto.lib.candlesticks import (
    detect_all,
    detect_bearish_engulfing,
    detect_bullish_engulfing,
    detect_doji,
    detect_hammer,
    detect_inside_bar,
    detect_shooting_star,
)
from crypto.lib.data_sources import fetch_bars, now_utc


def _bar(open_t: datetime, o: float, h: float, l: float, c: float, v: float = 1.0) -> Bar:
    return Bar(
        open_time=open_t, open=o, high=h, low=l, close=c, volume=v,
        granularity_seconds=300, source="synthetic",
    )


def run_offline() -> dict:
    base = datetime(2026, 5, 16, 0, 0, 0, tzinfo=timezone.utc)
    def t(i: int) -> datetime:
        return base + timedelta(seconds=300 * i)

    results = []

    # Bullish engulfing: red bar then green bar whose body engulfs prior body
    bars = [_bar(t(0), 100, 101, 98, 99), _bar(t(1), 98.5, 102, 98.5, 101.5)]
    hits = detect_bullish_engulfing(bars)
    results.append(("T1_bullish_engulfing_fires", len(hits) == 1 and hits[0].bar_index == 1, str(hits)))

    # Bullish engulfing should NOT fire when bodies don't engulf
    bars = [_bar(t(0), 100, 101, 98, 99), _bar(t(1), 99.5, 100, 99, 99.8)]
    hits = detect_bullish_engulfing(bars)
    results.append(("T2_bullish_engulfing_skip", len(hits) == 0, str(hits)))

    # Bearish engulfing
    bars = [_bar(t(0), 100, 102, 99.5, 101), _bar(t(1), 101.5, 101.5, 98, 99)]
    hits = detect_bearish_engulfing(bars)
    results.append(("T3_bearish_engulfing_fires", len(hits) == 1, str(hits)))

    # Doji: tiny body, large range
    bars = [_bar(t(0), 100, 102, 98, 100.05)]
    hits = detect_doji(bars)
    results.append(("T4_doji_fires", len(hits) == 1, str(hits)))

    # Doji should NOT fire on a full-body bar
    bars = [_bar(t(0), 100, 102, 98, 101.5)]
    hits = detect_doji(bars)
    results.append(("T5_doji_skip_full_body", len(hits) == 0, str(hits)))

    # Hammer: small body at top, near-zero upper wick, long lower wick (>=2x body)
    # open=100.50 close=100.55 (body=0.05), high=100.55 (upper=0), low=99.0 (lower=1.50)
    bars = [_bar(t(0), 100.50, 100.55, 99.0, 100.55)]
    hits = detect_hammer(bars)
    results.append(("T6_hammer_fires", len(hits) == 1, str(hits)))

    # Shooting star: small body at bottom, near-zero lower wick, long upper wick
    bars = [_bar(t(0), 100.50, 102.0, 100.50, 100.55)]
    hits = detect_shooting_star(bars)
    results.append(("T7_shooting_star_fires", len(hits) == 1, str(hits)))

    # Inside bar: current bar's range within prior
    bars = [_bar(t(0), 100, 103, 97, 102), _bar(t(1), 100.5, 101.5, 99, 100)]
    hits = detect_inside_bar(bars)
    results.append(("T8_inside_bar_fires", len(hits) == 1, str(hits)))

    # Inside bar should NOT fire when current bar's high exceeds prior high
    bars = [_bar(t(0), 100, 103, 97, 102), _bar(t(1), 100, 104, 99, 102)]
    hits = detect_inside_bar(bars)
    results.append(("T9_inside_bar_skip", len(hits) == 0, str(hits)))

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
    hits = detect_all(bars)

    by_pattern: dict[str, list[str]] = {}
    for h in hits:
        by_pattern.setdefault(h.pattern, []).append(bars[h.bar_index].open_time.isoformat())

    return {
        "mode": "live",
        "symbol": symbol,
        "granularity_seconds": granularity_seconds,
        "closed_bars": len(bars),
        "total_hits": len(hits),
        "hits_by_pattern": {p: {"count": len(ts), "open_times": ts[-5:]} for p, ts in by_pattern.items()},
        "pass": True,  # informational only
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    p.add_argument("--symbol", default="BTC-USD")
    p.add_argument("--granularity", type=int, default=300)
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    sc = {}
    if args.mode in ("offline", "both"):
        sc["offline"] = run_offline()
        print(f"=== OFFLINE === {sc['offline']['passed']}/{sc['offline']['total']} pass")
        for t in sc["offline"]["tests"]:
            mark = "PASS" if t["pass"] else "FAIL"
            print(f"  [{mark}] {t['name']:35s} {t['note']}")
    if args.mode in ("live", "both"):
        sc["live"] = run_live(args.symbol, args.granularity, args.count)
        print(f"\n=== LIVE === {args.symbol} {args.granularity}s on {sc['live']['closed_bars']} closed bars")
        print(f"  total pattern hits: {sc['live']['total_hits']}")
        for pat, info in sc["live"]["hits_by_pattern"].items():
            print(f"  [{pat:20s}] count={info['count']}  last5={info['open_times']}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))
        print(f"\nscorecard written to {args.json_out}")

    return 0 if sc.get("offline", {}).get("all_pass", True) else 1


if __name__ == "__main__":
    sys.exit(main())
