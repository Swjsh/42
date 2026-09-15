# dashboard_deploy.ps1 -- ONE command that encodes the 5-step dashboard deploy
# protocol every HQ worker previously re-implemented by hand (two got it wrong
# the night of 2026-09-15). Safe when several sessions deploy concurrently:
# a file-based lock (dashboard/.build.lock) serializes builds, and the
# STALE-BUILD GUARD already in run-dashboard-keepalive.ps1 (read there for
# full incident history) handles the post-build restart so this script does
# not duplicate that restart logic -- it just re-invokes the keepalive and
# polls /api/hq for build_id parity.
#
# Usage:
#   powershell -File setup\scripts\dashboard_deploy.ps1 -Tag "<who/what>"
#   powershell -File setup\scripts\dashboard_deploy.ps1 -Tag "<who>" -DryRun
#   powershell -File setup\scripts\dashboard_deploy.ps1 -Tag "<who>" -BreakStaleLock
#
# Params:
#   -Tag <string>        REQUIRED. Identifies the caller in the lock file and log
#                         (e.g. a session name / worker id). Not a secret.
#   -MaxWaitMin <int>     Max minutes to wait on another session's fresh lock
#                         before refusing. Default 20.
#   -BreakStaleLock       If the existing lock is stale (> 15 min old), delete
#                         it and proceed instead of just reporting it.
#   -DryRun               Print every decision, build nothing, write nothing
#                         (no lock file is created or removed).
#   -DashboardDir <path>  Override the dashboard directory. FOR TESTING ONLY
#                         (lock-contention tests point this at a temp dir) --
#                         production callers must never pass this; omitting it
#                         is the only supported use in real deploys.
#
# Exit codes (distinct per stage, matches the final printed line):
#   0   DEPLOY OK
#   10  REFUSED -- lock held by another session past -MaxWaitMin
#   11  REFUSED -- stale lock present, -BreakStaleLock not passed
#   12  FAILED stage=lock-acquire -- lost the atomic-create race
#   20  FAILED stage=build -- npm run build failed (after the one ENOENT retry)
#   30  FAILED stage=restart -- keepalive never produced a live /api/hq response
#   31  FAILED stage=restart -- /api/hq build_id never matched .next/BUILD_ID
#   99  FAILED stage=args -- bad invocation (e.g. missing -Tag)
#
# STALE-BUILD GUARD note (read run-dashboard-keepalive.ps1's own header first):
# that script already refuses to restart while dashboard/.build.lock is < 15
# min old, specifically so an in-flight deploy via THIS script is never raced
# by the 5-min keepalive scheduled task. This script's lock IS that contract.

param(
    [string]$Tag = "",
    [int]$MaxWaitMin = 20,
    [switch]$BreakStaleLock,
    [switch]$DryRun,
    [string]$DashboardDir = ""
)

. "$PSScriptRoot\_shared.ps1"

$deployTask = "dashboard-deploy"
$startTime = Get-Date

function Emit-Log {
    param([string]$Message)
    $line = "[dashboard_deploy] $Message"
    Write-Host $line
    Write-TaskLog -TaskName $deployTask -Message $Message
}

function Finish {
    param([int]$Code, [string]$FinalLine)
    Emit-Log $FinalLine
    exit $Code
}

if (-not $Tag) {
    Finish 99 "DEPLOY FAILED stage=args reason=-Tag is required"
}

$dashDir = if ($DashboardDir) { $DashboardDir } else { Join-Path $WorkDir "dashboard" }
$lockPath = Join-Path $dashDir ".build.lock"
$buildIdPath = Join-Path $dashDir ".next\BUILD_ID"
$buildLogPath = Join-Path $LogDir "$deployTask-build-$((Get-EtNow).ToString('yyyy-MM-dd')).log"

Emit-Log "starting deploy tag=$Tag dashDir=$dashDir dryRun=$($DryRun.IsPresent) maxWaitMin=$MaxWaitMin"

# --- STEP 1: lock wait / stale-lock check -----------------------------------
$pollSec = 15
$maxWaitSec = $MaxWaitMin * 60
$waited = 0
while ($true) {
    if (-not (Test-Path $lockPath)) { break }

    $lockAgeMin = (New-TimeSpan -Start (Get-Item $lockPath).LastWriteTime -End (Get-Date)).TotalMinutes
    if ($lockAgeMin -gt 15) {
        if ($BreakStaleLock) {
            $ownerInfo = Get-Content $lockPath -Raw -ErrorAction SilentlyContinue
            Emit-Log "STALE LOCK ($([math]::Round($lockAgeMin,1)) min old, owner: $ownerInfo) -- BreakStaleLock passed, removing"
            if (-not $DryRun) { Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue }
            break
        } else {
            $ownerInfo = Get-Content $lockPath -Raw -ErrorAction SilentlyContinue
            Finish 11 "DEPLOY FAILED stage=lock-wait reason=stale lock ($([math]::Round($lockAgeMin,1)) min old, owner: $ownerInfo) -- rerun with -BreakStaleLock to clear it"
        }
    }

    if ($waited -ge $maxWaitSec) {
        $ownerInfo = Get-Content $lockPath -Raw -ErrorAction SilentlyContinue
        Finish 10 "DEPLOY FAILED stage=lock-wait reason=lock held past -MaxWaitMin=$MaxWaitMin (owner: $ownerInfo)"
    }

    Emit-Log "lock held (age $([math]::Round($lockAgeMin,1)) min) -- waiting ${pollSec}s (waited ${waited}s / ${maxWaitSec}s)"
    if ($DryRun) {
        Emit-Log "[DryRun] would poll every ${pollSec}s up to ${maxWaitSec}s total -- stopping dry-run wait simulation here"
        break
    }
    Start-Sleep -Seconds $pollSec
    $waited += $pollSec
}

if ($DryRun) {
    Emit-Log "[DryRun] would atomically create $lockPath with pid=$PID tag=$Tag start=$(Get-Date -Format o)"
    Emit-Log "[DryRun] would run: npm run build (cwd=$dashDir), log -> $buildLogPath"
    Emit-Log "[DryRun] would remove lock in finally"
    Emit-Log "[DryRun] would wait for BUILD_ID age > 35s, then run run-dashboard-keepalive.ps1 hidden"
    Emit-Log "[DryRun] would poll http://127.0.0.1:3000/api/hq for up to 120s for build_id match, re-running keepalive once if not restarted by 60s"
    Finish 0 "DEPLOY OK (dry-run, nothing built/written) elapsed_s=$([int]((Get-Date) - $startTime).TotalSeconds)"
}

# --- STEP 2: atomic lock create ----------------------------------------------
if (-not (Test-Path $dashDir)) {
    Finish 99 "DEPLOY FAILED stage=args reason=dashboard dir not found: $dashDir"
}
$lockBody = "pid=$PID tag=$Tag start=$(Get-Date -Format o)"
$lockAcquired = $false
try {
    # FileStream with CreateNew fails atomically if another process wins the race
    # (equivalent to O_CREAT|O_EXCL) -- New-Item alone is not race-safe on its own
    # under concurrent PowerShell sessions targeting the same path.
    $fs = [System.IO.FileStream]::new($lockPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    $writer = [System.IO.StreamWriter]::new($fs)
    $writer.Write($lockBody)
    $writer.Flush()
    $writer.Close()
    $fs.Close()
    $lockAcquired = $true
    Emit-Log "lock acquired: $lockBody"
} catch {
    Finish 12 "DEPLOY FAILED stage=lock-acquire reason=$($_.Exception.Message)"
}

$exitCode = 0
$finalLine = ""
try {
    # --- STEP 3: npm run build (captured, one retry on the known ENOENT) ----
    function Invoke-Build {
        $p = Start-Process -FilePath "cmd.exe" `
            -ArgumentList "/c npm run build > `"$buildLogPath`" 2>&1" `
            -WorkingDirectory $dashDir -WindowStyle Hidden -PassThru
        $p.WaitForExit()
        return $p.ExitCode
    }

    Emit-Log "npm run build starting (log: $buildLogPath)"
    $buildExit = Invoke-Build
    $buildLog = if (Test-Path $buildLogPath) { Get-Content $buildLogPath -Raw } else { "" }

    if ($buildExit -ne 0 -and $buildLog -match "ENOENT.*build-manifest\.json") {
        Emit-Log "build failed with known transient ENOENT (build-manifest.json) -- retrying once"
        $buildExit = Invoke-Build
        $buildLog = if (Test-Path $buildLogPath) { Get-Content $buildLogPath -Raw } else { "" }
    }

    if ($buildExit -ne 0) {
        $lines = ($buildLog -split "`r?`n") | Select-Object -Last 30
        $tail = ($lines -join "`n")
        $exitCode = 20
        $finalLine = "DEPLOY FAILED stage=build reason=npm run build exit=$buildExit`n--- last 30 log lines ---`n$tail"
        return
    }
    Emit-Log "npm run build OK"

    # --- STEP 5: wait BUILD_ID settle, restart, poll /api/hq ----------------
    if (-not (Test-Path $buildIdPath)) {
        $exitCode = 20
        $finalLine = "DEPLOY FAILED stage=build reason=build succeeded but BUILD_ID missing at $buildIdPath"
        return
    }
    $newBuildId = (Get-Content $buildIdPath -Raw).Trim()

    $settleDeadline = (Get-Item $buildIdPath).LastWriteTime.AddSeconds(35)
    while ((Get-Date) -lt $settleDeadline) {
        Start-Sleep -Seconds 2
    }

    $keepaliveScript = Join-Path $PSScriptRoot "run-dashboard-keepalive.ps1"
    function Invoke-KeepaliveHidden {
        Start-Process -FilePath "powershell.exe" `
            -ArgumentList "-NonInteractive", "-WindowStyle", "Hidden", "-File", "`"$keepaliveScript`"" `
            -WindowStyle Hidden | Out-Null
    }

    Emit-Log "running keepalive hidden to restart dashboard on new build (BUILD_ID=$newBuildId)"
    Invoke-KeepaliveHidden

    $pollDeadline = (Get-Date).AddSeconds(120)
    $reRan = $false
    $matched = $false
    while ((Get-Date) -lt $pollDeadline) {
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:3000/api/hq" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
            $json = $resp.Content | ConvertFrom-Json
            if ($json.build_id -eq $newBuildId) {
                $matched = $true
                break
            }
        } catch {
            # server not answering yet -- expected during restart, keep polling
        }

        $elapsedSincePoll = (New-TimeSpan -Start $startTime -End (Get-Date)).TotalSeconds
        if (-not $reRan -and $elapsedSincePoll -ge 60) {
            Emit-Log "no build_id match by 60s -- re-running keepalive once"
            Invoke-KeepaliveHidden
            $reRan = $true
        }
        Start-Sleep -Seconds 5
    }

    if (-not $matched) {
        $exitCode = 31
        $finalLine = "DEPLOY FAILED stage=restart reason=/api/hq build_id never matched .next/BUILD_ID ($newBuildId) within 120s"
        return
    }

    $elapsed = [int]((Get-Date) - $startTime).TotalSeconds
    $exitCode = 0
    $finalLine = "DEPLOY OK build_id=$newBuildId elapsed_s=$elapsed"
} finally {
    # --- STEP 4 (always): remove lock ---------------------------------------
    if ($lockAcquired -and (Test-Path $lockPath)) {
        Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
        Emit-Log "lock released"
    }
}

Finish $exitCode $finalLine
