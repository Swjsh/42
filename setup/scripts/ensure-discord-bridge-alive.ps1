# ============================================================================
# ensure-discord-bridge-alive.ps1 -- watchdog for Discord bridge + watcher
# ============================================================================
#
# Runs every 5 minutes via Task Scheduler. Checks:
#   - discord-bridge.py PID file present + process alive
#   - discord-watcher.py PID file present + process alive
# If either is dead, restarts it. Logs all actions.
#
# Idempotent. Safe to run on top of healthy state (no-op).
# ============================================================================

. "$PSScriptRoot\_shared.ps1"

$task = "discord-watchdog"
# Use the SYSTEM pythonw.exe (true GUI-subsystem binary, no console) with PYTHONPATH set
# to the venv's site-packages. The venv's own pythonw.exe stub re-execs as system
# python.exe (CONSOLE subsystem), which always allocates conhost — even -WindowStyle Hidden
# can't fully suppress it on Windows 11. See CLAUDE.md OP 27 L38 + 5/16 evening foot-gun.
$sysPythonw  = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$venvPythonw = Join-Path $WorkDir "backtest\.venv\Scripts\pythonw.exe"
$venv = if (Test-Path $sysPythonw) { $sysPythonw } else { $venvPythonw }
$venvSitePackages = Join-Path $WorkDir "backtest\.venv\Lib\site-packages"
$logDir = Join-Path $WorkDir "automation\state\logs"

function Test-PidAlive {
    param([string]$PidFilePath)
    if (-not (Test-Path $PidFilePath)) { return $false }
    try {
        $content = Get-Content $PidFilePath -Raw -ErrorAction Stop
        $pidValue = [int]($content.Trim().Split('|')[0])
        $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
        return ($null -ne $proc)
    } catch { return $false }
}

function Restart-DiscordProc {
    param(
        [string]$Name,
        [string]$ScriptPath,
        [string]$PidFilePath
    )
    Write-TaskLog -TaskName $task -Message "RESTART $Name (was dead or missing)"
    Remove-Item $PidFilePath -Force -ErrorAction SilentlyContinue
    $log = Join-Path $logDir "$Name.log"

    # Launch via wscript with PYTHONPATH set so system pythonw.exe sees venv's site-packages.
    # Combined with the 2026-05-16 registry change (default terminal -> conhost) + script-level
    # stdio redirect, this should produce zero visible windows.
    $vbs = Join-Path $WorkDir "setup\scripts\run_exe_hidden.vbs"
    try {
        $env:PYTHONPATH = $venvSitePackages
        $env:VIRTUAL_ENV = Join-Path $WorkDir "backtest\.venv"
        $wscriptArgs = @("//nologo", $vbs, $venv, $ScriptPath)
        Start-Process -FilePath "wscript.exe" -ArgumentList $wscriptArgs -WindowStyle Hidden -WorkingDirectory $WorkDir | Out-Null
    } catch {
        Write-TaskLog -TaskName $task -Message "  $Name START FAILED: $_"
        return
    }

    Start-Sleep -Seconds 2
    if (Test-PidAlive $PidFilePath) {
        Write-TaskLog -TaskName $task -Message "  $Name OK"
    } else {
        Write-TaskLog -TaskName $task -Message "  $Name FAILED to start"
    }
}

# Check bridge
$bridgePid = Join-Path $WorkDir "automation\state\discord-bridge.pid"
if (-not (Test-PidAlive $bridgePid)) {
    Restart-DiscordProc -Name "discord-bridge" -ScriptPath (Join-Path $WorkDir "setup\scripts\discord-bridge.py") -PidFilePath $bridgePid
}

# Check watcher
$watcherPid = Join-Path $WorkDir "automation\state\discord-watcher.pid"
if (-not (Test-PidAlive $watcherPid)) {
    Restart-DiscordProc -Name "discord-watcher" -ScriptPath (Join-Path $WorkDir "setup\scripts\discord-watcher.py") -PidFilePath $watcherPid
}

# Done -- silent if everything healthy.
exit 0
