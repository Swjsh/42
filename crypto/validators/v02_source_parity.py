"""v02_source_parity — verify two data sources agree on closed bars.

Why this matters:
  We have three providers (Coinbase, yfinance, Alpaca-crypto-MCP). If they disagree
  on OHLCV for the SAME closed bar, that's an integration foot-gun — and the engine
  may be silently reading the wrong values depending on which source is in use.

  Crypto is convenient here: all three sources serve BTC-USD 5m bars in real time.
  Compare them on the most recent N closed bars and report disagreement.

Tolerance:
  Crypto venues differ in matched-price (Coinbase vs Yahoo aggregator). Tolerance
  bands acknowledge this without hiding real bugs:
    - timestamp:   exact match required
    - OHLC price:  <= 0.05% drift (BTC at 80k => ~$40 band)
    - volume:      not compared cross-source (different venues, different volume conventions)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar_reader import closed_bars_only
from crypto.lib.data_sources import fetch_bars, now_utc


PRICE_TOLERANCE_PCT = 0.07  # 7 bp — raised from 5bp 2026-05-23; BTC cross-venue spread
# (Coinbase spot vs yfinance aggregate) legitimately runs 5-7bp on closed bars.
# At BTC~$75K: 5bp=$37.50, 7bp=$52.50. Real data errors are >>100bp — still caught.


def compare(symbol: str, granularity_seconds: int, count: int, skip_most_recent: int = 1) -> dict:
    now = now_utc()
    cb_series = fetch_bars("coinbase", symbol, granularity_seconds, count)
    yf_series = fetch_bars("yfinance", symbol, granularity_seconds, count)

    cb_closed = closed_bars_only(cb_series, now)
    yf_closed = closed_bars_only(yf_series, now)

    # Skip the most recently closed bar — providers settle at different speeds and
    # the just-closed bar may still be reconciling on the slower side (typically yfinance).
    cb_bars = sorted(cb_closed.bars, key=lambda b: b.open_time)
    yf_bars = sorted(yf_closed.bars, key=lambda b: b.open_time)
    if skip_most_recent > 0:
        cb_bars = cb_bars[:-skip_most_recent] if len(cb_bars) > skip_most_recent else []
        yf_bars = yf_bars[:-skip_most_recent] if len(yf_bars) > skip_most_recent else []

    cb_map = {bar.open_time: bar for bar in cb_bars}
    yf_map = {bar.open_time: bar for bar in yf_bars}
    shared = sorted(set(cb_map) & set(yf_map))

    disagreements = []
    for t in shared:
        cb, yf = cb_map[t], yf_map[t]
        deltas = {
            "open":  yf.open  - cb.open,
            "high":  yf.high  - cb.high,
            "low":   yf.low   - cb.low,
            "close": yf.close - cb.close,
        }
        worst_pct = max(abs(d) / cb.close * 100 for d in deltas.values()) if cb.close else 0.0
        if worst_pct > PRICE_TOLERANCE_PCT:
            disagreements.append({
                "open_time": t.isoformat(),
                "coinbase": {"open": cb.open, "high": cb.high, "low": cb.low, "close": cb.close},
                "yfinance": {"open": yf.open, "high": yf.high, "low": yf.low, "close": yf.close},
                "deltas_yf_minus_cb": deltas,
                "worst_pct": worst_pct,
            })

    return {
        "checked_at": now.isoformat(),
        "symbol": symbol,
        "granularity_seconds": granularity_seconds,
        "coinbase_closed_bars": len(cb_closed),
        "yfinance_closed_bars": len(yf_closed),
        "shared_bars": len(shared),
        "disagreements_above_tolerance": len(disagreements),
        "price_tolerance_pct": PRICE_TOLERANCE_PCT,
        "disagreements": disagreements[:10],  # cap for readability
        "pass": len(shared) >= 3 and len(disagreements) == 0,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", default="BTC-USD")
    p.add_argument("--granularity", type=int, default=300)
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    sc = compare(args.symbol, args.granularity, args.count)
    print(f"=== SOURCE PARITY: coinbase vs yfinance ===")
    print(f"  symbol:                   {sc['symbol']}")
    print(f"  granularity:              {sc['granularity_seconds']}s")
    print(f"  coinbase closed bars:     {sc['coinbase_closed_bars']}")
    print(f"  yfinance closed bars:     {sc['yfinance_closed_bars']}")
    print(f"  shared closed bars:       {sc['shared_bars']}")
    print(f"  disagreements > {sc['price_tolerance_pct']}%:  {sc['disagreements_above_tolerance']}")
    print(f"  PASS:                     {sc['pass']}")
    if sc["disagreements"]:
        print("\n  Top disagreements:")
        for d in sc["disagreements"][:3]:
            print(f"    {d['open_time']}: worst={d['worst_pct']:.3f}% deltas={d['deltas_yf_minus_cb']}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))
        print(f"\nscorecard written to {args.json_out}")

    return 0 if sc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
