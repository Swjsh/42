#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_OpenBellStatus -- the OPEN-BELL status push (OP-33e, 2026-07-09).

  PURPOSE: retire J's recurring "is it running today?" question for the open-of-day
  window specifically. Fires 6 min after the 09:30 ET bell and pushes ONE short Discord
  message combining engine-health verdict + kill-switch armed/re-armed-today (both
  accounts) + tick freshness + fills so far -- composed from EXISTING state only (no new
  producers). The script is read-only / notify-only: it writes NOTHING except its own
  idempotency marker (automation/state/open-bell-pinged.json) and the shared Discord
  outbox. It places NO order, arms NOTHING, exits 0 always, and can NEVER trade-halt or
  block J (rail-2 fail-open, same contract as preopen_readiness.py).

  WIRING PATTERN (flash-free, matches preopen_readiness + heartbeat_core + sight_beacon):
    wscript -> run_exe_hidden.vbs -> pythonw.exe -> open_bell_status.py
  Both wscript + pythonw are GUI-subsystem (no console allocation); the .vbs passes
  window=0 -- no visible window flash ever (project_mcp_window_leak_fix).

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 09:36 ET -> 07:36 MT.
  NEVER pass an ET literal to -At. Weekly Mon-Fri trigger (NOT a one-time trigger, which
  would go dark the next day -- project_scheduled_task_onetime_trigger_dark).

  To verify after running: Get-ScheduledTask -TaskName Gamma_OpenBellStatus
#>

$ErrorActionPreference = "Stop"

$root      = "C:\Users\jackw\Desktop\42"
$vbs       = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$script    = Join-Path $root "setup\scripts\open_bell_status.py"
$etz       = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName  = "Gamma_OpenBellStatus"

function Show-NextET {
    param([string]$Name)
    $info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction SilentlyContinue
    if ($info -and $info.NextRunTime) {
        $et = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
        Write-Host ("  NextRun ET: {0}" -f $et.ToString("yyyy-MM-dd HH:mm"))
    } else {
        Write-Host "  NextRun ET: (none / on-demand)"
    }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> pythonw -> open_bell_status.py (flash-free chain)
$wscriptArgs = "//nologo `"$vbs`" `"$pythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 07:36 MT = 09:36 ET, weekdays Mon-Fri (6 min after the 09:30 ET bell)
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At ([DateTime]"07:36")

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "OPEN-BELL status push (OP-33e, 2026-07-09). 07:36 MT = 09:36 ET weekdays. open_bell_status.py -> engine-health verdict + kill-switch armed/re-armed-today (both accounts) + tick freshness + fills so far, ONE short Discord message via the existing outbox. Read-only/notify-only, idempotent per ET day, NEVER trade-halts." `
    -Force | Out-Null

Write-Host "Registered $taskName (07:36 MT = 09:36 ET, Mon-Fri)"
Show-NextET $taskName
Write-Host ""
Write-Host "Open-bell status wired.  Verify with: Get-ScheduledTask -TaskName Gamma_OpenBellStatus"
