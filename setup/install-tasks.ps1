# Install-tasks.ps1 - RETIRED 2026-06-27 (G17). DO NOT USE. Registers NOTHING.
#
# Why this script was retired (it was a dormant two-fold time-bomb, not a working installer):
#
#   1. TZ TIME-BOMB (project_scheduled_task_tz). The rig runs in MOUNTAIN time and
#      Windows Task Scheduler's -At takes a LOCAL (MT) clock value, but every task below
#      passed the ET value straight to -At (LaunchTV 08:00, Premarket 08:30, Heartbeat
#      09:30, EodFlatten 15:55). ET = MT + 2h, so a re-run fired the whole core chain 2h
#      LATE: heartbeats at 11:30 ET and -- catastrophically -- EodFlatten at 17:55 ET,
#      i.e. AFTER the close, leaving 0DTE positions to expire worthless.
#
#   2. RETIRED ENGINE. It registered the LLM heartbeats (run-heartbeat.ps1 /
#      run-heartbeat-aggressive.ps1), which were RETIRED 2026-06-25 in favor of the
#      deterministic Gamma_HeartbeatCore (+ Gamma_SightBeacon / Gamma_FleetExecutor).
#      Re-running this would have re-armed dead tasks that conflict with the live engine.
#      It also used the bare "powershell.exe -WindowStyle Hidden" action that flashes a
#      console on Win11 (project_mcp_window_leak_fix); live tasks use the wscript->pythonw
#      chain instead.
#
# The live tasks are correct ONLY because other scripts re-registered them at the right MT
# literal. This 6-task view is a stale snapshot of an architecture that now has ~46 tasks.
#
# CANONICAL SOURCES OF TRUTH (use these instead):
#   - Registry / authority:  automation/state/SCHEDULED-TASKS.md  (every active task + its
#                            own per-task install script; audited daily by
#                            setup/scripts/audit_scheduled_tasks.py).
#   - Pre-market prep chain:  setup/install-swarm-task.ps1, setup/install-ema-snapshot.ps1,
#                            setup/scripts/register_tz_fixed_tasks.ps1 (all MT-literal correct).
#   - Trading-task health/repair:  setup/scripts/fix-trading-tasks.ps1 [-Fix]
#                            (enable + WakeToRun for the live trading chain).
#
# If you genuinely need to (re)register a core task, find its dedicated installer in
# SCHEDULED-TASKS.md and run THAT -- never this script.

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Red
Write-Host " install-tasks.ps1 is RETIRED (G17, 2026-06-27). NOTHING was registered." -ForegroundColor Red
Write-Host "========================================================================" -ForegroundColor Red
Write-Host ""
Write-Host " Reason: it passed ET times straight to -At on the Mountain-time rig (fires" -ForegroundColor Yellow
Write-Host "         2h late -> EodFlatten after the close) AND it registered the RETIRED" -ForegroundColor Yellow
Write-Host "         LLM heartbeats (superseded by Gamma_HeartbeatCore on 2026-06-25)." -ForegroundColor Yellow
Write-Host ""
Write-Host " Use instead:" -ForegroundColor Cyan
Write-Host "   - Registry / authority : automation/state/SCHEDULED-TASKS.md"
Write-Host "   - Prep chain           : setup/install-swarm-task.ps1,"
Write-Host "                            setup/install-ema-snapshot.ps1,"
Write-Host "                            setup/scripts/register_tz_fixed_tasks.ps1"
Write-Host "   - Trading-task repair  : setup/scripts/fix-trading-tasks.ps1 -Fix"
Write-Host ""
Write-Host " Each core task has its own per-task installer listed in SCHEDULED-TASKS.md." -ForegroundColor Cyan
Write-Host ""

exit 1
