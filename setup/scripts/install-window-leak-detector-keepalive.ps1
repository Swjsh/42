#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_WindowLeakDetectorKeepalive -- keepalive for the LIVE, real-time
  window-leak detector (setup/scripts/window-leak-detector.py), which continuously
  enumerates visible top-level windows (Win32 EnumWindows, 2x/sec) and logs any
  window owned by a suspect process image (python/pythonw/cmd/conhost/powershell/
  pwsh/wscript/cscript/WindowsTerminal) to automation/state/window-leaks.jsonl with
  full command_line + ancestry -- hard, timestamped, ground-truth evidence of any
  popup, independent of what any static source-code auditor believes.

.CONTEXT (2026-07-14, J: "stop the fkin popus on my screen")
  This detector was BUILT and ran cleanly for a week (2026-05-17 through 05-23,
  4200 polls, caught 7 real WindowsTerminal-Embedding leaks with full ancestry) and
  then silently stopped: automation/state/window-leak-detector-keepalive-*.log has
  no entries after 2026-05-23, and no task named *WindowLeak* was registered on
  this box (verified via Get-ScheduledTask '*WindowLeak*' -> empty). Nothing
  re-armed it and nothing flagged its absence -- a monitor-of-monitors gap: the ONE
  instrument that would have shown hard, real-time proof of the Gamma_DiscordBridge
  / SwjshAK-BrainSync popups (rather than J's word against a green JSON) was dark
  for ~2 months while the static audit_window_leak_compliance.py audit (which never
  looks at live windows at all, only source-code text patterns) quietly stood in
  for it. Re-arming this closes that hole: going forward, "is the audit lying" is
  answerable by reading window-leaks.jsonl directly, not by trusting any auditor's
  self-report.

  WIRING PATTERN (flash-free, matches install-ccr-keepalive.ps1's action pattern):
    wscript -> run_exe_hidden.vbs -> pythonw.exe -> window_leak_detector_keepalive.py
  window_leak_detector_keepalive.py is a native Python keepalive (checks
  window-leak-detector.pid, launches the detector via system pythonw +
  CREATE_NO_WINDOW|DETACHED_PROCESS if dead) -- no .ps1 to wrap, 3-arg chain.

  CADENCE: matches install-ccr-keepalive.ps1's `-Once` + 5-min repetition + ~10-year
  duration idiom -- every 5 min, 24/7 (a popup can happen at any hour, not just RTH).

  To verify after running: Get-ScheduledTask -TaskName Gamma_WindowLeakDetectorKeepalive
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root      = "C:\Users\jackw\Desktop\42"
$taskName  = "Gamma_WindowLeakDetectorKeepalive"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs     = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$script  = Join-Path $root "setup\scripts\window_leak_detector_keepalive.py"

if (-not (Test-Path $pythonw)) { throw "system pythonw.exe not found at $pythonw" }
if (-not (Test-Path $script))  { throw "window_leak_detector_keepalive.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> pythonw -> window_leak_detector_keepalive.py (flash-free)
$wscriptArgs = "//nologo `"$vbs`" `"$pythonw`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# Every 5 min, 24/7 -- a popup can happen at any hour.
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
    -Description "Keepalive for the LIVE window-leak detector (window-leak-detector.py): checks window-leak-detector.pid every 5 min 24/7, relaunches (detached, CREATE_NO_WINDOW) if dead. The detector itself polls EnumWindows 2x/sec and logs any visible window owned by a suspect process image to automation/state/window-leaks.jsonl with command_line + ancestry -- ground-truth popup evidence independent of any static auditor. Re-armed 2026-07-14 after ~2 months dark (last ran 2026-05-23); root cause of the popup audit's blind spot (J: 'stop the fkin popus on my screen')." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
