"""PREMARKET_FAIL_FADE setup detector.

The J-edge insight (extracted from 2026-05-13 09:30 ET real-money trade):
when SPY gaps UP near but BELOW a major premarket-identified resistance
level and the FIRST RTH bar fails to test the level (high never reaches
within $0.05 of it) AND closes below its open with body commitment, enter
ITM-2 0DTE PUTS at the close.

This is the INVERSE of SNIPER_LEVEL_BREAK. SNIPER waits for a level break
WITH volume. PREMARKET_FAIL_FADE waits for a level FAIL — the level acts
as a magnet from above before any new buying can confirm.

The detector does NOT require volume confirmation: failures happen on
exhaustion/absorption, not high-volume rejection.

Per CLAUDE.md OP 21 (Watch-First Promotion Path) the setup starts
WATCH-ONLY. Promotion to live orders requires:
  - 3+ historical wins via watcher_grader.py
  - 3+ live wins observed by J
  - positive expectancy over the 16-month backfill
  - J's explicit ratification

See `markdown/0dte/premarket_fail_fade.md` for the full spec.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .sniper_detector import SniperLevel, SniperParams, compute_levels


@dataclass(frozen=True)
class PremarketFailFadeParams:
    """Knobs for the PREMARKET_FAIL_FADE detector. Immutable; one per combo."""

    proximity_to_level_dollars: float = 0.50
    body_min_cents: float = 0.20
    vol_mult: float = 1.0  # baseline — no volume gate
    min_stars: int = 2
    lookback_bars: int = 3  # first 3 RTH bars eligible (09:30, 09:35, 09:40)
    direction: str = "short_only"  # "short_only" | "both" (long mirror deferred)
    level_upper_tolerance: float = 0.05  # high may flick this many $ over level
    stop_buffer_dollars: float = 0.10  # stop sits this many $ above the level

    # Window — first 3 RTH bars. No premarket/postmarket fires.
    rth_open: dt.time = dt.time(9, 30)
    last_eligible_bar: dt.time = dt.time(9, 40)  # 09:40 is the 3rd bar (09:30, 09:35, 09:40)


@dataclass(frozen=True)
class PremarketFailFadeSignal:
    """Output of detect_premarket_fail_fade() when the trigger fires."""

    direction: str  # "short" (initially short_only)
    entry_price: float  # bar.close of the failing bar
    level: SniperLevel  # the resistance level that held
    bar_timestamp_et: dt.datetime
    bar_volume: float
    vol_ratio: float  # bar_vol / 20-bar baseline (informational)
    body_dollars: float  # bar.open - bar.close (positive = red body)
    distance_to_level: float  # level.price - bar.high (positive = below level)
    bar_high: float
    bar_open: float
    reason: str


def _resistance_levels_from_bias(today_bias: Optional[dict]) -> list[SniperLevel]:
    """Extract resistance levels from `today-bias.json#key_levels.resistance`.

    The bias file lists resistance as a plain list of floats (no labels/stars).
    We tag them as ★★ "premarket_resistance" so they pass min_stars=2 by default.
    The bias file's resistance entries reflect chart-confirmed premarket levels.

    If `today_bias` is None or malformed, returns [].
    """
    if not isinstance(today_bias, dict):
        return []
    key_levels = today_bias.get("key_levels")
    if not isinstance(key_levels, dict):
        return []
    raw = key_levels.get("resistance")
    if not isinstance(raw, list):
        return []
    out: list[SniperLevel] = []
    for i, val in enumerate(raw):
        try:
            px = float(val)
        except (TypeError, ValueError):
            continue
        if px <= 0:
            continue
        out.append(
            SniperLevel(
                price=px,
                stars=2,
                label=f"premarket_resistance_{i+1}",
                tier="Active",
            )
        )
    return out


def detect_premarket_fail_fade(
    bar: pd.Series,
    bar_idx: int,
    spy_bars: pd.DataFrame,
    levels: list[SniperLevel],
    params: PremarketFailFadeParams,
    today_bias: Optional[dict] = None,
) -> Optional[PremarketFailFadeSignal]:
    """Detect a PREMARKET_FAIL_FADE on the current bar.

    Returns a PremarketFailFadeSignal when ALL conditions met:
      1. Bar time within [params.rth_open, params.last_eligible_bar] inclusive
         (first 3 RTH bars: 09:30, 09:35, 09:40).
      2. Bar.open is within `proximity_to_level_dollars` of ANY resistance
         level AND bar.open <= level + level_upper_tolerance (gap-up but
         still below).
      3. Bar.high < level + level_upper_tolerance (failed to test cleanly).
      4. Bar.close < bar.open - body_min_cents (committed red body).
      5. Level meets min_stars threshold.

    `levels` should include resistance levels from BOTH:
      - today_bias.json#key_levels.resistance (premarket-identified)
      - sniper_detector.compute_levels() (prior-day RTH high, 5-day high)

    Caller is responsible for assembling that union (use the helper module
    `_resistance_levels_from_bias` for the bias side).

    The `today_bias` arg is currently unused in core logic (the detector
    expects levels pre-assembled) but reserved for future per-day overrides.
    """
    if bar is None or spy_bars is None or spy_bars.empty:
        return None

    bar_time = bar.get("timestamp_et")
    if bar_time is None or not hasattr(bar_time, "time"):
        return None

    bar_t = bar_time.time()
    if bar_t < params.rth_open or bar_t > params.last_eligible_bar:
        return None

    if params.direction not in ("short_only", "both"):
        return None

    try:
        bar_open = float(bar["open"])
        bar_high = float(bar["high"])
        bar_close = float(bar["close"])
        bar_volume = float(bar["volume"])
    except (KeyError, TypeError, ValueError):
        return None

    # Body commitment: closed below open by body_min_cents
    body_dollars = bar_open - bar_close
    if body_dollars < params.body_min_cents:
        return None

    # 20-bar vol baseline (informational; not gated by default)
    vol_base = 0.0
    if bar_idx >= 20:
        try:
            vol_base = float(spy_bars["volume"].iloc[bar_idx - 20 : bar_idx].mean())
        except Exception:
            vol_base = 0.0
    vol_ratio = (bar_volume / vol_base) if vol_base > 0 else 0.0

    if vol_base > 0 and bar_volume < params.vol_mult * vol_base:
        # vol_mult default 1.0 — this only triggers if a caller raises the gate.
        return None

    # Scan resistance levels for a fail-fade fire.
    # Iterate in proximity order so the CLOSEST level wins ties.
    candidate_levels: list[tuple[float, SniperLevel]] = []
    for level in levels:
        if level.stars < params.min_stars:
            continue
        # Must be a RESISTANCE configuration: open <= level + tolerance.
        if bar_open > level.price + params.level_upper_tolerance:
            continue
        # Proximity gate
        dist_open = level.price - bar_open
        if dist_open > params.proximity_to_level_dollars:
            continue
        # Failed-to-test gate: bar high never reached level (within tolerance).
        if bar_high > level.price + params.level_upper_tolerance:
            continue
        candidate_levels.append((dist_open, level))

    if not candidate_levels:
        return None

    candidate_levels.sort(key=lambda t: t[0])
    _, best_level = candidate_levels[0]

    distance_to_level = best_level.price - bar_high

    return PremarketFailFadeSignal(
        direction="short",
        entry_price=bar_close,
        level=best_level,
        bar_timestamp_et=bar_time,
        bar_volume=bar_volume,
        vol_ratio=vol_ratio,
        body_dollars=body_dollars,
        distance_to_level=distance_to_level,
        bar_high=bar_high,
        bar_open=bar_open,
        reason=(
            f"{best_level.label}({best_level.price:.2f}) FAILED_TO_TEST "
            f"open={bar_open:.2f} high={bar_high:.2f} close={bar_close:.2f} "
            f"d_lvl=${distance_to_level:.2f} body=${body_dollars:.2f} "
            f"vol={vol_ratio:.2f}x"
        ),
    )


def assemble_levels(
    spy_bars: pd.DataFrame,
    as_of: dt.datetime,
    today_bias: Optional[dict],
    sniper_params: Optional[SniperParams] = None,
) -> list[SniperLevel]:
    """Build the union of resistance levels for PFF.

    Combines:
      - Premarket resistance levels from today-bias.json (★★ Active)
      - Prior-day RTH high + 5-day RTH high from historical bars (★★/★★★)

    De-dupes by price (within $0.05).
    """
    bias_levels = _resistance_levels_from_bias(today_bias)
    sp = sniper_params if sniper_params is not None else SniperParams()
    hist_levels = compute_levels(spy_bars, as_of=as_of, params=sp)
    # Only keep historical HIGH levels (resistance side); drop LOW levels.
    hist_resistance = [
        lvl for lvl in hist_levels
        if lvl.label in ("prior_day_high", "5d_high")
    ]

    combined: list[SniperLevel] = []
    seen_prices: list[float] = []
    for lvl in list(bias_levels) + list(hist_resistance):
        # Dedup within $0.05
        if any(abs(lvl.price - p) <= 0.05 for p in seen_prices):
            continue
        seen_prices.append(lvl.price)
        combined.append(lvl)
    return combined
