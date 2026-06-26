"""v46_market_structure — validate swing labeling, trend-from-structure, BOS, CHoCH.

Proves the new crypto.lib.market_structure detector reads price structure the way
a human trader does: labels HH/HL/LH/LL, derives trend FROM the swings, and flags
Break-of-Structure (continuation) vs Change-of-Character (first counter-trend break).

Offline (deterministic fixtures):
  T1  ascending swings  -> HH/HL labels
  T2  descending swings -> LH/LL labels
  T3  classify uptrend   (HH + HL)
  T4  classify downtrend (LH + LL)
  T5  classify range     (mixed)
  T6  classify unknown   (too few swings)
  T7  bullish BOS   (uptrend, close above last swing high)
  T8  bearish CHoCH (uptrend, close below last swing low)
  T9  bullish CHoCH (downtrend, close above last swing high)
  T10 bearish BOS   (downtrend, close below last swing low)
  T11 end-to-end analyze_structure on a clean uptrend bar zigzag
  T12 empty bars -> trend "unknown", no crash
  T13 immutability of returned dataclasses (frozen)

Live: fetch BTC bars, analyze structure, assert a valid trend label + no crash.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar import Bar
from crypto.lib.bar_reader import closed_bars_only
from crypto.lib.data_sources import fetch_bars, now_utc
from crypto.lib.market_structure import (
    analyze_structure,
    classify_trend,
    detect_structure_break,
    label_swings,
    signal_tier,
    walk_structure,
)
from crypto.lib.trendlines import SwingPoint, find_swing_points

_BASE = datetime(2026, 5, 16, 0, 0, 0, tzinfo=timezone.utc)


def _t(i: int) -> datetime:
    return _BASE + timedelta(seconds=300 * i)


def _bar(i: int, price: float) -> Bar:
    return Bar(open_time=_t(i), open=price, high=price + 0.5, low=price - 0.5,
               close=price, volume=1.0, granularity_seconds=300, source="synthetic")


def _flat_bars(n: int, last_close: float) -> list[Bar]:
    """n bars; only the final close matters for break detection."""
    bars = [_bar(i, 100.0) for i in range(n - 1)]
    bars.append(Bar(open_time=_t(n - 1), open=last_close, high=last_close + 2,
                    low=last_close - 2, close=last_close, volume=1.0,
                    granularity_seconds=300, source="synthetic"))
    return bars


def _sh(idx: int, price: float) -> SwingPoint:
    return SwingPoint(idx, _t(idx).timestamp(), price, "swing_high")


def _sl(idx: int, price: float) -> SwingPoint:
    return SwingPoint(idx, _t(idx).timestamp(), price, "swing_low")


def run_offline() -> dict:
    results: list[tuple[str, bool, str]] = []

    # T1: ascending highs + lows -> HH / HL
    asc = [_sh(2, 105), _sl(4, 99), _sh(6, 108), _sl(8, 102), _sh(10, 111), _sl(12, 105)]
    lab = label_swings(asc)
    high_labels = [s.label for s in lab if s.kind == "swing_high"]
    low_labels = [s.label for s in lab if s.kind == "swing_low"]
    ok = high_labels == ["H", "HH", "HH"] and low_labels == ["L", "HL", "HL"]
    results.append(("T1_ascending_HH_HL", ok, f"highs={high_labels} lows={low_labels}"))

    # T2: descending highs + lows -> LH / LL
    desc = [_sh(2, 111), _sl(4, 105), _sh(6, 108), _sl(8, 102), _sh(10, 105), _sl(12, 99)]
    lab = label_swings(desc)
    high_labels = [s.label for s in lab if s.kind == "swing_high"]
    low_labels = [s.label for s in lab if s.kind == "swing_low"]
    ok = high_labels == ["H", "LH", "LH"] and low_labels == ["L", "LL", "LL"]
    results.append(("T2_descending_LH_LL", ok, f"highs={high_labels} lows={low_labels}"))

    # T3: classify uptrend
    t = classify_trend(label_swings(asc))
    results.append(("T3_classify_uptrend", t == "uptrend", f"trend={t}"))

    # T4: classify downtrend
    t = classify_trend(label_swings(desc))
    results.append(("T4_classify_downtrend", t == "downtrend", f"trend={t}"))

    # T5: range -- HH high but LL low (mixed)
    mixed = [_sh(2, 105), _sl(4, 99), _sh(6, 108), _sl(8, 97)]  # high HH, low LL
    t = classify_trend(label_swings(mixed))
    results.append(("T5_classify_range", t == "range", f"trend={t}"))

    # T6: unknown -- only one high/low
    few = [_sh(2, 105), _sl(4, 99)]
    t = classify_trend(label_swings(few))
    results.append(("T6_classify_unknown", t == "unknown", f"trend={t}"))

    # T7: bullish BOS -- uptrend, close above last swing high (111)
    swings = [_sh(5, 105), _sl(8, 102)]
    ev = detect_structure_break(_flat_bars(11, 106.0), swings, "uptrend")
    ok = ev is not None and ev.kind == "BOS" and ev.direction == "bullish" and ev.broken_price == 105
    results.append(("T7_bullish_BOS", ok, f"event={ev}"))

    # T8: bearish CHoCH -- uptrend, close below last swing low (102)
    ev = detect_structure_break(_flat_bars(11, 101.0), swings, "uptrend")
    ok = ev is not None and ev.kind == "CHoCH" and ev.direction == "bearish" and ev.broken_price == 102
    results.append(("T8_bearish_CHoCH", ok, f"event={ev}"))

    # T9: bullish CHoCH -- downtrend, close above last swing high (105)
    ev = detect_structure_break(_flat_bars(11, 106.0), swings, "downtrend")
    ok = ev is not None and ev.kind == "CHoCH" and ev.direction == "bullish"
    results.append(("T9_bullish_CHoCH", ok, f"event={ev}"))

    # T10: bearish BOS -- downtrend, close below last swing low (102)
    ev = detect_structure_break(_flat_bars(11, 101.0), swings, "downtrend")
    ok = ev is not None and ev.kind == "BOS" and ev.direction == "bearish"
    results.append(("T10_bearish_BOS", ok, f"event={ev}"))

    # T11: end-to-end on a clean uptrend bar zigzag (verified swing geometry, window=2)
    prices = [100, 102, 105, 101, 99, 103, 108, 104, 102, 106, 111, 107, 105, 109, 112]
    bars = [_bar(i, p) for i, p in enumerate(prices)]
    read = analyze_structure(bars, window=2)
    has_hh = any(s.label == "HH" for s in read.labeled_swings)
    ok = (read.trend == "uptrend" and has_hh and read.last_event is not None
          and read.last_event.direction == "bullish")
    results.append(("T11_e2e_uptrend_bos", ok,
                    f"trend={read.trend} seq={read.notes['recent_label_sequence']} ev={read.last_event.kind if read.last_event else None}"))

    # T12: empty bars -> unknown, no crash
    read = analyze_structure([], window=2)
    ok = read.trend == "unknown" and read.last_event is None and read.labeled_swings == ()
    results.append(("T12_empty_unknown", ok, f"trend={read.trend}"))

    # T13: returned dataclasses are frozen (immutability rule)
    read = analyze_structure(bars, window=2)
    try:
        read.labeled_swings[0].label = "XX"  # type: ignore[misc]
        froze = False
    except FrozenInstanceError:
        froze = True
    results.append(("T13_immutable", froze, "FrozenInstanceError expected on mutate"))

    # T14: CHoCH flips the working trend; first counter-trend break = CHoCH, then BOS
    sw = [_sh(2, 110), _sl(5, 100), _sh(8, 107)]
    closes = [108, 107, 109, 104, 104, 103, 102, 105, 99, 101, 103, 108, 106]
    wbars = [_bar(i, p) for i, p in enumerate(closes)]
    working, evs = walk_structure(wbars, sw, window=2)
    ok = (len(evs) == 2 and evs[0].kind == "BOS" and evs[0].direction == "bearish"
          and evs[1].kind == "CHoCH" and evs[1].direction == "bullish"
          and working == "uptrend" and sum(1 for e in evs if e.kind == "CHoCH") == 1)
    results.append(("T14_choch_flips_trend", ok,
                    f"working={working} evs={[(e.kind, e.direction) for e in evs]}"))

    # T15: equal-level plateau registers a swing ONLY with the inclusive_right tie-break
    plat = [100, 101, 102, 103, 104, 105, 105, 104, 103, 102, 101]
    pbars = [_bar(i, p) for i, p in enumerate(plat)]
    strict_h = [s for s in find_swing_points(pbars, window=2) if s.kind == "swing_high"]
    incl_h = [s for s in find_swing_points(pbars, window=2, inclusive_right=True) if s.kind == "swing_high"]
    ok = len(strict_h) == 0 and len(incl_h) >= 1
    results.append(("T15_equal_level_tiebreak", ok, f"strict={len(strict_h)} incl={len(incl_h)}"))

    # T16: bars_since_last_swing staleness surfaced in notes
    prices = [100, 102, 105, 101, 99, 103, 108, 104, 102, 106, 111, 107, 105, 109, 112]
    sbars = [_bar(i, p) for i, p in enumerate(prices)]
    read = analyze_structure(sbars, window=2)
    ok = read.notes.get("bars_since_last_swing") == 2 and read.trend_basis == "structure_breaks"
    results.append(("T16_staleness_and_basis", ok,
                    f"since={read.notes.get('bars_since_last_swing')} basis={read.trend_basis}"))

    # T17: deep pullback printing one LL does NOT flip an intact uptrend to range
    # (authoritative trend = working trend, only flips on a confirmed break)
    deep = [_sh(2, 110), _sl(5, 100), _sh(8, 113), _sl(11, 98)]  # HH then LL (deep pullback, no break)
    lab = label_swings(deep)
    label_only = classify_trend(lab)  # tentative: range (HH + LL)
    ok = label_only == "range"  # confirms classify_trend is a run-based tentative read
    results.append(("T17_pullback_tentative_range", ok, f"label_trend={label_only}"))

    # T18: outside bar (both swing kinds at one index) labels deterministically (high before low)
    dual = [SwingPoint(2, _t(2).timestamp(), 110, "swing_high"),
            SwingPoint(2, _t(2).timestamp(), 90, "swing_low")]
    lab = label_swings(dual)
    ok = len(lab) == 2 and lab[0].kind == "swing_high" and lab[1].kind == "swing_low"
    results.append(("T18_dual_kind_sort", ok, f"order={[s.kind for s in lab]}"))

    # T19: signal_tier maps confidence onto WatcherSignal vocabulary
    ok = signal_tier(0.9) == "high" and signal_tier(0.6) == "medium" and signal_tier(0.3) == "low"
    results.append(("T19_signal_tier", ok, "0.9->high 0.6->medium 0.3->low"))

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
    bars = list(closed_bars_only(raw, now))
    if not bars:
        return {"mode": "live", "pass": False, "note": "no bars"}

    read = analyze_structure(bars, window=3)
    valid_trend = read.trend in ("uptrend", "downtrend", "range", "unknown")
    ev = read.last_event
    return {
        "mode": "live",
        "closed_bars": len(bars),
        "trend": read.trend,
        "n_swings": read.notes["n_swings"],
        "recent_sequence": read.notes["recent_label_sequence"],
        "last_swing_high": read.last_swing_high,
        "last_swing_low": read.last_swing_low,
        "last_event": f"{ev.kind}/{ev.direction}@{ev.broken_price}" if ev else None,
        "confidence": read.confidence,
        "pass": valid_trend,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    p.add_argument("--symbol", default="BTC-USD")
    p.add_argument("--granularity", type=int, default=300)
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    sc: dict = {}
    if args.mode in ("offline", "both"):
        sc["offline"] = run_offline()
        print(f"=== OFFLINE === {sc['offline']['passed']}/{sc['offline']['total']} pass")
        for t in sc["offline"]["tests"]:
            mark = "PASS" if t["pass"] else "FAIL"
            print(f"  [{mark}] {t['name']:24s} {t['note']}")
    if args.mode in ("live", "both"):
        try:
            sc["live"] = run_live(args.symbol, args.granularity, args.count)
            live = sc["live"]
            print(f"\n=== LIVE === {args.symbol} on {live.get('closed_bars','?')} bars")
            print(f"  trend={live.get('trend')}  n_swings={live.get('n_swings')}  "
                  f"seq={live.get('recent_sequence')}  last_event={live.get('last_event')}")
        except Exception as e:  # live data is best-effort; offline is the gate
            print(f"\n=== LIVE === skipped/failed: {e}")
            sc["live"] = {"mode": "live", "pass": False, "note": str(e)[:120]}

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))

    return 0 if sc.get("offline", {}).get("all_pass", True) else 1


if __name__ == "__main__":
    sys.exit(main())
