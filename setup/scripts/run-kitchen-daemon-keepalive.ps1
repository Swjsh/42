# Kitchen daemon keepalive -- every 5 min, restart kitchen_daemon.py if dead.
# Long-running pythonw process pattern (same as live_grinder keepalive).
# Per CLAUDE.md OP-30 + J directive "24/7 cooking, Claude is the driver."
. "$PSScriptRoot\_shared.ps1"

$task = "kitchen-daemon-keepalive"
$pidFile = Join-Path $WorkDir "automation\state\kitchen-daemon.pid"
$daemonScript = Join-Path $WorkDir "setup\scripts\kitchen_daemon.py"

# Liveness probe: is the daemon's recorded PID a real pythonw process whose
# command line points at kitchen_daemon.py?
$alive = $false
if (Test-Path $pidFile) {
    try {
        $payload = Get-Content $pidFile -Raw | ConvertFrom-Json
        $existingPid = [int]$payload.pid
        if ($existingPid -gt 0) {
            # Use WMI -- Get-Process can miss console-less pythonw (per L27)
            $proc = Get-WmiObject Win32_Process -Filter "ProcessId = $existingPid" -ErrorAction SilentlyContinue
            if ($proc -and $proc.CommandLine -match "kitchen_daemon\.py") {
                $alive = $true
            }
        }
    } catch {
        $alive = $false
    }
}

if ($alive) {
    # Sanity: did kitchen-status.json get written in the last 25 min? If not,
    # daemon is wedged -- kill it so the next keepalive restarts it fresh.
    # 25min cap accommodates worst-case Nemotron reasoning + full ladder fallback
    # (each tier can take 5min on slow free-tier providers).
    $statusFile = Join-Path $WorkDir "automation\state\kitchen-status.json"
    if (Test-Path $statusFile) {
        $statAge = ((Get-Date) - (Get-Item $statusFile).LastWriteTime).TotalMinutes
        if ($statAge -gt 25) {
            Write-TaskLog -TaskName $task -Message "DAEMON WEDGED status_age=${statAge}min > 25min; killing pid=$existingPid"
            try { Stop-Process -Id $existingPid -Force -ErrorAction Stop } catch {}
            $alive = $false
        } else {
            # GOAL-RIG-HYGIENE-2026-09-05 H1: alive + fresh status is not the whole story --
            # if the daemon is IDLE right now and started before the newest edit to the
            # scripts it imports, shipped code is sitting un-deployed. Never restart while
            # busy (idle=false); the policy script enforces that itself.
            $policyScript = Join-Path $WorkDir "setup\scripts\kitchen_daemon_restart_policy.py"
            $decision = Invoke-PythonHidden -ScriptPath $policyScript -TaskName "$task-policy"
            $shouldRestart = $false
            $reason = "policy check failed or produced no output"
            if ($decision.ExitCode -eq 0 -and $decision.Stdout) {
                try {
                    $parsed = $decision.Stdout | ConvertFrom-Json
                    $shouldRestart = [bool]$parsed.restart
                    $reason = $parsed.reason
                } catch {
                    $reason = "could not parse policy stdout: $($decision.Stdout)"
                }
            }
            if ($shouldRestart) {
                Write-TaskLog -TaskName $task -Message "IDLE+STALE-CODE pid=$existingPid reason=$reason -- killing for restart"
                try { Stop-Process -Id $existingPid -Force -ErrorAction Stop } catch {}
                $alive = $false
            } else {
                Write-TaskLog -TaskName $task -Message "OK daemon alive pid=$existingPid status_age=$([math]::Round($statAge,1))min policy=$reason"
                exit 0
            }
        }
    } else {
        Write-TaskLog -TaskName $task -Message "OK daemon alive pid=$existingPid (no status file yet)"
        exit 0
    }
}

# Daemon dead -- spawn fresh pythonw + kitchen_daemon.py
$sysPy = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $sysPy)) {
    Write-TaskLog -TaskName $task -Message "ABORT system pythonw not at $sysPy"
    exit 1
}

# Spawn via CreateProcess with CREATE_NO_WINDOW (OP-27 L41 layer 4)
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $sysPy
$psi.Arguments = "`"$daemonScript`" run"
$psi.WorkingDirectory = $WorkDir
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$psi.RedirectStandardOutput = $false
$psi.RedirectStandardError = $false

# Wire venv site-packages so openai SDK is importable
$venvSite = Join-Path $WorkDir "backtest\.venv\Lib\site-packages"
if (Test-Path $venvSite) {
    $psi.EnvironmentVariables["PYTHONPATH"] = $venvSite
}

try {
    $proc = [System.Diagnostics.Process]::Start($psi)
    Write-TaskLog -TaskName $task -Message "STARTED kitchen daemon pid=$($proc.Id)"
} catch {
    Write-TaskLog -TaskName $task -Message "FAIL to start daemon: $($_.Exception.Message)"
    exit 1
}
exit 0
