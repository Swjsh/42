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


def test_structure_catastrophe_cap_still_fires_intrabar():
    """Even in structure mode the -50% catastrophe cap protects intrabar: a worst_premium
    crash past the (demoted) stop fires BEFORE the structure check is even reached."""
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
