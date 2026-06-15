#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_NumericPulse1m scheduled task -- every 1 min during RTH.

.DESCRIPTION
  Runs numeric_pulse.py every 1 minute. Per docs/2-MIN-CADENCE-ARCHITECTURE.md
  Option 1: pure-Python pattern detection is FREE and gives Gamma 1-min
  numeric coverage without busting the LLM budget.

  Wired via OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> sys-pythonw
                   -> run_ps1_hidden.py -> run-numeric-pulse-1m.ps1
                   -> numeric_pulse.py
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_NumericPulse1m"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1 = Join-Path $ScriptsDir "run-numeric-pulse-1m.ps1"

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

# Fire at 09:30 ET, repeat every minute for 6h25m (covers 09:30 - 15:55 ET)
$startTime = [DateTime]"09:30"
$trigger = New-ScheduledTaskTrigger -Daily -At $startTime

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Every-1-min pure-Python pattern detector pass during RTH. Per OP-25 ENGINE-EYES + docs/2-MIN-CADENCE-ARCHITECTURE.md Option 1. Zero LLM cost. Wrapper enforces RTH/weekday gate." | Out-Null

# Add 1-minute repetition for 6h25m duration
$task = Get-ScheduledTask -TaskName $TaskName
$task.Triggers[0].Repetition.Interval = "PT1M"
$task.Triggers[0].Repetition.Duration = "PT6H25M"
Set-ScheduledTask -TaskName $TaskName -Trigger $task.Triggers[0] | Out-Null

Write-Output ("OK: Registered $TaskName")
Write-Output ("    First fire: 09:30 ET, repeats every 1 min until 15:55 ET")
Write-Output ("    Chain: wscript -> run_exe_hidden.vbs -> sys-pythonw -> run_ps1_hidden.py -> run-numeric-pulse-1m.ps1 -> numeric_pulse.py")
Write-Output ("    Cost:  `$0/day (pure Python)")
