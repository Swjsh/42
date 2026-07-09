"""swing_sim.py -- multiday extension of futures_sim.py (42 Futures Edition, Phase 1).

`futures_sim.py` assumes same-day intraday exits on 5m bars. This module is the
swing-horizon (1-5 day) counterpart: daily or 4h-of-RTH bars, ATR-based point
stops, and GAP-AWARE fills -- the load-bearing difference from an intraday
walker, where a stop/target can be crossed BETWEEN bars (overnight/weekend) and
must fill at the bar's OPEN (worse than the nominal level), never at the level
itself. A wrong implementation that always fills at the nominal stop/target
price silently overstates edge on every gap day; see
`backtest/tests/test_swing_sim.py` for the guard.

Fill-ordering convention (matches the existing 42 futures stack, e.g. the prior
`analysis/PHASE1-swing-battery/swing_battery.py::ExitEngine.sim`):
  1. On bars AFTER the entry bar, check the bar's OPEN first -- if it already
     gapped through the stop or target, fill there (worse for stops, better for
     targets -- both are "the market already moved past the level").
  2. Otherwise check the bar's intrabar high/low against stop and target --
     STOP CHECKED FIRST if both could fire in the same bar (conservative).
  3. If neither fires within `max_hold_bars`, exit at that bar's CLOSE ("TIME").
  4. If bars run out before `max_hold_bars` is reached, exit at the last
     available bar's CLOSE ("DATA_END").

Causality: `atr_at_entry` is a CALLER-supplied value -- this module does not
compute "the ATR as of entry" itself (that's `wilder_atr` + the caller indexing
it at `entry_idx - 1`, mirroring the ribbon/RRW detector convention elsewhere
in this repo where the caller is responsible for not leaking future bars).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
import pandas as pd


def wilder_atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's smoothed ATR from OHLC bars (any timeframe -- daily or 4h-of-RTH).

    TR[i] = max(H[i]-L[i], |H[i]-C[i-1]|, |L[i]-C[i-1]|); TR[0] = H[0]-L[0]
    (no prior close to gap against). ATR seeded with the SMA of the first
    `period` TRs, then Wilder-smoothed: ATR[i] = (ATR[i-1]*(period-1) + TR[i]) / period.

    Returns a Series aligned to `bars.index` (RangeIndex assumed); the first
    (period-1) values are NaN (warmup).
    """
    if len(bars) == 0:
        return pd.Series(dtype=float)
    h = bars["high"].astype(float).to_numpy()
    l = bars["low"].astype(float).to_numpy()
    c = bars["close"].astype(float).to_numpy()
    n = len(bars)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = np.full(n, np.nan)
    if n >= period:
        atr[period - 1] = tr[:period].mean()
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return pd.Series(atr, index=bars.index)


@dataclass(frozen=True)
class SwingResult:
    direction: str
    entry_idx: int
    exit_idx: int
    entry_px: float
    exit_px: float
    stop_px: float
    target_px: Optional[float]
    pnl_pts: float
    pnl_usd: float
    reason: str            # "STOP" | "TARGET" | "TIME" | "DATA_END"
    gapped: bool            # True iff the exit fill was AT THE OPEN (gap-through), not the nominal level
    hold_bars: int
    qty: int

    def to_dict(self) -> dict:
        return asdict(self)


def simulate_swing(
    direction: str,
    entry_idx: int,
    bars: pd.DataFrame,
    atr_at_entry: float,
    instrument,
    *,
    stop_mult: float = 1.5,
    target_mult: Optional[float] = 3.0,
    max_hold_bars: int = 5,
    qty: int = 1,
    cost_per_side_usd: float = 2.50,
) -> SwingResult:
    """Simulate ONE swing trade entering at `bars.iloc[entry_idx]`'s OPEN.

    Args:
        direction: "long" or "short".
        entry_idx: positional index (0-based, RangeIndex) into `bars` of the
            entry bar. Entry fills at that bar's OPEN (next-bar-open-after-signal
            is the caller's responsibility -- pass the bar AFTER the signal bar).
        bars: OHLC frame, chronological, RangeIndex 0..n-1, columns
            open/high/low/close (volume not required by the sim).
        atr_at_entry: ATR point value known as of entry (caller-causal -- see
            module docstring). Must be positive and finite.
        instrument: an `instruments.Instrument` (MES/MNQ/...) -- supplies point_value.
        stop_mult: stop distance = stop_mult * atr_at_entry (points).
        target_mult: target distance = target_mult * atr_at_entry (points), or
            None for NO fixed target (the trade only exits on stop, max_hold_bars,
            or DATA_END).
        max_hold_bars: exit at this bar's close if neither stop nor target has
            fired by then (bar index entry_idx + max_hold_bars). In DAILY bars
            this is calendar TRADING days held; in 4h-of-RTH bars it is 4h
            buckets (caller converts a day-count to a bar-count for that
            timeframe -- see `seeds/*` for the day<->bar mapping used).
        qty: contracts.
        cost_per_side_usd: commission + slippage charged PER SIDE. Total
            round-turn cost = 2 * cost_per_side_usd * qty (entry AND exit each
            pay it), per the Phase-1 honesty bar.

    Returns:
        SwingResult with entry/exit prices, $ P&L (net of costs), and the exit
        reason. `gapped=True` marks a fill that happened at a bar's OPEN because
        the level was already crossed before the bar's intrabar range -- the
        one behavior this module exists to get right (see module docstring).
    """
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")
    n = len(bars)
    if n == 0 or entry_idx < 0 or entry_idx >= n:
        raise ValueError(f"entry_idx {entry_idx} out of range [0, {n})")
    if atr_at_entry is None or not np.isfinite(atr_at_entry) or atr_at_entry <= 0:
        raise ValueError(f"atr_at_entry must be a positive finite number, got {atr_at_entry!r}")
    if max_hold_bars < 0:
        raise ValueError(f"max_hold_bars must be >= 0, got {max_hold_bars}")

    o = bars["open"].astype(float).to_numpy()
    h = bars["high"].astype(float).to_numpy()
    l = bars["low"].astype(float).to_numpy()
    c = bars["close"].astype(float).to_numpy()

    entry_px = float(o[entry_idx])
    sign = 1.0 if direction == "long" else -1.0
    stop_px = entry_px - sign * stop_mult * atr_at_entry
    target_px = (entry_px + sign * target_mult * atr_at_entry) if target_mult is not None else None

    last_reachable = min(n - 1, entry_idx + max_hold_bars)
    ran_out_of_data = last_reachable < entry_idx + max_hold_bars
    # Default (falls through if no stop/target ever fires): time/data-end exit.
    exit_idx = last_reachable
    exit_px = float(c[last_reachable])
    reason = "DATA_END" if ran_out_of_data else "TIME"
    gapped = False

    for i in range(entry_idx, last_reachable + 1):
        if i > entry_idx:
            bar_open = float(o[i])
            if direction == "long" and bar_open <= stop_px:
                exit_idx, exit_px, reason, gapped = i, bar_open, "STOP", True
                break
            if direction == "short" and bar_open >= stop_px:
                exit_idx, exit_px, reason, gapped = i, bar_open, "STOP", True
                break
            if target_px is not None:
                if direction == "long" and bar_open >= target_px:
                    exit_idx, exit_px, reason, gapped = i, bar_open, "TARGET", True
                    break
                if direction == "short" and bar_open <= target_px:
                    exit_idx, exit_px, reason, gapped = i, bar_open, "TARGET", True
                    break
        bar_hi, bar_lo = float(h[i]), float(l[i])
        if direction == "long" and bar_lo <= stop_px:
            exit_idx, exit_px, reason, gapped = i, stop_px, "STOP", False
            break
        if direction == "short" and bar_hi >= stop_px:
            exit_idx, exit_px, reason, gapped = i, stop_px, "STOP", False
            break
        if target_px is not None:
            if direction == "long" and bar_hi >= target_px:
                exit_idx, exit_px, reason, gapped = i, target_px, "TARGET", False
                break
            if direction == "short" and bar_lo <= target_px:
                exit_idx, exit_px, reason, gapped = i, target_px, "TARGET", False
                break

    pts = (exit_px - entry_px) * sign
    gross_usd = pts * instrument.point_value * qty
    cost_usd = 2.0 * cost_per_side_usd * qty
    net_usd = gross_usd - cost_usd

    return SwingResult(
        direction=direction, entry_idx=int(entry_idx), exit_idx=int(exit_idx),
        entry_px=round(entry_px, 4), exit_px=round(exit_px, 4),
        stop_px=round(stop_px, 4),
        target_px=(round(target_px, 4) if target_px is not None else None),
        pnl_pts=round(pts, 4), pnl_usd=round(net_usd, 2),
        reason=reason, gapped=gapped, hold_bars=int(exit_idx - entry_idx), qty=qty,
    )


def simulate_buy_and_hold(
    direction: str, entry_idx: int, bars: pd.DataFrame, instrument, *,
    hold_bars: int = 5, qty: int = 1, cost_per_side_usd: float = 2.50,
) -> SwingResult:
    """No-stop, no-target benchmark: enter at open, exit at close `hold_bars`
    bars later (or DATA_END). Used as the buy-and-hold-same-horizon null
    (battery discipline requirement -- distinguishes a real edge from riding
    the 2025-26 uptrend)."""
    n = len(bars)
    if n == 0 or entry_idx < 0 or entry_idx >= n:
        raise ValueError(f"entry_idx {entry_idx} out of range [0, {n})")
    sign = 1.0 if direction == "long" else -1.0
    o = bars["open"].astype(float).to_numpy()
    c = bars["close"].astype(float).to_numpy()
    last_reachable = min(n - 1, entry_idx + hold_bars)
    ran_out = last_reachable < entry_idx + hold_bars
    entry_px = float(o[entry_idx])
    exit_px = float(c[last_reachable])
    pts = (exit_px - entry_px) * sign
    gross_usd = pts * instrument.point_value * qty
    cost_usd = 2.0 * cost_per_side_usd * qty
    return SwingResult(
        direction=direction, entry_idx=int(entry_idx), exit_idx=int(last_reachable),
        entry_px=round(entry_px, 4), exit_px=round(exit_px, 4),
        stop_px=float("nan"), target_px=None,
        pnl_pts=round(pts, 4), pnl_usd=round(gross_usd - cost_usd, 2),
        reason=("DATA_END" if ran_out else "TIME"), gapped=False,
        hold_bars=int(last_reachable - entry_idx), qty=qty,
    )


__all__ = ["wilder_atr", "SwingResult", "simulate_swing", "simulate_buy_and_hold"]
