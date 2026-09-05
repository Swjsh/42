#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_VixBullHardCapUnblockShadow -- forward accrual for the
  VIX_BULL_HARD_CAP_UNBLOCK candidate (K5/K9, GOAL-KITCHEN-KEEPERS-TO-SHADOW-2026-09-03).
  Read-only, SHADOW ONLY -- no engine wiring, no orders, no params/heartbeat_core/filters/
  orchestrator-live-dispatch/strategies touched.

  Pre-reg: analysis/recommendations/prereg-vix-bull-hard-cap-unblock-shadow-2026-09-05.json.
  Runner: setup/scripts/vix_bull_hard_cap_unblock_shadow.py (rewrites the FULL ledger +
  summary from automation/state/core-decisions.jsonl + fills-ledger.jsonl every fire -- a
  deterministic recompute, same idempotency contract as day_throttle_shadow.py /
  pullback_hold_shadow.py).

  CORRECTED PREMISE (see the script's own module docstring + the prereg): the candidate's
  own 2026-09-05 ADJUDICATION assumed the 18->22 VIX_BULL_HARD_CAP change was still
  CONFIG-FROZEN/pending. Fresh verification this session found BOTH params.json and
  filters.py already at 22.0, pinned by backtest/tests/test_no_stale_blocks.py (PASS). So
  this shadow does not scan for suppressed/blocked trades (none exist at this threshold
  anymore) -- it accrues FORWARD P&L on safe-2 bull trades entered with VIX in [18,22) to
  test whether the candidate's cited +$471 in-sample benefit holds out of sample.

  WIRING PATTERN (matches Gamma_PullbackHoldShadow / Gamma_FleetGateLeakShadow --
  the run_py_venv_hidden.py relay, exit-code + log visibility):
    wscript -> run_exe_hidden.vbs -> system pythonw.exe -> run_py_venv_hidden.py ->
    backtest-venv-equivalent vix_bull_hard_cap_unblock_shadow.py (run_py_venv_hidden.py puts
    the backtest venv's site-packages on PYTHONPATH and launches under system pythonw --
    this script itself is stdlib-only via fills_fifo.py, but the relay is kept identical to
    every sibling shadow task for one consistent launch contract).

  SCHEDULE: 16:57 ET weekdays = 14:57 MT (this rig runs Mountain local, ET = local + 2h) --
  after the 16:50/16:55 shadow cluster, before the 17:00 Gamma_GymSession fire. Weekdays
  only (Monday-Friday, i.e. -Daily-style weekday cadence) -- no session, nothing to scan on
  weekends. Self-heal: fires again 15 and 30 min later (IgnoreNew -- a same-day re-fire is a
  safe no-op per the idempotent full-rewrite design above).

  To verify after running: Get-ScheduledTask -TaskName Gamma_VixBullHardCapUnblockShadow | Get-ScheduledTaskInfo
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_VixBullHardCapUnblockShadow" -Confirm:$false
          (also remove its SCHEDULED-TASKS.md row + decrement the header count, and the ledger/
          summary files it wrote under analysis/recommendations/ if a full revert is wanted).
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root       = "C:\Users\jackw\Desktop\42"
$vbs        = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runPyVenv  = Join-Path $root "setup\scripts\run_py_venv_hidden.py"
$script     = Join-Path $root "setup\scripts\vix_bull_hard_cap_unblock_shadow.py"
$taskName   = "Gamma_VixBullHardCapUnblockShadow"

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

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_py_venv_hidden.py -> vix_bull_hard_cap_unblock_shadow.py
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runPyVenv`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# Weekdays, 14:57 local (= 16:57 ET, this rig is Mountain local).
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At ([DateTime]"14:57")

# Self-heal window: every 15 min for 30 min after the primary fire. Safe no-op re-fire --
# vix_bull_hard_cap_unblock_shadow.py rewrites the full ledger deterministically from
# core-decisions.jsonl + fills-ledger.jsonl every run, it does not append/duplicate.
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At ([DateTime]"14:57") `
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
    -Description "Forward P&L accrual for VIX_BULL_HARD_CAP_UNBLOCK (prereg analysis/recommendations/prereg-vix-bull-hard-cap-unblock-shadow-2026-09-05.json). Read-only, SHADOW ONLY, zero engine wiring. Fires 16:57 ET (14:57 MT) weekdays. Relay: run_py_venv_hidden.py." `
    -Force | Out-Null

Write-Host "Registered $taskName (14:57 MT / 16:57 ET weekdays, run_py_venv_hidden.py relay)"
Show-Next $taskName
Write-Host ""
Write-Host "Gamma_VixBullHardCapUnblockShadow wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_VixBullHardCapUnblockShadow | Get-ScheduledTaskInfo"
