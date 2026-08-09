$ErrorActionPreference = 'Stop'
# ===== Gamma_KalshiAuto -- autonomous Kalshi weather lane (daily) =====
#
# Scores yesterday's predictions against NOAA's official settlement, writes new predictions
# for tomorrow, and trades ONLY the cities whose live scorecard has cleared the bar
# (>=20 settled days, >=45% hit rate, mean |error| <=1.6F). A city that has not earned it
# stays in shadow forever without anyone remembering to check.
#
# ############################################################################
# ##  ARM SWITCH -- DELIBERATELY NOT SET.                                    ##
# ##  Uncommenting this alone does NOT start trading: the per-city scorecard  ##
# ##  gate still has to pass. Both must be true before a dollar moves.        ##
# ##  REVOKE = re-comment, or disable the scheduled task.                     ##
# ############################################################################
# $env:GAMMA_KALSHI_ARMED = '1'

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))

# L41 / C8: never launch the venv's own python.exe (it re-execs with a hardcoded
# CREATE_NEW_CONSOLE and flashes a window). System interpreter + PYTHONPATH at the venv.
# `cryptography` lives ONLY in the venv here -- not in the base Programs Python.
$sysPythonW = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$venvSite   = Join-Path $repoRoot 'backtest\.venv\Lib\site-packages'
$script     = Join-Path $repoRoot 'automation\kalshi\kalshi_auto.py'
$logDir     = Join-Path $repoRoot 'automation\state\kalshi'
$log        = Join-Path $logDir 'auto.log'

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
if (-not (Test-Path $sysPythonW)) { throw "system pythonw missing: $sysPythonW" }
if (-not (Test-Path $script))     { throw "auto script missing: $script" }

$env:PYTHONPATH = $venvSite
$env:PYTHONIOENCODING = 'utf-8'

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

# C7: a scheduled task that dies silently on an import error is the failure mode this
# project keeps paying for. Capture BOTH streams and the exit code, every run.
$stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
$mode = if ($env:GAMMA_KALSHI_ARMED -eq '1') { 'ARMED' } else { 'SHADOW' }
Add-Content -Path $log -Value "===== [$stamp] ($mode) exit=$($proc.ExitCode) =====" -Encoding utf8
if ($stdout) { Add-Content -Path $log -Value $stdout.TrimEnd() -Encoding utf8 }
if ($stderr) { Add-Content -Path $log -Value "STDERR: $($stderr.TrimEnd())" -Encoding utf8 }

exit $proc.ExitCode
