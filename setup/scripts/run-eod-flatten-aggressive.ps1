# Aggressive EOD flatten safety net — fires at 15:55 ET weekdays.
# Closes any 0DTE position in the aggressive paper account not already
# closed by the aggressive heartbeat's 15:50 time stop.
. "$PSScriptRoot\_shared.ps1"

$task = "eod-flatten-aggressive"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) { exit 0 }
if (Test-HolidayFromAlpaca) { exit 0 }

$reaped = Stop-StaleClaudeProcesses -StaleAfterMinutes 5
if ($reaped.Count -gt 0) { Write-TaskLog -TaskName $task -Message "REAPED stale: $($reaped -join ',')" }

Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('HH:mm:ss'))"

$exit = Invoke-Claude `
    -PromptFile (Join-Path $WorkDir "automation\prompts\aggressive\eod-flatten.md") `
    -TaskName $task `
    -MaxBudgetUsd 1 `
    -TimeoutSec 120 `
    -Effort "low"
exit $exit
