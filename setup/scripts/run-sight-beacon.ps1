$ErrorActionPreference = 'Stop'
# Gamma_SightBeacon wrapper -- the NEVER-BLIND eye. Runs sight_beacon.py every 1 min
# across the trading day. PURE PYTHON / REST (Alpaca data API + yfinance) -- NO MCP, NO
# CDP, NO Claude pool, so it cannot be blocked the way the heartbeat's TV/Alpaca MCP can,
# and it never touches the Max rate-limit pool. Writes automation/state/sight-beacon.json
# which the heartbeat reads as its Layer-1b fallback. Hidden process (no window flash).
$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython  = Join-Path $repoRoot 'backtest\.venv\Scripts\python.exe'
$venvPythonW = Join-Path $repoRoot 'backtest\.venv\Scripts\pythonw.exe'
$exe = if (Test-Path $venvPythonW) { $venvPythonW } else { $venvPython }
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = "`"$repoRoot\setup\scripts\sight_beacon.py`""
$startInfo.WorkingDirectory = $repoRoot
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$proc = [System.Diagnostics.Process]::Start($startInfo)
$proc.WaitForExit(60000) | Out-Null
exit $proc.ExitCode
