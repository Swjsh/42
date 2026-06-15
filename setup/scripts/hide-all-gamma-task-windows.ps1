#requires -Version 5.1
<#
.SYNOPSIS
  Idempotent fix-up: hide console windows for all Gamma_* scheduled tasks.

.DESCRIPTION
  Many Gamma_* tasks invoke powershell.exe without -WindowStyle Hidden or
  -NonInteractive, causing brief console-window flashes when Task Scheduler
  fires them. This script:

    1. Lists all Gamma_* Ready tasks
    2. For each task whose Action.Execute is powershell.exe AND missing
       -WindowStyle Hidden, rewrites the Action with the hidden flags
       PREPENDED (original arguments preserved exactly)
    3. Logs what changed

  Idempotent: re-running is safe; already-hidden tasks are skipped.

  Does NOT touch:
    - Disabled tasks (no need)
    - Tasks whose Execute is NOT powershell.exe (cmd.exe, exe, etc. — separate decision)
    - Gamma_LaunchTV's TradingView launch itself (that GUI app must remain visible — but the
      wrapper console gets hidden)
#>
[CmdletBinding()] param([switch]$DryRun, [switch]$ShowDiff)
$ErrorActionPreference = "Stop"

$logDir = "C:\Users\jackw\Desktop\42\automation\state\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir ("hide-gamma-windows-" + (Get-Date -Format "yyyy-MM-dd") + ".log")
$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

function Write-Log([string]$msg) {
    $line = "[$now] $msg"
    Add-Content -Path $logFile -Value $line
    Write-Host $line
}

Write-Log "hide-gamma-windows: START (DryRun=$DryRun)"

$tasks = Get-ScheduledTask -TaskName "Gamma_*"
$skippedDisabled = 0
$skippedAlreadyHidden = 0
$skippedNotPowershell = 0
$updated = 0
$failed = 0

foreach ($task in $tasks) {
    $name = $task.TaskName

    if ($task.State -eq "Disabled") {
        $skippedDisabled++
        continue
    }

    $actions = @($task.Actions)
    if ($actions.Count -ne 1) {
        Write-Log "  SKIP $name -- has $($actions.Count) actions (not handled)"
        $skippedNotPowershell++
        continue
    }

    $action = $actions[0]
    $exec = $action.Execute
    $arg = $action.Arguments

    if ($exec -notlike "*powershell.exe*") {
        Write-Log "  SKIP $name -- Execute is $exec (not powershell.exe)"
        $skippedNotPowershell++
        continue
    }

    if ($arg -like "*-WindowStyle Hidden*" -or $arg -like "*-WindowStyle hidden*") {
        $skippedAlreadyHidden++
        continue
    }

    # Construct the new argument: prepend hidden+non-interactive flags
    # Note: if -NoProfile already present, don't duplicate; otherwise add
    $newFlags = "-WindowStyle Hidden -NonInteractive"
    if ($arg -notlike "*-NoProfile*") {
        $newFlags = "-NoProfile $newFlags"
    }
    $newArg = "$newFlags $arg".Trim()

    Write-Log "  UPDATE $name"
    if ($ShowDiff) {
        Write-Log "    old args: $arg"
        Write-Log "    new args: $newArg"
    }

    if ($DryRun) {
        continue
    }

    try {
        $newAction = New-ScheduledTaskAction -Execute $exec -Argument $newArg
        Set-ScheduledTask -TaskName $name -Action $newAction | Out-Null
        $updated++
    } catch {
        Write-Log "  FAIL $name -- $_"
        $failed++
    }
}

Write-Log "hide-gamma-windows: END"
Write-Log "  updated:           $updated"
Write-Log "  skipped (disabled): $skippedDisabled"
Write-Log "  skipped (already hidden): $skippedAlreadyHidden"
Write-Log "  skipped (not powershell): $skippedNotPowershell"
Write-Log "  failed:            $failed"
