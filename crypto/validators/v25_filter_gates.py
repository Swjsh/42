"""v25_filter_gates — boundary-condition regression tests for heartbeat filters F1-F11.

Background:
  `backtest/lib/filters.py` implements the 10 bearish + 11 bullish entry filters. The
  threshold constants in filters.py MUST stay in sync with `automation/state/params.json`.
  Without an automated gate, a future edit can silently change a threshold (e.g. F6
  ribbon_spread_min_cents) and only show up as a live mis-fire hours later.

  This validator exercises each filter's boundary at +ε (PASS) and -ε (BLOCK), and
  verifies that the params.json threshold values match the filters.py constants.

Offline tests:
  B1a/B1b  F1 time gate PASS/BLOCK (09:35 ET boundary)
  B5a/B5b  F5 ribbon-stack PASS(BEAR)/BLOCK(MIXED)
  B6a/B6b  F6 ribbon-spread PASS(30c)/BLOCK(29c)
  B8a/B8b  F8 VIX PASS(>17.30 rising)/BLOCK(<17.30)
  B8c      F8 VIX BLOCK when flat (not rising)
  B8d      F8 vix_soft_mode: VIX fail becomes score modifier, not hard block
  B9a/B9b  F9 vol-mult PASS(red+vol≥0.7×)/BLOCK(green bar)
  U1a/U1b  Bull-F8 VIX<17.20 PASS / VIX=17.25 rising BLOCK
  U1c      Bull-F8 VIX=17.50 falling → PASS (falling satisfies)
  U2a/U2b  Bull-F9 VIX hard cap PASS(<22.0) / BLOCK(≥22.0)
  P1-P5    Parity: constants in filters.py match params.json values

Live: N/A — pure unit-level / doctrine-consistency test.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from copy import replace
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Optional

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "backtest"))

from backtest.lib.filters import (
    BarContext,
    evaluate_bearish_setup,
    evaluate_bullish_setup,
    RIBBON_SPREAD_MIN_CENTS,
    VIX_BEAR_THRESHOLD,
    VIX_BULL_LOW_THRESHOLD,
    VIX_BULL_HARD_CAP,
    VIX_RISING_DEADBAND,
)
from backtest.lib.ribbon import RibbonState

_PARAMS_PATH = _REPO / "automation" / "state" / "params.json"


# ---------------------------------------------------------------------------
# Helpers — baseline passing contexts
# ---------------------------------------------------------------------------

def _make_bar(
    open_: float = 541.0,
    high: float = 541.5,
    low: float = 540.0,
    close: float = 540.3,
    volume: int = 750_000,
    ts: str = "2026-05-20 10:00:00",
) -> pd.Series:
    return pd.Series({
        "timestamp_et": pd.Timestamp(ts),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def _prior_bars_no_divergence(n: int = 5, base_price: float = 542.0) -> pd.DataFrame:
    """N monotonically declining bars — no volume_divergence_failed pattern."""
    rows = []
    for i in range(n):
        p = base_price - i * 0.2
        rows.append({
            "timestamp_et": pd.Timestamp(f"2026-05-20 0{9+i//12}:{30 + i*5:02d}:00"),
            "open": p + 0.2,
            "high": p + 0.4,
            "low": p - 0.2,
            "close": p,
            "volume": 600_000 - i * 10_000,
        })
    return pd.DataFrame(rows)


def _bear_ribbon(spread_cents: float = 50.0) -> RibbonState:
    """BEAR-stacked ribbon with configurable spread."""
    return RibbonState(fast=539.0, pivot=540.0, slow=541.0, spread_cents=spread_cents, stack="BEAR")


def _bull_ribbon(spread_cents: float = 50.0) -> RibbonState:
    """BULL-stacked ribbon with configurable spread."""
    return RibbonState(fast=541.0, pivot=540.0, slow=539.0, spread_cents=spread_cents, stack="BULL")


def _bear_ctx(
    time_str: str = "10:00",
    vix_now: float = 17.5,
    vix_prior: float = 17.3,   # rising by 0.2
    ribbon: Optional[RibbonState] = None,
    bar: Optional[pd.Series] = None,
    vol_baseline: float = 1_000_000.0,
    levels_active: Optional[list] = None,
) -> BarContext:
    """A fully-PASSING bearish context. Override specific fields per test."""
    ts_str = f"2026-05-20 {time_str}:00"
    ts = dt.datetime.fromisoformat(ts_str).replace(tzinfo=dt.timezone(dt.timedelta(hours=-4)))
    prior = _prior_bars_no_divergence()
    if bar is None:
        bar = _make_bar(ts=ts_str)
    if ribbon is None:
        ribbon = _bear_ribbon()
    if levels_active is None:
        # level at 540.8: bar.high(541.5) > 540.8 AND bar.close(540.3) < 540.8 → level_reject trigger
        levels_active = [540.8]
    return BarContext(
        bar_idx=4,   # >= 2 so volume_divergence check runs
        timestamp_et=ts,
        bar=bar,
        prior_bars=prior,
        ribbon_now=ribbon,
        ribbon_history=[ribbon],
        vix_now=vix_now,
        vix_prior=vix_prior,
        vol_baseline_20=vol_baseline,
        range_baseline_20=1.0,
        levels_active=levels_active,
        multi_day_levels=[],
        htf_15m_stack="BEAR",
        level_states={},
    )


def _bull_ctx(
    time_str: str = "10:00",
    vix_now: float = 17.1,
    vix_prior: float = 17.3,   # falling
    ribbon: Optional[RibbonState] = None,
    bar: Optional[pd.Series] = None,
    vol_baseline: float = 1_000_000.0,
    levels_active: Optional[list] = None,
) -> BarContext:
    """A fully-PASSING bullish context."""
    ts_str = f"2026-05-20 {time_str}:00"
    ts = dt.datetime.fromisoformat(ts_str).replace(tzinfo=dt.timezone(dt.timedelta(hours=-4)))
    prior = _prior_bars_no_divergence()
    if bar is None:
        # Green bar: close > open, vol > 0.7× baseline
        bar = _make_bar(open_=540.0, high=541.5, low=539.8, close=541.2,
                        volume=750_000, ts=ts_str)
    if ribbon is None:
        ribbon = _bull_ribbon()
    if levels_active is None:
        # level at 540.5: bar.low(539.8) < 540.5 AND bar.close(541.2) > 540.5 → level_reclaim
        levels_active = [540.5]
    return BarContext(
        bar_idx=4,
        timestamp_et=ts,
        bar=bar,
        prior_bars=prior,
        ribbon_now=ribbon,
        ribbon_history=[ribbon],
        vix_now=vix_now,
        vix_prior=vix_prior,
        vol_baseline_20=vol_baseline,
        range_baseline_20=1.0,
        levels_active=levels_active,
        multi_day_levels=[],
        htf_15m_stack="BULL",
        level_states={},
    )


def _bear(ctx: BarContext, **kwargs) -> bool:
    """Convenience: run evaluate_bearish_setup, return passed."""
    kwargs.setdefault("disable_filters", [7])   # skip F7 unless testing it
    return evaluate_bearish_setup(ctx, **kwargs).passed


def _bear_blockers(ctx: BarContext, **kwargs) -> list:
    kwargs.setdefault("disable_filters", [7])
    return evaluate_bearish_setup(ctx, **kwargs).blockers


def _bull(ctx: BarContext, **kwargs) -> bool:
    kwargs.setdefault("disable_filters", [7])
    return evaluate_bullish_setup(ctx, **kwargs).passed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    """Run filter boundary + parity tests for F1-F11."""
    results: list[tuple[str, bool, str]] = []

    # ---- BEARISH FILTER TESTS ----

    # B1a: F1 time gate PASS — bar at exactly 09:35 ET
    ctx = _bear_ctx(time_str="09:35")
    passed = _bear(ctx)
    results.append(("B1a_F1_time_gate_PASS_at_0935", passed,
                    f"09:35 bar -> bear.passed={passed}"))

    # B1b: F1 time gate BLOCK — bar at 09:34
    ctx = _bear_ctx(time_str="09:34")
    blockers = _bear_blockers(ctx)
    results.append(("B1b_F1_time_gate_BLOCK_at_0934", 1 in blockers,
                    f"09:34 bar → blockers={blockers}"))

    # B5a: F5 ribbon stack PASS — BEAR stacked
    ctx = _bear_ctx(ribbon=_bear_ribbon(50))
    passed = _bear(ctx)
    results.append(("B5a_F5_ribbon_BEAR_stack_PASS", passed,
                    f"BEAR ribbon → passed={passed}"))

    # B5b: F5 ribbon stack BLOCK — MIXED stack
    mixed_ribbon = RibbonState(fast=540.5, pivot=540.0, slow=540.5,
                                spread_cents=30, stack="MIXED")
    ctx = _bear_ctx(ribbon=mixed_ribbon)
    blockers = _bear_blockers(ctx, disable_filters=[7])
    results.append(("B5b_F5_ribbon_MIXED_stack_BLOCK", 5 in blockers,
                    f"MIXED ribbon → blockers={blockers}"))

    # B6a: F6 spread PASS — exactly 30c
    ctx = _bear_ctx(ribbon=_bear_ribbon(30))
    passed = _bear(ctx)
    results.append(("B6a_F6_spread_30c_PASS", passed,
                    f"30c spread → passed={passed}"))

    # B6b: F6 spread BLOCK — 29c (below 30c threshold)
    ctx = _bear_ctx(ribbon=_bear_ribbon(29))
    blockers = _bear_blockers(ctx)
    results.append(("B6b_F6_spread_29c_BLOCK", 6 in blockers,
                    f"29c spread → blockers={blockers}"))

    # B8a: F8 VIX PASS — VIX 17.35 rising
    ctx = _bear_ctx(vix_now=17.35, vix_prior=17.20)  # rising by 0.15
    passed = _bear(ctx, disable_filters=[7])
    results.append(("B8a_F8_vix_1735_rising_PASS", passed,
                    f"VIX=17.35 rising → passed={passed}"))

    # B8b: F8 VIX BLOCK — VIX 17.25 (below 17.30 threshold)
    ctx = _bear_ctx(vix_now=17.25, vix_prior=17.10)
    blockers = _bear_blockers(ctx, disable_filters=[7])
    results.append(("B8b_F8_vix_1725_BLOCK", 8 in blockers,
                    f"VIX=17.25 → blockers={blockers}"))

    # B8c: F8 VIX BLOCK when flat (above threshold but not rising)
    ctx = _bear_ctx(vix_now=17.35, vix_prior=17.33)  # diff=0.02 < 0.05 deadband → flat
    blockers = _bear_blockers(ctx, disable_filters=[7])
    results.append(("B8c_F8_vix_flat_BLOCK", 8 in blockers,
                    f"VIX=17.35 flat (diff<0.05) → blockers={blockers}"))

    # B8d: F8 vix_soft_mode — VIX fail is a score modifier, not a hard block
    ctx = _bear_ctx(vix_now=17.25, vix_prior=17.10)  # VIX fails
    result = evaluate_bearish_setup(ctx, disable_filters=[7], vix_soft_mode=True)
    vix_not_in_blockers = 8 not in result.blockers
    results.append(("B8d_F8_vix_soft_mode_no_hard_block", vix_not_in_blockers,
                    f"vix_soft_mode=True → blockers={result.blockers} passed={result.passed}"))

    # B9a: F9 seller pressure PASS — red bar, vol=750k ≥ 0.7×1000k=700k
    bar_red = _make_bar(open_=541.0, high=541.5, low=540.0, close=540.3, volume=750_000)
    ctx = _bear_ctx(bar=bar_red, vol_baseline=1_000_000)
    passed = _bear(ctx, disable_filters=[7], f9_vol_mult=0.7)
    results.append(("B9a_F9_red_bar_vol_07x_PASS", passed,
                    f"red bar vol=750k baseline=1000k (0.75x) → passed={passed}"))

    # B9b: F9 seller pressure BLOCK — green bar
    bar_green = _make_bar(open_=540.0, high=541.5, low=539.8, close=541.2, volume=750_000)
    ctx = _bear_ctx(bar=bar_green, vol_baseline=1_000_000)
    blockers = _bear_blockers(ctx, disable_filters=[7], f9_vol_mult=0.7)
    results.append(("B9b_F9_green_bar_BLOCK", 9 in blockers,
                    f"green bar → blockers={blockers}"))

    # ---- BULLISH FILTER TESTS ----

    # U1a: Bull F8 PASS — VIX < 17.20
    ctx = _bull_ctx(vix_now=17.10, vix_prior=17.15)   # not falling but < threshold
    passed = _bull(ctx)
    results.append(("U1a_bull_F8_vix_below_1720_PASS", passed,
                    f"VIX=17.10 → passed={passed}"))

    # U1b: Bull F8 BLOCK — VIX=17.25 rising (above threshold, not falling)
    ctx = _bull_ctx(vix_now=17.25, vix_prior=17.10)   # rising
    blockers_bull = evaluate_bullish_setup(ctx, disable_filters=[7]).blockers
    results.append(("U1b_bull_F8_vix_1725_rising_BLOCK", 8 in blockers_bull,
                    f"VIX=17.25 rising → blockers={blockers_bull}"))

    # U1c: Bull F8 PASS — VIX=17.50 but FALLING (falling satisfies the OR condition)
    ctx = _bull_ctx(vix_now=17.50, vix_prior=17.70)   # falling by 0.20
    passed = _bull(ctx)
    results.append(("U1c_bull_F8_vix_1750_falling_PASS", passed,
                    f"VIX=17.50 falling → passed={passed}"))

    # U2a: Bull F9 hard cap PASS — VIX=21.9 (< 22.0)
    ctx = _bull_ctx(vix_now=21.9, vix_prior=22.2)  # falling, also passes F8
    passed = _bull(ctx)
    results.append(("U2a_bull_F9_hard_cap_vix_219_PASS", passed,
                    f"VIX=21.9 → passed={passed}"))

    # U2b: Bull F9 hard cap BLOCK — VIX=22.0 (exactly at cap)
    ctx = _bull_ctx(vix_now=22.0, vix_prior=22.3)  # falling but at hard cap
    blockers_bull = evaluate_bullish_setup(ctx, disable_filters=[7]).blockers
    results.append(("U2b_bull_F9_hard_cap_vix_220_BLOCK", 9 in blockers_bull,
                    f"VIX=22.0 → blockers={blockers_bull}"))

    # ---- PARITY TESTS ----
    params = json.loads(_PARAMS_PATH.read_text(encoding="utf-8"))
    vix_thresholds = params.get("vix_entry_thresholds", {})

    p1_ok = RIBBON_SPREAD_MIN_CENTS == params.get("ribbon_min_spread_cents")
    results.append(("P1_parity_ribbon_spread_min_cents",
                    p1_ok,
                    f"filters={RIBBON_SPREAD_MIN_CENTS} params={params.get('ribbon_min_spread_cents')}"))

    p2_ok = VIX_BEAR_THRESHOLD == vix_thresholds.get("bear_min_exclusive_and_rising")
    results.append(("P2_parity_vix_bear_threshold",
                    p2_ok,
                    f"filters={VIX_BEAR_THRESHOLD} params={vix_thresholds.get('bear_min_exclusive_and_rising')}"))

    p3_ok = VIX_BULL_LOW_THRESHOLD == vix_thresholds.get("bull_max_exclusive_or_falling")
    results.append(("P3_parity_vix_bull_low_threshold",
                    p3_ok,
                    f"filters={VIX_BULL_LOW_THRESHOLD} params={vix_thresholds.get('bull_max_exclusive_or_falling')}"))

    p4_ok = VIX_BULL_HARD_CAP == vix_thresholds.get("bull_hard_cap")
    results.append(("P4_parity_vix_bull_hard_cap",
                    p4_ok,
                    f"filters={VIX_BULL_HARD_CAP} params={vix_thresholds.get('bull_hard_cap')}"))

    p5_ok = VIX_RISING_DEADBAND == params.get("vix_dir_deadband")
    results.append(("P5_parity_vix_dir_deadband",
                    p5_ok,
                    f"filters={VIX_RISING_DEADBAND} params={params.get('vix_dir_deadband')}"))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note[:120]} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live() -> dict:
    """No live data required — pure doctrine consistency + boundary test."""
    return {
        "mode": "live",
        "pass": True,
        "note": (
            "Filter gate regression is offline-only — tests boundary conditions and "
            "params.json parity using synthetic BarContext objects. B1-B9 cover "
            "bearish filters; U1-U2 cover bullish; P1-P5 verify threshold sync."
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
            print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:<52} {t['note']}")

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
