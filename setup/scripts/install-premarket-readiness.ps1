#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_PremarketReadiness -- ONE deterministic morning readiness gate (WS2,
  2026-07-27).

.DESCRIPTION
  J had to ask "are we ready to trade?" this morning and the review missed 3 of 6 accounts
  (the SECOND time this class of miss happened -- see queue.md's FLEET-LIVENESS-IN-ENGINE-
  HEALTH item, filed 2026-07-27 ~10:00 ET). Later the same day the TV/CDP port was found dead
  and nobody had flagged it. `premarket_readiness.py` fuses 7 checks (every enabled fleet
  arm's broker reachability + today's ledger, the two core .mcp.json accounts, key-levels.json
  structural sanity, today-bias.json freshness, TV/CDP liveness, engine_health.py's own
  verdict, and Gamma_HeartbeatCore's Task Scheduler registration) into ONE GREEN/YELLOW/RED
  verdict, writes automation/state/premarket-readiness.json, and pings Discord once on a
  transition into a new red check. Read-only/notify-only, $0, no LLM, NEVER trade-halts.

  WIRING PATTERN (flash-free, matches install-daily-brief.ps1 exactly):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> premarket_readiness.py
  Runs on the BACKTEST venv -- automatically reaper-exempt (backtest\.venv is already in
  _shared.ps1's EXEMPT_DAEMONS substring list) and matches the interpreter engine_health.py's
  own optional gex-archive/pandas-touching imports were smoke-tested against (2026-07-27).

  TZ RULE: this rig is Mountain Time (ET = local + 2h, year-round -- both zones share the same
  DST calendar). 09:00 ET -> 07:00 MT. NEVER pass an ET literal to -At.
  WEEKLY trigger (Mon-Fri), NOT -Once (a one-shot TimeTrigger fires once ever then goes dark --
  project_scheduled_task_onetime_trigger_dark).

  2026-09-03 SINGLE-FIRE-TRIGGER-BLANKET-AUDIT fix (queue.md, class hit 3x already on
  Gamma_MacroCalendar/Gamma_EarningsCalendar/Gamma_FuturesEod2 -- a correctly-registered
  -Weekly Mon-Fri trigger can still silently skip ONE day's fire; Windows gives no forensic
  trail why, StartWhenAvailable does not catch it). This task feeds
  automation/state/premarket-readiness.json, a date-field-checked freshness consumer
  (state-freshness-manifest.json) read by premarket_readiness.py's own downstream gate --
  exactly the consumer class this audit prioritizes. Added the same bounded self-heal window
  as the other 3 fixes: every 15 min for 30 min after the primary 09:00 ET fire. Read-only/
  idempotent script, so the extra fires change nothing on a normal day.

  To verify after running:
    Get-ScheduledTask -TaskName Gamma_PremarketReadiness | Get-ScheduledTaskInfo
  REVERT:
    Unregister-ScheduledTask -TaskName "Gamma_PremarketReadiness" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath   = Join-Path $root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\premarket_readiness.py"
$taskName     = "Gamma_PremarketReadiness"
$atMT         = "07:00"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')

foreach ($p in @($vbs, $sysPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- backtest venv pythonw -> premarket_readiness.py (no args)
# (2026-08-08 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT migration -- was fire-and-forget.)
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At $atMT
# -Weekly triggers come back with a null .Repetition CIM instance -- steal one from a
# throwaway -Once trigger built with the repetition params (documented PS workaround, same
# idiom as install-macro-calendar.ps1 / install-earnings-calendar.ps1 / install-futures-eod.ps1;
# direct property assignment on the null instance throws PropertyNotFound). Self-heals a single
# missed fire within 30 min.
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $atMT -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description ("ONE deterministic morning readiness gate (WS2, 2026-07-27; queue.md " + `
    "FLEET-LIVENESS-IN-ENGINE-HEALTH). 09:00 ET weekdays (07:00 MT). premarket_readiness.py " + `
    "fuses 7 checks -- every ENABLED fleet arm's broker reachability + today's decision " + `
    "ledger (names the silent arm), the 2 core .mcp.json accounts, key-levels.json structural " + `
    "sanity (dated today, >=4 non-expired levels straddling spot, age<90m), today-bias.json " + `
    "freshness, TV/CDP liveness (advisory, never blocks), engine_health.py's own reused " + `
    "verdict, and Gamma_HeartbeatCore's Task Scheduler state -- into ONE GREEN/YELLOW/RED " + `
    "verdict written to automation/state/premarket-readiness.json, with one Discord ping on " + `
    "a NEW red-check transition. Read-only/notify-only, `$0, no LLM, NEVER trade-halts. Fails " + `
    "open internally (a broken checker degrades to UNKNOWN, never blocks the morning). " + `
    "Consumed by daily_brief.py's morning brief lead line. Guard: " + `
    "backtest/tests/test_premarket_readiness.py.") `
    -Force | Out-Null

Write-Host "Registered $taskName ($atMT MT = 09:00 ET, Mon-Fri)"
$info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
if ($info -and $info.NextRunTime) {
    $et = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
    Write-Host ("  NextRun ET: {0}" -f $et.ToString("yyyy-MM-dd HH:mm"))
} else {
    Write-Host "  NextRun ET: (none / on-demand)"
}
Write-Host ""
Write-Host "Verify with: Get-ScheduledTask -TaskName Gamma_PremarketReadiness | Get-ScheduledTaskInfo"
