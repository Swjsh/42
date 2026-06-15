"""v14_sweep — validate liquidity-grab / failed-breakout pattern detection.

Includes a synthetic reproduction of the 2026-05-14 09:55 SPY bar
(the bar that the heartbeat mistook for a reclaim trigger). On synthetic
data with PMH 745.43 + a bar with high 745.47 + close 744.43, the
sweep detector must fire bearish (up-sweep) — proving the engine has
the primitive to catch what bit us on Friday.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.lib.bar import Bar
from crypto.lib.bar_reader import closed_bars_only
from crypto.lib.data_sources import fetch_bars, now_utc
from crypto.lib.levels import Level, LevelKind, round_number_levels
from crypto.lib.sweep import detect_sweeps


def _bar(t, o, h, l, c) -> Bar:
    return Bar(open_time=t, open=o, high=h, low=l, close=c, volume=1.0,
               granularity_seconds=300, source="synthetic")


def run_offline() -> dict:
    base = datetime(2026, 5, 14, 13, 0, 0, tzinfo=timezone.utc)
    def t(i): return base + timedelta(seconds=300 * i)
    results = []

    # T1: The 5/14 09:55 SPY bar — bar 3 sweeps PMH 745.43
    bars_5_14 = [
        _bar(t(0), 743.65, 745.00, 743.56, 744.81),   # 09:30 RTH open
        _bar(t(1), 745.42, 745.87, 745.20, 745.70),   # 09:45 bar (let's pretend matches PMH)
        _bar(t(2), 745.68, 745.89, 744.93, 745.02),   # 09:50 RED close below PMH 745.43
        _bar(t(3), 745.02, 745.47, 744.25, 744.43),   # 09:55 — THE SWEEP
    ]
    pmh = Level(745.43, LevelKind.PRIOR_PERIOD_HIGH, 3, "PMH")
    hits = detect_sweeps(bars_5_14, [pmh], min_wick_pct=0.005, min_close_back_pct=0.05, clean_prior=1)
    # The 09:55 bar should produce an up-sweep on PMH 745.43:
    #   high 745.47 - 745.43 = 0.04 > 0.005% of 745.43 (= 0.037) -> wick OK
    #   745.43 - 744.43 = 1.00 > 0.05% of 745.43 (= 0.37) -> close OK
    #   prior bar (09:50) close 745.02 < 745.43 -> clean
    up_sweep = [h for h in hits if h.bar_index == 3 and h.direction == "up"]
    results.append(("T1_5_14_sweep_detected", len(up_sweep) == 1,
                    f"hits={hits}"))

    # T2: A bar that closes ABOVE the level after touching it = reclaim, NOT sweep
    bars = [_bar(t(0), 99, 99.5, 98.5, 99.0), _bar(t(1), 99.0, 101.0, 98.8, 100.8)]
    hits = detect_sweeps(bars, [Level(100, LevelKind.ROUND_NUMBER, 2)], 0.5, 0.5, 1)
    results.append(("T2_reclaim_not_sweep", len(hits) == 0, f"hits={hits}"))

    # T3: down-sweep — bar dips below support, closes back above
    bars = [_bar(t(0), 101, 101.5, 100.5, 101.0), _bar(t(1), 101.0, 101.2, 99.0, 100.5)]
    hits = detect_sweeps(bars, [Level(100, LevelKind.ROUND_NUMBER, 2)], 0.5, 0.3, 1)
    results.append(("T3_down_sweep", len(hits) == 1 and hits[0].direction == "down", f"hits={hits}"))

    # T4: prior bars closed past the level = NOT a clean sweep
    bars = [
        _bar(t(0), 101, 102, 100.5, 101.5),  # closed above 100
        _bar(t(1), 101.5, 102.5, 101, 102),  # closed above 100
        _bar(t(2), 102, 102.5, 99.5, 99.0),  # would be down-sweep IF clean
    ]
    hits = detect_sweeps(bars, [Level(100, LevelKind.ROUND_NUMBER, 2)], 0.1, 0.5, 2)
    # prior 2 bars closed above 100, so this isn't a clean down-sweep on 100
    results.append(("T4_not_clean_no_sweep", len(hits) == 0, f"hits={hits}"))

    # T5: marginal wick (doesn't exceed threshold)
    bars = [_bar(t(0), 99, 99.5, 98.5, 99), _bar(t(1), 99, 100.001, 98.5, 98.5)]
    hits = detect_sweeps(bars, [Level(100, LevelKind.ROUND_NUMBER, 2)], 0.5, 0.5, 1)
    # wick excess is 0.001/100*100 = 0.001% < 0.5% threshold
    results.append(("T5_marginal_wick_no_sweep", len(hits) == 0, f"hits={hits}"))

    return {"mode": "offline",
            "tests": [{"name": n, "pass": p, "note": note[:80]} for n, p, note in results],
            "passed": sum(1 for _, p, _ in results if p), "total": len(results),
            "all_pass": all(p for _, p, _ in results)}


def run_live(symbol, granularity, count) -> dict:
    now = now_utc()
    raw = fetch_bars("coinbase", symbol, granularity, count)
    series = closed_bars_only(raw, now)
    bars = list(series)
    if not bars:
        return {"mode": "live", "pass": False, "reason": "no_bars"}
    levels = round_number_levels(bars[-1].close, 1000, radius=2)
    # 0.01% = ~$7.70 threshold at BTC $77K — calibrated from sweep_threshold_calibration.py (2026-05-19)
    # Prior 0.02% threshold ($15.40) was too conservative: blocked all observed BTC round-number sweeps
    # (strongest real sweep in 211-bar window = 0.013% = ~$10). Lowered to capture genuine sweeps.
    hits = detect_sweeps(bars, levels, min_wick_pct=0.01, min_close_back_pct=0.05, clean_prior=3)
    by_dir = {"up": 0, "down": 0}
    for h in hits:
        by_dir[h.direction] += 1
    return {"mode": "live", "closed_bars": len(bars), "levels": len(levels),
            "sweep_hits": len(hits), "by_direction": by_dir,
            "examples": [
                {"bar_idx": h.bar_index, "level": h.level_price, "dir": h.direction,
                 "wick_excess_pct": h.wick_excess_pct, "close_back_pct": h.close_back_pct}
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
            print(f"  sweep hits: {live['sweep_hits']}  by direction: {live['by_direction']}")
            for ex in live["examples"]:
                print(f"    bar {ex['bar_idx']:>3d}  level {ex['level']:>10.2f}  dir {ex['dir']:>4s}  wick {ex['wick_excess_pct']:.3f}%  close_back {ex['close_back_pct']:.3f}%")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))
    return 0 if sc.get("offline", {}).get("all_pass", True) else 1


if __name__ == "__main__":
    sys.exit(main())
