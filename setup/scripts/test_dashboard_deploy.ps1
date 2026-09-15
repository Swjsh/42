# test_dashboard_deploy.ps1 -- harness for dashboard_deploy.ps1, no real build/restart.
#
# WHY: the 2026-09-15 PERSONA-LATENCY incident showed dashboard_deploy.ps1 could hit a
# failure path, print NO final DEPLOY line, and exit 0 (false success) because of a
# top-level `return` inside its try block. This harness proves the fix holds across
# every failure/success path WITHOUT running `npm run build` or touching the real
# dashboard process, by:
#   - using -DashboardDir pointed at a temp dir with a fake .next\BUILD_ID
#   - using -SkipBuild so no real `npm run build` runs
#   - using -KeepaliveScript pointed at a local no-op stub .ps1 (never touches the
#     real dashboard / run-dashboard-keepalive.ps1)
#   - using -ApiUrl pointed at a tiny local Python http.server stub on a free
#     127.0.0.1 port, so /api/hq polling is fully local and deterministic
#
# Every command runs in the FOREGROUND. Run with:
#   powershell -File setup\scripts\test_dashboard_deploy.ps1
#
# Exits 0 if every case matched its expected {exit code, final-line prefix}; exits 1
# and prints a FAIL block per mismatch otherwise.

$ErrorActionPreference = "Stop"
$deployScript = Join-Path $PSScriptRoot "dashboard_deploy.ps1"
$results = @()
$anyFail = $false

function New-TempDashDir {
    $dir = Join-Path $env:TEMP ("dashdeploy-test-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path (Join-Path $dir ".next") | Out-Null
    return $dir
}

function Write-FakeBuildId {
    param([string]$DashDir, [string]$BuildId)
    Set-Content -Path (Join-Path $DashDir ".next\BUILD_ID") -Value $BuildId -NoNewline -Encoding utf8
}

function New-NoOpKeepaliveStub {
    param([string]$DashDir)
    $path = Join-Path $DashDir "noop-keepalive.ps1"
    # Intentionally does nothing -- proves dashboard_deploy.ps1 doesn't depend on the
    # real keepalive script's behavior for these test cases (the stub server below is
    # what actually answers /api/hq).
    Set-Content -Path $path -Value "# no-op keepalive stub for tests" -Encoding utf8
    return $path
}

# --- tiny local /api/hq stub server (Python http.server, foreground start/stop) ----
function Start-StubApiServer {
    param([int]$Port, [string]$BuildId, [bool]$AlwaysMismatch)

    $stubDir = Join-Path $env:TEMP ("dashdeploy-stub-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $stubDir | Out-Null

    $returnedBuildId = if ($AlwaysMismatch) { "$BuildId-MISMATCH" } else { $BuildId }
    $handlerPy = @"
import http.server, json

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/hq'):
            body = json.dumps({'build_id': '$returnedBuildId'}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # keep test output quiet

http.server.HTTPServer(('127.0.0.1', $Port), Handler).serve_forever()
"@
    $pyPath = Join-Path $stubDir "stub_api.py"
    Set-Content -Path $pyPath -Value $handlerPy -Encoding utf8

    $sysPython = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\python.exe"
    if (-not (Test-Path $sysPython)) {
        $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($cmd) { $sysPython = $cmd.Source } else { throw "python.exe not found" }
    }

    $proc = Start-Process -FilePath $sysPython -ArgumentList "`"$pyPath`"" -WindowStyle Hidden -PassThru
    # Wait for the stub to actually accept connections before returning.
    $deadline = (Get-Date).AddSeconds(10)
    $up = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/hq" -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
            if ($r.StatusCode -eq 200) { $up = $true; break }
        } catch { Start-Sleep -Milliseconds 200 }
    }
    if (-not $up) { throw "stub API server on port $Port never came up" }
    return $proc
}

function Stop-StubApiServer {
    param($Proc)
    if ($Proc -and -not $Proc.HasExited) {
        Stop-Process -Id $Proc.Id -Force -ErrorAction SilentlyContinue
    }
}

function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = $listener.LocalEndpoint.Port
    $listener.Stop()
    return $port
}

function Invoke-DeployCase {
    param(
        [string]$CaseName,
        [string[]]$ExtraArgs,
        [int]$ExpectedExit,
        [string]$ExpectedLinePrefix,
        [string]$DashDir,
        [string]$LockPath
    )

    Write-Host "=== CASE: $CaseName ==="
    $psExe = (Get-Process -Id $PID).Path
    $argList = @("-NoProfile", "-NonInteractive", "-File", "`"$deployScript`"") + $ExtraArgs
    $p = Start-Process -FilePath $psExe -ArgumentList $argList -NoNewWindow -PassThru -Wait `
        -RedirectStandardOutput (Join-Path $env:TEMP "dashdeploy-test-stdout.txt") `
        -RedirectStandardError (Join-Path $env:TEMP "dashdeploy-test-stderr.txt")
    $exitCode = $p.ExitCode
    $stdout = Get-Content (Join-Path $env:TEMP "dashdeploy-test-stdout.txt") -Raw -ErrorAction SilentlyContinue
    $stderr = Get-Content (Join-Path $env:TEMP "dashdeploy-test-stderr.txt") -Raw -ErrorAction SilentlyContinue
    $allOut = "$stdout`n$stderr"
    $nonEmptyLines = ($allOut -split "`r?`n") | Where-Object { $_.Trim() -ne "" }
    $lastLine = if ($nonEmptyLines.Count -gt 0) { $nonEmptyLines[-1] } else { "" }

    $lockGone = -not (Test-Path $LockPath)
    $exitOk = ($exitCode -eq $ExpectedExit)
    # Finish() routes the final line through Emit-Log, which prefixes every line with
    # "[dashboard_deploy] " -- match on substring-after-prefix, not a strict StartsWith.
    $lineOk = $lastLine.Contains($ExpectedLinePrefix)

    $pass = $exitOk -and $lineOk -and $lockGone
    if (-not $pass) { $script:anyFail = $true }

    Write-Host "  exit_code   = $exitCode (expected $ExpectedExit) -> $(if ($exitOk) {'OK'} else {'FAIL'})"
    Write-Host "  last_line   = $lastLine"
    Write-Host "  expected_pfx= $ExpectedLinePrefix -> $(if ($lineOk) {'OK'} else {'FAIL'})"
    Write-Host "  lock_gone   = $lockGone -> $(if ($lockGone) {'OK'} else {'FAIL'})"
    Write-Host ""

    return [PSCustomObject]@{
        Case      = $CaseName
        ExitCode  = $exitCode
        LastLine  = $lastLine
        Pass      = $pass
    }
}

# ============================================================================
# Case (a): API returns matching build_id -> exit 0, last line starts "DEPLOY OK"
# ============================================================================
$dirA = New-TempDashDir
$buildIdA = "BUILDID-A-" + [guid]::NewGuid().ToString("N").Substring(0,8)
Write-FakeBuildId -DashDir $dirA -BuildId $buildIdA
$stubScriptA = New-NoOpKeepaliveStub -DashDir $dirA
$portA = Get-FreePort
$serverA = Start-StubApiServer -Port $portA -BuildId $buildIdA -AlwaysMismatch:$false
try {
    $results += Invoke-DeployCase -CaseName "a: build_id matches" `
        -ExtraArgs @("-Tag", "test-a", "-DashboardDir", $dirA, "-SkipBuild", `
                     "-KeepaliveScript", $stubScriptA, "-ApiUrl", "http://127.0.0.1:$portA/api/hq", `
                     "-RestartWaitSec", "20") `
        -ExpectedExit 0 -ExpectedLinePrefix "DEPLOY OK" `
        -DashDir $dirA -LockPath (Join-Path $dirA ".build.lock")
} finally {
    Stop-StubApiServer -Proc $serverA
    Remove-Item -Recurse -Force $dirA -ErrorAction SilentlyContinue
}

# ============================================================================
# Case (b): API always responds but build_id never matches -> exit 31,
# "DEPLOY FAILED stage=restart", re-run logged after ~half the poll window
# (short -RestartWaitSec so the test is fast; ratio documented in the script).
# ============================================================================
$dirB = New-TempDashDir
$buildIdB = "BUILDID-B-" + [guid]::NewGuid().ToString("N").Substring(0,8)
Write-FakeBuildId -DashDir $dirB -BuildId $buildIdB
$stubScriptB = New-NoOpKeepaliveStub -DashDir $dirB
$portB = Get-FreePort
$serverB = Start-StubApiServer -Port $portB -BuildId $buildIdB -AlwaysMismatch:$true
try {
    $caseB = Invoke-DeployCase -CaseName "b: build_id never matches" `
        -ExtraArgs @("-Tag", "test-b", "-DashboardDir", $dirB, "-SkipBuild", `
                     "-KeepaliveScript", $stubScriptB, "-ApiUrl", "http://127.0.0.1:$portB/api/hq", `
                     "-RestartWaitSec", "20") `
        -ExpectedExit 31 -ExpectedLinePrefix "DEPLOY FAILED stage=restart" `
        -DashDir $dirB -LockPath (Join-Path $dirB ".build.lock")
    $results += $caseB
    $reRanOk = $caseB.LastLine -match "reran_keepalive=True"
    Write-Host "  reran_keepalive logged = $reRanOk (RestartWaitSec=20 -> re-run threshold ~10s of polling, well under the 20s deadline)"
    if (-not $reRanOk) { $script:anyFail = $true }
} finally {
    Stop-StubApiServer -Proc $serverB
    Remove-Item -Recurse -Force $dirB -ErrorAction SilentlyContinue
}

# ============================================================================
# Case (c): -SkipBuild with BUILD_ID missing -> exit 20, "DEPLOY FAILED stage=build"
# ============================================================================
$dirC = New-TempDashDir
# deliberately do NOT write .next\BUILD_ID
$stubScriptC = New-NoOpKeepaliveStub -DashDir $dirC
$results += Invoke-DeployCase -CaseName "c: BUILD_ID missing (fake build failure)" `
    -ExtraArgs @("-Tag", "test-c", "-DashboardDir", $dirC, "-SkipBuild", `
                 "-KeepaliveScript", $stubScriptC, "-ApiUrl", "http://127.0.0.1:1/api/hq", `
                 "-RestartWaitSec", "5") `
    -ExpectedExit 20 -ExpectedLinePrefix "DEPLOY FAILED stage=build" `
    -DashDir $dirC -LockPath (Join-Path $dirC ".build.lock")
Remove-Item -Recurse -Force $dirC -ErrorAction SilentlyContinue

# ============================================================================
# Case (d) is folded into (a)/(b)/(c) above: Invoke-DeployCase already asserts
# lock_gone (the .build.lock file no longer exists) after every run.
# ============================================================================

Write-Host "=== SUMMARY ==="
foreach ($r in $results) {
    $status = if ($r.Pass) { "PASS" } else { "FAIL" }
    Write-Host "[$status] $($r.Case) -- exit=$($r.ExitCode) last_line=`"$($r.LastLine.Split("`n")[0])`""
}

if ($anyFail) {
    Write-Host "TEST HARNESS: FAIL"
    exit 1
} else {
    Write-Host "TEST HARNESS: PASS"
    exit 0
}
