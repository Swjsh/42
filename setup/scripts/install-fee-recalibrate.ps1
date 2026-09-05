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
# WIRING (2026-09-03 CHANGED -- trial subject for VENV-PYTHONW-REDIRECTS-TO-CONSOLE-PYTHON,
# queue.md, recipe (a), status:recipe-proven): the ENTIRE chain now runs the BASE install's
# pythonw.exe (system pythonw), never backtest\.venv\Scripts\pythonw.exe. Root cause
# (PANDAS-CONSOLE-LEAK-ROOT-CAUSE, closed 2026-09-03): backtest\.venv\Scripts\pythonw.exe
# is CPython's venvwlauncher redirector, but backtest\.venv\pyvenv.cfg records only
# `executable=...\python.exe` (no GUI-variant path) -- EVERY venv pythonw launch re-execs
# the base install's CONSOLE python.exe internally, which spawns a console-host window
# (conhost.exe / WindowsTerminal.exe -Embedding) per fire, and CREATE_NO_WINDOW passed to
# the OUTER launch does NOT survive that internal re-exec (live-verified 2026-09-03: WMI
# process-tree showed a python.exe + conhost.exe descendant pair even with the outer
# subprocess.Popen call passing creationflags=CREATE_NO_WINDOW; the base install's own
# pythonw.exe launched identically produced zero console-relevant descendants).
# Fix: launch the BASE pythonw.exe directly and activate the venv via environment instead
# of via the venv's own launcher stub -- VIRTUAL_ENV + PYTHONPATH=<venv>\Lib\site-packages,
# injected through run_cmd_hidden.py's existing --env flag. PATH is deliberately NOT
# touched: fee_recalibrate.py's only go_live_gate usage is module-level constants
# (TRADES_ENRICHED, SECRETS_PATH, ACTIVE_ARMS) -- it never calls go_live_gate._run_pytest
# or spawns BACKTEST_PY, so no PATH-relative interpreter lookup is in this script's path.
# Verified live 2026-09-03 (both the manual recipe AND the registered task via
# Start-ScheduledTask): `python.__file__`/`pandas.__file__` resolve into
# backtest\.venv\Lib\site-packages (not the base install, which has no pandas installed at
# all -- ModuleNotFoundError confirmed, ruling out ambiguous resolution), zero
# console-host descendants observed via live Win32_Process inspection, rc=0,
# fee-calibration.json mtime advanced with a correct roster.
#   wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#     --env VIRTUAL_ENV=<venv> --env PYTHONPATH=<venv>\Lib\site-packages
#     -- system pythonw -> fee_recalibrate.py
#
# NOT rolled to any other install script tonight (queue item explicitly scopes the trial
# to this ONE non-trading task; a repo-wide roll is a separate future pass with the leak
# detector as the oracle). Pinned by
# backtest/tests/test_venv_launch_recipe_2026_09_03.py.
#
# Output: automation/state/fee-calibration.json (this script's own health surface; nothing
# on the trading path reads this file). Guard: backtest/tests/test_fee_recalibrate_2026_09_03.py.
# REVOKE: Unregister-ScheduledTask -TaskName Gamma_FeeRecalibrate -Confirm:$false

[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$repo         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $repo "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$venvDir      = Join-Path $repo "backtest\.venv"
$venvSitePkgs = Join-Path $repo "backtest\.venv\Lib\site-packages"
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

foreach ($p in @($vbs, $sysPythonw, $venvSitePkgs, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# 2026-09-03: inner target changed from $pywVenv to $sysPythonw (base install pythonw),
# venv activated via --env instead -- see WIRING comment above (VENV-PYTHONW-REDIRECTS-
# TO-CONSOLE-PYTHON recipe (a) trial). PATH is intentionally not injected -- see comment.
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$repo`" " + `
    "--env VIRTUAL_ENV=`"$venvDir`" --env PYTHONPATH=`"$venvSitePkgs`" -- `"$sysPythonw`" `"$script`""

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
