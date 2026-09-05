# install-tickers-lane.ps1 -- register Gamma_TickersLane, the TICKERS LANE's ARMED paper tick.
#
# LANE tickers (three DEDICATED non-SPY 0DTE paper accounts: tickers-1 NVDA/AAPL/AMZN,
# tickers-2 TSLA/META/AVGO, tickers-3 QQQ/IWM/GLD). Config: automation/state/tickers/params.json
# (shadow_only:false -- this task PLACES REAL PAPER ORDERS, unlike Gamma_MultiCore's shadow
# tick). Worker: multi/execute.py --once (the OS trigger below provides the 2-minute cadence,
# same pattern as every other worker in this registry -- the process does ONE pass and exits).
# Prereg: analysis/recommendations/prereg-tickers-lane-production-scorer-2026-09-04.json.
#
# WHY 2 MINUTES, NOT 15 (unlike Gamma_MultiCore). This lane's exits include a -50% catastrophe
# cap and an expiry-day flatten schedule (soft 14:45 / hard 14:50 / last-resort 14:55 ET) --
# both are 0DTE-shaped safety items that cannot wait 15 minutes. tick_cadence.minutes=2 in
# params.json keeps API use ~20/min across three arms, far under Alpaca's 200/min limit.
#
# ============================================================================================
# TIMES BELOW ARE **LOCAL (MOUNTAIN)**, NOT ET. ET = local + 2.
# Task Scheduler triggers fire on LOCAL wall-clock; this box runs Mountain time, so 09:35 ET is
# 07:35 local -- verified against the known-correct Gamma_HeartbeatCore (StartBoundary 07:30
# local for its documented 09:30 ET start) and install-multi-evaluate.ps1's own proven mapping.
# Do NOT "correct" these to ET values. Verify with setup/scripts/et_clock.py, never by assuming
# -- this exact mistake (registering the ET number as if it were local) is a documented scar
# (project_tz_systemic_fix) and this task ARMS REAL PAPER ORDERS, so getting it wrong here
# would silently start the lane trading two hours late/early relative to what J asked for.
# ============================================================================================
# 07:35 local = 09:35 ET first tick (entry.09:35 ET / tick_cadence.first_tick_et), repeating
# every 2 min for 5h20m -> last fire at 12:55 local = 14:55 ET (tick_cadence covers entries
# through 14:30 ET and exits/flattens through the 14:45/14:50/14:55 schedule; the dedicated
# Gamma_TickersEodFlatten task at 12:52 local = 14:52 ET is the separate safety-net backstop).

$ErrorActionPreference = "Stop"
$Root = "C:\Users\jackw\Desktop\42"; $ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName = "Gamma_TickersLane"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath = Join-Path $Root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"
$worker = Join-Path $Root "multi\execute.py"
foreach ($p in @($runExeHidden, $sysPythonw, $runCmdHidden, $worker)) {
  if (-not (Test-Path $p)) { Write-Error "missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# --log IS NOT OPTIONAL (C7: silent success is failure -- and this task places real paper
# orders, so an unlogged failed run is worse here than anywhere else in this registry). The
# outer wscript hop is fire-and-forget and swallows the child's true exit code either way; the
# log's own "exit=" line is what makes a bad run visible.
$logDir = Join-Path $Root "automation\state\tickers"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
$logFile = Join-Path $logDir "execute-last-run.log"
$action = New-ScheduledTaskAction -Execute "wscript.exe" `
  -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --log `"$logFile`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$Root`" -- `"$sysPythonw`" `"$worker`" --once"

$trigger = New-ScheduledTaskTrigger -Daily -At "07:35" -DaysInterval 1
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "07:35" `
  -RepetitionInterval (New-TimeSpan -Minutes 2) `
  -RepetitionDuration (New-TimeSpan -Hours 5 -Minutes 20)).Repetition

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
  -MultipleInstances IgnoreNew

$desc = "TICKERS LANE ARMED paper tick (three dedicated non-SPY 0DTE paper accounts: " + `
  "tickers-1 NVDA/AAPL/AMZN, tickers-2 TSLA/META/AVGO, tickers-3 QQQ/IWM/GLD). " + `
  "multi/execute.py --once: calls multi/core.py (SHADOW ONLY, AST-guarded) per arm, then acts " + `
  "on WOULD_PLACE/SELL_PARTIAL/SELL_ALL rows via multi/lib/broker.py with armed=True -- REAL " + `
  "PAPER ORDERS. Per-arm invariants self-check + NO_CREDS self-heal + account pin + daily kill " + `
  "switch (1% of equity, blocks new entries only) all fail LOUD and per-arm, never crash the " + `
  "process. Writes automation/state/tickers/<arm>/{ledger.jsonl,participation-cascade.jsonl," + `
  "exit-state.json,day-<date>.json,account.json} + journal/trades-tickers-<arm>.csv. " + `
  "Prereg: analysis/recommendations/prereg-tickers-lane-production-scorer-2026-09-04.json. " + `
  "Guard: backtest/tests/test_tickers_execute_2026_09_04.py. " + `
  "REVOKE: set shadow_only:true in automation/state/tickers/params.json (exits/flatten still " + `
  "run), or Unregister-ScheduledTask Gamma_TickersLane."

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description $desc | Out-Null

# ---- VERIFY, DON'T CLAIM (OP-33): registered + enabled + repeating + will actually fire, AND
# the LOCAL->ET mapping is the one J asked for (09:35 ET), proven rather than just asserted.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
if ($null -eq $info.NextRunTime) { Write-Error "$TaskName has a NULL NextRunTime -- it would never fire"; exit 1 }
$rep = $t.Triggers[0].Repetition
if ($null -eq $rep -or [string]::IsNullOrEmpty($rep.Interval)) {
  Write-Error "$TaskName has NO repetition -- it would fire once and go dark"; exit 1
}
$nextLocal = $info.NextRunTime
$etOffset = 2   # Mountain -> Eastern; both observe DST so the gap is stable year-round
$nextEt = $nextLocal.AddHours($etOffset)
Write-Output "next run local: $nextLocal   next run ET: $nextEt  (local + $etOffset h)"
if ($nextLocal.Hour -ne 7) {
  Write-Error "VERIFY FAILED: next local hour $($nextLocal.Hour) is not 07 -- ET mapping wrong (should land at 09:35 ET)"; exit 1
}
Write-Output "OK: Registered $TaskName  State=$($t.State)  Repeat=$($rep.Interval) for $($rep.Duration)  NextRun=$nextLocal"
