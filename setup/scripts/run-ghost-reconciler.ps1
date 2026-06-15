#requires -Version 5.1
<#
.SYNOPSIS
  Ghost order reconciler -- fires every 1 min during 09:30-15:55 ET.
  Detects ENTER decisions logged to decisions.jsonl that have no matching
  Alpaca order placed within ±180s. Alert-only V1 per OP-21 watch-first.
  Per J directive 2026-05-22 09:25 ET ("ship reconcile").
#>
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_shared.ps1"

$task = "ghost-reconciler"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) { exit 0 }
if (Test-HolidayFromAlpaca) { exit 0 }
if (-not (Test-MarketHours -Et $et -StartHour 9 -StartMin 30 -EndHour 15 -EndMin 55)) { exit 0 }

Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('HH:mm:ss'))"

$result = Invoke-PythonHidden `
    -ScriptPath "setup\scripts\ghost_order_reconciler.py" `
    -ArgList @() `
    -TaskName $task `
    -TimeoutSec 30

$exit = $result.ExitCode
if ($exit -eq 2) {
    Write-TaskLog -TaskName $task -Message "GHOST_DETECTED -- STATUS.md updated"
} elseif ($exit -eq 0) {
    # Quiet success — only log every 10 min to avoid log spam
    $min = $et.Minute % 10
    if ($min -eq 0) {
        Write-TaskLog -TaskName $task -Message "clean (no ghosts in window)"
    }
} else {
    Write-TaskLog -TaskName $task -Message "ERROR exit=$exit"
}

exit 0  # never fail the task even if reconciler had an error
