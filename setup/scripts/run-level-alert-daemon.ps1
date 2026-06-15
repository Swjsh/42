#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Launch the local SPY level-alert daemon for one RTH session.

.DESCRIPTION
  Wrapper for `automation/scripts/level_alert_daemon.py`. Designed to be
  registered as `Gamma_LevelAlertDaemon` scheduled task, firing 09:25 ET
  weekdays. Runs until 16:05 ET (or `--hours 6.75` from start, whichever first).

  Cost: $0/day. yfinance is free, no Claude API calls. The daemon writes
  alerts to `automation/state/live-alerts.jsonl` which the heartbeat reads
  on each tick.

.NOTES
  Per CLAUDE.md OP 3 (cost-effectiveness): runs locally in pythonw so it
  doesn't flash a console.
  Per CLAUDE.md OP 25 (autonomous operator): wrapping silent-fail mode 3
  in stderr capture so a missing yfinance or import crash is loud.
#>

$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\jackw\Desktop\42'
$daemon = Join-Path $repo 'automation\scripts\level_alert_daemon.py'
$logDir = Join-Path $repo 'automation\state\level-alert-daemon-logs'

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$logFile = Join-Path $logDir "daemon_$stamp.log"

# Use pythonw.exe so no console window flashes (matches sniper / orb pattern).
$pythonw = "$env:LOCALAPPDATA\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    # Fallback to whatever python is on PATH.
    $pythonw = 'pythonw.exe'
}

# Run for up to 6.75 hours; exit at 16:05 ET self-checked inside daemon.
$proc = Start-Process -FilePath $pythonw `
    -ArgumentList @($daemon, '--interval', '30', '--hours', '6.75') `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError "$logFile.err" `
    -WorkingDirectory $repo `
    -NoNewWindow `
    -PassThru

Write-Output "Gamma_LevelAlertDaemon launched PID=$($proc.Id) logFile=$logFile"
