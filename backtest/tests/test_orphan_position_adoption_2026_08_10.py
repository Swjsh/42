"""Guards for the 2026-08-10 night failure-mode audit -- "if we're in a trade and X happens,
can we still get out?"

Two defects found by walking the exit path adversarially rather than by a failing test:

DEFECT 1 -- ORPHANED POSITIONS HAD NO SAFETY NET ON FLEET ARMS.
heartbeat_core has had `_adopt_untracked_positions` since 2026-07-07, but only the CORE
accounts (safe-2, bold-2) run through it. fleet_live -- safe-3, risky-1, risky-3 -- had none.
`load_states` fails open to {} on unreadable JSON and `manage_tick` returns [] on empty state,
so ANY loss of exit-state (corrupt write, disk error, an errant prune, a future bug) left a
live position with ZERO exit management until the 15:55 flatten, silently. That is the exact
shape of the 2026-08-10 risky-1 -$440. The pending-fill guard closed the CAUSE seen that day;
`adopt_untracked_positions` closes the CLASS, independently.

DEFECT 2 -- RE-ANCHOR COULD SILENTLY LOWER AN ARMED LADDER FLOOR.
`reanchor_entry` refuses when `tp1_filled or profit_lock_armed`. The pre-TP1 ladder shipped
today deliberately sets NEITHER (it is independent of the post-TP1 chandelier by design), so a
ladder-armed position passed both checks and the entry recompute would overwrite a floor of
entry*1.30 with entry*(1+premium_stop_pct) -- a silent ratchet violation of the one invariant
the whole give-back fix rests on. Not reachable today (both call sites re-anchor in the same
tick as registration), but that is a timing argument; the guard is now structural.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
if str(FLEET) not in sys.path:
    sys.path.insert(0, str(FLEET))

import exit_actuator as ea  # noqa: E402
import exit_manager as em  # noqa: E402
import strategies as st  # noqa: E402

ARM = "pytest-orphan-adoption"
SYM = "SPY260810C00773000"


class PositionBroker:
    """Broker showing ONE open SPY option position the arm is not tracking."""

    def __init__(self, qty=3, entry=1.16, symbol=SYM):
        self._p = [{"symbol": symbol, "qty": str(qty), "avg_entry_price": str(entry)}]

    def open_spy_option_positions(self, creds):
        return list(self._p)


@pytest.fixture()
def arm(tmp_path, monkeypatch):
    monkeypatch.setattr(ea, "FLEET_DIR", tmp_path)
    monkeypatch.setattr(ea, "STATUS_MD", tmp_path / "STATUS.md")
    (tmp_path / ARM).mkdir(parents=True, exist_ok=True)
    return tmp_path


def _shape():
    return st.by_name("ribbon_ride").exit.to_dict()


# ---------------------------------------------------------------- DEFECT 1


def test_orphan_position_is_adopted_not_left_naked(arm):
    """THE INCIDENT SHAPE: broker shows a position, exit-state is empty -> must be adopted."""
    assert ea.load_states(ARM) == {}
    out = ea.adopt_untracked_positions(ARM, {}, broker=PositionBroker(),
                                       registry_shape=_shape())
    assert any(r.get("action") == "ADOPTED_UNTRACKED" for r in out), out
    states = ea.load_states(ARM)
    assert SYM in states, "position still untracked after adoption"
    assert states[SYM].total_qty == 3
    assert states[SYM].entry_premium == pytest.approx(1.16)
    assert states[SYM].runner_stop_premium is not None, "adopted with no stop = still naked"


def test_adoption_is_idempotent_and_preserves_evolving_state(arm):
    """A tracked symbol must NOT be re-registered -- that would reset hwm/tp1/floor."""
    ea.register_entry(ARM, symbol=SYM, side="C", entry_premium=1.16, qty=3,
                      exit_shape=_shape(), strategy="RIBBON")
    states = ea.load_states(ARM)
    states[SYM] = em.replace(states[SYM], hwm_premium=2.30, runner_stop_premium=1.856)
    ea.save_states(ARM, states)
    out = ea.adopt_untracked_positions(ARM, {}, broker=PositionBroker(), registry_shape=_shape())
    assert not [r for r in out if r.get("action") == "ADOPTED_UNTRACKED"]
    after = ea.load_states(ARM)[SYM]
    assert after.hwm_premium == pytest.approx(2.30)
    assert after.runner_stop_premium == pytest.approx(1.856)


def test_engine_placed_orphan_gets_the_full_ladder_back(arm):
    """Provenance: the arm's own ledger shows it placed this symbol today -> restore the
    FULL registry shape (ladder included), anchored to the BROKER's avg entry."""
    today = ea._now_et().strftime("%Y-%m-%d")
    row = {"ts_et": f"{today}T09:35:05-04:00",
           "placement": {"placed": True, "symbol": SYM}}
    (arm / ARM / "decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    out = ea.adopt_untracked_positions(ARM, {}, broker=PositionBroker(), registry_shape=_shape())
    assert out[0]["adopted_as"] == "engine_placed_full_shape", out
    adopted = ea.load_states(ARM)[SYM]
    assert adopted.pre_tp1_ladder == [[0.50, 0.30], [0.75, 0.60]]
    assert adopted.entry_premium == pytest.approx(1.16)   # broker truth, not a guess
    # and the restored ladder must actually ARM -- a shape that is present but inert is
    # the C14 dead-knob failure this repo keeps repeating
    dec = em.plan_exit_actions(adopted, best_premium=1.16 * 1.60, worst_premium=1.70,
                               open_qty=3, now_et=em._time(10, 30))
    assert dec.state.runner_stop_premium == pytest.approx(1.16 * 1.30, abs=1e-4)


def test_unknown_provenance_downgrades_to_cap_only(arm):
    """No ledger evidence -> CAP-ONLY. The engine never imposes a strategy exit on a trade
    it cannot prove it opened (heartbeat_core's D2 rule, mirrored)."""
    out = ea.adopt_untracked_positions(ARM, {}, broker=PositionBroker(), registry_shape=_shape())
    assert out[0]["adopted_as"] == "cap_only"
    adopted = ea.load_states(ARM)[SYM]
    assert not adopted.pre_tp1_ladder
    assert adopted.catastrophe_stop_pct == pytest.approx(-0.50)


def test_unreadable_provenance_fails_closed_to_cap_only(arm):
    """Corrupt decisions.jsonl must DOWNGRADE adoption, never upgrade it."""
    (arm / ARM / "decisions.jsonl").write_text("{not json\n", encoding="utf-8")
    out = ea.adopt_untracked_positions(ARM, {}, broker=PositionBroker(), registry_shape=_shape())
    assert out[0]["adopted_as"] == "cap_only"


def test_adoption_never_raises_on_broker_error(arm):
    """Fail-open: adoption must never abort the caller's exit pass."""
    class Boom:
        def open_spy_option_positions(self, creds):
            raise RuntimeError("broker down")
    out = ea.adopt_untracked_positions(ARM, {}, broker=Boom(), registry_shape=_shape())
    assert out and out[0]["action"] == "ADOPT_ERROR"


def test_adopted_position_is_actually_managed_on_the_same_tick(arm):
    """END TO END: adopt, then plan an exit on the adopted state and get a real SELL when the
    catastrophe cap is breached. Proves adoption restores MANAGEMENT, not just a ledger row."""
    ea.adopt_untracked_positions(ARM, {}, broker=PositionBroker(), registry_shape=_shape())
    s = ea.load_states(ARM)[SYM]
    dec = em.plan_exit_actions(s, best_premium=1.16, worst_premium=0.40,
                               open_qty=3, now_et=em._time(11, 0))
    assert any(a.kind in ("SELL_ALL", "SELL") for a in dec.actions), dec.actions


def test_adoption_writes_a_durable_receipt(arm):
    ea.adopt_untracked_positions(ARM, {}, broker=PositionBroker(), registry_shape=_shape())
    log = arm / ARM / "prune-log.jsonl"
    assert log.exists()
    assert "ADOPTED_UNTRACKED" in log.read_text(encoding="utf-8")


# ---------------------------------------------------------------- DEFECT 2


def test_reanchor_refuses_once_the_ladder_has_armed(arm):
    """A ladder-armed floor must survive re-anchoring. Before this guard, reanchor_entry
    recomputed runner_stop from the new entry and silently DROPPED the floor."""
    ea.register_entry(ARM, symbol=SYM, side="C", entry_premium=1.16, qty=3,
                      exit_shape=_shape(), strategy="RIBBON")
    states = ea.load_states(ARM)
    seeded = states[SYM].runner_stop_premium
    # drive a real ladder arm through the real planner (+98% MFE)
    dec = em.plan_exit_actions(states[SYM], best_premium=2.30, worst_premium=2.20,
                               open_qty=3, now_et=em._time(10, 45))
    states[SYM] = dec.state
    ea.save_states(ARM, states)
    armed = ea.load_states(ARM)[SYM].runner_stop_premium
    assert armed > seeded, "fixture must actually arm the ladder"
    assert ea.load_states(ARM)[SYM].profit_lock_armed is False, (
        "the ladder must NOT set profit_lock_armed -- that is why the old guard was blind")

    assert ea.reanchor_entry(ARM, symbol=SYM, true_entry_premium=1.10) is None
    assert ea.load_states(ARM)[SYM].runner_stop_premium == pytest.approx(armed)


def test_reanchor_still_works_on_a_virgin_position(arm):
    """The new refusal must not break the real fix it guards: an un-ratcheted position
    re-anchors normally (this is the 2026-08-03 entry-anchor fix)."""
    ea.register_entry(ARM, symbol=SYM, side="C", entry_premium=0.42, qty=3,
                      exit_shape=_shape(), strategy="RIBBON")
    new = ea.reanchor_entry(ARM, symbol=SYM, true_entry_premium=0.37)
    assert new is not None
    assert new.entry_premium == pytest.approx(0.37)
    assert new.runner_stop_premium == pytest.approx(0.37 * (1 + new.premium_stop_pct), abs=1e-4)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
