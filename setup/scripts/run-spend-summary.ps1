# Spend summary wrapper -- fires every 2h via Gamma_SpendSummary.
# Walks Claude Code session JSONL + MiniMax telemetry, writes spend-{date}.json
# snapshot + spend-daily.jsonl history. Adds STATUS.md WARN above $30/day.
# Threshold lowered from $50 to $30 to catch rate-limit risk earlier.
#
# Per CLAUDE.md OP-3 (cost discipline) + OP-25 engine-benefit autonomy.
. "$PSScriptRoot\_shared.ps1"

$task = "spend-summary"
$et = Get-EtNow

Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('HH:mm:ss'))"

$result = Invoke-PythonHidden `
    -ScriptPath "setup\scripts\spend_summary.py" `
    -ArgList @("--warn-threshold", "30") `
    -TaskName $task `
    -TimeoutSec 120

if ($result.Stdout) {
    Write-TaskLog -TaskName $task -Message "SUMMARY:`n$($result.Stdout)"
}

Write-TaskLog -TaskName $task -Message "END exit=$($result.ExitCode)"
exit $result.ExitCode
