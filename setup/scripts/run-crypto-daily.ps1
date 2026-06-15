#requires -Version 5.1
<#
.SYNOPSIS
  Daily crypto-harness routine. Fires once per day at 06:00 ET via Gamma_CryptoDaily.

.DESCRIPTION
  Keeps the gym routine fresh:
    1. Health-audit both Gamma_Crypto* tasks (must have fired in last 24h)
    2. Rotate grinder.jsonl if > 5 MB (snapshot, truncate, keep last 100 lines)
    3. Re-run benchmark.replay_5_14 (regression smoke test of the floor)
    4. Generate daily DIGEST: harness health + grinder findings + recommendations
    5. Append daily summary to STATUS.md and crypto/data/scorecards/daily-digest.jsonl

  Pure Python + PowerShell. Zero LLM cost. ALL Python spawned via Invoke-PythonHidden
  (CREATE_NO_WINDOW) per OP-27 L41 -- bare `python script.py` leaks conhost windows.
#>
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_shared.ps1"

$projectRoot = $WorkDir
Set-Location $projectRoot

$digestDir = Join-Path $projectRoot "crypto\data\scorecards\daily"
if (-not (Test-Path $digestDir)) { New-Item -ItemType Directory -Path $digestDir -Force | Out-Null }

$today = Get-Date -Format "yyyy-MM-dd"
$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$logFile = Join-Path $LogDir ("crypto-daily-" + $today + ".log")
$digestFile = Join-Path $digestDir ($today + ".md")

function Write-Log([string]$msg) {
    $line = "[$now] $msg"
    Add-Content -Path $logFile -Value $line
}

Write-Log "crypto-daily: START"

# === Step 1: Task health audit ===
Write-Log "Step 1 -- task health audit"
$regression = Get-ScheduledTask -TaskName "Gamma_CryptoRegression" -ErrorAction SilentlyContinue
$keepalive  = Get-ScheduledTask -TaskName "Gamma_CryptoGrinderKeepalive" -ErrorAction SilentlyContinue
$regResult = "?"; $regMissed = "?"
$kaResult  = "?"; $kaMissed  = "?"
if ($regression) {
    $info = $regression | Get-ScheduledTaskInfo
    $regResult = $info.LastTaskResult
    $regMissed = $info.NumberOfMissedRuns
}
if ($keepalive) {
    $info = $keepalive | Get-ScheduledTaskInfo
    $kaResult = $info.LastTaskResult
    $kaMissed = $info.NumberOfMissedRuns
}
Write-Log "task health: regression result=$regResult missed=$regMissed | keepalive result=$kaResult missed=$kaMissed"

# === Step 2: Rotate grinder.jsonl if > 5 MB ===
Write-Log "Step 2 -- grinder rotation check"
$grinderPath = Join-Path $projectRoot "crypto\data\scorecards\grinder.jsonl"
if (Test-Path $grinderPath) {
    $size = (Get-Item $grinderPath).Length
    Write-Log ("grinder.jsonl size: " + [math]::Round($size / 1MB, 2) + " MB")
    if ($size -gt 5MB) {
        $archive = Join-Path $projectRoot "crypto\data\scorecards\grinder-archive-$today.jsonl"
        Copy-Item $grinderPath $archive
        Get-Content $grinderPath -Tail 100 | Set-Content $grinderPath -Encoding utf8
        Write-Log "rotated -> $archive (kept last 100 lines)"
    }
}

# === Step 3: 5/14 floor regression smoke test ===
Write-Log "Step 3 -- 5/14 floor regression smoke test"
$replay = Invoke-PythonHidden -ScriptPath "crypto\benchmarks\replay_5_14.py" -TaskName "crypto-daily-replay" -TimeoutSec 300
Write-Log ("replay_5_14 exit=" + $replay.ExitCode)
$replayExit = $replay.ExitCode

# === Step 4: Drift report + analyzer ===
Write-Log "Step 4 -- drift report"
$drift = Invoke-PythonHidden -ScriptPath "crypto\benchmarks\track_drift.py" -TaskName "crypto-daily-drift" -TimeoutSec 120
$analyzer = Invoke-PythonHidden -ScriptPath "crypto\benchmarks\analyze_grinder.py" -TaskName "crypto-daily-analyzer" -TimeoutSec 120

# === Step 4a: Scheduled-tasks audit (OP-27) ===
Write-Log "Step 4a -- scheduled-tasks audit"
$taskAudit = Invoke-PythonHidden -ScriptPath "setup\scripts\audit_scheduled_tasks.py" -TaskName "crypto-daily-audit" -TimeoutSec 60
$taskAuditExit = $taskAudit.ExitCode
Write-Log "task audit exit=$taskAuditExit"
if ($taskAuditExit -ne 0) {
    $statusPath = Join-Path $projectRoot "automation\overnight\STATUS.md"
    if (Test-Path $statusPath) {
        Add-Content -Path $statusPath -Value "`n- [$now] scheduled-tasks audit RED -- see automation/state/scheduled-tasks-audit.json"
    }
}

# === Step 4b: Window-leak compliance audit (OP-27 L41) ===
Write-Log "Step 4b -- window-leak compliance audit"
$wlAudit = Invoke-PythonHidden -ScriptPath "setup\scripts\audit_window_leak_compliance.py" -TaskName "crypto-daily-wlaudit" -TimeoutSec 30
$wlAuditExit = $wlAudit.ExitCode
Write-Log "window-leak audit exit=$wlAuditExit"
if ($wlAuditExit -ne 0) {
    $statusPath = Join-Path $projectRoot "automation\overnight\STATUS.md"
    if (Test-Path $statusPath) {
        Add-Content -Path $statusPath -Value "`n- [$now] window-leak compliance RED -- bare python or subprocess w/o creationflags found; see automation/state/window-leak-compliance-audit.json"
    }
}

# === Step 4c: Gym harvester (Coach feedback-loop closure) ===
# Tails grinder.jsonl + history.jsonl + latest.json, detects 7 edge-case rules,
# appends candidate tasks to automation/overnight/queue.md. Idempotent — running
# twice in a 5-min window produces zero duplicate rows. No scheduled task added;
# piggybacks on this 06:00 ET daily fire. See crypto/benchmarks/gym_harvester.py.
Write-Log "Step 4c -- gym harvester"
$harvest = Invoke-PythonHidden -ScriptPath "crypto\benchmarks\gym_harvester.py" -TaskName "crypto-daily-harvester" -TimeoutSec 60
Write-Log ("gym_harvester exit=" + $harvest.ExitCode)
if ($harvest.Stdout) { Write-Log ("gym_harvester output: " + ($harvest.Stdout -replace "`r?`n", " ")) }

# === Step 5: Write daily DIGEST markdown ===
Write-Log "Step 5 -- write daily digest"
$digest = Invoke-PythonHidden -ScriptPath "setup\scripts\_crypto_daily_digest.py" `
    -ArgList @($today, $digestFile, "$regResult", "$regMissed", "$kaResult", "$kaMissed") `
    -TaskName "crypto-daily-digest" -TimeoutSec 60
if ($digest.ExitCode -eq 0) {
    Write-Log "daily digest written: $digestFile"
} else {
    Write-Log ("daily digest FAILED with exit " + $digest.ExitCode)
}

# === Step 6: Append one-line summary to STATUS.md ===
$statusPath = Join-Path $projectRoot "automation\overnight\STATUS.md"
if (Test-Path $statusPath) {
    $summary = "[$now] crypto-daily PASS -- digest: crypto/data/scorecards/daily/$today.md"
    if ($replayExit -ne 0) { $summary = "[$now] crypto-daily PARTIAL -- replay_5_14 exit=$replayExit" }
    Add-Content -Path $statusPath -Value "`n$summary"
}

Write-Log "crypto-daily: END exit=0"
exit 0
