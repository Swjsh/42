#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_AutoCommitCandidates -- periodic preventive auto-commit of
  strategy/candidates/ (L242 re-violation guard, 2026-07-23 conductor fire).

  SCAR: L242 (2026-07-22) -- 1,176 untracked strategy/candidates/ files sat
  uncommitted for weeks with no disk-loss recovery path. self_check.py's
  CANDIDATES-UNTRACKED check (threshold 20) was added as a DETECTOR only --
  it re-violated within 24h (a 2026-07-23 conductor fire had to manually
  clear 41 more chef/kitchen/prospector files). Per OP-25 a re-violated
  lesson graduates to an enforced guard: this task runs
  setup/scripts/auto_commit_candidates.py, which stages + commits
  strategy/candidates/ changes ONLY once they reach >=10 untracked/modified
  entries (below self_check's 20-threshold DEGRADED bar, so the detector
  should now rarely if ever fire again).

  Fail-open (OP-25/C7): the script never raises and always exits 0; a git
  error (including the repo's own pre-commit safety-gate hook rejecting the
  commit) is logged to automation/state/auto-commit-candidates-log.jsonl and
  skipped quietly -- never blocks, never retries in a loop.

  Scope: strategy/candidates/ ONLY (git add scoped by pathspec, never -A).
  Local commit only -- never pushes (push discipline unaffected).

  CADENCE: every 2 hours, every day (weekday + weekend -- the chef/kitchen/
  prospector daemons that write into strategy/candidates/ run continuously,
  not just during RTH).

  REAPER EXEMPTION -- same verified pattern as install-key-levels-snapshot.ps1
  / install-ledger-archive.ps1: launched via backtest\.venv\Scripts\pythonw.exe
  (outside Stop-StaleClaudeProcesses's Name filter, plus the '.venv' path-match
  exemption, defense in depth) and the script itself exits well under a minute.

  WIRING (flash-free, matches install-key-levels-snapshot.ps1 exactly):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> auto_commit_candidates.py

  Guard: backtest/tests/test_auto_commit_candidates.py (9/9).
  To verify after running: Get-ScheduledTask -TaskName Gamma_AutoCommitCandidates | Get-ScheduledTaskInfo
  REVERT: powershell setup\scripts\install-auto-commit-candidates.ps1 -Uninstall
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root     = "C:\Users\jackw\Desktop\42"
$taskName = "Gamma_AutoCommitCandidates"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs         = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script      = Join-Path $root "setup\scripts\auto_commit_candidates.py"

if (-not (Test-Path $pythonwVenv)) { throw "backtest venv pythonw.exe not found at $pythonwVenv" }
if (-not (Test-Path $script))      { throw "auto_commit_candidates.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$pythonwVenv`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# Every 2 hours, every day -- repeat trigger needs a base daily trigger + repetition.
$trigger = New-ScheduledTaskTrigger -Daily -At "00:00"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "00:00" -RepetitionInterval (New-TimeSpan -Hours 2) -RepetitionDuration (New-TimeSpan -Days 3650)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "L242 re-violation prevention guard (2026-07-23). Every 2h, every day: runs auto_commit_candidates.py, which stages+commits strategy/candidates/ changes ONLY once >=10 untracked/modified entries accrue (below self_check.py's 20-threshold DEGRADED bar) so the pipeline's chef/kitchen/prospector output never again sits uncommitted for weeks (L242 scar: 1,176 files). Scoped to strategy/candidates/ only, never -A. Fail-open: any git error (incl. pre-commit safety-gate rejection) is logged and skipped, never raises, never pushes. Guard: backtest/tests/test_auto_commit_candidates.py." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
