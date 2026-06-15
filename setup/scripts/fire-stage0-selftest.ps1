#!/usr/bin/env pwsh
# Stage 0 self-test for any wake fire - pin chain, TV CDP, Discord bridge, scheduled tasks.
# Reusable across fires - extends fire19-final-verify.ps1 with task audit.
$ErrorActionPreference = "Continue"

Write-Output "=== STAGE 0 SELF-TEST ==="
Write-Output ("now_et: " + (Get-Date -Format "yyyy-MM-ddTHH:mm:ss"))
Write-Output ""

Write-Output "--- v15 PIN CHAIN ---"
$p = Get-Content 'C:\Users\jackw\Desktop\42\automation\state\params.json' -Raw | ConvertFrom-Json
Write-Output ("rule_version: " + $p.rule_version)
Write-Output ("ratified_at:  " + $p.rule_version_ratified_at)

$hbLine = Select-String -Path 'C:\Users\jackw\Desktop\42\automation\prompts\heartbeat.md' -Pattern 'RULE_VERSION\s*=\s*' | Select-Object -First 1
Write-Output ("heartbeat.md: " + $hbLine.Line.Trim())
$pmLine = Select-String -Path 'C:\Users\jackw\Desktop\42\automation\prompts\premarket.md' -Pattern 'RULE_VERSION_EXPECTED' | Select-Object -First 1
Write-Output ("premarket.md: " + $pmLine.Line.Trim())
Write-Output ""

Write-Output "--- TV CDP PORT 9222 ---"
$cdp = Test-NetConnection -ComputerName 127.0.0.1 -Port 9222 -InformationLevel Quiet -WarningAction SilentlyContinue
Write-Output ("listening: " + $cdp)
$tvCount = (Get-Process | Where-Object { $_.ProcessName -like '*TradingView*' }).Count
Write-Output ("tv_process_count: " + $tvCount)
Write-Output ""

Write-Output "--- DISCORD BRIDGE ---"
$disc = Get-Process -Id 20708 -ErrorAction SilentlyContinue
if ($disc) {
    Write-Output ("PID 20708 ALIVE name=" + $disc.ProcessName)
} else {
    Write-Output "PID 20708 DEAD - discord_bridge process not found"
}
Write-Output ""

Write-Output "--- GAMMA SCHEDULED TASKS ---"
$tasks = Get-ScheduledTask | Where-Object { $_.TaskName -like 'Gamma_*' }
foreach ($t in $tasks) {
    $info = Get-ScheduledTaskInfo -TaskName $t.TaskName
    Write-Output ($t.TaskName + " :: state=" + $t.State + " :: lastRun=" + $info.LastRunTime + " :: lastResult=" + $info.LastTaskResult)
}
Write-Output ""

Write-Output "--- STATUS.md AGE ---"
$statusFile = Get-Item 'C:\Users\jackw\Desktop\42\automation\overnight\STATUS.md'
$age = (Get-Date) - $statusFile.LastWriteTime
$ageMin = [math]::Round($age.TotalMinutes, 1)
Write-Output ("STATUS.md last_write: " + $statusFile.LastWriteTime + " (" + $ageMin + " min ago)")
if ($age.TotalMinutes -gt 90) {
    Write-Output "WARNING: STATUS.md over 90 min stale - harness suspected dead"
}
