#requires -Version 5.1
<#
.SYNOPSIS
  Keepalive for the crypto live grinder. Fires every 5 min via Gamma_CryptoGrinderKeepalive.
  If a grinder process is already running, exits silently. Otherwise launches a fresh one
  with a 12-hour duration. Self-healing.

.DESCRIPTION
  Detects via Get-WmiObject Win32_Process (per L27 lesson -- Get-Process misses pythonw).
  Filters CommandLine for `live_grinder.py`. If none alive, restart.
#>
$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\jackw\Desktop\42"
Set-Location $projectRoot

$logDir = Join-Path $projectRoot "automation\state\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir ("crypto-grinder-keepalive-" + (Get-Date -Format "yyyy-MM-dd") + ".log")
$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# Check for existing grinder process (use WMI per L27 -- pythonw invisible to Get-Process)
$existing = Get-WmiObject Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='python3.13.exe' OR Name='pythonw3.13.exe'" |
    Where-Object { $_.CommandLine -like '*live_grinder*' }

if ($existing) {
    Add-Content -Path $logFile -Value "[$now] grinder-keepalive: alive (PID=$($existing.ProcessId | Out-String -NoNewline))"
    exit 0
}

# Not running -- launch a fresh one with 12-hour duration.
# OP-27 L41 layer 4: MUST use SYSTEM pythonw (true GUI subsystem) with PYTHONPATH wiring.
# venv\Scripts\pythonw.exe is a console-subsystem STUB that re-execs as system python.exe,
# which Windows 11 default-terminal grabs and shows as a WindowsTerminal -Embedding window.
# Detector confirmed this leak 2026-05-17 evening (6 WT instances during 3x stress-test).
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $sysPythonw)) {
    Add-Content -Path $logFile -Value "[$now] grinder-keepalive: FATAL system pythonw missing at $sysPythonw"
    exit 1
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $sysPythonw
$psi.Arguments = "crypto\benchmarks\live_grinder.py --interval 120 --duration 43200 --symbol BTC-USD --granularity 300"
$psi.WorkingDirectory = $projectRoot
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $true
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
# venv site-packages so live_grinder can import pandas/numpy/yfinance without venv stub.
$venvSite = Join-Path $projectRoot "backtest\.venv\Lib\site-packages"
if (Test-Path $venvSite) {
    $psi.EnvironmentVariables["PYTHONPATH"] = $venvSite
    $psi.EnvironmentVariables["VIRTUAL_ENV"] = Join-Path $projectRoot "backtest\.venv"
}

$proc = [System.Diagnostics.Process]::Start($psi)
Add-Content -Path $logFile -Value "[$now] grinder-keepalive: launched PID=$($proc.Id) (system pythonw, venv PYTHONPATH) duration=12h interval=2m"
exit 0
