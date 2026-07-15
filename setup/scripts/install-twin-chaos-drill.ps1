#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_TwinChaos -- the CRYPTO TWIN's weekly CHAOS DRILL (TWIN-B4,
  markdown/planning/TWIN-PROGRAM.md value stream #4: "Chaos drills (weekly). Injected
  failures we'd never dare on SPY: process kill mid-position, corrupt state file,
  stale feed, breaker mid-trip. Resilience ledger.").

  Fires ONCE weekly, Sunday 03:00 ET (deliberately off-hours, outside 09:30-15:55 ET
  market hours AND outside J's interactive-session window -- CLAUDE.md's standing
  discipline reminder). Runs `setup/scripts/twin_chaos_drill.py --all`, which forces
  all FOUR failure injections against the REAL crypto twin (Alpaca crypto PAPER,
  dedicated twin-only account -- see crypto_twin_broker.get_twin_creds()) one at a
  time, each restoring clean state before the next starts, and appends one row per
  drill to automation/state/crypto-twin/resilience-ledger.jsonl.

  SCOPE: twin-only, by construction. twin_chaos_drill.py imports ONLY
  crypto_twin_core/crypto_twin_broker/crypto_twin_health (all namespace-isolated to
  automation/state/crypto-twin/ -- see crypto_twin_core.py's own
  _assert_twin_namespace static+runtime guard) -- it NEVER touches SPY/fleet/core
  state, params, or orders. This task places NOTHING on the SPY/fleet accounts.

  WIRING PATTERN (flash-free, matches install-crypto-twin.ps1's own hidden chain):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> twin_chaos_drill.py --all
  backtest-venv pythonw is used for the SAME two reasons install-crypto-twin.ps1
  documents: (1) reaper-exempt by construction (pythonw.exe is outside
  Stop-StaleClaudeProcesses's Win32_Process -Filter Name clause, PLUS the
  'backtest\.venv' path substring is itself one of $EXEMPT_DAEMONS's entries --
  defense in depth); (2) it is the interpreter with this repo's twin/exit_manager/
  risk_gate import environment already set up.

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 03:00 ET -> 01:00 MT.
  NEVER pass an ET literal to -At. Weekly Sunday trigger (NOT a one-time/bare interval
  trigger, which goes dark after the install day --
  project_scheduled_task_onetime_trigger_dark / L103,153's DailyTrigger-pattern
  lesson, applied here to a Weekly cadence).

  A single drill cycle (all 4 injections) completes in seconds to low minutes --
  ExecutionTimeLimit gives a generous 15-minute ceiling (drill 1's real order
  fill-poll + managing-subprocess kill/recovery pair is the slowest leg).

  To verify after running: Get-ScheduledTask -TaskName Gamma_TwinChaos
  To check the last real drill cycle: tail
  automation\state\crypto-twin\resilience-ledger.jsonl
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root      = "C:\Users\jackw\Desktop\42"
$taskName  = "Gamma_TwinChaos"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs         = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script      = Join-Path $root "setup\scripts\twin_chaos_drill.py"

if (-not (Test-Path $pythonwVenv)) { throw "backtest venv pythonw.exe not found at $pythonwVenv" }
if (-not (Test-Path $script))      { throw "twin_chaos_drill.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> backtest-venv pythonw -> twin_chaos_drill.py --all
# (flash-free chain; mirrors install-crypto-twin.ps1 verbatim).
$wscriptArgs = "//nologo `"$vbs`" `"$pythonwVenv`" `"$script`" `"--all`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# Weekly, Sunday 03:00 ET = 01:00 MT (this rig is MT; ET = local + 2h -- NEVER an ET
# literal here). Weekly+DaysOfWeek is the proven DailyTrigger-pattern-safe recurrence
# (matches install-open-bell-status.ps1/install-macro-calendar.ps1's own Weekly
# triggers) -- NOT a bare one-time/interval trigger, which goes dark after today.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "01:00"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "CRYPTO TWIN weekly CHAOS DRILL (TWIN-B4, markdown/planning/TWIN-PROGRAM.md stream 4). Sunday 03:00 ET: twin_chaos_drill.py --all forces FOUR real failure injections against the twin (Alpaca crypto PAPER, dedicated twin-only account) -- process-kill mid-position, corrupt state file, stale feed, breaker mid-trip -- each observes the REAL recovery mechanism then restores clean state, appending one row per drill to automation/state/crypto-twin/resilience-ledger.jsonl. Twin-only by construction (namespace-isolated, never touches SPY/fleet/core). Reaper-exempt: pythonw.exe is outside Stop-StaleClaudeProcesses's Name filter, plus backtest\.venv path match as defense in depth (same guard class as test_crypto_twin_reaper_exemption.py). Built 2026-07-15." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
