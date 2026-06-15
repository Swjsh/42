# Register the autoresearch watchdog as a Windows Scheduled Task.
# Runs every 30 minutes for the next 24 hours from registration.
#
# Usage:
#   .\setup\install-watchdog-modes-sweep.ps1
#   .\setup\install-watchdog-modes-sweep.ps1 -TargetIterations 100 -DurationHours 48

param(
    [int]$TargetIterations = 60,
    [int]$BatchSize = 10,
    [int]$IntervalMinutes = 30,
    [int]$DurationHours = 24
)

$ErrorActionPreference = "Stop"
$TaskName = "Gamma_AR_Watchdog"
$WatchdogScript = "C:\Users\jackw\Desktop\42\setup\watchdog-modes-sweep.ps1"

if (-not (Test-Path $WatchdogScript)) {
    Write-Error "Watchdog script not found: $WatchdogScript"
    exit 1
}

# Remove existing task (idempotent re-register).
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument ("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WatchdogScript`" " +
               "-TargetIterations $TargetIterations -BatchSize $BatchSize")

# First trigger fires 1 minute from now, repeats every $IntervalMinutes for $DurationHours.
$startAt = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $startAt

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Watchdog for autoresearch modes sweep. Restarts the sweep if stopped, until each mode hits $TargetIterations iterations." `
    -Force | Out-Null

# Add the repetition pattern (must be set post-register).
$task = Get-ScheduledTask -TaskName $TaskName
$task.Triggers[0].Repetition.Interval = "PT${IntervalMinutes}M"
$task.Triggers[0].Repetition.Duration = "PT${DurationHours}H"
$task | Set-ScheduledTask | Out-Null

Write-Host ""
Write-Host "Registered $TaskName" -ForegroundColor Green
Write-Host "  First fire:        $($startAt.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host "  Repeats every:     $IntervalMinutes min"
Write-Host "  Total duration:    $DurationHours hours"
Write-Host "  Target iterations: $TargetIterations per mode"
Write-Host "  Batch size:        $BatchSize iters per restart"
Write-Host ""
Write-Host "Watchdog log: C:\Users\jackw\Desktop\42\backtest\autoresearch\_state\watchdog.log"
Write-Host "Tail it with:"
Write-Host "  Get-Content C:\Users\jackw\Desktop\42\backtest\autoresearch\_state\watchdog.log -Wait -Tail 20"
Write-Host ""
Write-Host "To uninstall:  .\setup\uninstall-watchdog-modes-sweep.ps1"
