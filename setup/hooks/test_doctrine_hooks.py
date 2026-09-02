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
import os
import subprocess
import tempfile
import uuid
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import doctrine as D  # noqa: E402

_HOOK = _HERE / "gamma_doctrine.py"

ALLOW, BLOCK = 0, 2


def run_hook(payload: dict, env: dict | None = None) -> tuple[int, str, str]:
    full_env = dict(os.environ)
    # The hook runs as a real SUBPROCESS, so monkeypatch cannot redirect its telemetry
    # sink. GAMMA_PULSE_PATH is the only way to keep the suite out of production
    # pulse.jsonl -- without it each run appended ~10 rows indistinguishable from real
    # message edges that had lost their recipient. Overridable by an explicit env arg.
    full_env.setdefault("GAMMA_PULSE_PATH", str(Path(tempfile.gettempdir()) / "gamma-test-pulse.jsonl"))
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


# ---------------------------------------------------------------------------------------
# path-matching bypass hunt (2026-08-29 stress test): a suffix comparison on a raw
# string is exact-text matching, not filesystem resolution -- these prove the paths a
# real Edit/Write tool call would resolve to the SAME on-disk frozen/generated file
# still get caught even when the string is spelled a different way.
# ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "path",
    [
        # ".."/"." segments resolve away on any real filesystem access -- a raw suffix
        # match missed this before normalise_path ran posixpath.normpath.
        "automation/state/dummy/../params.json",
        "automation/x/../state/params.json",
        "x/../../setup/scripts/heartbeat_core.py",
        # doubled separators collapse to one on disk.
        "automation//state/params.json",
        # trailing "." / " " / "/" -- VERIFIED empirically on this box (2026-08-29):
        # writing through "x.txt." or "x.txt " mutates "x.txt" itself, so a path
        # spelled with a trailing dot/space/slash is the SAME file to the OS and must
        # be caught the same as the bare name.
        "automation/state/params.json.",
        "automation/state/params.json ",
        "automation/state/params.json/",
        "automation/state/params.json. . ",
    ],
)
def test_frozen_path_traversal_and_windows_quirks_cannot_bypass(path):
    assert D.frozen_path_hit(path) is not None


@pytest.mark.parametrize(
    "path",
    [
        "some/dir/../../MAP.md",
        "MAP.md.",
        "MAP.md ",
        "journal/2026-08-29.md.",
        "journal/2026-08-29.md ",
    ],
)
def test_generated_surface_traversal_and_windows_quirks_cannot_bypass(path):
    assert D.generated_surface_hit(path) is not None


@pytest.mark.parametrize(
    "path",
    [
        # Documented, NOT fixed here: the PreToolUse payload carries only the string
        # the tool was called with, never the session's working directory, so a
        # relative path with no "automation/state/" prefix at all cannot be resolved
        # to the frozen file from the string alone. A session with cwd already inside
        # automation/state/ could name the frozen file this way and slip through.
        "params.json",
        "state/params.json",
        # A homoglyph filename does not exist on disk under that name, so this is a
        # non-match by construction, not a resolvable bypass -- kept as a documented
        # boundary, not a claimed fix.
        "automation/state/ｐarams.json",
    ],
)
def test_frozen_path_hit_known_unresolved_limitations(path):
    """Two things that do NOT get caught, on purpose documented rather than silently
    left as a surprise: a bare/partial relative path (no cwd in the payload to resolve
    it against) and a non-ASCII lookalike (no such file exists under that name)."""
    assert D.frozen_path_hit(path) is None


def test_freeze_window_boundaries():
    """CORRECTED 2026-09-02. This test previously asserted `not freeze_active(2026-09-30)`,
    pinning FREEZE_END at 09-29 -- it encoded the bug rather than the intent. 09-29 is a
    CHECKPOINT inside the freeze (the one date pre-registered kill-type risk REDUCTIONS may
    ship); the freeze itself must outlive the scoring window it protects and run to the
    2026-10-30 decision. Ending it on 09-29 would unblock trading-path edits a month early,
    mid-window, and the only symptom would be the banner quietly changing to "freeze closed".
    """
    assert not D.freeze_active(dt.date(2026, 8, 30))
    assert D.freeze_active(dt.date(2026, 8, 31))
    assert D.freeze_active(dt.date(2026, 9, 29))
    assert D.freeze_active(dt.date(2026, 9, 30)), (
        "the freeze must NOT expire at the 09-29 safety checkpoint -- that is a checkpoint "
        "inside the window, not its end"
    )
    assert D.freeze_active(dt.date(2026, 10, 30))
    assert not D.freeze_active(dt.date(2026, 10, 31))


def test_freeze_end_outlives_the_safety_checkpoint():
    """The two dates must never be conflated again, in either direction."""
    assert D.FREEZE_SAFETY_CHECKPOINT == dt.date(2026, 9, 29)
    assert D.FREEZE_END == dt.date(2026, 10, 30)
    assert D.FREEZE_START < D.FREEZE_SAFETY_CHECKPOINT < D.FREEZE_END


def test_freeze_banner_names_the_checkpoint_and_the_override_token():
    """A banner that says only 'edits are blocked' leaves a session guessing what the one
    sanctioned exception is and how to invoke it -- so it names both, on both sides of the
    checkpoint, and states that risk EXPANSIONS are never in scope."""
    before = D.freeze_banner(dt.date(2026, 9, 2))
    after = D.freeze_banner(dt.date(2026, 9, 30))
    for banner in (before, after):
        assert "2026-09-29" in banner
        assert D.FREEZE_OVERRIDE_TOKEN in banner
        assert "EXPANSIONS" in banner
    assert "not before" in before
    assert "has passed" in after


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


@pytest.mark.parametrize(
    "cmd",
    [
        # Regression (2026-08-29 probe): the guard had NO pattern for either of these --
        # a raw Bash `rm -rf automation/state` or `export GAMMA_CORE_ARMED=1` sailed
        # through with bash_guard_hit() returning None. GAMMA_CORE_ARMED=1 is OP-0 #1
        # (arming live money, the one thing that always routes to J); automation/state
        # holds the same class of live decision-gating state git reset --hard protects
        # (lesson cluster C34).
        "export GAMMA_CORE_ARMED=1",
        "$env:GAMMA_CORE_ARMED=1",
        "set GAMMA_CORE_ARMED=1",
        "rm -rf automation/state",
        "rm -fr automation/state",
        "rm -Rf automation/state",
        "rm --recursive --force automation/state",
        "rm -rf ./automation/state/params.json",
    ],
)
def test_rm_rf_and_live_arm_export_are_caught(cmd):
    assert D.bash_guard_hit(cmd) is not None


@pytest.mark.parametrize(
    "cmd",
    [
        # Narrow by design: unarming, reading the flag, or an rm -rf elsewhere (e.g. a
        # dead worktree/scratch dir) must NOT be caught -- OP-25 sanctions that cleanup,
        # and a guard that blocks general work is the OP-32 lockout scar repeating.
        "echo $GAMMA_CORE_ARMED",
        "export GAMMA_CORE_ARMED=0",
        "rm -rf node_modules",
        "rm -rf /tmp/scratch-worktree",
        "git worktree remove --force ../dead-branch",
        # Known, accepted trade-off (same contract as strip_quoted_strings' documented
        # quoting bypass above): a value smuggled inside quotes reads as DATA, not a
        # command literal, so `'1'` inside a PowerShell assignment is not caught.
        "$env:GAMMA_CORE_ARMED = '1'",
    ],
)
def test_rm_rf_and_arm_guard_does_not_overreach(cmd):
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
    "cmd",
    [
        # Regression (2026-08-29): caught live while writing THIS test suite -- the
        # guard denied its own test-authoring session for echoing a JSON fixture
        # that quoted a banned phrase as DATA, never executed. Same failure shape as
        # the heredoc bug above, one quoting style over.
        'echo \'{"tool_input":{"command":"git push --force origin main"}}\'',
        'git commit -m "docs: note that git push --force is banned here"',
        'printf "reminder: never run git reset --hard on shared state\\n"',
        "git commit -m 'TZ=America/New_York date is 2h wrong on this box'",
    ],
)
def test_quoted_strings_are_data_not_commands(cmd):
    assert D.bash_guard_hit(cmd) is None


def test_real_command_inside_double_quotes_is_still_not_a_bypass_for_unquoted_use():
    """The stripper only blanks QUOTED content -- an unquoted banned command right
    next to a quoted string must still be caught."""
    cmd = 'echo "just a note" && git reset --hard origin/main'
    assert D.bash_guard_hit(cmd) is not None


@pytest.mark.parametrize(
    "msg",
    [
        "I've drafted the plan. Want me to build it?",
        "That's the analysis. Should I proceed with the refactor?",
        "Ready when you are -- let me know if you'd like me to ship it.",
        "Two options exist here. Your call.",
        # The 2026-08-30 escape, verbatim: a conditional offer is an ask wearing a
        # statement's clothes. J: "it should have been done already."
        "That's the next real autonomy fix if you want it.",
        "I can wire the digest too, if you'd like.",
        "Happy to build the persistent session next.",
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
def test_dispatcher_fails_open(payload, tmp_path):
    # Isolated from the REAL automation/state/active-goal.json on purpose: this test
    # asserts the dispatcher fails open on messy/unexpected payloads in general, not on
    # goal-continuation behavior specifically (that's covered by the dedicated
    # test_goal_continuation_* cases below). Without this override, a genuinely active
    # goal in the real repo (the normal state once /goal is in use) would correctly
    # BLOCK the Stop-payload case here -- that's the goal mechanism working as
    # designed, not a dispatcher regression, so this test must not depend on the
    # repo's live goal state either way.
    env = {"GAMMA_ACTIVE_GOAL_PATH": str(tmp_path / "does-not-exist.json")}
    code, _, _ = run_hook(payload, env=env)
    assert code == ALLOW


# ---------------------------------------------------------------------------------------
# malformed tool_input TYPE (not just malformed JSON) -- found stress-testing 2026-08-29.
# A raw string or a non-empty list for tool_input used to make _handle_pre_tool's
# `tin.get(...)` calls raise AttributeError, caught only by main()'s top-level fail-open
# catch. The call still exited 0 (correct outcome), but silently: bash_guard_hit /
# frozen_path_hit never actually ran for it (they never got the chance), and
# P.record_tool() never fired, so the call vanished from the army-view pulse with no
# signal beyond a generic hook_error log row. Fix coerces non-dict tool_input to {},
# matching the isinstance guard _session_state/_load_active_goal already use for their
# own non-dict-JSON case -- same ALLOW outcome, reached without an exception, guards
# actually invoked (against nothing, so they no-op), and telemetry still fires.
# ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "tool_input",
    ["just a raw string", ["a", "b"], ["automation/state/params.json"], None, []],
)
@pytest.mark.parametrize("tool_name", ["Bash", "Edit"])
def test_malformed_tool_input_type_fails_open_end_to_end(tool_input, tool_name):
    code, stdout, stderr = run_hook(
        {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
    )
    assert code == ALLOW
    # No hook_error / exception trace should leak onto either channel for this case --
    # the crash-then-fail-open path is exactly what the fix removes.
    assert "Traceback" not in stderr
    assert "AttributeError" not in (stdout + stderr)


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


# ---------------------------------------------------------------------------------------
# end-to-end frozen-path block, real subprocess, real clock -- simulated via
# GAMMA_FREEZE_TODAY_OVERRIDE (test-only env var). Before this seam existed, the ONLY
# thing proving the freeze block worked was the pure freeze_active()/frozen_path_hit()
# predicates in isolation -- nothing exercised the actual PreToolUse dispatcher with the
# freeze genuinely active, because the real ET clock cannot be pointed at a date inside
# the window until the calendar gets there.
# ---------------------------------------------------------------------------------------
def test_frozen_path_edit_is_blocked_end_to_end_during_freeze():
    env = {"GAMMA_FREEZE_TODAY_OVERRIDE": "2026-09-05"}
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "automation/state/params.json", "new_string": "x"},
        },
        env=env,
    )
    assert code == BLOCK
    assert "frozen trading path" in (stdout + stderr)


def test_frozen_path_edit_allowed_before_freeze_opens_end_to_end():
    env = {"GAMMA_FREEZE_TODAY_OVERRIDE": "2026-08-30"}
    code, _, _ = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "automation/state/params.json", "new_string": "x"},
        },
        env=env,
    )
    assert code == ALLOW


def test_frozen_path_edit_with_real_override_token_is_allowed_end_to_end():
    env = {"GAMMA_FREEZE_TODAY_OVERRIDE": "2026-09-05"}
    code, _, _ = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "automation/state/params.json",
                "old_string": "x",
                "new_string": "y  # GAMMA_FREEZE_OVERRIDE pre-registered kill-type reduction",
            },
        },
        env=env,
    )
    assert code == ALLOW


def test_frozen_path_override_token_only_in_old_string_does_not_count_end_to_end():
    """Bug (found stress-testing 2026-08-29): GAMMA_FREEZE_OVERRIDE sitting only in
    the text being REMOVED (old_string), never landing in the resulting file, used to
    satisfy the override check -- a session could fake a pre-registered override while
    leaving no trace of one in the diff. Only text that actually reaches disk may
    count."""
    env = {"GAMMA_FREEZE_TODAY_OVERRIDE": "2026-09-05"}
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "automation/state/params.json",
                "old_string": "# GAMMA_FREEZE_OVERRIDE placeholder, never actually written",
                "new_string": "tp1_premium_pct = 0.99  # no override annotation left behind",
            },
        },
        env=env,
    )
    assert code == BLOCK
    assert "frozen trading path" in (stdout + stderr)


def test_frozen_path_multiedit_nested_new_string_can_carry_a_real_override_end_to_end():
    """MultiEdit nests its changes under edits: [{old_string, new_string}, ...] rather
    than top-level keys. A legitimate override placed in a nested new_string (text that
    DOES reach disk) must be honoured, not silently ignored."""
    env = {"GAMMA_FREEZE_TODAY_OVERRIDE": "2026-09-05"}
    code, _, _ = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": "automation/state/params.json",
                "edits": [
                    {"old_string": "a", "new_string": "b  # GAMMA_FREEZE_OVERRIDE kill-type"}
                ],
            },
        },
        env=env,
    )
    assert code == ALLOW


def test_frozen_path_notebookedit_and_multiedit_are_blocked_end_to_end():
    env = {"GAMMA_FREEZE_TODAY_OVERRIDE": "2026-09-05"}
    code_nb, _, _ = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "NotebookEdit",
            "tool_input": {"notebook_path": "automation/state/params.json", "new_source": "x"},
        },
        env=env,
    )
    assert code_nb == BLOCK

    code_me, _, _ = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": "automation/state/params.json",
                "edits": [{"old_string": "a", "new_string": "b"}],
            },
        },
        env=env,
    )
    assert code_me == BLOCK


def test_bash_write_to_frozen_path_is_now_closed():
    """CLOSED 2026-08-29, same day it was documented. This test previously asserted
    ALLOW and carried the note 'flip to BLOCK if this is ever closed' -- doing exactly
    that now, rather than deleting the case.

    The gap was judged out of scope on the grounds that parsing shell targets risks the
    OP-32 lockout. That trade-off was real but resolvable: `shell_write_hit()` inspects
    only WRITE POSITIONS (redirect target, sed -i operand, tee/dd operand, the final
    operand of cp/mv), so a path merely mentioned -- `grep params.json`, `cat
    filters.py`, `cp filters.py /tmp/backup` -- still passes. See
    test_shell_write_guard.py, whose second half is entirely ordinary-work cases."""
    env = {"GAMMA_FREEZE_TODAY_OVERRIDE": "2026-09-05"}
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "cat > automation/state/params.json <<'EOF'\n{}\nEOF"
            },
        },
        env=env,
    )
    assert code == BLOCK
    assert "frozen trading path" in (stdout + stderr)


def test_stop_blocks_permission_question_once_only(tmp_path):
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
    # Isolated from the REAL active-goal.json for the same reason as
    # test_dispatcher_fails_open above: this asserts the op0 once-per-session ledger,
    # not goal-continuation (that's the third, independent Stop clause -- a real active
    # goal would correctly re-block the second call for its OWN reason, which would
    # make this assertion fail for a reason unrelated to what it's testing).
    env = {"GAMMA_ACTIVE_GOAL_PATH": str(tmp_path / "does-not-exist.json")}
    first, _, _ = run_hook(payload, env=env)
    second, _, _ = run_hook(payload, env=env)
    assert first == BLOCK, "first permission-question turn must be blocked"
    assert second == ALLOW, "guard must never loop: one block per session per rule"


def test_stop_survives_a_session_state_file_shaped_as_a_list():
    """Regression (2026-08-29): a session-*.json holding syntactically valid JSON
    that is not an object -- e.g. `["not","a","dict"]` -- made every downstream
    `state.setdefault(...)` raise, which main()'s top-level catch swallows into
    ALLOW. That fails open (never over-blocks, per this module's own contract),
    but it means the OP-0 guard goes silently and PERMANENTLY dark for that one
    session_id, since nothing ever repairs the file. Confirmed before the fix:
    this same payload returned ALLOW instead of the BLOCK the clean-session test
    above proves for byte-identical input. _session_state() now coerces a non-dict
    body to {}, so a malformed state file behaves like a missing one -- state
    resets, and the guard keeps working for the rest of that session."""
    session_id = f"pyt-{uuid.uuid4().hex[:10]}"
    state_path = _HOOK.parent.parent / "automation" / "state" / "hooks" / f"session-{session_id[:16]}.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text('["not","a","dict"]', encoding="utf-8")
    try:
        env = {"GAMMA_ACTIVE_GOAL_PATH": str(state_path.parent / "does-not-exist.json")}
        code, _, _ = run_hook(
            {
                "hook_event_name": "Stop",
                "session_id": session_id,
                "last_assistant_message": "Here's the plan. Want me to implement it?",
            },
            env=env,
        )
        assert code == BLOCK, "a malformed session-state file must not silently disable OP-0"
    finally:
        state_path.unlink(missing_ok=True)


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


# ---------------------------------------------------------------------------------------
# pulse telemetry -- the Army view's event stream
# ---------------------------------------------------------------------------------------
import pulse as P  # noqa: E402


@pytest.mark.parametrize(
    "tool,expected",
    [
        ("SendMessage", "message"),
        ("Agent", "spawn"),
        ("Task", "spawn"),
        ("Workflow", "spawn"),
        ("Edit", "act"),
        ("Bash", "act"),
        ("Read", None),
        ("Grep", None),
        ("", None),
    ],
)
def test_pulse_classifies_only_edge_worthy_tools(tool, expected):
    assert P.classify(tool) == expected


def test_pulse_message_edge_carries_recipient():
    row = P._target("SendMessage", {"to": "42-d3", "message": "hi"})
    assert row == "42-d3"


def test_pulse_target_to_field_is_bounded():
    """A SendMessage `to` field is untrusted-ish (caller-controlled) and every OTHER row
    field is truncated (_detail caps at 100-120 chars) -- `to` must be too, or a single
    oversized value produces an unbounded JSONL row that defeats MAX_ROWS' byte budget
    and taxes every later PreToolUse call (_trim reads the whole file every time).
    Verified 2026-08-29: an unbounded `to` grew one row past 1MB; fixed by capping it."""
    huge = "x" * 1_000_000
    assert len(P._target("SendMessage", {"to": huge})) <= P._TARGET_MAX_LEN
    assert len(P._target("Agent", {"subagent_type": huge})) <= P._TARGET_MAX_LEN
    assert len(P._target("Workflow", {"name": huge})) <= P._TARGET_MAX_LEN


def test_pulse_act_edge_has_no_recipient():
    """An 'act' is a self-glow on its own box, never a travelling pulse."""
    assert P._target("Edit", {"file_path": "x.py"}) == ""


def test_pulse_detail_is_short_and_human():
    assert P._detail("Edit", {"file_path": "C:/a/b/filters.py"}) == "Editing filters.py"
    assert P._detail("Bash", {"command": "git status"}).startswith("Ran: git status")
    assert len(P._detail("SendMessage", {"summary": "x" * 500})) <= 120


def test_pulse_row_carries_session_and_agent_id(tmp_path, monkeypatch):
    """Without BOTH ids every worker in a fan-out collapses onto its parent session node."""
    monkeypatch.setattr(P, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(P, "_PULSE", tmp_path / "pulse.jsonl")
    P.record_tool(
        {
            "session_id": "sess-123",
            "agent_id": "agent-abc",
            "tool_name": "SendMessage",
            "tool_input": {"to": "42-d3", "summary": "schema done"},
        }
    )
    row = json.loads((tmp_path / "pulse.jsonl").read_text(encoding="utf-8").strip())
    assert row["event"] == "message"
    assert row["session_id"] == "sess-123"
    assert row["agent_id"] == "agent-abc"
    assert row["to"] == "42-d3"


def test_pulse_ring_cap_holds(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(P, "_PULSE", tmp_path / "pulse.jsonl")
    monkeypatch.setattr(P, "MAX_ROWS", 50)
    monkeypatch.setattr(P, "_TRIM_SLACK", 10)
    for i in range(200):
        P.record({"session_id": "s", "tool_name": "Edit"}, "act", detail=str(i))
    n = len((tmp_path / "pulse.jsonl").read_text(encoding="utf-8").strip().splitlines())
    assert n <= 60, f"ring cap leaked: {n} rows"


def test_pulse_never_raises_on_garbage(tmp_path, monkeypatch):
    """Telemetry must never be the reason a tool call fails.

    Redirected to tmp_path: the first version of this test wrote to the REAL
    automation/state/hooks/pulse.jsonl, so every pytest run injected fake `message` rows
    with an empty recipient into production telemetry. 13 of them accumulated and briefly
    looked like evidence that real SendMessage edges were losing their `to` field. A test
    that pollutes the data it is meant to protect is worse than no test.
    """
    monkeypatch.setattr(P, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(P, "_PULSE", tmp_path / "pulse.jsonl")
    P.record_tool({"tool_name": "SendMessage", "tool_input": "not-a-dict"})
    P.record_tool({})
    P.record_tool({"tool_name": None, "tool_input": None})


def test_pulse_module_paths_are_redirectable():
    """The guard that makes the fix above possible: both sinks must be monkeypatchable
    module attributes, not values baked into record()'s body. If a refactor inlines the
    path, tests silently start writing to production telemetry again."""
    assert isinstance(P._PULSE, Path) and P._PULSE.name == "pulse.jsonl"
    assert isinstance(P._STATE_DIR, Path)


# ---------------------------------------------------------------------------------------
# goal continuation -- Stop hook third clause (pure predicates)
# ---------------------------------------------------------------------------------------
_GOAL_MD_OPEN = """\
# GOAL: G1
> J verbatim: "test"
## DONE-WHEN
Something falsifiable.
## OPERATING RULES
Config freeze applies.
## QUEUE
- [x] done item
- [~] wip item
- [B] blocked item
- [ ] the real next item
- [ ] a later item
## J-DECISIONS
## PROGRESS LOG
## HONEST STATE
"""

_GOAL_MD_NO_OPEN = """\
# GOAL: G1
## QUEUE
- [x] done item
- [~] wip item
- [B-J] blocked on J
## PROGRESS LOG
"""

_GOAL_MD_NO_QUEUE_SECTION = """\
# GOAL: G1
## DONE-WHEN
- [ ] this looks like an item but is NOT under QUEUE
"""


def test_goal_next_open_item_finds_first_unchecked_under_queue():
    assert D.goal_next_open_item(_GOAL_MD_OPEN) == "the real next item"


def test_goal_next_open_item_skips_wip_done_and_blocked_markers():
    assert D.goal_next_open_item(_GOAL_MD_NO_OPEN) is None


def test_goal_next_open_item_ignores_checkboxes_outside_queue_section():
    assert D.goal_next_open_item(_GOAL_MD_NO_QUEUE_SECTION) is None


def test_goal_next_open_item_handles_missing_or_empty_text():
    assert D.goal_next_open_item("") is None
    assert D.goal_next_open_item(None) is None  # type: ignore[arg-type]


def test_goal_next_open_item_heading_case_insensitive():
    assert D.goal_next_open_item("## queue\n- [ ] lower item\n") == "lower item"


def test_goal_next_open_item_heading_wrong_level_still_recognized():
    """A goal file's `## QUEUE` typo'd to H1 or H3 must not silently blind the
    parser -- before this fix, only an exact `##` heading toggled in_queue, so
    `# QUEUE` / `### QUEUE` matched no heading at all and every real open item
    under them was invisible (goal_next_open_item returned None)."""
    assert D.goal_next_open_item("### QUEUE\n- [ ] h3 item\n") == "h3 item"
    assert D.goal_next_open_item("# QUEUE\n- [ ] h1 item\n") == "h1 item"


def test_goal_next_open_item_crlf_line_endings():
    md = "## QUEUE\r\n- [x] done\r\n- [ ] crlf item\r\n"
    assert D.goal_next_open_item(md) == "crlf item"


def test_goal_next_open_item_ignores_indented_nested_sub_bullets():
    """An indented `  - [ ]` sub-bullet under a parent item is NOT recognized
    as a queue item (the regex anchors `-` to column 0) -- only top-level
    checkboxes drive continuation. Documents current behavior."""
    md = "## QUEUE\n- [x] parent done\n  - [ ] nested child (not picked up)\n- [ ] top-level open\n"
    assert D.goal_next_open_item(md) == "top-level open"


def test_goal_next_open_item_multiple_queue_sections_scans_both():
    md = (
        "## QUEUE\n- [x] first section done\n"
        "## Other\n- [ ] other section item (must NOT count)\n"
        "## QUEUE\n- [ ] second queue section item\n"
    )
    assert D.goal_next_open_item(md) == "second queue section item"


def test_goal_next_open_item_item_text_containing_literal_checkbox_markup():
    md = "## QUEUE\n- [ ] fix parser bug where a line like '- [ ] foo' appears in prose\n"
    assert (
        D.goal_next_open_item(md)
        == "fix parser bug where a line like '- [ ] foo' appears in prose"
    )


def test_goal_next_open_item_unknown_marker_not_treated_as_open():
    md = "## QUEUE\n- [?] unknown marker item\n- [ ] the real open item\n"
    assert D.goal_next_open_item(md) == "the real open item"


def test_goal_expired_no_expiry_set_is_not_expired():
    assert not D.goal_expired("", dt.datetime(2026, 8, 29, 12, 0))
    assert not D.goal_expired(None, dt.datetime(2026, 8, 29, 12, 0))  # type: ignore[arg-type]


def test_goal_expired_past_date_is_expired():
    assert D.goal_expired("2026-08-01", dt.datetime(2026, 8, 29, 12, 0))


def test_goal_expired_future_date_is_not_expired():
    assert not D.goal_expired("2026-12-31", dt.datetime(2026, 8, 29, 12, 0))


def test_goal_expired_same_day_end_of_day_not_yet_expired():
    assert not D.goal_expired("2026-08-29", dt.datetime(2026, 8, 29, 12, 0))


def test_goal_expired_malformed_expiry_fails_open_as_expired():
    """A goal that says nonsense about its own expiry must never block J forever --
    it fails toward 'treat as expired' (allow the stop), not toward 'block forever'."""
    assert D.goal_expired("not-a-date", dt.datetime(2026, 8, 29, 12, 0))


def test_goal_max_continuations_default_and_override():
    assert D.goal_max_continuations({}) == D.DEFAULT_MAX_CONTINUATIONS
    assert D.goal_max_continuations({"max_continuations_per_session": 5}) == 5
    assert D.goal_max_continuations({"max_continuations_per_session": 0}) == D.DEFAULT_MAX_CONTINUATIONS
    assert D.goal_max_continuations({"max_continuations_per_session": -1}) == D.DEFAULT_MAX_CONTINUATIONS
    assert D.goal_max_continuations({"max_continuations_per_session": "3"}) == D.DEFAULT_MAX_CONTINUATIONS


def test_goal_should_continue_true_with_open_item_and_budget():
    assert D.goal_should_continue("next item", None, 0, 3)
    assert D.goal_should_continue("next item", "a different earlier item", 1, 3)


def test_goal_should_continue_false_when_no_item():
    assert not D.goal_should_continue(None, None, 0, 3)
    assert not D.goal_should_continue("", None, 0, 3)


def test_goal_should_continue_false_when_counter_at_or_over_max():
    assert not D.goal_should_continue("next item", None, 3, 3)
    assert not D.goal_should_continue("next item", None, 4, 3)


def test_goal_should_continue_false_when_item_unchanged_convergence():
    """The third brake: an item identical to the one named at the last block means
    the last continuation did not move the goal -- stop, don't loop."""
    assert not D.goal_should_continue("same item", "same item", 0, 3)


# ---------------------------------------------------------------------------------------
# goal continuation -- Stop hook third clause, end-to-end via the real hook process
# ---------------------------------------------------------------------------------------
def _goal_env(tmp_path: Path, goal_json: dict | None, goal_md: str | None) -> dict:
    """Point the hook at a throwaway active-goal.json + goal file for this test only.
    Never touches the real automation/state/active-goal.json."""
    env = {}
    if goal_json is not None:
        goal_file = tmp_path / "GOAL-TEST.md"
        if goal_md is not None:
            goal_file.write_text(goal_md, encoding="utf-8")
        goal_json = dict(goal_json)
        goal_json.setdefault("file", str(goal_file))
        active_goal_path = tmp_path / "active-goal.json"
        active_goal_path.write_text(json.dumps(goal_json), encoding="utf-8")
        env["GAMMA_ACTIVE_GOAL_PATH"] = str(active_goal_path)
    else:
        # Point at a path that does not exist -- the "no goal file at all" case.
        env["GAMMA_ACTIVE_GOAL_PATH"] = str(tmp_path / "does-not-exist.json")
    return env


def _stop_payload(session_id: str) -> dict:
    return {
        "hook_event_name": "Stop",
        "session_id": session_id,
        "last_assistant_message": "Continuing.",
    }


def test_goal_continuation_blocks_when_open_item_exists(tmp_path):
    env = _goal_env(
        tmp_path,
        {"id": "GOAL-T1", "active": True, "expires_at_et": "2099-01-01"},
        _GOAL_MD_OPEN,
    )
    code, stdout, stderr = run_hook(_stop_payload(f"pyt-goal-{uuid.uuid4().hex[:8]}"), env=env)
    assert code == BLOCK
    assert "the real next item" in (stdout + stderr)
    assert "GOAL-T1" in (stdout + stderr)


def test_goal_continuation_allows_when_no_active_goal_file(tmp_path):
    env = _goal_env(tmp_path, None, None)
    code, _, _ = run_hook(_stop_payload(f"pyt-goal-{uuid.uuid4().hex[:8]}"), env=env)
    assert code == ALLOW


def test_goal_continuation_allows_when_goal_inactive(tmp_path):
    env = _goal_env(
        tmp_path,
        {"id": "GOAL-T2", "active": False, "expires_at_et": "2099-01-01"},
        _GOAL_MD_OPEN,
    )
    code, _, _ = run_hook(_stop_payload(f"pyt-goal-{uuid.uuid4().hex[:8]}"), env=env)
    assert code == ALLOW


def test_goal_continuation_allows_when_goal_expired(tmp_path):
    env = _goal_env(
        tmp_path,
        {"id": "GOAL-T3", "active": True, "expires_at_et": "2020-01-01"},
        _GOAL_MD_OPEN,
    )
    code, _, _ = run_hook(_stop_payload(f"pyt-goal-{uuid.uuid4().hex[:8]}"), env=env)
    assert code == ALLOW


def test_goal_continuation_allows_when_goal_md_path_missing(tmp_path):
    active_goal_path = tmp_path / "active-goal.json"
    active_goal_path.write_text(
        json.dumps(
            {
                "id": "GOAL-T4",
                "active": True,
                "expires_at_et": "2099-01-01",
                "file": str(tmp_path / "does-not-exist.md"),
            }
        ),
        encoding="utf-8",
    )
    env = {"GAMMA_ACTIVE_GOAL_PATH": str(active_goal_path)}
    code, _, _ = run_hook(_stop_payload(f"pyt-goal-{uuid.uuid4().hex[:8]}"), env=env)
    assert code == ALLOW


def test_goal_continuation_allows_when_active_goal_json_malformed(tmp_path):
    active_goal_path = tmp_path / "active-goal.json"
    active_goal_path.write_text("}{not json", encoding="utf-8")
    env = {"GAMMA_ACTIVE_GOAL_PATH": str(active_goal_path)}
    code, _, _ = run_hook(_stop_payload(f"pyt-goal-{uuid.uuid4().hex[:8]}"), env=env)
    assert code == ALLOW


def test_goal_continuation_allows_when_queue_has_no_open_item(tmp_path):
    env = _goal_env(
        tmp_path,
        {"id": "GOAL-T5", "active": True, "expires_at_et": "2099-01-01"},
        _GOAL_MD_NO_OPEN,
    )
    code, _, _ = run_hook(_stop_payload(f"pyt-goal-{uuid.uuid4().hex[:8]}"), env=env)
    assert code == ALLOW


def test_goal_continuation_honours_stop_hook_active(tmp_path):
    env = _goal_env(
        tmp_path,
        {"id": "GOAL-T6", "active": True, "expires_at_et": "2099-01-01"},
        _GOAL_MD_OPEN,
    )
    payload = _stop_payload(f"pyt-goal-{uuid.uuid4().hex[:8]}")
    payload["stop_hook_active"] = True
    code, _, _ = run_hook(payload, env=env)
    assert code == ALLOW


def test_goal_continuation_allows_after_max_continuations(tmp_path):
    """Brake 2: the hard counter. Each fire in this test edits the goal file so the
    NEXT item differs each time (so convergence never masks the counter), and stays
    under one session id so the ledger accumulates."""
    session_id = f"pyt-goal-{uuid.uuid4().hex[:8]}"
    goal_json = {
        "id": "GOAL-T7",
        "active": True,
        "expires_at_et": "2099-01-01",
        "max_continuations_per_session": 3,
    }
    goal_file = tmp_path / "GOAL-T7.md"
    active_goal_path = tmp_path / "active-goal.json"
    env = {"GAMMA_ACTIVE_GOAL_PATH": str(active_goal_path)}

    codes = []
    for i in range(4):
        goal_file.write_text(
            f"# GOAL: G7\n## QUEUE\n- [ ] item number {i}\n## PROGRESS LOG\n",
            encoding="utf-8",
        )
        gj = dict(goal_json)
        gj["file"] = str(goal_file)
        active_goal_path.write_text(json.dumps(gj), encoding="utf-8")
        code, _, _ = run_hook(_stop_payload(session_id), env=env)
        codes.append(code)

    assert codes[:3] == [BLOCK, BLOCK, BLOCK], codes
    assert codes[3] == ALLOW, "4th continuation must be denied by the hard counter"


def test_goal_continuation_blocks_end_to_end_when_queue_heading_is_wrong_level(tmp_path):
    """End-to-end (real subprocess, not the pure predicate) proof that a goal file
    whose QUEUE heading is typo'd to a non-H2 level still drives continuation --
    before the _HEADING_LINE fix this silently ALLOWED the stop with real open
    work still queued, because goal_next_open_item saw no heading at all."""
    env = _goal_env(
        tmp_path,
        {"id": "GOAL-T8", "active": True, "expires_at_et": "2099-01-01"},
        "# GOAL: G8\n### QUEUE\n- [ ] item under an H3 QUEUE heading\n## PROGRESS LOG\n",
    )
    code, stdout, stderr = run_hook(_stop_payload(f"pyt-goal-{uuid.uuid4().hex[:8]}"), env=env)
    assert code == BLOCK
    assert "item under an H3 QUEUE heading" in (stdout + stderr)


def test_goal_continuation_convergence_stop_same_item_twice(tmp_path):
    """Brake 3: if the item named at the last block is unchanged, the next Stop
    allows -- this is also the 'never blocks twice for the same reason' guarantee."""
    session_id = f"pyt-goal-{uuid.uuid4().hex[:8]}"
    env = _goal_env(
        tmp_path,
        {"id": "GOAL-T8", "active": True, "expires_at_et": "2099-01-01"},
        _GOAL_MD_OPEN,
    )
    first, _, _ = run_hook(_stop_payload(session_id), env=env)
    # Goal file is untouched -- the next open item is identical to the one just named.
    second, _, _ = run_hook(_stop_payload(session_id), env=env)
    assert first == BLOCK
    assert second == ALLOW, "unchanged next item must not block again (convergence)"


def test_block_messages_are_ascii_safe():
    """Regression: goal-file prose is copied verbatim into the Stop-hook block message,
    which lands on a non-UTF-8 Windows console. An em-dash arrived as a replacement glyph
    twice on 2026-08-29 -- garbling the loop's PRIMARY instruction channel."""
    import gamma_doctrine as G

    folded = G._ascii_safe("Step 4 — Action cards · “quoted” · 5 ≥ 3 → done…")
    assert folded.isascii(), folded
    assert "--" in folded and "->" in folded and ">=" in folded
    assert '"quoted"' in folded


def test_ascii_safe_never_raises_on_none_or_empty():
    import gamma_doctrine as G

    assert G._ascii_safe("") == ""
    assert G._ascii_safe(None) == ""


@pytest.mark.parametrize(
    "msg",
    [
        "Everything else is ready. Still owed: the chat endpoint. That's next.",
        "Fixed the guard. Next up: the cost meter.",
        "Committed. Then I will wire the digest.",
        "That's the next real autonomy fix if you want it.",
    ],
)
def test_deferral_endings_are_caught(msg):
    """J, 2026-08-29: 'i thought hooks prevented you from ending with saying you are doing
    something and not doing it.' He was right -- announcing future work and stopping passed
    both the OP-0 ask-guard and the OP-33 claim-guard. Ending on a promise is not a report."""
    assert D.is_deferral(msg)


@pytest.mark.parametrize(
    "msg",
    [
        "A workflow is running the other lanes in the background; I will report when it lands.",
        "Shipped all six. Revert with git revert abc123.",
        "Arming live money needs you (OP-0 #1) -- that is next only with your go-ahead.",
    ],
)
def test_inflight_and_escalation_endings_are_not_deferrals(msg):
    assert not D.is_deferral(msg)


@pytest.mark.parametrize(
    "msg",
    [
        "Revert with git revert if you want to undo it.",
        "Set GAMMA_HOOKS_OFF=1 if you want to silence the hooks.",
    ],
)
def test_instructional_if_you_want_to_is_not_an_ask(msg):
    """'if you want to <verb>' teaches J how to act; 'if you want it' asks J whether
    Gamma should. Only the second is the OP-0 anti-pattern."""
    assert not D.is_permission_question(msg)


@pytest.mark.parametrize(
    "msg",
    [
        # The 2026-08-30 escape, verbatim. J: "why did you violate operating
        # principles and not just build it. i thought we had hooks in place."
        "The load test I can force by spawning agents; the control surface is a real "
        "build. Say which and I'll go.",
        "Which one do you want?",
        "Tell me which and I start.",
        "Pick one and I'll build it.",
        "Let me know which lane to take.",
        "Two options — your pick.",
    ],
)
def test_choice_requests_are_permission_questions(msg):
    """A MENU is the same failed turn as asking permission.

    _ASK_PATTERNS was built entirely around permission verbs (want me to, shall I,
    your call), and a menu does not ask permission -- it asks for a SELECTION. So the
    whole "say which / pick one / which do you want" family walked past a table that
    had no concept of it, which is how a rule already on file as re-violated
    ("ranked list + say go IS a menu") got violated again.
    """
    assert D.is_permission_question(msg)


@pytest.mark.parametrize(
    "msg",
    [
        "Revert with git revert if you want to undo it.",
        "I picked the second one and shipped it; revert with git revert abc1234.",
        "Which file it reads is decided by the payload, not the client.",
        "It will go through the LOUD band from now on.",
    ],
)
def test_declarative_which_is_not_a_menu(msg):
    """"Which" as a relative pronoun, and a reported decision, must stay legal --
    otherwise the guard blocks the very reports OP-0 asks for."""
    assert not D.is_permission_question(msg)
