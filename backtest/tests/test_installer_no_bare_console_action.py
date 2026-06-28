"""Installer bare-console-action guard -- permanent regression ratchet.

WHY THIS EXISTS (the 2026-06-27 recurrence that motivated it):
  `setup/fix-powershell-task-flash.ps1` converted live tasks off bare
  `powershell.exe` actions to the windowless wscript->run_exe_hidden.vbs->
  pythonw->run_ps1_hidden.py chain (project_mcp_window_leak_fix). But the
  2026-06-26 TZ-systemic fix `register_tz_fixed_tasks.ps1` RE-REGISTERED
  Gamma_SwarmPremarket + Gamma_ContextGuard with BARE powershell.exe actions
  again -> the flash returned, and `audit_scheduled_tasks.py` flagged
  BARE_CMD_POWERSHELL (HEALTH RED) on the next fire.

  The existing WS6 guard (test_guard_cmd_popup_fix_ws6.py) only exercises the
  audit's DETECTION helpers against synthetic strings -- it never scanned the
  actual INSTALLER .ps1 source, so an installer re-emitting a bare action stayed
  green. This guard closes that gap: it STATICALLY scans every setup/**/*.ps1 for
  a `New-ScheduledTaskAction -Execute "powershell.exe"` / `"cmd.exe"` bare action
  and fails if a NEW one appears (or a fixed one regresses).

GUARD CLASS: HARD shrinks-only ratchet.
  - The three installers fixed 2026-06-27 (register_tz_fixed_tasks.ps1,
    register-context-guard.ps1, install-swarm-task.ps1) are PINNED clean -- a
    revert to a bare action REDs immediately.
  - KNOWN_BARE_INSTALLERS documents the pre-existing latent offenders (their LIVE
    tasks are flash-fix-converted, so the audit is GREEN today, but the installer
    source would re-clobber on a direct re-run). The allowlist is SHRINKS-ONLY:
    fixing one makes its entry stale and the staleness test REDs, forcing removal
    -> the ratchet tightens toward zero and can never silently grow.

2026-06-27 G18 follow-up (author: Gamma conductor).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SETUP = REPO / "setup"

# A bare console launcher action: New-ScheduledTaskAction -Execute "powershell.exe"
# (or cmd.exe). These ALWAYS flash OpenConsole on Win11 (the -WindowStyle Hidden
# arg is applied ~200ms too late). Case-insensitive; tolerates backtick line breaks
# because we match the -Execute token anywhere in the file that also constructs a task.
_BARE_EXEC = re.compile(r'-Execute\s+"(?:powershell|cmd)\.exe"', re.IGNORECASE)
_REGISTERS_TASK = re.compile(r"New-ScheduledTaskAction", re.IGNORECASE)

# Installers fixed 2026-06-27/28 -- MUST stay on the wscript hidden chain.
#   G18 fire (cf3ef6a): register_tz_fixed_tasks / register-context-guard / install-swarm-task.
#   G18b drain #1 (cf88aec): crypto x3 + register-eod-deep-dive (ratchet 6->2).
#   G18b drain #2 (this fire): install-watchdog-modes-sweep + scripts/setup-all (ratchet 2->0 = WIN STATE).
#     - install-watchdog-modes-sweep.ps1: DYNAMIC -TargetIterations/-BatchSize ride through
#       run_ps1_hidden.py's argv[2:] forwarding -> -File ... -TargetIterations N -BatchSize N.
#     - scripts/setup-all.ps1: only the step-4 inline freshness-watchdog register was bare.
FIXED_CLEAN = {
    "setup/scripts/register_tz_fixed_tasks.ps1",
    "setup/scripts/register-context-guard.ps1",
    "setup/install-swarm-task.ps1",
    "setup/install-crypto-daily.ps1",
    "setup/install-crypto-grinder-keepalive.ps1",
    "setup/install-crypto-regression.ps1",
    "setup/scripts/register-eod-deep-dive.ps1",
    "setup/install-watchdog-modes-sweep.ps1",
    "setup/scripts/setup-all.ps1",
}

# Pre-existing latent offenders. SHRINKS-ONLY: remove an entry the moment you fix it
# (the stale-entry test forces it). Do NOT add to this list -- a NEW bare installer is
# a regression, not an allowance. RATCHET FULLY DRAINED 2026-06-28 (G18b) -> empty = the
# win state: every task-constructing installer in setup/** is now on the wscript hidden
# chain, and test_no_new_bare_console_installer guards that no new one can appear.
KNOWN_BARE_INSTALLERS: set[str] = set()


def _rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def _offending_installers() -> set[str]:
    """Every setup/**/*.ps1 that constructs a task AND uses a bare console -Execute."""
    out: set[str] = set()
    for ps1 in SETUP.rglob("*.ps1"):
        text = ps1.read_text(encoding="utf-8", errors="replace")
        if _REGISTERS_TASK.search(text) and _BARE_EXEC.search(text):
            out.add(_rel(ps1))
    return out


def test_no_new_bare_console_installer() -> None:
    """No installer outside the documented allowlist emits a bare powershell/cmd action."""
    offending = _offending_installers()
    new_offenders = offending - KNOWN_BARE_INSTALLERS
    assert not new_offenders, (
        "NEW installer(s) emit a bare `New-ScheduledTaskAction -Execute \"powershell.exe\"`/"
        "`\"cmd.exe\"` action -> they will flash OpenConsole on Win11 and trip the audit's "
        "BARE_CMD_POWERSHELL flag the moment the task runs.  Convert to the wscript->"
        "run_exe_hidden.vbs->pythonw->run_ps1_hidden.py chain (see register_tz_fixed_tasks.ps1 "
        f"for the pattern).  Offenders: {sorted(new_offenders)}"
    )


def test_fixed_installers_stay_on_hidden_chain() -> None:
    """The 3 installers fixed 2026-06-27 must NOT regress to a bare action."""
    offending = _offending_installers()
    regressed = FIXED_CLEAN & offending
    assert not regressed, (
        "A G18-fixed installer reverted to a bare console action (the exact "
        "register_tz_fixed_tasks.ps1 clobber that motivated this guard).  Restore the "
        f"wscript hidden chain.  Regressed: {sorted(regressed)}"
    )


def test_allowlist_has_no_stale_entries() -> None:
    """Shrinks-only: every allowlisted file must still exist AND still offend.

    When you fix one, this test REDs until you remove its entry -> the ratchet
    can only tighten, never silently carry a fixed file.
    """
    offending = _offending_installers()
    stale = sorted(
        e for e in KNOWN_BARE_INSTALLERS
        if not (REPO / e).exists() or e not in offending
    )
    assert not stale, (
        "KNOWN_BARE_INSTALLERS has stale entries -- either the file was removed or it no "
        "longer emits a bare action (you fixed it).  Remove these entries to tighten the "
        f"ratchet: {stale}"
    )


def test_allowlist_and_fixed_sets_are_disjoint() -> None:
    """A fixed installer can never also be allowlisted as a known offender."""
    overlap = FIXED_CLEAN & KNOWN_BARE_INSTALLERS
    assert not overlap, f"Installer is both FIXED_CLEAN and KNOWN_BARE: {sorted(overlap)}"
