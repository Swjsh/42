# Launch REGIME_SWITCHER pipeline silently (no console window).
#
# Two-stage flow:
#   1. If pre-pass cache (strategy_pnl_matrix.json) is missing, launch
#      regime_switcher_prepass (~3.5 hr wall-clock, sequential).
#   2. Otherwise launch regime_switcher_grinder Stage 1 (~30 min, parallel).
#
# Idempotent: detects an already-running job via PID file and exits.
#
# Run via Windows Task Scheduler or manually:
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup\scripts\launch-regime-switcher.ps1 [stage] [hours]
#
# Args:
#   stage:  'prepass' | 'grinder' | 'auto' (default 'auto' = prepass-if-missing then grinder)
#   hours:  grinder runtime hours (default 1)

param(
    [string]$Stage = 'auto',
    [string]$Hours = '1'
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython = Join-Path $repoRoot 'backtest\.venv\Scripts\python.exe'
$venvPythonW = Join-Path $repoRoot 'backtest\.venv\Scripts\pythonw.exe'
$logDir = Join-Path $repoRoot 'backtest\autoresearch\_state\regime_switcher_stage1'
$launchLog = Join-Path $logDir 'launch.log'
$matrixPath = Join-Path $logDir 'strategy_pnl_matrix.json'
$inputsPath = Join-Path $logDir 'regime_inputs.json'
$prepassPid = Join-Path $logDir 'prepass.pid'
$grinderPid = Join-Path $logDir 'runner.pid'

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

function Test-PidAlive {
    param([string]$PidFile)
    if (-not (Test-Path $PidFile)) { return $false }
    $existingPid = (Get-Content $PidFile -Raw).Trim()
    if ($existingPid -notmatch '^\d+$') { return $false }
    $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
    return ($null -ne $proc)
}

# Idempotent: skip if anything is alive
if (Test-PidAlive $prepassPid) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [SKIP] regime_switcher prepass PID alive" | Out-File -FilePath $launchLog -Append -Encoding utf8
    exit 0
}
if (Test-PidAlive $grinderPid) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [SKIP] regime_switcher grinder PID alive" | Out-File -FilePath $launchLog -Append -Encoding utf8
    exit 0
}

# Decide which stage to run
$wantedStage = $Stage.ToLower()
if ($wantedStage -eq 'auto') {
    if ((Test-Path $matrixPath) -and (Test-Path $inputsPath)) {
        $wantedStage = 'grinder'
    } else {
        $wantedStage = 'prepass'
    }
}

# Prefer pythonw to suppress console; fallback to python
$exe = if (Test-Path $venvPythonW) { $venvPythonW } else { $venvPython }
if (-not (Test-Path $exe)) {
    $exe = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $exe) {
        "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [ERROR] No python found" | Out-File -FilePath $launchLog -Append -Encoding utf8
        exit 1
    }
}

$workingDir = Join-Path $repoRoot 'backtest'

if ($wantedStage -eq 'prepass') {
    $args = '-m autoresearch.regime_switcher_prepass'
    $label = 'regime_switcher prepass'
} elseif ($wantedStage -eq 'grinder') {
    $args = "-m autoresearch.regime_switcher_grinder --hours $Hours --workers 4"
    $label = 'regime_switcher grinder'
} else {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [ERROR] unknown stage: $Stage" | Out-File -FilePath $launchLog -Append -Encoding utf8
    exit 1
}

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = $args
$startInfo.WorkingDirectory = $workingDir
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

$proc = [System.Diagnostics.Process]::Start($startInfo)
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [START] $label PID $($proc.Id) args=$args" | Out-File -FilePath $launchLog -Append -Encoding utf8
Write-Output "started $label PID $($proc.Id)"
exit 0
