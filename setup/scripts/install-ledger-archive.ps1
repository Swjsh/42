#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_LedgerArchive -- the belt-and-suspenders DAILY LOCAL archive of
  decision ledgers + trade logs (2026-07-14: a `git stash drop` in the shared
  checkout destroyed ~3 weeks of uncommitted decision-ledger history, recovered
  by luck, not process). The ledgers are being gitignored+untracked by the
  orchestrating session tonight, which means git no longer protects them at all
  -- this task is the independent local safety net.

  Each fire runs setup/scripts/ledger_archive.py, which:
    1. Copies (via shutil.copy2, always-overwrite -- idempotent) each of:
         automation/state/core-decisions.jsonl
         automation/state/fleet/{risky-1,risky-3,safe-3}/decisions.jsonl
         journal/trades.csv
         journal/trades-aggressive.csv
       into automation/archive/ledgers/<ET-date>/<flattened-name> -- missing
       sources are SKIPPED with a logged note, never a crash.
    2. Prunes archive dirs older than 30 days (judged by DIRECTORY NAME date).
    3. Always exits 0; prints one summary line per file (COPY/SKIP/ERROR) +
       a prune-count line -- OP-25/C7 (silent success is failure).

  ET comes from et_clock.py (this repo's canonical clock) -- NEVER local time.

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 16:12 ET -> 14:12 MT.
  NEVER pass an ET literal to -At.

  CADENCE: `-Daily -At "14:12"` -- the proven DailyTrigger pattern (matches
  install-free-model-audit.ps1 / register-eod-deep-dive.ps1), NOT the bare
  one-time/interval-trigger foot-gun (a trigger with no recurrence spec goes
  dark after the install day -- project_scheduled_task_onetime_trigger_dark).
  Fires every day (not weekday-gated): the archive job is harmless to run on
  weekends (nothing changed -> copy2 re-writes identical bytes, prune is a
  no-op) and this is deliberately a belt-and-suspenders SAFETY task, not a
  trading task, so it should not silently skip a day the ledgers DID change
  (e.g. a Saturday kitchen/backfill write).

  REAPER EXEMPTION -- verified pattern (setup/scripts/_shared.ps1's
  Stop-StaleClaudeProcesses reaps stale python.exe references to this repo
  every ~3-5 min unless EXEMPT_DAEMONS matches): 'pythonw.exe' sits outside
  Stop-StaleClaudeProcesses's Win32_Process Name filter entirely (primary
  exemption, independent of any string match), PLUS this task is launched via
  backtest\.venv\Scripts\pythonw.exe, whose CommandLine also contains the
  literal substring 'backtest\.venv' (an existing $EXEMPT_DAEMONS entry,
  defense in depth) -- same verified shape as install-crypto-twin.ps1 /
  install-twin-sentinel.ps1 / install-free-model-audit.ps1.

  WIRING PATTERN (flash-free, matches the above installers exactly):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> ledger_archive.py
  Single-hop chain (ledger_archive.py is a native Python script, no .ps1 wrapper
  needed, no --live flag -- it never places orders, never touches heartbeat/
  params/CLAUDE.md, read-only on every source it copies).

  To verify after running: Get-ScheduledTask -TaskName Gamma_LedgerArchive | Get-ScheduledTaskInfo
  REVERT: powershell setup\scripts\install-ledger-archive.ps1 -Uninstall
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root      = "C:\Users\jackw\Desktop\42"
$taskName  = "Gamma_LedgerArchive"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs         = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script      = Join-Path $root "setup\scripts\ledger_archive.py"

if (-not (Test-Path $pythonwVenv)) { throw "backtest venv pythonw.exe not found at $pythonwVenv" }
if (-not (Test-Path $script))      { throw "ledger_archive.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> backtest-venv pythonw -> ledger_archive.py
# (flash-free chain; backtest-venv pythonw is BOTH the reaper-exempt-by-path
# launcher AND the interpreter that already has et_clock importable cleanly).
$wscriptArgs = "//nologo `"$vbs`" `"$pythonwVenv`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# Daily fire, every day (no weekday gate -- safety archive, not a trading task).
# 16:12 ET -> 14:12 MT (this rig's fixed 2h Mountain-behind-Eastern offset).
$trigger = New-ScheduledTaskTrigger -Daily -At "14:12"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Daily LOCAL archive of decision ledgers + trade logs (belt-and-suspenders after the 2026-07-14 git-stash-drop incident that destroyed ~3 weeks of uncommitted history). Fires daily 16:12 ET (14:12 MT). ledger_archive.py copies core-decisions.jsonl + fleet risky-1/risky-3/safe-3 decisions.jsonl + journal/trades.csv + journal/trades-aggressive.csv into automation/archive/ledgers/<ET-date>/ via shutil.copy2 (idempotent overwrite), then prunes archive dirs older than 30 days. Pure Python, `$0, read-only on sources, always exits 0. Reaper-exempt: pythonw.exe outside Stop-StaleClaudeProcesses's Name filter, plus backtest\.venv path match (defense in depth). Guard: backtest/tests/test_ledger_archive.py. Built 2026-07-14." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
