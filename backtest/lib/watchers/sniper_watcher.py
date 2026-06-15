"""SNIPER watcher — wraps detect_sniper_break() for live observation.

Per CLAUDE.md OP 21 + OP 23 (SNIPER_LEVEL_BREAK DRAFT 2026-05-12) this
watcher starts WATCH-ONLY. Detects named-level breaks/reclaims with
volume + body commitment confirmation; bypasses v14's 10:00 ET gate.

Default knobs come from Stage 5 winner combo at
`analysis/recommendations/sniper-v1.json` (proposed 2026-05-13 04:04 ET).
Promotion to live trading requires walk-forward PASS + real-fills resolved
+ 3 live wins + J ratification.

The wrapper is a thin adapter:
  1. Build SniperParams from the Stage 5 winner combo
  2. Compute named levels (prior day RTH H/L, 5-day H/L)
  3. Call detect_sniper_break() with the current bar + level set
  4. If signal fires, translate to a WatcherSignal with entry/stop/tp1/runner
     prices derived from the entry premium-target knobs

DOES NOT place orders. Watcher is observation-only — order placement is the
heartbeat's job (when promoted).
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from . import WatcherSignal
from ..sniper_detector import (
    SniperParams,
    compute_levels,
    detect_sniper_break,
)


# Default knobs from sniper-v1.json winner_combo (Stage 5 proposed 2026-05-13).
# Source of truth: analysis/recommendations/sniper-v1.json
# DO NOT mutate at runtime — params.json controls live trading once promoted.
DEFAULT_VOL_MULT = 1.1
DEFAULT_BODY_MIN_CENTS = 0.02
DEFAULT_MIN_STARS = 2
DEFAULT_PROXIMITY_DOLLARS = 1.5
DEFAULT_REQUIRE_BREAK_ABOVE_OPEN = True

# Exit knobs (Stage 5 winner). Used for would-be P&L computation.
DEFAULT_STRIKE_OFFSET = 2
DEFAULT_PREMIUM_STOP_PCT = -0.10
DEFAULT_TP1_PREMIUM_PCT = 0.40
DEFAULT_RUNNER_TARGET_PCT = 1.25
DEFAULT_TP1_QTY_FRACTION = 0.667
DEFAULT_QTY = 10
DEFAULT_PROFIT_LOCK_THRESHOLD_PCT = 0.0
DEFAULT_PROFIT_LOCK_STOP_OFFSET_PCT = 0.08


def _build_params() -> SniperParams:
    """Construct SniperParams from default knobs (Stage 5 winner)."""
    return SniperParams(
        vol_mult=DEFAULT_VOL_MULT,
        body_min_cents=DEFAULT_BODY_MIN_CENTS,
        min_stars=DEFAULT_MIN_STARS,
        proximity_dollars=DEFAULT_PROXIMITY_DOLLARS,
        require_break_above_open=DEFAULT_REQUIRE_BREAK_ABOVE_OPEN,
    )


def detect_sniper_setup(
    bar: pd.Series,
    bar_idx: int,
    spy_bars: pd.DataFrame,
    params: Optional[SniperParams] = None,
) -> Optional[WatcherSignal]:
    """Run SNIPER detector on the current bar; emit WatcherSignal on fire.

    Args:
        bar: pandas Series with OHLCV + timestamp_et.
        bar_idx: integer position of `bar` within `spy_bars`.
        spy_bars: full RTH SPY 5m DataFrame.
        params: SniperParams override; defaults to Stage 5 winner knobs.

    Returns:
        WatcherSignal if a SNIPER trigger fires on this bar, else None.

    The wrapper computes spot-based entry/stop/tp1/runner prices.
    Note: these are SPY *premium* targets translated from the
    `premium_stop_pct` / `tp1_premium_pct` / `runner_target_pct` knobs at
    typical 0DTE ITM-2 delta (~0.55). Real fills go through
    `simulator_real.py`; consumers should rely on `metadata` for the
    canonical percent-based exit targets.
    """
    if bar is None or spy_bars is None or spy_bars.empty:
        return None

    bar_time = bar.get("timestamp_et")
    if bar_time is None or not hasattr(bar_time, "time"):
        return None

    p = params if params is not None else _build_params()

    levels = compute_levels(spy_bars, as_of=bar_time, params=p)
    if not levels:
        return None

    signal = detect_sniper_break(
        bar=bar,
        bar_idx=bar_idx,
        spy_bars=spy_bars,
        levels=levels,
        params=p,
    )
    if signal is None:
        return None

    # Translate premium-percent exits into spot-price targets for the
    # WatcherSignal envelope. These are heuristic — final exit logic uses
    # the percent knobs against actual premium ticks.
    entry = float(signal.entry_price)
    # SPY spot stop/tp distances mirror premium stop assuming ~$1 SPY move
    # per 1% premium move on 0DTE ITM-2. For LONG: stop below entry; for
    # SHORT: stop above. Use percent multipliers as approximate ratios.
    if signal.direction == "long":
        stop_price = entry * (1.0 + DEFAULT_PREMIUM_STOP_PCT / 10.0)
        tp1_price = entry * (1.0 + DEFAULT_TP1_PREMIUM_PCT / 10.0)
        runner_price = entry * (1.0 + DEFAULT_RUNNER_TARGET_PCT / 10.0)
    else:
        stop_price = entry * (1.0 - DEFAULT_PREMIUM_STOP_PCT / 10.0)
        tp1_price = entry * (1.0 - DEFAULT_TP1_PREMIUM_PCT / 10.0)
        runner_price = entry * (1.0 - DEFAULT_RUNNER_TARGET_PCT / 10.0)

    level = signal.level
    quality_tier = "ELITE" if level.stars >= 3 else "BASE"

    confidence = (
        "high" if (level.stars >= 3 and signal.vol_ratio >= 1.5)
        else "medium" if level.stars >= 2
        else "low"
    )

    reason = (
        f"SNIPER {signal.direction} {level.label}@{level.price:.2f} "
        f"({level.tier}, {level.stars}*) entry={entry:.2f} "
        f"vol={signal.vol_ratio:.2f}x body=${signal.body_dollars:.2f}"
    )

    return WatcherSignal(
        watcher_name="sniper_watcher",
        setup_name="SNIPER_LEVEL_BREAK",
        direction=signal.direction,
        entry_price=entry,
        stop_price=float(stop_price),
        tp1_price=float(tp1_price),
        runner_price=float(runner_price),
        confidence=confidence,
        reason=reason,
        triggers_fired=["level_break"],
        metadata={
            "level_label": level.label,
            "level_price": level.price,
            "level_stars": level.stars,
            "level_tier": level.tier,
            "vol_ratio": signal.vol_ratio,
            "body_dollars": signal.body_dollars,
            "bar_volume": signal.bar_volume,
            "quality_tier": quality_tier,
            "strike_offset": DEFAULT_STRIKE_OFFSET,
            "default_qty": DEFAULT_QTY,
            "default_premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,
            "default_tp1_pct": DEFAULT_TP1_PREMIUM_PCT,
            "default_tp1_qty_fraction": DEFAULT_TP1_QTY_FRACTION,
            "default_runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
            "profit_lock_threshold_pct": DEFAULT_PROFIT_LOCK_THRESHOLD_PCT,
            "profit_lock_stop_offset_pct": DEFAULT_PROFIT_LOCK_STOP_OFFSET_PCT,
            "winner_combo_source": "analysis/recommendations/sniper-v1.json",
            "promotion_status": "WATCH_ONLY",
        },
    )
