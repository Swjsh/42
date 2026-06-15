#requires -Version 5.1
<#
.SYNOPSIS
  Daily watcher grader -- grades ungraded watcher observations post-market.
  Fires via Gamma_WatcherGrader at 17:10 ET weekdays.

.DESCRIPTION
  Lightweight (no 30-day replay). Reads watcher-observations.jsonl, finds rows
  where would_be_outcome=null, fetches future bars from the daily-appended CSV
  (created by append_today.py at 16:00 ET), simulates the trade outcome, writes
  back to the file.

  Runs AFTER Gamma_EodSummary (16:00) so append_today.py has already created
  spy_5m_2026-05-08_{today}.csv, which runner.load_data() can now auto-discover
  via _discover_csv_candidates() (runner.py fix 2026-05-21).

  Pure Python. Zero LLM cost. Window-leak-safe per OP-27 L42.
#>

$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_shared.ps1"

$projectRoot = $WorkDir
Set-Location $projectRoot

$dateStr = (Get-Date).ToString("yyyy-MM-dd")
$logFile = Join-Path $LogDir ("watcher-grader-" + $dateStr + ".log")
$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Add-Content -Path $logFile -Value "[$now] watcher-grader: starting for $dateStr"

# Step 1: Grade all non-shotgun ungraded observations.
# shotgun_scalper_watcher uses single-exit doctrine (no TP1+runner 50/50 split)
# and is handled by shotgun_grader.py in Step 2.
$result = Invoke-PythonHidden `
    -ScriptPath "backtest\autoresearch\watcher_grader.py" `
    -TaskName "watcher-grader" `
    -TimeoutSec 120

$exit = $result.ExitCode
$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "[$now] watcher-grader exit=$exit log=$($result.LogFile)"

if ($result.Stdout) {
    Add-Content -Path $logFile -Value "STDOUT: $($result.Stdout.TrimEnd())"
}
if ($result.Stderr) {
    Add-Content -Path $logFile -Value "STDERR: $($result.Stderr.TrimEnd())"
}

# Step 2: Re-grade ALL shotgun_scalper observations using correct single-exit doctrine.
# Writes to automation/state/shotgun-grader-summary.json (separate from watcher-summary.json).
$result2 = Invoke-PythonHidden `
    -ScriptPath "backtest\autoresearch\shotgun_grader.py" `
    -TaskName "shotgun-grader" `
    -TimeoutSec 180

$exit2 = $result2.ExitCode
$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "[$now] shotgun-grader exit=$exit2 log=$($result2.LogFile)"

if ($result2.Stdout) {
    Add-Content -Path $logFile -Value "SHOTGUN STDOUT: $($result2.Stdout.TrimEnd())"
}
if ($result2.Stderr) {
    Add-Content -Path $logFile -Value "SHOTGUN STDERR: $($result2.Stderr.TrimEnd())"
}

# Surface failures to STATUS.md so Manager + wake fires see them
$combinedExit = [Math]::Max($exit, $exit2)
if ($combinedExit -ne 0) {
    $statusPath = Join-Path $projectRoot "automation\overnight\STATUS.md"
    $statusLine = "[$dateStr 17:10] Gamma_WatcherGrader FAILED exit=$exit shotgun_exit=$exit2 — check $logFile"
    Add-Content -Path $statusPath -Value $statusLine
}
$exit = $combinedExit

exit $exit
