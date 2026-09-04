"""Guards for setup/scripts/goal_autopilot.py -- task A1, GOAL-GAMMA-AUTONOMY-2026-09-03.

Gamma's goal producer used to be entirely human-gated (`.claude/skills/gamma-goal/
SKILL.md` is `disable-model-invocation: true`), so `active-goal.json` sat inactive
for days at a time and the conductor drained janitorial work instead of learning.
This is the deterministic (no-LLM) walker that opens the next `automation/state/
goals/LADDER.md` entry whenever nothing is active, and closes a goal whose QUEUE
has gone fully terminal or whose expiry has passed.

Every test builds a throwaway tmp_path "repo" (active-goal.json / goals/LADDER.md /
goals/GOAL-*.md / overnight/queue.md) and calls the module's `Autopilot` class
directly -- never the real repo state, per CLAUDE.md's "parallel Claudes stay in
their own lane" discipline.
"""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

ga = importlib.import_module("goal_autopilot")


# ============================================================================
# Fixture builders
# ============================================================================

def _goal_md(done_when: bool = True, queue_lines: tuple[str, ...] = ("- [ ] step 1",)) -> str:
    dw = "## DONE-WHEN\nSomething falsifiable.\n\n" if done_when else ""
    queue_body = "\n".join(queue_lines)
    return (
        "# GOAL: TEST\n"
        "> test fixture, not a real J quote.\n\n"
        f"{dw}"
        "## OPERATING RULES\n- rule one\n\n"
        "## QUEUE\n[ ] todo   [~] wip   [x] done\n"
        f"{queue_body}\n\n"
        "## J-DECISIONS\n- none\n\n"
        "## PROGRESS LOG\n- 2026-09-01 00:00 ET — opened.\n\n"
        "## HONEST STATE\nNothing shipped yet.\n"
    )


def _queue_md_with_row(goal_id: str, status: str = "in_progress") -> str:
    return (
        "# queue.md fixture\n\n"
        "## Active backlog\n"
        "> some blockquote note\n"
        f"- [ ] {goal_id} (HIGH, goal) :: one line -- file: automation/state/goals/{goal_id}.md "
        f":: depends:none :: status:{status}\n"
        "### Some other section\n"
        "- [ ] OTHER-ITEM (MED, misc) :: unrelated :: depends:none :: status:pending\n"
    )


def _queue_md_no_row() -> str:
    return (
        "# queue.md fixture\n\n"
        "## Active backlog\n"
        "> some blockquote note\n"
        "> another blockquote line\n"
        "- [ ] OTHER-ITEM (MED, misc) :: unrelated :: depends:none :: status:pending\n"
    )


def _write_repo(tmp_path: Path, *, active_goal: dict | None, ladder_lines: list[str],
                 goal_files: dict[str, str], queue_text: str) -> ga.Paths:
    paths = ga.Paths(tmp_path)
    paths.state.mkdir(parents=True, exist_ok=True)
    paths.goals_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "automation" / "overnight").mkdir(parents=True, exist_ok=True)

    if active_goal is not None:
        paths.active_goal.write_text(json.dumps(active_goal), encoding="utf-8")

    header = (
        "# LADDER.md fixture\n> format doc (irrelevant to parsing)\n\n"
    )
    paths.ladder.write_text(header + "\n".join(ladder_lines) + "\n", encoding="utf-8")

    for name, text in goal_files.items():
        (paths.goals_dir / name).write_text(text, encoding="utf-8")

    paths.queue_md.write_text(queue_text, encoding="utf-8")
    return paths


NOW = datetime(2026, 9, 3, 20, 0, 0)  # 20:00 ET Thursday -- well after hours
FUTURE_EXPIRY = "2026-09-17"
PAST_EXPIRY = "2026-08-01"


# ============================================================================
# 1. Opens the first eligible queued entry when inactive
# ============================================================================

def test_opens_first_eligible_queued_entry_when_inactive(tmp_path):
    ladder = [
        "- [ ] GOAL-A :: first queued goal :: file: automation/state/goals/GOAL-A.md :: expires_days:14",
        "- [ ] GOAL-B :: second queued goal :: file: automation/state/goals/GOAL-B.md :: expires_days:14",
    ]
    paths = _write_repo(
        tmp_path, active_goal=None, ladder_lines=ladder,
        goal_files={"GOAL-A.md": _goal_md(), "GOAL-B.md": _goal_md()},
        queue_text=_queue_md_no_row(),
    )
    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.ensure()

    assert result["action"] == "opened"
    assert result["active_goal_id"] == "GOAL-A"
    new_active = json.loads(paths.active_goal.read_text(encoding="utf-8"))
    assert new_active["id"] == "GOAL-A"
    assert new_active["active"] is True
    assert new_active["max_continuations_per_session"] == 3
    assert new_active["last_next_item"] is None

    ladder_text = paths.ladder.read_text(encoding="utf-8")
    assert "- [~] GOAL-A ::" in ladder_text
    assert "- [ ] GOAL-B ::" in ladder_text  # untouched -- only the FIRST opens

    queue_text = paths.queue_md.read_text(encoding="utf-8")
    assert "GOAL-A (HIGH, goal) :: first queued goal -- file: automation/state/goals/GOAL-A.md :: depends:none :: status:in_progress" in queue_text

    goal_text = (paths.goals_dir / "GOAL-A.md").read_text(encoding="utf-8")
    assert "opened by goal_autopilot" in goal_text


# ============================================================================
# 2. Noop when active + open item
# ============================================================================

def test_noop_when_active_goal_has_open_item(tmp_path):
    active = {
        "id": "GOAL-A", "active": True, "opened_at_et": "2026-09-01T00:00:00",
        "expires_at_et": FUTURE_EXPIRY, "file": "automation/state/goals/GOAL-A.md",
        "queue_id": "GOAL-A", "max_continuations_per_session": 3, "last_next_item": None,
    }
    ladder = ["- [~] GOAL-A :: active goal :: file: automation/state/goals/GOAL-A.md :: expires_days:14"]
    paths = _write_repo(
        tmp_path, active_goal=active, ladder_lines=ladder,
        goal_files={"GOAL-A.md": _goal_md()}, queue_text=_queue_md_with_row("GOAL-A"),
    )
    before_active = paths.active_goal.read_text(encoding="utf-8")
    before_ladder = paths.ladder.read_text(encoding="utf-8")
    before_queue = paths.queue_md.read_text(encoding="utf-8")

    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.ensure()

    assert result["action"] == "noop"
    assert result["active_goal_id"] == "GOAL-A"
    assert result["next_item"] == "step 1"
    # Nothing on disk changed.
    assert paths.active_goal.read_text(encoding="utf-8") == before_active
    assert paths.ladder.read_text(encoding="utf-8") == before_ladder
    assert paths.queue_md.read_text(encoding="utf-8") == before_queue


# ============================================================================
# 3. Skips a queued entry with a missing file
# ============================================================================

def test_skips_queued_entry_with_missing_file(tmp_path):
    ladder = [
        "- [ ] GOAL-MISSING :: file does not exist :: file: automation/state/goals/GOAL-MISSING.md :: expires_days:14",
        "- [ ] GOAL-REAL :: this one exists :: file: automation/state/goals/GOAL-REAL.md :: expires_days:14",
    ]
    paths = _write_repo(
        tmp_path, active_goal=None, ladder_lines=ladder,
        goal_files={"GOAL-REAL.md": _goal_md()},  # GOAL-MISSING.md deliberately absent
        queue_text=_queue_md_no_row(),
    )
    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.ensure()

    assert result["action"] == "opened"
    assert result["active_goal_id"] == "GOAL-REAL"
    assert any("GOAL-MISSING" in ev and "missing file" in ev for ev in ap.events)
    ladder_text = paths.ladder.read_text(encoding="utf-8")
    assert "- [ ] GOAL-MISSING ::" in ladder_text  # never opened
    assert "- [~] GOAL-REAL ::" in ladder_text


def test_skips_queued_entry_missing_done_when(tmp_path):
    ladder = [
        "- [ ] GOAL-NODW :: has queue but no DONE-WHEN :: file: automation/state/goals/GOAL-NODW.md :: expires_days:14",
        "- [ ] GOAL-REAL :: eligible :: file: automation/state/goals/GOAL-REAL.md :: expires_days:14",
    ]
    paths = _write_repo(
        tmp_path, active_goal=None, ladder_lines=ladder,
        goal_files={
            "GOAL-NODW.md": _goal_md(done_when=False),
            "GOAL-REAL.md": _goal_md(),
        },
        queue_text=_queue_md_no_row(),
    )
    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.ensure()
    assert result["action"] == "opened"
    assert result["active_goal_id"] == "GOAL-REAL"
    assert any("GOAL-NODW" in ev and "DONE-WHEN" in ev for ev in ap.events)


def test_skips_queued_entry_with_no_open_queue_item(tmp_path):
    ladder = [
        "- [ ] GOAL-ALLDONE :: nothing left to do :: file: automation/state/goals/GOAL-ALLDONE.md :: expires_days:14",
        "- [ ] GOAL-REAL :: eligible :: file: automation/state/goals/GOAL-REAL.md :: expires_days:14",
    ]
    paths = _write_repo(
        tmp_path, active_goal=None, ladder_lines=ladder,
        goal_files={
            "GOAL-ALLDONE.md": _goal_md(queue_lines=("- [x] step 1 done",)),
            "GOAL-REAL.md": _goal_md(),
        },
        queue_text=_queue_md_no_row(),
    )
    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.ensure()
    assert result["action"] == "opened"
    assert result["active_goal_id"] == "GOAL-REAL"


# ============================================================================
# 4. Closes an all-terminal goal, then opens the next
# ============================================================================

def test_closes_terminal_goal_then_opens_next(tmp_path):
    active = {
        "id": "GOAL-A", "active": True, "opened_at_et": "2026-09-01T00:00:00",
        "expires_at_et": FUTURE_EXPIRY, "file": "automation/state/goals/GOAL-A.md",
        "queue_id": "GOAL-A", "max_continuations_per_session": 3, "last_next_item": None,
    }
    ladder = [
        "- [~] GOAL-A :: now terminal :: file: automation/state/goals/GOAL-A.md :: expires_days:14",
        "- [ ] GOAL-B :: next up :: file: automation/state/goals/GOAL-B.md :: expires_days:14",
    ]
    paths = _write_repo(
        tmp_path, active_goal=active, ladder_lines=ladder,
        goal_files={
            "GOAL-A.md": _goal_md(queue_lines=("- [x] step 1 done",)),  # fully terminal
            "GOAL-B.md": _goal_md(),
        },
        queue_text=_queue_md_with_row("GOAL-A"),
    )
    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.ensure()

    assert result["action"] == "closed_opened"
    assert result["closed_id"] == "GOAL-A"
    assert result["opened_id"] == "GOAL-B"

    ladder_text = paths.ladder.read_text(encoding="utf-8")
    assert "- [x] GOAL-A ::" in ladder_text
    assert "- [~] GOAL-B ::" in ladder_text

    active_json = json.loads(paths.active_goal.read_text(encoding="utf-8"))
    assert active_json["id"] == "GOAL-B"
    assert active_json["active"] is True

    goal_a_text = (paths.goals_dir / "GOAL-A.md").read_text(encoding="utf-8")
    assert "closed by goal_autopilot" in goal_a_text
    assert "AUTOPILOT CLOSE" in goal_a_text

    queue_text = paths.queue_md.read_text(encoding="utf-8")
    goal_a_row = [l for l in queue_text.splitlines() if "GOAL-A (" in l]
    assert len(goal_a_row) == 1
    assert goal_a_row[0].endswith("status:done")
    assert "GOAL-B (HIGH, goal)" in queue_text  # new row inserted for the newly-opened goal


# ============================================================================
# 4b. WIP items keep a goal OPEN -- the 2026-09-04 01:19 ET bug.
#
# Root cause: goal_autopilot's close-if-terminal path used to treat
# "doctrine.goal_next_open_item returned None" as "the goal is finished", but
# that function deliberately skips `[~]` (wip, owned by a running session) as
# well as bare `[ ]` -- so a goal with only `[~]` items left (nothing
# ASSIGNABLE to a new fire) looked identical to a goal with nothing OPEN at
# all, and got closed out from under the session that owned the wip items.
# The fix: a goal is terminal only when every QUEUE marker is x/B/B-J.
# ============================================================================

def test_active_goal_with_one_wip_item_is_not_closed(tmp_path):
    active = {
        "id": "GOAL-A", "active": True, "opened_at_et": "2026-09-01T00:00:00",
        "expires_at_et": FUTURE_EXPIRY, "file": "automation/state/goals/GOAL-A.md",
        "queue_id": "GOAL-A", "max_continuations_per_session": 3, "last_next_item": None,
    }
    ladder = ["- [~] GOAL-A :: has a wip item :: file: automation/state/goals/GOAL-A.md :: expires_days:14"]
    paths = _write_repo(
        tmp_path, active_goal=active, ladder_lines=ladder,
        # All [x] except one [~] -- nothing bare-open, but NOT finished:
        # this is exactly the shape GOAL-COCKPIT-REDESIGN-2026-09-03 was in
        # (R4b/R5/R5b/R6 all [~], owned by session 42-98) when it got closed.
        goal_files={"GOAL-A.md": _goal_md(queue_lines=(
            "- [x] step 1 done",
            "- [~] step 2 owned by another session",
            "- [x] step 3 done",
        ))},
        queue_text=_queue_md_with_row("GOAL-A"),
    )
    before_active = paths.active_goal.read_text(encoding="utf-8")
    before_ladder = paths.ladder.read_text(encoding="utf-8")
    before_queue = paths.queue_md.read_text(encoding="utf-8")
    before_goal = (paths.goals_dir / "GOAL-A.md").read_text(encoding="utf-8")

    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.ensure()

    assert result["action"] == "noop"
    assert result["active_goal_id"] == "GOAL-A"
    assert result["reason"] == "active goal has in-progress items (no assignable item)"
    assert "in-progress" in result["reason"]
    # Nothing on disk changed -- it must NOT be closed, NOT reopened as a
    # different goal, and the goal file must not be touched.
    assert paths.active_goal.read_text(encoding="utf-8") == before_active
    assert paths.ladder.read_text(encoding="utf-8") == before_ladder
    assert paths.queue_md.read_text(encoding="utf-8") == before_queue
    assert (paths.goals_dir / "GOAL-A.md").read_text(encoding="utf-8") == before_goal


def test_close_if_terminal_also_keeps_wip_only_goal_open(tmp_path):
    active = {
        "id": "GOAL-A", "active": True, "opened_at_et": "2026-09-01T00:00:00",
        "expires_at_et": FUTURE_EXPIRY, "file": "automation/state/goals/GOAL-A.md",
        "queue_id": "GOAL-A", "max_continuations_per_session": 3, "last_next_item": None,
    }
    ladder = ["- [~] GOAL-A :: has a wip item :: file: automation/state/goals/GOAL-A.md :: expires_days:14"]
    paths = _write_repo(
        tmp_path, active_goal=active, ladder_lines=ladder,
        goal_files={"GOAL-A.md": _goal_md(queue_lines=("- [~] still owned",))},
        queue_text=_queue_md_with_row("GOAL-A"),
    )
    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.close_if_terminal()
    assert result["action"] == "noop"
    assert result["reason"] == "active goal has in-progress items (no assignable item)"
    assert json.loads(paths.active_goal.read_text(encoding="utf-8"))["active"] is True


def test_all_x_b_bj_markers_close_and_open_next(tmp_path):
    active = {
        "id": "GOAL-A", "active": True, "opened_at_et": "2026-09-01T00:00:00",
        "expires_at_et": FUTURE_EXPIRY, "file": "automation/state/goals/GOAL-A.md",
        "queue_id": "GOAL-A", "max_continuations_per_session": 3, "last_next_item": None,
    }
    ladder = [
        "- [~] GOAL-A :: fully terminal via x/B/B-J :: file: automation/state/goals/GOAL-A.md :: expires_days:14",
        "- [ ] GOAL-B :: next up :: file: automation/state/goals/GOAL-B.md :: expires_days:14",
    ]
    paths = _write_repo(
        tmp_path, active_goal=active, ladder_lines=ladder,
        goal_files={
            "GOAL-A.md": _goal_md(queue_lines=(
                "- [x] step 1 done",
                "- [B] step 2 blocked",
                "- [B-J] step 3 blocked by J",
            )),
            "GOAL-B.md": _goal_md(),
        },
        queue_text=_queue_md_with_row("GOAL-A"),
    )
    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.ensure()

    assert result["action"] == "closed_opened"
    assert result["closed_id"] == "GOAL-A"
    assert result["opened_id"] == "GOAL-B"
    assert result["reason"] == "queue fully terminal (no bare '- [ ] ' item left)"
    ladder_text = paths.ladder.read_text(encoding="utf-8")
    assert "- [x] GOAL-A ::" in ladder_text
    assert "- [~] GOAL-B ::" in ladder_text


def test_queue_markers_ignores_lines_outside_queue_heading():
    text = (
        "# GOAL: TEST\n\n"
        "## DONE-WHEN\nSomething falsifiable.\n\n"
        "## OPERATING RULES\n"
        "- [ ] not a queue item -- this must be ignored\n"
        "- [x] also not a queue item\n\n"
        "## QUEUE\n"
        "- [x] real item one\n"
        "- [~] real item two\n\n"
        "## J-DECISIONS\n"
        "- [ ] a decision bullet, also not QUEUE -- must be ignored\n\n"
        "## PROGRESS LOG\n- note\n"
    )
    assert ga.queue_markers(text) == ["x", "~"]
    assert ga.goal_is_terminal(text) is False  # the [~] keeps it open


def test_goal_is_terminal_true_only_when_all_markers_terminal():
    assert ga.goal_is_terminal("## QUEUE\n- [x] a\n- [B] b\n- [B-J] c\n") is True
    assert ga.goal_is_terminal("## QUEUE\n- [x] a\n- [~] b\n") is False
    assert ga.goal_is_terminal("## QUEUE\n- [ ] a\n") is False
    assert ga.goal_is_terminal("## QUEUE\nno markers here\n") is False  # empty -> not terminal
    assert ga.goal_is_terminal(None) is False


# ============================================================================
# 5. Closes an expired goal
# ============================================================================

def test_closes_expired_goal(tmp_path):
    active = {
        "id": "GOAL-A", "active": True, "opened_at_et": "2026-08-01T00:00:00",
        "expires_at_et": PAST_EXPIRY, "file": "automation/state/goals/GOAL-A.md",
        "queue_id": "GOAL-A", "max_continuations_per_session": 3, "last_next_item": None,
    }
    ladder = ["- [~] GOAL-A :: expired :: file: automation/state/goals/GOAL-A.md :: expires_days:14"]
    paths = _write_repo(
        tmp_path, active_goal=active, ladder_lines=ladder,
        # Still has an open item -- expiry alone must force the close.
        goal_files={"GOAL-A.md": _goal_md(queue_lines=("- [ ] still not done",))},
        queue_text=_queue_md_with_row("GOAL-A"),
    )
    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.ensure()

    assert result["closed_id"] == "GOAL-A"
    assert result["reason"] == "expired"
    active_json = json.loads(paths.active_goal.read_text(encoding="utf-8"))
    assert active_json["active"] is False
    assert active_json["closed_reason"] == "expired"
    queue_text = paths.queue_md.read_text(encoding="utf-8")
    assert "status:expired" in queue_text
    ladder_text = paths.ladder.read_text(encoding="utf-8")
    assert "- [x] GOAL-A ::" in ladder_text


def test_closes_expired_goal_even_with_a_wip_item(tmp_path):
    """Expiry is independent of terminality -- a `[~]` item does NOT protect
    an expired goal from closing (only an unexpired goal gets the new
    in-progress noop)."""
    active = {
        "id": "GOAL-A", "active": True, "opened_at_et": "2026-08-01T00:00:00",
        "expires_at_et": PAST_EXPIRY, "file": "automation/state/goals/GOAL-A.md",
        "queue_id": "GOAL-A", "max_continuations_per_session": 3, "last_next_item": None,
    }
    ladder = ["- [~] GOAL-A :: expired with wip :: file: automation/state/goals/GOAL-A.md :: expires_days:14"]
    paths = _write_repo(
        tmp_path, active_goal=active, ladder_lines=ladder,
        goal_files={"GOAL-A.md": _goal_md(queue_lines=("- [~] still owned by a session",))},
        queue_text=_queue_md_with_row("GOAL-A"),
    )
    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.ensure()

    # No other ladder entry exists here, so after closing GOAL-A there is
    # nothing left to open -- "closed_ladder_empty" (still confirms it closed).
    assert result["action"] == "closed_ladder_empty"
    assert result["closed_id"] == "GOAL-A"
    assert result["reason"] == "expired"
    active_json = json.loads(paths.active_goal.read_text(encoding="utf-8"))
    assert active_json["active"] is False
    assert active_json["closed_reason"] == "expired"


# ============================================================================
# 6. ladder_empty when nothing eligible
# ============================================================================

def test_ladder_empty_when_nothing_eligible(tmp_path):
    ladder = [
        "- [ ] GOAL-MISSING :: gone :: file: automation/state/goals/GOAL-MISSING.md :: expires_days:14",
        "- [x] GOAL-DONE :: already closed :: file: automation/state/goals/GOAL-DONE.md :: expires_days:14",
    ]
    paths = _write_repo(
        tmp_path, active_goal=None, ladder_lines=ladder,
        goal_files={"GOAL-DONE.md": _goal_md(queue_lines=("- [x] done",))},
        queue_text=_queue_md_no_row(),
    )
    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.ensure()

    assert result["action"] == "ladder_empty"
    assert result["active_goal_id"] is None
    status_row = {r["id"]: r for r in result["ladder"]}
    assert status_row["GOAL-MISSING"]["eligible"] is False
    assert status_row["GOAL-MISSING"]["state"] == "queued"
    assert status_row["GOAL-DONE"]["state"] == "done"


# ============================================================================
# 7. queue.md row grammar + status flip in place
# ============================================================================

def test_queue_row_is_exactly_one_line_with_grammar():
    text = _queue_md_no_row()
    row = ga.queue_row_grammar("GOAL-X", "one line goal", "automation/state/goals/GOAL-X.md")
    assert row == (
        "- [ ] GOAL-X (HIGH, goal) :: one line goal -- file: automation/state/goals/GOAL-X.md "
        ":: depends:none :: status:in_progress"
    )
    new_text, inserted = ga.ensure_queue_row(text, "GOAL-X", row)
    assert inserted is True
    lines = new_text.splitlines()
    matches = [l for l in lines if "GOAL-X (" in l]
    assert len(matches) == 1, "row must be exactly one line, no continuation prose"
    assert matches[0] == row

    # Re-running must not duplicate the row.
    again_text, inserted_again = ga.ensure_queue_row(new_text, "GOAL-X", row)
    assert inserted_again is False
    assert again_text.count("GOAL-X (") == 1


def test_queue_row_status_flips_in_place_on_close():
    text = _queue_md_with_row("GOAL-A", status="in_progress")
    new_text, found = ga.flip_queue_row_status(text, "GOAL-A", "done")
    assert found is True
    lines = [l for l in new_text.splitlines() if "GOAL-A (" in l]
    assert len(lines) == 1
    assert lines[0].endswith("status:done")
    assert "status:in_progress" not in lines[0]
    # every other field on the line is untouched
    assert "depends:none" in lines[0]
    assert "GOAL-A (HIGH, goal)" in lines[0]


# ============================================================================
# 8. RTH -> skip_rth, zero writes
# ============================================================================

def test_rth_skips_with_zero_writes(tmp_path):
    ladder = ["- [ ] GOAL-A :: queued :: file: automation/state/goals/GOAL-A.md :: expires_days:14"]
    paths = _write_repo(
        tmp_path, active_goal=None, ladder_lines=ladder,
        goal_files={"GOAL-A.md": _goal_md()}, queue_text=_queue_md_no_row(),
    )
    before_status_exists = paths.status_json.exists()
    before_log_exists = paths.log_jsonl.exists()
    before_ladder = paths.ladder.read_text(encoding="utf-8")
    before_active_exists = paths.active_goal.exists()

    rth_now = datetime(2026, 9, 3, 10, 0, 0)  # Thursday 10:00 ET -- inside RTH
    assert ga.is_market_hours_et(rth_now) is True

    rc = ga.main(["ensure", "--repo", str(tmp_path), "--now", rth_now.isoformat()])
    assert rc == 0
    assert paths.ladder.read_text(encoding="utf-8") == before_ladder
    assert paths.status_json.exists() == before_status_exists
    assert paths.log_jsonl.exists() == before_log_exists
    assert paths.active_goal.exists() == before_active_exists


def test_market_hours_boundaries():
    # Monday 09:30 ET -- inside
    assert ga.is_market_hours_et(datetime(2026, 8, 31, 9, 30, 0)) is True
    # Monday 15:54 -- inside; 15:55 -- outside (exclusive upper bound)
    assert ga.is_market_hours_et(datetime(2026, 8, 31, 15, 54, 0)) is True
    assert ga.is_market_hours_et(datetime(2026, 8, 31, 15, 55, 0)) is False
    # Saturday -- always outside regardless of time
    assert ga.is_market_hours_et(datetime(2026, 9, 5, 12, 0, 0)) is False
    # 09:29 -- one minute before open
    assert ga.is_market_hours_et(datetime(2026, 8, 31, 9, 29, 0)) is False


# ============================================================================
# 9. dry-run writes nothing
# ============================================================================

def test_dry_run_writes_nothing(tmp_path):
    ladder = ["- [ ] GOAL-A :: queued :: file: automation/state/goals/GOAL-A.md :: expires_days:14"]
    paths = _write_repo(
        tmp_path, active_goal=None, ladder_lines=ladder,
        goal_files={"GOAL-A.md": _goal_md()}, queue_text=_queue_md_no_row(),
    )
    before_ladder = paths.ladder.read_text(encoding="utf-8")
    before_goal = (paths.goals_dir / "GOAL-A.md").read_text(encoding="utf-8")
    before_queue = paths.queue_md.read_text(encoding="utf-8")
    before_active_exists = paths.active_goal.exists()
    before_status_exists = paths.status_json.exists()
    before_log_exists = paths.log_jsonl.exists()

    rc = ga.main(["ensure", "--repo", str(tmp_path), "--now", NOW.isoformat(), "--dry-run"])
    assert rc == 0

    assert paths.ladder.read_text(encoding="utf-8") == before_ladder
    assert (paths.goals_dir / "GOAL-A.md").read_text(encoding="utf-8") == before_goal
    assert paths.queue_md.read_text(encoding="utf-8") == before_queue
    assert paths.active_goal.exists() == before_active_exists
    assert paths.status_json.exists() == before_status_exists
    assert paths.log_jsonl.exists() == before_log_exists


# ============================================================================
# 10. Exceptions fail open
# ============================================================================

def test_exceptions_fail_open(tmp_path, monkeypatch):
    ladder = ["- [ ] GOAL-A :: queued :: file: automation/state/goals/GOAL-A.md :: expires_days:14"]
    paths = _write_repo(
        tmp_path, active_goal=None, ladder_lines=ladder,
        goal_files={"GOAL-A.md": _goal_md()}, queue_text=_queue_md_no_row(),
    )

    def _boom(*a, **kw):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(ga, "parse_ladder", _boom)
    rc = ga.main(["ensure", "--repo", str(tmp_path), "--now", NOW.isoformat()])
    assert rc == 0  # fail OPEN -- never a nonzero exit without --strict

    status = json.loads(paths.status_json.read_text(encoding="utf-8"))
    assert status["action"] == "error"
    assert "simulated failure" in status["error"]


def test_exceptions_reraise_with_strict(tmp_path, monkeypatch):
    ladder = ["- [ ] GOAL-A :: queued :: file: automation/state/goals/GOAL-A.md :: expires_days:14"]
    _write_repo(
        tmp_path, active_goal=None, ladder_lines=ladder,
        goal_files={"GOAL-A.md": _goal_md()}, queue_text=_queue_md_no_row(),
    )

    def _boom(*a, **kw):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(ga, "parse_ladder", _boom)
    with pytest.raises(RuntimeError):
        ga.main(["ensure", "--repo", str(tmp_path), "--now", NOW.isoformat(), "--strict"])


# ============================================================================
# Idempotency: running ensure twice in a row is a noop the second time
# ============================================================================

def test_idempotent_second_run_is_noop(tmp_path):
    ladder = ["- [ ] GOAL-A :: queued :: file: automation/state/goals/GOAL-A.md :: expires_days:14"]
    paths = _write_repo(
        tmp_path, active_goal=None, ladder_lines=ladder,
        goal_files={"GOAL-A.md": _goal_md()}, queue_text=_queue_md_no_row(),
    )
    first = ga.Autopilot(paths, NOW, write=True).ensure()
    assert first["action"] == "opened"

    second = ga.Autopilot(paths, NOW, write=True).ensure()
    assert second["action"] == "noop"
    assert second["active_goal_id"] == "GOAL-A"


# ============================================================================
# close-if-terminal CLI path (no auto-open of the next entry)
# ============================================================================

def test_close_if_terminal_does_not_open_next(tmp_path):
    active = {
        "id": "GOAL-A", "active": True, "opened_at_et": "2026-09-01T00:00:00",
        "expires_at_et": FUTURE_EXPIRY, "file": "automation/state/goals/GOAL-A.md",
        "queue_id": "GOAL-A", "max_continuations_per_session": 3, "last_next_item": None,
    }
    ladder = [
        "- [~] GOAL-A :: now terminal :: file: automation/state/goals/GOAL-A.md :: expires_days:14",
        "- [ ] GOAL-B :: should stay queued :: file: automation/state/goals/GOAL-B.md :: expires_days:14",
    ]
    paths = _write_repo(
        tmp_path, active_goal=active, ladder_lines=ladder,
        goal_files={
            "GOAL-A.md": _goal_md(queue_lines=("- [x] step 1 done",)),
            "GOAL-B.md": _goal_md(),
        },
        queue_text=_queue_md_with_row("GOAL-A"),
    )
    ap = ga.Autopilot(paths, NOW, write=True)
    result = ap.close_if_terminal()
    assert result["action"] == "closed"
    ladder_text = paths.ladder.read_text(encoding="utf-8")
    assert "- [x] GOAL-A ::" in ladder_text
    assert "- [ ] GOAL-B ::" in ladder_text  # untouched -- close-if-terminal never opens


# ============================================================================
# Pure-helper unit tests (no IO)
# ============================================================================

def test_parse_ladder_ignores_non_matching_lines():
    text = (
        "# header\n> blockquote\n\n"
        "- [ ] GOAL-A :: desc one :: file: automation/state/goals/GOAL-A.md :: expires_days:7\n"
        "some random prose line\n"
        "- [~] GOAL-B :: desc two :: file: automation/state/goals/GOAL-B.md :: expires_days:30\n"
    )
    entries = ga.parse_ladder(text)
    assert len(entries) == 2
    assert entries[0]["id"] == "GOAL-A"
    assert entries[0]["marker"] == " "
    assert entries[0]["expires_days"] == 7
    assert entries[1]["marker"] == "~"


def test_goal_file_eligible_missing_file_returns_false():
    eligible, reason, item = ga.goal_file_eligible(None)
    assert eligible is False
    assert "missing" in reason
    assert item is None


def test_flip_ladder_marker_only_touches_named_entry():
    text = (
        "- [ ] GOAL-A :: a :: file: automation/state/goals/GOAL-A.md :: expires_days:14\n"
        "- [ ] GOAL-B :: b :: file: automation/state/goals/GOAL-B.md :: expires_days:14\n"
    )
    new_text = ga.flip_ladder_marker(text, "GOAL-A", "~")
    assert "- [~] GOAL-A ::" in new_text
    assert "- [ ] GOAL-B ::" in new_text


def test_append_under_heading_inserts_before_next_heading():
    text = (
        "## PROGRESS LOG\n- line one\n\n"
        "## HONEST STATE\nsome state\n"
    )
    new_text = ga.append_under_heading(text, "PROGRESS LOG", "- line two")
    lines = new_text.splitlines()
    idx_progress = lines.index("## PROGRESS LOG")
    idx_honest = lines.index("## HONEST STATE")
    assert idx_progress < lines.index("- line two") < idx_honest
    assert "- line one" in new_text
