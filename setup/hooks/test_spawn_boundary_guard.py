"""Regression guards for the subagent-spawn boundary warning (2026-08-29).

The rule this guards is the delegation contract in
`automation/prompts/orchestrator.md` section 2 / `markdown/doctrine/AGENT-ORCHESTRATION.md`:
every spawn carries an objective, an exact return schema, which tools/files are in scope,
and what not to touch. Anthropic names vague task descriptions as the documented cause of
duplicated subagent work, and the cost lands in the WORKER's context, so nothing at the
spawn site surfaces it on its own.

Two classes of guard here, and the SECOND matters more:
  1. An under-specified spawn produces a warning.
  2. The guard NEVER blocks -- not a bad spawn, not a good one, not a malformed payload.
     A boundaryless spawn is a quality problem, not an irreversible one; blocking it would
     be the OP-32 fail-closed scar (2026-05-22 market-hours lockout) repeating, which is
     the single failure mode this hook layer is not allowed to have.

Run: backtest/.venv/Scripts/python.exe -m pytest setup/hooks/test_spawn_boundary_guard.py -q
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import doctrine as D  # noqa: E402

_HOOK = _HERE / "gamma_doctrine.py"

ALLOW, BLOCK = 0, 2

# A spawn prompt that actually carries the four fields. Used as the negative control in
# several tests, so it lives once.
GOOD_SPAWN = (
    "Objective: name the file:line where the live TP1 fraction is read at runtime; "
    "the done-test is quoting that assignment. "
    "Return schema: JSON {file, line, snippet} or the literal string NOT_FOUND. "
    "Scope: setup/scripts/ and automation/state/fleet/, entry point is MAP.md's routing "
    "table -- no repo-wide grep. "
    "Do not edit any file, and never write to params.json or any generated surface."
)


def run_hook(payload: dict, env: dict | None = None) -> tuple[int, str, str]:
    full_env = dict(os.environ)
    # Same reason as test_doctrine_hooks.run_hook: the hook is a real subprocess, so the
    # only way to keep the suite out of production pulse.jsonl is the env override.
    full_env.setdefault(
        "GAMMA_PULSE_PATH", str(Path(tempfile.gettempdir()) / "gamma-test-pulse.jsonl")
    )
    if env:
        full_env.update(env)
    proc = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        env=full_env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def spawn_payload(tool: str = "Task", **tool_input) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": tool_input,
        "session_id": "pyt-spawn",
    }


# ---------------------------------------------------------------------------------------
# pure predicates
# ---------------------------------------------------------------------------------------
def test_short_prompt_is_a_gap():
    gaps = D.spawn_boundary_gaps("look into the exit manager")
    assert gaps, "a 26-char spawn brief cannot hold four fields"
    assert any("characters" in g for g in gaps)


def test_marker_free_prompt_is_a_gap_even_when_long():
    """Length alone is not the contract. A long prompt with no return shape and no
    not-touch list is exactly the 'vague scope' Anthropic names."""
    wordy = (
        "Have a really thorough look through the whole repository for anything that "
        "seems related to how we size positions, and then let me know what you think "
        "about it all when you are finished with that investigation please. " * 2
    )
    assert len(wordy) > D.SPAWN_MIN_PROMPT_CHARS
    gaps = D.spawn_boundary_gaps(wordy)
    assert len(gaps) == 1
    assert "objective" in gaps[0]


def test_well_specified_spawn_has_no_gaps():
    assert D.spawn_boundary_gaps(GOOD_SPAWN) == []
    assert D.spawn_boundary_note(GOOD_SPAWN) is None


@pytest.mark.parametrize("marker", ["objective", "return", "do not", "don't", "never", "schema"])
def test_each_boundary_marker_satisfies_the_marker_half(marker):
    """Every documented marker is honoured, so the note's own wording stays true."""
    padded = f"{marker} " + ("x" * D.SPAWN_MIN_PROMPT_CHARS)
    assert D.spawn_boundary_gaps(padded) == []


def test_note_is_none_only_when_both_halves_pass():
    short_but_marked = "Objective: x. Return: y."
    assert D.spawn_boundary_note(short_but_marked) is not None, "short still warns"


@pytest.mark.parametrize("value", [None, "", "   ", "\n\n"])
def test_empty_prompt_warns_rather_than_raising(value):
    assert D.spawn_boundary_note(value) is not None


def test_note_names_the_contract_and_says_nothing_is_blocked():
    note = D.spawn_boundary_note("go")
    assert "orchestrator.md" in note
    assert "Nothing is blocked" in note


def test_note_is_factual_register_not_shouted_imperative():
    """Anthropic's guidance: out-of-band imperative phrasing can trigger prompt-injection
    defenses and get discounted. The prime card is written as facts; so is this."""
    note = D.spawn_boundary_note("go")
    assert "MUST" not in note and "NEVER" not in note and "BANNED" not in note


def test_spawn_prompt_text_reads_every_key_and_survives_junk():
    assert D.spawn_prompt_text({"prompt": "p", "description": "d"}) == "p\nd"
    assert D.spawn_prompt_text({"instructions": "i"}) == "i"
    assert D.spawn_prompt_text({"prompt": 17}) == ""
    assert D.spawn_prompt_text("not a dict") == ""
    assert D.spawn_prompt_text(None) == ""


def test_description_alone_cannot_pass_the_length_check():
    """Task's `description` is a short label, not a spec. Concatenating it must not let a
    one-line label plus a one-line prompt look like a specified spawn."""
    tin = {"description": "check exits", "prompt": "have a look at exit_manager"}
    assert D.spawn_boundary_note(D.spawn_prompt_text(tin)) is not None


# ---------------------------------------------------------------------------------------
# end-to-end through the real hook subprocess
# ---------------------------------------------------------------------------------------
def test_bad_spawn_warns_and_allows():
    code, stdout, stderr = run_hook(spawn_payload(prompt="look into the exit manager"))
    assert code == ALLOW, "a boundaryless spawn is a quality problem, never a block"
    body = json.loads(stdout)["hookSpecificOutput"]
    assert body["hookEventName"] == "PreToolUse"
    assert "orchestrator.md" in body["additionalContext"]
    assert "permissionDecision" not in body, "warn-only: no decision field at all"
    assert stderr == "", "stderr is the deny channel; a warning must not use it"


def test_agent_tool_is_guarded_too():
    code, stdout, _ = run_hook(spawn_payload(tool="Agent", prompt="do the thing"))
    assert code == ALLOW
    assert "additionalContext" in json.loads(stdout)["hookSpecificOutput"]


def test_good_spawn_is_silent():
    code, stdout, stderr = run_hook(spawn_payload(prompt=GOOD_SPAWN))
    assert code == ALLOW
    assert stdout.strip() == "", f"a specified spawn gets no note, got: {stdout!r}"
    assert stderr == ""


def test_warning_is_ascii_safe():
    """The stderr/console channel on this box is not UTF-8; block messages were observed
    rendering em-dashes as replacement glyphs on 2026-08-29."""
    code, stdout, _ = run_hook(spawn_payload(prompt="go"))
    assert code == ALLOW
    assert json.loads(stdout)["hookSpecificOutput"]["additionalContext"].isascii()


@pytest.mark.parametrize("tool", ["Bash", "Edit", "Read", "Grep", "WebFetch"])
def test_non_spawn_tools_are_untouched(tool):
    """Narrow by tool name: the guard may not start warning on ordinary work."""
    code, stdout, _ = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": tool,
            "tool_input": {"command": "ls", "file_path": "notes.md", "prompt": "hi"},
            "session_id": "pyt-spawn",
        }
    )
    assert code == ALLOW
    assert "orchestrator.md" not in stdout


@pytest.mark.parametrize(
    "tool_input", [None, "a string", ["a", "list"], 42, {}, {"prompt": None}]
)
def test_malformed_spawn_input_fails_open(tool_input):
    """Fail-open is the whole contract of this layer: a payload the guard cannot read
    still allows. It may warn (an unreadable brief IS an unspecified brief) but never
    blocks and never crashes."""
    code, _, _ = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Task",
            "tool_input": tool_input,
            "session_id": "pyt-spawn",
        }
    )
    assert code == ALLOW


def test_spawn_warning_does_not_suppress_the_hard_blocks():
    """Regression fence: the spawn branch is appended AFTER the deny branches, so adding
    it must not have made a frozen-path/generated-surface edit allowable."""
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "MAP.md", "content": "x"},
            "session_id": "pyt-spawn",
        }
    )
    assert code == BLOCK
    assert "obsidian_vault_sync.py" in (stdout + stderr)
