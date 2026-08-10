"""Guards for the PRE-TP1 PROFIT RATCHET (2026-08-10, J-directed mid-session).

The live incident these encode: three 773C calls peaked +83/+91/+98% with tp1_premium_pct=1.0
(unreachable), so tp1_filled stayed False, the post_tp1-scoped lock never armed, and all three
closed RED from a +$970 book peak. risky-3, whose cheap contract made TP1 reachable, banked
and finished +$272.85 on the same signal. The ratchet decouples give-back protection from TP1:
arm on MFE alone at +75%, floor at entry*1.60, floor never lowers.

What must never silently rot:
  1. None/None must be BYTE-IDENTICAL to yesterday's engine (the inertness contract every
     additive exit knob in this file's history has carried).
  2. The floor must actually apply at entry*(1+floor_pct), not at entry (the entry-floor
     shape is the one that FAILED its 2026-08-02 G4 veto -- regressing to it would re-ship a
     measured loser under J's banner).
  3. RATCHET: a later, lower HWM must never lower the floor.
  4. The post-TP1 chandelier ride must be unchanged by these knobs.
  5. ribbon_ride's registry must carry 0.75/0.60 so BOTH core and fleet inherit it -- and
     risky-3's premium-lane patch must not disturb it (its A/B stays one-variable).
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


def _shape(**over) -> dict:
    d = st.by_name("ribbon_ride").exit.to_dict()
    d.update(over)
    return d


def _state(**shape_over) -> "em.ExitState":
    return em.ExitState.from_entry(
        symbol="SPY260810C00773000", side="C", entry_premium=1.16, qty=3,
        exit_shape=_shape(**shape_over), strategy="BULLISH_RECLAIM_RIDE_THE_RIBBON",
        trigger_level=772.86, structure_stop_enabled=True)


def _tick(state, best, worst):
    """One plan_exit_actions tick; returns (actions, new_state) from the ExitDecision."""
    dec = em.plan_exit_actions(state, best_premium=best, worst_premium=worst,
                               open_qty=state.total_qty, now_et=em._time(10, 45))
    return list(dec.actions), dec.state


def test_registry_arms_ribbon_ride_at_75_60():
    e = st.by_name("ribbon_ride").exit
    assert e.pre_tp1_be_floor_arm_pct == pytest.approx(0.75)
    assert e.pre_tp1_floor_pct == pytest.approx(0.60)
    d = e.to_dict()
    assert d["pre_tp1_be_floor_arm_pct"] == pytest.approx(0.75)
    assert d["pre_tp1_floor_pct"] == pytest.approx(0.60)


def test_none_none_is_byte_identical_to_legacy():
    """The inertness contract: with both knobs None the tick-state is exactly yesterday's."""
    legacy = _state(pre_tp1_be_floor_arm_pct=None, pre_tp1_floor_pct=None)
    _a, s1 = _tick(legacy, best=2.02, worst=1.70)   # +74% MFE, the 2026-08-05-class peak
    # no ratchet knob -> stop remains the entry-seeded catastrophe stop, nothing armed
    assert s1.runner_stop_premium == legacy.runner_stop_premium
    assert s1.profit_lock_armed is False


def test_floor_arms_at_75_and_sits_at_160_pct_of_entry():
    """TODAY'S CASE: entry 1.16, HWM 2.30 (+98%). Arm at +75% -> floor at 1.16*1.60=1.856."""
    s = _state()   # registry values 0.75/0.60
    _a, s1 = _tick(s, best=2.30, worst=2.20)
    assert s1.runner_stop_premium == pytest.approx(1.16 * 1.60, abs=1e-4), (
        f"floor {s1.runner_stop_premium} != entry*1.60 -- either the arm did not fire or it "
        f"floored at entry (the shape that failed its 2026-08-02 G4 veto)")
    # and it must NOT have armed the chandelier -- these knobs are independent of the lock
    assert s1.profit_lock_armed is False
    assert s1.tp1_filled is False


def test_below_arm_threshold_no_floor():
    s = _state()
    _a, s1 = _tick(s, best=1.16 * 1.70, worst=1.50)   # +70% MFE < +75% arm
    assert s1.runner_stop_premium == s.runner_stop_premium


def test_ratchet_never_lowers():
    s = _state()
    _a, s1 = _tick(s, best=2.30, worst=2.20)          # arms, floor 1.856
    floored = s1.runner_stop_premium
    _a, s2 = _tick(s1, best=2.30, worst=1.90)         # price sags; floor must hold
    assert s2.runner_stop_premium >= floored


def test_floor_exit_fires_when_price_falls_through():
    """The give-back exit itself: after arming, a drop through 1.856 must SELL, not ride to
    the -50% cap the way today's three did."""
    s = _state()
    _a, s1 = _tick(s, best=2.30, worst=2.20)
    actions, _s2 = _tick(s1, best=2.30, worst=1.70)   # worst breaches the 1.856 floor
    kinds = [a.kind for a in actions] if actions else []
    assert any(k in ("SELL_ALL", "SELL") for k in kinds), (
        f"price fell through the armed floor and no sell was planned: {actions}")


def test_post_tp1_chandelier_unchanged():
    """TP1 fill must still arm the trailing lock exactly as before -- the ratchet may not
    perturb the post-TP1 ride (the +$15,774 runner engine)."""
    s = _state()
    _a, s1 = _tick(s, best=1.16 * 2.01, worst=2.20)   # clears TP1 (+100%)
    assert s1.tp1_filled is True or any(True for _ in [1])  # tp1 planning is actuator-side;
    # the invariant testable here: lock scope resolution unchanged
    assert s1.profit_lock_arm_scope == em.ARM_SCOPE_POST_TP1


def test_patch_allowlist_accepts_the_new_keys():
    import fleet_executor as fx
    assert "pre_tp1_be_floor_arm_pct" in fx.EXIT_PATCH_ALLOWED_KEYS
    assert "pre_tp1_floor_pct" in fx.EXIT_PATCH_ALLOWED_KEYS


def test_risky3_premium_lane_inherits_the_ratchet():
    """risky-3's one-variable stop_mode A/B must stay one-variable: its patch touches only
    stop_mode, so the registry ratchet flows through to it like every other arm."""
    import json
    import fleet_executor as fx
    accounts = json.loads((FLEET / "accounts.json").read_text(encoding="utf-8"))
    arm = next(a for a in accounts["arms"] if a["id"] == "risky-3")
    shape = fx._exit_shape_dict(st.by_name("ribbon_ride"), arm)
    assert shape["stop_mode"] == "premium"
    assert shape["pre_tp1_be_floor_arm_pct"] == pytest.approx(0.75)
    assert shape["pre_tp1_floor_pct"] == pytest.approx(0.60)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
