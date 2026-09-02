#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_DeadMansSwitch -- the independent watchdog that flattens an open SPY option
  position if the engine PROCESS has gone silent (queue.md DEAD-MANS-SWITCH-POSITION-FLATTENER,
  filed 2026-08-29 Fable full review; go_live_gate.py operational criterion 2's last named gap).

  WHY 2-MINUTE CADENCE, 09:32-15:58 ET: heal-engine.ps1 fires every ~1 min during RTH and needs
  ~60-90s for a re-fired tick to land after detecting a stale brain (CORE_STALE_MIN=8). This
  watchdog's own STALE_MIN=10 (in dead_mans_switch.py) is deliberately AFTER that heal window,
  so a /2min fire gives the healer two full chances to resurrect the process before this
  watchdog ever considers flattening anything -- it is the LAST line of defense, not a race
  against the first one. 09:32 (2 min after the 09:30 open) avoids acting on pre-open noise;
  15:58 stops 2 min before the market truly closes (15:52/15:55 ET flatten backstops already
  cover the close itself).

  WIRING PATTERN (flash-free, matches heartbeat_core / eod_flatten / sight_beacon):
    wscript -> run_exe_hidden.vbs -> pythonw.exe -> dead_mans_switch.py
  Both wscript and pythonw are GUI-subsystem (no console allocation); run_exe_hidden.vbs
  passes window=0 -- no visible window ever, matching J's "no popups" standing directive.

  TZ RULE: this rig runs Mountain Time (ET = local + 2h). NEVER pass an ET literal to -At.
  09:32 ET -> 07:32 MT. Repeating every 2 min for 6h26m covers 07:32-13:58 MT = 09:32-15:58 ET.

  To verify after running:
    Get-ScheduledTask -TaskName Gamma_DeadMansSwitch | Get-ScheduledTaskInfo

  REVERT: Unregister-ScheduledTask -TaskName "Gamma_DeadMansSwitch" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$root    = "C:\Users\jackw\Desktop\42"
$vbs     = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$script  = Join-Path $root "setup\scripts\dead_mans_switch.py"
$taskName = "Gamma_DeadMansSwitch"
$etz     = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> pythonw -> dead_mans_switch.py (flash-free chain)
$wscriptArgs = "//nologo `"$vbs`" `"$pythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 07:32 MT = 09:32 ET, repeating every 2 min for 6h26m (-> last fire 13:56 MT = 15:56 ET,
# comfortably covering the 09:32-15:58 ET window the script itself also gates on internally).
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At ([DateTime]"07:32")
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At ([DateTime]"07:32") `
    -RepetitionInterval (New-TimeSpan -Minutes 2) `
    -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 26)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Independent dead-man's-switch watchdog (queue.md DEAD-MANS-SWITCH-POSITION-FLATTENER, filed 2026-08-29 Fable full review; closes go_live_gate.py operational criterion 2's last named gap). Flattens an open SPY option position via fleet_broker if that arm's engine-decision ledger has gone stale (>10 min, per-arm: core-decisions.jsonl for safe-2/bold-2, fleet/<arm>/decisions.jsonl for safe-3/risky-1) AND the broker read confirms an open position. Fires every 2 min, 09:32-15:58 ET weekdays. NO LLM/MCP. Fail-open per OP-25 -- never blocks trading, never raises. Guard: backtest/tests/test_dead_mans_switch_2026_09_01.py. Revert: Unregister-ScheduledTask -TaskName Gamma_DeadMansSwitch -Confirm:`$false" `
    -Force | Out-Null

Write-Host "Registered $taskName (07:32 MT = 09:32 ET, every 2 min for 6h26m)"

$info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
if ($info -and $info.NextRunTime) {
    $et = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
    Write-Host ("  NextRun ET: {0}" -f $et.ToString("yyyy-MM-dd HH:mm"))
} else {
    Write-Host "  NextRun ET: (none / on-demand)"
}

Write-Host ""
Write-Host "Verify with: Get-ScheduledTask -TaskName Gamma_DeadMansSwitch | Get-ScheduledTaskInfo"
