"""profit_lock — chandelier trailing profit-lock state machine.

Mirrors `backtest.lib.simulator_real`'s profit-lock block (T41 + T50b) per
`automation/state/params.json#v15_profit_lock_*` and Operating Principle 12.

State machine:
  - DISARMED while best_premium < entry * (1 + threshold_pct).
  - ARMED when best_premium >= arm_premium. On arm, stop floor moves to
    entry * (1 + stop_offset_pct). For 'trailing' mode, stop floor also tracks
    HWM * (1 - trail_pct) as HWM rises.
  - Stop floor is MONOTONIC: it only moves up, never down. Once ARMED, stays ARMED.

Three modes (all from production):
  fixed    : stop floor = entry * (1 + stop_offset_pct) and never moves after arm.
  trailing : stop floor = max(arm_floor, HWM * (1 - trail_pct)) — chandelier.
  stepped  : stop floor = max(arm_floor, _stepped_floor(entry, HWM)) — rung table
             (this validator does not exercise stepped — covered by simulator tests).

Production defaults (params.json v15.1):
  v15_profit_lock_mode:           "trailing"
  v15_profit_lock_threshold_pct:  0.05  (arm at +5%)
  v15_profit_lock_trail_pct:      0.20  (chandelier 20% off HWM)

Module is pure functions over a `ProfitLockState` dataclass — no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional


@dataclass(frozen=True, slots=True)
class ProfitLockState:
    """Immutable snapshot of the profit-lock state machine."""
    entry_premium: float
    threshold_pct: float
    stop_offset_pct: float
    mode: str                 # "fixed" | "trailing"
    trail_pct: float
    armed: bool
    hwm: float                # highest favorable premium observed
    arm_floor: Optional[float]
    stop_floor: float         # current effective stop floor (premium)

    def __post_init__(self) -> None:
        if self.entry_premium <= 0:
            raise ValueError("entry_premium must be positive")
        if self.mode not in ("fixed", "trailing"):
            raise ValueError(f"mode must be fixed|trailing, got {self.mode!r}")


def initial_state(
    entry_premium: float,
    initial_stop_premium: float,
    threshold_pct: float = 0.05,
    stop_offset_pct: float = 0.0,
    mode: str = "trailing",
    trail_pct: float = 0.20,
) -> ProfitLockState:
    """Construct the at-fill state.

    `initial_stop_premium` is the entry-side stop (e.g. entry * 0.92 for v15 -8%
    bear stop). This becomes the starting stop_floor (it will only move up).
    """
    return ProfitLockState(
        entry_premium=entry_premium,
        threshold_pct=threshold_pct,
        stop_offset_pct=stop_offset_pct,
        mode=mode,
        trail_pct=trail_pct,
        armed=False,
        hwm=entry_premium,
        arm_floor=None,
        stop_floor=initial_stop_premium,
    )


def tick(state: ProfitLockState, current_premium: float) -> ProfitLockState:
    """Process one bar's `current_premium` and return the new state.

    Behavior:
      - HWM updated to max(prev hwm, current).
      - If not yet armed AND current >= entry * (1 + threshold), arm:
          arm_floor = entry * (1 + stop_offset_pct), stop_floor = max(stop_floor, arm_floor)
      - If armed AND mode == 'trailing': candidate = max(arm_floor, hwm * (1 - trail_pct));
          stop_floor = max(stop_floor, candidate)
      - Stop floor never decreases.
    """
    new_hwm = max(state.hwm, current_premium)
    new_armed = state.armed
    new_arm_floor = state.arm_floor
    new_stop_floor = state.stop_floor

    arm_premium = state.entry_premium * (1.0 + state.threshold_pct)
    if not state.armed and current_premium >= arm_premium:
        new_armed = True
        new_arm_floor = state.entry_premium * (1.0 + state.stop_offset_pct)
        if new_arm_floor > new_stop_floor:
            new_stop_floor = new_arm_floor

    if new_armed and state.mode == "trailing":
        trail_floor = new_hwm * (1.0 - state.trail_pct)
        candidate = max(new_arm_floor or 0.0, trail_floor)
        if candidate > new_stop_floor:
            new_stop_floor = candidate

    return replace(
        state,
        hwm=new_hwm,
        armed=new_armed,
        arm_floor=new_arm_floor,
        stop_floor=new_stop_floor,
    )


def stop_triggered(state: ProfitLockState, current_premium: float) -> bool:
    """A bar at `current_premium` trips the stop iff current <= stop_floor."""
    return current_premium <= state.stop_floor
