"""ADDITIVE-FIELDS-INERT guard (2026-08-18, weekly-options multi-day exit management
workstream). exit_manager.ExitState gained two new fields this session --
theta_budget_hit / theta_budget_reason (see exit_manager.py's dataclass field comment for
the full rationale). They are informational pass-through fields a CALLER-SIDE wrapper
(automation/state/weekly/weekly_exit_gate.py) sets on the shared ExitState record;
plan_exit_actions itself must NEVER read or act on them.

exit_manager.py is the LIVE state machine for the entire SPY book (both core accounts +
all 5 fleet arms) -- an additive field is the maximum acceptable blast radius for a change
to this file (per this workstream's brief: "Change NO existing logic, NO existing
thresholds, NO existing control flow"). This test proves the addition is genuinely inert:
for a battery of pre-existing SPY-shaped scenarios (premium stop, time stop, ribbon-flip,
TP1 partial, runner target, runner trail-stop, structure stop -- both pre- and post-TP1),
plan_exit_actions returns a BYTE-IDENTICAL decision (every action's kind/qty/reason/stage/
new_stop_premium, and every OTHER field of the resulting ExitState) regardless of what
these two new fields are set to on the INPUT state.

RED-PROOF (quoted in the session report): a temporary one-line edit to exit_manager.
plan_exit_actions that short-circuited on theta_budget_hit made every scenario in this
file fail before the edit was reverted.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from datetime import time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "automation" / "state" / "fleet"))
import exit_manager as em  # noqa: E402

RIBBON_SHAPE = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.5,
                "tp1_qty_fraction": 0.8, "profit_lock_mode": "fixed"}
TRAIL_SHAPE = {"premium_stop_pct": -0.08, "tp1_premium_pct": 0.3,
               "tp1_qty_fraction": 0.667, "profit_lock_mode": "trailing"}
STRUCTURE_SHAPE = {"premium_stop_pct": -0.20, "tp1_premium_pct": 1.0,
                    "tp1_qty_fraction": 0.667, "profit_lock_mode": "trailing",
                    "stop_mode": "structure", "catastrophe_stop_pct": -0.50}
MORNING = time(11, 0)
AFTER_STOP = time(15, 51)


def _pre_tp1_state(shape, *, qty, entry, theta_hit, theta_reason,
                    trigger_level=None, structure_stop_enabled=False):
    st = em.ExitState.from_entry(symbol="SPY260825C00600000", side="C", entry_premium=entry,
                                  qty=qty, exit_shape=shape, strategy="x",
                                  trigger_level=trigger_level,
                                  structure_stop_enabled=structure_stop_enabled)
    return replace(st, theta_budget_hit=theta_hit, theta_budget_reason=theta_reason)


def _post_tp1_state(shape, *, qty, entry, theta_hit, theta_reason, hwm=None,
                     trigger_level=None, structure_stop_enabled=False):
    st = _pre_tp1_state(shape, qty=qty, entry=entry, theta_hit=theta_hit,
                         theta_reason=theta_reason, trigger_level=trigger_level,
                         structure_stop_enabled=structure_stop_enabled)
    return replace(st, tp1_filled=True, runner_stop_premium=entry,
                    hwm_premium=(hwm if hwm is not None else entry), profit_lock_armed=True)


# Each scenario: (label, state_builder(theta_hit, theta_reason) -> ExitState, plan kwargs)
SCENARIOS: "list[tuple[str, Callable, dict]]" = [
    ("pre_tp1_hold",
     lambda th, tr: _pre_tp1_state(RIBBON_SHAPE, qty=5, entry=1.00, theta_hit=th,
                                    theta_reason=tr),
     dict(best_premium=1.10, worst_premium=1.05, open_qty=5, now_et=MORNING)),
    ("pre_tp1_premium_stop",
     lambda th, tr: _pre_tp1_state(RIBBON_SHAPE, qty=5, entry=1.00, theta_hit=th,
                                    theta_reason=tr),
     dict(best_premium=0.85, worst_premium=0.79, open_qty=5, now_et=MORNING)),
    ("pre_tp1_time_stop",
     lambda th, tr: _pre_tp1_state(RIBBON_SHAPE, qty=5, entry=1.00, theta_hit=th,
                                    theta_reason=tr),
     dict(best_premium=1.10, worst_premium=1.05, open_qty=5, now_et=AFTER_STOP)),
    ("pre_tp1_ribbon_flip",
     lambda th, tr: _pre_tp1_state(RIBBON_SHAPE, qty=5, entry=1.00, theta_hit=th,
                                    theta_reason=tr),
     dict(best_premium=1.10, worst_premium=1.05, open_qty=5, now_et=MORNING,
          ribbon_flip_back=True)),
    ("tp1_partial",
     lambda th, tr: _pre_tp1_state(RIBBON_SHAPE, qty=5, entry=1.00, theta_hit=th,
                                    theta_reason=tr),
     dict(best_premium=2.55, worst_premium=2.40, open_qty=5, now_et=MORNING)),
    ("pre_tp1_structure_stop",
     lambda th, tr: _pre_tp1_state(STRUCTURE_SHAPE, qty=5, entry=1.00, theta_hit=th,
                                    theta_reason=tr, trigger_level=600.0,
                                    structure_stop_enabled=True),
     dict(best_premium=1.10, worst_premium=1.05, open_qty=5, now_et=MORNING,
          last_closed_5m_close=599.0)),
    ("post_tp1_hold",
     lambda th, tr: _post_tp1_state(TRAIL_SHAPE, qty=3, entry=1.00, theta_hit=th,
                                     theta_reason=tr),
     dict(best_premium=1.20, worst_premium=1.10, open_qty=1, now_et=MORNING)),
    ("post_tp1_runner_target",
     lambda th, tr: _post_tp1_state(TRAIL_SHAPE, qty=3, entry=1.00, theta_hit=th,
                                     theta_reason=tr),
     dict(best_premium=3.60, worst_premium=3.55, open_qty=1, now_et=MORNING)),
    ("post_tp1_runner_trail_stop",
     lambda th, tr: _post_tp1_state(TRAIL_SHAPE, qty=3, entry=1.00, theta_hit=th,
                                     theta_reason=tr, hwm=1.00),
     dict(best_premium=2.00, worst_premium=1.70, open_qty=1, now_et=MORNING)),
    ("post_tp1_ribbon_flip",
     lambda th, tr: _post_tp1_state(TRAIL_SHAPE, qty=3, entry=1.00, theta_hit=th,
                                     theta_reason=tr),
     dict(best_premium=1.20, worst_premium=1.10, open_qty=1, now_et=MORNING,
          ribbon_flip_back=True)),
    ("post_tp1_time_stop",
     lambda th, tr: _post_tp1_state(TRAIL_SHAPE, qty=3, entry=1.00, theta_hit=th,
                                     theta_reason=tr),
     dict(best_premium=1.20, worst_premium=1.10, open_qty=1, now_et=AFTER_STOP)),
    ("post_tp1_structure_stop",
     lambda th, tr: _post_tp1_state(STRUCTURE_SHAPE, qty=3, entry=1.00, theta_hit=th,
                                     theta_reason=tr, trigger_level=600.0,
                                     structure_stop_enabled=True),
     dict(best_premium=1.20, worst_premium=1.10, open_qty=1, now_et=MORNING,
          last_closed_5m_close=599.0)),
]


def _state_dict_minus_theta(state: em.ExitState) -> dict:
    d = state.to_dict()
    d.pop("theta_budget_hit")
    d.pop("theta_budget_reason")
    return d


def _actions_as_tuples(actions):
    return tuple((a.kind, a.qty, a.reason, a.stage, a.new_stop_premium) for a in actions)


def test_inert_battery_every_scenario_byte_identical_regardless_of_theta_fields():
    assert len(SCENARIOS) >= 10, "battery must cover pre-TP1, TP1, and post-TP1 branches"
    for label, build, kwargs in SCENARIOS:
        state_false = build(False, "")
        state_true = build(True, "some prior weekly-lane note (hypothetical -- these "
                                  "fields are never set on a real SPY position)")
        dec_false = em.plan_exit_actions(state_false, **kwargs)
        dec_true = em.plan_exit_actions(state_true, **kwargs)

        assert _actions_as_tuples(dec_false.actions) == _actions_as_tuples(dec_true.actions), (
            f"[{label}] actions diverged when only theta_budget_hit/reason varied")
        assert _state_dict_minus_theta(dec_false.state) == _state_dict_minus_theta(dec_true.state), (
            f"[{label}] resulting state diverged (excluding the two varied fields)")
        # the two new fields must simply carry through unchanged from whatever the INPUT
        # state already had -- proving plan_exit_actions never sets/clears them itself.
        assert dec_false.state.theta_budget_hit is False
        assert dec_false.state.theta_budget_reason == ""
        assert dec_true.state.theta_budget_hit is True
        assert dec_true.state.theta_budget_reason.startswith("some prior")


def test_from_dict_backward_compatible_with_pre_2026_08_18_records():
    """A persisted exit-state.json record written before this session has no
    theta_budget_hit/theta_budget_reason keys at all. from_dict must resolve them to the
    exact legacy-inert defaults (False/""), never raise, never guess a non-default value."""
    legacy = em.ExitState.from_entry(
        symbol="SPY260825C00600000", side="C", entry_premium=1.00, qty=5,
        exit_shape=RIBBON_SHAPE, strategy="x").to_dict()
    legacy.pop("theta_budget_hit")
    legacy.pop("theta_budget_reason")
    restored = em.ExitState.from_dict(legacy)
    assert restored.theta_budget_hit is False
    assert restored.theta_budget_reason == ""
