#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_PreopenReadiness -- the pure-Python pre-open readiness verifier
  (WIRE-PREOPEN-READINESS-SCHEDULE, 2026-06-29).

  PURPOSE: graduate the W26 *manual* human ritual ("BEFORE Monday open: verify the
  heartbeat task + Alpaca key + TV CDP") into an automated pre-open fire. Runs
  preopen_readiness.py at 06:25 MT = 08:25 ET, BEFORE Gamma_Premarket (08:30 ET) and
  ~1h before market open (09:30 ET), giving a window to react to a RED verdict. The
  script is read-only / notify-only: it verifies the LIVE chain (HeartbeatCore +
  SightBeacon + EodFlatten) + broker auth, writes preopen-readiness.json, and pings J
  ONCE via the Discord outbox on a transition into RED. It places NO order, arms
  NOTHING, exits 0 always, and can NEVER trade-halt or block J (rail-2 fail-open).

  WIRING PATTERN (flash-free, matches heartbeat_core + sight_beacon + eod_flatten):
    wscript -> run_exe_hidden.vbs -> pythonw.exe -> preopen_readiness.py
  Both wscript + pythonw are GUI-subsystem (no console allocation); the .vbs passes
  window=0 -- no visible window flash ever (project_mcp_window_leak_fix).

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 08:25 ET -> 06:25 MT.
  NEVER pass an ET literal to -At. Weekly Mon-Fri trigger (NOT a one-time trigger,
  which would go dark the next day -- project_scheduled_task_onetime_trigger_dark).

  To verify after running: setup\scripts\task_health_et.ps1
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonw      = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\preopen_readiness.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName     = "Gamma_PreopenReadiness"

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

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- system pythonw -> preopen_readiness.py
# (2026-08-08 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT migration -- was fire-and-forget.)
$wscriptArgs = "//nologo `"$vbs`" `"$pythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 06:25 MT = 08:25 ET, weekdays Mon-Fri (BEFORE Premarket 08:30 ET)
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At ([DateTime]"06:25")

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
    -Description "Pre-open readiness verifier (W26 ritual graduated, 2026-06-29). 06:25 MT = 08:25 ET weekdays. preopen_readiness.py -> verifies LIVE chain + broker auth, pings J once on RED. Read-only/notify-only, NEVER trade-halts." `
    -Force | Out-Null

Write-Host "Registered $taskName (06:25 MT = 08:25 ET, Mon-Fri)"
Show-NextET $taskName
Write-Host ""
Write-Host "Pre-open readiness wired.  Verify with: setup\scripts\task_health_et.ps1"
