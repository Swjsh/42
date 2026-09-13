#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_StationKiosk scheduled task -- the TV face's launcher (GOAL-
  GAMMA-STATION-2026-09-13 item 5 + the 2026-09-13 Wi-Fi/security amendments).

.DESCRIPTION
  Registers ONE task with a 5-min repeating trigger, 24/7, StartWhenAvailable
  (so a fresh logon/reboot picks it up within 5 minutes rather than needing a
  separate AtLogOn trigger) -- `station_kiosk.ps1 -Start`, which is itself
  idempotent: it no-ops if the kiosk is already alive, so firing it
  redundantly on every 5-min tick is always safe.

  ELEVATION NOTE (found during this build, 2026-09-13): registering a task
  with an ADDITIONAL `AtLogOn` trigger requires an elevated (Run as
  Administrator) PowerShell session -- verified by isolating exactly this
  parameter combination: the identical Action/Settings/Principal register
  successfully without an AtLogOn trigger, and fail with "Access is denied"
  the moment one is added, in this same non-elevated session. Rather than
  block the whole task on an elevation this installer does not have, it ships
  with the 5-min repeater ONLY (StartWhenAvailable already means a missed
  window after logon self-heals within 5 minutes). To ALSO add instant AtLogOn
  coverage later, run this from an elevated PowerShell:
      $t = Get-ScheduledTask -TaskName Gamma_StationKiosk
      Set-ScheduledTask -TaskName Gamma_StationKiosk -Trigger (
          @($t.Triggers) + (New-ScheduledTaskTrigger -AtLogOn))

  station_kiosk.ps1 -Start also runs station_presence.py --once FIRST, on the
  SAME fire -- per spec, presence rides this task's cadence rather than
  getting a second scheduled task.

  WIRING PATTERN (silent-rig canonical, matches Gamma_Station / Gamma_SelfCheck):
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> powershell.exe (hidden)
                   -> station_kiosk.ps1 -Start

  REGISTERED DISABLED ON PURPOSE (found during this build's own verification,
  2026-09-13): station_kiosk.ps1 -Start's fallback path calls `station_tv.py
  --face`, which opens a websocket to the TV requiring the SAME pairing
  handshake `--pair` uses -- and pairing has NOT happened yet (J is away; he
  pairs in person at the TV per the coordinator's instruction). If this task
  fired on its own 5-min cadence before that pairing exists, it would likely
  pop the TV's "Allow this device?" prompt with nobody there to accept it.
  Enable it ONLY after `station_tv.py --pair --i-am-j` has been run
  successfully with J at the TV:
      Enable-ScheduledTask -TaskName Gamma_StationKiosk
  (Separately, station_kiosk.ps1's local-Edge-kiosk path is ALSO gated off by
  default via config.json's hdmi_kiosk_enabled -- this box already has 2
  displays for J's own normal desk use, confirmed by a real -Snapshot capture,
  so a bare "displays >= 2" check would have hijacked his own active monitor.
  That gate is independent of this task's enabled/disabled state and stays
  off until a human confirms the TV is the real second display.)

  Verify:  schtasks /Query /TN Gamma_StationKiosk /V /FO LIST
  Test now (after enabling): Start-ScheduledTask -TaskName Gamma_StationKiosk
  Disable: .\setup\install-station-kiosk.ps1 -Uninstall
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$TaskName = "Gamma_StationKiosk"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Unregistered $TaskName."
    } else {
        Write-Host "$TaskName was not registered."
    }
    return
}

$WorkDir      = "C:\Users\jackw\Desktop\42"
$ScriptsDir   = Join-Path $WorkDir "setup\scripts"
$psExe        = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$kioskScript  = Join-Path $ScriptsDir "station_kiosk.ps1"

foreach ($p in @($psExe, $runExeHidden, $kioskScript)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Build the vbs argument list as an array + join, rather than hand-nested
# backtick-quoting -- each element becomes one independently-quoted token in
# run_exe_hidden.vbs's own command line, which is exactly what powershell.exe's
# argv parser expects regardless of the quoting (see run_exe_hidden.vbs's own
# "Usage: wscript //nologo run_exe_hidden.vbs <exe-path> [args...]").
$psArgs = @(
    $psExe,
    "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
    "-File", $kioskScript,
    "-Start"
)
$quoted = $psArgs | ForEach-Object { '"' + $_ + '"' }
$argumentString = "//nologo `"$runExeHidden`" " + ($quoted -join " ")

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $argumentString `
    -WorkingDirectory $WorkDir

$keepaliveTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration ([System.TimeSpan]::FromDays(365 * 10))

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Trigger $keepaliveTrigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description "Station TV face launcher (GOAL-GAMMA-STATION-2026-09-13 item 5): every 5 min (StartWhenAvailable covers logon within 5 min -- see this installer's ELEVATION NOTE for adding a true AtLogOn trigger later), runs station_presence.py --once then decides Edge-kiosk-on-second-display (gated off by config.json hdmi_kiosk_enabled, default false) vs the Wi-Fi TV face (station_tv.py --face) vs no_tv_display, idempotently. REGISTERED DISABLED until station_tv.py --pair --i-am-j has been run with J at the TV -- see this installer's own header comment for why. Guard: backtest/tests/test_station_kiosk_2026_09_13.py." `
    -Force | Out-Null

Disable-ScheduledTask -TaskName $TaskName | Out-Null

$info = Get-ScheduledTask -TaskName $TaskName
Write-Output "OK: Registered $TaskName -- every 5 min (StartWhenAvailable), REGISTERED DISABLED (pairing not done yet)"
Write-Output "    Worker:  setup\scripts\station_kiosk.ps1 -Start (also fires station_presence.py --once first)"
Write-Output "    State:   $($info.State)"
Write-Output "    Enable after pairing: Enable-ScheduledTask -TaskName $TaskName"
