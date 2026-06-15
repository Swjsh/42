# Launch OPENING_DRIVE_FADE Stage 1 grinder silently (no console window).
# Idempotent: detects an already-running grinder via PID file and exits.
#
# Run via Windows Task Scheduler or manually:
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup\scripts\launch-odf-stage1.ps1 [hours]

$ErrorActionPreference = 'Stop'

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython = Join-Path $repoRoot 'backtest\.venv\Scripts\python.exe'
$venvPythonW = Join-Path $repoRoot 'backtest\.venv\Scripts\pythonw.exe'
$pidFile = Join-Path $repoRoot 'backtest\autoresearch\_state\opening_drive_fade_stage1\runner.pid'
$logDir = Join-Path $repoRoot 'backtest\autoresearch\_state\opening_drive_fade_stage1'
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
            "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [SKIP] ODF grinder PID $existingPid still alive" | Out-File -FilePath $launchLog -Append -Encoding utf8
            exit 0
        }
    }
}

# Prefer pythonw to suppress console; fallback to python if pythonw absent.
$exe = if (Test-Path $venvPythonW) { $venvPythonW } else { $venvPython }
if (-not (Test-Path $exe)) {
    # Final fallback: system python
    $exe = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $exe) {
        "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [ERROR] No python found" | Out-File -FilePath $launchLog -Append -Encoding utf8
        exit 1
    }
}

$workingDir = Join-Path $repoRoot 'backtest'
$hours = if ($args.Count -gt 0) { $args[0] } else { '2' }

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = "-m autoresearch.opening_drive_fade_grinder --hours $hours --workers 4"
$startInfo.WorkingDirectory = $workingDir
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

$proc = [System.Diagnostics.Process]::Start($startInfo)
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [START] ODF grinder PID $($proc.Id) hours=$hours" | Out-File -FilePath $launchLog -Append -Encoding utf8
Write-Output "started PID $($proc.Id)"
exit 0
