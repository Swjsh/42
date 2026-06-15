"""v40_bearish_rejection_morning_gate — BEARISH_REJECTION_MORNING watcher correctness gate.

Background:
  2026-05-24: bearish_rejection_morning_watcher.py ships as WATCH_ONLY.
  Designed to capture J's highest-value BEAR entries:
    - 2026-04-29 10:25 ET: SPY 710P ×6 → +$342 ("711.4 rejection + ribbon flip")
    - 2026-05-04 10:27 ET: SPY 721P ×10 → +$730 ("premarket level + trendline + ribbon flip")

  DISTINCT from BEARISH_REVERSAL_AT_LEVEL (11:00+, ribbon=BULL countertrend).
  THIS watcher: 09:35-10:55 ET, ribbon=BEAR (entering WITH the flip).

  Key thresholds:
    ENTRY_TIME_START   = 09:35 ET
    ENTRY_TIME_END     = 10:55 ET
    LEVEL_PROXIMITY    = $0.50 (bar high within $0.50 of a ★★★ level)
    REJECTION_BODY_MIN = 15 cents below level
    VOLUME_MULTIPLIER  = 1.5× 20-bar average
    ribbon=BEAR required at bar close

Offline tests (10 total):

  T01  All conditions met (10:25, ribbon=BEAR, level reject 25c, vol=2.0×, bear candle)
       → WatcherSignal with confidence="medium" returned
  T02  HIGH conf: body=35c, vol=3.0×, bear candle → confidence="high"
  T03  LOW conf: body=15c (minimum), vol=1.5×, doji (close≥open) → confidence="low"
  T04  Time too early (09:30 — before gate) → None
  T05  Time too late (11:00 — after morning window) → None
  T06  Ribbon is BULL (not BEAR) → None (wrong ribbon — this is not countertrend)
  T07  No level in proximity (bar high $0.60 below nearest level) → None
  T08  Level in proximity but close ≥ level (no rejection body) → None
  T09  Volume below threshold (vol_ratio=1.4× < 1.5×) → None
  T10  Doji bar (close=open) with medium vol and body → confidence="low" (downgraded)

Live audit (informational):
  Scan watcher-observations.jsonl for bearish_rejection_morning_watcher rows.
  Report confidence distribution and any anomalies.
  pass=True always (evidence audit, not blocking).

Exit code:
  0 — all offline tests PASS
  1 — any offline test FAIL
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

from backtest.lib.filters import BarContext, RibbonState
from backtest.lib.watchers.bearish_rejection_morning_watcher import (
    detect_bearish_rejection_morning,
    ENTRY_TIME_START,
    ENTRY_TIME_END,
    LEVEL_PROXIMITY_DOLLARS,
    REJECTION_BODY_MIN_CENTS,
    VOLUME_MULTIPLIER,
)


# ---------------------------------------------------------------------------
# Bar + context factory helpers
# ---------------------------------------------------------------------------

_BASE_DATE = dt.date(2026, 4, 29)    # J's 4/29 anchor day


def _make_bar(
    hour: int,
    minute: int,
    bar_open: float = 711.70,
    bar_high: float = 712.00,
    bar_close: float = 711.60,
    bar_low: float = 711.50,
    volume: float = 90_000,
) -> pd.Series:
    ts = dt.datetime(2026, 4, 29, hour, minute, tzinfo=dt.timezone.utc)
    return pd.Series({
        "timestamp_et": ts,
        "open": bar_open,
        "high": bar_high,
        "close": bar_close,
        "low": bar_low,
        "volume": volume,
    })


def _make_ctx(
    bar: pd.Series,
    ribbon_stack: str = "BEAR",
    levels: Optional[list] = None,
    vol_baseline: float = 50_000.0,
    htf_15m: str = "BEAR",
) -> BarContext:
    ts = bar["timestamp_et"]
    # Convert naive UTC to naive ET (subtract 4h for EDT)
    ts_et = ts.replace(tzinfo=None) - dt.timedelta(hours=4)
    ts_et = ts_et.replace(tzinfo=dt.timezone(dt.timedelta(hours=-4)))

    ribbon = RibbonState(fast=710.5, pivot=711.0, slow=711.5, spread_cents=10.0, stack=ribbon_stack)

    # Minimal prior_bars DataFrame (just enough for internal computations)
    prior_df = pd.DataFrame([{
        "timestamp_et": ts,
        "open": bar["open"],
        "high": bar["high"],
        "close": bar["close"],
        "low": bar["low"],
        "volume": bar["volume"],
    }])

    if levels is None:
        levels = [712.00]   # default: ★★★ level at 712.00

    return BarContext(
        bar_idx=10,
        timestamp_et=ts_et,
        bar=bar,
        prior_bars=prior_df,
        ribbon_now=ribbon,
        ribbon_history=[],
        vix_now=18.5,
        vix_prior=17.0,
        vol_baseline_20=vol_baseline,
        range_baseline_20=1.5,
        levels_active=levels,
        multi_day_levels=[],
        htf_15m_stack=htf_15m,
    )


# ---------------------------------------------------------------------------
# Offline tests
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    results = []

    def check(label: str, signal, expected_signal: bool, expected_conf: Optional[str] = None):
        got_signal = signal is not None
        passed = got_signal == expected_signal
        if expected_conf and got_signal:
            passed = passed and (signal.confidence == expected_conf)
        results.append({"label": label, "passed": passed, "got_signal": got_signal,
                         "got_conf": signal.confidence if signal else None, "expected_conf": expected_conf})

    # T01: All conditions met (10:25, ribbon=BEAR, level=712.00, bar_high=712.00,
    #      bar_close=711.75, body=25c, vol=2.0×) → signal, confidence="medium"
    bar = _make_bar(14, 25, bar_open=711.80, bar_high=712.00, bar_close=711.75, volume=100_000)
    ctx = _make_ctx(bar, ribbon_stack="BEAR", levels=[712.00], vol_baseline=50_000.0)
    sig = detect_bearish_rejection_morning(ctx)
    check("T01 all-conds-medium", sig, True, "medium")

    # T02: HIGH conf — body=35c, vol=3.0×, bear candle → confidence="high"
    bar = _make_bar(14, 25, bar_open=711.80, bar_high=712.00, bar_close=711.65, volume=150_000)
    ctx = _make_ctx(bar, ribbon_stack="BEAR", levels=[712.00], vol_baseline=50_000.0)
    sig = detect_bearish_rejection_morning(ctx)
    check("T02 high-conf", sig, True, "high")

    # T03: LOW conf — minimum thresholds, doji candle (close >= open)
    bar = _make_bar(14, 25, bar_open=711.60, bar_high=712.00, bar_close=711.85, volume=75_000)
    ctx = _make_ctx(bar, ribbon_stack="BEAR", levels=[712.00], vol_baseline=50_000.0)
    sig = detect_bearish_rejection_morning(ctx)
    # close=711.85 is below 712.00 by 15c (just at minimum), open=711.60, close>open → doji
    # body=15c (minimum), vol=1.5×, close>open → should fire at LOW conf
    check("T03 low-conf-doji", sig, True, "low")

    # T04: Time too early (09:30 — before ENTRY_TIME_START 09:35)
    bar = _make_bar(13, 30, bar_open=711.80, bar_high=712.00, bar_close=711.70, volume=100_000)
    ctx = _make_ctx(bar, ribbon_stack="BEAR", levels=[712.00], vol_baseline=50_000.0)
    sig = detect_bearish_rejection_morning(ctx)
    check("T04 time-too-early", sig, False)

    # T05: Time too late (11:00 ET — after ENTRY_TIME_END 10:55)
    bar = _make_bar(15, 0, bar_open=711.80, bar_high=712.00, bar_close=711.70, volume=100_000)
    ctx = _make_ctx(bar, ribbon_stack="BEAR", levels=[712.00], vol_baseline=50_000.0)
    sig = detect_bearish_rejection_morning(ctx)
    check("T05 time-too-late", sig, False)

    # T06: Ribbon is BULL (countertrend — not what this watcher watches)
    bar = _make_bar(14, 25, bar_open=711.80, bar_high=712.00, bar_close=711.75, volume=100_000)
    ctx = _make_ctx(bar, ribbon_stack="BULL", levels=[712.00], vol_baseline=50_000.0)
    sig = detect_bearish_rejection_morning(ctx)
    check("T06 ribbon-bull-blocked", sig, False)

    # T07: No level in proximity (bar_high=711.40, nearest level=712.10 — gap=$0.70 > $0.50)
    bar = _make_bar(14, 25, bar_open=711.20, bar_high=711.40, bar_close=711.20, volume=100_000)
    ctx = _make_ctx(bar, ribbon_stack="BEAR", levels=[712.10], vol_baseline=50_000.0)
    sig = detect_bearish_rejection_morning(ctx)
    check("T07 no-level-proximity", sig, False)

    # T08: Level in proximity but close >= level (no rejection — bar closed ABOVE level)
    bar = _make_bar(14, 25, bar_open=712.30, bar_high=712.50, bar_close=712.10, volume=100_000)
    ctx = _make_ctx(bar, ribbon_stack="BEAR", levels=[712.00], vol_baseline=50_000.0)
    sig = detect_bearish_rejection_morning(ctx)
    # close=712.10 > level=712.00, so (level - close) = -10c < 15c threshold → no rejection
    check("T08 close-above-level", sig, False)

    # T09: Volume below threshold (vol_ratio=1.4× < 1.5× minimum)
    bar = _make_bar(14, 25, bar_open=711.80, bar_high=712.00, bar_close=711.75, volume=69_000)
    ctx = _make_ctx(bar, ribbon_stack="BEAR", levels=[712.00], vol_baseline=50_000.0)
    sig = detect_bearish_rejection_morning(ctx)
    # vol_ratio = 69000/50000 = 1.38 < 1.5
    check("T09 vol-too-low", sig, False)

    # T10: Medium criteria but close=open (doji) — should downgrade to LOW
    bar = _make_bar(14, 25, bar_open=711.75, bar_high=712.00, bar_close=711.75, volume=100_000)
    ctx = _make_ctx(bar, ribbon_stack="BEAR", levels=[712.00], vol_baseline=50_000.0)
    sig = detect_bearish_rejection_morning(ctx)
    # close=711.75, level=712.00, body=25c (meets "medium"), vol=2×, but close=open (doji)
    # Should fire but at LOW conf (downgraded from medium due to doji)
    check("T10 doji-downgrade-to-low", sig, True, "low")

    passed_n = sum(1 for r in results if r["passed"])
    total_n = len(results)
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        conf_str = f" got_conf={r['got_conf']!r}" if r.get("got_conf") else ""
        expected_str = f" expected_conf={r['expected_conf']!r}" if r.get("expected_conf") else ""
        signal_str = f"signal={'YES' if r['got_signal'] else 'NO ':3s}"
        print(f"  [{status}] {r['label']:40s} {signal_str}{conf_str}{expected_str}")

    return {"passed": passed_n, "total": total_n, "all_pass": passed_n == total_n, "results": results}


# ---------------------------------------------------------------------------
# Live audit
# ---------------------------------------------------------------------------

def run_live() -> dict:
    obs_path = _ROOT / "automation" / "state" / "watcher-observations.jsonl"
    if not obs_path.exists():
        print("  [SKIP] watcher-observations.jsonl not found")
        return {"all_pass": True, "mode": "live", "total": 0}

    brm_obs = []
    with obs_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("watcher_name") == "bearish_rejection_morning_watcher":
                brm_obs.append(obj)

    from collections import Counter
    conf_counts = Counter(o.get("confidence", "unknown") for o in brm_obs)
    pnl_values = [o.get("would_be_pnl_dollars") for o in brm_obs if o.get("would_be_pnl_dollars") is not None]
    wins = sum(1 for p in pnl_values if p > 0)
    wr = wins / len(pnl_values) * 100 if pnl_values else 0

    print(f"  [AUDIT] bearish_rejection_morning_watcher obs: N={len(brm_obs)}")
    print(f"          conf: high={conf_counts.get('high',0)} medium={conf_counts.get('medium',0)} low={conf_counts.get('low',0)}")
    if pnl_values:
        print(f"          graded: N={len(pnl_values)} WR={wr:.1f}% avg=${sum(pnl_values)/len(pnl_values):.2f}")
    else:
        print(f"          graded: 0 (watcher recently shipped — live accumulation in progress)")
    print(f"          promotion status: WATCH_ONLY (live gate: {len(brm_obs)}/3 J confirmations)")

    return {
        "mode": "live",
        "all_pass": True,
        "total_obs": len(brm_obs),
        "conf_high": conf_counts.get("high", 0),
        "conf_medium": conf_counts.get("medium", 0),
        "conf_low": conf_counts.get("low", 0),
        "graded_n": len(pnl_values),
        "wr_pct": round(wr, 1),
        "promotion_status": "WATCH_ONLY — needs 3+ J live confirmations",
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["offline", "live", "both"],
        default="offline",
        help="offline=deterministic gate tests; live=obs audit; both=all",
    )
    args = parser.parse_args(argv)

    print(f"\n[v40] BEARISH_REJECTION_MORNING watcher gate — mode={args.mode}")
    print(f"      TIME_WINDOW = {ENTRY_TIME_START}–{ENTRY_TIME_END} ET")
    print(f"      LEVEL_PROX  = ${LEVEL_PROXIMITY_DOLLARS:.2f}  BODY_MIN = {REJECTION_BODY_MIN_CENTS:.0f}c  VOL_MIN = {VOLUME_MULTIPLIER:.1f}×")

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
