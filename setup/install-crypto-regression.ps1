#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_CryptoRegression scheduled task -- fires every 30 min, 24/7.

.DESCRIPTION
  Runs crypto/validators/runner.py + analyze_grinder.py on a 30-min cadence.
  Pure Python execution; zero LLM cost.
  Logs to automation/state/logs/crypto-regression-YYYY-MM-DD.log
  On FAIL appends to automation/overnight/STATUS.md `Known broken` for wake fires (OP 24).

  Idempotent -- re-registers cleanly if already present.
#>
[CmdletBinding()]
param(
    [Parameter()][switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$taskName = "Gamma_CryptoRegression"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    } else {
        Write-Host "$taskName not registered. Nothing to do."
    }
    return
}

$projectRoot = "C:\Users\jackw\Desktop\42"
$scriptPath = Join-Path $projectRoot "setup\scripts\run-crypto-regression.ps1"

if (-not (Test-Path $scriptPath)) {
    throw "Wrapper script not found: $scriptPath"
}

# Remove any existing version so we re-register cleanly
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Removed existing $taskName."
}

# 30-min cadence, starting at next half-hour boundary, runs forever
$startBoundary = (Get-Date).AddMinutes(2)
$trigger = New-ScheduledTaskTrigger -Once -At $startBoundary `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration ([System.TimeSpan]::FromDays(365 * 10))

# Windowless launch chain (project_mcp_window_leak_fix / audit BARE_CMD_POWERSHELL):
# a direct powershell.exe action flashes OpenConsole on Win11 -- route via wscript->pythonw.
$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runPs1  = "C:\Users\jackw\Desktop\42\setup\scripts\run_ps1_hidden.py"
$runExe  = "C:\Users\jackw\Desktop\42\setup\scripts\run_exe_hidden.vbs"
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument ("//nologo `"" + $runExe + "`" `"" + $pythonw + "`" `"" + $runPs1 + "`" `"" + $scriptPath + "`"")

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "Gamma crypto regression check -- validates chart-reading primitives every 30 min on live BTC. Pure Python, no LLM. PASS/FAIL logged to automation/state/logs/crypto-regression-*.log." | Out-Null

$task = Get-ScheduledTask -TaskName $taskName
Write-Host "Registered $taskName."
Write-Host "  State:        $($task.State)"
Write-Host "  Next run:     $($task | Get-ScheduledTaskInfo | Select-Object -ExpandProperty NextRunTime)"
Write-Host "  Wrapper:      $scriptPath"
Write-Host ""
Write-Host ("Verify:        Get-ScheduledTask -TaskName " + "'$taskName'" + " | Format-Table")
Write-Host ("Manual run:    Start-ScheduledTask -TaskName " + "'$taskName'")
Write-Host ("Logs:          " + $projectRoot + "/automation/state/logs/crypto-regression-*.log")
Write-Host ("Uninstall:     setup/install-crypto-regression.ps1 -Uninstall")
