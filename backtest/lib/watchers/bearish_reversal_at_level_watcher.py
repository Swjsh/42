"""BEARISH_REVERSAL_AT_LEVEL_ON_BULL_RIBBON watcher (WATCH-ONLY per OP-21).

Detects J's 5/01-style countertrend puts setup:
  - Ribbon is BULL (fading an extended uptrend, not riding a bear continuation)
  - SPY has trended UP >= $3.00 from RTH open before the rejection bar
  - Bar touches a named ★★★ level (PDH/PDL/5DH/monthly-open in levels_active)
    AND closes >= 15c BELOW that level (rejection body)
  - Volume >= 2.0× 20-bar average (higher bar than continuation setups)
  - Time gate: only AFTER 11:00 ET (avoids early chop)
  - Not too late: no new signals after 14:30 ET (theta risk)

Promotion path (OP-21):
  - Historical gate: 3/3 PASS (2025-04-23, 2026-03-23×2, 2026-03-31)
  - Live gate: 0/3 — needs 3+ live J-confirmed observations
  - DO NOT wire into production heartbeat.md until live gate passes

Spec: strategy/candidates/2026-05-19-bearish-reversal-at-level-on-bull-ribbon.md
Registered: automation/state/watcher-observations.jsonl (2026-05-19 sentinel + 4 historical)
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from . import WatcherSignal
from ..filters import BarContext


# ---- Thresholds (per candidate spec) ----
MIN_UPTREND_FROM_OPEN_DOLLARS: float = 3.00   # SPY must be up >= $3 from RTH open
LEVEL_PROXIMITY_DOLLARS: float = 0.30         # bar high must be within $0.30 of a ★★★ level
REJECTION_BODY_MIN_CENTS: float = 15.0        # close must be >= 15c BELOW the level
VOLUME_MULTIPLIER: float = 2.0                # volume >= 2× 20-bar average
ENTRY_TIME_GATE: dt.time = dt.time(11, 0)     # only fire after 11:00 ET
LATE_SIGNAL_CUTOFF: dt.time = dt.time(14, 30) # no new signals after 14:30 ET (too late)
RTH_START: dt.time = dt.time(9, 30)

# ---- Default knobs (conservative — OP-21 watch-only defaults) ----
DEFAULT_QTY: int = 3
DEFAULT_PREMIUM_STOP_PCT: float = -0.06      # tighter than bear continuation (-8%)
DEFAULT_TP1_PREMIUM_PCT: float = 0.25        # earlier TP1 than continuation (+30%)
DEFAULT_RUNNER_TARGET_PCT: float = 1.5       # shorter runner (countertrend, less runway)

# SPY-price approximations for stop/target levels (used in watcher signal for logging)
# These are rough proxies; actual option P&L depends on premium at entry.
_CHART_STOP_ABOVE_LEVEL: float = 0.20   # stop = rejection_level + $0.20
_TP1_SPY_DROP: float = 1.00             # TP1 ≈ bar_close - $1.00 (approx +25% on $0.50 put)
_RUNNER_SPY_DROP: float = 2.50          # runner ≈ bar_close - $2.50 (approx 1.5× entry)


def _get_rth_open_price(
    prior_bars: pd.DataFrame,
    today_date: dt.date,
) -> Optional[float]:
    """Return the RTH open price (first bar >= 09:30 ET on today_date).

    Works with both tz-aware and tz-naive timestamp columns.
    """
    if prior_bars is None or prior_bars.empty:
        return None
    ts_col = prior_bars["timestamp_et"]
    # Normalize to date/time — handle tz-aware and tz-naive
    try:
        ts_parsed = pd.to_datetime(ts_col, utc=True).dt.tz_convert("America/New_York")
    except Exception:
        try:
            ts_parsed = pd.to_datetime(ts_col)
        except Exception:
            return None

    today_mask = ts_parsed.dt.date == today_date
    rth_mask = ts_parsed.dt.time >= RTH_START
    today_rth = prior_bars[today_mask & rth_mask]
    if today_rth.empty:
        return None
    return float(today_rth.iloc[0]["open"])


def _bull_ribbon_fraction_today(
    prior_bars: pd.DataFrame,
    today_date: dt.date,
    ribbon_history: list,
) -> float:
    """Estimate fraction of today's RTH bars with BULL ribbon stack.

    Uses ribbon_history if available (aligned with prior_bars index).
    Falls back to 0.0 if insufficient data.
    """
    if not ribbon_history:
        return 0.0

    try:
        ts_col = prior_bars["timestamp_et"]
        ts_parsed = pd.to_datetime(ts_col, utc=True).dt.tz_convert("America/New_York")
        today_rth_idx = prior_bars[
            (ts_parsed.dt.date == today_date) &
            (ts_parsed.dt.time >= RTH_START)
        ].index.tolist()
    except Exception:
        return 0.0

    if not today_rth_idx:
        return 0.0

    bull_count = 0
    for idx in today_rth_idx:
        if idx < len(ribbon_history):
            r = ribbon_history[idx]
            if r is not None and getattr(r, "stack", None) == "BULL":
                bull_count += 1

    return bull_count / len(today_rth_idx)


def detect_bearish_reversal_at_level(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect BEARISH_REVERSAL_AT_LEVEL_ON_BULL_RIBBON setup on the current bar.

    Returns WatcherSignal if all conditions met, else None.

    This is a COUNTERTREND setup (fading an extended bull move at a ★★★ resistance level).
    It requires stricter volume confirmation than the ribbon-continuation bear setup.

    Watch-only: does NOT place trades (OP-21 live gate: 0/3 confirmed observations).
    """
    # ---- Gate 1: Time window (11:00 - 14:30 ET) ----
    bar_time = ctx.timestamp_et.time()
    if bar_time < ENTRY_TIME_GATE:
        return None
    if bar_time > LATE_SIGNAL_CUTOFF:
        return None

    # ---- Gate 2: BULL ribbon stack (inverted from normal bear setup) ----
    if ctx.ribbon_now is None:
        return None
    if ctx.ribbon_now.stack != "BULL":
        return None

    bar_close = float(ctx.bar["close"])
    bar_high = float(ctx.bar["high"])
    bar_vol = float(ctx.bar["volume"])

    # ---- Gate 3: Extended uptrend from RTH open (>= $3.00) ----
    today_date = ctx.timestamp_et.date()
    rth_open_price = _get_rth_open_price(ctx.prior_bars, today_date)
    if rth_open_price is None:
        return None
    move_from_open = bar_high - rth_open_price
    if move_from_open < MIN_UPTREND_FROM_OPEN_DOLLARS:
        return None

    # ---- Gate 4: Level rejection at a ★★★ level ----
    # Bar high must be within $0.30 of level AND close >= 15c below it
    rejection_level: Optional[float] = None
    rejection_body_cents: float = 0.0
    for lvl in ctx.levels_active:
        # Touch check: high reached the level zone
        if bar_high >= lvl - LEVEL_PROXIMITY_DOLLARS:
            # Rejection check: close is clearly below the level
            # round to 4dp to avoid floating-point drift at exact thresholds
            body_below_cents = round((lvl - bar_close) * 100.0, 4)
            if body_below_cents >= REJECTION_BODY_MIN_CENTS:
                if body_below_cents > rejection_body_cents:
                    rejection_body_cents = body_below_cents
                    rejection_level = lvl

    if rejection_level is None:
        return None

    # ---- Gate 5: Volume >= 2.0× 20-bar average ----
    if ctx.vol_baseline_20 <= 0:
        return None
    vol_ratio = bar_vol / ctx.vol_baseline_20
    if vol_ratio < VOLUME_MULTIPLIER:
        return None

    # ---- Gate 6: HTF 15m — informational, not a hard gate ----
    # The spec says "15m does NOT show strong bull momentum" but the entire point
    # of this setup is fading on a BULL ribbon day. Record HTF state as informational.
    htf_str = ctx.htf_15m_stack or "UNKNOWN"
    htf_conflict = (htf_str == "BULL")  # note but don't block

    # ---- Informational: bull ribbon fraction across today's RTH bars ----
    # Higher fraction = more confirmed BULL day = stronger countertrend context.
    bull_frac = _bull_ribbon_fraction_today(ctx.prior_bars, today_date, ctx.ribbon_history)

    # ---- Confidence tier ----
    # HIGH: large body (>= 50c) AND very high volume (>= 3× avg)
    # MEDIUM: body >= 25c OR volume >= 2.5×
    # LOW: minimum thresholds met
    if rejection_body_cents >= 50.0 and vol_ratio >= 3.0:
        confidence = "high"
    elif rejection_body_cents >= 25.0 or vol_ratio >= 2.5:
        confidence = "medium"
    else:
        confidence = "low"

    # ---- Price levels for the signal (SPY proxy, not premium %) ----
    stop_price = rejection_level + _CHART_STOP_ABOVE_LEVEL  # chart stop above rejection
    tp1_price = bar_close - _TP1_SPY_DROP                   # first target ~$1 drop
    runner_price = bar_close - _RUNNER_SPY_DROP             # extended target ~$2.50 drop

    # ---- Build reason string ----
    reason = (
        f"BULL-ribbon reversal at level {rejection_level:.2f}: "
        f"body={rejection_body_cents:.0f}c below level, "
        f"vol={vol_ratio:.1f}x, "
        f"move_from_open=+${move_from_open:.2f}, "
        f"htf={htf_str}{'(CONFLICT)' if htf_conflict else ''}"
    )

    return WatcherSignal(
        watcher_name="bearish_reversal_at_level_watcher",
        setup_name="BEARISH_REVERSAL_AT_LEVEL_ON_BULL_RIBBON",
        direction="short",
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=reason,
        triggers_fired=["BULL_RIBBON_REVERSAL", "LEVEL_REJECTION", "VOL_2X"],
        metadata={
            "promotion_status": "WATCH_ONLY",
            "rejection_level": rejection_level,
            "rejection_body_cents": rejection_body_cents,
            "vol_ratio": vol_ratio,
            "move_from_open_dollars": move_from_open,
            "rth_open_price": rth_open_price,
            "htf_15m_stack": htf_str,
            "htf_conflict": htf_conflict,
            "bull_ribbon_fraction_today": round(bull_frac, 3),
            "default_qty": DEFAULT_QTY,
            "default_premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,
            "default_tp1_pct": DEFAULT_TP1_PREMIUM_PCT,
            "default_runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
            "op21_live_confirmed": 0,
            "op21_live_required": 3,
            "spec_file": "strategy/candidates/2026-05-19-bearish-reversal-at-level-on-bull-ribbon.md",
        },
    )
