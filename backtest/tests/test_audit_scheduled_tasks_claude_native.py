"""Guard: audit_scheduled_tasks.py sees Claude-native scheduled skills too.

AUDIT-BLINDSPOT-CLAUDE-NATIVE-TASKS (queue.md, filed 2026-07-25): the audit only ever
knew about Gamma_* Windows Task Scheduler entries. A SEPARATE scheduling mechanism --
Claude-native scheduled skills at ~/.claude/scheduled-tasks/<name>/SKILL.md -- was
completely invisible, which is how `gamma-sniper-shadow-eod` (a daily opus fire, ~$100/mo)
ran ungoverned for 2 months. These tests RED-proof the fix: any un-allowlisted task under
that directory must be flagged, and the flag must fail OPEN (never raise) when the
directory is absent or a SKILL.md is malformed.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "setup" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

audit_scheduled_tasks = importlib.import_module("audit_scheduled_tasks")


def _write_skill(base: Path, dirname: str, name: str | None) -> None:
    d = base / dirname
    d.mkdir(parents=True, exist_ok=True)
    if name is not None:
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: test fixture\n---\n\nBody text.\n",
            encoding="utf-8",
        )


class TestClaudeNativeTaskEnumeration:
    def test_missing_directory_returns_empty(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        assert audit_scheduled_tasks._claude_native_tasks(missing) == []

    def test_finds_named_task_from_frontmatter(self, tmp_path):
        _write_skill(tmp_path, "gamma-sniper-shadow-eod", "gamma-sniper-shadow-eod")
        out = audit_scheduled_tasks._claude_native_tasks(tmp_path)
        assert len(out) == 1
        assert out[0]["name"] == "gamma-sniper-shadow-eod"
        assert out[0]["dir"].endswith("gamma-sniper-shadow-eod")

    def test_falls_back_to_dirname_when_skill_md_missing(self, tmp_path):
        (tmp_path / "some-task").mkdir()
        out = audit_scheduled_tasks._claude_native_tasks(tmp_path)
        assert out == [{"name": "some-task", "dir": str(tmp_path / "some-task")}]

    def test_ignores_files_at_top_level(self, tmp_path):
        (tmp_path / "not-a-task-dir.txt").write_text("noise", encoding="utf-8")
        assert audit_scheduled_tasks._claude_native_tasks(tmp_path) == []

    def test_multiple_tasks_sorted(self, tmp_path):
        _write_skill(tmp_path, "b-task", "b-task")
        _write_skill(tmp_path, "a-task", "a-task")
        out = audit_scheduled_tasks._claude_native_tasks(tmp_path)
        assert [t["name"] for t in out] == ["a-task", "b-task"]

    def test_never_scans_a_retired_sibling_directory(self, tmp_path):
        # The retired dir is a SEPARATE path entirely -- passing the live dir must never
        # pick up entries that live only under a "-retired-" sibling.
        live = tmp_path / "scheduled-tasks"
        retired = tmp_path / "scheduled-tasks-retired-2026-07-25"
        _write_skill(retired, "gamma-sniper-shadow-eod", "gamma-sniper-shadow-eod")
        assert audit_scheduled_tasks._claude_native_tasks(live) == []


class TestClaudeNativeGovernanceFlag:
    def test_ungoverned_task_flagged(self, monkeypatch, tmp_path):
        native_dir = tmp_path / "scheduled-tasks"
        _write_skill(native_dir, "sneaky-opus-loop", "sneaky-opus-loop")
        monkeypatch.setattr(audit_scheduled_tasks, "CLAUDE_NATIVE_TASKS_DIR", native_dir)
        monkeypatch.setattr(audit_scheduled_tasks, "KNOWN_CLAUDE_NATIVE_TASKS", set())

        flags: list[dict] = []
        for ct in audit_scheduled_tasks._claude_native_tasks():
            if ct["name"] not in audit_scheduled_tasks.KNOWN_CLAUDE_NATIVE_TASKS:
                flags.append({"flag": "CLAUDE_NATIVE_TASK_UNGOVERNED", "task": ct["name"]})
        assert len(flags) == 1
        assert flags[0]["task"] == "sneaky-opus-loop"

    def test_allowlisted_task_not_flagged(self, monkeypatch, tmp_path):
        native_dir = tmp_path / "scheduled-tasks"
        _write_skill(native_dir, "reviewed-task", "reviewed-task")
        monkeypatch.setattr(audit_scheduled_tasks, "CLAUDE_NATIVE_TASKS_DIR", native_dir)
        monkeypatch.setattr(audit_scheduled_tasks, "KNOWN_CLAUDE_NATIVE_TASKS", {"reviewed-task"})

        flags: list[dict] = []
        for ct in audit_scheduled_tasks._claude_native_tasks():
            if ct["name"] not in audit_scheduled_tasks.KNOWN_CLAUDE_NATIVE_TASKS:
                flags.append({"flag": "CLAUDE_NATIVE_TASK_UNGOVERNED", "task": ct["name"]})
        assert flags == []

    def test_no_native_dir_never_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(audit_scheduled_tasks, "CLAUDE_NATIVE_TASKS_DIR",
                             tmp_path / "nonexistent")
        assert audit_scheduled_tasks._claude_native_tasks() == []


class TestAuditIntegration:
    """Full `audit()` wiring -- the actual regression this fix guards against."""

    def _fake_registered_tasks(self):
        return [{
            "name": "Gamma_Sample", "state": "Ready",
            "execute": "wscript.exe", "arguments": "//nologo run_exe_hidden.vbs pythonw.exe x.ps1",
            "last_run": None, "last_result": 0, "next_run": None,
        }]

    def test_audit_flags_ungoverned_claude_native_task(self, monkeypatch, tmp_path):
        registry = tmp_path / "SCHEDULED-TASKS.md"
        registry.write_text(
            "## Active tasks (current production)\n\n| `Gamma_Sample` | ... |\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(audit_scheduled_tasks, "REGISTRY_PATH", registry)
        monkeypatch.setattr(audit_scheduled_tasks, "_registered_tasks",
                             self._fake_registered_tasks)
        monkeypatch.setattr(audit_scheduled_tasks, "_audit_hooks", lambda: [])

        native_dir = tmp_path / "scheduled-tasks"
        _write_skill(native_dir, "ungoverned-loop", "ungoverned-loop")
        monkeypatch.setattr(audit_scheduled_tasks, "CLAUDE_NATIVE_TASKS_DIR", native_dir)
        monkeypatch.setattr(audit_scheduled_tasks, "KNOWN_CLAUDE_NATIVE_TASKS", set())

        out = audit_scheduled_tasks.audit()
        native_flags = [f for f in out["flags"] if f["flag"] == "CLAUDE_NATIVE_TASK_UNGOVERNED"]
        assert len(native_flags) == 1
        assert native_flags[0]["task"] == "ungoverned-loop"
        assert out["claude_native_registered"] == 1
        assert out["health"] == "RED"

    def test_audit_clean_when_native_dir_empty(self, monkeypatch, tmp_path):
        registry = tmp_path / "SCHEDULED-TASKS.md"
        registry.write_text(
            "## Active tasks (current production)\n\n| `Gamma_Sample` | ... |\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(audit_scheduled_tasks, "REGISTRY_PATH", registry)
        monkeypatch.setattr(audit_scheduled_tasks, "_registered_tasks",
                             self._fake_registered_tasks)
        monkeypatch.setattr(audit_scheduled_tasks, "_audit_hooks", lambda: [])
        monkeypatch.setattr(audit_scheduled_tasks, "CLAUDE_NATIVE_TASKS_DIR",
                             tmp_path / "scheduled-tasks")
        monkeypatch.setattr(audit_scheduled_tasks, "KNOWN_CLAUDE_NATIVE_TASKS", set())

        out = audit_scheduled_tasks.audit()
        assert out["claude_native_registered"] == 0
        assert not any(f["flag"] == "CLAUDE_NATIVE_TASK_UNGOVERNED" for f in out["flags"])
        assert out["health"] == "GREEN"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
