# install-winner-autopsy.ps1 -- register Gamma_WinnerAutopsy (the WINNER-side autopsy organ,
# J 2026-07-31: "We need to analyze these winners just as much as the losers so we can figure
# out how to either stay in them longer or get better exits").
#
# Clone of install-trade-autopsy.ps1's wscript->pythonw hidden pattern (OP-27 L41 / lesson C8:
# headless Windows spawn = system pythonw + CREATE_NO_WINDOW + stdio redirect; a visible
# console popup on J's screen is a standing offense). ONE daily fire:
#   14:25 LOCAL (Mountain) = 16:25 ET -- 10 min AFTER Gamma_TradeAutopsy (14:15 local /
#   16:15 ET) so the loss-side organ finishes first, and both land well before the next
#   morning's Gamma_FirmBrief premarket fire (08:35 ET) which renders BOTH lines.
#
# DAILY (not weekly-weekdays like its loss-side sibling) on purpose: this is a POPULATION
# re-walk, not a same-day job. It is idempotent and $0, so a weekend fire simply re-confirms
# the standing capture-rate number rather than leaving it stale across the weekend. A real
# MSFT_TaskDailyTrigger is asserted at the end of this script -- this repo has been burned by
# tasks documented Active while sitting Disabled, and by one-time triggers that go dark after
# their first fire.
$ErrorActionPreference = "Stop"
$Root       = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName   = "Gamma_WinnerAutopsy"
$pythonw    = Join-Path $Root "backtest\.venv\Scripts\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$worker     = Join-Path $ScriptsDir "winner_autopsy.py"

foreach ($p in @($pythonw, $runExeHidden, $worker)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# --out all -> analysis/winner-autopsies/all.{md,jsonl} is the standing, always-current
# population report; winner-autopsy-last.json is what firm_brief renders.
$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$worker`" --out all"

# 14:25 local (Mountain) = 16:25 ET, every day.
$trigger = New-ScheduledTaskTrigger -Daily -At "14:25"

# Wider than the worker's own runtime: the population re-walk scales with the winner count and
# the OPRA bar fetcher retries with backoff on a cold/indexing contract.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "The winner-side autopsy organ (J 2026-07-31: 'we need to analyze these winners just as much as the losers'). winner_autopsy.py walks EVERY winning closed engine position in the broker-truth fills-ledger and answers, mechanically: what triggered the entry, why that strike, the in-trade timeline with high-water mark (from the engine's own exit_pass rows), which exit_manager stage closed each leg, giveback per leg (peak available vs realized), and a live-executable exit-variant grid replayed through the REAL exit_manager on real 1-min OPRA bars (entry+1 convention). Headline metric = CAPTURE RATE: realized P&L over the best SINGLE fixed exit policy -- never the hindsight peak (oracle is reported separately, labelled unachievable). Writes analysis/winner-autopsies/all.{md,jsonl} + winner-autopsy-last.json (firm-brief renders it). DESCRIPTIVE ONLY: never writes hypothesis-queue.jsonl or queue.md, never proposes an exit change -- winners-only samples condition on the outcome and cannot support a policy switch. Notify-only, fail-open, exits 0 always. Guards: test_winner_autopsy.py (24/24) + test_firm_brief_winner_autopsy_section.py (10/10)."

Write-Output "Registered $TaskName."
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State

# --- POST-REGISTRATION ASSERTIONS (OP-33b: registered != firing) ---------------------------
$t = Get-ScheduledTask -TaskName $TaskName
if ($t.State -eq "Disabled") { Write-Error "$TaskName registered but DISABLED"; exit 1 }
$trigType = $t.Triggers[0].CimClass.CimClassName
if ($trigType -ne "MSFT_TaskDailyTrigger") {
    Write-Error "$TaskName trigger is $trigType, expected MSFT_TaskDailyTrigger (a one-time trigger goes dark after its first fire)"
    exit 1
}
$info = Get-ScheduledTaskInfo -TaskName $TaskName
if (-not $info.NextRunTime) { Write-Error "$TaskName has NO NextRunTime -- it will never fire"; exit 1 }
Write-Output "Assertions PASS: State=$($t.State), Trigger=$trigType, NextRunTime=$($info.NextRunTime)"
$info | Select-Object NextRunTime, LastRunTime, LastTaskResult
