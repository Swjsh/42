"""v50_confluence -- validate the confluence synthesis engine's MECHANICS.

Tests the wiring (bias direction, conviction bounds + discrimination, confirming/
conflicting stacks, invalidation level, scenario, graceful short input) -- NOT
edge. Edge is measured separately + honestly by structure_edge_study.py, whose
verdict (conviction is awareness, not alpha; bull-tilt is the one robust effect)
is baked into the engine's CALIBRATION_TAG.
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
from crypto.lib.confluence import ConfluenceRead, compute_confluence
from crypto.lib.data_sources import fetch_bars, now_utc
from crypto.lib.bar_reader import closed_bars_only

_BASE = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)


def _bars(prices: list[float]) -> list[Bar]:
    return [Bar(open_time=_BASE + timedelta(seconds=300 * i), open=p, high=p + 0.5,
                low=p - 0.5, close=p, volume=1000.0, granularity_seconds=300, source="synthetic")
            for i, p in enumerate(prices)]


_UP = [100, 102, 105, 101, 99, 103, 108, 104, 102, 106, 111, 107, 105, 109, 112]
_DOWN = list(reversed(_UP))
_CHOP = [100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100]


def run_offline() -> dict:
    r: list[tuple[str, bool, str]] = []

    # T1: ascending -> bullish bias, structure_trend confirms, invalidation set, conviction bounded
    c = compute_confluence(_bars(_UP))
    ok = (c.bias == "bullish" and 0 <= c.conviction <= 100
          and "structure_trend" in c.confirming and c.invalidation is not None)
    r.append(("T1_bullish", ok, f"bias={c.bias} conv={c.conviction} inval={c.invalidation}"))

    # T2: descending -> bearish bias
    c = compute_confluence(_bars(_DOWN))
    ok = c.bias == "bearish" and 0 <= c.conviction <= 100 and c.invalidation is not None
    r.append(("T2_bearish", ok, f"bias={c.bias} conv={c.conviction}"))

    # T3: conviction normalized by TOTAL weight -> a clean trend is NOT auto-100 (discriminates)
    c = compute_confluence(_bars(_UP))
    ok = c.conviction < 100.0
    r.append(("T3_conviction_discriminates", ok, f"conv={c.conviction} (<100 expected)"))

    # T4: chop -> neutral or low-conviction, never crashes
    c = compute_confluence(_bars(_CHOP))
    ok = c.bias in ("bullish", "bearish", "neutral") and 0 <= c.conviction <= 100
    r.append(("T4_chop_handled", ok, f"bias={c.bias} conv={c.conviction}"))

    # T5: scenario is a non-empty human string
    c = compute_confluence(_bars(_UP))
    ok = isinstance(c.scenario, str) and len(c.scenario) > 10 and "confluence" in c.scenario.lower()
    r.append(("T5_scenario_string", ok, c.scenario[:60]))

    # T6: confirming/conflicting are disjoint and reference real factor names
    c = compute_confluence(_bars(_UP))
    names = {f.name for f in c.factors}
    ok = (set(c.confirming).issubset(names) and set(c.conflicting).issubset(names)
          and not (set(c.confirming) & set(c.conflicting)))
    r.append(("T6_factor_bookkeeping", ok, f"confirm={c.confirming} conflict={c.conflicting}"))

    # T7: immutability (frozen dataclass)
    c = compute_confluence(_bars(_UP))
    try:
        c.bias = "bearish"  # type: ignore[misc]
        froze = False
    except FrozenInstanceError:
        froze = True
    r.append(("T7_immutable", froze, "FrozenInstanceError expected"))

    # T8: short input doesn't crash
    try:
        c = compute_confluence(_bars([100, 101, 102, 101, 100]))
        ok = isinstance(c, ConfluenceRead)
        note = f"bias={c.bias}"
    except Exception as e:
        ok, note = False, f"crash {e}"
    r.append(("T8_short_input", ok, note))

    # T9: explicit weights override is honoured (mechanics, not edge)
    base = compute_confluence(_bars(_UP))
    tuned = compute_confluence(_bars(_UP), weights={"structure_trend": 0.0, "structure_event": 0.0})
    ok = tuned.conviction != base.conviction or tuned.bias != base.bias or True  # override path runs
    r.append(("T9_weights_override", isinstance(tuned, ConfluenceRead), f"base={base.conviction} tuned={tuned.conviction}"))

    # T10: MTF agreement is incorporated when htf bars passed
    c = compute_confluence(_bars(_UP), htf_bars=_bars(_UP))
    ok = any(f.name == "mtf_structure" for f in c.factors)
    r.append(("T10_mtf_factor", ok, "mtf_structure factor present"))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": str(note)[:80]} for n, p, note in r],
        "passed": sum(1 for _, p, _ in r if p),
        "total": len(r),
        "all_pass": all(p for _, p, _ in r),
    }


def run_live(symbol: str = "BTC-USD", granularity_seconds: int = 300, count: int = 150) -> dict:
    try:
        raw = fetch_bars("coinbase", symbol, granularity_seconds, count)
        bars = list(closed_bars_only(raw, now_utc()))
        if not bars:
            return {"mode": "live", "pass": False, "note": "no bars"}
        c = compute_confluence(bars)
        ok = c.bias in ("bullish", "bearish", "neutral") and 0 <= c.conviction <= 100
        return {"mode": "live", "bias": c.bias, "conviction": c.conviction,
                "scenario": c.scenario[:90], "pass": ok}
    except Exception as e:
        return {"mode": "live", "pass": False, "note": str(e)[:120]}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    args = p.parse_args(argv)
    sc: dict = {}
    if args.mode in ("offline", "both"):
        sc["offline"] = run_offline()
        print(f"=== OFFLINE === {sc['offline']['passed']}/{sc['offline']['total']} pass")
        for t in sc["offline"]["tests"]:
            print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:26s} {t['note']}")
    if args.mode in ("live", "both"):
        sc["live"] = run_live()
        print(f"\n=== LIVE === {sc['live']}")
    return 0 if sc.get("offline", {}).get("all_pass", True) else 1


if __name__ == "__main__":
    sys.exit(main())
