"""MOMENTUM_ACCELERATION_HIGHVOL watcher (WATCH-ONLY per OP-21).

16-month combination search (2025-01-01 to 2026-05-15) Rank #1 by OP-16 score:
    momentum_acceleration | ALIGNED | vix=HIGH_VOL
    N=47, WR=59.6%, EdgeCap=+$24.46, Score=+7.17

The highest score result in the 16-month leaderboard. Rank #2 adds NOT_NEAR_NAMED:
    momentum_acceleration | ALIGNED | NOT_NEAR_NAMED | vix=HIGH_VOL
    N=42, WR=59.5%, Score=+6.37

Setup definition:
  1. `momentum_acceleration` detector fires on the current bar's sliding window
  2. Regime is ALIGNED (ribbon stack in same direction as the hit's bias)
  3. VIX >= 20 at entry (HIGH_VOL regime) — elevated vol = directional urgency, not noise
  4. NOT required: time window (any time 09:35-15:55 ET)
  5. Cooldown: 45 min between signals (momentum_acceleration can cluster in trending days)

Why HIGH_VOL + ALIGNED is the sweet spot:
  - Momentum_acceleration detects a bar where SPY is moving fast with expanding volume
  - In HIGH_VOL (VIX>=20), these fast bars are more often genuine trend impulses
    (vs LOW_VOL where they're more often noise spikes that reverse quickly)
  - ALIGNED regime means the ribbon already agrees with the direction — momentum
    is WITH the trend, not counter-trend. Reduces the "impulse then reversal" risk.
  - The 90-day OOS top combo (NOT_NEAR_NAMED+AFTERNOON, N=21, WR=66.7%) was a
    Dec-Mar 2026 period artifact. The 16-month signal (ALIGNED+HIGH_VOL) is more robust.

Why NOT_NEAR_NAMED is secondary:
  - Rank #1 (ALIGNED+HIGH_VOL, N=47) and Rank #2 (ALIGNED+NOT_NEAR_NAMED+HIGH_VOL, N=42)
    have nearly identical WR (59.6% vs 59.5%). The proximity filter drops N by 5 at the cost
    of negligible WR improvement. Default: don't apply the proximity filter.

Walk-forward validation result (2026-05-20):
  - Train (2025-01-01 to 2025-09-30): N=11, WR=54.55%
  - Test  (2025-10-01 to 2026-05-15): N=36, WR=61.11%  <- +6.6pp improvement
  - VERDICT: IMPROVED -- ALIGNED+HIGH_VOL thesis strengthens OOS (SPY-price proxy)
  - NOTE: Walk-forward used SPY-price direction proxy, not real option fills.

Real-fills validation result (2026-05-20):
  - N=47 signals, 35 completed (12 no OPRA data), scan_proxy_WR=59.6%
  - Real WR=42.9% (15W/20L), delta=-16.7pp, total P&L=-$733 (avg -$21/trade)
  - Root cause: VIX[20-25) = 69% of signals with WR=37.5% (dominant drag)
    VIX[25+) shows WR=50%+ but N too small to cite as edge (N=11)
  - No chart stop width ($0.40-$1.00 tested) achieves positive P&L
  - STATUS: WATCH_FRAGILE -- real-fills gate NOT met; negative expectancy in VIX[20-25)
  - Full results: analysis/recommendations/momentum-accel-highvol-real-fills.json

VIX=25 floor investigation result (2026-05-20):
  - Raised VIX_HIGH_VOL_FLOOR from 20.0 to 25.0 in isolation test
  - N=15 signals found, 11 completed (4 no OPRA data)
  - Real WR=54.5% (6W/5L), total P&L=+$452 (avg +$41/trade) — POSITIVE_EXPECTANCY
  - Walk-forward TRAIN (Jan-Sep 2025): N=5, WR=60.0%, P&L=+$217
  - Walk-forward TEST  (Jan-May 2026): N=6, WR=50.0%, P&L=+$235
  - WF verdict: MARGINAL (OOS WR>=50%, positive P&L, but thin margin)
  - N-gate FAILURE: N_completed=11 (16 months) — too thin for reliable edge estimation
    Chef inbox promotion gate requires N_test>=15 in OOS window; actual N_test=6.
  - Status: PROMISING but INSUFFICIENT_N. Monitor live VIX>=25 signals separately.
  - Full results: analysis/recommendations/momentum-accel-vix25-validate.json

Direction split at VIX>=25 (computed 2026-05-20 from real-fills results):
  - Long  (BULL ribbon, calls): N=4,  WR=75.0%,  P&L=+$887  (+$222/trade) ← STRONG
  - Short (BEAR ribbon, puts):  N=7,  WR=42.9%,  P&L=-$435  (-$62/trade)  ← DRAG
  Key insight: the BULL ribbon direction at VIX>=25 drives ALL the positive P&L.
  The BEAR ribbon puts drag the combined number back to marginal. Possible future path:
  VIX>=25 + direction=long only — but N=4 is too thin (need N>=10+ for confirmation).
  DO NOT narrow to long-only based on 4 trades. Accumulate live observations first.

OP-21 promotion gate:
  - Historical: N=47 wins (3+ gate MET) ✓
  - Walk-forward: IMPROVED +6.6pp (train N=11 WR=54.55% -> test N=36 WR=61.11%) ✓
    (SPY-price proxy — see real-fills note above)
  - Real-fills: DEGRADED -16.7pp (WR=42.9%, negative expectancy) ✗
    Root: VIX[20-25) drag. VIX=25 floor flips to positive (+$452, WR=54.5%) but N too thin.
    Requires N>=15 real-fills at VIX>=25 before VIX_FLOOR promotion is justified.
  - Live J observations: 0/3 needed
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from . import WatcherSignal
from ..filters import BarContext

try:
    from crypto.lib.chart_patterns import Bar, momentum_acceleration
    _PATTERNS_AVAILABLE = True
except ImportError:
    _PATTERNS_AVAILABLE = False


# ── Detection thresholds ─────────────────────────────────────────────────────

# VIX gate: HIGH_VOL regime (VIX>=20 in combo_search)
VIX_HIGH_VOL_FLOOR: float = 20.0

# Regime gate: ribbon direction must match the hit bias
ALIGNED_STACKS_BULL: tuple[str, ...] = ("BULL",)
ALIGNED_STACKS_BEAR: tuple[str, ...] = ("BEAR",)

# Sliding window for momentum_acceleration detector
_WINDOW_BARS: int = 20  # momentum patterns need fewer bars than double bottom

# Cooldown: 45 min between signals (momentum can cluster in trending conditions)
_COOLDOWN_MINUTES: int = 45


# ── Default exit knobs ────────────────────────────────────────────────────────

DEFAULT_QTY: int = 3
DEFAULT_PREMIUM_STOP_PCT: float = -0.99   # chart stop (same reasoning as L51/L55 —
                                          # initial bar in high-vol can wick significantly
                                          # before the directional move develops)
DEFAULT_TP1_PREMIUM_PCT: float = 0.30
DEFAULT_RUNNER_TARGET_PCT: float = 2.0    # more aggressive runner: high-vol moves extend

_CHART_STOP_OFFSET: float = 0.40          # stop = entry - $0.40 (wider for high-vol)
_TP1_SPY_MOVE: float = 0.80
_RUNNER_SPY_MOVE: float = 2.50


# ── Module-level state (cooldown tracking) ────────────────────────────────────

_last_signal_time: Optional[dt.datetime] = None


def _build_bars_from_context(ctx: BarContext, n: int = _WINDOW_BARS) -> list[Bar]:
    """Convert the last n rows of prior_bars into Bar objects."""
    if not _PATTERNS_AVAILABLE:
        return []
    import pandas as pd

    df = ctx.prior_bars.tail(n).copy()
    bars = []
    for ts, row in df.iterrows():
        if isinstance(ts, (int, float)):
            open_time = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=int(ts) * 300)
        else:
            try:
                pt = pd.Timestamp(ts)
                open_time = (pt.tz_localize("UTC") if pt.tzinfo is None else pt.tz_convert("UTC")).to_pydatetime()
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


def detect_momentum_accel_highvol_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect MOMENTUM_ACCELERATION_HIGHVOL setup on the current bar.

    Returns WatcherSignal with direction matching the detector bias if all gates pass.
    Returns None if any gate fails.

    Confidence tiers:
      - "high":   VIX >= 25 AND ribbon spread >= 50c (strong directional conviction)
      - "medium": VIX 20-25 AND aligned ribbon
      - "low":    VIX barely >= 20 (barely over threshold — lower historical WR)
    """
    global _last_signal_time

    if not _PATTERNS_AVAILABLE:
        return None

    # ── Gate 1: VIX HIGH_VOL (>=20) ──────────────────────────────────────────
    if ctx.vix_now < VIX_HIGH_VOL_FLOOR:
        return None

    # ── Gate 2: Cooldown ─────────────────────────────────────────────────────
    if _last_signal_time is not None:
        elapsed = (ctx.timestamp_et - _last_signal_time).total_seconds() / 60.0
        if elapsed < _COOLDOWN_MINUTES:
            return None

    # ── Gate 3: Run momentum_acceleration on sliding window ──────────────────
    bars = _build_bars_from_context(ctx)
    if len(bars) < 5:
        return None

    hit = momentum_acceleration(bars)
    if hit is None:
        return None

    # ── Gate 4: Regime ALIGNED — ribbon direction matches bias ───────────────
    if ctx.ribbon_now is None:
        return None

    ribbon_stack = ctx.ribbon_now.stack
    bias = hit.bias  # "bullish" | "bearish"

    if bias == "bullish" and ribbon_stack not in ALIGNED_STACKS_BULL:
        return None
    if bias == "bearish" and ribbon_stack not in ALIGNED_STACKS_BEAR:
        return None

    direction = "long" if bias == "bullish" else "short"

    # ── Signal passes all gates ───────────────────────────────────────────────
    _last_signal_time = ctx.timestamp_et

    bar_close = float(ctx.bar["close"])
    spread_cents = ctx.ribbon_now.spread_cents

    # Confidence tier
    if ctx.vix_now >= 25.0 and spread_cents >= 50.0:
        confidence = "high"
        conf_note = f"VIX={ctx.vix_now:.1f} elevated+strong ribbon spread={spread_cents:.0f}c"
    elif ctx.vix_now >= 20.0:
        confidence = "medium"
        conf_note = f"VIX={ctx.vix_now:.1f} high-vol regime, ribbon={ribbon_stack} spread={spread_cents:.0f}c"
    else:
        confidence = "low"
        conf_note = f"VIX={ctx.vix_now:.1f} barely above HIGH_VOL threshold"

    # Stop and targets
    if direction == "long":
        stop_price = bar_close - _CHART_STOP_OFFSET
        tp1_price = bar_close + _TP1_SPY_MOVE
        runner_price = bar_close + _RUNNER_SPY_MOVE
    else:
        stop_price = bar_close + _CHART_STOP_OFFSET
        tp1_price = bar_close - _TP1_SPY_MOVE
        runner_price = bar_close - _RUNNER_SPY_MOVE

    return WatcherSignal(
        watcher_name="momentum_accel_highvol",
        setup_name="MOMENTUM_ACCELERATION_HIGHVOL",
        direction=direction,
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=(
            f"Momentum acceleration {bias} with aligned {ribbon_stack} ribbon. "
            f"{conf_note}. Chart stop={stop_price:.2f}."
        ),
        triggers_fired=["momentum_acceleration_detector", "aligned_regime", "high_vol_vix"],
        metadata={
            "combo_search_rank": 1,
            "combo_search_n": 47,
            "combo_search_wr_pct": 59.6,
            "combo_search_window": "2025-01-01 to 2026-05-15",
            "ribbon_stack": ribbon_stack,
            "ribbon_spread_cents": spread_cents,
            "vix_now": ctx.vix_now,
            "op21_live_gate": "0/3 — DO NOT promote until 3+ live J confirmations",
        },
    )
