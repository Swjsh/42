# Spend summary wrapper -- fires nightly 23:30 ET via Gamma_SpendSummary.
# Walks Claude Code session JSONL + MiniMax telemetry, writes spend-{date}.json
# snapshot + spend-daily.jsonl history.
#
# THRESHOLD (recalibrated 2026-09-03, SPEND-SUMMARY-CHRONIC-RED-ALERT-FATIGUE): the
# hardcoded --warn-threshold 30 below fired a WARN on every single one of 20 real
# sampled days (2026-08-10..2026-09-02, low $43/day, high $2,697/day) -- an alarm
# that never once cleared. --warn-threshold is now OMITTED so spend_summary.py
# auto-derives it every run (75th percentile of the trailing 30 days, floored at
# $50 -- see spend_summary.py's module docstring ALERTING section and
# _derive_warn_threshold), and alerts fire ONLY on a breach-state transition, not
# every fire. Pass --warn-threshold explicitly here only to force a fixed value.
#
# Per CLAUDE.md OP-3 (cost discipline) + OP-25 engine-benefit autonomy.
. "$PSScriptRoot\_shared.ps1"

$task = "spend-summary"
$et = Get-EtNow

Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('HH:mm:ss'))"

$result = Invoke-PythonHidden `
    -ScriptPath "setup\scripts\spend_summary.py" `
    -TaskName $task `
    -TimeoutSec 120

if ($result.Stdout) {
    Write-TaskLog -TaskName $task -Message "SUMMARY:`n$($result.Stdout)"
}

Write-TaskLog -TaskName $task -Message "END exit=$($result.ExitCode)"
exit $result.ExitCode
