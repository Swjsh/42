$ErrorActionPreference = 'Stop'
$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython = Join-Path $repoRoot 'backtest\.venv\Scripts\python.exe'
$venvPythonW = Join-Path $repoRoot 'backtest\.venv\Scripts\pythonw.exe'
$pidFile = Join-Path $repoRoot 'backtest\autoresearch\_state\bullish_grinder\runner.pid'
$logDir = Join-Path $repoRoot 'backtest\autoresearch\_state\bullish_grinder'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
if (Test-Path $pidFile) {
    $existingPid = (Get-Content $pidFile -Raw).Trim()
    if ($existingPid -match '^\d+$' -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) { exit 0 }
}
$exe = if (Test-Path $venvPythonW) { $venvPythonW } else { $venvPython }
$workingDir = Join-Path $repoRoot 'backtest'
$hours = if ($args.Count -gt 0) { $args[0] } else { '4' }
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = "-m autoresearch.bullish_grinder --hours $hours --workers 4"
$startInfo.WorkingDirectory = $workingDir
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$proc = [System.Diagnostics.Process]::Start($startInfo)
Write-Output "started bullish PID $($proc.Id)"
exit 0
