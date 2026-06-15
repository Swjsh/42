# Install-tasks.ps1 - registers the full autonomy stack with Windows Task Scheduler.
# Idempotent: safe to re-run. Removes existing Gamma_* tasks first, then registers fresh.
# User-level only - does NOT require admin.

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"

if (-not (Test-Path $ScriptsDir)) {
    Write-Error "Scripts directory not found: $ScriptsDir"
    exit 1
}

# Common settings - wake the PC to run, retry if missed, no idle stop, allow battery
$commonSettings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

# Weekly settings - allow longer runtime for the heavier weekly aggregation
$weeklySettings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 12)

function Register-GammaTask {
    param(
        [string]$Name,
        [string]$ScriptName,
        [DateTime]$AtTime,
        $RepetitionInterval,
        $RepetitionDuration,
        [string]$Description
    )

    $scriptPath = Join-Path $ScriptsDir $ScriptName
    if (-not (Test-Path $scriptPath)) {
        Write-Error "Script not found: $scriptPath"
        return
    }

    # Remove existing
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue

    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

    $trigger = New-ScheduledTaskTrigger -Daily -At $AtTime

    Register-ScheduledTask `
        -TaskName $Name `
        -Action $action `
        -Trigger $trigger `
        -Settings $commonSettings `
        -Description $Description `
        -Force | Out-Null

    # Repetition cannot be set on the trigger object before registration. Update post-register.
    if ($RepetitionInterval) {
        $task = Get-ScheduledTask -TaskName $Name
        $iso = "PT$([int]$RepetitionInterval.TotalMinutes)M"
        $task.Triggers[0].Repetition.Interval = $iso
        if ($RepetitionDuration) {
            $hr = [int]$RepetitionDuration.TotalHours
            $min = [int]($RepetitionDuration.TotalMinutes - ($hr * 60))
            $task.Triggers[0].Repetition.Duration = "PT${hr}H${min}M"
        }
        $task | Set-ScheduledTask | Out-Null
        Write-Host "  Registered: $Name @ $($AtTime.ToString('HH:mm')) repeating every $($RepetitionInterval.TotalMinutes)m for $($RepetitionDuration.TotalHours)h$([int]($RepetitionDuration.TotalMinutes % 60))m"
    } else {
        Write-Host "  Registered: $Name @ $($AtTime.ToString('HH:mm'))"
    }
}

Write-Host "Installing Gamma autonomy tasks..."
Write-Host "  Working dir: $WorkDir"
Write-Host ""

# 08:00 ET - Launch TradingView with CDP
Register-GammaTask `
    -Name "Gamma_LaunchTV" `
    -ScriptName "run-launch-tv.ps1" `
    -AtTime ([DateTime]"08:00") `
    -Description "Gamma: Launch TradingView with --remote-debugging-port=9222 before market open"

# 08:30 ET - Premarket routine
Register-GammaTask `
    -Name "Gamma_Premarket" `
    -ScriptName "run-premarket.ps1" `
    -AtTime ([DateTime]"08:30") `
    -Description "Gamma: Pre-market routine (level audit, today-bias.json, falsifiable hypothesis, draw levels, seed journal)"

# 09:30 ET - Heartbeat starts, repeats every 3 min for 6h25m (until 15:55)
Register-GammaTask `
    -Name "Gamma_Heartbeat" `
    -ScriptName "run-heartbeat.ps1" `
    -AtTime ([DateTime]"09:30") `
    -RepetitionInterval (New-TimeSpan -Minutes 3) `
    -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 25) `
    -Description "Gamma: Heartbeat tick (every 3 min during market hours, loop v2 adaptive cadence inside prompt)"

# 15:55 ET - EOD flatten safety net
Register-GammaTask `
    -Name "Gamma_EodFlatten" `
    -ScriptName "run-eod-flatten.ps1" `
    -AtTime ([DateTime]"15:55") `
    -Description "Gamma: EOD flatten safety net - close any 0DTE position not already closed by heartbeat time stop"


# 09:30 ET - Aggressive heartbeat (second paper account), repeats every 3 min for 6h25m
Register-GammaTask `
    -Name "Gamma_Heartbeat_Aggressive" `
    -ScriptName "run-heartbeat-aggressive.ps1" `
    -AtTime ([DateTime]"09:30") `
    -RepetitionInterval (New-TimeSpan -Minutes 3) `
    -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 25) `
    -Description "Gamma: Aggressive heartbeat -- second paper account, wider stops, relaxed gates"

# 15:55 ET - Aggressive EOD flatten safety net
Register-GammaTask `
    -Name "Gamma_EodFlatten_Aggressive" `
    -ScriptName "run-eod-flatten-aggressive.ps1" `
    -AtTime ([DateTime]"15:55") `
    -Description "Gamma: Aggressive EOD flatten safety net -- close any open aggressive 0DTE before expiry"

Write-Host ""
Write-Host "Installed 6 tasks (4 safe + 2 aggressive). Verify with: Get-ScheduledTask -TaskName 'Gamma_*' | Format-Table"
Write-Host ""
Write-Host "First run:"
Write-Host "  Tomorrow 08:00 ET - launch-tv"
Write-Host "  Tomorrow 08:30 ET - premarket (shared -- same SPY levels for both strategies)"
Write-Host "  Tomorrow 09:30 ET - safe + aggressive heartbeats begin"
Write-Host "  Sunday 18:00 ET - weekly review (Mon-Fri rollup)"
Write-Host ""
Write-Host "To uninstall: setup\uninstall-tasks.ps1"
