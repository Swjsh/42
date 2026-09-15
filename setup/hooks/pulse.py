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
import re
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


_TARGET_MAX_LEN = 120  # matches _detail's cap; see test_pulse_target_to_field_is_bounded

# HQ live-agent persona classification reads pulse rows for filename evidence
# (dashboard/lib/hq-agents.ts PERSONA_EVIDENCE_RULES) but Bash/PowerShell rows never
# populated `to`, and the old 100-char, no-marker `detail` cap silently cut real commands
# before the filename ever appeared (e.g. `python -c "print(open('automation/scout/
# state/scout-feed-summary.json'...` never reaches char 100). Widened 2026-09-15:
# `detail` grows to 240 chars with a trailing '…' marker on truncation so a consumer
# can detect truncation without an exact-length heuristic (the old 100-char/no-marker
# rows stay readable as a separate historical case -- see hq-agents.ts's own
# isTruncatedBashDetail), and `to` is now populated for Bash/PowerShell from the first
# path-like token in the FULL (untruncated) command.
_BASH_DETAIL_CAP = 240
_TRUNCATION_MARKER = "…"  # single-char ellipsis, not "..." -- keeps the cap exact

# Extensions worth surfacing as a persona-evidence target. Kept narrow and explicit
# (never a catch-all) so `to` only ever holds something that looks like a real repo
# artifact, never an arbitrary command-line word that happens to contain a dot.
_TARGET_EXTENSIONS = ("json", "jsonl", "md", "py", "ps1", "ts", "tsx", "csv")

# A path-like token: word chars, dots, slashes (either direction), colons (Windows drive
# letters), and hyphens/underscores, ending in one of the known extensions. Quotes,
# parens, and other command-syntax characters are NOT in the class, so the regex
# naturally stops at the surrounding `'...'` / `"..."` a `python -c` one-liner wraps the
# path in -- no separate quote-stripping pass needed.
_PATH_TOKEN_RE = re.compile(r"[A-Za-z0-9_./\\:-]+\.(?:" + "|".join(_TARGET_EXTENSIONS) + r")\b")

_REPO_POSIX = str(_REPO).replace("\\", "/")


def _to_repo_relative_or_basename(token: str) -> str:
    """Normalize a path-like token for the `to` field.

    Repo-relative when the token is an absolute path under the repo root; basename-only
    otherwise (covers absolute paths outside the repo, e.g. a user home directory -- this
    hook must never write a user home path into telemetry). A relative token is returned
    with backslashes normalized to forward slashes and any leading "./" stripped.
    """
    normalized = token.replace("\\", "/")
    is_absolute = normalized.startswith("/") or bool(re.match(r"^[A-Za-z]:/", normalized))
    if is_absolute:
        prefix = _REPO_POSIX + "/"
        if normalized.lower().startswith(prefix.lower()):
            return normalized[len(prefix):]
        return normalized.rsplit("/", 1)[-1]
    return normalized[2:] if normalized.startswith("./") else normalized


def _first_path_target(command: str) -> str:
    """First path-like token in `command` (the FULL, untruncated command), bounded to
    _TARGET_MAX_LEN. Empty string when the command names no recognizable file."""
    match = _PATH_TOKEN_RE.search(command)
    if not match:
        return ""
    return _to_repo_relative_or_basename(match.group(0))[:_TARGET_MAX_LEN]


def _target(tool_name: str, tool_input: dict) -> str:
    """Who the edge points at. Empty string means a self-glow, not a travelling pulse.

    Bounded like every other row field: an oversized `to` (bug, or a payload built from
    untrusted/attacker-controlled text) must not produce an unbounded JSONL row. MAX_ROWS
    caps row COUNT, not bytes -- an unbounded single row defeats that cap's byte budget,
    and since _trim() reads the whole file on every call, an inflated file quietly taxes
    every later PreToolUse hook for the rest of the session. Verified 2026-08-29: an
    unbounded `to` field grew one row past 1MB and pushed per-call hook overhead from
    ~8ms at an empty file to ~30ms at 20MB, scaling linearly with file size.
    """
    if tool_name == "SendMessage":
        return str(tool_input.get("to") or "")[:_TARGET_MAX_LEN]
    if tool_name in ("Agent", "Task"):
        return str(tool_input.get("subagent_type") or tool_input.get("description") or "agent")[:_TARGET_MAX_LEN]
    if tool_name == "Workflow":
        return str(tool_input.get("name") or "workflow")[:_TARGET_MAX_LEN]
    if tool_name in ("Bash", "PowerShell"):
        return _first_path_target(str(tool_input.get("command") or ""))
    return ""


def _detail(tool_name: str, tool_input: dict) -> str:
    """One short human string -- the 'last action' chip under a box."""
    if tool_name == "SendMessage":
        return str(tool_input.get("summary") or tool_input.get("message") or "")[:120]
    if tool_name in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        raw = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        return "Editing " + raw.replace("\\", "/").rsplit("/", 1)[-1] if raw else "Editing"
    if tool_name in ("Bash", "PowerShell"):
        command = str(tool_input.get("command") or "")
        marker = _TRUNCATION_MARKER if len(command) > _BASH_DETAIL_CAP else ""
        return "Ran: " + command[:_BASH_DETAIL_CAP] + marker
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


def record_tool_done(payload: dict, *, failed: bool = False) -> None:
    """PostToolUse / PostToolUseFailure entry point -- the completion half of
    record_tool()'s start edge (HQ live-agent BUG-1, 2026-09-14).

    Until this existed, pulse.jsonl only ever recorded a tool STARTING
    (PreToolUse), never finishing: `grep -c '"event": "done"' pulse.jsonl` was
    always 0. dashboard/lib/hq-agents.ts's 3-min idle rule reads "no new row
    for 3 min" as "the agent walked away", so one long foreground tool call
    (verified case: a 244s probe, 23:30:32 -> 23:34:36 local) made a
    still-working agent look idle and despawn mid-work.

    This writes a matching "done" row keyed the same way hq-agents.ts already
    matches a start to its completion: same session_id/agent_id (via
    record()'s own payload-derived fields) + same tool name (row.tool). The
    consumer only needs to know THIS tool call finished, not whether it
    succeeded, so both PostToolUse and PostToolUseFailure write the identical
    "done" event -- `failed` only changes the diagnostic `detail` string, it
    is not part of the matching key.

    Gated by the same classify() the start edge used: a tool that never got a
    start row (classify() returns None) must never get a completion row
    either, or hq-agents.ts would see a "done" with no matching open call.
    """
    tool_name = payload.get("tool_name") or ""
    if classify(tool_name) is None:
        return
    record(payload, "done", detail="failed" if failed else "ok")
