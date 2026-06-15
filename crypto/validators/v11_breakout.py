"""v11_breakout — validate quality-breakout composite primitive."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar import Bar
from crypto.lib.bar_reader import closed_bars_only
from crypto.lib.breakout import detect_quality_breakouts
from crypto.lib.data_sources import fetch_bars, now_utc
from crypto.lib.levels import Level, LevelKind, round_number_levels


def _bar(t, o, h, l, c, v) -> Bar:
    return Bar(open_time=t, open=o, high=h, low=l, close=c, volume=v,
               granularity_seconds=300, source="synthetic")


def run_offline() -> dict:
    base = datetime(2026, 5, 16, 0, 0, 0, tzinfo=timezone.utc)
    def t(i): return base + timedelta(seconds=300 * i)
    results = []

    # T1: clean breakout (close past level + volume 2x avg)
    avg_vol = 100.0
    bars = [_bar(t(i), 99, 99.5, 98.5, 99.0, avg_vol) for i in range(20)]
    bars.append(_bar(t(20), 99.5, 101.0, 99.0, 100.8, avg_vol * 2.5))  # breakout
    levels = [Level(100.0, LevelKind.ROUND_NUMBER, 2)]
    hits = detect_quality_breakouts(bars, levels, min_close_margin_pct=0.5, volume_threshold=1.5)
    results.append(("T1_clean_breakout", len(hits) == 1 and hits[0].direction == "up", f"hits={hits}"))

    # T2: same close but volume insufficient -> no hit
    bars2 = list(bars[:-1])
    bars2.append(_bar(t(20), 99.5, 101.0, 99.0, 100.8, avg_vol * 1.0))  # no vol confirmation
    hits = detect_quality_breakouts(bars2, levels, min_close_margin_pct=0.5, volume_threshold=1.5)
    results.append(("T2_no_volume_no_break", len(hits) == 0, f"hits={hits}"))

    # T3: down-direction break
    bars = [_bar(t(i), 101, 101.5, 100.5, 101.0, avg_vol) for i in range(20)]
    bars.append(_bar(t(20), 100.5, 101, 99, 99.2, avg_vol * 3))
    hits = detect_quality_breakouts(bars, levels, min_close_margin_pct=0.5, volume_threshold=1.5)
    results.append(("T3_break_down", len(hits) == 1 and hits[0].direction == "down", f"hits={hits}"))

    # T4: marginal close (within margin band) -> no hit
    bars = [_bar(t(i), 99, 99.5, 98.5, 99.0, avg_vol) for i in range(20)]
    bars.append(_bar(t(20), 99.5, 100.4, 99.0, 100.05, avg_vol * 3))  # close only $0.05 past 100
    hits = detect_quality_breakouts(bars, levels, min_close_margin_pct=0.5, volume_threshold=1.5)
    # margin = 100 * 0.5 / 100 = 0.5, close 100.05 - 100 = 0.05 < 0.5 -> no break
    results.append(("T4_marginal_no_break", len(hits) == 0, f"hits={hits}"))

    return {"mode": "offline",
            "tests": [{"name": n, "pass": p, "note": note[:80]} for n, p, note in results],
            "passed": sum(1 for _, p, _ in results if p), "total": len(results),
            "all_pass": all(p for _, p, _ in results)}


def run_live(symbol, granularity, count) -> dict:
    now = now_utc()
    raw = fetch_bars("coinbase", symbol, granularity, count)
    series = closed_bars_only(raw, now)
    bars = list(series)
    if len(bars) < 25:
        return {"mode": "live", "pass": False, "reason": "not_enough_bars"}
    last = bars[-1]
    levels = round_number_levels(last.close, 1000, radius=3)
    hits = detect_quality_breakouts(bars, levels, min_close_margin_pct=0.05, volume_threshold=1.5, require_clean_prior=5)
    by_dir = {"up": 0, "down": 0}
    for h in hits:
        by_dir[h.direction] += 1
    return {"mode": "live", "closed_bars": len(bars), "levels_count": len(levels),
            "breakout_hits": len(hits), "by_direction": by_dir,
            "examples": [
                {"bar": h.bar_index, "level": h.level_price, "close": h.close,
                 "direction": h.direction, "margin_pct": h.margin_pct, "vol_ratio": h.volume_ratio}
                for h in hits[-3:]
            ], "pass": True}


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
            print(f"  breakout hits: {live['breakout_hits']}  by direction: {live['by_direction']}")
            for ex in live["examples"]:
                print(f"    bar {ex['bar']:>3d}  level {ex['level']:>10.2f}  close {ex['close']:>10.2f}  dir {ex['direction']}  margin {ex['margin_pct']:.2f}%  vol {ex['vol_ratio']:.1f}x")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))
    return 0 if sc.get("offline", {}).get("all_pass", True) else 1


if __name__ == "__main__":
    sys.exit(main())
