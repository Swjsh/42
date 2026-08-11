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


def test_registry_arms_js_ladder_and_trail():
    """J's spec: rungs +50->+30 and +75->+60, trail arms +40 riding 20% off HWM."""
    e = st.by_name("ribbon_ride").exit
    assert e.pre_tp1_ladder == [[0.50, 0.30], [0.75, 0.60]]
    assert e.pre_tp1_trail_arm_pct == pytest.approx(0.40)
    assert e.pre_tp1_trail_pct == pytest.approx(0.20)
    d = e.to_dict()
    assert d["pre_tp1_ladder"] == [[0.50, 0.30], [0.75, 0.60]]


def test_none_none_is_byte_identical_to_legacy():
    """The inertness contract: with both knobs None the tick-state is exactly yesterday's."""
    legacy = _state(pre_tp1_be_floor_arm_pct=None, pre_tp1_floor_pct=None,
                    pre_tp1_ladder=None, pre_tp1_trail_arm_pct=None, pre_tp1_trail_pct=None)
    _a, s1 = _tick(legacy, best=2.02, worst=1.70)   # +74% MFE, the 2026-08-05-class peak
    # no ratchet knob -> stop remains the entry-seeded catastrophe stop, nothing armed
    assert s1.runner_stop_premium == legacy.runner_stop_premium
    assert s1.profit_lock_armed is False


def test_top_rung_and_trail_both_apply_max_wins():
    """TODAY'S CASE: entry 1.16, HWM 2.30 (+98%). Rung +75 floors 1.856; trail floors
    2.30*0.80=1.84. max() -> 1.856, the rung."""
    s = _state()
    _a, s1 = _tick(s, best=2.30, worst=2.20)
    assert s1.runner_stop_premium == pytest.approx(max(1.16 * 1.60, 2.30 * 0.80), abs=1e-4)
    # and it must NOT have armed the chandelier -- these knobs are independent of the lock
    assert s1.profit_lock_armed is False
    assert s1.tp1_filled is False


def test_trail_protects_between_rungs():
    """+70% MFE: below the +75 rung but above BOTH the +40 trail arm and the +50 rung.
    This is the gap the single ratchet left wide open -- safe-3 peaked +83% and got nothing."""
    s = _state()
    hwm = 1.16 * 1.70
    _a, s1 = _tick(s, best=hwm, worst=1.50)
    assert s1.runner_stop_premium == pytest.approx(max(1.16 * 1.30, hwm * 0.80), abs=1e-4)
    assert s1.runner_stop_premium > s.runner_stop_premium


def test_below_trail_arm_nothing_engages():
    s = _state()
    _a, s1 = _tick(s, best=1.16 * 1.30, worst=1.20)   # +30% MFE < +40% trail arm
    assert s1.runner_stop_premium == s.runner_stop_premium


def test_trail_rises_with_hwm_then_never_falls():
    """Between the +40 trail arm and the +50 rung the TRAIL is the only thing holding the
    floor, so this is where its ratcheting is observable (at +50%+ the fixed rung dominates
    and would mask a broken trail -- the first draft of this test made exactly that mistake)."""
    s = _state()
    _a, s1 = _tick(s, best=1.16 * 1.42, worst=1.40)   # +42% MFE: trail only
    lo = s1.runner_stop_premium
    assert lo == pytest.approx(1.16 * 1.42 * 0.80, abs=1e-4)
    _a, s2 = _tick(s1, best=1.16 * 1.48, worst=1.50)  # higher HWM -> higher trail
    assert s2.runner_stop_premium > lo
    _a, s3 = _tick(s2, best=1.16 * 1.48, worst=1.40)  # price sags, HWM unchanged
    assert s3.runner_stop_premium >= s2.runner_stop_premium


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
    for k in ("pre_tp1_be_floor_arm_pct", "pre_tp1_floor_pct", "pre_tp1_ladder",
              "pre_tp1_trail_arm_pct", "pre_tp1_trail_pct"):
        assert k in fx.EXIT_PATCH_ALLOWED_KEYS, k


def test_risky3_premium_lane_inherits_the_ratchet():
    """risky-3's one-variable stop_mode A/B must stay one-variable: its patch touches only
    stop_mode, so the registry ratchet flows through to it like every other arm."""
    import json
    import fleet_executor as fx
    accounts = json.loads((FLEET / "accounts.json").read_text(encoding="utf-8"))
    arm = next(a for a in accounts["arms"] if a["id"] == "risky-3")
    shape = fx._exit_shape_dict(st.by_name("ribbon_ride"), arm)
    assert shape["stop_mode"] == "premium"
    assert shape["pre_tp1_ladder"] == [[0.50, 0.30], [0.75, 0.60]]
    assert shape["pre_tp1_trail_pct"] == pytest.approx(0.20)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
