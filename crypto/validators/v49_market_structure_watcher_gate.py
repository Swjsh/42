"""v49_market_structure_watcher_gate — validate the MARKET_STRUCTURE watcher wrapper.

The structure DETECTOR (crypto.lib.market_structure.analyze_structure: HH/HL/LH/LL,
trend-from-structure, BOS, CHoCH) is covered by v46. This gate locks the WATCHER
WRAPPER (backtest/lib/watchers/market_structure_watcher.py) — specifically the
new wiring logic v46 does NOT exercise:

  * It emits a WatcherSignal ONLY when a structure event "prints" on the CURRENT bar
    (break_index == last bar). This is the load-bearing no-stale-re-emit / no-look-
    ahead guard — without it the watcher would re-fire the same BOS every tick.
  * Direction maps bullish->long, bearish->short; the triggering swing price
    (broken_price) and a HEURISTIC confidence tier (signal_tier) are carried through.
  * RTH gate + minimum-bars gate.

It is OBSERVE-ONLY (OP-21, 0/3 live wins). BOS/CHoCH have no published failure-rate
stat (TA-PATTERN-REFERENCE.md §A.4); confidence is heuristic, never gated on. A live
trigger additionally requires injecting the live engine's swing primitive (see the
watcher's promotion-prereq note) — out of scope here.

Offline tests (fixtures verified against analyze_structure):
  T1  fresh bullish BOS on the last bar   -> fires long, STRUCTURE_BOS, stop < entry
  T2  fresh bearish CHoCH on the last bar -> fires short, STRUCTURE_CHoCH, stop > entry
  T3  STALE event (break printed earlier, flat tail) -> None  (no-stale-re-emit guard)
  T4  flat series (no swings/structure)   -> None
  T5  too few bars (< _MIN_BARS)          -> None
  T6  fresh BOS but OUTSIDE RTH           -> None  (time gate)
  T7  metadata + direction-mapping contract

Live: audit watcher-observations.jsonl for market_structure rows (informational).

Exit code: 0 if all offline tests PASS, 1 otherwise.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import pandas as pd

from backtest.lib.filters import BarContext
from backtest.lib.watchers.market_structure_watcher import (
    detect_market_structure_setup,
    _RTH_START,
    _RTH_END,
    _STRUCTURE_WINDOW,
    _WINDOW_BARS,
    _MIN_BARS,
)

# Fixtures verified against crypto.lib.market_structure.analyze_structure(window=2):
_BULLISH_BOS = [100, 102, 105, 101, 99, 103, 108, 104, 102, 106, 111, 107, 105, 109, 113, 110, 108, 112, 116]
_BEARISH_CHOCH = [100, 102, 105, 101, 104, 108, 106, 110, 107, 113, 111, 99]
_STALE = [100, 102, 105, 101, 99, 103, 108, 104, 102, 106, 111, 107, 105, 109, 113, 113, 113]
_FLAT = [100.0] * 15
_TOO_FEW = [100, 101, 102, 103]


def _ts(i: int, *, hour: int = 9, minute: int = 35) -> dt.datetime:
    return dt.datetime(2026, 5, 4, hour, minute) + dt.timedelta(minutes=5 * i)


def _rows(prices: list[float], *, hour: int = 9, minute: int = 35) -> list[dict]:
    return [dict(timestamp_et=_ts(i, hour=hour, minute=minute),
                 open=p, high=p + 0.6, low=p - 0.6, close=p, volume=1000)
            for i, p in enumerate(prices)]


def _make_ctx(rows: list[dict], vix: float = 17.0) -> BarContext:
    df = pd.DataFrame(rows)
    cur = df.iloc[-1]
    return BarContext(
        bar_idx=len(df) - 1,
        timestamp_et=cur["timestamp_et"],
        bar=cur,
        prior_bars=df,
        ribbon_now=None,
        ribbon_history=[],
        vix_now=vix,
        vix_prior=vix,
        vol_baseline_20=1000.0,
        range_baseline_20=0.5,
        levels_active=[],
        multi_day_levels=[],
        htf_15m_stack=None,
    )


def run_offline() -> dict:
    results: list[dict] = []

    def record(name: str, ok: bool, note: str) -> None:
        results.append({"name": name, "pass": bool(ok), "note": note})

    # T1 — fresh bullish BOS on the last bar -> long
    sig = detect_market_structure_setup(_make_ctx(_rows(_BULLISH_BOS)))
    ok = (sig is not None and sig.direction == "long" and sig.setup_name == "STRUCTURE_BOS"
          and sig.stop_price < sig.entry_price and sig.metadata.get("broken_swing_price") is not None)
    record("T1_bullish_BOS_fires_long", ok,
           f"{sig.setup_name} dir={sig.direction} conf={sig.confidence} broke@{sig.metadata.get('broken_swing_price')}"
           if sig else "None (expected long BOS)")

    # T2 — fresh bearish CHoCH on the last bar -> short
    sig = detect_market_structure_setup(_make_ctx(_rows(_BEARISH_CHOCH)))
    ok = (sig is not None and sig.direction == "short" and sig.setup_name == "STRUCTURE_CHoCH"
          and sig.stop_price > sig.entry_price)
    record("T2_bearish_CHoCH_fires_short", ok,
           f"{sig.setup_name} dir={sig.direction} conf={sig.confidence} broke@{sig.metadata.get('broken_swing_price')}"
           if sig else "None (expected short CHoCH)")

    # T3 — STALE: a BOS printed earlier, last bars are flat -> NO emit (the key guard)
    sig = detect_market_structure_setup(_make_ctx(_rows(_STALE)))
    record("T3_stale_event_none", sig is None,
           "None (PASS — no stale re-emit)" if sig is None else f"RE-EMITTED stale {sig.setup_name}!")

    # T4 — flat series, no structure -> None
    sig = detect_market_structure_setup(_make_ctx(_rows(_FLAT)))
    record("T4_flat_none", sig is None, "None (PASS)" if sig is None else f"FIRED {sig.setup_name}")

    # T5 — too few bars -> None
    sig = detect_market_structure_setup(_make_ctx(_rows(_TOO_FEW)))
    record("T5_too_few_bars_none", sig is None, "None (PASS)" if sig is None else f"FIRED {sig.setup_name}")

    # T6 — fresh BOS but OUTSIDE RTH (premarket 06:00 start -> last bar ~07:30) -> None
    sig = detect_market_structure_setup(_make_ctx(_rows(_BULLISH_BOS, hour=6, minute=0)))
    record("T6_outside_rth_none", sig is None, "None (PASS)" if sig is None else f"FIRED outside RTH {sig.setup_name}")

    # T7 — metadata + direction-mapping contract
    sig_b = detect_market_structure_setup(_make_ctx(_rows(_BULLISH_BOS)))
    sig_s = detect_market_structure_setup(_make_ctx(_rows(_BEARISH_CHOCH)))
    md = sig_b.metadata if sig_b else {}
    needed = {"event_kind", "event_direction", "broken_swing_price", "trend",
              "confidence_is_heuristic", "promotion_prereq", "op21_live_gate"}
    ok = (sig_b is not None and sig_s is not None
          and needed.issubset(md.keys())
          and md.get("confidence_is_heuristic") is True
          and md.get("event_direction") == "bullish" and sig_b.direction == "long"
          and sig_s.metadata.get("event_direction") == "bearish" and sig_s.direction == "short"
          and sig_b.confidence in {"low", "medium", "high"})
    record("T7_metadata_and_direction_mapping", ok,
           f"missing={sorted(needed - set(md.keys()))} bull->{sig_b.direction if sig_b else '?'} "
           f"bear->{sig_s.direction if sig_s else '?'}")

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    for r in results:
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['name']:38s} {r['note']}")

    return {
        "mode": "offline",
        "constants_verified": {
            "RTH_START": str(_RTH_START),
            "RTH_END": str(_RTH_END),
            "STRUCTURE_WINDOW": _STRUCTURE_WINDOW,
            "WINDOW_BARS": _WINDOW_BARS,
            "MIN_BARS": _MIN_BARS,
        },
        "design_note": (
            "WATCH_ONLY. Fires only on a BOS/CHoCH that prints on the CURRENT bar "
            "(break_index == last) — no stale re-emit, no look-ahead. Confidence is heuristic "
            "(no published BOS/CHoCH failure stat). Live trigger requires injecting the live "
            "engine swing primitive. OP-21 live gate 0/3."
        ),
        "tests": results,
        "passed": passed,
        "total": total,
        "all_pass": passed == total,
    }


def run_live() -> dict:
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        print("  [SKIP] watcher-observations.jsonl not found")
        return {"mode": "live", "all_pass": True, "total_obs": 0}

    n_obs = 0
    by_kind: dict[str, int] = {}
    with obs_path.open(encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("watcher_name") != "market_structure":
                continue
            n_obs += 1
            k = str((o.get("metadata") or {}).get("event_kind", o.get("setup_name", "?")))
            by_kind[k] = by_kind.get(k, 0) + 1

    print(f"  [AUDIT] market_structure observations: N={n_obs} by_kind={by_kind}")
    return {"mode": "live", "all_pass": True, "total_obs": n_obs, "by_kind": by_kind}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    args = parser.parse_args(argv)

    print("\n[v49] MARKET_STRUCTURE watcher gate — BOS/CHoCH Insight stream (WATCH_ONLY, OP-21 0/3)")
    rc = 0
    if args.mode in ("offline", "both"):
        result = run_offline()
        status = "PASS" if result["all_pass"] else "FAIL"
        print(f"\n  [{status}] offline: {result['passed']}/{result['total']} tests passed")
        if not result["all_pass"]:
            rc = 1
    if args.mode in ("live", "both"):
        run_live()
    return rc


if __name__ == "__main__":
    sys.exit(main())
