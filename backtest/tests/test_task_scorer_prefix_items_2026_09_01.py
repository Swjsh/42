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


def test_live_queue_surfaces_the_two_gate_blocking_items():
    """End-to-end guard against the actual live incident: read the real
    queue.md and confirm both previously-invisible HIGH items now parse."""
    queue_text = (REPO / "automation" / "overnight" / "queue.md").read_text(
        encoding="utf-8", errors="replace"
    )
    # The two items sit ABOVE '## Active backlog' in the live file -- that placement is the
    # incident this test guards. Their CHECKBOX state is not: both were legitimately closed
    # (- [x] / status:done) once the fixes shipped 2026-09-01, and parse_queue() excludes
    # completed items by design. Normalise the checkbox + status for these two ids only, so
    # the assertion stays about PARSER SCOPE (position in the file), not about queue status.
    for expected_id in ("DEAD-MANS-SWITCH-POSITION-FLATTENER", "PROD-SHADOW-ARM-DESIGNATION"):
        assert expected_id in queue_text, f"{expected_id} no longer present in queue.md at all"
        queue_text = queue_text.replace(f"- [x] {expected_id}", f"- [ ] {expected_id}")
    lines = []
    for ln in queue_text.splitlines():
        if any(f"] {i}" in ln for i in ("DEAD-MANS-SWITCH-POSITION-FLATTENER", "PROD-SHADOW-ARM-DESIGNATION")):
            ln = ln.replace("status:done", "status:pending")
        lines.append(ln)
    by_id = _by_id(TS.parse_queue("\n".join(lines)))
    for expected_id in ("DEAD-MANS-SWITCH-POSITION-FLATTENER", "PROD-SHADOW-ARM-DESIGNATION"):
        assert expected_id in by_id, f"{expected_id} missing from parse_queue(queue.md)"
        assert by_id[expected_id].priority == "HIGH"
