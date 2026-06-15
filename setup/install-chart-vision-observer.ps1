#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_ChartVisionObserver scheduled task -- fires every 6 min during 09:30-15:55 ET
  weekdays. OBSERVER-ONLY layer that captures a SPY 5m chart screenshot via TV MCP, sends to
  haiku vision, emits 6-field JSON to automation/state/vision-observations.jsonl. EOD grader at
  16:05 pairs vs heartbeat decisions + grades vs next-bar truth.

  AUTHORIZATION: J 2026-05-18 ET, in chat: "decisions that benefit the engine do not need
  my approval ... trading day is over, get to work adding and testing this extensively"

  CADENCE CHOICE: 6 min (every 2nd heartbeat tick) per VISION-OBSERVER-PROTOCOL.md §6 cost
  table -- 64 fires/day × $0.05/tick × 21 trading days = ~$67/mo, within OP-3 $100/mo budget.
  Full-cadence (every 3 min) = $133/mo = OVER BUDGET; deferred until vision shows signal worth
  the cost in first-week observation.

  Hidden window per OP-27 (wscript + run_hidden.vbs).

.NOTES
  Wrapper script: setup\scripts\run-chart-vision-observer.ps1
  Prompt:         automation\prompts\chart_vision_observer.md
  Grader:         backtest\autoresearch\vision_observer_grader.py (wired into eod_deep stage 4a.7)
  Protocol doc:   docs\VISION-OBSERVER-PROTOCOL.md
  Candidate:      strategy\candidates\2026-05-17-vision-chart-observer.md
  Cost ceiling:   $80/mo (auto-disable not yet wired -- Stage 2 deliverable)
  Revert:         Run with -Uninstall switch
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$taskName = "Gamma_ChartVisionObserver"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    } else {
        Write-Host "$taskName not registered -- nothing to do."
    }
    return
}

$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\run-chart-vision-observer.ps1"
$vbsWrapper = "C:\Users\jackw\Desktop\42\setup\scripts\run_hidden.vbs"

# Verify scaffold files exist before registering
$requiredFiles = @(
    $scriptPath,
    $vbsWrapper,
    "C:\Users\jackw\Desktop\42\automation\prompts\chart_vision_observer.md",
    "C:\Users\jackw\Desktop\42\backtest\autoresearch\vision_observer_grader.py"
)
foreach ($f in $requiredFiles) {
    if (-not (Test-Path $f)) {
        throw "Required scaffold file missing: $f"
    }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Removed existing $taskName for re-registration."
}

# Trigger: daily at 09:30 ET, then repeat every 6 min for 6h 25min (covers 09:30-15:55).
# Daily trigger so it recurs each day. Weekday filtering is enforced at runtime by the
# wrapper's Test-WeekDay gate (and Test-HolidayFromAlpaca).
$trigger = New-ScheduledTaskTrigger -Daily -At "09:30"

# Use the canonical wscript wrapper per OP-27 (no window flash)
$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$vbsWrapper`" `"$scriptPath`""

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "Chart Vision Observer (L3 'see like a person' layer) -- fires every 6 min 09:30-15:55 ET wd. Captures SPY 5m chart screenshot via TV MCP, sends to haiku vision, emits 6-field JSON to vision-observations.jsonl. OBSERVER-ONLY (no orders, no production state mutation). EOD grader pairs vs heartbeat. Cost ~`$3.20/day = `$67/mo at half cadence. Hidden window per OP-27. Auth: J 2026-05-18." | Out-Null

# Apply repetition post-registration (same pattern as heartbeat in install-tasks.ps1)
$task = Get-ScheduledTask -TaskName $taskName
$task.Triggers[0].Repetition.Interval = "PT6M"   # every 6 minutes (half cadence)
$task.Triggers[0].Repetition.Duration = "PT6H25M"  # 09:30 → 15:55 ET window
# Weekday restriction is enforced at runtime by the wrapper's Test-WeekDay gate.
Set-ScheduledTask -TaskName $taskName -Trigger $task.Triggers[0] | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host ""
Write-Host "=== Registered $taskName ==="
Write-Host "  State:        $((Get-ScheduledTask -TaskName $taskName).State)"
Write-Host "  Next run:     $($info.NextRunTime)"
Write-Host "  Cadence:      every 6 min, 09:30-15:55 ET weekdays (wrapper enforces weekday)"
Write-Host "  Cost ceiling: ~`$3.20/day = ~`$67/mo (within OP-3 budget)"
Write-Host "  Revert:       .\install-chart-vision-observer.ps1 -Uninstall"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Smoke-fire now (will exit cleanly via market-hours gate if outside RTH):"
Write-Host "     powershell.exe -ExecutionPolicy Bypass -File `"$scriptPath`""
Write-Host "  2. Verify zero window leaks:"
Write-Host "     python C:\Users\jackw\Desktop\42\setup\scripts\audit_window_leak_compliance.py"
Write-Host "  3. After first live trading day, inspect:"
Write-Host "     automation\state\vision-observations.jsonl  (raw observations)"
Write-Host "     analysis\vision-vs-heartbeat-{date}.json  (EOD grader output)"
