#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_LaunchRate -- daily launches-per-hour instrument (GOAL-SILENT-RIG-2026-09-05 R3).

.CONTEXT
  J: "this is a recurring thing it has to stop. everything must be silent, and it needs to be
  optimized, i can't have my pc bogged down." setup/scripts/launch_rate.py (GOAL-SILENT-RIG L3)
  reads the two hidden-launcher logs (run_ps1_hidden.py / run_cmd_hidden.py), buckets launches
  per box-local hour, and upserts ONE `LAUNCH-RATE:` Known-broken line via the shared
  status_known_broken.upsert() helper whenever a market-closed hour exceeds 60 launches. It was
  built and run once by hand (L3, read-only `--no-flag`) but never registered as a scheduled
  task -- this closes that gap (R3's first half; R3's second half, re-enabling ConductorWeekend,
  is Fable's call after watching one live fire's hook log per the goal's own S4 note).

  WIRING PATTERN (matches install-crypto-twin-keepalive.ps1's proven shape):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --env
      PYTHONPATH=<repo>\backtest\.venv\Lib\site-packages --cwd <repo>
      -- system pythonw -> launch_rate.py
  No PowerShell anywhere in the fire chain (OP-27 L41). System pythonw only, never the venv
  stub (GOAL-SILENT-RIG S1/S2 -- this repo scans for that regression class now).

  CADENCE: once daily at 23:40 ET (box is Mountain time, ET = local+2 per et_clock.py verified
  2026-09-05: ET 14:48 == local 12:48 MDT -- so 23:40 ET == 21:40 local), reading the day's own
  logs just before rollover. A single daily fire, not a recurring load source itself.

  DISABLED AT REGISTRATION (GOAL-SILENT-RIG-2026-09-05 operating rule -- workers/conductor fires
  never enable a scheduled task). This script registers the task then immediately calls
  Disable-ScheduledTask in the SAME run. Fable enables it after reviewing the goal.

  NOT a live-money/secret/CLAUDE.md-doctrine surface, NOT on the September freeze's frozen-path
  list (heartbeat_core.py / filters.py / risk_gate.py / exit_manager.py / fleet_executor.py /
  strategies.py / build_shared_signal.py / params.json / aggressive/params.json /
  accounts.json) -- this is an operational monitor script, not a trading-path edit.

  To verify after running: Get-ScheduledTask -TaskName Gamma_LaunchRate
    (State should read Disabled until Fable enables it)
  Revert (undo this install entirely): .\install-launch-rate.ps1 -Uninstall
  Flip live (Fable only): Enable-ScheduledTask -TaskName Gamma_LaunchRate
  Revert THAT flip: Disable-ScheduledTask -TaskName Gamma_LaunchRate
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root     = "C:\Users\jackw\Desktop\42"
$taskName = "Gamma_LaunchRate"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonw      = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"  # SYS pythonw only, never the venv stub (GOAL-SILENT-RIG S1/S2)
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\launch_rate.py"
$pythonPathEnv = "PYTHONPATH=$root\backtest\.venv\Lib\site-packages"

if (-not (Test-Path $pythonw))      { throw "system pythonw.exe not found at $pythonw" }
if (-not (Test-Path $vbs))          { throw "run_exe_hidden.vbs not found at $vbs" }
if (-not (Test-Path $runCmdHidden)) { throw "run_cmd_hidden.py not found at $runCmdHidden" }
if (-not (Test-Path $script))       { throw "launch_rate.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --env PYTHONPATH=...
#   --cwd <repo> -- system pythonw -> launch_rate.py
$wscriptArgs = "//nologo `"$vbs`" `"$pythonw`" `"$runCmdHidden`" --env `"$pythonPathEnv`" --cwd `"$root`" -- `"$pythonw`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# Once daily, 21:40 local (== 23:40 ET, box is Mountain time / ET = local+2).
$today = Get-Date
$startBoundary = Get-Date -Year $today.Year -Month $today.Month -Day $today.Day -Hour 21 -Minute 40 -Second 0
if ($startBoundary -lt $today) { $startBoundary = $startBoundary.AddDays(1) }
$trigger = New-ScheduledTaskTrigger -Daily -At $startBoundary

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
    -MultipleInstances IgnoreNew `
    -Priority 7

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Daily launches-per-hour instrument (GOAL-SILENT-RIG-2026-09-05 R3). Reads the day's two hidden-launcher logs, writes automation/state/launch-rate.json, upserts a LAUNCH-RATE: Known-broken line when any market-closed hour exceeds 60 launches. Fires once daily at 21:40 local (23:40 ET). Registered DISABLED; Fable enables after reviewing this goal." `
    -Force | Out-Null

# DISABLE IMMEDIATELY -- workers/conductor fires never enable a scheduled task
# (GOAL-SILENT-RIG-2026-09-05 operating rules). Fable enables after review.
Disable-ScheduledTask -TaskName $taskName | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
$state = (Get-ScheduledTask -TaskName $taskName).State
Write-Host "Registered $taskName. State=$state. Next run (while disabled, informational only): $($info.NextRunTime)"
