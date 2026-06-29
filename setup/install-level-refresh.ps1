#requires -Version 5.1
# Install Gamma_LevelRefresh -- every 5 min, keeps key-levels.json tracking live intraday
# structure so the engine is never blind to a fresh high/low (the 2026-06-29 739.40 miss).
# ASCII-only. Windowless wscript->pythonw chain. backtest .venv (reaper-exempt). $0.
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$taskName = "Gamma_LevelRefresh"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\run-level-refresh.ps1"
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Every 5 min, all day (cheap REST call; outside RTH it just recomputes premarket levels).
$startBoundary = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $startBoundary `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration ([System.TimeSpan]::FromDays(365 * 10))

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runPs1  = "C:\Users\jackw\Desktop\42\setup\scripts\run_ps1_hidden.py"
$runExe  = "C:\Users\jackw\Desktop\42\setup\scripts\run_exe_hidden.vbs"
$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument ("//nologo `"" + $runExe + "`" `"" + $pythonw + "`" `"" + $runPs1 + "`" `"" + $scriptPath + "`"")

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "Every 5 min: refresh key-levels.json with live intraday RTH high/low + swings so the engine sees current structure (fixes the 2026-06-29 frozen-premarket-levels blindness). Pure Python REST, backtest .venv, no orders. $0." | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
