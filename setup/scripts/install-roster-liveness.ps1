# Registers Gamma_RosterLiveness -- daily free-model lane liveness probe.
# Producer: setup/scripts/roster_liveness.py (probes every lane in model-roster.json, $0,
# writes automation/state/roster-health.json + flags dead ids to STATUS.md Known broken).
#
# WHY THIS TASK EXISTS (2026-08-29 audit fire): the probe was BUILT in Phase 0 and then
# never scheduled -- the classic producer/consumer mismatch (C14/C7 lesson class, same
# shape as the Gamma_EarningsCalendar 2026-08-21 fire). Its last run before tonight was
# 2026-07-01. In that two-month gap THREE lanes 404'd:
#     openrouter::meta-llama/llama-3.3-70b-instruct:free  (coordinator PRIMARY)
#     openrouter::qwen/qwen3-coder:free                   (coder PRIMARY)
#     cerebras::zai-glm-4.7                               (critic, archived)
# Consequence, measured: gamma_manager's pick phase failed on EVERY fire for ~2 months
# ("schema_invalid ... lanes_rejected=[], content_head=''" -- both lanes dead, so neither
# was even recorded as rejected), and the free swarm's artifact output collapsed from 13
# artifacts in Jun25-Jul08 to roughly one a month. Free models de-tag to paid without
# warning; without a scheduled probe the roster ALWAYS eventually rots. This closes the
# loop the same way Gamma_MacroCalendar closes it for the macro feed.
#
# SIGNAL PATH -- read this before "fixing" the exit code: the wscript fire-and-forget hop
# means Task Scheduler's LastTaskResult stays 0 even when the probe exits 1 (documented in
# install-earnings-calendar.ps1's header, same wiring). So the LOAD-BEARING signal is the
# STATUS.md "## Known broken" line the probe writes itself; the non-zero exit is for manual
# runs and shows up as "exit=1" in automation/state/logs/run-cmd-hidden-<date>.log.
# Guard: backtest/tests/test_roster_liveness_alerting_2026_08_29.py (5 tests).
#
# Interpreter: SYSTEM pythonw for both hops -- roster_liveness.py needs `openai`, which IS
# present in system Python313 (2.37.0, verified 2026-08-29). No venv hop needed.
#
# 04:40 MT = 06:40 ET daily -- clear of the 05:45/05:50/06:15 MT premarket task cluster, and
# well before Gamma_SwarmPremarket (06:15 MT) so the day's R&D starts on a verified roster.
# Bounded repetition (every 20 min for 40 min) so one missed trigger self-heals; the probe
# is cheap (6 lanes, ~10s, $0) and idempotent, so extra fires cost nothing.
$ErrorActionPreference = "Stop"
$repo = "C:\Users\jackw\Desktop\42"
$vbs = Join-Path $repo "setup\scripts\run_exe_hidden.vbs"
$pyw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $repo "setup\scripts\run_cmd_hidden.py"
$script = Join-Path $repo "setup\scripts\roster_liveness.py"

if (-not (Test-Path $pyw))    { throw "system pythonw.exe not found at $pyw" }
if (-not (Test-Path $script)) { throw "roster_liveness.py not found at $script" }

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//nologo `"$vbs`" `"$pyw`" `"$runCmdHidden`" --cwd `"$repo`" -- `"$pyw`" `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At "04:40"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "04:40" -RepetitionInterval (New-TimeSpan -Minutes 20) -RepetitionDuration (New-TimeSpan -Minutes 40)).Repetition
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName "Gamma_RosterLiveness" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Get-ScheduledTask -TaskName "Gamma_RosterLiveness" | Select-Object TaskName, State
(Get-ScheduledTaskInfo -TaskName "Gamma_RosterLiveness").NextRunTime
