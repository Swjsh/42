#requires -Version 5.1
<#
.SYNOPSIS
  Gamma Swarm Pre-Market Hypothesis Engine -- fires at 06:00 ET weekdays.

.DESCRIPTION
  Runs automation/swarm/runner.py which orchestrates 6 specialist agents
  (technical, macro, level_thesis, internals, validator, synthesis).
  Produces automation/swarm/state/swarm_output.json by ~06:10 ET.
  Consumed by premarket.md Step 1c at 08:30 ET as advisory context.

  Zero impact if it fails -- premarket Step 1c skips gracefully when
  swarm_output.json is missing or stale.
#>

. "$PSScriptRoot\_shared.ps1"

$ErrorActionPreference = "Continue"
$task = "swarm-premarket"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) {
    Write-TaskLog -TaskName $task -Message "SKIP weekend"
    exit 0
}

if (Test-HolidayFromAlpaca) {
    Write-TaskLog -TaskName $task -Message "SKIP holiday"
    exit 0
}

$logDir = Join-Path $WorkDir "automation\state\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir ("swarm-premarket-" + $et.ToString("yyyy-MM-dd") + ".log")
$now = $et.ToString("yyyy-MM-dd HH:mm:ss")

function Write-Log {
    param([string]$Msg)
    $ts = (Get-EtNow).ToString("HH:mm:ss")
    $line = "[$ts ET] $Msg"
    Add-Content -Path $logFile -Value $line
    Write-Host $line
}

Write-Log "SWARM_START"

# Use the backtest venv Python (has all required packages)
$pyExe = Join-Path $WorkDir "backtest\.venv\Scripts\python.exe"
if (-not (Test-Path $pyExe)) {
    # Fallback to system Python
    $pyExe = "python"
    Write-Log "WARNING: backtest venv not found, using system python"
}

$runnerScript = Join-Path $WorkDir "automation\swarm\runner.py"
if (-not (Test-Path $runnerScript)) {
    Write-Log "ERROR: runner.py not found at $runnerScript"
    exit 1
}

# Run the swarm orchestrator (timeout: 15 min — generous for 4 parallel agents + synthesis)
$startTime = Get-Date
$proc = Start-Process `
    -FilePath $pyExe `
    -ArgumentList "`"$runnerScript`"" `
    -WorkingDirectory $WorkDir `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError ($logFile -replace "\.log$", "-err.log") `
    -PassThru `
    -NoNewWindow

$timeoutMs = 15 * 60 * 1000
$completed = $proc.WaitForExit($timeoutMs)

if (-not $completed) {
    $proc.Kill()
    Write-Log "ERROR: runner.py TIMEOUT after 15min -- killed"
    exit 1
}

$elapsedSec = [math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)
$exitCode = $proc.ExitCode

if ($exitCode -eq 0) {
    # Validate swarm_output.json was produced
    $outputPath = Join-Path $WorkDir "automation\swarm\state\swarm_output.json"
    if (Test-Path $outputPath) {
        try {
            $swarm = Get-Content $outputPath -Raw | ConvertFrom-Json
            $bias = $swarm.consensus_bias
            $confidence = $swarm.swarm_confidence
            Write-Log "SWARM_OK: bias=$bias confidence=$confidence elapsed=${elapsedSec}s"
        } catch {
            Write-Log "SWARM_WARN: output.json exists but invalid JSON elapsed=${elapsedSec}s"
        }
    } else {
        Write-Log "SWARM_WARN: runner.py exited 0 but swarm_output.json missing elapsed=${elapsedSec}s"
    }
} else {
    Write-Log "SWARM_FAIL: exit=$exitCode elapsed=${elapsedSec}s"
}

exit $exitCode
