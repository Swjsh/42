# Launch v14_enhanced Stage 1 grinder silently.
# Idempotent: detects an already-running grinder via PID file and exits.
#
# T71 (Fire #24 2026-05-14): redirects pythonw stderr + stdout to log files via
# Start-Process -RedirectStandardError/-RedirectStandardOutput. pythonw is GUI
# subsystem (no console) so without explicit redirection any silent-kill stack
# trace vanishes. With redirection, even pythonw writes a final traceback to
# the stderr file before being OOM-killed (best effort; OOM may also lose the
# trailing bytes, but we get MUCH more than before).
# See docs/T39-V14E-GRINDER-SILENT-DEATH-2026-05-14.md

$ErrorActionPreference = 'Stop'

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython = Join-Path $repoRoot 'backtest\.venv\Scripts\python.exe'
$venvPythonW = Join-Path $repoRoot 'backtest\.venv\Scripts\pythonw.exe'
$pidFile = Join-Path $repoRoot 'backtest\autoresearch\_state\v14_enhanced_stage1\runner.pid'
$logDir = Join-Path $repoRoot 'backtest\autoresearch\_state\v14_enhanced_stage1'
$launchLog = Join-Path $logDir 'launch.log'
$stdoutLog = Join-Path $logDir 'pythonw.stdout.log'
$stderrLog = Join-Path $logDir 'pythonw.stderr.log'

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

if (Test-Path $pidFile) {
    $existingPid = (Get-Content $pidFile -Raw).Trim()
    if ($existingPid -match '^\d+$') {
        $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($proc) {
            "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [SKIP] v14_enhanced grinder PID $existingPid still alive" | Out-File -FilePath $launchLog -Append -Encoding utf8
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
$hours = if ($args.Count -gt 0) { $args[0] } else { '2' }

# Rotate stdout/stderr logs on each launch so we keep the most recent crash trail
# (don't append forever; each grinder run gets fresh logs).
if (Test-Path $stdoutLog) {
    $rotated = $stdoutLog -replace '\.log$', ('.{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Move-Item -Path $stdoutLog -Destination $rotated -Force -ErrorAction SilentlyContinue
}
if (Test-Path $stderrLog) {
    $rotated = $stderrLog -replace '\.log$', ('.{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Move-Item -Path $stderrLog -Destination $rotated -Force -ErrorAction SilentlyContinue
}

# Start-Process supports -RedirectStandardError/-RedirectStandardOutput, which
# is exactly what we need to capture pythonw output. -PassThru returns the
# Process object so we can grab its PID.
$startArgs = @{
    FilePath = $exe
    ArgumentList = @('-m', 'autoresearch.v14_enhanced_grinder', '--hours', $hours, '--workers', '4')
    WorkingDirectory = $workingDir
    RedirectStandardOutput = $stdoutLog
    RedirectStandardError = $stderrLog
    NoNewWindow = $true
    PassThru = $true
}

$proc = Start-Process @startArgs
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [START] v14_enhanced grinder PID $($proc.Id) hours=$hours stdout=$stdoutLog stderr=$stderrLog" | Out-File -FilePath $launchLog -Append -Encoding utf8
Write-Output "started PID $($proc.Id)"
exit 0
