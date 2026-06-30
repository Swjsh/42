"""Guard: CONFIRM-BEFORE-CAPITAL recency gate at the SECOND chokepoint (the actuator).

DEFENSE IN DEPTH for the 2026-06-29 incident fix. The FIRST chokepoint
(contender_oos_check.assess_recency_gate, OP-11 gate 5) blocks a contender from
FLIPPING eval_bar_cleared=true while recency is RED. But the actuator's
auto_approve_pending() op11_evalbar path re-verifies the scorecard (wf/oos/anchor)
and historically did NOT re-check recency -- so a proposal whose eval_bar_cleared
was set by a different path, a pre-gate emit, or a manual flip could auto-apply a
recency-RED change to LIVE params at the apply chokepoint. _recency_gate_clears now
re-checks recency there: NO autonomous params apply while recency is RED.

Two invariants pinned here:
  1. _recency_gate_clears fails CLOSED on any unreadable/missing/garbled input and
     passes ONLY on an explicit headline.edges_confirmed_on_recent == True.
  2. PARITY: _recency_gate_clears returns the SAME verdict as the first-chokepoint
     assess_recency_gate across a fixture matrix -- so the two can never drift (C14).
  3. BITE: a fully-clearing op11 proposal is auto-approved iff recency is confirmed.

Pure ($0) -- never loads market data or runs a backtest.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "autonomy_actuator", REPO / "setup" / "scripts" / "autonomy_actuator.py"
)
act = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(act)


def _write(tmp_path: Path, payload) -> Path:
    p = tmp_path / "recency-confirmation.json"
    if isinstance(payload, (dict, list)):
        p.write_text(json.dumps(payload), encoding="utf-8")
    else:
        p.write_text(str(payload), encoding="utf-8")
    return p


# ----------------------------------------------------------------------------
# 1. fail-closed + only-explicit-True
# ----------------------------------------------------------------------------
def test_missing_file_fails_closed(tmp_path):
    assert act._recency_gate_clears(tmp_path / "nope.json") is False


def test_garbled_json_fails_closed(tmp_path):
    assert act._recency_gate_clears(_write(tmp_path, "{not json")) is False


def test_non_dict_fails_closed(tmp_path):
    assert act._recency_gate_clears(_write(tmp_path, [1, 2, 3])) is False


def test_malformed_headline_fails_closed(tmp_path):
    assert act._recency_gate_clears(_write(tmp_path, {"headline": "RED"})) is False


def test_missing_headline_fails_closed(tmp_path):
    assert act._recency_gate_clears(_write(tmp_path, {"foo": "bar"})) is False


def test_explicit_false_is_blocked(tmp_path):
    p = _write(tmp_path, {"headline": {"edges_confirmed_on_recent": False, "any_red": True}})
    assert act._recency_gate_clears(p) is False


def test_none_is_blocked(tmp_path):
    p = _write(tmp_path, {"headline": {"edges_confirmed_on_recent": None}})
    assert act._recency_gate_clears(p) is False


def test_missing_key_is_blocked(tmp_path):
    assert act._recency_gate_clears(_write(tmp_path, {"headline": {}})) is False


def test_truthy_one_does_not_pass(tmp_path):
    # `is True` -- a truthy 1 must NOT clear (mirrors assess_recency_gate exactly).
    assert act._recency_gate_clears(_write(tmp_path, {"headline": {"edges_confirmed_on_recent": 1}})) is False


def test_explicit_true_passes(tmp_path):
    p = _write(tmp_path, {"headline": {"edges_confirmed_on_recent": True}})
    assert act._recency_gate_clears(p) is True


# ----------------------------------------------------------------------------
# 2. PARITY with the first-chokepoint assess_recency_gate (no drift -- C14)
# ----------------------------------------------------------------------------
_PARITY_FIXTURES = [
    {"headline": {"edges_confirmed_on_recent": True}},
    {"headline": {"edges_confirmed_on_recent": False, "any_red": True}},
    {"headline": {"edges_confirmed_on_recent": None}},
    {"headline": {}},
    {"headline": "RED"},
    {"foo": "bar"},
    [1, 2, 3],
    "{not json",
]


def _load_first_chokepoint():
    for _p in (str(REPO / "backtest" / "autoresearch"), str(REPO / "backtest"), str(REPO)):
        if _p not in sys.path:
            sys.path.insert(0, _p)
    try:
        from autoresearch.contender_oos_check import assess_recency_gate  # noqa
        return assess_recency_gate
    except Exception as exc:  # pragma: no cover - env-dependent
        pytest.skip(f"contender_oos_check import unavailable: {exc}")


@pytest.mark.parametrize("payload", _PARITY_FIXTURES)
def test_parity_with_first_chokepoint(tmp_path, payload):
    assess_recency_gate = _load_first_chokepoint()
    p = _write(tmp_path, payload)
    actuator_verdict = act._recency_gate_clears(p)
    first_verdict, _detail = assess_recency_gate(p)
    assert actuator_verdict is first_verdict, (
        f"actuator={actuator_verdict} vs first-chokepoint={first_verdict} for {payload!r}"
    )


# ----------------------------------------------------------------------------
# 3. BITE: a clearing op11 proposal auto-approves IFF recency is confirmed
# ----------------------------------------------------------------------------
def _setup_clearing_proposal(tmp_path, monkeypatch):
    prop = tmp_path / "proposals.jsonl"
    monkeypatch.setattr(act, "PROPOSALS", prop)
    monkeypatch.setattr(act, "CHANGELOG", tmp_path / "changelog.jsonl")
    monkeypatch.setattr(act, "REPO", tmp_path)
    sc = tmp_path / "analysis" / "recommendations"
    sc.mkdir(parents=True)
    (sc / "pass.json").write_text(
        json.dumps({"wf": 1.8, "oos_positive": True, "anchor_no_regression": True}),
        encoding="utf-8",
    )
    prop.write_text(
        json.dumps({
            "proposal_id": "edge-cleared", "status": "pending", "kind": "params",
            "eval_bar_cleared": True, "scorecard": "analysis/recommendations/pass.json",
            "apply_ops": [{"file": "automation/state/params.json", "find": "a", "replace": "b"}],
        }) + "\n",
        encoding="utf-8",
    )
    return prop


def test_bite_recency_red_blocks_otherwise_clearing_op11(tmp_path, monkeypatch):
    _setup_clearing_proposal(tmp_path, monkeypatch)
    rec = _write(tmp_path, {"headline": {"edges_confirmed_on_recent": False, "any_red": True}})
    monkeypatch.setattr(act, "RECENCY", rec)
    n = act.auto_approve_pending()
    status = {r["proposal_id"]: r["status"] for r in act._read_proposals()}
    assert status["edge-cleared"] == "pending", "recency RED must block the op11 auto-apply"
    assert n == 0


def test_bite_recency_confirmed_lets_clearing_op11_through(tmp_path, monkeypatch):
    _setup_clearing_proposal(tmp_path, monkeypatch)
    rec = _write(tmp_path, {"headline": {"edges_confirmed_on_recent": True}})
    monkeypatch.setattr(act, "RECENCY", rec)
    n = act.auto_approve_pending()
    status = {r["proposal_id"]: r["status"] for r in act._read_proposals()}
    assert status["edge-cleared"] == "approved", "recency confirmed + scorecard clears -> approve"
    assert n == 1


def test_bite_recency_missing_file_fails_closed_blocks(tmp_path, monkeypatch):
    _setup_clearing_proposal(tmp_path, monkeypatch)
    monkeypatch.setattr(act, "RECENCY", tmp_path / "absent-recency.json")
    n = act.auto_approve_pending()
    status = {r["proposal_id"]: r["status"] for r in act._read_proposals()}
    assert status["edge-cleared"] == "pending", "unreadable recency must fail closed (block)"
    assert n == 0
