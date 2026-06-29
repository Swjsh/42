#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_EngineStressSwarm — overnight counterfactual engine-stress cook.

  Fires every 2h across the after-hours/overnight window, one bounded batch per fire.
  Each batch: real SPY days x perturbations x sizing/exit/direction variants through the
  REAL engine, then the 5-model free swarm critiques the anomalies. $0. The runner's
  own market-hours guard skips 09:30-15:55 ET, so this never overlaps live trading.

  Windowless launch chain (project_mcp_window_leak_fix): wscript -> run_exe_hidden.vbs
  -> pythonw -> run_ps1_hidden.py -> run-engine-stress-swarm.ps1. The runner uses the
  backtest\.venv interpreter, which is reaper-EXEMPT in _shared.ps1.
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$taskName = "Gamma_EngineStressSwarm"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\run-engine-stress-swarm.ps1"
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Repeat every 2h for 24h starting in 2 min -> the runner's market-hours guard keeps it
# to after-hours/overnight only, so an every-2h trigger effectively "cooks all night"
# without firing during live trading. Start soon so tonight gets extra batches.
$startBoundary = (Get-Date).AddMinutes(2)
$trigger = New-ScheduledTaskTrigger -Once -At $startBoundary `
    -RepetitionInterval (New-TimeSpan -Hours 2) `
    -RepetitionDuration ([System.TimeSpan]::FromDays(365 * 10))

# Windowless launch chain (project_mcp_window_leak_fix / audit BARE_CMD_POWERSHELL).
$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runPs1  = "C:\Users\jackw\Desktop\42\setup\scripts\run_ps1_hidden.py"
$runExe  = "C:\Users\jackw\Desktop\42\setup\scripts\run_exe_hidden.vbs"
$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument ("//nologo `"" + $runExe + "`" `"" + $pythonw + "`" `"" + $runPs1 + "`" `"" + $scriptPath + "`"")

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 35)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "Overnight counterfactual engine-stress swarm: perturb real SPY days x sizing/exit/direction variants through the real engine, 5-model free swarm critiques anomalies. Runner skips market hours. backtest .venv (reaper-exempt). \$0." | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
