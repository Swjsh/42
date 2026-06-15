"""v08_ribbon — validate EMA ribbon cascade interpretation."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar import Bar
from crypto.lib.bar_reader import closed_bars_only
from crypto.lib.data_sources import fetch_bars, now_utc
from crypto.lib.ribbon import compute_ribbon


def _bar(t, p) -> Bar:
    return Bar(open_time=t, open=p, high=p+0.5, low=p-0.5, close=p, volume=1.0,
               granularity_seconds=300, source="synthetic")


def run_offline() -> dict:
    base = datetime(2026, 5, 16, 0, 0, 0, tzinfo=timezone.utc)
    def t(i): return base + timedelta(seconds=300 * i)
    results = []

    # T1: monotonic uptrend -> BULL stack after warmup
    bars = [_bar(t(i), 100 + i * 0.5) for i in range(100)]
    rib = compute_ribbon(bars, 9, 21, 55)
    results.append(("T1_uptrend_bull", rib[-1].status == "BULL", f"status={rib[-1].status}"))

    # T2: monotonic downtrend -> BEAR
    bars = [_bar(t(i), 200 - i * 0.5) for i in range(100)]
    rib = compute_ribbon(bars, 9, 21, 55)
    results.append(("T2_downtrend_bear", rib[-1].status == "BEAR", f"status={rib[-1].status}"))

    # T3: flat -> MIXED (fast == pivot == slow approximately)
    bars = [_bar(t(i), 100.0) for i in range(100)]
    rib = compute_ribbon(bars, 9, 21, 55)
    results.append(("T3_flat_mixed", rib[-1].status == "MIXED", f"status={rib[-1].status}"))

    # T4: ribbon insufficient data -> all MIXED
    bars = [_bar(t(i), 100 + i) for i in range(20)]
    rib = compute_ribbon(bars, 9, 21, 55)
    results.append(("T4_short_series_mixed", rib[-1].status == "MIXED", f"status={rib[-1].status}"))

    # T5: spread > 0 in trend
    bars = [_bar(t(i), 100 + i * 0.5) for i in range(100)]
    rib = compute_ribbon(bars, 9, 21, 55)
    results.append(("T5_spread_positive", rib[-1].spread > 0, f"spread={rib[-1].spread:.2f}"))

    return {"mode": "offline",
            "tests": [{"name": n, "pass": p, "note": note[:80]} for n, p, note in results],
            "passed": sum(1 for _, p, _ in results if p), "total": len(results),
            "all_pass": all(p for _, p, _ in results)}


def run_live(symbol, granularity, count) -> dict:
    now = now_utc()
    raw = fetch_bars("coinbase", symbol, granularity, count)
    series = closed_bars_only(raw, now)
    bars = list(series)
    if len(bars) < 56:
        return {"mode": "live", "pass": False, "reason": "not_enough_bars"}
    rib = compute_ribbon(bars, 9, 21, 55)
    last = rib[-1]
    statuses = [r.status for r in rib if r.status in ("BULL", "BEAR", "MIXED")]
    counts = {s: statuses.count(s) for s in ("BULL", "BEAR", "MIXED")}
    return {"mode": "live", "closed_bars": len(bars),
            "last": {"fast": last.fast, "pivot": last.pivot, "slow": last.slow,
                     "spread": last.spread, "status": last.status},
            "status_distribution": counts, "pass": True}


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
            l = live["last"]
            print(f"  ribbon: fast={l['fast']:.2f}  pivot={l['pivot']:.2f}  slow={l['slow']:.2f}  spread={l['spread']:.2f}  status={l['status']}")
            print(f"  distribution: BULL={live['status_distribution']['BULL']}  BEAR={live['status_distribution']['BEAR']}  MIXED={live['status_distribution']['MIXED']}")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))
    return 0 if sc.get("offline", {}).get("all_pass", True) else 1


if __name__ == "__main__":
    sys.exit(main())
