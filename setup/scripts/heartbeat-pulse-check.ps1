#!/usr/bin/env pwsh
# heartbeat-pulse-check.ps1 — verify Gamma_Heartbeat scheduled task is firing on schedule.
#
# AUDIT: read automation/state/logs/heartbeat-{date}.log for FIRE timestamps + intervals.
# DIAGNOSE: GREEN if all intervals ≤ 6 min during 09:30-15:55 ET; YELLOW if 1 gap 6-15 min;
#           RED if any gap > 15 min OR no FIRE entries during a market hour.
# HEAL: GREEN/YELLOW = no-op. RED = check Get-ScheduledTask Gamma_Heartbeat state, attempt
#       Start-ScheduledTask if disabled-but-shouldnt-be, write Discord alert.
# REPORT: stdout + JSON at automation/state/heartbeat-pulse-check-{date}.json.
#
# Usage:
#   & "C:\Users\jackw\Desktop\42\setup\scripts\heartbeat-pulse-check.ps1"
#   & "C:\Users\jackw\Desktop\42\setup\scripts\heartbeat-pulse-check.ps1" -Date 2026-05-14
#   & "C:\Users\jackw\Desktop\42\setup\scripts\heartbeat-pulse-check.ps1" -Heal
#
param(
    [string]$Date = (Get-Date -Format "yyyy-MM-dd"),
    [switch]$Heal,
    [switch]$Quiet
)

$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\jackw\Desktop\42"
$LOG_PATH = Join-Path $ROOT "automation\state\logs\heartbeat-$Date.log"
$OUT_JSON = Join-Path $ROOT "automation\state\heartbeat-pulse-check-$Date.json"

# Market hours window (RTH)
$MARKET_OPEN_MINUTES  = 9 * 60 + 30   # 09:30 ET
$MARKET_CLOSE_MINUTES = 15 * 60 + 55  # 15:55 ET

function Write-Result {
    param([string]$Verdict, [hashtable]$Data)
    $payload = @{
        skill        = "heartbeat-pulse-check"
        run_at       = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
        target_date  = $Date
        verdict      = $Verdict
    } + $Data
    $payload | ConvertTo-Json -Depth 6 | Out-File -FilePath $OUT_JSON -Encoding utf8 -Force
    if (-not $Quiet) {
        Write-Output "=== heartbeat-pulse-check $Date ==="
        Write-Output "VERDICT: $Verdict"
        foreach ($k in $Data.Keys) {
            Write-Output ("  {0}: {1}" -f $k, $Data[$k])
        }
        Write-Output ("  output: $OUT_JSON")
    }
}

# 1. AUDIT — read log
if (-not (Test-Path $LOG_PATH)) {
    Write-Result -Verdict "RED" -Data @{
        reason             = "log-missing"
        log_path           = $LOG_PATH
        fire_count         = 0
        max_gap_minutes    = 0
        gaps_over_15_min   = 0
        scheduled_task     = $null
        heal_action        = "no-log-cannot-heal-investigate-task-scheduler"
    }
    exit 1
}

$logLines = Get-Content $LOG_PATH
# v2 fix (2026-05-14T22:30 ET, FIRE #44 false-alarm investigation):
# v1 regex matched only `ET FIRE ` lines. That missed `SKIP hash_unchanged` and
# `SKIP throttle` early-exits (run-heartbeat.ps1 lines 75-117 cost-optimization
# paths). Both ARE task fires that completed early without invoking Claude.
# From the task-scheduler perspective they DID run — they just chose to skip
# the Claude call when state was unchanged. Counting both eliminates the
# false-alarm pattern observed on 2026-05-14 14:30-15:48 ET (kill-switch hours,
# state hash unchanged for 5 consecutive ticks → v1 reported 3 gaps of 15 min).
# Also count `REAPED stale ...` lines (line 122 of run-heartbeat.ps1 — process
# reaper runs BEFORE FIRE on every tick; same minute as the FIRE). De-dup by
# minute so REAPED+FIRE pair only counts once.
$fireRegex = "^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):(\d{2}) ET (FIRE|SKIP|REAPED) "
$fires = @()
$seenMinute = @{}
foreach ($line in $logLines) {
    if ($line -match $fireRegex) {
        $hh = [int]$matches[2]
        $mm = [int]$matches[3]
        $ss = [int]$matches[4]
        $kind = $matches[5]
        $totalMin = $hh * 60 + $mm + ($ss / 60.0)
        # De-dup multiple log lines on same wall-clock minute (REAPED 0-1s
        # before FIRE, SKIP-only minutes have no FIRE — count each minute once).
        $minuteKey = "{0:D2}:{1:D2}" -f $hh, $mm
        if ($seenMinute.ContainsKey($minuteKey)) { continue }
        $seenMinute[$minuteKey] = $true
        $fires += [PSCustomObject]@{
            time_str    = "$($matches[2]):$($matches[3]):$($matches[4])"
            kind        = $kind
            total_min   = $totalMin
            in_market   = ($totalMin -ge $MARKET_OPEN_MINUTES -and $totalMin -le $MARKET_CLOSE_MINUTES)
        }
    }
}

$fireCount = $fires.Count
$marketFires = @($fires | Where-Object { $_.in_market })
$marketFireCount = $marketFires.Count

# Compute intervals between consecutive market-hours FIREs
$gaps = @()
for ($i = 1; $i -lt $marketFires.Count; $i++) {
    $delta = $marketFires[$i].total_min - $marketFires[$i - 1].total_min
    $gaps += [PSCustomObject]@{
        from        = $marketFires[$i - 1].time_str
        to          = $marketFires[$i].time_str
        gap_minutes = [math]::Round($delta, 2)
    }
}

$maxGap = if ($gaps.Count -gt 0) { ($gaps | Measure-Object -Property gap_minutes -Maximum).Maximum } else { 0 }
$gapsOver15 = @($gaps | Where-Object { $_.gap_minutes -gt 15 })
$gapsOver6  = @($gaps | Where-Object { $_.gap_minutes -gt 6 -and $_.gap_minutes -le 15 })

# 2. DIAGNOSE
$verdict = "GREEN"
$reason  = "all-intervals-OK"
if ($marketFireCount -eq 0) {
    # If today is target and market currently open, this is RED. If audit-after-hours of past day
    # and no fires, also RED — heartbeat didn't fire at all.
    $verdict = "RED"
    $reason  = "zero-market-hour-fires"
} elseif ($gapsOver15.Count -gt 0) {
    $verdict = "RED"
    $reason  = "$($gapsOver15.Count)-gaps-over-15-min"
} elseif ($gapsOver6.Count -gt 0) {
    $verdict = "YELLOW"
    $reason  = "$($gapsOver6.Count)-gaps-6-to-15-min"
}

# 3. CHECK SCHEDULED TASK
$schedTask = $null
$schedState = $null
try {
    $schedTask  = Get-ScheduledTask -TaskName "Gamma_Heartbeat" -ErrorAction Stop
    $schedInfo  = Get-ScheduledTaskInfo -TaskName "Gamma_Heartbeat" -ErrorAction SilentlyContinue
    $schedState = $schedTask.State.ToString()
    if ($schedState -ne "Ready" -and $schedState -ne "Running") {
        $verdict = "RED"
        $reason  = "$reason; sched-task-state=$schedState"
    }
} catch {
    $verdict = "RED"
    $reason  = "$reason; sched-task-missing"
}

# 4. HEAL
$healAction = "no-op"
if ($Heal -and $verdict -eq "RED") {
    if ($schedState -eq "Disabled") {
        try {
            Enable-ScheduledTask -TaskName "Gamma_Heartbeat" -ErrorAction Stop | Out-Null
            $healAction = "enabled-Gamma_Heartbeat-task"
        } catch {
            $healAction = "enable-failed: $($_.Exception.Message)"
        }
    } elseif ($null -eq $schedTask) {
        $healAction = "task-missing-CANNOT-AUTO-HEAL-needs-J-to-recreate-via-setup-scripts"
    } else {
        $healAction = "task-state-$schedState-no-action-investigate-windows-task-scheduler-history"
    }
}

# Discord alert if RED + Heal
if ($Heal -and $verdict -eq "RED") {
    $alertMsg = "[heartbeat-pulse-check] RED on $Date :: $reason :: heal=$healAction"
    Add-Content -Path (Join-Path $ROOT "automation\state\discord-outbox.jsonl") -Value (
        @{ ts = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss"); kind = "ALERT"; severity = "RED"; text = $alertMsg } | ConvertTo-Json -Compress
    )
}

# 5. REPORT
Write-Result -Verdict $verdict -Data @{
    reason            = $reason
    log_path          = $LOG_PATH
    fire_count_total  = $fireCount
    market_fire_count = $marketFireCount
    max_gap_minutes   = [math]::Round($maxGap, 2)
    gaps_over_15_min  = $gapsOver15.Count
    gaps_6_to_15_min  = $gapsOver6.Count
    scheduled_task_state = $schedState
    heal_action       = $healAction
    sample_gaps       = ($gapsOver15 + $gapsOver6 | Select-Object -First 5)
}

if ($verdict -eq "RED") { exit 1 } else { exit 0 }
