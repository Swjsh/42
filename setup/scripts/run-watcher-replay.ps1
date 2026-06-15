$ErrorActionPreference = 'Continue'
$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython = Join-Path $repoRoot 'backtest\.venv\Scripts\python.exe'
$venvPythonW = Join-Path $repoRoot 'backtest\.venv\Scripts\pythonw.exe'
$exe = if (Test-Path $venvPythonW) { $venvPythonW } else { $venvPython }
$workingDir = Join-Path $repoRoot 'backtest'

# Replay last 30 days (catches up + fills observation history daily)
$end = (Get-Date).ToString('yyyy-MM-dd')
$start = (Get-Date).AddDays(-30).ToString('yyyy-MM-dd')

# Run replay then grader
$args = "-m autoresearch.watcher_replay --start $start --end $end"
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = $args
$startInfo.WorkingDirectory = $workingDir
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$proc = [System.Diagnostics.Process]::Start($startInfo)
$proc.WaitForExit(600000) | Out-Null

# Then grade
$startInfo2 = New-Object System.Diagnostics.ProcessStartInfo
$startInfo2.FileName = $exe
$startInfo2.Arguments = '-m autoresearch.watcher_grader'
$startInfo2.WorkingDirectory = $workingDir
$startInfo2.UseShellExecute = $false
$startInfo2.CreateNoWindow = $true
$startInfo2.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$proc2 = [System.Diagnostics.Process]::Start($startInfo2)
$proc2.WaitForExit(120000) | Out-Null
exit 0
