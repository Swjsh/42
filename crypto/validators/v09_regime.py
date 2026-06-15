"""v09_regime — validate trend/chop/breakout classification."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar import Bar
from crypto.lib.bar_reader import closed_bars_only
from crypto.lib.data_sources import fetch_bars, now_utc
from crypto.lib.regime import classify_regimes


def _bar(t, o, h, l, c) -> Bar:
    return Bar(open_time=t, open=o, high=h, low=l, close=c, volume=1.0,
               granularity_seconds=300, source="synthetic")


def run_offline() -> dict:
    base = datetime(2026, 5, 16, 0, 0, 0, tzinfo=timezone.utc)
    def t(i): return base + timedelta(seconds=300 * i)
    results = []

    # T1: low-volatility flat -> CHOP after warmup
    bars = [_bar(t(i), 100.0, 100.05, 99.95, 100.0) for i in range(80)]
    r = classify_regimes(bars)
    last_n = [s.regime for s in r[-10:]]
    results.append(("T1_flat_chop", all(rg == "CHOP" or rg == "UNKNOWN" for rg in last_n), f"last10={last_n[:5]}"))

    # T2: monotonic uptrend with steady ATR -> TREND_UP
    bars = []
    for i in range(80):
        p = 100 + i * 0.5
        bars.append(_bar(t(i), p, p + 0.5, p - 0.5, p + 0.4))
    r = classify_regimes(bars)
    last = r[-1].regime
    results.append(("T2_uptrend_trend_up", last in ("TREND_UP", "BREAKOUT"), f"last={last}"))

    # T3: monotonic downtrend -> TREND_DOWN
    bars = []
    for i in range(80):
        p = 200 - i * 0.5
        bars.append(_bar(t(i), p, p + 0.5, p - 0.5, p - 0.4))
    r = classify_regimes(bars)
    results.append(("T3_downtrend_trend_down", r[-1].regime in ("TREND_DOWN", "BREAKOUT"), f"last={r[-1].regime}"))

    # T4: sudden jump = BREAKOUT
    bars = [_bar(t(i), 100.0, 100.1, 99.9, 100.0) for i in range(60)]
    # Now a huge bar
    bars.append(_bar(t(60), 100.0, 110.0, 100.0, 109.0))
    r = classify_regimes(bars)
    results.append(("T4_jump_breakout", r[-1].regime == "BREAKOUT", f"last={r[-1].regime}"))

    return {"mode": "offline",
            "tests": [{"name": n, "pass": p, "note": note[:80]} for n, p, note in results],
            "passed": sum(1 for _, p, _ in results if p), "total": len(results),
            "all_pass": all(p for _, p, _ in results)}


def run_live(symbol, granularity, count) -> dict:
    now = now_utc()
    raw = fetch_bars("coinbase", symbol, granularity, count)
    series = closed_bars_only(raw, now)
    bars = list(series)
    if len(bars) < 70:
        return {"mode": "live", "pass": False, "reason": "not_enough_bars"}
    r = classify_regimes(bars)
    valid = [s for s in r if s.regime != "UNKNOWN"]
    dist = {}
    for s in valid:
        dist[s.regime] = dist.get(s.regime, 0) + 1
    return {"mode": "live", "closed_bars": len(bars), "last_regime": r[-1].regime,
            "atr_14": r[-1].atr_14, "median_atr_50": r[-1].median_atr_50,
            "regime_distribution": dist, "pass": True}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    p.add_argument("--symbol", default="BTC-USD"); p.add_argument("--granularity", type=int, default=300)
    p.add_argument("--count", type=int, default=200); p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)
    sc = {}
    if args.mode in ("offline", "both"):
        sc["offline"] = run_offline()
        print(f"=== OFFLINE === {sc['offline']['passed']}/{sc['offline']['total']} pass")
        for t in sc["offline"]["tests"]:
            print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:30s} {t['note']}")
    if args.mode in ("live", "both"):
        sc["live"] = run_live(args.symbol, args.granularity, args.count)
        live = sc["live"]
        print(f"\n=== LIVE === {args.symbol} {args.granularity}s on {live.get('closed_bars','?')} bars")
        if live.get("pass"):
            print(f"  last regime: {live['last_regime']}  atr14={live['atr_14']:.2f}  median_atr_50={live['median_atr_50']:.2f}")
            print(f"  distribution: {live['regime_distribution']}")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))
    return 0 if sc.get("offline", {}).get("all_pass", True) else 1


if __name__ == "__main__":
    sys.exit(main())
