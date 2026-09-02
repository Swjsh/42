#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_EodFlattenEarlyClose -- the mid-day early-close flatten check (B2,
  2026-09-01, queue item EARLY-CLOSE-CALENDAR-AWARENESS).

  WHY THIS EXISTS: the live broker calendar closes 2026-11-27 and 2026-12-24 at 13:00 ET.
  The existing Gamma_EodFlattenCore / Gamma_EodFlatten* tasks all fire at 15:52/15:55 ET --
  AFTER those two days' 0DTE contracts have already expired. heartbeat_core.py's matching
  entry-side fix (stop opening new positions once an early close makes the session shorter)
  needs the frozen file and waits for the 2026-09-29 config-freeze window to lift. This ships
  the EXIT-side half now, independently: a second task that fires mid-day, asks the shared
  calendar cache (setup/scripts/market_calendar.py) whether TODAY closes early, and if so
  runs the SAME sweep 30 minutes before that early close via
  `eod_flatten.py --only-if-early-close`.

  On a normal 16:00 day (365-2 days a year) this task is a silent no-op: cache read, log
  one NOOP line, exit 0 -- no broker calls, no positions read, nothing placed.

  WHY 12:32 ET (10:32 MT): the earliest known early close this rig has seen is 13:00 ET, so
  close-30min = 12:30 ET. 12:32 ET gives that a 2-minute margin without waking a normal-day
  flatten uselessly hours early. If a future early close before 13:00 ET is ever added to the
  calendar, this fire time should move earlier to match (see market_calendar.py -- it always
  answers with the CACHED value, so a too-late fire on a 12:00-close day is the actual risk to
  watch for; none exists as of 2026-09-01).

  WIRING PATTERN (flash-free, matches Gamma_EodFlattenCore):
    wscript -> run_exe_hidden.vbs -> pythonw.exe -> eod_flatten.py --only-if-early-close
  The wscript + pythonw are both GUI-subsystem (no console allocation).

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 12:32 ET -> 10:32 MT.
  NEVER pass an ET literal to -At.

  To verify after running:
    Get-ScheduledTask -TaskName Gamma_EodFlattenEarlyClose | Get-ScheduledTaskInfo
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_EodFlattenEarlyClose" -Confirm:$false
          (no other task touched -- nothing else to restore.)
#>

$ErrorActionPreference = "Stop"

$root      = "C:\Users\jackw\Desktop\42"
$vbs       = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$script    = Join-Path $root "setup\scripts\eod_flatten.py"
$etz       = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')

$taskName  = "Gamma_EodFlattenEarlyClose"

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

# wscript -> run_exe_hidden.vbs -> pythonw -> eod_flatten.py --only-if-early-close
$wscriptArgs = "//nologo `"$vbs`" `"$pythonw`" `"$script`" `"--only-if-early-close`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 10:32 MT = 12:32 ET, weekdays Mon-Fri
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At ([DateTime]"10:32")

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
    -Description "Early-close flatten check (B2, 2026-09-01). Weekdays 12:32 ET. NOOP on a normal 16:00 day; on a 13:00 ET early close (2026-11-27, 2026-12-24) runs the same sweep as Gamma_EodFlattenCore, 30 min ahead of that close. eod_flatten.py --only-if-early-close -> market_calendar.py + fleet_broker. NO LLM." `
    -Force | Out-Null

Write-Host "Registered $taskName (10:32 MT = 12:32 ET)"
Show-NextET $taskName

Write-Host ""
Write-Host "Gamma_EodFlattenEarlyClose wired.  Verify with: Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo"
