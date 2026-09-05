# install-trade-autopsy.ps1 -- register Gamma_TradeAutopsy (the hypothesis organ, J 2026-07-08:
# "why doesn't Gamma think 'maybe we're stopping out too early' -- I need to stop prompting").
# Clone of install-firm-brief.ps1's wscript->pythonw hidden pattern. ONE daily fire:
#   14:15 LOCAL (Mountain) = 16:15 ET -- AFTER Gamma_BrokerFills' 16:05 ET EOD fire (the
#   fills-ledger this reads) and AFTER Gamma_EodFlatten (15:55), BEFORE the next morning's
#   Gamma_FirmBrief premarket fire (08:35 ET) which renders the autopsy line.
$ErrorActionPreference = "Stop"
$Root       = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName   = "Gamma_TradeAutopsy"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$worker       = Join-Path $ScriptsDir "trade_autopsy.py"
# 2026-08-07: relay through run_cmd_hidden.py for real exit-code visibility -- see
# VBS-WRAPPER-EXIT-CODE-BLIND-SPOT / Gamma_CryptoTwin drift finding, queue.md.
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath   = Join-Path $Root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"

foreach ($p in @($runExeHidden, $worker, $sysPythonw, $runCmdHidden)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$Root`" --env `"PYTHONPATH=$pythonPath`" -- `"$sysPythonw`" `"$worker`""

# 14:15 local (Mountain) = 16:15 ET, weekdays.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:15"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "The hypothesis organ (J 2026-07-08). trade_autopsy.py autopsies EVERY closed engine position from the broker-truth fills-ledger: counterfactual replays through the LIVE exit_manager on real 1-min bars, mechanism tags (stopped_then_paid / paid_the_spike / exit_shape_cost / exit_beat_theta), rolling detectors -> structured hypotheses into automation/state/hypothesis-queue.jsonl + queue.md task blocks (conductor/chef intake) + one Discord line. Writes analysis/autopsies/{date}.{jsonl,md} + trade-autopsy-last.json (firm-brief renders it). Notify-only, fail-open, exits 0 always."

Write-Output "Registered $TaskName."
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName $TaskName | Select-Object NextRunTime, LastRunTime, LastTaskResult
