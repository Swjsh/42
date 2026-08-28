#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_QuoteRecorderKeepalive -- keepalive for quote_recorder.py, the
  independent exit-quote NBBO side-channel (Task B1, built 2026-08-28: "we log NBBO
  on ~25 of 128 entry events and ZERO on exits; every slippage number in every
  analysis is therefore an ASSUMPTION").

.CONTEXT (2026-08-28 conductor fire)
  quote_recorder.py was built and verified the same day but never given an
  always-on scheduled task -- it was started manually once (~17:18 ET) and the
  moment that process exits, self_check.py's check_quote_recorder_alive flags
  QUOTE-RECORDER RED forever (a status file that exists but goes stale has no way
  to read as "never armed" again). This closes that gap with the same treatment as
  every other always-on daemon in this repo (Gamma_CryptoGrinderKeepalive /
  Gamma_WindowLeakDetectorKeepalive / retired Gamma_CcrKeepalive): a 5-min,
  24/7 pid-liveness probe + auto-relaunch.

  WIRING PATTERN (matches install-window-leak-detector-keepalive.ps1's 2026-08-08
  VBS-WRAPPER-EXIT-CODE-BLIND-SPOT migration):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> quote_recorder_keepalive.py
  quote_recorder_keepalive.py checks quote-recorder-status.json's own `pid` field
  against the live process table (wmic), relaunches quote_recorder.py --loop via
  system pythonw + CREATE_NO_WINDOW|DETACHED_PROCESS if dead. The recorder itself
  already self-gates to its 08:55-16:05 ET RTH window and idles (5-min cadence)
  outside it -- this keepalive runs 24/7 so a crash overnight is caught before the
  next trading day, not discovered cold at 08:55.

  NOT a live-money/secret/CLAUDE.md surface: quote_recorder.py is READ-ONLY (Alpaca
  REST GETs for options-chain NBBO), places no orders, mutates no trading-path
  state. Paper-infra engine-benefit authoring path (OP-22/OP-26); rail-4 discipline
  observed anyway (guard test + one-key revert + REVOKE report in STATUS.md).

  To verify after running: Get-ScheduledTask -TaskName Gamma_QuoteRecorderKeepalive
  Revert: .\install-quote-recorder-keepalive.ps1 -Uninstall
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root      = "C:\Users\jackw\Desktop\42"
$taskName  = "Gamma_QuoteRecorderKeepalive"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonw      = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\quote_recorder_keepalive.py"

if (-not (Test-Path $pythonw))      { throw "system pythonw.exe not found at $pythonw" }
if (-not (Test-Path $runCmdHidden)) { throw "run_cmd_hidden.py not found at $runCmdHidden" }
if (-not (Test-Path $script))       { throw "quote_recorder_keepalive.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- system pythonw -> quote_recorder_keepalive.py
$wscriptArgs = "//nologo `"$vbs`" `"$pythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonw`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# Every 5 min, 24/7 -- a crash outside RTH must be caught before the next session opens.
$startBoundary = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $startBoundary `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration ([System.TimeSpan]::FromDays(365 * 10))

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Keepalive for quote_recorder.py (Task B1's independent exit-quote NBBO side-channel). Checks quote-recorder-status.json's pid every 5 min 24/7 against the live process table, relaunches (detached, CREATE_NO_WINDOW, 24h bounded duration) if dead. READ-ONLY market-data recorder -- places no orders, touches no trading-path state. Built 2026-08-28 to close the gap where quote_recorder.py was verified but never given an always-on task, so self_check.py flagged QUOTE-RECORDER RED forever after its one manual launch exited." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
