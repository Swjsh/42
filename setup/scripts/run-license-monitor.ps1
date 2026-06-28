# License-monitor wrapper -- fires nightly at 22:30 ET via Gamma_LicenseMonitor.
# Refreshes recency verdicts (reads cached OPRA) and pings J via Discord on
# RED->green transitions. Pure $0 monitor -- no live orders, no Claude invocation.
# See backtest/autoresearch/license_monitor.py for the full logic.
#
# Launched via: wscript -> run_exe_hidden.vbs -> pythonw -> run_ps1_hidden.py -> THIS.
# Uses the backtest .venv Python (has pandas/recency_check dependencies).
param()
$ErrorActionPreference = "Continue"

. "$PSScriptRoot\_shared.ps1"

$task    = "license-monitor"
$et      = Get-EtNow
Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('HH:mm:ss'))"

$python  = "C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe"
$workdir = "C:\Users\jackw\Desktop\42\backtest"

if (-not (Test-Path $python)) {
    Write-TaskLog -TaskName $task -Message "ERROR: backtest venv python not found at $python"
    exit 1
}

$env:PYTHONPATH = $workdir
Set-Location $workdir

# --run: re-invokes recency_check.py to refresh verdicts from the latest OPRA cache ($0)
# --announce-baseline: emits a one-time "armed" Discord ping on the very first run
$stdout = & $python -m autoresearch.license_monitor --run --announce-baseline 2>&1 | Out-String
$exit   = $LASTEXITCODE

Write-TaskLog -TaskName $task -Message "OUTPUT:`n$stdout"
Write-TaskLog -TaskName $task -Message "END exit=$exit"
exit $exit
