"""Regression guards for the Gamma doctrine hooks (2026-08-29).

Two classes of guard, and the second matters more than the first:
  1. The guard fires on what it must catch.
  2. The guard FAILS OPEN on everything else -- garbage stdin, unknown events, an
     unreadable clock, ordinary work. A doctrine guard that can block general work is
     the OP-32 market-hours-lockout scar (2026-05-22) repeating, and that is the one
     failure mode this whole layer is not allowed to have.

Run: backtest/.venv/Scripts/python.exe -m pytest setup/hooks/test_doctrine_hooks.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import uuid
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import doctrine as D  # noqa: E402

_HOOK = _HERE / "gamma_doctrine.py"

ALLOW, BLOCK = 0, 2


def run_hook(payload: dict) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


# ---------------------------------------------------------------------------------------
# pure predicates
# ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "path",
    [
        "C:/Users/jackw/Desktop/42/automation/state/params.json",
        "automation/state/aggressive/params.json",
        r"automation\state\fleet\exit_manager.py",
        "backtest/lib/filters.py",
        "setup/scripts/heartbeat_core.py",
    ],
)
def test_frozen_paths_are_recognised(path):
    assert D.frozen_path_hit(path) is not None


@pytest.mark.parametrize(
    "path",
    [
        "journal/2026-08-29.md",
        "markdown/infra/DOCTRINE-HOOKS.md",
        "setup/hooks/gamma_doctrine.py",
        "analysis/recommendations/queue.jsonl",
        "dashboard/app/page.tsx",
    ],
)
def test_ordinary_work_is_never_frozen(path):
    assert D.frozen_path_hit(path) is None


@pytest.mark.parametrize(
    "path", ["MAP.md", "C:/x/42/HOME.md", "shadow.md", "analysis/INDEX.md", "journal/2026-08-29.md"]
)
def test_generated_surfaces_are_recognised(path):
    assert D.generated_surface_hit(path) is not None


@pytest.mark.parametrize("path", ["CLAUDE.md", "README.md", "markdown/README.md", "setup/x.py"])
def test_non_generated_markdown_is_allowed(path):
    assert D.generated_surface_hit(path) is None


def test_freeze_window_boundaries():
    assert not D.freeze_active(dt.date(2026, 8, 30))
    assert D.freeze_active(dt.date(2026, 8, 31))
    assert D.freeze_active(dt.date(2026, 9, 29))
    assert not D.freeze_active(dt.date(2026, 9, 30))


@pytest.mark.parametrize(
    "cmd",
    [
        'TZ=America/New_York date',
        "git checkout .",
        "git reset --hard origin/main",
        "git push --force origin main",
    ],
)
def test_scarred_shell_commands_are_caught(cmd):
    assert D.bash_guard_hit(cmd) is not None


@pytest.mark.parametrize(
    "cmd",
    [
        "git push origin main",
        "git checkout -b feature/x",
        "git status",
        "python setup/scripts/et_clock.py",
        "pytest backtest/tests -q",
    ],
)
def test_ordinary_shell_commands_pass(cmd):
    assert D.bash_guard_hit(cmd) is None


def test_heredoc_bodies_are_data_not_commands():
    """Regression: the guard denied its own commit for quoting a banned command in the
    commit message. Heredoc bodies are documentation, never executed."""
    commit = (
        "git commit -F - <<'EOF'\n"
        "docs: explain the clock guard\n"
        "\n"
        "Verified live: `TZ=America/New_York date` is blocked, and `git reset --hard`\n"
        "is refused because it reverts live state backward.\n"
        "EOF\n"
        "git log --oneline -1"
    )
    assert D.bash_guard_hit(commit) is None


def test_real_command_after_a_heredoc_is_still_caught():
    """The stripper must not become a bypass: a banned command outside the body still hits."""
    cmd = "cat > note.md <<'EOF'\nharmless text\nEOF\ngit reset --hard origin/main"
    assert D.bash_guard_hit(cmd) is not None


def test_unterminated_heredoc_does_not_swallow_the_rest():
    cmd = "cat <<'EOF'\nbody line\n"
    assert D.bash_guard_hit(cmd) is None


@pytest.mark.parametrize(
    "msg",
    [
        "I've drafted the plan. Want me to build it?",
        "That's the analysis. Should I proceed with the refactor?",
        "Ready when you are -- let me know if you'd like me to ship it.",
        "Two options exist here. Your call.",
    ],
)
def test_permission_questions_are_caught(msg):
    assert D.is_permission_question(msg)


@pytest.mark.parametrize(
    "msg",
    [
        "Shipped. Revert with `git revert abc1234`.",
        "Arming live money needs you (OP-0 #1) -- confirm and I'll flip fleet live:true.",
        "This would rotate the OpenRouter secret, so it routes to you. Want me to prepare it?",
        "Done: 3 files changed, guard added, tests green.",
    ],
)
def test_escalations_and_reports_are_not_blocked(msg):
    assert not D.is_permission_question(msg)


def test_unverified_claim_needs_zero_tool_calls():
    assert D.is_unverified_claim("It works now.", 0)
    assert not D.is_unverified_claim("It works now.", 3)
    assert not D.is_unverified_claim("Here is the design.", 0)


@pytest.mark.parametrize(
    "prompt", ["tldr", "TL;DR", "recap please", "summarise that", "what did you change?", "why?"]
)
def test_recap_turns_are_exempt_from_op33(prompt):
    """Regression: on day one the guard blocked a 'tldr' that restated checks already
    quoted earlier in the same session. OP-33 governs NEW claims, not recaps."""
    assert D.is_recap_request(prompt)
    assert not D.is_unverified_claim("Verified: 52/52 pass.", 0, prompt)


@pytest.mark.parametrize("prompt", ["ship the exit patch", "fix the heartbeat", "run the gate"])
def test_action_turns_still_need_verification(prompt):
    assert not D.is_recap_request(prompt)
    assert D.is_unverified_claim("Fixed it, all tests passing.", 0, prompt)


def test_prompt_router_is_quiet_by_default():
    assert D.route_prompt("what did we learn from yesterday's journal") == []
    assert D.route_prompt("bump tp1_premium_pct on safe-2") != []


# ---------------------------------------------------------------------------------------
# end-to-end: the dispatcher must fail open on anything unexpected
# ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"hook_event_name": "TotallyUnknownEvent"},
        {"hook_event_name": "PreToolUse"},
        {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "x"}},
        {"hook_event_name": "Stop", "last_assistant_message": "Shipped it, reverting is one command."},
    ],
)
def test_dispatcher_fails_open(payload):
    code, _, _ = run_hook(payload)
    assert code == ALLOW


def test_malformed_stdin_fails_open():
    proc = subprocess.run(
        [sys.executable, str(_HOOK)], input="}{not json", capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == ALLOW


def test_generated_surface_edit_is_blocked_end_to_end():
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "C:/Users/jackw/Desktop/42/MAP.md", "new_string": "x"},
        }
    )
    assert code == BLOCK
    assert "obsidian_vault_sync" in (stdout + stderr)


def test_stop_blocks_permission_question_once_only():
    # The one-block-per-session ledger is a real file keyed by session_id, so the test
    # needs a session id no previous run has used -- otherwise it reads the ledger from
    # the last run and asserts against a session that has already spent its block.
    # pytest's tmp_path is NOT unique enough here: its name derives from the test name
    # and so repeats every run.
    session_id = f"pyt-{uuid.uuid4().hex[:10]}"
    payload = {
        "hook_event_name": "Stop",
        "session_id": session_id,
        "last_assistant_message": "Here's the plan. Want me to implement it?",
    }
    first, _, _ = run_hook(payload)
    second, _, _ = run_hook(payload)
    assert first == BLOCK, "first permission-question turn must be blocked"
    assert second == ALLOW, "guard must never loop: one block per session per rule"


def test_stop_respects_stop_hook_active():
    code, _, _ = run_hook(
        {
            "hook_event_name": "Stop",
            "session_id": "pytest-active",
            "stop_hook_active": True,
            "last_assistant_message": "Want me to do that?",
        }
    )
    assert code == ALLOW


def test_session_start_emits_valid_envelope():
    code, stdout, _ = run_hook({"hook_event_name": "SessionStart", "reason": "startup"})
    assert code == ALLOW
    out = json.loads(stdout)
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "OP-0" in out["hookSpecificOutput"]["additionalContext"]
