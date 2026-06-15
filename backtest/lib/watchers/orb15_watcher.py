"""ORB-15 watcher — 15-minute Opening Range Breakout (Reddit r/FuturesTradingNQ adoption).

Source: J-supplied post "I've been paid $95,336 from prop firms trading NQ" (2026-06-14).
The author's first setup is a 15-MINUTE opening-range breakout that "catches the opening
momentum." Gamma already ships a 30-minute ORB (`orb_watcher.py`, leaderboard #4/#5). This
file is a SELF-CONTAINED 15-minute variant so the deployed 30-min watcher is untouched
(zero production risk) and the 15-min stream accumulates its own observations.

Two deltas vs the deployed 30-min ORB, both faithful to the post:
  1. Opening range = first 15 min (09:30-09:45 ET) instead of 30 min (09:30-10:00).
  2. ENTRY_MODE: "break" enters on the breakout bar itself ("opening momentum"), the
     post's described behavior. "retest" reuses the proven break->retest->held machine.
     The live watcher default is set after the Stage-1 scan picks the better mode.

Per-day state machine (retest mode mirrors orb_watcher):
  NEUTRAL -> WAITING_RETEST_LONG -> RETEST_HELD (entry)        [retest mode]
  NEUTRAL -> (breakout bar) -> ENTRY                           [break mode]

Long-only by default (ORB_DIRECTION_FILTER evidence: wide shorts are the drag; see
orb_watcher.py + leaderboard #5). Watch-only: does NOT place trades. Promotion to live
requires OP-21 (3+ live J confirmations) + Rule 9 ratification.

Author: Gamma (interactive session 2026-06-14). Spec:
  strategy/candidates/2026-06-14-reddit-orb15-and-erl-irl-fvg-adoption.md
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from . import WatcherSignal


# ---- Opening-range window (the 15-min delta) ----
OR_START = dt.time(9, 30)
OR_END = dt.time(9, 45)              # 15-minute opening range
ENTRY_WINDOW_END = dt.time(12, 0)    # no new ORB-15 entries after noon

# ---- Range gates (re-fit for the narrower 15-min window — 30-min gate was 2.00) ----
MIN_RANGE_DOLLARS = 0.35             # 15-min range is tighter than 30-min; lower floor
MAX_OR_RANGE = 1.50                  # narrow-OR quality gate (Stage-1 re-fits; default 1.50)

# ---- Retest-mode tolerances (mirror orb_watcher) ----
RETEST_TOLERANCE = 0.20
INVALIDATION_DOLLARS = 0.30
MAX_BARS_AWAIT_RETEST = 6            # 6 * 5min = 30 min retest window (tighter than 30-min ORB)
MIN_VOLUME_MULT = 1.3

# ---- Behaviour knobs ----
ORB15_DIRECTION_FILTER: Optional[str] = "long"   # "long" | None (R&D)
ORB15_ENTRY_MODE: str = "retest"                 # "retest" | "break" — live default; scan overrides


@dataclass
class OpeningRange15:
    high: float
    low: float
    range: float
    pt_long_05: float
    pt_long_10: float
    pt_short_05: float
    pt_short_10: float


def compute_opening_range_15(
    day_bars: pd.DataFrame,
    or_start: dt.time = OR_START,
    or_end: dt.time = OR_END,
    max_or_range: Optional[float] = MAX_OR_RANGE,
) -> Optional[OpeningRange15]:
    """ORH/ORL/ladders from bars within [or_start, or_end). Narrow-OR gated."""
    or_bars = day_bars[
        (day_bars["timestamp_et"].dt.time >= or_start)
        & (day_bars["timestamp_et"].dt.time < or_end)
    ]
    if or_bars.empty:
        return None
    high = float(or_bars["high"].max())
    low = float(or_bars["low"].min())
    rng = high - low
    if rng < MIN_RANGE_DOLLARS:
        return None
    if max_or_range is not None and rng >= max_or_range:
        return None
    return OpeningRange15(
        high=high, low=low, range=rng,
        pt_long_05=high + 0.5 * rng, pt_long_10=high + 1.0 * rng,
        pt_short_05=low - 0.5 * rng, pt_short_10=low - 1.0 * rng,
    )


def _sma(closes: pd.Series, period: int) -> float:
    if len(closes) < period:
        return float("nan")
    return float(closes.iloc[-period:].mean())


# Per-day state machine (distinct store from the 30-min ORB)
_orb15_state: dict[str, dict] = {}


def _get_state(date_str: str) -> dict:
    if date_str not in _orb15_state:
        _orb15_state[date_str] = {
            "state": "NEUTRAL", "direction": None,
            "breakout_close": None, "breakout_ts": None,
            "bars_since_breakout": 0, "or_data": None,
        }
    return _orb15_state[date_str]


def _build_long_signal(or_data, entry, stop, bar, vol_baseline_20, sma10, sma50, mode, reason_extra=""):
    bullish_bias = sma10 > sma50 if not (pd.isna(sma10) or pd.isna(sma50)) else None
    vol_ok = bar["volume"] >= MIN_VOLUME_MULT * vol_baseline_20 if vol_baseline_20 > 0 else False
    confidence = "high" if (bullish_bias and vol_ok) else ("medium" if (bullish_bias or vol_ok) else "low")
    triggers = [f"or15_break_{mode}"]
    if bullish_bias:
        triggers.append("sma_bullish")
    if vol_ok:
        triggers.append("volume_confirm")
    return WatcherSignal(
        watcher_name="orb15_watcher",
        setup_name="ORB15_LONG",
        direction="long",
        entry_price=float(entry),
        stop_price=float(stop),
        tp1_price=or_data.pt_long_05,
        runner_price=or_data.pt_long_10,
        confidence=confidence,
        reason=(f"ORB-15 {mode} long: ORH {or_data.high:.2f} broken, entry {entry:.2f}, "
                f"or_range={or_data.range:.2f}, {'bullish' if bullish_bias else 'neutral'} SMA, "
                f"vol={'high' if vol_ok else 'low'}{reason_extra}"),
        triggers_fired=triggers,
        metadata={
            "promotion_status": "WATCH_ONLY",
            "or_high": or_data.high, "or_low": or_data.low, "or_range": or_data.range,
            "or_window_minutes": 15, "entry_mode": mode,
            "pt_05": or_data.pt_long_05, "pt_10": or_data.pt_long_10,
            "sma10": sma10, "sma50": sma50,
            "premium_stop_pct": -0.99,   # chart-stop only per L51/L55 (retest pullback misfires premium stops)
            "op21_live_confirmed": 0, "op21_live_required": 3,
            "spec_file": "strategy/candidates/2026-06-14-reddit-orb15-and-erl-irl-fvg-adoption.md",
        },
    )


def detect_orb15_break(
    bar: pd.Series,
    day_bars: pd.DataFrame,
    bar_idx_in_day: int,
    vol_baseline_20: float,
    entry_mode: str = ORB15_ENTRY_MODE,
    max_or_range: Optional[float] = MAX_OR_RANGE,
    direction_filter: Optional[str] = ORB15_DIRECTION_FILTER,
) -> Optional[WatcherSignal]:
    """Detect a 15-minute ORB long entry. Returns a WatcherSignal or None.

    Long-only by default. `entry_mode`:
      "break"  -> emit on the breakout bar (close > ORH, green) — the post's momentum entry.
      "retest" -> emit on break -> pullback-to-ORH -> held-green (proven 30-min machine).
    Short branch is implemented only when direction_filter is None (R&D parity).
    """
    bar_time = bar["timestamp_et"]
    bar_t = bar_time.time() if hasattr(bar_time, "time") else dt.time(0, 0)
    if bar_t < OR_END or bar_t > ENTRY_WINDOW_END:
        return None

    date_str = bar_time.date().isoformat() if hasattr(bar_time, "date") else "?"
    state = _get_state(date_str)
    if state["or_data"] is None:
        or_data = compute_opening_range_15(day_bars, max_or_range=max_or_range)
        if or_data is None:
            return None
        state["or_data"] = or_data
    or_data = state["or_data"]

    bar_high = float(bar["high"]); bar_low = float(bar["low"])
    bar_close = float(bar["close"]); bar_open = float(bar["open"])
    closes = day_bars["close"]
    sma10 = _sma(closes, 10); sma50 = _sma(closes, 50)
    s = state["state"]

    if s == "NEUTRAL":
        # Long breakout: bar closes above ORH on a green bar
        if bar_high > or_data.high and bar_close > or_data.high and bar_close > bar_open:
            if entry_mode == "break":
                state["state"] = "ENTERED"; state["direction"] = "long"
                # chart stop just inside OR (below ORH)
                stop = or_data.high - 0.05
                return _build_long_signal(or_data, bar_close, stop, bar, vol_baseline_20,
                                          sma10, sma50, "break", reason_extra=" [momentum]")
            state["state"] = "WAITING_RETEST_LONG"; state["direction"] = "long"
            state["breakout_close"] = bar_close; state["breakout_ts"] = bar_time
            state["bars_since_breakout"] = 0
            return None
        if direction_filter != "long":
            if bar_low < or_data.low and bar_close < or_data.low and bar_close < bar_open:
                state["state"] = "ENTERED" if entry_mode == "break" else "WAITING_RETEST_SHORT"
                state["direction"] = "short"; state["breakout_close"] = bar_close
                state["breakout_ts"] = bar_time; state["bars_since_breakout"] = 0
                # (short signal construction omitted in watch-only long-default mode)
        return None

    elif s == "WAITING_RETEST_LONG":
        state["bars_since_breakout"] += 1
        if bar_close < (or_data.high - INVALIDATION_DOLLARS):
            state["state"] = "NEUTRAL"; state["direction"] = None
            return None
        if state["bars_since_breakout"] > MAX_BARS_AWAIT_RETEST:
            state["state"] = "NEUTRAL"; state["direction"] = None
            return None
        retest_zone_top = or_data.high + RETEST_TOLERANCE
        retest_zone_bot = or_data.high - RETEST_TOLERANCE
        if (bar_low <= retest_zone_top) and (bar_low >= retest_zone_bot - 0.10):
            if bar_close >= or_data.high and bar_close > bar_open:
                state["state"] = "ENTERED"
                stop = min(bar_low - 0.05, or_data.high - 0.05)
                return _build_long_signal(or_data, bar_close, stop, bar, vol_baseline_20,
                                          sma10, sma50, "retest",
                                          reason_extra=f", retest@{bar_low:.2f}")
        return None

    return None
