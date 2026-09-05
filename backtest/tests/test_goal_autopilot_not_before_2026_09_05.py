"""Guard: LADDER.md entries may carry ` :: not_before:YYYY-MM-DD`; the autopilot never opens
such an entry before that ET calendar date and walks past it to the next eligible line.

Why (2026-09-05, Saturday): GOAL-FIRST-FIRES-2026-09-08 (evidence that Tuesday's first live
fires of four new instruments were sane) was opened as the ACTIVE goal on Saturday morning,
because the ladder had no way to say "not yet". Every weekend conductor fire would have spent
~$1 recording "not yet", and any real goal authored behind it was starved (active goal has an
open item -> ensure noops). A date is not a gate in general (feedback_overnight_loop_never_idle)
-- but a goal whose evidence cannot exist before a date IS date-bound, and the ladder needs to
say so in its own grammar.
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

GOAL_MD = (
    "# GOAL: T\n> fixture\n\n## DONE-WHEN\nx.\n\n## OPERATING RULES\n- r\n\n"
    "## QUEUE\n[ ] todo\n- [ ] step 1\n\n## J-DECISIONS\n- none\n\n## PROGRESS LOG\n- none\n"
    "## HONEST STATE\nqueued.\n"
)


def _line(gid: str, not_before: str | None = None, marker: str = " ") -> str:
    tail = f" :: not_before:{not_before}" if not_before else ""
    return f"- [{marker}] {gid} :: one line :: file: automation/state/goals/{gid}.md :: expires_days:14{tail}"


def _repo(tmp_path: Path, ladder_lines: list[str]) -> Path:
    (tmp_path / "automation" / "state" / "goals").mkdir(parents=True)
    (tmp_path / "automation" / "overnight").mkdir(parents=True)
    for line in ladder_lines:
        gid = line.split("]")[1].split("::")[0].strip()
        (tmp_path / "automation" / "state" / "goals" / f"{gid}.md").write_text(GOAL_MD, encoding="utf-8")
    (tmp_path / "automation" / "state" / "goals" / "LADDER.md").write_text(
        ga.LADDER_HEADER + "\n".join(ladder_lines) + "\n", encoding="utf-8")
    (tmp_path / "automation" / "state" / "active-goal.json").write_text(
        json.dumps({"active": False}), encoding="utf-8")
    return tmp_path


def _ensure(root: Path, now: str) -> dict:
    ap = ga.Autopilot(ga.Paths(root), now_et=datetime.fromisoformat(now), write=True)
    return ap.ensure()


def test_parse_ladder_reads_optional_not_before():
    rows = ga.parse_ladder(_line("GOAL-A", "2026-09-08") + "\n" + _line("GOAL-B"))
    assert [r["not_before"] for r in rows] == ["2026-09-08", None]
    assert rows[0]["expires_days"] == 14


def test_flip_marker_preserves_not_before_token():
    text = _line("GOAL-A", "2026-09-08") + "\n"
    flipped = ga.flip_ladder_marker(text, "GOAL-A", "~")
    assert flipped == _line("GOAL-A", "2026-09-08", marker="~") + "\n"


def test_gated_entry_is_skipped_and_the_next_eligible_opens(tmp_path):
    root = _repo(tmp_path, [_line("GOAL-GATED", "2026-09-08"), _line("GOAL-NOW")])
    res = _ensure(root, "2026-09-05T12:00:00")
    assert res["action"] == "opened"
    active = json.loads((root / "automation" / "state" / "active-goal.json").read_text(encoding="utf-8"))
    assert active["id"] == "GOAL-NOW"
    ladder = (root / "automation" / "state" / "goals" / "LADDER.md").read_text(encoding="utf-8")
    assert _line("GOAL-GATED", "2026-09-08") in ladder  # untouched, still queued with its gate
    row = next(r for r in res["ladder"] if r["id"] == "GOAL-GATED")
    assert row["eligible"] is False and row["why"].startswith("not before 2026-09-08")


def test_gated_entry_opens_on_its_date(tmp_path):
    root = _repo(tmp_path, [_line("GOAL-GATED", "2026-09-08")])
    assert _ensure(root, "2026-09-07T23:59:00")["action"] != "opened"
    res = _ensure(root, "2026-09-08T00:01:00")
    assert res["action"] == "opened"
    active = json.loads((root / "automation" / "state" / "active-goal.json").read_text(encoding="utf-8"))
    assert active["id"] == "GOAL-GATED"


def test_malformed_not_before_never_blocks(tmp_path):
    entry = {"not_before": "someday"}
    assert ga.not_before_blocks(entry, datetime(2026, 9, 5, 12, 0)) is None
    assert ga.not_before_blocks({"not_before": None}, datetime(2026, 9, 5, 12, 0)) is None


def test_real_ladder_gates_the_two_dated_goals():
    text = (REPO / "automation" / "state" / "goals" / "LADDER.md").read_text(encoding="utf-8")
    by_id = {r["id"]: r for r in ga.parse_ladder(text)}
    assert by_id["GOAL-FIRST-FIRES-2026-09-08"]["not_before"] == "2026-09-08"
    assert by_id["GOAL-SEPT-MIDWINDOW-READ-2026-09-15"]["not_before"] == "2026-09-15"
