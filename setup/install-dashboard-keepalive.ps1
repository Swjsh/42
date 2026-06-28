#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_DashboardKeepalive scheduled task -- fires every 5 min, keeps
  the Next.js dashboard alive at http://localhost:3000.

.DESCRIPTION
  The Next.js dashboard at :3000 is the primary visibility layer (pixel-art trade
  house). It has no auto-start; without a keepalive it goes dark whenever the host
  reboots or the process dies silently.

  This task mirrors run-companion-keepalive.ps1 (companion at :4317):
    - HTTP liveness probe against / (200 = alive)
    - If dead and port is free: spawns `node .next/standalone/server.js` or
      `node node_modules/next/dist/bin/next start -p 3000` (production build only)
    - CreateNoWindow spawn -- no bare PowerShell/OpenConsole window (OP-27 L41)
    - Does NOT run `next dev` (dev server is not safe for Task Scheduler context)

  REQUIRES: a production build already exists at dashboard/.next/
  To build: cd C:\Users\jackw\Desktop\42\dashboard && npm run build

.PARAMETER Uninstall
  Remove the task.
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$taskName = "Gamma_DashboardKeepalive"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\run-dashboard-keepalive.ps1"
$vbsWrapper  = "C:\Users\jackw\Desktop\42\setup\scripts\run_hidden.vbs"

if (-not (Test-Path $scriptPath)) { throw "missing $scriptPath" }
if (-not (Test-Path $vbsWrapper)) { throw "missing $vbsWrapper" }

# Warn if no production build exists yet (task can still be registered -- it will
# log an ABORT and retry next tick once a build is present).
$buildDir = "C:\Users\jackw\Desktop\42\dashboard\.next"
if (-not (Test-Path $buildDir)) {
    Write-Warning "No .next build found at $buildDir. Run 'npm run build' in the dashboard directory before the task fires."
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Every 5 minutes, indefinitely (matches companion keepalive cadence).
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -Once -At (Get-Date) -RepetitionDuration ([TimeSpan]::MaxValue)

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$vbsWrapper`" `"$scriptPath`""

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "Every 5min: keeps Next.js dashboard alive at :3000 (primary visibility layer). HTTP probe + silent node respawn. Hidden window per OP-27 L41. No dev server -- production build only." | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
