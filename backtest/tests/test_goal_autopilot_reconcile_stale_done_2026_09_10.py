"""Guard for setup/scripts/goal_autopilot.py's `reconcile_stale_done` -- found
live 2026-09-10 conductor fire.

ROOT CAUSE: `ensure()`'s `_open_next` only opens a LADDER.md entry that is
both `[ ]` (queued) AND has a bare `- [ ] ` item in its own `## QUEUE`
section (`goal_file_eligible`). A goal whose work was done DIRECTLY by a
session that never went through the autopilot's open flow (no
active-goal.json entry, no queue.md row) ends up with every QUEUE marker
already `[x]` but the LADDER.md marker still `[ ]` -- `goal_file_eligible`
correctly calls that "not eligible to open" (nothing left to assign), so
`_open_next` skips it FOREVER: it can never open (nothing to do) and it can
never close (it was never the active goal, so `_close` is never reached).

Confirmed live: GOAL-GATE-EXPIRY-RECONCILE-2026-09-05 and
GOAL-FUTURES-YELLOWS-2026-09-05 both sat `[ ]` in LADDER.md while their own
files' `## QUEUE` sections were 100% `[x]`, PROGRESS LOG'd, and HONEST
STATE'd as complete since 2026-09-05 14:4x ET -- 5 days of ladder noise
falsely reading "not yet started."

This is intentionally a SEPARATE, EXPLICIT method
(`reconcile_stale_done`/`reconcile-stale-done` CLI verb), not a change to
`ensure()`'s own close/open semantics -- `test_skips_queued_entry_with_no_
open_queue_item` (test_goal_autopilot_2026_09_03.py) pins that `ensure()`
itself must never silently close an entry it never opened (a goal file that
LOOKS done might just be a badly-authored template with no QUEUE items at
all). `reconcile_stale_done` is the deliberate, auditable step for the real
case where the goal genuinely finished outside the loop.
"""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

ga = importlib.import_module("goal_autopilot")

NOW = datetime(2026, 9, 10, 5, 30, 0)


def _goal_md(queue_lines: tuple[str, ...]) -> str:
    queue_body = "\n".join(queue_lines)
    return (
        "# GOAL: TEST\n> test fixture.\n\n"
        "## DONE-WHEN\nSomething falsifiable.\n\n"
        "## QUEUE\n[ ] todo   [~] wip   [x] done\n"
        f"{queue_body}\n\n"
        "## PROGRESS LOG\n- 2026-09-05 14:41 ET — done directly, autopilot never opened it.\n\n"
        "## HONEST STATE\nAll done.\n"
    )


def _write_repo(tmp_path: Path, *, ladder_lines: list[str], goal_files: dict[str, str],
                 queue_text: str | None = None, active_goal: dict | None = None) -> "ga.Paths":
    paths = ga.Paths(tmp_path)
    paths.state.mkdir(parents=True, exist_ok=True)
    paths.goals_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "automation" / "overnight").mkdir(parents=True, exist_ok=True)

    if active_goal is not None:
        paths.active_goal.write_text(json.dumps(active_goal), encoding="utf-8")

    header = "# LADDER.md fixture\n> format doc (irrelevant to parsing)\n\n"
    paths.ladder.write_text(header + "\n".join(ladder_lines) + "\n", encoding="utf-8")

    for name, text in goal_files.items():
        (paths.goals_dir / name).write_text(text, encoding="utf-8")

    if queue_text is not None:
        paths.queue_md.write_text(queue_text, encoding="utf-8")
    return paths


def test_reconciles_a_never_opened_but_fully_terminal_queued_entry(tmp_path):
    ladder = [
        "- [ ] GOAL-DONE-OUTSIDE-LOOP :: finished directly :: file: automation/state/goals/GOAL-DONE-OUTSIDE-LOOP.md :: expires_days:14",
        "- [ ] GOAL-STILL-OPEN :: real work remains :: file: automation/state/goals/GOAL-STILL-OPEN.md :: expires_days:14",
    ]
    paths = _write_repo(
        tmp_path, ladder_lines=ladder,
        goal_files={
            "GOAL-DONE-OUTSIDE-LOOP.md": _goal_md(queue_lines=("- [x] step 1 done", "- [x] step 2 done")),
            "GOAL-STILL-OPEN.md": _goal_md(queue_lines=("- [ ] step 1",)),
        },
        queue_text="# queue.md fixture\n\n## Active backlog\n> note\n",
    )
    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.reconcile_stale_done()

    assert result["action"] == "reconciled"
    assert result["closed_ids"] == ["GOAL-DONE-OUTSIDE-LOOP"]

    ladder_text = paths.ladder.read_text(encoding="utf-8")
    assert "- [x] GOAL-DONE-OUTSIDE-LOOP ::" in ladder_text
    # The genuinely-unfinished entry is untouched.
    assert "- [ ] GOAL-STILL-OPEN ::" in ladder_text

    goal_text = (paths.goals_dir / "GOAL-DONE-OUTSIDE-LOOP.md").read_text(encoding="utf-8")
    assert "closed by goal_autopilot" in goal_text
    assert "never flipped" in goal_text
    assert "AUTOPILOT CLOSE" in goal_text

    # No queue.md row existed for it (never opened) -- WARN event, no crash.
    assert any("WARN" in ev and "GOAL-DONE-OUTSIDE-LOOP" in ev for ev in ap.events)


def test_never_touches_active_goal_json(tmp_path):
    """None of the reconciled entries were ever the active pointer -- the
    currently-active goal (a DIFFERENT id) must be completely untouched."""
    active = {
        "id": "GOAL-ACTIVE", "active": True, "opened_at_et": "2026-09-09T00:00:00",
        "expires_at_et": "2026-09-20", "file": "automation/state/goals/GOAL-ACTIVE.md",
        "queue_id": "GOAL-ACTIVE", "max_continuations_per_session": 3, "last_next_item": None,
    }
    ladder = [
        "- [~] GOAL-ACTIVE :: currently active :: file: automation/state/goals/GOAL-ACTIVE.md :: expires_days:14",
        "- [ ] GOAL-DONE-OUTSIDE-LOOP :: finished directly :: file: automation/state/goals/GOAL-DONE-OUTSIDE-LOOP.md :: expires_days:14",
    ]
    paths = _write_repo(
        tmp_path, ladder_lines=ladder, active_goal=active,
        goal_files={
            "GOAL-ACTIVE.md": _goal_md(queue_lines=("- [ ] still open",)),
            "GOAL-DONE-OUTSIDE-LOOP.md": _goal_md(queue_lines=("- [x] step 1 done",)),
        },
        queue_text="# queue.md fixture\n\n## Active backlog\n> note\n",
    )
    before_active_json = paths.active_goal.read_text(encoding="utf-8")

    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.reconcile_stale_done()

    assert result["closed_ids"] == ["GOAL-DONE-OUTSIDE-LOOP"]
    # active-goal.json byte-for-byte unchanged.
    assert paths.active_goal.read_text(encoding="utf-8") == before_active_json
    ladder_text = paths.ladder.read_text(encoding="utf-8")
    assert "- [~] GOAL-ACTIVE ::" in ladder_text  # untouched
    assert "- [x] GOAL-DONE-OUTSIDE-LOOP ::" in ladder_text


def test_noop_when_nothing_stale(tmp_path):
    ladder = [
        "- [ ] GOAL-STILL-OPEN :: real work remains :: file: automation/state/goals/GOAL-STILL-OPEN.md :: expires_days:14",
        "- [x] GOAL-ALREADY-CLOSED :: already flipped :: file: automation/state/goals/GOAL-ALREADY-CLOSED.md :: expires_days:14",
    ]
    paths = _write_repo(
        tmp_path, ladder_lines=ladder,
        goal_files={
            "GOAL-STILL-OPEN.md": _goal_md(queue_lines=("- [ ] step 1",)),
            "GOAL-ALREADY-CLOSED.md": _goal_md(queue_lines=("- [x] step 1 done",)),
        },
    )
    before_ladder = paths.ladder.read_text(encoding="utf-8")

    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.reconcile_stale_done()

    assert result["action"] == "noop"
    assert result["closed_ids"] == []
    assert paths.ladder.read_text(encoding="utf-8") == before_ladder


def test_ensure_own_pinned_skip_behavior_is_unaffected():
    """Regression guard: this fix must NOT change ensure()'s own semantics --
    re-import the sibling test module's fixture shape inline rather than
    depending on it, and confirm goal_file_eligible still reports the
    all-terminal-but-never-opened entry as ineligible (ensure() must keep
    skipping it, never auto-closing it itself)."""
    text = _goal_md(queue_lines=("- [x] step 1 done",))
    eligible, reason, item = ga.goal_file_eligible(text)
    assert eligible is False
    assert item is None
    assert ga.goal_is_terminal(text) is True


def test_cli_reconcile_stale_done_dry_run_writes_nothing(tmp_path):
    ladder = [
        "- [ ] GOAL-DONE-OUTSIDE-LOOP :: finished directly :: file: automation/state/goals/GOAL-DONE-OUTSIDE-LOOP.md :: expires_days:14",
    ]
    paths = _write_repo(
        tmp_path, ladder_lines=ladder,
        goal_files={"GOAL-DONE-OUTSIDE-LOOP.md": _goal_md(queue_lines=("- [x] step 1 done",))},
    )
    before_ladder = paths.ladder.read_text(encoding="utf-8")
    rc = ga.main([
        "reconcile-stale-done", "--repo", str(tmp_path), "--now", NOW.isoformat(), "--dry-run",
    ])
    assert rc == 0
    assert paths.ladder.read_text(encoding="utf-8") == before_ladder
