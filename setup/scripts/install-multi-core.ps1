# install-multi-core.ps1 -- register Gamma_MultiCore, the multi-symbol lane's RTH shadow tick.
#
# LANE multi-symbol / ARM multi-1 (acct PA38EG1JTFBT). SHADOW ONLY: multi/core.py contains no
# order-placement call at all -- guarded structurally by
# backtest/tests/test_multi_core.py::test_tick_module_contains_no_order_placement_call, which
# parses the AST rather than grepping and is RED-proofed.
#
# WHY 15 MINUTES and not 1: this is a multi-DAY lane reading a ~72-name universe. A 1-minute
# cadence would burn the shared Alpaca rate limit for no decision benefit -- the funnel already
# narrows to <=5 names per tick, and a multi-day thesis does not change between minutes. The SPY
# 0DTE engine ticks 1/min because ITS holding period is minutes; copying that cadence here would
# be cargo-culting the number instead of the reason.
#
# DailyTrigger with 15-min repetition, NOT a one-time trigger
# (scar: project_scheduled_task_onetime_trigger_dark -- a one-time trigger goes dark after it fires).

$ErrorActionPreference = "Stop"
$Root = "C:\Users\jackw\Desktop\42"; $ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName = "Gamma_MultiCore"
$pythonw = Join-Path $Root "backtest\.venv\Scripts\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath = Join-Path $Root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"
$worker = Join-Path $Root "multi\core.py"
foreach ($p in @($pythonw, $runExeHidden, $sysPythonw, $runCmdHidden, $worker)) {
  if (-not (Test-Path $p)) { Write-Error "missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
  -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$Root`" -- `"$sysPythonw`" `"$worker`""

# 09:35 ET start mirrors the SPY engine's own entry gate (never the opening auction), repeating
# every 15 min until 15:45 so the last tick still leaves room before the flatten window.
$trigger = New-ScheduledTaskTrigger -Daily -At "09:35" -DaysInterval 1
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "09:35" `
  -RepetitionInterval (New-TimeSpan -Minutes 15) `
  -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 10)).Repetition

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 12) `
  -MultipleInstances IgnoreNew

$desc = "MULTI-SYMBOL LANE shadow tick (LANE multi-symbol / ARM multi-1, acct PA38EG1JTFBT). " + `
  "Funnels a ~72-name universe to <=5 by RANKING (liquidity -> relative volume -> setup score), " + `
  "then scores the forked SPY engine per symbol and records a WOULD_PLACE / BLOCKED row with the " + `
  "gate that stopped it. SHADOW ONLY -- multi/core.py has NO order path (AST-guarded, RED-proofed). " + `
  "Writes automation/state/multi/shadow-ledger.jsonl + participation-cascade.jsonl. Shares its " + `
  "account with the crypto twin: OCC-only position filters mean neither lane can see or flatten " + `
  "the other, and account equity is NOT evidence for either. " + `
  "Doctrine: markdown/planning/WEEKLY-OPTIONS-PROGRAM.md 9a/9c. " + `
  "Guard: backtest/tests/test_multi_core.py. Revert: Unregister-ScheduledTask Gamma_MultiCore."

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description $desc | Out-Null

# ---- VERIFY, DON'T CLAIM (OP-33): registered + enabled + repeating + will actually fire.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
if ($null -eq $info.NextRunTime) { Write-Error "$TaskName has a NULL NextRunTime -- it would never fire"; exit 1 }
$rep = $t.Triggers[0].Repetition
if ($null -eq $rep -or [string]::IsNullOrEmpty($rep.Interval)) {
  Write-Error "$TaskName has NO repetition -- it would fire once a day, not through the session"; exit 1
}
Write-Output "OK: Registered $TaskName  State=$($t.State)  Repeat=$($rep.Interval) for $($rep.Duration)  NextRun=$($info.NextRunTime)"
