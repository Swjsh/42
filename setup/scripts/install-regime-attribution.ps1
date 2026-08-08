# install-regime-attribution.ps1 -- register Gamma_RegimeAttribution (LENS 4, 2026-08-04).
#
# Runs setup/scripts/regime_attribution.py --nightly once per evening: grades the completed
# session's REAL broker P&L against the day's mechanical archetype -- population frequency of
# that day shape, the mean of PRIOR days of the same shape (strictly-before, never the graded
# day itself), the resulting regime_lift, the mix-weighted expected day (mix_ev), and the
# concentration of the day's gross-positive P&L in its top 1-2 round trips.
#
# WHY: 2026-08-04 printed +$3,624 -- 145% of the fleet's entire prior live record -- and
# answering "was that us or the tape?" cost a whole research session. It is a JSON read now
# (OP-33(e): a repeated question is a missing instrument, not a query).
#
# Writes automation/state/regime-attribution.json + upserts
# analysis/regime-library/attribution-history.jsonl (idempotent by date).
# STDLIB ONLY, $0, read-only against the fills ledger + archetype library. No LLM, no network,
# no orders, fail-open by contract (an untagged date reports UNTAGGED, never raises).
#
# TIME: 15:45 MOUNTAIN = 17:45 ET. This box runs Mountain; ET = local + 2 (CLAUDE.md).
# Slot follows Gamma_ViolinMetric (17:35 ET) and must run AFTER the day's 5m bars land and the
# archetype library has been rebuilt -- if it has not, the report says UNTAGGED and names the
# rebuild command instead of guessing.
#
# Windowless wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py
#   --cwd <repo> -- backtest-venv-pythonw (C8/L41). 2026-08-08 VBS-WRAPPER-EXIT-CODE-
# BLIND-SPOT migration -- was fire-and-forget, LastTaskResult always fake-0.
$ErrorActionPreference = "Stop"
$Root = "C:\Users\jackw\Desktop\42"; $ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName = "Gamma_RegimeAttribution"
$pythonw = Join-Path $Root "backtest\.venv\Scripts\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"
$worker = Join-Path $ScriptsDir "regime_attribution.py"
foreach ($p in @($pythonw, $runExeHidden, $sysPythonw, $runCmdHidden, $worker)) {
  if (-not (Test-Path $p)) { Write-Error "missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$Root`" -- `"$pythonw`" `"$worker`" --nightly"
# DailyTrigger, NOT a one-time/interval trigger (scar: project_scheduled_task_onetime_trigger_dark).
# Weekend fires are harmless: --nightly grades the latest TRADED session (idempotent upsert).
$trigger = New-ScheduledTaskTrigger -Daily -At "15:45" -DaysInterval 1
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$desc = "REGIME ATTRIBUTION nightly (LENS 4 2026-08-04): the completed session's real " + `
  "broker P&L vs its mechanical day-archetype -- population share, strictly-prior " + `
  "archetype mean, regime_lift, mix_ev, top-1/top-2 concentration. Writes " + `
  "automation/state/regime-attribution.json + analysis/regime-library/" + `
  "attribution-history.jsonl (idempotent upsert by date). Fail-open, `$0, stdlib-only, no " + `
  "LLM, places nothing. Guard: backtest/tests/test_regime_attribution_2026_08_04.py."
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description $desc | Out-Null

# ---- VERIFY, DON'T CLAIM (OP-33): registered + enabled + real daily trigger + will fire.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
$trigType = $t.Triggers[0].CimClass.CimClassName
if ($trigType -ne "MSFT_TaskDailyTrigger") { Write-Error "$TaskName trigger is $trigType, expected MSFT_TaskDailyTrigger"; exit 1 }
if ($null -eq $info.NextRunTime) { Write-Error "$TaskName has a NULL NextRunTime -- it would never fire"; exit 1 }
Write-Output "OK: Registered $TaskName  State=$($t.State)  Trigger=$trigType  NextRun=$($info.NextRunTime)"
