"""Guards for the PRE-TP1 RIBBON CONFIRMATION BUFFER (2026-08-11, prereg RIBBON-CONFIRM).

THE DEFECT. `plan_exit_actions` fired a full pre-TP1 SELL_ALL on a SINGLE flipped ribbon tick.
exit_manager's own comment recorded that the spread/buffer rule was "aspirational, never
implemented". On a 60-second heartbeat, one minute of wobble liquidated the whole position.

LIVE EXHIBIT (2026-08-11): three PROFITABLE puts killed in 11 minutes at 57-60 second holds
(+20%, +13%, +7%). The 09:46 771P dumped at 0.54 printed 1.29 at 14:41 -- our own bold-2 fill.
Holding 10 lots was +$840 against the +$90 taken: 10.7% capture of a move identified at the
correct minute.

WHAT MUST NEVER ROT:
  1. INERTNESS: None (and 1) reproduce single-tick behaviour byte-identically. Every arm
     except the armed trial runs None, so a regression here silently changes every arm.
  2. N=2 requires two CONSECUTIVE ticks; the first flip HOLDS.
  3. A clean tick RESETS the streak -- flip/clean/flip must not accumulate to a sell.
  4. POST-TP1 IS UNTOUCHED. The runner ribbon exit has a different give-back profile and the
     prereg scopes the change pre-TP1 only.
  5. The streak SURVIVES to_dict/from_dict -- a mid-position process restart must not reset
     confirmation progress (the state file is the only carrier between ticks).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
if str(FLEET) not in sys.path:
    sys.path.insert(0, str(FLEET))

import exit_manager as em  # noqa: E402
import strategies as st  # noqa: E402


def _state(confirm=None, tp1_filled=False):
    shape = st.by_name("ribbon_ride").exit.to_dict()
    shape["pre_tp1_ribbon_confirm_ticks"] = confirm
    s = em.ExitState.from_entry(
        symbol="SPY260811P00771000", side="P", entry_premium=0.45, qty=10,
        exit_shape=shape, strategy="RIBBON", trigger_level=None,
        structure_stop_enabled=False)
    return em.replace(s, tp1_filled=tp1_filled)


def _tick(state, flip, best=0.54, worst=0.53):
    dec = em.plan_exit_actions(state, best_premium=best, worst_premium=worst,
                               open_qty=10, now_et=em._time(9, 47), ribbon_flip_back=flip)
    return [a.stage for a in dec.actions], dec.state


def test_default_registry_is_none_every_arm_unarmed():
    assert st.by_name("ribbon_ride").exit.pre_tp1_ribbon_confirm_ticks is None


def test_inertness_none_sells_on_the_first_flip():
    """The single-tick contract every unarmed arm still runs."""
    stages, _ = _tick(_state(None), flip=True)
    assert "ribbon_flip" in stages


def test_inertness_one_is_identical_to_none():
    a, _ = _tick(_state(None), flip=True)
    b, _ = _tick(_state(1), flip=True)
    assert a == b == ["ribbon_flip"]


def test_n2_holds_the_first_flip_then_sells_the_second():
    """THE INCIDENT SHAPE: one wobbly tick must not liquidate."""
    s = _state(2)
    stages1, s1 = _tick(s, flip=True)
    assert stages1 == [], f"first flip must HOLD, got {stages1}"
    assert s1.ribbon_flip_streak == 1
    stages2, _ = _tick(s1, flip=True)
    assert "ribbon_flip" in stages2, "second consecutive flip must sell"


def test_a_clean_tick_resets_the_streak():
    """flip / clean / flip must NOT sell -- non-consecutive is not confirmation."""
    s = _state(2)
    _st1, s1 = _tick(s, flip=True)
    assert s1.ribbon_flip_streak == 1
    _st2, s2 = _tick(s1, flip=False)
    assert s2.ribbon_flip_streak == 0, "clean tick must reset"
    stages3, _ = _tick(s2, flip=True)
    assert stages3 == [], "post-reset first flip must HOLD again"


def test_post_tp1_runner_exit_is_untouched_by_confirmation():
    """Scoped pre-TP1 only: a TP1-filled position still exits on a single flip."""
    s = _state(confirm=2, tp1_filled=True)
    stages, _ = _tick(s, flip=True)
    assert "ribbon_flip" in stages, (
        "post-TP1 runner ribbon exit must NOT require confirmation -- prereg scopes the "
        f"change pre-TP1 only; got {stages}")


def test_streak_survives_serialization_roundtrip():
    """A process restart mid-position must not reset confirmation progress."""
    s = _state(2)
    _stages, s1 = _tick(s, flip=True)
    assert s1.ribbon_flip_streak == 1
    back = em.ExitState.from_dict(s1.to_dict())
    assert back.ribbon_flip_streak == 1
    assert back.pre_tp1_ribbon_confirm_ticks == 2
    stages2, _ = _tick(back, flip=True)
    assert "ribbon_flip" in stages2, "restored state must sell on its next consecutive flip"


def test_reason_string_reports_the_confirmation_count():
    s = _state(2)
    _s1, s1 = _tick(s, flip=True)
    dec = em.plan_exit_actions(s1, best_premium=0.54, worst_premium=0.53, open_qty=10,
                               now_et=em._time(9, 48), ribbon_flip_back=True)
    reason = dec.actions[0].reason
    assert "2/2" in reason, f"reason must show confirmation progress, got {reason!r}"


def test_confirmation_does_not_suppress_a_breached_stop():
    """A held ribbon tick must never mask a real stop -- the catastrophe cap still binds."""
    s = _state(2)
    dec = em.plan_exit_actions(s, best_premium=0.45, worst_premium=0.20, open_qty=10,
                               now_et=em._time(9, 47), ribbon_flip_back=True)
    assert any(a.kind == "SELL_ALL" for a in dec.actions), (
        "a -55% premium must still exit even while ribbon confirmation is pending")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
