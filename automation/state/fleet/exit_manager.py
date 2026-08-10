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


def parse_time_stop_et(value, default: _time = TIME_STOP_ET) -> _time:
    """Parse a params.json ``time_stop_et`` value ("HH:MM"[:SS] str, a datetime.time, or a
    {"hour","minute"} dict) into a datetime.time. FIX (2026-07-07): the live exit
    (exit_actuator.manage_tick) called plan_exit_actions WITHOUT time_stop_et, so the
    hard-coded 15:50 always won and the params key ``time_stop_et`` was a DEAD knob
    (see l117_time_stop_artifact / B10-EXIT). Any missing/malformed value fails SAFE to the
    doctrine default (15:50 -- the EOD-flatten backstop), never widening the stop past close.
    Guard: test_audit_fix_exit.py."""
    if value is None:
        return default
    if isinstance(value, _time):
        return value
    try:
        if isinstance(value, dict):
            return _time(int(value["hour"]), int(value.get("minute", 0)))
        parts = str(value).strip().split(":")
        hh = int(parts[0])
        mm = int(parts[1]) if len(parts) > 1 else 0
        ss = int(parts[2]) if len(parts) > 2 else 0
        if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
            return default
        return _time(hh, mm, ss)
    except (ValueError, TypeError, KeyError, IndexError):
        return default


DEFAULT_RUNNER_TARGET_PCT = 2.5     # CLAUDE.md: runner target 2.5x
DEFAULT_TRAIL_PCT = 0.125           # WP-6 (chandelier trail 0.125; arms at +5% favor)
DEFAULT_PROFIT_LOCK_ARM_PCT = 0.05  # CLAUDE.md: chandelier arms at +5% favor
CATASTROPHE_STOP_PCT = -0.50        # -50% catastrophe cap both sides (chart-stop-primary)

# PROFIT-LOCK ARM SCOPE (2026-07-09 scope-mismatch finding). simulator_real:540-584 arms
# the profit-lock on ANY favorable touch -- including BEFORE TP1, where the ratcheted stop
# IS the exit-ALL stop -- so every sim study passing profit_lock_threshold_pct>0 credited
# pre-TP1 breakeven scratches. This core only armed the lock at/after TP1, so those
# scorecards overstate live's downside protection. "post_tp1" (default) = the exact
# pre-existing live behavior; "full" = simulator-parity pre-TP1 arming (whole position gets
# the BE floor / trail from the first +arm_pct touch). NOTHING declares "full" until a
# live-machine scorecard + STOP-B arms it -- expressible, not armed.
ARM_SCOPE_POST_TP1 = "post_tp1"
ARM_SCOPE_FULL = "full"


def _norm_arm_scope(value) -> str:
    """Normalize a shape/persisted arm-scope value; anything not 'full' fails to legacy."""
    return ARM_SCOPE_FULL if str(value).strip().lower() == ARM_SCOPE_FULL else ARM_SCOPE_POST_TP1


# --- STRUCTURE-STOP (v15.3 chart-stop-primary, flag-gated OFF by default) ----------------
# The doctrine (CLAUDE.md "chart-stop-primary", 2026-06-18) names chart-level / ribbon-
# flip-back / chandelier profit-lock as the PRIMARY invalidation, with the premium stop
# demoted to a -50% catastrophe cap. Ribbon-flip-back has been live since G14; THIS is the
# missing "chart-level" leg -- exit on the first CLOSED 5m SPY bar beyond the level the
# setup's trigger reacted to. Fully additive + flag-gated: a position's stop_mode is
# resolved ONCE at from_entry (never flaps mid-trade) and every new field defaults to the
# exact today-behavior value, so this is inert until BOTH (a) a strategy's ExitShape
# declares stop_mode="structure" AND (b) the caller's structure_stop_enabled (sourced from
# params.json's structure_stop_enabled, default False/absent) is True at entry time.
def nearest_active_level(prices: Sequence[float], spot: Optional[float], side: str,
                         max_distance: float = 2.0) -> Optional[float]:
    """Best-effort trigger_level: the price in `prices` nearest to `spot`, DIRECTIONALLY
    filtered by `side` and within `max_distance`.

    side="P" (bear/rejection) only considers levels AT/ABOVE spot (the resistance a
    rejection setup just bounced off); side="C" (bull/reclaim) only considers levels
    AT/BELOW spot (the support a reclaim setup just broke above). This directional filter
    is a correctness guard, not a nicety: an unfiltered nearest-by-raw-distance could
    return a level on the WRONG side of spot (e.g. a support below a bear's entry), which
    would make the structure-stop's close-vs-level comparison true at/near entry -- a
    same-tick false exit. key-levels.json does not (yet) retain WHICH specific level a
    trigger matched (role/provenance tracking is unbuilt), so this is a proximity proxy for
    "the level this setup reacted to", not a lookup. None on empty/absent/malformed input;
    callers must treat a missing trigger_level as 'stay in premium-stop mode', never guess
    or block on it. Pure -- no I/O (callers supply the already-loaded price list).
    """
    if spot is None or not prices or side not in ("P", "C"):
        return None
    try:
        spot_f = float(spot)
    except (TypeError, ValueError):
        return None
    best: Optional[float] = None
    best_dist: Optional[float] = None
    for raw in prices:
        try:
            p = float(raw)
        except (TypeError, ValueError):
            continue
        if side == "P" and p < spot_f:
            continue   # bear needs the level AT/ABOVE spot (the rejected resistance)
        if side == "C" and p > spot_f:
            continue   # bull needs the level AT/BELOW spot (the reclaimed support)
        dist = abs(p - spot_f)
        if dist <= max_distance and (best_dist is None or dist < best_dist):
            best, best_dist = round(p, 2), dist
    return best


def _structure_stop_hit(side: str, trigger_level: Optional[float],
                        last_closed_5m_close: Optional[float]) -> bool:
    """v15.3 chart-stop-primary exit test: the first CLOSED 5m SPY bar beyond the trigger
    level -- calls (side C) exit when close < trigger_level, puts (side P) exit when
    close > trigger_level. False whenever either input is missing (fail-open: the caller's
    staleness guard already turns a stale/absent closed-bar feed into None for this tick;
    the catastrophe cap + time stop still protect the position on a skipped tick)."""
    if trigger_level is None or last_closed_5m_close is None:
        return False
    return (last_closed_5m_close < trigger_level) if side == "C" else (last_closed_5m_close > trigger_level)


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
    # STRUCTURE-STOP (flag-gated, resolved ONCE at from_entry -- never flaps mid-trade):
    stop_mode: str = "premium"              # "premium" (today) | "structure" (v15.3 chart-stop)
    trigger_level: Optional[float] = None   # the chart level structure-mode exits against
    catastrophe_stop_pct: float = CATASTROPHE_STOP_PCT  # the cap structure mode falls back to
    # PROFIT-LOCK ARM SCOPE (2026-07-09, appended last for positional compatibility):
    profit_lock_arm_scope: str = ARM_SCOPE_POST_TP1  # "post_tp1" (today) | "full" (sim parity)
    # ISOLATED PRE-TP1 BE FLOOR (2026-08-02, EXIT-HYBRID-PRETP1-FLOOR iteration 4 -- appended
    # last for positional compatibility). Independent of profit_lock_arm_scope/profit_lock_mode
    # entirely: arms a BREAKEVEN-ONLY floor pre-TP1 (never trails pre-TP1) without touching
    # profit_lock_armed, so the post-TP1 chandelier ride (profit_lock_mode="trailing", the
    # +$15,774/35-for-35 runner engine) is BYTE-IDENTICAL regardless of this knob -- unlike
    # profit_lock_mode="fixed" (iteration 3), which is read by both the pre-TP1 AND post-TP1
    # branches and silently disables post-TP1 trailing for any trade reaching TP1. None (the
    # default) is fully inert -- this is a NEW additive knob, no existing persisted
    # exit-state.json record or ExitShape declares it.
    pre_tp1_be_floor_arm_pct: Optional[float] = None
    # PROFIT RATCHET FLOOR LEVEL (2026-08-10, J-DIRECTED mid-session, rule-9 override by the
    # rule author -- his 3rd/4th escalation of "trailing stops", armed same day the three 773C
    # calls peaked +83/+91/+98% with zero protection and closed red, -$568 realized from a
    # +$970 open peak). Where pre_tp1_be_floor_arm_pct alone floors at ENTRY (breakeven, the
    # shape that FAILED G4 on 2026-08-02 by scratching pullback-then-run winners at $0), this
    # knob raises the armed floor to entry*(1 + pre_tp1_floor_pct) -- J's spec: arm high,
    # floor at "sixty or seventy percent" so a near-double can never round-trip red. None =
    # floor stays at entry (byte-identical to the 2026-08-02 semantics). Only meaningful when
    # pre_tp1_be_floor_arm_pct is also set. J's counter to the G4 veto, on the record: the
    # veto cohort was round-trip-to-entry-then-run trades ("that's not a good entry then...
    # pure gambling"), and a floored exit frees the arm to re-enter -- a counterfactual the
    # single-position replay never priced. Forward ledger decides.
    pre_tp1_floor_pct: Optional[float] = None

    @staticmethod
    def from_entry(*, symbol: str, side: str, entry_premium: float, qty: int,
                   exit_shape: dict, strategy: str = "",
                   trigger_level: Optional[float] = None,
                   structure_stop_enabled: bool = False) -> "ExitState":
        """Build the entry-time record from the placed order + the strategy's ExitShape.

        Splits qty exactly like simulator_real:465-466 (int floor on tp1) and seeds the
        runner stop at the catastrophe-guarded premium stop. Used by the live actuator
        right after place_bracket fills.

        STRUCTURE-STOP resolution (v15.3 chart-stop-primary, flag-gated): stop_mode is
        resolved HERE, ONCE, and never re-evaluated mid-trade (a position's exit contract
        must not shift shape because someone edits params.json while it is open). Entering
        "structure" mode requires ALL THREE: the shape declares stop_mode=="structure", the
        caller's structure_stop_enabled is True (params.json structure_stop_enabled, default
        False/absent), AND a trigger_level is available. Missing ANY of the three resolves
        to "premium" mode via the EXACT pre-existing math (byte-identical -- this is the
        inertness contract). In structure mode the premium stop is DEMOTED to the
        catastrophe cap (exit_shape's own catastrophe_stop_pct override, else the global
        CATASTROPHE_STOP_PCT); TP1/runner/trail math is untouched either way.
        """
        frac = float(exit_shape.get("tp1_qty_fraction", 0.667))
        tp1_qty = int(qty * frac)
        runner_qty = qty - tp1_qty
        cat_pct = exit_shape.get("catastrophe_stop_pct")
        cat_pct = float(cat_pct) if cat_pct not in (None,) else CATASTROPHE_STOP_PCT
        shape_mode = str(exit_shape.get("stop_mode", "premium")).lower()
        resolved_structure = (shape_mode == "structure" and bool(structure_stop_enabled)
                              and trigger_level is not None)
        if resolved_structure:
            stop_pct = cat_pct
            mode = "structure"
        else:
            stop_pct = exit_shape.get("premium_stop_pct")
            stop_pct = float(stop_pct) if stop_pct not in (None, 0) else CATASTROPHE_STOP_PCT
            # guard: a too-tight/invalid stop -> catastrophe cap (mirrors _place_live's guard)
            if stop_pct >= 0:
                stop_pct = CATASTROPHE_STOP_PCT
            mode = "premium"
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
            stop_mode=mode,
            trigger_level=(float(trigger_level) if trigger_level is not None else None),
            catastrophe_stop_pct=cat_pct,
            profit_lock_arm_scope=_norm_arm_scope(
                exit_shape.get("profit_lock_arm_scope", ARM_SCOPE_POST_TP1)),
            pre_tp1_be_floor_arm_pct=(
                None if exit_shape.get("pre_tp1_be_floor_arm_pct") is None
                else float(exit_shape["pre_tp1_be_floor_arm_pct"])),
            pre_tp1_floor_pct=(
                None if exit_shape.get("pre_tp1_floor_pct") is None
                else float(exit_shape["pre_tp1_floor_pct"])),
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
            "stop_mode": self.stop_mode, "trigger_level": self.trigger_level,
            "catastrophe_stop_pct": self.catastrophe_stop_pct,
            "profit_lock_arm_scope": self.profit_lock_arm_scope,
            "pre_tp1_be_floor_arm_pct": self.pre_tp1_be_floor_arm_pct,
            "pre_tp1_floor_pct": self.pre_tp1_floor_pct,
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
            # STRUCTURE-STOP fields (2026-07-09): absent on any pre-existing exit-state.json
            # record -> "premium"/None/global-cap, i.e. the exact legacy behavior (C14/L149
            # tolerance -- old persisted state must never crash or silently reinterpret).
            stop_mode=str(d.get("stop_mode", "premium")),
            trigger_level=(None if d.get("trigger_level") is None else float(d["trigger_level"])),
            catastrophe_stop_pct=float(d.get("catastrophe_stop_pct", CATASTROPHE_STOP_PCT)),
            # absent on any pre-2026-07-09 record -> "post_tp1", the exact legacy behavior
            profit_lock_arm_scope=_norm_arm_scope(d.get("profit_lock_arm_scope",
                                                        ARM_SCOPE_POST_TP1)),
            # absent on any pre-2026-08-02 record -> None, the exact legacy (inert) behavior
            pre_tp1_be_floor_arm_pct=(
                None if d.get("pre_tp1_be_floor_arm_pct") is None
                else float(d["pre_tp1_be_floor_arm_pct"])),
            pre_tp1_floor_pct=(
                None if d.get("pre_tp1_floor_pct") is None
                else float(d["pre_tp1_floor_pct"])),
        )


@dataclass(frozen=True)
class ExitAction:
    """ONE action this tick. The actuator turns SELL_PARTIAL/SELL_ALL into market sells and
    RATCHET_STOP into a replace_order; HOLD does nothing. qty is the contracts to sell."""
    kind: str          # "SELL_PARTIAL" | "SELL_ALL" | "RATCHET_STOP" | "HOLD"
    qty: int = 0
    reason: str = ""
    new_stop_premium: Optional[float] = None
    stage: str = ""    # "tp1" | "runner_target" | "premium_stop" | "profit_lock_floor" |
                        # "time_stop" | "trail" | "structure_stop" | ""


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
    last_closed_5m_close: Optional[float] = None,
) -> ExitDecision:
    """ONE tick of the live exit walk -- a faithful per-tick port of simulator_real's bar
    loop, evaluated against the live position instead of looping cached bars.

    Inputs (all read live by the caller, broker = source of truth):
      best_premium / worst_premium : this tick's option bar high / low (or last+spread).
      open_qty                     : contracts the broker still shows open for this symbol.
      now_et                       : current ET wall-clock time (for the time_stop_et time
                                     stop -- defaults to 15:50 but is params.json-configurable
                                     via parse_time_stop_et; the exit `reason` string reflects
                                     whichever value is ACTUALLY armed this tick, see
                                     EXITMGR-TIME-STOP-LABEL fix below).
      ribbon_flip_back             : True if the opposite ribbon stack invalidated the trade
                                     (caller computes from the live ribbon, same rule as sim).
      last_closed_5m_close         : the latest CLOSED 5m SPY bar's close, or None when the
                                     caller's feed is missing/stale (structure-stop's fail-
                                     open input -- see _structure_stop_hit). Only consulted
                                     when this position's stop_mode == "structure"; every
                                     existing caller omits it (None), so this is a no-op
                                     unless the position was ALSO seeded with stop_mode
                                     "structure" at from_entry.

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
        # (a0) PRE-TP1 PROFIT-LOCK -- scope=="full" ONLY (default "post_tp1" leaves this
        # tick byte-identical to the pre-2026-07-09 walk). Mirrors simulator_real:540-584:
        # arm on THIS tick's best (before the stop check, the simulator's intra-bar
        # ordering), BE floor at arm (offset 0), trailing mode ratchets off the HWM. The
        # ratcheted stop feeds the SAME (a) exit-ALL check the simulator's does.
        orig_stop = runner_stop
        if state.profit_lock_arm_scope == ARM_SCOPE_FULL:
            if (not profit_lock_armed
                    and best_premium >= entry * (1.0 + state.profit_lock_arm_pct)):
                profit_lock_armed = True
                runner_stop = max(runner_stop, entry)  # BE floor (simulator parity)
            if profit_lock_armed and state.profit_lock_mode == "trailing":
                runner_stop = max(runner_stop, hwm * (1.0 - state.trail_pct))
        # ISOLATED PRE-TP1 BE FLOOR (2026-08-02, EXIT-HYBRID-PRETP1-FLOOR iteration 4):
        # completely independent of profit_lock_arm_scope/profit_lock_mode/profit_lock_armed --
        # arms a BE floor ONLY (never trails further pre-TP1) the first tick best_premium
        # clears entry*(1+pre_tp1_be_floor_arm_pct). Deliberately does NOT set
        # profit_lock_armed=True (TP1 fill unconditionally sets it True itself at line ~456
        # regardless of this branch), so the post-TP1 chandelier ride is byte-identical to
        # CONTROL whether or not this knob is set. Inert (no-op) when None, the default.
        if (state.pre_tp1_be_floor_arm_pct is not None
                and best_premium >= entry * (1.0 + state.pre_tp1_be_floor_arm_pct)):
            # RATCHET LEVEL (2026-08-10, J-directed): when pre_tp1_floor_pct is set the armed
            # floor sits at entry*(1+floor_pct) -- bank a fixed majority of the move -- not at
            # breakeven. None preserves the 2026-08-02 BE semantics byte-identically. max()
            # keeps it a RATCHET: the floor can never be lowered by a later tick, and it can
            # only ever RAISE runner_stop, so the catastrophe/structure stops beneath are
            # untouched.
            _floor = entry * (1.0 + (state.pre_tp1_floor_pct or 0.0))
            runner_stop = max(runner_stop, _floor)
        lock_ratcheted = round(runner_stop, 4) > round(orig_stop, 4)
        if state.profit_lock_arm_scope == ARM_SCOPE_FULL or state.pre_tp1_be_floor_arm_pct is not None:
            pre_state = replace(state, hwm_premium=hwm, profit_lock_armed=profit_lock_armed,
                                runner_stop_premium=round(runner_stop, 4))
        else:
            pre_state = replace(state, hwm_premium=hwm)
        # (a) STRUCTURE STOP (v15.3 chart-stop-primary) -- checked BEFORE the premium/
        # catastrophe stop so that when BOTH conditions land on the SAME tick (a closed-5m
        # structure break AND a catastrophe premium touch), the STRUCTURE exit fires. This is
        # the VALIDATED ordering: structure_stop_study.replay_structure_aware checks its
        # ss_time FIRST, every bar, before any intrabar plan_exit_actions branch can run (see
        # that module's docstring: "nothing else in this bar could have fired first, because
        # the exit was already decided at the bar's open"). ssb-certification-2026-07-09.json
        # found this production branch ordered the OTHER way (catastrophe checked before
        # structure), producing REAL-DIVERGENCE on 2/10 same-tick positions that day (-$24.50
        # vs the certified SS-B cell). This swap conforms production to the certified cell --
        # not a new shape. Only active when from_entry resolved this position to stop_mode==
        # "structure" (flag-gated, see module docstring). last_closed_5m_close is None
        # whenever the caller's feed is missing/stale -> fail-open, this tick's structure
        # check is simply skipped (the catastrophe cap below and the time stop still protect
        # the position).
        if state.stop_mode == "structure" and _structure_stop_hit(
                state.side, state.trigger_level, last_closed_5m_close):
            actions.append(ExitAction("SELL_ALL", qty=open_qty,
                                      reason=f"structure_stop @ {state.trigger_level}",
                                      stage="structure_stop"))
            return ExitDecision(pre_state, tuple(actions))
        # (a2) premium/catastrophe stop -> exit ALL (structure mode: this IS the -50%
        # catastrophe cap, firing alone whenever NO structure break exists on this tick --
        # its whole job is protecting intrabar disasters BETWEEN closed 5m bars; premium
        # mode: the strategy's unchanged tight stop -- from_entry already baked the right
        # stop_pct into runner_stop, so this ONE check serves both modes verbatim.
        # scope=="full" + armed: runner_stop may now BE the profit-lock floor -- the reason
        # string discloses which stop actually fired).
        if worst_premium <= runner_stop:
            floor_active = (
                (profit_lock_armed and state.profit_lock_arm_scope == ARM_SCOPE_FULL
                 and runner_stop > entry * (1.0 + state.premium_stop_pct) + 1e-9)
                # ISOLATED PRE-TP1 BE FLOOR (2026-08-02): label this exit as a profit-lock
                # floor too, not the static catastrophe cap, when the isolated knob is the
                # reason runner_stop moved above the raw premium stop -- keeps mechanism
                # analytics (e.g. exit_manager_walk's reached_tp1/runner_mechanism helpers)
                # correct for this new knob exactly as they already are for arm_scope="full".
                or (state.pre_tp1_be_floor_arm_pct is not None
                    and runner_stop > entry * (1.0 + state.premium_stop_pct) + 1e-9)
            )
            # EXITMGR-STAGE-LABEL-CONFLATION fix (2026-07-23): stage now matches reason --
            # this was previously hardcoded "premium_stop" even when floor_active, silently
            # conflating the static -50% catastrophe cap with a pre-TP1 profit-lock-floor
            # scratch under profit_lock_arm_scope="full". Two distinct stage names now, so
            # exit-reason analytics (and any future journal-row consumer) can tell them apart
            # without re-parsing the human-readable `reason` string.
            reason = (f"profit_lock_floor @ {round(runner_stop,2)}" if floor_active
                      else f"premium_stop @ {round(runner_stop,2)}")
            actions.append(ExitAction("SELL_ALL", qty=open_qty, reason=reason,
                                      stage=("profit_lock_floor" if floor_active
                                             else "premium_stop")))
            return ExitDecision(pre_state, tuple(actions))
        # (b) time stop pre-TP1 -> exit ALL at market
        # EXITMGR-TIME-STOP-LABEL fix (2026-08-01, chip task_30a7b291): `reason` used to be
        # the hardcoded literal "time_stop_15:50" regardless of the ACTUAL time_stop_et this
        # call was given -- label-only bug (the mechanism itself, time_stop_now above, always
        # compared against the real configured value; only the human-readable string lied).
        # Live params.json has carried time_stop_et="15:40" since before this fix, so every
        # real 0DTE time-stop exit journaled a reason 10 minutes later than what actually
        # fired. stage stays the untouched machine-readable key ("time_stop") -- only the
        # prose reason now reports the value that was actually enforced this tick.
        if time_stop_now:
            actions.append(ExitAction("SELL_ALL", qty=open_qty,
                                      reason=f"time_stop_{time_stop_et.strftime('%H:%M')}",
                                      stage="time_stop"))
            return ExitDecision(pre_state, tuple(actions))
        # (c) ribbon-flip-back -> exit ALL at market. NOTE (corrected 2026-08-08): callers
        # apply NO spread/buffer rule -- both real callers (heartbeat_core._ribbon_flip_fn
        # live; exit_manager_walk replay) pass a bare single-tick categorical stack equality.
        # The prior comment claiming a caller-side "spread+buffer rule" was aspirational,
        # never implemented (verified by the 2026-08-08 ribbon-flipback-buffer prereg sweep).
        if ribbon_flip_back:
            actions.append(ExitAction("SELL_ALL", qty=open_qty,
                                      reason="ribbon_flip_back", stage="ribbon_flip"))
            return ExitDecision(pre_state, tuple(actions))
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
        # no exit, no TP1 -> update the HWM (+ persist/record the pre-TP1 lock ratchet,
        # scope=="full" only; tick-managed like the post-TP1 ratchet, see exit_actuator)
        if lock_ratcheted:
            actions.append(ExitAction("RATCHET_STOP", reason="pre_tp1 profit_lock arm/trail",
                                      new_stop_premium=round(runner_stop, 4),
                                      stage="trail" if state.profit_lock_mode == "trailing"
                                      else "arm"))
        return ExitDecision(pre_state, tuple(actions))

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

    # runner exits (priority: structure / ribbon-flip / runner-target / BE-or-trail stop / time
    # stop). Structure is checked FIRST -- same same-tick-priority invariant as the pre-TP1
    # branch above (ssb-certification-2026-07-09.json / 2026-07-09 ordering fix): on a tick
    # where BOTH a structure break and the BE-or-trail stop would fire, structure wins.
    if state.stop_mode == "structure" and _structure_stop_hit(
            state.side, state.trigger_level, last_closed_5m_close):
        actions.append(ExitAction("SELL_ALL", qty=open_qty,
                                  reason=f"structure_stop @ {state.trigger_level} (runner)",
                                  stage="structure_stop"))
        return ExitDecision(replace(state, hwm_premium=hwm, profit_lock_armed=profit_lock_armed,
                                    runner_stop_premium=round(new_runner_stop, 4)), tuple(actions))
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
    # EXITMGR-TIME-STOP-LABEL fix (2026-08-01, chip task_30a7b291) -- runner-stage twin of
    # the pre-TP1 fix above; same bug (hardcoded "15:50" label vs the real configured value).
    if time_stop_now:
        actions.append(ExitAction("SELL_ALL", qty=open_qty,
                                  reason=f"time_stop_{time_stop_et.strftime('%H:%M')} (runner)",
                                  stage="time_stop"))
        return ExitDecision(replace(state, hwm_premium=hwm, profit_lock_armed=profit_lock_armed,
                                    runner_stop_premium=round(new_runner_stop, 4)), tuple(actions))

    # no runner exit; persist the ratchet if the floor moved up
    if ratcheted:
        actions.append(ExitAction("RATCHET_STOP", reason="runner_stop trail/arm",
                                  new_stop_premium=round(new_runner_stop, 4),
                                  stage="trail" if state.profit_lock_mode == "trailing" else "arm"))
    return ExitDecision(replace(state, hwm_premium=hwm, profit_lock_armed=profit_lock_armed,
                                runner_stop_premium=round(new_runner_stop, 4)), tuple(actions))
