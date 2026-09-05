#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_CryptoTwinKeepalive -- keepalive for crypto_twin_health.py's new RESIDENT
  --loop mode, replacing Gamma_CryptoTwin's old "spawn a fresh Python process every minute,
  24/7" shape (GOAL-SILENT-RIG-2026-09-05 R2).

.CONTEXT
  J: "this is a recurring thing it has to stop. everything must be silent, and it needs to be
  optimized, i can't have my pc bogged down." Gamma_CryptoTwin was firing
  crypto_twin_health.py --live as a brand-new Python process every single minute, 24/7 --
  1,440 process launches/day, the largest remaining off-hours load on J's box. This does NOT
  change the twin's strategy, cadence, or any FROZEN_TRADING_PATH file -- it is a PROCESS
  SHAPE change only: crypto_twin_health.py gained `--loop` (one resident process, same
  run_tick_with_health() tick function, same 1-min cadence, same outputs -- decisions.jsonl /
  twin-health.json / soak-log.jsonl -- unchanged) so ONE long-lived process now does what
  1,440 short-lived ones used to do.

  WIRING PATTERN (matches install-quote-recorder-keepalive.ps1's proven shape, itself matching
  install-window-leak-detector-keepalive.ps1's 2026-08-08 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT
  migration):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --env
      PYTHONPATH=<repo>\backtest\.venv\Lib\site-packages --cwd <repo>
      -- system pythonw -> crypto_twin_keepalive.py
  No PowerShell anywhere in the fire chain (OP-27 L41).

  crypto_twin_keepalive.py checks the live process table (wmic, CREATE_NO_WINDOW) for a
  `crypto_twin_health.py --loop` command line, relaunches (system pythonw + PYTHONPATH,
  DETACHED_PROCESS|CREATE_NO_WINDOW, 24h bounded --duration-sec) if none is found.

  DISABLED AT REGISTRATION (GOAL-SILENT-RIG-2026-09-05 operating rule -- workers never enable
  a scheduled task): this script registers the task then immediately calls
  Disable-ScheduledTask in the SAME run. Fable flips it on after reviewing this goal's R2
  item and disabling the old Gamma_CryptoTwin 1-min task (the two must not both be enabled at
  once -- that would double-run the twin).

  NOT a live-money/secret/CLAUDE.md-doctrine surface: crypto_twin_health.py is the SAME
  gym-only paper twin (crypto is gym-only per CLAUDE.md "What I will refuse") that has run
  under Gamma_CryptoTwin since 2026-08-07; this changes HOW it launches, never its strategy.
  Paper-infra / engine-benefit authoring path (OP-22/OP-26).

  To verify after running: Get-ScheduledTask -TaskName Gamma_CryptoTwinKeepalive
    (State should read Disabled until Fable enables it)
  Revert (undo this install entirely): .\install-crypto-twin-keepalive.ps1 -Uninstall
  Flip live (Fable only, after reviewing R2):
    Disable-ScheduledTask -TaskName Gamma_CryptoTwin
    Enable-ScheduledTask  -TaskName Gamma_CryptoTwinKeepalive
  Revert THAT flip:
    Disable-ScheduledTask -TaskName Gamma_CryptoTwinKeepalive
    Enable-ScheduledTask  -TaskName Gamma_CryptoTwin
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root      = "C:\Users\jackw\Desktop\42"
$taskName  = "Gamma_CryptoTwinKeepalive"

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
$script       = Join-Path $root "setup\scripts\crypto_twin_keepalive.py"
$pythonPathEnv = "PYTHONPATH=$root\backtest\.venv\Lib\site-packages"

if (-not (Test-Path $pythonw))      { throw "system pythonw.exe not found at $pythonw" }
if (-not (Test-Path $vbs))          { throw "run_exe_hidden.vbs not found at $vbs" }
if (-not (Test-Path $runCmdHidden)) { throw "run_cmd_hidden.py not found at $runCmdHidden" }
if (-not (Test-Path $script))       { throw "crypto_twin_keepalive.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --env PYTHONPATH=...
#   --cwd <repo> -- system pythonw -> crypto_twin_keepalive.py
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
    -Description "Keepalive for crypto_twin_health.py's resident --loop mode (GOAL-SILENT-RIG-2026-09-05 R2). Checks the live process table every 5 min 24/7 for a crypto_twin_health.py --loop process, relaunches (detached, CREATE_NO_WINDOW, 24h bounded duration, system pythonw + PYTHONPATH) if none found. Replaces Gamma_CryptoTwin's old 1,440-spawns/day per-minute task with ONE resident process -- process SHAPE change only, same twin strategy/cadence/outputs. Registered DISABLED; Fable enables after disabling Gamma_CryptoTwin." `
    -Force | Out-Null

# DISABLE IMMEDIATELY -- workers never enable a scheduled task (GOAL-SILENT-RIG-2026-09-05
# operating rules). Fable reviews R2 and flips both tasks (disable old, enable this).
Disable-ScheduledTask -TaskName $taskName | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
$state = (Get-ScheduledTask -TaskName $taskName).State
Write-Host "Registered $taskName. State=$state. Next run (while disabled, informational only): $($info.NextRunTime)"
