"""Guard: STATUS.md's `## Known broken` section must stay in the PREAMBLE.

THE SCAR (2026-08-20, and again 2026-09-02). `status_retention.py::split_entries` splits
STATUS.md on `## [` headers and rebuilds the file as `preamble + newest N entries`. Only
the preamble -- the text before the FIRST `## [` -- survives forever. `## Known broken`
does not start with `## [`, so anywhere below that first entry it is absorbed into the body
of whatever dated entry precedes it, and rolls off to the monthly archive when that entry
ages out. From June 2026 onward that is exactly what happened: every producer targeting the
marker (`guard_runner_slow.py`, `gate_expiry_check.py`, `twin_gauntlet_conductor_hook.py`,
`prereg_hygiene.py`) silently discarded its RED for two months.

It was fixed once. It drifted back, and the mechanism is ordinary use: a session that
prepends a new dated entry pushes the section one entry further from the top. A fix that
any normal write undoes is not a fix -- so this pins the invariant in code, where a
regression fails loudly instead of quietly resuming the two-month discard.
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


def test_marker_is_above_the_first_dated_entry(text: str):
    """The whole point: it must land in split_entries' preamble, not inside an entry."""
    first_entry = text.find("\n## [")
    if text.startswith("## ["):
        first_entry = 0
    marker_at = text.find(MARKER)
    assert marker_at != -1
    assert first_entry == -1 or marker_at < first_entry, (
        "'## Known broken' sits BELOW the first '## [' entry, so status_retention.py "
        "treats it as that entry's body and will roll it into the monthly archive when "
        "the entry ages out -- silently killing every producer that targets it. Move the "
        "section (and its lines) back to the top of STATUS.md, above the newest entry."
    )


def test_split_entries_actually_puts_it_in_the_preamble(text: str):
    """Assert against the REAL splitter, not a re-implementation of its rule here -- if
    status_retention.py's parsing changes, this must fail rather than keep passing against
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

    preamble, _entries = sr.split_entries(text)
    assert MARKER in preamble, (
        "status_retention.split_entries does NOT see '## Known broken' in the preamble -- "
        "it will not survive the next roll"
    )


def test_preamble_carries_a_do_not_move_note(text: str):
    """A bare header invites the next session to prepend above it. The note is what makes
    the invariant survive contact with a human (or a Claude) editing the file by hand."""
    preamble = text.split("\n## [", 1)[0]
    assert "PREAMBLE" in preamble and "status_retention" in preamble, (
        "the '## Known broken' block lost its do-not-move note -- restore it, or the next "
        "session that prepends an entry will quietly undo this fix again"
    )
