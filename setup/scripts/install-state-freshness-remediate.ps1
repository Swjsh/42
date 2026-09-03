#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_StateFreshnessRemediate -- every 30 min, all day: direct-invocation
  remediation of state_freshness_audit's STALE-BY-SESSION entries (queue item
  STATE-FRESHNESS-AUTO-REMEDIATOR, 2026-09-03).

.DESCRIPTION
  WHY ITS OWN TASK, NOT A FLAG ON Gamma_HealthBeacon: setup/scripts/engine_health.py
  gained a --remediate flag (2026-09-03) that can call the same remediation function
  in-process, but run-engine-health.ps1 invokes engine_health.py with
  -TimeoutSec 45 every 1 minute (Gamma_HealthBeacon). A remediation pass can shell out
  to a producer that hits yfinance (refresh_levels_intraday / level_memory_producer /
  context_bundle_producer / confluence_producer / compute_ema_snapshot), each with its
  own internal 180s subprocess timeout -- one stale entry alone can exceed the beacon's
  45s budget, and Task Scheduler / Invoke-PythonHidden's 45s cap would kill the
  producer mid-write, turning a remediation attempt into a NEW corruption risk instead
  of a fix. So --remediate stays available on engine_health.py (for manual/ad-hoc use)
  but is DELIBERATELY never armed on the 1-min beacon -- this task runs the SAME
  underlying module (setup/scripts/state_freshness_remediate.py) standalone, on its
  own cadence, with a generous execution budget.

  setup/scripts/state_freshness_remediate.py itself is the safety boundary: per-writer
  explicit allowlist (11 of 19 manifest writers -- never heartbeat_core.py, never the
  futures live-trading scripts, never the kill-switch-anchor writers), STALE-BY-SESSION
  only (never MISSING/UNKNOWN/STALE-BY-AGE), a 60-min per-writer cooldown persisted to
  automation/state/state-freshness-remediate.json, its OWN internal RTH refusal
  (09:30-15:55 ET weekdays -- refuses before even running the audit), and verify-after
  via a fresh state_freshness_audit.audit() call rather than trusting the producer's
  exit code (C7). Real mode (not --dry-run): this task is meant to actually fix
  staleness, not just report it -- the RED/YELLOW state already IS the report.

  CADENCE: every 30 minutes, every day (weekday + weekend -- state files can go stale
  on any day the box is on; the script's own RTH refusal is what actually gates
  trading-hours safety, not the schedule).

  WIRING (cloned from install-auto-commit-candidates.ps1's every-N cadence pattern +
  install-first-live-day-review.ps1's flash-free hidden-launch chain):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- backtest\.venv\Scripts\pythonw.exe -> state_freshness_remediate.py
  Backtest-venv pythonw (not system pythonw) for the OUTER call: several allowlisted
  producers import pandas, and state_freshness_remediate.py invokes them with
  `sys.executable`, so the interpreter running THIS script must itself be the venv one
  for those producers to succeed when re-invoked.
  REAPER EXEMPTION: same verified pattern as install-auto-commit-candidates.ps1 --
  launched via backtest\.venv\Scripts\pythonw.exe (outside Stop-StaleClaudeProcesses's
  Name filter, plus the '.venv' path-match exemption) and each producer subprocess
  exits well under Stop-StaleClaudeProcesses's 5-min reap window.

  Guard: backtest/tests/test_state_freshness_remediate_2026_09_03.py (19/19, 3-mutation
  RED-proofed). To verify after running:
    Get-ScheduledTask -TaskName Gamma_StateFreshnessRemediate | Get-ScheduledTaskInfo
  REVERT: powershell setup\scripts\install-state-freshness-remediate.ps1 -Uninstall
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root     = "C:\Users\jackw\Desktop\42"
$taskName = "Gamma_StateFreshnessRemediate"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv  = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\state_freshness_remediate.py"

if (-not (Test-Path $pythonwVenv))   { throw "backtest venv pythonw.exe not found at $pythonwVenv" }
if (-not (Test-Path $sysPythonw))    { throw "system pythonw.exe not found at $sysPythonw" }
if (-not (Test-Path $runCmdHidden))  { throw "run_cmd_hidden.py not found at $runCmdHidden" }
if (-not (Test-Path $script))        { throw "state_freshness_remediate.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- backtest-venv pythonw -> state_freshness_remediate.py  (real mode, not --dry-run)
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonwVenv`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# Every 30 min, every day -- repeat trigger needs a base daily trigger + repetition.
$trigger = New-ScheduledTaskTrigger -Daily -At "00:00"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "00:00" -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Every 30 min, all day: setup/scripts/state_freshness_remediate.py direct-invokes producers for state_freshness_audit entries whose ONLY problem is STALE BY SESSION (never MISSING/UNKNOWN/STALE-BY-AGE). 11-writer explicit allowlist (never heartbeat_core.py, never futures live-trading scripts, never kill-switch-anchor writers). 60-min per-writer cooldown. Script's OWN internal RTH refusal (09:30-15:55 ET weekdays) gates trading-hours safety, not this schedule. Verify-after via fresh audit(), not producer exit code. Real mode. NOT the same as engine_health.py --remediate (that flag exists but is deliberately unarmed on the 1-min/45s-timeout Gamma_HealthBeacon -- see this script's own header). Guard: backtest/tests/test_state_freshness_remediate_2026_09_03.py. REVERT: powershell setup\scripts\install-state-freshness-remediate.ps1 -Uninstall" `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
