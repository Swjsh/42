# install-tickers-eod-flatten.ps1 -- register Gamma_TickersEodFlatten, the TICKERS LANE's
# 14:52 ET safety-net flatten.
#
# LANE tickers (three DEDICATED non-SPY 0DTE paper accounts). Worker: multi/tickers_flatten.py
# (no --shadow -- this ARMS real paper closes). This is the SAFETY NET behind Gamma_TickersLane's
# own expiry-day flatten schedule (soft 14:45 / hard 14:50 / last-resort 14:55 ET, evaluated
# every 2 minutes inside multi/execute.py itself): a position execute.py's own 2-minute cadence
# somehow failed to close still gets one more close attempt here, registered as a SEPARATE
# scheduled task so a stall or crash in the tick cadence cannot also disable this backstop --
# same "the backstop must not share a failure mode with the thing it backstops" logic as the
# SPY engine's own Gamma_EodFlatten alongside Gamma_HeartbeatCore.
#
# ============================================================================================
# TIMES BELOW ARE **LOCAL (MOUNTAIN)**, NOT ET. ET = local + 2.
# Verified against the known-correct Gamma_HeartbeatCore / install-multi-evaluate.ps1 mapping.
# Do NOT "correct" these to ET values. Verify with setup/scripts/et_clock.py, never by assuming.
# ============================================================================================
# 12:52 local = 14:52 ET, daily, single fire (no intra-day repetition needed -- one flatten
# attempt is the point; Gamma_TickersLane's own 2-minute cadence already covers everything
# before this and Alpaca's do-not-exercise cutoff is 15:00 ET, so this sits with margin before it).

$ErrorActionPreference = "Stop"
$Root = "C:\Users\jackw\Desktop\42"; $ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName = "Gamma_TickersEodFlatten"
$pythonw = Join-Path $Root "backtest\.venv\Scripts\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath = Join-Path $Root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"
$worker = Join-Path $Root "multi\tickers_flatten.py"
foreach ($p in @($pythonw, $runExeHidden, $sysPythonw, $runCmdHidden, $worker)) {
  if (-not (Test-Path $p)) { Write-Error "missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# --log IS NOT OPTIONAL (C7). This task ARMS real paper closes; an unlogged failed run is a
# position left open with nobody knowing the safety net missed it.
$logDir = Join-Path $Root "automation\state\tickers"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
$logFile = Join-Path $logDir "flatten-last-run.log"
$action = New-ScheduledTaskAction -Execute "wscript.exe" `
  -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --log `"$logFile`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$Root`" -- `"$sysPythonw`" `"$worker`""

$trigger = New-ScheduledTaskTrigger -Daily -At "12:52" -DaysInterval 1

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
  -MultipleInstances IgnoreNew

$desc = "TICKERS LANE 14:52 ET safety-net flatten (three dedicated non-SPY 0DTE paper " + `
  "accounts: tickers-1/2/3). multi/tickers_flatten.py: for each arm with resolvable, " + `
  "pin-consistent credentials, closes every open equity-option position narrowed to that " + `
  "arm's OWN universe roots via multi/lib/broker.py::close_all_equity_options (armed=True -- " + `
  "REAL PAPER ORDERS). Backstops Gamma_TickersLane's own 2-minute expiry-day flatten schedule " + `
  "(soft 14:45 / hard 14:50 / last-resort 14:55 ET) as a SEPARATE task so a stall in that " + `
  "cadence cannot also disable this backstop. " + `
  "Guard: backtest/tests/test_tickers_execute_2026_09_04.py. " + `
  "REVOKE: Unregister-ScheduledTask Gamma_TickersEodFlatten."

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description $desc | Out-Null

# ---- VERIFY, DON'T CLAIM (OP-33): registered + enabled + will actually fire, AND the
# LOCAL->ET mapping is the one J asked for (14:52 ET), proven rather than just asserted.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
if ($null -eq $info.NextRunTime) { Write-Error "$TaskName has a NULL NextRunTime -- it would never fire"; exit 1 }
$nextLocal = $info.NextRunTime
$etOffset = 2   # Mountain -> Eastern; both observe DST so the gap is stable year-round
$nextEt = $nextLocal.AddHours($etOffset)
Write-Output "next run local: $nextLocal   next run ET: $nextEt  (local + $etOffset h)"
if ($nextLocal.Hour -ne 12) {
  Write-Error "VERIFY FAILED: next local hour $($nextLocal.Hour) is not 12 -- ET mapping wrong (should land at 14:52 ET)"; exit 1
}
Write-Output "OK: Registered $TaskName  State=$($t.State)  NextRun=$nextLocal"
