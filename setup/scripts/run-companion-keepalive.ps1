# Gamma-companion keepalive -- every 5 min, restart gamma-companion/server.js if dead.
# Mirrors run-kitchen-daemon-keepalive.ps1 (WMI liveness per L27, CreateNoWindow
# spawn per OP-27 L41). The companion (port 4317) is the Tailscale-Serve-exposed
# face at https://dabox.tail2641b2.ts.net -- a 502 there means this process died
# with nothing to restart it. This task is that supervisor.
. "$PSScriptRoot\_shared.ps1"

$task = "companion-keepalive"
$companionDir = Join-Path $WorkDir "gamma-companion"
$serverScript = Join-Path $companionDir "server.js"
$port = 4317

# Liveness probe: definitive HTTP health check against the companion's own API.
# (Path-string matching on the process command line is fragile -- the VBS launcher
# runs `node server.js` with a RELATIVE arg, so the command line never contains
# "gamma-companion". A 200 from /api/state is unambiguous proof the companion is up.)
$alive = $false
$existingPid = 0
try {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) { $existingPid = [int]$conn.OwningProcess }
} catch {}
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/state" -TimeoutSec 8 -UseBasicParsing
    if ($r.StatusCode -eq 200) { $alive = $true }
} catch {
    $alive = $false
}

if ($alive) {
    Write-TaskLog -TaskName $task -Message "OK companion alive pid=$existingPid on :$port (/api/state 200)"
    exit 0
}

# Not answering on 4317. If a non-companion process holds the port, do NOT kill it
# and do NOT spawn (would EADDRINUSE). Log and bail -- a human owns that conflict.
if ($existingPid -gt 0) {
    $owner = Get-WmiObject Win32_Process -Filter "ProcessId = $existingPid" -ErrorAction SilentlyContinue
    Write-TaskLog -TaskName $task -Message "PORT $port held by pid=$existingPid ($($owner.Name)) but /api/state not 200; not killing, not spawning"
    exit 0
}

# Dead -- spawn fresh node + server.js (window-free, CreateNoWindow per L41)
$node = "C:\Program Files\nodejs\node.exe"
if (-not (Test-Path $node)) {
    $node = (Get-Command node.exe -ErrorAction SilentlyContinue).Source
}
if (-not $node -or -not (Test-Path $node)) {
    Write-TaskLog -TaskName $task -Message "ABORT node.exe not found"
    exit 1
}
if (-not (Test-Path $serverScript)) {
    Write-TaskLog -TaskName $task -Message "ABORT server.js not at $serverScript"
    exit 1
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $node
$psi.Arguments = "`"$serverScript`""
$psi.WorkingDirectory = $companionDir
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden

try {
    $proc = [System.Diagnostics.Process]::Start($psi)
    Write-TaskLog -TaskName $task -Message "STARTED companion pid=$($proc.Id) on :$port"
} catch {
    Write-TaskLog -TaskName $task -Message "FAIL to start companion: $($_.Exception.Message)"
    exit 1
}
exit 0
