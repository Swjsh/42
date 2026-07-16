"""Guard test for context_audit.movable_candidates() -- per-OP token attribution.

Bug (found 2026-07-16 context-leanness pass): the OP-block splitter only
recognized the plain numbered-list header ("32. **Title**"). OP-0 and OP-33
are written as "> ## ⛔ OP-N -- Title" blockquote callouts in CLAUDE.md, so
that header form was never a split boundary. Result: OP-33's ~745 tokens
bled into whatever bucket preceded it (OP-32), inflating OP-32's reported
size (1020 tok) far past its real size (~275 tok), while OP-33 never
appeared in the report at all. Visibility bug only -- nothing traded on it --
but a future context-trim decision reading the report could be misled into
shrinking/relocating the wrong block.

Fix: setup/scripts/context_audit.py movable_candidates() now also splits on
`^>\\s*##\\s*⛔\\s*OP-\\d+`, so each blockquote-form OP gets its own chunk.

This test is RED against the pre-fix splitter (regex re.split on
`^(?=\\d+\\.\\s+\\*\\*)` alone) and GREEN after the fix, run against the real
repo CLAUDE.md. Ranges are pinned approximately (not exact token counts) so
routine doctrine edits don't flip this RED.

Run: pytest -v setup/scripts/test_context_audit.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

SETUP_SCRIPTS = Path(__file__).resolve().parent
REPO = SETUP_SCRIPTS.parent.parent
if str(SETUP_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SETUP_SCRIPTS))

import context_audit as ca  # noqa: E402

CLAUDE_MD = REPO / "CLAUDE.md"


def _pre_fix_movable_candidates(txt: str) -> list[tuple[int, str]]:
    """Reproduction of the ORIGINAL (buggy) splitter -- numbered form only.

    Kept inline (not imported) so this test still proves the regression
    even after the fix lands in context_audit.py; it is the pre-fix
    baseline, not a call into current source.
    """
    cands: list[tuple[int, str]] = []
    op = re.search(r'(?ms)^## Operating principles.*?(?=^## )', txt)
    if op:
        for b in re.split(r'(?m)^(?=\d+\.\s+\*\*)', op.group(0)):
            mm = re.match(r'(\d+)\.\s+\*\*(.+?)\*\*', b)
            if mm and ca.TOK(b) >= ca.MOVABLE_MIN_TOKENS:
                cands.append((ca.TOK(b), f"OP-{mm.group(1)}: {mm.group(2)[:42]}"))
    return sorted(cands, reverse=True)


@pytest.fixture(scope="module")
def claude_md_text() -> str:
    if not CLAUDE_MD.exists():
        pytest.skip(f"CLAUDE.md not found at {CLAUDE_MD}")
    return ca.read(str(CLAUDE_MD))


def test_op0_and_op33_are_blockquote_form_in_live_claude_md(claude_md_text: str) -> None:
    """Sanity check the premise: OP-0 and OP-33 use the blockquote callout header.

    If a future doctrine edit converts these back to plain numbered list
    items, this test documents that assumption is now false rather than
    silently no-op'ing the rest of the guard.
    """
    assert re.search(r'(?m)^>\s*##\s*⛔\s*OP-0\b', claude_md_text), (
        "OP-0 no longer uses the '> ## ⛔ OP-0' blockquote header -- "
        "re-check whether the blockquote split branch is still needed."
    )
    assert re.search(r'(?m)^>\s*##\s*⛔\s*OP-33\b', claude_md_text), (
        "OP-33 no longer uses the '> ## ⛔ OP-33' blockquote header -- "
        "re-check whether the blockquote split branch is still needed."
    )


def test_pre_fix_splitter_mis_buckets_op33_onto_op32(claude_md_text: str) -> None:
    """RED-proof: demonstrates the bug existed in the old numbered-only splitter.

    Old behavior: OP-33's blockquote content has no numbered-list header, so
    re.split's boundary regex never fires on it -- it stays glued onto the
    end of the OP-32 chunk. OP-32's bucket should show as suspiciously large
    (>= 900 tok, well above OP-32's real ~275 tok) and OP-33 should not
    appear as its own bucket at all.
    """
    cands = _pre_fix_movable_candidates(claude_md_text)
    labels = {label.split(":")[0]: tok for tok, label in cands}

    assert "OP-33" not in labels, (
        "Pre-fix splitter unexpectedly produced a standalone OP-33 bucket -- "
        "the bug this test pins may already be gone from the reproduction helper."
    )
    assert "OP-32" in labels, "Pre-fix splitter should still report an OP-32 bucket."
    # The buggy OP-32 bucket = real OP-32 (~275 tok) + all of OP-33 (~745 tok).
    assert labels["OP-32"] >= 900, (
        f"Expected the pre-fix OP-32 bucket to be inflated by OP-33's tokens "
        f"(>= 900), got {labels['OP-32']} -- bug reproduction no longer holds."
    )


def test_fixed_splitter_separates_op32_and_op33(claude_md_text: str) -> None:
    """GREEN-proof: current context_audit.movable_candidates() separates them.

    Pinned as approximate RANGES (not exact token counts) so a routine
    doctrine edit that adds/removes a sentence inside OP-32 or OP-33 doesn't
    flip this test RED. The load-bearing assertions are:
      1. OP-33 exists as its own bucket (nonzero).
      2. OP-32's bucket drops back down near its real size, clearly below
         the old inflated (~1020 tok) reading.
    """
    cands = ca.movable_candidates(claude_md_text)
    labels = {label.split(":")[0]: tok for tok, label in cands}

    assert "OP-33" in labels, (
        "OP-33 should now appear as its own movable-candidate bucket "
        "(blockquote header form was not recognized as a split boundary)."
    )
    assert labels["OP-33"] > 0
    # Real measured size ~745 tok (2026-07-16) -- generous band for drift.
    assert 400 <= labels["OP-33"] <= 1400, (
        f"OP-33 bucket {labels['OP-33']} tok is outside the expected band -- "
        "re-verify against a fresh `context_audit.py report` run."
    )

    if "OP-32" in labels:
        # Real measured size ~275 tok (2026-07-16) -- must be well under the
        # old mis-bucketed reading (~1020 tok), and under MOVABLE_MIN_TOKENS
        # is also an acceptable (even stronger) outcome -- see below.
        assert labels["OP-32"] < 700, (
            f"OP-32 bucket {labels['OP-32']} tok still looks inflated by "
            "OP-33's content -- the blockquote split boundary may not be firing."
        )
    # else: OP-32 dropped below MOVABLE_MIN_TOKENS entirely once correctly
    # isolated from OP-33 -- that is the expected, fixed outcome (its real
    # size ~275 tok is below the 500-tok candidate threshold).


def test_op32_and_op33_buckets_do_not_overlap_in_content(claude_md_text: str) -> None:
    """The two buckets must sum close to their pre-fix combined total,
    proving tokens moved from one bucket to the other rather than vanishing
    or double-counting."""
    cands = ca.movable_candidates(claude_md_text)
    labels = {label.split(":")[0]: tok for tok, label in cands}
    op33 = labels.get("OP-33", 0)
    op32 = labels.get("OP-32", 0)
    pre_fix = _pre_fix_movable_candidates(claude_md_text)
    pre_labels = {label.split(":")[0]: tok for tok, label in pre_fix}
    combined_old = pre_labels.get("OP-32", 0)
    # OP-32 in the fixed splitter may be 0 if it fell under threshold; recover
    # its real size directly for the reconciliation check.
    if op32 == 0:
        op = re.search(r'(?ms)^## Operating principles.*?(?=^## )', claude_md_text)
        boundary = re.compile(r'(?m)^(?=\d+\.\s+\*\*|>\s*##\s*⛔\s*OP-\d+)')
        for b in boundary.split(op.group(0)):
            mm = re.match(r'(\d+)\.\s+\*\*(.+?)\*\*', b)
            if mm and mm.group(1) == "32":
                op32 = ca.TOK(b)
                break
    assert abs((op32 + op33) - combined_old) <= 5, (
        f"op32({op32}) + op33({op33}) should reconcile with the old combined "
        f"bucket ({combined_old}) within a few tokens of split-boundary "
        "whitespace slop."
    )


def test_context_audit_verify_still_passes() -> None:
    """The --verify integrity gate (used after every doctrine edit) must
    still be all-green after this fix -- this change only touches the
    report-mode candidate labeling, never rule semantics."""
    if not CLAUDE_MD.exists():
        pytest.skip(f"CLAUDE.md not found at {CLAUDE_MD}")
    txt = ca.read(str(CLAUDE_MD))
    ck, missing = ca.integrity(txt, str(REPO))
    failed = [name for name, ok in ck if not ok]
    assert not failed, f"integrity check(s) failed: {failed}; missing pointers: {missing}"
