# Launch SNIPER full pipeline orchestrator (Stage 1 → 2 → 3+4+5).
# Long-running (~3-5 hours total). Idempotent via pipeline.pid.

$ErrorActionPreference = 'Stop'

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython = Join-Path $repoRoot 'backtest\.venv\Scripts\python.exe'
$venvPythonW = Join-Path $repoRoot 'backtest\.venv\Scripts\pythonw.exe'
$pidFile = Join-Path $repoRoot 'backtest\autoresearch\_state\sniper_pipeline\pipeline.pid'
$logDir = Join-Path $repoRoot 'backtest\autoresearch\_state\sniper_pipeline'
$launchLog = Join-Path $logDir 'launch.log'

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

if (Test-Path $pidFile) {
    $existingPid = (Get-Content $pidFile -Raw).Trim()
    if ($existingPid -match '^\d+$') {
        $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($proc) {
            "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [SKIP] pipeline PID $existingPid still alive" | Out-File -FilePath $launchLog -Append -Encoding utf8
            exit 0
        }
    }
}

$exe = if (Test-Path $venvPythonW) { $venvPythonW } elseif (Test-Path $venvPython) { $venvPython } else { (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $exe) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [ERROR] No python found" | Out-File -FilePath $launchLog -Append -Encoding utf8
    exit 1
}

$workingDir = Join-Path $repoRoot 'backtest'

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = "-m autoresearch.sniper_pipeline --max-wait-hours 6 --stage2-hours 2"
$startInfo.WorkingDirectory = $workingDir
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

$proc = [System.Diagnostics.Process]::Start($startInfo)
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [START] pipeline PID $($proc.Id)" | Out-File -FilePath $launchLog -Append -Encoding utf8
Write-Output "started PID $($proc.Id)"
exit 0
