# install-firm-brief.ps1 -- register Gamma_FirmBrief (HANDOFF-2026-07-09-TRUTH-AND-EXITS, T9).
# Clone of install-level-memory.ps1 / install-broker-fills.ps1's wscript->pythonw hidden pattern.
# Two single-daily-fire triggers on ONE task (this is NOT a repeating-intraday producer -- it's
# a twice-a-day cockpit snapshot):
#   (a) 14:10 LOCAL (Mountain) = 16:10 ET -- AFTER Gamma_BrokerFills' 16:05 ET EOD fire (T1, which
#       writes pnl-statement.json this script reads) and AFTER Gamma_EodFlatten (15:55 ET), so the
#       day's ledger is fully settled before the EOD brief is written.
#   (b) 06:35 LOCAL (Mountain) = 08:35 ET -- AFTER Gamma_Premarket (08:30 ET), so the premarket
#       brief reports yesterday's numbers fresh each morning (pnl-statement.json's last full day).
$ErrorActionPreference = "Stop"
$Root       = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName   = "Gamma_FirmBrief"
$pythonw      = Join-Path $Root "backtest\.venv\Scripts\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$worker       = Join-Path $ScriptsDir "firm_brief.py"
# 2026-08-07: relay through run_cmd_hidden.py for real exit-code visibility -- see
# VBS-WRAPPER-EXIT-CODE-BLIND-SPOT / Gamma_CryptoTwin drift finding, queue.md.
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"

foreach ($p in @($pythonw, $runExeHidden, $worker, $sysPythonw, $runCmdHidden)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$Root`" -- `"$pythonw`" `"$worker`""

# (a) EOD fire -- 14:10 local (Mountain) = 16:10 ET.
$eodTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:10"

# (b) Premarket fire -- 06:35 local (Mountain) = 08:35 ET.
$premarketTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "06:35"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 3)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($eodTrigger, $premarketTrigger) `
    -Settings $settings `
    -Description "T9 (HANDOFF-2026-07-09-TRUTH-AND-EXITS): ONE-page firm cockpit. firm_brief.py reads T1's pnl-statement.json (engine P&L last 2 trading days + one line per consolidated engine trade), the HANDOFF J-DECISIONS top-3 + any queue.md J: marker, and the cached self_check verdict -> writes automation/state/firm-brief.md + queues one mentioned Discord ping. Read-only/notify-only, $0, no network. Fires 16:10 ET EOD (after Gamma_BrokerFills 16:05 EOD) + 08:35 ET premarket (after Gamma_Premarket 08:30)."

Write-Output "Registered $TaskName."
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName $TaskName | Select-Object NextRunTime, LastRunTime, LastTaskResult
