# install-risky-divergence-weekly.ps1 -- register Gamma_RiskyDivergenceWeekly
# (RISKY3-SPECULATIVE lane, 2026-08-04).
#
# Runs setup/scripts/full_send_vs_gated.py --weekly every SUNDAY evening: the last 5
# weekday sessions' per-arm participation + the MARGINAL COHORT headline J asked for this
# week without having to ask again -- "risky-3 took N trades the safes did not; that
# cohort paid $X" (real closed FIFO fills via fleet/fills_fifo.py; core-safe counting is
# extra_exec-aware per L244). Writes analysis/fleet-weekly/risky-divergence-<date>.md+.json.
# $0, stdlib-only, read-only on trading state, no LLM, places nothing.
#
# TIME: 15:00 MOUNTAIN Sunday = 17:00 ET Sunday. This box runs Mountain; ET = local + 2
# (CLAUDE.md). Market closed; clear of every RTH/heartbeat window and the 16:0x EOD fires.
#
# Windowless wscript -> run_exe_hidden.vbs -> system-pythonw -> run_py_venv_hidden.py (2026-08-13
# console-leak fix, C8/L41 -- see install-gate-expiry-check.ps1's comment for the full history).
# Also closes VBS-WRAPPER-EXIT-CODE-BLIND-SPOT for this task via
# self_check.check_run_py_venv_hidden_masked_exit() (2026-08-18). Live state was already on
# this wiring (2026-08-13 imperative patch); this template was drifted (CryptoTwin-class
# regression) until this fix.
$ErrorActionPreference = "Stop"
$Root = "C:\Users\jackw\Desktop\42"; $ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName = "Gamma_RiskyDivergenceWeekly"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$runPyVenvHidden = Join-Path $ScriptsDir "run_py_venv_hidden.py"
$worker = Join-Path $ScriptsDir "full_send_vs_gated.py"
foreach ($p in @($sysPythonw, $runExeHidden, $runPyVenvHidden, $worker)) {
  if (-not (Test-Path $p)) { Write-Error "missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runPyVenvHidden`" `"$worker`" --weekly"
# Weekly STANDING trigger (never a one-time trigger: project_scheduled_task_onetime_trigger_dark).
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "15:00"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$desc = "RISKY-vs-SAFES weekly divergence (RISKY3-SPECULATIVE lane 2026-08-04): last 5 " + `
  "sessions' marginal cohort -- risk-arm entries neither safe-3 nor core safe-2 took, " + `
  "joined to real closed FIFO P&L. Writes analysis/fleet-weekly/risky-divergence-<date>" + `
  ".md+.json. Read-only, `$0, no LLM, places nothing. Guard: " + `
  "backtest/tests/test_risky_divergence_weekly_2026_08_04.py."
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description $desc | Out-Null

# ---- VERIFY, DON'T CLAIM (OP-33): registered + enabled + weekly trigger + will fire.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
$trigType = $t.Triggers[0].CimClass.CimClassName
if ($trigType -ne "MSFT_TaskWeeklyTrigger") { Write-Error "$TaskName trigger is $trigType, expected MSFT_TaskWeeklyTrigger"; exit 1 }
if ($null -eq $info.NextRunTime) { Write-Error "$TaskName has a NULL NextRunTime -- it would never fire"; exit 1 }
Write-Output "OK: Registered $TaskName  State=$($t.State)  Trigger=$trigType  NextRun=$($info.NextRunTime)"
