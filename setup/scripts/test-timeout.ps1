# Smoke test: prove the wall-clock timeout in Invoke-Claude actually kills.
# Uses a tiny prompt with a 15s timeout. Heartbeat normally finishes Haiku in ~30-60s,
# so a 15s cap should hard-kill mid-run and we should see exit=124 + TIMEOUT_KILL in log.
. "$PSScriptRoot\_shared.ps1"

$task = "test-timeout"
Write-Host "=== Self-heal smoke test ===" -ForegroundColor Cyan
Write-Host "Calling Invoke-Claude with -TimeoutSec 15 on the heartbeat prompt."
Write-Host "Expected: exit=124, log contains TIMEOUT_KILL, no orphan processes after."
Write-Host ""

$start = Get-Date
$exit = Invoke-Claude `
    -PromptFile (Join-Path $WorkDir "automation\prompts\heartbeat.md") `
    -TaskName $task `
    -MaxBudgetUsd 0.10 `
    -Model "haiku" `
    -TimeoutSec 15 `
    -Effort "low"
$elapsed = ((Get-Date) - $start).TotalSeconds

Write-Host ""
Write-Host "=== Result ===" -ForegroundColor Cyan
Write-Host "Exit code: $exit (expected 124 = timeout)"
Write-Host "Elapsed: $([math]::Round($elapsed, 1))s (expected 15-20s)"
Write-Host ""
Write-Host "=== Log tail ==="
$logPath = Join-Path $LogDir "$task-$((Get-EtNow).ToString('yyyy-MM-dd')).log"
if (Test-Path $logPath) { Get-Content $logPath -Tail 10 } else { "no log written" }
Write-Host ""
Write-Host "=== Orphan check (claude/node/uv younger than 30s) ==="
$cutoff = (Get-Date).AddSeconds(-30)
$orphans = Get-Process -Name "claude","node","python","uv" -ErrorAction SilentlyContinue | Where-Object { $_.StartTime -gt $cutoff }
if ($orphans) {
    Write-Host "FAIL: orphans still alive:" -ForegroundColor Red
    $orphans | Select-Object Id, ProcessName, StartTime | Format-Table -AutoSize
} else {
    Write-Host "PASS: no orphans" -ForegroundColor Green
}
