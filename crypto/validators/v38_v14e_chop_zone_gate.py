"""v38_v14e_chop_zone_gate — Chop-zone quality elevation regression gate.

Background:
  2026-05-24: V14E_CHOP_HOURS = {10, 11} and V14E_CHOP_MIN_SCORE = 9 added to
  v14_enhanced_watcher.py (OP-22 engine-benefit).

  IS/OOS walk-forward (backtest/autoresearch/_v14e_ampm_oos.py) confirmed:
    10:xx IS: WR=50% exp=-$18.14  OOS: WR=41.7%  (negative edge)
    11:xx IS: WR=31.2% exp=-$17.93  OOS: WR=45.8% exp=-$7.65  (negative edge)
    HIGH+AM OOS: N=7 WR=71.4% (positive — quality matters in chop zone)

  Gate logic added to detect_v14_enhanced_setup() bear branch:
    if bar_hour in V14E_CHOP_HOURS:
        if confidence != "high" or bear_score < V14E_CHOP_MIN_SCORE:
            return None   # suppress low-quality chop-zone signal

  Candidate: strategy/candidates/2026-05-24-v14e-bear-time-of-day-gate.md

Offline tests (8 total):

  T1  chop-hour (10:xx), low-quality (score=7, conf=low): blocked -> None
  T2  chop-hour (11:xx), low-quality (score=8, conf=medium): blocked -> None
  T3  chop-hour (10:xx), high quality (score=9, conf=high): passes -> short signal
  T4  chop-hour (11:xx), high quality (score=10, conf=high): passes -> short signal
  T5  PM hour (13:xx), low quality (score=7, conf=low): passes (no chop gate)
  T6  opening hour (09:xx), low quality (score=7): passes (09:xx not in chop hours)
  T7  chop-hour (10:xx), conf=high but score=8 (<9): blocked (score too low)
  T8  chop-hour (10:xx), score=9 but conf=medium (<high): blocked (conf too low)

Live tests:
  Audit watcher-observations.jsonl for v14e chop-hour observations.
  Reports how many fired in {10, 11}:xx and whether they meet quality threshold.
  pass=True always (informational audit).

Modes:
  offline  8 deterministic tests. All 8 must PASS.
  live     Audit mode — pass=True always.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import pandas as pd

import backtest.lib.watchers.v14_enhanced_watcher as _mod
from backtest.lib.filters import SetupResult
from backtest.lib.watchers import WatcherSignal


# ---------------------------------------------------------------------------
# Stub factories
# ---------------------------------------------------------------------------

def _bear_result(
    passed: bool = True,
    score: int = 8,
    has_confluence: bool = False,
    n_extra_triggers: int = 0,
) -> SetupResult:
    triggers = ["level_rejection", "ribbon_flip"]
    if has_confluence:
        triggers.append("confluence")
    for i in range(n_extra_triggers):
        triggers.append(f"extra_{i}")
    return SetupResult(
        passed=passed,
        bear_score=score,
        blockers=[],
        triggers_fired=triggers,
        rejection_level=750.0,
        ribbon_just_flipped_bearish=True,
        confluence_match=750.0 if has_confluence else None,
    )


def _ctx_at(hour: int, bar_close: float = 750.0) -> object:
    """Create a minimal BarContext-like namespace with a specific bar hour."""
    import types
    ctx = types.SimpleNamespace()
    ctx.bar = pd.Series({
        "close": bar_close, "open": bar_close - 0.5,
        "high": bar_close + 0.5, "low": bar_close - 1.0, "volume": 10000,
    })
    ctx.bar_idx = 0
    ctx.timestamp_et = dt.datetime(2026, 5, 24, hour, 15, 0)
    ctx.prior_bars = pd.DataFrame([{
        "close": bar_close, "open": bar_close - 0.5,
        "high": bar_close + 0.5, "low": bar_close - 1.0, "volume": 10000,
    }] * 25)
    ctx.ribbon_now = None
    ctx.ribbon_history = []
    ctx.vix_now = 18.0
    ctx.vix_prior = 17.5
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

    _orig_dir  = _mod.V14E_DIRECTION_FILTER
    _orig_bear = _mod.evaluate_bearish_setup
    _orig_bull = _mod.evaluate_bullish_setup

    def _bull_never(ctx, **kw):
        raise AssertionError("bull branch must not be called in bear-only mode")

    try:
        _mod.V14E_DIRECTION_FILTER = "bear"
        _mod.evaluate_bullish_setup = _bull_never

        # --- T1: chop hour 10:xx, low quality (score=7, conf=low) -> blocked ---
        _mod.evaluate_bearish_setup = lambda ctx, **kw: _bear_result(score=7, has_confluence=False)
        sig = _mod.detect_v14_enhanced_setup(_ctx_at(10))
        ok = sig is None
        results.append({"test": "T1", "pass": ok,
                        "desc": "chop-hour 10:xx, score=7 conf=low -> blocked (None)",
                        "detail": f"sig={sig}"})

        # --- T2: chop hour 11:xx, medium quality (score=8, conf=medium) -> blocked ---
        _mod.evaluate_bearish_setup = lambda ctx, **kw: _bear_result(score=8, has_confluence=False)
        sig = _mod.detect_v14_enhanced_setup(_ctx_at(11))
        ok = sig is None
        results.append({"test": "T2", "pass": ok,
                        "desc": "chop-hour 11:xx, score=8 conf=medium -> blocked (None)",
                        "detail": f"sig={sig}"})

        # --- T3: chop hour 10:xx, high quality (score=9, conf=high) -> passes ---
        # conf=high requires: has_confluence=True AND n_triggers>=3
        _mod.evaluate_bearish_setup = lambda ctx, **kw: _bear_result(
            score=9, has_confluence=True)
        sig = _mod.detect_v14_enhanced_setup(_ctx_at(10))
        ok = (sig is not None and sig.direction == "short" and sig.confidence == "high")
        results.append({"test": "T3", "pass": ok,
                        "desc": "chop-hour 10:xx, score=9 conf=high -> passes, short signal",
                        "detail": f"sig={sig.direction if sig else None} conf={getattr(sig,'confidence',None)}"})

        # --- T4: chop hour 11:xx, high quality (score=10, conf=high) -> passes ---
        _mod.evaluate_bearish_setup = lambda ctx, **kw: _bear_result(
            score=10, has_confluence=True)
        sig = _mod.detect_v14_enhanced_setup(_ctx_at(11))
        ok = (sig is not None and sig.direction == "short" and sig.confidence == "high")
        results.append({"test": "T4", "pass": ok,
                        "desc": "chop-hour 11:xx, score=10 conf=high -> passes, short signal",
                        "detail": f"sig={sig.direction if sig else None} conf={getattr(sig,'confidence',None)}"})

        # --- T5: PM hour (13:xx), low quality -> passes (no chop gate) ---
        _mod.evaluate_bearish_setup = lambda ctx, **kw: _bear_result(score=7, has_confluence=False)
        sig = _mod.detect_v14_enhanced_setup(_ctx_at(13))
        ok = (sig is not None and sig.direction == "short")
        results.append({"test": "T5", "pass": ok,
                        "desc": "PM 13:xx, score=7 conf=low -> passes (chop gate does not apply)",
                        "detail": f"sig={sig.direction if sig else None}"})

        # --- T6: opening hour (09:xx), low quality -> passes (09:xx not in chop hours) ---
        _mod.evaluate_bearish_setup = lambda ctx, **kw: _bear_result(score=7, has_confluence=False)
        sig = _mod.detect_v14_enhanced_setup(_ctx_at(9))
        ok = (sig is not None and sig.direction == "short")
        results.append({"test": "T6", "pass": ok,
                        "desc": "09:xx, score=7 conf=low -> passes (09:xx not in V14E_CHOP_HOURS)",
                        "detail": f"sig={sig.direction if sig else None}"})

        # --- T7: chop hour 10:xx, conf=high but score=8 (<9) -> blocked ---
        # high-conf (has_confluence=True, n_triggers=3) but score too low
        _mod.evaluate_bearish_setup = lambda ctx, **kw: _bear_result(
            score=8, has_confluence=True)
        sig = _mod.detect_v14_enhanced_setup(_ctx_at(10))
        ok = sig is None
        results.append({"test": "T7", "pass": ok,
                        "desc": "chop-hour 10:xx, conf=high score=8 (<9) -> blocked (score too low)",
                        "detail": f"sig={sig}"})

        # --- T8: chop hour 10:xx, score=9 but conf=medium -> blocked ---
        # score >= 9 but no confluence -> conf=medium, not high
        _mod.evaluate_bearish_setup = lambda ctx, **kw: _bear_result(
            score=9, has_confluence=False)
        sig = _mod.detect_v14_enhanced_setup(_ctx_at(10))
        ok = sig is None
        results.append({"test": "T8", "pass": ok,
                        "desc": "chop-hour 10:xx, score=9 conf=medium (no confluence) -> blocked (conf too low)",
                        "detail": f"sig={sig}"})

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
# Live audit
# ---------------------------------------------------------------------------

def run_live() -> dict:
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        return {"mode": "live", "pass": True,
                "note": "watcher-observations.jsonl not found", "chop_fires": 0}

    chop_total = 0
    chop_high_quality = 0
    chop_low_quality = 0
    seen_keys: set[str] = set()

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
            if row.get("direction") not in ("short", "bear"):
                continue
            ts = row.get("bar_timestamp_et", "")
            key = ts[:16]
            if key in seen_keys:
                continue
            seen_keys.add(key)

            try:
                hour = dt.datetime.fromisoformat(ts).hour
            except Exception:
                continue
            if hour not in _mod.V14E_CHOP_HOURS:
                continue

            chop_total += 1
            conf = row.get("confidence", "")
            score = row.get("metadata", {}).get("score", 0) if isinstance(row.get("metadata"), dict) else 0
            if conf == "high" and score >= _mod.V14E_CHOP_MIN_SCORE:
                chop_high_quality += 1
            else:
                chop_low_quality += 1

    print(f"  [AUDIT] chop-zone v14e bear obs: "
          f"total={chop_total} high_quality={chop_high_quality} "
          f"low_quality_blocked={chop_low_quality}")
    if chop_low_quality > 0:
        print(f"  [INFO]  {chop_low_quality} chop-zone obs would now be blocked "
              f"(pre-gate data, not a regression)")

    return {
        "mode": "live",
        "pass": True,
        "note": "audit only — pass=True regardless",
        "chop_fires": chop_total,
        "chop_high_quality": chop_high_quality,
        "chop_low_quality": chop_low_quality,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", choices=["offline", "live"], default="offline")
    args = parser.parse_args()

    print(f"\n[v38] V14E_CHOP_ZONE_GATE — mode={args.mode}")
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
