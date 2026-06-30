"""Guard: task_scorer must NOT surface a recency-blocked promote as a ready task.

WHY THIS GUARD EXISTS (conductor 2026-06-30)
--------------------------------------------
For ~9 consecutive after-hours fires ``task_scorer`` ranked
``PROMOTE-KEEPER-OOS-VALIDATION`` as the #1 READY item, because it scored the
queue line purely on priority + keywords + ``status:pending`` with ZERO
awareness that the promote's top contender was the dead premium axis (WR ~12%)
AND recency-RED — i.e. unshippable (the recency gate in
``contender_oos_check``/``autonomy_actuator`` blocks it at BOTH apply
chokepoints). So every fire was pointed at the same wall and had to manually
re-verify "dead-axis + recency-RED → dismiss" — the recurring waste this fix
closes (OP-33d: the same wall every fire ⇒ fix the thing that keeps pointing
you AT the wall, don't dismiss it a 9th time).

The fix: ``task_scorer._recency_explicitly_red`` down-ranks a recency-gated
item to ``ready=False`` ONLY when the confirm-before-capital headline is
readable and EXPLICITLY RED. On missing / garbled / confirmed it does NOT
suppress (conservative ATTENTION-routing — never hide work on uncertainty).

These tests pin:
  * the explicit-RED → not-ready behaviour (+ the reason string),
  * confirmed → ready (the promote becomes actionable again when recency
    flips green — the gate is not a permanent mute),
  * fail-OPEN on missing/garbled (never hides the item on uncertainty),
  * non-promote items are unaffected by recency,
  * a non-vacuous BITE (neutering the predicate flips the RED case back to
    ready ⇒ proves the predicate is what bites),
  * field-contract PARITY with ``autonomy_actuator._recency_gate_clears`` so
    the two readers of ``headline.edges_confirmed_on_recent`` cannot drift (C14).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


tsk = _load("task_scorer", "setup/scripts/task_scorer.py")
act = _load("autonomy_actuator", "setup/scripts/autonomy_actuator.py")


_QUEUE = """# header

## Active backlog

- [ ] PROMOTE-KEEPER-OOS-VALIDATION (HIGH, research->deploy bridge) :: the bridge :: depends:none :: status:pending
- [ ] SOME-ENGINE-ITEM (HIGH, engine-edge) :: a real engine fix :: depends:none :: status:pending

## Completed
"""


def _write_recency(tmp_path: Path, confirmed) -> Path:
    p = tmp_path / "recency-confirmation.json"
    p.write_text(
        json.dumps({"headline": {"edges_confirmed_on_recent": confirmed}}),
        encoding="utf-8",
    )
    return p


def _by_id(tasks, marker):
    return next((t for t in tasks if marker in t.id), None)


# ---------------------------------------------------------------------------
# explicit RED → promote not-ready (+ reason)
# ---------------------------------------------------------------------------
def test_explicit_red_makes_promote_not_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(tsk, "RECENCY_STATE", _write_recency(tmp_path, False))
    tasks = tsk.parse_queue(_QUEUE)
    pk = _by_id(tasks, "PROMOTE-KEEPER")
    assert pk is not None
    assert pk.ready is False
    assert "recency RED" in pk.reason


def test_explicit_red_drops_promote_from_default_ranking(tmp_path, monkeypatch):
    monkeypatch.setattr(tsk, "RECENCY_STATE", _write_recency(tmp_path, False))
    ranked = tsk.rank(_QUEUE)  # ready-only
    assert not any("PROMOTE-KEEPER" in t.id for t in ranked)
    # ...but it is still visible under include_blocked with the reason.
    allt = tsk.rank(_QUEUE, include_blocked=True)
    assert any("PROMOTE-KEEPER" in t.id for t in allt)


# ---------------------------------------------------------------------------
# confirmed / missing / garbled → NOT suppressed (fail-open toward surfacing)
# ---------------------------------------------------------------------------
def test_confirmed_keeps_promote_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(tsk, "RECENCY_STATE", _write_recency(tmp_path, True))
    pk = _by_id(tsk.parse_queue(_QUEUE), "PROMOTE-KEEPER")
    assert pk.ready is True
    assert "recency RED" not in pk.reason


def test_missing_recency_does_not_hide_promote(tmp_path, monkeypatch):
    monkeypatch.setattr(tsk, "RECENCY_STATE", tmp_path / "nope.json")
    pk = _by_id(tsk.parse_queue(_QUEUE), "PROMOTE-KEEPER")
    assert pk.ready is True


def test_garbled_recency_does_not_hide_promote(tmp_path, monkeypatch):
    p = tmp_path / "recency-confirmation.json"
    p.write_text("not json {{{", encoding="utf-8")
    monkeypatch.setattr(tsk, "RECENCY_STATE", p)
    pk = _by_id(tsk.parse_queue(_QUEUE), "PROMOTE-KEEPER")
    assert pk.ready is True


def test_missing_headline_does_not_hide_promote(tmp_path, monkeypatch):
    p = tmp_path / "recency-confirmation.json"
    p.write_text(json.dumps({"other": 1}), encoding="utf-8")
    monkeypatch.setattr(tsk, "RECENCY_STATE", p)
    pk = _by_id(tsk.parse_queue(_QUEUE), "PROMOTE-KEEPER")
    assert pk.ready is True


# ---------------------------------------------------------------------------
# non-promote items are unaffected by recency RED
# ---------------------------------------------------------------------------
def test_non_promote_item_unaffected_by_red(tmp_path, monkeypatch):
    monkeypatch.setattr(tsk, "RECENCY_STATE", _write_recency(tmp_path, False))
    other = _by_id(tsk.parse_queue(_QUEUE), "SOME-ENGINE-ITEM")
    assert other is not None
    assert other.ready is True
    assert "recency RED" not in other.reason


# ---------------------------------------------------------------------------
# direct predicate unit tests
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "confirmed,expected",
    [(False, True), (True, False), (None, False), (1, False), ("False", False)],
)
def test_recency_explicitly_red_only_on_bool_false(tmp_path, confirmed, expected):
    p = _write_recency(tmp_path, confirmed)
    assert tsk._recency_explicitly_red(p) is expected


def test_recency_explicitly_red_missing_is_false(tmp_path):
    assert tsk._recency_explicitly_red(tmp_path / "nope.json") is False


# ---------------------------------------------------------------------------
# BITE: neuter the predicate ⇒ the RED case flips back to ready
# ---------------------------------------------------------------------------
def test_bite_neutering_predicate_unblocks_red_promote(tmp_path, monkeypatch):
    monkeypatch.setattr(tsk, "RECENCY_STATE", _write_recency(tmp_path, False))
    # Pre: explicit RED suppresses the promote.
    assert _by_id(tsk.parse_queue(_QUEUE), "PROMOTE-KEEPER").ready is False
    # Neuter the predicate to always-False (no longer "explicitly red").
    monkeypatch.setattr(tsk, "_recency_explicitly_red", lambda *a, **k: False)
    assert _by_id(tsk.parse_queue(_QUEUE), "PROMOTE-KEEPER").ready is True


# ---------------------------------------------------------------------------
# PARITY: the two readers of headline.edges_confirmed_on_recent agree (C14)
# ---------------------------------------------------------------------------
def test_field_contract_parity_with_actuator_on_red(tmp_path):
    p = _write_recency(tmp_path, False)
    # explicit RED: scorer says "explicitly red"=True; capital gate does NOT clear.
    assert tsk._recency_explicitly_red(p) is True
    assert act._recency_gate_clears(p) is False


def test_field_contract_parity_with_actuator_on_confirmed(tmp_path):
    p = _write_recency(tmp_path, True)
    # confirmed: scorer says "explicitly red"=False; capital gate clears.
    assert tsk._recency_explicitly_red(p) is False
    assert act._recency_gate_clears(p) is True


def test_field_contract_parity_uses_same_live_field():
    """Both readers key off headline.edges_confirmed_on_recent on the LIVE file
    (skip if absent). Pins that they read the SAME field, not just fixtures."""
    live = _ROOT / "automation" / "state" / "recency-confirmation.json"
    if not live.exists():
        pytest.skip("live recency-confirmation.json absent")
    red = tsk._recency_explicitly_red(live)
    clears = act._recency_gate_clears(live)
    # They cannot both be True (explicitly-red and clears are mutually exclusive).
    assert not (red and clears)
