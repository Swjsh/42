#requires -Version 5.1
<#
.SYNOPSIS
  Pattern Gym Overnight -- nightly chart-pattern detector regression.

.DESCRIPTION
  Fires from Gamma_PatternGymOvernight task once nightly (post-EOD).
  Replays the last 5 trading days through pattern_backtest, writes scorecards
  to analysis/pattern-gym-history.jsonl + analysis/pattern-gym-latest.json,
  drift-detects rolling-7-day WR vs 16-mo baseline.

  Pure Python execution. Zero LLM cost. Python spawned via Invoke-PythonHidden
  (CREATE_NO_WINDOW) per OP-27 L41 — bare `python script.py` leaks conhost
  windows on WT-default Win11.
#>

$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_shared.ps1"

$projectRoot = $WorkDir
Set-Location $projectRoot

$logFile = Join-Path $LogDir ("pattern-gym-" + (Get-Date -Format "yyyy-MM-dd") + ".log")
$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Add-Content -Path $logFile -Value "[$now] pattern-gym-overnight: starting"

# Run the gym replay (5 trading days back)
$gym = Invoke-PythonHidden -ScriptPath "backtest\autoresearch\pattern_gym_overnight.py" -ArgList @("--days", "5") -TaskName "pattern-gym-overnight" -TimeoutSec 600
$gymExit = $gym.ExitCode
Add-Content -Path $logFile -Value ("[$now] gym exit=$gymExit log=" + $gym.LogFile)

# Surface drift to STATUS.md if drift_detected = true
$latestJson = Join-Path $projectRoot "analysis\pattern-gym-latest.json"
if (Test-Path $latestJson) {
    try {
        $snap = Get-Content $latestJson -Raw | ConvertFrom-Json
        if ($snap.drift.drift_detected) {
            $statusPath = Join-Path $projectRoot "automation\overnight\STATUS.md"
            $entry = "- [$now] AMBER: pattern_gym drift -- " + (($snap.drift.alerts | ForEach-Object { "$($_.detector) $($_.delta_pp)pp" }) -join ", ")
            if (Test-Path $statusPath) {
                Add-Content -Path $statusPath -Value $entry
                Add-Content -Path $logFile -Value "[$now] drift surfaced to STATUS.md"
            }
        }
    } catch {
        Add-Content -Path $logFile -Value "[$now] drift parse failed: $_"
    }
}

Add-Content -Path $logFile -Value "[$now] pattern-gym-overnight: done"
exit 0
