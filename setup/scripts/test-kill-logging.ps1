# $0 regression guard for GOAL-SUBTRACTION-2026-09-11 item (d):
# Get-ProcessKillInfo (the helper the 15:55 flattener's timeout-kill branch uses to
# log image name + command line for every pid it kills) must correctly attribute a
# REAL running process and must SKIP a pid that does not exist rather than padding
# the result with a null row. No claude.exe is spawned -- this costs $0 and no
# Anthropic tokens, unlike test-timeout.ps1 / test-self-heal.ps1.
. "$PSScriptRoot\_shared.ps1"

$failures = 0
function Assert-True {
    param([bool]$Condition, [string]$Message)
    if ($Condition) {
        Write-Host "PASS: $Message" -ForegroundColor Green
    } else {
        Write-Host "FAIL: $Message" -ForegroundColor Red
        $script:failures++
    }
}

Write-Host "=== Get-ProcessKillInfo regression guard ===" -ForegroundColor Cyan

# Spawn a real, harmless, short-lived process we fully control.
$dummy = Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoProfile -NonInteractive -Command Start-Sleep -Seconds 20" `
    -WindowStyle Hidden -PassThru
Start-Sleep -Milliseconds 500   # let CIM's process table catch up

try {
    $bogusPid = 999999   # astronomically unlikely to be a live pid
    $result = Get-ProcessKillInfo -Pids @($dummy.Id, $bogusPid)

    Assert-True ($result.Count -eq 1) "returns exactly 1 row (real pid kept, bogus pid skipped) -- got $($result.Count)"
    if ($result.Count -ge 1) {
        $row = $result[0]
        Assert-True ($row.Pid -eq $dummy.Id) "attributed row's Pid matches the spawned process ($($row.Pid) vs $($dummy.Id))"
        Assert-True ($row.Name -eq "powershell.exe") "Name captured as powershell.exe -- got '$($row.Name)'"
        Assert-True ($row.CommandLine -like "*Start-Sleep*") "CommandLine captured the real command line -- got '$($row.CommandLine)'"
    }
} finally {
    try { Stop-Process -Id $dummy.Id -Force -ErrorAction SilentlyContinue } catch {}
}

Write-Host ""
if ($failures -eq 0) {
    Write-Host "ALL PASS" -ForegroundColor Green
    exit 0
} else {
    Write-Host "$failures FAILURE(S)" -ForegroundColor Red
    exit 1
}
