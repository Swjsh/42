$ErrorActionPreference = 'Stop'
# ===== Gamma_KalshiTick -- the Kalshi lane tick (SHADOW BY DEFAULT) =====
#
# Ports the SPY 0DTE directional decision from shared-signal.json onto a Kalshi
# S&P index contract. Pure Python + public REST. No LLM, no MCP, no Max-pool burn.
#
# ############################################################################
# ##  ARM SWITCH -- DELIBERATELY NOT SET.                                    ##
# ##  This lane runs in SHADOW: it decides, logs, and places NOTHING.        ##
# ##  To go LIVE (real money on J's Kalshi account) uncomment the next line. ##
# ##  REVOKE = comment it out again, or disable the scheduled task.          ##
# ##  Live ALSO requires credentials in the gitignored secrets store --      ##
# ##  the flag alone cannot place an order.                                  ##
# ############################################################################
# $env:GAMMA_KALSHI_ARMED = '1'

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))

# L41 / C8: the venv's OWN python.exe is a stub that re-execs into the system
# interpreter with a hardcoded CREATE_NEW_CONSOLE, ignoring CreateNoWindow and
# flashing a console window every fire. Always launch the SYSTEM interpreter with
# PYTHONPATH pointed at the venv's site-packages instead.
#
# 2026-08-09: `cryptography` (required for Kalshi's RSA-PSS request signing) was
# MISSING from this venv and had to be installed. It is not in the base Programs
# Python either -- only in the Store Python, which this pattern does not use.
# If signing ever starts failing, check that import FIRST.
$sysPythonW = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$venvSite   = Join-Path $repoRoot 'backtest\.venv\Lib\site-packages'
$script     = Join-Path $repoRoot 'automation\kalshi\kalshi_tick.py'
$logDir     = Join-Path $repoRoot 'automation\state\kalshi'
$log        = Join-Path $logDir 'tick.log'

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
if (-not (Test-Path $sysPythonW)) { throw "system pythonw missing: $sysPythonW" }
if (-not (Test-Path $script))     { throw "tick script missing: $script" }

$env:PYTHONPATH = $venvSite
$env:PYTHONIOENCODING = 'utf-8'

# Hidden, no console window (C8). Capture both streams -- a silent scheduled task
# that fails on import is the exact C7 failure mode this project keeps paying for.
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $sysPythonW
$psi.Arguments = "`"$script`""
$psi.WorkingDirectory = $repoRoot
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true

$proc = [System.Diagnostics.Process]::Start($psi)
$stdout = $proc.StandardOutput.ReadToEnd()
$stderr = $proc.StandardError.ReadToEnd()
$proc.WaitForExit()

$stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
$mode = if ($env:GAMMA_KALSHI_ARMED -eq '1') { 'LIVE' } else { 'SHADOW' }
Add-Content -Path $log -Value "[$stamp] ($mode) exit=$($proc.ExitCode)" -Encoding utf8
if ($stdout) { Add-Content -Path $log -Value $stdout.TrimEnd() -Encoding utf8 }
if ($stderr) { Add-Content -Path $log -Value "STDERR: $($stderr.TrimEnd())" -Encoding utf8 }

exit $proc.ExitCode
