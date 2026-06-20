"""entry_gate — verify a candidate entry timestamp passes the v15.1 RTH-window rules.

Production source-of-truth (per `automation/state/params.json`):
  - entry_no_trade_before_et: "09:35"   (v15.1 ratified 2026-05-14)
  - entry_no_trade_after_et:  "15:00"   (v15.1 — tightened from 15:50 to protect against theta)
  - entry_no_trade_window_et: null      (v15.1 REMOVED the 14:00-15:00 mid-day blackout)

R2 closed-bar guard (per markdown/audits/HEARTBEAT-CHART-DATA-AUDIT-2026-05-14.md):
  A trigger bar must be CLOSED before its trigger is consumed for entry.
  `bar_close_et = bar_open_et + 5min`; entry is permitted only when `bar_close_et <= now_et`.

This module is pure config-driven math. It does NOT make network calls. It does NOT
know about the live wall clock — callers pass a `now_et` (a `datetime.time` or
tz-aware `datetime` from which `.time()` is taken). The decision tree is:

  1. Time-of-day gate: must be in [entry_no_trade_before_et, entry_no_trade_after_et)
  2. Mid-day blackout: if `entry_no_trade_window_et` is non-null, must NOT be in it
  3. R2 bar-age guard (optional): if a trigger_bar_open_et is passed, the bar's
     close (open + granularity) must be ≤ `now_et`.

Returns a `GateDecision` with `passed: bool` + a `reason` string for diagnostics.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta
from typing import Optional


@dataclass(frozen=True, slots=True)
class GateDecision:
    passed: bool
    reason: str  # "ok" | "before_open" | "after_close" | "midday_blackout" | "bar_in_progress"
    now_et_time: dtime
    bar_close_et: Optional[dtime] = None


def _coerce_time(value) -> dtime:
    """Accept dtime, datetime, or 'HH:MM' string. Return a naive dtime."""
    if isinstance(value, dtime):
        return value
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, str):
        parts = value.split(":")
        if len(parts) < 2 or len(parts) > 3:
            raise ValueError(f"time string must be HH:MM[:SS], got {value!r}")
        h, m = int(parts[0]), int(parts[1])
        s = int(parts[2]) if len(parts) == 3 else 0
        return dtime(h, m, s)
    raise TypeError(f"Cannot coerce {type(value).__name__} to time")


def check_entry_gate(
    now_et,
    entry_no_trade_before_et: str = "09:35",
    entry_no_trade_after_et: str = "15:00",
    entry_no_trade_window_et: Optional[tuple[str, str]] = None,
    trigger_bar_open_et=None,
    bar_granularity_seconds: int = 300,
) -> GateDecision:
    """Decide whether `now_et` is a valid entry tick under the v15.1 doctrine.

    Args:
      now_et: current ET time (datetime or dtime or 'HH:MM' string)
      entry_no_trade_before_et: cutoff before which entries are blocked
      entry_no_trade_after_et: cutoff at-or-after which entries are blocked
      entry_no_trade_window_et: optional (start, end) tuple blocking mid-day window;
        v15.1 default is `None` (no mid-day blackout)
      trigger_bar_open_et: optional ET datetime of the candidate trigger bar's OPEN.
        If passed, the bar must be CLOSED (open + granularity ≤ now_et) to pass.
      bar_granularity_seconds: bar length in seconds (default 300 = 5min)

    Returns: GateDecision
    """
    now_t = _coerce_time(now_et)
    before = _coerce_time(entry_no_trade_before_et)
    after = _coerce_time(entry_no_trade_after_et)

    if now_t < before:
        return GateDecision(passed=False, reason="before_open", now_et_time=now_t)

    if now_t >= after:
        return GateDecision(passed=False, reason="after_close", now_et_time=now_t)

    if entry_no_trade_window_et is not None:
        win_start = _coerce_time(entry_no_trade_window_et[0])
        win_end = _coerce_time(entry_no_trade_window_et[1])
        if win_start <= now_t < win_end:
            return GateDecision(passed=False, reason="midday_blackout", now_et_time=now_t)

    bar_close_t: Optional[dtime] = None
    if trigger_bar_open_et is not None:
        if not isinstance(trigger_bar_open_et, datetime):
            raise TypeError("trigger_bar_open_et must be a datetime (with date component)")
        if not isinstance(now_et, datetime):
            raise TypeError(
                "trigger_bar_open_et requires now_et to be a datetime, not dtime/str — "
                "needed for closed-bar comparison."
            )
        bar_close_dt = trigger_bar_open_et + timedelta(seconds=bar_granularity_seconds)
        bar_close_t = bar_close_dt.time()
        if bar_close_dt > now_et:
            return GateDecision(
                passed=False, reason="bar_in_progress", now_et_time=now_t,
                bar_close_et=bar_close_t,
            )

    return GateDecision(passed=True, reason="ok", now_et_time=now_t, bar_close_et=bar_close_t)
