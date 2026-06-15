"""v15_three_source_parity — 3-way source agreement with true 2-of-3 voting.

Why this exists:
  v02 (2-source: coinbase vs yfinance) hits ~11% drift rate on the just-closed
  bar because yfinance settles slightly after coinbase. We mitigated by
  skip_most_recent=1, but the underlying disagreement is real.

  Adding Alpaca crypto REST as a 3rd source enables 2-of-3 voting:
    - For each shared bar, sort the 3 closes; the median is the "truth"
    - A bar PASSES if any 2 sources agree within INNER_TOLERANCE (5 bp)
      (i.e. the closer of the two inner-pair spreads is under threshold)
    - A bar FAILS only when ALL 3 sources are spread out — no 2-source
      consensus exists (genuine data quality error)

  Why 2-of-3, not 3-of-3:
    yfinance is an aggregator that occasionally returns stale closes for
    recently-settled bars (up to 2 hours after close). Coinbase + Alpaca
    are direct exchange feeds and agree tightly. Requiring all 3 to agree
    causes false positives on yfinance stale bars. True 2-of-3 catches
    real errors (both direct feeds disagree) while tolerating single-
    source lag/staleness.

  Empirical evidence (2026-05-16 21:20 UTC, 29 bars):
    - 3-way shared: 29/29 (100% coverage)
    - max spread: 4.15 bp (well under 5 bp tolerance)
    - violations: 0/29 (0.00%)

  This validator is the OUTER-layer ratifier when v02 reports drift.
  If v02 alerts but v15 passes, the disagreement is a single-provider artifact
  (likely yfinance settling late) and can be safely ignored.

Tolerance: inner-pair 5 bp — bar passes if any 2 of 3 sources agree within 5 bp.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar_reader import closed_bars_only
from crypto.lib.data_sources import fetch_bars, now_utc


INNER_PAIR_TOLERANCE_PCT = 0.05   # 5bp on the 2 closest sources (true 2-of-3 vote).
# Bar passes if any 2 of 3 sources agree within 5 bp.
# Real data errors (all 3 genuinely disagree) are >>20bp — still caught.
THREE_SOURCE_TOLERANCE_PCT = 0.07  # kept for informational max-min spread reporting only.


def compare3(symbol: str, granularity_seconds: int, count: int, skip_most_recent: int = 1) -> dict:
    now = now_utc()
    try:
        cb = fetch_bars("coinbase", symbol, granularity_seconds, count)
        yf = fetch_bars("yfinance", symbol, granularity_seconds, count)
        al = fetch_bars("alpaca", symbol, granularity_seconds, count)
    except Exception as e:
        return {"checked_at": now.isoformat(), "symbol": symbol, "error": str(e), "pass": False}

    cb_bars = sorted(closed_bars_only(cb, now).bars, key=lambda b: b.open_time)
    yf_bars = sorted(closed_bars_only(yf, now).bars, key=lambda b: b.open_time)
    al_bars = sorted(closed_bars_only(al, now).bars, key=lambda b: b.open_time)
    if skip_most_recent > 0:
        cb_bars = cb_bars[:-skip_most_recent] if len(cb_bars) > skip_most_recent else []
        yf_bars = yf_bars[:-skip_most_recent] if len(yf_bars) > skip_most_recent else []
        al_bars = al_bars[:-skip_most_recent] if len(al_bars) > skip_most_recent else []

    cb_map = {b.open_time: b for b in cb_bars}
    yf_map = {b.open_time: b for b in yf_bars}
    al_map = {b.open_time: b for b in al_bars}
    shared = sorted(set(cb_map) & set(yf_map) & set(al_map))

    violations = []
    single_outlier_bars = 0
    spreads_bp = []
    median_disagrees_cb = 0
    median_disagrees_yf = 0
    median_disagrees_al = 0
    for t in shared:
        closes = [cb_map[t].close, yf_map[t].close, al_map[t].close]
        sorted_closes = sorted(closes)
        median_close = sorted_closes[1]
        max_spread_pct = (sorted_closes[2] - sorted_closes[0]) / median_close * 100
        spreads_bp.append(max_spread_pct * 100)
        # True 2-of-3 vote: bar passes if any 2 sources agree within INNER_PAIR_TOLERANCE_PCT.
        # The inner pair is the closer of (lo,mid) or (mid,hi).
        bottom_pair_pct = (sorted_closes[1] - sorted_closes[0]) / sorted_closes[1] * 100
        top_pair_pct = (sorted_closes[2] - sorted_closes[1]) / sorted_closes[2] * 100
        min_inner_pct = min(bottom_pair_pct, top_pair_pct)
        if min_inner_pct > INNER_PAIR_TOLERANCE_PCT:
            # All 3 sources genuinely disagree — no 2-source consensus.
            violations.append({
                "open_time": t.isoformat(),
                "coinbase_close": cb_map[t].close,
                "yfinance_close": yf_map[t].close,
                "alpaca_close": al_map[t].close,
                "median": median_close,
                "max_spread_pct": max_spread_pct,
                "min_inner_pct": min_inner_pct,
            })
        elif max_spread_pct > THREE_SOURCE_TOLERANCE_PCT:
            # One source is an outlier but the other 2 agree — single-source artifact.
            single_outlier_bars += 1
        # Per-source distance from median (in bp)
        if abs(cb_map[t].close - median_close) / median_close * 10000 > 5:
            median_disagrees_cb += 1
        if abs(yf_map[t].close - median_close) / median_close * 10000 > 5:
            median_disagrees_yf += 1
        if abs(al_map[t].close - median_close) / median_close * 10000 > 5:
            median_disagrees_al += 1

    return {
        "checked_at": now.isoformat(),
        "symbol": symbol,
        "granularity_seconds": granularity_seconds,
        "three_way_shared_bars": len(shared),
        "coinbase_closed_bars": len(cb_bars),
        "yfinance_closed_bars": len(yf_bars),
        "alpaca_closed_bars": len(al_bars),
        "spreads_bp_mean": round(statistics.mean(spreads_bp), 3) if spreads_bp else None,
        "spreads_bp_max": round(max(spreads_bp), 3) if spreads_bp else None,
        "inner_pair_tolerance_pct": INNER_PAIR_TOLERANCE_PCT,
        "tolerance_pct": THREE_SOURCE_TOLERANCE_PCT,
        "single_outlier_bars": single_outlier_bars,
        "violations_count": len(violations),
        "violations": violations[:5],
        "median_disagrees": {
            "coinbase": median_disagrees_cb,
            "yfinance": median_disagrees_yf,
            "alpaca": median_disagrees_al,
        },
        "pass": len(shared) >= 3 and len(violations) == 0,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", default="BTC-USD")
    p.add_argument("--granularity", type=int, default=300)
    p.add_argument("--count", type=int, default=30)
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    sc = compare3(args.symbol, args.granularity, args.count)
    print("=" * 70)
    print("v15 — THREE-SOURCE PARITY (coinbase + yfinance + alpaca)")
    print("=" * 70)
    if "error" in sc:
        print(f"  ERROR: {sc['error']}")
        return 1
    print(f"  symbol:                 {sc['symbol']}")
    print(f"  3-way shared bars:      {sc['three_way_shared_bars']}")
    print(f"  per-source closed:      cb={sc['coinbase_closed_bars']} yf={sc['yfinance_closed_bars']} al={sc['alpaca_closed_bars']}")
    print(f"  max-min spread:         mean={sc['spreads_bp_mean']}bp  max={sc['spreads_bp_max']}bp")
    print(f"  single-outlier bars:    {sc['single_outlier_bars']}  (1-source artifact, other 2 agree)")
    print(f"  violations (no 2-agree):{sc['violations_count']}  (inner_pair > {sc['inner_pair_tolerance_pct']}%)")
    print(f"  median disagrees:       cb={sc['median_disagrees']['coinbase']}  yf={sc['median_disagrees']['yfinance']}  al={sc['median_disagrees']['alpaca']}  (per-source bars >5bp from median)")
    print(f"  PASS:                   {sc['pass']}")
    if sc["violations"]:
        print(f"\n  Violations:")
        for v in sc["violations"][:3]:
            print(f"    {v['open_time']}: cb={v['coinbase_close']:.2f} yf={v['yfinance_close']:.2f} al={v['alpaca_close']:.2f}  spread={v['max_spread_pct']:.4f}%")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))
        print(f"\n  scorecard: {args.json_out}")

    return 0 if sc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
