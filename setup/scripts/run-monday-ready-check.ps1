$ErrorActionPreference = 'Continue'  # don't fail the task on non-zero exit
$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython = Join-Path $repoRoot 'backtest\.venv\Scripts\python.exe'
$venvPythonW = Join-Path $repoRoot 'backtest\.venv\Scripts\pythonw.exe'
$exe = if (Test-Path $venvPythonW) { $venvPythonW } else { $venvPython }
$workingDir = Join-Path $repoRoot 'backtest'

# Snapshot pre-state
$prevPath = Join-Path $repoRoot 'automation\state\monday-ready.json'
$wasReady = $false
if (Test-Path $prevPath) {
    try {
        $prev = Get-Content $prevPath -Raw | ConvertFrom-Json
        $wasReady = $prev.monday_ready
    } catch {}
}

$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = '-m autoresearch.monday_ready_check'
$startInfo.WorkingDirectory = $workingDir
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$proc = [System.Diagnostics.Process]::Start($startInfo)
$proc.WaitForExit(120000) | Out-Null

# Post-state — if transitioned to ready, ping Discord
if (Test-Path $prevPath) {
    try {
        $now = Get-Content $prevPath -Raw | ConvertFrom-Json
        if ($now.monday_ready -and -not $wasReady) {
            $msg = @{
                queued_at = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ');
                content = "<@207983230618435584> 🟢 **MONDAY READY** — all 6 gates passed. v15-final.json exists, walk-forward OOS net+, all tasks enabled, bridge alive, floors held. Per rule 9, your YES bumps params.json. See docs/MONDAY-READY-CHECKLIST.md."
            } | ConvertTo-Json -Compress
            Add-Content -Path (Join-Path $repoRoot 'automation\state\discord-outbox.jsonl') -Value $msg -Encoding UTF8
        }
    } catch {}
}
exit 0
