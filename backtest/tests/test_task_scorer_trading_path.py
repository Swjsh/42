"""Guards for the 2026-07-01 task_scorer re-aim (pipeline-audit fix #5).

WHAT THIS GUARDS (each bug buried J's own HIGH trading items for ~7 days —
see markdown/audits/PIPELINE-AUDIT-2026-07-01.md "Why the autonomy loop never
fixed this"):

  1. ``depends:none (annotation)`` is NONE — the parenthesized annotation is
     prose, not a dependency. Items like RIBBON-LAG-PRICE-STRUCTURE-TRIGGER
     ('depends:none (was OPEN-BLINDNESS-TV-HANG; decoupled 2026-06-27)') must
     score ready=True.
  2. A TRADING_PATH_RE item (order/fill/entry/exit/placement/arm/stop/
     position-monitor) is NEVER expense-penalized even when it matches
     EXPENSIVE_RE (spec/design/research...).
  3. A dependency naming a NON-OPEN item (done / '- [~]' / unknown compound
     status like G4's 'wiring-done-arm-is-j-gated') is satisfied; a dependency
     naming a genuinely open item still blocks.

Run with:
    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_task_scorer_trading_path.py -q
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCORER = REPO / "setup" / "scripts" / "task_scorer.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("task_scorer_tp", SCORER)
    assert spec and spec.loader, f"cannot load scorer at {SCORER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TS = _load_module()


QUEUE = """# OVERNIGHT TASK QUEUE

## Active backlog

### Tier 0

- [~] G4-LIKE-TILDE (P1, engine-wiring) :: wiring shipped disarmed :: depends:none :: status:wiring-done-arm-is-j-gated
- [ ] DONEISH-DEP (HIGH) :: finished but unchecked :: depends:none :: status:done
- [ ] OPEN-DEP (HIGH) :: a genuinely open prerequisite :: depends:none :: status:pending

- [ ] ANNOTATED-NONE (HIGH, engine-design) :: J-directed trigger that fires on the rejection candle, needs real-fills validation :: depends:none (was OPEN-BLINDNESS-TV-HANG; decoupled 2026-06-27 -- live-engine sight verified hang-resistant) :: status:pending
- [ ] DEP-ON-TILDE (HIGH, engine-exit) :: wire the ribbon-flip-back exit fn :: depends:G4-LIKE-TILDE :: status:pending
- [ ] DEP-ON-DONEISH (HIGH) :: depends on an unchecked-but-done item :: depends:DONEISH-DEP :: status:pending
- [ ] DEP-ON-OPEN (HIGH) :: depends on a real open item :: depends:OPEN-DEP :: status:pending
- [ ] DEP-ON-ABSENT (HIGH) :: depends on an id that is not in the queue :: depends:SOME-COMPLETED-ELSEWHERE :: status:pending
- [ ] MULTI-DEP-ONE-OPEN (HIGH) :: two deps, one still open :: depends:DONEISH-DEP,OPEN-DEP :: status:pending
"""


def _by_id(tasks):
    return {t.id: t for t in tasks}


# ---------------------------------------------------------------------------
# 1. depends:none (annotation) == none  → ready=True.
# ---------------------------------------------------------------------------
def test_depends_none_with_annotation_is_ready():
    by_id = _by_id(TS.parse_queue(QUEUE))
    assert by_id["ANNOTATED-NONE"].ready is True


def test_depends_none_with_annotation_gets_ready_bonus():
    by_id = _by_id(TS.parse_queue(QUEUE))
    assert "ready-now" in by_id["ANNOTATED-NONE"].reason


def test_dep_tokens_ignores_parenthesized_prose():
    assert TS._dep_tokens("none (was X; decoupled 2026-06-27)") == []
    assert TS._dep_tokens("none") == []
    assert TS._dep_tokens("") == []
    assert TS._dep_tokens("A,B (annotation, with comma)") == ["A", "B"]


# ---------------------------------------------------------------------------
# 2. Trading-path items are never expense-penalized.
# ---------------------------------------------------------------------------
def test_trading_path_item_not_expense_penalized():
    # Matches EXPENSIVE_RE ("design") AND TRADING_PATH_RE ("order", "exit").
    score_tp, reason_tp = TS.score_item(
        "HIGH", "design the order placement + exit wiring", "(HIGH)", True, False
    )
    # Matches EXPENSIVE_RE only — gets divided.
    score_doc, reason_doc = TS.score_item(
        "HIGH", "design the documentation taxonomy spec", "(HIGH)", True, False
    )
    assert "expensive-exempt(trading-path)" in reason_tp
    assert "expensive(cost)" not in reason_tp
    assert "expensive(cost)" in reason_doc
    assert score_tp > score_doc


def test_trading_path_regex_matches_the_function_vocabulary():
    for desc in (
        "prove one core-account fill intraday",
        "wire the entry ceiling into the hot path",
        "position monitor 1-min ticks for stops",
        "arm vwap_continuation on paper",
        "exit actuator placement path",
        "orders accepted per day instrument",
    ):
        assert TS.TRADING_PATH_RE.search(desc), f"should match: {desc}"
    assert not TS.TRADING_PATH_RE.search("fold the doc index taxonomy")


def test_non_trading_expensive_item_still_penalized():
    # The cost proxy must survive for genuinely non-trading design work (BITE:
    # this REDs if the exemption is over-broadened to everything).
    _, reason = TS.score_item(
        "MED", "research a new lesson taxonomy redesign", "(MED)", True, False
    )
    assert "expensive(cost)" in reason


# ---------------------------------------------------------------------------
# 3. Dependency satisfied unless the dep item is genuinely OPEN.
# ---------------------------------------------------------------------------
def test_dep_on_tilde_item_is_satisfied():
    # G4's '- [~]' + 'wiring-done-arm-is-j-gated' never parses as an open item
    # → G14-shaped dependents are pickable.
    by_id = _by_id(TS.parse_queue(QUEUE))
    assert by_id["DEP-ON-TILDE"].ready is True


def test_dep_on_unchecked_done_item_is_satisfied():
    by_id = _by_id(TS.parse_queue(QUEUE))
    assert by_id["DEP-ON-DONEISH"].ready is True


def test_dep_on_absent_id_is_satisfied():
    by_id = _by_id(TS.parse_queue(QUEUE))
    assert by_id["DEP-ON-ABSENT"].ready is True


def test_dep_on_open_item_still_blocks():
    # BITE: the fix must NOT dissolve real dependencies.
    by_id = _by_id(TS.parse_queue(QUEUE))
    assert by_id["DEP-ON-OPEN"].ready is False
    assert by_id["MULTI-DEP-ONE-OPEN"].ready is False


def test_legacy_no_context_behavior_preserved():
    # Without an open_ids set, any named dep blocks (standalone callers).
    assert TS._is_blocked_by_deps("SOME-DEP") is True
    assert TS._is_blocked_by_deps("none (annotation)") is False
    assert TS._is_blocked_by_deps("none") is False
