"""Regression guard for the pulse.jsonl detail-cap widen + `to` extraction (PULSE-WIDEN,
2026-09-15).

WHY: dashboard/lib/hq-agents.ts classifies HQ live-agent persona visits by searching pulse
row text for persona-evidence filenames, but two bugs starved it of real signal:
  1. setup/hooks/pulse.py#_detail wrote `"Ran: " + command[:100]` with no truncation
     marker, so a real command like `python -c "print(open('automation/scout/state/
     scout-feed-summary.json'...` got cut before the filename ever appeared.
  2. Bash/PowerShell rows never populated `to` at all.
This suite proves both fixes: the 240-char cap with a trailing '\u2026' marker on
truncation, and `to` extraction of the first path-like token from the FULL (untruncated)
command, normalized to repo-relative (or basename-only outside the repo).

Run: backtest/.venv/Scripts/python.exe -m pytest setup/hooks/test_pulse_target_extraction.py -q
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOK = _HERE / "gamma_doctrine.py"
_REPO = _HERE.parent.parent

ALLOW = 0


def _pulse_path() -> Path:
    return Path(tempfile.gettempdir()) / f"gamma-test-pulse-{uuid.uuid4().hex}.jsonl"


def run_hook(payload: dict, pulse_path: Path) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["GAMMA_PULSE_PATH"] = str(pulse_path)
    proc = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _read_rows(pulse_path: Path) -> list[dict]:
    if not pulse_path.exists():
        return []
    return [json.loads(line) for line in pulse_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _bash_payload(command: str, tool_name: str = "Bash") -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "session_id": "sess-target",
        "agent_id": "agent-target",
        "agent_type": "general-purpose",
        "tool_name": tool_name,
        "tool_input": {"command": command},
    }


def _fire(command: str, tool_name: str = "Bash") -> dict:
    pulse_path = _pulse_path()
    try:
        code, _, _ = run_hook(_bash_payload(command, tool_name), pulse_path)
        assert code == ALLOW
        rows = _read_rows(pulse_path)
        assert len(rows) == 1
        return rows[0]
    finally:
        pulse_path.unlink(missing_ok=True)


def test_long_command_gets_capped_at_240_with_ellipsis_marker():
    command = "echo " + ("a" * 300)
    row = _fire(command)
    assert row["detail"].startswith("Ran: ")
    body = row["detail"][len("Ran: "):]
    assert len(body) == 241  # 240 chars of command + the marker
    assert body.endswith("\u2026")
    assert body[:240] == command[:240]


def test_short_command_is_not_marked_truncated():
    command = "git status"
    row = _fire(command)
    assert row["detail"] == "Ran: git status"
    assert not row["detail"].endswith("\u2026")


def test_to_extraction_python_dash_c_open_call():
    command = "python -c \"print(open('automation/scout/state/scout-feed-summary.json').read())\""
    row = _fire(command)
    assert row["to"] == "automation/scout/state/scout-feed-summary.json"


def test_to_extraction_powershell_dash_file_path():
    command = "powershell -NoProfile -File setup\\scripts\\dashboard_deploy.ps1 -Tag pulse-widen"
    row = _fire(command, tool_name="PowerShell")
    assert row["to"] == "setup/scripts/dashboard_deploy.ps1"


def test_to_extraction_absolute_windows_path_under_repo_becomes_repo_relative():
    abs_path = str(_REPO / "automation" / "state" / "hooks" / "pulse.jsonl").replace("/", "\\")
    command = f"type {abs_path}"
    row = _fire(command)
    assert row["to"] == "automation/state/hooks/pulse.jsonl"


def test_to_extraction_path_outside_repo_falls_back_to_basename_never_full_home_path():
    command = r"type C:\Users\jackw\Desktop\some-other-project\notes.md"
    row = _fire(command)
    assert row["to"] == "notes.md"
    assert "Users" not in row["to"]
    assert "jackw" not in row["to"]


def test_no_recognizable_path_leaves_to_empty():
    row = _fire("git status")
    assert row["to"] == ""
