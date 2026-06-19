# fix-trading-tasks.ps1 - diagnose (and optionally fix) the dormant trading tasks.
#
# Finding 2026-06-15: the trading loop (LaunchTV/Premarket/Heartbeat/EOD) has not fired
# since 2026-06-08, while Kitchen/crypto 24/7 tasks kept running. The 6/08 premarket ran
# at 15:21 instead of 08:30 -> classic "PC asleep at the scheduled market-hours time and
# the task is not allowed to wake the computer."
#
# This REPORTS each trading task's State / LastRunTime / LastTaskResult / NextRunTime /
# WakeToRun and writes it to automation/state/trading-tasks-status.json (so it can be read
# even when the console is masked). With -Fix it ENABLES any disabled task and sets
# WakeToRun=true. PS 5.1, ASCII. Run before 08:30 ET.

param([switch]$Fix)
$ErrorActionPreference = "Continue"
$repo = "C:\Users\jackw\Desktop\42"
$out = Join-Path $repo "automation\state\trading-tasks-status.json"
$trading = @("Gamma_LaunchTV","Gamma_TvWatchdog","Gamma_Premarket","Gamma_Heartbeat",
             "Gamma_Heartbeat_Aggressive","Gamma_EodFlatten","Gamma_EodFlatten_Aggressive")
$report = @()
Write-Host "=== Trading scheduled tasks ===" -ForegroundColor Cyan
foreach ($n in $trading) {
    $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
    if (-not $t) {
        Write-Host ("[MISSING]   {0}" -f $n) -ForegroundColor Red
        $report += [ordered]@{ name=$n; state="MISSING" }
        continue
    }
    $info = Get-ScheduledTaskInfo -TaskName $n -ErrorAction SilentlyContinue
    $wake = $t.Settings.WakeToRun
    $color = if ($t.State -eq "Disabled") { "Red" } elseif (-not $wake) { "Yellow" } else { "Green" }
    Write-Host ("[{0,-8}] {1,-28} last={2} result={3} next={4} wake={5}" -f `
        $t.State, $n, $info.LastRunTime, $info.LastTaskResult, $info.NextRunTime, $wake) -ForegroundColor $color
    if ($Fix) {
        if ($t.State -eq "Disabled") { Enable-ScheduledTask -TaskName $n | Out-Null; Write-Host "   -> ENABLED" -ForegroundColor Green }
        try { $s = $t.Settings; $s.WakeToRun = $true; Set-ScheduledTask -TaskName $n -Settings $s | Out-Null; Write-Host "   -> WakeToRun=true" -ForegroundColor Green } catch {}
    }
    $report += [ordered]@{ name=$n; state="$($t.State)"; lastRun="$($info.LastRunTime)"; lastResult="$($info.LastTaskResult)"; nextRun="$($info.NextRunTime)"; wakeToRun=$wake }
}
[ordered]@{ checked_at=(Get-Date).ToString("o"); fixed=[bool]$Fix; tasks=$report } | ConvertTo-Json -Depth 5 | Set-Content $out -Encoding UTF8
Write-Host "`nWrote $out"
Write-Host "ALSO REQUIRED: the PC must be AWAKE during 08:30-16:00 ET. Either keep it on, or"
Write-Host "set Power & sleep -> 'When plugged in, PC goes to sleep' = Never during market hours."
if (-not $Fix) { Write-Host "`nRe-run with -Fix to enable disabled tasks + set WakeToRun." -ForegroundColor Yellow }
exit 0
