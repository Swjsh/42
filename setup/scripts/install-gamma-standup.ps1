#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_StandupAM + Gamma_StandupEOD -- Gamma's self-initiated, first-person
  Discord standups (J directive 2026-08-08: "Gamma isn't existing or wanting anything;
  I need a coworker, not a chatbot").

  PURPOSE: two short daily messages, written in Gamma's own voice (what I did, what I'm
  on, what I want), queued through the EXISTING Discord bridge outbox
  (setup/scripts/gamma_standup.py --mode morning|eod appends ONE row to
  automation/state/discord-outbox.jsonl, same {content, source, queued_at} schema every
  other producer already uses -- discord-bridge.py drains it, unchanged). Deterministic,
  $0, no LLM anywhere on this path -- see gamma_standup.py's own module docstring.

    Gamma_StandupAM  -- 06:15 MT = 08:15 ET weekdays -- gamma_standup.py --mode morning
    Gamma_StandupEOD -- 14:45 MT = 16:45 ET weekdays -- gamma_standup.py --mode eod

  WIRING PATTERN (flash-free, matches install-futures-mirror.ps1 / VBS-WRAPPER-EXIT-CODE-
  BLIND-SPOT migration -- 2026-08-08 relay, real exit-code visibility):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -> backtest\.venv\Scripts\pythonw.exe -> gamma_standup.py --mode <morning|eod>
  gamma_standup.py is pure-stdlib (no pandas/numpy needed) but the build spec pins the
  SAME backtest-venv pythonw every other cloned-from-futures-mirror install script uses,
  for interpreter consistency across the fleet -- see CLAUDE.md's repo-wide "interpreter
  for all runs" pin.

  TZ RULE: this rig is Mountain Time (ET = local + 2h). NEVER pass an ET literal to -At.
  Weekly Mon-Fri triggers (NOT one-time, which would go dark the next day --
  project_scheduled_task_onetime_trigger_dark). Single daily fire each -- no repetition
  block (unlike the all-day-repeating futures-mirror trigger; a standup runs once).

  NOT RUN BY THIS SESSION (per build instructions): registration is deliberately left to
  J / a future fire. automation/state/SCHEDULED-TASKS.md is deliberately NOT edited here
  either -- the orchestrator's stated-count guard owns that file.

  To register (when ready):        powershell -File setup\scripts\install-gamma-standup.ps1
  To verify after registering:     setup\scripts\task_health_et.ps1
                                    Get-ScheduledTask -TaskName Gamma_StandupAM,Gamma_StandupEOD | Get-ScheduledTaskInfo
  REVERT (either or both):         Unregister-ScheduledTask -TaskName "Gamma_StandupAM" -Confirm:$false
                                    Unregister-ScheduledTask -TaskName "Gamma_StandupEOD" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\gamma_standup.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')

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

function Register-StandupTask {
    param(
        [string]$TaskName,
        [string]$Mode,
        [string]$AtLocal,
        [string]$Description
    )

    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    # wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
    #   -- backtest-venv pythonw -> gamma_standup.py --mode <morning|eod>
    $wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- " +
                   "`"$pythonwVenv`" `"$script`" --mode $Mode"

    $action = New-ScheduledTaskAction `
        -Execute "wscript.exe" `
        -Argument $wscriptArgs `
        -WorkingDirectory $root

    $trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At ([DateTime]$AtLocal)

    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
        -MultipleInstances IgnoreNew

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description $Description `
        -Force | Out-Null

    Write-Host "Registered $TaskName ($AtLocal MT, Mon-Fri, --mode $Mode)"
    Show-NextET $TaskName
}

Register-StandupTask `
    -TaskName "Gamma_StandupAM" `
    -Mode "morning" `
    -AtLocal "06:15" `
    -Description ("Gamma's self-initiated morning Discord standup (J directive 2026-08-08). " +
    "06:15 MT = 08:15 ET weekdays. gamma_standup.py --mode morning: OVERNIGHT/YESTERDAY " +
    "(git log, feat/fix/docs only) + TODAY (queue.md backlog) + I WANT (top-3 wants " +
    "registry) + CLOCKS (SSR/MES shadow progress + catastrophe-cap accrual); Monday adds " +
    "a WEEKEND RECAP section. Appends ONE row to discord-outbox.jsonl (bridge drains it), " +
    "writes automation/state/gamma-standup-latest.json. Deterministic, `$0, no LLM. " +
    "1200-char hard cap + banned-substring/long-path filters, test-enforced " +
    "(backtest/tests/test_gamma_standup.py). Read-only against every trading-path file; " +
    "places no order, arms nothing.")

Register-StandupTask `
    -TaskName "Gamma_StandupEOD" `
    -Mode "eod" `
    -AtLocal "14:45" `
    -Description ("Gamma's self-initiated end-of-day Discord standup (J directive 2026-08-08). " +
    "14:45 MT = 16:45 ET weekdays. gamma_standup.py --mode eod: P&L (both accounts if " +
    "today's journal has rows) + WHAT I LEARNED (today's top shipped commit) + TOMORROW " +
    "(queue.md backlog) + I WANT (delta-annotated vs the morning run's latest.json). " +
    "Appends ONE row to discord-outbox.jsonl (bridge drains it), writes " +
    "automation/state/gamma-standup-latest.json. Deterministic, `$0, no LLM. 1200-char " +
    "hard cap + banned-substring/long-path filters, test-enforced " +
    "(backtest/tests/test_gamma_standup.py). Read-only against every trading-path file; " +
    "places no order, arms nothing.")

Write-Host ""
Write-Host "Gamma standup wired (2 tasks). Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_StandupAM,Gamma_StandupEOD | Get-ScheduledTaskInfo"
Write-Host "  setup\scripts\task_health_et.ps1"
