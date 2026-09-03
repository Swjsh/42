# Registers Gamma_FeeRecalibrate -- weekly broker-truth fee drift monitor.
#
# WHY (queue.md FEE-RECALIBRATION-FROM-BROKER, LOW, 2026-09-03): go_live_gate.py's
# reconciliation + cost-adjusted statistical criterion both lean on a STATIC FEE_RATES
# dict calibrated once, 2026-08-18. Nothing rechecks it against a real broker bill on any
# cadence. setup/scripts/fee_recalibrate.py pulls Alpaca FEE activities (OCC/ORF/TAF/REG/
# CAT) for every active arm over the trailing 14 days, derives the realized rate the
# broker's own charges imply, and writes automation/state/fee-calibration.json with a
# GREEN/YELLOW/RED status (>10%/>25% max drift). READ-ONLY: it NEVER edits FEE_RATES in
# go_live_gate.py or anywhere else -- drift is reported, the gate keeps its static dict
# (freeze, per OP-11 -- a mid-window bar change is a post-hoc anti-pattern however
# well-evidenced). A human decides whether/when to pre-register a rate change.
#
# CADENCE: Sunday 17:00 ET = 15:00 MT (this box runs Mountain time, ET = local+2, per
# CLAUDE.md's clock-discipline banner) -- weekly is plenty for a slowly-drifting
# regulatory-fee schedule, and Sunday keeps it off the trading-day critical path entirely.
# A bounded 30-min/2h self-heal repetition window is added (same remedy this repo already
# shipped for Gamma_EarningsCalendar/Gamma_MacroCalendar after a single-fire trigger
# silently missed a day) -- cheap insurance since the script is idempotent and fast.
#
# WIRING: split-interpreter pattern (system pythonw for the outer wscript relay hop only,
# backtest-venv pythonw for the actual script -- fee_recalibrate.py imports go_live_gate,
# which needs the venv per its own docstring):
#   wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#     -- backtest-venv pythonw -> fee_recalibrate.py
#
# Output: automation/state/fee-calibration.json (this script's own health surface; nothing
# on the trading path reads this file). Guard: backtest/tests/test_fee_recalibrate_2026_09_03.py.
# REVOKE: Unregister-ScheduledTask -TaskName Gamma_FeeRecalibrate -Confirm:$false

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$repo         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $repo "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pywVenv      = Join-Path $repo "backtest\.venv\Scripts\pythonw.exe"
$runCmdHidden = Join-Path $repo "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $repo "setup\scripts\fee_recalibrate.py"
$taskName     = "Gamma_FeeRecalibrate"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

foreach ($p in @($vbs, $sysPythonw, $pywVenv, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$repo`" -- `"$pywVenv`" `"$script`""

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $repo

# Sunday 15:00 MT (= 17:00 ET). -Weekly triggers come back with a null .Repetition CIM
# instance -- steal one from a throwaway -Once trigger built with the repetition params
# (documented PS workaround; direct property assignment on the null instance throws
# PropertyNotFound) -- same technique install-earnings-calendar.ps1 already uses.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "15:00"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "15:00" `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration (New-TimeSpan -Hours 2)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Weekly (Sunday 15:00 MT = 17:00 ET, self-heals every 30 min for 2h on " + `
    "a missed fire): pulls Alpaca FEE activities (OCC/ORF/TAF/REG/CAT) for every active " + `
    "arm over the trailing 14 days, derives the realized rate vs go_live_gate.FEE_RATES " + `
    "(calibrated 2026-08-18), writes automation/state/fee-calibration.json with a " + `
    "GREEN/YELLOW/RED drift status (>10%/>25%). READ-ONLY -- never edits FEE_RATES " + `
    "anywhere; drift is reported, the gate keeps its static dict. `$0. Guard: " + `
    "backtest/tests/test_fee_recalibrate_2026_09_03.py. REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_FeeRecalibrate -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- Sunday 15:00 MT (17:00 ET), self-heals 30min/2h."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
