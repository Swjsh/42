#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_DayTypeLabels -- the nightly $0 refresh of the F5 day-type classifier's
  label table + no-look-ahead feature snapshots, per
  analysis/recommendations/prereg-day-type-classifier-2026-09-03.md.

.DESCRIPTION
  backtest/tools/day_type_labels.py rebuilds (in full, every run -- the two input files are
  small enough that a full recompute finishes in under a second, measured; no incremental
  cursor needed) analysis/recommendations/day-type-labels.json: one row per trading session
  since 2026-07-01, carrying (a) the REALIZED label (paying/tax/mixed/no_trade/in_progress,
  from automation/state/fills-ledger.jsonl broker-truth fills, FIFO-matched per activity)
  and (b) two no-look-ahead feature snapshots (features_0935, features_0945) built from
  automation/state/core-decisions.jsonl. RESEARCH INSTRUMENT ONLY -- feeds the Kitchen/Chef
  free-swarm seed at strategy/candidates/_chef-inbox/2026-09-03-day-type-classifier-f5.md;
  never fits or ships a classifier itself, never touches params*.json/heartbeat_core.py/
  strategies.py/accounts.json, never places an order. Read-only on automation/state/**.

  WHY NIGHTLY: the Kitchen swarm (Chef persona + kitchen_daemon.py cook workers) will be
  grinding against day-type-labels.json over the coming days per the inbox seed above --
  keeping it current as each new session closes (today's `in_progress` row finalizes to a
  real label the next trading day) means the swarm is never working off a stale table
  without J or a future session having to notice and re-run it by hand (CLAUDE.md's
  repeated-question-is-a-missing-instrument rule).

  16:50 ET weekdays = 14:50 MT (this box runs Mountain time; ET = local+2) -- after
  Gamma_EodFlatten (15:55), Gamma_ChopMeter (16:08), Gamma_WinnerAutopsy (16:25),
  Gamma_LadderRungShadow (16:40) and Gamma_Tp1R50ForwardShadow/Gamma_TrendlineTightExitShadow
  (16:40/16:45) -- fills-ledger.jsonl for the session is settled by then. PT15M/PT30M
  self-heal window covers a missed single-daily trigger (same remedy already shipped for the
  evening-window task family).

  WIRING (stdlib-only -- no pandas/numpy import anywhere in day_type_labels.py, verified this
  build; system pythonw, not the backtest venv -- nothing this script needs requires the
  venv's installed packages):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> day_type_labels.py

  Output:
    analysis/recommendations/day-type-labels.json   FULL REBUILD every run (not append-only
                                                      -- see the script's own docstring for
                                                      why a cursor is unnecessary here)

  Per CLAUDE.md OP-3 ($0, pure Python stdlib over two already-written JSONL files), OP-25
  (fail loud -- every unavailable feature is emitted as null with an explicit *_reason field,
  never fabricated), OP-33 (visibility is the product). Guard:
  backtest/tests/test_day_type_labels_2026_09_03.py (12/12).
  REVOKE (whole instrument, one shot): Unregister-ScheduledTask -TaskName Gamma_DayTypeLabels
  -Confirm:$false -- nothing on the trading path depends on this task (analysis-only leaf,
  same class as Gamma_LadderRungShadow / Gamma_Tp1R50ForwardShadow).
#>

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "backtest\tools\day_type_labels.py"
$taskName     = "Gamma_DayTypeLabels"

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

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 14:50 MT (16:50 ET) weekdays -- -Weekly triggers come back with a null .Repetition CIM
# instance; steal one from a throwaway -Once trigger built with the repetition params
# (documented PS workaround, same technique install-tp1-r50-forward-shadow.ps1 uses).
# PT15M/PT30M self-heal window on a missed single-daily fire.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:50"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "14:50" `
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
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Weekdays 14:50 MT (16:50 ET), self-heals every 15 min for 30 min on a " + `
    "missed fire: full rebuild of analysis/recommendations/day-type-labels.json (F5 day-type " + `
    "classifier's realized label table + no-look-ahead 09:35/09:45 feature snapshots) per " + `
    "the frozen prereg " + `
    "analysis/recommendations/prereg-day-type-classifier-2026-09-03.md. Feeds the Kitchen/" + `
    "Chef free-swarm seed strategy/candidates/_chef-inbox/2026-09-03-day-type-classifier-" + `
    "f5.md. RESEARCH ONLY -- fits nothing, ships nothing, places no order. `$0. Guard: " + `
    "backtest/tests/test_day_type_labels_2026_09_03.py. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_DayTypeLabels -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- weekdays 14:50 MT (16:50 ET), self-heals 15min/30min."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
