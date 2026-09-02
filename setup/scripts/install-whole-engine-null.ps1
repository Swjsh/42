#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_WholeEngineNull -- the weekly whole-engine-level null study fire
  (TASK B1-whole-engine-null-runner, 2026-09-01).

  PURPOSE: runs setup/scripts/whole_engine_null.py, which implements
  analysis/recommendations/prereg-whole-engine-null-2026-09-01.json (R10,
  FABLE-FULL-AUDIT-2026-09-01) -- the first ENGINE-level null this repo has ever run
  (every prior null was feature-level: does gate X help within trades the engine already
  took). Answers whether the WHOLE engine beats the nulls a long-beta strategy would also
  beat, given the measured +0.232 book-day-P&L correlation with SPY's own open->close
  return. MEASUREMENT ONLY -- never places an order, never edits a gate/params file.

  CADENCE: Fridays 16:55 ET -- after the week's last session closes (15:55 ET flatten) and
  after the daily EOD pipeline, so the week's trades are already in trades-enriched.jsonl.
  Weekly, not daily: this study re-walks every P1 trading day's option bars through
  walk_exit_manager every fire, which is real CPU/IO even with the bars-cache warm --
  a daily cadence would burn the same $0-but-not-free compute for a distribution that
  only grows by a handful of trades between Fridays.

  WIRING PATTERN (flash-free, matches install-context-bundle.ps1 / install-ssr-shadow.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- backtest\.venv\Scripts\pythonw.exe -> whole_engine_null.py
  Runs on the BACKTEST venv (imports pandas + exit_manager_walk + strategies) via
  run_cmd_hidden.py's exit-code-forwarding relay (2026-08-08 VBS-WRAPPER-EXIT-CODE-BLIND-
  SPOT fix -- a bare wscript relay masks LastTaskResult).

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 16:55 ET -> 14:55 MT. NEVER pass
  an ET literal to -At.

  CONFIG FREEZE (2026-08-31 -> 2026-09-29): whole_engine_null.py imports strategies.py
  READ-ONLY (RIBBON_RIDE.exit.to_dict(), a dataclass literal) and writes only under
  analysis/whole-engine-null/ -- no frozen-path file is ever opened for write. Freeze-safe
  by construction, same as refused_setup_ledger.py.

  To verify after running: Get-ScheduledTask -TaskName Gamma_WholeEngineNull | Get-ScheduledTaskInfo
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_WholeEngineNull" -Confirm:$false
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv  = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\whole_engine_null.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName     = "Gamma_WholeEngineNull"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

foreach ($p in @($vbs, $pythonwVenv, $sysPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

function Show-NextET {
    param([string]$Name)
    $info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction SilentlyContinue
    if ($info -and $info.NextRunTime) {
        $et = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
        Write-Host ("  NextRun ET: {0}" -f $et.ToString("yyyy-MM-dd HH:mm"))
    } else {
        Write-Host "  NextRun ET: (none / on-demand)"
    }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- backtest venv pythonw -> whole_engine_null.py (default resamples: 300, ~2-8 min warm-cache)
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonwVenv`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 14:55 MT = 16:55 ET, Fridays only.
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Friday `
    -At ([DateTime]"14:55")

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description ("Whole-engine null study (TASK B1, prereg-whole-engine-null-2026-09-01.json, " + `
    "R10 FABLE-FULL-AUDIT-2026-09-01). Fridays 16:55 ET. whole_engine_null.py: N_a random-" + `
    "entry-same-exit / N_b buy-and-hold-ATM / N_c opposite-direction nulls, walked through " + `
    "the REAL exit_manager core with the production RIBBON_RIDE ExitShape, plus V9 (replays " + `
    "the engine's OWN entries to validate the harness -- verdict withheld below 85% sign " + `
    "agreement). MEASUREMENT ONLY: never places, arms, or edits a gate/params file. Writes " + `
    "analysis/whole-engine-null/{date}.json + latest.json + {date}.md + summary-line.txt.") `
    -Force | Out-Null

Write-Host "Registered $taskName (14:55 MT = 16:55 ET, Fridays)"
Show-NextET $taskName
Write-Host ""
Write-Host "Verify: Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo"
Write-Host "Revert: Unregister-ScheduledTask -TaskName `"$taskName`" -Confirm:`$false"
