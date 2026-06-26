"""Integration tests for the autonomy actuator -- it can edit CLAUDE.md/params.json
autonomously, so every safety guard is pinned here. Each test spins up a throwaway
git repo, points the actuator's module globals at it, and stubs the safety gate so we
can exercise both the green (commit) and red (restore) paths deterministically.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "setup" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import autonomy_actuator as A  # noqa: E402


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A throwaway git repo with a target file + the actuator wired to it."""
    r = tmp_path / "repo"
    (r / "automation" / "state").mkdir(parents=True)
    _git(r, "init")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    target = r / "CLAUDE.md"
    target.write_text("line A\nMARKER_ONCE\nline C\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-m", "init")

    # point the actuator at the throwaway repo
    monkeypatch.setattr(A, "REPO", r)
    monkeypatch.setattr(A, "STATE", r / "automation" / "state")
    monkeypatch.setattr(A, "PROPOSALS", r / "automation" / "state" / "conductor-proposals.jsonl")
    monkeypatch.setattr(A, "CHANGELOG", r / "automation" / "state" / "autonomy-changelog.jsonl")
    monkeypatch.setattr(A, "SNAP_DIR", r / "automation" / "state" / ".autonomy-snapshots")
    monkeypatch.setattr(A, "_market_is_open", lambda: False)  # tests run any time
    return r


def _write_proposals(repo, rows):
    p = repo / "automation" / "state" / "conductor-proposals.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _status(repo, pid):
    p = repo / "automation" / "state" / "conductor-proposals.jsonl"
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("proposal_id") == pid:
                return r
    return None


def test_green_apply_commits(repo, monkeypatch):
    monkeypatch.setattr(A, "_run_gate", lambda: (True, ""))
    _write_proposals(repo, [{
        "proposal_id": "t-1", "status": "approved", "title": "fold",
        "apply_ops": [{"file": "CLAUDE.md", "find": "MARKER_ONCE", "replace": "MARKER_DONE"}],
    }])
    assert A.apply_approved() == 0
    assert "MARKER_DONE" in (repo / "CLAUDE.md").read_text(encoding="utf-8")
    row = _status(repo, "t-1")
    assert row["status"] == "applied" and row.get("commit_sha")
    # the TARGET file is committed (clean); the actuator deliberately does NOT commit
    # its own bookkeeping (proposals ledger / changelog / snapshots) -- those stay untracked.
    assert _git(repo, "status", "--porcelain", "--", "CLAUDE.md").stdout.strip() == ""
    # audit + snapshot exist
    assert (repo / "automation" / "state" / "autonomy-changelog.jsonl").exists()
    assert (repo / "automation" / "state" / ".autonomy-snapshots" / "t-1" / "CLAUDE.md").exists()


def test_red_gate_restores_no_commit(repo, monkeypatch):
    monkeypatch.setattr(A, "_run_gate", lambda: (False, "test_x FAILED"))
    before = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    head_before = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _write_proposals(repo, [{
        "proposal_id": "t-2", "status": "approved", "title": "bad",
        "apply_ops": [{"file": "CLAUDE.md", "find": "MARKER_ONCE", "replace": "BROKEN"}],
    }])
    assert A.apply_approved() == 1  # a failure -> nonzero
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == before  # fully restored
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == head_before  # NO commit
    assert _status(repo, "t-2")["status"] == "apply_failed"


def test_prose_only_refused(repo, monkeypatch):
    monkeypatch.setattr(A, "_run_gate", lambda: (True, ""))
    before = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    _write_proposals(repo, [{
        "proposal_id": "t-3", "status": "approved", "title": "prose",
        "apply": "go edit CLAUDE.md and append ,177 somewhere",  # prose, no apply_ops
    }])
    A.apply_approved()
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == before  # untouched
    assert _status(repo, "t-3")["status"] == "needs_structured_apply"


def test_ambiguous_find_refused(repo, monkeypatch):
    monkeypatch.setattr(A, "_run_gate", lambda: (True, ""))
    (repo / "CLAUDE.md").write_text("DUP\nDUP\n", encoding="utf-8")  # find occurs 2x
    _git(repo, "commit", "-am", "dup")
    before = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    _write_proposals(repo, [{
        "proposal_id": "t-4", "status": "approved", "title": "ambig",
        "apply_ops": [{"file": "CLAUDE.md", "find": "DUP", "replace": "X"}],
    }])
    A.apply_approved()
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == before  # refused, untouched
    assert _status(repo, "t-4")["status"] == "needs_structured_apply"


def test_revert_restores(repo, monkeypatch):
    monkeypatch.setattr(A, "_run_gate", lambda: (True, ""))
    original = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    _write_proposals(repo, [{
        "proposal_id": "t-5", "status": "approved", "title": "fold",
        "apply_ops": [{"file": "CLAUDE.md", "find": "MARKER_ONCE", "replace": "MARKER_DONE"}],
    }])
    A.apply_approved()
    assert "MARKER_DONE" in (repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert A.revert("t-5") == 0
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == original  # back to pre-apply
    assert _status(repo, "t-5")["status"] == "reverted"


def test_market_hours_gate_noop(repo, monkeypatch):
    monkeypatch.setattr(A, "_market_is_open", lambda: True)  # pretend RTH
    monkeypatch.setattr(A, "_run_gate", lambda: (True, ""))
    before = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    _write_proposals(repo, [{
        "proposal_id": "t-6", "status": "approved", "title": "fold",
        "apply_ops": [{"file": "CLAUDE.md", "find": "MARKER_ONCE", "replace": "X"}],
    }])
    assert A.apply_approved() == 0
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8") == before  # nothing applied during RTH
    assert _status(repo, "t-6")["status"] == "approved"  # left for after-hours
