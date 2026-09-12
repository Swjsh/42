#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_SdZonesProducer -- headless, $0 supply/demand zone producer
  (GOAL-SD-LIQUIDITY-ZONES-2026-09-11 item b, automation/state/goals/GOAL-SD-LIQUIDITY-
  ZONES-2026-09-11.md).

.DESCRIPTION
  Runs setup/scripts/sd_zones_producer.py: reads the `Smart Money Concepts [LuxAlgo]`
  study's order-block boxes headlessly over CDP (tv_cdp.TvChart.pine_boxes, added
  2026-09-12 -- same mechanism the TradingView MCP's getPineBoxes uses), scores each
  against real SPY 5m bars via the ALREADY-RATIFIED `_uniform_touches` math (imported
  read-only from refresh_levels_intraday.py, zero edits to that frozen file), and writes
  `automation/state/sd-zones.json` -- a SHADOW file, never key-levels.json. Runs WITHOUT
  --draw by default (the LuxAlgo study already paints these same boxes on the chart; J's
  most recent chart directive was "remove all lines other than the most touched ones,
  there are too many", 2026-09-11 -- a second redundant rendering works against that).

  WHY A NEW TASK, NOT INSIDE Gamma_LevelRefresh: refresh_levels_intraday.py (the level
  refresher this producer would otherwise piggyback on) was added to
  setup/hooks/doctrine.FROZEN_TRADING_PATH on 2026-09-11 for the September clean window
  (through 2026-10-30). This is a brand-new file/task -- the freeze cannot apply to code
  that does not yet exist -- so a separate lightweight task is the only freeze-compliant
  path to a live refresh cadence.

  FAIL-OPEN: TradingView/CDP down (market closed, or TV not launched yet) preserves the
  PRIOR zones untouched with status=SKIPPED_TV_DOWN, exit 0 -- never raises into the
  scheduler, never wipes sd-zones.json to empty. This state file is deliberately unwired
  from engine_health.py -- its absence/staleness can never turn the engine RED.

  VERIFIED LIVE 2026-09-12: real run against the live BATS:SPY chart -- read 10 boxes from
  Smart Money Concepts [LuxAlgo], classified 5 supply / 3 demand / (2 folded by touch
  count), touches_uniform 1-17 against real 5m bars, wrote sd-zones.json. --draw mode also
  verified live (10 rectangles created + removed in the same session, chart left clean).

  WIRING (cloned from install-trendline-headless-draw.ps1 -- same reasoning applies
  verbatim): system pythonw (GUI subsystem, allocates no console) + PYTHONPATH onto the
  backtest venv's site-packages via run_py_venv_hidden.py (needed for pandas + pytz +
  websockets), NEVER the venv's own pythonw (WindowsTerminal -Embedding host leak on
  complex imports -- window-leak-detector's 2026-07-14/2026-08-13 root-cause finding).
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_py_venv_hidden.py ->
      sd_zones_producer.py

  SCHEDULE: 08:44 ET weekdays (06:44 MT -- box runs Mountain time) -- AFTER
  Gamma_ChartAutoDraw (08:35) and Gamma_TrendlineHeadlessDraw (08:40) so the study/levels
  exist first and the three headless CDP tasks never race on the same websocket (5-min
  stagger); repeats every 15 min through ~16:00 ET -- zones change slower than 5m price
  levels, so a lighter cadence than the trendline/level refreshers is deliberate.

  Per CLAUDE.md OP-25 (fail loud) + OP-3 ($0). Guard:
  backtest/tests/test_sd_zones_producer_2026_09_12.py (12/12, safety mutation RED-proofed
  live this session). To disable:
  Unregister-ScheduledTask -TaskName Gamma_SdZonesProducer -Confirm:$false
#>

$ErrorActionPreference = "Stop"
$Root       = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName   = "Gamma_SdZonesProducer"

$sysPythonw      = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runExeHidden    = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$runPyVenvHidden = Join-Path $ScriptsDir "run_py_venv_hidden.py"
$worker          = Join-Path $ScriptsDir "sd_zones_producer.py"

foreach ($p in @($sysPythonw, $runExeHidden, $runPyVenvHidden, $worker)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript //nologo run_exe_hidden.vbs <sys-pythonw> run_py_venv_hidden.py <sd_zones_producer.py>
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runPyVenvHidden`" `"$worker`""

# 06:44 LOCAL (Mountain) = 08:44 ET weekdays; repeat every 15 min for ~7h16m (through ~16:00 ET).
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "06:44"
$rep = (New-ScheduledTaskTrigger -Once -At "06:44" `
        -RepetitionInterval (New-TimeSpan -Minutes 15) `
        -RepetitionDuration (New-TimeSpan -Hours 7 -Minutes 16)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Headless, `$0 supply/demand zone producer (GOAL-SD-LIQUIDITY-ZONES-2026-09-11 item b). Reads Smart Money Concepts [LuxAlgo] order-block boxes via tv_cdp.TvChart.pine_boxes, scores via refresh_levels_intraday._uniform_touches (imported read-only), writes automation/state/sd-zones.json (SHADOW file, never key-levels.json). No --draw by default. Fail-open: TV down = SKIPPED_TV_DOWN, exit 0, prior zones preserved. Weekly Mon-Fri 06:44 MT (08:44 ET), repeat 15min for ~7h16m." `
    | Out-Null

# ---- VERIFY, DON'T CLAIM (OP-33): registered + enabled + will fire.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
$trigType = $t.Triggers[0].CimClass.CimClassName
if ($trigType -ne "MSFT_TaskWeeklyTrigger") { Write-Error "$TaskName trigger is $trigType, expected MSFT_TaskWeeklyTrigger"; exit 1 }
if ($null -eq $info.NextRunTime) { Write-Error "$TaskName has a NULL NextRunTime -- it would never fire"; exit 1 }
Write-Output "OK: Registered $TaskName  State=$($t.State)  Trigger=$trigType  NextRun=$($info.NextRunTime)"
