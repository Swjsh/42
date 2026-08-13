"""The SHARED strategy set — the validated edges every fleet account trades.

Architecture (J's model, 2026-06-25): an account is NOT a strategy. An account is a
(gate-strictness x contract-sizing) profile. EVERY validated strategy runs on EVERY
account; the account only decides *how selective* the entry gate is and *how big* the
position is. So strategies live here, once, and the executor applies each account's
gate + sizing to all of them.

A STRATEGY = an entry edge + its proven exit shape (stop / TP1 / runner). The exit is a
property of the strategy (the grind proved it), NOT the account. Strike selection and
contract count are the ACCOUNT's sizing axis, so they are deliberately absent here.

Add a validated edge by appending one Strategy. `fired(side_block)` maps a shared-signal
side-block to the strategies that triggered this tick (by setup-name match); the executor
then gates + sizes each. Pure functions, no I/O — unit-tested in test_strategies.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ExitShape:
    """The strategy's proven bracket (fractions, not strikes/qty — those are account sizing).

    The 4 leading fields define the scale-out the live exit_manager realizes (partial TP1 +
    runner + profit-lock). The 3 trailing fields (defaulted to production constants so every
    existing 4-arg ExitShape literal stays valid) make the runner ride fully self-describing:
    where the runner targets, how tight the chandelier trails, and when profit-lock arms.

    STRUCTURE-STOP (2026-07-09, flag-gated): stop_mode/catastrophe_stop_pct are ADDITIVE --
    every existing ExitShape literal (4- or 7-arg) stays valid, defaulting to "premium" (today's
    exact behavior, byte-identical). "structure" only takes effect on a position whose entry
    ALSO had params.json's structure_stop_enabled=True (see exit_manager.ExitState.from_entry) --
    a shape declaring stop_mode="structure" is inert on its own."""
    premium_stop_pct: float      # e.g. -0.20  (negative = stop at (1+pct)*entry)
    tp1_premium_pct: float       # e.g. 1.5    (+150% take-profit-1 level)
    tp1_qty_fraction: float      # e.g. 0.8    (sell 80% at TP1, rest rides)
    profit_lock_mode: str        # "fixed" | "trailing"
    runner_target_pct: float = 2.5       # runner exits at entry*(1+this) (CLAUDE.md 2.5x)
    trail_pct: float = 0.125             # chandelier: floor = HWM*(1-this) (WP-6 0.125)
    profit_lock_arm_pct: float = 0.05    # arm the profit-lock at +5% favorable (CLAUDE.md)
    stop_mode: str = "premium"           # "premium" (today) | "structure" (v15.3 chart-stop)
    catastrophe_stop_pct: "float | None" = None  # override for the structure-mode cap; None = global -50%
    # PROFIT-LOCK ARM SCOPE (2026-07-09 sim-vs-live scope-mismatch fix): "post_tp1" (default,
    # today's exact live behavior -- the lock arms at/after TP1 only) | "full" (simulator_real
    # parity -- the WHOLE position gets the BE floor / trail from the first +arm_pct touch,
    # pre-TP1 included). Every sim study that passed profit_lock_threshold_pct>0 assumed
    # "full"; NO live shape declares it until a live-machine scorecard + STOP-B arms it.
    profit_lock_arm_scope: str = "post_tp1"
    # PROFIT RATCHET (2026-08-10, J-DIRECTED mid-session -- rule-9 override by the rule
    # author, his repeated "trailing stops" escalation, armed the day three 773C calls peaked
    # +83/+91/+98% and closed red with $0 banked). Arms once best_premium clears
    # entry*(1+pre_tp1_be_floor_arm_pct); the floor then sits at entry*(1+pre_tp1_floor_pct)
    # and can never be lowered. Independent of TP1 and of the post-TP1 chandelier (which is
    # byte-identical whether or not these are set). None/None = exactly yesterday's engine.
    # PRIOR ART, disclosed not hidden: a floor AT ENTRY arming at +30/50/70% failed its G4
    # runner veto on 2026-08-02 (scratched pullback-then-run winners at $0). THIS shape --
    # arm high, floor well above entry -- was never tested there; J's on-record counter is
    # that the G4 cohort was bad entries bailed out by luck, and a floored exit frees the arm
    # to re-enter (never priced by the single-position replay). Forward ledger decides.
    pre_tp1_be_floor_arm_pct: "float | None" = None
    pre_tp1_floor_pct: "float | None" = None
    # J's LADDER (2026-08-10): fixed rungs lock a guaranteed minimum; the trail protects
    # everything that never reaches a rung. Effective floor = max(rungs, trail, stop).
    pre_tp1_ladder: "list | None" = None
    # PRE-TP1 RIBBON CONFIRMATION (2026-08-11, prereg RIBBON-CONFIRM-2026-08-11).
    # N consecutive flipped ticks required before a pre-TP1 ribbon exit sells. None or 1 =
    # today's exact single-tick behaviour. Post-TP1 runner ribbon exit is untouched.
    pre_tp1_ribbon_confirm_ticks: "int | None" = None
    pre_tp1_trail_arm_pct: "float | None" = None
    pre_tp1_trail_pct: "float | None" = None

    def to_dict(self) -> dict:
        """The exit-shape dict the executor/live paths thread through (kept in sync with
        fleet_executor._exit_shape_dict + exit_manager.ExitState.from_entry keys)."""
        return {
            "premium_stop_pct": self.premium_stop_pct,
            "tp1_premium_pct": self.tp1_premium_pct,
            "tp1_qty_fraction": self.tp1_qty_fraction,
            "profit_lock_mode": self.profit_lock_mode,
            "runner_target_pct": self.runner_target_pct,
            "trail_pct": self.trail_pct,
            "profit_lock_arm_pct": self.profit_lock_arm_pct,
            "stop_mode": self.stop_mode,
            "catastrophe_stop_pct": self.catastrophe_stop_pct,
            "profit_lock_arm_scope": self.profit_lock_arm_scope,
            "pre_tp1_be_floor_arm_pct": self.pre_tp1_be_floor_arm_pct,
            "pre_tp1_floor_pct": self.pre_tp1_floor_pct,
            "pre_tp1_ladder": self.pre_tp1_ladder,
            "pre_tp1_ribbon_confirm_ticks": self.pre_tp1_ribbon_confirm_ticks,
            "pre_tp1_trail_arm_pct": self.pre_tp1_trail_arm_pct,
            "pre_tp1_trail_pct": self.pre_tp1_trail_pct,
        }


@dataclass(frozen=True)
class Strategy:
    name: str
    # setup_name(s) (from the shared signal's side block) that mean THIS strategy fired.
    entry_setups: Sequence[str]
    exit: ExitShape
    note: str = ""
    # Strategies are direction-agnostic by construction — the side comes from which
    # side-block (bull/bear) fired. No per-strategy direction lock (that was the bug).


# --- The validated set (extend by appending) ------------------------------------------
# ribbon_ride: the mass-grind funnel winner (2026-06-25). Tight-stop directional ride on
# the ribbon rejection/reclaim edge; grind-proven exit = -20% stop / +150% TP1 / sell 80%.
#
# stop_mode="structure" (2026-07-09, STRUCTURE-STOP build): declares this strategy's INTENT
# to run v15.3 "chart-stop-primary" (CLAUDE.md 2026-06-18: chart-level is the primary
# invalidation, premium stop demoted to a -50% catastrophe cap) -- ribbon_ride's entry_setups
# are literally REJECT/RECLAIM of a chart level, so this is the strategy the doctrine
# describes. Declaring it here is BEHAVIORALLY INERT on its own: exit_manager.ExitState.
# from_entry only resolves "structure" mode when params.json's structure_stop_enabled is
# ALSO True at entry time (absent/False today -- see automation/state/fleet/exit_manager.py).
# This is intentionally the ONE place + the params flag is the ONLY other place activation
# touches -- do not also flip params.structure_stop_enabled without reading the activation
# steps in this build's report.
RIBBON_RIDE = Strategy(
    name="ribbon_ride",
    entry_setups=("BEARISH_REJECTION_RIDE_THE_RIBBON", "BULLISH_RECLAIM_RIDE_THE_RIBBON"),
    # SS-B validated cell (structure-stop-2026-07-09.json -- the ONLY candidate passing BOTH
    # pre-registered layers: fresh-slice -47.34/tr vs control -100.67; anchor -604.70 vs -757.10).
    # WHOLE cell ported per C29, no field mixed from another cell: structure stop primary,
    # -50% intrabar catastrophe cap, TP1 +100% sell 66%, trailing runner 15% off HWM,
    # runner_target 99.0 == the cell's tgt-none (runner exits via structure/trail/EOD only).
    exit=ExitShape(premium_stop_pct=-0.20, tp1_premium_pct=1.0, tp1_qty_fraction=0.667,
                   pre_tp1_ladder=[[0.50, 0.30], [0.75, 0.60]],
                   # Trail arms at the TOP RUNG, not at +40% as first drafted. Measured on the
                   # 2026-08-10 tape (9 real fills, real OPRA 5m): a +40%-armed 20% trail can only
                   # ever bind between +40% and +50% MFE -- above +50% the fixed rungs are always
                   # the higher floor -- and in that dead band it sold every 773C at ~10:05 on the
                   # first pullback. Day came to +$132 vs +$446 with the rungs alone, and it cut
                   # the day's one real winner from +$123 to +$62. Armed at +75% the trail only
                   # takes over above +100% MFE (hwm*0.80 > entry*1.60), which is exactly the gap
                   # the fixed top rung leaves open: without it a +200% runner still gives back to
                   # +60%. Inert on today's tape (best MFE was +98%); it exists for the bigger run.
                   pre_tp1_trail_arm_pct=0.75, pre_tp1_trail_pct=0.20,
                   profit_lock_mode="trailing", runner_target_pct=99.0, trail_pct=0.15,
                   stop_mode="structure", catastrophe_stop_pct=-0.50),
    note="SS-B structure-stop cell shipped 2026-07-09 (STOP-B; waiver: structure stops sit "
         "outside the premium-grind P5 universe; forward kill-check = fresh P5 grind + 2-week "
         "paper). Prior premium cell (-20/+150/sell80/fixed) was a P5 non-survivor that lost "
         "-$893 on our own fills. premium_stop_pct -0.20 is the flag-OFF emergency fallback "
         "only (tight-stop safety mode, NOT the validated cell); in structure mode the live cap "
         "is catastrophe_stop_pct -0.50. Instant de-arm: params.structure_stop_enabled=false "
         "(new entries fall back to -20% premium + quick TP1); full revert = git revert the "
         "STOP-B commit.",
)

# vwap_continuation: ported 2026-07-09 to the FULL validated core cell (T-W6 option a) --
# the old -0.08/+0.30/0.667/trailing literal was the STALE 2026-07-02 copy; the 2026-07-07
# walk-forward A/B superseded it in the core lane and nobody propagated to this file.
VWAP_CONTINUATION = Strategy(
    name="vwap_continuation",
    entry_setups=("VWAP_CONTINUATION", "vwap_continuation"),
    exit=ExitShape(premium_stop_pct=-0.06, tp1_premium_pct=0.40, tp1_qty_fraction=0.8, profit_lock_mode="fixed"),
    note="full validated core cell ported 2026-07-09 (T-W6 option a, STOP-B): -6% stop / +40% "
         "TP1 / sell 80% / fixed lock. Validated 2026-07-07, ALL 5 OP-22 gates PASS on n=149 "
         "real OPRA fills (analysis/recommendations/vwapcont-exit-ab-ship-gate.json: OOS "
         "$75.47 vs $66.83/tr, WF 1.62, anchor 82.04 vs 44.52). Provenance + two-lane drift "
         "history: markdown/audits/T-W6-VWAP-TWO-LANE-PROVENANCE-2026-07-08.md. CAVEAT (C29, "
         "recorded + accepted by STOP-B): validated at ATM (core Safe-2 cell); fleet arms size "
         "strikes per account, so fleet-strike cells are unvalidated -- but this shape carries "
         "the validated exit body and now matches the core lane exactly (no two-lane drift).",
)

# vwap_reclaim_failed_break: FLEET-VWAP-RECLAIM-EXTENSION-RISKY3 (2026-08-04; prereg
# frozen BEFORE arming: analysis/recommendations/fleet-vwap-reclaim-extension-prereg-
# 2026-08-04.json). Edge #2 -- the SUBTRACTIVE/STRUCTURAL sibling of vwap_continuation
# (morning trend -> counter-trend VWAP break FAILS -> with-trend reclaim <=10:30 ET, one
# causal entry/day; detector: backtest/lib/watchers/vwap_reclaim_failed_break_watcher.py,
# byte-for-byte the validated autoresearch port). Exit = the Safe-2 ARMED ATM cell
# (-8% stop / +30% TP1 / sell 80% / fixed lock -- the isolated params keys core Safe-2
# trades live via extra_setup_exec_armed since; real PLACED engine fill 2026-07-28 10:36).
# CAVEAT (C29, same disclosure pattern as VWAP_CONTINUATION above): validated at ATM
# (Safe-2) and ITM-2 (Bold); OTM-2 measured FAILING (theta/delta) -- which is exactly why
# fleet_executor.STRATEGY_STRIKE_TIERS routes this strategy's entries to the ATM-class
# PROBE table instead of an arm's bold/OTM table. Fleet-account cells remain unvalidated
# as cells; the forward paper ledger is the evidence (TRADE-TO-LEARN standing).
# KILL: producer flag build_shared_signal.RUN_VWAP_RECLAIM_FB=False (one line).
VWAP_RECLAIM_FAILED_BREAK = Strategy(
    name="vwap_reclaim_failed_break",
    entry_setups=("VWAP_RECLAIM_FAILED_BREAK", "vwap_reclaim_failed_break"),
    exit=ExitShape(premium_stop_pct=-0.08, tp1_premium_pct=0.30, tp1_qty_fraction=0.8,
                   profit_lock_mode="fixed"),
    note="Safe-2 armed ATM cell ported 2026-08-04 (stop -8% / TP1 +30% / sell 80% / fixed). "
         "8/8 anti-cherry-pick gates on real OPRA fills (sub-struct scorecards); OTM cells "
         "FAIL (C29) -- entries strike-routed ATM-class via STRATEGY_STRIKE_TIERS. Per-arm "
         "exit_patch overlays apply on top by existing design (risky-3 structure/trail 0.20, "
         "risky-1 tp1 0.5) -- disclosed, the fleet exit A/B is the point.",
)

REGISTRY: tuple[Strategy, ...] = (RIBBON_RIDE, VWAP_CONTINUATION, VWAP_RECLAIM_FAILED_BREAK)


def _setup_of(side_block: Mapping[str, object]) -> str:
    return str(side_block.get("setup_name") or side_block.get("setup") or "").strip()


def _disarmed_setups() -> set[str]:
    """Setup keys explicitly set FALSE in params.json's extra_setup_exec_armed.

    ⛔ WHY THIS EXISTS (2026-08-12). vwap_continuation was DISARMED on 2026-07-25 (commit
    e0356fb1, whose own message reads "DISARM vwap_continuation + vix_regime_dayside (0-for-12
    live, -$357, caused 2 of 3 losing days)"). That commit touched ONLY params.json -- which
    governs the CORE arms. The fleet arms never consulted params at all: fired() matched against
    REGISTRY membership alone, and build_shared_signal.py hardcodes RUN_VWAP = True.

    So the kill landed on 2 of 5 arms and the setup kept trading on the other three for 18 days.
    Measured from journal/trades.csv: 43 fills after the disarm date -- risky-3 26 fills -$646,
    risky-1 17 fills -$400, TOTAL -$1,046, still filling on 2026-08-12. The half-landed kill cost
    ~3x the -$357 that motivated the kill in the first place.

    L287 class: an imperative fix applied to one surface expires the moment a second surface
    regenerates the same decision independently. The fix is structural, not another one-off --
    ONE switch (params.extra_setup_exec_armed) now governs BOTH paths, so the next disarm cannot
    half-land the same way.

    Semantics, deliberately asymmetric:
      * key present and FALSE  -> disarmed on the fleet path too.
      * key present and TRUE   -> armed (vwap_reclaim_failed_break, unaffected).
      * key ABSENT             -> armed. RIBBON_RIDE is the CORE setup and correctly appears
                                  nowhere in extra_setup_exec_armed; keying off absence would
                                  disarm the whole engine.

    FAILS OPEN on any read/parse error -- a guard that halts trading because a config read
    hiccupped is worse than the bug it prevents (OP-25: guards must never block the engine).
    """
    try:
        import json  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415
        # This file lives at automation/state/fleet/strategies.py, so parents[1] IS
        # automation/state -- params.json sits right there. (First cut used parents[2] plus a
        # re-appended "automation/state", which resolved to automation/automation/state/... ,
        # failed to read, and fell through the fail-open path -- i.e. the disarm would have
        # silently done NOTHING while looking installed. Anchor to __file__, count carefully: L21.)
        params = json.loads(
            (Path(__file__).resolve().parents[1] / "params.json").read_text(encoding="utf-8"))
        armed = params.get("extra_setup_exec_armed") or {}
        return {str(k).lower() for k, v in armed.items() if v is False}
    except Exception as exc:  # noqa: BLE001 -- fail OPEN, never block the engine
        print(f"[strategies] WARN: could not read extra_setup_exec_armed ({exc}); "
              "no fleet-side disarm applied this tick")
        return set()


def fired(side_block: Mapping[str, object]) -> list[Strategy]:
    """Strategies whose entry setup matches this fired side-block (>=1 trigger).

    Selectivity (how many triggers / what quality) is the ACCOUNT's gate, applied later —
    here we only answer 'did this edge's entry pattern appear this tick'."""
    if side_block.get("passed") is not True:
        return []
    triggers = side_block.get("triggers_fired") or []
    if not triggers:
        return []
    setup = _setup_of(side_block).upper()
    out = []
    for strat in REGISTRY:
        if any(setup == s.upper() for s in strat.entry_setups):
            out.append(strat)
    return out

    # NOTE: the params disarm is deliberately NOT enforced here. fired() is only reached by
    # plan_all's LEGACY fallback branch, and build_shared_signal always emits a top-level
    # "strategies" key (:684), so production never takes it. Enforcing here was inert in
    # production and only broke legacy-path plumbing tests. The disarm lives at
    # fleet_executor.select_plan -- the point where exactly one plan becomes an order.
    # test_fleet_disarm_parity_2026_08_12.py pins that the producer keeps emitting
    # "strategies"; if that ever stops, the legacy branch goes live and needs its own guard.


def by_name(name: str) -> Strategy | None:
    for s in REGISTRY:
        if s.name == name:
            return s
    return None
