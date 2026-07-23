"""Guard for self_check.check_candidates_untracked_backlog -- the CANDIDATES-UNTRACKED
VISIBILITY instrument (STRATEGY-CANDIDATES-UNTRACKED-BACKFILL, 2026-07-22).

Motivation: 1,176 files under strategy/candidates/ -- live chef/kitchen/prospector pipeline
state, confirmed NOT gitignored -- silently accumulated with ZERO commit history (no
disk-loss recovery path) until a one-time backfill commit (d148f7e8). The lesson's own fix
explicitly named a graduated guard as part (3): a cheap periodic check flagging the
untracked-count above a small threshold so this cannot silently re-accumulate unnoticed (C7).

Mirrors test_self_check_tv_cdp.py's fake-probe injection convention, but this check is
DEGRADED-only (never BROKEN) -- an untracked-file backlog has zero trading-relevant impact,
unlike a dead TV-CDP feed.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "self_check.py"

_spec = importlib.util.spec_from_file_location("self_check", MOD_PATH)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


def _fake_git(stdout: str):
    def _run():
        return SimpleNamespace(stdout=stdout, returncode=0)
    return _run


# ---- under/at threshold: never flags ----

def test_zero_untracked_never_flags():
    assert sc.check_candidates_untracked_backlog(run_git=_fake_git("")) == []


def test_at_threshold_never_flags():
    lines = "\n".join(f"?? strategy/candidates/f{i}.md" for i in range(sc.CANDIDATES_UNTRACKED_THRESHOLD))
    assert sc.check_candidates_untracked_backlog(run_git=_fake_git(lines)) == []


def test_non_untracked_lines_ignored():
    # modified (' M') / staged ('A ') entries must not count toward the untracked tally
    lines = "\n".join([" M strategy/candidates/_review-log.jsonl",
                        "A  strategy/candidates/new.md"] * 30)
    assert sc.check_candidates_untracked_backlog(run_git=_fake_git(lines)) == []


# ---- over threshold: flags DEGRADED, never BROKEN ----

def test_over_threshold_flags_degraded_not_broken():
    n = sc.CANDIDATES_UNTRACKED_THRESHOLD + 5
    lines = "\n".join(f"?? strategy/candidates/f{i}.md" for i in range(n))
    problems = sc.check_candidates_untracked_backlog(run_git=_fake_git(lines))
    assert len(problems) == 1
    assert "CANDIDATES-UNTRACKED" in problems[0]
    assert str(n) in problems[0]
    assert not sc._problem_is_broken(problems[0]), "untracked backlog has no trading-relevant impact -- must never be BROKEN"


def test_exactly_1176_reproduces_the_real_scar_count():
    n = 1176
    lines = "\n".join(f"?? strategy/candidates/f{i}.md" for i in range(n))
    problems = sc.check_candidates_untracked_backlog(run_git=_fake_git(lines))
    assert len(problems) == 1
    assert "1176" in problems[0]


# ---- fail-open: any git-invocation error must return [], never raise ----

def test_git_error_fails_open():
    def _boom():
        raise RuntimeError("git not found")
    assert sc.check_candidates_untracked_backlog(run_git=_boom) == []


def test_default_probe_never_raises():
    # No run_git injected -- exercises the real subprocess call against this repo's actual
    # git state. Must never raise regardless of outcome (rail-2, notify-only observer).
    problems = sc.check_candidates_untracked_backlog()
    assert isinstance(problems, list)


# ---- wiring: run() must call the check and feed it into problems ----

def test_run_source_wires_candidates_untracked_check():
    import inspect
    src = inspect.getsource(sc.run)
    assert "check_candidates_untracked_backlog()" in src
    assert "problems.extend(check_candidates_untracked_backlog())" in src
