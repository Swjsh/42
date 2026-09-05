#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_ParticipationDaily -- the GOAL-LAYER daily instrument (root-cause audit
  2026-07-15, markdown/audits/FIX-SHIP-REPEAT-ROOT-CAUSE-2026-07-15.md SS9).

  WHY: the audit's Miner-3 effort-allocation census found ~36 of ~81 scheduled tasks are
  monitoring instruments -- and ZERO measure GOAL ATTAINMENT (fills/day vs J's 2-4/day/account
  target). Every existing instrument watches aliveness or gate-correctness; none compute "did
  the engine actually participate enough today." The one tool that could answer this --
  backtest/tools/participation_cascade.py -- was built the day AFTER a real $0 day ("6 arms
  and nothing took a trade from over 700 signals? why didn't you see this yesterday?"), yet
  was never scheduled, had no installer, and was imported by nothing. Both of 2026-07-15's
  goal-level failures were caught by an angry human, not an instrument.

  Each fire runs setup/scripts/participation_daily.py, which:
    1. Calls participation_cascade.compute_cascade_day/write_state_file/write_report --
       REUSES that module's ledger-parsing + dedup + stage-classification verbatim (this fire
       is also the first time participation_cascade.py's OWN artifacts get produced on ANY
       schedule at all: automation/state/participation-cascade.json +
       analysis/participation-cascade/{date}.md).
    2. Derives PER-ACCOUNT (safe-2, bold-2 -- the 2 real CORE production accounts, not the 4
       fleet research arms) enter_verdicts / attempts / fills for the day.
    3. Compares fills to a per-account target (default 2-4/day; params-overridable per account
       via participation_target_fills_min/_max in that account's own params.json).
    4. Writes automation/state/participation-daily.json (GREEN/YELLOW/RED/IDLE per account +
       an overall worst-account-wins rollup) and appends a goal-layer section to that day's
       analysis/participation-cascade/{date}.md.
    5. On YELLOW/RED, appends ONE line to automation/state/discord-outbox.jsonl (schema mirrors
       self_check.py's {ts,channel,source,message} rows), de-duped per (date,verdict) so a
       manual re-run never double-alerts.
  Read-only on every ledger it touches, places no order, arms nothing, always exits 0.

  CADENCE: single daily weekday fire, 16:10 ET -- after Gamma_EodFlattenCore (15:52 ET) and
  Gamma_BrokerFills' 16:05 ET EOD fire so the day's fills are settled before this reads them;
  same slot as Gamma_ContextGuard/Gamma_FirmBrief (multiple 16:10 ET fires already coexist).

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 16:10 ET -> 14:10 MT. NEVER pass an ET
  literal to -At. Plain `-Weekly -DaysOfWeek Mon-Fri -At "14:10"` (the proven single-fire
  DailyTrigger pattern -- matches install-macro-calendar.ps1/install-ledger-archive.ps1), NOT
  a bare one-time trigger (goes dark after the install day --
  project_scheduled_task_onetime_trigger_dark) and NOT context-bundle's all-day Repetition
  block (this is one fire a day, not a 5-min intraday cadence).

  WIRING PATTERN (flash-free, matches install-context-bundle.ps1 / install-ledger-archive.ps1
  exactly):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> participation_daily.py
  Backtest venv (not system Python) for consistency with the module it wraps
  (participation_cascade.py lives under backtest/tools/) and because backtest\.venv pythonw is
  BOTH the reaper-exempt-by-path launcher AND already has et_clock importable cleanly (same
  choice as every other 2026-07-14/07-15 producer). The script carries its own OP-27 L41
  layer-3 headless stdio redirect (copied verbatim from context_bundle_producer.py /
  firm_brief.py), defense in depth even without this wscript relay.

  REAPER EXEMPTION -- verified pattern (setup/scripts/_shared.ps1's Stop-StaleClaudeProcesses
  reaps stale python.exe references to this repo every ~3-5 min): 'pythonw.exe' sits entirely
  outside Stop-StaleClaudeProcesses's Win32_Process Name filter (primary exemption), PLUS this
  task is launched via backtest\.venv\Scripts\pythonw.exe, whose CommandLine also contains the
  literal substring 'backtest\.venv' (an existing $EXEMPT_DAEMONS entry, defense in depth) --
  same verified shape as Gamma_ContextBundle/Gamma_LedgerArchive/Gamma_CryptoTwin.

  To verify after running: Get-ScheduledTask -TaskName Gamma_ParticipationDaily | Get-ScheduledTaskInfo
  REVERT: powershell setup\scripts\install-participation-daily.ps1 -Uninstall
          (the underlying data this task reads/writes is untouched by uninstall -- this only
          removes the scheduled fire; automation/state/participation-daily.json,
          participation-cascade.json, and the analysis/ reports stay on disk as of last fire.)
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath   = Join-Path $root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\participation_daily.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName     = "Gamma_ParticipationDaily"

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

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- backtest venv pythonw -> participation_daily.py
# (2026-08-08 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT migration -- was fire-and-forget.)
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 14:10 MT = 16:10 ET, single fire, weekdays only.
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "14:10"

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
    -Description ("GOAL-LAYER daily check (root-cause audit 2026-07-15 SS9: zero of ~36 " + `
    "monitoring instruments measured goal attainment). Fires 16:10 ET weekdays. " + `
    "participation_daily.py wraps backtest/tools/participation_cascade.py (reuses its " + `
    "ledger-parsing verbatim, never reimplements it): computes per-account (safe-2/bold-2) " + `
    "ENTER-verdicts/attempts/fills vs a 2-4/day target (params-overridable via " + `
    "participation_target_fills_min/_max), writes automation/state/participation-daily.json " + `
    "+ automation/state/participation-cascade.json (the underlying module's own artifact, " + `
    "now finally produced on a schedule) + appends a goal-layer section to " + `
    "analysis/participation-cascade/{date}.md, and pings Discord on YELLOW/RED (de-duped " + `
    "per date+verdict). Read-only on all ledgers, places no order, arms nothing, exits 0 " + `
    "always. Guard: backtest/tests/test_participation_daily.py.") `
    -Force | Out-Null

Write-Host "Registered $taskName (14:10 MT = 16:10 ET, weekdays)"
Show-NextET $taskName
Write-Host ""
Write-Host "Participation-daily goal-layer instrument wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_ParticipationDaily | Get-ScheduledTaskInfo"
