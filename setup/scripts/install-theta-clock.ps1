#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_ThetaClock -- the THETA COCKPIT in-trade Greeks visibility instrument
  (J directive, 2026-08-01, verbatim: "We can't just be getting in options trades and have
  Theta kick our ass without us knowing.").

  VISIBILITY ONLY. This task places NO order, touches NO exit rule, adds NO gate, and never
  writes anything heartbeat_core.py reads -- it is a standalone read-only watcher, fully off
  the 1-min trading hot path. A THETA-based EXIT class is a SEPARATE, un-built,
  pre-registered study; nothing here arms one.

  Each fire runs setup/scripts/theta_clock.py, which:
    1. Reads open SPY option positions for every ACTIVE account (core safe-2/bold-2 +
       fleet safe-3/risky-1/risky-3) via automation/state/fleet/fleet_broker.py -- the SAME
       credential-loading + REST module heartbeat_core.py itself already depends on
       (read-only calls only: get_positions, get_option_greeks).
    2. Computes a THETA CLOCK row per open position (mid/bid/ask, unrealized %, a
       model-free intrinsic-value delta component, a documented sqrt(time-remaining)
       theta-decay ESTIMATE, and real broker greeks when Alpaca's feed returns them) and
       appends it to automation/state/theta-clock/theta-clock-<date>.jsonl +
       automation/state/theta-clock.json (current snapshot).
    3. Fires ONE loud, non-repeating STATUS.md "## Live watch" line when a position's
       estimated theta burn over the last 15 min exceeds its estimated delta gain by more
       than $5 -- ALERT ONLY, latched per-position forever, never auto-acts.
    4. Fail-open everywhere: one account/position failure never stops the others; always
       exits 0; writes NO lock/pid file (Task Scheduler's own -MultipleInstances IgnoreNew
       below is the sole overlap guard, so a crashed run can never wedge a future one).

  CADENCE -- every 1 min, 09:30-16:00 ET weekdays (matches HeartbeatCore's own RTH window,
  extended 5 min past EOD-flatten at 15:55 so a lingering position's final minutes are still
  watched):
    07:30 MT = 09:30 ET start, repeat every 1 min for 6h30m -> covers 09:30-16:00 ET.

  TZ RULE: this rig is Mountain Time (ET = local + 2h). NEVER pass an ET literal to -At.

  CADENCE PATTERN: `-Weekly -DaysOfWeek Mon-Fri -At <MT time>` base trigger + a `.Repetition`
  taken from a throwaway `-Once` trigger's RepetitionInterval/RepetitionDuration -- the
  verified-live pattern (install-context-bundle.ps1 / install-key-levels-snapshot.ps1), NOT a
  bare one-time/interval trigger (a trigger with no recurrence spec goes dark the next day --
  project_scheduled_task_onetime_trigger_dark).

  REAPER EXEMPTION -- verified pattern (setup/scripts/_shared.ps1's Stop-StaleClaudeProcesses
  reaps stale python.exe references to this repo every ~3-5 min unless EXEMPT_DAEMONS
  matches): 'pythonw.exe' sits outside Stop-StaleClaudeProcesses's Win32_Process Name filter
  entirely (primary exemption), PLUS this task launches backtest\.venv\Scripts\pythonw.exe,
  whose CommandLine also contains the literal substring 'backtest\.venv' (an existing
  $EXEMPT_DAEMONS entry, defense in depth) -- same verified shape as every sibling
  install-*.ps1 in this directory.

  WIRING PATTERN (flash-free, matches install-context-bundle.ps1 exactly):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> theta_clock.py
  Single-hop chain. theta_clock.py itself ALSO carries its own OP-27 L41 headless stdio
  redirect (copied-and-depth-adapted from guard_runner_slow.py/firm_brief.py) so a pythonw
  launch never allocates a visible console window even without this wscript relay --
  defense in depth, matching every other popup-storm fix in this repo.

  To verify after running: Get-ScheduledTask -TaskName Gamma_ThetaClock | Get-ScheduledTaskInfo
  REVERT: powershell setup\scripts\install-theta-clock.ps1 -Uninstall
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root     = "C:\Users\jackw\Desktop\42"
$taskName = "Gamma_ThetaClock"

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
$script       = Join-Path $root "setup\scripts\theta_clock.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')

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
#   -- backtest venv pythonw -> theta_clock.py
# (2026-08-08 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT migration -- was fire-and-forget.)
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonwVenv`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# 07:30 MT = 09:30 ET start; repeat every 1 min for 6h30m -> covers 09:30-16:00 ET, Mon-Fri.
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "07:30"
$rep = (New-ScheduledTaskTrigger -Once -At "07:30" `
        -RepetitionInterval (New-TimeSpan -Minutes 1) `
        -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 30)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("THETA COCKPIT (J directive 2026-08-01) -- in-trade Greeks VISIBILITY " + `
    "ONLY, never places/closes/resizes an order, never touches an exit rule. Every 1 min, " + `
    "09:30-16:00 ET weekdays. Reads open SPY option positions across all 5 active accounts " + `
    "(core safe-2/bold-2 + fleet safe-3/risky-1/risky-3) via fleet_broker.py (read-only). " + `
    "Writes automation/state/theta-clock.json + theta-clock/theta-clock-<date>.jsonl + " + `
    "theta-clock/position-state.json. Fires ONE non-repeating STATUS.md '## Live watch' " + `
    "line when estimated theta burn over 15 min exceeds estimated delta gain by >`$5 -- " + `
    "alert only, never auto-exits. Fail-open, no lock file, exits 0 always. " + `
    "Guard: backtest/tests/test_theta_clock.py.") `
    -Force | Out-Null

Write-Host "Registered $taskName (07:30 MT = 09:30 ET start, every 1 min for 6h30m, Mon-Fri)"
Show-NextET $taskName
Write-Host ""
Write-Host "Theta clock wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_ThetaClock | Get-ScheduledTaskInfo"
