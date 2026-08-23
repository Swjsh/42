# install-multi-evaluate.ps1 -- register Gamma_MultiEvaluate, the per-ticker evaluation surface.
#
# WHAT THIS IS. J asked for "a complex evaluation system for each ticker and its prospective
# trade". multi/evaluate.py is that system; this registers it so the cards exist without anyone
# asking for them -- a premarket run plus one every 30 minutes through the session.
#
# WHAT THIS IS NOT. It is NOT an execution task and it cannot become one by configuration.
# multi/evaluate.py contains no order-placement call at all, guarded structurally by
# backtest/tests/test_multi_evaluate.py::test_evaluate_contains_no_order_placement_call, which
# parses the AST rather than grepping and is RED-proofed (inserting a place_bracket call fails
# it). The multi-symbol lane is STOPPED on a null verdict; nothing here changes that, and the
# evaluation cards print the STOPPED state on every run so a reader cannot mistake an
# evaluation for an authorization.
#
# WHY 30 MINUTES. Cost and honesty both point the same way. Each run is 3 batch bar calls plus
# a chain+quote for the top names -- roughly 19 API calls, about 250/day against a 200/MINUTE
# limit, and $0 in model spend because there is no LLM anywhere in this path. A tighter cadence
# would add API load without adding information: the zone map is a multi-bar object and the
# blocker set does not meaningfully change between five-minute bars.
#
# DailyTrigger with repetition, NOT a one-time trigger
# (scar: project_scheduled_task_onetime_trigger_dark -- a one-time trigger goes dark after it fires).

$ErrorActionPreference = "Stop"
$Root = "C:\Users\jackw\Desktop\42"; $ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName = "Gamma_MultiEvaluate"
$pythonw = Join-Path $Root "backtest\.venv\Scripts\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"
$worker = Join-Path $Root "multi\evaluate.py"
foreach ($p in @($pythonw, $runExeHidden, $sysPythonw, $runCmdHidden, $worker)) {
  if (-not (Test-Path $p)) { Write-Error "missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# -m multi.evaluate (not the bare path) so the package-relative imports resolve the same way
# they do when it is run by hand -- the form that was actually tested.
#
# --log IS NOT OPTIONAL. run_cmd_hidden.py discards the child's stdout when no log is given, and
# the outer wscript hop swallows the exit code, so a failed run reports LastTaskResult=0 with no
# output anywhere -- indistinguishable from a successful one. That is this shop's single most
# repeated failure class (C7: silent success is failure), and it bit this very task on its first
# manual fire: result 0, artifact never written, nothing to read. The log is the only thing that
# makes a bad run visible.
$logDir = Join-Path $Root "automation\state\multi"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
$logFile = Join-Path $logDir "evaluate-last-run.log"
$action = New-ScheduledTaskAction -Execute "wscript.exe" `
  -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --log `"$logFile`" --cwd `"$Root`" -- `"$pythonw`" -m multi.evaluate --top 8"

# ============================================================================================
# TIMES BELOW ARE **LOCAL (MOUNTAIN)**, NOT ET.  ET = local + 2.
# Task Scheduler triggers fire on LOCAL wall-clock. This box runs Mountain time, so 09:00 ET is
# 07:00 local -- verified against the known-correct Gamma_HeartbeatCore, whose StartBoundary is
# 07:30-06:00 for its documented 09:30 ET start. Registering "09:00" here would have fired the
# premarket card at 11:00 ET, ninety minutes AFTER the open, which is the whole point missed.
# Do not "correct" these to ET values. Verify with setup/scripts/et_clock.py, never by assuming.
# ============================================================================================
# 07:00 local = 09:00 ET premarket card, then every 30 min through 13:30 local = 15:30 ET. The
# premarket run is the important one: the read J can act on before the session, with the
# overnight zone map already built.
# WEEKDAYS ONLY. A Saturday fire evaluates stale Friday bars and produces a card that can
# never be stamped with an outcome (no forward bars exist), so it is pure API burn: 216 junk
# cards and ~860 wasted calls accumulated over one weekend before this was caught.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "07:00"
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At "07:00" `
  -RepetitionInterval (New-TimeSpan -Minutes 30) `
  -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 30)).Repetition

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
  -MultipleInstances IgnoreNew

$desc = "PER-TICKER EVALUATION SURFACE (LANE multi-symbol, acct PA38EG1JTFBT). For every name: " + `
  "the tiered ZONE MAP (supply/demand shelves, pivots, PDH/PDL/PDC, premarket + intraday extremes) " + `
  "with distance in percent AND ATR, market structure (HH/HL/BOS/CHoCH), relative volume, VIX " + `
  "regime, the per-side score with NAMED triggers and NAMED blocking filters, and -- for the top " + `
  "names -- the concrete prospective trade (contract, strike, expiry, premium, spread, size, " + `
  "dollar risk, catastrophe cap). Every field is a real measurement or an explicit UNAVAILABLE " + `
  "with a reason; nothing defaults to a plausible number. READ-ONLY: no order path exists in " + `
  "multi/evaluate.py (AST-guarded, RED-proofed). The lane is STOPPED on a null verdict and each " + `
  "run prints that state -- these are EVALUATIONS, not authorizations. " + `
  "Writes analysis/multi-lane/evaluations/evaluation-<date>.json. Cost: ~250 API calls/day, `$0 model spend."

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings -Description $desc | Out-Null

# VERIFY -- registering is not running, and a task that exists but is disabled or mis-triggered
# is the silent-failure class this shop keeps re-learning (C7). Assert the real state back.
$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $t) { Write-Error "VERIFY FAILED: $TaskName did not register"; exit 1 }
$info = Get-ScheduledTaskInfo -TaskName $TaskName
$rep = $t.Triggers[0].Repetition
Write-Host "registered : $($t.TaskName)"
Write-Host "state      : $($t.State)"
Write-Host "repetition : every $($rep.Interval) for $($rep.Duration)"
Write-Host "next run   : $($info.NextRunTime)"
if ($t.State -eq "Disabled") { Write-Error "VERIFY FAILED: registered but Disabled"; exit 1 }
if (-not $rep.Interval) { Write-Error "VERIFY FAILED: no repetition -- would fire once and go dark"; exit 1 }

# Prove the ET mapping instead of asserting it in a comment. NextRunTime is LOCAL; the premarket
# card must land at 09:00 ET, so local must read 07:00.
$nextLocal = $info.NextRunTime
if ($nextLocal) {
  $etOffset = 2   # Mountain -> Eastern; both observe DST so the gap is stable year-round
  $nextEt = $nextLocal.AddHours($etOffset)
  Write-Host "next run ET: $nextEt  (local + $etOffset h)"
  if ($nextLocal.Hour -ne 7 -and $nextLocal.Hour -ne 13) {
    Write-Error "VERIFY FAILED: next local hour $($nextLocal.Hour) is not 07 -- ET mapping wrong"; exit 1
  }
}
Write-Host "OK"
