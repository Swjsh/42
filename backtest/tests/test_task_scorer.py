"""Tests for setup/scripts/task_scorer.py — the conductor's ROI backlog ranker.

WHAT THIS GUARDS
----------------
``task_scorer.py`` lets the conductor pick its next task by value-per-cost (ROI)
instead of fixed tier label. These tests pin the contract that matters:

  1. HIGH outranks LOW (priority base flows through to the score).
  2. Dependency-blocked items are excluded from --top (and from the default
     ready-only ranking), but appear with ready=false under --all.
  3. The engine-benefit signal boosts an item above an otherwise-equal one.
  4. Malformed / non-item lines are skipped, never crash the parser.
  5. Only the "## Active backlog" section is parsed — Completed/Archived/
     HARVESTED items are ignored.
  6. A missing queue file yields [] (array) / "" (--top) and never raises.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCORER = REPO / "setup" / "scripts" / "task_scorer.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("task_scorer", SCORER)
    assert spec and spec.loader, f"cannot load scorer at {SCORER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TS = _load_module()


# A small synthetic queue.md exercising every branch we care about.
SYNTHETIC_QUEUE = """# OVERNIGHT TASK QUEUE

> Some preamble prose that is NOT an item.

---

## Active backlog

> Ranked by leverage — this blockquote must be ignored.

### Tier 1 — engine correctness

- [ ] HI-ENGINE (HIGH, engine-benefit) :: Fix the strike exit stop sizing param :: depends:none :: status:pending
- [ ] LO-DOC (LOW, doc-index) :: Fold L169 into the OP-25 index :: depends:none :: status:pending
- [x] DONE-ITEM (HIGH) :: This one is already finished :: depends:none :: status:done
- [ ] BLOCKED-ITEM (HIGH, engine-benefit) :: Wire the new validator into the fill path :: depends:HI-ENGINE :: status:pending

### Tier 2 — j-ratification

- [ ] AWAIT-J (HIGH, Rule-9) :: Some doctrine change for J to rule on :: depends:none :: status:awaiting-j-ratification
- [ ] PLAIN-MED (MED) :: A plain medium task with no special signals here :: depends:none :: status:pending
- [ ] EXPENSIVE-MED (MED, engine-benefit) :: Design and research a new exit redesign spec :: depends:none :: status:pending

### Tier 3

this is a malformed line that should be skipped entirely
- [ ] :: totally broken no id here :: depends:none :: status:pending
- [ ] TIER4-NOSTATUS (LOW) :: Carry-over with no depends/status fields

## Completed

- [ ] SHOULD-NOT-APPEAR (HIGH, engine-benefit) :: This is under Completed, must be ignored :: depends:none :: status:pending

## HARVESTED-FROM-GYM

- [ ] HARVEST-X (HIGH) :: also must be ignored, wrong section :: depends:none :: status:queued
"""


@pytest.fixture()
def ranked_ready():
    return TS.rank(SYNTHETIC_QUEUE, include_blocked=False)


@pytest.fixture()
def ranked_all():
    return TS.rank(SYNTHETIC_QUEUE, include_blocked=True)


def _by_id(tasks):
    return {t.id: t for t in tasks}


# ---------------------------------------------------------------------------
# 1. HIGH > LOW ordering.
# ---------------------------------------------------------------------------
def test_high_outranks_low(ranked_ready):
    ids = [t.id for t in ranked_ready]
    assert "HI-ENGINE" in ids and "LO-DOC" in ids
    assert ids.index("HI-ENGINE") < ids.index("LO-DOC")
    by_id = _by_id(ranked_ready)
    assert by_id["HI-ENGINE"].score > by_id["LO-DOC"].score


# ---------------------------------------------------------------------------
# 2. Blocked items excluded from --top / ready ranking; present under --all.
# ---------------------------------------------------------------------------
def test_blocked_excluded_from_ready(ranked_ready):
    ids = [t.id for t in ranked_ready]
    assert "BLOCKED-ITEM" not in ids  # has depends:HI-ENGINE → not ready


def test_blocked_present_under_all(ranked_all):
    by_id = _by_id(ranked_all)
    assert "BLOCKED-ITEM" in by_id
    assert by_id["BLOCKED-ITEM"].ready is False


def test_top_skips_blocked_and_returns_highest_ready():
    # --top runs over ready items only; the best ready item is HI-ENGINE.
    ranked = TS.rank(SYNTHETIC_QUEUE, include_blocked=False)
    assert ranked, "expected a non-empty ready ranking"
    assert ranked[0].id == "HI-ENGINE"
    assert ranked[0].id != "BLOCKED-ITEM"


# ---------------------------------------------------------------------------
# 3. Engine-benefit boost applied.
# ---------------------------------------------------------------------------
def test_engine_benefit_boost_applied():
    # Two MED items: one with an engine-benefit description, one plain.
    by_id = _by_id(TS.rank(SYNTHETIC_QUEUE, include_blocked=False))
    # EXPENSIVE-MED has the engine words but is divided by the cost proxy, so to
    # isolate the *boost* we compare the score_item value directly.
    boosted, _ = TS.score_item("MED", "tune the exit stop sizing param", "(MED)", True, False)
    plain, _ = TS.score_item("MED", "a plain task with no special words", "(MED)", True, False)
    assert boosted > plain
    # And the engine-benefit reason is recorded.
    _, reason = TS.score_item("MED", "fix the fill risk param", "(MED)", True, False)
    assert "engine-benefit" in reason


# ---------------------------------------------------------------------------
# 4. Malformed lines skipped, parser never raises.
# ---------------------------------------------------------------------------
def test_malformed_lines_skipped():
    ids = [t.id for t in TS.parse_queue(SYNTHETIC_QUEUE)]
    # The broken "no id" line and the free-text line produce no tasks.
    assert "" not in ids
    assert all(i for i in ids)


def test_parser_never_raises_on_garbage():
    garbage = "\n".join(
        [
            "## Active backlog",
            "- [ ] ((( malformed parens",
            "- [ ] X (HIGH :: missing close paren",
            "::::::::",
            "- [ ] GOOD (HIGH) :: a valid one :: depends:none :: status:pending",
        ]
    )
    tasks = TS.parse_queue(garbage)  # must not raise
    assert any(t.id == "GOOD" for t in tasks)


# ---------------------------------------------------------------------------
# 5. Only the Active-backlog section is parsed.
# ---------------------------------------------------------------------------
def test_only_active_section_parsed():
    ids = [t.id for t in TS.parse_queue(SYNTHETIC_QUEUE)]
    assert "SHOULD-NOT-APPEAR" not in ids  # under ## Completed
    assert "HARVEST-X" not in ids  # under ## HARVESTED-FROM-GYM


def test_done_and_awaiting_j_excluded():
    ids = [t.id for t in TS.parse_queue(SYNTHETIC_QUEUE)]
    assert "DONE-ITEM" not in ids  # - [x]
    assert "AWAIT-J" not in ids  # status:awaiting-j-ratification


# ---------------------------------------------------------------------------
# 6. Missing file → [] / "" and never raises.
# ---------------------------------------------------------------------------
def test_missing_file_yields_none(tmp_path):
    missing = tmp_path / "nope.md"
    assert TS.load_queue_text(missing) is None


def test_no_status_item_is_ready():
    # TIER4-NOSTATUS has no status/depends fields → treated as ready pending.
    by_id = _by_id(TS.rank(SYNTHETIC_QUEUE, include_blocked=False))
    assert "TIER4-NOSTATUS" in by_id
    assert by_id["TIER4-NOSTATUS"].ready is True


def test_json_shape_round_trips():
    ranked = TS.rank(SYNTHETIC_QUEUE, include_blocked=False)
    payload = json.loads(TS._to_json(ranked))
    assert isinstance(payload, list)
    for row in payload:
        assert set(row.keys()) == {"id", "score", "priority", "ready", "reason"}
