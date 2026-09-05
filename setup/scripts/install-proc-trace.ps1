#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_ProcTraceKeepalive -- keepalive for proc_trace.py, the event-driven
  process-creation tracer (GOAL-SILENT-RIG-2026-09-05 R4a).

.CONTEXT
  window_leak_hook.py's own leak attribution (S3, 2026-09-05) can only name processes still
  ALIVE in a toolhelp snapshot taken right after a hide -- a short-lived process whose parent
  already exited by the time the hide fires shows up as "(parent=?)" in the log, exactly what
  the live 14:00:0x incident showed (4 pythonw.exe processes, no parent nameable). proc_trace.py
  subscribes to WMI's own process-creation eventing (Register-CimIndicationEvent, event-driven,
  never a polling loop) via a hidden child powershell.exe and records EVERY process creation
  with its parent looked up immediately, to automation/state/logs/proc-trace-<date>.jsonl.
  window_leak_hook.py's attribution then cross-references this file (last 2s of trace) for the
  full parent chain of anything created around a hide.

  WIRING PATTERN (matches install-crypto-twin-keepalive.ps1's proven shape):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --env
      PYTHONPATH=<repo>\backtest\.venv\Lib\site-packages --cwd <repo>
      -- system pythonw -> proc_trace_keepalive.py
  No PowerShell anywhere in THIS fire chain (OP-27 L41) -- proc_trace_keepalive.py itself
  only ever shells to wmic (read-only process-table query), and proc_trace.py (which the
  keepalive launches) is the one process in this chain that spawns a hidden powershell.exe
  child for the actual CIM subscription (documented in proc_trace.py's own module docstring;
  that hop is inherent to the event-driven design the spec calls for, not a leak).

  proc_trace_keepalive.py checks the live process table (wmic, CREATE_NO_WINDOW) for a
  `proc_trace.py` command line, relaunches (system pythonw, DETACHED_PROCESS|CREATE_NO_WINDOW)
  if none is found.

  DISABLED AT REGISTRATION (GOAL-SILENT-RIG-2026-09-05 operating rule -- workers never enable
  a scheduled task): this script registers the task then immediately calls
  Disable-ScheduledTask in the SAME run. Fable enables after reviewing this goal's R4a item.

  Not a live-money/secret/CLAUDE.md-doctrine surface: proc_trace.py is a read-only diagnostic
  (it inspects process creation events, places no orders, touches no FROZEN_TRADING_PATH
  file). Paper-infra / engine-benefit authoring path (OP-22/OP-26).

  To verify after running: Get-ScheduledTask -TaskName Gamma_ProcTraceKeepalive
    (State should read Disabled until Fable enables it)
  Revert (undo this install entirely): .\install-proc-trace.ps1 -Uninstall
  Flip live (Fable only, after reviewing R4a):
    Enable-ScheduledTask -TaskName Gamma_ProcTraceKeepalive
  Revert THAT flip:
    Disable-ScheduledTask -TaskName Gamma_ProcTraceKeepalive
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root      = "C:\Users\jackw\Desktop\42"
$taskName  = "Gamma_ProcTraceKeepalive"

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
$script       = Join-Path $root "setup\scripts\proc_trace_keepalive.py"
$pythonPathEnv = "PYTHONPATH=$root\backtest\.venv\Lib\site-packages"

if (-not (Test-Path $pythonw))      { throw "system pythonw.exe not found at $pythonw" }
if (-not (Test-Path $vbs))          { throw "run_exe_hidden.vbs not found at $vbs" }
if (-not (Test-Path $runCmdHidden)) { throw "run_cmd_hidden.py not found at $runCmdHidden" }
if (-not (Test-Path $script))       { throw "proc_trace_keepalive.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --env PYTHONPATH=...
#   --cwd <repo> -- system pythonw -> proc_trace_keepalive.py
$wscriptArgs = "//nologo `"$vbs`" `"$pythonw`" `"$runCmdHidden`" --env `"$pythonPathEnv`" --cwd `"$root`" -- `"$pythonw`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# Every 5 min, 24/7 -- same cadence as every other Gamma_*Keepalive in this repo.
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
    -Description "Keepalive for proc_trace.py, the event-driven process-creation tracer (GOAL-SILENT-RIG-2026-09-05 R4a). Checks the live process table every 5 min 24/7 for a proc_trace.py process, relaunches (detached, CREATE_NO_WINDOW, system pythonw + PYTHONPATH) if none found. proc_trace.py records every process creation (WMI Register-CimIndicationEvent, event-driven, not polling) with immediate parent lookup to automation/state/logs/proc-trace-<date>.jsonl for window_leak_hook.py's attribution. Registered DISABLED; Fable enables after review." `
    -Force | Out-Null

# DISABLE IMMEDIATELY -- workers never enable a scheduled task (GOAL-SILENT-RIG-2026-09-05
# operating rules). Fable reviews R4a and enables.
Disable-ScheduledTask -TaskName $taskName | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
$state = (Get-ScheduledTask -TaskName $taskName).State
Write-Host "Registered $taskName. State=$state. Next run (while disabled, informational only): $($info.NextRunTime)"
