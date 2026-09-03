#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_SpendSummary scheduled task -- fires 23:30 ET nightly.

.DESCRIPTION
  Walks Claude Code session JSONL + MiniMax telemetry, writes per-day spend
  snapshot + history. Closes the OP-3 cost-effectiveness loop -- see actual
  burn velocity instead of inferring only when rate-limits fire.

  Output:
    automation/state/spend-{YYYY-MM-DD}.json -- daily snapshot
    automation/state/spend-daily.jsonl       -- append-only history
    STATUS.md WARN appended if total > $50/day (default threshold)

  Per CLAUDE.md OP-3 (cost discipline) + OP-25 engine-benefit autonomy.
  Uses OP-27 L42 canonical zero-leak chain.

  Pure Python. Zero LLM cost.
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_SpendSummary"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-spend-summary.ps1"

foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

# TZ-SYSTEMIC fix (2026-06-26): machine is Mountain time (ET = local + 2h).
# Intended fire time: 23:30 ET = 21:30 MT.  Use MT local time for -At.
# If the machine moves back to ET, change 21:30 -> 23:30 and update this comment.
$trigger = New-ScheduledTaskTrigger -Daily -At "21:30"
# 2026-09-03 EVENING-TASK-MISSED-RUN-SWEEP (queue.md): same self-heal fix already shipped on
# Gamma_MacroCalendar/Gamma_EarningsCalendar/Gamma_PremarketReadiness (ac47dd10) -- a
# correctly-registered -Daily trigger can still silently skip one evening. spend_summary.py's
# _append_jsonl_history() is documented idempotent ("if today's row already exists, replace
# it"), and its alerting is transition-only, so an extra fire on a normal day is a safe no-op.
# Self-heal window: every 15 min for 30 min after the primary fire.
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "21:30" `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily spend summary -- aggregates Claude Code + MiniMax token costs into automation/state/spend-{date}.json + spend-daily.jsonl. OP-3 cost discipline. Pure Python, zero LLM cost."

Write-Output "OK: Registered $TaskName for 23:30 ET daily"
Write-Output "    Snapshot: automation\state\spend-{date}.json"
Write-Output "    History:  automation\state\spend-daily.jsonl"
Write-Output "    Audit:    python setup\scripts\audit_scheduled_tasks.py"
Write-Output "    Test:     Start-ScheduledTask -TaskName $TaskName"
