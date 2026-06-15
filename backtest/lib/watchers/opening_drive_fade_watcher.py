"""OPENING_DRIVE_FADE watcher — wraps detect_opening_drive_fade().

Per CLAUDE.md OP 21 + strategy/opening_drive_fade.md this setup starts
WATCH-ONLY. Detects HOD/LOD thrust then stall on declining volume,
fades the drive direction.

Default knobs from strategy/opening_drive_fade.md sections 5+6+8
(spec defaults; Stage 1 sweep pending — NOT ratified).

The wrapper is a thin adapter:
  1. Build OpeningDriveFadeParams from spec defaults
  2. Call detect_opening_drive_fade() with current bar + history
  3. If signal fires, translate to WatcherSignal

The detector already manages a per-day state machine (HOD/LOD ratchet +
stall counter + one-and-done lock-out) keyed by ISO date. The wrapper
exposes the detector's `reset_*_state` symbols so batch backtests can
clear between days.

DOES NOT place orders. Observation-only — order placement is heartbeat's
job (when promoted).
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from . import WatcherSignal
from ..opening_drive_fade_detector import (
    OpeningDriveFadeParams,
    detect_opening_drive_fade,
    reset_state as _detector_reset_state,
    reset_all_state as _detector_reset_all_state,
)


# Default knobs from strategy/opening_drive_fade.md sections 5+6+8 (DRAFT).
DEFAULT_THRUST_BAR_MIN_DOLLARS = 0.40
DEFAULT_STALL_BARS_REQUIRED = 2
DEFAULT_STALL_PROXIMITY_DOLLARS = 0.20
DEFAULT_VOL_DECLINE_RATIO = 0.70
# 2026-05-13 J explicit instruction: "remove the time gates entirely". Open
# window starts 09:30. Still need 2 bars for HOD/LOD ratchet so first fire
# realistically 09:40+, but no hard time-gate block on bar 09:30 itself.
DEFAULT_TIME_WINDOW_START = dt.time(9, 30)
DEFAULT_TIME_WINDOW_END = dt.time(11, 0)
DEFAULT_ENTRY_WINDOW_END = dt.time(11, 30)

# Exit knobs (per OP 21 default watcher knobs + spec section 5)
DEFAULT_STRIKE_OFFSET = 2
DEFAULT_QTY = 3
DEFAULT_PREMIUM_STOP_PCT = -0.10
DEFAULT_TP1_PREMIUM_PCT = 0.30
DEFAULT_TP1_QTY_FRACTION = 0.667
DEFAULT_RUNNER_TARGET_PCT = 1.5
DEFAULT_PROFIT_LOCK_THRESHOLD_PCT = 0.10
DEFAULT_PROFIT_LOCK_STOP_OFFSET_PCT = 0.05


def _build_params() -> OpeningDriveFadeParams:
    """Construct OpeningDriveFadeParams from spec defaults."""
    return OpeningDriveFadeParams(
        thrust_bar_min_dollars=DEFAULT_THRUST_BAR_MIN_DOLLARS,
        stall_bars_required=DEFAULT_STALL_BARS_REQUIRED,
        stall_proximity_dollars=DEFAULT_STALL_PROXIMITY_DOLLARS,
        vol_decline_ratio=DEFAULT_VOL_DECLINE_RATIO,
        time_window_start=DEFAULT_TIME_WINDOW_START,
        time_window_end=DEFAULT_TIME_WINDOW_END,
        entry_window_end=DEFAULT_ENTRY_WINDOW_END,
    )


def reset_state(date_str: str) -> None:
    """Clear per-day detector state. Forwards to opening_drive_fade_detector."""
    _detector_reset_state(date_str)


def reset_all_state() -> None:
    """Clear all per-day detector state. Forwards to opening_drive_fade_detector."""
    _detector_reset_all_state()


def detect_opening_drive_fade_setup(
    bar: pd.Series,
    bar_idx: int,
    spy_bars: pd.DataFrame,
    params: Optional[OpeningDriveFadeParams] = None,
) -> Optional[WatcherSignal]:
    """Run OPENING_DRIVE_FADE detector on the current bar.

    The detector maintains a module-level per-day state dict (mirror of
    orb_watcher pattern) — call this function on EVERY RTH bar in order to
    update the HOD/LOD ratchet + stall counter even on bars that don't fire.

    Args:
        bar: pandas Series with OHLCV + timestamp_et.
        bar_idx: integer position of `bar` within `spy_bars`.
        spy_bars: full SPY 5m DataFrame (for the detector's history lookups).
        params: override; defaults to spec values.

    Returns:
        WatcherSignal if an ODF trigger fires (one per day max), else None.
    """
    if bar is None or spy_bars is None or spy_bars.empty:
        return None

    bar_time = bar.get("timestamp_et")
    if bar_time is None or not hasattr(bar_time, "time"):
        return None

    p = params if params is not None else _build_params()

    signal = detect_opening_drive_fade(
        bar=bar,
        bar_idx=bar_idx,
        spy_bars=spy_bars,
        params=p,
    )
    if signal is None:
        return None

    # Translate premium-percent exits into spot-price targets (heuristic).
    entry = float(signal.entry_price)
    if signal.direction == "long":
        stop_price = entry * (1.0 + DEFAULT_PREMIUM_STOP_PCT / 10.0)
        tp1_price = entry * (1.0 + DEFAULT_TP1_PREMIUM_PCT / 10.0)
        runner_price = entry * (1.0 + DEFAULT_RUNNER_TARGET_PCT / 10.0)
    else:
        stop_price = entry * (1.0 - DEFAULT_PREMIUM_STOP_PCT / 10.0)
        tp1_price = entry * (1.0 - DEFAULT_TP1_PREMIUM_PCT / 10.0)
        runner_price = entry * (1.0 - DEFAULT_RUNNER_TARGET_PCT / 10.0)

    # Confidence: ELITE quality_tier from detector => high; BASE with strong
    # vol_decline => medium; else low.
    if signal.quality_tier == "ELITE":
        confidence = "high"
    elif signal.vol_ratio_thrust <= 0.60:
        confidence = "medium"
    else:
        confidence = "low"

    setup_suffix = "HOD" if signal.direction == "short" else "LOD"
    setup_name = f"OPENING_DRIVE_FADE_{setup_suffix}"

    reason = (
        f"ODF {signal.direction} extreme={signal.extreme_price:.2f} "
        f"stall_bars={signal.stall_bar_count} "
        f"vol_ratio={signal.vol_ratio_thrust:.2f}x "
        f"thrust@{signal.thrust_bar_time.strftime('%H:%M') if signal.thrust_bar_time else '?'}"
    )

    return WatcherSignal(
        watcher_name="opening_drive_fade_watcher",
        setup_name=setup_name,
        direction=signal.direction,
        entry_price=entry,
        stop_price=float(stop_price),
        tp1_price=float(tp1_price),
        runner_price=float(runner_price),
        confidence=confidence,
        reason=reason,
        triggers_fired=["opening_drive_thrust", "stall_volume_decline", "extreme_fade"],
        metadata={
            "extreme_price": signal.extreme_price,
            "thrust_bar_time": str(signal.thrust_bar_time),
            "stall_bar_count": signal.stall_bar_count,
            "vol_ratio_thrust": signal.vol_ratio_thrust,
            "quality_tier": signal.quality_tier,
            "strike_offset": DEFAULT_STRIKE_OFFSET,
            "default_qty": DEFAULT_QTY,
            "default_premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,
            "default_tp1_pct": DEFAULT_TP1_PREMIUM_PCT,
            "default_tp1_qty_fraction": DEFAULT_TP1_QTY_FRACTION,
            "default_runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
            "profit_lock_threshold_pct": DEFAULT_PROFIT_LOCK_THRESHOLD_PCT,
            "profit_lock_stop_offset_pct": DEFAULT_PROFIT_LOCK_STOP_OFFSET_PCT,
            "winner_combo_source": "strategy/opening_drive_fade.md#5+6 (DRAFT, not ratified)",
            "promotion_status": "WATCH_ONLY",
        },
    )
