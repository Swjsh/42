"""Reaper-exemption guard for Gamma_CryptoTwin -- static, no live Windows calls.

WHY THIS EXISTS: "grinds silently killed before" is a named, recurring foot-gun
class in this codebase (CLAUDE.md debugging-discipline scar; C7/C8 lesson themes).
setup/scripts/_shared.ps1's Stop-StaleClaudeProcesses reaps any Win32_Process named
claude.exe/node.exe/python.exe/uv.exe/uvx.exe whose CommandLine references this repo
and is older than ~5 min, UNLESS its CommandLine matches one of $EXEMPT_DAEMONS.
Gamma_CryptoTwin (setup/install-crypto-twin.ps1) fires every 1 min, 24/7 (was 5 min
2026-07-10..2026-07-31, CADENCE-TUNE 2026-08-01) -- if its
process shape ever fell inside the reaper's blast radius, soak data would go dark
exactly like the historical grind-killer incidents this lesson is named after, and
nobody would notice until the soak report came up suspiciously thin.

TWO independent exemption layers, BOTH verified here against the REAL committed
source (never hand-copied or assumed):

  1. PRIMARY -- Name-filter omission. Stop-StaleClaudeProcesses's CIM query only
     asks Win32_Process for Name='claude.exe' OR 'node.exe' OR 'python.exe' OR
     'uv.exe' OR 'uvx.exe'. 'pythonw.exe' -- what crypto_twin_health.py actually runs
     under -- is not in that set at all, so the twin's process is never even fetched
     by the reaper's query, independent of EXEMPT_DAEMONS string matching.

  2. DEFENSE IN DEPTH -- EXEMPT_DAEMONS path match. The installer launches the twin
     via backtest\\.venv\\Scripts\\pythonw.exe (not system pythonw), so its
     CommandLine also contains the literal substring 'backtest\\.venv', which IS one
     of $EXEMPT_DAEMONS's existing entries (added for the mass_grind family, reused
     here for free) -- verified via the same plain-substring semantics PowerShell's
     `-like "*backtest\\.venv*"` performs (backslash and dot are not `-like`
     metacharacters, so this is a literal containment check, not a regex).

Pure file parsing (mirrors test_scheduled_tasks_doc.py / test_guard_cmd_popup_fix_
ws6.py's static-source-text convention) -- runs anywhere, no Windows Task Scheduler
needed, portable to CI.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SHARED_PS1 = REPO / "setup" / "scripts" / "_shared.ps1"
INSTALLER_PS1 = REPO / "setup" / "scripts" / "install-crypto-twin.ps1"


def _shared_text() -> str:
    return SHARED_PS1.read_text(encoding="utf-8")


def _installer_text() -> str:
    return INSTALLER_PS1.read_text(encoding="utf-8")


def _extract_cim_filter(text: str) -> str:
    """Pull the Win32_Process -Filter string literal used INSIDE
    Stop-StaleClaudeProcesses specifically. _shared.ps1 has OTHER unrelated
    Get-CimInstance Win32_Process -Filter calls (Stop-ProcessTree / Get-DescendantPids
    filter on ParentProcessId for a completely different purpose) -- naively taking
    "the first occurrence in the file" finds the wrong one, so this scopes the search
    to the Stop-StaleClaudeProcesses function body first."""
    fn = re.search(r"function Stop-StaleClaudeProcesses\b.*?(?=\nfunction |\Z)", text, re.DOTALL)
    assert fn, "could not find 'function Stop-StaleClaudeProcesses' in _shared.ps1 -- was it renamed?"
    m = re.search(r'Get-CimInstance Win32_Process -Filter "([^"]+)"', fn.group(0))
    assert m, ("could not find the Win32_Process -Filter string inside "
              "Stop-StaleClaudeProcesses -- its shape changed; update this test's regex.")
    return m.group(1)


def _extract_exempt_daemons(text: str) -> list[str]:
    """Pull every single-quoted string literal inside the $EXEMPT_DAEMONS = @(...)
    array via a LINE-based scan (not a single regex blob over the whole array text).
    A naive "match up to the first )" regex breaks here: one of the array's own
    inline comments reads "...(mass_grind shards + phase2)..." -- a stray ')'
    inside prose that would truncate a non-greedy blob match long before the real
    closing paren. Scanning line-by-line and skipping '#'-comment lines sidesteps
    that entirely; the array's real close is a line that, stripped, is exactly ')'."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip().startswith("$EXEMPT_DAEMONS")), None)
    assert start is not None, ("could not find $EXEMPT_DAEMONS = @(...) in _shared.ps1 -- "
                               "update this test if it was renamed or restructured.")
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
    assert line is not None, f"could not find a line starting with {prefix!r} in install-crypto-twin.ps1"
    return line


# ---------------------------------------------------------------------------
# Layer 1: PRIMARY exemption -- pythonw.exe is outside the reaper's Name filter.
# ---------------------------------------------------------------------------
class TestReaperNameFilterExcludesPythonw:
    def test_shared_ps1_exists(self) -> None:
        assert SHARED_PS1.exists(), f"_shared.ps1 missing at {SHARED_PS1}"

    def test_cim_filter_targets_python_exe(self) -> None:
        filt = _extract_cim_filter(_shared_text())
        assert "Name='python.exe'" in filt, f"expected the reaper filter to target python.exe, got: {filt}"

    def test_cim_filter_does_not_target_pythonw_exe(self) -> None:
        filt = _extract_cim_filter(_shared_text())
        assert "pythonw.exe" not in filt, (
            f"Stop-StaleClaudeProcesses's CIM filter now matches pythonw.exe: {filt!r} -- "
            "the PRIMARY reaper-exemption mechanism this task relies on (pythonw.exe is "
            "never even fetched by the query) no longer holds. If this test fails, "
            "TestExemptDaemonsPathMatch below (layer 2) is the only remaining "
            "protection for Gamma_CryptoTwin -- verify it still passes and treat this "
            "as a load-bearing change, not a routine update."
        )

    def test_wscript_also_outside_name_filter(self) -> None:
        """The task's outer Execute (wscript.exe, WS6 flash-free doctrine) is
        likewise never fetched by the reaper's query -- belt check, not load-bearing."""
        filt = _extract_cim_filter(_shared_text())
        assert "wscript.exe" not in filt


# ---------------------------------------------------------------------------
# Layer 2: DEFENSE IN DEPTH -- backtest\.venv path match in EXEMPT_DAEMONS.
# ---------------------------------------------------------------------------
class TestExemptDaemonsPathMatch:
    def test_exempt_daemons_contains_a_backtest_venv_marker(self) -> None:
        daemons = _extract_exempt_daemons(_shared_text())
        assert any("backtest" in d and ".venv" in d for d in daemons), (
            f"$EXEMPT_DAEMONS no longer contains a backtest-venv marker: {daemons} -- "
            "Gamma_CryptoTwin's defense-in-depth exemption (launching via "
            "backtest\\.venv\\Scripts\\pythonw.exe) depends on one of these substrings "
            "matching its CommandLine."
        )

    @pytest.mark.parametrize("marker", ["backtest\\.venv", "backtest/.venv"])
    def test_specific_known_markers_present(self, marker: str) -> None:
        daemons = _extract_exempt_daemons(_shared_text())
        assert marker in daemons, f"expected {marker!r} in $EXEMPT_DAEMONS, got {daemons}"


# ---------------------------------------------------------------------------
# The installer itself: prove the REAL registered command line matches.
# ---------------------------------------------------------------------------
class TestInstallerCommandLineMatchesExemption:
    def test_installer_exists(self) -> None:
        assert INSTALLER_PS1.exists(), f"install-crypto-twin.ps1 missing at {INSTALLER_PS1}"

    def test_installer_task_name_is_gamma_crypto_twin(self) -> None:
        line = _find_line(_installer_text(), "$taskName")
        assert "Gamma_CryptoTwin" in line

    def test_installer_pythonw_var_points_at_backtest_venv(self) -> None:
        """$pythonwVenv (the actual interpreter that will run crypto_twin_health.py)
        must resolve to the backtest venv path -- this is what puts the
        'backtest\\.venv' substring into the spawned process's real CommandLine."""
        line = _find_line(_installer_text(), "$pythonwVenv")
        assert "backtest\\.venv\\Scripts\\pythonw.exe" in line, (
            f"$pythonwVenv does not reference the backtest-venv pythonw path: {line}"
        )

    def test_installer_wscript_args_actually_uses_the_pythonw_var(self) -> None:
        """$wscriptArgs (what becomes the task's real Arguments, and therefore the
        spawned process's real CommandLine) must reference $pythonwVenv -- not some
        other interpreter -- so the exempt-marker path genuinely flows through to
        the live process, not just to an unused variable."""
        line = _find_line(_installer_text(), "$wscriptArgs")
        assert "$pythonwVenv" in line
        assert "$script" in line
        assert "$vbs" in line
        assert "--live" in line

    def test_installer_script_target_is_crypto_twin_health(self) -> None:
        line = _find_line(_installer_text(), "$script")
        assert "crypto_twin_health.py" in line

    def test_installer_execute_is_wscript_not_a_bare_console_launcher(self) -> None:
        text = _installer_text()
        assert 'New-ScheduledTaskAction -Execute "wscript.exe"' in text, (
            "install-crypto-twin.ps1's task Execute must be wscript.exe (WS6 "
            "flash-free doctrine) -- a bare cmd.exe/powershell.exe/python.exe Execute "
            "would both flash a console AND put python.exe (IN the reaper's Name "
            "filter) directly into Win32_Process's Name field instead of pythonw.exe."
        )

    def test_installer_registers_24_7_with_no_day_restriction(self) -> None:
        """Crypto never closes -- confirms no Test-MarketHours/weekday gating was
        copy-pasted in from an RTH-only installer template.

        CADENCE-TUNE (2026-08-01, J latency drill): the exact repetition value is
        checked against the string ACTUALLY in the installer today (was 5min
        2026-07-10..2026-07-31, now 1min -- see install-crypto-twin.ps1's docstring
        for the measured-latency + realized-vol evidence) rather than a value
        independently hardcoded here, so this test's real purpose -- confirming NO
        day/RTH gating exists -- doesn't silently pin a stale cadence number again on
        the next legitimate retune."""
        text = _installer_text()
        assert "Test-MarketHours" not in text
        assert "Test-WeekDay" not in text
        assert "RepetitionInterval (New-TimeSpan -Minutes 1)" in text
        assert "RepetitionDuration" in text

    def test_installer_multiple_instances_ignore_new(self) -> None:
        """A slow tick must not stack a second instance on top of itself (guards ANY
        cadence -- currently 1 min, CADENCE-TUNE 2026-08-01, was 5 min)."""
        text = _installer_text()
        assert "-MultipleInstances IgnoreNew" in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
