"""v03_indicators — validate RSI / EMA / ATR / VWAP math.

Three layers of validation:
  1. Invariants    : RSI in [0,100], VWAP between min(L) and max(H), no NaN after warmup.
  2. Hand-computed : EMA on a constant series equals that constant once seeded.
                     RSI on a monotonic-up series approaches 100; monotonic-down approaches 0.
  3. Live sanity   : Run on 100 live BTC 5m bars; assert values are sensible.

This is NOT a regression test against TV's exact values — that requires reading
indicator values from a TV pane (use mcp__tradingview__data_get_study_values
during interactive sessions). v03 ensures the math is internally correct.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar import Bar, BarSeries
from crypto.lib.bar_reader import closed_bars_only
from crypto.lib.data_sources import fetch_bars, now_utc
from crypto.lib.indicators import atr, ema, rsi, true_range, vwap


def _flat_bars(n: int, price: float = 100.0, volume: float = 1.0) -> list[Bar]:
    base = datetime(2026, 5, 16, 0, 0, 0, tzinfo=timezone.utc)
    return [
        Bar(
            open_time=base + timedelta(seconds=300 * i),
            open=price, high=price + 0.1, low=price - 0.1, close=price, volume=volume,
            granularity_seconds=300, source="synthetic",
        )
        for i in range(n)
    ]


def _trending_bars(n: int, start: float = 100.0, step: float = 1.0) -> list[Bar]:
    base = datetime(2026, 5, 16, 0, 0, 0, tzinfo=timezone.utc)
    return [
        Bar(
            open_time=base + timedelta(seconds=300 * i),
            open=start + step * i,
            high=start + step * i + 0.5,
            low=start + step * i - 0.5,
            close=start + step * i + 0.4,
            volume=1.0, granularity_seconds=300, source="synthetic",
        )
        for i in range(n)
    ]


def run_offline() -> dict:
    results = []

    # T1: EMA on flat series equals the price (after seed)
    bars = _flat_bars(50, price=100.0)
    e = ema(bars, length=10)
    last = e[-1]
    results.append(("T1_ema_flat_series", abs(last - 100.0) < 1e-9, f"ema[-1]={last}"))

    # T2: RSI on monotonic-up series approaches 100
    bars = _trending_bars(60, start=100.0, step=1.0)
    r = rsi(bars, length=14)
    last = r[-1]
    results.append(("T2_rsi_up_trend", last > 99.0, f"rsi[-1]={last:.4f}"))

    # T3: RSI on monotonic-down series approaches 0
    bars = _trending_bars(60, start=200.0, step=-1.0)
    r = rsi(bars, length=14)
    last = r[-1]
    results.append(("T3_rsi_down_trend", last < 1.0, f"rsi[-1]={last:.4f}"))

    # T4: RSI bounded [0,100] always
    bars = _trending_bars(100, start=100.0, step=0.5)
    r = rsi(bars, length=14)
    all_bounded = all(math.isnan(v) or (0.0 <= v <= 100.0) for v in r)
    results.append(("T4_rsi_bounded", all_bounded, "all values in [0,100] or NaN"))

    # T5: ATR on flat series is small (~0.2 = high-low width)
    bars = _flat_bars(50)
    a = atr(bars, length=14)
    last = a[-1]
    results.append(("T5_atr_flat_series", abs(last - 0.2) < 1e-6, f"atr[-1]={last:.6f}"))

    # T6: VWAP equals the constant price on a flat series
    bars = _flat_bars(50, price=100.0, volume=1.0)
    v = vwap(bars)
    last = v[-1]
    # vwap typical_price = (100.1 + 99.9 + 100.0) / 3 = 100.0
    results.append(("T6_vwap_flat", abs(last - 100.0) < 1e-9, f"vwap[-1]={last}"))

    # T7: true_range first bar is high-low
    bars = _flat_bars(3)
    tr = true_range(bars)
    expected_first = bars[0].high - bars[0].low
    results.append(("T7_tr_first_bar", abs(tr[0] - expected_first) < 1e-12, f"tr[0]={tr[0]}"))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live(symbol: str, granularity_seconds: int, count: int) -> dict:
    now = now_utc()
    raw = fetch_bars("coinbase", symbol, granularity_seconds, count)
    series = closed_bars_only(raw, now)
    bars = list(series)

    r14 = rsi(bars, length=14)
    e20 = ema(bars, length=20)
    a14 = atr(bars, length=14)
    vw = vwap(bars)

    last_close = bars[-1].close if bars else None

    sane_rsi = all(math.isnan(v) or (0.0 <= v <= 100.0) for v in r14)
    nan_after_warmup_rsi = any(math.isnan(v) for v in r14[20:])  # should not have NaN past warmup
    nan_after_warmup_ema = any(math.isnan(v) for v in e20[25:])

    high_max = max(b.high for b in bars) if bars else float("nan")
    low_min = min(b.low for b in bars) if bars else float("nan")
    vwap_in_range = (low_min <= vw[-1] <= high_max) if bars else False

    return {
        "mode": "live",
        "symbol": symbol,
        "granularity_seconds": granularity_seconds,
        "closed_bars": len(bars),
        "last_close": last_close,
        "rsi_14_last": r14[-1] if bars else None,
        "ema_20_last": e20[-1] if bars else None,
        "atr_14_last": a14[-1] if bars else None,
        "vwap_last": vw[-1] if bars else None,
        "high_max": high_max,
        "low_min": low_min,
        "checks": {
            "rsi_bounded_0_100": sane_rsi,
            "rsi_no_nan_after_warmup": not nan_after_warmup_rsi,
            "ema_no_nan_after_warmup": not nan_after_warmup_ema,
            "vwap_in_lo_hi_range": vwap_in_range,
        },
        "pass": sane_rsi and not nan_after_warmup_rsi and not nan_after_warmup_ema and vwap_in_range,
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
            print(f"  [{mark}] {t['name']:30s}  {t['note']}")
    if args.mode in ("live", "both"):
        sc["live"] = run_live(args.symbol, args.granularity, args.count)
        print(f"\n=== LIVE === {args.symbol} {args.granularity}s on {sc['live']['closed_bars']} bars")
        print(f"  rsi_14:   {sc['live']['rsi_14_last']:.2f}" if sc["live"]["rsi_14_last"] is not None else "  rsi_14: None")
        print(f"  ema_20:   {sc['live']['ema_20_last']:.2f}")
        print(f"  atr_14:   {sc['live']['atr_14_last']:.2f}")
        print(f"  vwap:     {sc['live']['vwap_last']:.2f}")
        print(f"  hi/lo:    {sc['live']['high_max']:.2f} / {sc['live']['low_min']:.2f}")
        for k, v in sc["live"]["checks"].items():
            mark = "PASS" if v else "FAIL"
            print(f"  [{mark}] {k}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))
        print(f"\nscorecard written to {args.json_out}")

    all_ok = True
    if "offline" in sc and not sc["offline"]["all_pass"]:
        all_ok = False
    if "live" in sc and not sc["live"]["pass"]:
        all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
