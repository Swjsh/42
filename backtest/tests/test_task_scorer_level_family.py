"""Guard test for setup/scripts/task_scorer.py's LEVEL_FAMILY signal.

WHAT THIS GUARDS
----------------
FOCUS-DOCTRINE (markdown/doctrine/FOCUS-DOCTRINE.md, 2026-07-22 night,
CHEF-FOCUS-FILTER queue item) narrows R&D intake to level-interaction
research (rejection, reclaim, S/R flip + retest, range ping-pong, break-
and-retest) as the primary bounded lane. Part (2) of that item is:
"task_scorer.py adds a level-family priority weight for research items."

This test pins that a level-family-worded item scores STRICTLY HIGHER than
an otherwise-identical non-level item at the same priority tier, so a
regression that silently drops the LEVEL_FAMILY_RE match (or its bonus)
fails loud here instead of quietly re-starving the FOCUS-DOCTRINE lane the
way the pre-fix engine-benefit/quick-win signals could (same class of bug
this module already guards against).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCORER = REPO / "setup" / "scripts" / "task_scorer.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("task_scorer_lf", SCORER)
    assert spec and spec.loader, f"cannot load scorer at {SCORER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TS = _load_module()


# ---------------------------------------------------------------------------
# 1. Each named level-family phrase from FOCUS-DOCTRINE #2 is recognized.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "phrase",
    [
        "a bearish rejection at a key level on the 5m chart",
        "bullish reclaim of the overnight high",
        "S/R flip and retest of the prior resistance",
        "range ping-pong between the two adjacent levels",
        "a break and retest of the opening range high",
        "level break-retest continuation setup",
    ],
)
def test_level_family_phrases_recognized(phrase):
    assert TS.LEVEL_FAMILY_RE.search(phrase), f"expected a match for: {phrase!r}"


def test_non_level_research_not_matched():
    # A generic research item with no level-interaction language at all.
    plain = "investigate a volume-profile based entry timing model"
    assert not TS.LEVEL_FAMILY_RE.search(plain)


# ---------------------------------------------------------------------------
# 2. The bonus actually moves the score (same priority tier, same other
#    signals held constant) and is recorded in the human-readable reason.
# ---------------------------------------------------------------------------
def test_level_family_bonus_outranks_plain_at_same_priority():
    level_score, level_reason = TS.score_item(
        "MED",
        "backtest a bullish reclaim of the level as a new trigger",
        "(MED)",
        True,
        False,
    )
    plain_score, plain_reason = TS.score_item(
        "MED",
        "backtest a volume-spike based new trigger",
        "(MED)",
        True,
        False,
    )
    assert level_score > plain_score
    assert "level-family" in level_reason
    assert "level-family" not in plain_reason


def test_level_family_stacks_with_engine_benefit():
    # Level-family + engine-benefit words together should out-score
    # engine-benefit alone -- the two signals are additive, not exclusive.
    both, both_reason = TS.score_item(
        "HIGH",
        "tune the exit stop param for the level reclaim trigger",
        "(HIGH)",
        True,
        False,
    )
    engine_only, _ = TS.score_item(
        "HIGH",
        "tune the exit stop param for a generic trigger",
        "(HIGH)",
        True,
        False,
    )
    assert both > engine_only
    assert "level-family" in both_reason
    assert "engine-benefit" in both_reason


# ---------------------------------------------------------------------------
# 3. End-to-end through parse_queue/rank on a synthetic queue.md fragment.
# ---------------------------------------------------------------------------
SYNTHETIC_QUEUE = """# OVERNIGHT TASK QUEUE

## Active backlog

- [ ] LEVEL-ITEM (MED) :: Validate a bullish reclaim of the level as a new setup :: depends:none :: status:pending
- [ ] NONLEVEL-ITEM (MED) :: Validate a volume-spike based new setup :: depends:none :: status:pending
"""


def test_level_family_outranks_nonlevel_in_full_ranking():
    ranked = TS.rank(SYNTHETIC_QUEUE, include_blocked=False)
    ids = [t.id for t in ranked]
    assert ids.index("LEVEL-ITEM") < ids.index("NONLEVEL-ITEM")
    by_id = {t.id: t for t in ranked}
    assert by_id["LEVEL-ITEM"].score > by_id["NONLEVEL-ITEM"].score
