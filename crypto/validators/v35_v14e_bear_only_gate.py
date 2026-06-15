"""v35_v14e_bear_only_gate — V14E_DIRECTION_FILTER regression gate.

Background:
  2026-05-21: V14E_DIRECTION_FILTER = "bear" added to v14_enhanced_watcher.py.
  502 graded watcher observations showed:
    direction=short: N=241, WR=58.5%, P&L=+$1,492 (bear branch — POSITIVE EDGE)
    direction=long:  N=261, WR=47.9%, P&L=-$3,642 (bull branch — STRUCTURAL DRAG)

  The gate is at v14_enhanced_watcher.py lines 178-179:
    if V14E_DIRECTION_FILTER == "bear":
        return None  # direction filter: accumulate bear-only forward observations

  Evidence: analysis/backtests/v14e-bear-gate/results.json (BEAR_ONLY WR=58.5%, +$1,492)

Offline tests (6 total):

  T1  filter="bear", bear_setup passes → WatcherSignal(direction="short") returned
      Bear always passes through regardless of direction filter value.
  T2  filter="bear", bear_setup fails → None (bull blocked, gate enforced)
  T3  filter=None, bear fails, bull passes → WatcherSignal(direction="long")
      When filter=None bull branch runs and can produce a signal.
  T4  filter=None, bear fails, bull fails → None (neither side fired)
  T5  filter="bear", bear passes with confluence → confidence="high" in signal
      Verifies the confidence mapping path is correct on the bear branch.
  T6  filter="bear", bear passes → bull is never called (short-circuit verified)
      Regression guard: bull evaluation should be skipped when bear passes.

Live tests (audit mode):
  Scan watcher-observations.jsonl for v14_enhanced_watcher observations with
  direction="long". Since V14E_DIRECTION_FILTER="bear" is live, any such row
  was either recorded before the gate shipped or indicates a gate regression.
  pass=True always (informational audit, not a blocking gate).

Modes:
  offline  6 deterministic gate tests. All 6 must PASS.
  live     Audit: count long-direction obs from v14_enhanced. pass=True always.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import pandas as pd

import backtest.lib.watchers.v14_enhanced_watcher as _mod
from backtest.lib.filters import SetupResult, BullishSetupResult
from backtest.lib.watchers import WatcherSignal


# ---------------------------------------------------------------------------
# Stubs for evaluate_bearish_setup / evaluate_bullish_setup
# ---------------------------------------------------------------------------

def _bear_pass(level: float = 750.0, has_confluence: bool = False) -> SetupResult:
    triggers = ["level_rejection", "ribbon_flip"]
    if has_confluence:
        triggers.append("confluence")
    return SetupResult(
        passed=True,
        bear_score=8,
        blockers=[],
        triggers_fired=triggers,
        rejection_level=level,
        ribbon_just_flipped_bearish=True,
        confluence_match=level if has_confluence else None,
    )


def _bear_fail() -> SetupResult:
    return SetupResult(
        passed=False,
        bear_score=3,
        blockers=[1, 2, 3],
        triggers_fired=[],
    )


def _bull_pass(level: float = 750.0) -> BullishSetupResult:
    return BullishSetupResult(
        passed=True,
        bull_score=9,
        blockers=[],
        triggers_fired=["level_reclaim", "ribbon_flip"],
        reclaim_level=level,
        ribbon_just_flipped_bullish=True,
    )


def _bull_fail() -> BullishSetupResult:
    return BullishSetupResult(
        passed=False,
        bull_score=2,
        blockers=[1, 2, 3],
        triggers_fired=[],
    )


def _minimal_ctx(bar_close: float = 750.0, hour: int = 13) -> object:
    """Minimal namespace satisfying BarContext attributes checked before eval_* calls.

    Default hour=13 (PM) so direction-filter tests are outside the chop zone.
    Pass hour=10 or hour=11 to test chop-zone gate behavior.
    """
    import types
    ctx = types.SimpleNamespace()
    ctx.bar = pd.Series({
        "close": bar_close, "open": bar_close - 0.5,
        "high": bar_close + 0.5, "low": bar_close - 1.0, "volume": 10000,
    })
    ctx.bar_idx = 0
    ctx.timestamp_et = dt.datetime(2026, 5, 21, hour, 0, 0)
    row = {"close": bar_close, "open": bar_close - 0.5, "high": bar_close + 0.5, "low": bar_close - 1.0, "volume": 10000}
    ctx.prior_bars = pd.DataFrame([row] * 25)
    ctx.ribbon_now = None
    ctx.ribbon_history = []
    ctx.vix_now = 15.0
    ctx.vix_prior = 15.0
    ctx.vol_baseline_20 = 10000.0
    ctx.range_baseline_20 = 2.0
    ctx.levels_active = [bar_close]
    ctx.multi_day_levels = [bar_close]
    ctx.htf_15m_stack = None
    ctx.level_states = {}
    return ctx


# ---------------------------------------------------------------------------
# Offline tests
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    results: list[dict] = []
    ctx = _minimal_ctx()

    # ----- T1: filter="bear", bear passes → short signal returned -----
    _orig_dir = _mod.V14E_DIRECTION_FILTER
    _orig_bear = _mod.evaluate_bearish_setup
    _orig_bull = _mod.evaluate_bullish_setup
    try:
        bull_call_count = {"n": 0}

        def _bear_pass_fn(ctx, **kw):
            return _bear_pass()

        def _bull_never_fn(ctx, **kw):
            bull_call_count["n"] += 1
            return _bull_pass()

        _mod.V14E_DIRECTION_FILTER = "bear"
        _mod.evaluate_bearish_setup = _bear_pass_fn
        _mod.evaluate_bullish_setup = _bull_never_fn

        sig = _mod.detect_v14_enhanced_setup(ctx)
        t1_ok = (
            sig is not None
            and sig.direction == "short"
            and sig.watcher_name == "v14_enhanced_watcher"
            and sig.setup_name == "BEARISH_REJECTION_v14e"
        )
        results.append({
            "test": "T1",
            "desc": 'filter="bear", bear passes -> short signal returned',
            "pass": t1_ok,
            "detail": f"sig={sig.direction if sig else None}",
        })

        # ----- T6 (while still in T1 setup): bear passes, verify bull never called -----
        t6_ok = bull_call_count["n"] == 0
        results.append({
            "test": "T6",
            "desc": 'filter="bear", bear passes -> bull eval never called (short-circuit)',
            "pass": t6_ok,
            "detail": f"bull_calls={bull_call_count['n']} (expected 0)",
        })

        # ----- T2: filter="bear", bear fails -> None (bull blocked) -----
        bull_call_count["n"] = 0

        def _bear_fail_fn(ctx, **kw):
            return _bear_fail()

        _mod.evaluate_bearish_setup = _bear_fail_fn
        _mod.evaluate_bullish_setup = _bull_never_fn

        sig = _mod.detect_v14_enhanced_setup(ctx)
        t2_ok = sig is None and bull_call_count["n"] == 0
        results.append({
            "test": "T2",
            "desc": 'filter="bear", bear fails -> None (bull blocked)',
            "pass": t2_ok,
            "detail": f"sig={'None' if sig is None else sig.direction}, bull_calls={bull_call_count['n']}",
        })

        # ----- T3: filter=None, bear fails, bull passes -> long signal returned -----
        _mod.V14E_DIRECTION_FILTER = None

        def _bull_pass_fn(ctx, **kw):
            return _bull_pass()

        _mod.evaluate_bearish_setup = _bear_fail_fn
        _mod.evaluate_bullish_setup = _bull_pass_fn

        sig = _mod.detect_v14_enhanced_setup(ctx)
        t3_ok = (
            sig is not None
            and sig.direction == "long"
            and sig.setup_name == "BULLISH_RECLAIM_v14e"
        )
        results.append({
            "test": "T3",
            "desc": "filter=None, bear fails, bull passes -> long signal returned",
            "pass": t3_ok,
            "detail": f"sig={sig.direction if sig else None}",
        })

        # ----- T4: filter=None, bear fails, bull fails -> None -----
        def _bull_fail_fn(ctx, **kw):
            return _bull_fail()

        _mod.evaluate_bullish_setup = _bull_fail_fn
        sig = _mod.detect_v14_enhanced_setup(ctx)
        t4_ok = sig is None
        results.append({
            "test": "T4",
            "desc": "filter=None, bear fails, bull fails -> None",
            "pass": t4_ok,
            "detail": f"sig={'None' if sig is None else sig.direction}",
        })

        # ----- T5: filter="bear", bear passes with confluence -> confidence="high" -----
        _mod.V14E_DIRECTION_FILTER = "bear"

        def _bear_confluence_fn(ctx, **kw):
            return _bear_pass(level=750.0, has_confluence=True)

        _mod.evaluate_bearish_setup = _bear_confluence_fn

        sig = _mod.detect_v14_enhanced_setup(ctx)
        t5_ok = (
            sig is not None
            and sig.direction == "short"
            and sig.confidence == "high"
        )
        results.append({
            "test": "T5",
            "desc": 'filter="bear", bear passes with confluence -> confidence="high"',
            "pass": t5_ok,
            "detail": f"sig={sig.direction if sig else None} confidence={getattr(sig, 'confidence', None) if sig else None}",
        })

    finally:
        _mod.V14E_DIRECTION_FILTER = _orig_dir
        _mod.evaluate_bearish_setup = _orig_bear
        _mod.evaluate_bullish_setup = _orig_bull

    all_pass = all(r["pass"] for r in results)
    passed_n = sum(1 for r in results if r["pass"])
    total_n = len(results)

    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        print(f"  [{status}] {r['test']}: {r['desc']}")
        if not r["pass"]:
            print(f"         detail={r['detail']}")

    return {
        "mode": "offline",
        "pass": all_pass,
        "passed": passed_n,
        "total": total_n,
        "tests": results,
    }


# ---------------------------------------------------------------------------
# Live tests (audit mode)
# ---------------------------------------------------------------------------

def run_live() -> dict:
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        return {
            "mode": "live",
            "pass": True,
            "note": "watcher-observations.jsonl not found (no data yet)",
            "long_obs_count": 0,
            "total_v14e_obs": 0,
        }

    v14e_obs = []
    long_obs = []
    with obs_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("watcher_name") != "v14_enhanced_watcher":
                continue
            v14e_obs.append(row)
            if row.get("direction") == "long":
                long_obs.append(row)

    if long_obs:
        print(
            f"  [AUDIT] {len(long_obs)} long-direction v14e obs found "
            f"(pre-gate or regression). Most recent: "
            f"{long_obs[-1].get('bar_timestamp_et', '?')[:10]}"
        )
    else:
        print(f"  [AUDIT] 0 long-direction obs in {len(v14e_obs)} total v14e observations. Gate healthy.")

    return {
        "mode": "live",
        "pass": True,
        "note": "audit only — pass=True regardless of count",
        "long_obs_count": len(long_obs),
        "total_v14e_obs": len(v14e_obs),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", choices=["offline", "live"], default="offline")
    args = parser.parse_args()

    print(f"\n[v35] V14E_DIRECTION_FILTER gate — mode={args.mode}")
    if args.mode == "live":
        result = run_live()
    else:
        result = run_offline()

    status = "PASS" if result["pass"] else "FAIL"
    if args.mode == "offline":
        print(f"\n  [{status}] {result['passed']}/{result['total']} tests passed")
    else:
        print(f"\n  [{status}] audit complete")
    sys.exit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
