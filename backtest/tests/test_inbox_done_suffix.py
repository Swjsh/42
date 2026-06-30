"""Graduated guard (STAGE 4.5 learn-loop): author-inbox DONE-markers must NOT
end in `.md`, or the author's `*.md` glob re-consumes them.

WHY THIS EXISTS (the re-violated foot-gun this encodes)
-------------------------------------------------------
Every inbox author (`lesson-author`, `skill-author`, `validator-author`) picks
its next item with a literal glob:

    ls -1 strategy/candidates/_<name>-inbox/*.md 2>/dev/null | grep -v README | head -1

The skip convention is "rename a processed item so it NO LONGER ends in `.md`"
-- the canonical suffix is `<slug>.md.DONE`. But on 2026-06-26 (commit 667217a)
four already-encoded lesson items were renamed to `<slug>.DONE.md` instead.
`.DONE.md` STILL ENDS IN `.md`, so the `*.md` glob would re-pick one and the
lesson-author would append a DUPLICATE L## entry to LESSONS-LEARNED.md. All four
were genuinely already encoded (L173 / L174 / L186 / L188) -- the duplicate would
have been pure doctrine corruption. STATUS L86 named the exact mechanism
("still ends in `.md` -> a `*.md` author glob could re-consume them") yet it
recurred -> a re-violated prose rule is a missing guardrail (OP-25): graduate it
to a code assertion at the boundary.

WHAT IT GUARDS
--------------
No file inside an author inbox may be a DONE/terminal marker that still ends in
`.md`. A processed item must end in `.md.DONE` (or another non-`.md` terminal
suffix) so the `*.md` glob can never re-consume it. Active, un-processed items
(plain `<slug>.md`) are allowed and untouched.

RAIL-4 / FAIL-OPEN
------------------
Pure filesystem read of the inbox directories -- touches NO params / doctrine /
orders / heartbeat / filters / CLAUDE. A dev/CI test; it can never block J.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
INBOX_ROOT = ROOT / "strategy" / "candidates"
INBOXES = ["_lesson-inbox", "_skill-inbox", "_validator-inbox", "_chef-inbox"]

# A processed/terminal marker that AUTHORS must skip. If a filename contains one
# of these tokens but still ENDS IN `.md`, the `*.md` glob re-consumes it.
DONE_TOKENS = ("DONE", "SUPERSEDED", "STALE", "DEFERRED", "ARCHIVED")
_DONE_BEFORE_MD = re.compile(
    r"\.(?:" + "|".join(DONE_TOKENS) + r")\.md$", re.IGNORECASE
)


def _inbox_files():
    for name in INBOXES:
        d = INBOX_ROOT / name
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.is_file():
                yield f


def test_no_done_marker_still_ends_in_md():
    """The exact 2026-06-26 foot-gun: a `*.DONE.md` (or SUPERSEDED/STALE/etc.)
    file in any author inbox is re-consumable by the author's `*.md` glob."""
    offenders = [
        str(f.relative_to(ROOT)).replace("\\", "/")
        for f in _inbox_files()
        if _DONE_BEFORE_MD.search(f.name)
    ]
    assert not offenders, (
        "Author-inbox DONE-markers still ending in `.md` -- the `*.md` glob will "
        "re-consume these (duplicate L##/skill/validator). Rename to `.md.DONE`:\n  "
        + "\n  ".join(offenders)
    )


def test_processed_items_use_md_dot_done_suffix():
    """Canonical skip suffix is `.md.DONE`. Confirm the four reconciled lessons
    are present under that suffix (anchors the convention, catches a future
    blanket rename back to `.DONE.md`)."""
    lesson_inbox = INBOX_ROOT / "_lesson-inbox"
    if not lesson_inbox.is_dir():
        return  # no inbox in this checkout -> nothing to assert (fail-open)
    done = {f.name for f in lesson_inbox.iterdir() if f.name.endswith(".md.DONE")}
    # none of them may simultaneously exist as the re-consumable `.DONE.md` form
    bad = {f.name for f in lesson_inbox.iterdir() if _DONE_BEFORE_MD.search(f.name)}
    assert not bad, f"reconsumable DONE-markers present: {sorted(bad)}"
    # the canonical form is what we expect processed items to use
    assert all(n.endswith(".md.DONE") for n in done)


def test_bite_done_md_pattern_actually_matches():
    """Non-vacuous bite: the regex MUST flag `.DONE.md` and MUST NOT flag the
    canonical `.md.DONE` or an active `.md`. If this fails the guard is asleep."""
    assert _DONE_BEFORE_MD.search("x.DONE.md")
    assert _DONE_BEFORE_MD.search("x.SUPERSEDED.md")
    assert _DONE_BEFORE_MD.search("X.stale.MD")  # case-insensitive
    assert not _DONE_BEFORE_MD.search("x.md.DONE")  # canonical skip suffix
    assert not _DONE_BEFORE_MD.search("2026-06-30-real-active-item.md")  # active
    assert not _DONE_BEFORE_MD.search("README.md")
