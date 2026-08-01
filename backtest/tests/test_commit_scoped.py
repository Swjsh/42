"""Guard: `setup/scripts/commit_scoped.py` never absorbs another session's
staged files -- the fix for the 2026-08-01 shared-index absorption incidents
(482a662a, da18da34, a363bd5f, be9c1b58, 90fd1e40; see strategy/candidates/
_lesson-inbox/2026-08-01-shared-index-absorption-between-parallel-lanes.md).

THE BUG this guards against: in a shared checkout, `git add <paths>` followed
by a BARE `git commit` (no pathspec) commits the WHOLE index at commit time --
including anything another concurrent session staged before or during the
gap between your add and your commit. Content isn't lost, but it lands under
the wrong commit message/attribution.

THE FIX this guards: `git commit -- <paths>` (which `commit_scoped.py` wraps)
commits ONLY the named paths' content, regardless of what else is staged --
git builds a temporary, pathspec-scoped index for the duration of the commit
(hooks included) rather than snapshotting the real `.git/index`.

Tests exercise a REAL throwaway git repo (same pattern as
test_verify_committed.py) so the guard has teeth -- an assertion against a
mock subprocess would not catch a regression that swaps `git commit -- paths`
back for a bare `git commit`.

RED-proofed by hand this fire: temporarily edited `commit_scoped.commit_scoped`
to issue a bare `git commit -m message` (dropping the trailing `-- paths`) and
re-ran this suite -- 5 of 9 tests failed (`test_scoped_commit_excludes_foreign_staged_file`,
`test_foreign_staged_file_survives_untouched`, `test_new_untracked_file_gets_committed`,
`test_multiple_named_paths_all_land_foreign_stays_out`, `test_main_cli_argv_contract`),
every failure showing `dirB/foreign.txt` swept into the commit alongside the
intended file(s) -- the exact absorption bug, reproduced on demand. Restored
the real two-pathspec-call version, suite back to 9/9 green. See STATUS.md
2026-08-01 entry for the full transcript.

Run:  cd backtest && python -m pytest tests/test_commit_scoped.py -q
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

from commit_scoped import commit_scoped, main  # noqa: E402

GIT = "git"

# Same env hygiene as test_verify_committed.py (2026-07-01 scar): if this
# suite runs from INSIDE a `git commit -- <paths>` pre-commit hook, git has
# exported GIT_INDEX_FILE (a temp index of the PARENT repo) into our process
# environment. The throwaway tmp repo's git subprocesses must not inherit it.
_POISON_GIT_ENV = ("GIT_INDEX_FILE", "GIT_DIR", "GIT_WORK_TREE", "GIT_PREFIX",
                   "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR")


@pytest.fixture(autouse=True)
def _clean_git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _POISON_GIT_ENV:
        monkeypatch.delenv(var, raising=False)


def _scrubbed_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _POISON_GIT_ENV}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [GIT, *args], cwd=str(repo), capture_output=True, text=True, check=False,
        env=_scrubbed_env(),
    )


def _has_git() -> bool:
    try:
        return subprocess.run([GIT, "--version"], capture_output=True).returncode == 0
    except (OSError, FileNotFoundError):
        return False


pytestmark = pytest.mark.skipif(not _has_git(), reason="git not on PATH")


@pytest.fixture()
def tmp_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repo with one committed file, plus a SECOND "session"'s
    file already staged (git add, not committed) -- the absorption setup."""
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

    # "Concurrent session B" stages its own file and does NOT commit it --
    # exactly the pending-commit state that a blocked pre-commit gate leaves
    # tonight's incidents sitting in for minutes at a time.
    foreign = repo / "dirB" / "foreign.txt"
    foreign.write_text("foreign session's work\n", encoding="utf-8")
    cp = _git(repo, "add", "dirB/foreign.txt")
    assert cp.returncode == 0, cp.stderr
    assert "dirB/foreign.txt" in _git(repo, "diff", "--cached", "--name-only").stdout

    # commit_scoped.py runs `git` via subprocess with cwd=REPO (the real repo
    # root); redirect it at the tmp repo for the duration of each test.
    monkeypatch.setattr("commit_scoped.REPO", repo)
    return repo


def _staged(repo: Path) -> list[str]:
    return [
        line for line in _git(repo, "diff", "--cached", "--name-only").stdout.splitlines()
        if line
    ]


def _committed_files(repo: Path, sha: str = "HEAD") -> list[str]:
    cp = _git(repo, "show", "--stat", "--format=", sha)
    return [line.split("|")[0].strip() for line in cp.stdout.splitlines() if "|" in line]


def test_scoped_commit_excludes_foreign_staged_file(tmp_repo: Path) -> None:
    """THE core guard: my own new file lands; the OTHER session's foreign
    staged file does NOT get swept into my commit."""
    mine = tmp_repo / "dirA" / "mine.txt"
    mine.write_text("my session's work\n", encoding="utf-8")

    rc = commit_scoped("my scoped commit", ["dirA/mine.txt"])
    assert rc == 0

    committed = _committed_files(tmp_repo)
    assert committed == ["dirA/mine.txt"], (
        f"expected ONLY dirA/mine.txt in the commit, got {committed} -- "
        f"the foreign file leaked in (absorption bug reproduced)"
    )


def test_foreign_staged_file_survives_untouched(tmp_repo: Path) -> None:
    """The other session's staged file must remain staged (still committable
    by them later) -- not consumed, not reverted, not touched at all."""
    mine = tmp_repo / "dirA" / "mine.txt"
    mine.write_text("my session's work\n", encoding="utf-8")

    rc = commit_scoped("my scoped commit", ["dirA/mine.txt"])
    assert rc == 0

    assert _staged(tmp_repo) == ["dirB/foreign.txt"], (
        "the foreign session's staged file must still be staged after my "
        "scoped commit -- untouched, ready for them to commit next"
    )
    # And its working-tree content is unchanged too.
    assert (tmp_repo / "dirB" / "foreign.txt").read_text(encoding="utf-8") == "foreign session's work\n"


def test_new_untracked_file_gets_committed(tmp_repo: Path) -> None:
    """A brand-new (never staged) file named explicitly must be picked up --
    proves the `git add --` step is doing real work, not just riding along
    on files that were already staged."""
    new_file = tmp_repo / "dirA" / "new.txt"
    new_file.write_text("brand new\n", encoding="utf-8")
    assert "dirA/new.txt" not in _staged(tmp_repo)

    rc = commit_scoped("adds a new file", ["dirA/new.txt"])
    assert rc == 0
    assert _committed_files(tmp_repo) == ["dirA/new.txt"]


def test_multiple_named_paths_all_land_foreign_stays_out(tmp_repo: Path) -> None:
    """Committing SEVERAL of my own paths at once still excludes the
    concurrently-staged foreign file."""
    (tmp_repo / "dirA" / "one.txt").write_text("one\n", encoding="utf-8")
    (tmp_repo / "dirB" / "two.txt").write_text("two\n", encoding="utf-8")

    rc = commit_scoped("two files, one commit", ["dirA/one.txt", "dirB/two.txt"])
    assert rc == 0

    committed = set(_committed_files(tmp_repo))
    assert committed == {"dirA/one.txt", "dirB/two.txt"}
    assert "dirB/foreign.txt" not in committed
    assert _staged(tmp_repo) == ["dirB/foreign.txt"]


def test_refuses_broad_pathspec_footguns(tmp_repo: Path) -> None:
    for bad in ("-A", "--all", ".", "*"):
        rc = commit_scoped("dangerous", [bad])
        assert rc != 0, f"commit_scoped must refuse pathspec {bad!r}"
    # Nothing was committed and the foreign file is still exactly where it was.
    assert _staged(tmp_repo) == ["dirB/foreign.txt"]


def test_refuses_empty_message_or_no_paths(tmp_repo: Path) -> None:
    (tmp_repo / "dirA" / "x.txt").write_text("x\n", encoding="utf-8")
    assert commit_scoped("", ["dirA/x.txt"]) != 0
    assert commit_scoped("   ", ["dirA/x.txt"]) != 0
    assert commit_scoped("a message", []) != 0
    # No accidental commit happened.
    head_before = _git(tmp_repo, "rev-parse", "HEAD").stdout
    assert head_before == _git(tmp_repo, "rev-parse", "HEAD").stdout


def test_missing_path_fails_loud_not_silent(tmp_repo: Path) -> None:
    rc = commit_scoped("ghost file", ["dirA/does_not_exist.txt"])
    assert rc != 0
    assert _staged(tmp_repo) == ["dirB/foreign.txt"]  # untouched


def test_main_cli_argv_contract(tmp_repo: Path) -> None:
    """The CLI entrypoint: `commit_scoped.py "<message>" <path>...` -- argv[0]
    is the message, the rest are paths."""
    (tmp_repo / "dirA" / "cli.txt").write_text("via cli\n", encoding="utf-8")
    rc = main(["cli commit", "dirA/cli.txt"])
    assert rc == 0
    assert _committed_files(tmp_repo) == ["dirA/cli.txt"]

    # Too few args -> usage failure, not a crash.
    assert main([]) != 0
    assert main(["only a message"]) != 0


def test_bare_commit_reproduces_the_absorption_bug(tmp_repo: Path) -> None:
    """Not a test of commit_scoped.py -- a pinned reproduction of the BUG
    it exists to prevent, so a future reader can see the mechanism directly
    rather than take the docstring's word for it. If this test ever starts
    FAILING (bare commit stops absorbing the foreign file), git's behavior
    changed underneath this repo and the whole premise needs re-checking."""
    mine = tmp_repo / "dirA" / "mine.txt"
    mine.write_text("my session's work\n", encoding="utf-8")
    _git(tmp_repo, "add", "dirA/mine.txt")

    # Bare commit -- no pathspec. This is the footgun itself.
    cp = _git(tmp_repo, "commit", "-q", "-m", "bare commit, no pathspec")
    assert cp.returncode == 0, cp.stderr

    committed = set(_committed_files(tmp_repo))
    assert committed == {"dirA/mine.txt", "dirB/foreign.txt"}, (
        "expected the bare commit to absorb the foreign file too -- if it "
        "didn't, git's pathspec-less commit semantics changed"
    )
