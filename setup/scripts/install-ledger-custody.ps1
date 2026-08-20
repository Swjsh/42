#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_LedgerCustody -- the DURABLE, OFF-VOLUME, CHECKSUMMED archive of the
  irreplaceable trading book, plus a daily self-proving restore drill.

  WHY (2026-08-19 data-custody emergency): automation/state/fills-ledger.jsonl is the ONLY
  surviving copy of 22 of our 35 trading days. Alpaca's paper API has deleted its own
  history -- verified live: a FILL query for 2026-06-25..2026-08-03 returns ZERO rows while
  the identical query from 2026-08-03 returns rows immediately. 137 of 303 round trips and
  -$1,664 of the -$1,805 gross rest on that one file.

  It was found with THREE protections missing at once:
    1. untracked by git,
    2. NOT in .gitignore either -- so `git clean -fd automation/state/` DELETES it
       (verified: `git clean -nd` prints "Would remove automation/state/fills-ledger.jsonl"),
    3. absent from Gamma_LedgerArchive's SOURCES -- the existing daily archive never copied
       it, and prunes at 30 days regardless.

  THIS TASK IS NOT A DUPLICATE OF Gamma_LedgerArchive. That one is a 30-day rolling, same-
  volume, unchecksummed convenience copy and stays as-is. This one is the CUSTODY tier:
    * OFF-VOLUME  -- D:\GammaArchive, a different physical disk from the repo on C:. An
                     archive beside the thing it protects dies to the same `git clean -xfd`,
                     the same rm, the same disk failure.
    * CHECKSUMMED -- content-addressed blobs at blobs/<aa>/<sha256>.gz. The filename IS the
                     hash of the content, so silent bit-rot is detectable, not discovered
                     years later.
    * PERMANENT   -- snapshots are NEVER pruned. Dedupe makes this affordable: measured
                     2026-08-20, 89.5 MB of sources compress to 3.6 MB on disk (25x), and a
                     re-run writes 0 new blobs.
    * SELF-PROVING -- each fire runs the RESTORE DRILL: it rebuilds the canonical 303-row
                     trade matrix from the archive alone and asserts gross reproduces
                     exactly. An archive nobody has read back is not a backup.

  Read-only on every live file (safe mid-session). Places no orders, touches no params,
  no heartbeat, no CLAUDE.md. Pure stdlib, no network, $0.

  CADENCE: -Daily -At "14:40"  (16:40 ET). AFTER Gamma_BrokerFills' 16:05 ET EOD fire, which
  is what finishes writing fills-ledger.jsonl for the day, and after Gamma_LedgerArchive
  (16:12 ET) so the two never contend. Uses the proven DailyTrigger pattern, NOT the bare
  one-time/interval trigger that goes dark after install day
  (project_scheduled_task_onetime_trigger_dark).

  TZ RULE: this rig is Mountain (ET = local + 2h). 16:40 ET -> 14:40 MT. NEVER pass an ET
  literal to -At.

  REAPER EXEMPTION (setup/scripts/_shared.ps1#Stop-StaleClaudeProcesses reaps stale
  python.exe referencing this repo every ~3-5 min): 'pythonw.exe' is outside that function's
  Win32_Process Name filter entirely (primary exemption), PLUS the launch path contains the
  literal 'backtest\.venv', an existing $EXEMPT_DAEMONS entry (defense in depth). Same shape
  as install-ledger-archive.ps1 / install-free-model-audit.ps1.

  WIRING (flash-free, matches the existing installers exactly):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
            -- backtest\.venv\Scripts\pythonw.exe -> archive_ledgers.py --restore-drill --deep

  VISIBILITY: the run writes D:\GammaArchive\integrity-report.json AND mirrors a one-screen
  summary to automation/state/archive-custody-status.json inside the repo, so health is
  visible without anyone reaching for the backup volume.

  Verify:  Get-ScheduledTask -TaskName Gamma_LedgerCustody | Get-ScheduledTaskInfo
  Status:  backtest\.venv\Scripts\python.exe setup\scripts\archive_ledgers.py --status
  REVERT:  powershell setup\scripts\install-ledger-custody.ps1 -Uninstall
  Guard:   backtest/tests/test_archive_ledgers.py
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root     = "C:\Users\jackw\Desktop\42"
$taskName = "Gamma_LedgerCustody"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv  = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\archive_ledgers.py"

if (-not (Test-Path $vbs))          { throw "run_exe_hidden.vbs not found at $vbs" }
if (-not (Test-Path $pythonwVenv))  { throw "backtest venv pythonw.exe not found at $pythonwVenv" }
if (-not (Test-Path $sysPythonw))   { throw "system pythonw.exe not found at $sysPythonw" }
if (-not (Test-Path $runCmdHidden)) { throw "run_cmd_hidden.py not found at $runCmdHidden" }
if (-not (Test-Path $script))       { throw "archive_ledgers.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonwVenv`" `"$script`" --restore-drill --deep"
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# 16:40 ET -> 14:40 MT. Daily (not weekday-gated): a custody task must never skip a day the
# ledgers DID change (weekend backfills, kitchen writes), and a no-change day costs 0 bytes.
$trigger = New-ScheduledTaskTrigger -Daily -At "14:40"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "DURABLE OFF-VOLUME CUSTODY of the irreplaceable trading book (2026-08-19 emergency: fills-ledger.jsonl is the ONLY copy of 22 of 35 trading days -- Alpaca deleted its history, and the file was untracked AND unignored so ``git clean -fd`` would delete it). archive_ledgers.py snapshots fills-ledger + core/fleet decisions + trades.csv + key-levels + exit-state + OPRA bars into D:\GammaArchive as content-addressed sha256 blobs (blobs/<aa>/<sha256>.gz), verifies by READING EVERY BLOB BACK, then runs a RESTORE DRILL that rebuilds the 303-row trade matrix from the archive alone and asserts gross reproduces exactly. Retention PERMANENT (dedupe: 89.5MB -> 3.6MB, re-run writes 0 new blobs). Read-only on live files, no orders, no network, ``$0. Daily 16:40 ET (14:40 MT), after Gamma_BrokerFills' 16:05 EOD fire. Reaper-exempt: pythonw.exe outside Stop-StaleClaudeProcesses's Name filter + backtest\.venv path match. Guard: backtest/tests/test_archive_ledgers.py. Built 2026-08-19." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
