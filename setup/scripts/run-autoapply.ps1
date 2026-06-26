$ErrorActionPreference = 'Stop'
# Gamma_AutoApply wrapper -- the Actuator's scheduled entrypoint (Phase 1).
# Runs autonomy_actuator.py once: apply every J-approved-unapplied proposal, gated by
# the fast safety suite, snapshot-backed, auto-committed. PURE PYTHON ($0 LLM -- never
# touches the Max rate-limit pool), so cadence/cost are unconstrained. The actuator
# self-gates RTH (Rule 9), and the task window is after-hours anyway (belt + suspenders).
$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython  = Join-Path $repoRoot 'backtest\.venv\Scripts\python.exe'
$venvPythonW = Join-Path $repoRoot 'backtest\.venv\Scripts\pythonw.exe'
$exe = if (Test-Path $venvPythonW) { $venvPythonW } else { $venvPython }
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
