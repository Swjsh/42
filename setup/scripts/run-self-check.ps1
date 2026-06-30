#requires -Version 5.1
# Gamma_SelfCheck runner -- Gamma verifies ITSELF every 30 min and alerts J (STATUS.md +
# Discord) on DEGRADED/BROKEN, so J never has to ask "is it still running / did it crash?".
# ASCII-ONLY (the exact class this whole feature exists to kill). backtest .venv (reaper-exempt).
[CmdletBinding()] param()
$ErrorActionPreference = "Stop"
$repo = "C:\Users\jackw\Desktop\42"
$py   = Join-Path $repo "backtest\.venv\Scripts\python.exe"
$logDir = Join-Path $repo "automation\state\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$log = Join-Path $logDir ("self-check-" + (Get-Date -Format "yyyy-MM-dd") + ".log")
& $py (Join-Path $repo "setup\scripts\self_check.py") *>> $log
