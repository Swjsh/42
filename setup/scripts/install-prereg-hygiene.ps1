#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_PreregHygiene -- nightly prereg hygiene monitor (B3-monitors,
  2026-09-01). Fires daily 16:58 ET (14:58 MT local -- this box is Mountain, ET=local+2h).

.DESCRIPTION
  THE GAP THIS CLOSES: pre-registrations (analysis/recommendations/*prereg*.json) are
  frozen commitments per the eval-first doctrine (OP-11) -- but nothing checked whether
  a filed prereg still parses, has gone stale (FROZEN/NOT RUN for weeks), or is an
  ORPHAN nothing in the live pipeline references any more (so its kill/arm criteria can
  never fire). setup/scripts/prereg_hygiene.py closes this: parses every prereg,
  extracts a status/verdict field, computes age, checks for code/doc references under
  setup/backtest/automation (excluding its own STATUS.md output -- guards against a
  self-referential loop), and flags any prereg that is stale + old + orphaned.

  Writes analysis/recommendations/prereg-hygiene.json every run (stable read surface).
  Appends ONE '### BROKEN: prereg-hygiene <ts>' block to automation/overnight/STATUS.md
  ONLY when the flagged-file set CHANGED since the last run (deduped -- OP-25 "compound,
  don't accumulate", never spam an unchanged nightly finding).

  NEVER blocks/kills/auto-disarms/writes params -- pure report. Pure stdlib + optional
  `rg` subprocess (falls back to a single combined Python tree walk if `rg` is
  unavailable on this box's native-Python subprocess PATH, which it is -- verified this
  session). $0 cost, ~1-20s runtime.

  WIRING PATTERN (flash-free, cloned from install-gate-recency.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> prereg_hygiene.py
  System pythonw (no third-party deps -- pure stdlib).

  TZ RULE: rig is Mountain Time (ET = local + 2h). -At is LOCAL time. 14:58 MT = 16:58 ET,
  after the 15:55 ET EOD flatten and before the overnight pipeline's later fires. A DAILY
  trigger (not a one-time TimeTrigger, which goes dark after the install day per
  project_scheduled_task_onetime_trigger_dark).

  Output:
    analysis/recommendations/prereg-hygiene.json -- latest report
    automation/state/logs/prereg-hygiene.std{out,err}.log -- headless stdio redirect
    automation/state/logs/run-cmd-hidden-<date>.log -- the real exit code, dated

  To verify after running: Get-ScheduledTask -TaskName Gamma_PreregHygiene | Get-ScheduledTaskInfo
  To test now (does NOT wait for the fire time): Start-ScheduledTask -TaskName Gamma_PreregHygiene
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_PreregHygiene" -Confirm:$false

  Per CLAUDE.md OP-3 ($0, pure Python) + OP-25 (fail loud, never silent) + OP-11
  (eval-first prereg discipline). Guard: backtest/tests/test_prereg_hygiene_2026_09_01.py.
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\prereg_hygiene.py"
$taskName     = "Gamma_PreregHygiene"

foreach ($p in @($vbs, $sysPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- system pythonw -> prereg_hygiene.py
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# Daily 14:58 LOCAL (Mountain) = 16:58 ET.
$trigger = New-ScheduledTaskTrigger -Daily -At "14:58"

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
    -Description ("Nightly prereg hygiene monitor (B3-monitors, 2026-09-01): parses every " + `
    "analysis/recommendations/*prereg*.json, flags malformed JSON, and flags any prereg " + `
    "that is FROZEN/NOT RUN + age>14d + orphaned (no setup/backtest/automation reference). " + `
    "Writes analysis/recommendations/prereg-hygiene.json every run; appends ONE deduped " + `
    "STATUS.md block only when the flagged set CHANGES. NEVER blocks/kills/writes params " + `
    "-- report only. Daily 14:58 MT (16:58 ET). Pure stdlib Python, `$0. Guard: " + `
    "backtest/tests/test_prereg_hygiene_2026_09_01.py.") `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Output "OK: Registered $taskName for daily 14:58 MT (16:58 ET)"
Write-Output "    Report:   analysis\recommendations\prereg-hygiene.json"
Write-Output "    Test now: Start-ScheduledTask -TaskName $taskName"
Write-Output "    Next run: $($info.NextRunTime)"
