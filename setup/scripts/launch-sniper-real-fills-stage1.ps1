# Launch SNIPER_LEVEL_BREAK REAL-FILLS Stage 1 grinder silently (no console window).
# Idempotent: detects an already-running grinder via PID file and exits.
#
# This is the T42-full real-fills variant — same launcher contract as
# launch-sniper-stage1.ps1 but targets sniper_real_fills_grinder + writes
# state to autoresearch/_state/sniper_real_fills_stage1/.
#
# Run via Windows Task Scheduler or manually:
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup\scripts\launch-sniper-real-fills-stage1.ps1 [hours]

$ErrorActionPreference = 'Stop'

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython = Join-Path $repoRoot 'backtest\.venv\Scripts\python.exe'
$venvPythonW = Join-Path $repoRoot 'backtest\.venv\Scripts\pythonw.exe'
$pidFile = Join-Path $repoRoot 'backtest\autoresearch\_state\sniper_real_fills_stage1\runner.pid'
$logDir = Join-Path $repoRoot 'backtest\autoresearch\_state\sniper_real_fills_stage1'
$launchLog = Join-Path $logDir 'launch.log'

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# Idempotent: already running?
if (Test-Path $pidFile) {
    $existingPid = (Get-Content $pidFile -Raw).Trim()
    if ($existingPid -match '^\d+$') {
        # Per CLAUDE.md OP 25 foot-gun: Get-Process can miss pythonw — use WMI for ground truth.
        $proc = Get-WmiObject Win32_Process -Filter "ProcessId = $existingPid" -ErrorAction SilentlyContinue
        if ($proc) {
            "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [SKIP] sniper-real-fills grinder PID $existingPid still alive (WMI-confirmed)" | Out-File -FilePath $launchLog -Append -Encoding utf8
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
$hours = if ($args.Count -gt 0) { $args[0] } else { '8' }

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = "-m autoresearch.sniper_real_fills_grinder --hours $hours --workers 4"
$startInfo.WorkingDirectory = $workingDir
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

$proc = [System.Diagnostics.Process]::Start($startInfo)
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [START] sniper-real-fills grinder PID $($proc.Id) hours=$hours" | Out-File -FilePath $launchLog -Append -Encoding utf8
Write-Output "started PID $($proc.Id)"
exit 0
