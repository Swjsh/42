# Market-hours circuit breaker -- fires every 2 min during 09:20-15:56 ET weekdays.
# Reads today's Claude token spend; if >= $100 fires the circuit breaker:
#   1. Kills interactive Claude sessions (not --print heartbeat/EOD tasks)
#   2. Writes rate-limit-cooldown.json with claude_print_exempt: true
#      so Gamma_Heartbeat keeps trading even while other consumers are locked out
#
# Per CLAUDE.md OP-30 (effort/concurrency discipline) + L62 (rate-limit exhaustion
# silenced heartbeat 2026-05-20) + L54 (interactive loop during market hours).
# Companion to Gamma_SessionGuard (which kills; this one fires at the $-threshold).
. "$PSScriptRoot\_shared.ps1"

$task = "market-hours-circuit-breaker"
$et = Get-EtNow

# Fast exit outside window. Widen by 10min on each side to catch ramp-up/down.
if (-not (Test-WeekDay $et)) { exit 0 }
if (Test-HolidayFromAlpaca) { exit 0 }
if (-not (Test-MarketHours -Et $et -StartHour 9 -StartMin 20 -EndHour 15 -EndMin 56)) { exit 0 }

Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('HH:mm:ss'))"

$result = Invoke-PythonHidden `
    -ScriptPath "setup\scripts\market_hours_circuit_breaker.py" `
    -ArgList @() `
    -TaskName $task `
    -TimeoutSec 60

Write-TaskLog -TaskName $task -Message "END exit=$($result.ExitCode) out=$($result.Stdout.Trim() -replace '\r?\n',' ')"
exit $result.ExitCode
