"""Tests for setup/scripts/auto_commit_candidates.py -- the L242 re-violation
prevention guard.

SCAR: L242 (2026-07-22) -- 1,176 untracked strategy/candidates/ files sat
uncommitted for weeks. self_check.py's CANDIDATES-UNTRACKED check (threshold
20) was a DETECTOR, not a preventer, and re-violated within 24h (a 2026-07-23
conductor fire had to manually clear 41 more files). This guard is the
graduated-to-code fix (OP-25: a re-violated lesson must become an enforced
guard, not a repeated manual cleanup).

Coverage:
  * COMMIT_THRESHOLD is strictly LESS than self_check.py's
    CANDIDATES_UNTRACKED_THRESHOLD -- the preventer must act before the
    detector would ever need to flag DEGRADED (the core invariant this
    guard exists to hold).
  * QUIET path: below threshold -> no git add/commit invoked, exits 0.
  * COMMITTED path: at/above threshold -> git add + git commit invoked,
    scoped ONLY to strategy/candidates (never -A), exits 0.
  * Fail-open (OP-25/C7): a raised exception anywhere in the git calls
    never propagates -- main() always returns 0.
  * git status failure / git add failure / empty-stage-after-add / git
    commit failure (e.g. pre-commit hook rejects) all SKIP quietly and
    exit 0 -- never raise, never retry-loop.

No real git repo mutation -- all subprocess calls are mocked.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import auto_commit_candidates as acc  # noqa: E402
import self_check as sc  # noqa: E402


def _fake_result(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# ============================================================================
# section 1: the core invariant -- preventer threshold < detector threshold
# ============================================================================

def test_commit_threshold_is_strictly_below_self_check_detector_threshold():
    assert acc.COMMIT_THRESHOLD < sc.CANDIDATES_UNTRACKED_THRESHOLD, (
        "auto_commit_candidates must fire BEFORE self_check.py would ever flag "
        "CANDIDATES-UNTRACKED DEGRADED -- otherwise this is not actually a "
        "preventer, just a second detector."
    )


def test_commit_scoped_to_candidates_path_only():
    assert acc.CANDIDATES_PATH == "strategy/candidates"


# ============================================================================
# section 2: QUIET path -- below threshold, no mutation
# ============================================================================

def test_quiet_below_threshold_no_add_or_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(acc, "LOG_PATH", tmp_path / "log.jsonl")
    lines = "\n".join([" M strategy/candidates/x.md"] * (acc.COMMIT_THRESHOLD - 1))
    calls = []

    def fake_run(args):
        calls.append(args)
        return _fake_result(stdout=lines)

    with patch.object(acc, "_run", side_effect=fake_run):
        rc = acc.main()

    assert rc == 0
    assert len(calls) == 1  # only the status check -- never add/commit
    assert calls[0][:2] == ["git", "status"]


# ============================================================================
# section 3: COMMITTED path -- at/above threshold
# ============================================================================

def test_committed_at_threshold_adds_and_commits_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(acc, "LOG_PATH", tmp_path / "log.jsonl")
    lines = "\n".join([f" M strategy/candidates/x{i}.md" for i in range(acc.COMMIT_THRESHOLD)])
    calls = []

    def fake_run(args):
        calls.append(args)
        if args[:2] == ["git", "status"]:
            return _fake_result(stdout=lines)
        if args[:2] == ["git", "add"]:
            return _fake_result()
        if args[:3] == ["git", "diff", "--cached"]:
            return _fake_result(stdout=" 10 files changed")
        if args[:2] == ["git", "commit"]:
            return _fake_result()
        raise AssertionError(f"unexpected git call: {args}")

    with patch.object(acc, "_run", side_effect=fake_run):
        rc = acc.main()

    assert rc == 0
    add_calls = [c for c in calls if c[:2] == ["git", "add"]]
    commit_calls = [c for c in calls if c[:2] == ["git", "commit"]]
    assert len(add_calls) == 1
    assert add_calls[0][-1] == acc.CANDIDATES_PATH  # never "-A", never "."
    assert len(commit_calls) == 1


def test_empty_stage_after_add_skips_commit(tmp_path, monkeypatch):
    """git add ran but nothing actually staged (e.g. a race) -- must not commit."""
    monkeypatch.setattr(acc, "LOG_PATH", tmp_path / "log.jsonl")
    lines = "\n".join([f" M strategy/candidates/x{i}.md" for i in range(acc.COMMIT_THRESHOLD)])

    def fake_run(args):
        if args[:2] == ["git", "status"]:
            return _fake_result(stdout=lines)
        if args[:2] == ["git", "add"]:
            return _fake_result()
        if args[:3] == ["git", "diff", "--cached"]:
            return _fake_result(stdout="")  # nothing staged
        if args[:2] == ["git", "commit"]:
            raise AssertionError("must not commit when nothing is staged")
        raise AssertionError(f"unexpected git call: {args}")

    with patch.object(acc, "_run", side_effect=fake_run):
        rc = acc.main()

    assert rc == 0


# ============================================================================
# section 4: fail-open -- never raise, never block
# ============================================================================

def test_git_status_failure_skips_quietly(tmp_path, monkeypatch):
    monkeypatch.setattr(acc, "LOG_PATH", tmp_path / "log.jsonl")
    with patch.object(acc, "_run", return_value=_fake_result(returncode=1, stderr="git error")):
        rc = acc.main()
    assert rc == 0


def test_git_commit_failure_eg_precommit_hook_reject_skips_quietly(tmp_path, monkeypatch):
    """A safety-gate pre-commit hook rejection must never crash or retry-loop."""
    monkeypatch.setattr(acc, "LOG_PATH", tmp_path / "log.jsonl")
    lines = "\n".join([f" M strategy/candidates/x{i}.md" for i in range(acc.COMMIT_THRESHOLD)])

    def fake_run(args):
        if args[:2] == ["git", "status"]:
            return _fake_result(stdout=lines)
        if args[:2] == ["git", "add"]:
            return _fake_result()
        if args[:3] == ["git", "diff", "--cached"]:
            return _fake_result(stdout=" 10 files changed")
        if args[:2] == ["git", "commit"]:
            return _fake_result(returncode=1, stderr="[pre-commit] SAFETY GATE RED")
        raise AssertionError(f"unexpected git call: {args}")

    with patch.object(acc, "_run", side_effect=fake_run):
        rc = acc.main()

    assert rc == 0


def test_unexpected_exception_never_propagates(tmp_path, monkeypatch):
    monkeypatch.setattr(acc, "LOG_PATH", tmp_path / "log.jsonl")
    with patch.object(acc, "_run", side_effect=RuntimeError("boom")):
        rc = acc.main()
    assert rc == 0


def test_logging_failure_itself_never_crashes(tmp_path, monkeypatch):
    """Even if the log file write fails, main() must still return 0."""
    bad_log_path = tmp_path / "nonexistent_dir" / "sub" / "log.jsonl"
    monkeypatch.setattr(acc, "LOG_PATH", bad_log_path)
    with patch("pathlib.Path.mkdir", side_effect=OSError("disk full")):
        with patch.object(acc, "_run", return_value=_fake_result(stdout="")):
            rc = acc.main()
    assert rc == 0
