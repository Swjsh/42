#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_LiveWatch -- the WS7 LIVE WATCH canonical state surface
  ("J should never have to ask: are we in a trade / what's it doing").

  VISIBILITY ONLY. Places NO order, touches NO exit rule, writes nothing any engine
  reads. Each fire runs setup/scripts/live_watch.py, which rewrites
  automation/state/live-watch.json with per-arm position / unrealized P&L / distance to
  stop + TP / high-water mark / time in trade / last decision verdict+reason+age /
  kill-switch state across the 5 active SPY accounts (core safe-2/bold-2 + fleet
  safe-3/risky-1/risky-3), plus a READ-ONLY link-in of theta-clock.json (Gamma_ThetaClock
  owns writing that file). Market closed -> one CLOSED marker, then silence (no spam).
  Consumers: dashboard Live Watch panel (dashboard/components/LiveWatchPanel.tsx via
  /api/live-watch) + `live_watch.py --brief` (Discord/brief compact text).

  CADENCE -- every 1 min, 09:25-16:10 ET weekdays (5 min before the bell so the surface
  is alive at 09:30; past 16:05 the script itself writes the single CLOSED marker):
    07:25 MT = 09:25 ET start, repeat every 1 min for 6h45m.

  TZ RULE: this rig is Mountain Time (ET = local + 2h). NEVER pass an ET literal to -At.

  CADENCE PATTERN: `-Weekly -DaysOfWeek Mon-Fri -At <MT time>` base trigger + a
  `.Repetition` taken from a throwaway `-Once` trigger -- the verified-live pattern
  (install-theta-clock.ps1 / install-context-bundle.ps1), NOT a bare one-time trigger
  (goes dark next day -- project_scheduled_task_onetime_trigger_dark).

  REAPER EXEMPTION -- verified pattern: 'pythonw.exe' sits outside _shared.ps1's
  Stop-StaleClaudeProcesses Win32_Process Name filter entirely (primary), PLUS the
  launched interpreter is backtest\.venv\Scripts\pythonw.exe whose CommandLine contains
  'backtest\.venv' (an existing $EXEMPT_DAEMONS entry, defense in depth).

  WIRING (flash-free, matches install-theta-clock.ps1 exactly):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> live_watch.py
  live_watch.py also carries its own OP-27 L41 headless stdio redirect (copied from
  guard_runner_slow.py) -- defense in depth against console popups.

  Verify after running: Get-ScheduledTask -TaskName Gamma_LiveWatch | Get-ScheduledTaskInfo
  REVERT: powershell setup\scripts\install-live-watch.ps1 -Uninstall
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root     = "C:\Users\jackw\Desktop\42"
$taskName = "Gamma_LiveWatch"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs         = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script      = Join-Path $root "setup\scripts\live_watch.py"
$etz         = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')

foreach ($p in @($vbs, $pythonwVenv, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> backtest venv pythonw -> live_watch.py
$wscriptArgs = "//nologo `"$vbs`" `"$pythonwVenv`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# 07:25 MT = 09:25 ET start; repeat every 1 min for 6h45m -> covers 09:25-16:10 ET, Mon-Fri.
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "07:25"
$rep = (New-ScheduledTaskTrigger -Once -At "07:25" `
        -RepetitionInterval (New-TimeSpan -Minutes 1) `
        -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 45)).Repetition
$trigger.Repetition = $rep

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
    -Description ("WS7 LIVE WATCH (2026-08-01) -- the ONE canonical 'are we in a trade / " + `
    "what's it doing' surface. Every 1 min 09:25-16:10 ET weekdays, rewrites " + `
    "automation/state/live-watch.json: per-arm position/uPnL/dist-to-stop+TP/HWM/" + `
    "time-in-trade/last-decision/kill-switch across all 5 active SPY accounts " + `
    "(fleet_broker read-only REST) + READ-ONLY theta-clock.json link-in. Market closed " + `
    "-> single CLOSED marker, no spam. Consumers: dashboard LiveWatchPanel + " + `
    "live_watch.py --brief. Fail-open, no lock file, exits 0 always, places nothing. " + `
    "Guard: backtest/tests/test_live_watch.py (23 tests).") `
    -Force | Out-Null

Write-Host "Registered $taskName (07:25 MT = 09:25 ET start, every 1 min for 6h45m, Mon-Fri)"

# --- POST-REGISTRATION ASSERTIONS (OP-33b: registered != firing) -------------------------
$t = Get-ScheduledTask -TaskName $taskName
if ($t.State -eq "Disabled") { Write-Error "$taskName registered but DISABLED"; exit 1 }
$trigType = $t.Triggers[0].CimClass.CimClassName
if ($trigType -ne "MSFT_TaskWeeklyTrigger") {
    Write-Error "$taskName trigger is $trigType, expected MSFT_TaskWeeklyTrigger"
    exit 1
}
if (-not $t.Triggers[0].Repetition.Interval) {
    Write-Error "$taskName has NO repetition interval -- it would fire once/day, not every minute"
    exit 1
}
$info = Get-ScheduledTaskInfo -TaskName $taskName
if (-not $info.NextRunTime) { Write-Error "$taskName has NO NextRunTime -- it will never fire"; exit 1 }
$nextEt = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
Write-Host ("Assertions PASS: State={0}, Trigger={1}, Repetition={2}, NextRun ET={3}" -f `
    $t.State, $trigType, $t.Triggers[0].Repetition.Interval, $nextEt.ToString("yyyy-MM-dd HH:mm"))
