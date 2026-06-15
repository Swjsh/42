#!/usr/bin/env pwsh
# L31 recovery — TradingView CDP silent-death fix.
# Kill all TV processes, relaunch via launch_tv_debug.ps1 with --remote-debugging-port=9222.
$ErrorActionPreference = "Continue"

Write-Output "=== TV CDP RECOVERY ==="
Write-Output ("now: " + (Get-Date -Format "yyyy-MM-ddTHH:mm:ss"))

$tvProcs = Get-Process | Where-Object { $_.ProcessName -like '*TradingView*' }
Write-Output ("found_tv_procs: " + $tvProcs.Count)

if ($tvProcs.Count -gt 0) {
    foreach ($p in $tvProcs) {
        Write-Output ("  killing PID " + $p.Id + " (" + $p.ProcessName + ")")
    }
    $tvProcs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

Write-Output ""
Write-Output "Relaunching via launch_tv_debug.ps1..."
& "C:\Users\jackw\Desktop\42\setup\launch_tv_debug.ps1"

Start-Sleep -Seconds 8
Write-Output ""
$cdp = Test-NetConnection -ComputerName 127.0.0.1 -Port 9222 -InformationLevel Quiet -WarningAction SilentlyContinue
Write-Output ("TV CDP port 9222 listening: " + $cdp)
$newTvProcs = Get-Process | Where-Object { $_.ProcessName -like '*TradingView*' }
Write-Output ("new_tv_proc_count: " + $newTvProcs.Count)
