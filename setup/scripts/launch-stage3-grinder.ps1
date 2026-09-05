# Launch stage-3 grinder (regime-robust scoring) silently. Idempotent via PID file.
$ErrorActionPreference = 'Stop'

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$pidFile = Join-Path $repoRoot 'backtest\autoresearch\_state\stage3_grinder\runner.pid'
$logDir = Join-Path $repoRoot 'backtest\autoresearch\_state\stage3_grinder'
$launchLog = Join-Path $logDir 'launch.log'

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

if (Test-Path $pidFile) {
    $existingPid = (Get-Content $pidFile -Raw).Trim()
    if ($existingPid -match '^\d+$') {
        $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($proc) {
            "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [SKIP] stage3 PID $existingPid alive" | Out-File -FilePath $launchLog -Append -Encoding utf8
            exit 0
        }
    }
}

# System pythonw.exe -- the venv's own pythonw.exe stub resolves to the CONSOLE python.exe
# and opens a terminal window per fire from this windowless parent (GOAL-SILENT-RIG R6a).
$sysPythonW = 'C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe'
$exe = $sysPythonW
$env:PYTHONPATH = Join-Path $repoRoot 'backtest\.venv\Lib\site-packages'
$env:VIRTUAL_ENV = Join-Path $repoRoot 'backtest\.venv'
$workingDir = Join-Path $repoRoot 'backtest'
$hours = if ($args.Count -gt 0) { $args[0] } else { '6' }

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = "-m autoresearch.stage3_grinder --hours $hours --workers 4 --top-seeds 10"
$startInfo.WorkingDirectory = $workingDir
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

$proc = [System.Diagnostics.Process]::Start($startInfo)
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [START] stage3 PID $($proc.Id) hours=$hours" | Out-File -FilePath $launchLog -Append -Encoding utf8
Write-Output "started stage3 PID $($proc.Id)"
exit 0
