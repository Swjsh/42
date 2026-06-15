"""v23_orb_warmup — regression test for ORB stateful warmup fix (L35 / T82).

Background (L35):
  `detect_orb_break` uses a module-level per-day state dict `_orb_state[date_str]`.
  The BREAKOUT → WAITING_RETEST → RETEST_HELD sequence MUST span multiple bars in a
  single process.  `Gamma_WatcherLive` spawns a fresh `pythonw.exe` every 5 min, so
  the state machine resets on every fire.

  T82 fix (shipped 2026-05-14): before calling `detect_orb_break` on the current bar,
  `watcher_live.py` replays today_bars[0..bar_idx_in_day-1] sequentially to warm up
  the state machine.  Without warmup: 0 signals across an entire ORB day.  With warmup:
  the state machine fires at the expected retest bar.

Offline tests (T1-T5):
  T1  SEQUENTIAL — feed all bars 0..N in one process → signal fires at retest bar
  T2  FRESH (no warmup) — call only the retest bar with reset state → None (broken behavior)
  T3  PROD-MIMIC (T82 warmup) — warmup 0..N-1, call bar N → signal fires (fix verified)
  T4  WARMUP_OVERHEAD — timing N bars ≤ 1000ms (≈ 80 bars × <1ms each)
  T5  INVALIDATION — price re-enters OR during WAITING_RETEST → state resets, no signal

Live: N/A — behavior test, no live data dependency.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd

# Repo root so both `backtest` and `crypto` are importable.
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from backtest.lib.watchers.orb_watcher import (
    _orb_state,
    detect_orb_break,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_state() -> None:
    for k in list(_orb_state.keys()):
        del _orb_state[k]


def _make_bar(
    ts: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 300_000,
) -> pd.Series:
    """Build a minimal bar Series matching the schema detect_orb_break expects."""
    return pd.Series({
        "timestamp_et": pd.Timestamp(ts),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def _build_synthetic_day() -> pd.DataFrame:
    """Return a synthetic ORB day with an identifiable breakout+retest pattern.

    Opening Range (09:30-09:55):  ORH=742.0, ORL=740.5 (range=$1.50 — narrow-OR gate)
    Breakout bar (10:05):         H=743.5, C=743.2, O=742.1  → BREAKOUT_LONG
    Wait bars (10:10, 10:15):     price consolidates above ORH
    Retest bar (10:20):           L=742.1, C=742.4, O=742.2  → RETEST_HELD (entry signal)

    Note: ORL changed from 739.0→740.5 (range=$3.00→$1.50) to pass MAX_OR_RANGE=2.00 gate
    wired into orb_watcher.py 2026-05-21 (ORB_NARROW_OR_GATE). The warmup test exercises
    state-machine logic; OR range is incidental and must be < 2.00 to reach WAITING_RETEST.
    """
    bars = [
        # ---- Opening Range: 09:30 to 09:55 ----
        _make_bar("2026-05-23 09:30:00", 740.6, 741.5, 740.5, 741.0, 450_000),  # L=740.5 = ORL
        _make_bar("2026-05-23 09:35:00", 741.0, 742.0, 740.7, 741.8, 400_000),
        _make_bar("2026-05-23 09:40:00", 741.8, 742.0, 741.2, 741.9, 350_000),
        _make_bar("2026-05-23 09:45:00", 741.9, 742.0, 741.5, 741.8, 320_000),
        _make_bar("2026-05-23 09:50:00", 741.8, 742.0, 741.5, 741.7, 310_000),
        _make_bar("2026-05-23 09:55:00", 741.7, 742.0, 741.6, 741.9, 300_000),
        # ---- Post-OR bars ----
        _make_bar("2026-05-23 10:00:00", 741.9, 742.2, 741.5, 742.0, 320_000),   # no breakout
        # Breakout: H > ORH=742.0, C > ORH, green (C > O)
        _make_bar("2026-05-23 10:05:00", 742.1, 743.5, 742.0, 743.2, 520_000),   # BREAKOUT_LONG
        _make_bar("2026-05-23 10:10:00", 743.2, 743.6, 742.4, 742.9, 310_000),   # wait
        _make_bar("2026-05-23 10:15:00", 742.9, 743.1, 742.2, 742.5, 290_000),   # pulling back
        # Retest: L in [741.70, 742.20], C >= ORH=742.0, green (C > O)
        _make_bar("2026-05-23 10:20:00", 742.2, 742.8, 742.1, 742.4, 410_000),   # RETEST_HELD
    ]
    df = pd.DataFrame(bars)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    return df


def _run_sequential(df: pd.DataFrame, vol_baseline: float = 350_000.0) -> Optional[object]:
    """Feed all bars 0..N sequentially; return signal if any fires."""
    _reset_state()
    sig = None
    for idx in range(len(df)):
        bar = df.iloc[idx]
        result = detect_orb_break(bar, df, idx, vol_baseline)
        if result is not None:
            sig = result
    return sig


def _run_fresh_on_retest(df: pd.DataFrame, vol_baseline: float = 350_000.0) -> Optional[object]:
    """Reset state, call ONLY the retest bar (mimics broken pre-T82 behavior)."""
    _reset_state()
    retest_idx = len(df) - 1  # last bar is the retest bar
    bar = df.iloc[retest_idx]
    return detect_orb_break(bar, df, retest_idx, vol_baseline)


def _run_warmup_then_retest(df: pd.DataFrame, vol_baseline: float = 350_000.0) -> Optional[object]:
    """T82 prod-mimic: warmup bars 0..N-2, then call bar N-1 (the retest bar)."""
    _reset_state()
    retest_idx = len(df) - 1
    for warmup_idx in range(retest_idx):
        warmup_bar = df.iloc[warmup_idx]
        try:
            detect_orb_break(warmup_bar, df, warmup_idx, vol_baseline)
        except Exception:
            pass
    bar = df.iloc[retest_idx]
    return detect_orb_break(bar, df, retest_idx, vol_baseline)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    """Run T1-T5 offline regression tests for the ORB warmup fix."""
    results = []
    df = _build_synthetic_day()
    vol_baseline = 350_000.0

    # T1: SEQUENTIAL — full bar walk in one process → signal at retest bar
    sig = _run_sequential(df, vol_baseline)
    t1_ok = sig is not None and sig.setup_name == "ORB_RETEST_LONG"
    results.append((
        "T1_sequential_fires_at_retest_bar",
        t1_ok,
        f"sig={sig.setup_name if sig else None}",
    ))

    # T2: FRESH (no warmup) — only retest bar called → no signal (broken pre-T82)
    sig_fresh = _run_fresh_on_retest(df, vol_baseline)
    t2_ok = sig_fresh is None
    results.append((
        "T2_fresh_state_produces_no_signal",
        t2_ok,
        f"sig={sig_fresh}",
    ))

    # T3: PROD-MIMIC (T82 warmup) → signal fires at retest bar
    sig_warmed = _run_warmup_then_retest(df, vol_baseline)
    t3_ok = sig_warmed is not None and sig_warmed.setup_name == "ORB_RETEST_LONG"
    results.append((
        "T3_t82_warmup_fires_at_retest_bar",
        t3_ok,
        f"sig={sig_warmed.setup_name if sig_warmed else None}",
    ))

    # T4: OVERHEAD — warmup N bars ≤ 1000ms
    _reset_state()
    t0 = time.perf_counter()
    for idx in range(len(df)):
        try:
            detect_orb_break(df.iloc[idx], df, idx, vol_baseline)
        except Exception:
            pass
    elapsed_ms = (time.perf_counter() - t0) * 1000
    t4_ok = elapsed_ms < 1000.0
    results.append((
        "T4_warmup_overhead_under_1000ms",
        t4_ok,
        f"elapsed={elapsed_ms:.1f}ms ({len(df)} bars)",
    ))

    # T5: INVALIDATION — price re-enters OR during WAITING_RETEST → state resets, no signal
    # Build a day where breakout fires but then price falls back inside OR by > $0.30
    inv_bars = [
        # ORL=740.5 (range=$1.50) — narrow-OR gate; invalidation bar (close=741.50) still
        # triggers WAITING_RETEST→NEUTRAL since 741.50 < ORH(742.0) - INVALIDATION(0.30)=741.70
        _make_bar("2026-05-24 09:30:00", 740.6, 741.5, 740.5, 741.0, 400_000),  # L=740.5 = ORL
        _make_bar("2026-05-24 09:35:00", 741.0, 742.0, 740.7, 741.8, 380_000),
        _make_bar("2026-05-24 09:40:00", 741.8, 742.0, 741.2, 741.9, 350_000),
        _make_bar("2026-05-24 09:45:00", 741.9, 742.0, 741.5, 741.7, 320_000),
        _make_bar("2026-05-24 09:50:00", 741.7, 742.0, 741.3, 741.8, 310_000),
        _make_bar("2026-05-24 09:55:00", 741.8, 742.0, 741.5, 741.9, 300_000),
        _make_bar("2026-05-24 10:00:00", 741.9, 742.2, 741.5, 742.0, 310_000),
        # Breakout
        _make_bar("2026-05-24 10:05:00", 742.1, 743.5, 742.0, 743.2, 510_000),  # BREAKOUT_LONG
        # Invalidation bar: close < ORH - 0.30 = 742.0 - 0.30 = 741.70
        _make_bar("2026-05-24 10:10:00", 743.2, 743.3, 740.5, 741.50, 280_000),  # re-enters OR → NEUTRAL
        # Attempt retest after invalidation — should produce no signal
        _make_bar("2026-05-24 10:15:00", 741.5, 742.5, 741.8, 742.2, 410_000),
    ]
    df_inv = pd.DataFrame(inv_bars)
    df_inv["timestamp_et"] = pd.to_datetime(df_inv["timestamp_et"])

    sig_inv = _run_sequential(df_inv, vol_baseline)
    t5_ok = sig_inv is None
    results.append((
        "T5_invalidation_resets_state_no_signal",
        t5_ok,
        f"sig={'None (correct)' if sig_inv is None else sig_inv.setup_name}",
    ))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note[:120]} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live() -> dict:
    """No live data source required — ORB warmup is a state-machine behavior test."""
    return {
        "mode": "live",
        "pass": True,
        "note": (
            "ORB warmup regression is offline-only — tests state machine behavior, "
            "not live market data. T1-T5 cover sequential / fresh / warmup / overhead / "
            "invalidation scenarios using synthetic SPY-like bars."
        ),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)

    sc = {}
    if args.mode in ("offline", "both"):
        sc["offline"] = run_offline()
        print(f"=== OFFLINE === {sc['offline']['passed']}/{sc['offline']['total']} pass")
        for t in sc["offline"]["tests"]:
            print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:55s} {t['note']}")

    if args.mode in ("live", "both"):
        sc["live"] = run_live()
        print(f"\n=== LIVE === {sc['live']['note']}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(sc, indent=2, default=str))

    all_ok = True
    if "offline" in sc and not sc["offline"]["all_pass"]:
        all_ok = False
    if "live" in sc and not sc["live"]["pass"]:
        all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
