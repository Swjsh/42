# Registers Gamma_KalshiLiquiditySurvey -- twice-daily weekday RTH re-run of the Kalshi
# ATM liquidity survey.
#
# WHY (queue.md KALSHI-RTH-LIQUIDITY-RERUN, LOW-MEDIUM, filed 2026-08-23 Fable
# profitability sweep): the 34-36c index-series spread reading that blocks the
# reuse-spy-signal Kalshi lane (KXINXU/KXINX) came from a SUNDAY, quote-starved sample
# -- Kalshi order books are thinner off-session, the same C4/edge-hunt lesson class this
# repo already knows from equities. The $0 unblock the item names: re-run
# research/kalshi/kalshi_liquidity_survey.py during weekday RTH so the reading reflects
# real conditions before any lane decision (ask J for the API key, or retarget/park) is
# made. Interactive Claude sessions are banned 09:30-15:55 ET (CLAUDE.md), so this has
# to be a scheduled fire, not a manual one.
#
# The item's second ask -- "no scheduled task was ever registered for the shadow
# ticker -- register one or formally park the lane" -- is answered by registering THIS
# task. The decision rule itself (3 consecutive weekday-RTH passes on the 5c gate -> ask
# J for the key; otherwise retarget to BTC daily or park) lives in the script's own
# module docstring (research/kalshi/kalshi_liquidity_survey.py), not duplicated here --
# this installer only wires the measurement, it does not decide anything.
#
# SCRIPT: research/kalshi/kalshi_liquidity_survey.py -- pure stdlib (json, statistics,
# urllib), public Kalshi market-data GET endpoints only (/markets, /markets/{t}/
# orderbook on api.elections.kalshi.com), NO Authorization header anywhere in the
# script, NO account, NO orders -- verified by reading the script's _get() helper
# before wiring this task. System pythonw is sufficient (no venv-only deps).
#
# CADENCE: two fires per weekday, spanning the RTH session so a single early/late book
# doesn't decide the read -- 10:30 ET (08:30 MT) and 14:30 ET (12:30 MT), each a
# -Weekly Mon-Fri trigger with a bounded PT15M/PT30M self-heal repetition (every 15 min
# for 30 min after the primary fire) -- the same missed-trigger-recovery shape already
# shipped on Gamma_MacroCalendar/Gamma_EarningsCalendar/Gamma_FuturesEod2/
# Gamma_FeeRecalibrate after a single-fire trigger silently missed a day on this box.
# NOT a bare one-shot trigger (would fire once, ever, then go dark -- the exact class
# backtest/tests/test_no_recurring_task_has_a_one_time_trigger_2026_09_03.py guards).
#
# WIRING: system pythonw only (script is pure stdlib):
#   wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#     -- system pythonw -> kalshi_liquidity_survey.py
#
# Output: analysis/kalshi/liquidity-survey-<ET date>.json (one dated snapshot per day;
# the 14:30 ET fire overwrites the same day's file with the later-session read -- fine,
# both fires' stdout (incl. the 5C-GATE summary line) land in
# automation/state/logs/run-cmd-hidden-<date>.log for the evidence trail). Nothing on
# the trading path reads this file.
#
# Per CLAUDE.md OP-3 ($0, pure Python stdlib, no LLM), OP-25 (fail loud -- the script's
# existing _get() already returns {"_error": ...} rather than crashing on a dead venue),
# OP-33 (visibility is the product -- the 5C-GATE line is the human-skimmable summary).
# REVOKE: Unregister-ScheduledTask -TaskName Gamma_KalshiLiquiditySurvey -Confirm:$false

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$repo         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $repo "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $repo "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $repo "research\kalshi\kalshi_liquidity_survey.py"
$taskName     = "Gamma_KalshiLiquiditySurvey"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

foreach ($p in @($vbs, $sysPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$repo`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $repo

# Two weekday fires spanning RTH: 10:30 ET (08:30 MT) and 14:30 ET (12:30 MT). Box runs
# Mountain time, ET = local+2 (CLAUDE.md clock-discipline banner) -- -At times below are
# LOCAL (Mountain), matching every other installer's convention in this repo.
#
# -Weekly triggers come back with a null .Repetition CIM instance -- steal one from a
# throwaway -Once trigger built with the repetition params (documented PS workaround;
# direct property assignment on the null instance throws PropertyNotFound) -- same
# technique install-earnings-calendar.ps1 / install-fee-recalibrate.ps1 already use.
$triggerMorning = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "08:30"
$triggerMorning.Repetition = (New-ScheduledTaskTrigger -Once -At "08:30" `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition

$triggerAfternoon = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "12:30"
$triggerAfternoon.Repetition = (New-ScheduledTaskTrigger -Once -At "12:30" `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger @($triggerMorning, $triggerAfternoon) `
    -Settings $settings `
    -Principal $principal `
    -Description ("Twice-daily weekday RTH re-run (10:30 ET / 14:30 ET, each self-heals " + `
    "every 15 min for 30 min on a missed fire) of the Kalshi ATM liquidity survey " + `
    "(research/kalshi/kalshi_liquidity_survey.py) -- queue.md " + `
    "KALSHI-RTH-LIQUIDITY-RERUN's $0 unblock for the reuse-spy-signal lane " + `
    "(KXINXU/KXINX). Public GET endpoints only, no auth, no orders. Writes " + `
    "analysis/kalshi/liquidity-survey-<ET date>.json + prints one 5C-GATE summary " + `
    "line per series. Decision rule lives in the script's own module docstring: 3 " + `
    "consecutive weekday-RTH passes on the 5c gate -> ask J for the API key; " + `
    "otherwise retarget to BTC daily or park. `$0. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_KalshiLiquiditySurvey -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- 10:30 ET + 14:30 ET weekdays, self-heals 15min/30min."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
