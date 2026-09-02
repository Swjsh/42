#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_RuleBreakAudit -- deterministic post-hoc audit of the SPY arms against J's
  10 rules. Fires daily 16:40 ET (14:40 MT local -- this box is Mountain, ET=local+2h), after
  the day's decisions are written and after Gamma_RefusedSetupLedger (16:20) and
  Gamma_FirstLiveDayReview (16:30).

.DESCRIPTION
  THE GAP THIS CLOSES: `automation/state/rule-breaks.jsonl` is what the go-live gate's
  BEHAVIOURAL criterion (criterion 4) counts. It holds exactly ONE row, dated 2026-05-18.
  Its only writers were ever LLM prompt instructions (`eod-summary.md`,
  `eod-workers/02-predictions-and-audit.md`, `weekly-review.md`) and the LLM EOD workers were
  retired -- so NO code path has ever written a rule break. `analysis/weekly/2026-W30.md` put
  it plainly months ago: with that ledger dead and `followed_rules` always blank, "there is
  currently no mechanism anywhere that flags a Rule 1-10 violation on a real trade." The
  2026-09-01 audit said "writer restoration queued"; no queue item was ever filed.

  `setup/scripts/rule_break_audit.py` is that writer. Ported from the pattern already working
  on the futures side (`futures_eod.py::rule_audit`): a post-hoc check run INDEPENDENTLY of
  the pre-trade gate, because checking only at entry time cannot catch a gate that was
  bypassed or mis-wired. Process over P&L -- a winning trade that broke a rule is a break.

  HONESTY BY CONSTRUCTION. This exists because an instrument that could not tell "clean" from
  "dead" reported clean for four months, so it must not repeat that:
    * Checks the mechanically-verifiable SUBSET (rules 1,2,3,4,5,6) and NAMES the ones it
      cannot check (7 PDT, 8 journal-join, 9 params history, 10 not mechanical).
    * A rule whose inputs are absent is reported NOT_CHECKED, never a pass.
    * Reports BINDING EVIDENCE: a zero from a rule tested at 99% of its limit and a zero from
      a rule that never had an opportunity to fire are the same number and completely
      different claims. First run: RULE_6 max 0.99 of cap (informative -- the cap was
      approached and respected); RULE_5 kill switch never tripped (uninformative).

  Writes ONLY real breaks to `rule-breaks.jsonl`, idempotently -- the gate counts every
  parseable row with an in-window `date` as a break, so a heartbeat row written there would
  spuriously FAIL criterion 4. Coverage goes to `automation/state/rule-break-audit.json`.

  DELIBERATELY NOT DONE HERE: teaching `go_live_gate.py` criterion 4 to read the coverage
  artifact so an audited-and-clean window reads PASS instead of PASS_UNVERIFIED. That changes
  how a go-live criterion is MEASURED, mid-window, and a measurement change without a
  pre-registration is the post-hoc-bar-change anti-pattern this project bans (OP-11). Filed
  as its own queue item.

  Never places, arms, cancels, or edits params -- report only.

  WIRING PATTERN (flash-free, cloned from install-prereg-hygiene.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> rule_break_audit.py

  Output:
    automation/state/rule-breaks.jsonl       -- real breaks only (gate reads this)
    automation/state/rule-break-audit.json   -- coverage/heartbeat + binding evidence
    automation/state/logs/run-cmd-hidden-<date>.log -- the real exit code, dated

  To verify: Get-ScheduledTask -TaskName Gamma_RuleBreakAudit | Get-ScheduledTaskInfo
  To test now: Start-ScheduledTask -TaskName Gamma_RuleBreakAudit
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_RuleBreakAudit" -Confirm:$false

  Guard: backtest/tests/test_rule_break_audit_2026_09_02.py (29 -- every detector proven to
  fire on a synthetic violation; a detector that has never fired is not evidence).
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\rule_break_audit.py"
$taskName     = "Gamma_RuleBreakAudit"

foreach ($p in @($vbs, $sysPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# Daily 14:40 LOCAL (Mountain) = 16:40 ET.
$trigger = New-ScheduledTaskTrigger -Daily -At "14:40"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Deterministic post-hoc audit of the SPY arms against J's 10 rules " + `
    "(2026-09-02). Writes the rule-breaks.jsonl ledger that go_live_gate criterion 4 counts " + `
    "and that NO code path had ever written -- its only writers were retired LLM prompts. " + `
    "Checks the mechanically-verifiable subset (rules 1-6), NAMES the rules it cannot check, " + `
    "reports NOT_CHECKED rather than a pass when inputs are absent, and reports binding " + `
    "evidence so an uninformative zero cannot read as compliance. Report only -- never " + `
    "places, arms or edits params. Daily 14:40 MT (16:40 ET). Pure stdlib Python, `$0. " + `
    "Guard: backtest/tests/test_rule_break_audit_2026_09_02.py") `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Output "OK: Registered $taskName for daily 14:40 MT (16:40 ET)"
Write-Output "    Breaks:   automation\state\rule-breaks.jsonl (real breaks only)"
Write-Output "    Coverage: automation\state\rule-break-audit.json"
Write-Output "    Test now: Start-ScheduledTask -TaskName $taskName"
Write-Output "    Next run: $($info.NextRunTime)"
