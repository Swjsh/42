#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_TaskStateGuard -- closes self-healing blind spot (a) from the 2026-08-08
  Lane B audit: NOTHING previously verified a scheduled task's Enabled state. If a
  trading-critical task (Gamma_HeartbeatCore, Gamma_SightBeacon, ...) were ever flipped
  Disabled, heal-engine.ps1's Start-ScheduledTask recovery throws and is swallowed by its
  own try/catch; the one existing tool that DOES list task state, task_health_et.ps1,
  explicitly `Where-Object { $_.State -ne 'Disabled' }`s them OUT -- i.e. it excludes the
  exact failure mode this task exists to catch.

  PURPOSE: every 30 minutes, 24/7, task_state_guard.py queries the live state of a pinned
  list of TRADING-CRITICAL + AUTONOMY-CRITICAL Gamma_* scheduled tasks (see
  setup/scripts/task_state_guard.py#CRITICAL_TASKS for the full pinned list + per-task
  justification). A DISABLED task gets re-enabled and logged loudly; a MISSING task gets
  logged CRITICAL (nothing to auto-fix -- needs re-registration); a nonzero LastTaskResult
  gets recorded (not acted on -- self_check.py's own MASKED EXIT checks already own "is the
  real outcome bad"). Writes automation/state/task-state-guard.json every fire; appends ONE
  automation/state/discord-outbox.jsonl row ONLY when something was actually broken or
  repaired (never spams a clean pass). $0, pure Python, stdlib-only (no venv needed), never
  touches params.json/heartbeat/CLAUDE.md, places no order, fail-open always.

  WIRING PATTERN (C8 hidden-spawn chain, cloned verbatim from install-futures-mirror.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo> --
    system pythonw task_state_guard.py
  Runs on SYSTEM Python (not the backtest venv) because task_state_guard.py imports only
  stdlib (json/subprocess/argparse/pathlib/datetime) + this repo's own stdlib-only
  et_clock.py -- no pandas/yfinance/etc, so the heavier backtest venv buys nothing here
  (same reasoning as Gamma_ConductorWake's conductor_wake_watch.py).

  CADENCE: -Once + 30-min RepetitionInterval + 10-year RepetitionDuration (the proven
  indefinite-recurrence pattern from install-conductor-wake-task.ps1 / Gamma_SelfCheck --
  NOT a same-day-duration -Once trigger, which goes dark after one day:
  project_scheduled_task_onetime_trigger_dark). 24/7, not RTH-gated -- a critical task can
  get flipped Disabled at any hour, and Gamma_Premarket/Gamma_LaunchTV/Gamma_Conductor all
  fire outside 09:30-15:55 ET, so this guard must watch outside RTH too.

  To verify after running: Get-ScheduledTask -TaskName Gamma_TaskStateGuard | Get-ScheduledTaskInfo
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_TaskStateGuard" -Confirm:$false

  NOTE (per this session's task scope): this installer is written but deliberately NOT run
  here, and automation/state/SCHEDULED-TASKS.md is deliberately NOT edited here -- both are
  the orchestrator's step, not this lane's.
#>

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\task_state_guard.py"
$taskName     = "Gamma_TaskStateGuard"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    } else {
        Write-Host "$taskName was not registered."
    }
    return
}

foreach ($p in @($vbs, $sysPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

function Show-NextET {
    param([string]$Name)
    $etz = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
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

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo> --
#   system pythonw task_state_guard.py   (real synchronous exit code captured in
#   automation/state/logs/run-cmd-hidden-<date>.log even though the outer wscript hop
#   stays fire-and-forget -- same relay self_check.py's MASKED EXIT check already reads,
#   so this task's own real outcome is automatically covered by that existing detector too)
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

$startBoundary = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $startBoundary `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration ([System.TimeSpan]::FromDays(365 * 10))

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Self-healing blind-spot closer (LANE B, 2026-08-08 audit): every 30 min, " + `
    "24/7, task_state_guard.py queries the live state of the pinned TRADING-CRITICAL + " + `
    "AUTONOMY-CRITICAL Gamma_* task list (see task_state_guard.py#CRITICAL_TASKS). DISABLED " + `
    "-> re-enabled + logged loudly. MISSING -> logged CRITICAL (needs re-registration, not " + `
    "auto-fixable). Nonzero LastTaskResult -> recorded only. Writes " + `
    "automation/state/task-state-guard.json every fire; Discord outbox row ONLY on a real " + `
    "break/repair (never spams a clean pass). `$0, pure Python stdlib-only, fail-open, " + `
    "never touches params.json/heartbeat/CLAUDE.md, places no order. " + `
    "Kill-switch: Disable-ScheduledTask Gamma_TaskStateGuard.") `
    -Force | Out-Null

Write-Host "Registered $taskName (every 30 min, 24/7)"
Show-NextET $taskName
Write-Host ""
Write-Host "Task-state guard wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_TaskStateGuard | Get-ScheduledTaskInfo"
Write-Host "Dry-run test (no schtasks changes):"
Write-Host "  python setup\scripts\task_state_guard.py --dry-run"
