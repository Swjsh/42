#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_KeyLevelsSnapshot -- dated point-in-time snapshots of the LIVE
  level feed (J-directed SHIP-TONIGHT fire, 2026-07-23, following the full-engine
  replay finding: automation/state/key-levels.json is NEVER historically
  snapshotted -- refresh_levels_intraday.py / level_memory_producer.py overwrite
  it in place every fire, so no backtest can ever reconstruct what the engine
  actually SAW at entry time on a past day. The past is unrecoverable; this is
  the FORWARD-ONLY fix -- every day without it is a day of lost replay fidelity.

  Each fire runs setup/scripts/snapshot_key_levels.py, which:
    1. Copies automation/state/key-levels.json (if present) into
       automation/state/key-levels-history/<ET-date>/<HHMM>.json.
    2. Copies automation/state/key-levels-memory.json (the G11 level_memory merge
       input, if present) into
       automation/state/key-levels-history/<ET-date>/<HHMM>-memory.json.
    3. Skips the write (logs SKIP-UNCHANGED) when content is byte-identical to
       the day's latest same-kind snapshot -- avoids 4x/day churn on a quiet day.
    4. Fail-open: a missing source is a logged SKIP, never a crash; always
       exits 0 (OP-25/C7).

  CADENCE -- 4 fires/day weekdays (premarket-final / open / midday drift / EOD):
    08:35 ET (06:35 MT)  -- premarket-final, right after Gamma_Premarket (08:30)
    09:30 ET (07:30 MT)  -- open, first HeartbeatCore tick
    12:00 ET (10:00 MT)  -- midday drift
    15:50 ET (13:50 MT)  -- EOD, before Gamma_EodFlatten* (15:55)

  TZ RULE: this rig is Mountain Time (ET = local + 2h, year-round -- both zones
  share the same DST calendar). NEVER pass an ET literal to -At.

  CADENCE PATTERN: 4x `-Weekly -DaysOfWeek Monday..Friday -At <MT time>` triggers
  registered together on ONE task (matches install-daily-brief.ps1's DailyTrigger
  pattern, just four of them) -- NOT a bare one-time/interval trigger (a trigger
  with no recurrence spec goes dark after the install day --
  project_scheduled_task_onetime_trigger_dark).

  REAPER EXEMPTION -- verified pattern (setup/scripts/_shared.ps1's
  Stop-StaleClaudeProcesses reaps stale python.exe references to this repo every
  ~3-5 min unless EXEMPT_DAEMONS matches): 'pythonw.exe' sits outside
  Stop-StaleClaudeProcesses's Win32_Process Name filter entirely (primary
  exemption, independent of any string match), PLUS this task is launched via
  backtest\.venv\Scripts\pythonw.exe, whose CommandLine also contains the literal
  substring 'backtest\.venv' (an existing $EXEMPT_DAEMONS entry, defense in
  depth) -- same verified shape as install-ledger-archive.ps1 / install-crypto-
  twin.ps1 / install-twin-sentinel.ps1.

  WIRING PATTERN (flash-free, matches install-ledger-archive.ps1 exactly):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> snapshot_key_levels.py
  Single-hop chain -- native Python script, no .ps1 wrapper needed, no --live
  flag, no order path, read-only on every source it copies.

  To verify after running: Get-ScheduledTask -TaskName Gamma_KeyLevelsSnapshot | Get-ScheduledTaskInfo
  REVERT: powershell setup\scripts\install-key-levels-snapshot.ps1 -Uninstall
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root      = "C:\Users\jackw\Desktop\42"
$taskName  = "Gamma_KeyLevelsSnapshot"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$venvDir      = Join-Path $root "backtest\.venv"
$venvSitePkgs = Join-Path $root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\snapshot_key_levels.py"

if (-not (Test-Path $sysPythonw))   { throw "system pythonw.exe not found at $sysPythonw" }
if (-not (Test-Path $venvSitePkgs)) { throw "backtest venv site-packages not found at $venvSitePkgs" }
if (-not (Test-Path $runCmdHidden)) { throw "run_cmd_hidden.py not found at $runCmdHidden" }
if (-not (Test-Path $script))       { throw "snapshot_key_levels.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- system pythonw (venv activated via --env) -> snapshot_key_levels.py
# 2026-09-03 VENV-PYTHONW-REDIRECTS-TO-CONSOLE-PYTHON recipe (a): inner target changed
# from $pythonwVenv to $sysPythonw, venv activated via --env instead -- see
# install-fee-recalibrate.ps1's WIRING comment for the full root cause.
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" " + `
    "--env VIRTUAL_ENV=`"$venvDir`" --env PYTHONPATH=`"$venvSitePkgs`" -- `"$sysPythonw`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# 4 weekday fires: 08:35 / 09:30 / 12:00 / 15:50 ET -> 06:35 / 07:30 / 10:00 / 13:50 MT.
$days = @('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')
$triggers = @(
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At "06:35"
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At "07:30"
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At "10:00"
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At "13:50"
)

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
    -Trigger $triggers `
    -Settings $settings `
    -Principal $principal `
    -Description "Dated point-in-time snapshots of the LIVE level feed (J SHIP-TONIGHT fire, 2026-07-23, following the full-engine replay finding that key-levels.json is never historically snapshotted -- no backtest can reconstruct what the engine SAW at entry time on a past day; forward-only fix). Fires 4x weekdays: 08:35/09:30/12:00/15:50 ET (06:35/07:30/10:00/13:50 MT). snapshot_key_levels.py copies key-levels.json + key-levels-memory.json into automation/state/key-levels-history/<ET-date>/<HHMM>[-memory].json, skipping the write (SKIP-UNCHANGED) when content is byte-identical to the day's latest same-kind snapshot. Pure Python, `$0, read-only on sources, always exits 0. Reaper-exempt: pythonw.exe outside Stop-StaleClaudeProcesses's Name filter, plus backtest\.venv path match (defense in depth). Guard: backtest/tests/test_snapshot_key_levels.py." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
