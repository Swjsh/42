"""Guard for task_scorer.staleness_advisory — the OP-25 graduation of the
2026-07-18 "stale queue item outranked real work" lesson (3 same-day recurrences:
RANGE-SCALP-REGIME-STRATEGY, POSITION-MONITOR-1MIN cluster,
RIBBON-LAG-PRICE-STRUCTURE-TRIGGER — all CLOSED_ALREADY_ANSWERED/CLOSED_SUPERSEDED
by research or infra that shipped AFTER the item was filed).

WHAT THIS GUARDS
----------------
1. A HIGH/CRITICAL-ranked #1 item prints a non-None advisory nudging the operator
   to trace the item against current reality before executing.
2. A MED/LOW-ranked #1 item does NOT print an advisory (this is a targeted nudge
   for the class of item that actually caused the 3 same-day recurrences — HIGH
   items — not indiscriminate noise on every fire).
3. An empty ranking (no ready items) never raises and returns None.
4. --top's stdout contract is UNCHANGED (id-only, or empty string) — the advisory
   goes to stderr only, verified via subprocess so a real accidental stdout leak
   would be caught (this is the exact kind of contract a downstream `.strip()`
   consumer like the conductor's `task_scorer.py --top` shell-out depends on).
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCORER = REPO / "setup" / "scripts" / "task_scorer.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("task_scorer_staleness", SCORER)
    assert spec and spec.loader, f"cannot load scorer at {SCORER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TS = _load_module()

HIGH_QUEUE = """# Q

## Active backlog

- [ ] HI-ITEM (HIGH, engine-benefit) :: Some high item :: depends:none :: status:pending
"""

MED_QUEUE = """# Q

## Active backlog

- [ ] MED-ITEM (MED) :: Some medium item :: depends:none :: status:pending
"""

LOW_QUEUE = """# Q

## Active backlog

- [ ] LOW-ITEM (LOW, doc-index) :: Some low item :: depends:none :: status:pending
"""


def test_high_ranked_first_gets_advisory():
    ranked = TS.rank(HIGH_QUEUE, include_blocked=False)
    assert ranked and ranked[0].priority == "HIGH"
    advisory = TS.staleness_advisory(ranked)
    assert advisory is not None
    assert "HI-ITEM" in advisory
    assert "HIGH" in advisory


def test_med_ranked_first_gets_no_advisory():
    ranked = TS.rank(MED_QUEUE, include_blocked=False)
    assert ranked and ranked[0].priority == "MED"
    assert TS.staleness_advisory(ranked) is None


def test_low_ranked_first_gets_no_advisory():
    ranked = TS.rank(LOW_QUEUE, include_blocked=False)
    assert ranked and ranked[0].priority == "LOW"
    assert TS.staleness_advisory(ranked) is None


def test_empty_ranking_returns_none_never_raises():
    assert TS.staleness_advisory([]) is None


def test_top_stdout_contract_unaffected_by_advisory():
    """--top's stdout must stay id-only even when a HIGH item triggers the
    advisory — the advisory is stderr-only. Run as a real subprocess so a
    stray `print(advisory)` (no file=sys.stderr) would be caught exactly the
    way it would break the conductor's real `subprocess.run(...).stdout` shell-out.
    """
    # Real subprocess against the REAL repo queue.md (whatever HIGH item, if
    # any, currently ranks #1) — stdout must be a single bare id line (or
    # empty), never containing the advisory's "[task_scorer] advisory:"
    # marker, proving the advisory never leaked onto stdout.
    result = subprocess.run(
        [sys.executable, str(SCORER), "--top"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert "[task_scorer] advisory:" not in result.stdout
    stdout_id = result.stdout.strip()
    assert "\n" not in stdout_id, f"--top stdout must be a single id line, got: {result.stdout!r}"
