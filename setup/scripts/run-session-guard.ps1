# Session guard wrapper -- fires every 5 min during 09:30-15:55 ET weekdays.
# Detects interactive Claude Code sessions running during market hours and
# logs them to JSONL + STATUS.md WARN section.
#
# Default mode: SOFT (warn only). To enable hard-kill, set $env:GAMMA_SESSION_GUARD_MODE=hard
# in the scheduled task's environment, or pass --mode hard via task argument.
#
# Per CLAUDE.md L54 + OP-22.
. "$PSScriptRoot\_shared.ps1"

$task = "session-guard"
$et = Get-EtNow

# Weekday + market-hours gate is duplicated in the Python script, but checking
# here too lets us exit-0 fast on weekends/off-hours without spawning Python.
if (-not (Test-WeekDay $et)) { exit 0 }
if (Test-HolidayFromAlpaca) { exit 0 }
if (-not (Test-MarketHours -Et $et -StartHour 9 -StartMin 30 -EndHour 15 -EndMin 55)) { exit 0 }

# Mode: env var override > default "hard" (per TONIGHT block OP-30/L62 fix 2026-05-21)
# "hard" kills interactive sessions during market hours. "soft" warns only.
$mode = if ($env:GAMMA_SESSION_GUARD_MODE) { $env:GAMMA_SESSION_GUARD_MODE } else { "hard" }
if ($mode -notin @("soft", "hard")) { $mode = "hard" }

Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('HH:mm:ss')) mode=$mode"

$result = Invoke-PythonHidden `
    -ScriptPath "setup\scripts\session_guard.py" `
    -ArgList @("--mode", $mode) `
    -TaskName $task `
    -TimeoutSec 60

Write-TaskLog -TaskName $task -Message "END exit=$($result.ExitCode)"
exit $result.ExitCode
