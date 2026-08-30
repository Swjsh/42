# Autofire Cards evening runner -- fires the safe (read-and-report) subset of
# cockpit action cards unattended, so results are waiting for J instead of
# waiting for a tap. J, 2026-08-29: "Auto-fire the safe cards... I would only
# click the ones with consequences."
#
# This is the DEDICATED evening task named in gamma_watcher.py's own install
# comment ("the autofire runner has its own evening task with its own
# guards") -- separate from Gamma_Watcher's 24/7 observe-only 15-min tick.
#
# All real safety logic lives in autofire_cards.py itself (RTH refusal via
# et_clock, companion-halt.flag, quiet-mode.json, per-run/per-day caps
# ledgered across restarts) -- this wrapper is deliberately thin. The
# Test-WeekDay guard here is belt-and-suspenders scheduling hygiene, not the
# enforcement point.
. "$PSScriptRoot\_shared.ps1"

$task = "autofire-cards"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) {
    Write-TaskLog -TaskName $task -Message "SKIP weekend et=$($et.ToString('yyyy-MM-dd HH:mm:ss'))"
    exit 0
}

$scriptPath = Join-Path $WorkDir "setup\scripts\autofire_cards.py"

Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('yyyy-MM-dd HH:mm:ss'))"

$res = Invoke-PythonHidden -ScriptPath $scriptPath `
    -ArgList @("--live") `
    -TaskName $task `
    -TimeoutSec 300

if ($res.ExitCode -eq 0) {
    Write-TaskLog -TaskName $task -Message "OK ledger=automation/state/autofire-ledger.jsonl"
    Write-TaskLog -TaskName $task -Message "STDOUT: $($res.Stdout | Select-Object -Last 5 | Out-String)"
} else {
    Write-TaskLog -TaskName $task -Message "ERROR exit=$($res.ExitCode)"
    Write-TaskLog -TaskName $task -Message "STDERR: $($res.Stderr | Select-Object -First 5 | Out-String)"
}
