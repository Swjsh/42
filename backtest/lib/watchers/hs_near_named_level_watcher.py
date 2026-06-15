"""HEAD_AND_SHOULDERS_NEAR_NAMED_LEVEL watcher (WATCH_FRAGILE — 16-month WR=50.0%, NO EDGE).

90-Day OOS evidence (2025-12-01 to 2026-03-31, 87 trading days):
    head_and_shoulders_top::near_named  N=26, WR=61.5% (+13.0pp vs base 48.5%)
    head_and_shoulders_top::no_named    N=33, WR=48.5%

    The proximity-to-named-level filter is the ENTIRE edge for H&S:
    - Without proximity filter: N=60, WR=54.2% (barely above 50%)
    - Near named level: N=26, WR=61.5% (strong)
    - Far from named level: N=33, WR=48.5% (below 50%)

    Structural interpretation: H&S tops that COMPLETE near a ★★+ named level
    (PDH, PDL, 5-day high/low, key swing) get amplified follow-through from
    level participants adding to the bearish break. The level acts as a "floor
    of conviction" for sellers — when H&S forms exactly AT a named resistance
    and then breaks below its neckline, it combines two bearish signals in one.

    Contrast with momentum_acceleration::near_named (NEGATIVE, N=36 WR=50.0%):
    impulse bars STALL at named levels. Structural patterns ACCELERATE from them.
    This asymmetry is the core insight from the 90-day proximity study.

16-month backfill statistics (COMPLETED 2026-05-20 — proximity edge REVERSED, WATCH_FRAGILE):
    Source: `analysis/pattern-backtest-range-2025-01-02-to-2026-05-19.json`
    head_and_shoulders_top::near_named  N=88,  wins=44, losses=44, WR=50.0%  ← coin flip, NO EDGE
    head_and_shoulders_top::no_named    N=195, wins=108,losses=87, WR=55.4%  ← BETTER without filter
    Overall H&S top:                    N=285, WR=53.7%

    CRITICAL REVERSAL: the 90-day OOS proximity edge (N=26, WR=61.5%) was a false positive.
    At full 16-month scale (N=88), near_named collapses to 50.0% (coin flip). The no_named
    variant (N=195, WR=55.4%) outperforms WITH the proximity filter removed. Unlike
    momentum_acceleration (where level proximity consistently hurts impulse), H&S near/far
    divergence was noise within the 90-day window, not signal.

    The most honest conclusion: H&S has modest bearish edge (53.7% overall) regardless of
    named-level proximity. The proximity filter adds variance without improving expectancy.
    The no_named variant (larger N, higher WR) is the more promising research path.

Setup gates:
    1. `head_and_shoulders_detector(bars, lookback=30)` fires (bearish, neckline broken)
    2. Neckline within $0.50 of any ★★+ named level in `ctx.levels_active`
    3. Time: 09:40-13:30 ET (avoids gap-open noise and EOD theta burn)
    4. No strict VIX/ribbon filter initially — accumulate observations first
    5. Cooldown: 45 min (H&S can persist without re-firing same pattern)

Exit defaults (OP-21 conservative):
    - premium_stop_pct = -0.20 (standard bear stop; H&S neckline break is confirmed entry)
    - tp1 = +30% premium
    - runner = 1.5× entry
    - Chart stop: SPY recovers above neckline + $0.30 buffer (pattern failed)

OP-21 promotion gate (NO PROMOTION PATH for near_named variant — WATCH_FRAGILE):
    - Historical: ❌ FAILED — 16-month WR=50.0% (N=88). OP-21 economics gate requires positive
      expectancy over full backfill. 50% WR with equal stop/target = zero or negative expectancy
      after bid-ask spreads. Promotion to heartbeat.md blocked indefinitely under current evidence.
    - Walk-forward OOS: ❌ NOT RUN (blocked by historical gate failure above)
    - Real-fills: ❌ NOT RUN (blocked by historical gate failure above)
    - Live J observations: 0/3 ❌

WATCHER STATUS: WATCH_FRAGILE — accumulates live observations only.
  Watcher stays in runner.py to log real-world signals and test if live trading reveals
  any edge the backtest missed. However there is NO promotion path to heartbeat.md
  under current 16-month evidence.

  NEXT RESEARCH PATH: H&S::no_named variant (N=195, WR=55.4%) is more promising.
  A watcher without the proximity filter would fire ~2x more often and with better
  historical evidence. See T-2026-05-20-HS-NO-NAMED in queue.md.

DO NOT wire into production heartbeat.md. Historical gate FAILED (WR=50.0% over 16 months).
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from . import WatcherSignal
from ..filters import BarContext

try:
    from crypto.lib.chart_patterns import Bar, head_and_shoulders_detector, enrich_hit_with_proximity
    _PATTERNS_AVAILABLE = True
except ImportError:
    _PATTERNS_AVAILABLE = False


# ── Detection thresholds ─────────────────────────────────────────────────────

# Lookback window: H&S needs 30+ bars for the 3-peak structure
_WINDOW_BARS: int = 35   # extra margin above lookback=30

# Proximity gate: near a named level (within $0.50)
PROXIMITY_MAX_DISTANCE: float = 0.50

# Time window: avoid gap-open and EOD theta
ENTRY_TIME_START: dt.time = dt.time(9, 40)
ENTRY_TIME_END: dt.time = dt.time(13, 30)

# Cooldown: H&S forms over multiple bars, don't re-fire within 45 min
_COOLDOWN_MINUTES: int = 45


# ── Default exit knobs (OP-21 watch-only conservative) ───────────────────────

DEFAULT_QTY: int = 3
DEFAULT_PREMIUM_STOP_PCT: float = -0.20   # standard bear stop; neckline break = confirmed entry
DEFAULT_TP1_PREMIUM_PCT: float = 0.30
DEFAULT_RUNNER_TARGET_PCT: float = 1.5

# SPY-price levels for observation grading in runner.py
_CHART_STOP_ABOVE_NECKLINE: float = 0.30   # stop = neckline + $0.30 (reclaim = pattern failed)
_TP1_SPY_DROP: float = 0.70                # TP1 ≈ entry - $0.70 (half of median H&S move)
_RUNNER_SPY_DROP: float = 2.50             # runner ≈ entry - $2.50 (deep level target)


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
        if isinstance(ts, (int, float)):
            open_time = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=int(ts) * 300)
        else:
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


def detect_hs_near_named_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect HEAD_AND_SHOULDERS_NEAR_NAMED_LEVEL bearish setup.

    Returns WatcherSignal with direction="short" (buy puts) if all gates pass.
    Returns None if any gate fails.

    Confidence tiers:
      - "high":   H&S conf >= 0.65 AND neckline_break_pct > 0.05%
      - "medium": H&S conf >= 0.50 OR decent neckline break
      - "low":    base pattern only (conf=0.40-0.50)
    """
    global _last_signal_time

    if not _PATTERNS_AVAILABLE:
        return None

    # ── Gate 1: Time window (09:40-13:30 ET) ────────────────────────────────
    bar_time = ctx.timestamp_et.time()
    if bar_time < ENTRY_TIME_START or bar_time > ENTRY_TIME_END:
        return None

    # ── Gate 2: Cooldown — don't re-fire within 45 min ──────────────────────
    if _last_signal_time is not None:
        elapsed = (ctx.timestamp_et - _last_signal_time).total_seconds() / 60.0
        if elapsed < _COOLDOWN_MINUTES:
            return None

    # ── Gate 3: Named levels available (proximity check requires levels) ────
    if not ctx.levels_active:
        return None

    # ── Gate 4: H&S detector fires ──────────────────────────────────────────
    bars = _build_bars_from_context(ctx)
    if len(bars) < 30:
        return None

    hit = head_and_shoulders_detector(bars, lookback=30)
    if hit is None:
        return None

    # ── Gate 5: Neckline IS near a named level ($0.50 proximity check) ──────
    named_levels = [
        {"price": lvl, "name": f"level_{lvl:.2f}", "stars": 2}
        for lvl in ctx.levels_active
    ]
    enriched = enrich_hit_with_proximity(hit, named_levels, max_distance=PROXIMITY_MAX_DISTANCE)
    if enriched.notes.get("near_key_level") is not True:
        return None  # FAR_FROM_NAMED — no edge without level proximity (WR=48.5%)

    # ── Signal passes all gates ──────────────────────────────────────────────
    _last_signal_time = ctx.timestamp_et

    bar_close = float(ctx.bar["close"])
    neckline = float(enriched.notes.get("neckline", bar_close))
    head_high = float(enriched.notes.get("head_high", bar_close))
    nearest_level = enriched.notes.get("nearest_key_level_name", "unknown")
    level_dist = enriched.notes.get("nearest_key_level_distance", None)
    conf_score = float(enriched.confidence)
    neckline_break_pct = float(enriched.notes.get("neckline_break_pct", 0.0))

    # Stop: SPY recovers ABOVE neckline → pattern invalidated
    stop_price = neckline + _CHART_STOP_ABOVE_NECKLINE
    # Targets: bearish direction (price expected to fall from neckline break)
    tp1_price = bar_close - _TP1_SPY_DROP
    runner_price = bar_close - _RUNNER_SPY_DROP

    # Confidence tier
    if conf_score >= 0.65 and neckline_break_pct > 0.05:
        confidence = "high"
        conf_note = f"conf={conf_score:.2f} neckline_break={neckline_break_pct:.2f}%"
    elif conf_score >= 0.50 or neckline_break_pct > 0.03:
        confidence = "medium"
        conf_note = f"conf={conf_score:.2f} (moderate structure)"
    else:
        confidence = "low"
        conf_note = f"conf={conf_score:.2f} (base H&S, weak break)"

    prox_str = f"neckline_near_{nearest_level} dist=${level_dist:.2f}" if level_dist else f"neckline_near_level"

    return WatcherSignal(
        watcher_name="hs_near_named",
        setup_name="HEAD_AND_SHOULDERS_NEAR_NAMED_LEVEL",
        direction="short",
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=(
            f"H&S top near named level ({conf_note}). "
            f"Neckline={neckline:.2f} [{prox_str}], head={head_high:.2f}. "
            f"Stop={stop_price:.2f} (above neckline+$0.30). "
            f"OOS edge: 61.5% WR near named vs 48.5% far (N=26, 90-day)."
        ),
        triggers_fired=["hs_top_detector", "near_named_level", "time_window"],
        metadata={
            "oos_n": 26,
            "oos_wr_pct": 61.5,
            "oos_window": "2025-12-01 to 2026-03-31 (87 days)",
            "proximity_delta_pp": 13.0,
            "neckline": neckline,
            "head_high": head_high,
            "confidence_score": conf_score,
            "neckline_break_pct": neckline_break_pct,
            "nearest_level": nearest_level,
            "level_dist": level_dist,
        },
    )
