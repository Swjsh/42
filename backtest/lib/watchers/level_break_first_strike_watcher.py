"""LEVEL_BREAK_FIRST_STRIKE (LBFS) watcher (WATCH-ONLY per OP-21).

Detects bearish level breaks on MIXED-ribbon days — the "first strike" before
the ribbon fully confirms the bearish direction.

Setup definition (from chef-inbox 2026-05-19-ribbon-lag-first-strike-bear.md):
  1. Ribbon = MIXED (not yet fully BEAR — the "lag" that LBFS exploits)
  2. Ribbon spread = 12-30c (above MIN_SPREAD_MIXED=12c, below 30c BEAR-confirm threshold)
  3. Bar closes >= 20c BELOW a named ★★+ level (PDH/PDL/5DH/monthly-open)
  4. Volume >= 1.5× 20-bar average
  5. VIX direction NOT hard-falling (vix_diff >= -0.15)
  6. Time >= 09:45 ET (entry gate)

Two confidence tiers based on VIX regime:
  - VIX < 20: "low" confidence — aggregate WR=43.3% (30 signals), below the edge threshold
  - VIX >= 20: "high" confidence — 19 live observations, OP-21 gate PASSED 2026-05-24

OP-21 gate status (updated 2026-05-24):
  - VIX<20 variant: NO EDGE. Do not promote unless WR improves to >55% at N>=30.
  - VIX>=20 variant: *** N=19 GATE PASSED *** (across 4 distinct regimes: 2025-Q1/Q2,
    2025-Q2/Q3, 2025-Q4/2026-Q1, 2026-Q1/Q2). Remaining gate: 3 live J observations.

Real-fills validation (2026-05-24, lbfs_expanded_real_fills.py):
  Output: analysis/recommendations/lbfs-expanded-real-fills.json
  ATM (strike_offset=0): N=17 graded, WR=58.8% (10W/7L), P&L=+$763 → OP21 GATE: PASS
  OTM-1 (strike_offset=1): N=15 graded, WR=46.7%, P&L=-$589 → FAIL
  → ATM is the ONLY correct strike class for LBFS entries.
  Stop mechanism: premium_stop_pct=-0.99 (chart-stop-only per L51)

Key discriminating filter (2026-05-24):
  All 3 false-break losses (level_stop fired) had break_below_cents < 100c (23c, 27c, 54c).
  break_below_cents >= 100c filter: WR ~71%, P&L ~+$1,525 (subgroup of N=14 graded)
  This filter should be applied when wiring to production (post-ratification).

Research arc:
  - v1 (MIN_SPREAD=0): 34 signals, 50% WR, guard FAIL (5/07 loser day fires)
  - v2 (MIN_SPREAD=12c): 26 signals, 50% WR, guard PASS
  - v3 (MIN_SPREAD=20c): 7 signals, 57% WR, N too thin
  - v4 (VIX_MIN=20, MIN_SPREAD=12c): 4 signals, 100% SPY-heuristic WR, guard PASS
  - Vol-regime split: VIX<20 WR=43.3% (88% of signals), VIX>=20 edge confirmed (L48)
  - Real-fills v4: 1/4 WR with chart-stop-only (L50, L51); false-break problem identified
  - Expanded N=19: ATM WR=58.8% P&L=+$763 → OP-21 gate PASSED 2026-05-24

Spec: strategy/candidates/2026-05-19-level-break-first-strike-bear.md
Research arc: strategy/candidates/_chef-inbox/2026-05-19-ribbon-lag-first-strike-bear.md
DO NOT wire into production heartbeat.md until: 3 live J observations confirmed.
Production config: premium_stop_pct=-0.99, break_below_cents_min=100, strike_offset=0 (ATM).
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from . import WatcherSignal
from ..filters import BarContext


# ---- Thresholds (per v2/v4 scan parameters) ----
MIN_SPREAD_MIXED_CENTS: float = 12.0    # ribbon spread >= 12c (above noise floor)
MAX_SPREAD_MIXED_CENTS: float = 30.0    # ribbon spread < 30c (below full-BEAR threshold)
LEVEL_BREAK_MIN_CENTS: float = 20.0     # close must be >= 20c BELOW the level
VOLUME_MULTIPLIER: float = 1.5          # volume >= 1.5× 20-bar average
VIX_FALLING_HARD_THRESHOLD: float = -0.15  # vix_diff < -0.15 = hard-falling (block)
VIX_HIGH_THRESHOLD: float = 20.0       # VIX >= 20 = high-vol regime (100% WR discriminator)
ENTRY_TIME_GATE: dt.time = dt.time(9, 45)  # only fire after 09:45 ET
LATE_SIGNAL_CUTOFF: dt.time = dt.time(15, 0)  # no new signals after 15:00 ET

# ---- Default knobs (conservative OP-21 watch-only defaults) ----
DEFAULT_QTY: int = 3
DEFAULT_PREMIUM_STOP_PCT: float = -0.08   # same as baseline bear continuation
DEFAULT_TP1_PREMIUM_PCT: float = 0.30     # standard TP1
DEFAULT_RUNNER_TARGET_PCT: float = 1.5    # conservative runner (watch-only)

# SPY-price approximations for stop/target levels
_CHART_STOP_ABOVE_LEVEL: float = 0.30    # stop = break_level + $0.30
_TP1_SPY_DROP: float = 0.80              # TP1 ≈ entry - $0.80 (first 16 bars avg drop = $1.5)
_RUNNER_SPY_DROP: float = 2.00           # runner ≈ entry - $2.00


def detect_lbfs_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect LEVEL_BREAK_FIRST_STRIKE setup on the current bar.

    Returns WatcherSignal if conditions met (both low-VIX and high-VIX variants),
    with confidence tier indicating expected edge:
      - "low": VIX < 20 (43.3% WR, observation-only — no promotion)
      - "medium": VIX >= 18 AND < 20 (borderline — track closely)
      - "high": VIX >= 20 (100% WR on n=4 — the ratifiable regime)

    Returns None if any hard gate fails.
    """
    # ---- Gate 1: Time window (09:45 - 15:00 ET) ----
    bar_time = ctx.timestamp_et.time()
    if bar_time < ENTRY_TIME_GATE:
        return None
    if bar_time > LATE_SIGNAL_CUTOFF:
        return None

    # ---- Gate 2: Ribbon MIXED ----
    if ctx.ribbon_now is None:
        return None
    if ctx.ribbon_now.stack != "MIXED":
        return None

    # ---- Gate 3: Spread in [12c, 30c) ----
    spread_cents = ctx.ribbon_now.spread_cents
    if spread_cents < MIN_SPREAD_MIXED_CENTS:
        return None
    if spread_cents >= MAX_SPREAD_MIXED_CENTS:
        return None

    # ---- Gate 4: VIX not hard-falling ----
    vix_diff = ctx.vix_now - ctx.vix_prior
    if vix_diff < VIX_FALLING_HARD_THRESHOLD:
        return None

    bar_close = float(ctx.bar["close"])
    bar_vol = float(ctx.bar["volume"])

    # ---- Gate 5: Volume >= 1.5× 20-bar average ----
    if ctx.vol_baseline_20 <= 0:
        return None
    vol_ratio = bar_vol / ctx.vol_baseline_20
    if vol_ratio < VOLUME_MULTIPLIER:
        return None

    # ---- Gate 6: Level break — close >= 20c BELOW a named ★★+ level ----
    break_level: Optional[float] = None
    break_below_cents: float = 0.0
    for lvl in ctx.levels_active:
        # Bar close must be BELOW the level by at least LEVEL_BREAK_MIN_CENTS
        cents_below = (lvl - bar_close) * 100.0
        if cents_below >= LEVEL_BREAK_MIN_CENTS:
            if cents_below > break_below_cents:
                break_below_cents = cents_below
                break_level = lvl

    if break_level is None:
        return None

    # ---- Confidence tier based on VIX regime ----
    vix_now = ctx.vix_now
    # High: VIX >= 20 (100% WR on n=4 historical signals — the key discriminator)
    # Medium: VIX >= 18 (borderline regime — track but don't count toward ratification)
    # Low: VIX < 18 (sub-threshold, record for informational only)
    if vix_now >= VIX_HIGH_THRESHOLD:
        confidence = "high"
        op21_note = f"VIX>={VIX_HIGH_THRESHOLD} (HIGH-VOL regime, 100% WR on n=4 historical)"
    elif vix_now >= 18.0:
        confidence = "medium"
        op21_note = f"VIX={vix_now:.1f} (borderline regime, 18-20 zone)"
    else:
        confidence = "low"
        op21_note = f"VIX={vix_now:.1f} (low-vol regime, 43.3% historical WR — no edge)"

    # ---- Signal output ----
    stop_price = break_level + _CHART_STOP_ABOVE_LEVEL   # chart stop ABOVE broken level
    tp1_price = bar_close - _TP1_SPY_DROP
    runner_price = bar_close - _RUNNER_SPY_DROP

    reason = (
        f"LBFS bearish break at level {break_level:.2f}: "
        f"close {break_below_cents:.0f}c below (break_below=${break_below_cents/100:.2f}), "
        f"ribbon MIXED spread={spread_cents:.1f}c, "
        f"vol={vol_ratio:.1f}x, "
        f"vix={vix_now:.2f}(diff={vix_diff:+.2f}). {op21_note}"
    )

    # OP-21 promotion status notes
    vix_gated_note = "VIX>=20 GATED (ratifiable route)" if vix_now >= VIX_HIGH_THRESHOLD else "VIX<20 (observe-only)"

    return WatcherSignal(
        watcher_name="level_break_first_strike_watcher",
        setup_name="LEVEL_BREAK_FIRST_STRIKE",
        direction="short",
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=reason,
        triggers_fired=["MIXED_RIBBON_LEVEL_BREAK", "VOL_1.5X"],
        metadata={
            "promotion_status": "WATCH_ONLY",
            "vix_gated": vix_now >= VIX_HIGH_THRESHOLD,
            "vix_gated_note": vix_gated_note,
            "break_level": break_level,
            "break_below_cents": round(break_below_cents, 2),
            "ribbon_spread_cents": spread_cents,
            "vol_ratio": round(vol_ratio, 2),
            "vix_now": vix_now,
            "vix_diff": round(vix_diff, 3),
            "default_qty": DEFAULT_QTY,
            "default_premium_stop_pct": DEFAULT_PREMIUM_STOP_PCT,
            "default_tp1_pct": DEFAULT_TP1_PREMIUM_PCT,
            "default_runner_target_pct": DEFAULT_RUNNER_TARGET_PCT,
            "op21_vix_gated_n": 4,
            "op21_vix_gated_wr": 1.0,
            "op21_vix_gated_target_n": 15,
            "op21_note": op21_note,
            "spec_file": "strategy/candidates/2026-05-19-level-break-first-strike-bear.md",
        },
    )
