"""Regression guard for the pulse.jsonl tool-completion row (HQ live-agent BUG-1,
2026-09-14).

Before this, pulse.jsonl recorded a tool STARTING (PreToolUse, P.record_tool) but never
finishing -- `grep -c '"event": "done"' pulse.jsonl` was always 0 in production. A single
long foreground tool call then made dashboard/lib/hq-agents.ts's 3-min idle rule read a
still-working agent as having walked away. This suite proves the completion row now
exists and is keyed the same way hq-agents.ts matches it back to its start row (same
session_id/agent_id/tool), for both the success path (PostToolUse) and the failure path
(PostToolUseFailure).

Run: backtest/.venv/Scripts/python.exe -m pytest setup/hooks/test_pulse_completion.py -q
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


def _base_payload(event: str, **extra) -> dict:
    payload = {
        "hook_event_name": event,
        "session_id": "sess-abc123",
        "agent_id": "agent-xyz789",
        "agent_type": "general-purpose",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
    }
    payload.update(extra)
    return payload


def test_posttooluse_writes_a_done_row_matching_the_start_row():
    pulse_path = _pulse_path()
    try:
        code, _, _ = run_hook(_base_payload("PreToolUse"), pulse_path)
        assert code == ALLOW
        code, _, _ = run_hook(_base_payload("PostToolUse"), pulse_path)
        assert code == ALLOW

        rows = _read_rows(pulse_path)
        assert len(rows) == 2
        start, done = rows
        assert start["event"] == "act"
        assert done["event"] == "done"
        # The exact matching key hq-agents.ts's open-tool-call tracker uses.
        assert done["session_id"] == start["session_id"] == "sess-abc123"
        assert done["agent_id"] == start["agent_id"] == "agent-xyz789"
        assert done["tool"] == start["tool"] == "Bash"
    finally:
        pulse_path.unlink(missing_ok=True)


def test_posttoolusefailure_also_writes_a_done_row_on_the_first_failure():
    """The completion edge must fire on the FIRST failure, not only once the
    repeated-identical-failure counter (_handle_post_tool_failure) reaches 2 -- a
    single failed tool call still finished; it must not stay "open" forever in the
    army view just because it didn't repeat."""
    pulse_path = _pulse_path()
    try:
        run_hook(_base_payload("PreToolUse"), pulse_path)
        code, _, _ = run_hook(_base_payload("PostToolUseFailure"), pulse_path)
        assert code == ALLOW

        rows = _read_rows(pulse_path)
        done_rows = [r for r in rows if r["event"] == "done"]
        assert len(done_rows) == 1
        assert done_rows[0]["tool"] == "Bash"
        assert done_rows[0]["detail"] == "failed"
    finally:
        pulse_path.unlink(missing_ok=True)


def test_posttooluse_skips_tools_the_start_edge_also_skips():
    """A tool classify() never gave a start row to (e.g. a bare Read) must never get a
    completion row either -- a lone "done" with no matching open call would be a bug
    in the other direction."""
    pulse_path = _pulse_path()
    try:
        code, _, _ = run_hook(_base_payload("PostToolUse", tool_name="Read", tool_input={"file_path": "x.py"}), pulse_path)
        assert code == ALLOW
        assert _read_rows(pulse_path) == []
    finally:
        pulse_path.unlink(missing_ok=True)


def test_posttooluse_fails_open_on_malformed_stdin():
    pulse_path = _pulse_path()
    try:
        env = dict(os.environ)
        env["GAMMA_PULSE_PATH"] = str(pulse_path)
        proc = subprocess.run(
            [sys.executable, str(_HOOK)],
            input="not json at all {{{",
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        assert proc.returncode == ALLOW
    finally:
        pulse_path.unlink(missing_ok=True)
