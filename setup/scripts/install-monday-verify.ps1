#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_MondayVerify -- WEEKEND-TWELVE Next-Twelve #6: the mechanical post-close
  verify sweep for the five weekend-shipped MONDAY-VERIFY checklist items (WS7 live-watch,
  WS6 regime stamp, WS3 level hysteresis, WS11 core recency, theta cockpit) plus the WS1
  Monday-preview-vs-actuals diff.

.DESCRIPTION
  Each fire runs setup/scripts/monday_verify.py, which reads (never writes any TRADING
  state -- report-only, per OP-25/C7):
    automation/state/core-decisions.jsonl, automation/state/fleet/*/decisions.jsonl,
    automation/state/live-watch.json + logs/live-watch.stdout.log,
    automation/state/regime-stamp.json + today-bias.json,
    automation/state/logs/level-refresh-<date>.log,
    automation/state/core-strategy-recency.json (best-effort live re-run, --no-replay,
    bounded 90s timeout),
    automation/state/theta-clock.json + theta-clock/theta-clock-<date>.jsonl,
    automation/state/aggressive/params.json + fleet/*/circuit-breaker.json,
    analysis/deep-research/MONDAY-PREVIEW-2026-08-03.md's JSON sidecar.
  Writes automation/state/monday-verify.json (full detail) + prepends ONE dated block to
  automation/overnight/STATUS.md (newest-first, matches every other producer) + appends a
  loud transition-only line under STATUS.md's "## Known broken" for any item newly RED this
  run (byte-for-byte the gate_expiry_check.py / guard_runner_slow.py pattern).

  NEVER blocks, NEVER kills, NEVER places an order or edits engine/params/doctrine -- pure
  report. Fail-open throughout: one check's exception never sinks the other five, and
  main() itself is wrapped so the script always exits 0.

  CADENCE -- DAILY (all 7 days, like Gamma_GateExpiryCheck's own "nightly checker" cadence,
  not weekday-gated like an RTH watcher) at 16:15 ET post-close (after Gamma_EodFlatten
  15:55 and live_watch's own 16:05-16:10 CLOSED-transition window):
    14:15 MT = 16:15 ET.
  On a non-trading day every check correctly self-reports NOT_EXERCISED (verified live via
  --dry-run against the real Saturday 2026-08-01 state before this task registered) -- firing
  daily is deliberate, not a bug: a holiday/weekend fire is a cheap, harmless no-op.

  TZ RULE: this rig is Mountain Time (ET = local + 2h). NEVER pass an ET literal to -At.

  WIRING (flash-free, matches install-live-watch.ps1 / install-theta-clock.ps1 exactly):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> monday_verify.py
  monday_verify.py ALSO carries its own OP-27 L41 headless stdio redirect (header copied
  verbatim from setup/guard_runner_slow.py) -- defense in depth against console popups.

  On demand (any time): backtest\.venv\Scripts\python.exe setup\scripts\monday_verify.py
                          [--date YYYY-MM-DD] [--dry-run]
  Verify after running: Get-ScheduledTask -TaskName Gamma_MondayVerify | Get-ScheduledTaskInfo
  REVERT: powershell setup\scripts\install-monday-verify.ps1 -Uninstall
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root     = "C:\Users\jackw\Desktop\42"
$taskName = "Gamma_MondayVerify"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs         = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script      = Join-Path $root "setup\scripts\monday_verify.py"
$etz         = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')

foreach ($p in @($vbs, $pythonwVenv, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> backtest venv pythonw -> monday_verify.py
$wscriptArgs = "//nologo `"$vbs`" `"$pythonwVenv`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# 14:15 MT = 16:15 ET daily (all 7 days -- see .DESCRIPTION cadence note).
$trigger = New-ScheduledTaskTrigger -Daily -At "14:15"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("WEEKEND-TWELVE Next-Twelve #6 (2026-08-01): mechanical Monday-verify " + `
    "sweep -- WS7 live-watch, WS6 regime stamp, WS3 level hysteresis, WS11 core recency, " + `
    "theta cockpit greeks-source, WS1 preview-vs-actuals diff. Daily 14:15 MT (16:15 ET), " + `
    "post-close. Writes automation/state/monday-verify.json + a dated STATUS.md block + " + `
    "'## Known broken' lines for newly-RED items. NEVER blocks/kills/trades -- report only, " + `
    "fail-open (NOT_EXERCISED when a precondition never fired). " + `
    "Guard: backtest/tests/test_monday_verify_2026_08_01.py.") `
    -Force | Out-Null

Write-Host "Registered $taskName (14:15 MT = 16:15 ET daily, all 7 days)"

# --- POST-REGISTRATION ASSERTIONS (OP-33b: registered != firing) -------------------------
$t = Get-ScheduledTask -TaskName $taskName
if ($t.State -eq "Disabled") { Write-Error "$taskName registered but DISABLED"; exit 1 }
$trigType = $t.Triggers[0].CimClass.CimClassName
if ($trigType -ne "MSFT_TaskDailyTrigger") {
    Write-Error "$taskName trigger is $trigType, expected MSFT_TaskDailyTrigger"
    exit 1
}
$info = Get-ScheduledTaskInfo -TaskName $taskName
if (-not $info.NextRunTime) { Write-Error "$taskName has NO NextRunTime -- it will never fire"; exit 1 }
$nextEt = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
Write-Host ("Assertions PASS: State={0}, Trigger={1}, NextRun ET={2}" -f `
    $t.State, $trigType, $nextEt.ToString("yyyy-MM-dd HH:mm"))
Write-Host "Test now: Start-ScheduledTask -TaskName $taskName"
Write-Host "Audit:    python setup\scripts\audit_scheduled_tasks.py   (expect no VISIBLE_WINDOW)"
