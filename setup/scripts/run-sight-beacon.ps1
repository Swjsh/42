$ErrorActionPreference = 'Stop'
# Gamma_SightBeacon wrapper -- the NEVER-BLIND eye. Runs sight_beacon.py every 1 min
# across the trading day. PURE PYTHON / REST (Alpaca data API + yfinance) -- NO MCP, NO
# CDP, NO Claude pool, so it cannot be blocked the way the heartbeat's TV/Alpaca MCP can,
# and it never touches the Max rate-limit pool. Writes automation/state/sight-beacon.json
# which the heartbeat reads as its Layer-1b fallback. Hidden process (no window flash).
$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
# L41 (2026-05-17 lesson, LESSONS-LEARNED.md): the VENV's OWN pythonw.exe/python.exe is a
# stub that re-execs into the system interpreter via a hardcoded CREATE_NEW_CONSOLE,
# ignoring whatever CreateNoWindow the caller set -- always launch the SYSTEM interpreter
# with PYTHONPATH/VIRTUAL_ENV pointed at the venv instead (same pattern as _shared.ps1's
# Invoke-PythonHidden). Root-caused 2026-07-03: this exact violation flashed a visible
# WindowsTerminal window every ~1 min, all day, market hours -- J's "cmd popups".
$sysPythonW = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$venvSite = Join-Path $repoRoot 'backtest\.venv\Lib\site-packages'
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $sysPythonW
$startInfo.Arguments = "`"$repoRoot\setup\scripts\sight_beacon.py`""
$startInfo.WorkingDirectory = $repoRoot
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
if (Test-Path $venvSite) {
    $startInfo.EnvironmentVariables["PYTHONPATH"] = $venvSite
    $startInfo.EnvironmentVariables["VIRTUAL_ENV"] = (Join-Path $repoRoot 'backtest\.venv')
}
$proc = [System.Diagnostics.Process]::Start($startInfo)
$proc.WaitForExit(60000) | Out-Null
exit $proc.ExitCode
