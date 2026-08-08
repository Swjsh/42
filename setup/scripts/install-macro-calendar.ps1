# Registers Gamma_MacroCalendar -- daily premarket macro/event calendar refresh.
# Producer: setup/scripts/macro_calendar.py (stdlib-only, system pythonw, $0, fail-open).
# 05:45 MT = 07:45 ET weekdays -- before ScoutPremarket buffer, the 06:00 ET swarm macro
# agent, and Gamma_Premarket 08:30 ET (all read automation/state/macro-calendar.json / news.json).
# 2026-08-08 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT migration: now on the run_cmd_hidden.py
# relay (runs the child SYNCHRONOUSLY, logs the real exit code) -- was fire-and-forget.
# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- system pythonw -> macro_calendar.py
$ErrorActionPreference = "Stop"
$repo = "C:\Users\jackw\Desktop\42"
$vbs = Join-Path $repo "setup\scripts\run_exe_hidden.vbs"
$pyw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $repo "setup\scripts\run_cmd_hidden.py"
$script = Join-Path $repo "setup\scripts\macro_calendar.py"

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//nologo `"$vbs`" `"$pyw`" `"$runCmdHidden`" --cwd `"$repo`" -- `"$pyw`" `"$script`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "05:45"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName "Gamma_MacroCalendar" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Get-ScheduledTask -TaskName "Gamma_MacroCalendar" | Select-Object TaskName, State
(Get-ScheduledTaskInfo -TaskName "Gamma_MacroCalendar").NextRunTime
