#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_CboeOiBank scheduled task -- fires 13:55 MT (= 15:55 ET) weekdays.

.DESCRIPTION
  Daily forward-bank of the FREE CBOE delayed-quotes chain (per-strike OI + NATIVE gamma)
  for SPY (+SPX). The N=2 GEX banker, complementary to Gamma_GexCapture (Alpaca, N=1).
  Worker: backtest/tools/cboe_oi_bank.py. Each fire:
    1. GETs https://cdn.cboe.com/api/global/delayed_quotes/options/SPY.json (+ _SPX.json)
       -- free, no auth, ~13.4k/~29.8k contracts each, every contract carrying a NATIVE
       open_interest + gamma (no BS inversion, no OI join -- unlike the Alpaca banker).
    2. Writes journal/gex-archive/{date}-cboe.json -- DISTINCT from the Alpaca banker's
       {date}.json (ADDITIVE, no clobber). This is the second independent OI+gamma history
       that accrues going forward so the one peer-reviewed regime signal in
       backtest/lib/engine/gex_regime.py becomes BACKTESTABLE in ~60-90 days, and so the
       two sources can cross-check the net-GEX sign.

  WHY 13:55 MT (= 15:55 ET): the meaningful GEX snapshot is the END-OF-DAY chain (OI is a
  settled end-of-day figure; the close-of-session gamma map is what the literature reads).
  -At is LOCAL time (Task Scheduler convention); the rig is Mountain, so 13:55 MT = 15:55
  ET. Do NOT relabel the -At value as an ET hour (the project_scheduled_task_tz foot-gun).

  INTERPRETER NOTE: unlike gex_capture.py, this worker imports NO engine package -- the
  CBOE doc carries native gamma+OI, so it has ZERO third-party deps and runs on ANY
  interpreter. We use the backtest venv pythonw for consistency with the sibling banker;
  the system pythonw would work equally. pythonw + the wscript -> run_exe_hidden.vbs chain
  is the canonical L41/L42/C8 zero-leak hidden spawn (no console flash -- the
  dont-disturb-user / project_mcp_window_leak_fix mandate: a bare powershell.exe
  -WindowStyle Hidden action flashes OpenConsole on Win11).

  The job is idempotent (re-run same day overwrites {date}-cboe.json atomically) and
  fail-safe (per-symbol failures logged+skipped; total failure logs + exits 0, never
  crashes the scheduler). Reads no production state; writes only the NEW dated archive.
  Never places orders; never edits params*.json / heartbeat.md / CLAUDE.md. Pure stdlib +
  one free REST pull per symbol. $0 (free CBOE CDN). Data-banking only.

  To enable:  .\setup\install-cboe-oi-bank.ps1
  To verify:  python setup\scripts\audit_scheduled_tasks.py
  To test:    Start-ScheduledTask -TaskName Gamma_CboeOiBank
  To disable: Unregister-ScheduledTask -TaskName Gamma_CboeOiBank
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_CboeOiBank"

# Backtest venv pythonw for consistency with the sibling Gamma_GexCapture banker. (This
# worker has no third-party deps, so the system pythonw would also work -- but mirroring
# keeps the fleet uniform. pythonw keeps the process windowless.)
$pythonw = "C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "backtest venv pythonw not found at $pythonw (create: cd backtest; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt)"
    exit 1
}

$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$worker       = Join-Path $WorkDir "backtest\tools\cboe_oi_bank.py"

foreach ($p in @($runExeHidden, $worker)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript //nologo run_exe_hidden.vbs <venv-pythonw> <cboe_oi_bank.py>  (fully hidden)
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$worker`""

# 13:55 LOCAL (Mountain) = 15:55 ET -- end-of-session chain (settled OI + close gamma map).
# LOCAL time per Task Scheduler convention (project_scheduled_task_tz).
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "13:55"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily free-CBOE OI+native-gamma banker (SPY+SPX): GETs cdn.cboe.com delayed_quotes and archives the chain to journal/gex-archive/{date}-cboe.json (backtestable GEX history, N=2 banker complementary to Gamma_GexCapture). 15:55 ET weekdays (13:55 MT, end-of-session). Idempotent + fail-safe. Pure stdlib, zero deps, $0 (free CDN). Data-banking only -- does NOT trade or edit doctrine."

Write-Output "OK: Registered $TaskName for 15:55 ET weekdays (13:55 MT)"
Write-Output "    Interpreter: $pythonw"
Write-Output "    Worker:      backtest\tools\cboe_oi_bank.py"
Write-Output "    Archive:     journal\gex-archive\{date}-cboe.json   (free-CBOE OI+gamma)"
Write-Output "    Audit:       python setup\scripts\audit_scheduled_tasks.py"
Write-Output "    Test now:    Start-ScheduledTask -TaskName $TaskName"
