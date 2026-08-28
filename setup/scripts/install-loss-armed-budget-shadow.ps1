#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_LossArmedBudgetShadow -- the forward counter that ADJUDICATES
  analysis/recommendations/loss-armed-budget-forward-prereg-2026-08-28.json.

  PURPOSE: the pre-registration froze three per-arm session PREMIUM BUDGETS
  (B-500 / B-700 / B-1000) armed by "this arm is already red today", plus the
  H-TIER observation, and promised a 15-session forward window. This task is the
  thing that keeps that promise, so the pre-reg cannot sit as prose that never
  gets judged (C35 / L221 -- built != shipped until it lands on a surface that
  actually fires).

  Sibling of Gamma_DayThrottleShadow (16:35 ET), which adjudicates the HARD-STOP
  form of the same family. This one fires 5 minutes later so the two never race
  on journal/trades.csv, and so their ledgers are written from the same tape.

  SHADOW ONLY. loss_armed_budget_shadow.py recomputes would_block per entry AFTER
  the close from journal/trades.csv; it places no order, touches no broker, and
  the live gate it measures (risk_gate.check_daily_premium_budget) is INERT --
  params.daily_premium_budget_dollars is absent from every params file. A crash
  in this counter can never touch a trade.

  WIRING PATTERN (flash-free, mirrors Gamma_DayThrottleShadow exactly):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_py_venv_hidden.py
      -> setup\scripts\loss_armed_budget_shadow.py
  System Python is correct here: the script is stdlib + et_clock only (it imports
  its shared helpers from day_throttle_shadow, which runs on the same interpreter).

  TZ RULE: this rig runs Mountain Time (ET = local + 2h). 16:40 ET -> 14:40 MT.
  NEVER pass an ET literal to -At.

  SILENT-SKIP SELF-HEAL: a bare single daily trigger has silently skipped a day on
  three separate producers in this repo (Gamma_MacroCalendar, Gamma_EarningsCalendar,
  Gamma_FuturesEod2 -- see SINGLE-FIRE-TRIGGER-BLANKET-AUDIT in queue.md). A 15-min
  repetition over a 30-min window is the fix that was applied to all three; applied
  here from day one rather than waiting to be bitten. The script is idempotent --
  it rewrites the ledger and summary from scratch each run -- so repeat fires
  inside the window are harmless.

  VERIFY: Get-ScheduledTask -TaskName Gamma_LossArmedBudgetShadow | Get-ScheduledTaskInfo
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_LossArmedBudgetShadow" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$root       = "C:\Users\jackw\Desktop\42"
$vbs        = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runVenv    = Join-Path $root "setup\scripts\run_py_venv_hidden.py"
$script     = Join-Path $root "setup\scripts\loss_armed_budget_shadow.py"
$prereg     = Join-Path $root "analysis\recommendations\loss-armed-budget-forward-prereg-2026-08-28.json"
$taskName   = "Gamma_LossArmedBudgetShadow"
$etz        = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')

foreach ($p in @($vbs, $sysPythonw, $runVenv, $script, $prereg)) {
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

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runVenv`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 14:40 MT = 16:40 ET, daily. Repetition window guards the silent-skip class.
$trigger = New-ScheduledTaskTrigger -Daily -At "14:40"
$rep = (New-ScheduledTaskTrigger -Once -At "14:40" `
        -RepetitionInterval (New-TimeSpan -Minutes 15) `
        -RepetitionDuration (New-TimeSpan -Minutes 30)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description ("Forward counter for the LOSS-ARMED session premium budget pre-registration " + `
    "(analysis/recommendations/loss-armed-budget-forward-prereg-2026-08-28.json). Daily 14:40 MT " + `
    "= 16:40 ET, 15-min repetition over 30 min to survive a missed fire. Recomputes would_block " + `
    "per ENTRY after the close from journal/trades.csv for three frozen caps (B-500/B-700/B-1000) " + `
    "armed by 'this arm's realized session P&L is below zero, counting only already-EXITED " + `
    "trades' -- the no-look-ahead rule is the whole validity of it. An unreadable premium " + `
    "ABSTAINS (None) rather than defaulting to not-blocked. Writes " + `
    "loss-armed-budget-shadow-ledger.jsonl + -summary.json; the forward block is the only " + `
    "adjudicator and in-sample is emitted under the key in_sample_NOT_EVIDENCE. F5 band-coherence " + `
    "is the gate that tests whether the in-sample-argmax B-700 is a curve-fit. SHADOW ONLY -- " + `
    "refuses nothing live; the gate it measures (risk_gate.check_daily_premium_budget) is INERT. " + `
    "Guard: backtest/tests/test_loss_armed_budget_shadow.py (19/19, RED-proofed on 5 conventions).") `
    -Force | Out-Null

Write-Host "Registered $taskName (14:40 MT = 16:40 ET daily, +15min repetition over 30min)"
Show-NextET $taskName
Write-Host ""
Write-Host "Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_LossArmedBudgetShadow | Get-ScheduledTaskInfo"
