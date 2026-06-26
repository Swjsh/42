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
VWAP_SHAPE = {"premium_stop_pct": -0.08, "tp1_premium_pct": 0.3,
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


def test_entry_split_vwap_667pct():
    """vwap 0.667 on qty3 -> tp1=2, runner=1; -8% stop."""
    s = _state(VWAP_SHAPE, qty=3)
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


def test_tp1_partial_vwap_qty3_sells_2():
    s = _state(VWAP_SHAPE, qty=3, entry=1.00)  # TP1 at +30% = 1.30, tp1_qty=2
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


# --- runner ride: trailing chandelier (stage 4, vwap = trailing) --------------
def test_runner_trailing_ratchets_with_hwm():
    """vwap (trailing) runner: stop trails to HWM*(1-trail_pct) once armed."""
    s = _state(VWAP_SHAPE, qty=3, entry=1.00)  # trail_pct default 0.125
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
    s = _state(VWAP_SHAPE, qty=3, entry=1.00)
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
    s = _state(VWAP_SHAPE, qty=3, entry=1.23, strategy="vwap_continuation")
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
