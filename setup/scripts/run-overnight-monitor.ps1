# Hourly check-in for the overnight grinder.
# Verifies the grinder is alive; if dead before deadline, restarts it.
# Logs heartbeat to backtest/autoresearch/_state/overnight_grinder/monitor.jsonl
#
# Run via Windows Task Scheduler hourly trigger.

$ErrorActionPreference = 'Stop'

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython = Join-Path $repoRoot 'backtest\.venv\Scripts\python.exe'
$workingDir = Join-Path $repoRoot 'backtest'

# pythonw.exe gives no console for the monitor too
$venvPythonW = Join-Path $repoRoot 'backtest\.venv\Scripts\pythonw.exe'
$exe = if (Test-Path $venvPythonW) { $venvPythonW } else { $venvPython }

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = '-m autoresearch.overnight_monitor'
$startInfo.WorkingDirectory = $workingDir
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

$proc = [System.Diagnostics.Process]::Start($startInfo)
$proc.WaitForExit(60000) | Out-Null
exit $proc.ExitCode
