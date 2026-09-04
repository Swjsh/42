"""Guard: PreToolUse blocks a credential LITERAL from ever reaching disk (2026-09-03).

ROOT CAUSE this closes: .gitignore correctly protects credential FILES (.mcp.json,
automation/state/fleet/secrets.json) -- every one of this repo's six leaked Alpaca paper
credentials (four commits: 2026-06-15, 06-19, 06-24, 09-03) happened because a session
READ a value out of one of those files and then WROTE THE LITERAL into ordinary tracked
source (a hardcoded env fallback, an ACCOUNT_KEYS dict, a debug script, a docs example).
gitignore cannot stop that. The pre-commit staged scan (github_audit.py --staged) is the
LAST line of defence -- it catches the literal only once it is already on disk and
staged. This test file proves the FIRST line: setup/hooks/gamma_doctrine.py's PreToolUse
handler now refuses the Write/Edit/NotebookEdit/MultiEdit/Bash/PowerShell call itself.

FIX: setup/hooks/doctrine.py gained `credential_write_hit()` / `credential_deny_message()`,
built on `CREDENTIAL_PATTERNS` -- an ALIAS of setup/scripts/github_audit.py's
`SECRET_PATTERNS` (imported, not copied: a pattern widened there, e.g. by a sibling
session adding live-key/secret/token coverage, is picked up here automatically). That
import required one tiny refactor: github_audit.py's `PROJECT_ROOT` used to be computed
EAGERLY at import time via a `git rev-parse` subprocess -- fine for a script invoked once,
but doctrine.py now imports that module on every single PreToolUse Write/Edit/Bash call,
so `_project_root()` is now a lazy, cached accessor instead (see github_audit.py's own
comment at the top of that section for the full before/after).

These tests exercise the CLI end-to-end (subprocess, stdin JSON, real exit code) --
exactly the shape Claude Code itself invokes the hook with -- never a pure-function-only
proxy for "the hook blocks this". They never touch the real repo's git state, params, or
generated surfaces.

NEVER a real credential in this file. Every synthetic key is built by STRING
CONCATENATION (`"PK" + "A" * 24`) -- the trick backtest/tests/test_github_audit_staged_
2026_09_03.py already uses and documents -- so the resolved literal only ever exists as a
Python runtime value, never as a literal substring of this file's own source (which this
guard itself, and the pre-commit gate, would otherwise flag when this file is committed).

Run: python -m pytest backtest/tests/test_doctrine_hook_blocks_credential_writes_2026_09_03.py -q
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO / "setup" / "hooks"
_SCRIPTS_DIR = _REPO / "setup" / "scripts"
_HOOK = _HOOKS_DIR / "gamma_doctrine.py"

for _p in (_HOOKS_DIR, _SCRIPTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import doctrine as D  # noqa: E402
import github_audit  # noqa: E402

ALLOW, BLOCK = 0, 2

# Fixture-only fake credential, built by concatenation -- never a real key, and never a
# literal PK+24 substring anywhere in THIS file's own source. Same trick, same rationale
# as test_github_audit_staged_2026_09_03.py's FAKE_ALPACA_KEY.
FAKE_ALPACA_KEY = "PK" + "A" * 24
assert len(FAKE_ALPACA_KEY) == 26


def run_hook(payload: dict, env: dict | None = None) -> tuple[int, str, str]:
    full_env = dict(os.environ)
    # Real subprocess -> real telemetry sink; keep this suite out of production pulse.jsonl
    # the same way setup/hooks/test_doctrine_hooks.py's run_hook() does.
    full_env.setdefault(
        "GAMMA_PULSE_PATH", str(Path(tempfile.gettempdir()) / "gamma-test-pulse-cred.jsonl")
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


# ── 1. Write carrying a synthetic key is blocked and redacted ─────────────────────────

def test_write_with_credential_is_blocked_and_redacted():
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "automation/scripts/some_new_script.py",
                "content": f'ALPACA_API_KEY = "{FAKE_ALPACA_KEY}"\n',
            },
        }
    )
    combined = stdout + stderr
    assert code == BLOCK, combined
    assert FAKE_ALPACA_KEY not in combined, "raw secret leaked into hook output"
    assert FAKE_ALPACA_KEY[:4] in combined
    assert "Alpaca API key" in combined


# ── 2. Edit is blocked ─────────────────────────────────────────────────────────────────

def test_edit_with_credential_is_blocked():
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "automation/scripts/existing_script.py",
                "old_string": 'API_KEY = os.environ.get("ALPACA_API_KEY")',
                "new_string": f'API_KEY = os.environ.get("ALPACA_API_KEY", "{FAKE_ALPACA_KEY}")',
            },
        }
    )
    assert code == BLOCK, stdout + stderr


# ── 3. Bash heredoc carrying one is blocked ────────────────────────────────────────────

def test_bash_heredoc_with_credential_is_blocked():
    command = (
        "cat > automation/scripts/leaky.py <<'EOF'\n"
        f'ALPACA_API_KEY = "{FAKE_ALPACA_KEY}"\n'
        "EOF"
    )
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }
    )
    combined = stdout + stderr
    assert code == BLOCK, combined
    assert FAKE_ALPACA_KEY not in combined


def test_bash_echo_redirect_with_credential_is_blocked():
    command = f'echo "ALPACA_API_KEY={FAKE_ALPACA_KEY}" > automation/scripts/leaky2.py'
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }
    )
    assert code == BLOCK, stdout + stderr


# ── 4. A concatenated fixture is NOT blocked ───────────────────────────────────────────

def test_concatenated_fixture_write_is_not_blocked():
    """This is what a session SHOULD write when it needs a synthetic key for a test --
    the exact pattern this file itself uses. The literal text reaching disk in this case
    is the source code `"PK" + "A" * 24`, not a resolved 26-char credential-shaped run,
    so no CREDENTIAL_PATTERNS regex matches it."""
    content = (
        'FAKE_ALPACA_KEY = "PK" + "A" * 24\n'
        "assert len(FAKE_ALPACA_KEY) == 26\n"
    )
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "backtest/tests/test_some_new_fixture_2026_09_03.py",
                "content": content,
            },
        }
    )
    assert code == ALLOW, stdout + stderr


# ── 5. A normal Write is not blocked ───────────────────────────────────────────────────

def test_ordinary_write_is_not_blocked():
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "analysis/recommendations/note.md",
                "content": "# Just a note\n\nNothing secret here, only prose.\n",
            },
        }
    )
    assert code == ALLOW, stdout + stderr


def test_ordinary_bash_is_not_blocked():
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git status --short"},
        }
    )
    assert code == ALLOW, stdout + stderr


# ── 6. GAMMA_HOOKS_OFF=1 disables it ────────────────────────────────────────────────────

def test_hooks_off_env_disables_credential_guard():
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "automation/scripts/some_new_script.py",
                "content": f'ALPACA_API_KEY = "{FAKE_ALPACA_KEY}"\n',
            },
        },
        env={"GAMMA_HOOKS_OFF": "1"},
    )
    assert code == ALLOW, stdout + stderr


# ── 7. The message names the runtime-loader alternative ────────────────────────────────

def test_deny_message_names_runtime_loader_alternative():
    code, stdout, stderr = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "automation/scripts/some_new_script.py",
                "content": f'ALPACA_API_KEY = "{FAKE_ALPACA_KEY}"\n',
            },
        }
    )
    combined = stdout + stderr
    assert code == BLOCK, combined
    assert "_load_account_keys()" in combined
    assert "fast_path_executor.py" in combined
    assert "noqa:secret-ok" in combined


# ── 8. The pattern list is IMPORTED, not duplicated ─────────────────────────────────────

def test_credential_patterns_is_the_same_object_as_github_audit_secret_patterns():
    assert D.CREDENTIAL_PATTERNS is github_audit.SECRET_PATTERNS


def test_credential_patterns_widened_in_place_is_picked_up_automatically():
    """Proves this is a live reference to the SAME list object, not a value copied at
    import time: appending to github_audit.SECRET_PATTERNS IN PLACE -- the natural way a
    sibling session adds a new live-key/secret/token pattern -- is visible to
    doctrine.CREDENTIAL_PATTERNS (and therefore credential_write_hit()) with no second
    edit here, because both names point at the one list object (test 8 above)."""
    import re as _re

    sentinel_pattern = (
        _re.compile(r"\bZZTESTSENTINEL[0-9]{10}\b"),
        "Test sentinel credential",
        "HIGH",
    )
    github_audit.SECRET_PATTERNS.append(sentinel_pattern)
    try:
        assert sentinel_pattern in D.CREDENTIAL_PATTERNS
        hit = D.credential_write_hit("TOKEN = ZZTESTSENTINEL1234567890")
        assert hit is not None
        assert hit[0] == "Test sentinel credential"
    finally:
        github_audit.SECRET_PATTERNS.remove(sentinel_pattern)


# ── Pure-predicate coverage (fast, no subprocess) for the same behaviour ────────────────

def test_pure_credential_write_hit_matches_alpaca_key():
    hit = D.credential_write_hit(f'ALPACA_API_KEY = "{FAKE_ALPACA_KEY}"')
    assert hit is not None
    label, prefix, severity = hit
    assert label == "Alpaca API key"
    assert prefix == FAKE_ALPACA_KEY[:4]
    assert severity == "HIGH"


def test_pure_credential_write_hit_ignores_concatenation_fixture():
    assert D.credential_write_hit('FAKE_ALPACA_KEY = "PK" + "A" * 24') is None


def test_pure_credential_write_hit_honours_noqa_escape():
    line = f'ALPACA_API_KEY = "{FAKE_ALPACA_KEY}"  # noqa:secret-ok'
    assert D.credential_write_hit(line) is None


def test_pure_credential_write_hit_none_on_empty_or_plain_text():
    assert D.credential_write_hit("") is None
    assert D.credential_write_hit("just some ordinary prose about the market") is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
