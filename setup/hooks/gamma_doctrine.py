"""Gamma doctrine hooks -- the enforcement layer under CLAUDE.md.

ONE entry point for every hook event. Claude Code passes the event payload on stdin;
this script dispatches on `hook_event_name` and either injects a small, situational
piece of context or hard-blocks an action doctrine says must never happen.

  SessionStart        prime card + live state (re-fires after /compact, where doctrine dies)
  UserPromptSubmit    keyword-routed situational rule (usually nothing)
  PreToolUse          HARD BLOCK: frozen trading path, generated surfaces, scarred shell cmds
  PostToolUseFailure  repeated-identical-failure -> the stop-repeating-it rule
  Stop                HARD BLOCK: turn ends on a permission question (OP-0), an
                      unverified success claim (OP-33), or an active unexpired
                      goal (automation/state/active-goal.json) still has an open
                      QUEUE item -- bounded by a hard per-session counter and a
                      convergence stop (see _check_goal_continuation)
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
import pulse as P  # noqa: E402

_STATE_DIR = _REPO / "automation" / "state" / "hooks"
_LOG = _STATE_DIR / "doctrine-hooks.jsonl"
_INSTR_LOG = _STATE_DIR / "instructions-loaded.jsonl"
_OFF_FILE = _STATE_DIR / "OFF"

# GAMMA_ACTIVE_GOAL_PATH lets tests point this at a throwaway file instead of the real
# automation/state/active-goal.json -- so a goal-continuation test run never risks a
# real conductor fire reading a stray test fixture off disk.
_ACTIVE_GOAL = Path(
    os.environ.get("GAMMA_ACTIVE_GOAL_PATH") or str(_REPO / "automation" / "state" / "active-goal.json")
)

_ALLOW = 0
_BLOCK = 2


# ---------------------------------------------------------------------------------------
# infrastructure -- none of it may ever raise into the caller
# ---------------------------------------------------------------------------------------
_LOG_MAX_ROWS = 2000


def _log(record: dict, payload: dict | None = None) -> None:
    """Append to the doctrine log.

    `payload` is threaded through so every row carries session_id/agent_id: without them,
    8 concurrent workers all write timestamp-only rows and per-box attribution in the Army
    view is impossible (they collapse onto one node). Ring-capped per OP-22 -- this
    producer had no retention cap when first shipped, which was a defect.
    """
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        record["ts"] = dt.datetime.now().isoformat(timespec="seconds")
        if payload:
            record.setdefault("session_id", (payload.get("session_id") or "")[:36])
            record.setdefault("agent_id", (payload.get("agent_id") or "")[:36])
        with _LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        lines = _LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) > _LOG_MAX_ROWS + 400:
            _LOG.write_text("\n".join(lines[-_LOG_MAX_ROWS:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def _et_today() -> dt.date:
    """ET date via the DST-aware project clock. Falls back to local date.

    GAMMA_FREEZE_TODAY_OVERRIDE (test-only, "YYYY-MM-DD") lets a test simulate a
    date inside the September freeze window without waiting for the real clock to
    reach it -- before this seam existed, nothing could prove end-to-end (real
    subprocess, real dispatcher) that the frozen-path PreToolUse block actually
    fires once FREEZE_START arrives; only the pure freeze_active()/frozen_path_hit()
    predicates were exercised. Mirrors the existing GAMMA_ACTIVE_GOAL_PATH /
    GAMMA_PULSE_PATH test-seam pattern in this same module. Unset in production.
    """
    override = os.environ.get("GAMMA_FREEZE_TODAY_OVERRIDE")
    if override:
        try:
            return dt.date.fromisoformat(override)
        except Exception:
            pass
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


def _et_now_datetime() -> dt.datetime:
    """Naive ET wall-clock datetime, DST-aware. Falls back to local time -- an
    unreadable clock must never be the reason a goal reads as expired-or-not
    incorrectly; goal_expired() itself still fails toward "expired" on any
    downstream parse error, so this fallback is a second, cheap safety net."""
    try:
        sys.path.insert(0, str(_REPO / "setup" / "scripts"))
        from et_clock import et_now  # type: ignore

        return et_now().replace(tzinfo=None)
    except Exception:
        return dt.datetime.now()


def _load_active_goal() -> dict | None:
    """Read + validate active-goal.json. Missing file, malformed JSON, a non-dict
    body, or `active` not truthy all mean the same thing: no goal work is owed."""
    try:
        if not _ACTIVE_GOAL.is_file():
            return None
        goal = json.loads(_ACTIVE_GOAL.read_text(encoding="utf-8"))
        if not isinstance(goal, dict) or not goal.get("active"):
            return None
        return goal
    except Exception:
        return None


def _load_goal_file_text(goal: dict) -> str:
    """The goal .md body, or "" on anything unreadable (unset field, missing file,
    permission error) -- an unreadable goal file has no open item, by construction."""
    try:
        rel = str(goal.get("file") or "")
        if not rel:
            return ""
        candidate = Path(rel)
        path = candidate if candidate.is_absolute() else _REPO / rel
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _write_goal_last_item(item: str) -> None:
    """Persist the item just named in active-goal.json so the NEXT block (this
    session or a later one) can tell whether the goal actually moved -- the
    convergence brake. Best-effort: a failure here must not turn into a block."""
    try:
        goal = json.loads(_ACTIVE_GOAL.read_text(encoding="utf-8"))
        if not isinstance(goal, dict):
            return
        goal["last_next_item"] = item
        _ACTIVE_GOAL.write_text(json.dumps(goal), encoding="utf-8")
    except Exception:
        pass


def _check_goal_continuation(state: dict) -> int | None:
    """Stop hook, third clause. Returns a _deny() block code, or None to let the
    stop fall through to _ALLOW. Every step fails toward None -- absence of
    active-goal.json is the common case on most machines/sessions and must never
    read as a block."""
    try:
        goal = _load_active_goal()
        if goal is None:
            return None
        if D.goal_expired(str(goal.get("expires_at_et") or ""), _et_now_datetime()):
            return None
        item = D.goal_next_open_item(_load_goal_file_text(goal))
        if not item:
            return None
        n = int(state.get("goal_continuations") or 0)
        max_n = D.goal_max_continuations(goal)
        last_next_item = goal.get("last_next_item")
        if not D.goal_should_continue(item, last_next_item, n, max_n):
            return None
        state["goal_continuations"] = n + 1
        _write_goal_last_item(item)
        reason = D.goal_continuation_reason(
            str(goal.get("id") or "GOAL"), item, str(goal.get("file") or ""), n + 1, max_n
        )
        _log({"event": "Stop", "rule": "goal-continuation", "n": n + 1})
        return _deny("Stop", reason)
    except Exception:
        return None


def _session_state(session_id: str) -> tuple[Path, dict]:
    """(path, state dict). A missing file, unreadable file, or malformed JSON all
    return {} -- the common empty-state case. A file holding syntactically VALID
    JSON that is not an object (a list, a number, a bare string) used to be
    returned as-is: every caller immediately does `state.setdefault(...)`, which
    raises on a non-dict and is swallowed by main()'s top-level fail-open catch --
    so the call falls back to _ALLOW, but SILENTLY and PERMANENTLY for that
    session_id, since nothing ever repairs the file. Confirmed live 2026-08-29:
    a session-*.json containing `["not","a","dict"]` made the OP-0 Stop guard
    return 0 on a message that should have been denied (2 on a clean session),
    with no visible signal beyond a generic hook_error log row. Coercing to {}
    here, matching the same isinstance guard _load_active_goal already uses for
    the sibling goal-file case, makes a malformed state file behave exactly like
    a missing one -- state resets for that session rather than the Stop guard
    going dark for its remaining lifetime.
    """
    path = _STATE_DIR / f"session-{(session_id or 'unknown')[:16]}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return path, data if isinstance(data, dict) else {}
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


# The stderr channel lands on a Windows console whose codepage is not UTF-8, so a smart
# dash or curly quote arrives as a replacement glyph. Observed twice on 2026-08-29: the
# goal-continuation block rendered "Step 4 <?> Action cards", because goal-file prose is
# copied verbatim into the message. A garbled instruction in the loop's PRIMARY feedback
# channel is a real defect, not a cosmetic one -- this is how an autonomous session is told
# what to do next. json.dumps() already escapes the stdout copy (ensure_ascii defaults True).
_ASCII_FOLD = str.maketrans({
    "—": "--", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", " ": " ",
    "→": "->", "≥": ">=", "≤": "<=", "×": "x",
})


def _ascii_safe(text: str) -> str:
    """Fold typographic characters, then drop anything still non-ASCII."""
    return (text or "").translate(_ASCII_FOLD).encode("ascii", "ignore").decode("ascii")


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
        sys.stderr.write(_ascii_safe(reason))
        sys.stderr.flush()
    except Exception:
        pass
    return _BLOCK


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _turn_context(transcript_path: str) -> tuple[int, str]:
    """(tool calls since the last human message, that human message's text).

    Used only to catch a success claim made with zero verification. On ANY doubt it
    returns (1, "") -- "assume verified", i.e. fail open.
    """
    try:
        path = Path(transcript_path)
        if not path.is_file():
            return 1, ""
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
                    return calls, _text_of(content)  # reached the human turn boundary
            if isinstance(content, list):
                calls += sum(
                    1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
                )
        return calls, ""
    except Exception:
        return 1, ""


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


def _added_content(tool: str, tin: dict) -> str:
    """Text this edit actually ADDS to the file -- never text being replaced away.

    Bug (found stress-testing 2026-08-29): the override-token check used to scan
    `old_string` too, so GAMMA_FREEZE_OVERRIDE sitting only in the text being
    DELETED (never landing in the resulting file) satisfied the check -- a session
    could claim a pre-registered override while leaving no trace of one in the
    diff. Only text that actually reaches disk may count. MultiEdit nests its
    changes under `edits: [{old_string, new_string}, ...]` rather than top-level
    keys, so it needs its own extraction -- read from `edits` scans nothing there
    and would ALWAYS deny an override.
    """
    if tool == "MultiEdit":
        edits = tin.get("edits")
        if isinstance(edits, list):
            return "".join(str(e.get("new_string") or "") for e in edits if isinstance(e, dict))
        return ""
    return "".join(str(tin.get(k) or "") for k in ("new_string", "content", "new_source"))


def _handle_pre_tool(payload: dict) -> int:
    tool = payload.get("tool_name") or ""
    # tool_input is normally a dict, but a malformed/adversarial payload can hand this a
    # raw string or a list. `tin.get(...)` below would then raise AttributeError, which
    # used to propagate all the way to main()'s top-level fail-open catch -- the call
    # still exits 0, but silently: bash_guard_hit/frozen_path_hit never ran for it (they
    # never got a chance to inspect anything), P.record_tool() at the bottom of this
    # function never fired (a real tool call goes missing from the army-view pulse), and
    # the only trace is a generic hook_error log row indistinguishable from any other
    # crash. Coercing to {} here -- same isinstance guard as _session_state/
    # _load_active_goal use for their own non-dict-JSON case -- makes a malformed
    # tool_input behave exactly like a missing one: guards run (against nothing, so they
    # no-op, same as any call with no useful fields), and P.record_tool() still fires.
    raw_tin = payload.get("tool_input")
    tin = raw_tin if isinstance(raw_tin, dict) else {}

    if tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        file_path = str(tin.get("file_path") or tin.get("notebook_path") or "")
        body = _added_content(tool, tin)

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

        # Guard the FILE, not just the tool name. Until 2026-08-29 the freeze and
        # generated-surface checks lived only in the Edit branch, so `sed -i` and
        # `echo >` walked straight past them -- verified, exit 0 both times. Under OP-0
        # a blocked Edit produces a workaround rather than an escalation, so the Edit-only
        # guard was effectively signposting this route.
        target = D.shell_write_hit(command)
        if target:
            surface = D.generated_surface_hit(target)
            if surface:
                return _deny(
                    "PreToolUse",
                    f"This shell command writes to {surface}, which is generated by "
                    f"{D.GENERATED_GENERATOR}. The next sync overwrites it, so the change "
                    f"would silently revert. Edit the generator instead.",
                )
            if D.freeze_active(_et_today()):
                left = (D.FREEZE_END - _et_today()).days
                return _deny(
                    "PreToolUse",
                    f"This shell command writes to {target}, which is on the frozen trading "
                    f"path. The September scoring window ({D.FREEZE_START} -> {D.FREEZE_END}, "
                    f"{left}d left) needs 20 clean days for go_live_gate.py. Blocking the "
                    f"Edit tool but not the shell would just be a signpost to this route. "
                    f"A pre-registered kill-type reduction carries {D.FREEZE_OVERRIDE_TOKEN}.",
                )

    # Subagent spawns: WARN, never deny. The rule most likely to be broken in this repo is
    # a spawn with no boundaries -- Anthropic names vague task descriptions as the cause of
    # duplicated subagent work, and the cost lands in the WORKER's tokens, so nothing at the
    # spawn site makes it visible. A block here would be the OP-32 fail-closed mistake: a
    # boundaryless spawn is a quality problem, not an irreversible one, and this layer's one
    # forbidden failure mode is stopping legitimate work.
    spawn_note = None
    if tool in D.SPAWN_TOOLS:
        spawn_note = D.spawn_boundary_note(D.spawn_prompt_text(tin))

    # Emit the army-view edge only for calls that survived the guards: a DENIED edit must
    # not pulse as though it happened.
    P.record_tool(payload)
    if spawn_note:
        # additionalContext, not a permissionDecision: the call proceeds either way.
        _emit("PreToolUse", _ascii_safe(spawn_note))
        _log({"event": "PreToolUse", "guard": "spawn_boundaries", "tool": tool}, payload)
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
    _log({"event": "PostToolUseFailure", "signature": signature[:80], "count": count}, payload)
    P.record(payload, "fail", detail=f"{payload.get('tool_name')} failed x{count}")
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
        calls, user_prompt = _turn_context(payload.get("transcript_path") or "")
        if D.is_unverified_claim(message, calls, user_prompt):
            blocked["op33"] = True
            _save_session_state(path, state)
            _log({"event": "Stop", "rule": "OP-33"})
            return _deny(
                "Stop",
                "This turn claims something works, is fixed, or is verified, but ran no tool "
                "call to check. OP-33: quote a check run this session, or label the claim "
                "UNVERIFIED.",
            )

    goal_block = _check_goal_continuation(state)
    if goal_block is not None:
        _save_session_state(path, state)
        return goal_block

    _save_session_state(path, state)
    P.record(payload, "idle", detail="turn ended")
    return _ALLOW


def _handle_subagent_start(payload: dict) -> int:
    # Built-in Explore and Plan agents skip CLAUDE.md entirely; custom agents load it but
    # not the parent's auto memory. Either way the prime card has to arrive here.
    _emit("SubagentStart", D.PRIME_CARD.rstrip())
    _log({"event": "SubagentStart", "agent_type": payload.get("agent_type")}, payload)
    P.record(payload, "spawn", to=str(payload.get("agent_type") or "agent"), detail="subagent started")
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
