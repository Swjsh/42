#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_Prospector -- the exogenous-idea organ (J 2026-07-09: "these are
  things gamma should be thinking of on its own! where is the autonomy? gamma
  hasn't introduced a single new idea like this at all yet").

  PURPOSE: every existing idea-producing organ is ENDOGENOUS -- trade_autopsy
  mines OUR OWN losses, chef proposes OUR OWN strategy variants, kitchen/grinders
  tune OUR OWN knobs, swarm_consult reviews OUR OWN proposals. None of them scan
  OUTWARD: new data feeds, indicator ecosystems, community tooling, academic
  intraday anomalies, cross-asset tells. prospector.py is that organ: one nightly
  fire rotates through 7 fixed research beats, dispatches ONE free-tier LLM scan
  per beat, triages the response into a structured idea-ledger row (idempotent by
  dedupe_key; killed ideas never re-enter), and promotes the single oldest
  not-yet-promoted 'battery-ready' idea into strategy/candidates/_chef-inbox/ as a
  pre-registered STUDY SPEC stub (hypothesis/data/null/pass bar -- NOT code) --
  the SAME standing intake Chef already drains every wake. Full design:
  markdown/infra/PROSPECTOR-SPEC.md.

  The script is notify-only / propose-only: it never touches engine/params/exits,
  never places an order, and only ever writes its OWN ledger/state files plus a
  markdown stub into Chef's inbox + a Discord one-liner. $0 (free-tier LLM lane
  only, sequential-until-success, no paid fallback). Fail-open: any failure
  (including "no free lane up tonight") is logged and the run exits 0, leaving
  the ledger fully intact and readable.

  WIRING PATTERN (flash-free, matches trade_autopsy + broker_fills + kitchen):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> prospector.py
  backtest\.venv is required (not system Python) -- prospector.py imports
  swarm_consult.py, whose cerebras/groq lanes need the `openai` package that only
  lives in the backtest venv (project_backtest_venv_interpreter). Both wscript +
  pythonw are GUI-subsystem (no console allocation); the .vbs passes window=0 --
  no visible window flash ever (project_mcp_window_leak_fix).

  SCHEDULE: DAILY (not weekdays-only -- research/ideation needs no market hours,
  matching the Kitchen daemon's 24/7 cadence) at 19:30 MT = 21:30 ET. The trigger's
  first occurrence is EXPLICITLY forced to TOMORROW's date (never today's), so
  running this installer at any time of day/evening can never cause a same-night
  fire -- required by this build's own instruction ("it first fires on its
  schedule, never tonight").

  TZ RULE: this rig is Mountain Time (ET = local + 2h in DST). NEVER pass an ET
  literal to -At. Verify actual current time via setup\scripts\et_clock.py or
  PowerShell before relying on any offset arithmetic -- never guess it.

  To verify after running: Get-ScheduledTask -TaskName Gamma_Prospector
                            Get-ScheduledTaskInfo -TaskName Gamma_Prospector
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$script       = Join-Path $root "setup\scripts\prospector.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName     = "Gamma_Prospector"
# 2026-08-07: relay through run_cmd_hidden.py for real exit-code visibility -- see
# VBS-WRAPPER-EXIT-CODE-BLIND-SPOT / Gamma_CryptoTwin drift finding, queue.md.
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath   = Join-Path $root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"

foreach ($p in @($vbs, $script, $sysPythonw, $runCmdHidden)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

function Show-NextET {
    param([string]$Name)
    $info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction SilentlyContinue
    if ($info -and $info.NextRunTime) {
        $et = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
        Write-Host ("  NextRun (local): {0}" -f $info.NextRunTime)
        Write-Host ("  NextRun ET:      {0}" -f $et.ToString("yyyy-MM-dd HH:mm"))
    } else {
        Write-Host "  NextRun ET: (none / on-demand)"
    }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- backtest venv pythonw -> prospector.py (flash-free chain, real exit-code logged)
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# EVERY 4 HOURS, 24/7 (J directive 2026-07-09: "prospector runs on a 4hr cadence, not
# nightly. we're months in i need results, asap"). Originally nightly 21:30 ET; re-registered
# same night. Free-swarm scans are $0 so the cadence cost is zero; the 7-beat rotation
# completes a full cycle every ~28h at this rate.
$firstRun = (Get-Date).AddMinutes(5)
$trigger = New-ScheduledTaskTrigger -Once -At $firstRun `
    -RepetitionInterval (New-TimeSpan -Hours 4) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "The exogenous-idea organ (J 2026-07-09: 'gamma hasn't introduced a single new idea like this at all yet'). Daily 19:30 MT = 21:30 ET. prospector.py rotates through 7 outward-scanning research beats (free data feeds / TV community indicators / options structure metrics / academic intraday anomalies / cross-asset signals / futures positioning / microstructure internals), dispatches ONE free-tier LLM scan per beat (reuses swarm_consult.py's provider-call plumbing), triages the response into analysis/prospector/ideas-ledger.jsonl (idempotent by dedupe_key; killed ideas never re-enter), and promotes the single oldest not-yet-promoted battery-ready idea into strategy/candidates/_chef-inbox/ as a pre-registered STUDY SPEC stub (hypothesis/data/null/pass bar -- NOT code). Surfaces a one-liner on automation/state/firm-brief.md + Discord. Notify-only, propose-only, `$0 (free-tier only), fail-open, exits 0 always. Spec: markdown/infra/PROSPECTOR-SPEC.md. Guard: backtest/tests/test_prospector.py." `
    -Force | Out-Null

Write-Host "Registered $taskName (19:30 MT = 21:30 ET daily; first fire forced to tomorrow)"
Show-NextET $taskName
Write-Host ""
Write-Host "Prospector wired. Verify with: Get-ScheduledTask -TaskName Gamma_Prospector"
