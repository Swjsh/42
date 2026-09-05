# install-chop-meter.ps1 -- register Gamma_ChopMeter (LANE 5 "don't trade chop", 2026-08-06).
#
# Runs setup/scripts/chop_exposure_meter.py once per evening: for today's real engine entries
# (fills-ledger.jsonl) it counts ordinal>=4 entries (CAP-3's forward-clock recorder), entries
# against V-d1, entries with zero completed structure events, rr<0.70 range-compression
# entries, worst consecutive-loss runs (CONSEC4's recorder), and the fleet-POOLED REALIZED
# intraday P&L floor + would-a--$600-breaker-have-latched (BRK600's forward-evidence surface,
# which the live per-account equity-based daily_loss_guard.py does NOT provide).
#
# WHY: J's directive for next week (2026-08-06): "don't trade chop." The day-level chop
# classifier is DEAD (20.9% vs 39.1% baseline); this is the honest replacement -- per-trade
# measurement so "did we trade chop today" is a glance in firm-brief.md, not a question.
# MEASUREMENT ONLY: never blocks an entry, never touches params, never places orders.
# Contract frozen in analysis/recommendations/chop-defense-prereg-2026-08-06.json @ 5737488a.
#
# Writes automation/state/chop-exposure-{date}.json + chop-exposure-last.json (the -last
# snapshot is what firm_brief.render_chop_lines reads, fail-open).
#
# TIME: 14:08 MOUNTAIN = 16:08 ET. This box runs Mountain; ET = local + 2 (CLAUDE.md).
# Slot is AFTER Gamma_BrokerFills (16:05 ET refreshes fills-ledger.jsonl) and BEFORE
# Gamma_FirmBrief (16:10 ET renders the line) -- the meter must sit between them.
# One network read: a single paged SPY 5Min SIP request (probed live arm key, L234);
# on fetch failure the bar-dependent columns render n/a (bars_degraded), never crash.
#
# Windowless wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py
#   --cwd <repo> -- backtest-venv-pythonw (C8/L41). 2026-08-08 VBS-WRAPPER-EXIT-CODE-
# BLIND-SPOT migration: run_cmd_hidden.py runs the child SYNCHRONOUSLY and logs the
# real exit code (was fire-and-forget, LastTaskResult always fake-0). One of the 31
# direct-invocation tasks named in the 2026-08-07 audit (queue.md).
$ErrorActionPreference = "Stop"
$Root = "C:\Users\jackw\Desktop\42"; $ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName = "Gamma_ChopMeter"
$pythonw = Join-Path $Root "backtest\.venv\Scripts\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath = Join-Path $Root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"
$worker = Join-Path $ScriptsDir "chop_exposure_meter.py"
foreach ($p in @($pythonw, $runExeHidden, $sysPythonw, $runCmdHidden, $worker)) {
  if (-not (Test-Path $p)) { Write-Error "missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$Root`" -- `"$sysPythonw`" `"$worker`""
# DailyTrigger, NOT a one-time/interval trigger (scar: project_scheduled_task_onetime_trigger_dark).
# Weekend fires are harmless: a no-entry day writes an honest "no engine entries" artifact.
$trigger = New-ScheduledTaskTrigger -Daily -At "14:08" -DaysInterval 1
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$desc = "CHOP EXPOSURE METER nightly (LANE 5 2026-08-06): today's real entries scored for " + `
  "ordinal>=4 / against-V-d1 / zero-structure / rr<0.70 + consec-loss runs + the fleet-pooled " + `
  "REALIZED floor & BRK600 would-trip (forward-evidence recorders for the CAP3/CONSEC4/BRK600 " + `
  "preregs). Writes automation/state/chop-exposure-{date}.json + -last.json; firm_brief " + `
  "renders the line. MEASUREMENT ONLY -- blocks nothing, places nothing. Guard: " + `
  "backtest/tests/test_chop_exposure_meter.py. Revert: Unregister-ScheduledTask Gamma_ChopMeter."
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description $desc | Out-Null

# ---- VERIFY, DON'T CLAIM (OP-33): registered + enabled + real daily trigger + will fire.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
$trigType = $t.Triggers[0].CimClass.CimClassName
if ($trigType -ne "MSFT_TaskDailyTrigger") { Write-Error "$TaskName trigger is $trigType, expected MSFT_TaskDailyTrigger"; exit 1 }
if ($null -eq $info.NextRunTime) { Write-Error "$TaskName has a NULL NextRunTime -- it would never fire"; exit 1 }
Write-Output "OK: Registered $TaskName  State=$($t.State)  Trigger=$trigType  NextRun=$($info.NextRunTime)"
