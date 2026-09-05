# install-multi-outcomes.ps1 -- register Gamma_MultiOutcomes, the learning half of the lane.
#
# WHY IT EXISTS. multi/evaluate.py records what it SAW; this records what FOLLOWED. Without it
# the evaluation surface is a dashboard with no memory -- readable forever, informative never.
# It stamps each evaluation card with the underlying's actual move at +10/+30/+60 min, building
# the ledger that can eventually answer, from OUR live pipeline on OUR universe: does a high
# score predict anything on non-SPY names, and is a given blocker saving us or costing us?
#
# 16:45 ET (14:45 LOCAL -- this box runs Mountain, ET = local + 2; see install-multi-evaluate.ps1
# for the full trap). By then every card from the 09:00-15:30 evaluation window is older than
# the 65-minute settle threshold, so a single daily pass stamps the whole day and never reads an
# open window.
#
# READ-ONLY: multi/outcomes.py has no order path. $0 -- no LLM anywhere in it.
# DailyTrigger, not one-time (scar: project_scheduled_task_onetime_trigger_dark).

$ErrorActionPreference = "Stop"
$Root = "C:\Users\jackw\Desktop\42"; $ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName = "Gamma_MultiOutcomes"
$pythonw = Join-Path $Root "backtest\.venv\Scripts\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath = Join-Path $Root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"
$worker = Join-Path $Root "multi\outcomes.py"
foreach ($p in @($pythonw, $runExeHidden, $sysPythonw, $runCmdHidden, $worker)) {
  if (-not (Test-Path $p)) { Write-Error "missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# --log is NOT optional: run_cmd_hidden discards stdout without it and the wscript hop swallows
# the exit code, so a crashed run reports LastTaskResult=0 and writes nothing. That exact
# combination hid a real crash in Gamma_MultiEvaluate on its first fire.
$logFile = Join-Path $Root "automation\state\multi\outcomes-last-run.log"
$action = New-ScheduledTaskAction -Execute "wscript.exe" `
  -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --log `"$logFile`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$Root`" -- `"$sysPythonw`" -m multi.outcomes"

# 14:45 LOCAL = 16:45 ET. Do not "correct" this to 16:45.
# WEEKDAYS ONLY -- nothing to stamp on a day with no session.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:45"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
  -MultipleInstances IgnoreNew

$desc = "MULTI-LANE LEARNING PASS. Stamps every evaluation card with the underlying's actual " + `
  "forward move (+10/+30/+60 min) into analysis/multi-lane/evaluations/card-outcomes.jsonl, and " + `
  "rebuilds learning-report.json: hit rate by symbol, BY LEAN SCORE (does a higher score predict " + `
  "anything?), BY BLOCKER (is the block saving or costing us?), and shelf-vs-not. Cards are only " + `
  "stamped once older than the 65-min settle threshold, so an open window is never read; outcomes " + `
  "go to a SEPARATE file so card-history.jsonl stays append-only and immutable. Every cut carries " + `
  "its n. READ-ONLY, no order path, `$0. Lane remains STOPPED -- this accumulates evidence at zero " + `
  "risk, it does not authorize anything."

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings -Description $desc | Out-Null

$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $t) { Write-Error "VERIFY FAILED: $TaskName did not register"; exit 1 }
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "registered : $($t.TaskName)"
Write-Host "state      : $($t.State)"
Write-Host "next run   : $($info.NextRunTime)  (local)"
if ($info.NextRunTime) { Write-Host "next run ET: $($info.NextRunTime.AddHours(2))" }
if ($t.State -eq "Disabled") { Write-Error "VERIFY FAILED: registered but Disabled"; exit 1 }
if ($info.NextRunTime -and $info.NextRunTime.Hour -ne 14) {
  Write-Error "VERIFY FAILED: next local hour $($info.NextRunTime.Hour) is not 14 -- ET mapping wrong"; exit 1
}
Write-Host "OK"
