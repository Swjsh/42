"""exit_manager -- the SHARED live exit/scale-out state machine (the HARD GATE).

THE GAP THIS CLOSES (J hard requirement 2): the validated edge IS its exit. The
simulator (`backtest/lib/simulator_real.py:simulate_trade_real`, the source of truth for
every ratified exit shape) runs a 5-stage lifecycle per trade:

  1. ENTRY: qty split into tp1_qty = int(qty * tp1_qty_fraction) and runner_qty = rest.
  2. PRE-TP1 hard exits on ALL units: premium stop (worst <= entry*(1+premium_stop_pct)),
     ribbon-flip-back, level stop, 15:50 time stop.
  3. TP1 partial: best_premium >= entry*(1+tp1_premium_pct) -> SELL tp1_qty, ratchet the
     runner stop to BREAK-EVEN (entry_premium).
  4. RUNNER ride with profit-lock: the runner trails per profit_lock_mode -- "fixed"
     (BE-ish floor) or "trailing" (chandelier: floor = HWM*(1-trail_pct)) -- targeting
     entry*(1+runner_target_premium_pct).
  5. TIME STOP 15:50 force-closes the remainder (the EOD-flatten task is the live backstop).

Both live order paths today place only stage 1 + a single full-qty TP + a single stop --
stages 3/4/5 do not exist live, so the live order throws away the validated edge.

Alpaca's native bracket is single-TP/single-stop and cannot express a partial scale-out
or a trailing-then-fixed runner (confirmed in fleet_broker.place_bracket). So this module
implements the simulator walk as a TICK-MANAGED state machine: ONE decision per tick
against the live premium, reconstructing runner state each tick from the broker position +
the persisted per-position exit record (broker = source of truth, C11). Survives a missed
tick -- the next tick re-derives state.

SPLIT: a PURE decision core (`plan_exit_actions`, unit-tested, no I/O) and a thin live
actuator (the caller wires the broker). This file is the pure core ONLY -- it places
nothing, imports no broker, has no network. DRY: both heartbeat_core and fleet import it.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import time as _time
from typing import Optional, Sequence

# Canonical exit constants (mirror simulator.py:71-74 / simulator_real defaults). The exit
# shape carries the per-strategy overrides; these are the production-default fallbacks.
TIME_STOP_ET = _time(15, 50)
DEFAULT_RUNNER_TARGET_PCT = 2.5     # CLAUDE.md: runner target 2.5x
DEFAULT_TRAIL_PCT = 0.125           # WP-6 (chandelier trail 0.125; arms at +5% favor)
DEFAULT_PROFIT_LOCK_ARM_PCT = 0.05  # CLAUDE.md: chandelier arms at +5% favor
CATASTROPHE_STOP_PCT = -0.50        # -50% catastrophe cap both sides (chart-stop-primary)


# --- the per-position persisted record (broker is the source of truth for qty/flat) ----
@dataclass(frozen=True)
class ExitState:
    """The minimal persisted state for ONE managed position. Everything else (current
    premium, open qty, flat) is read live from the broker each tick. Immutable -- a tick
    returns a NEW ExitState (coding-style: never mutate)."""
    symbol: str
    side: str                       # "P" | "C"
    entry_premium: float
    total_qty: int
    tp1_qty: int                    # int(total_qty * tp1_qty_fraction)
    runner_qty: int                 # total_qty - tp1_qty
    # exit-shape (per-strategy, frozen at entry):
    premium_stop_pct: float         # negative, e.g. -0.20
    tp1_premium_pct: float          # e.g. +1.5
    profit_lock_mode: str           # "fixed" | "trailing"
    runner_target_pct: float = DEFAULT_RUNNER_TARGET_PCT
    trail_pct: float = DEFAULT_TRAIL_PCT
    profit_lock_arm_pct: float = DEFAULT_PROFIT_LOCK_ARM_PCT
    # evolving state (reconstructed/updated each tick):
    tp1_filled: bool = False
    runner_stop_premium: Optional[float] = None  # set at entry to entry*(1+premium_stop_pct)
    hwm_premium: Optional[float] = None          # high-water mark of best premium seen
    profit_lock_armed: bool = False
    strategy: str = ""

    @staticmethod
    def from_entry(*, symbol: str, side: str, entry_premium: float, qty: int,
                   exit_shape: dict, strategy: str = "") -> "ExitState":
        """Build the entry-time record from the placed order + the strategy's ExitShape.

        Splits qty exactly like simulator_real:465-466 (int floor on tp1) and seeds the
        runner stop at the catastrophe-guarded premium stop. Used by the live actuator
        right after place_bracket fills."""
        frac = float(exit_shape.get("tp1_qty_fraction", 0.667))
        tp1_qty = int(qty * frac)
        runner_qty = qty - tp1_qty
        stop_pct = exit_shape.get("premium_stop_pct")
        stop_pct = float(stop_pct) if stop_pct not in (None, 0) else CATASTROPHE_STOP_PCT
        # guard: a too-tight/invalid stop -> catastrophe cap (mirrors _place_live's guard)
        if stop_pct >= 0:
            stop_pct = CATASTROPHE_STOP_PCT
        return ExitState(
            symbol=symbol, side=side, entry_premium=float(entry_premium),
            total_qty=int(qty), tp1_qty=int(tp1_qty), runner_qty=int(runner_qty),
            premium_stop_pct=stop_pct,
            tp1_premium_pct=float(exit_shape.get("tp1_premium_pct", 0.30)),
            profit_lock_mode=str(exit_shape.get("profit_lock_mode", "fixed")),
            runner_target_pct=float(exit_shape.get("runner_target_pct", DEFAULT_RUNNER_TARGET_PCT)),
            trail_pct=float(exit_shape.get("trail_pct", DEFAULT_TRAIL_PCT)),
            profit_lock_arm_pct=float(exit_shape.get("profit_lock_arm_pct", DEFAULT_PROFIT_LOCK_ARM_PCT)),
            tp1_filled=False,
            runner_stop_premium=round(float(entry_premium) * (1.0 + stop_pct), 4),
            hwm_premium=float(entry_premium),
            profit_lock_armed=False,
            strategy=strategy,
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "side": self.side, "entry_premium": self.entry_premium,
            "total_qty": self.total_qty, "tp1_qty": self.tp1_qty, "runner_qty": self.runner_qty,
            "premium_stop_pct": self.premium_stop_pct, "tp1_premium_pct": self.tp1_premium_pct,
            "profit_lock_mode": self.profit_lock_mode, "runner_target_pct": self.runner_target_pct,
            "trail_pct": self.trail_pct, "profit_lock_arm_pct": self.profit_lock_arm_pct,
            "tp1_filled": self.tp1_filled, "runner_stop_premium": self.runner_stop_premium,
            "hwm_premium": self.hwm_premium, "profit_lock_armed": self.profit_lock_armed,
            "strategy": self.strategy,
        }

    @staticmethod
    def from_dict(d: dict) -> "ExitState":
        return ExitState(
            symbol=d["symbol"], side=d["side"], entry_premium=float(d["entry_premium"]),
            total_qty=int(d["total_qty"]), tp1_qty=int(d["tp1_qty"]), runner_qty=int(d["runner_qty"]),
            premium_stop_pct=float(d["premium_stop_pct"]), tp1_premium_pct=float(d["tp1_premium_pct"]),
            profit_lock_mode=str(d["profit_lock_mode"]),
            runner_target_pct=float(d.get("runner_target_pct", DEFAULT_RUNNER_TARGET_PCT)),
            trail_pct=float(d.get("trail_pct", DEFAULT_TRAIL_PCT)),
            profit_lock_arm_pct=float(d.get("profit_lock_arm_pct", DEFAULT_PROFIT_LOCK_ARM_PCT)),
            tp1_filled=bool(d.get("tp1_filled", False)),
            runner_stop_premium=(None if d.get("runner_stop_premium") is None
                                 else float(d["runner_stop_premium"])),
            hwm_premium=(None if d.get("hwm_premium") is None else float(d["hwm_premium"])),
            profit_lock_armed=bool(d.get("profit_lock_armed", False)),
            strategy=str(d.get("strategy", "")),
        )


@dataclass(frozen=True)
class ExitAction:
    """ONE action this tick. The actuator turns SELL_PARTIAL/SELL_ALL into market sells and
    RATCHET_STOP into a replace_order; HOLD does nothing. qty is the contracts to sell."""
    kind: str          # "SELL_PARTIAL" | "SELL_ALL" | "RATCHET_STOP" | "HOLD"
    qty: int = 0
    reason: str = ""
    new_stop_premium: Optional[float] = None
    stage: str = ""    # "tp1" | "runner_target" | "premium_stop" | "time_stop" | "trail" | ""


@dataclass(frozen=True)
class ExitDecision:
    """The tick result: the NEW state to persist + the ordered actions to execute."""
    state: ExitState
    actions: Sequence[ExitAction] = field(default_factory=tuple)

    @property
    def closes_position(self) -> bool:
        return any(a.kind == "SELL_ALL" for a in self.actions)


# --- the PURE decision core --------------------------------------------------------------
def plan_exit_actions(
    state: ExitState,
    *,
    best_premium: float,
    worst_premium: float,
    open_qty: int,
    now_et: _time,
    ribbon_flip_back: bool = False,
    time_stop_et: _time = TIME_STOP_ET,
) -> ExitDecision:
    """ONE tick of the live exit walk -- a faithful per-tick port of simulator_real's bar
    loop, evaluated against the live position instead of looping cached bars.

    Inputs (all read live by the caller, broker = source of truth):
      best_premium / worst_premium : this tick's option bar high / low (or last+spread).
      open_qty                     : contracts the broker still shows open for this symbol.
      now_et                       : current ET wall-clock time (for the 15:50 time stop).
      ribbon_flip_back             : True if the opposite ribbon stack invalidated the trade
                                     (caller computes from the live ribbon, same rule as sim).

    Returns an ExitDecision: the new ExitState to persist + the actions to place. Pure --
    no I/O, no placement. Idempotent on a missed tick: state is reconstructed each call so a
    re-fire derives the same actions from the same broker truth.
    """
    actions: list[ExitAction] = []

    # Position already flat (broker truth) -> nothing to manage.
    if open_qty <= 0:
        return ExitDecision(state=state, actions=())

    entry = state.entry_premium
    hwm = max(state.hwm_premium if state.hwm_premium is not None else entry, best_premium)
    runner_stop = state.runner_stop_premium
    if runner_stop is None:
        runner_stop = entry * (1.0 + state.premium_stop_pct)
    profit_lock_armed = state.profit_lock_armed

    time_stop_now = now_et >= time_stop_et

    # ── PRE-TP1: hard exits apply to ALL open units (simulator_real:642-708) ──────────
    if not state.tp1_filled:
        # (a) premium stop -> exit ALL
        if worst_premium <= runner_stop:
            actions.append(ExitAction("SELL_ALL", qty=open_qty,
                                      reason=f"premium_stop @ {round(runner_stop,2)}",
                                      stage="premium_stop"))
            return ExitDecision(replace(state, hwm_premium=hwm), tuple(actions))
        # (b) time stop pre-TP1 -> exit ALL at market
        if time_stop_now:
            actions.append(ExitAction("SELL_ALL", qty=open_qty,
                                      reason="time_stop_15:50", stage="time_stop"))
            return ExitDecision(replace(state, hwm_premium=hwm), tuple(actions))
        # (c) ribbon-flip-back -> exit ALL at market (caller already applied spread+buffer rule)
        if ribbon_flip_back:
            actions.append(ExitAction("SELL_ALL", qty=open_qty,
                                      reason="ribbon_flip_back", stage="ribbon_flip"))
            return ExitDecision(replace(state, hwm_premium=hwm), tuple(actions))
        # (d) TP1 partial: best >= entry*(1+tp1_premium_pct) -> SELL tp1_qty, runner stop -> BE
        tp1_level = entry * (1.0 + state.tp1_premium_pct)
        if best_premium >= tp1_level and state.tp1_qty > 0:
            sell_n = min(state.tp1_qty, open_qty)
            actions.append(ExitAction("SELL_PARTIAL", qty=sell_n,
                                      reason=f"tp1 @ +{int(state.tp1_premium_pct*100)}%",
                                      stage="tp1"))
            # ratchet runner stop to break-even (simulator_real:738)
            be = entry
            new_state = replace(state, tp1_filled=True, hwm_premium=hwm,
                                runner_stop_premium=round(be, 4), profit_lock_armed=True)
            actions.append(ExitAction("RATCHET_STOP", reason="runner_stop->BE",
                                      new_stop_premium=round(be, 4), stage="tp1"))
            return ExitDecision(new_state, tuple(actions))
        # no exit, no TP1 -> just update the HWM
        return ExitDecision(replace(state, hwm_premium=hwm), tuple(actions))

    # ── POST-TP1: runner ride with profit-lock (simulator_real:540-839) ──────────────
    # profit-lock: arm at +arm_pct favorable, then fixed (BE floor) or trailing (chandelier).
    arm_level = entry * (1.0 + state.profit_lock_arm_pct)
    new_runner_stop = runner_stop
    if not profit_lock_armed and best_premium >= arm_level:
        profit_lock_armed = True
        floor = entry  # BE floor at arm (runner already ratcheted to BE at TP1)
        new_runner_stop = max(new_runner_stop, floor)
    if profit_lock_armed and state.profit_lock_mode == "trailing":
        trail_floor = hwm * (1.0 - state.trail_pct)
        new_runner_stop = max(new_runner_stop, trail_floor)
    # else fixed: BE floor already applied; no further movement.

    ratcheted = round(new_runner_stop, 4) > round(runner_stop, 4)

    # runner exits (priority: ribbon-flip / runner-target / BE-or-trail stop / time stop)
    if ribbon_flip_back:
        actions.append(ExitAction("SELL_ALL", qty=open_qty,
                                  reason="ribbon_flip_back (runner)", stage="ribbon_flip"))
        return ExitDecision(replace(state, hwm_premium=hwm, profit_lock_armed=profit_lock_armed,
                                    runner_stop_premium=round(new_runner_stop, 4)), tuple(actions))
    runner_target = entry * (1.0 + state.runner_target_pct)
    if best_premium >= runner_target:
        actions.append(ExitAction("SELL_ALL", qty=open_qty,
                                  reason=f"runner_target @ +{int(state.runner_target_pct*100)}%",
                                  stage="runner_target"))
        return ExitDecision(replace(state, hwm_premium=hwm, profit_lock_armed=profit_lock_armed,
                                    runner_stop_premium=round(new_runner_stop, 4)), tuple(actions))
    if worst_premium <= new_runner_stop:
        actions.append(ExitAction("SELL_ALL", qty=open_qty,
                                  reason=f"runner_stop @ {round(new_runner_stop,2)}",
                                  stage="trail" if state.profit_lock_mode == "trailing" else "be_stop"))
        return ExitDecision(replace(state, hwm_premium=hwm, profit_lock_armed=profit_lock_armed,
                                    runner_stop_premium=round(new_runner_stop, 4)), tuple(actions))
    if time_stop_now:
        actions.append(ExitAction("SELL_ALL", qty=open_qty,
                                  reason="time_stop_15:50 (runner)", stage="time_stop"))
        return ExitDecision(replace(state, hwm_premium=hwm, profit_lock_armed=profit_lock_armed,
                                    runner_stop_premium=round(new_runner_stop, 4)), tuple(actions))

    # no runner exit; persist the ratchet if the floor moved up
    if ratcheted:
        actions.append(ExitAction("RATCHET_STOP", reason="runner_stop trail/arm",
                                  new_stop_premium=round(new_runner_stop, 4),
                                  stage="trail" if state.profit_lock_mode == "trailing" else "arm"))
    return ExitDecision(replace(state, hwm_premium=hwm, profit_lock_armed=profit_lock_armed,
                                runner_stop_premium=round(new_runner_stop, 4)), tuple(actions))
