"""Regression guards for the shell-write bypass found 2026-08-29.

THE BUG: the freeze and generated-surface guards were dispatched only inside the
Edit/Write/NotebookEdit/MultiEdit branch, so they guarded TOOL NAMES rather than FILES.
Reproduced directly before the fix:

    Edit  automation/state/params.json              -> exit 2   blocked
    sed -i s/0.8/0.5/ automation/state/params.json  -> exit 0   sailed through
    echo x > MAP.md                                 -> exit 0   sailed through

Why it mattered more than it looks: the freeze window opens 2026-08-31 to give
go_live_gate.py 20 clean scoring days, one shell write to params.json silently
invalidates it, and pulse telemetry records shell calls WITHOUT a path -- so it would
not be discoverable afterwards either. And under OP-0 ("act, don't ask") a blocked Edit
produces a workaround rather than an escalation, which means the Edit-only guard was
actively signposting the unguarded route.

The second half of this file matters as much as the first: this guard may NEVER block
ordinary work (the OP-32 lockout scar). A path MENTIONED is not a path WRITTEN.

Run: backtest/.venv/Scripts/python.exe -m pytest setup/hooks/test_shell_write_guard.py -q
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


def run_hook(payload: dict, env: dict | None = None) -> tuple[int, str, str]:
    full_env = dict(os.environ)
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
# it catches real writes
# ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "cmd",
    [
        "sed -i s/0.8/0.5/ automation/state/params.json",
        "sed --in-place 's/a/b/' backtest/lib/filters.py",
        "echo x > automation/state/params.json",
        "echo x >> automation/state/aggressive/params.json",
        "cat foo | tee automation/state/fleet/accounts.json",
        "echo hi > MAP.md",
        "printf x >> HOME.md",
        "dd if=/dev/zero of=backtest/lib/risk_gate.py",
        "cp /tmp/evil.json automation/state/params.json",
        "mv /tmp/x.py setup/scripts/heartbeat_core.py",
        "Set-Content -Path automation/state/params.json -Value x",
        "Out-File MAP.md",
    ],
)
def test_shell_writes_to_protected_paths_are_caught(cmd):
    assert D.shell_write_hit(cmd) is not None, cmd


# ---------------------------------------------------------------------------------------
# and it never blocks ordinary work -- the half that protects J
# ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "cmd",
    [
        "grep -n tp1 automation/state/params.json",
        "cat backtest/lib/filters.py",
        "cp backtest/lib/filters.py /tmp/backup.py",
        "git log --oneline -- automation/state/params.json",
        "echo done > /tmp/scratch.txt",
        "pytest setup/hooks -q > /tmp/out.txt",
        "ls automation/state/params.json",
        "wc -l MAP.md",
        "diff MAP.md /tmp/old-map.md",
        "python setup/scripts/et_clock.py",
    ],
)
def test_reading_or_unrelated_writes_are_never_blocked(cmd):
    assert D.shell_write_hit(cmd) is None, cmd


def test_copy_FROM_a_protected_file_is_legal():
    """Only the final operand of cp/mv is a write target. Backing up a frozen file is
    ordinary work and must stay allowed."""
    assert D.shell_write_hit("cp automation/state/params.json /tmp/params.bak") is None
    assert D.shell_write_hit("cp /tmp/params.bak automation/state/params.json") is not None


def test_stderr_redirect_is_not_a_write():
    assert D.shell_write_hit("pytest -q 2>&1 | tee /tmp/log.txt") is None


def test_a_command_quoted_as_DATA_is_not_a_write():
    """Regression: this guard blocked its OWN verification command within a minute of
    being written. A shell loop carries whole commands inside quotes as data:

        for c in "sed -i ... params.json" "echo x > MAP.md"; do ... done

    Nothing is written there. Quoted spans containing whitespace are blanked before
    scanning -- exact, not heuristic, because every protected path is a single
    space-free token and so can never BE a multi-word quoted span."""
    assert D.shell_write_hit('for c in "echo x > MAP.md"; do echo "$c"; done') is None
    assert D.shell_write_hit('echo "run: sed -i s/a/b/ automation/state/params.json"') is None


def test_quote_scanner_survives_apostrophes_and_escaped_quotes():
    """Regression, found twice in a row by this guard blocking its own commit.

    First attempt used a regex over ``[^'"]*`` -- an apostrophe inside a double-quoted
    commit message ended the character class early, the span never closed, and fragments
    leaked. Second attempt scanned for the matching quote but not for ``\\"`` escapes, so
    the span closed at the first escaped inner quote and leaked the rest. Both cases are
    ordinary commit messages, which is precisely the ordinary work this may never block."""
    q = chr(39)
    msg_with_apostrophe = 'git commit -m "closed the ' + q + "sed -i params.json" + q + ' bypass"'
    assert D.shell_write_hit(msg_with_apostrophe) is None

    msg_with_escaped_quote = (
        'commit_scoped.py "fix: the guard' + q + 's note said \\"echo x > MAP.md\\" leaked" a.py'
    )
    assert D.shell_write_hit(msg_with_escaped_quote) is None


def test_unterminated_quote_does_not_swallow_the_command():
    """An unbalanced quote must not blank the remainder and hide a real write."""
    assert D.shell_write_hit('echo "oops > /tmp/x') is None


def test_quoted_TARGETS_are_still_caught():
    """The other half: blanking must not become a bypass. A genuinely quoted write
    target has no whitespace, so it survives the blanking and is still inspected."""
    assert D.shell_write_hit('sed -i "s/a/b/" "automation/state/params.json"') is not None
    assert D.shell_write_hit('echo x > "MAP.md"') is not None


def test_shell_write_honours_the_freeze_override():
    cmd = "sed -i s/a/b/ automation/state/params.json  # " + D.FREEZE_OVERRIDE_TOKEN
    assert D.shell_write_hit(cmd) is None


def test_shell_write_ignores_heredoc_bodies():
    """A commit message DESCRIBING the bypass must not itself be blocked -- the same
    false-positive class already fixed once in bash_guard_hit."""
    cmd = "\n".join(
        [
            "git commit -F - <<'MSGEOF'",
            "fix: sed -i s/x/y/ automation/state/params.json was slipping through",
            "MSGEOF",
        ]
    )
    assert D.shell_write_hit(cmd) is None


def test_empty_and_garbage_input_never_raises():
    assert D.shell_write_hit("") is None
    assert D.shell_write_hit(None) is None


# ---------------------------------------------------------------------------------------
# end to end, through the real dispatcher
# ---------------------------------------------------------------------------------------
def test_shell_bypass_is_blocked_end_to_end_during_freeze():
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "sed -i s/0.8/0.5/ automation/state/params.json"},
        },
        env={"GAMMA_FREEZE_TODAY_OVERRIDE": "2026-09-05"},
    )
    assert code == BLOCK
    assert "frozen trading path" in (stdout + stderr)


def test_same_command_allowed_before_the_freeze_opens():
    """Doctrine-correct, not a hole: the freeze is a dated window."""
    code, _, _ = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "sed -i s/a/b/ automation/state/params.json"},
        },
        env={"GAMMA_FREEZE_TODAY_OVERRIDE": "2026-08-25"},
    )
    assert code == ALLOW


def test_shell_write_to_generated_surface_blocked_any_day():
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "echo x > MAP.md"},
        },
        env={"GAMMA_FREEZE_TODAY_OVERRIDE": "2026-08-25"},
    )
    assert code == BLOCK
    assert "obsidian_vault_sync" in (stdout + stderr)


def test_ordinary_shell_work_still_passes_end_to_end():
    code, _, _ = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "grep -n tp1 automation/state/params.json"},
        },
        env={"GAMMA_FREEZE_TODAY_OVERRIDE": "2026-09-05"},
    )
    assert code == ALLOW
