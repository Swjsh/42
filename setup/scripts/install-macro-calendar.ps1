# Registers Gamma_MacroCalendar -- daily premarket macro/event calendar refresh.
# Producer: setup/scripts/macro_calendar.py (stdlib-only, system pythonw, $0, fail-open).
# 05:45 MT = 07:45 ET weekdays -- before ScoutPremarket buffer, the 06:00 ET swarm macro
# agent, and Gamma_Premarket 08:30 ET (all read automation/state/macro-calendar.json / news.json).
# 2026-08-08 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT migration: now on the run_cmd_hidden.py
# relay (runs the child SYNCHRONOUSLY, logs the real exit code) -- was fire-and-forget.
# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- system pythonw -> macro_calendar.py
#
# 2026-08-25 CONDUCTOR FIX -- MISSED-TRIGGER SELF-HEAL. Live incident: the single 05:45
# daily trigger silently did not fire on 2026-08-25 (Get-ScheduledTaskInfo showed
# LastRunTime stuck on the PRIOR day, NumberOfMissedRuns=1, NextRunTime already advanced
# to the NEXT day) despite the box being continuously awake, on AC power, and other
# same-minute tasks (window_leak_detector_keepalive, quiet_mode) firing normally --
# StartWhenAvailable=True did NOT catch it up. Microsoft-Windows-TaskScheduler/Operational
# is disabled on this box (access-denied to enable non-elevated), so Windows itself gives
# no forensic trail for WHY a single-fire weekly trigger occasionally drops -- only that it
# does. self_check.py's freshness check caught the resulting staleness, but that only
# heals on the next conductor/self-check pass, which could be hours after 08:30 Premarket
# needs a fresh feed for CPI/FOMC/NFP no-trade-window coverage. Fix: add a bounded
# repetition window (every 15 min for 30 min after the primary 05:45 fire) so a single
# missed trigger self-heals within 15 min instead of depending on external detection --
# same shape as Gamma_TvWatchdog's re-check cadence. macro_calendar.py is cheap (~1s) and
# idempotent (re-running when already fresh just no-ops with skipped_existing_count), so
# the extra fires cost nothing and change no behavior on a normal day.
$ErrorActionPreference = "Stop"
$repo = "C:\Users\jackw\Desktop\42"
$vbs = Join-Path $repo "setup\scripts\run_exe_hidden.vbs"
$pyw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $repo "setup\scripts\run_cmd_hidden.py"
$script = Join-Path $repo "setup\scripts\macro_calendar.py"

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//nologo `"$vbs`" `"$pyw`" `"$runCmdHidden`" --cwd `"$repo`" -- `"$pyw`" `"$script`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "05:45"
# -Weekly triggers come back with a null .Repetition CIM instance -- steal one from a
# throwaway -Once trigger built with the repetition params (documented PS workaround;
# direct property assignment on the null instance throws PropertyNotFound).
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "05:45" -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName "Gamma_MacroCalendar" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Get-ScheduledTask -TaskName "Gamma_MacroCalendar" | Select-Object TaskName, State
(Get-ScheduledTaskInfo -TaskName "Gamma_MacroCalendar").NextRunTime
