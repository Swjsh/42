"""Tests for gamma_cockpit_army's per-session context-usage bar.

Covers: a transcript with a usage object, one without, a missing transcript
file, a corrupt/truncated line, and the percentage math (incl. clipping).

Run: pytest -v setup/scripts/test_cockpit_context.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

# Direct import (script is in setup/scripts, not a package) -- same pattern
# as the other setup/scripts/test_*.py files in this repo.
_spec = importlib.util.spec_from_file_location(
    "gamma_cockpit_army",
    Path(__file__).parent / "gamma_cockpit_army.py",
)
army = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(army)  # type: ignore[union-attr]


def _assistant_usage_line(input_tokens=2, cache_creation=3000, cache_read=100000, output_tokens=500) -> str:
    return json.dumps({
        "type": "assistant",
        "message": {
            "model": "claude-opus-5",
            "usage": {
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
                "output_tokens": output_tokens,
            },
        },
    })


def _write_transcript(projects_dir: Path, slug: str, session_id: str, lines: list[str]) -> Path:
    d = projects_dir / slug
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{session_id}.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _last_context_tokens
# ---------------------------------------------------------------------------

def test_transcript_with_usage_sums_the_three_input_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(army, "PROJECTS_DIR", tmp_path)
    slug, sid = "proj-a", "sess-1"
    _write_transcript(tmp_path, slug, sid, [
        json.dumps({"type": "user", "message": {"content": "hi"}}),
        _assistant_usage_line(input_tokens=2, cache_creation=3000, cache_read=100000, output_tokens=500),
    ])
    tokens, reason = army._last_context_tokens(slug, sid)
    assert tokens == 2 + 3000 + 100000  # output_tokens deliberately excluded
    assert reason == "transcript_tail"


def test_last_usage_wins_when_multiple_assistant_turns_present(tmp_path, monkeypatch):
    monkeypatch.setattr(army, "PROJECTS_DIR", tmp_path)
    slug, sid = "proj-a", "sess-2"
    _write_transcript(tmp_path, slug, sid, [
        _assistant_usage_line(input_tokens=1, cache_creation=100, cache_read=100, output_tokens=10),
        json.dumps({"type": "user", "message": {"content": "more"}}),
        _assistant_usage_line(input_tokens=2, cache_creation=200, cache_read=200, output_tokens=20),
    ])
    tokens, reason = army._last_context_tokens(slug, sid)
    assert tokens == 2 + 200 + 200
    assert reason == "transcript_tail"


def test_transcript_without_any_usage_object_is_unresolvable(tmp_path, monkeypatch):
    monkeypatch.setattr(army, "PROJECTS_DIR", tmp_path)
    slug, sid = "proj-a", "sess-3"
    _write_transcript(tmp_path, slug, sid, [
        json.dumps({"type": "user", "message": {"content": "hi"}}),
        json.dumps({"type": "system", "subtype": "stop_hook_summary"}),
    ])
    tokens, reason = army._last_context_tokens(slug, sid)
    assert tokens is None
    assert reason == "no_usage_in_tail"


def test_missing_transcript_file_is_unresolvable(tmp_path, monkeypatch):
    monkeypatch.setattr(army, "PROJECTS_DIR", tmp_path)
    tokens, reason = army._last_context_tokens("proj-a", "does-not-exist")
    assert tokens is None
    assert reason == "transcript_unreadable"


def test_empty_slug_is_unresolvable(tmp_path, monkeypatch):
    monkeypatch.setattr(army, "PROJECTS_DIR", tmp_path)
    tokens, reason = army._last_context_tokens("", "sess-1")
    assert tokens is None
    assert reason == "no_cwd"


def test_corrupt_line_is_skipped_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(army, "PROJECTS_DIR", tmp_path)
    slug, sid = "proj-a", "sess-4"
    _write_transcript(tmp_path, slug, sid, [
        _assistant_usage_line(input_tokens=5, cache_creation=50, cache_read=500, output_tokens=1),
        '{"type":"assistant","message":{"usage":{"input_tokens":9999',  # truncated/corrupt JSON
    ])
    # The corrupt line must not raise and must not overwrite the last GOOD reading.
    tokens, reason = army._last_context_tokens(slug, sid)
    assert tokens == 5 + 50 + 500
    assert reason == "transcript_tail"


def test_usage_field_wrong_type_is_skipped_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(army, "PROJECTS_DIR", tmp_path)
    slug, sid = "proj-a", "sess-5"
    _write_transcript(tmp_path, slug, sid, [
        _assistant_usage_line(input_tokens=1, cache_creation=10, cache_read=10, output_tokens=1),
        json.dumps({"type": "assistant", "message": {"usage": "not-a-dict"}}),
    ])
    tokens, reason = army._last_context_tokens(slug, sid)
    assert tokens == 1 + 10 + 10
    assert reason == "transcript_tail"


def test_tail_read_finds_usage_beyond_a_huge_earlier_line(tmp_path, monkeypatch):
    """A single oversized line (e.g. a long tool result) earlier in the file
    must not push the real tail read past CONTEXT_TAIL_BYTES."""
    monkeypatch.setattr(army, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(army, "CONTEXT_TAIL_BYTES", 2000)
    slug, sid = "proj-a", "sess-6"
    huge = json.dumps({"type": "user", "message": {"content": "x" * 50000}})
    _write_transcript(tmp_path, slug, sid, [
        huge,
        _assistant_usage_line(input_tokens=3, cache_creation=30, cache_read=300, output_tokens=3),
    ])
    tokens, reason = army._last_context_tokens(slug, sid)
    assert tokens == 3 + 30 + 300
    assert reason == "transcript_tail"


# ---------------------------------------------------------------------------
# _auto_compact_window_for
# ---------------------------------------------------------------------------

def test_global_settings_autocompact_window(tmp_path, monkeypatch):
    global_settings = tmp_path / "global-settings.json"
    global_settings.write_text(json.dumps({"autoCompactWindow": 800000}), encoding="utf-8")
    monkeypatch.setattr(army, "GLOBAL_SETTINGS_PATH", global_settings)
    cache: dict = {}
    limit, origin = army._auto_compact_window_for(str(tmp_path / "some-project"), cache)
    assert limit == 800000
    assert origin == "global"


def test_project_local_settings_override_global(tmp_path, monkeypatch):
    global_settings = tmp_path / "global-settings.json"
    global_settings.write_text(json.dumps({"autoCompactWindow": 800000}), encoding="utf-8")
    monkeypatch.setattr(army, "GLOBAL_SETTINGS_PATH", global_settings)

    project_dir = tmp_path / "myproject"
    (project_dir / ".claude").mkdir(parents=True)
    (project_dir / ".claude" / "settings.json").write_text(
        json.dumps({"autoCompactWindow": 500000}), encoding="utf-8",
    )
    cache: dict = {}
    limit, origin = army._auto_compact_window_for(str(project_dir), cache)
    assert limit == 500000
    assert origin == "project"


def test_missing_settings_files_are_unresolvable(tmp_path, monkeypatch):
    monkeypatch.setattr(army, "GLOBAL_SETTINGS_PATH", tmp_path / "no-such-file.json")
    cache: dict = {}
    limit, origin = army._auto_compact_window_for(str(tmp_path / "some-project"), cache)
    assert limit is None
    assert origin == "settings_unreadable"


def test_settings_cache_is_reused_per_cwd(tmp_path, monkeypatch):
    global_settings = tmp_path / "global-settings.json"
    global_settings.write_text(json.dumps({"autoCompactWindow": 800000}), encoding="utf-8")
    monkeypatch.setattr(army, "GLOBAL_SETTINGS_PATH", global_settings)
    cache: dict = {}
    cwd = str(tmp_path / "some-project")
    first = army._auto_compact_window_for(cwd, cache)
    # Delete the settings file; a cached result must not require re-reading it.
    global_settings.unlink()
    second = army._auto_compact_window_for(cwd, cache)
    assert first == second == (800000, "global")


# ---------------------------------------------------------------------------
# _context_usage -- the combined field the payload actually carries
# ---------------------------------------------------------------------------

def test_context_usage_percentage_math(tmp_path, monkeypatch):
    monkeypatch.setattr(army, "PROJECTS_DIR", tmp_path)
    global_settings = tmp_path / "global-settings.json"
    global_settings.write_text(json.dumps({"autoCompactWindow": 800000}), encoding="utf-8")
    monkeypatch.setattr(army, "GLOBAL_SETTINGS_PATH", global_settings)

    slug, sid = "proj-a", "sess-pct"
    _write_transcript(tmp_path, slug, sid, [
        _assistant_usage_line(input_tokens=0, cache_creation=200000, cache_read=200000, output_tokens=1),
    ])
    cache: dict = {}
    out = army._context_usage(slug, sid, str(tmp_path / "proj"), cache)
    assert out["context_tokens"] == 400000
    assert out["context_limit"] == 800000
    assert out["context_pct"] == 50.0
    assert out["context_source"] == "transcript_tail+global_autoCompactWindow"


def test_context_usage_pct_clipped_at_100(tmp_path, monkeypatch):
    """Usage can momentarily exceed autoCompactWindow before compaction
    actually fires -- the bar must never report over 100%."""
    monkeypatch.setattr(army, "PROJECTS_DIR", tmp_path)
    global_settings = tmp_path / "global-settings.json"
    global_settings.write_text(json.dumps({"autoCompactWindow": 800000}), encoding="utf-8")
    monkeypatch.setattr(army, "GLOBAL_SETTINGS_PATH", global_settings)

    slug, sid = "proj-a", "sess-over"
    _write_transcript(tmp_path, slug, sid, [
        _assistant_usage_line(input_tokens=0, cache_creation=500000, cache_read=500000, output_tokens=1),
    ])
    cache: dict = {}
    out = army._context_usage(slug, sid, str(tmp_path / "proj"), cache)
    assert out["context_tokens"] == 1000000
    assert out["context_pct"] == 100.0


def test_context_usage_unknown_when_tokens_unresolvable(tmp_path, monkeypatch):
    monkeypatch.setattr(army, "PROJECTS_DIR", tmp_path)
    global_settings = tmp_path / "global-settings.json"
    global_settings.write_text(json.dumps({"autoCompactWindow": 800000}), encoding="utf-8")
    monkeypatch.setattr(army, "GLOBAL_SETTINGS_PATH", global_settings)

    cache: dict = {}
    out = army._context_usage("proj-a", "does-not-exist", str(tmp_path / "proj"), cache)
    assert out["context_source"] == army.CONTEXT_UNKNOWN
    assert out["context_tokens"] == 0
    assert out["context_limit"] == 0
    assert out["context_pct"] == 0.0


def test_context_usage_unknown_when_limit_unresolvable(tmp_path, monkeypatch):
    monkeypatch.setattr(army, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(army, "GLOBAL_SETTINGS_PATH", tmp_path / "no-such-file.json")

    slug, sid = "proj-a", "sess-noLimit"
    _write_transcript(tmp_path, slug, sid, [
        _assistant_usage_line(input_tokens=1, cache_creation=10, cache_read=10, output_tokens=1),
    ])
    cache: dict = {}
    out = army._context_usage(slug, sid, str(tmp_path / "proj"), cache)
    assert out["context_source"] == army.CONTEXT_UNKNOWN
    assert out["context_tokens"] == 0
    assert out["context_limit"] == 0


def test_context_usage_never_raises_on_double_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(army, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(army, "GLOBAL_SETTINGS_PATH", tmp_path / "no-such-file.json")
    cache: dict = {}
    out = army._context_usage("proj-a", "does-not-exist", str(tmp_path / "proj"), cache)
    assert out["context_source"] == army.CONTEXT_UNKNOWN


# ---------------------------------------------------------------------------
# build_army() integration -- fields land on the session dict with the right
# types, and a session with no resolvable data still gets the "unknown" shape.
# ---------------------------------------------------------------------------

def test_build_army_session_dict_carries_context_fields(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    global_settings = tmp_path / "global-settings.json"
    global_settings.write_text(json.dumps({"autoCompactWindow": 800000}), encoding="utf-8")

    monkeypatch.setattr(army, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(army, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(army, "GLOBAL_SETTINGS_PATH", global_settings)
    monkeypatch.setattr(army, "PULSE_JSONL", tmp_path / "pulse.jsonl")
    monkeypatch.setattr(army, "_pid_alive", lambda pid: True)

    cwd = str(tmp_path / "repo")
    slug = army._slug_for(cwd)
    sid = "11111111-1111-1111-1111-111111111111"
    (sessions_dir / "111.json").write_text(json.dumps({
        "pid": 111, "sessionId": sid, "cwd": cwd, "startedAt": 1700000000000,
        "name": "test-session", "kind": "interactive", "version": "2.1.246",
    }), encoding="utf-8")
    _write_transcript(projects_dir, slug, sid, [
        _assistant_usage_line(input_tokens=0, cache_creation=80000, cache_read=0, output_tokens=1),
    ])

    payload = army.build_army()
    assert len(payload["sessions"]) == 1
    s = payload["sessions"][0]
    assert s["context_tokens"] == 80000
    assert s["context_limit"] == 800000
    assert s["context_pct"] == 10.0
    assert s["context_source"] == "transcript_tail+global_autoCompactWindow"
    assert isinstance(s["context_tokens"], int)
    assert isinstance(s["context_limit"], int)
    assert isinstance(s["context_pct"], float)
    assert isinstance(s["context_source"], str)


def test_build_army_unknown_session_still_typed(tmp_path, monkeypatch):
    """A session with no transcript at all still gets int/float-typed fields
    plus the literal "unknown" source -- never omitted, never fabricated."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    monkeypatch.setattr(army, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(army, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(army, "GLOBAL_SETTINGS_PATH", tmp_path / "no-such-file.json")
    monkeypatch.setattr(army, "PULSE_JSONL", tmp_path / "pulse.jsonl")
    monkeypatch.setattr(army, "_pid_alive", lambda pid: True)

    cwd = str(tmp_path / "repo2")
    sid = "22222222-2222-2222-2222-222222222222"
    (sessions_dir / "222.json").write_text(json.dumps({
        "pid": 222, "sessionId": sid, "cwd": cwd, "startedAt": 1700000000000,
        "name": "no-transcript", "kind": "interactive", "version": "2.1.246",
    }), encoding="utf-8")
    # No transcript file written for this session at all.

    payload = army.build_army()
    s = payload["sessions"][0]
    assert s["context_source"] == "unknown"
    assert s["context_tokens"] == 0
    assert s["context_limit"] == 0
    assert s["context_pct"] == 0.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
