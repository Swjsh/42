#requires -Version 5.1
<#
.SYNOPSIS
  Daily gym session — unified chart-reading audit scorecard for the SPY engine.

.DESCRIPTION
  Fires from Gamma_GymSession task at 17:00 ET weekdays (between Analyst 16:45 and
  Manager 17:30). Manager consumes the scorecard for the daily brief.

  Aggregates: crypto-gym (53 validators) + chart-data-verify + heartbeat-tick-audit
  + pin-chain-verify + heartbeat-mcp-self-test + heartbeat-pulse-check
  + watcher-state-inspector → ONE GREEN/YELLOW/RED scorecard.

  Pure Python execution. Zero LLM cost. Window-leak-safe per OP-27 L42.
#>

$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_shared.ps1"

$projectRoot = $WorkDir
Set-Location $projectRoot

$dateStr = (Get-Date).ToString("yyyy-MM-dd")
$logFile = Join-Path $LogDir ("gym-session-" + $dateStr + ".log")
$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Add-Content -Path $logFile -Value "[$now] gym-session: starting for $dateStr"

# Run the orchestrator (re-runs stale audits, aggregates verdicts, writes scorecard)
$session = Invoke-PythonHidden `
    -ScriptPath "backtest\autoresearch\gym_session.py" `
    -ArgList @("--date", $dateStr, "--stale-hours", "2.0") `
    -TaskName "gym-session" `
    -TimeoutSec 600

$exit = $session.ExitCode
Add-Content -Path $logFile -Value ("[$now] gym-session exit=$exit log=" + $session.LogFile)

# Surface RED to STATUS.md is handled inside gym_session.py — no PS-side append needed.
# Manager (.claude/agents/gamma.md, 17:30 ET) reads automation/state/gym-scorecard-{date}.json directly.

exit $exit
