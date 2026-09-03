# Weekly Review — fires at Sunday 18:00 ET.
. "$PSScriptRoot\_shared.ps1"

$task = "weekly-review"
$et = Get-EtNow

if ($et.DayOfWeek -ne [DayOfWeek]::Sunday) { exit 0 }

$reaped = Stop-StaleClaudeProcesses -StaleAfterMinutes 5
if ($reaped.Count -gt 0) { Write-TaskLog -TaskName $task -Message "REAPED stale: $($reaped -join ',')" }

Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('yyyy-MM-dd HH:mm:ss')) day=$($et.DayOfWeek)"

# 2026-09-03 WEEKLY-REVIEW-RETRY-DONE-MARKER (queue.md): this task now carries a
# PT15M/PT30M self-heal retry window (matching the other 7 evening producers,
# dceb125e) so a silently-skipped fire gets recovered. But Invoke-Claude below is a
# real ~$8 LLM call -- a retry re-running it for a week already reviewed would
# double-bill. Gate it on a done-marker written ONLY after a successful run.
$markerScript = Join-Path $PSScriptRoot "weekly_review_marker.py"
$markerPath = Join-Path $WorkDir "automation\state\weekly-review-done.json"
$checkResult = Invoke-PythonHidden -ScriptPath $markerScript -ArgList @("check", "--marker", $markerPath) -TaskName $task
Write-TaskLog -TaskName $task -Message "marker check: exit=$($checkResult.ExitCode) stdout=$($checkResult.Stdout.Trim())"
if ($checkResult.ExitCode -eq 0) {
    Write-TaskLog -TaskName $task -Message "$($checkResult.Stdout.Trim()) -- skipping Invoke-Claude, no charge"
    exit 0
}

# Weekly review = deepest analytical task, runs Sunday evening. 12-min cap, high effort allowed.
$exit = Invoke-Claude -PromptFile (Join-Path $WorkDir "automation\prompts\weekly-review.md") -TaskName $task -MaxBudgetUsd 8 -TimeoutSec 720 -Effort "high"

if ($exit -eq 0) {
    # SUCCESS ONLY: write the marker so a same-week retry (self-heal window, or any
    # other re-fire) skips the LLM call instead of double-billing. A FAILED run
    # ($exit -ne 0) deliberately does NOT reach this branch -- the marker stays
    # stale/missing so the retry window can actually recover the failure.
    $weekIso = ($checkResult.Stdout -replace '^RUN\s+', '').Trim()
    $writeArgs = @("write", "--marker", $markerPath)
    if ($weekIso) { $writeArgs += @("--artifact", "analysis\weekly\$weekIso.md") }
    $writeResult = Invoke-PythonHidden -ScriptPath $markerScript -ArgList $writeArgs -TaskName $task
    Write-TaskLog -TaskName $task -Message "marker write: exit=$($writeResult.ExitCode) stdout=$($writeResult.Stdout.Trim())"
} else {
    Write-TaskLog -TaskName $task -Message "FAILED exit=$exit -- marker NOT written, retry window may recover"
}

exit $exit
