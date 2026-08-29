"""Gamma doctrine hooks -- the enforcement layer under CLAUDE.md.

ONE entry point for every hook event. Claude Code passes the event payload on stdin;
this script dispatches on `hook_event_name` and either injects a small, situational
piece of context or hard-blocks an action doctrine says must never happen.

  SessionStart        prime card + live state (re-fires after /compact, where doctrine dies)
  UserPromptSubmit    keyword-routed situational rule (usually nothing)
  PreToolUse          HARD BLOCK: frozen trading path, generated surfaces, scarred shell cmds
  PostToolUseFailure  repeated-identical-failure -> the stop-repeating-it rule
  Stop                HARD BLOCK: turn ends on a permission question (OP-0) or an
                      unverified success claim (OP-33)
  SubagentStart       prime card (built-in Explore/Plan agents skip CLAUDE.md entirely)
  InstructionsLoaded  append-only log of what doctrine actually loaded, and when

SAFETY -- read before editing:
  * FAIL OPEN, ALWAYS. Every path is wrapped; any unexpected error exits 0 = allow.
    A guard that can wedge J's session is the OP-32 lockout scar (2026-05-22) repeating.
  * Kill switch, no restart needed: set GAMMA_HOOKS_OFF=1, or `touch
    automation/state/hooks/OFF`. Full removal: delete the "hooks" key from
    .claude/settings.json (git-tracked, so `git revert` is the off-switch).
  * The Stop guard blocks at most ONCE per session per reason, and honours
    `stop_hook_active`. It cannot loop.
  * Denylists are NARROW and suffix-matched. Anything not explicitly named is allowed.

Invoked as: pythonw.exe gamma_doctrine.py     (verified 2026-08-29: pythonw passes
stdout/stderr/exit-code through Claude Code's pipes and never flashes a console.)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_HERE))

import doctrine as D  # noqa: E402

_STATE_DIR = _REPO / "automation" / "state" / "hooks"
_LOG = _STATE_DIR / "doctrine-hooks.jsonl"
_INSTR_LOG = _STATE_DIR / "instructions-loaded.jsonl"
_OFF_FILE = _STATE_DIR / "OFF"

_ALLOW = 0
_BLOCK = 2


# ---------------------------------------------------------------------------------------
# infrastructure -- none of it may ever raise into the caller
# ---------------------------------------------------------------------------------------
def _log(record: dict) -> None:
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        record["ts"] = dt.datetime.now().isoformat(timespec="seconds")
        with _LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass


def _et_today() -> dt.date:
    """ET date via the DST-aware project clock. Falls back to local date."""
    try:
        sys.path.insert(0, str(_REPO / "setup" / "scripts"))
        from et_clock import et_now  # type: ignore

        return et_now().date()
    except Exception:
        return dt.date.today()


def _et_now_parts() -> tuple[str, bool]:
    """(display string, market_open) -- best effort, never raises."""
    try:
        sys.path.insert(0, str(_REPO / "setup" / "scripts"))
        from et_clock import et_now  # type: ignore

        now = et_now()
        mins = now.hour * 60 + now.minute
        is_open = now.weekday() <= 4 and 570 <= mins <= 955
        return now.strftime("%Y-%m-%d %H:%M ET (%a)"), is_open
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M local"), False


def _session_state(session_id: str) -> tuple[Path, dict]:
    path = _STATE_DIR / f"session-{(session_id or 'unknown')[:16]}.json"
    try:
        return path, json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return path, {}


def _save_session_state(path: Path, data: dict) -> None:
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def _emit(event: str, context: str = "", system_message: str = "") -> None:
    """Write the hookSpecificOutput envelope Claude Code expects on stdout."""
    payload: dict = {"hookEventName": event}
    if context:
        payload["additionalContext"] = context
    if system_message:
        payload["systemMessage"] = system_message
    try:
        sys.stdout.write(json.dumps({"hookSpecificOutput": payload}))
        sys.stdout.flush()
    except Exception:
        pass


def _deny(event: str, reason: str) -> int:
    """Block, using both signalling channels (JSON reason wins; stderr is the fallback)."""
    try:
        sys.stdout.write(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": event,
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }
            )
        )
        sys.stdout.flush()
    except Exception:
        pass
    try:
        sys.stderr.write(reason)
        sys.stderr.flush()
    except Exception:
        pass
    return _BLOCK


def _count_tool_calls_this_turn(transcript_path: str) -> int:
    """Tool calls since the last human message. Used only to catch a claim made with
    zero verification; on any doubt it returns 1 (= 'assume verified', fail open)."""
    try:
        path = Path(transcript_path)
        if not path.is_file():
            return 1
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
        calls = 0
        for line in reversed(lines):
            try:
                rec = json.loads(line)
            except Exception:
                continue
            message = rec.get("message") or {}
            role = message.get("role") or rec.get("type")
            content = message.get("content")
            if role == "user":
                blocks = content if isinstance(content, list) else []
                if not any(
                    isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks
                ):
                    return calls  # reached the human turn boundary
            if isinstance(content, list):
                calls += sum(
                    1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
                )
        return calls
    except Exception:
        return 1


# ---------------------------------------------------------------------------------------
# handlers
# ---------------------------------------------------------------------------------------
def _handle_session_start(payload: dict) -> int:
    when, is_open = _et_now_parts()
    today = _et_today()
    lines = [
        f"Gamma session context ({when}).",
        f"Market: {'OPEN -- no interactive work 09:30-15:55 ET; the heartbeat shares the pool.' if is_open else 'closed.'}",
        D.freeze_banner(today),
        "",
        D.PRIME_CARD.rstrip(),
        "",
        "Doctrine hooks are active: frozen trading-path edits, hand-edits to generated "
        "surfaces, and a turn that ends on a permission question are blocked "
        "deterministically rather than left to judgement. Off-switch: GAMMA_HOOKS_OFF=1.",
    ]
    _emit("SessionStart", "\n".join(lines))
    _log({"event": "SessionStart", "reason": payload.get("reason")})
    return _ALLOW


def _handle_user_prompt(payload: dict) -> int:
    # Field name drifted across versions (prompt -> user_input); read both.
    prompt = payload.get("user_input") or payload.get("prompt") or ""
    notes = D.route_prompt(prompt)
    if not notes:
        return _ALLOW
    _emit("UserPromptSubmit", D.join_notes(notes))
    _log({"event": "UserPromptSubmit", "routes": len(notes)})
    return _ALLOW


def _handle_pre_tool(payload: dict) -> int:
    tool = payload.get("tool_name") or ""
    tin = payload.get("tool_input") or {}

    if tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        file_path = str(tin.get("file_path") or tin.get("notebook_path") or "")
        body = "".join(
            str(tin.get(k) or "") for k in ("new_string", "content", "old_string", "new_source")
        )

        surface = D.generated_surface_hit(file_path)
        if surface:
            return _deny(
                "PreToolUse",
                f"{surface} is generated by {D.GENERATED_GENERATOR}; a hand-edit here is "
                f"overwritten on the next sync, so the change would silently revert. "
                f"Edit the generator or its source data instead.",
            )

        frozen = D.frozen_path_hit(file_path)
        if frozen and D.freeze_active(_et_today()):
            if D.FREEZE_OVERRIDE_TOKEN not in body:
                left = (D.FREEZE_END - _et_today()).days
                return _deny(
                    "PreToolUse",
                    f"{frozen} is on the frozen trading path. The September scoring window "
                    f"({D.FREEZE_START} -> {D.FREEZE_END}, {left}d left) needs 20 clean days "
                    f"for go_live_gate.py; an edit here invalidates it. Pre-registered "
                    f"kill-type risk reductions are exempt -- include "
                    f"{D.FREEZE_OVERRIDE_TOKEN} in the edit to record one.",
                )

    if tool in ("Bash", "PowerShell"):
        command = str(tin.get("command") or "")
        message = D.bash_guard_hit(command)
        if message:
            return _deny("PreToolUse", message)

    return _ALLOW


def _handle_post_tool_failure(payload: dict) -> int:
    """Second identical failure in a session is a loop; name it rather than retry."""
    session_id = payload.get("session_id") or ""
    tin = payload.get("tool_input") or {}
    signature = f"{payload.get('tool_name')}::{str(tin.get('command') or tin.get('file_path') or '')[:160]}"
    path, state = _session_state(session_id)
    fails = state.setdefault("fails", {})
    fails[signature] = fails.get(signature, 0) + 1
    count = fails[signature]
    _save_session_state(path, state)
    if count < 2:
        return _ALLOW
    _emit(
        "PostToolUseFailure",
        f"This exact action has now failed {count}x this session. Re-running it is a loop, "
        f"not progress: read the error text, name the failure signature, and change one "
        f"thing. Silent death with clean stderr on this box means an EXTERNAL kill "
        f"(_shared.ps1#Stop-StaleClaudeProcesses reaps python.exe older than 5 min).",
    )
    _log({"event": "PostToolUseFailure", "signature": signature[:80], "count": count})
    return _ALLOW


def _handle_stop(payload: dict) -> int:
    if payload.get("stop_hook_active"):
        return _ALLOW  # already inside a Stop-hook continuation; never chain

    message = payload.get("last_assistant_message") or ""
    session_id = payload.get("session_id") or ""
    path, state = _session_state(session_id)
    blocked = state.setdefault("stop_blocks", {})

    if D.is_permission_question(message) and not blocked.get("op0"):
        blocked["op0"] = True
        _save_session_state(path, state)
        _log({"event": "Stop", "rule": "OP-0"})
        return _deny(
            "Stop",
            "This turn ends on a permission question about sanctioned work. OP-0: work that "
            "is doctrine-sanctioned, reversible, or paper-only gets done and reported for "
            "REVOKE. Only four things route to J -- arming live money, a secret, an "
            "irreversible external action, a genuine fork with no doctrine default. Do the "
            "work now and report what was done plus how to revert it. (If this IS one of the "
            "four, name which one and the guard stands down.)",
        )

    if not blocked.get("op33"):
        calls = _count_tool_calls_this_turn(payload.get("transcript_path") or "")
        if D.is_unverified_claim(message, calls):
            blocked["op33"] = True
            _save_session_state(path, state)
            _log({"event": "Stop", "rule": "OP-33"})
            return _deny(
                "Stop",
                "This turn claims something works, is fixed, or is verified, but ran no tool "
                "call to check. OP-33: quote a check run this session, or label the claim "
                "UNVERIFIED.",
            )

    _save_session_state(path, state)
    return _ALLOW


def _handle_subagent_start(payload: dict) -> int:
    # Built-in Explore and Plan agents skip CLAUDE.md entirely; custom agents load it but
    # not the parent's auto memory. Either way the prime card has to arrive here.
    _emit("SubagentStart", D.PRIME_CARD.rstrip())
    _log({"event": "SubagentStart", "agent_type": payload.get("agent_type")})
    return _ALLOW


def _handle_instructions_loaded(payload: dict) -> int:
    """The instrument for 'is my doctrine even loading?' -- append-only, no output."""
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        with _INSTR_LOG.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": dt.datetime.now().isoformat(timespec="seconds"),
                        "reason": payload.get("reason"),
                        "files": payload.get("files") or payload.get("paths"),
                        "session_id": (payload.get("session_id") or "")[:16],
                    }
                )
                + "\n"
            )
    except OSError:
        pass
    return _ALLOW


_HANDLERS = {
    "SessionStart": _handle_session_start,
    "UserPromptSubmit": _handle_user_prompt,
    "PreToolUse": _handle_pre_tool,
    "PostToolUseFailure": _handle_post_tool_failure,
    "Stop": _handle_stop,
    "SubagentStart": _handle_subagent_start,
    "InstructionsLoaded": _handle_instructions_loaded,
}


def main() -> int:
    if os.environ.get("GAMMA_HOOKS_OFF") == "1" or _OFF_FILE.exists():
        return _ALLOW
    try:
        raw = sys.stdin.read()
    except Exception:
        return _ALLOW
    if not raw or not raw.strip():
        return _ALLOW
    try:
        payload = json.loads(raw)
    except Exception:
        return _ALLOW
    handler = _HANDLERS.get(payload.get("hook_event_name") or "")
    if handler is None:
        return _ALLOW
    return handler(payload)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # FAIL OPEN -- a broken guard must never wedge a session
        _log({"event": "hook_error", "error": repr(exc)[:300]})
        sys.exit(_ALLOW)
