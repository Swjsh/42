"""Bullish watcher — BULLISH_RECLAIM_RIDE_THE_RIBBON setup detector.

Mirror of the bearish setup. Uses the existing evaluate_bullish_setup() in
lib/filters.py (already implemented) — this is a thin adapter that:

  1. Runs the bullish filter checklist (11 filters)
  2. If passed → emits a WatcherSignal
  3. Watch-only (does NOT enter)

Per CLAUDE.md OP 16: bullish stays in DRAFT until 3 live wins are documented.
This watcher accelerates that — every bullish trigger fires gets logged with
would-be P&L so you can build the source-of-truth list quickly.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from . import WatcherSignal
from ..filters import (
    BarContext,
    evaluate_bullish_setup,
    vol_baseline_20bar,
    range_baseline_20bar,
)


# Default conservative knobs (until ratification per OP 16)
DEFAULT_QTY = 3
DEFAULT_PREMIUM_STOP_PCT = -0.10
DEFAULT_TP1_PREMIUM_PCT = 0.30
DEFAULT_RUNNER_TARGET_PCT = 1.5


def detect_bullish_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Run the bullish filter checklist; emit a WatcherSignal if passed.

    The bullish setup uses 11 filters per heartbeat.md BULLISH:
      1.  time gates
      2.  news clear
      3.  budget
      4.  day-trades
      5.  ribbon BULL-stacked
      6.  spread >= 30c
      7.  NOT volume_divergence
      8.  VIX < 17.20 OR vix_falling
      9.  VIX < 22 HARD
      10. buyer pressure
      11. >= min_triggers AND htf != BEAR
    """
    # 2026-05-10 evening tune: relax min_triggers to 1 to fire more often,
    # but still require a level-tied trigger (engine's Filter 11 enforces this).
    # Quality is graded via confidence tier instead of binary fire/skip.
    result = evaluate_bullish_setup(
        ctx,
        min_triggers=1,
        no_trade_before=dt.time(10, 0),
        no_trade_window=(dt.time(14, 0), dt.time(15, 0)),
    )
    if not result.passed:
        return None
    # Require at least one level-tied trigger for ANY confidence
    level_tied = {"level_reclaim", "confluence", "sequence_reclaim"}
    if not any(t in level_tied for t in result.triggers_fired):
        return None

    # Compute entry/stop/targets from current bar + reclaim level
    bar_close = float(ctx.bar["close"])
    reclaim_level = result.reclaim_level

    # Stop = below reclaim level (chart stop)
    stop_price = (reclaim_level - 0.20) if reclaim_level else (bar_close - 0.30)

    # TP1 = +30% on premium (translated: SPY needs to move ~$1.20 for ATM call)
    # For watcher, approximate TP1 SPY price = entry + 0.7 × stop_distance
    stop_dist = bar_close - stop_price
    tp1_price = bar_close + 0.7 * stop_dist
    runner_price = bar_close + 1.5 * stop_dist

    # Confidence: three-tier system with volume_confirm as supplementary 3rd trigger.
    #
    # History: 2026-05-21 fix set high=n_triggers>=2.  But ALL 289 historical obs had
    # n_triggers=2 (confluence + level_reclaim always co-fire), so ALL got "high" — tier
    # was still structurally undiversified (leaderboard #9 caveat).
    #
    # 2026-05-24 volume_confirm fix: add volume ≥ 1.5× 20-bar avg as a supplementary
    # trigger so n_triggers can be 2 (→ medium) or 3 (→ high), creating real diversity.
    # Tier thresholds:
    #   high   = n_triggers ≥ 3  (base pair + volume_confirm)
    #   medium = n_triggers ≥ 2 OR has_confluence OR sequence_reclaim
    #   low    = all others
    _VOL_CONFIRM_MULT = 1.5
    triggers = list(result.triggers_fired)  # mutable copy
    has_confluence = "confluence" in triggers
    if ctx.vol_baseline_20 > 0 and ctx.bar["volume"] >= _VOL_CONFIRM_MULT * ctx.vol_baseline_20:
        triggers.append("volume_confirm")
    n_triggers = len(triggers)
    if n_triggers >= 3:
        confidence = "high"
    elif n_triggers >= 2 or has_confluence or "sequence_reclaim" in triggers:
        confidence = "medium"
    else:
        confidence = "low"

    return WatcherSignal(
        watcher_name="bullish_watcher",
        setup_name="BULLISH_RECLAIM_RIDE_THE_RIBBON",
        direction="long",
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=f"bull_score={result.bull_score}/11 triggers={triggers} reclaim={reclaim_level}",
        triggers_fired=list(triggers),
        metadata={
            "bull_score": result.bull_score,
            "blockers": list(result.blockers),
            "reclaim_level": reclaim_level,
            "ribbon_flipped": result.ribbon_just_flipped_bullish,
            "confluence": result.confluence_match,
            "volume_confirm": "volume_confirm" in triggers,
            "vol_baseline_20": round(float(ctx.vol_baseline_20), 0),
            "bar_volume": int(ctx.bar["volume"]),
            "stop_dist_dollars": stop_dist,
            "default_qty": DEFAULT_QTY,
            "default_premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,
            "default_tp1_pct": DEFAULT_TP1_PREMIUM_PCT,
            "default_runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
        },
    )
