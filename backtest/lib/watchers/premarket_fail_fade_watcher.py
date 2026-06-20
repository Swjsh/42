"""PREMARKET_FAIL_FADE watcher — wraps detect_premarket_fail_fade().

Per CLAUDE.md OP 21 + markdown/0dte/premarket_fail_fade.md this setup starts
WATCH-ONLY. Detects first-3-bars failure-to-test of a major premarket
resistance level + committed red body → fades short.

Extracted from J's 2026-05-13 09:30 ET real-money trade
(SPY 736P x 5, +$443 / +115% in 18 min). The 7 existing watchers all
missed this setup because:
  - SNIPER needs a level BREAK; here the level was never even tested.
  - VWAP needs VWAP history; opening bar has none.
  - ORB needs 30-min range; fires earliest 10:00 ET.
  - ODF needs HOD/LOD ratchet (2+ bars).
  - PIN_FADE is disabled.
  - BULLISH/v14_ENHANCED filtered by ribbon spread; opening bar ribbon has no signal.

Default knobs come from markdown/0dte/premarket_fail_fade.md sections 3+5
(spec defaults; Stage 1 sweep pending — NOT ratified).

The wrapper is a thin adapter:
  1. Build PremarketFailFadeParams from spec defaults
  2. Read today-bias.json for premarket resistance levels
  3. Assemble level union (bias + historical via compute_levels)
  4. Call detect_premarket_fail_fade()
  5. If signal fires, translate to WatcherSignal

DOES NOT place orders. Observation-only — order placement is heartbeat's
job (when promoted).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional

import pandas as pd

from . import WatcherSignal
from ..premarket_fail_fade_detector import (
    PremarketFailFadeParams,
    assemble_levels,
    detect_premarket_fail_fade,
)


# Default knobs from markdown/0dte/premarket_fail_fade.md section 3 (DRAFT).
DEFAULT_PROXIMITY_TO_LEVEL_DOLLARS = 0.50
DEFAULT_BODY_MIN_CENTS = 0.20
DEFAULT_VOL_MULT = 1.0  # baseline — no volume gate
DEFAULT_MIN_STARS = 2
DEFAULT_LOOKBACK_BARS = 3
DEFAULT_DIRECTION = "short_only"
DEFAULT_LEVEL_UPPER_TOLERANCE = 0.05
DEFAULT_STOP_BUFFER_DOLLARS = 0.10
DEFAULT_TP1_DISTANCE_DOLLARS = 1.00

# Exit knobs (per OP 21 default watcher knobs + spec section 2/3)
DEFAULT_STRIKE_OFFSET = 2
DEFAULT_QTY = 3
DEFAULT_PREMIUM_STOP_PCT = -0.10
DEFAULT_TP1_PREMIUM_PCT = 0.75  # J's first scale: $0.77 -> $1.50 = +95%
DEFAULT_TP1_QTY_FRACTION = 0.50
DEFAULT_RUNNER_TARGET_PCT = 1.5  # 2x in spec; spot-side translation uses 1.5
DEFAULT_PROFIT_LOCK_THRESHOLD_PCT = 0.10
DEFAULT_PROFIT_LOCK_STOP_OFFSET_PCT = 0.05

# Bias file path (resolved relative to repo root)
_LIB_DIR = Path(__file__).resolve().parent
_BACKTEST_DIR = _LIB_DIR.parent.parent  # backtest/
_REPO_ROOT = _BACKTEST_DIR.parent
_TODAY_BIAS_PATH = _REPO_ROOT / "automation" / "state" / "today-bias.json"


def _build_params() -> PremarketFailFadeParams:
    """Construct PremarketFailFadeParams from spec defaults."""
    return PremarketFailFadeParams(
        proximity_to_level_dollars=DEFAULT_PROXIMITY_TO_LEVEL_DOLLARS,
        body_min_cents=DEFAULT_BODY_MIN_CENTS,
        vol_mult=DEFAULT_VOL_MULT,
        min_stars=DEFAULT_MIN_STARS,
        lookback_bars=DEFAULT_LOOKBACK_BARS,
        direction=DEFAULT_DIRECTION,
        level_upper_tolerance=DEFAULT_LEVEL_UPPER_TOLERANCE,
        stop_buffer_dollars=DEFAULT_STOP_BUFFER_DOLLARS,
    )


def _load_today_bias() -> Optional[dict]:
    """Read automation/state/today-bias.json. Returns None on any failure.

    Failures are non-fatal: detector falls back to historical levels only.
    """
    try:
        if not _TODAY_BIAS_PATH.exists():
            return None
        return json.loads(_TODAY_BIAS_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def detect_premarket_fail_fade_setup(
    bar: pd.Series,
    bar_idx: int,
    spy_bars: pd.DataFrame,
    params: Optional[PremarketFailFadeParams] = None,
    today_bias: Optional[dict] = None,
) -> Optional[WatcherSignal]:
    """Run PREMARKET_FAIL_FADE detector on the current bar.

    Args:
        bar: pandas Series with OHLCV + timestamp_et.
        bar_idx: integer position of `bar` within `spy_bars`.
        spy_bars: full SPY 5m DataFrame (RTH-filtered, multi-day for historical level).
        params: override; defaults to spec values.
        today_bias: pre-loaded bias dict. If None, watcher reads from disk.

    Returns:
        WatcherSignal if a PREMARKET_FAIL_FADE trigger fires, else None.
    """
    if bar is None or spy_bars is None or spy_bars.empty:
        return None

    bar_time = bar.get("timestamp_et")
    if bar_time is None or not hasattr(bar_time, "time"):
        return None

    p = params if params is not None else _build_params()

    # Early exit if bar is outside the 09:30-09:40 window — avoids the
    # cost of bias-file read on every bar.
    bar_t = bar_time.time()
    if bar_t < p.rth_open or bar_t > p.last_eligible_bar:
        return None

    bias = today_bias if today_bias is not None else _load_today_bias()

    # Coerce bar_time to datetime if it's a pd.Timestamp
    as_of = bar_time.to_pydatetime() if hasattr(bar_time, "to_pydatetime") else bar_time

    levels = assemble_levels(
        spy_bars=spy_bars,
        as_of=as_of,
        today_bias=bias,
    )
    if not levels:
        return None

    signal = detect_premarket_fail_fade(
        bar=bar,
        bar_idx=bar_idx,
        spy_bars=spy_bars,
        levels=levels,
        params=p,
        today_bias=bias,
    )
    if signal is None:
        return None

    # Translate to WatcherSignal spot-price targets (heuristic; canonical exits
    # live in metadata percent knobs).
    entry = float(signal.entry_price)
    # Stop sits at level + buffer (above entry). For SHORT this is a stop-out
    # if price reclaims the level we faded.
    stop_price = float(signal.level.price + p.stop_buffer_dollars)
    # TP1 default: entry - tp1_distance_dollars OR support from bias if closer.
    tp1_distance = DEFAULT_TP1_DISTANCE_DOLLARS
    bias_support = None
    if isinstance(today_bias if today_bias is not None else _load_today_bias(), dict):
        bias_dict = today_bias if today_bias is not None else _load_today_bias()
        kl = bias_dict.get("key_levels", {}) if isinstance(bias_dict, dict) else {}
        sup_list = kl.get("support", []) if isinstance(kl, dict) else []
        # Pick nearest support below entry, within $3
        candidates = []
        for v in sup_list:
            try:
                fv = float(v)
                if fv < entry - 0.10 and (entry - fv) <= 3.0:
                    candidates.append(fv)
            except (TypeError, ValueError):
                pass
        if candidates:
            bias_support = max(candidates)  # highest support below entry
    if bias_support is not None:
        tp1_price = bias_support
    else:
        tp1_price = entry - tp1_distance
    # Runner is more aggressive: 2x the TP1 distance (or premium 1.5x knob).
    runner_price = entry - max(tp1_distance * 2.0, entry - tp1_price + 0.50)

    # Confidence tiering:
    # - HIGH: ELITE level (3 stars) AND body >= 0.30
    # - MEDIUM: 2-star level AND body >= 0.20 (the default tier)
    # - LOW: edge cases (small body or weak level)
    if signal.level.stars >= 3 and signal.body_dollars >= 0.30:
        confidence = "high"
    elif signal.level.stars >= 2 and signal.body_dollars >= 0.20:
        confidence = "medium"
    else:
        confidence = "low"

    quality_tier = "ELITE" if signal.level.stars >= 3 else "BASE"

    reason = (
        f"PFF short {signal.level.label}@{signal.level.price:.2f} "
        f"({signal.level.tier}, {signal.level.stars}*) "
        f"open={signal.bar_open:.2f} high={signal.bar_high:.2f} "
        f"entry={entry:.2f} body=${signal.body_dollars:.2f} "
        f"d_lvl=${signal.distance_to_level:.2f}"
    )

    return WatcherSignal(
        watcher_name="premarket_fail_fade_watcher",
        setup_name="PREMARKET_FAIL_FADE",
        direction=signal.direction,
        entry_price=entry,
        stop_price=stop_price,
        tp1_price=float(tp1_price),
        runner_price=float(runner_price),
        confidence=confidence,
        reason=reason,
        triggers_fired=["level_fail_to_test", "red_body_commit", "opening_window"],
        metadata={
            "level_label": signal.level.label,
            "level_price": signal.level.price,
            "level_stars": signal.level.stars,
            "level_tier": signal.level.tier,
            "bar_open": signal.bar_open,
            "bar_high": signal.bar_high,
            "distance_to_level": signal.distance_to_level,
            "body_dollars": signal.body_dollars,
            "vol_ratio": signal.vol_ratio,
            "bar_volume": signal.bar_volume,
            "quality_tier": quality_tier,
            "tp1_source": "bias_support" if bias_support is not None else "default_distance",
            "strike_offset": DEFAULT_STRIKE_OFFSET,
            "default_qty": DEFAULT_QTY,
            "default_premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,
            "default_tp1_pct": DEFAULT_TP1_PREMIUM_PCT,
            "default_tp1_qty_fraction": DEFAULT_TP1_QTY_FRACTION,
            "default_runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
            "profit_lock_threshold_pct": DEFAULT_PROFIT_LOCK_THRESHOLD_PCT,
            "profit_lock_stop_offset_pct": DEFAULT_PROFIT_LOCK_STOP_OFFSET_PCT,
            "winner_combo_source": "DRAFT spec only — live observation needed",
            "promotion_status": "WATCH_ONLY",
        },
    )
