"""Tests for audit_scheduled_tasks._is_hidden — OP-27 approved hidden-window patterns.

Per OP-27 L42 escalation (2026-05-17 evening), the canonical zero-leak chain is:
    wscript.exe //nologo run_exe_hidden.vbs <sys-pythonw> <run_ps1_hidden.py> <ps1>

The audit was failing to recognize this pattern (only accepted the older `run_hidden.vbs`).
This test locks in both approved patterns + rejects bare invocations.

Run: pytest -v setup/scripts/test_audit_scheduled_tasks.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the audit module importable
SETUP_SCRIPTS = Path(__file__).resolve().parent
if str(SETUP_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SETUP_SCRIPTS))

from audit_scheduled_tasks import _is_hidden  # noqa: E402


# =====================================================================
# Approved patterns (must return True)
# =====================================================================

def test_wscript_run_hidden_vbs_is_hidden() -> None:
    """The older OP-27 pattern: wscript + run_hidden.vbs wrapping a PS1."""
    assert _is_hidden(
        execute="wscript.exe",
        arguments='//nologo "C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run_hidden.vbs" '
                  '"C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run-heartbeat.ps1"',
    )


def test_wscript_run_exe_hidden_vbs_is_hidden() -> None:
    """The canonical OP-27 L42 pattern: wscript + run_exe_hidden.vbs + pythonw + ps1.
    This was the 24-task false-positive fix on 2026-05-18 ET."""
    assert _is_hidden(
        execute="wscript.exe",
        arguments='//nologo "C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run_exe_hidden.vbs" '
                  '"C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe" '
                  '"C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run_ps1_hidden.py" '
                  '"C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run-heartbeat-aggressive.ps1"',
    )


def test_powershell_windowstyle_hidden_is_hidden() -> None:
    """powershell.exe with explicit -WindowStyle Hidden (used by some one-off tasks)."""
    assert _is_hidden(
        execute="powershell.exe",
        arguments='-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass '
                  '-File "C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\some-script.ps1"',
    )


def test_case_insensitive_matching() -> None:
    """The matcher must be case-insensitive (Windows task XML can use any case)."""
    assert _is_hidden(execute="WSCRIPT.EXE", arguments='//NOLOGO "RUN_HIDDEN.VBS" "FOO.PS1"')
    assert _is_hidden(execute="PowerShell.exe", arguments='-WindowStyle hidden -File foo.ps1')


# =====================================================================
# NOT-approved patterns (must return False)
# =====================================================================

def test_bare_powershell_is_not_hidden() -> None:
    """powershell.exe WITHOUT -WindowStyle Hidden flashes a console window."""
    assert not _is_hidden(
        execute="powershell.exe",
        arguments='-NoProfile -File "C:\\some\\script.ps1"',
    )


def test_bare_python_is_not_hidden() -> None:
    """python.exe (console subsystem) always allocates a console window."""
    assert not _is_hidden(
        execute="python.exe",
        arguments='C:\\Users\\jackw\\some\\script.py',
    )


def test_bare_cmd_is_not_hidden() -> None:
    """cmd.exe always allocates a console."""
    assert not _is_hidden(
        execute="cmd.exe",
        arguments='/c some_command',
    )


def test_wscript_without_approved_vbs_is_not_hidden() -> None:
    """wscript with a DIFFERENT vbs (not in the approved list) should fail.
    Prevents someone introducing a new vbs wrapper that isn't actually hidden-safe."""
    assert not _is_hidden(
        execute="wscript.exe",
        arguments='//nologo "C:\\path\\some_other_wrapper.vbs" "foo.ps1"',
    )


def test_empty_or_null_args() -> None:
    """Defensive: null/empty inputs return False, not crash."""
    assert not _is_hidden(execute="", arguments="")
    assert not _is_hidden(execute=None, arguments=None)  # type: ignore[arg-type]


# =====================================================================
# Regression guard for the 2026-05-18 fix
# =====================================================================

def test_regression_24_false_positives_fixed() -> None:
    """Locks in the 2026-05-18 fix: the audit was flagging 24 production tasks as
    VISIBLE_WINDOW because it only recognized `run_hidden.vbs`, not the newer
    canonical `run_exe_hidden.vbs` (OP-27 L42).

    If this test fails, someone reverted the fix and the audit will spam 24
    false-positive flags again, hiding any REAL future flag in the noise.
    """
    canonical_l42_invocation = (
        '//nologo "C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run_exe_hidden.vbs" '
        '"C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe" '
        '"C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run_ps1_hidden.py" '
        '"C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run-eod-flatten.ps1"'
    )
    assert _is_hidden(execute="wscript.exe", arguments=canonical_l42_invocation), \
        "OP-27 L42 canonical pattern (run_exe_hidden.vbs + pythonw + run_ps1_hidden.py) " \
        "must be recognized as hidden — reverting this breaks 24 production tasks' audit."
