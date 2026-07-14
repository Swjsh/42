#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_ContextBundle -- the multi-timeframe TREND-ALIGNMENT context bundle
  producer (Phase 0, context-enrichment plan, 2026-07-14).

  PURPOSE: answers J's 2026-07-14 question ("do we cross-correlate any information before
  acting on signals... it should be calculated beforehand and tagged onto the signal").
  Every 5 minutes during RTH, context_bundle_producer.py --once pulls SPY daily(~6mo) /
  hourly(~3wk) / 15m(~5d) bars via direct Alpaca REST (TV-independent, same un-blockable
  path as heartbeat_core/sight_beacon), runs crypto/lib/market_structure.py::analyze_structure
  on each timeframe (the SAME structure primitive the live structure_veto gate already uses
  on today's 5m bars), and writes automation/state/context-bundle.json: per-timeframe trend
  state + an alignment_score in [-3,+3] + a per-direction trend_alignment read. Off the hot
  path by design -- the 1-min heartbeat tick just reads this file (heartbeat_core.py's
  _read_context_bundle), it never computes multi-day structure inline.

  PHASE 0 IS LOGGED-ONLY / ZERO-BEHAVIOR-CHANGE: heartbeat_core tags the bundle onto
  bar_ctx + the decision row for VISIBILITY only -- nothing on score/gates/_derive_tier
  reads it this phase. This task places NO order, touches NO broker credentials, and never
  edits the live params/doctrine -- read-only market data in, one JSON state file out.

  WIRING PATTERN (flash-free, matches install-futures-mirror.ps1 / install-crypto-twin.ps1):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> context_bundle_producer.py --once
  Runs on the BACKTEST venv (not system Python) because the script imports pandas +
  crypto.lib.market_structure/trendlines/bar, matching Gamma_FuturesMirror's interpreter
  choice. The script itself carries the OP-27 L41 layer-3 headless stdio redirect (copied
  verbatim from confluence_producer.py / firm_brief.py / free_model_audit.py, 2026-07-14) so
  a pythonw launch never allocates a visible console window even without this wscript relay
  -- defense in depth, same pattern as every other 2026-07-14 popup-storm fix.

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 09:30 ET -> 07:30 MT. NEVER pass an
  ET literal to -At. A REPEATING trigger (Once + 5-min RepetitionInterval + RepetitionDuration
  spanning RTH), never a one-shot TimeTrigger (which would go dark the next day --
  project_scheduled_task_onetime_trigger_dark).

  REAPER EXEMPTION: setup/scripts/_shared.ps1's Stop-StaleClaudeProcesses reaps stale
  python.exe/claude.exe/etc referencing this repo every ~3-5 min via a Win32_Process -Filter
  Name clause that does NOT include pythonw.exe -- this task's spawned process is never even
  fetched by the reaper's query (same primary exemption Gamma_CryptoTwin documents). Defense
  in depth: launched via backtest\.venv\Scripts\pythonw.exe, whose CommandLine also contains
  the literal substring 'backtest\.venv' (one of $EXEMPT_DAEMONS's existing entries).

  To verify after running: Get-ScheduledTask -TaskName Gamma_ContextBundle | Get-ScheduledTaskInfo
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_ContextBundle" -Confirm:$false
          (plus, to fully revert Phase 0: remove the two heartbeat_core.py tag lines --
          see STATUS.md's dated entry for the exact revert.)
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root        = "C:\Users\jackw\Desktop\42"
$vbs         = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script      = Join-Path $root "setup\scripts\context_bundle_producer.py"
$etz         = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName    = "Gamma_ContextBundle"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

foreach ($p in @($vbs, $pythonwVenv, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

function Show-NextET {
    param([string]$Name)
    $info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction SilentlyContinue
    if ($info -and $info.NextRunTime) {
        $et = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
        Write-Host ("  NextRun ET: {0}" -f $et.ToString("yyyy-MM-dd HH:mm"))
    } else {
        Write-Host "  NextRun ET: (none / on-demand)"
    }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> backtest venv pythonw -> context_bundle_producer.py --once
$wscriptArgs = "//nologo `"$vbs`" `"$pythonwVenv`" `"$script`" --once"

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 07:30 MT = 09:30 ET start; repeat every 5 min for 6h30m -> covers 09:30-16:00 ET.
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "07:30"
$rep = (New-ScheduledTaskTrigger -Once -At "07:30" `
        -RepetitionInterval (New-TimeSpan -Minutes 5) `
        -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 30)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 4) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description ("Multi-timeframe TREND-ALIGNMENT context bundle producer (Phase 0, " + `
    "context-enrichment plan, 2026-07-14). Every 5 min, 09:30-16:00 ET weekdays. " + `
    "context_bundle_producer.py --once: pulls SPY daily/hourly/15m bars via direct Alpaca " + `
    "REST, runs crypto/lib/market_structure.analyze_structure per timeframe (same primitive " + `
    "the live structure_veto gate uses), writes automation/state/context-bundle.json " + `
    "(per-TF trend + alignment_score [-3,+3] + trend_alignment). LOGGED ONLY -- " + `
    "heartbeat_core.py tags it onto bar_ctx + the decision row for visibility; nothing on " + `
    "score/gates/_derive_tier reads it this phase (zero-behavior-change, guard: " + `
    "test_context_bundle_tag_no_behavior_change.py). Places NOTHING, no broker, no creds " + `
    "beyond read-only market-data REST. Fail-open (exits 0 always, degraded:true + reason " + `
    "on any timeframe fetch failure).") `
    -Force | Out-Null

Write-Host "Registered $taskName (07:30 MT = 09:30 ET start, every 5 min for 6h30m, Mon-Fri)"
Show-NextET $taskName
Write-Host ""
Write-Host "Context bundle producer wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_ContextBundle | Get-ScheduledTaskInfo"
