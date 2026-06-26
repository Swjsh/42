"""DOUBLE_TOP watcher (WATCH-ONLY per OP-21) — the bearish mirror of the two
double-bottom watchers.

The `crypto.lib.chart_patterns.double_top_detector` (bearish "M": two highs near
the same price + a trough between + a CLOSE below the trough) has full v22 gym
coverage but had NO live watcher — the one mirror gap called out in
markdown/research/TA-CAPABILITY-AND-GAPS-2026-06-20.md §2 ("Double top — PARTIAL:
detector + tests exist, but no live watcher"). This module closes that gap as an
OBSERVE-ONLY stream.

WHY THIS HAS NO EDGE-DERIVED GATES (deliberate, unlike double_bottom_base_quiet):
  The double_bottom_base_quiet watcher carries a conf=LOW ceiling + VIX<20 +
  NOT_NEAR_NAMED gate because each was earned by a 16-month cross-validated combo
  search (Rank #3, N=168). NO equivalent validated combo search exists for the
  double top on OUR data. Worse, the two things we DO know point opposite ways:
    - Proximity HURTS double tops: chart_patterns.py records 20% WR near named
      resistance (N=5) — "named levels attract breakout buyers who fade the
      pattern." So a NOT_NEAR / near-named filter is NOT justified either way yet.
    - TA-PATTERN-REFERENCE.md §B "Double Top" (line ~119): the textbook double top
      is a WEEKS-long structure; Bulkowski's 25% break-even failure rate is a
      DAILY/WEEKLY stat that "do[es] not transfer to 5m/15m." The intraday double
      top "IS a usable short trigger — but it is really an A.4 CHoCH/level-rejection
      in disguise; do not attach Bulkowski's 25% figure to it."
  => This watcher exists precisely to gather an UNBIASED SPY 5m double-top sample
     so that caveat can be RESOLVED with our own real-fills before any live trigger.
     Adding unvalidated filters now would bias the very sample we need. So the only
     gates are structural housekeeping: RTH window + a cooldown + "the detector
     fired." Confidence is logged, never gated on.

OP-21 promotion gate (NONE of the quantitative gates met yet — this is a NEW stream):
  - Historical: PENDING — re-measure double-top failure rate on our SPY 5m sample
    (the daily/weekly Bulkowski 25% does NOT transfer; see caveat above).
  - Walk-forward OOS: PENDING.
  - Real-fills: PENDING.
  - Live J observations: 0/3.
  DO NOT wire any live trigger until all four pass + Rule 9 ratification.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from . import WatcherSignal
from ..filters import BarContext

try:
    from crypto.lib.chart_patterns import Bar, double_top_detector
    _PATTERNS_AVAILABLE = True
except ImportError:
    _PATTERNS_AVAILABLE = False


# ── Detection thresholds ──────────────────────────────────────────────────────

# Sliding window for double_top_detector (default lookback=20); 30 gives margin.
_WINDOW_BARS: int = 30

# RTH window — fire 09:35-15:55 ET (mirror double_bottom_base_quiet; no morning filter).
_RTH_START: dt.time = dt.time(9, 35)
_RTH_END: dt.time = dt.time(15, 55)

# Cooldown: don't re-fire within 30 min of the last signal (mirror db_base_quiet).
_COOLDOWN_MINUTES: int = 30


# ── Default exit knobs (OP-21 watch-only conservative; bearish mirror) ─────────

DEFAULT_QTY: int = 3
DEFAULT_PREMIUM_STOP_PCT: float = -0.99   # chart-stop ONLY (L51/L55 — neckline-break
                                          # entries have violent initial bounces that
                                          # push put premiums down before the move)
DEFAULT_TP1_PREMIUM_PCT: float = 0.30
DEFAULT_RUNNER_TARGET_PCT: float = 1.5

# SPY-level targets (for observation grading in runner.grade_observation).
_CHART_STOP_ABOVE_NECKLINE: float = 0.30   # stop = trough(neckline) + $0.30 (reclaim = invalidation)
_TP1_SPY_DROP: float = 0.70                # TP1 ~ entry - $0.70
_RUNNER_SPY_DROP: float = 2.00             # runner ~ entry - $2.00


# ── Module-level state (cooldown tracking) ────────────────────────────────────

_last_signal_time: Optional[dt.datetime] = None


def _build_bars_from_context(ctx: BarContext) -> list[Bar]:
    """Convert the last _WINDOW_BARS rows of prior_bars into Bar objects.

    prior_bars INCLUDES the trigger bar as its last row (filters.BarContext), so
    window[-1] is the current closed bar — exactly what double_top_detector needs
    for its close-below-neckline confirmation.
    """
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


def _vix_bucket(vix: float) -> str:
    if vix < 15:
        return "<15"
    if vix < 20:
        return "15-20"
    if vix < 25:
        return "20-25"
    return ">=25"


def detect_double_top_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Detect a DOUBLE_TOP (bearish M) on the current bar — OBSERVE-ONLY.

    Returns a WatcherSignal with direction="short" (buy puts) when the M completes
    (close below the trough/neckline) inside RTH and the cooldown has elapsed.
    Returns None otherwise. NO edge-derived gates by design (see module docstring):
    the confidence tier is reported, never used to suppress.
    """
    global _last_signal_time

    if not _PATTERNS_AVAILABLE:
        return None

    # ── Gate 1: RTH window (09:35-15:55 ET) ──────────────────────────────────
    bar_time = ctx.timestamp_et.time()
    if bar_time < _RTH_START or bar_time > _RTH_END:
        return None

    # ── Gate 2: Cooldown — don't re-fire within 30 min ───────────────────────
    if _last_signal_time is not None:
        elapsed = (ctx.timestamp_et - _last_signal_time).total_seconds() / 60.0
        if elapsed < _COOLDOWN_MINUTES:
            return None

    # ── Gate 3: double_top_detector fires (M complete + neckline broken) ──────
    bars = _build_bars_from_context(ctx)
    if len(bars) < 10:
        return None

    hit = double_top_detector(bars)
    if hit is None:
        return None

    # ── Signal passes all gates ──────────────────────────────────────────────
    _last_signal_time = ctx.timestamp_et

    bar_close = float(ctx.bar["close"])
    neckline = float(hit.notes.get("neckline", bar_close))   # the trough between the two highs
    upper_high = float(hit.key_price)
    conf_score = float(hit.confidence)
    sep_pct = float(hit.notes.get("separation_pct", 0.0))
    drop_pct = float(hit.notes.get("neckline_drop_pct", 0.0))
    vix_now = float(getattr(ctx, "vix_now", None) or 17.0)

    stop_price = neckline + _CHART_STOP_ABOVE_NECKLINE
    tp1_price = bar_close - _TP1_SPY_DROP
    runner_price = bar_close - _RUNNER_SPY_DROP

    # Confidence tier — REPORTED ONLY (never a gate). double_top_detector conf base
    # is 0.5; a clean M with a decisive break lands ~0.70-0.85.
    if conf_score >= 0.70:
        confidence = "high"
    elif conf_score >= 0.58:
        confidence = "medium"
    else:
        confidence = "low"

    return WatcherSignal(
        watcher_name="double_top",
        setup_name="DOUBLE_TOP",
        direction="short",
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=(
            f"Double top (M) conf={conf_score:.2f}. "
            f"Highs~{upper_high:.2f}, neckline(trough)={neckline:.2f}, "
            f"stop={stop_price:.2f} (neckline+$0.30, reclaim=invalidation). "
            f"VIX={vix_now:.1f} (bucket={_vix_bucket(vix_now)}). "
            f"WATCH-ONLY: intraday double top ~ A.4 CHoCH/level-rejection; Bulkowski 25% "
            f"is a DAILY stat (does NOT transfer to 5m) — re-measure on SPY before any trigger."
        ),
        triggers_fired=["double_top_detector", "time_window"],
        metadata={
            "upper_high": upper_high,
            "high1_price": hit.notes.get("high1_price"),
            "high2_price": hit.notes.get("high2_price"),
            "neckline": neckline,
            "bars_between": hit.notes.get("bars_between"),
            "separation_pct": sep_pct,
            "neckline_drop_pct": drop_pct,
            "high2_volume_higher": hit.notes.get("high2_volume_higher"),
            "confidence_score": conf_score,
            "vix_now": vix_now,
            "vix_bucket": _vix_bucket(vix_now),
            "no_edge_gates": "intentional — gather unbiased SPY 5m double-top sample (no validated combo search)",
            "bulkowski_caveat": "25% break-even failure rate is daily/weekly; re-measure on SPY 5m before live trigger",
            "op21_live_gate": "0/3 — DO NOT promote until 3+ live J confirmations + SPY 5m failure-rate re-measure",
        },
    )
