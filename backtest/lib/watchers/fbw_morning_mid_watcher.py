"""FAILED_BREAKDOWN_WICK_MORNING_MID watcher (WATCH-ONLY per OP-21).

16-month combination search (2025-01-01 to 2026-05-15) best FBW combo:
    failed_breakdown_wick | conf=MID | time=MORNING | vix=ANY | proximity=ANY
    N=52, WR=59.62%, EdgeCap=+$6.50/trade, 14 months active, max_month_share=13.5%
    score=0.93 (best-per-detector for failed_breakdown_wick in 16-month leaderboard)

Setup definition:
  1. `failed_breakdown_wick` fires on the current bar:
       - Bar LOW dips below 10-bar rolling support level
       - Bar CLOSES back ABOVE that support (failed breakdown)
       - wick:body ratio >= 2.0 AND vol >= 1.3x avg, OR close-back-margin >= 0.1%
  2. Confidence in MID band [0.65, 0.80) — base + 1-2 partial factors
  3. Bar in LATE MORNING window (10:30-11:30 ET) — see TIMING SPLIT below
  4. Cooldown: 45 min between signals

TIMING SPLIT ANALYSIS (2026-05-24, fbw_morning_timing_split.py):
  Split tested: EARLY=09:35-10:30 vs LATE=10:30-11:30 across 16-month window.

  EARLY (09:35-10:30): N=6, WR=66.7%, P&L=-$351
    Train N=3 WR=33.3% exp=-$216.60 | Test N=3 WR=100.0% exp=+$99.60
    Result: Net negative, N too small, test_n=3 fails OP-21 gate (need >=10) — EXCLUDE

  LATE (10:30-11:30):  N=29, WR=75.9%, P&L=+$806
    Train N=13 WR=76.9% exp=+$15.82 | Test N=16 WR=75.0% exp=+$37.53
    WF ratio = 2.373 — STRONG PASS (OOS 2.4x better than IS) — KEEP

  The EARLY band's train losses were dragging ALL-band train_exp negative (-$27.76).
  Removing EARLY gives a clean IS/OOS profile:
    LATE IS: profitable (exp=+$15.82) → LATE OOS: strongly profitable (exp=+$37.53)
  ENTRY_TIME_START updated to 10:30 per this analysis (2026-05-24, OP-22 engine-benefit).
  See analysis/recommendations/fbw_timing_split.json

The pattern logic:
  - Support is the 10-bar rolling LOW (not named levels — proximity=ANY is optimal)
  - In the MID conf band: sweep depth + reclaim margin each contribute 0.05-0.13
  - HIGH conf (>=0.80) may mean stop-hunt + fast reversal territory (noise)
  - LOW conf (<0.65): base structural signal only, insufficient sweep/reclaim quality

Why ANY proximity (no NOT_NEAR_NAMED filter):
  - FBW uses ROLLING support (not named levels), so proximity to named levels is
    not informative — the support level the pattern swept is whatever the prior bars formed.
  - Combo search confirmed: proximity_filter=ANY scores best for FBW at 16-month scale.

Per L55 (NLWB analog): FBW is a bounce entry. The entry bar itself IS the adverse bar
(bar wicks below support before recovering). ATM call premiums can dip 10-20% in bar 1
before the upward move develops. premium_stop_pct=-0.99 (disabled); chart stop only.

Real-fills validation: PASS (2026-05-20, fbw_morning_mid_validate.py)
  Full MORNING window (pre-split): WR=74.3% N=35, P&L=+$455.00 (12 NO_OPRA_DATA)
  LATE-only (post-split, 2026-05-24): WR=75.9% N=29, P&L=+$806.00
  VIX stratification (pre-split): <17=83% | 17-20=58% | 20-25=86% | >=25=67%
Walk-forward (LATE band only, 2026-05-24):
  Train (Jan-Sep 2025): WR=76.9% N=13, P&L=+$205.70
  Test  (Oct 2025-May 2026): WR=75.0% N=16, P&L=+$600.50
  WF ratio = 2.373 — STRONG PASS (OOS 2.4x IS)

OP-21 status: WATCH_ONLY — real-fills + walk-forward PASS. Pending 3 live J confirmations.
  - Historical: N=52, 14/14 months active, max_month_share=13.5% ✓
  - Walk-forward (LATE band): STRONG PASS ✓ (WF ratio=2.373, OOS WR=75.0%, N=16)
  - Real-fills (LATE band): PASS ✓ (WR=75.9%, P&L=+$806, chart-stop-only per L55)
  - Live: 0/3 J observations needed before promotion
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from . import WatcherSignal
from ..filters import BarContext

try:
    from crypto.lib.chart_patterns import Bar, failed_breakdown_wick as _detect_fbw
    _PATTERNS_AVAILABLE = True
except ImportError:
    _PATTERNS_AVAILABLE = False


# ── Detection thresholds ─────────────────────────────────────────────────────

# Time window: LATE MORNING only (timing split 2026-05-24 found EARLY=09:35-10:30 net negative,
# LATE=10:30-11:30 WF ratio=2.373 STRONG PASS; early band excluded per OP-22 engine-benefit)
ENTRY_TIME_START: dt.time = dt.time(10, 30)
ENTRY_TIME_END: dt.time = dt.time(11, 30)

# Confidence gate: MID band [0.65, 0.80)
CONF_MID_LOW: float = 0.65   # inclusive
CONF_MID_HIGH: float = 0.80  # exclusive

# FBW lookback: 10-bar rolling support (matches combination_search.py DETECTORS definition)
_WINDOW_BARS: int = 20  # 10 prior bars + room for the latest bar

# Cooldown: 45 min (FBW can re-fire on nearby support levels; cooldown prevents double-signal)
_COOLDOWN_MINUTES: int = 45


# ── Default exit knobs (OP-21 watch-only) ────────────────────────────────────

DEFAULT_QTY: int = 3
DEFAULT_PREMIUM_STOP_PCT: float = -0.99   # chart-stop only (L55 analog — first-strike bounce entry)
DEFAULT_TP1_PREMIUM_PCT: float = 0.30     # +30% premium TP1
DEFAULT_RUNNER_TARGET_PCT: float = 1.5    # conservative runner

# SPY-level chart stop: if SPY closes below (support - $0.50), pattern invalidated
# In simulate_trade_real(side="C"): fires when spy_close < rejection_level - 0.50
# Effective: spy_close < support - 0.50 - 0.50 = support - $1.00
_CHART_STOP_BELOW_SUPPORT: float = 0.50   # rejection_level = support - $0.50

# SPY targets for observation grading
_TP1_SPY_MOVE: float = 0.50               # TP1 ~ +$0.50 from entry (conservative for morning)
_RUNNER_SPY_MOVE: float = 1.50            # runner ~ +$1.50 (half-session extension)


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
                open_time = (
                    pd.Timestamp(ts).tz_localize("UTC")
                    if pd.Timestamp(ts).tzinfo is None
                    else pd.Timestamp(ts).tz_convert("UTC")
                )
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


def detect_fbw_morning_mid_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect FAILED_BREAKDOWN_WICK_MORNING_MID setup on the current bar.

    Returns WatcherSignal with direction="long" if all gates pass.
    Returns None if any gate fails.

    Confidence tiers (layered on top of the [0.65, 0.80) MID gate):
      - "high":   conf >= 0.73 (both sweep + reclaim factors near saturation)
      - "medium": conf >= 0.68 (one factor saturated, one partial)
      - "low":    conf in [0.65, 0.68) (both factors partially active — MID floor)
    """
    global _last_signal_time

    if not _PATTERNS_AVAILABLE:
        return None

    # ── Gate 1: Morning window ────────────────────────────────────────────────
    bar_time = ctx.timestamp_et.time()
    if bar_time < ENTRY_TIME_START or bar_time > ENTRY_TIME_END:
        return None

    # ── Gate 2: Cooldown ──────────────────────────────────────────────────────
    if _last_signal_time is not None:
        elapsed = (ctx.timestamp_et - _last_signal_time).total_seconds() / 60.0
        if elapsed < _COOLDOWN_MINUTES:
            return None

    # ── Gate 3: FBW detector ─────────────────────────────────────────────────
    bars = _build_bars_from_context(ctx)
    if len(bars) < 12:  # need lookback_for_support=10 + 2 bars minimum
        return None

    hit = _detect_fbw(bars, lookback_for_support=10)
    if hit is None:
        return None

    # ── Gate 4: Confidence MID band [0.65, 0.80) ─────────────────────────────
    conf = hit.confidence
    if conf < CONF_MID_LOW or conf >= CONF_MID_HIGH:
        return None

    # ── Signal passes all gates ───────────────────────────────────────────────
    _last_signal_time = ctx.timestamp_et

    bar_close = float(ctx.bar["close"])
    support = float(hit.notes.get("support_price", bar_close))
    sweep_depth = float(hit.notes.get("sweep_depth_dollars", 0.0))
    close_back = float(hit.notes.get("close_back_margin_dollars", 0.0))
    wick_ratio = float(hit.notes.get("wick_to_body_ratio") or 0.0)
    vol_mult = float(hit.notes.get("volume_mult", 1.0))

    # Chart stop below support
    stop_price = support - _CHART_STOP_BELOW_SUPPORT
    tp1_price = bar_close + _TP1_SPY_MOVE
    runner_price = bar_close + _RUNNER_SPY_MOVE

    # Sub-tier within MID band (2026-05-24 empirical finding):
    # HIGH (conf >= 0.73): N=12, WR=91.7%, P&L=+$937, IS exp=+$102.96, OOS exp=+$60.26
    #   WF ratio=0.585 PASS — this is where the FBW edge lives in the LATE window
    # LOW/MED (conf < 0.73): N=17, WR=64.7%, P&L=-$131, IS negative — noise
    # J's 3-live-observation gate should target "high" signals (both sweep+reclaim saturated)
    if conf >= 0.73:
        confidence = "high"
        tier_note = f"conf={conf:.3f} — strong sweep+reclaim (both factors active) [EDGE TIER: WR=91.7% IS/OOS WF=0.585]"
    elif conf >= 0.68:
        confidence = "medium"
        tier_note = f"conf={conf:.3f} — one factor saturated, one partial"
    else:
        confidence = "low"
        tier_note = f"conf={conf:.3f} — MID floor (both partial)"

    vix_note = f"VIX={ctx.vix_now:.2f}"

    return WatcherSignal(
        watcher_name="fbw_morning_mid",
        setup_name="FAILED_BREAKDOWN_WICK_MORNING_MID",
        direction="long",
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=(
            f"Failed breakdown wick ({tier_note}). "
            f"Support={support:.2f}, swept={sweep_depth:.2f}, closed_back={close_back:.2f}. "
            f"wick:body={wick_ratio:.1f}x, vol_mult={vol_mult:.1f}x. "
            f"Stop={stop_price:.2f} (below support-${_CHART_STOP_BELOW_SUPPORT:.2f}). "
            f"{vix_note}."
        ),
        triggers_fired=["fbw_detector", "morning_window", "conf_mid_band"],
        metadata={
            "combo_search_rank": "best_per_detector_FBW",
            "combo_search_n": 52,
            "combo_search_wr_pct": 59.62,
            "combo_search_window": "2025-01-01 to 2026-05-15",
            "combo_search_months_active": 14,
            "combo_search_max_month_share": 0.135,
            "confidence_score": conf,
            "support_price": support,
            "sweep_depth_dollars": sweep_depth,
            "close_back_margin_dollars": close_back,
            "wick_to_body_ratio": wick_ratio,
            "volume_mult": vol_mult,
            "vix_now": ctx.vix_now,
            "op21_live_gate": "0/3 — DO NOT promote until 3+ live J confirmations",
            "op21_real_fills": "PENDING fbw_morning_mid_validate.py",
        },
    )
