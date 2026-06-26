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
$venvPython  = Join-Path $repoRoot 'backtest\.venv\Scripts\python.exe'
$venvPythonW = Join-Path $repoRoot 'backtest\.venv\Scripts\pythonw.exe'
$exe = if (Test-Path $venvPythonW) { $venvPythonW } else { $venvPython }
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = "`"$repoRoot\setup\scripts\heartbeat_core.py`""
$startInfo.WorkingDirectory = $repoRoot
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$proc = [System.Diagnostics.Process]::Start($startInfo)
$proc.WaitForExit(90000) | Out-Null
exit $proc.ExitCode
