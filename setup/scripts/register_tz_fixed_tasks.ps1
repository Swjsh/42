#requires -Version 5.1
<#
.SYNOPSIS
  Re-register 3 Gamma tasks at correct MT local times = correct ET fire times.
  TZ-SYSTEMIC fix 2026-06-26: machine moved Ohio(Eastern)->Colorado(Mountain).
  ET = local + 2h.  Tasks previously registered at "-At <ET time>" fired 2h LATE.

  Tasks corrected:
    Gamma_SwarmPremarket   intended 08:15 ET -> 06:15 MT
    Gamma_ContextGuard     intended 16:10 ET -> 14:10 MT
    Gamma_SpendSummary     intended 23:30 ET -> 21:30 MT
#>

$ErrorActionPreference = "Stop"
$etz = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$root = "C:\Users\jackw\Desktop\42"

# Windowless launch chain (project_mcp_window_leak_fix / audit_scheduled_tasks BARE_CMD_POWERSHELL).
# A DIRECT `powershell.exe -WindowStyle Hidden` action still flashes OpenConsole on Win11.
# Route every Gamma task through wscript -> run_exe_hidden.vbs -> pythonw -> run_ps1_hidden.py -> <ps1>.
$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runPs1  = Join-Path $root "setup\scripts\run_ps1_hidden.py"
$runExe  = Join-Path $root "setup\scripts\run_exe_hidden.vbs"

function Show-NextET {
    param([string]$TaskName)
    $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($info -and $info.NextRunTime) {
        $et = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
        Write-Host ("  -> NextRun ET: {0}" -f $et.ToString("yyyy-MM-dd HH:mm"))
    } else {
        Write-Host "  -> NextRun: (no trigger / not scheduled)"
    }
}

# ===== 1. Gamma_SwarmPremarket: 08:15 ET = 06:15 MT =====
$taskName = "Gamma_SwarmPremarket"
$scriptPath = Join-Path $root "setup\scripts\run-swarm-premarket.ps1"
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
$action   = New-ScheduledTaskAction -Execute "wscript.exe" `
              -Argument ("//nologo `"" + $runExe + "`" `"" + $pythonw + "`" `"" + $runPs1 + "`" `"" + $scriptPath + "`"")
$trigger  = New-ScheduledTaskTrigger -Weekly `
              -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
              -At ([DateTime]"06:15")
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable `
              -DontStopOnIdleEnd -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "Gamma: Swarm pre-market hypothesis engine. 06:15 MT = 08:15 ET. TZ-SYSTEMIC fix 2026-06-26." `
    -Force | Out-Null
Write-Host "Registered $taskName (06:15 MT = 08:15 ET)"
Show-NextET $taskName

# ===== 2. Gamma_ContextGuard: 16:10 ET = 14:10 MT =====
$taskName   = "Gamma_ContextGuard"
$scriptPath = Join-Path $root "setup\scripts\check-context-budget.ps1"
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
$action   = New-ScheduledTaskAction -Execute "wscript.exe" `
              -Argument ("//nologo `"" + $runExe + "`" `"" + $pythonw + "`" `"" + $runPs1 + "`" `"" + $scriptPath + "`" -AutoFix")
$trigger  = New-ScheduledTaskTrigger -Daily -At ([DateTime]"14:10")
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
              -RestartCount 1 -RestartInterval (New-TimeSpan -Minutes 5) `
              -StartWhenAvailable -WakeToRun -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "Context-leanness guard. 14:10 MT = 16:10 ET. TZ-SYSTEMIC fix 2026-06-26." `
    -Force | Out-Null
Write-Host "Registered $taskName (14:10 MT = 16:10 ET)"
Show-NextET $taskName

# ===== 3. Gamma_SpendSummary: 23:30 ET = 21:30 MT =====
$taskName   = "Gamma_SpendSummary"
$pythonw    = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runPs1     = Join-Path $root "setup\scripts\run_ps1_hidden.py"
$runExe     = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$targetPs1  = Join-Path $root "setup\scripts\run-spend-summary.ps1"
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
$action   = New-ScheduledTaskAction -Execute "wscript.exe" `
              -Argument ("//nologo `"" + $runExe + "`" `"" + $pythonw + "`" `"" + $runPs1 + "`" `"" + $targetPs1 + "`"")
$trigger  = New-ScheduledTaskTrigger -Daily -At ([DateTime]"21:30")
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
              -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "Daily spend summary. 21:30 MT = 23:30 ET. TZ-SYSTEMIC fix 2026-06-26." | Out-Null
Write-Host "Registered $taskName (21:30 MT = 23:30 ET)"
Show-NextET $taskName

Write-Host ""
Write-Host "All 3 tasks re-registered with correct MT local times."
Write-Host "Verify with: setup\scripts\task_health_et.ps1"
