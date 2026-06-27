"""Guard for the G8 companion->ledger consent bridge (autonomy_actuator.sync_companion_approvals).

Pins the contract so the dead loop (J taps Approve on localhost:4317 -> logged to
companion-decisions.jsonl -> NOTHING flips conductor-proposals.jsonl -> the actuator
never applies J's consent) can never silently return:

  - a companion `approve` for a REAL pending proposal_id flips it -> "approved"
    (so the existing apply path picks it up), tagged approved_via="companion";
  - a companion `reject` flips a pending proposal -> "shelved";
  - a synthetic companion card (act-*/oblig-*) matches no proposal -> NO-OP;
  - a NON-pending proposal (applied/approved/shelved/reverted) is NEVER re-touched
    by a stale companion row -> idempotent, J's later action always wins;
  - missing companion-decisions.jsonl -> 0, never raises (fail-open);
  - the bridge RECORDS consent only -- it never calls the apply/gate/git path.

$0, pure-stdlib, no network/git. Run: python -m pytest backtest/tests/test_companion_approval_bridge.py -q
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_MOD_PATH = _REPO / "setup" / "scripts" / "autonomy_actuator.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("autonomy_actuator_under_test", _MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    """Load the actuator with all state paths redirected into a temp dir, so the
    bridge never touches the real ledger/changelog."""
    m = _load_module()
    monkeypatch.setattr(m, "STATE", tmp_path, raising=True)
    monkeypatch.setattr(m, "PROPOSALS", tmp_path / "conductor-proposals.jsonl", raising=True)
    monkeypatch.setattr(m, "COMPANION_DECISIONS", tmp_path / "companion-decisions.jsonl", raising=True)
    monkeypatch.setattr(m, "CHANGELOG", tmp_path / "autonomy-changelog.jsonl", raising=True)
    return m


def _write_proposals(mod, rows):
    mod.PROPOSALS.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _write_decisions(mod, rows):
    mod.COMPANION_DECISIONS.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _proposal(pid, status="pending", **extra):
    return {"proposal_id": pid, "title": f"prop {pid}", "status": status, **extra}


def _statuses(mod):
    return {r["proposal_id"]: r for r in mod._read_proposals()}


def test_approve_flips_pending_to_approved(mod):
    _write_proposals(mod, [_proposal("gp-1"), _proposal("gp-2")])
    _write_decisions(mod, [{"ts": "2026-06-27T00:00:00Z", "id": "gp-1", "decision": "approve"}])
    changed = mod.sync_companion_approvals()
    assert changed == 1
    rows = _statuses(mod)
    assert rows["gp-1"]["status"] == "approved"
    assert rows["gp-1"]["approved_via"] == "companion"
    assert "approved_at" in rows["gp-1"]
    assert rows["gp-2"]["status"] == "pending"  # untouched


def test_reject_flips_pending_to_shelved(mod):
    _write_proposals(mod, [_proposal("gp-1")])
    _write_decisions(mod, [{"ts": "2026-06-27T00:00:00Z", "id": "gp-1", "decision": "reject"}])
    assert mod.sync_companion_approvals() == 1
    rows = _statuses(mod)
    assert rows["gp-1"]["status"] == "shelved"
    assert rows["gp-1"]["shelved_via"] == "companion"


def test_synthetic_card_id_is_ignored(mod):
    # The live companion-decisions.jsonl is full of these (act-kitchen-failed etc.).
    _write_proposals(mod, [_proposal("gp-1")])
    _write_decisions(mod, [
        {"ts": "2026-06-21T15:01:11Z", "id": "act-kitchen-failed", "decision": "approve"},
        {"ts": "2026-06-21T15:42:19Z", "id": "oblig-engine-red", "decision": "approve"},
    ])
    assert mod.sync_companion_approvals() == 0
    assert _statuses(mod)["gp-1"]["status"] == "pending"


@pytest.mark.parametrize("status", ["approved", "applied", "shelved", "reverted", "needs_structured_apply"])
def test_non_pending_proposal_is_never_retouched(mod, status):
    # A stale companion approve row must NOT re-open an already-resolved proposal.
    _write_proposals(mod, [_proposal("gp-1", status=status)])
    _write_decisions(mod, [{"ts": "2026-06-27T00:00:00Z", "id": "gp-1", "decision": "approve"}])
    assert mod.sync_companion_approvals() == 0
    assert _statuses(mod)["gp-1"]["status"] == status


def test_idempotent_second_run_is_noop(mod):
    _write_proposals(mod, [_proposal("gp-1")])
    _write_decisions(mod, [{"ts": "2026-06-27T00:00:00Z", "id": "gp-1", "decision": "approve"}])
    assert mod.sync_companion_approvals() == 1
    # Re-running with the same decision row does nothing (now "approved", not "pending").
    assert mod.sync_companion_approvals() == 0
    assert _statuses(mod)["gp-1"]["status"] == "approved"


def test_missing_decisions_file_is_fail_open(mod):
    _write_proposals(mod, [_proposal("gp-1")])
    # no companion-decisions.jsonl written
    assert not mod.COMPANION_DECISIONS.exists()
    assert mod.sync_companion_approvals() == 0
    assert _statuses(mod)["gp-1"]["status"] == "pending"


def test_torn_decision_line_does_not_crash(mod):
    _write_proposals(mod, [_proposal("gp-1")])
    mod.COMPANION_DECISIONS.write_text(
        '{"ts":"t","id":"gp-1","decision":"approve"}\n{ this is not json\n',
        encoding="utf-8",
    )
    assert mod.sync_companion_approvals() == 1
    assert _statuses(mod)["gp-1"]["status"] == "approved"


def test_apply_approved_dry_run_does_not_sync(mod, monkeypatch):
    # dry-run is a preview; it must NOT mutate the ledger via the bridge.
    _write_proposals(mod, [_proposal("gp-1")])
    _write_decisions(mod, [{"ts": "2026-06-27T00:00:00Z", "id": "gp-1", "decision": "approve"}])
    monkeypatch.setattr(mod, "_market_is_open", lambda: False, raising=True)
    mod.apply_approved(dry_run=True)
    assert _statuses(mod)["gp-1"]["status"] == "pending"  # unchanged by preview


def test_bite_guard_would_fail_without_pending_check(mod):
    """Non-vacuous: prove the 'pending-only' guard is what protects an applied row.
    If the bridge dropped the status check it WOULD re-approve an applied proposal --
    this test documents that the real code does NOT."""
    _write_proposals(mod, [_proposal("gp-1", status="applied", commit_sha="abc123")])
    _write_decisions(mod, [{"ts": "2026-06-27T00:00:00Z", "id": "gp-1", "decision": "approve"}])
    assert mod.sync_companion_approvals() == 0
    rows = _statuses(mod)
    assert rows["gp-1"]["status"] == "applied"
    assert rows["gp-1"].get("commit_sha") == "abc123"  # provenance preserved
