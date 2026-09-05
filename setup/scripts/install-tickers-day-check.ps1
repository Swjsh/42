# install-tickers-day-check.ps1 -- register Gamma_TickersDayCheck, the TICKERS LANE's deterministic
# day-check (goal GOAL-TICKERS-LANE-2026-09-04 T6 instrument). Worker: multi/tickers_day_check.py
# --phase auto. READ-ONLY against the lane and the broker: never places/cancels an order, never
# edits state. Writes automation/state/tickers/day-check-<date>-<phase>.json, one PROGRESS LOG
# line into the goal file, and a TICKERS-DAY-CHECK line on STATUS.md ## Known broken when RED.
#
# WHY A SCRIPT, NOT A SESSION: Rule-9 discipline forbids interactive Claude sessions 09:30-15:55
# ET, and "confirm the ledger has rows at 09:37" is exactly the kind of check that silently never
# happens when it depends on someone remembering (C7). $0, deterministic, fires twice a day.
#
# ============================================================================================
# TIMES BELOW ARE **LOCAL (MOUNTAIN)**, NOT ET. ET = local + 2. (Same scar note as
# install-tickers-lane.ps1 -- do NOT "correct" these to ET values.)
# ============================================================================================
# 07:40 local = 09:40 ET  (open phase: 5 min after the lane's first tick -> rows must exist)
# 13:05 local = 15:05 ET  (eod phase: after the 14:52 ET flatten + 14:55 last tick -> must be FLAT)

$ErrorActionPreference = "Stop"
$Root = "C:\Users\jackw\Desktop\42"; $ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName = "Gamma_TickersDayCheck"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath = Join-Path $Root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"
$worker = Join-Path $Root "multi\tickers_day_check.py"
foreach ($p in @($runExeHidden, $sysPythonw, $runCmdHidden, $worker)) {
  if (-not (Test-Path $p)) { Write-Error "missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# --log IS NOT OPTIONAL (C7). The outer wscript hop swallows the child's exit code; the log's own
# "exit=" line is what makes a bad run visible.
$logDir = Join-Path $Root "automation\state\tickers"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
$logFile = Join-Path $logDir "day-check-last-run.log"
$action = New-ScheduledTaskAction -Execute "wscript.exe" `
  -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --log `"$logFile`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$Root`" -- `"$sysPythonw`" `"$worker`" --phase auto"

$tOpen = New-ScheduledTaskTrigger -Daily -At "07:40" -DaysInterval 1
$tEod  = New-ScheduledTaskTrigger -Daily -At "13:05" -DaysInterval 1

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
  -MultipleInstances IgnoreNew

$desc = "TICKERS LANE day-check (goal T6 instrument). multi/tickers_day_check.py --phase auto, " + `
  "READ-ONLY: 09:40 ET verifies every arm wrote ledger rows (NO_CREDS-only = AMBER, dark = RED); " + `
  "15:05 ET verifies every arm is FLAT at the broker (never from state) and reports fills/P&L. " + `
  "Writes automation/state/tickers/day-check-<date>-<phase>.json + a PROGRESS LOG line in " + `
  "automation/state/goals/GOAL-TICKERS-LANE-2026-09-04.md + a TICKERS-DAY-CHECK line on STATUS.md " + `
  "## Known broken when RED (cleared on a later green). Guard: " + `
  "backtest/tests/test_tickers_day_check_2026_09_04.py. Never places orders."

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($tOpen, $tEod) -Settings $settings -Description $desc | Out-Null

# ---- VERIFY, DON'T CLAIM (OP-33): registered + enabled + will fire at a LOCAL hour that maps to
# 09:40 or 15:05 ET, proven from the scheduler's own NextRunTime rather than asserted.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
if ($null -eq $info.NextRunTime) { Write-Error "$TaskName has a NULL NextRunTime -- it would never fire"; exit 1 }
if ($t.Triggers.Count -ne 2) { Write-Error "$TaskName has $($t.Triggers.Count) triggers, expected 2"; exit 1 }
$nextLocal = $info.NextRunTime
$etOffset = 2
$nextEt = $nextLocal.AddHours($etOffset)
Write-Output "next run local: $nextLocal   next run ET: $nextEt  (local + $etOffset h)"
if (($nextLocal.Hour -ne 7) -and ($nextLocal.Hour -ne 13)) {
  Write-Error "VERIFY FAILED: next local hour $($nextLocal.Hour) is neither 07 nor 13 -- ET mapping wrong (should be 09:40 / 15:05 ET)"; exit 1
}
Write-Output "OK: Registered $TaskName  State=$($t.State)  Triggers=$($t.Triggers.Count)  NextRun=$nextLocal"
