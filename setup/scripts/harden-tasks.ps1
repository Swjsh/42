# Harden Gamma_* Task Scheduler tasks for resilience:
#   1. RestartOnFailure: each task auto-retries up to N times if it errors
#   2. ExecutionTimeLimit: matches per-task wall-clock budget from _shared.ps1
#      (prior default PT5M was too short for premarket retry-once and EOD-summary)
#   3. StartWhenAvailable: if scheduled time was missed (machine asleep/off), run
#      ASAP when it becomes available - so a machine that woke up at 09:31 still
#      runs the 08:30 premarket
#   4. WakeToRun: machine wakes from sleep to run the task (CRITICAL for premarket
#      - if J's PC is asleep at 08:00, the LaunchTV task must wake it)
#
# Idempotent. Run anytime to re-apply hardening (e.g. after Windows updates or
# manual task edits via Task Scheduler GUI that may have reset settings).
#
# Usage: .\setup\scripts\harden-tasks.ps1 [-Audit]
#   -Audit: report current settings, do not modify

param([switch]$Audit)

$tasks = @{
    "Gamma_LaunchTV"    = @{ TimeoutMinutes = 3;  RestartCount = 2; RestartIntervalMinutes = 1 }
    "Gamma_Premarket"   = @{ TimeoutMinutes = 14; RestartCount = 1; RestartIntervalMinutes = 2 }   # 6m primary + 6m retry + buffer
    "Gamma_Heartbeat"   = @{ TimeoutMinutes = 3;  RestartCount = 0; RestartIntervalMinutes = 1 }   # don't restart heartbeat - next tick is 3min away
    "Gamma_EodFlatten"  = @{ TimeoutMinutes = 3;  RestartCount = 2; RestartIntervalMinutes = 1 }   # critical: closes positions
    "Gamma_EodSummary"  = @{ TimeoutMinutes = 10; RestartCount = 1; RestartIntervalMinutes = 5 }
    "Gamma_DailyReview" = @{ TimeoutMinutes = 7;  RestartCount = 1; RestartIntervalMinutes = 5 }
}

$found = 0
$missing = @()
$updated = 0
$alreadyOk = 0
$auditRows = @()

foreach ($name in $tasks.Keys) {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $t) {
        $missing += $name
        continue
    }
    $found++
    $cfg = $tasks[$name]
    $expectedTimeout = (New-TimeSpan -Minutes $cfg.TimeoutMinutes).ToString()
    $expectedInterval = (New-TimeSpan -Minutes $cfg.RestartIntervalMinutes).ToString()

    $current = @{
        TimeoutOK   = ($t.Settings.ExecutionTimeLimit -eq $expectedTimeout)
        RestartOK   = ($t.Settings.RestartCount -eq $cfg.RestartCount)
        IntervalOK  = ($t.Settings.RestartInterval -eq $expectedInterval)
        StartWhenOK = ($t.Settings.StartWhenAvailable -eq $true)
        WakeToRunOK = ($t.Settings.WakeToRun -eq $true)
    }
    $allOK = $current.Values -notcontains $false

    $auditRows += [PSCustomObject]@{
        Task          = $name
        Timeout       = $t.Settings.ExecutionTimeLimit
        Expected      = $expectedTimeout
        RestartCount  = $t.Settings.RestartCount
        RestartIntvl  = $t.Settings.RestartInterval
        StartWhenAvail= $t.Settings.StartWhenAvailable
        WakeToRun     = $t.Settings.WakeToRun
        Status        = if ($allOK) { "OK" } else { "DRIFT" }
    }

    if ($allOK) {
        $alreadyOk++
        continue
    }

    if ($Audit) {
        # Report only
        continue
    }

    # Apply hardening. Task Scheduler requires RestartCount and RestartInterval
    # to be set together (or both unset). If RestartCount=0, omit RestartInterval.
    $settingsParams = @{
        ExecutionTimeLimit         = (New-TimeSpan -Minutes $cfg.TimeoutMinutes)
        StartWhenAvailable         = $true
        WakeToRun                  = $true
        DontStopOnIdleEnd          = $true
        AllowStartIfOnBatteries    = $true
        DontStopIfGoingOnBatteries = $true
        MultipleInstances          = "IgnoreNew"
    }
    if ($cfg.RestartCount -gt 0) {
        $settingsParams.RestartCount = $cfg.RestartCount
        $settingsParams.RestartInterval = (New-TimeSpan -Minutes $cfg.RestartIntervalMinutes)
    }
    $newSettings = New-ScheduledTaskSettingsSet @settingsParams

    try {
        Set-ScheduledTask -TaskName $name -Settings $newSettings -ErrorAction Stop | Out-Null
        $updated++
        Write-Host ("UPDATED " + $name) -ForegroundColor Green
    } catch {
        Write-Host ("FAILED  " + $name + " - " + $_.Exception.Message) -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== Audit ===" -ForegroundColor Cyan
$auditRows | Format-Table -AutoSize

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ("Found:       " + $found + " / " + $tasks.Keys.Count)
Write-Host ("Already OK:  " + $alreadyOk)
Write-Host ("Updated:     " + $updated)
if ($missing.Count -gt 0) {
    Write-Host ("Missing:     " + ($missing -join ', ')) -ForegroundColor Yellow
    Write-Host "Run setup\install-tasks.ps1 to register missing tasks." -ForegroundColor Yellow
}
if ($Audit) {
    Write-Host "(Audit mode - no changes applied. Re-run without -Audit to harden.)" -ForegroundColor Yellow
}
