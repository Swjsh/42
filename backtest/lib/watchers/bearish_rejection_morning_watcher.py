"""BEARISH_REJECTION_MORNING watcher — J's 4/29 + 5/04 MORNING ribbon-flip-at-level pattern.

Detects the setup responsible for J's two best anchor-day entries:
  - 2026-04-29 10:25 ET: SPY 710P ×6 → +$342  ("711.4 rejection + ribbon flip")
  - 2026-05-04 10:27 ET: SPY 721P ×10 → +$730 ("premarket level + trendline + ribbon flip")

Both entries were:
  - MORNING (10:20–10:30 ET), at_close, bars_after_trigger=0
  - BEARISH_REJECTION_RIDE_THE_RIBBON (not countertrend — entering WITH the flip)
  - At a named ★★★ resistance level
  - Ribbon FLIPPED to BEAR on or just before the entry bar

Why this watcher is distinct from BEARISH_REVERSAL_AT_LEVEL:
  - BEARISH_REVERSAL: 11:00-14:30 ET, ribbon=BULL (countertrend fade)
  - THIS WATCHER:   09:35-10:55 ET, ribbon=BEAR (enter WITH the flip, trend-following)

Hypothesis: the morning open creates a test of the prior overnight/pre-market high.
When SPY rallies into that level and the EMA ribbon simultaneously flips to BEAR,
the rejection has both technical structure (level) AND momentum signal (ribbon).
This is J's highest-conviction BEAR entry (best %-return in sample on 5/04).

Detection conditions:
  1. Time 09:35–10:55 ET (morning session, before BEARISH_REVERSAL window)
  2. EMA ribbon is BEAR at bar close (ribbon has flipped — not still BULL)
  3. Bar high is within $0.50 of a named ★★★ resistance level (proximity touch)
  4. Bar closes ≥ $0.15 below that level (rejection body confirmed)
  5. Volume ≥ 1.5× 20-bar average (lower threshold than BEARISH_REVERSAL — early session)
  6. Optional HTF 15m context logged (not a hard gate — morning HTF is often BULL before flip)

Promotion path (OP-21):
  - Live gate: 0/3 — needs 3+ live J-confirmed observations with positive P&L
  - DO NOT wire into production heartbeat.md until live gate passes + J ratification (Rule 9)
  - Pre-ratification: watch-only accumulation, P&L graded via replay scorer

Spec: strategy/candidates/2026-05-24-bearish-rejection-morning-watcher.md
Author: Gamma (interactive session 2026-05-24)
Registered: automation/state/watcher-observations.jsonl (live shadow from 2026-05-24)
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from . import WatcherSignal
from ..filters import BarContext


# ---- Thresholds ----
ENTRY_TIME_START: dt.time = dt.time(9, 35)    # standard RTH gate
ENTRY_TIME_END: dt.time   = dt.time(10, 55)   # morning window only; BEARISH_REVERSAL picks up 11:00+
LEVEL_PROXIMITY_DOLLARS: float = 0.50         # bar high must be within $0.50 of a ★★★ level
REJECTION_BODY_MIN_CENTS: float = 15.0        # close must be ≥ 15c BELOW the level
VOLUME_MULTIPLIER: float = 1.5                # 1.5× (lower than BEARISH_REVERSAL 2.0× — early session)

# ---- Stop / target proxies (SPY price, not premium %) ----
_CHART_STOP_ABOVE_LEVEL: float = 0.25         # stop = rejection_level + $0.25 above level
_TP1_SPY_DROP: float = 1.00                   # TP1 ≈ bar_close − $1.00
_RUNNER_SPY_DROP: float = 2.50                # runner target ≈ bar_close − $2.50 (v15 2.5× knob)

# ---- Default exit knobs ----
DEFAULT_PREMIUM_STOP_PCT: float = -0.08       # bear continuation stop (v15 chart-stop preferred)
DEFAULT_TP1_PREMIUM_PCT: float  =  0.30       # bear continuation TP1
DEFAULT_RUNNER_TARGET_PCT: float = 2.50       # runner 2.5× (v15)
DEFAULT_QTY: int = 3


def detect_bearish_rejection_morning(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect BEARISH_REJECTION_MORNING setup on the current bar.

    Returns WatcherSignal if all conditions met, else None.

    This is a TREND-FOLLOWING setup entering WITH the ribbon flip at resistance,
    NOT a countertrend fade. The distinction matters for exit management:
    once the ribbon is BEAR, ride it — don't exit at first bounce.

    Watch-only: does NOT place trades (OP-21 live gate: 0/3 confirmed observations).
    """
    # ---- Gate 1: Time window (09:35 – 10:55 ET) ----
    bar_time = ctx.timestamp_et.time()
    if bar_time < ENTRY_TIME_START:
        return None
    if bar_time > ENTRY_TIME_END:
        return None

    # ---- Gate 2: Ribbon is BEAR at bar close (ribbon has flipped) ----
    # Unlike BEARISH_REVERSAL which needs ribbon=BULL (countertrend), this setup
    # requires the ribbon to have already flipped to BEAR — we enter WITH momentum.
    if ctx.ribbon_now is None:
        return None
    if ctx.ribbon_now.stack != "BEAR":
        return None

    bar_close = float(ctx.bar["close"])
    bar_high  = float(ctx.bar["high"])
    bar_low   = float(ctx.bar["low"])
    bar_vol   = float(ctx.bar["volume"])
    bar_open  = float(ctx.bar["open"])

    # ---- Gate 3: Level rejection at a ★★★ resistance level ----
    # Bar high must be within $0.50 of a level AND close >= 15c below it.
    # Wider proximity than BEARISH_REVERSAL ($0.30) — morning wicks are more energetic.
    rejection_level: Optional[float] = None
    rejection_body_cents: float = 0.0
    for lvl in ctx.levels_active:
        # Touch check: high reached the level zone
        if bar_high >= lvl - LEVEL_PROXIMITY_DOLLARS:
            # Rejection check: close is clearly below the level
            body_below_cents = round((lvl - bar_close) * 100.0, 4)
            if body_below_cents >= REJECTION_BODY_MIN_CENTS:
                # Take the level with the largest rejection body (best confirmed rejection)
                if body_below_cents > rejection_body_cents:
                    rejection_body_cents = body_below_cents
                    rejection_level = lvl

    if rejection_level is None:
        return None

    # ---- Gate 4: Volume ≥ 1.5× 20-bar average ----
    if ctx.vol_baseline_20 <= 0:
        return None
    vol_ratio = bar_vol / ctx.vol_baseline_20
    if vol_ratio < VOLUME_MULTIPLIER:
        return None

    # ---- Gate 5: Bar is a BEAR candle (close < open) — confirms directional conviction ----
    # Soft gate: if close >= open (doji / bull bar) with ribbon BEAR + level rejection,
    # still allow it but lower confidence.
    is_bear_candle = bar_close < bar_open

    # ---- Informational: HTF 15m stack ----
    htf_str = ctx.htf_15m_stack or "UNKNOWN"
    htf_alignment = (htf_str == "BEAR")   # aligned when 15m is also BEAR

    # ---- Wick characteristics ----
    # Upper wick: how much the bar wicked above the close into the level
    upper_wick = bar_high - max(bar_close, bar_open)
    wick_to_body_ratio = upper_wick / max(abs(bar_close - bar_open), 0.01)

    # ---- Confidence tier ----
    # HIGH: large body (>= 30c), high volume (>= 2.5×), AND bear candle
    # MEDIUM: body >= 20c OR vol >= 2.0× (but not all HIGH criteria)
    # LOW: minimum thresholds met
    if rejection_body_cents >= 30.0 and vol_ratio >= 2.5 and is_bear_candle:
        confidence = "high"
    elif rejection_body_cents >= 20.0 or vol_ratio >= 2.0:
        confidence = "medium"
    else:
        confidence = "low"

    # Downgrade to LOW if it's a doji / bull candle (weaker conviction)
    if not is_bear_candle and confidence == "medium":
        confidence = "low"

    # ---- Price levels for the signal ----
    stop_price   = rejection_level + _CHART_STOP_ABOVE_LEVEL   # chart stop above the level
    tp1_price    = bar_close - _TP1_SPY_DROP                   # TP1 ~$1 drop
    runner_price = bar_close - _RUNNER_SPY_DROP                # runner target ~$2.50 drop

    # ---- Reason string ----
    reason = (
        f"MORNING ribbon-flip rejection at {rejection_level:.2f}: "
        f"body={rejection_body_cents:.0f}c below level, "
        f"vol={vol_ratio:.1f}x, "
        f"wick={upper_wick:.2f} ({wick_to_body_ratio:.1f}× body), "
        f"htf={htf_str}{'(ALIGNED)' if htf_alignment else '(UNALIGNED)'}"
    )

    return WatcherSignal(
        watcher_name="bearish_rejection_morning_watcher",
        setup_name="BEARISH_REJECTION_MORNING",
        direction="short",
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=reason,
        triggers_fired=[
            "BEAR_RIBBON_FLIP",
            "MORNING_LEVEL_REJECTION",
            f"VOL_{vol_ratio:.1f}X",
        ],
        metadata={
            "promotion_status": "WATCH_ONLY",
            "rejection_level": rejection_level,
            "rejection_body_cents": rejection_body_cents,
            "vol_ratio": vol_ratio,
            "upper_wick_dollars": round(upper_wick, 4),
            "wick_to_body_ratio": round(wick_to_body_ratio, 2),
            "is_bear_candle": is_bear_candle,
            "htf_15m_stack": htf_str,
            "htf_alignment": htf_alignment,
            "chart_stop_above_level": _CHART_STOP_ABOVE_LEVEL,
            "default_qty": DEFAULT_QTY,
            "default_premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,
            "default_tp1_pct": DEFAULT_TP1_PREMIUM_PCT,
            "default_runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
            "op21_live_confirmed": 0,
            "op21_live_required": 3,
            "j_anchor_coverage": ["2026-04-29 10:25 +342", "2026-05-04 10:27 +730"],
            "spec_file": "strategy/candidates/2026-05-24-bearish-rejection-morning-watcher.md",
        },
    )
