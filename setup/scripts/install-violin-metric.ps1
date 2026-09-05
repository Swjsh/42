# install-violin-metric.ps1 -- register Gamma_ViolinMetric (LANE-4, 2026-08-03).
#
# Runs setup/scripts/violin_metric.py --nightly once per weekday evening: measures, for the
# completed session, every level the TAPE respected (frozen defn v1-2026-08-03) vs every
# level the ENGINE had in levels_active AT THAT MOMENT -- the per-source coverage ratio +
# first-appearance latency ("playing these key levels like a violin" as a NUMBER that
# trends). Writes automation/state/violin-metric.json + upserts
# analysis/violin/violin-history.jsonl. $0, read-only + REST bars, no LLM, no orders.
#
# WHY: on 2026-08-03 the final premarket low 749.33 was respected at 09:25-09:29 and entered
# levels_active at 09:44:03 (delayed-SIP frame, fixed same night). The instrument exists so
# that class of gap TRENDS nightly instead of being rediscovered by embarrassment. First
# 5-session run: coverage 66.7 / 44.8 / 0.0 (the 07-30 blindness day, correctly re-detected)
# / 84.1 / 75.0 percent.
#
# TIME: 15:35 MOUNTAIN = 17:35 ET. This box runs Mountain; ET = local + 2 (CLAUDE.md).
# Must fire >= 16:15 ET (the plan tier's SIP recency delay must have cleared the close);
# slot follows Gamma_ShadowSignalAudit (17:25 ET), clear of the RTH heartbeat window.
#
# Windowless wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py
#   --cwd <repo> -- backtest-venv-pythonw (C8/L41). 2026-08-08 VBS-WRAPPER-EXIT-CODE-
# BLIND-SPOT migration -- was fire-and-forget, LastTaskResult always fake-0.
$ErrorActionPreference = "Stop"
$Root = "C:\Users\jackw\Desktop\42"; $ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName = "Gamma_ViolinMetric"
$pythonw = Join-Path $Root "backtest\.venv\Scripts\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath = Join-Path $Root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"
$worker = Join-Path $ScriptsDir "violin_metric.py"
foreach ($p in @($pythonw, $runExeHidden, $sysPythonw, $runCmdHidden, $worker)) {
  if (-not (Test-Path $p)) { Write-Error "missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$Root`" -- `"$sysPythonw`" `"$worker`" --nightly"
# DailyTrigger, NOT a one-time/interval trigger (scar: project_scheduled_task_onetime_trigger_dark).
# Weekend fires are harmless: --nightly grades the most recent COMPLETED session (idempotent upsert).
$trigger = New-ScheduledTaskTrigger -Daily -At "15:35" -DaysInterval 1
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
$desc = "VIOLIN METRIC nightly (LANE-4 2026-08-03): tape-respected levels vs engine " + `
  "levels_active at the touch -- per-source coverage + latency, frozen defn v1. Writes " + `
  "automation/state/violin-metric.json + analysis/violin/violin-history.jsonl (idempotent " + `
  "upsert by date). Fail-open, `$0, no LLM, places nothing. Guard: " + `
  "backtest/tests/test_violin_metric_2026_08_03.py."
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description $desc | Out-Null

# ---- VERIFY, DON'T CLAIM (OP-33): registered + enabled + real daily trigger + will fire.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
$trigType = $t.Triggers[0].CimClass.CimClassName
if ($trigType -ne "MSFT_TaskDailyTrigger") { Write-Error "$TaskName trigger is $trigType, expected MSFT_TaskDailyTrigger"; exit 1 }
if ($null -eq $info.NextRunTime) { Write-Error "$TaskName has a NULL NextRunTime -- it would never fire"; exit 1 }
Write-Output "OK: Registered $TaskName  State=$($t.State)  Trigger=$trigType  NextRun=$($info.NextRunTime)"
