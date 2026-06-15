# T74 -- Grinder RSS monitor sidecar
# Polls working-set RSS of the v14_enhanced grinder and all its worker processes
# every 30s. Writes to a CSV log. Alerts (RED) when total RSS exceeds threshold.
#
# Usage:
#   .\grinder-rss-monitor.ps1                         # defaults to v14_enhanced_stage1
#   .\grinder-rss-monitor.ps1 -Stage "v14_enhanced_stage2"
#   .\grinder-rss-monitor.ps1 -AlertMB 1500           # alert threshold in MB (default 2048)
#   .\grinder-rss-monitor.ps1 -PollSeconds 30         # poll interval (default 30)
#   .\grinder-rss-monitor.ps1 -RunOnce                # one poll then exit
#
# Foot-gun note (OP-25 L27): Get-Process can MISS pythonw.exe console-less processes.
# Always use WMI (Get-WmiObject Win32_Process) for ground-truth liveness and RSS.
# This script uses WMI throughout.
#
# Stop condition: progress.json status != "running" OR -RunOnce switch set.

param(
    [string]$Stage        = "v14_enhanced_stage1",
    [int]   $AlertMB      = 2048,
    [int]   $PollSeconds  = 30,
    [switch]$RunOnce
)

$ErrorActionPreference = "Stop"

$WorkDir      = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$StateDir     = Join-Path $WorkDir "backtest\autoresearch\_state\$Stage"
$ProgressFile = Join-Path $StateDir "progress.json"
$LogFile      = Join-Path $StateDir "rss-monitor.csv"

if (-not (Test-Path $StateDir)) {
    Write-Host "ERROR: State dir not found: $StateDir"
    exit 1
}

# Write CSV header if new file
if (-not (Test-Path $LogFile)) {
    "ts,master_pid,master_rss_mb,worker_count,workers_rss_mb,total_rss_mb,status,alert" |
        Out-File $LogFile -Encoding utf8
}

Write-Host "[rss-monitor] Stage=$Stage AlertMB=$AlertMB PollSeconds=$PollSeconds"
Write-Host "[rss-monitor] Log: $LogFile"

do {
    $ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"

    # Read progress.json
    try {
        $prog = Get-Content $ProgressFile -Raw | ConvertFrom-Json
    } catch {
        Write-Host "[$ts] WARN: Cannot read progress.json: $_"
        if (-not $RunOnce) { Start-Sleep -Seconds $PollSeconds }
        continue
    }

    $masterPid = [int]$prog.current_pid
    $status    = $prog.status

    if ($status -ne "running") {
        Write-Host "[$ts] Grinder status='$status' -- monitor stopping."
        break
    }

    # Query master process RSS via WMI (OP-25 L27: WMI only, not Get-Process)
    $masterRssBytes = 0L
    try {
        $wmiProc = Get-WmiObject Win32_Process -Filter "ProcessId = $masterPid" -ErrorAction Stop
        if ($wmiProc) {
            $masterRssBytes = [long]$wmiProc.WorkingSetSize
        }
    } catch {
        Write-Host "[$ts] WARN: WMI query for PID $masterPid failed: $_"
    }

    # Find worker pythonw processes spawned by master (ParentProcessId = master)
    $workerRssBytes = 0L
    $workerCount    = 0
    try {
        $workers = Get-WmiObject Win32_Process -Filter "Name LIKE '%pythonw%'" |
                   Where-Object { $_.ParentProcessId -eq $masterPid }
        foreach ($w in $workers) {
            $workerRssBytes += [long]$w.WorkingSetSize
            $workerCount++
        }
    } catch {
        Write-Host "[$ts] WARN: WMI worker query failed: $_"
    }

    $masterRssMB  = [math]::Round($masterRssBytes / 1MB, 1)
    $workerRssMB  = [math]::Round($workerRssBytes / 1MB, 1)
    $totalRssBytes = $masterRssBytes + $workerRssBytes
    $totalRssMB   = [math]::Round($totalRssBytes / 1MB, 1)
    $alert        = if ($totalRssBytes -gt ($AlertMB * 1MB)) { "RED" } else { "ok" }

    # Append CSV row
    "$ts,$masterPid,$masterRssMB,$workerCount,$workerRssMB,$totalRssMB,$status,$alert" |
        Out-File $LogFile -Encoding utf8 -Append

    if ($alert -eq "RED") {
        Write-Host "[$ts] RSS_ALERT: total=$($totalRssMB)MB threshold=$($AlertMB)MB master=$($masterRssMB)MB workers[$workerCount]=$($workerRssMB)MB -- OOM risk"
    } else {
        Write-Host "[$ts] RSS ok: total=$($totalRssMB)MB master=$($masterRssMB)MB workers[$workerCount]=$($workerRssMB)MB"
    }

    if (-not $RunOnce) {
        Start-Sleep -Seconds $PollSeconds
    }

} while (-not $RunOnce)

Write-Host "[rss-monitor] Done. Log at $LogFile"
