#requires -Version 5.1
# Gamma_LevelRefresh runner -- keep the engine's key levels LIVE during RTH.
# ASCII-ONLY (PS 5.1 reads BOM-less files as Windows-1252; non-ASCII = silent parse death).
# Calls refresh_levels_intraday.py via the backtest venv (reaper-exempt). $0, no orders.
[CmdletBinding()] param()
$ErrorActionPreference = "Stop"
$repo = "C:\Users\jackw\Desktop\42"
$py   = Join-Path $repo "backtest\.venv\Scripts\python.exe"
$script = Join-Path $repo "setup\scripts\refresh_levels_intraday.py"
$logDir = Join-Path $repo "automation\state\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$log = Join-Path $logDir ("level-refresh-" + (Get-Date -Format "yyyy-MM-dd") + ".log")
& $py $script *>> $log
