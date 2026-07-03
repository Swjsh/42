$ErrorActionPreference = 'Stop'
# ===== ARM SWITCH (2026-06-25) =====
# ARMED after the replay arm-gate PASSED: score parity 98.0% (>=95%) + entry fidelity 5/5
# matched / 0 extra / 0 missed (quality-lock ported) + 133 engine tests green, all independently
# re-verified. The child inherits this env var (UseShellExecute=false). J's REVOKE = set to '0'
# (or disable the Gamma_HeartbeatCore task); the permanent gate in backtest/replay_heartbeat_core.py
# fails loud (exit 1) if fidelity ever regresses.
$env:GAMMA_CORE_ARMED = '1'
# Exits APPLIED 2026-06-26 (J: "no trading without exits/scale-outs"): turn on the validated
# partial-TP1 + runner + profit-lock exit_manager on the brain path (was basic bracket only).
# 106 fleet tests green, exit-shape validated, no-crash verified. REVOKE = set to '0'.
$env:GAMMA_CORE_MANAGES_EXITS = '1'
# Gamma_HeartbeatCore wrapper -- the DETERMINISTIC trade engine (replaces the LLM heartbeat).
# Pure Python: reads SPY bars via REST, runs the tested score_bar + 15 gates (engine_cli),
# 2 free models veto-check entries, places brackets via REST. NO LLM / MCP / CDP on the hot
# path, NO Max-pool burn. Hidden process. Runs every 2 min during RTH.
$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
# L41 (2026-05-17 lesson, LESSONS-LEARNED.md): the VENV's OWN pythonw.exe/python.exe is a
# stub that re-execs into the system interpreter via a hardcoded CREATE_NEW_CONSOLE,
# ignoring whatever CreateNoWindow the caller set -- always launch the SYSTEM interpreter
# with PYTHONPATH/VIRTUAL_ENV pointed at the venv instead (same pattern as _shared.ps1's
# Invoke-PythonHidden). Root-caused 2026-07-03: this exact violation flashed a visible
# WindowsTerminal window every ~1 min, all day, market hours -- J's "cmd popups".
$sysPythonW = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$venvSite = Join-Path $repoRoot 'backtest\.venv\Lib\site-packages'
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $sysPythonW
$startInfo.Arguments = "`"$repoRoot\setup\scripts\heartbeat_core.py`""
$startInfo.WorkingDirectory = $repoRoot
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
if (Test-Path $venvSite) {
    $startInfo.EnvironmentVariables["PYTHONPATH"] = $venvSite
    $startInfo.EnvironmentVariables["VIRTUAL_ENV"] = (Join-Path $repoRoot 'backtest\.venv')
}
$proc = [System.Diagnostics.Process]::Start($startInfo)
$proc.WaitForExit(90000) | Out-Null
exit $proc.ExitCode
