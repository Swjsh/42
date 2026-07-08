"""Deterministic futures exit-manager — the MISSING piece of the futures loop.

The futures order-path (TastytradeBroker.place_bracket) is code-complete + dry-run proven,
but nothing MANAGES the bracket after entry. This module is the pure-logic exit brain: given
an open position's shape (entry/stop/tp1/runner) and the latest price, it decides the ONE next
exit action per tick. It mirrors the exit doctrine already validated in futures_sim.simulate_futures:

    - full stop before TP1              -> FULL_STOP     (exit all qty at stop)
    - TP1 touched (pre-TP1)             -> TP1_PARTIAL   (exit tp1_qty; move stop to break-even)
    - after TP1, runner target touched  -> RUNNER_TARGET (exit remaining runner qty)
    - after TP1, break-even stop touched -> RUNNER_BE_STOP (exit remaining runner qty)
    - at/after the hard time-stop        -> TIME_STOP     (flatten everything)
    - otherwise                          -> HOLD

Pure + deterministic + stateless-per-call: the caller owns persisted position state (position.json)
and passes it in; this returns an (action, new_state) pair. No broker, no I/O, no clock reads inside
the decision — the caller supplies now_et and price, so every branch is unit-testable and red-proofable.

Direction is "long"|"short"; qty in contracts. tp1_filled tracks whether the partial already fired
(so a re-touch of TP1 doesn't double-exit). Break-even = entry once TP1 is filled (mirrors sim's
`stopc = entry`).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from typing import Optional

# Exit action codes (stable strings; the tick + guards match on these).
HOLD = "HOLD"
FULL_STOP = "FULL_STOP"
TP1_PARTIAL = "TP1_PARTIAL"
RUNNER_TARGET = "RUNNER_TARGET"
RUNNER_BE_STOP = "RUNNER_BE_STOP"
TIME_STOP = "TIME_STOP"

# Actions that leave the position CLOSED (nothing left to manage).
_CLOSING = {FULL_STOP, RUNNER_TARGET, RUNNER_BE_STOP, TIME_STOP}

DEFAULT_TIME_STOP_ET = dt.time(15, 50)  # hard flatten (EOD task is the backstop)


@dataclass(frozen=True)
class ExitPlan:
    """One tick's exit decision. Immutable (coding-style: never mutate state in place)."""
    action: str                 # one of the codes above
    exit_qty: int               # contracts to exit THIS action (0 for HOLD)
    exit_side: str              # broker close side: "SELL" to close a long, "BUY" to close a short
    reason: str
    new_state: "FuturesExitState"   # position state AFTER applying this action

    @property
    def is_closing(self) -> bool:
        return self.action in _CLOSING or (self.action == TP1_PARTIAL and self.new_state.qty_open <= 0)

    def to_dict(self) -> dict:
        return {"action": self.action, "exit_qty": self.exit_qty, "exit_side": self.exit_side,
                "reason": self.reason, "position_after": self.new_state.to_dict()}


@dataclass(frozen=True)
class FuturesExitState:
    """Persisted per-position exit state (what position.json carries)."""
    instrument: str
    direction: str              # "long" | "short"
    entry: float
    stop: float                 # CURRENT stop (moves to break-even after TP1)
    tp1: float
    runner: Optional[float]
    qty_total: int              # original total contracts
    qty_open: int               # contracts still open
    tp1_qty: int                # contracts allocated to the TP1 scale-out
    tp1_filled: bool = False
    entry_time_et: str = ""

    def to_dict(self) -> dict:
        return {"instrument": self.instrument, "direction": self.direction, "entry": self.entry,
                "stop": self.stop, "tp1": self.tp1, "runner": self.runner,
                "qty_total": self.qty_total, "qty_open": self.qty_open, "tp1_qty": self.tp1_qty,
                "tp1_filled": self.tp1_filled, "entry_time_et": self.entry_time_et}

    @classmethod
    def from_dict(cls, d: dict) -> "FuturesExitState":
        return cls(
            instrument=str(d.get("instrument", "")),
            direction=str(d.get("direction", "long")),
            entry=float(d.get("entry", 0.0)),
            stop=float(d.get("stop", 0.0)),
            tp1=float(d.get("tp1", 0.0)),
            runner=(None if d.get("runner") is None else float(d["runner"])),
            qty_total=int(d.get("qty_total", 0)),
            qty_open=int(d.get("qty_open", 0)),
            tp1_qty=int(d.get("tp1_qty", 0)),
            tp1_filled=bool(d.get("tp1_filled", False)),
            entry_time_et=str(d.get("entry_time_et", "")),
        )


def open_state(*, instrument: str, direction: str, entry: float, stop: float, tp1: float,
               runner: Optional[float], qty_total: int, tp1_fraction: float = 0.5,
               entry_time_et: str = "") -> FuturesExitState:
    """Build the exit state at fill (mirrors simulate_futures tp1_qty = round(qty*frac), min 1)."""
    tp1_qty = max(1, int(round(qty_total * tp1_fraction)))
    tp1_qty = min(tp1_qty, qty_total)
    return FuturesExitState(
        instrument=instrument, direction=direction, entry=float(entry), stop=float(stop),
        tp1=float(tp1), runner=(None if runner is None else float(runner)),
        qty_total=int(qty_total), qty_open=int(qty_total), tp1_qty=int(tp1_qty),
        tp1_filled=False, entry_time_et=entry_time_et,
    )


def _close_side(direction: str) -> str:
    """Broker action to CLOSE the position (opposite of open)."""
    return "SELL" if direction == "long" else "BUY"


def _at_or_past_time_stop(now_et: dt.datetime, time_stop: dt.time) -> bool:
    return now_et.time() >= time_stop


def decide_exit(state: FuturesExitState, *, price: float, bar_high: Optional[float] = None,
                bar_low: Optional[float] = None, now_et: Optional[dt.datetime] = None,
                time_stop_et: dt.time = DEFAULT_TIME_STOP_ET) -> ExitPlan:
    """Decide the ONE next exit action for `state` given the latest price / bar extremes / clock.

    Uses bar_high/bar_low when supplied (a 5m bar can touch a level the close missed — matches the
    sim's high/low touch logic); falls back to `price` for both when they're absent (live last-trade).
    Priority per tick (checked in this order, at most one action fires):
      1. TIME_STOP  — at/after the hard time-stop, flatten everything unconditionally.
      2. Stop leg   — FULL_STOP (pre-TP1) or RUNNER_BE_STOP (post-TP1). Stop-before-target on a
                      bar that touches both is the conservative assumption (mirrors the sim's ordering
                      for the pre-TP1 stop; adverse-first is the safe convention for a manager).
      3. Target leg — TP1_PARTIAL (pre-TP1) or RUNNER_TARGET (post-TP1).
      4. HOLD.
    Fail-safe: a flat/empty state (qty_open<=0) always returns HOLD with 0 qty."""
    if state.qty_open <= 0:
        return ExitPlan(HOLD, 0, _close_side(state.direction), "already_flat", state)

    hi = float(bar_high) if bar_high is not None else float(price)
    lo = float(bar_low) if bar_low is not None else float(price)
    long = state.direction == "long"
    close_side = _close_side(state.direction)

    # 1. TIME STOP — unconditional flatten.
    if now_et is not None and _at_or_past_time_stop(now_et, time_stop_et):
        flat = replace(state, qty_open=0)
        return ExitPlan(TIME_STOP, state.qty_open, close_side,
                        f"time_stop {time_stop_et.isoformat()} reached", flat)

    # 2. STOP leg (adverse first).
    stop_hit = (lo <= state.stop) if long else (hi >= state.stop)
    if stop_hit:
        if not state.tp1_filled:
            flat = replace(state, qty_open=0)
            return ExitPlan(FULL_STOP, state.qty_open, close_side,
                            f"stop {state.stop} hit pre-TP1 (full loss)", flat)
        # post-TP1 stop = break-even stop on the runner
        flat = replace(state, qty_open=0)
        return ExitPlan(RUNNER_BE_STOP, state.qty_open, close_side,
                        f"break-even stop {state.stop} hit on runner", flat)

    # 3. TARGET leg.
    if state.tp1_filled:
        # runner target
        if state.runner is not None:
            runner_hit = (hi >= state.runner) if long else (lo <= state.runner)
            if runner_hit:
                flat = replace(state, qty_open=0)
                return ExitPlan(RUNNER_TARGET, state.qty_open, close_side,
                                f"runner target {state.runner} hit", flat)
        return ExitPlan(HOLD, 0, close_side, "runner riding", state)

    # pre-TP1: check TP1 touch
    tp1_hit = (hi >= state.tp1) if long else (lo <= state.tp1)
    if tp1_hit:
        exit_qty = min(state.tp1_qty, state.qty_open)
        remaining = state.qty_open - exit_qty
        # scale out tp1_qty; move stop to break-even (entry) on the runner (mirrors sim's stopc=entry)
        new = replace(state, qty_open=remaining, tp1_filled=True, stop=state.entry)
        return ExitPlan(TP1_PARTIAL, exit_qty, close_side,
                        f"TP1 {state.tp1} touched — scale {exit_qty}, stop->BE {state.entry}", new)

    return ExitPlan(HOLD, 0, close_side, "in trade, no level touched", state)
