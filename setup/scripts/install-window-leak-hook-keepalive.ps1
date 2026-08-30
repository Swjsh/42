#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_WindowLeakHookKeepalive -- keepalive for the EVENT-DRIVEN, pre-paint
  console-window hider (setup/scripts/window_leak_hook.py).

.CONTEXT (2026-08-30, J: "first priority is stopping all popups tho i am seeing cmd or
  poewrshell popups that must not happen")
  Two hiders defend this box and only one of them was being kept alive:

    window-leak-detector.py  -- polls EnumWindows every 0.5s. Has a keepalive
                                (Gamma_WindowLeakDetectorKeepalive). Hides LATE: a leaked
                                window can sit on screen for up to half a second.
    window_leak_hook.py      -- SetWinEventHook(EVENT_OBJECT_SHOW), hides within a frame.
                                Had NO keepalive and NO liveness check anywhere.

  The hook died 2026-08-10 and was still dead 2026-08-30 (pid 9036 from
  window-leak-hook.pid not running; last window-leak-hook-*.log dated 08-10; zero Gamma_*
  task actions referencing window_leak_hook). For 20 days the only defence was the 0.5s
  poller -- which on 2026-08-30 alone logged 29 leaks, all `mitigated: true`, i.e. each one
  visible before it was hidden. That is exactly the flash J reported.

  This is the THIRD instance of this shape on this subsystem. The detector itself went dark
  ~2 months (2026-05-23 -> 2026-07-14) with nothing flagging it -- which is why it got a
  keepalive. The hook then shipped in July without one and repeated the failure verbatim.
  Registering this task closes the instance; check (6) HIDER_NOT_RUNNING in
  audit_window_leak_compliance.py closes the class, so a dead hider can never read GREEN.

  WIRING (flash-free -- no PowerShell anywhere in the chain, since a .ps1 link would itself
  leak the very window this is meant to suppress):
    wscript -> run_exe_hidden.vbs -> sys pythonw -> run_cmd_hidden.py -> sys pythonw
      -> window_leak_hook_keepalive.py

  CADENCE: every 5 min, 24/7 -- matches the detector keepalive. A popup can happen at any
  hour, and the window that matters most is precisely when J is not at the keyboard.

  Verify after running: Get-ScheduledTask -TaskName Gamma_WindowLeakHookKeepalive
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root     = "C:\Users\jackw\Desktop\42"
$taskName = "Gamma_WindowLeakHookKeepalive"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonw      = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\window_leak_hook_keepalive.py"

if (-not (Test-Path $pythonw))      { throw "system pythonw.exe not found at $pythonw" }
if (-not (Test-Path $vbs))          { throw "run_exe_hidden.vbs not found at $vbs" }
if (-not (Test-Path $runCmdHidden)) { throw "run_cmd_hidden.py not found at $runCmdHidden" }
if (-not (Test-Path $script))       { throw "window_leak_hook_keepalive.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$pythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonw`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

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
    -Description "Keepalive for the EVENT-DRIVEN window-leak hook (window_leak_hook.py): checks window-leak-hook.pid every 5 min 24/7 and relaunches it (detached, CREATE_NO_WINDOW) if dead. The hook hides a service-rooted console-host window on EVENT_OBJECT_SHOW -- within a frame -- where the 0.5s poller leaves it visible for up to half a second. Registered 2026-08-30 after the hook was found dead since 2026-08-10 with nothing on the box responsible for restarting it (J: 'first priority is stopping all popups')." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
