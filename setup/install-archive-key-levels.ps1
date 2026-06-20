#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_ArchiveKeyLevels scheduled task -- fires 16:05 ET weekdays.

.DESCRIPTION
  Standalone $0 daily snapshot of automation/state/key-levels.json into:
    1. analysis/level-quality/snapshots/{date}/        (level-quality gym input)
    2. journal/key-levels-archive/key-levels-{date}.json (real-level backtest archive)

  WHY THIS EXISTS (the #1 validation constraint): every level-keyed watcher /
  backtest validation falls back to SYNTHETIC PDH/PDL proxies because there is no
  historical archive of the production 3-star key-levels J draws. run-daily-review.ps1
  archives key-levels.json inline, BUT it early-exits on holidays + on a rate-limit
  retry failure -- so the archive silently misses days. This independent task
  guarantees the archive accumulates toward the N>=20-30 days needed to RE-RUN the
  level validations on REAL levels (floor_hold, close_ceiling, BEARISH_REJECTION).
  See markdown/planning/FUTURE-IMPROVEMENTS.md.

  Worker: automation/scripts/archive_key_levels.py (idempotent -- SKIP_EXISTS per
  destination). Per CLAUDE.md OP-22/OP-25 engine-benefit autonomy.
  Uses OP-27 L41/L42 canonical zero-leak hidden chain.

  Does NOT modify key-levels.json, heartbeat.md, or params*.json. Never places orders.
  Pure Python. Zero LLM cost.
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_ArchiveKeyLevels"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-archive-key-levels.ps1"

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

# 16:05 ET weekdays -- after Gamma_DailyReview/EOD pipeline. (ET written as -At per
# the existing fleet convention; all EOD tasks share the same local offset on this box.)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "16:05"

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
    -Description "Daily key-levels snapshot -> journal/key-levels-archive + analysis/level-quality/snapshots. Unblocks real-level validation (the #1 data gap). Pure Python, zero LLM cost."

Write-Output "OK: Registered $TaskName for 16:05 ET weekdays"
Write-Output "    Archive:   journal\key-levels-archive\key-levels-{date}.json"
Write-Output "    Snapshot:  analysis\level-quality\snapshots\{date}\"
Write-Output "    Audit:     python setup\scripts\audit_scheduled_tasks.py"
Write-Output "    Test:      Start-ScheduledTask -TaskName $TaskName"
