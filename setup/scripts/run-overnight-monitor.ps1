# Hourly check-in for the overnight grinder.
# Verifies the grinder is alive; if dead before deadline, restarts it.
# Logs heartbeat to backtest/autoresearch/_state/overnight_grinder/monitor.jsonl
#
# Run via Windows Task Scheduler hourly trigger.

$ErrorActionPreference = 'Stop'

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$workingDir = Join-Path $repoRoot 'backtest'

# system pythonw.exe -- the venv's own pythonw.exe stub resolves to the CONSOLE python.exe
# and opens a terminal window per fire from this windowless parent (GOAL-SILENT-RIG R6a).
$sysPythonW = 'C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe'
if (-not (Test-Path $sysPythonW)) { throw "system pythonw.exe not found at $sysPythonW" }
$exe = $sysPythonW
$env:PYTHONPATH = Join-Path $repoRoot 'backtest\.venv\Lib\site-packages'
$env:VIRTUAL_ENV = Join-Path $repoRoot 'backtest\.venv'

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
