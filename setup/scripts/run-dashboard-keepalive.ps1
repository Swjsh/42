# Gamma Next.js dashboard keepalive -- every 5 min, restart dashboard (port 3000) if dead.
# Mirrors run-companion-keepalive.ps1 (HTTP liveness probe, CreateNoWindow node spawn).
# The dashboard is the primary visibility layer at http://localhost:3000.
#
# REGISTER (do NOT run this directly for task creation -- owner registers separately):
#   $action = New-ScheduledTaskAction -Execute "wscript.exe" `
#     -Argument '"C:\Users\jackw\Desktop\42\setup\scripts\vbs-launchers\run-dashboard-keepalive.vbs"'
#   $trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 5) -Once -At (Get-Date)
#   Register-ScheduledTask -TaskName "Gamma_DashboardKeepalive" -Action $action -Trigger $trigger `
#     -RunLevel Highest -Force
#
# The VBS launcher (run-dashboard-keepalive.vbs) must be created alongside this file:
#   CreateObject("WScript.Shell").Run "powershell.exe -NonInteractive -WindowStyle Hidden " & _
#     "-File ""C:\Users\jackw\Desktop\42\setup\scripts\run-dashboard-keepalive.ps1""", 0, False
# STALE-BUILD GUARD (2026-09-14, coordinator-directed, HALLWAY-FIX builder's own
# side finding this session): -DryRun prints the stale-build decision (see below)
# without killing/respawning anything -- for manual verification against a live
# server nobody wants disrupted. Comment-only lines may precede a param() block in
# PowerShell; this one line must stay the first EXECUTABLE statement in the file.
param(
    [switch]$DryRun
)

. "$PSScriptRoot\_shared.ps1"

$task   = "dashboard-keepalive"
$dashDir = Join-Path $WorkDir "dashboard"
$port   = 3000

# Liveness probe: HTTP health check against Next.js root. A 200 means the server
# is answering; any error or non-200 → dead → respawn.
$alive = $false
$existingPid = 0
try {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) { $existingPid = [int]$conn.OwningProcess }
} catch {}
# NON-LOOPBACK-LISTENER GUARD (GAMMA-STATION item 10, 2026-09-14 02:1x ET): twice tonight a second
# :3000 listener appeared on :: / 0.0.0.0 next to the loopback one -- a plain `next dev` / `next start`
# from a builder or the Browser pane's launch.json (both bind every interface by default, and Windows
# lets a dual-stack :: listener coexist with a 127.0.0.1 one). The dashboard is LAN-reachable the
# whole time that listener lives. This keepalive runs every 5 min: kill it, log it, carry on.
try {
    $rogue = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -ne '127.0.0.1' -and $_.LocalAddress -ne '::1' }
    foreach ($rg in $rogue) {
        $rp = Get-CimInstance Win32_Process -Filter "ProcessId = $($rg.OwningProcess)" -ErrorAction SilentlyContinue
        Write-TaskLog -TaskName $task -Message ("ROGUE LISTENER " + $rg.LocalAddress + ":" + $port + " pid=" + $rg.OwningProcess + " (" + $rp.Name + ") -- killing (loopback-only rule)")
        try { Stop-Process -Id $rg.OwningProcess -Force -ErrorAction Stop } catch { Write-TaskLog -TaskName $task -Message ("  kill failed: " + $_.Exception.Message) }
    }
} catch {}
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -TimeoutSec 8 -UseBasicParsing
    if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { $alive = $true }
} catch {
    $alive = $false
}

if ($alive) {
    # STALE-BUILD GUARD (2026-09-14, coordinator-directed follow-up to the
    # HALLWAY-FIX builder's own side finding this session): a `npm run build`
    # from ANY builder overwrites dashboard/.next -- including deleting the
    # OLD chunk files the currently-running node process's in-memory build
    # manifest still references -- but nothing forces that process to
    # actually restart afterward. Root-caused live this session (2026-09-14
    # ~18:30 ET): a stale server kept serving HTML that referenced a chunk
    # hash the fresh build had already deleted, giving every viewer
    # net::ERR_CONNECTION_REFUSED + ChunkLoadError and a frozen loading
    # screen for several minutes -- invisible to the liveness probe above,
    # since Next.js's own `/` root route doesn't touch the broken route's
    # chunks and still answers 200.
    #
    # Detection: BUILD_ID is rewritten by every `npm run build`
    # (dashboard/.next/BUILD_ID). If its LastWriteTime is NEWER than the
    # currently-listening process's own StartTime, that process predates the
    # build it is nominally serving -- exactly the observed failure
    # signature (verified this session via the same comparison, done by
    # hand: `Get-Process -Id <port-3000 pid> | select StartTime` vs
    # `(Get-Item dashboard/.next/BUILD_ID).LastWriteTime`). Two guards
    # against a false trigger: (a) BUILD_ID must be >30s old -- a build
    # still mid-write shouldn't trip an immediate restart, give it a moment
    # to settle; (b) no dashboard/.build.lock younger than 15min may exist
    # -- a builder actively mid build+restart cycle already owns this exact
    # transition (see every HQ builder task brief's own build-lock
    # protocol), racing them here would fight, not help.
    # $buildDir (dashDir\.next) isn't defined until further down this script
    # (the "Require a production build" check below) -- built directly from
    # $dashDir (defined at the top of the file) here instead of depending on
    # that later variable existing yet.
    $stale = $false
    $buildIdPath = Join-Path $dashDir ".next\BUILD_ID"
    $lockPath = Join-Path $dashDir ".build.lock"
    try {
        if ((Test-Path $buildIdPath) -and $existingPid -gt 0) {
            $buildIdTime = (Get-Item $buildIdPath).LastWriteTime
            $buildIdAgeSec = (New-TimeSpan -Start $buildIdTime -End (Get-Date)).TotalSeconds
            $lockIsFresh = $false
            if (Test-Path $lockPath) {
                $lockAgeMin = (New-TimeSpan -Start (Get-Item $lockPath).LastWriteTime -End (Get-Date)).TotalMinutes
                if ($lockAgeMin -lt 15) { $lockIsFresh = $true }
            }
            $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
            if ($proc -and $buildIdTime -gt $proc.StartTime -and $buildIdAgeSec -gt 30 -and (-not $lockIsFresh)) {
                $stale = $true
                $msg = "stale build: pid " + $existingPid + " started " + $proc.StartTime.ToString("HH:mm:ss") + ", BUILD_ID written " + $buildIdTime.ToString("HH:mm:ss") + " -> restart"
                if ($DryRun) { $msg = "[DryRun] " + $msg }
                Write-TaskLog -TaskName $task -Message $msg
            }
        }
    } catch {
        Write-TaskLog -TaskName $task -Message ("stale-build check error (non-fatal, treating as not stale): " + $_.Exception.Message)
    }

    if (-not $stale) {
        Write-TaskLog -TaskName $task -Message "OK dashboard alive pid=$existingPid on :$port"
        exit 0
    }
    if ($DryRun) {
        Write-TaskLog -TaskName $task -Message "[DryRun] would kill pid=$existingPid and fall through to respawn -- no action taken"
        exit 0
    }
    # Fall through to the existing kill+respawn path below -- but that path
    # only spawns fresh when nothing currently holds the port, and a stale
    # server IS still holding it, so kill it here first.
    try {
        Stop-Process -Id $existingPid -Force -ErrorAction Stop
        Write-TaskLog -TaskName $task -Message ("killed stale pid=" + $existingPid)
        Start-Sleep -Seconds 2
        $existingPid = 0
    } catch {
        Write-TaskLog -TaskName $task -Message ("FAIL to kill stale pid=" + $existingPid + ": " + $_.Exception.Message)
        exit 1
    }
}

# Not answering on 3000. If another process holds the port (e.g. dev server), do NOT
# kill it -- that could disrupt active development work. Log and bail.
if ($existingPid -gt 0) {
    $owner = Get-WmiObject Win32_Process -Filter "ProcessId = $existingPid" -ErrorAction SilentlyContinue
    Write-TaskLog -TaskName $task -Message "PORT $port held by pid=$existingPid ($($owner.Name)) but / not 200; not killing, not spawning"
    exit 0
}

# Resolve node.exe (must exist; dashboard needs Node 18+).
$node = "C:\Program Files\nodejs\node.exe"
if (-not (Test-Path $node)) {
    $node = (Get-Command node.exe -ErrorAction SilentlyContinue).Source
}
if (-not $node -or -not (Test-Path $node)) {
    Write-TaskLog -TaskName $task -Message "ABORT node.exe not found"
    exit 1
}

# Require a production build (.next/) -- never auto-run `next dev` (dev server
# leaks on all interfaces and is slow to cold-start under a Task Scheduler context).
$buildDir = Join-Path $dashDir ".next"
if (-not (Test-Path $buildDir)) {
    Write-TaskLog -TaskName $task -Message "ABORT .next build not found at $buildDir -- run 'npm run build' first"
    exit 1
}

# next binary is in node_modules/.bin/next (CommonJS entry point, safe for node spawn).
$nextBin = Join-Path $dashDir "node_modules\.bin\next"
if (-not (Test-Path "$nextBin") -and -not (Test-Path "$nextBin.cmd")) {
    Write-TaskLog -TaskName $task -Message "ABORT next binary not found at $nextBin"
    exit 1
}
# Prefer .cmd shim which resolves correctly across platforms; node can exec it directly.
$nextScript = Join-Path $dashDir "node_modules\next\dist\bin\next"

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $node
$psi.Arguments = "`"$nextScript`" start -p $port -H 127.0.0.1"   # loopback only (GAMMA-STATION item 10, 2026-09-13): was 0.0.0.0 + a Public-profile firewall Allow for node.exe
$psi.WorkingDirectory = $dashDir
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$psi.RedirectStandardOutput = $false
$psi.RedirectStandardError = $false

try {
    $proc = [System.Diagnostics.Process]::Start($psi)
    Write-TaskLog -TaskName $task -Message "STARTED dashboard pid=$($proc.Id) on :$port"
} catch {
    Write-TaskLog -TaskName $task -Message "FAIL to start dashboard: $($_.Exception.Message)"
    exit 1
}
exit 0
