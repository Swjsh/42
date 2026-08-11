"""entry_manager -- the SHARED live entry state machine (entry-2's machinery, T-W5).

THE GAP THIS CLOSES: today's ONLY entry policy (both lanes) is a marketable simple limit
`ask + entry_cross_buffer` (heartbeat_core:1140 -> fleet_broker.marketable_limit_price) --
no premium floor, no passive/patience logic anywhere (verified: no entry_manager*.py
existed in the repo before this file). T3 (entry-exit-matrix-t3-entries.md) found a
passive limit at `signal_premium*(1-delta)` beats paying up NET of the real misses, when
paired with a stop+reachable-target exit (the 741P exhibit: market@0.96 -> limit@0.77
turned -$57.60 into +$231.00 on the identical shipped exit shape).

THIS MODULE mirrors exit_manager.py's split: a PURE decision core (`plan_entry_action`,
unit-tested, no I/O, no placement) + (eventually) a thin live actuator the caller wires to
the broker. Ports t3_entry_matrix.entry_fill's fill/miss/convert/patience semantics
tick-wise (one decision per tick against the live ask, instead of scanning cached 5-min
bars) -- see test_entry_manager.py for the parity proof against the backtest function.

STATUS: SHADOW ONLY (2026-07-08). No arm places an order through this module yet.
shadow_entry_actuator.py drives it read-only: for each REAL engine entry, replay what
entry-2 (delta=0.10, patience=3, policy=cancel per the frozen pre-registration) WOULD have
done, logged to automation/state/entry-shadow.jsonl -- fill-rate + basis-delta vs the real
ask+$0.03 fills (sim-live parity check BEFORE T6 trusts the T3 backtest numbers).

FILL RULE (mirrors t3_entry_matrix.entry_fill's `bar_low <= L - 0.01`): a resting BUY limit
at `limit_price` fills once the market's current ask has dropped to (or below) the limit,
by the SAME $0.01 tolerance as the backtest's bar-low check -- the live tick-sampled analog
of "did the bar dip enough to fill".
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

_FILL_TOLERANCE = 0.01     # matches t3_entry_matrix.entry_fill's `L - 0.01`


@dataclass(frozen=True)
class EntryState:
    """The minimal persisted state for ONE pending passive entry. Immutable -- a tick
    returns a NEW EntryState (coding-style: never mutate)."""
    symbol: str
    side: str                       # "P" | "C"
    signal_premium: float
    delta: float                    # e.g. 0.10 (limit = signal*(1-delta))
    limit_price: float
    patience_ticks: int             # e.g. 3
    policy: str                     # "cancel" | "convert"
    elapsed_ticks: int = 0
    placed_order_id: Optional[str] = None
    status: str = "pending"         # "pending" | "filled" | "missed" | "converted"
    fill_price: Optional[float] = None

    @staticmethod
    def from_signal(*, symbol: str, side: str, signal_premium: float, delta: float,
                    patience_ticks: int, policy: str) -> "EntryState":
        if policy not in ("cancel", "convert"):
            raise ValueError(f"policy must be 'cancel' or 'convert', got {policy!r}")
        limit_price = round(float(signal_premium) * (1.0 - float(delta)), 4)
        return EntryState(
            symbol=symbol, side=side, signal_premium=float(signal_premium),
            delta=float(delta), limit_price=limit_price,
            patience_ticks=int(patience_ticks), policy=policy,
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "side": self.side, "signal_premium": self.signal_premium,
            "delta": self.delta, "limit_price": self.limit_price,
            "patience_ticks": self.patience_ticks, "policy": self.policy,
            "elapsed_ticks": self.elapsed_ticks, "placed_order_id": self.placed_order_id,
            "status": self.status, "fill_price": self.fill_price,
        }


@dataclass(frozen=True)
class EntryAction:
    """ONE action this tick. The (future) actuator turns PLACE_LIMIT into a resting limit
    order, CONVERT into a marketable order, CANCEL into cancelling the resting order; HOLD
    does nothing."""
    kind: str          # "PLACE_LIMIT" | "HOLD" | "CANCEL" | "CONVERT"
    price: Optional[float] = None
    reason: str = ""


@dataclass(frozen=True)
class EntryDecision:
    """The tick result: the NEW state to persist + the action to execute."""
    state: EntryState
    action: EntryAction


def plan_entry_action(state: EntryState, *, ask: float) -> EntryDecision:
    """ONE tick of the passive-entry walk -- a tick-wise port of t3_entry_matrix.entry_fill.

    ask: current best ask (or last trade) for the contract this tick. Pure -- no I/O, no
    placement, idempotent on a missed tick (state carries elapsed_ticks so a re-fire from
    the same persisted state resumes correctly, mirroring exit_manager's design).

    Tick counting matches entry_fill's `for i in range(patience)` exactly: patience_ticks
    checks are performed (this tick's check is the Nth), and if none filled, the policy
    resolves on THIS SAME tick (no extra tick needed) -- patience_ticks=3 resolves after
    the 3rd check, same as checking bars[0..2] in one backtest pass.
    """
    if state.status != "pending":
        return EntryDecision(state=state, action=EntryAction("HOLD", reason=f"already {state.status}"))

    filled = ask <= state.limit_price - _FILL_TOLERANCE
    checks_done = (1 if state.placed_order_id is None else state.elapsed_ticks + 1)

    if state.placed_order_id is None:
        base = replace(state, placed_order_id="SHADOW", elapsed_ticks=checks_done)
        place_reason = "initial placement"
    else:
        base = replace(state, elapsed_ticks=checks_done)
        place_reason = None

    if filled:
        return EntryDecision(state=replace(base, status="filled", fill_price=state.limit_price),
                             action=EntryAction("PLACE_LIMIT" if place_reason else "HOLD",
                                                price=state.limit_price if place_reason else None,
                                                reason="filled same tick" if place_reason else "filled"))

    if checks_done < state.patience_ticks:
        return EntryDecision(state=base,
                             action=EntryAction("PLACE_LIMIT" if place_reason else "HOLD",
                                                price=state.limit_price if place_reason else None,
                                                reason=place_reason or f"patience {checks_done}/{state.patience_ticks}"))

    # Patience exhausted (checks_done >= patience_ticks), still not filled.
    if state.policy == "convert":
        return EntryDecision(state=replace(base, status="converted", fill_price=ask),
                             action=EntryAction("CONVERT", price=ask,
                                                reason="patience exhausted -> marketable"))
    return EntryDecision(state=replace(base, status="missed"),
                         action=EntryAction("CANCEL", reason="patience exhausted -> miss"))
