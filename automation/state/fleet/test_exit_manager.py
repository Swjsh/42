"""Tests for exit_manager -- the pure exit/scale-out state machine.

Proves the live walk matches simulator_real's 5-stage lifecycle:
  * entry split: tp1_qty = int(qty * tp1_qty_fraction), runner_qty = rest
  * pre-TP1 premium stop / time stop / ribbon-flip-back exit ALL units
  * TP1 partial: SELL tp1_qty, runner stop ratchets to BE, rest rides
  * runner: trailing (chandelier HWM*(1-trail)) vs fixed (BE floor), runner target, time stop
  * the PLACED actions (qty sold per stage) == the exit_shape's scale-out geometry
"""
from __future__ import annotations

from datetime import time

import exit_manager as em

RIBBON_SHAPE = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5,
                "tp1_qty_fraction": 0.8, "profit_lock_mode": "fixed"}
# The live vwap_continuation body (-6%/+40%/sell80/fixed) in both arm scopes. "full" is the
# simulator_real-parity scope (pre-TP1 whole-position lock) -- EXPRESSIBLE but armed by NO
# live shape (2026-07-09 scope-mismatch fix; see test_pre_tp1_lock_* below).
VWAP_BODY = {"premium_stop_pct": -0.06, "tp1_premium_pct": 0.40,
             "tp1_qty_fraction": 0.8, "profit_lock_mode": "fixed"}
VWAP_FULL_SCOPE = dict(VWAP_BODY, profit_lock_arm_scope="full")
# TRAIL_SHAPE (renamed from VWAP_SHAPE 2026-07-09): a GENERIC trailing-mode mechanics fixture,
# NOT a registry pin. vwap_continuation's live shape moved to -0.06/+0.40/0.8/fixed (T-W6
# option a port, STOP-B; see strategies.py + vwapcont-exit-ab-ship-gate.json), so no live
# strategy currently trades this exact shape -- the trailing-chandelier state machine it
# exercises is still live machinery (any future trailing shape) and stays covered here.
TRAIL_SHAPE = {"premium_stop_pct": -0.08, "tp1_premium_pct": 0.3,
               "tp1_qty_fraction": 0.667, "profit_lock_mode": "trailing"}
MORNING = time(11, 0)
AFTER_STOP = time(15, 51)


def _state(shape, qty=5, entry=1.00, strategy="x"):
    return em.ExitState.from_entry(symbol="SPY260625P00600000", side="P",
                                   entry_premium=entry, qty=qty, exit_shape=shape,
                                   strategy=strategy)


# --- entry split (stage 1) ----------------------------------------------------
def test_entry_split_ribbon_80pct():
    """ribbon_ride 0.8 fraction on qty5 -> tp1=4, runner=1 (int floor)."""
    s = _state(RIBBON_SHAPE, qty=5)
    assert s.tp1_qty == 4 and s.runner_qty == 1
    assert s.runner_stop_premium == 0.80   # 1.00 * (1 - 0.20)
    assert s.profit_lock_mode == "fixed"


def test_entry_split_trailing_667pct():
    """trailing fixture 0.667 on qty3 -> tp1=2, runner=1; -8% stop."""
    s = _state(TRAIL_SHAPE, qty=3)
    assert s.tp1_qty == 2 and s.runner_qty == 1
    assert s.runner_stop_premium == 0.92   # 1.00 * (1 - 0.08)


def test_entry_invalid_stop_uses_catastrophe_cap():
    bad = dict(RIBBON_SHAPE, premium_stop_pct=0)
    s = _state(bad)
    assert s.premium_stop_pct == -0.50 and s.runner_stop_premium == 0.50


# --- pre-TP1 hard exits (stage 2) ---------------------------------------------
def test_pre_tp1_premium_stop_sells_all():
    s = _state(RIBBON_SHAPE, qty=5)  # stop 0.80
    dec = em.plan_exit_actions(s, best_premium=0.85, worst_premium=0.79,
                               open_qty=5, now_et=MORNING)
    assert dec.closes_position
    a = dec.actions[0]
    assert a.kind == "SELL_ALL" and a.qty == 5 and a.stage == "premium_stop"


def test_pre_tp1_time_stop_sells_all():
    s = _state(RIBBON_SHAPE, qty=5)
    dec = em.plan_exit_actions(s, best_premium=1.10, worst_premium=1.05,
                               open_qty=5, now_et=AFTER_STOP)
    assert dec.actions[0].kind == "SELL_ALL" and dec.actions[0].stage == "time_stop"


def test_pre_tp1_ribbon_flip_sells_all():
    s = _state(RIBBON_SHAPE, qty=5)
    dec = em.plan_exit_actions(s, best_premium=1.10, worst_premium=1.05,
                               open_qty=5, now_et=MORNING, ribbon_flip_back=True)
    assert dec.actions[0].kind == "SELL_ALL" and dec.actions[0].stage == "ribbon_flip"


def test_pre_tp1_hold_updates_hwm_only():
    s = _state(RIBBON_SHAPE, qty=5)
    dec = em.plan_exit_actions(s, best_premium=1.40, worst_premium=1.20,
                               open_qty=5, now_et=MORNING)
    assert not dec.actions  # no exit, no TP1 yet (TP1 at +150% = 2.50)
    assert dec.state.hwm_premium == 1.40 and not dec.state.tp1_filled


# --- TP1 partial scale-out (stage 3) -- THE HARD-REQUIREMENT ASSERTION ---------
def test_tp1_partial_sells_tp1_qty_and_ratchets_to_be():
    """ribbon TP1 at +150% (2.50) on qty5: SELL 4 (the 0.8 fraction), runner stop -> BE."""
    s = _state(RIBBON_SHAPE, qty=5, entry=1.00)
    dec = em.plan_exit_actions(s, best_premium=2.55, worst_premium=2.40,
                               open_qty=5, now_et=MORNING)
    sells = [a for a in dec.actions if a.kind == "SELL_PARTIAL"]
    ratchets = [a for a in dec.actions if a.kind == "RATCHET_STOP"]
    assert len(sells) == 1 and sells[0].qty == 4 and sells[0].stage == "tp1"
    assert not dec.closes_position  # the runner (1) still rides
    assert dec.state.tp1_filled is True
    assert dec.state.runner_stop_premium == 1.00  # break-even
    assert ratchets and ratchets[0].new_stop_premium == 1.00


def test_tp1_partial_trailing_qty3_sells_2():
    s = _state(TRAIL_SHAPE, qty=3, entry=1.00)  # TP1 at +30% = 1.30, tp1_qty=2
    dec = em.plan_exit_actions(s, best_premium=1.35, worst_premium=1.25,
                               open_qty=3, now_et=MORNING)
    sells = [a for a in dec.actions if a.kind == "SELL_PARTIAL"]
    assert sells[0].qty == 2  # 0.667 fraction floor on 3
    assert dec.state.tp1_filled and dec.state.runner_stop_premium == 1.00


def test_no_tp1_when_runner_qty_zero():
    """tp1_qty_fraction 1.0 -> runner_qty 0; TP1 'partial' is the whole position."""
    shape = dict(RIBBON_SHAPE, tp1_qty_fraction=1.0)
    s = _state(shape, qty=5)
    assert s.tp1_qty == 5 and s.runner_qty == 0
    dec = em.plan_exit_actions(s, best_premium=2.55, worst_premium=2.40,
                               open_qty=5, now_et=MORNING)
    sells = [a for a in dec.actions if a.kind == "SELL_PARTIAL"]
    assert sells[0].qty == 5  # sells all at TP1, no runner left


# --- runner ride: fixed BE floor (stage 4, ribbon = fixed) --------------------
def test_runner_fixed_stops_at_be():
    """After TP1, ribbon (fixed) runner stop sits at BE; a drop to BE exits the runner."""
    s = _state(RIBBON_SHAPE, qty=5, entry=1.00)
    after_tp1 = em.plan_exit_actions(s, best_premium=2.55, worst_premium=2.40,
                                     open_qty=5, now_et=MORNING).state
    # runner now alone (open_qty=1), price drops to BE
    dec = em.plan_exit_actions(after_tp1, best_premium=1.05, worst_premium=0.99,
                               open_qty=1, now_et=MORNING)
    assert dec.closes_position and dec.actions[0].stage == "be_stop"


def test_runner_fixed_does_not_trail_up():
    """Fixed mode: the runner stop stays at BE even as the premium climbs (no chandelier).
    Premium climbs to 3.00 (below the +250% runner target of 3.50) so it keeps riding."""
    s = _state(RIBBON_SHAPE, qty=5, entry=1.00)
    after_tp1 = em.plan_exit_actions(s, best_premium=2.55, worst_premium=2.40,
                                     open_qty=5, now_et=MORNING).state
    dec = em.plan_exit_actions(after_tp1, best_premium=3.00, worst_premium=2.80,
                               open_qty=1, now_et=MORNING)
    assert not dec.closes_position
    assert dec.state.runner_stop_premium == 1.00  # still BE, no trail (fixed mode)


# --- runner ride: trailing chandelier (stage 4, TRAIL_SHAPE fixture) -----------
def test_runner_trailing_ratchets_with_hwm():
    """trailing runner: stop trails to HWM*(1-trail_pct) once armed."""
    s = _state(TRAIL_SHAPE, qty=3, entry=1.00)  # trail_pct default 0.125
    after_tp1 = em.plan_exit_actions(s, best_premium=1.35, worst_premium=1.25,
                                     open_qty=3, now_et=MORNING).state
    # runner alone, premium runs to 2.00 -> trail floor 2.00*0.875 = 1.75
    dec = em.plan_exit_actions(after_tp1, best_premium=2.00, worst_premium=1.90,
                               open_qty=1, now_et=MORNING)
    assert not dec.closes_position
    assert dec.state.runner_stop_premium == 1.75
    ratchets = [a for a in dec.actions if a.kind == "RATCHET_STOP"]
    assert ratchets and ratchets[0].stage == "trail"


def test_runner_trailing_exits_on_retrace():
    s = _state(TRAIL_SHAPE, qty=3, entry=1.00)
    st = em.plan_exit_actions(s, best_premium=1.35, worst_premium=1.25,
                              open_qty=3, now_et=MORNING).state
    st = em.plan_exit_actions(st, best_premium=2.00, worst_premium=1.90,
                              open_qty=1, now_et=MORNING).state  # stop now 1.75
    dec = em.plan_exit_actions(st, best_premium=1.80, worst_premium=1.70,
                               open_qty=1, now_et=MORNING)       # retrace below 1.75
    assert dec.closes_position and dec.actions[0].stage == "trail"


# --- runner target (stage 4) --------------------------------------------------
def test_runner_target_exit():
    """Runner hits entry*(1+runner_target_pct) -> SELL_ALL the runner."""
    shape = dict(RIBBON_SHAPE, runner_target_pct=2.5)  # 1.00 -> 3.50
    s = _state(shape, qty=5, entry=1.00)
    st = em.plan_exit_actions(s, best_premium=2.55, worst_premium=2.40,
                              open_qty=5, now_et=MORNING).state
    dec = em.plan_exit_actions(st, best_premium=3.55, worst_premium=3.40,
                               open_qty=1, now_et=MORNING)
    assert dec.closes_position and dec.actions[0].stage == "runner_target"


# --- runner time stop (stage 5) -----------------------------------------------
def test_runner_time_stop_exit():
    s = _state(RIBBON_SHAPE, qty=5, entry=1.00)
    st = em.plan_exit_actions(s, best_premium=2.55, worst_premium=2.40,
                              open_qty=5, now_et=MORNING).state
    dec = em.plan_exit_actions(st, best_premium=1.50, worst_premium=1.40,
                               open_qty=1, now_et=AFTER_STOP)
    assert dec.closes_position and dec.actions[0].stage == "time_stop"


# --- EXITMGR-TIME-STOP-LABEL guard (2026-08-01, chip task_30a7b291) -----------
# `reason` used to be the hardcoded literal "time_stop_15:50" no matter what time_stop_et
# was actually passed in -- label-only (stage was always correct). Live params.json has
# carried time_stop_et="15:40" for a while, so every real time-stop exit journaled a reason
# 10 minutes later than what actually fired. These pin the reason string to the CONFIGURED
# value, both pre-TP1 and runner stages, and RED-proof that a non-default value is not
# coincidentally correct.
def test_pre_tp1_time_stop_reason_matches_configured_time_stop_et():
    """The live-configured value (params.json time_stop_et="15:40"), not the 15:50 default."""
    s = _state(RIBBON_SHAPE, qty=5)
    dec = em.plan_exit_actions(s, best_premium=1.10, worst_premium=1.05, open_qty=5,
                               now_et=time(15, 45), time_stop_et=time(15, 40))
    a = dec.actions[0]
    assert a.stage == "time_stop"
    assert a.reason == "time_stop_15:40", a.reason
    assert "15:50" not in a.reason, "must not silently fall back to the stale default label"


def test_runner_time_stop_reason_matches_configured_time_stop_et():
    s = _state(RIBBON_SHAPE, qty=5, entry=1.00)
    st = em.plan_exit_actions(s, best_premium=2.55, worst_premium=2.40, open_qty=5,
                              now_et=MORNING, time_stop_et=time(15, 40)).state
    dec = em.plan_exit_actions(st, best_premium=1.50, worst_premium=1.40, open_qty=1,
                               now_et=time(15, 45), time_stop_et=time(15, 40))
    a = dec.actions[0]
    assert a.stage == "time_stop"
    assert a.reason == "time_stop_15:40 (runner)", a.reason


def test_bite_time_stop_reason_tracks_an_arbitrary_non_default_value():
    """RED-PROOF / non-vacuous: 15:40 happens to be the live value, so also prove the label
    tracks an arbitrary DIFFERENT configured time (16:05) -- not a value the fix could have
    hardcoded by coincidence."""
    s = _state(RIBBON_SHAPE, qty=5)
    dec = em.plan_exit_actions(s, best_premium=1.10, worst_premium=1.05, open_qty=5,
                               now_et=time(16, 10), time_stop_et=time(16, 5))
    assert dec.actions[0].reason == "time_stop_16:05", dec.actions[0].reason


def test_pre_tp1_time_stop_reason_default_still_15_50_when_unconfigured():
    """Regression pin: the DEFAULT (no time_stop_et override, matching TIME_STOP_ET) must
    still read 15:50 -- the fix changes WHICH value is reported, not the default itself."""
    s = _state(RIBBON_SHAPE, qty=5)
    dec = em.plan_exit_actions(s, best_premium=1.10, worst_premium=1.05,
                               open_qty=5, now_et=AFTER_STOP)
    assert dec.actions[0].reason == "time_stop_15:50", dec.actions[0].reason


# --- idempotency / flat / serialization ---------------------------------------
def test_flat_position_is_noop():
    s = _state(RIBBON_SHAPE, qty=5)
    dec = em.plan_exit_actions(s, best_premium=2.55, worst_premium=0.10,
                               open_qty=0, now_et=MORNING)
    assert not dec.actions and not dec.closes_position


def test_state_roundtrips_through_dict():
    s = _state(TRAIL_SHAPE, qty=3, entry=1.23, strategy="roundtrip_test")
    s2 = em.ExitState.from_dict(s.to_dict())
    assert s2 == s


def test_full_scaleout_geometry_matches_exit_shape():
    """The TOTAL contracts sold across the lifecycle == total_qty, split tp1_qty + runner_qty
    exactly per the exit shape (the hard-requirement: placed orders == exit_shape scale-out)."""
    s = _state(RIBBON_SHAPE, qty=5, entry=1.00)  # tp1=4, runner=1
    sold = 0
    # tick 1: TP1 fires -> sell 4
    d1 = em.plan_exit_actions(s, best_premium=2.55, worst_premium=2.40, open_qty=5, now_et=MORNING)
    sold += sum(a.qty for a in d1.actions if a.kind in ("SELL_PARTIAL", "SELL_ALL"))
    # tick 2: runner stops at BE -> sell 1
    d2 = em.plan_exit_actions(d1.state, best_premium=1.05, worst_premium=0.99, open_qty=1, now_et=MORNING)
    sold += sum(a.qty for a in d2.actions if a.kind in ("SELL_PARTIAL", "SELL_ALL"))
    assert sold == 5 == s.total_qty
    assert s.tp1_qty == 4 and s.runner_qty == 1


# =============================================================================================
# STRUCTURE-STOP (v15.3 chart-stop-primary, 2026-07-09) -- flag-gated, both lanes.
# See exit_manager.py's module note above ExitState/plan_exit_actions for the full spec.
# =============================================================================================
STRUCTURE_SHAPE = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.8,
                   "profit_lock_mode": "fixed", "stop_mode": "structure"}


def _st(shape, *, side="P", qty=5, entry=1.00, strategy="x",
       trigger_level=None, structure_stop_enabled=False):
    """Structure-stop test helper (kept separate from `_state` above -- never mutates the
    existing fixture helper other tests depend on)."""
    return em.ExitState.from_entry(symbol="SPY260625P00600000", side=side, entry_premium=entry,
                                   qty=qty, exit_shape=shape, strategy=strategy,
                                   trigger_level=trigger_level,
                                   structure_stop_enabled=structure_stop_enabled)


# --- nearest_active_level (pure helper) ----------------------------------------
def test_nearest_active_level_bear_picks_above_spot():
    """side=P (bear/rejection): only levels AT/ABOVE spot qualify."""
    assert em.nearest_active_level([598.0, 600.5, 601.8, 605.0], 600.0, "P") == 600.5


def test_nearest_active_level_bull_picks_below_spot():
    """side=C (bull/reclaim): only levels AT/BELOW spot qualify."""
    assert em.nearest_active_level([598.5, 599.9, 600.5, 602.0], 600.0, "C") == 599.9


def test_nearest_active_level_excludes_wrong_side():
    """A bear entry ignores a level BELOW spot even if it's the closest raw distance,
    picking the farther (but correctly-sided) level within range instead."""
    assert em.nearest_active_level([599.99, 601.5], 600.0, "P") == 601.5


def test_nearest_active_level_respects_max_distance():
    assert em.nearest_active_level([610.0], 600.0, "P", max_distance=2.0) is None
    assert em.nearest_active_level([601.5], 600.0, "P", max_distance=2.0) == 601.5


def test_nearest_active_level_none_on_empty_or_bad_input():
    assert em.nearest_active_level([], 600.0, "P") is None
    assert em.nearest_active_level([601.0], None, "P") is None
    assert em.nearest_active_level([601.0], 600.0, "X") is None  # invalid side


# --- flag-off inertness (THE hard requirement: vary-and-assert) ----------------
def test_structure_shape_inert_when_flag_off():
    """A shape declaring stop_mode='structure' with structure_stop_enabled=False (the
    params-absent default) resolves to EXACTLY the same ExitState as the plain premium
    shape -- proves the params flag, not the shape literal, is what gates the behavior."""
    s_structure = _st(STRUCTURE_SHAPE, trigger_level=745.0, structure_stop_enabled=False)
    s_premium = _st(RIBBON_SHAPE)  # RIBBON_SHAPE carries no stop_mode key at all
    assert s_structure.stop_mode == "premium" == s_premium.stop_mode
    assert s_structure.premium_stop_pct == s_premium.premium_stop_pct == -0.20
    assert s_structure.runner_stop_premium == s_premium.runner_stop_premium == 0.80


def test_structure_shape_inert_when_trigger_level_missing():
    """flag ON but no trigger_level (e.g. no nearby chart level found) -> still 'premium'."""
    s = _st(STRUCTURE_SHAPE, trigger_level=None, structure_stop_enabled=True)
    assert s.stop_mode == "premium"
    assert s.premium_stop_pct == -0.20  # the strategy's own stop, unchanged


def test_plain_shape_inert_even_with_flag_on():
    """A shape with NO stop_mode key (e.g. vwap_continuation, untouched by this build) never
    enters structure mode regardless of the params flag or an available trigger_level."""
    s = _st(RIBBON_SHAPE, trigger_level=745.0, structure_stop_enabled=True)
    assert s.stop_mode == "premium"


def test_vary_and_assert_full_tick_byte_identical_flag_off():
    """THE inertness proof: replay an identical fixture tape (entry -> hold -> TP1 -> runner
    hold) through a stop_mode='structure' shape with the flag OFF vs the plain premium shape
    with the SAME numeric knobs, and assert every ExitDecision.actions + resulting state
    field is byte-identical tick-by-tick (only the cosmetic stop_mode/trigger_level bookkeeping
    fields are allowed to differ)."""
    tape = [
        dict(best_premium=1.40, worst_premium=1.20, open_qty=5, now_et=MORNING),
        dict(best_premium=2.55, worst_premium=2.40, open_qty=5, now_et=MORNING),   # TP1
        dict(best_premium=2.60, worst_premium=2.50, open_qty=1, now_et=MORNING),   # runner hold
    ]
    s_structure = _st(STRUCTURE_SHAPE, trigger_level=745.0, structure_stop_enabled=False)
    s_premium = _st(RIBBON_SHAPE)
    for tick in tape:
        d_structure = em.plan_exit_actions(s_structure, last_closed_5m_close=700.0, **tick)
        d_premium = em.plan_exit_actions(s_premium, **tick)
        assert len(d_structure.actions) == len(d_premium.actions)
        for a1, a2 in zip(d_structure.actions, d_premium.actions):
            assert (a1.kind, a1.qty, a1.stage, a1.new_stop_premium) == \
                   (a2.kind, a2.qty, a2.stage, a2.new_stop_premium)
        # state parity on every field EXCEPT the structure-stop bookkeeping fields themselves
        st1, st2 = d_structure.state, d_premium.state
        assert (st1.tp1_filled, st1.runner_stop_premium, st1.hwm_premium,
               st1.profit_lock_armed, st1.tp1_qty, st1.runner_qty) == \
               (st2.tp1_filled, st2.runner_stop_premium, st2.hwm_premium,
               st2.profit_lock_armed, st2.tp1_qty, st2.runner_qty)
        s_structure, s_premium = d_structure.state, d_premium.state


# --- structure mode resolution + exit firing ------------------------------------
def test_structure_mode_resolves_when_all_three_present():
    """shape='structure' + flag True + trigger_level set -> resolves 'structure' and the
    premium stop is DEMOTED to the -50% catastrophe cap (TP1 pct is untouched)."""
    s = _st(STRUCTURE_SHAPE, trigger_level=745.0, structure_stop_enabled=True, entry=1.00)
    assert s.stop_mode == "structure"
    assert s.trigger_level == 745.0
    assert s.premium_stop_pct == -0.50 and s.runner_stop_premium == 0.50
    assert s.tp1_premium_pct == 1.5  # TP1/runner/trail untouched by structure mode


def test_structure_exit_fires_put_close_above_level():
    """PUT (bear): close > trigger_level invalidates the thesis -> exit ALL, pre-TP1."""
    s = _st(STRUCTURE_SHAPE, side="P", trigger_level=745.0, structure_stop_enabled=True, entry=1.00)
    dec = em.plan_exit_actions(s, best_premium=1.05, worst_premium=1.00, open_qty=5,
                               now_et=MORNING, last_closed_5m_close=745.5)
    assert dec.closes_position
    assert dec.actions[0].kind == "SELL_ALL" and dec.actions[0].stage == "structure_stop"


def test_structure_exit_fires_call_close_below_level():
    """CALL (bull): close < trigger_level invalidates the thesis -> exit ALL, pre-TP1."""
    s = _st(STRUCTURE_SHAPE, side="C", trigger_level=745.0, structure_stop_enabled=True, entry=1.00)
    dec = em.plan_exit_actions(s, best_premium=1.05, worst_premium=1.00, open_qty=5,
                               now_et=MORNING, last_closed_5m_close=744.5)
    assert dec.closes_position
    assert dec.actions[0].kind == "SELL_ALL" and dec.actions[0].stage == "structure_stop"


def test_structure_no_exit_when_close_still_on_thesis_side():
    """PUT: close still BELOW the level (thesis intact) -> no structure exit; position holds."""
    s = _st(STRUCTURE_SHAPE, side="P", trigger_level=745.0, structure_stop_enabled=True, entry=1.00)
    dec = em.plan_exit_actions(s, best_premium=1.05, worst_premium=1.00, open_qty=5,
                               now_et=MORNING, last_closed_5m_close=744.0)
    assert not dec.actions  # no exit at all this tick (premium/time/TP1 also not hit)


def test_structure_mode_runner_also_protected():
    """Post-TP1 runner: a structure break force-exits the runner too (TP1/runner UNCHANGED
    means the runner's OWN math is untouched, not that structure stops applying to it --
    'chart-level is the primary invalidation' applies for the life of the trade, exactly
    like the existing ribbon-flip-back which ALSO checks both pre- and post-TP1)."""
    s = _st(STRUCTURE_SHAPE, side="P", trigger_level=745.0, structure_stop_enabled=True, entry=1.00)
    after_tp1 = em.plan_exit_actions(s, best_premium=2.55, worst_premium=2.40, open_qty=5,
                                     now_et=MORNING, last_closed_5m_close=744.0).state
    assert after_tp1.tp1_filled
    dec = em.plan_exit_actions(after_tp1, best_premium=2.60, worst_premium=2.50, open_qty=1,
                               now_et=MORNING, last_closed_5m_close=745.2)
    assert dec.closes_position and dec.actions[0].stage == "structure_stop"


# --- SAME-TICK ORDERING: structure-before-catastrophe (2026-07-09 ssb-certification fix) -----
# ssb-certification-2026-07-09.json (Task 1 parity vs backtest/tools/structure_stop_study.py's
# validated SS-B cell) found production's plan_exit_actions checking the premium/catastrophe
# stop BEFORE the structure stop, so a same-tick both-conditions position exited at the WORSE
# catastrophe fill instead of the structure fill the study (and the armed cell) uses --
# REAL-DIVERGENCE on 2/10 real positions that day (-$24.50). Fix: structure is now checked
# FIRST in the pre-TP1 branch (post-TP1 was already correctly ordered -- these tests lock that
# in as a regression guard alongside the pre-TP1 fix). See exit_manager.py's inline comments at
# both call sites for the full rationale.
def test_structure_wins_over_catastrophe_same_tick_pre_tp1_put():
    """PUT, pre-TP1: worst_premium breaches the -50% catastrophe cap AND the closed-5m close
    breaches the structure level on the SAME tick -> structure wins, not premium_stop. Before
    the 2026-07-09 fix this fired premium_stop instead (compare
    test_structure_catastrophe_cap_still_fires_intrabar below, the twin fixture where only
    catastrophe breaches)."""
    s = _st(STRUCTURE_SHAPE, side="P", trigger_level=745.0, structure_stop_enabled=True, entry=1.00)
    assert s.runner_stop_premium == 0.50  # -50% cap
    dec = em.plan_exit_actions(s, best_premium=0.55, worst_premium=0.48, open_qty=5,
                               now_et=MORNING, last_closed_5m_close=745.5)  # BOTH breach
    assert dec.closes_position
    assert dec.actions[0].stage == "structure_stop"
    assert dec.actions[0].reason == "structure_stop @ 745.0"


def test_structure_wins_over_catastrophe_same_tick_pre_tp1_call():
    """CALL twin of the PUT test above: close < trigger_level breaches structure while
    worst_premium simultaneously breaches the catastrophe cap -> structure wins."""
    s = _st(STRUCTURE_SHAPE, side="C", trigger_level=745.0, structure_stop_enabled=True, entry=1.00)
    assert s.runner_stop_premium == 0.50
    dec = em.plan_exit_actions(s, best_premium=0.55, worst_premium=0.48, open_qty=5,
                               now_et=MORNING, last_closed_5m_close=744.5)  # BOTH breach
    assert dec.closes_position
    assert dec.actions[0].stage == "structure_stop"
    assert dec.actions[0].reason == "structure_stop @ 745.0"


def test_catastrophe_fires_alone_pre_tp1_call_no_structure_breach():
    """CALL symmetry check for test_structure_catastrophe_cap_still_fires_intrabar (PUT-side):
    catastrophe fires alone when the structure condition is NOT met on this tick (close stays
    on the thesis-intact side) -- catastrophe's whole job is intrabar protection BETWEEN closed
    bars, and it must keep doing that job when structure hasn't actually broken."""
    s = _st(STRUCTURE_SHAPE, side="C", trigger_level=745.0, structure_stop_enabled=True, entry=1.00)
    dec = em.plan_exit_actions(s, best_premium=0.55, worst_premium=0.48, open_qty=5,
                               now_et=MORNING, last_closed_5m_close=746.0)  # still "safe" for a CALL
    assert dec.closes_position and dec.actions[0].stage == "premium_stop"


def test_structure_wins_over_stop_same_tick_post_tp1_put():
    """PUT, post-TP1 runner: worst_premium breaches the BE-floor runner stop AND the closed-5m
    close breaches structure on the SAME tick -> structure wins (already the correct order in
    the post-TP1 branch; this pins it as a regression guard alongside the pre-TP1 fix)."""
    s = _st(STRUCTURE_SHAPE, side="P", trigger_level=745.0, structure_stop_enabled=True, entry=1.00)
    after_tp1 = em.plan_exit_actions(s, best_premium=2.55, worst_premium=2.40, open_qty=5,
                                     now_et=MORNING, last_closed_5m_close=744.0).state
    assert after_tp1.tp1_filled and after_tp1.runner_stop_premium == 1.00  # BE floor
    dec = em.plan_exit_actions(after_tp1, best_premium=1.05, worst_premium=0.99, open_qty=1,
                               now_et=MORNING, last_closed_5m_close=745.3)  # BOTH breach
    assert dec.closes_position
    assert dec.actions[0].stage == "structure_stop"
    assert dec.actions[0].reason == "structure_stop @ 745.0 (runner)"


def test_structure_wins_over_stop_same_tick_post_tp1_call():
    """CALL twin of the post-TP1 test above."""
    s = _st(STRUCTURE_SHAPE, side="C", trigger_level=745.0, structure_stop_enabled=True, entry=1.00)
    after_tp1 = em.plan_exit_actions(s, best_premium=2.55, worst_premium=2.40, open_qty=5,
                                     now_et=MORNING, last_closed_5m_close=746.0).state
    assert after_tp1.tp1_filled and after_tp1.runner_stop_premium == 1.00
    dec = em.plan_exit_actions(after_tp1, best_premium=1.05, worst_premium=0.99, open_qty=1,
                               now_et=MORNING, last_closed_5m_close=744.5)  # BOTH breach
    assert dec.closes_position
    assert dec.actions[0].stage == "structure_stop"
    assert dec.actions[0].reason == "structure_stop @ 745.0 (runner)"


def test_post_tp1_stop_fires_alone_when_structure_intact():
    """Post-TP1 priority-order completeness: when structure is NOT breached this tick, the
    ordinary BE-floor runner stop still fires exactly as before (structure checked, doesn't
    fire, falls through) -- the post-TP1 twin of
    test_catastrophe_fires_alone_pre_tp1_call_no_structure_breach."""
    s = _st(STRUCTURE_SHAPE, side="P", trigger_level=745.0, structure_stop_enabled=True, entry=1.00)
    after_tp1 = em.plan_exit_actions(s, best_premium=2.55, worst_premium=2.40, open_qty=5,
                                     now_et=MORNING, last_closed_5m_close=744.0).state
    dec = em.plan_exit_actions(after_tp1, best_premium=1.05, worst_premium=0.99, open_qty=1,
                               now_et=MORNING, last_closed_5m_close=744.0)  # stays "safe"
    assert dec.closes_position and dec.actions[0].stage == "be_stop"


def test_premium_mode_byte_identical_regardless_of_closed_5m_close():
    """THE premium-mode inertness proof for the ordering fix (vary-and-assert): a stop_mode==
    'premium' position (structure_stop_enabled=False at entry, even though it carries a real
    trigger_level=745.0 -- proves the guard, not the absence of a level, is what gates this)
    produces a BYTE-IDENTICAL decision whether last_closed_5m_close is omitted or set to a
    value that WOULD breach structure (745.5 for this PUT) -- proving the (a)/(a2) reorder
    cannot leak into premium mode, because the branch is gated on state.stop_mode=='structure',
    not on check ordering. Non-vacuous: 745.5 > 745.0 really is the PUT breach condition, so
    this is a genuine adversarial input, not a fixture that happens to never matter."""
    s = _st(STRUCTURE_SHAPE, side="P", trigger_level=745.0, structure_stop_enabled=False, entry=1.00)
    assert s.stop_mode == "premium" and s.trigger_level == 745.0 and s.premium_stop_pct == -0.20
    dec_without = em.plan_exit_actions(s, best_premium=0.85, worst_premium=0.79, open_qty=5,
                                       now_et=MORNING)
    dec_with = em.plan_exit_actions(s, best_premium=0.85, worst_premium=0.79, open_qty=5,
                                    now_et=MORNING, last_closed_5m_close=745.5)
    assert len(dec_without.actions) == len(dec_with.actions) == 1
    a0, a1 = dec_without.actions[0], dec_with.actions[0]
    assert (a0.kind, a0.qty, a0.stage, a0.reason, a0.new_stop_premium) == \
           (a1.kind, a1.qty, a1.stage, a1.reason, a1.new_stop_premium) == \
           ("SELL_ALL", 5, "premium_stop", "premium_stop @ 0.8", None)
    assert dec_without.state == dec_with.state


def test_structure_catastrophe_cap_still_fires_intrabar():
    """Even in structure mode the -50% catastrophe cap protects intrabar: the structure check
    now runs FIRST (2026-07-09 ordering fix) but does not fire because the closed-5m bar stays
    on the thesis-intact side (744.0, not > the 745.0 trigger for this PUT) -- the catastrophe
    cap is what actually exits. See test_structure_wins_over_catastrophe_same_tick_pre_tp1_put
    above for the case where BOTH conditions are true on the same tick."""
    s = _st(STRUCTURE_SHAPE, side="P", trigger_level=745.0, structure_stop_enabled=True, entry=1.00)
    assert s.runner_stop_premium == 0.50  # -50% cap
    dec = em.plan_exit_actions(s, best_premium=0.55, worst_premium=0.48, open_qty=5,
                               now_et=MORNING, last_closed_5m_close=744.0)  # close still "safe"
    assert dec.closes_position and dec.actions[0].stage == "premium_stop"


def test_structure_stale_feed_skips_silently():
    """last_closed_5m_close=None (the caller's fail-open value on a missing/stale feed) ->
    the structure check is simply SKIPPED this tick; no exit, no crash. The -50% cap and
    time stop remain the live protections that tick."""
    s = _st(STRUCTURE_SHAPE, side="P", trigger_level=745.0, structure_stop_enabled=True, entry=1.00)
    dec = em.plan_exit_actions(s, best_premium=1.05, worst_premium=1.00, open_qty=5,
                               now_et=MORNING, last_closed_5m_close=None)
    assert not dec.actions  # would have fired structure_stop had a fresh close been supplied
    # catastrophe cap unaffected by the missing feed:
    dec2 = em.plan_exit_actions(s, best_premium=0.55, worst_premium=0.48, open_qty=5,
                                now_et=MORNING, last_closed_5m_close=None)
    assert dec2.closes_position and dec2.actions[0].stage == "premium_stop"


def test_structure_default_omitted_kwarg_is_noop_for_legacy_callers():
    """Every EXISTING caller of plan_exit_actions omits last_closed_5m_close entirely --
    confirms the default (None) never fires a structure exit even on a structure-mode state
    whose close condition would otherwise be met (defense-in-depth beyond the flag itself)."""
    s = _st(STRUCTURE_SHAPE, side="P", trigger_level=745.0, structure_stop_enabled=True, entry=1.00)
    dec = em.plan_exit_actions(s, best_premium=1.05, worst_premium=1.00, open_qty=5, now_et=MORNING)
    assert not dec.actions


# --- legacy-state compatibility --------------------------------------------------
def test_legacy_exit_state_dict_without_structure_fields_loads_clean():
    """An exit-state.json record written BEFORE this build (no stop_mode/trigger_level/
    catastrophe_stop_pct keys) must deserialize to the exact legacy defaults, never crash."""
    legacy = {
        "symbol": "SPY260625P00600000", "side": "P", "entry_premium": 1.00,
        "total_qty": 5, "tp1_qty": 4, "runner_qty": 1,
        "premium_stop_pct": -0.20, "tp1_premium_pct": 1.5, "profit_lock_mode": "fixed",
        "tp1_filled": False, "runner_stop_premium": 0.80, "hwm_premium": 1.00,
        "profit_lock_armed": False, "strategy": "ribbon_ride",
    }
    s = em.ExitState.from_dict(legacy)
    assert s.stop_mode == "premium"
    assert s.trigger_level is None
    assert s.catastrophe_stop_pct == em.CATASTROPHE_STOP_PCT
    # and it manages a full tick with no crash / no accidental structure behavior:
    dec = em.plan_exit_actions(s, best_premium=1.05, worst_premium=1.00, open_qty=5,
                               now_et=MORNING, last_closed_5m_close=9999.0)
    assert not dec.actions  # a huge "close" never triggers anything in premium mode


def test_state_roundtrips_through_dict_with_structure_fields():
    s = _st(STRUCTURE_SHAPE, side="C", trigger_level=745.25, structure_stop_enabled=True, entry=1.23)
    s2 = em.ExitState.from_dict(s.to_dict())
    assert s2 == s
    assert s2.stop_mode == "structure" and s2.trigger_level == 745.25


# --- PRE-TP1 PROFIT-LOCK ARM SCOPE (2026-07-09 sim-vs-live scope-mismatch fix) -----------
# simulator_real:540-584 arms the profit-lock on ANY favorable touch (pre-TP1 included) and
# ratchets the SAME stop the pre-TP1 exit-ALL check reads; this core only armed at/after
# TP1. Every sim study passing profit_lock_threshold_pct>0 therefore credited pre-TP1
# breakeven scratches live could not take. Resolution: scope is now EXPRESSIBLE
# ("post_tp1" default = legacy live behavior; "full" = simulator parity) and armed by NO
# live shape. Twin pin on the simulator side: backtest/tests/test_profit_lock_scope_pin.py.
# If either side's semantics silently changes, one of these REDs and forces a conscious
# cross-machine decision (C14-class guard).

def _walk(shape, ticks, qty=5, entry=1.00):
    """Run a (best, worst) tick list through plan_exit_actions; returns (decisions, books).
    books = per-tick tuples of (action kinds, runner_stop, armed) for comparison."""
    s = _state(shape, qty=qty, entry=entry)
    open_qty = qty
    decs, books = [], []
    for best, worst in ticks:
        dec = em.plan_exit_actions(s, best_premium=best, worst_premium=worst,
                                   open_qty=open_qty, now_et=MORNING)
        decs.append(dec)
        books.append((tuple((a.kind, a.stage, a.qty) for a in dec.actions),
                      dec.state.runner_stop_premium, dec.state.profit_lock_armed))
        for a in dec.actions:
            if a.kind in ("SELL_PARTIAL", "SELL_ALL"):
                open_qty -= a.qty
        s = dec.state
        if open_qty <= 0:
            break
    return decs, books


def test_pre_tp1_lock_full_arms_then_scratches_at_floor():
    """scope='full': +6% touch arms the whole-position BE floor pre-TP1; the pullback
    through entry exits ALL at the floor (the sim's breakeven scratch), NOT at -6%."""
    decs, _ = _walk(VWAP_FULL_SCOPE, [(1.06, 1.01), (1.01, 0.99)])
    # tick 1: armed, no exit, stop ratcheted to BE and RECORDED
    d1 = decs[0]
    assert d1.state.profit_lock_armed is True
    assert d1.state.runner_stop_premium == 1.00
    assert any(a.kind == "RATCHET_STOP" and a.new_stop_premium == 1.00 for a in d1.actions)
    assert not d1.closes_position
    # tick 2: worst 0.99 <= BE floor -> exit ALL, reason discloses the lock floor
    d2 = decs[1]
    assert d2.closes_position
    a = d2.actions[0]
    # EXITMGR-STAGE-LABEL-CONFLATION: stage must match reason, not the static "premium_stop"
    # label the catastrophe cap uses -- this is the profit-lock floor scratch, not the cap.
    assert a.kind == "SELL_ALL" and a.stage == "profit_lock_floor"
    assert "profit_lock_floor" in a.reason


def test_pre_tp1_lock_default_scope_rides_the_same_ticks_to_the_stop():
    """Default scope on the SAME ticks: no pre-TP1 arming -- the pullback is a HOLD and
    only the original -6% stop can exit. Vary-and-assert twin of the test above: the two
    configs MUST produce different books or the knob is dead (C14)."""
    decs_default, books_default = _walk(VWAP_BODY, [(1.06, 1.01), (1.01, 0.99), (0.95, 0.93)])
    _, books_full = _walk(VWAP_FULL_SCOPE, [(1.06, 1.01), (1.01, 0.99), (0.95, 0.93)])
    # default: ticks 1-2 do nothing (no arm, no ratchet, stop stays -6% = 0.94)
    assert decs_default[0].state.profit_lock_armed is False
    assert decs_default[0].state.runner_stop_premium == 0.94
    assert not decs_default[0].actions and not decs_default[1].actions
    # default: only tick 3 (worst 0.93 <= 0.94) exits, at the ORIGINAL stop
    assert decs_default[2].closes_position
    assert "premium_stop" in decs_default[2].actions[0].reason
    # the books DIFFER (full scratched at tick 2; default rode to the -6% stop at tick 3)
    assert books_default != books_full


def test_pre_tp1_lock_full_same_tick_arm_and_floor_exit():
    """Simulator intra-bar ordering parity: a single tick that BOTH touches the arm level
    and trades back through the floor arms FIRST, then exits at the floor (sim:546-552
    runs before the stop check at sim:644)."""
    decs, _ = _walk(VWAP_FULL_SCOPE, [(1.06, 0.99)])
    d = decs[0]
    assert d.closes_position
    assert d.state.profit_lock_armed is True
    assert "profit_lock_floor" in d.actions[0].reason
    assert d.actions[0].stage == "profit_lock_floor"


def test_stage_disambiguates_catastrophe_cap_from_profit_lock_floor():
    """EXITMGR-STAGE-LABEL-CONFLATION guard: the static -50% catastrophe cap (scope=default,
    no lock ever arms) and the pre-TP1 profit-lock floor scratch (scope='full', armed then
    trades back through the floor) must NOT share a stage name, even though both are
    SELL_ALL pre-TP1 hard exits hitting the same `runner_stop` check. A regression that
    re-hardcodes stage="premium_stop" for both cases REDs here."""
    cap_decs, _ = _walk(VWAP_BODY, [(1.06, 1.01), (1.01, 0.99), (0.95, 0.93)])
    assert cap_decs[2].closes_position
    assert cap_decs[2].actions[0].stage == "premium_stop"
    floor_decs, _ = _walk(VWAP_FULL_SCOPE, [(1.06, 1.01), (1.01, 0.99)])
    assert floor_decs[1].closes_position
    assert floor_decs[1].actions[0].stage == "profit_lock_floor"
    assert cap_decs[2].actions[0].stage != floor_decs[1].actions[0].stage


def test_pre_tp1_lock_full_trailing_trails_hwm_before_tp1():
    """scope='full' + trailing: pre-TP1 the floor ratchets to HWM*(1-trail) once armed."""
    shape = {"premium_stop_pct": -0.20, "tp1_premium_pct": 9.9, "tp1_qty_fraction": 0.8,
             "profit_lock_mode": "trailing", "trail_pct": 0.125,
             "profit_lock_arm_scope": "full"}
    decs, _ = _walk(shape, [(2.00, 1.80), (1.80, 1.74)])
    # tick 1: armed at +100%, trail floor = 2.00 * 0.875 = 1.75 (> BE)
    assert decs[0].state.runner_stop_premium == 1.75
    assert not decs[0].closes_position
    # tick 2: worst 1.74 <= 1.75 -> whole position exits at the trailed floor pre-TP1
    assert decs[1].closes_position
    assert "profit_lock_floor" in decs[1].actions[0].reason


def test_pre_tp1_lock_absent_key_walk_is_byte_identical_to_explicit_post_tp1():
    """Inertness contract: a shape WITHOUT the new key and one with explicit 'post_tp1'
    must produce IDENTICAL decisions/states across a walk that exercises pre-TP1 dips,
    TP1 fill, and the post-TP1 BE stop."""
    ticks = [(1.02, 1.00), (1.06, 1.01), (1.01, 0.99), (1.45, 1.30), (1.20, 0.99)]
    decs_a, books_a = _walk(VWAP_BODY, ticks)
    decs_b, books_b = _walk(dict(VWAP_BODY, profit_lock_arm_scope="post_tp1"), ticks)
    assert books_a == books_b
    assert [d.state for d in decs_a] == [d.state for d in decs_b]
    # the walk really exercised TP1 (tick 4) then the BE stop (tick 5)
    assert decs_a[3].actions and decs_a[3].actions[0].stage == "tp1"
    assert decs_a[4].closes_position


def test_pre_tp1_lock_scope_survives_dict_roundtrip_and_legacy_defaults():
    s_full = _state(VWAP_FULL_SCOPE)
    assert s_full.profit_lock_arm_scope == "full"
    s2 = em.ExitState.from_dict(s_full.to_dict())
    assert s2 == s_full and s2.profit_lock_arm_scope == "full"
    # legacy persisted record (key absent) -> post_tp1, the exact pre-existing behavior
    d = s_full.to_dict()
    del d["profit_lock_arm_scope"]
    assert em.ExitState.from_dict(d).profit_lock_arm_scope == "post_tp1"
    # garbage normalizes to legacy, never crashes
    assert em.ExitState.from_entry(
        symbol="x", side="P", entry_premium=1.0, qty=3,
        exit_shape=dict(VWAP_BODY, profit_lock_arm_scope="banana"),
    ).profit_lock_arm_scope == "post_tp1"


# --- ISOLATED PRE-TP1 BE FLOOR (2026-08-02, EXIT-HYBRID-PRETP1-FLOOR iteration 4) --------
# Iteration 3 (profit_lock_mode="fixed" + arm_scope="full") proved CONFOUNDED: "fixed" mode
# is read by BOTH the pre-TP1 arm branch AND the post-TP1 runner branch, so it silently
# disables the post-TP1 15%-trailing chandelier for any trade reaching TP1 -- 25 of 27
# degraded trades in that study were THAT mechanism, not the pre-TP1 whipsaw the hypothesis
# targeted. `pre_tp1_be_floor_arm_pct` is a NEW, fully independent knob: arms a BE-floor-only
# scratch pre-TP1 without ever touching profit_lock_mode/profit_lock_armed, so post-TP1 stays
# governed purely by profit_lock_mode (still "trailing" in every test below) -- the 4th
# candidate this queue item calls for.
ISO_FLOOR_SHAPE = dict(TRAIL_SHAPE, pre_tp1_be_floor_arm_pct=0.05)  # -8%/+30%/0.667/trailing


def test_pre_tp1_isolated_floor_arms_then_scratches_at_be():
    """+5% touch arms the BE-only floor pre-TP1; the pullback through entry exits ALL at the
    floor (a scratch), not at the -8% premium stop -- and profit_lock_armed stays FALSE
    (unlike arm_scope='full', which sets it True -- see next test)."""
    decs, _ = _walk(ISO_FLOOR_SHAPE, [(1.05, 1.01), (1.01, 0.99)])
    d1 = decs[0]
    assert d1.state.runner_stop_premium == 1.00      # BE floor, not a trail
    assert any(a.kind == "RATCHET_STOP" and a.new_stop_premium == 1.00 for a in d1.actions)
    assert not d1.closes_position
    d2 = decs[1]
    assert d2.closes_position
    a = d2.actions[0]
    assert a.kind == "SELL_ALL" and a.stage == "profit_lock_floor"
    assert "profit_lock_floor" in a.reason


def test_pre_tp1_isolated_floor_never_sets_profit_lock_armed():
    """The defining difference from arm_scope='full': this knob must NEVER flip
    profit_lock_armed, because that flag also gates post-TP1 mechanics. A regression that
    reuses profit_lock_armed for this knob would silently change post-TP1 behavior too."""
    decs, _ = _walk(ISO_FLOOR_SHAPE, [(1.05, 1.02), (1.02, 0.99)])
    assert decs[0].state.profit_lock_armed is False
    assert decs[1].state.profit_lock_armed is False


def test_pre_tp1_isolated_floor_does_not_trail_pre_tp1_unlike_arm_scope_full():
    """Contrast with test_pre_tp1_lock_full_trailing_trails_hwm_before_tp1: even with
    profit_lock_mode='trailing', the isolated floor NEVER ratchets past entry pre-TP1 (no
    trailing pre-TP1 -- that is the whole point of the 4th candidate, discriminating a BE
    scratch from the whipsaw a full pre-TP1 trail causes). tp1_premium_pct=9.9 (unreachable)
    isolates the pre-TP1 mechanism, same convention as
    test_pre_tp1_lock_full_trailing_trails_hwm_before_tp1."""
    shape = dict(ISO_FLOOR_SHAPE, tp1_premium_pct=9.9)
    decs, _ = _walk(shape, [(2.00, 1.80), (1.90, 1.70)])
    # armed at tick 1 (best 2.00 >= 1.05), floor = entry (1.00), NOT hwm*(1-trail) (2.00*0.875=1.75)
    assert decs[0].state.runner_stop_premium == 1.00
    assert not decs[0].closes_position   # worst 1.80 > 1.00, still open
    # tick 2: still no exit (worst 1.70 > 1.00) and floor is STILL just BE, no further ratchet
    assert not decs[1].closes_position
    assert decs[1].state.runner_stop_premium == 1.00


def test_pre_tp1_isolated_floor_post_tp1_trailing_byte_identical_to_control():
    """The headline safety property: a full walk through TP1 and into the post-TP1 chandelier
    must be BYTE-IDENTICAL whether or not the isolated pre-TP1 floor is set, because TP1 fill
    unconditionally sets profit_lock_armed=True itself (line ~456) regardless of this knob.
    This is what makes the +$15,774/35-for-35 runner engine provably untouched."""
    ticks = [(1.20, 1.10), (1.45, 1.30), (1.90, 1.60), (1.60, 1.35)]
    decs_ctl, books_ctl = _walk(TRAIL_SHAPE, ticks)
    decs_iso, books_iso = _walk(ISO_FLOOR_SHAPE, ticks)
    # the walk really exercised TP1 (tick 2, TRAIL_SHAPE tp1 @ +30% = 1.30) then post-TP1 trail
    assert decs_ctl[1].actions and decs_ctl[1].actions[0].stage == "tp1"
    # books = (action kinds/stages/qtys, runner_stop, armed) -- the MECHANISM, byte-identical
    # from TP1 onward regardless of the isolated pre-TP1 knob (tick 0 legitimately differs:
    # the isolated floor arms pre-TP1, control does not -- that's the tested mechanism, not
    # a bug). Full ExitState equality is intentionally NOT asserted here: the two states
    # legitimately differ in the static pre_tp1_be_floor_arm_pct config field itself.
    assert books_ctl[1:] == books_iso[1:]
    same_fields = ("tp1_filled", "runner_stop_premium", "hwm_premium", "profit_lock_armed")
    for f in same_fields:
        assert [getattr(d.state, f) for d in decs_ctl[1:]] == [getattr(d.state, f) for d in decs_iso[1:]]


def test_pre_tp1_isolated_floor_inert_when_none():
    """Vary-and-assert twin (C14): the default (key absent -> None) must be byte-identical to
    TRAIL_SHAPE with no isolated floor at all -- this is a NEW additive knob, never a silent
    default-on."""
    ticks = [(1.05, 1.01), (1.01, 0.99), (0.95, 0.90)]
    decs_default, books_default = _walk(TRAIL_SHAPE, ticks)
    decs_none, books_none = _walk(dict(TRAIL_SHAPE, pre_tp1_be_floor_arm_pct=None), ticks)
    assert books_default == books_none
    assert [d.state for d in decs_default] == [d.state for d in decs_none]
    # and the books DIFFER from the armed cell above (dead-knob guard)
    _, books_armed = _walk(ISO_FLOOR_SHAPE, ticks)
    assert books_default != books_armed


def test_pre_tp1_isolated_floor_coexists_independent_of_arm_scope_full():
    """Can be combined with (or exist entirely apart from) profit_lock_arm_scope='full' --
    the two mechanisms are orthogonal (different fields, both additive)."""
    combo = dict(ISO_FLOOR_SHAPE, profit_lock_arm_scope="full")
    s = _state(combo)
    assert s.pre_tp1_be_floor_arm_pct == 0.05
    assert s.profit_lock_arm_scope == "full"


def test_pre_tp1_isolated_floor_survives_dict_roundtrip_and_legacy_default():
    s = _state(ISO_FLOOR_SHAPE)
    assert s.pre_tp1_be_floor_arm_pct == 0.05
    s2 = em.ExitState.from_dict(s.to_dict())
    assert s2 == s and s2.pre_tp1_be_floor_arm_pct == 0.05
    # legacy persisted record (key absent) -> None, the exact pre-2026-08-02 behavior
    d = s.to_dict()
    del d["pre_tp1_be_floor_arm_pct"]
    assert em.ExitState.from_dict(d).pre_tp1_be_floor_arm_pct is None
    # and a fresh from_entry() with no key in the exit_shape also defaults to None
    assert em.ExitState.from_entry(
        symbol="x", side="P", entry_premium=1.0, qty=3, exit_shape=TRAIL_SHAPE,
    ).pre_tp1_be_floor_arm_pct is None


if __name__ == "__main__":
    import sys
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f"PASS  {t.__name__}"); passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
