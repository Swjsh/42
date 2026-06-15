"""v14_enhanced watcher — wraps evaluate_bearish_setup/evaluate_bullish_setup
with the alt-scoring top combo's early-entry + profit-lock knobs.

v14_enhanced extends production v14 BEARISH_REJECTION_RIDE_THE_RIBBON +
BULLISH_RECLAIM_RIDE_THE_RIBBON with:
  - no_trade_before relaxed from 10:00 ET to 09:45 ET (earlier entries)
  - profit_lock_threshold_pct = 0.05 (arm at +5% favor instead of v14's +10%)
  - profit_lock_offset_pct = 0.10 (lock stop to +10%, not v14's +5%)
  - tp1_qty_fraction = 0.5 (sell half at TP1 instead of v14's 0.667)
  - runner_target_pct = 2.5 (vs v14's 1.5)

Per CLAUDE.md OP 21 this variant starts WATCH-ONLY. Setup name is
"BEARISH_REJECTION_v14e" / "BULLISH_RECLAIM_v14e" to distinguish from
production v14 (which heartbeat runs as the live engine).

The wrapper is a thin adapter:
  1. Run evaluate_bearish_setup + evaluate_bullish_setup with the
     no_trade_before=09:45 override
  2. If either passes, emit a WatcherSignal with the v14e knobs in
     metadata so the heartbeat can later replay/grade against them

DOES NOT modify or override the production v14 watchers — only ADDS the
v14e variant. Heartbeat continues to use production filters.py.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from . import WatcherSignal
from ..filters import (
    BarContext,
    evaluate_bearish_setup,
    evaluate_bullish_setup,
)


# v14_enhanced alt-scoring top combo defaults
# 2026-05-13 J explicit instruction: "we were supposed to remove the time gates
# entirely, from all strategies". Time gate removed (09:30 = market open).
# Keep no_trade_window 14:00-15:00 (separate from open gate — that's chop window).
DEFAULT_NO_TRADE_BEFORE = dt.time(9, 30)
DEFAULT_NO_TRADE_WINDOW = (dt.time(14, 0), dt.time(15, 0))
DEFAULT_MIN_TRIGGERS = 1

# Exit knobs (v14_enhanced alt-scoring top combo)
DEFAULT_PROFIT_LOCK_THRESHOLD_PCT = 0.05
DEFAULT_PROFIT_LOCK_STOP_OFFSET_PCT = 0.10
DEFAULT_TP1_QTY_FRACTION = 0.5
DEFAULT_RUNNER_TARGET_PCT = 2.5

# Inherited from v14 (unchanged)
DEFAULT_STRIKE_OFFSET = 2
DEFAULT_QTY = 3
DEFAULT_PREMIUM_STOP_PCT = -0.08
DEFAULT_TP1_PREMIUM_PCT = 0.30

# Direction filter (V14E_BEAR_ONLY_GATE — OP-22 engine-benefit, 2026-05-21)
# 502 graded observations: short (N=241, WR=58.5%, +$1,492) vs long (N=261, WR=47.9%, -$3,642).
# Score=11 is structurally ALL long — bull v14e max score — and is the entire drag.
# Filter to "bear" to accumulate bear-only forward observations for the promotion path.
# Set to None to restore both directions (R&D use only).
# Candidate: strategy/candidates/2026-05-21-v14e-quality-filter.md
V14E_DIRECTION_FILTER: Optional[str] = "bear"

# Chop-zone quality elevation (V14E_CHOP_ZONE_GATE — OP-22 engine-benefit, 2026-05-24)
# IS/OOS walk-forward (backtest/autoresearch/_v14e_ampm_oos.py) confirms 10:xx-11:xx
# have structurally negative expectancy in both IS and OOS:
#   IS: 10:xx WR=50% exp=-$18.14 / 11:xx WR=31.2% exp=-$17.93
#   OOS: 10:xx WR=41.7% / 11:xx WR=45.8% exp=-$7.65
# BUT: HIGH+AM OOS N=7 WR=71.4% — high-confidence signals remain profitable in chop zone.
# Gate: during chop hours, require confidence=="high" AND score>=V14E_CHOP_MIN_SCORE to fire.
# This preserves J-style high-quality 10:xx entries (e.g., 4/29 10:25 +$342, 5/04 10:27 +$730)
# while eliminating low-quality watcher noise.
# OP-16 check: J's 10:xx winners have confluence + multiple triggers -> confidence=="high".
# Candidate: strategy/candidates/2026-05-24-v14e-bear-time-of-day-gate.md
V14E_CHOP_HOURS: frozenset = frozenset({10, 11})
V14E_CHOP_MIN_SCORE: int = 9


def _confidence_from_score(score: int, n_triggers: int, has_confluence: bool) -> str:
    """Map (score, n_triggers, confluence_flag) to confidence tier."""
    if has_confluence and n_triggers >= 3:
        return "high"
    if score >= 9 or has_confluence:
        return "medium"
    return "low"


def _vix_regime(vix: float) -> str:
    """Classify VIX into the regime buckets used by the high-conf promotion path."""
    if vix <= 0:
        return "UNKNOWN"
    if vix < 15:
        return "VIX_LOW"
    if vix < 20:
        return "VIX_MODERATE"
    if vix < 25:
        return "VIX_ELEVATED"
    return "VIX_HIGH"


def _build_metadata(
    direction: str,
    score: int,
    triggers: list[str],
    blockers: list[int],
    level: Optional[float],
    setup_label: str,
    vix: float = 0.0,
) -> dict:
    """Build the metadata dict for a v14e watcher signal."""
    return {
        "score": score,
        "blockers": list(blockers),
        "triggers": list(triggers),
        "rejection_or_reclaim_level": level,
        "setup_label": setup_label,
        "no_trade_before": str(DEFAULT_NO_TRADE_BEFORE),
        "no_trade_window": [
            str(DEFAULT_NO_TRADE_WINDOW[0]),
            str(DEFAULT_NO_TRADE_WINDOW[1]),
        ],
        "strike_offset": DEFAULT_STRIKE_OFFSET,
        "default_qty": DEFAULT_QTY,
        "default_premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,
        "default_tp1_pct": DEFAULT_TP1_PREMIUM_PCT,
        "default_tp1_qty_fraction": DEFAULT_TP1_QTY_FRACTION,
        "default_runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
        "profit_lock_threshold_pct": DEFAULT_PROFIT_LOCK_THRESHOLD_PCT,
        "profit_lock_stop_offset_pct": DEFAULT_PROFIT_LOCK_STOP_OFFSET_PCT,
        "winner_combo_source": "v14_enhanced alt-scoring top combo (DRAFT, not ratified)",
        "promotion_status": "WATCH_ONLY",
        "vix_at_signal": round(vix, 2) if vix > 0 else None,
        "vix_regime": _vix_regime(vix),
    }


def detect_v14_enhanced_setup(ctx: Optional[BarContext]) -> Optional[WatcherSignal]:
    """Run v14_enhanced bearish + bullish filters; emit a WatcherSignal if either passes.

    Args:
        ctx: BarContext describing the trigger bar. None-safe (returns None).

    Returns:
        WatcherSignal if either the bearish or bullish v14e filter chain
        passes; else None. If both pass on the same bar (rare), the bearish
        side wins (matches v14 production tie-break).
    """
    if ctx is None:
        return None
    if ctx.bar is None:
        return None

    bar_close = float(ctx.bar.get("close", 0.0))
    if bar_close <= 0:
        return None

    # ----- Bearish v14e -----
    bear_result = evaluate_bearish_setup(
        ctx,
        min_triggers=DEFAULT_MIN_TRIGGERS,
        no_trade_before=DEFAULT_NO_TRADE_BEFORE,
        no_trade_window=DEFAULT_NO_TRADE_WINDOW,
    )
    if bear_result.passed:
        level = bear_result.rejection_level
        triggers = list(bear_result.triggers_fired)
        has_confluence = "confluence" in triggers
        confidence = _confidence_from_score(
            bear_result.bear_score, len(triggers), has_confluence
        )

        # Chop-zone quality gate (V14E_CHOP_ZONE_GATE — OP-22 engine-benefit, 2026-05-24)
        # During 10:xx-11:xx, only fire if confidence=="high" AND score>=9.
        # Lower-quality chop-zone signals have WR<50% in both IS and OOS.
        bar_hour = ctx.timestamp_et.hour
        if bar_hour in V14E_CHOP_HOURS:
            if confidence != "high" or bear_result.bear_score < V14E_CHOP_MIN_SCORE:
                return None  # chop-zone quality gate: insufficient quality to fire

        # Stop above rejection level (chart stop), else 0.30 above close
        stop_price = (level + 0.20) if level else (bar_close + 0.30)
        stop_dist = stop_price - bar_close
        tp1_price = bar_close - 0.7 * stop_dist
        runner_price = bar_close - 2.5 * stop_dist  # honors runner_target_pct=2.5

        return WatcherSignal(
            watcher_name="v14_enhanced_watcher",
            setup_name="BEARISH_REJECTION_v14e",
            direction="short",
            entry_price=bar_close,
            stop_price=float(stop_price),
            tp1_price=float(tp1_price),
            runner_price=float(runner_price),
            confidence=confidence,
            reason=(
                f"bear_score={bear_result.bear_score}/10 "
                f"triggers={triggers} rejection={level}"
            ),
            triggers_fired=triggers,
            metadata=_build_metadata(
                direction="short",
                score=bear_result.bear_score,
                triggers=triggers,
                blockers=bear_result.blockers,
                level=level,
                setup_label="BEARISH_REJECTION_v14e",
                vix=float(getattr(ctx, "vix_now", None) or 0.0),
            ),
        )

    # ----- Bullish v14e (suppressed when V14E_DIRECTION_FILTER == "bear") -----
    if V14E_DIRECTION_FILTER == "bear":
        return None  # direction filter: accumulate bear-only forward observations

    bull_result = evaluate_bullish_setup(
        ctx,
        min_triggers=DEFAULT_MIN_TRIGGERS,
        no_trade_before=DEFAULT_NO_TRADE_BEFORE,
        no_trade_window=DEFAULT_NO_TRADE_WINDOW,
    )
    if bull_result.passed:
        level = bull_result.reclaim_level
        triggers = list(bull_result.triggers_fired)
        has_confluence = "confluence" in triggers
        confidence = _confidence_from_score(
            bull_result.bull_score, len(triggers), has_confluence
        )

        # Stop below reclaim level (chart stop), else 0.30 below close
        stop_price = (level - 0.20) if level else (bar_close - 0.30)
        stop_dist = bar_close - stop_price
        tp1_price = bar_close + 0.7 * stop_dist
        runner_price = bar_close + 2.5 * stop_dist  # honors runner_target_pct=2.5

        return WatcherSignal(
            watcher_name="v14_enhanced_watcher",
            setup_name="BULLISH_RECLAIM_v14e",
            direction="long",
            entry_price=bar_close,
            stop_price=float(stop_price),
            tp1_price=float(tp1_price),
            runner_price=float(runner_price),
            confidence=confidence,
            reason=(
                f"bull_score={bull_result.bull_score}/11 "
                f"triggers={triggers} reclaim={level}"
            ),
            triggers_fired=triggers,
            metadata=_build_metadata(
                direction="long",
                score=bull_result.bull_score,
                triggers=triggers,
                blockers=bull_result.blockers,
                level=level,
                setup_label="BULLISH_RECLAIM_v14e",
                vix=float(getattr(ctx, "vix_now", None) or 0.0),
            ),
        )

    return None
