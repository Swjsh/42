# Registers Gamma_Watcher: the command-center self-watch tick, every 15 min, 24/7.
#
# WHY (J, 2026-08-29): "i want a gamma watching the command center for efficiency and maybe
# even driving itself." gamma_watcher.py is the deterministic observe->decide->act loop over
# surfaces that already existed but did not talk to each other (army payload, cards, cost
# meter, autofire ledger, companion liveness, goal drift). $0 -- pure Python, no LLM.
#
# DELIBERATELY REGISTERED WITHOUT --drive. The watcher OBSERVES on this schedule; the
# autofire runner has its own evening task with its own guards. Flipping this task to
# --drive is a one-word change J (or a session, under OP-0 -- it is reversible and paper-
# only) can make once the watcher has a few quiet days of ledger behind it. Watch first,
# drive second, in that order on purpose.
#
# Window-leak discipline (L41/C8): wscript -> run_exe_hidden.vbs -> system pythonw chain,
# same as every other headless task on this box. Weekly Mon-Sun trigger with repetition,
# never -Once (project memory: one-time triggers go dark after a day).

$ErrorActionPreference = "Stop"
$TaskName = "Gamma_Watcher"
$Repo     = "C:\Users\jackw\Desktop\42"
$Vbs      = Join-Path $Repo "setup\scripts\run_exe_hidden.vbs"
$Pythonw  = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$Script   = Join-Path $Repo "setup\scripts\gamma_watcher.py"

if (-not (Test-Path $Pythonw)) { Write-Error "pythonw not found at $Pythonw"; exit 1 }
if (-not (Test-Path $Script))  { Write-Error "gamma_watcher.py not at $Script"; exit 1 }
if (-not (Test-Path $Vbs))     { Write-Error "run_exe_hidden.vbs not at $Vbs"; exit 1 }

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "`"$Vbs`" `"$Pythonw`" `"$Script`"" `
    -WorkingDirectory $Repo

$start = (Get-Date).Date.AddMinutes(7)   # off the :00/:05 herd the other tasks stampede on
$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday `
    -At $start
# [TimeSpan]::MaxValue serialises to a Duration the task XML rejects
# ("P99999999DT23H59M59S ... out of range"). 1 day is the correct span anyway: the WEEKLY
# trigger re-fires the chain each day, and the repetition only has to cover one of them.
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $start `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Hours 23 -Minutes 59)).Repetition

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description ("Gamma command-center self-watch (J directive 2026-08-29). Every 15 min, 24/7: " +
    "companion liveness, per-session context pressure, pulse freshness, cost line, autofire-ledger " +
    "health, goal drift. Writes automation/state/watcher-report.json + watcher-ledger.jsonl EVERY " +
    "tick including all-quiet -- silence and all-quiet are different claims. OBSERVE-ONLY: no " +
    "--drive flag; consequence stays behind autofire_cards.py's own guards. `$0/tick, no LLM. " +
    "Kill: Disable-ScheduledTask Gamma_Watcher.") | Out-Null

Write-Output "OK: Registered $TaskName (every 15 min, 24/7, observe-only)"
Write-Output "    Chain: wscript -> run_exe_hidden.vbs -> pythonw -> gamma_watcher.py"
Write-Output "    Verify: Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo"
