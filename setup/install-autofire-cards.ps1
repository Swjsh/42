#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_AutofireCards scheduled task -- fires daily at 23:30 ET (Mon-Fri),
  evening only, well outside 09:30-15:55 ET market hours. Runs autofire_cards.py
  --live, which fires ONLY cockpit action cards gamma_cockpit_cards.py already
  classified autofire_safe (read-and-report objectives, no action verb anywhere
  in the card). The runner re-checks RTH / companion-halt.flag / quiet-mode.json
  / per-run+per-day caps itself on every invocation -- this trigger time is
  scheduling hygiene, not the enforcement point.

  J, 2026-08-29: "Auto-fire the safe cards. Cards that only read and report
  could fire on a schedule with results waiting for me. I would only click the
  ones with consequences."

  This is the DEDICATED evening task named in gamma_watcher.py's own install
  comment ("the autofire runner has its own evening task with its own
  guards") -- separate from Gamma_Watcher's 24/7 observe-only 15-min tick,
  which stays undriven until J flips it.
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$taskName = "Gamma_AutofireCards"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$scriptPath = "C:\Users\jackw\Desktop\42\setup\scripts\run-autofire-cards.ps1"

# WINDOW-LEAK CHAIN (fixed 2026-08-30, J: "first priority is stopping all popups").
# This task was the LAST one on this box still using run_hidden.vbs, which builds
# `powershell.exe -WindowStyle Hidden ...` and hands it to WScript.Shell.Run -- i.e.
# ShellExecute, which routes through the Windows 11 default-terminal handler and leaks a
# visible `WindowsTerminal -Embedding` window. `-WindowStyle Hidden` does NOT prevent that
# (LESSONS-LEARNED: WT ignores it when WT is the default terminal app); it is the same
# chain that made Gamma_DiscordBridge pop a window every 5 min for weeks.
# Canonical replacement, per run_ps1_hidden.py's own docstring -- every hop is either
# GUI-subsystem or spawned with CREATE_NO_WINDOW, so no console is ever allocated:
#   wscript -> run_exe_hidden.vbs -> sys pythonw -> run_ps1_hidden.py -> the .ps1
# Flagged by audit_window_leak_compliance.py check (4) TASK_VISIBLE_WINDOW while the task
# sat un-fired (LastTaskResult 267011 = "has never run"). Its first real unattended fire is
# 2026-08-31 21:30 local, so this lands before it rather than after.
$vbsWrapper   = "C:\Users\jackw\Desktop\42\setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runPs1Hidden = "C:\Users\jackw\Desktop\42\setup\scripts\run_ps1_hidden.py"

foreach ($p in @($scriptPath, $vbsWrapper, $sysPythonw, $runPs1Hidden)) {
    if (-not (Test-Path $p)) { throw "required launcher-chain file missing: $p" }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# 20:30 ET weekdays -- after EOD pipeline (16:30-ish Analyst/Treasurer), inside
# the After-4pm work block, well clear of the 09:30-15:55 ET trading window and
# of Gamma_ShadowEval (16:05 ET) / Gamma_EodBrief. MT (Mountain) = ET - 2h
# during MDT, so 20:30 ET = 18:30 MT. Windows Task Scheduler uses LOCAL time.
# 21:30 LOCAL (this box runs Mountain) = 23:30 ET.
# ROOT CAUSE OF "NEVER RAN" (2026-08-30): this was 18:30 local = 20:30 ET, which sits
# INSIDE the weekday quiet window (18:00-23:00 ET). quiet-mode disables every task it
# holds down, so the trigger was muted before it could ever fire -- last result 267011
# ("has never run") since registration, and both autofire-ledger rows read
# "refused: quiet-mode". 23:30 ET is inside the LOUD maintenance band (23:00-08:00 ET),
# so the task is actually enabled when its trigger comes round, and it is still far
# outside 09:30-15:55 ET market hours.
$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "21:30"

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$vbsWrapper`" `"$sysPythonw`" `"$runPs1Hidden`" `"$scriptPath`""

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action `
    -Settings $settings -Principal $principal `
    -Description ("Fires ONLY autofire_safe cockpit action cards (read-and-report " +
    "objectives, classified by gamma_cockpit_cards.py). Refuses during 09:30-15:55 ET, " +
    "while companion-halt.flag exists, or while quiet-mode.json is active (unless " +
    "--allow-quiet). Capped 2/run, 6/day, ledgered in automation/state/autofire-ledger.jsonl " +
    "across restarts. Fires 23:30 ET weekdays, inside the LOUD band so quiet-mode cannot mute it.") | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
