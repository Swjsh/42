# test_keepalive_lock_ownership.ps1 -- unit-style proof for the 2026-09-15
# self-deadlock fix's ownership handshake in run-dashboard-keepalive.ps1's
# STALE-BUILD GUARD (-LockOwnerPid).
#
# WHY A SEPARATE UNIT TEST INSTEAD OF DRIVING THE REAL SCRIPT: unlike
# dashboard_deploy.ps1, run-dashboard-keepalive.ps1 has no -DashboardDir /
# -Port override -- it always targets the real dashboard dir (via
# _shared.ps1's $WorkDir) and always HTTP-probes real 127.0.0.1:3000, and its
# non-alive fallthrough path (existingPid -eq 0) spawns a REAL node process
# with NO -DryRun gate at all. Driving the real script from a test harness
# risks actually starting or restarting the live dashboard depending on
# whatever is answering :3000 at the moment the test runs -- explicitly
# forbidden for this fix (the orchestrator owns that process separately).
#
# So this test isolates and exercises the exact matching primitive the fix
# added (Select-String against the lock file's `pid=<n>` token) against a
# real temp file on disk, proving the three cases called for:
#   1. lock owned by caller pid  -> stale=true  (bypass applies)
#   2. lock owned by a DIFFERENT pid -> stale=false (still blocks, as before)
#   3. no -LockOwnerPid passed (0) -> stale=false with a fresh lock (unchanged
#      default behavior -- the bypass never triggers unless asked for)
#
# Mirrors the identical logic block added to run-dashboard-keepalive.ps1
# (STALE-BUILD GUARD, lockIsFresh computation) line-for-line so a change to
# one without the other is caught by a future diff review.
#
# Run with: powershell -File setup\scripts\test_keepalive_lock_ownership.ps1

$ErrorActionPreference = "Stop"
$anyFail = $false

function Test-LockFreshness {
    # Exact mirror of the block in run-dashboard-keepalive.ps1's STALE-BUILD
    # GUARD (lockIsFresh computation, ownership bypass sub-block).
    param(
        [string]$LockPath,
        [double]$LockAgeMin,
        [int]$LockOwnerPid
    )
    $lockIsFresh = $false
    if ($LockAgeMin -lt 15) { $lockIsFresh = $true }
    if ($lockIsFresh -and $LockOwnerPid -gt 0) {
        $lockOwnerMatch = Select-String -Path $LockPath -Pattern "pid=$LockOwnerPid(\s|$)" -Quiet -ErrorAction SilentlyContinue
        if ($lockOwnerMatch) {
            $lockIsFresh = $false
        }
    }
    return $lockIsFresh
}

function Assert-Case {
    param([string]$Name, [bool]$Actual, [bool]$Expected)
    $pass = ($Actual -eq $Expected)
    if (-not $pass) { $script:anyFail = $true }
    $status = if ($pass) { "PASS" } else { "FAIL" }
    Write-Host "[$status] $Name -- lockIsFresh=$Actual (expected $Expected)"
}

$tmpDir = Join-Path $env:TEMP ("keepalive-lock-test-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
try {
    $lockPath = Join-Path $tmpDir ".build.lock"

    # --- Case 1: lock owned by caller pid -> stale=true (bypass applies) ----
    $callerPid = 4242
    Set-Content -Path $lockPath -Value "pid=$callerPid tag=deploy-self start=2026-09-15T04:14:00" -NoNewline -Encoding utf8
    $r1 = Test-LockFreshness -LockPath $lockPath -LockAgeMin 2.0 -LockOwnerPid $callerPid
    Assert-Case -Name "1: lock owned by caller pid ($callerPid) -> stale=true (lockIsFresh=false)" -Actual $r1 -Expected $false

    # --- Case 2: lock owned by a DIFFERENT pid -> stale=false (still blocks) -
    $otherPid = 9999
    $r2 = Test-LockFreshness -LockPath $lockPath -LockAgeMin 2.0 -LockOwnerPid $otherPid
    Assert-Case -Name "2: lock owned by other pid ($otherPid, lock says $callerPid) -> stale=false (lockIsFresh=true)" -Actual $r2 -Expected $true

    # --- Case 3: no -LockOwnerPid (0, unchanged default) -> fresh lock blocks -
    $r3 = Test-LockFreshness -LockPath $lockPath -LockAgeMin 2.0 -LockOwnerPid 0
    Assert-Case -Name "3: no -LockOwnerPid passed (0) -> stale=false with fresh lock (lockIsFresh=true)" -Actual $r3 -Expected $true

    # --- Bonus: pid substring safety -- pid=42 must not falsely match caller 4242
    Set-Content -Path $lockPath -Value "pid=42 tag=other start=2026-09-15T04:14:00" -NoNewline -Encoding utf8
    $r4 = Test-LockFreshness -LockPath $lockPath -LockAgeMin 2.0 -LockOwnerPid $callerPid
    Assert-Case -Name "4: lock pid=42 vs caller pid=4242 (substring collision guard) -> stale=false (lockIsFresh=true)" -Actual $r4 -Expected $true

    # --- Bonus: stale lock (>=15min) is never "fresh" regardless of ownership -
    $r5 = Test-LockFreshness -LockPath $lockPath -LockAgeMin 20.0 -LockOwnerPid 0
    Assert-Case -Name "5: lock age 20min (>=15min) -> stale=false unconditionally (lockIsFresh=false)" -Actual $r5 -Expected $false
} finally {
    Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
}

Write-Host ""
if ($anyFail) {
    Write-Host "TEST HARNESS: FAIL"
    exit 1
} else {
    Write-Host "TEST HARNESS: PASS"
    exit 0
}
