#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_SsrShadow -- the SSR-v1 PULSE forward own-book shadow ledger
  (backtest/futures/analysis/SSR-battery/DESIGN.md ADDENDUM verdict rules: no v1 cell cleared
  the full BH-FDR ladder, but 3 A-family + 2 B-family cells hit the PULSE tier -- the
  sanctioned next step is a forward shadow, not another historical grind on sanity-tier
  yfinance data).

  PURPOSE: every 15 minutes 03:00-17:15 ET weekdays, ssr_shadow.py fetches fresh NQ=F (15m)
  and GC=F (1h) bars, drops the in-progress bar, rebuilds levels + the SSR detector fresh,
  and considers only SHORT signals newer than each config's own watermark and within the
  last 3 completed bars. A qualifying signal opens a synthetic position (entry = signal bar's
  own close +/- 1 tick, qty 3, TP1 at 1.5R for 2/3, stop to breakeven, runner = nearest
  opposing level beyond TP1 else 3R capped at 5R, forced flat 16:55 ET). Every lifecycle event
  is appended to automation/state/futures/ssr-shadow-would-be.jsonl. It places NO real order,
  touches NO broker, and never trades -- read-only against yfinance, otherwise entirely
  self-contained under automation/state/futures/ssr-shadow-*.

  WIRING PATTERN (flash-free, matches install-futures-mirror.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo> --
      backtest\.venv\Scripts\pythonw.exe ssr_shadow.py --once
  Runs on the BACKTEST venv (not system Python) because ssr_shadow.py imports pandas +
  yfinance + backtest.futures.ssr.* / backtest.futures.swing_sim / crypto.lib.*, none of
  which are installed under system Python (same interpreter choice as Gamma_FuturesMirror /
  Gamma_SwingCore -- see SCHEDULED-TASKS.md).

  TZ RULE: this rig is Mountain Time (ET = local + 2h). 03:00 ET -> 01:00 MT,
  17:15 ET -> 15:15 MT. NEVER pass an ET literal to -At. A REPEATING trigger (Once + 15-min
  RepetitionInterval + RepetitionDuration spanning the window), never a one-shot TimeTrigger
  (which would go dark the next day -- project_scheduled_task_onetime_trigger_dark).

  To verify after running: Get-ScheduledTask -TaskName Gamma_SsrShadow | Get-ScheduledTaskInfo
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_SsrShadow" -Confirm:$false

  NOTE: this installer does NOT run itself when invoked by the builder session -- registration
  is the verifier's job (per task instructions, "DO NOT RUN the installer").
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv  = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script       = Join-Path $root "setup\scripts\ssr_shadow.py"
$etz          = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$taskName     = "Gamma_SsrShadow"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath   = Join-Path $root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"

foreach ($p in @($vbs, $pythonwVenv, $script, $sysPythonw, $runCmdHidden)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

function Show-NextET {
    param([string]$Name)
    $info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction SilentlyContinue
    if ($info -and $info.NextRunTime) {
        $et = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
        Write-Host ("  NextRun ET: {0}" -f $et.ToString("yyyy-MM-dd HH:mm"))
    } else {
        Write-Host "  NextRun ET: (none / on-demand)"
    }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- backtest venv pythonw -> ssr_shadow.py --once
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`" --once"

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 01:00 MT = 03:00 ET start; repeat every 15 min for 14h15m -> covers 03:00-17:15 ET.
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "01:00"
$rep = (New-ScheduledTaskTrigger -Once -At "01:00" `
        -RepetitionInterval (New-TimeSpan -Minutes 15) `
        -RepetitionDuration (New-TimeSpan -Hours 14 -Minutes 15)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 8) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description ("SSR-v1 PULSE forward own-book shadow ledger. Every 15 min, 03:00-17:15 ET " + `
    "weekdays. ssr_shadow.py --once: fetches NQ=F 15m (period 8d) and GC=F 1h (period 60d), " + `
    "drops the in-progress bar, rebuilds levels + the SSR sweep->shift->retest detector " + `
    "fresh (zone_atr_mult=0.5, sweep_atr_mult=0.1, h4_anchor=2000, include_running=True), " + `
    "SHORT-only, opens a synthetic shadow trade off signals newer than a per-config " + `
    "watermark and within the last 3 completed bars (qty 3, TP1=1.5R for 2/3, stop to " + `
    "breakeven, runner = nearest opposing level beyond TP1 else 3R capped 5R, forced flat " + `
    "16:55 ET), logs every lifecycle event to " + `
    "automation/state/futures/ssr-shadow-would-be.jsonl. Places NOTHING real, no broker, no " + `
    "creds. Fail-open (exits 0 always, logs to automation/state/logs/ssr-shadow-*.log). " + `
    "Arming bar (computed every poll, armed by nobody automatically): >=20 closed round " + `
    "trips, positive expectancy, beats a same-direction unmanaged-hold null.") `
    -Force | Out-Null

Write-Host "Registered $taskName (01:00 MT = 03:00 ET start, every 15 min for 14h15m, Mon-Fri)"
Show-NextET $taskName
Write-Host ""
Write-Host "SSR shadow wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_SsrShadow | Get-ScheduledTaskInfo"
