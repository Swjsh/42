#requires -Version 5.1
<#
.SYNOPSIS
  Fleet executor -- fires every 3 min during 09:30-15:55 ET (mirrors the heartbeat
  cadence, 1 min behind it so decisions.jsonl is fresh). Two pure-Python steps,
  serial (read-after-write):
    1. build_shared_signal.py -- derive shared-signal.json from the heartbeat's
       latest decisions.jsonl row (the "one perception").
    2. fleet_live.py          -- fan that signal to every active fleet_rest arm
       (safe-3 / risky-1 / risky-3), apply each arm's frozen policy + the shared
       risk_gate against its REAL broker state, and LOG the per-arm decision.

  Default mode = WATCH ($0, read-only, places NOTHING) = "sniper eyes watching a
  plethora of strategies for all accounts". LIVE placement is gated behind the
  per-arm `live:true` flag in accounts.json (all false until the Monday-RTH order
  test) AND would require adding --live below. safe-1 + bold-2 are NOT touched here
  (they trade via their own Gamma_Heartbeat* MCP path).

  $0 LLM (pure Python). Wired 2026-06-21 (readiness audit Milestone-2). Per OP-25.
#>
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_shared.ps1"

$task = "fleet-executor"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) { exit 0 }
if (Test-HolidayFromAlpaca) { exit 0 }
if (-not (Test-MarketHours -Et $et -StartHour 9 -StartMin 30 -EndHour 15 -EndMin 55)) { exit 0 }

# Step 1: derive the shared signal from the heartbeat's latest decision (serial).
Invoke-PythonHidden `
    -ScriptPath "automation\state\fleet\build_shared_signal.py" `
    -ArgList @() `
    -TaskName "$task-signal" `
    -TimeoutSec 20 | Out-Null

# Step 2: fan to all fleet_rest arms + log per-arm decisions.
# 2026-06-22: --live ADDED (J directive -- all his Alpaca accounts trade for real-fills
# learning). Master-enable; each arm still ALSO needs its own live:true in accounts.json
# (safe-3 + risky-1 are live; risky-3 stays held = 1DTE/vertical not implemented). Every
# placement is a bracket (TP + never-null stop) via fleet_broker + the shared risk_gate +
# per-arm kill-switch + flat-verify. safe-1/bold-2 are skipped here (heartbeat owns them).
$result = Invoke-PythonHidden `
    -ScriptPath "automation\state\fleet\fleet_live.py" `
    -ArgList @("--quiet", "--live") `
    -TaskName $task `
    -TimeoutSec 45

$exit = $result.ExitCode
# Log once every ~15 min to avoid spam.
if (($et.Minute % 15) -eq 0) {
    Write-TaskLog -TaskName $task -Message "LIVE tick et=$($et.ToString('HH:mm')) exit=$exit"
}

# EOD flatten (2026-06-22): from 15:50 ET, market-sell any open SPY option on the fleet
# arms so no 0DTE long rides to expiry/auto-exercise (mirrors Gamma_EodFlatten for the
# heartbeat accounts; the fleet had NO EOD flatten before going live). Idempotent --
# flat arms no-op. Runs on the 15:51 + 15:54 fleet ticks (executor gate ends 15:55).
if ($et.Hour -eq 15 -and $et.Minute -ge 50) {
    Invoke-PythonHidden `
        -ScriptPath "automation\state\fleet\fleet_eod.py" `
        -ArgList @() `
        -TaskName "fleet-eod" `
        -TimeoutSec 30 | Out-Null
    Write-TaskLog -TaskName $task -Message "EOD flatten fired et=$($et.ToString('HH:mm'))"
}

exit 0  # never fail the task
