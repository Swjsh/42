"""vix_filter — VIX direction + Filter 8 entry-eligibility.

Two-fold purpose:
  1. Wrap `vix_direction(now, prior)` with a configurable deadband.
  2. Provide a 3-bar (15-minute) lookback variant per T81 (see markdown/research/T81-BULL-VIX-GATE.md)
     that catches "slow-drift" VIX trends single-bar deadband-locking misses.

Production source-of-truth (`automation/state/params.json`):
  vix_dir_deadband: 0.05
  vix_entry_thresholds:
    bull_max_exclusive_or_falling: 17.20
    bear_min_exclusive_and_rising: 17.30
    bull_hard_cap: 22.00

Filter 8 semantics:
  bullish:  VIX < 17.20  OR  vix_falling (3-bar)
  bearish:  VIX > 17.30  AND vix_rising  (3-bar)

This module is pure math. It does NOT fetch live data. Callers pass `vix_now`,
`vix_prior`, and (optionally) `vix_hist` (last N values, oldest first). When
`vix_hist` is provided AND `lookback_bars > 1`, the prior reading used for the
direction check is `vix_hist[-lookback_bars]` (i.e. N bars ago), not `vix_prior`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True, slots=True)
class VixDecision:
    direction: str       # "rising" | "falling" | "flat"
    deadband: float
    lookback_bars: int
    prior_used: float
    vix_now: float


def vix_direction(
    vix_now: float,
    vix_prior: float,
    deadband: float = 0.05,
) -> str:
    """Identical semantics to backtest.lib.filters.vix_direction.

    Returns 'rising' | 'falling' | 'flat'.
    """
    if vix_now > vix_prior + deadband:
        return "rising"
    if vix_now < vix_prior - deadband:
        return "falling"
    return "flat"


def vix_direction_lookback(
    vix_now: float,
    vix_hist: Sequence[float],
    lookback_bars: int = 3,
    deadband: float = 0.05,
) -> VixDecision:
    """Direction with N-bar lookback (T81 fix).

    `vix_hist` is the historical VIX series, oldest first. The PRIOR used for
    the deadband check is `vix_hist[-lookback_bars]`. If `vix_hist` is shorter
    than `lookback_bars`, falls back to the oldest available reading; if empty,
    returns 'flat' and prior_used=vix_now (defensive — no signal).
    """
    if lookback_bars < 1:
        raise ValueError(f"lookback_bars must be >= 1, got {lookback_bars}")
    if not vix_hist:
        return VixDecision(direction="flat", deadband=deadband,
                           lookback_bars=lookback_bars, prior_used=vix_now,
                           vix_now=vix_now)
    idx = -min(lookback_bars, len(vix_hist))
    prior = float(vix_hist[idx])
    direction = vix_direction(vix_now, prior, deadband=deadband)
    return VixDecision(direction=direction, deadband=deadband,
                       lookback_bars=lookback_bars, prior_used=prior,
                       vix_now=vix_now)


def passes_filter_8_bull(
    vix_now: float,
    vix_hist: Sequence[float],
    bull_threshold: float = 17.20,
    bull_hard_cap: float = 22.00,
    lookback_bars: int = 3,
    deadband: float = 0.05,
) -> bool:
    """Filter 8 (bullish): VIX < bull_threshold OR vix_falling (lookback).

    Hard cap: if vix_now > bull_hard_cap, ALWAYS reject regardless of direction.
    """
    if vix_now > bull_hard_cap:
        return False
    if vix_now < bull_threshold:
        return True
    decision = vix_direction_lookback(vix_now, vix_hist,
                                      lookback_bars=lookback_bars, deadband=deadband)
    return decision.direction == "falling"


def passes_filter_8_bear(
    vix_now: float,
    vix_hist: Sequence[float],
    bear_threshold: float = 17.30,
    lookback_bars: int = 3,
    deadband: float = 0.05,
) -> bool:
    """Filter 8 (bearish): VIX > bear_threshold AND vix_rising (lookback)."""
    if vix_now <= bear_threshold:
        return False
    decision = vix_direction_lookback(vix_now, vix_hist,
                                      lookback_bars=lookback_bars, deadband=deadband)
    return decision.direction == "rising"
