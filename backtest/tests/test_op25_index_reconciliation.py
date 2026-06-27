"""Graduated guard (STAGE 4.5 learn-loop): reconcile the lesson set in
markdown/doctrine/LESSONS-LEARNED.md against the CLAUDE.md OP-25 Lessons index.

WHY THIS EXISTS (the re-violated foot-gun this encodes)
-------------------------------------------------------
Lessons authored directly by the conductor (Agent tool / `lesson-author`
unavailable in a given fire) never get their CLAUDE.md OP-25 index fold, because
only `lesson-author` folds and it only folds lessons IT authors. Across many
consecutive fires this silently accumulated SIX rail-4-blocked
`L###-CLAUDE-FOLD` follow-ups (L169/L170/L173/L174/L177/L178) -- and a
reconciliation pass surfaced TWELVE additional older un-indexed lessons
(L3/L13/L16/L24/L25/L29/L31/L43/L56/L126/L137/L146) that NO guard had ever
flagged. Prose that gets re-violated is a missing guardrail (OP-25): graduate it
to a code assertion at the boundary.

WHAT IT GUARDS
--------------
1. RATCHET: the set of lessons defined in LESSONS-LEARNED.md but absent from the
   CLAUDE.md OP-25 index must NOT grow beyond a pinned baseline. A newly-authored
   lesson that is not folded into the index makes the set grow -> this test fails
   -> the next fire must either fold it (preferred) or consciously widen the
   baseline (visible, capped debt). As real folds land, TRIM the baseline so the
   ratchet tightens toward zero.
2. NO PHANTOMS: every L## referenced in the OP-25 index must actually be defined
   in LESSONS-LEARNED.md (catches typos / dangling references).

RAIL-4 / FAIL-OPEN
------------------
This test only READS CLAUDE.md + LESSONS-LEARNED.md -- it never edits the
doctrine surface (conductor cannot, rail 4). It is a dev/CI test, so it can never
block J's interactive session (OP-25 fail-open): if either file is missing it
skips rather than erroring.
"""
import re
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CLAUDE_MD = ROOT / "CLAUDE.md"
LESSONS_MD = ROOT / "markdown" / "doctrine" / "LESSONS-LEARNED.md"

# Pinned 2026-06-21. Lessons defined in LESSONS-LEARNED.md but not yet folded
# into the CLAUDE.md OP-25 index. The 6 recent rail-4-blocked folds + 12 older
# pre-existing gaps the new reconciliation surfaced. TRIM as folds land; the
# ratchet asserts this set only ever SHRINKS.
KNOWN_UNINDEXED_BASELINE = frozenset(
    {3, 13, 16, 24, 25, 29, 31, 43, 56, 126, 137, 146, 188}
    # 169,170,173,174,177,178,179,181,182,183,184,185,186,187 folded 2026-06-24 batch
    # 188 added 2026-06-26 conductor (L188 dir-controlled null) -- CLAUDE.md C3 fold rail-4-blocked, proposal cd-2026-06-26-001
)


# --------------------------------------------------------------------------- #
# Pure helpers (the detector -- tested on synthetic input below)
# --------------------------------------------------------------------------- #
def parse_indexed_lessons(claude_text: str) -> set:
    """L## numbers referenced in the OP-25 index C-rows.

    Rows look like `| C7 | <theme> | L19,26,28,...,164 |` -- only the first
    number in each comma list carries an `L` prefix; the rest are bare. The
    L-list is the LAST pipe-delimited cell of the row.
    """
    indexed = set()
    for line in claude_text.splitlines():
        if not re.match(r"\s*\| C\d+ \|", line):
            continue
        cell = line.rstrip().rstrip("|").rsplit("|", 1)[-1]
        for m in re.finditer(r"L0*(\d+)((?:\s*,\s*0*\d+)*)", cell):
            indexed.add(int(m.group(1)))
            for n in re.findall(r"(\d+)", m.group(2)):
                indexed.add(int(n))
    return indexed


def parse_defined_lessons(lessons_text: str) -> set:
    """L## numbers that have a real definition heading in LESSONS-LEARNED.md."""
    defined = set()
    for line in lessons_text.splitlines():
        m = re.match(r"\s*#{1,4}\s*L0*(\d+)\b", line)
        if m:
            defined.add(int(m.group(1)))
    for m in re.finditer(r"(?m)^\s*[-*]?\s*\*\*L0*(\d+)\b", lessons_text):
        defined.add(int(m.group(1)))
    return defined


def find_unindexed_lessons(claude_text: str, lessons_text: str) -> set:
    """Lessons DEFINED but absent from the OP-25 index (the fold debt)."""
    return parse_defined_lessons(lessons_text) - parse_indexed_lessons(claude_text)


def find_phantom_index_refs(claude_text: str, lessons_text: str) -> set:
    """L## referenced in the index but not actually defined (typos/dangles)."""
    return parse_indexed_lessons(claude_text) - parse_defined_lessons(lessons_text)


# --------------------------------------------------------------------------- #
# Behavioral tests on synthetic input -- prove the detector works both ways
# --------------------------------------------------------------------------- #
SYNTH_CLAUDE = """
    | C1 | theme one | L01,02,10 |
    | C2 | theme two | L05,07 |
"""
SYNTH_LESSONS = """
## L01: first
## L02: second
## L05 -- 2026: fifth
## L07 — seventh
## L10: tenth
"""


def test_detector_passes_when_all_lessons_indexed():
    assert find_unindexed_lessons(SYNTH_CLAUDE, SYNTH_LESSONS) == set()
    assert find_phantom_index_refs(SYNTH_CLAUDE, SYNTH_LESSONS) == set()


def test_detector_flags_a_newly_authored_unfolded_lesson():
    # A new L11 lesson appears with no matching index fold -> must be flagged.
    lessons = SYNTH_LESSONS + "\n## L11: newly authored, not folded\n"
    assert find_unindexed_lessons(SYNTH_CLAUDE, lessons) == {11}


def test_detector_flags_a_phantom_index_reference():
    # Index cites L99 that no lesson defines -> phantom.
    claude = SYNTH_CLAUDE + "    | C3 | bad | L99 |\n"
    assert find_phantom_index_refs(claude, SYNTH_LESSONS) == {99}


def test_detector_parses_bare_comma_continuation():
    # The exact format foot-gun: only the first number carries the L prefix.
    indexed = parse_indexed_lessons("    | C9 | x | L21,42,49,60 |")
    assert indexed == {21, 42, 49, 60}


# --------------------------------------------------------------------------- #
# Live ratchet against the real files
# --------------------------------------------------------------------------- #
def _read_live():
    if not CLAUDE_MD.exists() or not LESSONS_MD.exists():
        pytest.skip("CLAUDE.md or LESSONS-LEARNED.md absent -- fail open")
    return (
        CLAUDE_MD.read_text(encoding="utf-8"),
        LESSONS_MD.read_text(encoding="utf-8"),
    )


def test_no_new_unindexed_lessons_beyond_baseline():
    claude_text, lessons_text = _read_live()
    current = find_unindexed_lessons(claude_text, lessons_text)
    new_gaps = current - KNOWN_UNINDEXED_BASELINE
    assert not new_gaps, (
        f"New lesson(s) {sorted(new_gaps)} are defined in LESSONS-LEARNED.md but "
        "not folded into the CLAUDE.md OP-25 index. Fold them (lesson-author / "
        "interactive edit) or, if intentional, add to KNOWN_UNINDEXED_BASELINE."
    )


def test_baseline_only_shrinks():
    # If a baseline entry has since been folded, trim it -- keeps the ratchet honest.
    claude_text, lessons_text = _read_live()
    current = find_unindexed_lessons(claude_text, lessons_text)
    stale = KNOWN_UNINDEXED_BASELINE - current
    assert not stale, (
        f"Baseline lists {sorted(stale)} as unindexed, but they are now in the "
        "index. Remove them from KNOWN_UNINDEXED_BASELINE so the ratchet tightens."
    )


def test_no_phantom_index_references_live():
    claude_text, lessons_text = _read_live()
    phantoms = find_phantom_index_refs(claude_text, lessons_text)
    assert not phantoms, (
        f"CLAUDE.md OP-25 index references L## not defined in LESSONS-LEARNED.md: "
        f"{sorted(phantoms)} (typo or dangling reference)."
    )
