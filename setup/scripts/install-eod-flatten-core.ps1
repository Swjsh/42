#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_EodFlattenCore + Gamma_EodFlattenCore_Aggressive as the PURE-PYTHON
  EOD flatten executors (G7 fix, 2026-06-27).

  PURPOSE: replace the fragile `claude --print eod-flatten.md` path that shares the
  Max-pool with the heartbeat.  If that pool starves at 15:55 ET, open 0DTE positions
  expire worthless.  This script wires the pure-Python eod_flatten.py path (same broker
  primitives as heartbeat_core -- no LLM, no MCP, no CDP) at 13:55 MT = 15:55 ET.

  WIRING PATTERN (flash-free, matches heartbeat_core + sight_beacon):
    wscript -> run_exe_hidden.vbs -> pythonw.exe -> eod_flatten.py
  The wscript + pythonw are both GUI-subsystem (no console allocation).
  run_exe_hidden.vbs passes window=0 -- no visible window ever.

  ACCOUNTS:
    Gamma_EodFlattenCore            -- safe-2  (standard env)
    Gamma_EodFlattenCore_Aggressive -- bold-2  (same script, same env; secrets.json has both keys)

  BOTH tasks run at 13:55 MT = 15:55 ET.
  The retired LLM tasks (Gamma_EodFlatten / _Aggressive) are left DISABLED, not deleted,
  so the LLM path can be re-enabled as a verbose confirmation step if desired.

  TZ RULE: this rig is Mountain Time (ET = local + 2h).
  15:55 ET -> 13:55 MT.  NEVER pass an ET literal to -At.

  To verify after running: setup\scripts\task_health_et.ps1
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

    # 13:55 MT = 15:55 ET, weekdays Mon-Fri
    $trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At ([DateTime]"13:55")

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

    Write-Host "Registered $TaskName (13:55 MT = 15:55 ET)"
    Show-NextET $TaskName
}

# ---- 1. Safe account EOD flatten -----------------------------------------------
Register-EodFlattenCore `
    -TaskName "Gamma_EodFlattenCore" `
    -Description "Pure-Python EOD flatten (safe-2). G7 fix 2026-06-27. 13:55 MT = 15:55 ET. eod_flatten.py -> fleet_broker. NO LLM."

# ---- 2. Bold account EOD flatten -----------------------------------------------
Register-EodFlattenCore `
    -TaskName "Gamma_EodFlattenCore_Aggressive" `
    -Description "Pure-Python EOD flatten (bold-2). G7 fix 2026-06-27. 13:55 MT = 15:55 ET. eod_flatten.py -> fleet_broker. NO LLM."

# ---- 3. Disable the old LLM tasks (leave as confirmation fallback, NOT primary) -
foreach ($old in @("Gamma_EodFlatten", "Gamma_EodFlatten_Aggressive")) {
    $t = Get-ScheduledTask -TaskName $old -ErrorAction SilentlyContinue
    if ($t -and $t.State -ne 'Disabled') {
        Disable-ScheduledTask -TaskName $old | Out-Null
        Write-Host "Disabled LLM fallback task: $old (demoted, not primary)"
    } elseif ($t) {
        Write-Host "LLM fallback $old already disabled -- OK"
    } else {
        Write-Host "LLM fallback $old not found -- skipping"
    }
}

Write-Host ""
Write-Host "G7 EOD flatten wired.  Verify with: setup\scripts\task_health_et.ps1"
