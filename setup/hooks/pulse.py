"""pulse.py -- the event stream behind the cockpit's Army view.

WHY (2026-08-29): J wants to SEE the orchestrator and the army -- boxes, with a coloured
pulse travelling box-to-box as messages are sent. Research established there is NO passive
tap for that: cross-session messaging rides a point-to-point Windows named pipe
(`\\.\pipe\LOCAL\cc-msg-<32hex>`), only the owning process holds the server handle, and a
filesystem sweep of ~/.claude found no message spool. There is also no receive-side hook.

The ONE place a message edge is observable is the SEND side: a PreToolUse hook matching
`SendMessage` yields exactly (from_session, to_name, summary, ts) -- which IS a pulse edge.

  ⚠️ HONESTY CONSTRAINT, load-bearing: this records messages SENT, never messages
  DELIVERED. A held, expired, refused, or queue-full message still writes a row. Any UI
  built on this must say "sent". A surface implying a delivery it cannot prove is the exact
  class of thing OP-33 exists to prevent, so the legend wording is part of the contract.

Ring-capped (OP-22: every append-only producer gets a retention cap). Read-only w.r.t.
everything else; never blocks a tool call; every failure is swallowed -- telemetry must
never be the reason a hook denies work.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

# GAMMA_PULSE_PATH redirects the sink, matching the GAMMA_ACTIVE_GOAL_PATH pattern in
# gamma_doctrine.py. Needed because the end-to-end tests spawn the real hook as a
# SUBPROCESS -- monkeypatch cannot reach across that boundary, so without this every
# pytest run appended fake rows to production telemetry. Ten per run, and they looked
# exactly like real SendMessage edges that had lost their recipient.
_PULSE = Path(os.environ.get("GAMMA_PULSE_PATH") or (_REPO / "automation" / "state" / "hooks" / "pulse.jsonl"))
_STATE_DIR = _PULSE.parent

# ~2k rows is roughly a full day of a busy 8-worker fan-out, and keeps the tail cheap for a
# 1s poll. Trim is amortised: only rewrite when we are meaningfully over.
MAX_ROWS = 2000
_TRIM_SLACK = 400

# tool name -> (event kind, whether it carries a destination)
_TOOL_EVENTS = {
    "SendMessage": "message",
    "Agent": "spawn",
    "Task": "spawn",
    "Workflow": "spawn",
}


def classify(tool_name: str) -> str | None:
    """Pulse event kind for a tool, or None when the tool is not worth an edge."""
    if not tool_name:
        return None
    if tool_name in _TOOL_EVENTS:
        return _TOOL_EVENTS[tool_name]
    if tool_name in ("Edit", "Write", "NotebookEdit", "MultiEdit", "Bash", "PowerShell"):
        return "act"
    return None


def _target(tool_name: str, tool_input: dict) -> str:
    """Who the edge points at. Empty string means a self-glow, not a travelling pulse."""
    if tool_name == "SendMessage":
        return str(tool_input.get("to") or "")
    if tool_name in ("Agent", "Task"):
        return str(tool_input.get("subagent_type") or tool_input.get("description") or "agent")
    if tool_name == "Workflow":
        return str(tool_input.get("name") or "workflow")
    return ""


def _detail(tool_name: str, tool_input: dict) -> str:
    """One short human string -- the 'last action' chip under a box."""
    if tool_name == "SendMessage":
        return str(tool_input.get("summary") or tool_input.get("message") or "")[:120]
    if tool_name in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        raw = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        return "Editing " + raw.replace("\\", "/").rsplit("/", 1)[-1] if raw else "Editing"
    if tool_name in ("Bash", "PowerShell"):
        return "Ran: " + str(tool_input.get("command") or "")[:100]
    if tool_name in ("Agent", "Task", "Workflow"):
        return str(tool_input.get("description") or tool_input.get("name") or "")[:120]
    return ""


def _trim() -> None:
    """Amortised ring cap. Never raises."""
    try:
        if not _PULSE.exists():
            return
        lines = _PULSE.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) <= MAX_ROWS + _TRIM_SLACK:
            return
        _PULSE.write_text("\n".join(lines[-MAX_ROWS:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def record(payload: dict, event: str, *, to: str = "", detail: str = "", extra: dict | None = None) -> None:
    """Append one pulse row. Swallows every error -- telemetry never blocks a tool call."""
    try:
        row = {
            "ts": dt.datetime.now().isoformat(timespec="seconds"),
            "event": event,
            # session_id + agent_id together are what let the UI attribute a pulse to the
            # right BOX. Without agent_id every worker in a fan-out collapses onto its
            # parent session and the army view shows one node doing everything.
            "session_id": (payload.get("session_id") or "")[:36],
            "agent_id": (payload.get("agent_id") or "")[:36],
            "agent_type": payload.get("agent_type") or "",
            "cwd": payload.get("cwd") or "",
            "tool": payload.get("tool_name") or "",
            "to": to,
            "detail": detail,
        }
        if extra:
            row.update(extra)
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        with _PULSE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        _trim()
    except Exception:
        pass


def record_tool(payload: dict) -> None:
    """PreToolUse entry point: emit an edge if this tool is one the army view draws."""
    tool_name = payload.get("tool_name") or ""
    event = classify(tool_name)
    if event is None:
        return
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    record(
        payload,
        event,
        to=_target(tool_name, tool_input),
        detail=_detail(tool_name, tool_input),
    )
