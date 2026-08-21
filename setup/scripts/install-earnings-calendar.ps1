# Registers Gamma_EarningsCalendar -- daily premarket earnings-blackout feed refresh.
# Producer: setup/scripts/earnings_calendar.py (yfinance + Nasdaq cross-check, system
# pythonw, $0, fail-closed on the CONSUMER side -- weekly-1's non-exempt single-name
# entries are BLOCKED whenever this feed is missing/stale/failed).
#
# WHY THIS TASK EXISTS (2026-08-21 conductor fire): the feed + its freshness guard
# (self_check.py#check_earnings_calendar_freshness, backtest/tests/
# test_self_check_earnings_calendar_freshness.py) were built and fully guard-tested
# 2026-08-18, but NO scheduled producer was ever registered -- classic producer/consumer
# mismatch (CLAUDE.md C14/C7 lesson class). The file was written once by hand on 2026-08-18
# and then self_check correctly flagged it BROKEN 49.4h later (2026-08-21T00:39) once the
# 48h fail-closed threshold (params.json#entry.earnings_feed_stale_hours_fail_closed) was
# crossed. Since the file will ALWAYS eventually cross 48h without a cron, this closes the
# loop the same way Gamma_MacroCalendar closes it for the macro/event feed -- mirrors that
# installer's exact wiring (see setup/scripts/install-macro-calendar.ps1).
#
# 05:50 MT = 07:50 ET weekdays -- before Gamma_Premarket (08:30 ET) and well inside the 48h
# fail-closed window every single weekday, so the feed can never age past ~24h in practice.
# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- system pythonw -> earnings_calendar.py
$ErrorActionPreference = "Stop"
$repo = "C:\Users\jackw\Desktop\42"
$vbs = Join-Path $repo "setup\scripts\run_exe_hidden.vbs"
$pyw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $repo "setup\scripts\run_cmd_hidden.py"
$script = Join-Path $repo "setup\scripts\earnings_calendar.py"

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//nologo `"$vbs`" `"$pyw`" `"$runCmdHidden`" --cwd `"$repo`" -- `"$pyw`" `"$script`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "05:50"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName "Gamma_EarningsCalendar" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Get-ScheduledTask -TaskName "Gamma_EarningsCalendar" | Select-Object TaskName, State
(Get-ScheduledTaskInfo -TaskName "Gamma_EarningsCalendar").NextRunTime
