#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_JDrawnLinesLedger -- nightly, $0 capture + scoring of J's own drawn
  trend lines (TRENDLINE-J-DRAWN-LINES-LEDGER, 2026-09-03, queue HIGH).

.DESCRIPTION
  Two frozen mechanical reconstructions of J's rising-support anchor logic
  (trendline-historical-study.md, trendline-today-exhibit.md) both failed to reproduce his
  actual drawn line. This instrument stops guessing and reads the line he actually drew,
  straight off the chart -- full rule:
  analysis/recommendations/prereg-trendline-j-drawn-lines-2026-09-03.md.

  Runs, in order, every fire:
    1. setup/scripts/j_drawn_lines_capture.py  -- connects via the same headless CDP path
       trendline_headless_draw.py already runs in production (tv_cdp.TvChart, no MCP, no
       LLM), reads every non-engine-tagged trend_line on the SPY chart (read-only: no
       createShape/createMultipointShape/removeEntity call exists in the file), dedupes by
       TradingView's own entity_id against the ledger, restores the chart's original
       resolution before exit (verified, not merely attempted).
    2. setup/scripts/j_drawn_lines_score.py    -- scores every `rising`-shaped ledger line
       against cached 1m bars, starting strictly AFTER the line's own first_seen date (no
       look-ahead), writes the summary + decision status.

  VERIFIED LIVE 2026-09-03: capture found 23 non-engine trend_line shapes (2 "[GTL] "
  engine-tagged lines correctly excluded), resolution restored ok=True both times, a
  second run deduped to new=0/already_known=23. Scorer ran clean: 14 rising / 9
  non-rising-excluded, decision status=ACCRUING (0 forward sessions yet -- correct, since
  every captured line's first_seen_date_et is today and no-look-ahead forbids scoring
  today's own bars).

  SAFETY: capture-side is read-only against drawings by construction (no mutating chart
  method is ever called); resolution is always restored and the restore is verified before
  exit. Fail-open: TradingView/CDP down -> capture stamps `status=SKIPPED_TV_DOWN`, exit 0,
  scorer still runs against whatever is already in the ledger (never blocked by a
  live-chart outage). Never live, never paper -- prereg section 6.

  WIRING (cloned from setup/install-trendline-headless-draw.ps1 -- same reasoning applies
  verbatim): system pythonw (GUI subsystem, no console) + PYTHONPATH onto the backtest
  venv's site-packages via run_py_venv_hidden.py (needed for `websockets`/`pytz`, absent
  from bare system Python313), NEVER the venv's own pythonw (window-leak-detector's
  2026-07-14/2026-08-13 root-cause finding).
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_py_venv_hidden.py -> <script>.py

  SCHEDULE: 16:30 ET weekdays (14:30 MT -- box runs Mountain time), AFTER market close and
  AFTER the 16:30 ET EOD pipeline's own chart-touching steps settle. Two sequential actions
  in one task (capture, then score) -- ExecutionTimeLimit PT15M covers both comfortably;
  MultipleInstances IgnoreNew prevents a slow CDP round-trip from double-firing on the next
  polling tick (PT30M repetition window, matching the trendline-headless-draw sibling's own
  cadence convention, in case a retry pass is ever added).

  Per CLAUDE.md OP-25 (fail loud) + OP-3 ($0). Guard:
  backtest/tests/test_j_drawn_lines_2026_09_03.py (13/13). To disable:
  Unregister-ScheduledTask -TaskName Gamma_JDrawnLinesLedger -Confirm:$false
#>

$ErrorActionPreference = "Stop"
$Root       = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName   = "Gamma_JDrawnLinesLedger"

$sysPythonw      = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runExeHidden    = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$runPyVenvHidden = Join-Path $ScriptsDir "run_py_venv_hidden.py"
$captureWorker   = Join-Path $ScriptsDir "j_drawn_lines_capture.py"
$scoreWorker     = Join-Path $ScriptsDir "j_drawn_lines_score.py"

foreach ($p in @($sysPythonw, $runExeHidden, $runPyVenvHidden, $captureWorker, $scoreWorker)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript //nologo run_exe_hidden.vbs <sys-pythonw> run_py_venv_hidden.py <script>.py
$captureAction = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runPyVenvHidden`" `"$captureWorker`""
$scoreAction = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runPyVenvHidden`" `"$scoreWorker`""

# 14:30 LOCAL (Mountain) = 16:30 ET weekdays.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:30"
$rep = (New-ScheduledTaskTrigger -Once -At "14:30" `
        -RepetitionInterval (New-TimeSpan -Minutes 30) `
        -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action @($captureAction, $scoreAction) -Trigger $trigger -Settings $settings `
    -Description "Nightly, `$0 capture + scoring of J's own drawn trend lines (TRENDLINE-J-DRAWN-LINES-LEDGER 2026-09-03). Capture reads via tv_cdp.TvChart (read-only, no create/remove call exists in the file), dedupes by entity_id, restores chart resolution (verified). Score runs no-look-ahead TOUCH/BREAK scoring on rising-shaped lines only, forward from first_seen date. Fail-open: TV down = capture SKIPPED_TV_DOWN exit 0, scorer still runs off the existing ledger. Never live/paper -- shadow-only. Weekly Mon-Fri 14:30 MT (16:30 ET), after market close." `
    | Out-Null

# ---- VERIFY, DON'T CLAIM (OP-33): registered + enabled + will fire.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
$trigType = $t.Triggers[0].CimClass.CimClassName
if ($trigType -ne "MSFT_TaskWeeklyTrigger") { Write-Error "$TaskName trigger is $trigType, expected MSFT_TaskWeeklyTrigger"; exit 1 }
if ($t.Actions.Count -ne 2) { Write-Error "$TaskName has $($t.Actions.Count) actions, expected 2 (capture, score)"; exit 1 }
if ($null -eq $info.NextRunTime) { Write-Error "$TaskName has a NULL NextRunTime -- it would never fire"; exit 1 }
Write-Output "OK: Registered $TaskName  State=$($t.State)  Trigger=$trigType  Actions=$($t.Actions.Count)  NextRun=$($info.NextRunTime)"
