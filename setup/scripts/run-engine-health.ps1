#requires -Version 5.1
<#
.SYNOPSIS
  Engine Health Beacon -- every-minute liveness fusion pass.

.DESCRIPTION
  Fires from Gamma_HealthBeacon task every 1 min. Calls engine_health.py which
  reads existing state (loop-state, circuit-breakers, watcher-observations,
  tv-watchdog-status, positions), fuses a single GREEN/YELLOW/RED verdict, writes
  automation/state/engine-health.json, and pings Discord ONLY on a transition into
  RED (no spam). Phase 0a: turn fail-green into fail-loud mid-day.

  Pure Python execution. Zero LLM cost. Spawned via Invoke-PythonHidden
  (CREATE_NO_WINDOW) per OP-27 L41/L42. Python is market-hours aware, so this
  wrapper does NOT RTH-gate -- the beacon must run overnight too (a quiet engine
  reads GREEN; a dead daemon or tripped breaker still surfaces off-hours).
#>

$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_shared.ps1"

Set-Location $WorkDir

$null = Invoke-PythonHidden -ScriptPath "setup\scripts\engine_health.py" `
    -ArgList @() `
    -TaskName "engine-health" -TimeoutSec 45

exit 0
