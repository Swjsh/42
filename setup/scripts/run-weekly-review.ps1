# Weekly Review — fires at Sunday 18:00 ET.
. "$PSScriptRoot\_shared.ps1"

$task = "weekly-review"
$et = Get-EtNow

if ($et.DayOfWeek -ne [DayOfWeek]::Sunday) { exit 0 }

$reaped = Stop-StaleClaudeProcesses -StaleAfterMinutes 5
if ($reaped.Count -gt 0) { Write-TaskLog -TaskName $task -Message "REAPED stale: $($reaped -join ',')" }

Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('yyyy-MM-dd HH:mm:ss')) day=$($et.DayOfWeek)"
# Weekly review = deepest analytical task, runs Sunday evening. 12-min cap, high effort allowed.
$exit = Invoke-Claude -PromptFile (Join-Path $WorkDir "automation\prompts\weekly-review.md") -TaskName $task -MaxBudgetUsd 8 -TimeoutSec 720 -Effort "high"
exit $exit
