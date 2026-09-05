#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_FuturesBrokerProbe -- the Tastytrade SANDBOX futures dry-run probe.

  PURPOSE: 23:05 ET daily (re-timed 2026-08-26 out of quiet_mode.py's blackout into the
  LOUD maintenance band; was 18:05 ET just after the CME reopen -- TZ-DRIFT-DORMANT-9 fix
  2026-09-03: this installer still said the pre-08-26 time, SCHEDULED-TASKS.md is the live
  truth, kept in sync here), futures_broker_probe.py runs ONE
  broker-side dry_run=True MES order against cert account 5WW73759 -- routes NOTHING,
  fills NOTHING, sandbox only, no live venue -- and appends the verdict to
  automation/state/futures/broker-probe.jsonl.

  WHY: the 2026-07-07 "Rejected: Session offline" was recorded as "the sandbox is not
  provisioned for futures", but re-probing 2026-08-09 returned tif.futures_session_not_active
  (a MARKET-HOURS error) with is_futures_enabled=true. Both fit "futures are fine, the
  session simply was not active", so the July diagnosis is UNCONFIRMED. H1 (not approved)
  predicts the dry run still fails while the session is OPEN; H2 (session artifact)
  predicts it validates with a buying-power effect and no errors.

  INTERPRETER -- the 2026-08-09 fix. This runs on the BACKTEST VENV, not a system python.
  The first registration pointed at AppData\Local\Programs\Python\Python313, which does
  NOT carry the tastytrade SDK: the probe ran clean by hand and then failed its very first
  scheduled fire with ModuleNotFoundError. This box has THREE pythons and only the
  Microsoft Store one had the SDK -- "it works when I run it" proved nothing about the
  interpreter the scheduler actually uses. The SDK is now pinned into the venv at 12.4.1,
  the version the July order-path proof was obtained against (pip resolves 13.x by
  default, a major bump that would silently change the SDK surface the entire futures
  order path depends on).

  Credentials load from the gitignored .env.tastytrade, are never printed, never logged.

  DELETE THIS TASK once the verdict is conclusive -- it is a diagnostic, not a standing
  instrument.

  VERIFY:  Get-ScheduledTask -TaskName Gamma_FuturesBrokerProbe | Get-ScheduledTaskInfo
  REVERT:  Unregister-ScheduledTask -TaskName "Gamma_FuturesBrokerProbe" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$script       = Join-Path $root "setup\scripts\futures_broker_probe.py"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath   = Join-Path $root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName     = "Gamma_FuturesBrokerProbe"

foreach ($p in @($vbs, $script, $sysPythonw, $runCmdHidden)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw (launcher only) -> run_cmd_hidden.py
#   -- BACKTEST VENV pythonw -> futures_broker_probe.py
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# 21:05 MT = 23:05 ET (re-timed 2026-08-26 into the quiet-mode LOUD maintenance band).
$trigger = New-ScheduledTaskTrigger -Daily -At "21:05"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description ("Tastytrade SANDBOX futures dry-run probe (routes nothing, fills nothing, no " + `
    "live venue). Settles whether cert account 5WW73759 is genuinely un-provisioned for futures " + `
    "(H1) or whether the 2026-07-07 Session-offline reject was a market-hours artifact (H2) -- " + `
    "the 2026-08-09 re-probe returned tif.futures_session_not_active with is_futures_enabled=true, " + `
    "making the July diagnosis UNCONFIRMED. Fires 23:05 ET daily (re-timed 2026-08-26 into " + `
    "the quiet-mode LOUD maintenance band; was 18:05 ET just after the CME reopen); " + `
    "appends one row to automation/state/futures/broker-probe.jsonl; verdict surfaces on HOME. " + `
    "Runs on the BACKTEST VENV with tastytrade pinned 12.4.1 (the version the July order-path " + `
    "proof used); the first registration pointed at a system python lacking the SDK and failed " + `
    "its first fire with ModuleNotFoundError. Creds from the gitignored .env.tastytrade, never " + `
    "logged. DELETE once the verdict is conclusive. REVERT: Unregister-ScheduledTask -TaskName " + `
    "'Gamma_FuturesBrokerProbe' -Confirm:`$false") | Out-Null

Write-Host "Registered $taskName"
$info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
if ($info -and $info.NextRunTime) {
    Write-Host ("  NextRun ET: {0}" -f ([System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)).ToString("yyyy-MM-dd HH:mm"))
}
(Get-ScheduledTask -TaskName $taskName).State
