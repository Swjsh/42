"""chart_read_demo — apply the 7-step CHART-READING-PROTOCOL.md to live BTC.

End-to-end demonstration. Runs every primitive in the harness against live BTC bars
and outputs the canonical "chart read" statement defined by the protocol doc.

Usage:
  python crypto/benchmarks/chart_read_demo.py
  python crypto/benchmarks/chart_read_demo.py --symbol ETH-USD
  python crypto/benchmarks/chart_read_demo.py --tv-bars crypto/data/fixtures/tv_bars_latest.json
                       # use captured TV bars instead of live Coinbase REST
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar_reader import closed_bars_only, last_closed_bar
from crypto.lib.candlesticks import detect_all as detect_all_candles
from crypto.lib.data_sources import fetch_bars, now_utc
from crypto.lib.divergence import find_divergences
from crypto.lib.indicators import atr, ema, rsi, vwap
from crypto.lib.levels import (
    LevelEvent, classify_bar_at_level, nearest_levels,
    pivot_points, prior_period_levels, round_number_levels,
)
from crypto.lib.regime import classify_regimes
from crypto.lib.ribbon import compute_ribbon
from crypto.lib.sweep import detect_sweeps
from crypto.lib.volume import volume_ratio


def read_chart(symbol: str = "BTC-USD", granularity: int = 300, count: int = 200,
               round_increment: float = 1000.0) -> dict:
    now = now_utc()

    # Step 1 — fetch + filter to closed bars
    raw = fetch_bars("coinbase", symbol, granularity, count)
    closed_result = last_closed_bar(raw, now)
    if closed_result.verdict != "ok" or closed_result.last_closed is None:
        return {"verdict": closed_result.verdict, "reason": "step1_failed"}
    closed_series = closed_bars_only(raw, now)
    closed = list(closed_series)
    last = closed[-1]

    # Step 2 — staleness already enforced by verdict=ok

    # Step 4 — indicators (on closed bars)
    r14 = rsi(closed, 14)
    e20 = ema(closed, 20)
    e9 = ema(closed, 9)
    e55 = ema(closed, 55)
    a14 = atr(closed, 14)
    vw = vwap(closed)
    vr = volume_ratio(closed, 20)

    # Step 5 — levels
    rounds = round_number_levels(last.close, round_increment, radius=3)
    prior_8h = prior_period_levels(closed, lookback=min(96, len(closed) - 1))
    pivots = pivot_points(closed[-96:] if len(closed) >= 96 else closed)
    all_levels = rounds + prior_8h + pivots
    near3 = nearest_levels(last.close, all_levels, n=3)

    # Step 6 — level events on the LAST CLOSED bar
    events = {}
    for L in near3:
        events[f"{L.label}_{L.price:.2f}"] = classify_bar_at_level(last, L, min_margin_pct=0.05).value

    # Step 6.5 — sweep detection
    sweeps = detect_sweeps(closed[-10:], near3, min_wick_pct=0.02, min_close_back_pct=0.05, clean_prior=3)
    sweeps_on_last = [s for s in sweeps if s.bar_index == len(closed[-10:]) - 1]

    # Step 7 — context
    ribbon = compute_ribbon(closed, 9, 21, 55)[-1]
    regimes = classify_regimes(closed)
    regime_now = regimes[-1].regime
    divergences = find_divergences(closed, rsi_length=14, swing_window=3, lookback=40)
    divergence_summary = {"count": len(divergences),
                         "last_kind": divergences[-1].kind if divergences else None}
    candles_on_last = [h for h in detect_all_candles(closed[-5:]) if h.bar_index == len(closed[-5:]) - 1]

    # Verdict synthesis
    bias_signal = "MIXED"
    if ribbon.status == "BULL" and regime_now in ("TREND_UP", "BREAKOUT") and (vr[-1] or 0) >= 1.5:
        bias_signal = "BULL_BIAS_OK"
    elif ribbon.status == "BEAR" and regime_now in ("TREND_DOWN", "BREAKOUT") and (vr[-1] or 0) >= 1.5:
        bias_signal = "BEAR_BIAS_OK"
    if sweeps_on_last:
        bias_signal = f"SWEEP_WARNING_{sweeps_on_last[0].direction.upper()}"

    return {
        "now_utc": now.isoformat(),
        "symbol": symbol,
        "verdict": "ok",
        "last_closed_bar": {
            "open_utc": last.open_time.isoformat(),
            "close_utc": last.close_time.isoformat(),
            "OHLC": [last.open, last.high, last.low, last.close],
            "volume": last.volume,
            "age_seconds": (now - last.close_time).total_seconds(),
        },
        "indicators": {
            "rsi_14": r14[-1], "ema_9": e9[-1], "ema_20": e20[-1], "ema_55": e55[-1],
            "atr_14": a14[-1], "vwap": vw[-1], "volume_ratio_20": vr[-1],
        },
        "ribbon": {
            "fast": ribbon.fast, "pivot": ribbon.pivot, "slow": ribbon.slow,
            "spread": ribbon.spread, "status": ribbon.status,
        },
        "regime": regime_now,
        "nearest_levels": [
            {"price": L.price, "kind": L.kind.value, "strength": L.strength, "label": L.label}
            for L in near3
        ],
        "last_bar_level_events": events,
        "sweeps_on_last_bar": [
            {"level": s.level_price, "direction": s.direction,
             "wick_excess_pct": s.wick_excess_pct, "close_back_pct": s.close_back_pct}
            for s in sweeps_on_last
        ],
        "candlestick_patterns_on_last": [{"pattern": c.pattern} for c in candles_on_last],
        "divergence": divergence_summary,
        "bias_signal": bias_signal,
        "canonical_statement": _format_canonical(
            now, last, r14[-1], e20[-1], a14[-1], vw[-1], vr[-1] or 0,
            regime_now, ribbon, near3, events, sweeps_on_last, bias_signal,
        ),
    }


def _format_canonical(now, last, r14, e20, a14, vw, vr, regime, ribbon, near3, events, sweeps, bias):
    nearest = near3[0] if near3 else None
    near_str = f"{nearest.label} {nearest.price:.2f} (s{nearest.strength})" if nearest else "none"
    event_str = list(events.values())[0] if events else "none"
    sweep_str = f"SWEEP-{sweeps[0].direction.upper()}" if sweeps else "none"
    return (
        f"At {now.strftime('%H:%M:%S')} UTC, last closed 5m bar = "
        f"{last.open_time.strftime('%H:%M')} -> {last.close_time.strftime('%H:%M')} "
        f"O={last.open:.2f} H={last.high:.2f} L={last.low:.2f} C={last.close:.2f} V={last.volume:.2f}. "
        f"Nearest level: {near_str}. "
        f"Last-bar event: {event_str}. Sweep: {sweep_str}. "
        f"RSI(14)={r14:.2f}, EMA-20={e20:.2f}, ATR(14)={a14:.2f}, VWAP={vw:.2f}. "
        f"Regime: {regime}. Ribbon: {ribbon.status} spread={ribbon.spread:.2f}. "
        f"Volume ratio: {vr:.2f}x. Bias verdict: {bias}."
    )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", default="BTC-USD")
    p.add_argument("--granularity", type=int, default=300)
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--round-increment", type=float, default=1000.0)
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    out = read_chart(args.symbol, args.granularity, args.count, args.round_increment)
    print("=" * 70)
    print("CHART READ — applying 7-step protocol")
    print("=" * 70)
    print(out.get("canonical_statement", "(no canonical statement)"))
    print()
    print("Full structured read:")
    print(json.dumps(out, indent=2, default=str))

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
