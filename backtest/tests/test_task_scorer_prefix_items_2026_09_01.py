"""Guard for the 2026-09-01 PARSER SCOPE BUG (task W3-conductor-picker).

WHAT THIS GUARDS
----------------
``task_scorer.py::_active_lines()`` used to only start scanning at the
literal '## Active backlog' heading, so any genuine ``- [ ]`` item filed
ABOVE that heading (e.g. a fresh top-of-file block appended by a conductor
fire) was silently invisible to parse_queue()/--top/--all — identically to
the 2026-07-23 "stop at first heading after Active backlog" bug this same
function already fixed once, just on the OTHER side of the heading.

Confirmed live: DEAD-MANS-SWITCH-POSITION-FLATTENER and
PROD-SHADOW-ARM-DESIGNATION (queue.md lines ~66-67, both HIGH, both filed
2026-08-29, both go-live-gate-blocking) sat above '## Active backlog'
(queue.md line 75) and were never surfaced by ``--all`` through ~9
conductor fires.

Fix (2026-09-01): ``_active_lines()`` now scans the WHOLE FILE from line 0
to EOF, excluding only the provably-resolved '## Archived' / '## Completed'
sections (unchanged ``EXCLUDED_SECTION_RE`` behaviour) — the file's own
preamble (H1 title, blockquote prose) is naturally inert because it never
matches ``ITEM_RE``.

Run with:
    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_task_scorer_prefix_items_2026_09_01.py -q
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCORER = REPO / "setup" / "scripts" / "task_scorer.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("task_scorer_prefix", SCORER)
    assert spec and spec.loader, f"cannot load scorer at {SCORER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TS = _load_module()


# Synthetic queue.md shaped exactly like the real live incident: a HIGH item
# sits BEFORE '## Active backlog' with no heading of its own above it (just
# the H1 title + blockquote preamble), and a second, provably-resolved
# section also precedes the heading to prove exclusion still works no matter
# which side of 'Active backlog' it sits on.
PREFIX_QUEUE = """# OVERNIGHT TASK QUEUE — conductor work backlog

> Some preamble prose that is NOT an item.

---

- [ ] PREFIX-HIGH-ITEM (HIGH, filed 2026-08-29 Fable full review) :: A real HIGH item filed above the Active backlog heading, same shape as DEAD-MANS-SWITCH-POSITION-FLATTENER :: depends:none :: status:pending

## Archived 2026-06-19

- [ ] PREFIX-ARCHIVED-ITEM (HIGH) :: Provably-resolved noise that sits BEFORE Active backlog too :: depends:none :: status:pending

## Active backlog

- [ ] NORMAL-ITEM (MED, doc-index) :: A normal item that already lived under the heading :: depends:none :: status:pending
"""


def _by_id(tasks):
    return {t.id: t for t in tasks}


def test_high_item_above_active_backlog_heading_is_parsed():
    """The core regression: an item filed ABOVE '## Active backlog' must be
    visible to parse_queue(), not silently dropped."""
    ids = [t.id for t in TS.parse_queue(PREFIX_QUEUE)]
    assert "PREFIX-HIGH-ITEM" in ids
    assert "NORMAL-ITEM" in ids


def test_prefix_item_ranks_and_is_ready():
    by_id = _by_id(TS.parse_queue(PREFIX_QUEUE))
    task = by_id["PREFIX-HIGH-ITEM"]
    assert task.priority == "HIGH"
    assert task.ready is True


def test_archived_section_before_active_backlog_still_excluded():
    """Exclusion of provably-resolved sections must work regardless of which
    side of '## Active backlog' the section sits on."""
    ids = [t.id for t in TS.parse_queue(PREFIX_QUEUE)]
    assert "PREFIX-ARCHIVED-ITEM" not in ids


# Verbatim shape of the live incident, captured 2026-09-01 from queue.md lines ~60-80:
# two HIGH, gate-blocking items sitting ABOVE the '## Active backlog' heading with only the
# H1 title and blockquote preamble above them. This is a SNAPSHOT on purpose -- see
# test_the_incident_shape_still_parses.
INCIDENT_SNAPSHOT = """\
# OVERNIGHT TASK QUEUE — conductor work backlog

> Format: `- [ ] <id> (<priority>) :: <description> :: depends:<id|none> :: status:<state>`

- [ ] DEAD-MANS-SWITCH-POSITION-FLATTENER (HIGH) :: go_live_gate operational criterion 2 \
has no position flattener of last resort. :: depends:none :: status:pending
- [ ] PROD-SHADOW-ARM-DESIGNATION (HIGH) :: criterion 5 needs a designated prod-shadow arm \
frozen before the window opens. :: depends:none :: status:pending

## Active backlog

- [ ] SOME-OTHER-ITEM (LOW) :: below the heading, always parsed. :: depends:none :: status:pending
"""


def test_the_incident_shape_still_parses():
    """The 2026-09-01 parser-scope bug, pinned against a SNAPSHOT of the live file's shape.

    WHY NOT READ THE LIVE queue.md (changed 2026-09-02, queue item
    TASK-SCORER-LIVE-QUEUE-TEST-FIXTURE). This test used to read the real queue.md and
    normalise those two ids' checkbox and status so the assertion stayed about parser scope.
    That worked only while the ids were still IN the file. Both were completed and then
    archived to queue-archive-2026-09-02.md by an ordinary queue consolidation (commit
    b7f777b6) -- correct behaviour for a done item -- and the guard went RED for a reason
    that has nothing to do with the parser.

    The invariant was never about those two ids existing forever; it is about POSITION: an
    item above '## Active backlog' must be seen. A snapshot pins that permanently, and
    cannot be flipped by editing the backlog. Archiving a completed item must not turn a
    parser guard red -- a suite that is always RED is a suite nobody reads (2026-08-20).
    """
    by_id = _by_id(TS.parse_queue(INCIDENT_SNAPSHOT))
    for expected_id in ("DEAD-MANS-SWITCH-POSITION-FLATTENER", "PROD-SHADOW-ARM-DESIGNATION"):
        assert expected_id in by_id, (
            f"{expected_id} sits above '## Active backlog' and was not surfaced -- the "
            "2026-09-01 parser-scope bug is back"
        )
        assert by_id[expected_id].priority == "HIGH"
    assert "SOME-OTHER-ITEM" in by_id, "items below the heading stopped parsing"


def test_the_live_queue_still_parses_at_all():
    """A cheap liveness check on the real file, with no dependency on any particular id.

    It catches the class of breakage the removed assertion was really protecting against --
    a queue.md that the scorer silently reads as empty -- without going red every time an
    item is completed and archived.
    """
    queue_text = (REPO / "automation" / "overnight" / "queue.md").read_text(
        encoding="utf-8", errors="replace"
    )
    tasks = TS.parse_queue(queue_text)
    assert len(tasks) >= 5, (
        f"parse_queue() surfaced only {len(tasks)} item(s) from the live queue.md -- the "
        "conductor picks its work from this list, so a near-empty parse means it is idling "
        "with a full backlog"
    )
