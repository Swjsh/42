#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_XspSpreadRecorder -- every 5 min, 09:35-15:55 ET weekdays, the
  quote-recorder measurement the XSP work-order box names as the one thing that
  would settle "is XSP worth a lane" (work order §2b, 2026-09-03).

.DESCRIPTION
  markdown/planning/OPUS-WORK-ORDER-2026-09.md's XSP box: "The one measurement that
  would settle it: XSP vs SPY NBBO spread at matched ATM strikes, every 5 min across
  3+ RTH sessions, expressed as $/round-trip on a 3-lot." The 2026-09-02 single live
  sample flagged that the two strikes it used may not have been moneyness-matched,
  because XSP has no equity spot feed to confirm against. This task runs
  setup/scripts/xsp_spread_recorder.py, which resolves each side's TRUE ATM strike
  independently every cycle (SPY from its own equity spot; XSP via put-call parity
  on its own chain, labelled + fallback-safe) and appends one row to
  analysis/xsp/xsp-spread-tape-<date>.jsonl.

  READ-ONLY market-data probe: two GET calls per cycle (SPY equity quote + a
  batched option NBBO call), zero POST/DELETE/order endpoints anywhere in the
  script. Never imports and is never imported by any live-order-path module. Fails
  open on every missing quote (never fabricates) -- see the script's own docstring.

  Runs `--once` every 5 minutes ALL DAY (like Gamma_LevelRefresh) -- the script's
  own internal RTH gate (rth_only=True by default, 09:35-15:55 ET weekdays) makes
  every off-hours fire a fast no-op (skip_reason recorded, no network call), so the
  trigger stays simple and this task never needs day-of-week/time-window math in
  PowerShell.

  WIRING PATTERN (flash-free, cloned from install-first-live-day-review.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> xsp_spread_recorder.py --once
  System pythonw (no venv): the script is pure stdlib + setup/scripts/et_clock --
  verified live this session, no pandas/numpy import anywhere in it.

  Output:
    analysis/xsp/xsp-spread-tape-<date>.jsonl -- one row per 5-min cycle
    automation/state/xsp-spread-recorder-status.json -- this script's own health
    surface (never engine state; nothing on the trading path reads this file).

  Per CLAUDE.md OP-3 ($0, pure Python stdlib), OP-25 (fail loud, never silent),
  OP-33 (visibility is the product). Guard:
  backtest/tests/test_xsp_spread_recorder_2026_09_03.py.
  REVOKE: Unregister-ScheduledTask -TaskName Gamma_XspSpreadRecorder -Confirm:$false
#>

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\xsp_spread_recorder.py"
$taskName     = "Gamma_XspSpreadRecorder"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

foreach ($p in @($vbs, $sysPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`" --once"

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# Every 5 min, all day, all week -- the script's own internal RTH gate (09:35-15:55
# ET weekdays) does the real filtering, matching Gamma_LevelRefresh's convention.
$startBoundary = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $startBoundary `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration ([System.TimeSpan]::FromDays(365 * 10))

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Every 5 min (self-gated to 09:35-15:55 ET weekdays): XSP vs SPY " + `
    "NBBO spread at INDEPENDENTLY-resolved ATM strikes (SPY from equity spot, XSP " + `
    "via put-call parity on its own chain, labelled + fallback-safe) -- the work " + `
    "order's XSP box measurement. READ-ONLY (2 GET calls/cycle, no order endpoint " + `
    "anywhere in the script). Writes analysis/xsp/xsp-spread-tape-<date>.jsonl. " + `
    "Fails open on every missing quote -- never fabricates. `$0. Guard: " + `
    "backtest/tests/test_xsp_spread_recorder_2026_09_03.py. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_XspSpreadRecorder -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- every 5 min, self-gated to 09:35-15:55 ET weekdays."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
