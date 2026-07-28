# run-entry-block-watch.ps1 -- Fire entry_block_watch.py once per scheduled-task tick
# (09:30-16:00 ET, every 2 min). Called by Gamma_EntryBlockWatch.
#
# WHY: the escalation cord (WS4, 2026-07-27 night build) -- tells J the MOMENT the
# engine sees a high-quality, level-tied setup and doesn't take it, instead of hours
# later. Pure stdlib Python, $0/tick, no LLM anywhere in the detection path.
. "$PSScriptRoot\_shared.ps1"

$task = "entry-block-watch"
$et = Get-EtNow

# Market hours gate (also harmless if skipped -- the script itself is a pure no-op
# outside trading hours since core-decisions.jsonl only grows during RTH -- but this
# avoids the spawn cost).
if (-not (Test-WeekDay -Et $et)) { exit 0 }
if (-not (Test-MarketHours -Et $et -StartHour 9 -StartMin 30 -EndHour 16 -EndMin 0)) { exit 0 }

$script = Join-Path $WorkDir "setup\scripts\entry_block_watch.py"
if (-not (Test-Path $script)) {
    Write-TaskLog -TaskName $task -Message "ABORT entry_block_watch.py not found at $script"
    exit 1
}

$result = Invoke-PythonHidden -ScriptPath $script -TaskName $task -TimeoutSec 60
$exitMsg = "END exit=$($result.ExitCode)"
if ($result.ExitCode -ne 0) { $exitMsg += " WARN non-zero exit" }
Write-TaskLog -TaskName $task -Message $exitMsg

if ($result.Stdout -and $result.Stdout.Trim()) {
    Write-TaskLog -TaskName $task -Message "STDOUT: $($result.Stdout.Trim())"
}
if ($result.Stderr -and $result.Stderr.Trim()) {
    Write-TaskLog -TaskName $task -Message "STDERR: $($result.Stderr.Trim())"
}

exit 0
