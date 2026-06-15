# EOD Deep-Dive runner — fires at 16:05 ET (post-EodSummary).
# Pure Python pipeline, no LLM in loop, ~1 sec runtime.
#
# Phase 1: runs from journal+state files only (no MCP injection).
# Phase 2: will read snapshot files written by EodSummary that include
#          today's Alpaca orders + TV chart state.

$ErrorActionPreference = "Continue"

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython = Join-Path $repoRoot "backtest\.venv\Scripts\python.exe"
$logDir = Join-Path $repoRoot "automation\state"
$logFile = Join-Path $logDir "eod-deep-dive.log"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$exe = if (Test-Path $venvPython) { $venvPython } else { (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $exe) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [ERROR] No python found" | Out-File -FilePath $logFile -Append -Encoding utf8
    exit 1
}

# Use ET date — pull from Python because PS lacks tz-aware shortcuts
$today = (Get-Date).ToString("yyyy-MM-dd")
$workingDir = Join-Path $repoRoot "backtest"

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [START] eod-deep-dive for date=$today" | Out-File -FilePath $logFile -Append -Encoding utf8

# Use Start-Process to capture stdout/stderr (T71 pattern)
$stdoutLog = Join-Path $logDir "eod-deep-dive.stdout.log"
$stderrLog = Join-Path $logDir "eod-deep-dive.stderr.log"

$proc = Start-Process -FilePath $exe `
    -ArgumentList @("-m", "autoresearch.eod_deep.main", "--date", $today, "--rerun") `
    -WorkingDirectory $workingDir `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -NoNewWindow `
    -PassThru `
    -Wait

$exitCode = $proc.ExitCode
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [DONE]  eod-deep-dive exit=$exitCode" | Out-File -FilePath $logFile -Append -Encoding utf8
exit $exitCode
