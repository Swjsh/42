# Launch stage-2 grinder silently. Idempotent via PID file.
$ErrorActionPreference = 'Stop'

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython = Join-Path $repoRoot 'backtest\.venv\Scripts\python.exe'
$venvPythonW = Join-Path $repoRoot 'backtest\.venv\Scripts\pythonw.exe'
$pidFile = Join-Path $repoRoot 'backtest\autoresearch\_state\stage2_grinder\runner.pid'
$logDir = Join-Path $repoRoot 'backtest\autoresearch\_state\stage2_grinder'
$launchLog = Join-Path $logDir 'launch.log'

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

if (Test-Path $pidFile) {
    $existingPid = (Get-Content $pidFile -Raw).Trim()
    if ($existingPid -match '^\d+$') {
        $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($proc) {
            "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [SKIP] stage2 PID $existingPid alive" | Out-File -FilePath $launchLog -Append -Encoding utf8
            exit 0
        }
    }
}

$exe = if (Test-Path $venvPythonW) { $venvPythonW } else { $venvPython }
if (-not (Test-Path $exe)) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [ERROR] No python found" | Out-File -FilePath $launchLog -Append -Encoding utf8
    exit 1
}

$workingDir = Join-Path $repoRoot 'backtest'
$hours = if ($args.Count -gt 0) { $args[0] } else { '4' }

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = "-m autoresearch.stage2_grinder --hours $hours --workers 4 --top-seeds 5"
$startInfo.WorkingDirectory = $workingDir
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

$proc = [System.Diagnostics.Process]::Start($startInfo)
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [START] stage2 PID $($proc.Id) hours=$hours" | Out-File -FilePath $launchLog -Append -Encoding utf8
Write-Output "started stage2 PID $($proc.Id)"
exit 0
