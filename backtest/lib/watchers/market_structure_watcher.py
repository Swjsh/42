"""MARKET_STRUCTURE watcher (WATCH-ONLY per OP-21) — emits an Insight when a
Break of Structure (BOS) or Change of Character (CHoCH) prints.

Closes the #1 gap in markdown/research/TA-CAPABILITY-AND-GAPS-2026-06-20.md: the
engine reads *trend* from the EMA ribbon stack + regime classifier, NEVER from
price swing structure, so it had no answer to J's literal question "are we making
higher highs and lower lows?" The keystone detector
(`crypto.lib.market_structure.analyze_structure`) labels HH/HL/LH/LL, derives
trend-from-structure, and runs the BOS/CHoCH state machine. It is gym-validated
(crypto/validators/v46_market_structure.py, 13/13) but was telemetry-only with no
live fleet wiring. This module surfaces its events into the observation stream.

WHAT IT EMITS (per the task — direction, triggering swing price, confidence):
  - direction: "long" on a bullish break (close ABOVE the broken swing high),
    "short" on a bearish break (close BELOW the broken swing low).
  - triggering swing price: StructureEvent.broken_price — the swing level the
    close broke (carried in the reason + metadata).
  - confidence: signal_tier(read.confidence) — the purpose-built bridge in
    market_structure.py mapping the HEURISTIC structure-read confidence onto the
    WatcherSignal low/medium/high vocabulary. It is HEURISTIC, NOT outcome-
    calibrated (TA-PATTERN-REFERENCE.md §A.4: "No published failure-rate stat
    exists for BOS or CHoCH"). Reported, never gated on.

FIRES ONCE PER FRESH EVENT (no look-ahead, no stale re-emit):
  We emit ONLY when the most-recent structure event's break_index == the current
  (last) bar — i.e. the break "printed" this tick. On the next tick the same event
  is no longer on the newest bar, so it is not re-emitted. A bar produces at most
  one event (the walk_structure state machine takes one break branch per bar), so
  there is NO global cooldown — a cooldown would swallow a CHoCH that legitimately
  follows a BOS, and "CHoCH is the single earliest reversal hint, so it must fire
  once per flip" (market_structure.py). Per-day dedup in runner.run_all_watchers
  keys on (setup_name, direction), so STRUCTURE_BOS/STRUCTURE_CHoCH × long/short
  are four distinct first-per-day buckets — the right de-noiser.

PROMOTION PREREQUISITE (why this stays observe-only beyond the OP-21 live gate):
  analyze_structure's default swing finder is crypto.lib.trendlines.find_swing_points.
  Per market_structure.py's live-wiring note, ANY live trigger must first inject
  the LIVE engine's swing primitive (backtest/lib/trendlines scipy find_peaks) via
  `swing_finder=` so gym and live share ONE structure implementation (the drift the
  autonomy blueprint warns about). Using the default here is correct for an
  observe-only stream and matches v46 + the chart-read skill.

OP-21 promotion gate (NONE met yet — NEW stream):
  - Historical / Walk-forward / Real-fills: PENDING (BOS/CHoCH have no published
    stat; must be measured on our SPY 5m sample).
  - Live J observations: 0/3.
  DO NOT wire any live trigger until measured + 3 live J wins + Rule 9 ratification.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from . import WatcherSignal
from ..filters import BarContext

try:
    from crypto.lib.bar import Bar
    from crypto.lib.market_structure import analyze_structure, signal_tier
    _STRUCTURE_AVAILABLE = True
except ImportError:
    _STRUCTURE_AVAILABLE = False


# ── Detection parameters ──────────────────────────────────────────────────────

# Sliding window for the structure read. 40 bars (~3.3h of 5m) keeps the read
# intraday-scoped (RTH is ~78 bars) so overnight gaps never forge false swings.
_WINDOW_BARS: int = 40

# Bars-per-side fractal for swing detection. 2 = SPY 5m default (market_structure
# .DEFAULT_WINDOW; TA-PATTERN-REFERENCE.md §A.2 N=2). Smaller = noisier swings.
_STRUCTURE_WINDOW: int = 2

# Minimum bars before a structure read is meaningful (need a swing + a break).
_MIN_BARS: int = 6

# RTH window — observe 09:35-15:55 ET (premarket structure is noisy; engine is flat
# outside RTH). Mirrors the rest of the fleet.
_RTH_START: dt.time = dt.time(9, 35)
_RTH_END: dt.time = dt.time(15, 55)


# ── Default exit knobs (OP-21 watch-only; for runner.grade_observation only) ───

DEFAULT_QTY: int = 3
DEFAULT_PREMIUM_STOP_PCT: float = -0.99   # chart-stop only (structure stop is the level)
DEFAULT_TP1_PREMIUM_PCT: float = 0.30
DEFAULT_RUNNER_TARGET_PCT: float = 1.5

# SPY-level grading anchors. The broken swing (broken_price) is the structural
# reference: a close back through it invalidates the break, so the stop sits one
# buffer on the far side of broken_price.
_STRUCTURE_STOP_BUFFER: float = 0.30
_TP1_SPY_MOVE: float = 0.70
_RUNNER_SPY_MOVE: float = 2.00


def _build_bars_from_context(ctx: BarContext) -> list[Bar]:
    """Convert the last _WINDOW_BARS rows of prior_bars into Bar objects.

    prior_bars INCLUDES the trigger bar as its last row (filters.BarContext), so
    the returned list ends on the current closed bar — which is what lets us test
    "did the event print on THIS bar" via break_index == len(bars) - 1.
    """
    if not _STRUCTURE_AVAILABLE:
        return []
    import pandas as pd

    df = ctx.prior_bars.tail(_WINDOW_BARS).copy()
    bars: list[Bar] = []
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


def detect_market_structure_setup(ctx: BarContext) -> Optional[WatcherSignal]:
    """Emit an Insight when a BOS or CHoCH prints on the current bar — OBSERVE-ONLY.

    Returns a WatcherSignal (direction long/short) when the latest structure event
    landed on this bar. Returns None when no event printed this tick (the common
    case), the feed is too short, or it is outside RTH. NEVER a live trigger.
    """
    if not _STRUCTURE_AVAILABLE:
        return None

    # ── Gate 1: RTH window (09:35-15:55 ET) ──────────────────────────────────
    bar_time = ctx.timestamp_et.time()
    if bar_time < _RTH_START or bar_time > _RTH_END:
        return None

    # ── Gate 2: enough bars to read structure ────────────────────────────────
    bars = _build_bars_from_context(ctx)
    if len(bars) < _MIN_BARS:
        return None

    # ── Gate 3: a structure event printed on THIS bar ────────────────────────
    read = analyze_structure(bars, window=_STRUCTURE_WINDOW)
    ev = read.last_event
    if ev is None or ev.break_index != len(bars) - 1:
        return None  # no event, or the latest event is stale (printed on an earlier bar)

    # ── Signal: a fresh BOS/CHoCH ────────────────────────────────────────────
    bar_close = float(ctx.bar["close"])
    broken_price = float(ev.broken_price)        # the triggering swing price
    is_bullish = ev.direction == "bullish"
    direction = "long" if is_bullish else "short"
    confidence = signal_tier(read.confidence)
    vix_now = float(getattr(ctx, "vix_now", None) or 17.0)

    if is_bullish:
        stop_price = broken_price - _STRUCTURE_STOP_BUFFER   # reclaimed high flips to support
        tp1_price = bar_close + _TP1_SPY_MOVE
        runner_price = bar_close + _RUNNER_SPY_MOVE
    else:
        stop_price = broken_price + _STRUCTURE_STOP_BUFFER   # broken low flips to resistance
        tp1_price = bar_close - _TP1_SPY_MOVE
        runner_price = bar_close - _RUNNER_SPY_MOVE

    kind = ev.kind  # "BOS" | "CHoCH"
    recent_seq = read.notes.get("recent_label_sequence", [])

    return WatcherSignal(
        watcher_name="market_structure",
        setup_name=f"STRUCTURE_{kind}",
        direction=direction,
        entry_price=bar_close,
        stop_price=stop_price,
        tp1_price=tp1_price,
        runner_price=runner_price,
        confidence=confidence,
        reason=(
            f"{kind} {ev.direction} — close {'above' if is_bullish else 'below'} swing "
            f"{broken_price:.2f} (trend={read.trend} via {read.trend_basis}). "
            f"Seq={recent_seq}. Stop={stop_price:.2f} (swing{'-' if is_bullish else '+'}$0.30 = "
            f"invalidation). VIX={vix_now:.1f}. conf={read.confidence:.2f} (HEURISTIC). "
            f"WATCH-ONLY: BOS/CHoCH have no published failure-rate stat — observe, never trigger."
        ),
        triggers_fired=[f"structure_{kind.lower()}", f"structure_{ev.direction}"],
        metadata={
            "event_kind": kind,                    # BOS | CHoCH
            "event_direction": ev.direction,       # bullish | bearish
            "broken_swing_price": broken_price,    # the triggering swing price
            "swing_index": ev.swing_index,
            "break_index": ev.break_index,
            "trend": read.trend,
            "trend_basis": read.trend_basis,       # structure_breaks | labels | insufficient
            "last_swing_high": read.last_swing_high,
            "last_swing_low": read.last_swing_low,
            "recent_label_sequence": recent_seq,
            "n_swings": read.notes.get("n_swings"),
            "structure_confidence": read.confidence,
            "confidence_is_heuristic": True,
            "structure_window": _STRUCTURE_WINDOW,
            "vix_now": vix_now,
            "promotion_prereq": "inject live engine swing_finder (backtest trendlines) before any live trigger",
            "op21_live_gate": "0/3 — DO NOT promote until measured on SPY 5m + 3 live J confirmations",
        },
    )
