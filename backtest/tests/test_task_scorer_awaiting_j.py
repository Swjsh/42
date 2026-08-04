"""Guard: task_scorer must NOT surface a J-gated (Discord/wrist approval-bus)
proposal as the #1 ready task while it is genuinely awaiting J's reply.

WHY THIS GUARD EXISTS (conductor 2026-08-04)
---------------------------------------------
``task_scorer --top`` ranked ``TWIN-DOCTRINE-FIRST-DEPLOY`` #1 (score 6.5) on
2026-08-03, but that item is a DOCTRINE proposal already sitting on Discord/
wrist awaiting J's reply since 2026-07-23 (``gp-2026-07-23-twin-doctrine-001``,
``status:pending`` with no ``eval_bar_cleared`` in ``conductor-proposals.jsonl``
-- CLAUDE.md changes are J-first, full stop, per rail-4). ``status:pending`` +
satisfied ``depends:`` reads as "ready to work" to the scorer, but there is
genuinely nothing left for a conductor fire to DO except re-ping J, which
would be spam on an 11-day-old ask, not progress. This is the SAME class of
bug as ``TASK-SCORER-STATUS-VOCAB-GAP`` / ``TASK-SCORER-MULTILINE-STATUS-READ``
(queue.md) -- a status string the ranker doesn't recognize silently reads as
"ready" -- but the missing signal here lives in a SIBLING ledger
(``conductor-proposals.jsonl``), not queue.md itself.

The fix: an item whose block text names a ``gp-...`` proposal id that is
``status:pending`` with no ``eval_bar_cleared`` is J-GATED -- suppressed from
``ready`` while fresh (<=14d old), and resurfaces past 14d as a "re-ping J"
task (never as an "implement this" task -- the reason string says so).

These tests pin:
  * a fresh J-gated proposal -> not ready, reason names the proposal + why
  * a >14d-stale J-gated proposal -> resurfaces ready, reason says RE-PING
  * an already-resolved proposal (status != pending) -> unaffected, ready
  * a proposal with eval_bar_cleared=true (auto-ratifiable edge, not a human-
    reply-only gate) -> unaffected, ready
  * missing/garbled proposals ledger -> fail-open, does not hide the item
  * an item naming NO proposal id -> unaffected
  * a non-vacuous BITE: neutering the gate flips the fresh case back to ready
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


tsk = _load("task_scorer", "setup/scripts/task_scorer.py")


_QUEUE = """# header

## Active backlog

- [ ] TWIN-DOCTRINE-FIRST-DEPLOY (MED, doctrine, propose-only) :: DRAFTED, filed conductor-proposals.jsonl id gp-2026-07-23-twin-doctrine-001 (no eval_bar_cleared). :: depends:none :: status:pending
- [ ] SOME-ENGINE-ITEM (HIGH, engine-edge) :: a real engine fix :: depends:none :: status:pending

## Completed
"""


def _by_id(tasks, marker):
    return next((t for t in tasks if marker in t.id), None)


def _write_proposals(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "conductor-proposals.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat().replace(
        "+00:00", "Z"
    )


# ---------------------------------------------------------------------------
# fresh J-gated proposal -> not ready
# ---------------------------------------------------------------------------
def test_fresh_j_gated_proposal_not_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tsk,
        "PROPOSALS_STATE",
        _write_proposals(
            tmp_path,
            [
                {
                    "proposal_id": "gp-2026-07-23-twin-doctrine-001",
                    "created_at": _iso(11),
                    "status": "pending",
                }
            ],
        ),
    )
    t = _by_id(tsk.parse_queue(_QUEUE), "TWIN-DOCTRINE-FIRST-DEPLOY")
    assert t is not None
    assert t.ready is False
    assert "awaiting-j" in t.reason
    assert "gp-2026-07-23-twin-doctrine-001" in t.reason


def test_fresh_j_gated_proposal_dropped_from_default_ranking(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tsk,
        "PROPOSALS_STATE",
        _write_proposals(
            tmp_path,
            [
                {
                    "proposal_id": "gp-2026-07-23-twin-doctrine-001",
                    "created_at": _iso(11),
                    "status": "pending",
                }
            ],
        ),
    )
    ranked = tsk.rank(_QUEUE)
    assert not any("TWIN-DOCTRINE" in t.id for t in ranked)
    allt = tsk.rank(_QUEUE, include_blocked=True)
    assert any("TWIN-DOCTRINE" in t.id for t in allt)


# ---------------------------------------------------------------------------
# stale (>14d) J-gated proposal -> resurfaces as a RE-PING task, not "do this"
# ---------------------------------------------------------------------------
def test_stale_j_gated_proposal_resurfaces_as_reping(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tsk,
        "PROPOSALS_STATE",
        _write_proposals(
            tmp_path,
            [
                {
                    "proposal_id": "gp-2026-07-23-twin-doctrine-001",
                    "created_at": _iso(20),
                    "status": "pending",
                }
            ],
        ),
    )
    t = _by_id(tsk.parse_queue(_QUEUE), "TWIN-DOCTRINE-FIRST-DEPLOY")
    assert t is not None
    assert t.ready is True
    assert "STALE J-PING" in t.reason
    assert "RE-PING J" in t.reason


# ---------------------------------------------------------------------------
# resolved proposal (status != pending) -> unaffected
# ---------------------------------------------------------------------------
def test_resolved_proposal_unaffected(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tsk,
        "PROPOSALS_STATE",
        _write_proposals(
            tmp_path,
            [
                {
                    "proposal_id": "gp-2026-07-23-twin-doctrine-001",
                    "created_at": _iso(11),
                    "status": "approved",
                }
            ],
        ),
    )
    t = _by_id(tsk.parse_queue(_QUEUE), "TWIN-DOCTRINE-FIRST-DEPLOY")
    assert t.ready is True
    assert "awaiting-j" not in t.reason


# ---------------------------------------------------------------------------
# eval_bar_cleared=true (auto-ratifiable edge) -> unaffected
# ---------------------------------------------------------------------------
def test_eval_bar_cleared_proposal_unaffected(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tsk,
        "PROPOSALS_STATE",
        _write_proposals(
            tmp_path,
            [
                {
                    "proposal_id": "gp-2026-07-23-twin-doctrine-001",
                    "created_at": _iso(11),
                    "status": "pending",
                    "eval_bar_cleared": True,
                }
            ],
        ),
    )
    t = _by_id(tsk.parse_queue(_QUEUE), "TWIN-DOCTRINE-FIRST-DEPLOY")
    assert t.ready is True
    assert "awaiting-j" not in t.reason


# ---------------------------------------------------------------------------
# missing/garbled proposals ledger -> fail-open, never hides the item
# ---------------------------------------------------------------------------
def test_missing_proposals_ledger_does_not_hide_item(tmp_path, monkeypatch):
    monkeypatch.setattr(tsk, "PROPOSALS_STATE", tmp_path / "nope.jsonl")
    t = _by_id(tsk.parse_queue(_QUEUE), "TWIN-DOCTRINE-FIRST-DEPLOY")
    assert t.ready is True


def test_garbled_proposals_ledger_does_not_hide_item(tmp_path, monkeypatch):
    p = tmp_path / "conductor-proposals.jsonl"
    p.write_text("not json {{{\n", encoding="utf-8")
    monkeypatch.setattr(tsk, "PROPOSALS_STATE", p)
    t = _by_id(tsk.parse_queue(_QUEUE), "TWIN-DOCTRINE-FIRST-DEPLOY")
    assert t.ready is True


# ---------------------------------------------------------------------------
# item naming no proposal id -> unaffected
# ---------------------------------------------------------------------------
def test_item_with_no_proposal_id_unaffected(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tsk,
        "PROPOSALS_STATE",
        _write_proposals(
            tmp_path,
            [
                {
                    "proposal_id": "gp-2026-07-23-twin-doctrine-001",
                    "created_at": _iso(11),
                    "status": "pending",
                }
            ],
        ),
    )
    other = _by_id(tsk.parse_queue(_QUEUE), "SOME-ENGINE-ITEM")
    assert other.ready is True
    assert "awaiting-j" not in other.reason


# ---------------------------------------------------------------------------
# BITE: neuter the gate -> the fresh case flips back to ready
# ---------------------------------------------------------------------------
def test_bite_neutering_gate_unblocks_fresh_proposal(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tsk,
        "PROPOSALS_STATE",
        _write_proposals(
            tmp_path,
            [
                {
                    "proposal_id": "gp-2026-07-23-twin-doctrine-001",
                    "created_at": _iso(11),
                    "status": "pending",
                }
            ],
        ),
    )
    assert _by_id(tsk.parse_queue(_QUEUE), "TWIN-DOCTRINE-FIRST-DEPLOY").ready is False
    monkeypatch.setattr(tsk, "_j_gated_proposal", lambda *a, **k: None)
    assert _by_id(tsk.parse_queue(_QUEUE), "TWIN-DOCTRINE-FIRST-DEPLOY").ready is True


# ---------------------------------------------------------------------------
# LIVE parity: the real gp-2026-07-23-twin-doctrine-001 proposal on-disk is
# still pending/no-eval_bar_cleared -> real queue item reads not-ready today.
# ---------------------------------------------------------------------------
def test_live_twin_doctrine_proposal_still_gated_or_resolved():
    live_queue = _ROOT / "automation" / "overnight" / "queue.md"
    if not live_queue.exists():
        import pytest

        pytest.skip("live queue.md absent")
    text = live_queue.read_text(encoding="utf-8")
    tasks = tsk.parse_queue(text)
    t = _by_id(tasks, "TWIN-DOCTRINE-FIRST-DEPLOY")
    if t is None:
        return  # item closed/removed since -- nothing to assert
    proposals = tsk._load_proposals()
    row = proposals.get("gp-2026-07-23-twin-doctrine-001")
    if row is None or row.get("status") != "pending" or row.get("eval_bar_cleared"):
        return  # proposal resolved -- item's readiness is no longer gated by this rule
    age = tsk._proposal_age_days(row)
    if age is not None and age <= tsk.PROPOSAL_STALE_DAYS:
        assert t.ready is False
        assert "awaiting-j" in t.reason
