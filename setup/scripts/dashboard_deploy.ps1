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
#   -SkipBuild            FOR TESTING ONLY. Skips `npm run build` entirely and
#                         goes straight to the BUILD_ID / restart-poll steps
#                         against whatever is already on disk at -DashboardDir.
#                         Refused unless -DashboardDir is also passed, so a
#                         production invocation can never silently skip the
#                         build.
#   -ApiUrl <string>      FOR TESTING ONLY (default http://127.0.0.1:3000/api/hq).
#                         Lets a test point the restart-poll step at a local
#                         stub server instead of the real dashboard.
#   -KeepaliveScript <path>
#                         FOR TESTING ONLY (default: the real
#                         run-dashboard-keepalive.ps1 next to this script).
#                         Lets a test point the restart step at a no-op stub
#                         so no real dashboard process is spawned/killed.
#   -RestartWaitSec <int> Total seconds to poll -ApiUrl for build_id parity
#                         after the restart (default 180). The keepalive
#                         re-run-once fires at RestartWaitSec/2 (matches the
#                         original fixed 60s-of-120s = 1:2 ratio) so tests can
#                         pass a short -RestartWaitSec and get a proportionally
#                         fast re-run without changing the shape of the logic.
#                         Both the deadline and the re-run point are measured
#                         from the start of POLLING (after the restart is
#                         kicked off), never from script start -- that was
#                         bug #2 in the 2026-09-15 incident (see below).
#
# Exit codes (distinct per stage, matches the final printed line):
#   0   DEPLOY OK
#   10  REFUSED -- lock held by another session past -MaxWaitMin
#   11  REFUSED -- stale lock present, -BreakStaleLock not passed
#   12  FAILED stage=lock-acquire -- lost the atomic-create race
#   20  FAILED stage=build -- npm run build failed (after the one ENOENT retry),
#       or build "succeeded" but .next\BUILD_ID is missing
#   30  FAILED stage=restart -- keepalive never produced a single live
#       /api/hq response within -RestartWaitSec (server never came back up)
#   31  FAILED stage=restart -- /api/hq responded but build_id never matched
#       .next/BUILD_ID within -RestartWaitSec (server up on the OLD build)
#   99  FAILED stage=args -- bad invocation (e.g. missing -Tag)
#
# STALE-BUILD GUARD note (read run-dashboard-keepalive.ps1's own header first):
# that script already refuses to restart while dashboard/.build.lock is < 15
# min old, specifically so an in-flight deploy via THIS script is never raced
# by the 5-min keepalive scheduled task. This script's lock IS that contract.
#
# 2026-09-15 incident (PERSONA-LATENCY first real run) -- two bugs, both fixed
# here:
#   1. Every failure path inside the STEP 3-5 `try` block called bare
#      `return`. At PowerShell SCRIPT scope (not inside a function), `return`
#      unwinds past the trailing `Finish $exitCode $finalLine` line entirely
#      -- the `finally` still ran (so "lock released" printed) but the final
#      DEPLOY line never printed and the process exited 0 (PowerShell default)
#      instead of the intended failure code. FIX: the build/restart body now
#      lives in a function (Invoke-BuildAndRestart) that returns a
#      {Code, Line} result to the script; the script's own top-level code has
#      no `return` inside its try block any more, so it always reaches the
#      single `Finish` call after the lock is released.
#   2. The "re-run keepalive if not matched by 60s" check measured elapsed
#      time from $startTime (script start, including lock-wait + build time),
#      not from the start of polling -- so any build over 60s made it re-run
#      the keepalive immediately instead of after 60s of actual polling.
#      FIX: polling now has its own $pollStartTime and both the re-run point
#      and the deadline are measured from it.
#
# 2026-09-15 incident #2 (verified 04:14 ET, self-deadlock) -- this script's own
# STEP 2 lock (dashboard/.build.lock, held for the whole run) was being read by
# run-dashboard-keepalive.ps1's STALE-BUILD GUARD as "another deploy is already
# mid-flight, don't race it" -- but the "other deploy" WAS this script, calling
# keepalive itself to do the restart it had just built for. The guard refused to
# restart ("OK dashboard alive"), so /api/hq kept answering the OLD build_id until
# -RestartWaitSec ran out -> exit 31 stage=restart. FIX: an ownership handshake --
# this script passes -LockOwnerPid $PID to every Invoke-KeepaliveHidden call, and
# the keepalive only lets the lock through as "not fresh" when that pid matches
# the pid= token IN the lock file (so a genuinely different session's fresh lock
# still blocks, as designed). See run-dashboard-keepalive.ps1's own header for the
# other half of this fix.

param(
    [string]$Tag = "",
    [int]$MaxWaitMin = 20,
    [switch]$BreakStaleLock,
    [switch]$DryRun,
    [string]$DashboardDir = "",
    [switch]$SkipBuild,
    [string]$ApiUrl = "http://127.0.0.1:3000/api/hq",
    [string]$KeepaliveScript = "",
    [int]$RestartWaitSec = 180
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

if ($SkipBuild -and -not $DashboardDir) {
    Finish 99 "DEPLOY FAILED stage=args reason=-SkipBuild is testing-only and requires -DashboardDir"
}

$dashDir = if ($DashboardDir) { $DashboardDir } else { Join-Path $WorkDir "dashboard" }
$lockPath = Join-Path $dashDir ".build.lock"
$buildIdPath = Join-Path $dashDir ".next\BUILD_ID"
$buildLogPath = Join-Path $LogDir "$deployTask-build-$((Get-EtNow).ToString('yyyy-MM-dd')).log"
$keepaliveScriptPath = if ($KeepaliveScript) { $KeepaliveScript } else { Join-Path $PSScriptRoot "run-dashboard-keepalive.ps1" }

Emit-Log "starting deploy tag=$Tag dashDir=$dashDir dryRun=$($DryRun.IsPresent) maxWaitMin=$MaxWaitMin skipBuild=$($SkipBuild.IsPresent) apiUrl=$ApiUrl restartWaitSec=$RestartWaitSec"

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
    Emit-Log "[DryRun] would wait for BUILD_ID age > 35s, then run $keepaliveScriptPath hidden -LockOwnerPid $PID (so keepalive's stale-build guard doesn't block on our own lock)"
    Emit-Log "[DryRun] would poll $ApiUrl for up to ${RestartWaitSec}s for build_id match, re-running keepalive once if not matched by $([math]::Max(5,[int]([math]::Floor($RestartWaitSec/2))))s"
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

# Body of steps 3-5 lives in a FUNCTION (not inline in the try below) so that
# every failure path can use `return` to bail out of just this function --
# `return` at script scope would skip the trailing `Finish` call below (that
# was the 2026-09-15 false-success bug). The function returns @{Code; Line}
# and the script does the lock-release + single Finish call itself.
function Invoke-BuildAndRestart {
    param(
        [string]$DashDir,
        [string]$BuildLogPath,
        [string]$BuildIdPath,
        [string]$KeepaliveScriptPath,
        [string]$ApiUrl,
        [int]$RestartWaitSec,
        [datetime]$StartTime,
        [bool]$SkipBuild
    )

    if (-not $SkipBuild) {
        # --- STEP 3: npm run build (captured, one retry on the known ENOENT) ----
        function Invoke-Build {
            $p = Start-Process -FilePath "cmd.exe" `
                -ArgumentList "/c npm run build > `"$BuildLogPath`" 2>&1" `
                -WorkingDirectory $DashDir -WindowStyle Hidden -PassThru
            $p.WaitForExit()
            return $p.ExitCode
        }

        Emit-Log "npm run build starting (log: $BuildLogPath)"
        $buildExit = Invoke-Build
        $buildLog = if (Test-Path $BuildLogPath) { Get-Content $BuildLogPath -Raw } else { "" }

        if ($buildExit -ne 0 -and $buildLog -match "ENOENT.*build-manifest\.json") {
            Emit-Log "build failed with known transient ENOENT (build-manifest.json) -- retrying once"
            $buildExit = Invoke-Build
            $buildLog = if (Test-Path $BuildLogPath) { Get-Content $BuildLogPath -Raw } else { "" }
        }

        if ($buildExit -ne 0) {
            $lines = ($buildLog -split "`r?`n") | Select-Object -Last 30
            $tail = ($lines -join "`n")
            return @{ Code = 20; Line = "DEPLOY FAILED stage=build reason=npm run build exit=$buildExit`n--- last 30 log lines ---`n$tail" }
        }
        Emit-Log "npm run build OK"
    } else {
        Emit-Log "[SkipBuild] skipping npm run build (test-only path)"
    }

    # --- STEP 5: wait BUILD_ID settle, restart, poll /api/hq ----------------
    if (-not (Test-Path $BuildIdPath)) {
        $skipNote = if ($SkipBuild) { " (SkipBuild)" } else { "" }
        return @{ Code = 20; Line = "DEPLOY FAILED stage=build reason=build succeeded but BUILD_ID missing at $BuildIdPath$skipNote" }
    }
    $newBuildId = (Get-Content $BuildIdPath -Raw).Trim()

    if (-not $SkipBuild) {
        $settleDeadline = (Get-Item $BuildIdPath).LastWriteTime.AddSeconds(35)
        while ((Get-Date) -lt $settleDeadline) {
            Start-Sleep -Seconds 2
        }
    }

    function Invoke-KeepaliveHidden {
        # -LockOwnerPid $PID (this deploy script's own pid, matching the pid= token
        # this same process wrote into $lockPath in STEP 2) tells the keepalive's
        # STALE-BUILD GUARD that WE are the lock holder asking for the restart --
        # otherwise the guard sees dashboard/.build.lock < 15 min old (our own lock,
        # still held) and refuses to restart, and this deploy polls until it times
        # out at stage=restart (the 2026-09-15 self-deadlock, see file header).
        Start-Process -FilePath "powershell.exe" `
            -ArgumentList "-NonInteractive", "-WindowStyle", "Hidden", "-File", "`"$KeepaliveScriptPath`"", "-LockOwnerPid", "$PID" `
            -WindowStyle Hidden | Out-Null
    }

    Emit-Log "running keepalive hidden to restart dashboard on new build (BUILD_ID=$newBuildId)"
    Invoke-KeepaliveHidden

    # Both the deadline and the re-run-once point are measured from the START
    # OF POLLING, never from script start (bug #2, see file header). The
    # re-run point keeps the original 60s-of-120s = 1:2 ratio so a test can
    # pass a short -RestartWaitSec and get a proportionally scaled-down wait.
    $pollStartTime = Get-Date
    $reRanThresholdSec = [math]::Max(5, [int]([math]::Floor($RestartWaitSec / 2)))
    $pollDeadline = $pollStartTime.AddSeconds($RestartWaitSec)
    $reRan = $false
    $matched = $false
    $gotAnyResponse = $false
    while ((Get-Date) -lt $pollDeadline) {
        try {
            $resp = Invoke-WebRequest -Uri $ApiUrl -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
            $json = $resp.Content | ConvertFrom-Json
            $gotAnyResponse = $true
            if ($json.build_id -eq $newBuildId) {
                $matched = $true
                break
            }
        } catch {
            # server not answering yet -- expected during restart, keep polling
        }

        $elapsedSincePollStart = (New-TimeSpan -Start $pollStartTime -End (Get-Date)).TotalSeconds
        if (-not $reRan -and $elapsedSincePollStart -ge $reRanThresholdSec) {
            Emit-Log "no build_id match by ${reRanThresholdSec}s of polling -- re-running keepalive once"
            Invoke-KeepaliveHidden
            $reRan = $true
        }
        Start-Sleep -Seconds 5
    }

    if (-not $matched) {
        if ($gotAnyResponse) {
            return @{ Code = 31; Line = "DEPLOY FAILED stage=restart reason=/api/hq build_id never matched .next/BUILD_ID ($newBuildId) within ${RestartWaitSec}s of polling (reran_keepalive=$reRan)" }
        } else {
            return @{ Code = 30; Line = "DEPLOY FAILED stage=restart reason=$ApiUrl never produced a live response within ${RestartWaitSec}s of polling (reran_keepalive=$reRan)" }
        }
    }

    $elapsed = [int]((Get-Date) - $StartTime).TotalSeconds
    return @{ Code = 0; Line = "DEPLOY OK build_id=$newBuildId elapsed_s=$elapsed reran_keepalive=$reRan" }
}

$exitCode = 0
$finalLine = ""
try {
    $result = Invoke-BuildAndRestart -DashDir $dashDir -BuildLogPath $buildLogPath -BuildIdPath $buildIdPath `
        -KeepaliveScriptPath $keepaliveScriptPath -ApiUrl $ApiUrl -RestartWaitSec $RestartWaitSec `
        -StartTime $startTime -SkipBuild:$SkipBuild.IsPresent
    $exitCode = $result.Code
    $finalLine = $result.Line
} finally {
    # --- STEP 4 (always): remove lock ---------------------------------------
    if ($lockAcquired -and (Test-Path $lockPath)) {
        Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
        Emit-Log "lock released"
    }
}

Finish $exitCode $finalLine
