# run-watcher-live.ps1 -- Fire watcher_live.py once per scheduled-task tick (09:30-15:55 ET).
# Called every 5 min by Gamma_WatcherLive via the OP-27 L42 hidden chain.
#
# Per CLAUDE.md OP-27 L41/L42 + 2026-05-23 reset lessons:
#   - Uses Invoke-PythonHidden from _shared.ps1 (Python313 sys exe, NOT venv stub)
#   - PYTHONPATH wired to backtest\.venv\Lib\site-packages so pandas/yfinance/pytz resolve
#   - watcher_live.py inserts its own sys.path for backtest/lib + crypto.lib imports
#   - Zero LLM cost -- pure Python
. "$PSScriptRoot\_shared.ps1"

$task = "watcher-live"
$et = Get-EtNow

# Market hours gate (also enforced inside watcher_live.py, but skip spawn cost outside hours)
if (-not (Test-WeekDay -Et $et)) { exit 0 }
if (-not (Test-MarketHours -Et $et -StartHour 9 -StartMin 30 -EndHour 15 -EndMin 55)) { exit 0 }

Write-TaskLog -TaskName $task -Message "START et=$($et.ToString('HH:mm:ss'))"

$script = Join-Path $WorkDir "backtest\autoresearch\watcher_live.py"
if (-not (Test-Path $script)) {
    Write-TaskLog -TaskName $task -Message "ABORT watcher_live.py not found at $script"
    exit 1
}

$result = Invoke-PythonHidden -ScriptPath $script -TaskName $task -TimeoutSec 90
$exitMsg = "END exit=$($result.ExitCode)"
if ($result.ExitCode -ne 0) { $exitMsg += " WARN non-zero exit" }
Write-TaskLog -TaskName $task -Message $exitMsg

if ($result.Stderr -and $result.Stderr.Trim()) {
    # Log stderr but don't fail the task -- watchers emit T62/T76/T82 diagnostics to stderr by design
    Write-TaskLog -TaskName $task -Message "STDERR: $($result.Stderr.Trim())"
}

exit 0
