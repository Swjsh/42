"""VWAP_REJECTION_PRIME watcher — wraps detect_vwap_rejection() for live obs.

Per CLAUDE.md OP 21 + markdown/0dte/vwap_rejection_prime.md this setup starts
WATCH-ONLY. Detects VWAP test + rejection with volume + ribbon alignment.

Default knobs come from markdown/0dte/vwap_rejection_prime.md section 6+9
(spec defaults; numbers NOT yet ratified — Stage 1 sweep pending).

The wrapper is a thin adapter:
  1. Build VwapRejectionParams from spec defaults
  2. Call detect_vwap_rejection() with current bar + ribbon state
  3. If signal fires, translate to WatcherSignal with entry/stop/tp1/runner
     prices derived from premium-percent exit knobs
  4. Quality tier downgraded to BASE by default; consumer may upgrade via
     level confluence (caller has today-bias.json level data)

DOES NOT place orders. Observation-only — order placement is heartbeat's
job (when promoted).
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from . import WatcherSignal
from ..vwap_rejection_detector import (
    VwapRejectionParams,
    detect_vwap_rejection,
)


# Default knobs from markdown/0dte/vwap_rejection_prime.md sections 3+6+9.
# DRAFT — these are SPEC defaults, NOT ratified Stage-5 winners. Stage 1
# sweep pending. Treat as conservative starting values.
DEFAULT_VOL_MULT = 1.3
DEFAULT_PROXIMITY_DOLLARS = 0.10
DEFAULT_LOOKBACK_BARS = 2
DEFAULT_BODY_MIN_CENTS = 0.08
DEFAULT_REQUIRE_RIBBON_AGREEMENT = True
DEFAULT_RIBBON_MIN_SPREAD_CENTS = 30.0
# 2026-05-13 J explicit instruction: "remove the time gates entirely from all
# strategies". Open gate moved from 09:35 to 09:30. Mid-day no-trade window
# preserved (that's chop, not arbitrary).
DEFAULT_NO_TRADE_BEFORE = dt.time(9, 30)
DEFAULT_NO_TRADE_WINDOW_START = dt.time(14, 0)
DEFAULT_NO_TRADE_WINDOW_END = dt.time(15, 0)
DEFAULT_NO_TRADE_AFTER = dt.time(15, 50)

# Exit knobs from spec section 6 (per OP 21 default watcher knobs)
DEFAULT_STRIKE_OFFSET = 2
DEFAULT_QTY = 3
DEFAULT_PREMIUM_STOP_PCT = -0.10
DEFAULT_TP1_PREMIUM_PCT = 0.30
DEFAULT_TP1_QTY_FRACTION = 0.667
DEFAULT_RUNNER_TARGET_PCT = 1.5
DEFAULT_PROFIT_LOCK_THRESHOLD_PCT = 0.10
DEFAULT_PROFIT_LOCK_STOP_OFFSET_PCT = 0.05


def _build_params() -> VwapRejectionParams:
    """Construct VwapRejectionParams from spec defaults."""
    return VwapRejectionParams(
        vol_mult=DEFAULT_VOL_MULT,
        proximity_dollars=DEFAULT_PROXIMITY_DOLLARS,
        lookback_bars=DEFAULT_LOOKBACK_BARS,
        body_min_cents=DEFAULT_BODY_MIN_CENTS,
        require_ribbon_agreement=DEFAULT_REQUIRE_RIBBON_AGREEMENT,
        ribbon_min_spread_cents=DEFAULT_RIBBON_MIN_SPREAD_CENTS,
        no_trade_before=DEFAULT_NO_TRADE_BEFORE,
        no_trade_window_start=DEFAULT_NO_TRADE_WINDOW_START,
        no_trade_window_end=DEFAULT_NO_TRADE_WINDOW_END,
        no_trade_after=DEFAULT_NO_TRADE_AFTER,
    )


def detect_vwap_setup(
    bar: pd.Series,
    bar_idx: int,
    spy_bars: pd.DataFrame,
    ribbon_state: Optional[dict],
    params: Optional[VwapRejectionParams] = None,
) -> Optional[WatcherSignal]:
    """Run VWAP_REJECTION_PRIME detector on the current bar.

    Args:
        bar: pandas Series with OHLCV + timestamp_et.
        bar_idx: integer position of `bar` within `spy_bars`.
        spy_bars: full SPY 5m DataFrame (RTH-filtered, with session VWAP context).
        ribbon_state: dict with keys fast/pivot/slow/spread_cents/stack
            ({"BULL", "BEAR", "MIXED", "WARMUP"}). Required when
            require_ribbon_agreement=True (default).
        params: override; defaults to spec values.

    Returns:
        WatcherSignal if a VWAP_REJECTION_PRIME trigger fires, else None.
    """
    if bar is None or spy_bars is None or spy_bars.empty:
        return None

    bar_time = bar.get("timestamp_et")
    if bar_time is None or not hasattr(bar_time, "time"):
        return None

    p = params if params is not None else _build_params()

    signal = detect_vwap_rejection(
        bar=bar,
        bar_idx=bar_idx,
        spy_bars=spy_bars,
        ribbon_state=ribbon_state,
        params=p,
    )
    if signal is None:
        return None

    # Translate premium-percent exits into spot-price targets. Heuristic
    # only — consumers use metadata percent knobs for canonical exit logic.
    entry = float(signal.entry_price)
    if signal.direction == "long":
        stop_price = entry * (1.0 + DEFAULT_PREMIUM_STOP_PCT / 10.0)
        tp1_price = entry * (1.0 + DEFAULT_TP1_PREMIUM_PCT / 10.0)
        runner_price = entry * (1.0 + DEFAULT_RUNNER_TARGET_PCT / 10.0)
    else:
        stop_price = entry * (1.0 - DEFAULT_PREMIUM_STOP_PCT / 10.0)
        tp1_price = entry * (1.0 - DEFAULT_TP1_PREMIUM_PCT / 10.0)
        runner_price = entry * (1.0 - DEFAULT_RUNNER_TARGET_PCT / 10.0)

    # Confidence: ELITE requires level confluence which we don't have here.
    # BASE = ribbon agrees + vol_ratio >= 1.5 (a "clean" rejection).
    if signal.vol_ratio >= 1.5 and signal.body_dollars >= 0.15:
        confidence = "high"
    elif signal.vol_ratio >= 1.3:
        confidence = "medium"
    else:
        confidence = "low"

    reason = (
        f"VWAP_REJ {signal.direction} vwap={signal.vwap_at_bar:.2f} "
        f"entry={entry:.2f} d=${signal.distance:.2f} "
        f"vol={signal.vol_ratio:.2f}x body=${signal.body_dollars:.2f}"
    )

    return WatcherSignal(
        watcher_name="vwap_watcher",
        setup_name="VWAP_REJECTION_PRIME",
        direction=signal.direction,
        entry_price=entry,
        stop_price=float(stop_price),
        tp1_price=float(tp1_price),
        runner_price=float(runner_price),
        confidence=confidence,
        reason=reason,
        triggers_fired=["vwap_rejection", "ribbon_agreement", "volume_confirm"],
        metadata={
            "vwap_at_bar": signal.vwap_at_bar,
            "vwap_distance": signal.distance,
            "rejection_bar_idx": signal.rejection_bar_idx,
            "vol_ratio": signal.vol_ratio,
            "body_dollars": signal.body_dollars,
            "quality_tier": signal.quality_tier,  # BASE; evaluator may upgrade to ELITE
            "strike_offset": DEFAULT_STRIKE_OFFSET,
            "default_qty": DEFAULT_QTY,
            "default_premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,
            "default_tp1_pct": DEFAULT_TP1_PREMIUM_PCT,
            "default_tp1_qty_fraction": DEFAULT_TP1_QTY_FRACTION,
            "default_runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
            "profit_lock_threshold_pct": DEFAULT_PROFIT_LOCK_THRESHOLD_PCT,
            "profit_lock_stop_offset_pct": DEFAULT_PROFIT_LOCK_STOP_OFFSET_PCT,
            "winner_combo_source": "markdown/0dte/vwap_rejection_prime.md#6+9 (DRAFT, not ratified)",
            "promotion_status": "WATCH_ONLY",
        },
    )
