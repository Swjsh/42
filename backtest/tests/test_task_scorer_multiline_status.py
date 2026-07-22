"""Guard: task_scorer.py must read status from an item's WHOLE block, not
just its checkbox line — RED-proofs a real, demonstrated 2026-07-22 bug.

ROOT CAUSE (verified live against automation/overnight/queue.md before this
fix): queue.md items are append-only (OP-22) — many real items are long
multi-paragraph entries whose checkbox line ends bare at ``::`` (nothing
after it) and whose closing ``status:CLOSED-...``/``status:done...`` verdict
is appended several PHYSICAL lines below, inside later continuation prose.
``task_scorer``'s original parser only ever read ``rest`` off the checkbox
line via a single-line regex match, so a closed item's status silently read
``""`` — which the ready-rule treats as READY (see ``test_no_status_item_is_
ready`` in test_task_scorer.py, an intentionally-preserved behavior for
GENUINELY status-less items). Confirmed against the real queue: this exact
bug was why ``PULLBACK-HOLD-BULL-TRIGGER`` (status:CLOSED-LANE-B-NO-CELL-
SHIPS, appended ~30 lines below its checkbox) still ranked ``ready:true`` at
the top of ``task_scorer.py --top`` days after closure — the conductor's own
STATUS.md history shows multiple fires re-discovering "task_scorer surfaced
a since-closed item again" without ever finding the mechanism.

This file pins THREE things the fix must get right simultaneously:
  1. A closed multi-line item (status several lines below the checkbox) is
     correctly excluded from ready.
  2. A genuinely-open multi-line item (status:pending on the checkbox line,
     with unrelated ``::``-free blockquote prose appended below) is NOT
     corrupted into a garbage non-matching status string — it must still
     read cleanly as "pending" and stay ready (the naive "split whole block
     by ::" fix bled trailing prose into the value; this guards the
     per-line-bounded fix instead).
  3. ``_open_item_ids`` (the dependency-resolution reader) applies the same
     whole-block fix, so a dependent item naming a closed-but-unchecked
     item as its ``depends:`` is correctly unblocked.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCORER = REPO / "setup" / "scripts" / "task_scorer.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("task_scorer_mlstatus", SCORER)
    assert spec and spec.loader, f"cannot load scorer at {SCORER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TS = _load_module()


# Mirrors the REAL shape found in queue.md: checkbox line ends bare at "::",
# the actual status is appended many lines later inside plain prose.
MULTILINE_QUEUE = """## Active backlog

- [ ] CLOSED-MULTILINE (HIGH, engine-benefit) ::
  Some long paragraph of continuation prose that spans several physical
  lines, exactly like the real queue.md append-only convention, with no
  "::" delimiters at all until the closing verdict shows up much later.
  Here is the closing verdict, several lines down: depends:none :: status:CLOSED-LANE-B-NO-CELL-SHIPS
  (more trailing prose after the status field, also part of the same item)

- [ ] OPEN-MULTILINE (HIGH, engine-benefit) :: A short item :: depends:none :: status:pending

> **Unrelated blockquote commentary appended below OPEN-MULTILINE, with**
> **no "::" delimiter anywhere in it at all — must not corrupt the status**
> **value read off the checkbox line above.**

- [ ] DEPENDS-ON-CLOSED (MED) :: Should be ready once its dep resolves :: depends:CLOSED-MULTILINE :: status:pending
"""


def test_multiline_closed_status_excludes_from_ready():
    ranked = TS.rank(MULTILINE_QUEUE, include_blocked=False)
    ids = [t.id for t in ranked]
    assert "CLOSED-MULTILINE" not in ids


def test_multiline_closed_status_visible_under_all_as_not_ready():
    ranked = TS.rank(MULTILINE_QUEUE, include_blocked=True)
    by_id = {t.id: t for t in ranked}
    assert "CLOSED-MULTILINE" in by_id
    assert by_id["CLOSED-MULTILINE"].ready is False


def test_multiline_open_status_not_corrupted_by_trailing_blockquote():
    # OPEN-MULTILINE's status is a clean "pending" on its own checkbox line;
    # unrelated ::-free blockquote prose appended below it must NOT bleed
    # into the extracted value (the naive whole-block-split fix broke this).
    ranked = TS.rank(MULTILINE_QUEUE, include_blocked=False)
    ids = [t.id for t in ranked]
    assert "OPEN-MULTILINE" in ids


def test_dependent_on_closed_multiline_item_is_unblocked():
    # DEPENDS-ON-CLOSED names CLOSED-MULTILINE as its dependency. Since
    # CLOSED-MULTILINE's status:CLOSED-... makes it non-OPEN (per
    # OPEN_DEP_STATUSES), the dependent must be considered ready — this
    # exercises the same whole-block fix applied inside _open_item_ids.
    ranked = TS.rank(MULTILINE_QUEUE, include_blocked=False)
    ids = [t.id for t in ranked]
    assert "DEPENDS-ON-CLOSED" in ids


def test_extract_field_last_bounds_value_to_its_own_line():
    block = (
        "- [ ] X (HIGH) ::\n"
        "  status:pending\n"
        "\n"
        "  > some later blockquote paragraph with no further :: in it at all\n"
        "  > spanning multiple lines of unrelated prose\n"
    )
    assert TS._extract_field_last(block, "status") == "pending"


def test_extract_field_last_takes_the_last_occurrence():
    block = (
        "- [ ] X (HIGH) :: desc :: depends:none :: status:pending\n"
        "  a later append: depends:none :: status:CLOSED_DONE\n"
    )
    assert TS._extract_field_last(block, "status").lower() == "closed_done"


def test_single_line_item_unaffected_last_equals_only():
    # Sanity: for a normal single-line item (the vast majority of the real
    # queue), "last match" degenerates to "the only match" — identical to
    # the pre-fix behavior, i.e. zero regression risk for the common case.
    block = "- [ ] Y (MED) :: desc :: depends:none :: status:pending"
    assert TS._extract_field_last(block, "status") == "pending"
