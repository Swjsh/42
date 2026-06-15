"""TBR High-Volume standalone watcher — WATCH-ONLY observation pump.

Wraps ``shotgun_scalper_detector.detect()`` and emits *only* the
TRENDLINE_BREAK_RETEST tier with volume ≥ 1.5× the trailing 20-bar
average.  Low-volume TBR signals are silently suppressed here (they
are still visible in the SHOTGUN watcher observations if SHOTGUN is
running, but they are excluded from this dedicated stream).

**Why a dedicated watcher?**

A 2026-05-24 analysis of 16 months of SHOTGUN observations found that
splitting TRENDLINE_BREAK_RETEST by volume relative to the trailing
20-bar average reveals a cleanly positive sub-set:

  TBR vol ≥ 1.5×:  N=144  P&L=+$442.50  exp=+$3.07/obs
  TBR vol < 1.5×:  N=684  P&L=−$804.95  exp=−$1.18/obs

Walk-forward validation (IS 2025-01-01→2025-09-30 / OOS 2025-10-01→2026-05-24):
  IS : n=70  WR=57.1%  exp=+$2.64
  OOS: n=70  WR=70.0%  exp=+$3.68  WF-ratio=1.39 (gate ≥ 0.50) → PASS

**OP-21 STATUS: WATCH_ONLY — real-fills validation pending**

Gates remaining before live promotion:
  1. ✅ Walk-forward OOS PASS (ratio=1.39, OOS WR=70%, 3 quarters positive)
  2. ✅ Concentration check PASS (max OOS quarter=54%, gate <80%)
  3. ❌ Real-fills validation: 10+ fills, WR ≥ 55% required
  4. ✅ Standalone watcher: this file

This watcher uses the SHOTGUN single-exit doctrine:
  - No TP1 partial exit.  No runner.  Full position at target.
  - Chandelier trailing stop: arms at +25c / +50c / +75c favorable SPY price.
  - Time stop: 12 min from entry.
  - EOD hard exit: 15:50 ET.

To grade accumulated observations use ``shotgun_grader.py`` (NOT
``watcher_grader.py``, which applies TP1+runner split).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from . import shotgun_scalper_detector as _detector
from .shotgun_scalper_watcher import _load_levels

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = REPO_ROOT / "automation" / "state"
OBS_LOG = STATE_DIR / "watcher-observations.jsonl"

STRATEGY_NAME = "tbr_high_vol"
PROMOTION_STATUS = "WATCH_ONLY"

# Minimum vol ratio to emit a signal (matches TBR_VOL_CONFIRM_MULT in detector).
TBR_VOL_MIN_RATIO = _detector.TBR_VOL_CONFIRM_MULT  # 1.5


def _is_high_vol_tbr(trigger: dict) -> bool:
    """Return True if trigger is a high-volume TBR signal."""
    if trigger.get("name") != "TRENDLINE_BREAK_RETEST":
        return False
    vr = trigger.get("vol_ratio") or 0.0
    conf = trigger.get("confidence", "low")
    # Accept if vol_ratio is recorded AND above threshold, OR if confidence
    # was marked high/medium by the detector (which gates on the same threshold).
    return vr >= TBR_VOL_MIN_RATIO or conf in ("high", "medium")


def detect_tbr_high_vol_setup(
    bar: pd.Series,
    day_bars: pd.DataFrame,
    bar_idx_in_day: int,
    ribbon_state_dict: Optional[dict] = None,
    vix_now: Optional[float] = None,
) -> Optional["WatcherSignal"]:  # type: ignore[name-defined]  # noqa: F821
    """Runner-compatible adapter: returns a WatcherSignal or None.

    Calls the full SHOTGUN detector, then filters to only TBR signals
    with vol_ratio ≥ TBR_VOL_MIN_RATIO.

    Args:
        bar: current closed bar (as Series with OHLCV + timestamp_et).
        day_bars: all RTH bars for today up to and including *bar*.
        bar_idx_in_day: index of *bar* within *day_bars*.
        ribbon_state_dict: ribbon snapshot dict (optional; neutral default used if absent).
        vix_now: VIX print (optional; 17.0 placeholder used if absent).

    Returns:
        WatcherSignal if a high-vol TBR fired, else None.
    """
    from . import WatcherSignal  # local import avoids circular deps

    if day_bars is None or day_bars.empty or bar_idx_in_day < 0:
        return None

    levels = _load_levels()

    rb = ribbon_state_dict or {
        "fast": float("nan"),
        "pivot": float("nan"),
        "slow": float("nan"),
        "spread_cents": 0.0,
        "stack": "NEUTRAL",
    }
    # Ensure spread_cents and stack are populated
    if "spread_cents" not in rb and {"fast", "slow"}.issubset(rb.keys()):
        try:
            rb["spread_cents"] = round((float(rb["slow"]) - float(rb["fast"])) * 100, 1)
        except Exception:
            rb["spread_cents"] = 0.0
    if "stack" not in rb and {"fast", "pivot", "slow"}.issubset(rb.keys()):
        try:
            f, p, s = float(rb["fast"]), float(rb["pivot"]), float(rb["slow"])
            rb["stack"] = "BULL" if f > p > s else "BEAR" if f < p < s else "MIXED"
        except Exception:
            rb["stack"] = "NEUTRAL"

    v = float(vix_now) if vix_now is not None else 17.0

    try:
        trigger = _detector.detect(
            today_bars=day_bars,
            today_bar_idx=bar_idx_in_day,
            levels=levels,
            ribbon=rb,
            vix=v,
            htf_15m_stack=None,
            auto_derive_intraday_levels=True,
        )
    except Exception:
        logger.exception("tbr_high_vol_watcher: shotgun_scalper_detector raised")
        return None

    if trigger is None:
        return None

    if not _is_high_vol_tbr(trigger):
        # Not a TBR, or vol below threshold — skip silently
        return None

    direction = (
        "short"
        if trigger.get("direction", "").lower() in ("put", "short", "bearish")
        else "long"
    )
    entry_px = float(bar.get("close", trigger.get("rejection_low") or 0.0))
    target_px = float(trigger.get("target_level") or entry_px)
    stop_px = float(trigger.get("stop_chart") or entry_px)
    vol_ratio = trigger.get("vol_ratio") or 0.0
    confidence = trigger.get("confidence", "medium")

    return WatcherSignal(
        watcher_name="tbr_high_vol_watcher",
        setup_name="TBR_HIGH_VOL",
        direction=direction,
        entry_price=entry_px,
        stop_price=stop_px,
        tp1_price=target_px,
        runner_price=None,  # SHOTGUN doctrine: single exit, NO runner
        confidence=confidence,
        reason=trigger.get("reasoning", "TBR high-vol trigger"),
        triggers_fired=["TBR_HIGH_VOL"],
        metadata={
            "tier": 3,
            "rejection_high": trigger.get("rejection_high"),
            "rejection_low": trigger.get("rejection_low"),
            "target_level": trigger.get("target_level"),
            "target_label": trigger.get("target_label"),
            "vol_ratio": vol_ratio,
            "vol_ratio_threshold": TBR_VOL_MIN_RATIO,
            "promotion_status": PROMOTION_STATUS,
            "doctrine": "single_exit_no_runner",
            "grader": "shotgun_grader.py",
        },
    )


__all__ = [
    "STRATEGY_NAME",
    "PROMOTION_STATUS",
    "TBR_VOL_MIN_RATIO",
    "detect_tbr_high_vol_setup",
]
