#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_FuturesBrokerLane -- the REAL-FILL parity lane (Tastytrade SANDBOX).

  THE TWO-LANE DESIGN. Gamma_FuturesTrader runs the same deterministic tick on the local
  fill simulator; this task runs it on the real broker. Same bars, same watcher fleet,
  same should_take_v3 filter, same dollar risk rails -- only the execution backend
  differs. That is the point:

    * fillsim lane      = the PERSISTENT BOOK OF RECORD. Its positions and journal
                          survive restarts and days, so the trade ledger stays continuous.
    * tastytrade lane   = REAL FILLS. Actual broker acceptance, actual fill prices, actual
                          slippage against a live book -- the only thing that can tell us
                          whether the simulator's fill assumptions are honest.

  Divergence between them IS the signal. A sim that quietly disagrees with the broker is
  the failure mode every backtest in this repo is ultimately exposed to.

  WHY NOT JUST SWITCH THE DEFAULT TO THE BROKER: the cert environment WIPES positions and
  orders every 24 hours. That is fine for fill parity and disqualifying for a book of
  record whose journal depends on continuity. The lane detects the wipe explicitly
  (futures_trader_core._reconcile_broker_reset) and logs it as a reset rather than
  mistaking it for a lost fill, which would otherwise strand the lane in a permanent
  no-stack HOLD.

  STATE IS FULLY DISJOINT: automation/state/futures/trader-broker/ (vs trader/ for
  fillsim). Neither lane can read the other's fills as its own. Journal rows carry
  fills=BROKER vs fills=SIMULATED so no consumer can aggregate the two by accident.

  SANDBOX ONLY. TT_SANDBOX=true -> api.cert.tastyworks.com. Fake money. Live futures
  money is OP-0 #1 PLUS a new venue -- double-gated, and not reachable from this task.

  PROVEN before registration (2026-08-09, CME session open, cert account 5WW73759):
    dry run          -> validated, 0 errors, bp effect -$2.52
    resting order    -> Routed -> Live on the book, cancelled clean
    marketable order -> FILLED 1 /MESU6 @ 7772.50, position held, closed, flat
    full tick        -> connected=true, equity read from the broker, live bars, GREEN feed

  INTERPRETER: the backtest venv (tastytrade pinned 12.4.1 -- the version the July
  order-path proof used). Credentials load from the gitignored .env.tastytrade inside the
  process; a scheduled task has no shell to export them into, and running by hand proves
  nothing about the scheduled path.

  TZ: this rig is Mountain (ET = local + 2h). 09:30 ET -> 07:30 MT.

  VERIFY:  Get-ScheduledTask -TaskName Gamma_FuturesBrokerLane | Get-ScheduledTaskInfo
  REVERT:  Unregister-ScheduledTask -TaskName "Gamma_FuturesBrokerLane" -Confirm:$false
           (the fillsim book lane keeps running untouched -- the lanes are independent)
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv  = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script       = Join-Path $root "setup\scripts\futures_trader_runner.py"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName     = "Gamma_FuturesBrokerLane"

foreach ($p in @($vbs, $pythonwVenv, $script, $sysPythonw, $runCmdHidden)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonwVenv`" `"$script`" --backend tastytrade --armed"

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# 07:30 MT = 09:30 ET; every 5 min for 6h30m -> covers the 09:30-16:00 ET RTH window,
# matching the fillsim lane exactly so the two see the same bars and the same decisions.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "07:30"
$rep = (New-ScheduledTaskTrigger -Once -At "07:30" `
        -RepetitionInterval (New-TimeSpan -Minutes 5) `
        -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 30)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 4) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description ("REAL-FILL parity lane on the Tastytrade SANDBOX (fake money, " + `
    "api.cert.tastyworks.com). Every 5 min 09:30-16:00 ET weekdays, the SAME deterministic " + `
    "tick as Gamma_FuturesTrader -- same bars, same watcher fleet, same should_take_v3, same " + `
    "dollar risk rails -- routed to the real broker instead of the local fill simulator. " + `
    "fillsim stays the persistent BOOK OF RECORD (the cert env wipes positions every 24h, " + `
    "which is fine for fill parity and disqualifying for a continuous journal); this lane " + `
    "supplies REAL fills so we can tell whether the simulator's fill assumptions are honest. " + `
    "Divergence between the lanes IS the signal. State fully disjoint under " + `
    "automation/state/futures/trader-broker/; journal rows carry fills=BROKER vs SIMULATED so " + `
    "the two classes can never be aggregated by accident. Detects and logs the 24h sandbox " + `
    "reset rather than mistaking it for a lost fill. Refuses to act or journal as a BROKER " + `
    "lane if the adapter did not authenticate. Live futures money remains OP-0 #1 plus a new " + `
    "venue -- double-gated, unreachable from here. Proven 2026-08-09: dry run validated, " + `
    "order went Routed->Live, marketable order FILLED 1 /MESU6 @ 7772.50 and closed flat. " + `
    "REVERT: Unregister-ScheduledTask -TaskName 'Gamma_FuturesBrokerLane' -Confirm:`$false") | Out-Null

Write-Host "Registered $taskName"
$info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
if ($info -and $info.NextRunTime) {
    Write-Host ("  NextRun ET: {0}" -f ([System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)).ToString("yyyy-MM-dd HH:mm"))
}
(Get-ScheduledTask -TaskName $taskName).State
