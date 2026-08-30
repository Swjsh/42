"""Tests for whats_changed.py -- the WHAT-CHANGED digest.

Covers: no marker (first run), nothing changed, several changes across every
section, a corrupt marker file, and that reading never advances the marker.
Plus focused unit coverage for the trickier parsers (timestamp parsing,
STATUS.md 'Known broken' extraction, scheduled-task freshness gating, and
the goals opened/advanced/closed heuristic).

Run: pytest -v setup/scripts/test_whats_changed.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Direct import (script is in setup/scripts, not a package) -- same pattern
# as the other setup/scripts/test_*.py files in this repo.
_spec = importlib.util.spec_from_file_location(
    "whats_changed",
    Path(__file__).parent / "whats_changed.py",
)
wc = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(wc)  # type: ignore[union-attr]


# --------------------------------------------------------------------- setup

def _wire(monkeypatch, repo: Path) -> None:
    """Point every module-level path constant at an isolated tmp tree."""
    state = repo / "automation" / "state"
    monkeypatch.setattr(wc, "REPO", repo)
    monkeypatch.setattr(wc, "STATE", state)
    monkeypatch.setattr(wc, "MARKER_FILE", state / "whats-changed-marker.json")
    monkeypatch.setattr(wc, "OUT_FILE", state / "whats-changed.json")
    monkeypatch.setattr(wc, "GOALS_DIR", state / "goals")
    monkeypatch.setattr(wc, "ACTIVE_GOAL_FILE", state / "active-goal.json")
    monkeypatch.setattr(wc, "STATUS_MD", repo / "automation" / "overnight" / "STATUS.md")
    monkeypatch.setattr(wc, "MANAGER_ESCALATIONS", state / "manager-escalations.json")
    monkeypatch.setattr(wc, "CONDUCTOR_OUTCOMES", state / "conductor-outcomes.jsonl")
    monkeypatch.setattr(wc, "UNATTENDED_HEALTH", state / "unattended-health.json")
    monkeypatch.setattr(wc, "AUTONOMY_METRIC", state / "autonomy-metric.json")


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(path), check=True)


def _git_commit(path: Path, filename: str, content: str, message: str, when: datetime) -> None:
    f = path / filename
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True)
    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = when.isoformat()
    env["GIT_COMMITTER_DATE"] = when.isoformat()
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=str(path), check=True, env=env)


def _write_marker(repo: Path, since: datetime) -> None:
    p = repo / "automation" / "state" / "whats-changed-marker.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"since_iso": since.isoformat()}), encoding="utf-8")


T0 = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)
BEFORE = T0 - timedelta(hours=2)
AFTER = T0 + timedelta(hours=2)


# ------------------------------------------------------------- the 5 required scenarios

def test_no_marker_is_first_run(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path)
    marker = wc.read_marker()
    assert marker["status"] == "missing"
    assert marker["since"] is None

    payload = wc.build_digest(now=T0)
    assert payload["marker_status"] == "missing"
    assert payload["used_default_window"] is True
    assert payload["total_changes"] == 0
    assert payload["headline"].startswith("nothing changed since no stored marker")
    # OP-33: an empty digest still names every section, never a blank panel.
    for key in ("commits", "action_cards", "goals", "known_broken", "scheduled_task_failures"):
        assert "count" in payload["sections"][key]


def test_nothing_changed_renders_explicit_message_not_blank(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path)
    _write_marker(tmp_path, T0)

    payload = wc.build_digest(now=AFTER)
    assert payload["marker_status"] == "ok"
    assert payload["total_changes"] == 0
    assert payload["headline"] == "nothing changed since %s" % T0.isoformat()
    human = wc.render_human(payload)
    assert human.strip() == payload["headline"]


def test_several_changes_across_every_section(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path)
    _write_marker(tmp_path, T0)
    _init_git_repo(tmp_path)

    # commits: one before the marker (must be excluded), two after (included)
    _git_commit(tmp_path, "a.txt", "1", "old commit before marker", BEFORE)
    _git_commit(tmp_path, "b.txt", "2", "feat: new thing after marker", AFTER)
    _git_commit(tmp_path, "c.txt", "3", "fix: another thing after marker", AFTER + timedelta(minutes=1))

    # action cards / escalation ledger
    state = tmp_path / "automation" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "manager-escalations.json").write_text(json.dumps({
        "abc123": {"reason": "worker_fabrication", "count": 3, "detail": "claimed a file that doesn't exist",
                   "last_ts": AFTER.isoformat(), "first_ts": BEFORE.isoformat()},
        "old999": {"reason": "manager_flagged", "count": 1, "detail": "stale, before marker",
                   "last_ts": BEFORE.isoformat(), "first_ts": BEFORE.isoformat()},
    }), encoding="utf-8")
    (state / "conductor-outcomes.jsonl").write_text(
        json.dumps({"fired_at": AFTER.isoformat(), "task_id": "T-1", "note": "shipped the fix"}) + "\n"
        + json.dumps({"fired_at": BEFORE.isoformat(), "task_id": "T-0", "note": "before marker, excluded"}) + "\n",
        encoding="utf-8",
    )

    # goals: monkeypatch _last_touched so the classification is deterministic
    # and doesn't depend on git's committer-date resolution.
    (state / "goals").mkdir(parents=True, exist_ok=True)
    (state / "goals" / "GOAL-NEW-2026-08-29.md").write_text("# new", encoding="utf-8")
    (state / "goals" / "GOAL-OLD-2026-07-01.md").write_text("# old, now superseded", encoding="utf-8")
    (state / "active-goal.json").write_text(json.dumps({
        "id": "GOAL-NEW-2026-08-29", "opened_at_et": AFTER.isoformat(),
        "file": "automation/state/goals/GOAL-NEW-2026-08-29.md",
    }), encoding="utf-8")

    def _fake_touched(path):
        return {"GOAL-NEW-2026-08-29.md": AFTER, "GOAL-OLD-2026-07-01.md": AFTER}.get(path.name)
    monkeypatch.setattr(wc, "_last_touched", _fake_touched)

    # STATUS.md known-broken
    status_dir = tmp_path / "automation" / "overnight"
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / "STATUS.md").write_text(
        "## something else\n\n"
        "## Known broken\n\n"
        "- [%s] OLD-ISSUE: before the marker, must be excluded\n"
        "- [%s] NEW-ISSUE: after the marker, must be included\n\n"
        "### BROKEN: self-check %s\n"
        "- some header-style entry after the marker\n"
        % (BEFORE.isoformat(), AFTER.isoformat(), AFTER.isoformat()),
        encoding="utf-8",
    )

    # scheduled-task health, refreshed after the marker
    (state / "unattended-health.json").write_text(json.dumps({
        "checked_at_et": AFTER.isoformat(),
        "units": [
            {"id": "u1", "name": "Window-leak detector", "status": "YELLOW"},
            {"id": "u2", "name": "Engine core", "status": "GREEN"},
            {"id": "u3", "name": "LLM heartbeat", "status": "OFF"},
        ],
    }), encoding="utf-8")

    payload = wc.build_digest(now=AFTER + timedelta(minutes=5))

    assert payload["sections"]["commits"]["count"] == 2
    subjects = [c["subject"] for c in payload["sections"]["commits"]["top"]]
    assert "old commit before marker" not in subjects
    assert any("new thing" in s for s in subjects)

    ac = payload["sections"]["action_cards"]
    assert ac["count"] == 2  # 1 escalation + 1 fired outcome, both after marker
    assert ac["escalations"][0]["id"] == "abc123"
    assert ac["fired_outcomes"][0]["task_id"] == "T-1"

    goals = payload["sections"]["goals"]
    assert goals["count"] == 2
    assert [g["id"] for g in goals["opened"]] == ["GOAL-NEW-2026-08-29"]
    assert [g["id"] for g in goals["closed"]] == ["GOAL-OLD-2026-07-01"]
    assert goals["advanced"] == []  # the active goal was newly OPENED this window, not advanced

    kb = payload["sections"]["known_broken"]
    assert kb["count"] == 2
    texts = [e["text"] for e in kb["top"]]
    assert any("NEW-ISSUE" in t for t in texts)
    assert not any("OLD-ISSUE" in t for t in texts)

    tf = payload["sections"]["scheduled_task_failures"]
    assert tf["fresh"] is True
    assert tf["count"] == 1
    assert tf["top"][0]["name"] == "Window-leak detector"

    assert payload["total_changes"] == 2 + 2 + 2 + 2 + 1
    assert payload["headline"] == "%d change(s) since %s" % (payload["total_changes"], T0.isoformat())

    human = wc.render_human(payload)
    assert "COMMITS (2):" in human
    assert "GOALS (2):" in human


def test_corrupt_marker_file_falls_back_to_first_run(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path)
    marker_path = tmp_path / "automation" / "state" / "whats-changed-marker.json"
    marker_path.parent.mkdir(parents=True, exist_ok=True)

    marker_path.write_text("{not valid json", encoding="utf-8")
    m = wc.read_marker()
    assert m["status"] == "corrupt"
    assert m["since"] is None

    marker_path.write_text(json.dumps({"no_since_key": True}), encoding="utf-8")
    m = wc.read_marker()
    assert m["status"] == "corrupt"

    marker_path.write_text(json.dumps({"since_iso": "not-a-real-timestamp"}), encoding="utf-8")
    m = wc.read_marker()
    assert m["status"] == "corrupt"

    payload = wc.build_digest(now=T0)
    assert payload["marker_status"] == "corrupt"
    assert payload["used_default_window"] is True
    assert payload["total_changes"] == 0  # empty tree either way -- must not crash


def test_reading_never_advances_the_marker(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path)
    marker_path = tmp_path / "automation" / "state" / "whats-changed-marker.json"

    # first run: no marker file at all
    wc.build_digest(now=T0)
    wc.build_digest(now=T0 + timedelta(hours=1))
    assert not marker_path.exists()

    # with a marker present: repeated reads must not touch it
    _write_marker(tmp_path, T0)
    before_bytes = marker_path.read_bytes()
    for _ in range(3):
        wc.build_digest(now=T0 + timedelta(hours=1))
    assert marker_path.read_bytes() == before_bytes

    # main() without --seen must also leave it untouched (but still emit the digest file)
    monkeypatch.setattr("sys.argv", ["whats_changed.py"])
    wc.main()
    assert marker_path.read_bytes() == before_bytes
    out_path = tmp_path / "automation" / "state" / "whats-changed.json"
    assert out_path.exists()

    # only --seen advances it
    monkeypatch.setattr("sys.argv", ["whats_changed.py", "--seen"])
    wc.main()
    assert marker_path.read_bytes() != before_bytes
    new_marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert wc._parse_iso(new_marker["since_iso"]) is not None


# ------------------------------------------------------------- focused unit tests

@pytest.mark.parametrize("raw", [
    "2026-08-29T12:00:00+00:00",
    "2026-08-29T12:00:00Z",
    "2026-08-29T12:00:00",
    "2026-08-29 12:00:00",
    "2026-08-29T12:00",
    "2026-08-29",
])
def test_parse_iso_accepts_common_formats(raw):
    dt = wc._parse_iso(raw)
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.year == 2026 and dt.month == 8 and dt.day == 29


@pytest.mark.parametrize("raw", [None, "", "not a date", "banana"])
def test_parse_iso_rejects_garbage(raw):
    assert wc._parse_iso(raw) is None


def test_status_known_broken_reads_to_eof_past_interleaved_heading(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path)
    status_dir = tmp_path / "automation" / "overnight"
    status_dir.mkdir(parents=True)
    (status_dir / "STATUS.md").write_text(
        "## Known broken\n\n"
        "- [%s] before, excluded\n"
        "## Kitchen\n"
        "Kitchen: alive\n\n"
        "### DEGRADED: self-check %s\n"
        "- entry appended after the interleaved '## Kitchen' heading\n"
        % (BEFORE.isoformat(), AFTER.isoformat()),
        encoding="utf-8",
    )
    entries = wc.status_known_broken_since(T0)
    # Proves the parser did NOT stop at the interleaved '## Kitchen' heading --
    # the header-style entry living past it was still found. (The parser
    # captures the '### DEGRADED: ...' header line itself, not the bullet
    # text beneath it -- matching real STATUS.md's own header-only entries.)
    assert len(entries) == 1
    assert "DEGRADED" in entries[0]["text"]
    assert entries[0]["ts"] == AFTER.isoformat()


def test_scheduled_task_failures_gated_on_health_surface_freshness(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path)
    state = tmp_path / "automation" / "state"
    state.mkdir(parents=True)
    (state / "unattended-health.json").write_text(json.dumps({
        "checked_at_et": BEFORE.isoformat(),  # stale relative to the marker
        "units": [{"id": "u1", "name": "Something", "status": "RED"}],
    }), encoding="utf-8")
    result = wc.scheduled_task_failures(T0)
    assert result["fresh"] is False
    assert result["units"] == []  # a stale snapshot must never be reported as a new failure


def test_goals_since_classifies_opened_advanced_closed(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path)
    state = tmp_path / "automation" / "state"
    (state / "goals").mkdir(parents=True)
    for name in ("GOAL-ACTIVE-OLD.md", "GOAL-SUPERSEDED.md", "GOAL-UNTOUCHED.md"):
        (state / "goals" / name).write_text("# " + name, encoding="utf-8")
    (state / "active-goal.json").write_text(json.dumps({
        "id": "GOAL-ACTIVE-OLD", "opened_at_et": BEFORE.isoformat(),  # opened before marker
    }), encoding="utf-8")

    touched_map = {
        "GOAL-ACTIVE-OLD.md": AFTER,     # active goal touched again -> advanced
        "GOAL-SUPERSEDED.md": AFTER,     # not active, touched -> closed
        "GOAL-UNTOUCHED.md": BEFORE,     # not touched since marker -> ignored
    }
    monkeypatch.setattr(wc, "_last_touched", lambda p: touched_map.get(p.name))

    goals = wc.goals_since(T0)
    assert goals["opened"] == []
    assert [g["id"] for g in goals["advanced"]] == ["GOAL-ACTIVE-OLD"]
    assert [g["id"] for g in goals["closed"]] == ["GOAL-SUPERSEDED"]
