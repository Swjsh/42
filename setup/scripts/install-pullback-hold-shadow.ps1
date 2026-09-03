#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_PullbackHoldShadow -- nightly forward scanner for the
  PULLBACK-HOLD-BULL-TRIGGER Lane-B forward shadow ledger (queue item filed 2026-07-22,
  re-opened 2026-09-03 for a forward-shadow validation path distinct from the already-CLOSED
  historical-grid Lane B). Read-only, SHADOW ONLY -- no engine wiring, no orders, no
  params/heartbeat_core/filters/orchestrator-live-dispatch/strategies touched.

  Pre-reg: analysis/recommendations/prereg-pullback-hold-bull-trigger-2026-09-03.md (frozen
  decision rule, forward window opens 2026-09-03). Detector:
  backtest/lib/pullback_hold_detector.py. Runner: setup/scripts/pullback_hold_shadow.py
  (rewrites the FULL ledger + summary from automation/state/core-decisions.jsonl every fire --
  a deterministic recompute, so a missed-run/self-heal re-fire is a safe no-op, same
  idempotency contract as day_throttle_shadow.py).

  WIRING PATTERN (matches Gamma_RegimeShadow / Gamma_TrendlineTightExitShadow /
  Gamma_Tp1R50ForwardShadow -- the run_py_venv_hidden.py relay, exit-code + log visibility):
    wscript -> run_exe_hidden.vbs -> system pythonw.exe -> run_py_venv_hidden.py ->
    backtest-venv-equivalent pullback_hold_shadow.py (run_py_venv_hidden.py puts the backtest
    venv's site-packages, i.e. pandas/numpy, on PYTHONPATH and launches under system pythonw).

  SCHEDULE: 16:50 ET weekdays = 14:50 MT (this rig runs Mountain local, ET = local + 2h) --
  after Gamma_TrendlineTightExitShadow (16:45 ET) and Gamma_Tp1R50ForwardShadow (16:40 ET),
  before the 16:30 EOD pipeline's own downstream consumers finish, matching the existing
  after-close shadow-ledger cluster's cadence. Weekdays only (Monday-Friday) -- no session,
  nothing to scan on weekends. Self-heal: fires again 15 and 30 min later (IgnoreNew --
  a same-day re-fire is a safe no-op per the idempotent full-rewrite design above).

  To verify after running: Get-ScheduledTask -TaskName Gamma_PullbackHoldShadow | Get-ScheduledTaskInfo
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_PullbackHoldShadow" -Confirm:$false
          (also remove its SCHEDULED-TASKS.md row + decrement the header count, and the ledger/
          summary files it wrote under analysis/recommendations/ if a full revert is wanted).
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root       = "C:\Users\jackw\Desktop\42"
$vbs        = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runPyVenv  = Join-Path $root "setup\scripts\run_py_venv_hidden.py"
$script     = Join-Path $root "setup\scripts\pullback_hold_shadow.py"
$taskName   = "Gamma_PullbackHoldShadow"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

foreach ($p in @($vbs, $sysPythonw, $runPyVenv, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

function Show-Next {
    param([string]$Name)
    $info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction SilentlyContinue
    if ($info -and $info.NextRunTime) {
        Write-Host ("  NextRun (local): {0}" -f $info.NextRunTime.ToString("yyyy-MM-dd HH:mm"))
    } else {
        Write-Host "  NextRun: (none / on-demand)"
    }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_py_venv_hidden.py -> pullback_hold_shadow.py
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runPyVenv`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# Weekdays, 14:50 local (= 16:50 ET, this rig is Mountain local).
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At ([DateTime]"14:50")

# Self-heal window: every 15 min for 30 min after the primary fire. Safe no-op re-fire --
# pullback_hold_shadow.py rewrites the full ledger deterministically from core-decisions.jsonl
# every run, it does not append/duplicate.
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At ([DateTime]"14:50") `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Nightly forward scanner for PULLBACK-HOLD-BULL-TRIGGER's forward-shadow Lane B (prereg analysis/recommendations/prereg-pullback-hold-bull-trigger-2026-09-03.md). Read-only, SHADOW ONLY, zero engine wiring. Fires 16:50 ET (14:50 MT) weekdays. Relay: run_py_venv_hidden.py. Guard: backtest/tests/test_pullback_hold_detector_shadow.py." `
    -Force | Out-Null

Write-Host "Registered $taskName (14:50 MT / 16:50 ET weekdays, run_py_venv_hidden.py relay)"
Show-Next $taskName
Write-Host ""
Write-Host "Gamma_PullbackHoldShadow wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_PullbackHoldShadow | Get-ScheduledTaskInfo"
