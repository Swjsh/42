# Launch VWAP_REJECTION_PRIME Stage 1 grinder silently (no console window).
# Idempotent: detects an already-running grinder via PID file and exits.
#
# Run via Windows Task Scheduler or manually:
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup\scripts\launch-vwap-stage1.ps1 [hours]

$ErrorActionPreference = 'Stop'

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$pidFile = Join-Path $repoRoot 'backtest\autoresearch\_state\vwap_stage1\runner.pid'
$logDir = Join-Path $repoRoot 'backtest\autoresearch\_state\vwap_stage1'
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
            "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [SKIP] vwap grinder PID $existingPid still alive" | Out-File -FilePath $launchLog -Append -Encoding utf8
            exit 0
        }
    }
}

# System pythonw.exe -- the venv's own pythonw.exe stub resolves to the CONSOLE python.exe
# and opens a terminal window per fire from this windowless parent (GOAL-SILENT-RIG R6a).
$sysPythonW = 'C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe'
$exe = $sysPythonW
if (-not (Test-Path $exe)) {
    # Final fallback: system python on PATH
    $exe = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $exe) {
        "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [ERROR] No python found" | Out-File -FilePath $launchLog -Append -Encoding utf8
        exit 1
    }
}
$env:PYTHONPATH = Join-Path $repoRoot 'backtest\.venv\Lib\site-packages'
$env:VIRTUAL_ENV = Join-Path $repoRoot 'backtest\.venv'

$workingDir = Join-Path $repoRoot 'backtest'
$hours = if ($args.Count -gt 0) { $args[0] } else { '2' }

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = "-m autoresearch.vwap_overnight_grinder --hours $hours --workers 4"
$startInfo.WorkingDirectory = $workingDir
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

$proc = [System.Diagnostics.Process]::Start($startInfo)
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [START] vwap grinder PID $($proc.Id) hours=$hours" | Out-File -FilePath $launchLog -Append -Encoding utf8
Write-Output "started PID $($proc.Id)"
exit 0
