"""ORB watcher — Opening Range Breakout detector (mirrors J's TradingView ORB GOAT layout).

UPDATED 2026-05-10 evening — original v1 fired on initial breakout (5 of 8
trades stopped on retest). v2 implements the actual ORB GOAT pattern:

  STATE 1: BREAKOUT — price closes above ORH (or below ORL)
  STATE 2: WAIT FOR RETEST — price must pull back to within retest_tolerance of OR
  STATE 3: RETEST CONFIRMED — bar holds the level (small green bounce on long, red on short)
  STATE 4: ENTRY — next bar after confirmed retest

Rules from J's chart (read via TradingView MCP labels endpoint):
  - Labels show "Breakout / Wait for Retest" → "Retest" → entry
  - Also "Failed Retest" = invalidation, no entry
  - Opening Range = first 30 min (09:30-10:00 ET) high/low
  - Trend filter = SMA10 vs SMA50 (bullish bias when SMA10 > SMA50)
  - TP1 = 50% range projection beyond OR
  - Runner = 100% range projection
  - Stop = beyond the retested level (just inside OR)

Per-day state machine: BREAKOUT_LONG/SHORT detected, then WAITING_RETEST,
then RETEST_HELD = entry signal. If price re-enters OR by > break_invalidation
distance during WAITING_RETEST → FAILED_RETEST, reset to NEUTRAL.

Watch-only mode: detects setups + computes would-be P&L. Does NOT trade.
Promotion to live trading requires 3+ validated wins per OP 21.

Direction filter (Option A — OP-21 ratified 2026-05-21):
  16-month analysis (N=391): long-only (N=274) → +$7,378 / 4-of-6 quarters positive.
  Wide shorts are the primary drag (N=117, -$205 net, regime-fragile).
  `ORB_DIRECTION_FILTER = "long"` suppresses SHORT state-machine transitions.
  Set to None to restore both directions (for R&D only).

Narrow-OR quality gate (ORB_NARROW_OR_GATE — ratified 2026-05-21):
  Walk-forward OOS/IS Sharpe ratio=1.149 (gate >= 0.50: PASS).
  Real-fills: N=22 OPRA cases, WR=81.8% with chart-stop-only (L64).
  Narrow (or_range<2.00): N=274, WR=88.1%, P&L=+$4,597 over 16 months.
  Wide (or_range>=2.00): WR=48.9%, P&L=+$2,781 — no quality edge.
  VIX gate was tested and FAILED: VIX>=20 is the wrong discriminator.
  `MAX_OR_RANGE = 2.00` wired into compute_opening_range() — wide ORBs never
  advance past NEUTRAL because state["or_data"] is never populated.
  Set to None to disable (R&D only, disables quality filter).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from . import WatcherSignal


OR_START = dt.time(9, 30)
OR_END = dt.time(10, 0)
ENTRY_WINDOW_END = dt.time(12, 30)   # extended for retest pattern (was 11:30)
MIN_VOLUME_MULT = 1.3                 # break bar volume >= 1.3x 20-bar avg
MIN_RANGE_DOLLARS = 0.50              # OR must be at least $0.50 wide (avoid no-vol mornings)
MAX_RANGE_DOLLARS = 5.00              # OR > $5 = gappy/news-driven, skip
RETEST_TOLERANCE = 0.20               # retest = price within $0.20 of OR boundary
INVALIDATION_DOLLARS = 0.30           # if price re-enters OR by > $0.30 during wait, fail
MAX_BARS_AWAIT_RETEST = 8             # 8 × 5min = 40 min wait window for retest

# Option-A direction filter: "long" = long-only (recommended), None = both directions (R&D)
# Evidence: N=391 all → +$7,161 / 2-of-6 Q positive.  N=274 long-only → +$7,378 / 4-of-6 Q.
# Wide shorts (N=117) are regime-fragile and the primary drag on the composite.
# Candidate: strategy/candidates/2026-05-21-orb-direction-filter.md
ORB_DIRECTION_FILTER: Optional[str] = "long"

# Narrow-OR quality gate (ORB_NARROW_OR_GATE — ratified 2026-05-21):
# Walk-forward OOS/IS Sharpe ratio=1.149 PASS. Real-fills N=22 OPRA cases WR=81.8%.
# Narrow (or_range<2.00): N=274, WR=88.1%, P&L=+$4,597. Q2-2026 concentration: 85%→46%.
# Wide ORs (or_range>=2.00): WR=48.9%, P&L=+$2,781 — no quality edge over 16 months.
# VIX gate was tested and FAILED: VIX>=20 is the wrong discriminator.
# Gate is strict less-than: or_range == 2.00 is BLOCKED (matches v36 validator T3).
# Set to None to disable the gate (R&D / comparison only).
# Candidate: strategy/candidates/_LEADERBOARD.md (#4 ORB_NARROW_OR_GATE)
MAX_OR_RANGE: Optional[float] = 2.00


@dataclass
class OpeningRange:
    high: float
    low: float
    range: float
    pt_long_05: float
    pt_long_10: float
    pt_short_05: float
    pt_short_10: float


def compute_opening_range(day_bars: pd.DataFrame) -> Optional[OpeningRange]:
    """Compute ORH/ORL/ladders from bars within 09:30-10:00 ET window."""
    or_bars = day_bars[
        (day_bars["timestamp_et"].dt.time >= OR_START) &
        (day_bars["timestamp_et"].dt.time < OR_END)
    ]
    if or_bars.empty:
        return None
    high = float(or_bars["high"].max())
    low = float(or_bars["low"].min())
    rng = high - low
    # Two-tier upper bound:
    #   MAX_OR_RANGE active  → strict less-than gate (or_range < 2.00, so 2.00 is rejected)
    #   MAX_OR_RANGE = None  → original structural limit (or_range > 5.00 = gappy/news day)
    #   The two branches use different operators intentionally — do not unify.
    if MAX_OR_RANGE is not None:
        if rng < MIN_RANGE_DOLLARS or rng >= MAX_OR_RANGE:
            return None
    else:
        if rng < MIN_RANGE_DOLLARS or rng > MAX_RANGE_DOLLARS:
            return None
    return OpeningRange(
        high=high, low=low, range=rng,
        pt_long_05=high + 0.5 * rng,
        pt_long_10=high + 1.0 * rng,
        pt_short_05=low - 0.5 * rng,
        pt_short_10=low - 1.0 * rng,
    )


def _sma(closes: pd.Series, period: int) -> float:
    if len(closes) < period:
        return float("nan")
    return float(closes.iloc[-period:].mean())


# Per-day state machine (same dedup pattern as runner.py)
_orb_state: dict[str, dict] = {}   # date_str -> {state, direction, breakout_bar_ts, ...}


def _get_state(date_str: str) -> dict:
    if date_str not in _orb_state:
        _orb_state[date_str] = {
            "state": "NEUTRAL",
            "direction": None,
            "breakout_close": None,
            "breakout_ts": None,
            "bars_since_breakout": 0,
            "or_data": None,
        }
    return _orb_state[date_str]


def detect_orb_break(
    bar: pd.Series,
    day_bars: pd.DataFrame,
    bar_idx_in_day: int,
    vol_baseline_20: float,
) -> Optional[WatcherSignal]:
    """Detect an ORB BREAKOUT-then-RETEST signal.

    State machine (per day):
      NEUTRAL → BREAKOUT_LONG/SHORT → WAITING_RETEST → RETEST_HELD (= entry signal)

    Re-entry into OR by > INVALIDATION_DOLLARS during WAITING_RETEST → FAILED → NEUTRAL.
    No retest within MAX_BARS_AWAIT_RETEST → also NEUTRAL (assume continuation already happened).

    Returns WatcherSignal ONLY on RETEST_HELD bar (entry signal).
    """
    bar_time = bar["timestamp_et"]
    bar_t = bar_time.time() if hasattr(bar_time, "time") else dt.time(0, 0)

    # Only operate AFTER OR closes
    if bar_t < OR_END:
        return None
    # Don't fire after entry window
    if bar_t > ENTRY_WINDOW_END:
        return None

    # Compute OR (cached after first compute per day)
    date_str = bar_time.date().isoformat() if hasattr(bar_time, "date") else "?"
    state = _get_state(date_str)

    if state["or_data"] is None:
        or_data = compute_opening_range(day_bars)
        if or_data is None:
            return None
        state["or_data"] = or_data
    or_data = state["or_data"]

    bar_high = float(bar["high"])
    bar_low = float(bar["low"])
    bar_close = float(bar["close"])
    bar_open = float(bar["open"])

    closes = day_bars["close"]
    sma10 = _sma(closes, 10)
    sma50 = _sma(closes, 50)

    # State machine transitions
    s = state["state"]

    if s == "NEUTRAL":
        # Look for breakout
        if bar_high > or_data.high and bar_close > or_data.high and bar_close > bar_open:
            state["state"] = "WAITING_RETEST_LONG"
            state["direction"] = "long"
            state["breakout_close"] = bar_close
            state["breakout_ts"] = bar_time
            state["bars_since_breakout"] = 0
            return None  # don't enter on breakout, wait for retest
        # Option-A direction filter: skip short breakouts when long-only mode is active
        if ORB_DIRECTION_FILTER != "long":
            if bar_low < or_data.low and bar_close < or_data.low and bar_close < bar_open:
                state["state"] = "WAITING_RETEST_SHORT"
                state["direction"] = "short"
                state["breakout_close"] = bar_close
                state["breakout_ts"] = bar_time
                state["bars_since_breakout"] = 0
                return None
        return None

    elif s == "WAITING_RETEST_LONG":
        state["bars_since_breakout"] += 1
        # Invalidation: bar closes back inside OR by > INVALIDATION_DOLLARS
        if bar_close < (or_data.high - INVALIDATION_DOLLARS):
            state["state"] = "NEUTRAL"
            state["direction"] = None
            return None
        # Timeout
        if state["bars_since_breakout"] > MAX_BARS_AWAIT_RETEST:
            state["state"] = "NEUTRAL"
            state["direction"] = None
            return None
        # Retest detected: bar low touches within RETEST_TOLERANCE of ORH from above
        retest_zone_top = or_data.high + RETEST_TOLERANCE
        retest_zone_bot = or_data.high - RETEST_TOLERANCE
        if (bar_low <= retest_zone_top) and (bar_low >= retest_zone_bot - 0.10):
            # Held the level (close > ORH still) AND bar is green = RETEST_HELD
            if bar_close >= or_data.high and bar_close > bar_open:
                # ENTRY signal!
                bullish_bias = sma10 > sma50 if not (pd.isna(sma10) or pd.isna(sma50)) else None
                vol_ok = bar["volume"] >= MIN_VOLUME_MULT * vol_baseline_20 if vol_baseline_20 > 0 else False
                confidence = "high" if (bullish_bias and vol_ok) else (
                    "medium" if (bullish_bias or vol_ok) else "low"
                )
                triggers = ["orh_breakout_retest"]
                if bullish_bias: triggers.append("sma_bullish")
                if vol_ok: triggers.append("volume_confirm")
                signal = WatcherSignal(
                    watcher_name="orb_watcher",
                    setup_name="ORB_RETEST_LONG",
                    direction="long",
                    entry_price=bar_close,
                    # Stop = retest bar's low minus small buffer (chart stop, real ORB GOAT logic)
                    stop_price=min(bar_low - 0.05, or_data.high - 0.05),
                    tp1_price=or_data.pt_long_05,
                    runner_price=or_data.pt_long_10,
                    confidence=confidence,
                    reason=f"ORH {or_data.high:.2f} broken at {state['breakout_close']:.2f}, "
                           f"retested at {bar_low:.2f} held + green close {bar_close:.2f}, "
                           f"{'bullish' if bullish_bias else 'neutral'} SMA, vol={'high' if vol_ok else 'low'}",
                    triggers_fired=triggers,
                    metadata={
                        "or_high": or_data.high, "or_low": or_data.low, "or_range": or_data.range,
                        "pt_05": or_data.pt_long_05, "pt_10": or_data.pt_long_10,
                        "sma10": sma10, "sma50": sma50,
                        "breakout_close": state["breakout_close"],
                        "breakout_ts": str(state["breakout_ts"]),
                        "bars_to_retest": state["bars_since_breakout"],
                        "stop_dist_dollars": bar_close - (or_data.high - 0.10),
                    },
                )
                state["state"] = "ENTERED"  # don't re-fire after entry
                return signal
        return None

    elif s == "WAITING_RETEST_SHORT":
        state["bars_since_breakout"] += 1
        if bar_close > (or_data.low + INVALIDATION_DOLLARS):
            state["state"] = "NEUTRAL"
            state["direction"] = None
            return None
        if state["bars_since_breakout"] > MAX_BARS_AWAIT_RETEST:
            state["state"] = "NEUTRAL"
            state["direction"] = None
            return None
        # Retest from below: bar high touches within RETEST_TOLERANCE of ORL from below
        retest_zone_top = or_data.low + RETEST_TOLERANCE
        retest_zone_bot = or_data.low - RETEST_TOLERANCE
        if (bar_high >= retest_zone_bot) and (bar_high <= retest_zone_top + 0.10):
            if bar_close <= or_data.low and bar_close < bar_open:
                bearish_bias = sma10 < sma50 if not (pd.isna(sma10) or pd.isna(sma50)) else None
                vol_ok = bar["volume"] >= MIN_VOLUME_MULT * vol_baseline_20 if vol_baseline_20 > 0 else False
                confidence = "high" if (bearish_bias and vol_ok) else (
                    "medium" if (bearish_bias or vol_ok) else "low"
                )
                triggers = ["orl_breakout_retest"]
                if bearish_bias: triggers.append("sma_bearish")
                if vol_ok: triggers.append("volume_confirm")
                signal = WatcherSignal(
                    watcher_name="orb_watcher",
                    setup_name="ORB_RETEST_SHORT",
                    direction="short",
                    entry_price=bar_close,
                    # Chart stop: retest bar's high plus small buffer
                    stop_price=max(bar_high + 0.05, or_data.low + 0.05),
                    tp1_price=or_data.pt_short_05,
                    runner_price=or_data.pt_short_10,
                    confidence=confidence,
                    reason=f"ORL {or_data.low:.2f} broken at {state['breakout_close']:.2f}, "
                           f"retested at {bar_high:.2f} held + red close {bar_close:.2f}, "
                           f"{'bearish' if bearish_bias else 'neutral'} SMA, vol={'high' if vol_ok else 'low'}",
                    triggers_fired=triggers,
                    metadata={
                        "or_high": or_data.high, "or_low": or_data.low, "or_range": or_data.range,
                        "pt_05": or_data.pt_short_05, "pt_10": or_data.pt_short_10,
                        "sma10": sma10, "sma50": sma50,
                        "breakout_close": state["breakout_close"],
                        "breakout_ts": str(state["breakout_ts"]),
                        "bars_to_retest": state["bars_since_breakout"],
                        "stop_dist_dollars": (or_data.low + 0.10) - bar_close,
                    },
                )
                state["state"] = "ENTERED"
                return signal
        return None

    elif s == "ENTERED":
        # After ENTRY: allow OPPOSITE direction re-entry if SPY breaks the OTHER side of OR
        # (5/04 had bullish ORB break early then bearish reversal — this captures both)
        # Option-A direction filter: when long-only, suppress short re-entries.
        entered_dir = state.get("direction")
        if entered_dir == "long" and ORB_DIRECTION_FILTER != "long":
            # Look for bearish breakout (skipped in long-only mode)
            if bar_low < or_data.low and bar_close < or_data.low and bar_close < bar_open:
                state["state"] = "WAITING_RETEST_SHORT"
                state["direction"] = "short"
                state["breakout_close"] = bar_close
                state["breakout_ts"] = bar_time
                state["bars_since_breakout"] = 0
        elif entered_dir == "short":
            if bar_high > or_data.high and bar_close > or_data.high and bar_close > bar_open:
                state["state"] = "WAITING_RETEST_LONG"
                state["direction"] = "long"
                state["breakout_close"] = bar_close
                state["breakout_ts"] = bar_time
                state["bars_since_breakout"] = 0
        return None

    return None
