#requires -Version 5.1
<#
.SYNOPSIS
  (Re)install Gamma_ChartAutoDraw -- had NO declarative install script before 2026-08-18
  (VBS-WRAPPER-EXIT-CODE-BLIND-SPOT follow-up, queue.md), discovered live-only via
  Get-ScheduledTask/schtasks. This file is the first source of truth for it.

.DESCRIPTION
  Draws automation/state/key-levels.json onto the live TradingView chart and removes its
  OWN prior lines first, so the chart never accumulates stale levels (J directive
  2026-08-06 -- see setup/scripts/draw_key_levels.py's own docstring for the full incident).
  Pure Python + CDP, no LLM, $0. Fail-open: TV down = soft skip, exit 0.

  WIRING: wscript -> run_exe_hidden.vbs -> system pythonw -> run_py_venv_hidden.py ->
  draw_key_levels.py. Matches the live config this task already ran under (confirmed via
  Get-ScheduledTask 2026-08-18, migrated by the 2026-08-13 convert_tasks_off_venv_python.py
  console-leak fix): system pythonw + PYTHONPATH onto the backtest venv's site-packages,
  never the venv's own pythonw (which allocates a WindowsTerminal -Embedding host on
  `import pandas`). Also closes VBS-WRAPPER-EXIT-CODE-BLIND-SPOT for this task via
  self_check.check_run_py_venv_hidden_masked_exit() (2026-08-18) -- the relay already logs
  the real exit code to automation/state/logs/run-py-venv-hidden-<date>.log.

  SCHEDULE (reproduced verbatim from live Get-ScheduledTask state, not guessed): weekly
  Mon-Fri, starts 06:35 LOCAL (Mountain) = 08:35 ET, repeats every 30 min for 7h30m
  (covers through ~16:05 ET). ExecutionTimeLimit 5 min, MultipleInstances IgnoreNew,
  StartWhenAvailable.

  Per CLAUDE.md OP-25 (fail loud) + OP-3 ($0). To disable:
  Unregister-ScheduledTask -TaskName Gamma_ChartAutoDraw -Confirm:$false
#>

$ErrorActionPreference = "Stop"
$Root       = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName   = "Gamma_ChartAutoDraw"

$sysPythonw      = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runExeHidden    = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$runPyVenvHidden = Join-Path $ScriptsDir "run_py_venv_hidden.py"
$worker          = Join-Path $ScriptsDir "draw_key_levels.py"

foreach ($p in @($sysPythonw, $runExeHidden, $runPyVenvHidden, $worker)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript //nologo run_exe_hidden.vbs <sys-pythonw> run_py_venv_hidden.py <draw_key_levels.py>
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runPyVenvHidden`" `"$worker`""

# 06:35 LOCAL (Mountain) = 08:35 ET weekdays; repeat every 30 min for 7h30m (through ~16:05 ET).
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "06:35"
$rep = (New-ScheduledTaskTrigger -Once -At "06:35" `
        -RepetitionInterval (New-TimeSpan -Minutes 30) `
        -RepetitionDuration (New-TimeSpan -Hours 7 -Minutes 30)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Draws automation/state/key-levels.json onto the TradingView chart and removes its OWN prior lines so the chart never accumulates stale levels (J 2026-08-06). Pure Python + CDP, no LLM, `$0. Fail-open: TV down = soft skip exit 0. Weekly Mon-Fri 06:35 MT (08:35 ET), repeat 30min for 7h30m." `
    | Out-Null

# ---- VERIFY, DON'T CLAIM (OP-33): registered + enabled + will fire.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
$trigType = $t.Triggers[0].CimClass.CimClassName
if ($trigType -ne "MSFT_TaskWeeklyTrigger") { Write-Error "$TaskName trigger is $trigType, expected MSFT_TaskWeeklyTrigger"; exit 1 }
if ($null -eq $info.NextRunTime) { Write-Error "$TaskName has a NULL NextRunTime -- it would never fire"; exit 1 }
Write-Output "OK: Registered $TaskName  State=$($t.State)  Trigger=$trigType  NextRun=$($info.NextRunTime)"
