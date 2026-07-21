"""Guard: ONE shared proposal-id lookup, not three incompatible ones (L207 hardening).

FIX-CD-2026-06-28-002-ID-COLLISION (queue.md ACTUATOR-RESOLVE-DUP-ID-FAIL-LOUD) fixed the
immediate incident (split the colliding ids) and pinned ACTIVE-id uniqueness at guard-test
time (test_proposal_id_uniqueness.py). The DEEPER foot-gun stayed open: `autonomy_actuator.py`
resolved "the row for this proposal_id" THREE incompatible ways in the same module --
  - sync_companion_approvals: `by_id = {r["proposal_id"]: r for r in rows}` (dict
    comprehension -- LAST duplicate wins)
  - revert: `next((r for r in rows if r["proposal_id"] == pid), None)` (generator scan --
    FIRST duplicate wins)
  - _set_status: `for r in rows: if r["proposal_id"] == pid: r.update(...); break`
    (loop-with-break -- also first-wins, but a THIRD distinct mechanism)
A race window or an un-vetted `rows` list could still let a duplicate slip past the
guard-test and resolve DIFFERENTLY depending on which code path ran. This test file pins
that all three call sites now route through ONE helper (`resolve_proposal`) that fails
LOUD (`DuplicateProposalError`) on a genuine active-active collision, instead of silently
picking a row.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "setup" / "scripts"
TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS_DIR))  # so test_proposal_id_uniqueness is importable regardless of pytest rootdir/invocation
import autonomy_actuator as A  # noqa: E402


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = tmp_path / "repo"
    (r / "automation" / "state").mkdir(parents=True)
    _git(r, "init")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    target = r / "CLAUDE.md"
    target.write_text("line A\nMARKER_ONCE\nline C\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-m", "init")
    monkeypatch.setattr(A, "REPO", r)
    monkeypatch.setattr(A, "STATE", r / "automation" / "state")
    monkeypatch.setattr(A, "PROPOSALS", r / "automation" / "state" / "conductor-proposals.jsonl")
    monkeypatch.setattr(A, "CHANGELOG", r / "automation" / "state" / "autonomy-changelog.jsonl")
    monkeypatch.setattr(A, "SNAP_DIR", r / "automation" / "state" / ".autonomy-snapshots")
    monkeypatch.setattr(A, "COMPANION_DECISIONS", r / "automation" / "state" / "companion-decisions.jsonl")
    monkeypatch.setattr(A, "_market_is_open", lambda: False)
    return r


# ---------------------------------------------------------------------------
# Unit tests: resolve_proposal itself
# ---------------------------------------------------------------------------

def test_no_match_returns_none():
    assert A.resolve_proposal("nope", [{"proposal_id": "other", "status": "pending"}]) is None


def test_single_match_any_status():
    rows = [{"proposal_id": "a", "status": "applied"}]
    assert A.resolve_proposal("a", rows) is rows[0]


def test_terminal_plus_one_active_resolves_to_the_active_row():
    """Mirrors test_proposal_id_uniqueness.py::test_terminal_duplicate_is_allowed --
    a harmless re-emission (e.g. promote_keeper) must resolve to the ACTIONABLE row,
    not whichever one happens to be first in file order."""
    rows = [
        {"proposal_id": "pk-x", "status": "applied"},   # terminal, appears FIRST
        {"proposal_id": "pk-x", "status": "killed"},    # terminal
        {"proposal_id": "pk-x", "status": "pending"},   # the one live row, LAST in file order
    ]
    # The old next()/loop-with-break first-wins path would have returned the
    # terminal "applied" row here -- silently wrong. resolve_proposal must return
    # the actionable pending row regardless of file order.
    assert A.resolve_proposal("pk-x", rows) is rows[2]


def test_all_terminal_duplicates_returns_first_harmlessly():
    rows = [
        {"proposal_id": "pk-y", "status": "applied"},
        {"proposal_id": "pk-y", "status": "shelved"},
    ]
    assert A.resolve_proposal("pk-y", rows) is rows[0]


def test_two_active_rows_raises_duplicate_error():
    """The exact L207 incident shape: two rows a `ship`/apply/revert could BOTH
    still act on, sharing one id -- must fail LOUD, never silently pick one."""
    rows = [
        {"proposal_id": "dup-1", "status": "pending"},
        {"proposal_id": "dup-1", "status": "approved"},
        {"proposal_id": "unique-1", "status": "pending"},
    ]
    with pytest.raises(A.DuplicateProposalError):
        A.resolve_proposal("dup-1", rows)
    # the unrelated id is unaffected
    assert A.resolve_proposal("unique-1", rows) is rows[2]


def test_active_statuses_match_uniqueness_guard():
    """resolve_proposal's notion of ACTIVE must stay byte-identical to
    test_proposal_id_uniqueness.py's ACTIVE_STATUSES, or the two guards could
    silently disagree about what counts as a collision."""
    uniq = pytest.importorskip("test_proposal_id_uniqueness")
    assert A._ACTIVE_STATUSES == uniq.ACTIVE_STATUSES


# ---------------------------------------------------------------------------
# Integration: the three former call sites now route through resolve_proposal
# ---------------------------------------------------------------------------

def test_set_status_updates_the_active_row_not_a_terminal_sibling(repo):
    rows = [
        {"proposal_id": "z-1", "status": "applied", "title": "old re-emission"},
        {"proposal_id": "z-1", "status": "approved", "title": "the live one"},
    ]
    A._set_status(rows, "z-1", status="apply_failed", failure_reason="test")
    # exactly the "approved" row (the actionable one) got updated
    updated = [r for r in rows if r.get("status") == "apply_failed"]
    assert len(updated) == 1
    assert updated[0]["title"] == "the live one"
    terminal = [r for r in rows if r["title"] == "old re-emission"]
    assert terminal[0]["status"] == "applied"  # untouched


def test_set_status_raises_loud_on_active_collision(repo):
    rows = [
        {"proposal_id": "z-2", "status": "pending", "title": "A"},
        {"proposal_id": "z-2", "status": "approved", "title": "B"},
    ]
    with pytest.raises(A.DuplicateProposalError):
        A._set_status(rows, "z-2", status="apply_failed")


def test_revert_resolves_the_one_applied_row_not_a_stale_duplicate(repo, monkeypatch):
    monkeypatch.setattr(A, "_run_gate", lambda: (True, ""))
    p = repo / "automation" / "state" / "conductor-proposals.jsonl"
    p.write_text(
        json.dumps({"proposal_id": "shelved-dup", "status": "shelved", "title": "old"}) + "\n"
        + json.dumps({
            "proposal_id": "r-1", "status": "approved", "title": "fold",
            "apply_ops": [{"file": "CLAUDE.md", "find": "MARKER_ONCE", "replace": "MARKER_DONE"}],
        }) + "\n",
        encoding="utf-8",
    )
    assert A.apply_approved() == 0
    assert A.revert("r-1") == 0
    assert "MARKER_ONCE" in (repo / "CLAUDE.md").read_text(encoding="utf-8")


def test_sync_companion_approvals_skips_a_collision_without_crashing(repo):
    """A collision on ONE decision must not stop the OTHER decisions in the batch
    from syncing -- fail loud (logged) for the ambiguous one, keep going."""
    props = repo / "automation" / "state" / "conductor-proposals.jsonl"
    props.write_text(
        "\n".join(json.dumps(r) for r in [
            {"proposal_id": "collide-1", "status": "pending", "title": "A"},
            {"proposal_id": "collide-1", "status": "approved", "title": "B"},
            {"proposal_id": "clean-1", "status": "pending", "title": "clean"},
        ]) + "\n",
        encoding="utf-8",
    )
    decisions = repo / "automation" / "state" / "companion-decisions.jsonl"
    decisions.write_text(
        "\n".join(json.dumps(r) for r in [
            {"id": "collide-1", "decision": "approve", "ts": "t1"},
            {"id": "clean-1", "decision": "approve", "ts": "t2"},
        ]) + "\n",
        encoding="utf-8",
    )
    changed = A.sync_companion_approvals()
    assert changed == 1  # only the unambiguous one flipped
    rows = A._read_proposals()
    clean = next(r for r in rows if r["proposal_id"] == "clean-1")
    assert clean["status"] == "approved"
    # the colliding pair is untouched (neither silently flipped)
    collide_rows = [r for r in rows if r["proposal_id"] == "collide-1"]
    assert {r["status"] for r in collide_rows} == {"pending", "approved"}
    # the collision was logged, not swallowed
    changelog = repo / "automation" / "state" / "autonomy-changelog.jsonl"
    assert changelog.exists()
    logged = [json.loads(ln) for ln in changelog.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert any(r.get("outcome") == "duplicate_id_blocked" for r in logged)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
