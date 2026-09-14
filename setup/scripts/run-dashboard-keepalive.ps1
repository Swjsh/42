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
    Write-TaskLog -TaskName $task -Message "OK dashboard alive pid=$existingPid on :$port"
    exit 0
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
