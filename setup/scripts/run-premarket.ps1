# Premarket routine — fires at 08:30 ET weekdays.
# Self-heal: hard wall-clock cap 6 min, retry once on timeout/failure (but only
# if there's enough buffer before market open at 09:30).
. "$PSScriptRoot\_shared.ps1"

$task = "premarket"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) {
    Write-TaskLog -TaskName $task -Message "SKIP weekend"
    exit 0
}
if (Test-HolidayFromAlpaca) {
    Write-TaskLog -TaskName $task -Message "SKIP holiday"
    exit 0
}

# Self-heal: kill any stale claude/MCP processes from a prior crashed run.
$reaped = Stop-StaleClaudeProcesses -StaleAfterMinutes 5
if ($reaped.Count -gt 0) {
    Write-TaskLog -TaskName $task -Message "REAPED stale: $($reaped -join ',')"
}

function Invoke-PremarketAttempt {
    param([int]$AttemptNum)
    Write-TaskLog -TaskName $task -Message "FIRE attempt=$AttemptNum et=$((Get-EtNow).ToString('HH:mm:ss'))"
    # 2026-05-07: bumped 360s -> 540s. Premarket prompt has 9 steps including options
    # chain, dealer levels, ES overnight, dark-pool aggregation. 360s wasn't enough for
    # Sonnet to complete reliably; first attempt today timed out at exactly 360s.
    # 540s + 540s retry = 1080s = 18min, but Task Scheduler ExecutionTimeLimit on
    # Gamma_Premarket is PT14M = 840s. So retry will only fit if attempt 1 finished
    # under ~290s. That's the deliberate trade — long timeout helps single-attempt
    # success rate; short retry budget is a fallback only.
    return Invoke-Claude `
        -PromptFile (Join-Path $WorkDir "automation\prompts\premarket.md") `
        -TaskName $task `
        -MaxBudgetUsd 3 `
        -TimeoutSec 540 `
        -Effort "medium"
}

$exit = Invoke-PremarketAttempt -AttemptNum 1

# Retry-once self-heal — only if there's still time before market open.
# Market opens at 09:30 ET. We need at least 5 min buffer for a retry to be useful.
if ($exit -ne 0) {
    $now = Get-EtNow
    $marketOpen = [DateTime]::new($now.Year, $now.Month, $now.Day, 9, 30, 0)
    $minutesUntilOpen = ($marketOpen - $now).TotalMinutes
    if ($minutesUntilOpen -gt 11) {
        Write-TaskLog -TaskName $task -Message ("RETRY exit=" + $exit + ", " + ([math]::Round($minutesUntilOpen,1)) + "min until open - attempting once more")
        # Reap anything left from the failed first attempt before retry. Use 1 min
        # cutoff (the prior attempt's processes were tree-killed at timeout, but MCP
        # children that the kill missed will be older than 1min by now). Avoids the
        # StaleAfterMinutes=0 refusal-write-warning path that broke retry on 2026-05-07.
        Stop-StaleClaudeProcesses -StaleAfterMinutes 1 | Out-Null
        Start-Sleep -Seconds 5
        $exit = Invoke-PremarketAttempt -AttemptNum 2
    } else {
        Write-TaskLog -TaskName $task -Message ("NO_RETRY exit=" + $exit + ", only " + ([math]::Round($minutesUntilOpen,1)) + "min until open - give up cleanly")
    }
}
exit $exit
