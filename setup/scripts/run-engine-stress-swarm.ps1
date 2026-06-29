#requires -Version 5.1
<#
.SYNOPSIS
  Fire one engine-stress-swarm batch (overnight "cook all night" cadence).

  Runs the counterfactual engine-stress harness via the BACKTEST venv interpreter
  (backtest\.venv) -- which is reaper-EXEMPT in _shared.ps1, so the 3-min stale-process
  reaper will not kill a long batch. The free 5-model swarm does the evaluation ($0,
  separate API pool from the Max heartbeat -- never starves market-hours trading).

  Market-hours guard: skips the batch during 09:30-15:55 ET (uses local MT clock +2h)
  so the CPU burst never overlaps live trading. After-hours/overnight only.
#>
[CmdletBinding()] param()
$ErrorActionPreference = "Stop"
$repo = "C:\Users\jackw\Desktop\42"
$py   = Join-Path $repo "backtest\.venv\Scripts\python.exe"
$harness = Join-Path $repo "backtest\autoresearch\engine_stress_swarm.py"
$logDir = Join-Path $repo "automation\state\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$log = Join-Path $logDir ("engine-stress-swarm-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

# Market-hours guard: rig runs on Mountain Time; ET = local + 2h. Skip 09:30-15:55 ET
# (= 07:30-13:55 local MT) on weekdays so the batch never competes with live trading.
$nowLocal = Get-Date
$etNow = $nowLocal.AddHours(2)
$isWeekday = ($etNow.DayOfWeek -ne 'Saturday') -and ($etNow.DayOfWeek -ne 'Sunday')
$marketOpen = ($etNow.TimeOfDay -ge [TimeSpan]::Parse("09:30")) -and ($etNow.TimeOfDay -le [TimeSpan]::Parse("15:55"))
if ($isWeekday -and $marketOpen) {
    Add-Content -Path $log -Value ("[" + (Get-Date -Format o) + "] SKIP: market hours (ET " + $etNow.ToString("HH:mm") + ") -- overnight/after-hours only")
    return
}

Add-Content -Path $log -Value ("[" + (Get-Date -Format o) + "] START engine-stress-swarm batch (ET " + $etNow.ToString("HH:mm") + ")")
# One bounded batch per fire. Full variant grid for the richest overnight coverage.
& $py $harness --seeds 8 --full-variants --max-minutes 25 *>> $log
Add-Content -Path $log -Value ("[" + (Get-Date -Format o) + "] END (exit " + $LASTEXITCODE + ")")
