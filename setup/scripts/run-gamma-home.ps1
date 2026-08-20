#requires -Version 5.1
# Gamma_Home runner -- regenerate THE command center page (analysis\home\index.html).
# ASCII-ONLY (PS 5.1 reads BOM-less files as Windows-1252; non-ASCII = silent parse death).
# Pure Python, ~1.3s, $0, no LLM, no orders. Reads state; writes exactly one HTML file.
#
# WHY A TASK AT ALL: the page must already be correct when J opens it. The .vbs
# launcher regenerates on open, but a scheduled refresh means the file on disk is
# fresh even when he opens it directly, from a shortcut, or on another screen.
[CmdletBinding()] param()
$ErrorActionPreference = "Stop"
$repo   = "C:\Users\jackw\Desktop\42"
$py     = Join-Path $repo "backtest\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }   # fail open to system python
$script = Join-Path $repo "setup\scripts\gamma_home.py"
$logDir = Join-Path $repo "automation\state\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$log = Join-Path $logDir ("gamma-home-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

# EAP=Continue while capturing: a native stderr line under redirection can abort the
# runner on the FIRST warning, and this script's warnings (NO DATA sources) must reach
# the log rather than kill the logger. UTF-8 append, not PS 5.1's default UTF-16LE.
$ErrorActionPreference = "Continue"
$out = & $py $script 2>&1 | Out-String
$rc = $LASTEXITCODE
$ErrorActionPreference = "Stop"
Add-Content -Path $log -Value (("[" + (Get-Date -Format "HH:mm:ss") + "] ") + $out) -Encoding UTF8
if ($rc -ne 0) {
    Add-Content -Path $log -Value ("[run-gamma-home] NONZERO EXIT " + $rc) -Encoding UTF8
}
exit $rc
