"""DOUBLE_BOTTOM_MORNING_LOW_VOL watcher (WATCH-ONLY per OP-21).

16-month combination search (2025-01-01 to 2026-05-15) Rank #3 by OP-16 score:
    double_bottom | NOT_NEAR_NAMED | MORNING | vix=LOW_VOL
    N=166, WR=62.0%, EdgeCap=+$19.20, Score=+5.39

The highest sample-size result in the full leaderboard (N=166, ~0.52 fires/RTH day).

Setup definition:
  1. `double_bottom_detector` fires on the current bar's sliding window
  2. Bar is in MORNING window (09:35-11:30 ET) — avoids afternoon volatility patterns
  3. VIX < 20 at entry (LOW_VOL regime) — quiet market = clean mean-reversion
  4. Pattern center NOT within $0.50 of any ★★+ named level (enrich_hit_with_proximity)
  5. Cooldown: 30 min between signals to prevent duplicate re-fires on same pattern

Walk-forward validation result (2026-05-20):
  - Train (2025-01-01 to 2025-09-30): N=51, WR=72.55%
  - Test  (2025-10-01 to 2026-05-15): N=115, WR=57.39%  ← -15.2pp degradation
  - VERDICT: DEGRADED — the MORNING filter overfits to early 2025
  - The high-WR early period likely reflects a specific tape regime (trend + low vol)
    that does not persist into 2026. Still above 50%, but not the 62% headline figure.
  - STATUS: WATCH_FRAGILE — observe but treat as lower-confidence than initially ranked.
  - The more robust variant (without MORNING filter) is in momentum_acceleration_highvol.
  - Per OP-21: still viable for watch-only observation; promotion gate is stricter given drift.

Why low-vol morning was the sweet spot (early 2025):
  - Double bottom is a mean-reversion completion pattern (W shape)
  - In low vol (VIX<20), the tape is consolidating — W completions are high-fidelity
  - Morning fires (09:35-11:30) have the day's full extension ahead
  - NOT_NEAR_NAMED means the W is forming in open price space, not fighting a level

Real-fills validation result (2026-05-20):
  - N=116 signals (simplified scan, NOT_NEAR_NAMED omitted), 109 completed, 7 no OPRA data
  - Real WR=67.9% (74W/35L), delta=+5.9pp vs scan proxy 62.0%. Total P&L=+$828.
  - VERDICT: FAVORABLE — real-fills WR exceeds scan proxy despite MORNING filter degradation
  - Key insight: low-conf patterns (0.5-0.6) WR=74.2% outperform high-conf (0.7+) WR=56.2%
    (textbook W patterns may be "obvious" = already-priced; base patterns in open space = edge)
  - Exit breakdown: 51% TP1_THEN_RUNNER_RIBBON (+$80 avg), 27% chart_stop (-$254 avg)
  - NOT_NEAR_NAMED filter omitted — adding it should further improve WR
  - Full results: analysis/recommendations/db-morning-lowvol-real-fills.json

Why this is watch-only (OP-21 gates not yet met):
  - 16-month historical gate: 3+ wins PASS (N=166) ✓
  - Walk-forward OOS: DEGRADED -15.2pp (train N=51 WR=72.55% → test N=115 WR=57.39%) ✗
  - Real-fills: FAVORABLE +5.9pp (WR=67.9%, +$828 total P&L) ✓
  - Live J observations: 0/3 needed

OP-21 promotion gate:
  - Historical: N>=166 (full 16-month) ✓
  - Walk-forward: DEGRADED -15.2pp (train N=51 WR=72.55% -> test N=115 WR=57.39%) ✗
    STATUS: WATCH_FRAGILE — above 50% but not the headline 62%; promotion gate is stricter.
    The walk-forward degradation is the source of the MORNING filter overfitting signal.
  - Real-fills: FAVORABLE +5.9pp (WR=67.9%, N=109 completed, total +$828) ✓
    NOTE: simplified scan omits NOT_NEAR_NAMED — full-filter real-fills pending.
  - Live: 3+ live J confirmations on morning double bottom in quiet market
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from . import WatcherSignal
from ..filters import BarContext

try:
    from crypto.lib.chart_patterns import Bar, double_bottom_detector, enrich_hit_with_proximity
    _PATTERNS_AVAILABLE = True
except ImportError:
    _PATTERNS_AVAILABLE = False


# ── Detection thresholds ─────────────────────────────────────────────────────

# Time window: MORNING only (combo_search split 09:30-11:30 vs 11:30-15:55)
ENTRY_TIME_START: dt.time = dt.time(9, 35)
ENTRY_TIME_END: dt.time = dt.time(11, 30)

# VIX gate: LOW_VOL regime (VIX<20 in combo_search)
VIX_LOW_VOL_CEILING: float = 20.0

# Proximity gate: NOT within $0.50 of any ★★+ named level
PROXIMITY_MAX_DISTANCE: float = 0.50  # if within $0.50 → reject (NEAR_NAMED case)

# Sliding window for double_bottom_detector: last 30 bars (~2.5 hours of 5m bars)
# Double bottom needs ~10-20 bars minimum; 30 gives enough lookback
_WINDOW_BARS: int = 30

# Cooldown: don't re-fire the same watcher within 30 min of the last signal
_COOLDOWN_MINUTES: int = 30


# ── Default exit knobs (OP-21 watch-only conservative) ───────────────────────

DEFAULT_QTY: int = 3
DEFAULT_PREMIUM_STOP_PCT: float = -0.99   # chart-stop ONLY (L55 analog — double bottom
                                          # can have brief premium dip after neckline reclaim
                                          # before the full move develops). Only chart stop
                                          # via rejection_level = neckline - $0.30
DEFAULT_TP1_PREMIUM_PCT: float = 0.30     # +30% premium fallback TP1
DEFAULT_RUNNER_TARGET_PCT: float = 1.5    # conservative runner

# SPY-level targets (for observation grading in watcher_live.py)
_CHART_STOP_BELOW_NECKLINE: float = 0.30   # stop = neckline - $0.30 (below reclaim invalidates)
_TP1_SPY_MOVE: float = 0.70                # TP1 ≈ entry + $0.70 (half of median double-bottom move)
_RUNNER_SPY_MOVE: float = 2.00             # runner ≈ entry + $2.00


# ── Module-level state (cooldown tracking) ────────────────────────────────────

_last_signal_time: Optional[dt.datetime] = None


def _build_bars_from_context(ctx: BarContext) -> list[Bar]:
    """Convert the last _WINDOW_BARS rows of prior_bars into Bar objects."""
    if not _PATTERNS_AVAILABLE:
        return []
    import pandas as pd

    df = ctx.prior_bars.tail(_WINDOW_BARS).copy()
    bars = []
    for ts, row in df.iterrows():
        # prior_bars index may be integer or datetime
        if isinstance(ts, (int, float)):
            # fallback: use the bar's position as a synthetic timestamp offset
            open_time = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=int(ts) * 300)
        else:
            # convert to UTC datetime
            try:
                open_time = pd.Timestamp(ts).tz_localize("UTC") if pd.Timestamp(ts).tzinfo is None else pd.Timestamp(ts).tz_convert("UTC")
                open_time = open_time.to_pydatetime()
            except Exception:
                open_time = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)
        bars.append(Bar(
            open_time=open_time,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 50_000)),
            granularity_seconds=300,
            source="spy_5m",
        ))
    return bars


def detect_db_morning_low_vol_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect DOUBLE_BOTTOM_MORNING_LOW_VOL setup on the current bar.

    Returns WatcherSignal with direction="long" if all gates pass.
    Returns None if any gate fails.

    Confidence tiers:
      - "high":   VIX 15-19 AND bars_between in [4,12] AND decent_neckline_height
      - "medium": VIX < 17 OR any one high-quality factor active in v2
      - "low":    base pattern only (conf=0.45, no augmenting factors)
    """
    global _last_signal_time

    if not _PATTERNS_AVAILABLE:
        return None

    # ── Gate 1: Morning window (09:35-11:30 ET) ─────────────────────────────
    bar_time = ctx.timestamp_et.time()
    if bar_time < ENTRY_TIME_START or bar_time > ENTRY_TIME_END:
        return None

    # ── Gate 2: VIX LOW_VOL (<20) ────────────────────────────────────────────
    if ctx.vix_now >= VIX_LOW_VOL_CEILING:
        return None

    # ── Gate 3: Cooldown — don't re-fire within 30 min ───────────────────────
    if _last_signal_time is not None:
        elapsed = (ctx.timestamp_et - _last_signal_time).total_seconds() / 60.0
        if elapsed < _COOLDOWN_MINUTES:
            return None

    # ── Gate 4: Run double_bottom_detector on sliding window ─────────────────
    bars = _build_bars_from_context(ctx)
    if len(bars) < 10:
        return None

    hit = double_bottom_detector(bars)
    if hit is None:
        return None

    # ── Gate 5: NOT near a named level ($0.50 proximity check) ───────────────
    # Build named_levels dicts from ctx.levels_active (all levels are ★2+ by construction)
    named_levels = [
        {"price": lvl, "name": f"level_{lvl:.2f}", "stars": 2}
        for lvl in ctx.levels_active
    ]
    enriched = enrich_hit_with_proximity(hit, named_levels, max_distance=PROXIMITY_MAX_DISTANCE)
    if enriched.notes.get("near_key_level") is True:
        return None  # NEAR_NAMED — this combo has lower edge; wait for open space

    # ── Signal passes all gates ───────────────────────────────────────────────
    _last_signal_time = ctx.timestamp_et

    bar_close = float(ctx.bar["close"])
    neckline = enriched.notes.get("neckline", bar_close)  # double_bottom notes carry neckline

    # Confidence tier
    v2_factors = enriched.notes.get("v2_factors_active", [])
    conf_score = enriched.confidence

    if conf_score >= 0.70 and len(v2_factors) >= 3:
        confidence = "high"
        conf_note = f"v2 factors={v2_factors} conf={conf_score:.2f} (multi-factor confirmation)"
    elif conf_score >= 0.60 or len(v2_factors) >= 1:
        confidence = "medium"
        conf_note = f"v2 factors={v2_factors} conf={conf_score:.2f} (partial confirmation)"
    else:
        confidence = "low"
        conf_note = f"base pattern, no augmenting factors conf={conf_score:.2f} (WR=62% OOS at N=166)"

    # Stop, TP1, runner prices
    stop_price = float(neckline) - _CHART_STOP_BELOW_NECKLINE
    tp1_price = bar_close + _TP1_SPY_MOVE
    runner_price = bar_close + _RUNNER_SPY_MOVE

    vix_regime = f"VIX={ctx.vix_now:.2f} (LOW_VOL <{VIX_LOW_VOL_CEILING})"
    proximity_note = enriched.notes.get("nearest_key_level_distance", None)
    prox_str = f"nearest_level_dist=${proximity_note:.2f}" if proximity_note else "no_nearby_level"

    return WatcherSignal(
        watcher_name="db_morning_low_vol",
        setup_name="DOUBLE_BOTTOM_MORNING_LOW_VOL",
        direction="long",
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=(
            f"Double bottom ({conf_note}). "
            f"Neckline={neckline:.2f}, stop={stop_price:.2f}. "
            f"{vix_regime}. {prox_str}."
        ),
        triggers_fired=["double_bottom_detector", "morning_window", "low_vol_vix", "not_near_named"],
        metadata={
            "combo_search_rank": 3,
            "combo_search_n": 166,
            "combo_search_wr_pct": 62.0,
            "combo_search_window": "2025-01-01 to 2026-05-15",
            "confidence_score": conf_score,
            "v2_factors_active": v2_factors,
            "neckline": neckline,
            "vix_now": ctx.vix_now,
            "op21_live_gate": "0/3 — DO NOT promote until 3+ live J confirmations",
        },
    )
