#requires -Version 5.1
<#
.SYNOPSIS
  Numeric Pulse 1m -- every-minute pure-Python pattern detector pass during RTH.

.DESCRIPTION
  Fires from Gamma_NumericPulse1m task every 1 min during 09:30-15:55 ET weekdays.
  Calls numeric_pulse.py which fetches latest closed 5m SPY bar via yfinance and
  runs all 6 chart_patterns detectors. Writes:
    - automation/state/numeric-pulse.jsonl (forensic ledger, every fire)
    - automation/state/numeric-alert.jsonl (high-conviction, contra-trend, level-proximate ONLY)

  Pure Python execution. Zero LLM cost. Spawned via Invoke-PythonHidden
  (CREATE_NO_WINDOW) per OP-27 L41/L42.
#>

$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_shared.ps1"

$projectRoot = $WorkDir
Set-Location $projectRoot

# RTH/weekday gate (Python also checks but this avoids unnecessary spawns)
$now = Get-Date
if ($now.DayOfWeek -eq "Saturday" -or $now.DayOfWeek -eq "Sunday") { exit 0 }
$hhmm = [int]($now.ToString("HHmm"))
if ($hhmm -lt 930 -or $hhmm -ge 1555) { exit 0 }

$pulse = Invoke-PythonHidden -ScriptPath "backtest\autoresearch\numeric_pulse.py" `
    -ArgList @("--silent", "--cycles", "4", "--interval-sec", "15") `
    -TaskName "numeric-pulse-1m" -TimeoutSec 75

exit 0
