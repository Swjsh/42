#requires -Version 5.1
<#
.SYNOPSIS
  Keepalive for the window-leak detector. Fires every 5 min via Gamma_WindowLeakDetectorKeepalive.
  Restarts the detector if its PID is dead. Silent if alive. OP-27 enforcement spine.
.DESCRIPTION
  The detector itself MUST run windowless (system pythonw via wscript wrapper).
  Its presence is what makes OP-27 L41 violations DETECTABLE in real time -- when J
  reports a visible window, we can grep window-leaks.jsonl for the offender.
#>
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_shared.ps1"

$projectRoot = $WorkDir
$pidFile = Join-Path $projectRoot "automation\state\window-leak-detector.pid"
$logFile = Join-Path $LogDir ("window-leak-detector-keepalive-" + (Get-Date -Format "yyyy-MM-dd") + ".log")
$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

function Test-DetectorAlive {
    if (-not (Test-Path $pidFile)) { return $false }
    try {
        $detectorPid = [int]((Get-Content $pidFile -Raw).Trim())
        $proc = Get-WmiObject Win32_Process -Filter "ProcessId=$detectorPid" -ErrorAction SilentlyContinue
        if ($proc -and $proc.CommandLine -like "*window-leak-detector*") { return $true }
        return $false
    } catch { return $false }
}

if (Test-DetectorAlive) {
    Add-Content -Path $logFile -Value "[$now] detector alive (pid=$(Get-Content $pidFile -Raw))"
    exit 0
}

# Dead -- restart via wscript + run_exe_hidden.vbs
Add-Content -Path $logFile -Value "[$now] detector DEAD -- restarting"
$vbs = Join-Path $projectRoot "setup\scripts\run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$detector = Join-Path $projectRoot "setup\scripts\window-leak-detector.py"

if (-not (Test-Path $sysPythonw)) {
    Add-Content -Path $logFile -Value "[$now] FATAL: system pythonw missing at $sysPythonw"
    exit 1
}

# PYTHONPATH for any future deps; detector itself is stdlib-only but be safe.
$env:PYTHONPATH = Join-Path $projectRoot "backtest\.venv\Lib\site-packages"
$env:VIRTUAL_ENV = Join-Path $projectRoot "backtest\.venv"

Start-Process -FilePath "wscript.exe" -ArgumentList @('//nologo', $vbs, $sysPythonw, $detector) -WindowStyle Hidden -WorkingDirectory $projectRoot
Start-Sleep -Seconds 2

if (Test-DetectorAlive) {
    Add-Content -Path $logFile -Value "[$now] restart OK (pid=$(Get-Content $pidFile -Raw))"
    exit 0
} else {
    Add-Content -Path $logFile -Value "[$now] restart FAILED -- detector did not write PID"
    exit 1
}
