# install-eod-dojo-manifest.ps1 -- register Gamma_EodDojoManifest (the film-room agenda
# generator, markdown/specs/DOJO-EOD-PIPELINE.md, J-directed 2026-07-21: "brainstorm running
# the EOD pipeline in line with the dojo now that we have candle replays"). Clone of
# install-trade-autopsy.ps1's wscript->pythonw hidden pattern (backtest .venv interpreter =
# already reaper-exempt via _shared.ps1's EXEMPT_DAEMONS 'backtest\.venv' marker). ONE daily
# fire:
#   14:20 LOCAL (Mountain) = 16:20 ET -- 5 min AFTER Gamma_TradeAutopsy (16:15 ET), so its
#   counterfactual replays/hypotheses are already written and citable per-exhibit, and well
#   after Gamma_EodFlatten (15:55) / Gamma_BrokerFills (16:05) so the day's fills-ledger and
#   core-decisions.jsonl are both settled for the day.
# 2026-08-18: routed via run_py_venv_hidden.py (2026-08-13 console-leak fix). Also closes
# VBS-WRAPPER-EXIT-CODE-BLIND-SPOT via self_check.check_run_py_venv_hidden_masked_exit().
# Live state was already on this wiring (2026-08-13 imperative patch); this template was
# drifted (CryptoTwin-class regression) until now.
$ErrorActionPreference = "Stop"
$Root       = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName   = "Gamma_EodDojoManifest"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$runPyVenvHidden = Join-Path $ScriptsDir "run_py_venv_hidden.py"
$worker     = Join-Path $ScriptsDir "dojo\exhibit_extractor.py"

foreach ($p in @($sysPythonw, $runExeHidden, $runPyVenvHidden, $worker)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runPyVenvHidden`" `"$worker`""

# 14:20 local (Mountain) = 16:20 ET, weekdays.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:20"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "The nightly film-room agenda generator (markdown/specs/DOJO-EOD-PIPELINE.md, J-directed 2026-07-21). exhibit_extractor.py is a pure read of automation/state/core-decisions.jsonl + journal/trades.csv -> automation/state/dojo/session-briefs/{date}.md: <=6 ranked exhibits (blocked-triggers first w/ forward SPY path, then score-high-no-trigger runs, then extra-lane fills, then J-called trades) so a dojo replay session can jump straight to the moments that mattered instead of re-deriving them by hand. Never overwrites a hand-authored brief (auto-marker guard). Runs AFTER Gamma_TradeAutopsy so its counterfactuals are citable. Zero LLM, `$0. Notify-only, fail-open, exits 0 always."

Write-Output "Registered $TaskName."
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName $TaskName | Select-Object NextRunTime, LastRunTime, LastTaskResult
