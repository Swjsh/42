$ErrorActionPreference = 'Stop'
# Gamma_AutoApply wrapper -- the Actuator's scheduled entrypoint (Phase 1).
# Runs autonomy_actuator.py once: apply every J-approved-unapplied proposal, gated by
# the fast safety suite, snapshot-backed, auto-committed. PURE PYTHON ($0 LLM -- never
# touches the Max rate-limit pool), so cadence/cost are unconstrained. The actuator
# self-gates RTH (Rule 9), and the task window is after-hours anyway (belt + suspenders).
$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$sysPythonW = 'C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe'
if (-not (Test-Path $sysPythonW)) { throw "system pythonw.exe not found at $sysPythonW" }
$exe = $sysPythonW
$env:PYTHONPATH = Join-Path $repoRoot 'backtest\.venv\Lib\site-packages'
$env:VIRTUAL_ENV = Join-Path $repoRoot 'backtest\.venv'
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = "`"$repoRoot\setup\scripts\autonomy_actuator.py`" apply"
$startInfo.WorkingDirectory = $repoRoot
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$proc = [System.Diagnostics.Process]::Start($startInfo)
$proc.WaitForExit(300000) | Out-Null
exit $proc.ExitCode
