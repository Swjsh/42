"""kill_switch — daily-loss circuit breaker (latching, monotonic).

Production source-of-truth:
  params_safe.json#daily_loss_kill_switch_pct = 0.30 (-30%)
  params_bold.json#daily_loss_kill_switch_pct = 0.50 (-50%)

Semantics:
  - State is keyed by account_id (caller decides — Safe/Bold are independent
    per CLAUDE.md "Kill switches isolated").
  - Threshold breached iff current_equity <= start_of_day_equity * (1 - threshold_pct).
  - Once tripped, STAYS TRIPPED for the rest of the trading day. Recovery
    (equity rising above threshold) does NOT un-trip. This is the critical
    foot-gun the validator guards against.
  - Per-tick consumption: caller passes start_of_day_equity, current_equity,
    threshold_pct, and a prior `KillSwitchState` (None on day-start).
    Returns the new state.

Module is pure functions. No I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional


@dataclass(frozen=True, slots=True)
class KillSwitchState:
    account_id: str
    start_of_day_equity: float
    threshold_pct: float
    tripped: bool
    tripped_at_equity: Optional[float]  # snapshot at first trip
    min_equity_seen: float              # for diagnostics

    def __post_init__(self) -> None:
        if self.start_of_day_equity <= 0:
            raise ValueError(f"start_of_day_equity must be positive, got {self.start_of_day_equity}")
        if not (0 < self.threshold_pct < 1):
            raise ValueError(f"threshold_pct must be in (0, 1), got {self.threshold_pct}")


def initial_state(account_id: str, start_of_day_equity: float, threshold_pct: float) -> KillSwitchState:
    return KillSwitchState(
        account_id=account_id,
        start_of_day_equity=start_of_day_equity,
        threshold_pct=threshold_pct,
        tripped=False,
        tripped_at_equity=None,
        min_equity_seen=start_of_day_equity,
    )


def threshold_equity(state: KillSwitchState) -> float:
    """The equity floor at which the switch trips. <= floor means tripped."""
    return state.start_of_day_equity * (1.0 - state.threshold_pct)


def tick(state: KillSwitchState, current_equity: float) -> KillSwitchState:
    """Process one equity reading. Returns new state.

    Latching: once tripped, stays tripped even if current_equity recovers.
    """
    new_min = min(state.min_equity_seen, current_equity)
    if state.tripped:
        return replace(state, min_equity_seen=new_min)
    floor = threshold_equity(state)
    if current_equity <= floor:
        return replace(
            state,
            tripped=True,
            tripped_at_equity=current_equity,
            min_equity_seen=new_min,
        )
    return replace(state, min_equity_seen=new_min)


def trading_allowed(state: KillSwitchState) -> bool:
    """Convenience: True iff the switch has NOT tripped."""
    return not state.tripped


def loss_pct(state: KillSwitchState, current_equity: float) -> float:
    """Current loss as a fraction of start-of-day equity (positive number = loss)."""
    return 1.0 - (current_equity / state.start_of_day_equity)
