"""Guard: STATUS.md's `## Known broken` section must stay in the PREAMBLE.

THE SCAR (2026-08-20, and again 2026-09-02). `status_retention.py::split_entries` splits
STATUS.md on `## [` headers and rebuilds the file as `preamble + newest N entries`. Only
the preamble -- the text before the FIRST `## [` -- survives forever. `## Known broken`
does not start with `## [`, so anywhere below that first entry it is absorbed into the body
of whatever dated entry precedes it, and rolls off to the monthly archive when that entry
ages out. From June 2026 onward that is exactly what happened: every producer targeting the
marker (`guard_runner_slow.py`, `gate_expiry_check.py`, `twin_gauntlet_conductor_hook.py`,
`prereg_hygiene.py`) silently discarded its RED for two months.

It was fixed once by MOVING the section to the top. That drifted back within a day, and the
mechanism is ordinary use: a session prepends a dated entry at line 1 and the section is one
entry further down. A fix that any normal write undoes is not a fix.

So the invariant moved from POSITION to NAME (2026-09-02): `status_retention.PINNED_SECTIONS`
hoists the section into the preamble wherever it physically sits, and these tests assert the
thing that actually matters -- that it SURVIVES a real roll -- rather than where it happens
to live in the file. The positional test that used to be here is gone for that reason, not
because it was inconvenient; it was measuring the proxy, and the proxy had stopped tracking.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STATUS = REPO / "automation" / "overnight" / "STATUS.md"
MARKER = "## Known broken"


@pytest.fixture(scope="module")
def text() -> str:
    if not STATUS.exists():
        pytest.skip("STATUS.md absent")
    return STATUS.read_text(encoding="utf-8")


def test_marker_exists(text: str):
    """Producers that cannot find the marker have nowhere to report a RED."""
    assert MARKER in text, (
        "STATUS.md has no '## Known broken' section -- every guard that reports a RED "
        "through it is silently discarding findings right now"
    )


FINDING = "GUARD-X RED: a finding that must not be archived"


def _buried_fixture() -> str:
    """STATUS.md shaped like the real one, with the marker inside an entry that MUST roll.

    The first cut of this fixture put the marker in the NEWEST entry, which `min_keep=1`
    preserves regardless -- so it passed with pinning disabled and proved nothing. The
    marker has to sit in the tail that the roll actually discards.
    """
    newest = "".join(
        f"## [2026-09-{d:02d}T09:00 ET] recent entry\n- filler {'x' * 1800}\n\n"
        for d in range(2, 0, -1))
    oldest = (
        "## [2026-08-01T09:00 ET] oldest entry -- this one rolls off\n"
        "- filler\n\n"
        f"{MARKER}\n"
        f"- {FINDING}\n\n"
    )
    return newest + oldest


def test_the_marker_survives_a_real_roll_wherever_it_sits(text: str):
    """THE INVARIANT, replacing a positional assertion that this file's own history
    disproved (2026-09-02).

    The original test here demanded the marker sit physically above the first `## [` entry.
    It went RED within a day of being written -- not because anything broke, but because a
    producer prepended a dated entry at line 1, which is ordinary, correct behaviour. A
    guard that ordinary use turns RED is a guard that gets ignored, which is precisely how
    the `## Known broken` channel died the first time.

    Position was only ever a proxy for the thing that matters: does the section SURVIVE a
    retention roll? `split_entries` now hoists PINNED_SECTIONS by name, so it does -- from
    anywhere. This asserts that directly, against the real roll, with the marker buried deep
    enough that a positional fix could not save it.
    """
    sr = _retention()
    plan = sr.plan_consolidation(_buried_fixture(), max_keep_bytes=2000, min_keep=1)
    assert plan["n_rolled"] > 0, "fixture did not actually force a roll"
    assert any(MARKER in e for e in plan["rolled_entries"]) is False, (
        "the marker went out with the rolled tail"
    )
    assert MARKER in plan["kept_text"], (
        "'## Known broken' was rolled into the monthly archive -- every producer that "
        "targets it (guard_runner_slow, gate_expiry_check, twin_gauntlet_conductor_hook, "
        "prereg_hygiene) is silently discarding its RED again, which is the exact "
        "two-month outage this file exists to prevent"
    )
    assert FINDING in plan["kept_text"], (
        "the header survived but its CONTENT did not -- the section was truncated, so the "
        "channel is alive and empty, which reads identically to 'nothing is broken'"
    )


def test_the_hoisted_section_is_not_left_behind_as_a_duplicate():
    """Hoisting must MOVE the section, not copy it.

    If the source entry keeps its copy, STATUS.md carries two `## Known broken` blocks that
    drift apart, and a producer appending to "the" section has a 50/50 chance of writing to
    the one that is about to be archived. Silent, and indistinguishable from working.
    """
    sr = _retention()
    kept = sr.plan_consolidation(_buried_fixture(), max_keep_bytes=2000, min_keep=1)["kept_text"]
    assert kept.count(MARKER) == 1, f"marker appears {kept.count(MARKER)}x after the roll"
    assert kept.count(FINDING) == 1


def test_a_second_older_copy_is_left_alone_for_the_archive():
    """Only the NEWEST occurrence is pinned. Historical copies inside old entries are part
    of that entry's record and must roll with it -- otherwise every archived month's copy
    accumulates in the live preamble forever."""
    sr = _retention()
    doubled = _buried_fixture() + (
        "## [2026-07-01T09:00 ET] ancient entry\n"
        f"{MARKER}\n- OLD-FINDING RED: history, belongs in the archive\n\n")
    plan = sr.plan_consolidation(doubled, max_keep_bytes=2000, min_keep=1)
    assert FINDING in plan["kept_text"]
    assert "OLD-FINDING RED" not in plan["kept_text"], (
        "an older historical copy of the section was hoisted into the live preamble too"
    )


def _retention():
    """Load the REAL splitter, never a re-implementation of its rule here -- if
    status_retention.py's parsing changes, these must fail rather than keep passing against
    a stale copy of its logic."""
    import importlib.util
    import sys

    scripts = REPO / "setup" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location(
        "status_retention_g", scripts / "status_retention.py")
    assert spec and spec.loader
    sr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sr)
    return sr


def test_split_entries_actually_puts_it_in_the_preamble(text: str):
    """The live file, through the live splitter."""
    preamble, _entries = _retention().split_entries(text)
    assert MARKER in preamble, (
        "status_retention.split_entries does NOT see '## Known broken' in the preamble -- "
        "it will not survive the next roll"
    )


def test_preamble_carries_a_do_not_move_note(text: str):
    """A bare header invites the next session to "tidy" the section away. The note is what
    makes the invariant survive contact with a human (or a Claude) editing the file by hand.

    Reads the preamble from the real splitter. The earlier `text.split("\\n## [", 1)[0]`
    silently returned the first 66 lines whenever the file STARTS with an entry (no leading
    newline to match), so it was passing on a preamble that was in fact empty.
    """
    preamble, _ = _retention().split_entries(text)
    assert "PREAMBLE" in preamble and "status_retention" in preamble, (
        "the '## Known broken' block lost its do-not-move note -- restore it, or the next "
        "session that prepends an entry will quietly undo this fix again"
    )


def test_prose_quoting_the_marker_does_not_count_as_the_section():
    """The section's own do-not-move note QUOTES `## Known broken` in a blockquote line.

    A substring test (`"## Known broken" in preamble`) reads that prose as "the section is
    already here" and skips the hoist, so the real section stays inside a dated entry and
    rolls off -- the exact outage, reintroduced by the exact string-vs-structure mistake
    logged in _lesson-inbox/2026-09-02-string-search-cannot-answer-code-questions.md.
    """
    sr = _retention()
    text = (
        "> **This section is the PREAMBLE.** Do not move `## Known broken` below an entry.\n\n"
        "## [2026-09-02T09:00 ET] newest\n- filler\n\n"
        f"{MARKER}\n- {FINDING}\n\n"
        f"## [2026-08-01T09:00 ET] old\n- filler {'x' * 3000}\n\n"
    )
    preamble, _ = sr.split_entries(text)
    assert FINDING in preamble, (
        "the hoist was skipped because prose quoting the marker was mistaken for the "
        "section itself -- the real block is still inside a dated entry and will roll off"
    )
