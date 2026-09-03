#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_TrendlineHeadlessDraw -- headless, $0 trendline chart-drawing runner
  (TRENDLINE-DRAW-HEADLESS, 2026-09-03, automation/overnight/queue.md).

.DESCRIPTION
  THE GAP THIS CLOSES: `trendline-draw-state.json` last_run 2026-08-27
  status=skipped reason='budget conservation' -- premarket Step 5c (an LLM-
  discretionary step) chose not to run a $0 deterministic job, while
  `setup/scripts/trendline_chart_draw.py` (built 2026-08-09, computes what to draw
  via `backtest/lib/trendline_detector.py`) sat unused. That module's own header
  justified being LLM-only by citing a "cannot run from a headless scheduled task"
  constraint that `Gamma_ChartAutoDraw` (2026-08-06) had ALREADY disproved three
  days before the constraint was written down.

  Runs `setup/scripts/trendline_headless_draw.py`: imports
  `trendline_chart_draw.compute_draw_payload` (unchanged, no MCP calls) to compute
  what to draw, and draws it via `tv_cdp.TvChart.create_trend_line`
  (`createMultipointShape`, the correct CDP call for a 2-point shape -- discovered
  live this session; `createShape` throws "Wrong points count for trend_line.
  Required 2" for a trend_line). SAME headless CDP mechanism `draw_key_levels.py`
  already runs in production via `Gamma_ChartAutoDraw` -- no MCP, no LLM, $0.

  VERIFIED LIVE 2026-09-03: create -> text readback -> remove cycle, then a full
  production run against the real BATS:SPY chart -- drew 2 real lines, left the
  chart's other 22 pre-existing trend_line shapes untouched, redrew idempotently
  on a second run (removed exactly its own prior 2, drew 2 new).

  SAFETY: only ever creates/removes `trend_line`-named shapes (a `horizontal_line`
  -- J's manual lines OR draw_key_levels.py's key-level lines -- is structurally
  out of reach); removes only its own by recorded entity_id or the `[GTL] ` text
  TAG (distinct from draw_key_levels.py's `[G] ` tag, so the two producers can
  never mistake each other's drawings); never calls `draw_clear`/
  `removeAllShapes()`. Fail-open: TradingView/CDP down -> stamp
  `status=SKIPPED_TV_DOWN`, exit 0, never raises into the scheduler. State:
  `automation/state/trendline-headless-draw.json` -- a NEW stamp, separate from
  the OLD LLM-path `trendline-draw-state.json` (never touched by this script).

  WIRING (cloned from setup/install-chart-auto-draw.ps1, the ONE other headless
  CDP-drawing task in the repo -- same reasoning applies verbatim): system
  pythonw (GUI subsystem, allocates no console) + PYTHONPATH onto the backtest
  venv's site-packages via `run_py_venv_hidden.py` (needed for `pytz` +
  `websockets`, neither present in the bare system Python313), NEVER the venv's
  own pythonw (which allocates a WindowsTerminal -Embedding host on complex
  imports -- window-leak-detector's 2026-07-14/2026-08-13 root-cause finding).
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_py_venv_hidden.py ->
      trendline_headless_draw.py

  SCHEDULE: 08:40 ET weekdays (06:40 MT -- box runs Mountain time) -- AFTER
  Gamma_ChartAutoDraw's 08:35 ET so key levels exist first, per the queue item's
  own instruction -- then every 30 min through ~16:10 ET (mirrors
  Gamma_ChartAutoDraw's 08:35-16:05 cadence, offset +5 min so the two never race
  on the same CDP websocket).

  Per CLAUDE.md OP-25 (fail loud) + OP-3 ($0). Guard:
  backtest/tests/test_trendline_headless_draw_2026_09_03.py (9/9, 4 mutations
  RED-proofed). To disable:
  Unregister-ScheduledTask -TaskName Gamma_TrendlineHeadlessDraw -Confirm:$false
#>

$ErrorActionPreference = "Stop"
$Root       = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName   = "Gamma_TrendlineHeadlessDraw"

$sysPythonw      = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runExeHidden    = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$runPyVenvHidden = Join-Path $ScriptsDir "run_py_venv_hidden.py"
$worker          = Join-Path $ScriptsDir "trendline_headless_draw.py"

foreach ($p in @($sysPythonw, $runExeHidden, $runPyVenvHidden, $worker)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript //nologo run_exe_hidden.vbs <sys-pythonw> run_py_venv_hidden.py <trendline_headless_draw.py>
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runPyVenvHidden`" `"$worker`""

# 06:40 LOCAL (Mountain) = 08:40 ET weekdays; repeat every 30 min for 7h30m (through ~16:10 ET).
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "06:40"
$rep = (New-ScheduledTaskTrigger -Once -At "06:40" `
        -RepetitionInterval (New-TimeSpan -Minutes 30) `
        -RepetitionDuration (New-TimeSpan -Hours 7 -Minutes 30)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Headless, `$0 trendline chart-drawing runner (TRENDLINE-DRAW-HEADLESS 2026-09-03). Draws via tv_cdp.TvChart.create_trend_line (createMultipointShape), the same headless CDP mechanism draw_key_levels.py/Gamma_ChartAutoDraw already runs in production -- no MCP, no LLM. Fail-open: TV down = SKIPPED_TV_DOWN, exit 0. Only ever touches trend_line shapes tagged '[GTL] ' or recorded in its own state; never a horizontal_line, never draw_clear. Weekly Mon-Fri 06:40 MT (08:40 ET), repeat 30min for 7h30m -- after Gamma_ChartAutoDraw so key levels exist first." `
    | Out-Null

# ---- VERIFY, DON'T CLAIM (OP-33): registered + enabled + will fire.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
$trigType = $t.Triggers[0].CimClass.CimClassName
if ($trigType -ne "MSFT_TaskWeeklyTrigger") { Write-Error "$TaskName trigger is $trigType, expected MSFT_TaskWeeklyTrigger"; exit 1 }
if ($null -eq $info.NextRunTime) { Write-Error "$TaskName has a NULL NextRunTime -- it would never fire"; exit 1 }
Write-Output "OK: Registered $TaskName  State=$($t.State)  Trigger=$trigType  NextRun=$($info.NextRunTime)"
