"""Guard: the pre-commit hook's shared-index-absorption hardening
(COMMIT-SCOPED-ENFORCEMENT, filed 2026-08-21, shipped 2026-09-03).

INCIDENT this fixes: a `git add <paths> && git commit` (bare, no pathspec)
swept 9 unrelated already-staged files from the shared checkout's index into
one commit, briefly reverting `heartbeat_core.py` (the LIVE trading engine)
onto `main`. The pre-commit hook's dir-count WARN fired and named the exact
risk, but was non-blocking and got read-and-discounted. Lesson:
strategy/candidates/_lesson-inbox/shared-index-absorption-reverted-live-fix-
2026-08-21.md

TWO layers under test:
  1. `setup/scripts/commit_scope_gate.decide()` -- the pure decision function
     the hook's automation-only REFUSE path calls. Unit-tested directly with
     synthetic staged-file / pathspec inputs (fast, no subprocess).
  2. The REAL hook script (`setup/git-hooks/pre-commit`) end-to-end in a
     throwaway git repo, same pattern as test_commit_scoped.py -- proves the
     shell wiring (env-var gating, opt-out, exit code) actually matches the
     python decision it delegates to, not just that the python function is
     correct in isolation.

FAIL-OPEN is the load-bearing property: an INTERACTIVE commit (no
GAMMA_AUTO_COMMIT marker) must NEVER be refused, no matter how foreign the
staged set looks. Case (a) below is that guarantee, and it is checked
against the REAL hook, not a mock.

RED-proofed by hand this fire: temporarily changed the hook's automation gate
from `[ "$GAMMA_AUTO_COMMIT" = "1" ]` to unconditional (always evaluate the
REFUSE path) and re-ran this suite -- `test_case_a_interactive_absorbed_file_commits`
failed (interactive commit got refused, which must never happen). Reverted;
suite back to green. Also flipped `commit_scope_gate.decide()`'s no-pathspec
branch from `bool(staged_files)` to `False` (i.e. "undeclared automation
scope always allowed") and re-ran -- `test_decide_no_pathspec_declared_refuses_if_anything_staged`
and the case-b integration test both failed. Restored.

Run:  cd backtest && python -m pytest tests/test_pre_commit_scope_enforcement_2026_09_03.py -q
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

from commit_scope_gate import decide  # noqa: E402

GIT = "git"
HOOK_SRC = REPO / "setup" / "git-hooks" / "pre-commit"

_POISON_GIT_ENV = ("GIT_INDEX_FILE", "GIT_DIR", "GIT_WORK_TREE", "GIT_PREFIX",
                   "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR")


@pytest.fixture(autouse=True)
def _clean_git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _POISON_GIT_ENV:
        monkeypatch.delenv(var, raising=False)
    # Never let this process's own automation markers (if any) leak into a
    # throwaway repo's commits.
    for var in ("GAMMA_AUTO_COMMIT", "GAMMA_COMMIT_PATHSPEC", "GAMMA_COMMIT_SCOPE_OFF"):
        monkeypatch.delenv(var, raising=False)


def _base_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _POISON_GIT_ENV
            and k not in ("GAMMA_AUTO_COMMIT", "GAMMA_COMMIT_PATHSPEC", "GAMMA_COMMIT_SCOPE_OFF")}


def _git(repo: Path, *args: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = _base_env()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [GIT, *args], cwd=str(repo), capture_output=True, text=True, check=False, env=env,
    )


def _has_git() -> bool:
    try:
        return subprocess.run([GIT, "--version"], capture_output=True).returncode == 0
    except (OSError, FileNotFoundError):
        return False


def _has_sh() -> bool:
    """The hook is `#!/bin/sh`; on Windows this needs Git's bundled sh.exe
    reachable (git.exe's install dir has one, or it's on PATH via Git Bash)."""
    try:
        cp = subprocess.run(["sh", "-c", "echo ok"], capture_output=True, text=True)
        return cp.returncode == 0 and "ok" in cp.stdout
    except (OSError, FileNotFoundError):
        return False


pytestmark = pytest.mark.skipif(not _has_git(), reason="git not on PATH")


# ------------------------------------------------------------- unit layer ---
# commit_scope_gate.decide() in isolation -- no subprocess, no git.

def test_decide_no_pathspec_declared_refuses_if_anything_staged() -> None:
    """Automation that fires without declaring ANY scope is the exact
    violation this exists to catch -- undeclared scope + staged files =
    refuse."""
    refuse, offending = decide(["a/one.txt", "b/two.txt"], None)
    assert refuse is True
    assert set(offending) == {"a/one.txt", "b/two.txt"}


def test_decide_no_pathspec_declared_allows_if_nothing_staged() -> None:
    refuse, offending = decide([], None)
    assert refuse is False
    assert offending == []


def test_decide_all_staged_within_pathspec_allows() -> None:
    refuse, offending = decide(
        ["strategy/candidates/a.json", "strategy/candidates/sub/b.json"],
        "strategy/candidates",
    )
    assert refuse is False
    assert offending == []


def test_decide_foreign_file_outside_pathspec_refuses_and_names_it() -> None:
    """THE core case: automation declared strategy/candidates, but the
    staged set also carries a file from another session's work -- must
    refuse and name exactly that file."""
    refuse, offending = decide(
        ["strategy/candidates/a.json", "setup/scripts/heartbeat_core.py"],
        "strategy/candidates",
    )
    assert refuse is True
    assert offending == ["setup/scripts/heartbeat_core.py"]


def test_decide_pathspec_boundary_is_directory_aware() -> None:
    """A pathspec of 'strategy/candidates' must NOT accidentally allow
    'strategy/candidates2/...' via a naive string-prefix match."""
    refuse, offending = decide(["strategy/candidates2/sneaky.json"], "strategy/candidates")
    assert refuse is True
    assert offending == ["strategy/candidates2/sneaky.json"]


def test_decide_multiple_declared_pathspecs() -> None:
    refuse, offending = decide(
        ["dirA/one.txt", "dirB/two.txt", "dirC/foreign.txt"],
        "dirA:dirB",
    )
    assert refuse is True
    assert offending == ["dirC/foreign.txt"]


# -------------------------------------------------------- integration layer -
# The REAL hook script, in a throwaway repo, same absorption setup as
# test_commit_scoped.py (concurrent "session B" leaves a foreign file staged).

@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")

    (repo / "dirA").mkdir()
    (repo / "dirB").mkdir()
    base = repo / "dirA" / "base.txt"
    base.write_text("base\n", encoding="utf-8")
    _git(repo, "add", "dirA/base.txt")
    cp = _git(repo, "commit", "-q", "-m", "initial")
    assert cp.returncode == 0, cp.stderr

    # Install the REAL hook -- same file the installer copies to .git/hooks/,
    # not a re-typed copy, so a future edit to the shipped hook is what this
    # test exercises.
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    dst = hooks_dir / "pre-commit"
    shutil.copyfile(HOOK_SRC, dst)
    if hasattr(os, "chmod"):
        try:
            os.chmod(dst, 0o755)
        except OSError:
            pass

    # No backtest/.venv or run_safety_gate.py in this throwaway repo, so the
    # hook's PY resolution falls back to bare "python" and
    # backtest/tests/run_safety_gate.py won't exist -- make that step a
    # harmless no-op by pointing GIT's working tree at a repo where that
    # python call fails to *find* the gate script and the hook's own `if !
    # "$PY" ...` would treat a nonzero/failed invocation as GATE RED. To keep
    # this test scoped to the tripwire/REFUSE logic (not the unrelated
    # safety-gate step), stub a trivial run_safety_gate.py that exits 0.
    stub_dir = repo / "backtest" / "tests"
    stub_dir.mkdir(parents=True, exist_ok=True)
    (stub_dir / "run_safety_gate.py").write_text(
        "import sys\nsys.exit(0)\n", encoding="utf-8"
    )

    # The hook resolves the REFUSE decision helper as $ROOT/setup/scripts/
    # commit_scope_gate.py -- copy the REAL module in (not a re-typed stub)
    # so this test exercises the actual shipped decision logic end-to-end.
    gate_dir = repo / "setup" / "scripts"
    gate_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / "setup" / "scripts" / "commit_scope_gate.py",
                     gate_dir / "commit_scope_gate.py")

    # "Concurrent session B" stages its own file and does not commit it.
    foreign = repo / "dirB" / "foreign.txt"
    foreign.write_text("foreign session's work\n", encoding="utf-8")
    cp = _git(repo, "add", "dirB/foreign.txt")
    assert cp.returncode == 0, cp.stderr

    return repo


def _staged(repo: Path) -> list[str]:
    return [ln for ln in _git(repo, "diff", "--cached", "--name-only").stdout.splitlines() if ln]


def _commit(repo: Path, msg: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    return _git(repo, "commit", "-m", msg, extra_env=extra_env)


@pytest.mark.skipif(not _has_sh(), reason="hook is #!/bin/sh -- needs sh on PATH")
def test_case_a_interactive_absorbed_file_commits(tmp_repo: Path) -> None:
    """(a) Interactive commit (no GAMMA_AUTO_COMMIT) with an absorbed extra
    file -> commits (fail-open, never blocks a human), and the WARN
    directive naming commit_scoped.py appears on stderr."""
    mine = tmp_repo / "dirA" / "mine.txt"
    mine.write_text("my work\n", encoding="utf-8")
    _git(tmp_repo, "add", "dirA/mine.txt")

    cp = _commit(tmp_repo, "interactive commit")

    assert cp.returncode == 0, f"interactive commit must NEVER be blocked -- stderr:\n{cp.stderr}"
    assert "commit_scoped.py" in cp.stderr
    # And the foreign file really did land -- WARN, not refuse, for interactive.
    committed = _git(tmp_repo, "show", "--stat", "--format=", "HEAD").stdout
    assert "foreign.txt" in committed


@pytest.mark.skipif(not _has_sh(), reason="hook is #!/bin/sh -- needs sh on PATH")
def test_case_b_automation_with_pathspec_and_foreign_file_refused(tmp_repo: Path) -> None:
    """(b) Automation marker set + pathspec declared (dirA only) + an extra
    staged file OUTSIDE that pathspec (dirB/foreign.txt) -> refused, and the
    offending file is named on stderr."""
    mine = tmp_repo / "dirA" / "mine.txt"
    mine.write_text("automated work\n", encoding="utf-8")
    _git(tmp_repo, "add", "dirA/mine.txt")

    cp = _commit(
        tmp_repo, "automated commit",
        extra_env={"GAMMA_AUTO_COMMIT": "1", "GAMMA_COMMIT_PATHSPEC": "dirA"},
    )

    assert cp.returncode != 0, "automated commit outside its declared pathspec must be refused"
    assert "REFUSE" in cp.stderr
    assert "dirB/foreign.txt" in cp.stderr
    # Nothing committed -- both files still exactly where they were.
    assert set(_staged(tmp_repo)) == {"dirA/mine.txt", "dirB/foreign.txt"}


@pytest.mark.skipif(not _has_sh(), reason="hook is #!/bin/sh -- needs sh on PATH")
def test_case_c_automation_with_opt_out_commits(tmp_repo: Path) -> None:
    """(c) Automation + GAMMA_COMMIT_SCOPE_OFF=1 -> commits (opt-out bypasses
    REFUSE entirely, for a genuine multi-scope automated commit)."""
    mine = tmp_repo / "dirA" / "mine.txt"
    mine.write_text("automated work, opted out\n", encoding="utf-8")
    _git(tmp_repo, "add", "dirA/mine.txt")

    cp = _commit(
        tmp_repo, "automated commit, opted out",
        extra_env={
            "GAMMA_AUTO_COMMIT": "1",
            "GAMMA_COMMIT_PATHSPEC": "dirA",
            "GAMMA_COMMIT_SCOPE_OFF": "1",
        },
    )

    assert cp.returncode == 0, f"opt-out must let the automated commit through -- stderr:\n{cp.stderr}"
    committed = _git(tmp_repo, "show", "--stat", "--format=", "HEAD").stdout
    assert "foreign.txt" in committed  # absorbed, but that's what the opt-out means


@pytest.mark.skipif(not _has_sh(), reason="hook is #!/bin/sh -- needs sh on PATH")
def test_automation_without_any_pathspec_declared_refuses(tmp_repo: Path) -> None:
    """Automation that sets GAMMA_AUTO_COMMIT but never declares
    GAMMA_COMMIT_PATHSPEC at all must still be refused if anything is
    staged -- silence is not a scope."""
    mine = tmp_repo / "dirA" / "mine.txt"
    mine.write_text("automated, undeclared\n", encoding="utf-8")
    _git(tmp_repo, "add", "dirA/mine.txt")

    cp = _commit(tmp_repo, "undeclared automated commit", extra_env={"GAMMA_AUTO_COMMIT": "1"})

    assert cp.returncode != 0
    assert "REFUSE" in cp.stderr
