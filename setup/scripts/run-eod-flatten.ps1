# EOD flatten safety net — fires at 15:55 ET weekdays.
. "$PSScriptRoot\_shared.ps1"

$task = "eod-flatten"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) { exit 0 }
if (Test-HolidayFromAlpaca) { exit 0 }

$reaped = Stop-StaleClaudeProcesses -StaleAfterMinutes 5
if ($reaped.Count -gt 0) { Write-TaskLog -TaskName $task -Message "REAPED stale: $($reaped -join ',')" }

Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('HH:mm:ss'))"
# Flatten is small but critical (closes any open 0DTE before 16:00 expiry). Hard 2-min cap.
$exit = Invoke-Claude -PromptFile (Join-Path $WorkDir "automation\prompts\eod-flatten.md") -TaskName $task -MaxBudgetUsd 1 -TimeoutSec 120 -Effort "low"
exit $exit
