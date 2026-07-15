"""Reaper-exemption + trigger-safety guard for Gamma_TwinChaos -- static, no live
Windows calls. Mirrors test_crypto_twin_reaper_exemption.py's structure exactly
(same two independent exemption layers apply -- see that file's module docstring for
the full "why this exists" background); this file scopes the installer-specific
checks to setup/scripts/install-twin-chaos-drill.ps1.

Layer 1 (pythonw.exe outside Stop-StaleClaudeProcesses's Name filter) is already
covered generically by test_crypto_twin_reaper_exemption.py's
TestReaperNameFilterExcludesPythonw class (it asserts against _shared.ps1 itself, not
any one installer) -- not duplicated here. This file covers Layer 2 (the
backtest\\.venv path marker) against THIS installer's own real command line, plus the
Weekly-trigger-not-one-time-trigger safety property specific to a once-a-week cadence
(project_scheduled_task_onetime_trigger_dark -- a bare one-time trigger with no
recurrence spec goes dark after the install day; a Weekly+DaysOfWeek trigger is the
proven safe pattern, same as install-open-bell-status.ps1 / install-macro-calendar.ps1).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SHARED_PS1 = REPO / "setup" / "scripts" / "_shared.ps1"
INSTALLER_PS1 = REPO / "setup" / "scripts" / "install-twin-chaos-drill.ps1"


def _installer_text() -> str:
    return INSTALLER_PS1.read_text(encoding="utf-8")


def _extract_exempt_daemons(text: str) -> list[str]:
    """Verbatim copy of test_crypto_twin_reaper_exemption.py's own line-based
    extractor (not imported -- test modules don't import each other's internals in
    this codebase's convention). See that file's docstring for why a naive
    single-regex blob match breaks on the array's own inline prose."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip().startswith("$EXEMPT_DAEMONS")), None)
    assert start is not None, "could not find $EXEMPT_DAEMONS = @(...) in _shared.ps1"
    daemons: list[str] = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped == ")":
            break
        if stripped.startswith("#"):
            continue
        daemons.extend(re.findall(r"'([^']+)'", line))
    return daemons


def _find_line(text: str, prefix: str) -> str:
    line = next((l for l in text.splitlines() if l.strip().startswith(prefix)), None)
    assert line is not None, f"could not find a line starting with {prefix!r} in install-twin-chaos-drill.ps1"
    return line


# ---------------------------------------------------------------------------
# Layer 2: DEFENSE IN DEPTH -- backtest\.venv path match (shared array, verified
# once already by test_crypto_twin_reaper_exemption.py; re-verified here so THIS
# installer's own suite is self-contained and doesn't silently rely on another
# test file's import order).
# ---------------------------------------------------------------------------
def test_exempt_daemons_contains_a_backtest_venv_marker() -> None:
    daemons = _extract_exempt_daemons(SHARED_PS1.read_text(encoding="utf-8"))
    assert any("backtest" in d and ".venv" in d for d in daemons)


# ---------------------------------------------------------------------------
# The installer itself: prove the REAL registered command line matches the
# exemption, uses the flash-free chain, and recurs safely (Weekly, not one-time).
# ---------------------------------------------------------------------------
class TestInstallerCommandLineMatchesExemption:
    def test_installer_exists(self) -> None:
        assert INSTALLER_PS1.exists(), f"install-twin-chaos-drill.ps1 missing at {INSTALLER_PS1}"

    def test_installer_task_name_is_gamma_twin_chaos(self) -> None:
        line = _find_line(_installer_text(), "$taskName")
        assert "Gamma_TwinChaos" in line

    def test_installer_pythonw_var_points_at_backtest_venv(self) -> None:
        line = _find_line(_installer_text(), "$pythonwVenv")
        assert "backtest\\.venv\\Scripts\\pythonw.exe" in line, (
            f"$pythonwVenv does not reference the backtest-venv pythonw path: {line}"
        )

    def test_installer_wscript_args_actually_uses_the_pythonw_var(self) -> None:
        line = _find_line(_installer_text(), "$wscriptArgs")
        assert "$pythonwVenv" in line
        assert "$script" in line
        assert "$vbs" in line
        assert "--all" in line

    def test_installer_script_target_is_twin_chaos_drill(self) -> None:
        line = _find_line(_installer_text(), "$script")
        assert "twin_chaos_drill.py" in line

    def test_installer_execute_is_wscript_not_a_bare_console_launcher(self) -> None:
        text = _installer_text()
        assert 'New-ScheduledTaskAction -Execute "wscript.exe"' in text, (
            "install-twin-chaos-drill.ps1's task Execute must be wscript.exe (WS6 "
            "flash-free doctrine) -- a bare cmd.exe/powershell.exe/python.exe Execute "
            "would both flash a console AND put python.exe (IN the reaper's Name "
            "filter) directly into Win32_Process's Name field instead of pythonw.exe."
        )

    def test_installer_multiple_instances_ignore_new(self) -> None:
        text = _installer_text()
        assert "-MultipleInstances IgnoreNew" in text


# ---------------------------------------------------------------------------
# Trigger safety: Weekly + DaysOfWeek, never a bare one-time/interval trigger
# (project_scheduled_task_onetime_trigger_dark -- a trigger with no recurrence spec
# goes dark after the install day).
# ---------------------------------------------------------------------------
class TestWeeklyTriggerNotOneTime:
    def test_uses_weekly_trigger(self) -> None:
        text = _installer_text()
        assert "New-ScheduledTaskTrigger -Weekly" in text

    def test_scoped_to_sunday(self) -> None:
        text = _installer_text()
        assert "-DaysOfWeek Sunday" in text

    def test_never_passes_an_et_literal_to_at(self) -> None:
        """03:00 ET must be expressed as 01:00 (MT, this rig's local clock) -- a raw
        '03:00' literal would silently fire 2h early against real ET (the exact scar
        every other Weekly installer's own docstring warns about)."""
        text = _installer_text()
        assert '-At "01:00"' in text
        assert '-At "03:00"' not in text

    def test_does_not_use_a_bare_once_trigger(self) -> None:
        """A '-Once' base trigger with no -RepetitionInterval/-DaysOfWeek recurrence
        is the dark-after-one-day foot-gun this test class exists to forbid for a
        WEEKLY task (Gamma_CryptoTwin's own 24/7 installer legitimately uses -Once +
        -RepetitionInterval together for its 5-min cadence -- that combination is
        fine; a bare -Once alone, or on THIS weekly installer at all, is not)."""
        text = _installer_text()
        assert "New-ScheduledTaskTrigger -Once" not in text

    def test_execution_time_limit_is_generous_for_a_real_drill_cycle(self) -> None:
        """Drill 1's real order fill-poll + managing-subprocess kill/recovery pair is
        the slowest leg -- must not be capped so tight a real cycle gets truncated
        mid-drill (which would abort BEFORE the restore-to-flat step)."""
        text = _installer_text()
        assert "ExecutionTimeLimit (New-TimeSpan -Minutes 15)" in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
