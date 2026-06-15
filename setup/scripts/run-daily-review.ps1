# Daily Review — fires at 16:30 ET weekdays.
. "$PSScriptRoot\_shared.ps1"

$task = "daily-review"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) { exit 0 }
if (Test-HolidayFromAlpaca) { exit 0 }

$reaped = Stop-StaleClaudeProcesses -StaleAfterMinutes 5
if ($reaped.Count -gt 0) { Write-TaskLog -TaskName $task -Message "REAPED stale: $($reaped -join ',')" }

Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('HH:mm:ss'))"

# Archive today's key-levels.json BEFORE the daily-review overwrites it with tomorrow's levels.
# Archived copy goes to journal/key-levels-archive/key-levels-{for_session}.json so that
# pattern_backtest.py can use the actual production ★★+ levels for historical dates.
$klPath = Join-Path $WorkDir "automation\state\key-levels.json"
$archiveDir = Join-Path $WorkDir "journal\key-levels-archive"
if (Test-Path $klPath) {
    try {
        $kl = Get-Content $klPath -Raw | ConvertFrom-Json
        $session = $kl.for_session
        if ($session) {
            $archivePath = Join-Path $archiveDir "key-levels-${session}.json"
            if (-not (Test-Path $archivePath)) {
                if (-not (Test-Path $archiveDir)) { New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null }
                Copy-Item -Path $klPath -Destination $archivePath
                Write-TaskLog -TaskName $task -Message "Archived key-levels.json -> key-levels-${session}.json"
            }
        }
    } catch {
        Write-TaskLog -TaskName $task -Message "WARNING: key-levels archive failed: $_"
    }
}

# Daily review = strategic post-session, not time-critical. 5-min cap, medium effort.
# Retry on rate-limit (max 2h wait) — without this, a shared rate-limit hit silently
# drops tomorrow's key-levels.json generation (per L54).
$exit = Invoke-ClaudeWithRetry -PromptFile (Join-Path $WorkDir "automation\prompts\daily-review.md") -TaskName $task -MaxBudgetUsd 3 -TimeoutSec 300 -Effort "medium" -MaxRateLimitWaitSec 7200
exit $exit
