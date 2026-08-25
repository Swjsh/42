# Registers Gamma_EarningsCalendar -- daily premarket earnings-blackout feed refresh.
# Producer: setup/scripts/earnings_calendar.py (yfinance + Nasdaq cross-check, $0,
# fail-closed on the CONSUMER side -- weekly-1's non-exempt single-name entries are
# BLOCKED whenever this feed is missing/stale/failed).
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
# 2026-08-24 CONDUCTOR FIX: the ORIGINAL install script (2026-08-21) copied
# install-macro-calendar.ps1's wiring VERBATIM, including "system pythonw" for the INNER
# script call -- correct for macro_calendar.py (stdlib-only) but WRONG for this script,
# which does `import yfinance` (only installed in backtest\.venv, not system Python313).
# Root cause, verified live: every single 07:50 ET fire since registration crashed
# "FATAL earnings_calendar.py: No module named 'yfinance'" (confirmed reproducing the
# EXACT error by running system Python313 directly) -- masked from Task Scheduler by the
# wscript fire-and-forget hop (LastTaskResult stayed 0) but visible in
# automation/state/logs/run-cmd-hidden-<date>.log as "exit=1" the whole time, unread until
# now. Fix: inner hop now uses backtest\.venv\Scripts\pythonw.exe (has yfinance 0.2.66),
# matching install-ledger-archive.ps1's proven split-interpreter pattern (system pythonw
# for the outer run_cmd_hidden.py relay hop only, venv pythonw for the actual script).
#
# 05:50 MT = 07:50 ET weekdays -- before Gamma_Premarket (08:30 ET) and well inside the 48h
# fail-closed window every single weekday, so the feed can never age past ~24h in practice.
# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- backtest-venv pythonw -> earnings_calendar.py
#
# 2026-08-25 CONDUCTOR FIX -- MISSED-TRIGGER SELF-HEAL, same class as
# install-macro-calendar.ps1's identical same-day fix (see that file's header for the
# full live incident: Gamma_MacroCalendar's single 05:45 daily trigger silently did not
# fire despite the box being awake/on-AC and StartWhenAvailable=True). This task shares
# the exact same single-fire shape and the same downstream consumer deadline
# (Gamma_Premarket 08:30 ET), so it inherits the same fix pre-emptively rather than
# waiting for its own live miss: a bounded repetition window (every 15 min for 30 min
# after the primary 05:50 fire) so one missed trigger self-heals within 15 min.
# earnings_calendar.py is a cheap, idempotent refresh -- extra fires cost nothing.
$ErrorActionPreference = "Stop"
$repo = "C:\Users\jackw\Desktop\42"
$vbs = Join-Path $repo "setup\scripts\run_exe_hidden.vbs"
$pyw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pywVenv = Join-Path $repo "backtest\.venv\Scripts\pythonw.exe"
$runCmdHidden = Join-Path $repo "setup\scripts\run_cmd_hidden.py"
$script = Join-Path $repo "setup\scripts\earnings_calendar.py"

if (-not (Test-Path $pywVenv)) { throw "backtest venv pythonw.exe not found at $pywVenv" }

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//nologo `"$vbs`" `"$pyw`" `"$runCmdHidden`" --cwd `"$repo`" -- `"$pywVenv`" `"$script`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "05:50"
# -Weekly triggers come back with a null .Repetition CIM instance -- steal one from a
# throwaway -Once trigger built with the repetition params (documented PS workaround;
# direct property assignment on the null instance throws PropertyNotFound).
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "05:50" -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName "Gamma_EarningsCalendar" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Get-ScheduledTask -TaskName "Gamma_EarningsCalendar" | Select-Object TaskName, State
(Get-ScheduledTaskInfo -TaskName "Gamma_EarningsCalendar").NextRunTime
