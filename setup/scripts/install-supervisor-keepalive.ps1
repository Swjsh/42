#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_SupervisorKeepalive -- ONE keepalive process that checks liveness for
  + relaunches all 9 of the small always-on daemons that used to have their OWN separate
  5-min keepalive task (GOAL-SILENT-RIG-2026-09-05 R7).

.CONTEXT
  J: "this is a recurring thing it has to stop. everything must be silent, and it needs to
  be optimized, i can't have my pc bogged down." Off-hours launch rate was still ~150
  spawns/hour because 9 registered keepalive tasks (Gamma_CompanionKeepalive,
  Gamma_DashboardKeepalive, Gamma_KitchenDaemonKeepalive, Gamma_DiscordBridge,
  Gamma_QuoteRecorderKeepalive, Gamma_CryptoTwinKeepalive, Gamma_WindowLeakDetectorKeepalive,
  Gamma_WindowLeakHookKeepalive, Gamma_ProcTraceKeepalive) each independently fire every 5
  minutes, each spawning its own wscript->pythonw->run_cmd_hidden->pythonw (or, for the
  four PowerShell-authored ones, wscript->run_exe_hidden.vbs->powershell.exe) chain -- 9
  process trees every 5 minutes regardless of whether anything is actually dead.

  setup/scripts/supervisor_keepalive.py does all 9 liveness checks (ONE shared `wmic`
  process-table read, reused by every check) + relaunches the dead ones in ONE process --
  1 spawn per 5-min fire instead of 9. Each daemon's OWN keepalive script stays on disk,
  unregistered but importable, so its own existing guard tests keep proving its predicate
  correct and supervisor_keepalive.py imports (never reimplements) that predicate.

  crypto_grinder_keepalive.py is DELIBERATELY EXCLUDED -- grinders stay presence-gated on
  their own task, per this goal's spec.

  WIRING PATTERN (matches install-crypto-twin-keepalive.ps1's proven shape, itself matching
  install-quote-recorder-keepalive.ps1 / install-window-leak-detector-keepalive.ps1's
  2026-08-08 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT migration):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --env
      PYTHONPATH=<repo>\backtest\.venv\Lib\site-packages --cwd <repo>
      -- system pythonw -> supervisor_keepalive.py
  No PowerShell anywhere in the fire chain (OP-27 L41).

  DISABLED AT REGISTRATION (GOAL-SILENT-RIG-2026-09-05 operating rule -- workers never
  enable a scheduled task): this script registers the task then immediately calls
  Disable-ScheduledTask in the SAME run. Fable flips it on AND disables the 9 old keepalive
  tasks (they must never run alongside this one -- that would double-relaunch every daemon)
  after reviewing this goal's R7 item. The exact flip commands are documented in this
  goal's PROGRESS LOG for the R7 entry.

  NOT a live-money/secret/CLAUDE.md-doctrine surface: every daemon this supervises is the
  SAME paper-infra process each old keepalive already supervised (companion UI, dashboard,
  kitchen R&D daemon, Discord presence bridge, quote recorder, crypto gym twin, the two
  window-leak popup mitigations, the process-creation tracer) -- this changes HOW they are
  kept alive, never what they do. Paper-infra / engine-benefit authoring path (OP-22/OP-26).

  To verify after running: Get-ScheduledTask -TaskName Gamma_SupervisorKeepalive
    (State should read Disabled until Fable enables it)
  Revert (undo this install entirely): .\install-supervisor-keepalive.ps1 -Uninstall
  Flip live (Fable only, after reviewing R7 -- disable the 9 old keepalives FIRST):
    Disable-ScheduledTask -TaskName Gamma_CompanionKeepalive
    Disable-ScheduledTask -TaskName Gamma_DashboardKeepalive
    Disable-ScheduledTask -TaskName Gamma_KitchenDaemonKeepalive
    Disable-ScheduledTask -TaskName Gamma_DiscordBridge
    Disable-ScheduledTask -TaskName Gamma_QuoteRecorderKeepalive
    Disable-ScheduledTask -TaskName Gamma_CryptoTwinKeepalive
    Disable-ScheduledTask -TaskName Gamma_WindowLeakDetectorKeepalive
    Disable-ScheduledTask -TaskName Gamma_WindowLeakHookKeepalive
    Disable-ScheduledTask -TaskName Gamma_ProcTraceKeepalive
    Enable-ScheduledTask  -TaskName Gamma_SupervisorKeepalive
  Revert THAT flip: Enable-ScheduledTask each of the 9 above, Disable-ScheduledTask this one.
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root      = "C:\Users\jackw\Desktop\42"
$taskName  = "Gamma_SupervisorKeepalive"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonw      = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"  # SYS pythonw only, never the venv stub (GOAL-SILENT-RIG S1/S2)
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\supervisor_keepalive.py"
$pythonPathEnv = "PYTHONPATH=$root\backtest\.venv\Lib\site-packages"

if (-not (Test-Path $pythonw))      { throw "system pythonw.exe not found at $pythonw" }
if (-not (Test-Path $vbs))          { throw "run_exe_hidden.vbs not found at $vbs" }
if (-not (Test-Path $runCmdHidden)) { throw "run_cmd_hidden.py not found at $runCmdHidden" }
if (-not (Test-Path $script))       { throw "supervisor_keepalive.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --env PYTHONPATH=...
#   --cwd <repo> -- system pythonw -> supervisor_keepalive.py
$wscriptArgs = "//nologo `"$vbs`" `"$pythonw`" `"$runCmdHidden`" --env `"$pythonPathEnv`" --cwd `"$root`" -- `"$pythonw`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# Every 5 min, 24/7 -- same cadence as the 9 tasks it replaces.
$startBoundary = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $startBoundary `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration ([System.TimeSpan]::FromDays(365 * 10))

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
    -MultipleInstances IgnoreNew `
    -Priority 7

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "ONE keepalive for all 9 small always-on daemons (GOAL-SILENT-RIG-2026-09-05 R7): companion, dashboard, kitchen_daemon, discord bridge+watcher, quote_recorder, crypto_twin, window-leak detector+hook, proc_trace. One shared wmic process-table read per fire, relaunches only the dead ones. Replaces Gamma_CompanionKeepalive/DashboardKeepalive/KitchenDaemonKeepalive/DiscordBridge/QuoteRecorderKeepalive/CryptoTwinKeepalive/WindowLeakDetectorKeepalive/WindowLeakHookKeepalive/ProcTraceKeepalive -- 1 spawn/5min instead of 9. Registered DISABLED; Fable disables the 9 old tasks and enables this one to flip live." `
    -Force | Out-Null

# DISABLE IMMEDIATELY -- workers never enable a scheduled task (GOAL-SILENT-RIG-2026-09-05
# operating rules). Fable reviews R7 and flips all ten tasks (disable the 9 old ones, enable
# this one) in one pass so they are never both live at once.
Disable-ScheduledTask -TaskName $taskName | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
$state = (Get-ScheduledTask -TaskName $taskName).State
Write-Host "Registered $taskName. State=$state. Next run (while disabled, informational only): $($info.NextRunTime)"
