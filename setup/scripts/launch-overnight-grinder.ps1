# Launch overnight grinder silently (no console window).
# Idempotent: detects an already-running grinder via PID file and exits.
#
# Run via Windows Task Scheduler or manually:
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup\scripts\launch-overnight-grinder.ps1

$ErrorActionPreference = 'Stop'

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython = Join-Path $repoRoot 'backtest\.venv\Scripts\python.exe'
$venvPythonW = Join-Path $repoRoot 'backtest\.venv\Scripts\pythonw.exe'
$pidFile = Join-Path $repoRoot 'backtest\autoresearch\_state\overnight_grinder\runner.pid'
$logDir = Join-Path $repoRoot 'backtest\autoresearch\_state\overnight_grinder'
$launchLog = Join-Path $logDir 'launch.log'

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# Idempotent: already running?
if (Test-Path $pidFile) {
    $existingPid = (Get-Content $pidFile -Raw).Trim()
    if ($existingPid -match '^\d+$') {
        $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($proc) {
            "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [SKIP] grinder PID $existingPid still alive" | Out-File -FilePath $launchLog -Append -Encoding utf8
            exit 0
        }
    }
}

# Pick pythonw.exe to avoid console flash; fallback to python.exe if missing.
$exe = if (Test-Path $venvPythonW) { $venvPythonW } else { $venvPython }
if (-not (Test-Path $exe)) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [ERROR] No python found at $venvPython or $venvPythonW" | Out-File -FilePath $launchLog -Append -Encoding utf8
    exit 1
}

# Working dir = backtest/ so module path is autoresearch.overnight_grinder
$workingDir = Join-Path $repoRoot 'backtest'

# 8h overnight default. Caller can pass -hours 4 etc to override.
$hours = if ($args.Count -gt 0) { $args[0] } else { '8' }

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = "-m autoresearch.overnight_grinder --hours $hours --workers 4"
$startInfo.WorkingDirectory = $workingDir
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardOutput = $false
$startInfo.RedirectStandardError = $false
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

$proc = [System.Diagnostics.Process]::Start($startInfo)
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [START] grinder PID $($proc.Id) hours=$hours" | Out-File -FilePath $launchLog -Append -Encoding utf8
Write-Output "started PID $($proc.Id)"
exit 0
