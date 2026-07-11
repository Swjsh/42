"""Tests for setup/scripts/twin_gauntlet_conductor_hook.py -- B2b.

Covers: file->path mapping, the PURE detect_gap() decision logic (trading-path
commit -> flag; non-trading commit -> no flag; fresh coverage/gauntlet-last
evidence clears a flag; STALE evidence dated before the commit does NOT clear
it; dedup by newest implicated commit sha so a persisting gap is not re-flagged
every fire), and the end-to-end run_check() orchestrator against fixture
STATUS.md/queue.md files with an INJECTED git-log function (never touches the
real repo's git history or the real STATUS.md/queue.md).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", ""):
    sys.path.insert(0, str(REPO / _p) if _p else str(REPO))

import twin_gauntlet_conductor_hook as hook  # noqa: E402


def _commit(sha, ts_utc, subject, files):
    return {"sha": sha, "ts_utc": ts_utc, "subject": subject, "files": files}


def _fixture_git_log(commits):
    """Mimics real `since_sha..HEAD` semantics over a fixed, oldest-first commit
    list -- lets tests drive run_check() deterministically without a real repo."""
    def _fn(repo_root, since_sha, max_commits):
        if since_sha is None:
            return list(commits)
        idx = next((i for i, c in enumerate(commits) if c["sha"] == since_sha), None)
        if idx is None:
            return list(commits)
        return commits[idx + 1:]
    return _fn


STATUS_MD_SEED = "# STATUS\n\n## Known broken\n"
QUEUE_MD_SEED = "# QUEUE\n\n## Active backlog\n\n"


# ============================================================================
# map_files_to_paths
# ============================================================================

def test_map_files_to_paths_exit_manager_maps_all_exit_branches():
    mapped = hook.map_files_to_paths(["automation/state/fleet/exit_manager.py"])
    assert mapped == {"tp1_trail", "structure_stop", "catastrophe_cap", "max_hold",
                      "restart_open_position"}
    assert "entry" not in mapped


def test_map_files_to_paths_risk_gate_maps_entry_only():
    mapped = hook.map_files_to_paths(["backtest/lib/risk_gate.py"])
    assert mapped == {"entry"}


def test_map_files_to_paths_heartbeat_core_maps_everything():
    mapped = hook.map_files_to_paths(["setup/scripts/heartbeat_core.py"])
    assert mapped == set(hook.tg.PATH_REGISTRY)


def test_map_files_to_paths_non_trading_file_maps_nothing():
    mapped = hook.map_files_to_paths(["markdown/planning/TWIN-PROGRAM.md", "README.md"])
    assert mapped == set()


def test_map_files_to_paths_is_basename_robust_to_directory():
    """Matches by basename -- robust to a future directory move (still conservative:
    over-matching costs nothing, an advisory flag firing spuriously is cheap)."""
    mapped = hook.map_files_to_paths(["some/new/location/exit_manager.py"])
    assert "structure_stop" in mapped


# ============================================================================
# detect_gap -- pure decision logic
# ============================================================================

def test_detect_gap_non_trading_commit_no_flag():
    commits = [_commit("aaa1111", "2026-07-11T04:00:00+00:00", "docs: update README", ["README.md"])]
    gap = hook.detect_gap(commits=commits, watermark={}, coverage={}, gauntlet_last={})
    assert gap["flag_needed"] is False
    assert gap["implicated"] == {}


def test_detect_gap_trading_path_commit_no_coverage_flags():
    commits = [_commit("bbb2222", "2026-07-11T04:30:00+00:00", "fix(exit): tighten trail",
                       ["automation/state/fleet/exit_manager.py"])]
    gap = hook.detect_gap(commits=commits, watermark={}, coverage={}, gauntlet_last={})
    assert gap["flag_needed"] is True
    assert "structure_stop" in gap["implicated"]
    assert gap["newest_commit_sha"] == "bbb2222"


def test_detect_gap_fresh_path_coverage_green_clears_flag():
    commits = [_commit("bbb2222", "2026-07-11T04:30:00+00:00", "fix(exit): tighten trail",
                       ["automation/state/fleet/exit_manager.py"])]
    coverage = {"paths": {p: {"status": "green", "last_updated_utc": "2026-07-11T05:00:00+00:00"}
                          for p in ("tp1_trail", "structure_stop", "catastrophe_cap", "max_hold",
                                   "restart_open_position")}}
    gap = hook.detect_gap(commits=commits, watermark={}, coverage=coverage, gauntlet_last={})
    assert gap["flag_needed"] is False


def test_detect_gap_stale_coverage_before_commit_still_flags():
    """Coverage green DATED BEFORE the commit must NOT satisfy it -- otherwise a
    trading-path change could hide behind yesterday's unrelated pass."""
    commits = [_commit("bbb2222", "2026-07-11T04:30:00+00:00", "fix(exit): tighten trail",
                       ["automation/state/fleet/exit_manager.py"])]
    coverage = {"paths": {"structure_stop": {"status": "green",
                                             "last_updated_utc": "2026-07-11T04:00:00+00:00"}}}
    gap = hook.detect_gap(commits=commits, watermark={}, coverage=coverage, gauntlet_last={})
    assert gap["flag_needed"] is True
    assert "structure_stop" in gap["implicated"]


def test_detect_gap_partial_coverage_still_flags_uncovered_paths():
    """exit_manager.py maps to 5 paths -- only 3 covered means the other 2 still flag."""
    commits = [_commit("bbb2222", "2026-07-11T04:30:00+00:00", "fix(exit): tighten trail",
                       ["automation/state/fleet/exit_manager.py"])]
    coverage = {"paths": {p: {"status": "green", "last_updated_utc": "2026-07-11T05:00:00+00:00"}
                          for p in ("tp1_trail", "structure_stop", "catastrophe_cap")}}
    gap = hook.detect_gap(commits=commits, watermark={}, coverage=coverage, gauntlet_last={})
    assert gap["flag_needed"] is True
    assert set(gap["implicated"]) == {"max_hold", "restart_open_position"}


def test_detect_gap_fresh_gauntlet_last_pass_clears_flag():
    commits = [_commit("ccc3333", "2026-07-11T05:00:00+00:00", "feat(entry): new gate",
                       ["backtest/lib/risk_gate.py"])]
    gauntlet_last = {"ts_et": "2026-07-11T06:00:00-04:00", "overall": "PASS",
                     "paths": {"entry": "PASS"}}
    gap = hook.detect_gap(commits=commits, watermark={}, coverage={}, gauntlet_last=gauntlet_last)
    assert gap["flag_needed"] is False


def test_detect_gap_stale_gauntlet_last_does_not_clear_flag():
    commits = [_commit("ccc3333", "2026-07-11T05:00:00+00:00", "feat(entry): new gate",
                       ["backtest/lib/risk_gate.py"])]
    # ts_et 00:00 ET-04:00 == 04:00 UTC, BEFORE the commit's 05:00 UTC -> stale evidence.
    gauntlet_last = {"ts_et": "2026-07-11T00:00:00-04:00", "overall": "PASS",
                     "paths": {"entry": "PASS"}}
    gap = hook.detect_gap(commits=commits, watermark={}, coverage={}, gauntlet_last=gauntlet_last)
    assert gap["flag_needed"] is True


def test_detect_gap_dedup_same_head_not_reflagged():
    commits = [_commit("bbb2222", "2026-07-11T04:30:00+00:00", "fix(exit): tighten trail",
                       ["automation/state/fleet/exit_manager.py"])]
    watermark = {"last_flagged_head_sha": "bbb2222"}
    gap = hook.detect_gap(commits=commits, watermark=watermark, coverage={}, gauntlet_last={})
    assert gap["flag_needed"] is False           # already flagged for this exact head
    assert gap["implicated"]                     # but the gap itself is still real/reported


def test_detect_gap_new_commit_after_flagged_head_reflags():
    commits = [
        _commit("bbb2222", "2026-07-11T04:30:00+00:00", "fix(exit): tighten trail",
               ["automation/state/fleet/exit_manager.py"]),
        _commit("ddd4444", "2026-07-11T05:30:00+00:00", "fix(exit): another change",
               ["automation/state/fleet/exit_manager.py"]),
    ]
    watermark = {"last_flagged_head_sha": "bbb2222"}   # previously flagged at the OLD head
    gap = hook.detect_gap(commits=commits, watermark=watermark, coverage={}, gauntlet_last={})
    assert gap["flag_needed"] is True
    assert gap["newest_commit_sha"] == "ddd4444"


# ============================================================================
# run_check -- end-to-end orchestrator against fixture STATUS.md/queue.md
# ============================================================================

def _seed(tmp_path):
    status = tmp_path / "STATUS.md"
    queue = tmp_path / "queue.md"
    status.write_text(STATUS_MD_SEED, encoding="utf-8")
    queue.write_text(QUEUE_MD_SEED, encoding="utf-8")
    return status, queue


def test_run_check_fixture_git_log_flags_status_and_queue(tmp_path):
    commits = [_commit("bbb2222", "2026-07-11T04:30:00+00:00", "fix(exit): tighten trail",
                       ["automation/state/fleet/exit_manager.py"])]
    status_path, queue_path = _seed(tmp_path)
    watermark_path = tmp_path / "watermark.json"
    coverage_path = tmp_path / "path-coverage.json"   # missing -> no coverage
    gauntlet_last_path = tmp_path / "gauntlet-last.json"  # missing -> no gauntlet evidence
    now_et = datetime(2026, 7, 11, 22, 0)

    result = hook.run_check(now_et=now_et, watermark_path=watermark_path, coverage_path=coverage_path,
                            gauntlet_last_path=gauntlet_last_path, status_path=status_path,
                            queue_path=queue_path, git_log_fn=_fixture_git_log(commits))

    assert result["checked"] is True
    assert result["flagged"] is True
    assert "structure_stop" in result["implicated_paths"]

    status_text = status_path.read_text(encoding="utf-8")
    assert "TWIN-GAUNTLET-GAP" in status_text
    assert "bbb2222" in status_text

    queue_text = queue_path.read_text(encoding="utf-8")
    assert "TWIN-GAUNTLET-GAP-" in queue_text
    assert "status:pending" in queue_text

    watermark = json.loads(watermark_path.read_text(encoding="utf-8"))
    assert watermark["last_checked_commit"] == "bbb2222"
    assert watermark["last_flagged_head_sha"] == "bbb2222"


def test_run_check_non_trading_commit_no_flag_files_unchanged(tmp_path):
    commits = [_commit("aaa1111", "2026-07-11T04:00:00+00:00", "docs: update README", ["README.md"])]
    status_path, queue_path = _seed(tmp_path)
    status_before = status_path.read_text(encoding="utf-8")
    queue_before = queue_path.read_text(encoding="utf-8")
    watermark_path = tmp_path / "watermark.json"

    result = hook.run_check(now_et=datetime(2026, 7, 11, 22, 0), watermark_path=watermark_path,
                            coverage_path=tmp_path / "path-coverage.json",
                            gauntlet_last_path=tmp_path / "gauntlet-last.json",
                            status_path=status_path, queue_path=queue_path,
                            git_log_fn=_fixture_git_log(commits))

    assert result["checked"] is True
    assert result["flagged"] is False
    assert status_path.read_text(encoding="utf-8") == status_before
    assert queue_path.read_text(encoding="utf-8") == queue_before
    # watermark still advances -- next run won't re-scan this commit
    watermark = json.loads(watermark_path.read_text(encoding="utf-8"))
    assert watermark["last_checked_commit"] == "aaa1111"


def test_run_check_no_new_commits_is_a_clean_noop(tmp_path):
    status_path, queue_path = _seed(tmp_path)
    result = hook.run_check(now_et=datetime(2026, 7, 11, 22, 0), watermark_path=tmp_path / "watermark.json",
                            coverage_path=tmp_path / "path-coverage.json",
                            gauntlet_last_path=tmp_path / "gauntlet-last.json",
                            status_path=status_path, queue_path=queue_path,
                            git_log_fn=_fixture_git_log([]))
    assert result == {"checked": True, "flagged": False, "reason": "no new commits", "commits": 0}


def test_run_check_dedup_across_repeated_fires_same_commits(tmp_path):
    """Simulates the conductor firing twice before any new commit lands -- the
    watermark's normal since_sha advancement means the second fire's fixture
    git-log returns [] (mirrors real `sha..HEAD` semantics), so it must NOT
    re-append a second STATUS.md line."""
    commits = [_commit("bbb2222", "2026-07-11T04:30:00+00:00", "fix(exit): tighten trail",
                       ["automation/state/fleet/exit_manager.py"])]
    status_path, queue_path = _seed(tmp_path)
    watermark_path = tmp_path / "watermark.json"
    kwargs = dict(coverage_path=tmp_path / "path-coverage.json",
                 gauntlet_last_path=tmp_path / "gauntlet-last.json",
                 status_path=status_path, queue_path=queue_path,
                 git_log_fn=_fixture_git_log(commits))

    r1 = hook.run_check(now_et=datetime(2026, 7, 11, 22, 0), watermark_path=watermark_path, **kwargs)
    r2 = hook.run_check(now_et=datetime(2026, 7, 11, 23, 0), watermark_path=watermark_path, **kwargs)

    assert r1["flagged"] is True
    assert r2["flagged"] is False
    assert r2["reason"] == "no new commits"
    status_text = status_path.read_text(encoding="utf-8")
    assert status_text.count("TWIN-GAUNTLET-GAP") == 1   # not re-spammed


def test_run_check_fail_open_never_raises(tmp_path):
    def _boom(repo_root, since_sha, max_commits):
        raise RuntimeError("simulated git failure")
    result = hook.run_check(now_et=datetime(2026, 7, 11, 22, 0), watermark_path=tmp_path / "watermark.json",
                            coverage_path=tmp_path / "path-coverage.json",
                            gauntlet_last_path=tmp_path / "gauntlet-last.json",
                            status_path=tmp_path / "STATUS.md", queue_path=tmp_path / "queue.md",
                            git_log_fn=_boom)
    assert result["checked"] is False
    assert "simulated git failure" in result["error"]


def test_run_check_missing_status_marker_is_fail_open(tmp_path):
    """A STATUS.md without the '## Known broken' marker must degrade silently
    (never crash) -- mirrors guard_runner_slow.py's own _flag_status_md contract."""
    commits = [_commit("bbb2222", "2026-07-11T04:30:00+00:00", "fix(exit): tighten trail",
                       ["automation/state/fleet/exit_manager.py"])]
    status_path = tmp_path / "STATUS.md"
    status_path.write_text("# STATUS\n\nno marker here\n", encoding="utf-8")
    queue_path = tmp_path / "queue.md"
    queue_path.write_text(QUEUE_MD_SEED, encoding="utf-8")
    result = hook.run_check(now_et=datetime(2026, 7, 11, 22, 0), watermark_path=tmp_path / "watermark.json",
                            coverage_path=tmp_path / "path-coverage.json",
                            gauntlet_last_path=tmp_path / "gauntlet-last.json",
                            status_path=status_path, queue_path=queue_path,
                            git_log_fn=_fixture_git_log(commits))
    assert result["checked"] is True
    assert result["flagged"] is True   # the flag itself still "happened" -- queue.md still got it
    assert "no marker here" in status_path.read_text(encoding="utf-8")  # STATUS.md untouched


# ============================================================================
# real git log parser -- smoke test against THIS repo (read-only, no fixture)
# ============================================================================

def test_default_git_log_returns_parseable_recent_commits():
    """Real subprocess call against the actual repo -- read-only (git log), never
    mutates anything. Just proves the parser produces well-formed rows."""
    commits = hook._default_git_log(REPO, None, 5)
    assert isinstance(commits, list)
    if commits:  # a fresh/shallow clone could plausibly return [] -- don't hard-fail on that
        for c in commits:
            assert set(c.keys()) == {"sha", "ts_utc", "subject", "files"}
            assert len(c["sha"]) == 40
            datetime.fromisoformat(c["ts_utc"])  # must parse


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
