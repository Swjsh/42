"""WS6 CMD-popup guard — permanent regression test.

Ensures that:
  (a) _is_bare_console_launcher FAILS on the exact cmd.exe task shapes that
      existed BEFORE the WS6 fix (Gamma_Funnel_0..5, Gamma_Grind_all).
  (b) The approved replacement pattern (wscript->run_exe_hidden.vbs->pythonw->
      run_cmd_hidden.py) is recognized as hidden and NOT flagged.
  (c) audit_scheduled_tasks._is_hidden still accepts all pre-existing approved
      patterns (non-regression for the existing 24-task fix).
  (d) The audit emits BARE_CMD_POWERSHELL (not just VISIBLE_WINDOW) for bare
      console launcher tasks — so the flag is unambiguous and always exit 1.

Guard class: HARD — if any of these fail, a Gamma task is flashing OpenConsole
on every fire.  The audit exits 1 for BARE_CMD_POWERSHELL, so this shows up
RED in STATUS.md immediately.

2026-06-26 WS6 fix (author: Gamma WS6 workstream).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make setup/scripts importable from the backtest/tests location
SETUP_SCRIPTS = Path(__file__).resolve().parents[2] / "setup" / "scripts"
if str(SETUP_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SETUP_SCRIPTS))

from audit_scheduled_tasks import _is_bare_console_launcher, _is_hidden  # noqa: E402


# ---------------------------------------------------------------------------
# Pre-fix broken state — these are the EXACT task shapes from before WS6.
# The guard MUST flag them as bare console launchers.
# ---------------------------------------------------------------------------

class TestPreFixTasksAreFlashers:
    """Old cmd.exe task actions that flashed OpenConsole on every fire."""

    _FUNNEL_ARGS_TEMPLATE = (
        '/c "set GAMMA_FUNNEL_SHARD={shard}&& set GAMMA_FUNNEL_NSHARDS=6&& '
        r'C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe -m autoresearch.mass_grind_funnel '
        r'> C:\Users\jackw\Desktop\42\analysis\recommendations\mass-grind-funnel-{shard}-stdout.log 2>&1"'
    )

    @pytest.mark.parametrize("shard", range(6))
    def test_funnel_shard_is_bare_cmd(self, shard: int) -> None:
        """Gamma_Funnel_0..5 used cmd.exe — must be detected as a bare launcher."""
        assert _is_bare_console_launcher("cmd.exe"), (
            f"Gamma_Funnel_{shard}: cmd.exe must be detected as a bare console launcher. "
            "If this fails, the _is_bare_console_launcher guard was broken and the task "
            "will flash OpenConsole on every fire."
        )

    @pytest.mark.parametrize("shard", range(6))
    def test_funnel_shard_args_not_hidden(self, shard: int) -> None:
        """Confirm the OLD funnel cmd-line is NOT hidden (double-check via _is_hidden)."""
        args = self._FUNNEL_ARGS_TEMPLATE.format(shard=shard)
        assert not _is_hidden(execute="cmd.exe", arguments=args), (
            f"Gamma_Funnel_{shard}: cmd.exe action must NOT be considered hidden. "
            "_is_hidden should return False for bare cmd.exe invocations."
        )

    def test_grind_all_is_bare_cmd(self) -> None:
        """Gamma_Grind_all used cmd.exe — must be detected as a bare launcher."""
        assert _is_bare_console_launcher("cmd.exe"), (
            "Gamma_Grind_all: cmd.exe must be detected as bare console launcher."
        )

    def test_grind_all_args_not_hidden(self) -> None:
        """Confirm the OLD Grind_all cmd-line is NOT hidden."""
        args = (
            '/c "set GAMMA_GRIND_WORKERS=8&& '
            r'C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe -m autoresearch.mass_grind '
            r'> C:\Users\jackw\Desktop\42\analysis\recommendations\mass-grind-stdout.log 2>&1"'
        )
        assert not _is_hidden(execute="cmd.exe", arguments=args)


# ---------------------------------------------------------------------------
# Post-fix approved state — the new wscript chain must be recognized as hidden.
# ---------------------------------------------------------------------------

PYTHONW_BACKTEST = r"C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\pythonw.exe"
RUN_CMD_HIDDEN = r"C:\Users\jackw\Desktop\42\setup\scripts\run_cmd_hidden.py"
RUN_EXE_HIDDEN_VBS = r"C:\Users\jackw\Desktop\42\setup\scripts\run_exe_hidden.vbs"


class TestPostFixApprovedPattern:
    """New wscript->run_exe_hidden.vbs->pythonw->run_cmd_hidden.py chain."""

    def _funnel_args(self, shard: int) -> str:
        log = (
            fr"C:\Users\jackw\Desktop\42\analysis\recommendations"
            fr"\mass-grind-funnel-{shard}-stdout.log"
        )
        return (
            f'//nologo "{RUN_EXE_HIDDEN_VBS}" "{PYTHONW_BACKTEST}" "{RUN_CMD_HIDDEN}" '
            f'--env GAMMA_FUNNEL_SHARD={shard} --env GAMMA_FUNNEL_NSHARDS=6 '
            f'--log "{log}" --cwd '
            r'"C:\Users\jackw\Desktop\42\backtest" '
            f'-- '
            r'"C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\pythonw.exe" '
            r'-m autoresearch.mass_grind_funnel'
        )

    def _grind_all_args(self) -> str:
        log = r"C:\Users\jackw\Desktop\42\analysis\recommendations\mass-grind-stdout.log"
        return (
            f'//nologo "{RUN_EXE_HIDDEN_VBS}" "{PYTHONW_BACKTEST}" "{RUN_CMD_HIDDEN}" '
            f'--env GAMMA_GRIND_WORKERS=8 '
            f'--log "{log}" --cwd '
            r'"C:\Users\jackw\Desktop\42\backtest" '
            f'-- '
            r'"C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\pythonw.exe" '
            r'-m autoresearch.mass_grind'
        )

    @pytest.mark.parametrize("shard", range(6))
    def test_funnel_shard_fixed_is_hidden(self, shard: int) -> None:
        """After fix: wscript + run_exe_hidden.vbs chain must be recognized as hidden."""
        assert _is_hidden(execute="wscript.exe", arguments=self._funnel_args(shard)), (
            f"Gamma_Funnel_{shard} (fixed): wscript->run_exe_hidden.vbs chain not recognized "
            "as hidden — the audit will incorrectly flag it as VISIBLE_WINDOW."
        )

    @pytest.mark.parametrize("shard", range(6))
    def test_funnel_shard_fixed_not_bare_console(self, shard: int) -> None:
        """After fix: wscript.exe is NOT a bare console launcher."""
        assert not _is_bare_console_launcher("wscript.exe"), (
            f"Gamma_Funnel_{shard} (fixed): wscript.exe should not be flagged as a bare "
            "console launcher — it is GUI-subsystem and never allocates a console."
        )

    def test_grind_all_fixed_is_hidden(self) -> None:
        """After fix: Gamma_Grind_all wscript chain is hidden."""
        assert _is_hidden(execute="wscript.exe", arguments=self._grind_all_args())

    def test_grind_all_fixed_not_bare_console(self) -> None:
        """After fix: wscript.exe for Grind_all is not a bare console launcher."""
        assert not _is_bare_console_launcher("wscript.exe")


# ---------------------------------------------------------------------------
# Bare-launcher detection — edge cases and coverage
# ---------------------------------------------------------------------------

class TestBareLauncherDetection:
    """Unit tests for _is_bare_console_launcher covering paths and case."""

    def test_cmd_bare(self) -> None:
        assert _is_bare_console_launcher("cmd.exe")

    def test_powershell_bare(self) -> None:
        assert _is_bare_console_launcher("powershell.exe")

    def test_cmd_full_path(self) -> None:
        assert _is_bare_console_launcher(r"C:\Windows\System32\cmd.exe")

    def test_powershell_full_path(self) -> None:
        assert _is_bare_console_launcher(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")

    def test_case_insensitive_cmd(self) -> None:
        assert _is_bare_console_launcher("CMD.EXE")

    def test_case_insensitive_powershell(self) -> None:
        assert _is_bare_console_launcher("PowerShell.exe")

    def test_wscript_not_bare(self) -> None:
        assert not _is_bare_console_launcher("wscript.exe")

    def test_pythonw_not_bare(self) -> None:
        assert not _is_bare_console_launcher("pythonw.exe")

    def test_python_not_bare_console_launcher(self) -> None:
        # python.exe is console-subsystem but handled by PYTHON_NOT_PYTHONW flag,
        # not by the BARE_CMD_POWERSHELL check — they are separate audit flags.
        assert not _is_bare_console_launcher("python.exe")

    def test_empty_not_bare(self) -> None:
        assert not _is_bare_console_launcher("")

    def test_none_not_bare(self) -> None:
        assert not _is_bare_console_launcher(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Non-regression: existing approved patterns still accepted by _is_hidden
# ---------------------------------------------------------------------------

class TestExistingApprovedPatternsNonRegression:
    """Lock in the 2026-05-18 fix (24 false-positive VISIBLE_WINDOW flags) and
    ensure WS6 changes did not break it."""

    def test_run_hidden_vbs_still_recognized(self) -> None:
        """Older wscript + run_hidden.vbs pattern must still pass."""
        assert _is_hidden(
            execute="wscript.exe",
            arguments='//nologo "C:\\path\\run_hidden.vbs" "C:\\path\\some-script.ps1"',
        )

    def test_run_exe_hidden_vbs_ps1_still_recognized(self) -> None:
        """Canonical L42 pattern (run_exe_hidden.vbs + pythonw + run_ps1_hidden.py) still passes."""
        assert _is_hidden(
            execute="wscript.exe",
            arguments=(
                '//nologo "C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run_exe_hidden.vbs" '
                '"C:\\Users\\jackw\\AppData\\Local\\Programs\\Python\\Python313\\pythonw.exe" '
                '"C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run_ps1_hidden.py" '
                '"C:\\Users\\jackw\\Desktop\\42\\setup\\scripts\\run-heartbeat.ps1"'
            ),
        )

    def test_pythonw_direct_still_recognized(self) -> None:
        """Direct pythonw.exe task (GUI-subsystem, no console) still passes."""
        assert _is_hidden(
            execute=r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe",
            arguments=r'"C:\Users\jackw\Desktop\42\setup\scripts\some_script.py"',
        )

    def test_bare_powershell_no_windowstyle_still_fails(self) -> None:
        """Bare powershell.exe without -WindowStyle Hidden must still fail _is_hidden."""
        assert not _is_hidden(
            execute="powershell.exe",
            arguments='-NoProfile -File "C:\\path\\script.ps1"',
        )
