# install-shadow-signal-audit.ps1 -- register Gamma_ShadowSignalAudit (2026-07-31).
#
# Runs setup/scripts/shadow_signal_audit.py once nightly: re-derives, from the working tree,
# which signal producers have NO consumer on any decision path, regenerates the standing
# inventory at analysis/deep-research/SHADOW-SIGNAL-INVENTORY-2026-07-31.md, and appends ONE
# line to STATUS.md "## Known broken" when a NEW orphan appears. Fail-open ($0, no LLM, no
# orders, never blocks anything).
#
# WHY: on 2026-07-31 the wick_reclaim detector fired at 10:21 into a +4.82 bounce and was
# architecturally mute, while trendline_engine logged the 10:15:02 break with zero consumers.
# Nobody was counting how much this engine SEES and cannot ACT on. Now something does, nightly.
#
# TIME: 15:25 MOUNTAIN = 17:25 ET. This box runs Mountain; ET = local + 2 (CLAUDE.md).
# Slot chosen after Gamma_GymSession (17:00 ET) and Gamma_WatcherGrader (17:10 ET), well
# clear of the 09:30-15:55 ET heartbeat window.
#
# Windowless wscript -> run_exe_hidden.vbs -> system-pythonw -> run_py_venv_hidden.py (2026-08-13
# console-leak fix, C8/L41: a visible console popup on J's screen is a standing offense).
# Also closes VBS-WRAPPER-EXIT-CODE-BLIND-SPOT via self_check.check_run_py_venv_hidden_masked_exit()
# (2026-08-18). Live state was already on this wiring (2026-08-13 imperative patch); this
# template was drifted (CryptoTwin-class regression) until this fix.
$ErrorActionPreference = "Stop"
$Root = "C:\Users\jackw\Desktop\42"; $ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName = "Gamma_ShadowSignalAudit"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$runPyVenvHidden = Join-Path $ScriptsDir "run_py_venv_hidden.py"
$worker = Join-Path $ScriptsDir "shadow_signal_audit.py"
foreach ($p in @($sysPythonw, $runExeHidden, $runPyVenvHidden, $worker)) {
  if (-not (Test-Path $p)) { Write-Error "missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runPyVenvHidden`" `"$worker`""
# DailyTrigger, NOT a one-time/interval trigger -- a -Once trigger goes dark after it fires
# (scar: project_scheduled_task_onetime_trigger_dark).
$trigger = New-ScheduledTaskTrigger -Daily -At "15:25" -DaysInterval 1
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
$desc = "Shadow-signal / orphan detector (2026-07-31). Re-derives from the working tree which " + `
  "signal producers have NO consumer on any decision path; regenerates " + `
  "analysis/deep-research/SHADOW-SIGNAL-INVENTORY-2026-07-31.md and appends ONE STATUS.md " + `
  "'Known broken' line when a NEW orphan or drift appears (first run seeds the baseline " + `
  "silently). Fail-open, `$0, no LLM, places nothing. Guard: " + `
  "backtest/tests/test_shadow_signal_audit_2026_07_31.py."
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description $desc | Out-Null

# ---- VERIFY, DON'T CLAIM (OP-33). This repo has been burned by tasks documented Active
# ---- while sitting Disabled, and by -Once triggers going dark. Assert all three.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
$trigType = $t.Triggers[0].CimClass.CimClassName
if ($trigType -ne "MSFT_TaskDailyTrigger") { Write-Error "$TaskName trigger is $trigType, expected MSFT_TaskDailyTrigger"; exit 1 }
if ($null -eq $info.NextRunTime) { Write-Error "$TaskName has a NULL NextRunTime -- it would never fire"; exit 1 }
Write-Output "OK: Registered $TaskName  State=$($t.State)  Trigger=$trigType  NextRun=$($info.NextRunTime)"
