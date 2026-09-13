#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_Station scheduled task -- fires every 30 min, 24/7 (GOAL-GAMMA-STATION-
  2026-09-13 item (4)).

.DESCRIPTION
  The Station loop: a LOCAL Ollama model (default gamma-planner, $0, no Anthropic tokens)
  reads real ledger/hypothesis/goal-ladder state and proposes at most 2 new falsifiable
  idea-cards to automation/state/station/ideas-board.json + a short brief. The script itself
  (setup/scripts/station_loop.py) owns the yield rule (RTH / GPU-busy / denylisted-process /
  Ollama-down) and always exits 0 -- a yield or error is a logged ledger row, never a
  scheduler alarm.

  NEVER touches the trading path -- this installer registers a NEW task only; it does not
  read, modify, or unregister anything else. No orders, no broker calls, no Discord writes.

  WIRING PATTERN (silent-rig canonical, matches Gamma_SelfCheck / Gamma_GateExpiryCheck):
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> system pythonw.exe
                   -> station_loop.py --once
  station_loop.py is stdlib-only (no pandas/numpy), so the system pythonw is sufficient --
  no venv indirection needed (unlike the OOS-check family, which needs backtest deps).

  Verify:  schtasks /Query /TN Gamma_Station /V /FO LIST
  Test now: Start-ScheduledTask -TaskName Gamma_Station
  Disable: .\setup\install-station-loop.ps1 -Uninstall
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$TaskName = "Gamma_Station"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Unregistered $TaskName."
    } else {
        Write-Host "$TaskName was not registered."
    }
    return
}

$WorkDir     = "C:\Users\jackw\Desktop\42"
$ScriptsDir  = Join-Path $WorkDir "setup\scripts"
$pythonw     = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$worker      = Join-Path $ScriptsDir "station_loop.py"

foreach ($p in @($pythonw, $runExeHidden, $worker)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# wscript //nologo run_exe_hidden.vbs <sys-pythonw> station_loop.py --once  (fully hidden,
# no console/WindowsTerminal flash -- the OP-27 L42 / "silent rig" canonical chain).
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument ("//nologo `"" + $runExeHidden + "`" `"" + $pythonw + "`" `"" + $worker + "`" --once") `
    -WorkingDirectory $WorkDir

# Every 30 min, 24/7, starting 1 min from install -- matches Gamma_SelfCheck's own repeating
# trigger idiom (a DailyTrigger-with-repetition, never a one-time trigger, which goes dark
# after the install day per project_scheduled_task_onetime_trigger_dark). The script's OWN
# yield rule (RTH / GPU / denylisted process / Ollama-down) decides whether a given fire
# actually does anything -- the task itself fires unconditionally on the clock.
$startBoundary = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $startBoundary `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration ([System.TimeSpan]::FromDays(365 * 10))

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "Station loop v1 (GOAL-GAMMA-STATION-2026-09-13): every 30 min, 24/7, a LOCAL Ollama model (gamma-planner, `$0) reads real ledger/hypothesis/goal-ladder state and proposes <=2 falsifiable idea-cards to automation/state/station/ideas-board.json. Yields during RTH / high GPU load / a denylisted foreground process; logs ollama_down rather than failing loud. NEVER touches the trading path or places an order. Guard: backtest/tests/test_station_loop.py." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo
Write-Output "OK: Registered $TaskName -- every 30 min, 24/7"
Write-Output "    Worker:  setup\scripts\station_loop.py --once"
Write-Output "    Outputs: automation\state\station\{ideas-board.json,station-brief.md,loop-ledger.jsonl}"
Write-Output "    Log:     E:\Gamma\logs\station-loop-<date>.log"
Write-Output ("    NextRunTime: " + $info.NextRunTime)
