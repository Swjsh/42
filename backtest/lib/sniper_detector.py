"""SNIPER_LEVEL_BREAK setup detector.

The J-edge insight (extracted from 2026-05-11 and 2026-05-12 real-money
trades): when a named historical level (prior day RTH H/L, 5-day H/L) is
broken or reclaimed on a 5m bar with volume confirmation and body
commitment, enter ITM-2 0DTE in the direction of the break.

This setup BYPASSES v14's 10:00 ET gate and the ribbon >=30c spread filter.
The level break + volume IS the trigger.

Per CLAUDE.md OP 21 (Watch-First Promotion Path) the setup starts WATCH-ONLY.
Promotion to live orders requires 3+ historical wins via watcher_grader.py +
3+ live wins observed by J + positive expectancy over the 16-month backfill.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class SniperParams:
    """Knobs for the SNIPER detector. Immutable; one instance per combo."""

    vol_mult: float = 1.5
    body_min_cents: float = 0.10
    min_stars: int = 2
    proximity_dollars: float = 1.50
    # No time gate per J 2026-05-12: trade all market hours.
    # 09:30 = first RTH bar; 15:50 mandatory all-flat per Gamma rule.
    no_trade_before: dt.time = dt.time(9, 30)
    no_trade_after: dt.time = dt.time(15, 50)
    use_5d_levels: bool = True
    use_prior_day_levels: bool = True
    require_break_above_open: bool = True  # bar must close on the break side of its open


@dataclass(frozen=True)
class SniperLevel:
    """A named historical level the detector can react to."""

    price: float
    stars: int
    label: str
    tier: str  # "Active" or "Carry"


@dataclass(frozen=True)
class SniperSignal:
    """Output of detect_sniper_break() when the trigger fires."""

    direction: str  # "long" | "short"
    entry_price: float
    level: SniperLevel
    bar_timestamp_et: dt.datetime
    bar_volume: float
    vol_ratio: float
    body_dollars: float
    reason: str


def compute_levels(
    spy_bars: pd.DataFrame,
    as_of: dt.datetime,
    params: SniperParams,
) -> list[SniperLevel]:
    """Compute named historical levels available BEFORE `as_of` timestamp.

    Includes:
      - Prior trading day RTH high and low (star=2, tier=Active)
      - Last 5 trading day high and low (star=3, tier=Carry)

    Bars are assumed RTH-filtered already (09:30-16:00 ET) but we re-filter
    here to be safe.
    """
    as_of_date = as_of.date()
    prior = spy_bars[spy_bars["timestamp_et"].dt.date < as_of_date]
    rth_prior = prior[
        (prior["timestamp_et"].dt.time >= dt.time(9, 30))
        & (prior["timestamp_et"].dt.time < dt.time(16, 0))
    ]
    if rth_prior.empty:
        return []

    levels: list[SniperLevel] = []

    if params.use_prior_day_levels:
        last_date = rth_prior["timestamp_et"].dt.date.max()
        prior_rth = rth_prior[rth_prior["timestamp_et"].dt.date == last_date]
        if not prior_rth.empty:
            levels.append(
                SniperLevel(
                    price=float(prior_rth["high"].max()),
                    stars=2,
                    label="prior_day_high",
                    tier="Active",
                )
            )
            levels.append(
                SniperLevel(
                    price=float(prior_rth["low"].min()),
                    stars=2,
                    label="prior_day_low",
                    tier="Active",
                )
            )

    if params.use_5d_levels:
        unique_dates = sorted(rth_prior["timestamp_et"].dt.date.unique())[-5:]
        if unique_dates:
            five_d = rth_prior[rth_prior["timestamp_et"].dt.date.isin(unique_dates)]
            if not five_d.empty:
                levels.append(
                    SniperLevel(
                        price=float(five_d["high"].max()),
                        stars=3,
                        label="5d_high",
                        tier="Carry",
                    )
                )
                levels.append(
                    SniperLevel(
                        price=float(five_d["low"].min()),
                        stars=3,
                        label="5d_low",
                        tier="Carry",
                    )
                )

    return levels


def vol_baseline_20(spy_bars: pd.DataFrame, current_idx: int) -> float:
    """Compute 20-bar volume average ending at current_idx - 1."""
    if current_idx < 20:
        return 0.0
    return float(spy_bars["volume"].iloc[current_idx - 20 : current_idx].mean())


def detect_sniper_break(
    bar: pd.Series,
    bar_idx: int,
    spy_bars: pd.DataFrame,
    levels: list[SniperLevel],
    params: SniperParams,
) -> Optional[SniperSignal]:
    """Detect a SNIPER_LEVEL_BREAK on the current bar.

    Returns a SniperSignal when ALL conditions met:
      1. Bar time within [no_trade_before, no_trade_after]
      2. Bar volume >= vol_mult * 20-bar avg
      3. Prior bar closed on one side of a level; current bar closed on the
         opposite side AND >= body_min_cents past the level
      4. Level meets min_stars threshold
      5. If require_break_above_open: bar must close on the break-side of
         its open (committed body, not a wick)
    """
    bar_time = bar["timestamp_et"]
    if not hasattr(bar_time, "time"):
        return None
    bar_t = bar_time.time()
    if bar_t < params.no_trade_before or bar_t >= params.no_trade_after:
        return None

    bar_open = float(bar["open"])
    bar_close = float(bar["close"])
    bar_volume = float(bar["volume"])

    vol_base = vol_baseline_20(spy_bars, bar_idx)
    if vol_base <= 0 or bar_volume < params.vol_mult * vol_base:
        return None
    vol_ratio = bar_volume / vol_base

    if bar_idx == 0:
        return None
    prior_close = float(spy_bars["close"].iloc[bar_idx - 1])

    for level in levels:
        if level.stars < params.min_stars:
            continue

        # DOWN-break: prior bar above level, current bar closed below by body_min_cents
        if (
            prior_close > level.price + 0.001
            and bar_close < level.price - params.body_min_cents
        ):
            if params.require_break_above_open and bar_close >= bar_open:
                continue
            body_dollars = level.price - bar_close
            return SniperSignal(
                direction="short",
                entry_price=bar_close,
                level=level,
                bar_timestamp_et=bar_time,
                bar_volume=bar_volume,
                vol_ratio=vol_ratio,
                body_dollars=body_dollars,
                reason=(
                    f"{level.label}({level.price:.2f}) BROKEN_DOWN "
                    f"prior_c={prior_close:.2f} bar_c={bar_close:.2f} "
                    f"vol={vol_ratio:.1f}x body=${body_dollars:.2f}"
                ),
            )

        # UP-reclaim: prior bar below level, current bar closed above by body_min_cents
        if (
            prior_close < level.price - 0.001
            and bar_close > level.price + params.body_min_cents
        ):
            if params.require_break_above_open and bar_close <= bar_open:
                continue
            body_dollars = bar_close - level.price
            return SniperSignal(
                direction="long",
                entry_price=bar_close,
                level=level,
                bar_timestamp_et=bar_time,
                bar_volume=bar_volume,
                vol_ratio=vol_ratio,
                body_dollars=body_dollars,
                reason=(
                    f"{level.label}({level.price:.2f}) RECLAIMED_UP "
                    f"prior_c={prior_close:.2f} bar_c={bar_close:.2f} "
                    f"vol={vol_ratio:.1f}x body=${body_dollars:.2f}"
                ),
            )

    return None
