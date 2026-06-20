"""Guard: `git commit --only` silently drops UNTRACKED new files.

Graduates the 2026-06-19 foot-gun (markdown/doctrine/LESSONS-LEARNED.md "git commit --only
drops untracked"; OP-25 C7 silent-success-is-failure). Wave B deliverables were
reported "committed" by a `--only` commit but were actually never tracked -- the
commit reported a big diff from the modified/staged files and the omission of the
untracked new files went unnoticed for hours.

This exercises setup/scripts/verify_committed.py against a REAL throwaway git
repo so the guard has teeth:

  * test_tracked_file_passes        -> a staged/committed file is reported tracked.
  * test_untracked_file_is_flagged  -> THE BUG: an untracked new file under the
                                       same dir is flagged by find_untracked and
                                       makes assert_all_tracked raise. This is the
                                       exact silent drop the lesson is about; if
                                       verify_committed ever stops detecting it,
                                       this fails.
  * test_commit_only_reproduces_the_drop -> end-to-end reproduction: `git commit
                                       --only tracked` succeeds with a non-empty
                                       diff WHILE leaving an untracked sibling out
                                       of the commit; the helper catches it.

Regression caught: any change that makes verify_committed.py stop using the
authoritative `git ls-files --error-unmatch` check (e.g. a refactor to a glob /
os.path.exists check that treats on-disk presence as "tracked") would let an
untracked file pass -> this test fails.

Run:  cd backtest && python -m pytest tests/test_verify_committed.py -q
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# verify_committed lives in setup/scripts (repo root = .../42, this file is in
# 42/backtest/tests/).
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

from verify_committed import (  # noqa: E402
    UntrackedFilesError,
    assert_all_tracked,
    find_untracked,
    is_tracked,
)

GIT = "git"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [GIT, *args], cwd=str(repo), capture_output=True, text=True, check=False
    )


def _has_git() -> bool:
    try:
        return subprocess.run([GIT, "--version"], capture_output=True).returncode == 0
    except (OSError, FileNotFoundError):
        return False


pytestmark = pytest.mark.skipif(not _has_git(), reason="git not on PATH")


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    """A throwaway git repo with one tracked+committed file and one UNTRACKED file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    # Make commits possible without touching global config.
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")

    pkg = repo / "pkg"
    pkg.mkdir()
    tracked = pkg / "tracked.py"
    tracked.write_text("# tracked\n", encoding="utf-8")
    _git(repo, "add", "pkg/tracked.py")
    cp = _git(repo, "commit", "-q", "-m", "initial")
    assert cp.returncode == 0, cp.stderr

    # The silent-drop victim: a NEW file under the same dir that was never `git add`-ed.
    (pkg / "untracked.py").write_text("# untracked new file\n", encoding="utf-8")
    return repo


def test_tracked_file_passes(tmp_repo: Path) -> None:
    assert is_tracked("pkg/tracked.py", repo_root=tmp_repo) is True
    assert find_untracked(["pkg/tracked.py"], repo_root=tmp_repo) == []
    # Should NOT raise.
    assert_all_tracked(["pkg/tracked.py"], repo_root=tmp_repo)


def test_untracked_file_is_flagged(tmp_repo: Path) -> None:
    # The core guard: an untracked new file must be detected.
    assert is_tracked("pkg/untracked.py", repo_root=tmp_repo) is False
    missing = find_untracked(
        ["pkg/tracked.py", "pkg/untracked.py"], repo_root=tmp_repo
    )
    assert missing == ["pkg/untracked.py"], missing

    with pytest.raises(UntrackedFilesError) as ei:
        assert_all_tracked(["pkg/tracked.py", "pkg/untracked.py"], repo_root=tmp_repo)
    # Error names the dropped file so the operator can `git add` it.
    assert "pkg/untracked.py" in str(ei.value)


def test_commit_only_reproduces_the_drop(tmp_repo: Path) -> None:
    """End-to-end: `git commit --only` of the tracked file succeeds with a real
    diff yet leaves the untracked sibling uncommitted -- the exact foot-gun."""
    # Modify the tracked file so the --only commit has a non-empty diff (mirrors
    # the lesson: "commit reported a large diff, masking the omission").
    (tmp_repo / "pkg" / "tracked.py").write_text("# tracked v2\n", encoding="utf-8")

    cp = _git(tmp_repo, "commit", "--only", "pkg/tracked.py", "-q", "-m", "wave commit")
    assert cp.returncode == 0, cp.stderr  # commit "succeeds"

    # ...but the untracked sibling was silently NOT included.
    assert is_tracked("pkg/untracked.py", repo_root=tmp_repo) is False
    # The helper is what turns that silent drop into a loud failure.
    with pytest.raises(UntrackedFilesError):
        assert_all_tracked(
            ["pkg/tracked.py", "pkg/untracked.py"], repo_root=tmp_repo
        )


def test_helper_uses_index_not_disk_presence(tmp_repo: Path) -> None:
    """A file that EXISTS on disk but is not in the index must NOT count as tracked.

    Guards against a regression that swaps the `git ls-files --error-unmatch`
    check for an os.path.exists / glob check (on-disk presence != tracked).
    """
    assert (tmp_repo / "pkg" / "untracked.py").exists()  # present on disk
    assert is_tracked("pkg/untracked.py", repo_root=tmp_repo) is False  # but not tracked
