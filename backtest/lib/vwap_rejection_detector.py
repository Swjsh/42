"""VWAP_REJECTION_PRIME setup detector.

J's edge insight (extracted from 2026-04-29, 2026-05-01, 2026-05-04 winners):
when SPY pulls back to session VWAP within ~$0.10, the prior 1-2 bars REJECT
VWAP (close on the opposite side after testing it), volume on the rejection
bar is elevated (>= 1.3x 20-bar avg) AND the EMA ribbon already agrees with
the rejection direction, enter ITM-2 0DTE in the rejection direction.

Per CLAUDE.md OP 21 (Watch-First Promotion Path) this setup starts WATCH-ONLY.
Promotion to live orders requires 3+ historical wins via watcher_grader.py +
3+ live wins observed by J + positive expectancy over the 16-month backfill.

Strategy spec: strategy/vwap_rejection_prime.md
Pattern mirrors lib/sniper_detector.py (frozen dataclass params, pure detect).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class VwapRejectionParams:
    """Knobs for the VWAP rejection detector. Immutable; one instance per combo."""

    # Trigger knobs (drive fire rate)
    vol_mult: float = 1.3
    proximity_dollars: float = 0.10
    lookback_bars: int = 2
    body_min_cents: float = 0.08

    # Ribbon agreement
    require_ribbon_agreement: bool = True
    ribbon_min_spread_cents: float = 30.0

    # Time gates per spec section 3: trade [09:35, 14:00) U [15:00, 15:35)
    no_trade_before: dt.time = dt.time(9, 35)
    no_trade_window_start: dt.time = dt.time(14, 0)
    no_trade_window_end: dt.time = dt.time(15, 0)
    no_trade_after: dt.time = dt.time(15, 35)


@dataclass(frozen=True)
class VwapSignal:
    """Output of detect_vwap_rejection() when the trigger fires."""

    direction: str  # "long" (calls) | "short" (puts)
    entry_price: float
    timestamp: dt.datetime
    vwap_at_bar: float
    distance: float  # |bar.close - vwap|
    rejection_bar_idx: int  # bar idx where rejection footprint printed
    vol_ratio: float
    body_dollars: float
    quality_tier: str  # "BASE" | "ELITE"
    reason: str


# ---------- Helpers ----------

def compute_session_vwap(spy_bars: pd.DataFrame, as_of_idx: int) -> float:
    """Cumulative VWAP from the first bar of the AS-OF-IDX's session to as_of_idx.

    Typical price = (high + low + close) / 3, weighted by volume. Session start
    is detected dynamically by looking back from as_of_idx until the bar date
    changes — this lets the detector accept a frame with pre-roll bars without
    poisoning the session VWAP with yesterday's prints (2026-05-13 fix).
    """
    if as_of_idx < 0 or as_of_idx >= len(spy_bars):
        return float("nan")
    as_of_date = spy_bars["timestamp_et"].iloc[as_of_idx].date()
    # Walk back to find first bar of this session
    session_start = as_of_idx
    while session_start > 0 and spy_bars["timestamp_et"].iloc[session_start - 1].date() == as_of_date:
        session_start -= 1
    slice_ = spy_bars.iloc[session_start : as_of_idx + 1]
    typical = (slice_["high"].astype(float)
               + slice_["low"].astype(float)
               + slice_["close"].astype(float)) / 3.0
    vol = slice_["volume"].astype(float)
    cum_vol = float(vol.sum())
    if cum_vol <= 0:
        return float(slice_["close"].iloc[-1])
    return float((typical * vol).sum() / cum_vol)


def _vol_baseline_20(spy_bars: pd.DataFrame, current_idx: int) -> float:
    """20-bar volume mean ending at current_idx - 1."""
    if current_idx < 20:
        return 0.0
    window = spy_bars["volume"].iloc[current_idx - 20: current_idx]
    return float(window.astype(float).mean())


def _within_time_gate(bar_t: dt.time, params: VwapRejectionParams) -> bool:
    """True if bar_t is in [no_trade_before, no_trade_window_start) U
    [no_trade_window_end, no_trade_after)."""
    if bar_t < params.no_trade_before:
        return False
    if bar_t >= params.no_trade_after:
        return False
    if params.no_trade_window_start <= bar_t < params.no_trade_window_end:
        return False
    return True


# ---------- Detector ----------

def detect_vwap_rejection(
    bar: pd.Series,
    bar_idx: int,
    spy_bars: pd.DataFrame,
    ribbon_state: Optional[dict],
    params: VwapRejectionParams,
) -> Optional[VwapSignal]:
    """Detect a VWAP_REJECTION_PRIME trigger on the current closed bar.

    All conditions from strategy/vwap_rejection_prime.md section 3 are checked:
      - Bar time in trading gate
      - VWAP proximity (|close - vwap| <= proximity_dollars)
      - Rejection footprint on prior 1..lookback_bars bars
      - Current bar close on the side of VWAP matching the rejection direction
      - Volume confirmation (current bar vol >= vol_mult * 20-bar avg)
      - Ribbon agreement (if require_ribbon_agreement)
      - Ribbon spread >= ribbon_min_spread_cents (no chop)
      - Body commitment >= body_min_cents

    ribbon_state is a dict with keys: fast, pivot, slow, spread_cents, stack
    where stack ∈ {"BULL", "BEAR", "MIXED", "WARMUP"}.
    """
    bar_time = bar["timestamp_et"]
    if not hasattr(bar_time, "time"):
        return None
    bar_t = bar_time.time()
    if not _within_time_gate(bar_t, params):
        return None

    if bar_idx < params.lookback_bars + 1:
        return None  # need at least lookback bars of prior history within the day

    bar_close = float(bar["close"])

    # ---- VWAP at the current bar ----
    vwap_now = compute_session_vwap(spy_bars, bar_idx)
    if vwap_now != vwap_now:  # NaN guard
        return None
    distance = abs(bar_close - vwap_now)
    if distance > params.proximity_dollars:
        return None

    # ---- Body commitment ----
    bar_open = float(bar["open"])
    body_dollars = abs(bar_close - bar_open)
    if body_dollars < params.body_min_cents:
        return None

    # ---- Volume confirmation ----
    bar_volume = float(bar["volume"])
    vol_base = _vol_baseline_20(spy_bars, bar_idx)
    if vol_base <= 0:
        return None
    if bar_volume < params.vol_mult * vol_base:
        return None
    vol_ratio = bar_volume / vol_base

    # ---- Rejection footprint over the lookback window ----
    # Only look back within today's session — pre-roll bars from yesterday
    # would test a session VWAP that's not yet defined for them.
    bear_rejection_idx: Optional[int] = None  # rejection from above -> PUTS
    bull_rejection_idx: Optional[int] = None  # rejection from below -> CALLS
    bar_date = bar_time.date()
    start = max(0, bar_idx - params.lookback_bars)
    for j in range(start, bar_idx):  # exclude current bar
        prior = spy_bars.iloc[j]
        prior_ts = prior["timestamp_et"]
        if not hasattr(prior_ts, "date") or prior_ts.date() != bar_date:
            continue  # don't reject against yesterday's bars
        prior_high = float(prior["high"])
        prior_low = float(prior["low"])
        prior_close = float(prior["close"])
        vwap_prior = compute_session_vwap(spy_bars, j)
        if vwap_prior != vwap_prior:  # NaN guard
            continue

        # Bear rejection (price tested VWAP from above, closed below)
        if prior_high > vwap_prior and prior_close < vwap_prior:
            bear_rejection_idx = j
        # Bull rejection (price tested VWAP from below, closed above)
        if prior_low < vwap_prior and prior_close > vwap_prior:
            bull_rejection_idx = j

    # Both fired in the window -> whipsaw, SKIP
    if bear_rejection_idx is not None and bull_rejection_idx is not None:
        # Tie-break: most recent rejection wins. Both indices comparable.
        if bear_rejection_idx > bull_rejection_idx:
            bull_rejection_idx = None
        elif bull_rejection_idx > bear_rejection_idx:
            bear_rejection_idx = None
        else:
            # Same bar tagged both ways -> ambiguous
            return None

    if bear_rejection_idx is None and bull_rejection_idx is None:
        return None

    # ---- Direction + current bar must match rejection side of VWAP ----
    if bear_rejection_idx is not None:
        direction = "short"
        if bar_close > vwap_now:
            return None  # current bar broke back above VWAP -> not a confirmed rejection
        rejection_idx = bear_rejection_idx
    else:
        direction = "long"
        if bar_close < vwap_now:
            return None
        rejection_idx = bull_rejection_idx  # type: ignore[assignment]

    # ---- Ribbon agreement ----
    if params.require_ribbon_agreement:
        if ribbon_state is None:
            return None
        stack = str(ribbon_state.get("stack", "WARMUP"))
        spread_cents = float(ribbon_state.get("spread_cents", 0.0))
        if spread_cents < params.ribbon_min_spread_cents:
            return None  # chop / compressed -> reject
        if direction == "short" and stack != "BEAR":
            return None
        if direction == "long" and stack != "BULL":
            return None

    # Quality tier: BASE by default; ELITE requires a named separate level
    # within $0.50 of current bar (NOT VWAP itself). Caller may upgrade by
    # inspecting the signal + their own levels list. We default to BASE here.
    quality_tier = "BASE"

    reason = (
        f"VWAP_REJ {direction} vwap={vwap_now:.2f} close={bar_close:.2f} "
        f"d=${distance:.2f} rejected_at_idx={rejection_idx} "
        f"vol={vol_ratio:.2f}x body=${body_dollars:.2f}"
    )

    return VwapSignal(
        direction=direction,
        entry_price=bar_close,
        timestamp=bar_time,
        vwap_at_bar=vwap_now,
        distance=distance,
        rejection_bar_idx=int(rejection_idx),
        vol_ratio=vol_ratio,
        body_dollars=body_dollars,
        quality_tier=quality_tier,
        reason=reason,
    )
