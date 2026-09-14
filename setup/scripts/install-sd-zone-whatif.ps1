#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_SdZoneWhatIf -- headless, $0 SD-ZONE WHAT-IF shadow lane
  (GOAL-SD-LIQUIDITY-ZONES-2026-09-11 item f, prereg-sd-zone-anchor-promotion-
  2026-09-12.md section 9).

.DESCRIPTION
  Runs setup/scripts/sd_zone_whatif.py for TODAY (et_clock default): reads the day's
  intraday zone snapshots (journal/sd-zones-archive/intraday/{day}/*.json, written by
  Gamma_SdZonesProducer) + real SPY/option bars, plays every zone touch through a
  pre-registered grid of confirmations x exit shapes x strikes via the SAME production
  exit-stack decision core (backtest/lib/exit_manager_walk.walk_exit_manager) any real
  fill would use, and writes analysis/sd-zone-whatif/{ledger.jsonl,summary.json,SUMMARY.md}.

  Descriptive/diagnostic only -- see prereg section 9: this task NEVER places an order,
  NEVER writes key-levels.json/params*.json/automation/state/fleet/*, and cannot itself
  promote or kill SD_ZONE (that stays governed by the prereg's own section 3-6 forward-clock
  gate + G1-G6 gates, unchanged by this lane).

  WIRING (cloned from install-sd-zones-producer.ps1 -- same reasoning applies verbatim):
  system pythonw (GUI subsystem, no console) + PYTHONPATH onto the backtest venv's
  site-packages via run_py_venv_hidden.py (pandas + requests-free REST calls).
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_py_venv_hidden.py ->
      sd_zone_whatif.py

  SCHEDULE: 16:20 ET weekdays (14:20 MT -- box runs Mountain time), AFTER Gamma_EodFlatten
  (15:55) and well after the day's SD zones have had their full RTH window to develop --
  running once at end-of-day (rather than every 15 min like the producer) is deliberate:
  the whole day's price action + option bars must exist before a same-day replay is
  meaningful, and Alpaca 1-min OPRA option bars for 0DTE contracts are reliably available
  shortly after the close.

  Per CLAUDE.md OP-25 (fail loud) + OP-3 ($0). Guard: backtest/tests/test_sd_zone_whatif.py.
  To disable: Unregister-ScheduledTask -TaskName Gamma_SdZoneWhatIf -Confirm:$false
#>

$ErrorActionPreference = "Stop"
$Root       = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName   = "Gamma_SdZoneWhatIf"

$sysPythonw      = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runExeHidden    = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$runPyVenvHidden = Join-Path $ScriptsDir "run_py_venv_hidden.py"
$worker          = Join-Path $ScriptsDir "sd_zone_whatif.py"

foreach ($p in @($sysPythonw, $runExeHidden, $runPyVenvHidden, $worker)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript //nologo run_exe_hidden.vbs <sys-pythonw> run_py_venv_hidden.py <sd_zone_whatif.py>
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runPyVenvHidden`" `"$worker`""

# 14:20 LOCAL (Mountain) = 16:20 ET weekdays, once/day.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:20"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Headless, `$0 SD-ZONE WHAT-IF shadow lane (GOAL-SD-LIQUIDITY-ZONES-2026-09-11 item f). Plays each day's zone touches through a pre-registered confirmation x exit x strike grid via the real production exit-stack walker; writes analysis/sd-zone-whatif/. Descriptive-only, never orders, never key-levels.json/params*.json. Weekly Mon-Fri 14:20 MT (16:20 ET)." `
    | Out-Null

# ---- VERIFY, DON'T CLAIM (OP-33): registered + enabled + will fire.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
$trigType = $t.Triggers[0].CimClass.CimClassName
if ($trigType -ne "MSFT_TaskWeeklyTrigger") { Write-Error "$TaskName trigger is $trigType, expected MSFT_TaskWeeklyTrigger"; exit 1 }
if ($null -eq $info.NextRunTime) { Write-Error "$TaskName has a NULL NextRunTime -- it would never fire"; exit 1 }
Write-Output "OK: Registered $TaskName  State=$($t.State)  Trigger=$trigType  NextRun=$($info.NextRunTime)"
