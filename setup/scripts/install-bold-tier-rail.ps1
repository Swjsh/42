#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_BoldTierRail -- the standing daily instrument for BOLD-CORE-ATM-WIRE-
  FALSIFICATION-RAIL (commit 718e0809, 2026-07-18's own promised "first n>=20 live Bold fills
  under this tier get an expectancy check; negative result escalates to Fable judgment, not a
  silent revert"). A 2026-08-08 audit found that rail existed ONLY as prose (a queue.md bullet
  + a test-file docstring) -- setup/scripts/bold_tier_rail.py is the fix; this task runs it.

  PURPOSE: once daily, bold_tier_rail.py reconstructs bold-2's real post-2026-07-18 ATM-tier
  fills (via exit_shape_parity_study.reconstruct_positions -- the repo's ONE position
  definition, never re-derived), computes rail_status (NO_DATA/ACCRUING/TRIGGERED_NEGATIVE/
  TRIGGERED_POSITIVE), an honest PDT-blackout-aware ETA to n=20, and overwrites
  automation/state/bold-tier-rail.json. On the FIRST transition into TRIGGERED_NEGATIVE it
  appends ONE first-person row to automation/state/discord-outbox.jsonl (gamma_standup.py's
  exact {content, source, queued_at} schema) naming the finding and the one-line revert --
  never re-posted on subsequent runs while the status holds. Places NO order, touches NO
  broker credentials, edits NOTHING on the live trading path. Pure-stdlib (json/pathlib/
  datetime/statistics/math + the local et_clock + exit_shape_parity_study modules) -- $0.

    Gamma_BoldTierRail -- 14:50 MT = 16:50 ET weekdays -- bold_tier_rail.py

  WIRING PATTERN (flash-free, C8 hidden-spawn chain cloned from install-futures-mirror.ps1 /
  install-gamma-standup.ps1's real-exit-code relay):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -> backtest\.venv\Scripts\pythonw.exe -> bold_tier_rail.py
  Runs on the BACKTEST venv pythonw for interpreter consistency with every other cloned-from-
  futures-mirror install script (see CLAUDE.md's repo-wide "interpreter for all runs" pin) even
  though bold_tier_rail.py itself needs no third-party packages -- exit_shape_parity_study.py
  (imported for reconstruct_positions) pulls in the same fleet_broker/exit_manager modules the
  rest of this family already runs under that interpreter.

  TZ RULE: this rig is Mountain Time (ET = local + 2h). NEVER pass an ET literal to -At.
  Weekly Mon-Fri trigger (NOT one-time, which would go dark the next day --
  project_scheduled_task_onetime_trigger_dark). Single daily fire -- no repetition block
  (unlike futures-mirror's all-day-repeating trigger; this is a once-a-day report+escalation
  check, matching Gamma_StandupEOD's single-fire pattern). 16:50 ET sits after the 16:00 RTH
  close and after Gamma_EodFlatten (15:55) so the day's real fills are already settled into
  fills-ledger.jsonl by the time this runs.

  NOT RUN BY THIS SESSION (per build instructions): registration is deliberately left to J /
  a future fire. automation/state/SCHEDULED-TASKS.md is deliberately NOT edited here either --
  the orchestrator's stated-count guard owns that file.

  To register (when ready):        powershell -File setup\scripts\install-bold-tier-rail.ps1
  To verify after registering:     setup\scripts\task_health_et.ps1
                                    Get-ScheduledTask -TaskName Gamma_BoldTierRail | Get-ScheduledTaskInfo
  To run once by hand:             backtest\.venv\Scripts\python.exe setup\scripts\bold_tier_rail.py
  REVERT (unregister the task):    Unregister-ScheduledTask -TaskName "Gamma_BoldTierRail" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\bold_tier_rail.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName     = "Gamma_BoldTierRail"

foreach ($p in @($vbs, $sysPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

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
#   -- backtest-venv pythonw -> bold_tier_rail.py
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- " +
               "`"$pythonwVenv`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 14:50 MT = 16:50 ET, single daily fire, Mon-Fri.
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At ([DateTime]"14:50")

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
    -Description ("Standing daily falsification-rail instrument for commit 718e0809's " +
    "BOLD-CORE-ATM-WIRE ship (2026-08-08 audit fix -- the rail existed only as prose before " +
    "this). 14:50 MT = 16:50 ET weekdays, after RTH close + EOD flatten. " +
    "bold_tier_rail.py: reconstructs bold-2's real post-2026-07-18 fills via " +
    "exit_shape_parity_study.reconstruct_positions, computes rail_status (NO_DATA/ACCRUING/" +
    "TRIGGERED_NEGATIVE/TRIGGERED_POSITIVE) + a PDT-blackout-aware ETA to n=20, overwrites " +
    "automation/state/bold-tier-rail.json. On the FIRST transition into TRIGGERED_NEGATIVE " +
    "appends ONE first-person finding+revert row to discord-outbox.jsonl (gamma_standup.py's " +
    "schema) -- never reposted while the status holds. Places NO order, touches NO broker " +
    "creds, edits nothing on the live trading path. `$0, pure-stdlib. Fail-open always exit 0. " +
    "Guarded by backtest/tests/test_bold_tier_rail.py (30 tests incl. a real-ledger " +
    "regression anchor).") `
    -Force | Out-Null

Write-Host "Registered $taskName (14:50 MT = 16:50 ET, Mon-Fri)"
Show-NextET $taskName
Write-Host ""
Write-Host "Bold tier rail wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_BoldTierRail | Get-ScheduledTaskInfo"
Write-Host "  setup\scripts\task_health_et.ps1"
