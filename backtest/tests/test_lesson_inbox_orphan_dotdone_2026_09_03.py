"""Guard for LESSON-INBOX-ORPHAN-DOTDONE (queue.md, LOW hygiene, closed 2026-09-03).

WHAT WAS FLAGGED
-----------------
queue.md (filed 2026-06-30 ~21:55 conductor) named one specific stray file:
``strategy/candidates/_lesson-inbox/2026-06-27-persistently-red-audit-masks-
new-orphans.md.DONE`` as UNTRACKED — git never recorded the rename from
``.md`` to ``.md.DONE`` when the lesson was consumed, leaving it invisible to
``git status`` porcelain while still cluttering the working tree.

VERIFIED 2026-09-03 (this fire)
--------------------------------
``git ls-files`` shows the named file IS now tracked (175/175 files under
``_lesson-inbox/`` tracked, 0 untracked) and the lesson it encodes is present
at ``markdown/doctrine/LESSONS-LEARNED.md`` L189 (cites this exact inbox
filename). The specific orphan the item named has already been resolved by a
prior commit — nothing left to `git add` or delete for that file.

THIS GUARD
----------
Rather than re-litigate the single already-fixed instance, pin the GENERAL
invariant the item exists to protect: no file under an author inbox is
UNTRACKED (the exact failure mode — a rename git never recorded). This is a
``git status`` read, not a content check — cheap, and catches the next
occurrence of the same foot-gun in any of the four author inboxes, not just
``_lesson-inbox``.

RAIL-4 / FAIL-OPEN
------------------
Read-only git porcelain status query. Skips (never fails) when git is
unavailable or this checkout is not a git repo — a CI sandbox without git
history must not report a false orphan.
"""
from __future__ import annotations

import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
INBOX_ROOT = ROOT / "strategy" / "candidates"
INBOXES = ["_lesson-inbox", "_skill-inbox", "_validator-inbox", "_chef-inbox"]


def _git_available() -> bool:
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=ROOT,
            capture_output=True,
            timeout=10,
            check=True,
        )
        return True
    except Exception:
        return False


def _untracked_files(rel_dir: str) -> list[str]:
    """Untracked (never-git-added) file paths under an inbox dir, per
    ``git status --porcelain=v1 --untracked-files=all``. Never raises —
    a git failure yields an empty list (fail-open, matches this test's
    skip-on-no-git posture)."""
    d = INBOX_ROOT / rel_dir
    if not d.is_dir():
        return []
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all", "--", str(d)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout
    except Exception:
        return []
    untracked = []
    for line in out.splitlines():
        if line.startswith("?? "):
            untracked.append(line[3:].strip())
    return untracked


@pytest.mark.skipif(not _git_available(), reason="not a git checkout")
def test_no_untracked_files_in_author_inboxes():
    """The exact 2026-06-30 foot-gun: a processed (.md.DONE) or fresh (.md)
    inbox item that git never recorded — invisible clutter that silently
    drifts porcelain and can hide a genuinely-unconsumed item behind a
    rename git doesn't know about."""
    offenders = {}
    for name in INBOXES:
        found = _untracked_files(name)
        if found:
            offenders[name] = found
    assert not offenders, (
        "Untracked files found in author inbox dirs (git never recorded them "
        "-- LESSON-INBOX-ORPHAN-DOTDONE foot-gun class). `git add` (if the "
        "lesson/skill/validator is genuinely encoded downstream) or delete "
        f"the orphan:\n  {offenders}"
    )


@pytest.mark.skipif(not _git_available(), reason="not a git checkout")
def test_2026_06_27_named_orphan_is_now_tracked():
    """The SPECIFIC file this queue item named. Pins that the historical
    instance stays fixed rather than silently regressing (e.g. a future
    tree-wide git op that untracks state files — see LESSONS-LEARNED C34)."""
    target = (
        INBOX_ROOT
        / "_lesson-inbox"
        / "2026-06-27-persistently-red-audit-masks-new-orphans.md.DONE"
    )
    if not target.is_file():
        pytest.skip("named file no longer present on disk (fully archived elsewhere)")
    out = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(target)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert out.returncode == 0, (
        f"{target.relative_to(ROOT)} is present on disk but NOT tracked by git "
        "-- the exact LESSON-INBOX-ORPHAN-DOTDONE regression."
    )
