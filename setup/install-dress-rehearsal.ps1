#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_DressRehearsal scheduled task -- fires 18:45 MT (= 20:45 ET) DAILY.

.DESCRIPTION
  Nightly REAL-broker-boundary dress rehearsal (setup/scripts/dress_rehearsal.py).
  J's pain: "every time I asked 'are we good for tomorrow' I got green-lit, then it
  fails the next morning." Unit guards mock the broker; the killers live AT the
  boundary (42210000 complex-order rejections, 'expires soon', 401 stale keys, wrong
  OCC symbols). Each fire, against the REAL Alpaca paper API ($0, idempotent,
  self-cleaning):
    1. Options order ACCEPTANCE via the engine's exact _place_simple_entry POST on
       BOTH accounts (safe-2 + bold-2): next-trading-day deep-OTM SPY put, 1-lot buy
       limit @ $0.01 (never fills), verify accepted, cancel, verify flat.
    2. Crypto round-trip on safe-2: $10 notional BTC/USD market buy -> fill -> sell ->
       broker-flat (real fills prove auth+POST+fill+position machinery tonight).
       Hard $10 cap (guard-tested).
    3. Clock/key/feed sanity: next_open = next trading day 09:30 ET, options approval
       level >= 2 both accounts, sight-beacon ran today.
  Writes automation/state/dress-rehearsal.json {ran_at_et, per-check verdicts +
  verbatim broker evidence, overall GREEN/INCONCLUSIVE/RED}. self_check.py reads it
  every 30 min and flags BROKEN when RED or >24h stale on a weekday evening.

  WHY 18:45 MT (= 20:45 ET): after the evening work block starts, well before J's
  "are we good for tomorrow". -At is LOCAL time (Task Scheduler convention); the rig
  is Mountain (project_scheduled_task_tz foot-gun -- do NOT relabel as an ET hour).
  DAILY (not weekday-only): the script computes the NEXT trading day itself, so a
  Sunday fire correctly rehearses Monday. Never a one-shot TimeTrigger (those go
  dark after install day).

  pythonw + the wscript -> run_exe_hidden.vbs chain is the canonical L41/L42/C8
  zero-leak hidden spawn (no console flash). backtest venv (reaper-exempt, has the
  engine deps heartbeat_core imports). Fail-open: a crash writes a RED artifact and
  exits 0 -- never a silent death, never a scheduler error.

  Paper accounts ONLY; keys load at runtime from gitignored fleet secrets (same path
  as the live engine). Places only self-cancelling probe orders + a capped $10 paper
  crypto round-trip. Never touches params*.json / heartbeat.md / CLAUDE.md.

  To enable:  .\setup\install-dress-rehearsal.ps1
  To verify:  Get-ScheduledTask Gamma_DressRehearsal | Get-ScheduledTaskInfo
  To test:    Start-ScheduledTask -TaskName Gamma_DressRehearsal
  To disable: .\setup\install-dress-rehearsal.ps1 -Uninstall
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$TaskName = "Gamma_DressRehearsal"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Unregistered $TaskName."
    }
    return
}

$WorkDir = "C:\Users\jackw\Desktop\42"
$pythonw      = Join-Path $WorkDir "backtest\.venv\Scripts\pythonw.exe"
$runExeHidden = Join-Path $WorkDir "setup\scripts\run_exe_hidden.vbs"
$worker       = Join-Path $WorkDir "setup\scripts\dress_rehearsal.py"
# 2026-08-07: relay through run_cmd_hidden.py for real exit-code visibility -- see
# VBS-WRAPPER-EXIT-CODE-BLIND-SPOT / Gamma_CryptoTwin drift finding, queue.md.
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $WorkDir "setup\scripts\run_cmd_hidden.py"

foreach ($p in @($pythonw, $runExeHidden, $worker, $sysPythonw, $runCmdHidden)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$WorkDir`" -- `"$pythonw`" `"$worker`""

# 18:45 LOCAL (Mountain) = 20:45 ET. DAILY -- the worker computes the next trading day.
$trigger = New-ScheduledTaskTrigger -Daily -At "18:45"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Nightly 20:45 ET (18:45 MT) REAL-broker dress rehearsal: proves tomorrow's order path against the live Alpaca paper API (engine _place_simple_entry probe order accepted+canceled on both accounts, `$10-capped BTC round-trip real fill, clock/keys/approval/beacon sanity). Writes automation/state/dress-rehearsal.json; self_check flags RED/stale. `$0, paper-only, self-cleaning, fail-open." | Out-Null

$info = Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo
Write-Output "OK: Registered $TaskName daily 20:45 ET (18:45 MT). NextRunTime: $($info.NextRunTime)"
Write-Output "    Worker:   setup\scripts\dress_rehearsal.py  (backtest venv pythonw, hidden)"
Write-Output "    Artifact: automation\state\dress-rehearsal.json"
