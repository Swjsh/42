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
# UTF-8 log fix (2026-08-03 LANE-4 audit): PS 5.1 file redirects (>> / *>>) write UTF-16LE,
# which made every level-refresh log unreadable to grep/tail tooling (each char NUL-padded).
# Capture streams with EAP=Continue (EAP=Stop + native stderr under redirection can abort
# the runner on the FIRST stderr line - the refresh's own failure output must reach the log,
# not kill the logger), then append as real UTF-8.
$ErrorActionPreference = "Continue"
$out = & $py $script 2>&1 | Out-String
$rc = $LASTEXITCODE
$ErrorActionPreference = "Stop"
Add-Content -Path $log -Value $out -Encoding UTF8
if ($rc -ne 0) {
    Add-Content -Path $log -Value ("[run-level-refresh] NONZERO EXIT " + $rc + " at " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) -Encoding UTF8
}
exit $rc
