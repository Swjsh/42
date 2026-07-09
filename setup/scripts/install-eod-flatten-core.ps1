#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_EodFlattenCore -- the PURE-PYTHON EOD flatten backstop
  (Overnight Read D2 finding #4, 2026-07-09; original code+guards committed 2026-06-27).

  PURPOSE: replace reliance on `claude --print eod-flatten.md` (shares the Max-pool with
  the heartbeat -- if that pool starves at 15:55 ET, open 0DTE positions expire worthless).
  Confirmed 2026-07-09: both Gamma_EodFlatten/_Aggressive DID starve ("Exceeded USD budget
  (1)", real log `=== END tick exit=1 ===`) while Get-ScheduledTaskInfo reported
  LastTaskResult=0 (wscript fire-and-forget masking -- see preopen_readiness.py fix).
  This wires the pure-Python eod_flatten.py path (same broker primitives as
  heartbeat_core -- no LLM, no MCP, no CDP) at 13:52 MT = 15:52 ET, 3 minutes AHEAD of the
  LLM tasks' 15:55 fire, as an INDEPENDENT non-LLM backstop.

  WIRING PATTERN (flash-free, matches heartbeat_core + sight_beacon):
    wscript -> run_exe_hidden.vbs -> pythonw.exe -> eod_flatten.py
  The wscript + pythonw are both GUI-subsystem (no console allocation).
  run_exe_hidden.vbs passes window=0 -- no visible window ever.

  ACCOUNTS: eod_flatten.py's ACCOUNTS = ["safe-2", "bold-2"] already loops BOTH accounts
  internally in one fire -- ONE task covers both, no separate "_Aggressive" task needed.

  DEFENSE IN DEPTH (2026-07-09 correction): the existing LLM tasks (Gamma_EodFlatten /
  Gamma_EodFlatten_Aggressive) are LEFT REGISTERED AND UNTOUCHED -- this installer does
  NOT disable them (an earlier draft of this script did; that draft was never run/committed
  to production and is superseded by this version). Two independent flatten mechanisms
  covering the same 15:52-15:55 ET window is strictly safer than swapping one for the other.

  TZ RULE: this rig is Mountain Time (ET = local + 2h).
  15:52 ET -> 13:52 MT.  NEVER pass an ET literal to -At.

  To verify after running: Get-ScheduledTask -TaskName Gamma_EodFlattenCore | Get-ScheduledTaskInfo
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_EodFlattenCore" -Confirm:$false
          (Gamma_EodFlatten / _Aggressive were never touched -- nothing to restore there.)
#>

$ErrorActionPreference = "Stop"

$root      = "C:\Users\jackw\Desktop\42"
$vbs       = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$script    = Join-Path $root "setup\scripts\eod_flatten.py"
$etz       = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')

# ---- helper: show next-run in ET -----------------------------------------------
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

# ---- helper: register one EOD flatten task ------------------------------------
function Register-EodFlattenCore {
    param(
        [string]$TaskName,
        [string]$Description
    )

    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    # wscript -> run_exe_hidden.vbs -> pythonw -> eod_flatten.py (flash-free chain)
    $wscriptArgs = "//nologo `"$vbs`" `"$pythonw`" `"$script`""

    $action = New-ScheduledTaskAction `
        -Execute "wscript.exe" `
        -Argument $wscriptArgs `
        -WorkingDirectory $root

    # 13:52 MT = 15:52 ET, weekdays Mon-Fri (3 min AHEAD of the LLM tasks' 15:55 fire)
    $trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At ([DateTime]"13:52")

    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
        -MultipleInstances IgnoreNew

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description $Description `
        -Force | Out-Null

    Write-Host "Registered $TaskName (13:52 MT = 15:52 ET)"
    Show-NextET $TaskName
}

# ---- Register the single non-LLM EOD-flatten backstop (covers safe-2 + bold-2) -
Register-EodFlattenCore `
    -TaskName "Gamma_EodFlattenCore" `
    -Description "Pure-Python EOD flatten backstop (safe-2 + bold-2, one fire covers both). G7 fix 2026-06-27, registered 2026-07-09 (Overnight Read D2 finding #4). 13:52 MT = 15:52 ET. eod_flatten.py -> fleet_broker. NO LLM. Gamma_EodFlatten/_Aggressive (LLM) remain registered UNTOUCHED as defense-in-depth."

# NOTE (2026-07-09 correction): the old LLM tasks (Gamma_EodFlatten / Gamma_EodFlatten_Aggressive)
# are DELIBERATELY left registered and enabled -- NOT disabled. Two independent flatten
# mechanisms covering the same window is strictly safer than an order-close-surface swap.
# preopen_readiness.py's assess_eod_flatten_reality() now reads each task's REAL log-tail
# outcome (not Task Scheduler's masked LastTaskResult) to verify all three actually work.

Write-Host ""
Write-Host "Gamma_EodFlattenCore wired.  Verify with: Get-ScheduledTask -TaskName Gamma_EodFlattenCore | Get-ScheduledTaskInfo"
