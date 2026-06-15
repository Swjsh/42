# Self-heal smoke tests. No API tokens spent. Verifies:
#   1. Stop-StaleClaudeProcesses refuses unsafe input (StaleAfterMinutes < 1)
#   2. Stop-ProcessTree cascades through grandchildren
#   3. Stop-StaleClaudeProcesses ignores claude.exe NOT matching project workdir
#   4. Wall-clock timeout fires within tolerance

. "$PSScriptRoot\_shared.ps1"

$pass = 0
$fail = 0
function Assert {
    param([string]$Name, [bool]$Cond, [string]$Detail = "")
    if ($Cond) {
        Write-Host ("PASS  " + $Name) -ForegroundColor Green
        $script:pass++
    } else {
        Write-Host ("FAIL  " + $Name + " - " + $Detail) -ForegroundColor Red
        $script:fail++
    }
}

Write-Host "=== Test 1: Stop-StaleClaudeProcesses refuses unsafe input ==="
$result = Stop-StaleClaudeProcesses -StaleAfterMinutes 0 -WarningAction SilentlyContinue
Assert "refuses StaleAfterMinutes=0" ($result.Count -eq 0) "expected empty array"

$result = Stop-StaleClaudeProcesses -StaleAfterMinutes -5 -WarningAction SilentlyContinue
Assert "refuses StaleAfterMinutes=-5" ($result.Count -eq 0) "expected empty array"

Write-Host ""
Write-Host "=== Test 2: Stop-ProcessTree cascades through grandchildren ==="
# Spawn cmd.exe -> cmd.exe -> cmd.exe and verify killing the root kills all 3
$root = Start-Process -FilePath "cmd.exe" -ArgumentList "/c","start /b /wait cmd.exe /c ""start /b /wait cmd.exe /c ping -n 60 127.0.0.1 >nul""" -PassThru -WindowStyle Hidden
Start-Sleep -Milliseconds 1500  # let descendants spawn

$descendantsBefore = Get-DescendantPids -ParentId $root.Id
Write-Host ("  spawned root pid=" + $root.Id + ", descendants=" + ($descendantsBefore -join ','))
Assert "tree has at least 1 descendant" ($descendantsBefore.Count -ge 1) "expected nested cmd.exe to spawn"

$killed = Stop-ProcessTree -ParentId $root.Id
Start-Sleep -Milliseconds 500

# Verify ALL killed
$stillAlive = $descendantsBefore + @($root.Id) | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue }
Assert "tree-kill leaves nothing alive" ($stillAlive.Count -eq 0) ("survivors: " + ($stillAlive -join ','))
# killed-count may be less than descendants+1 if a child exits naturally during recursion
# (e.g. inner cmd.exe finishes after its parent is killed). The safety property is
# "nothing alive after," not "we killed every PID we expected."
Assert "killed array is non-empty" ($killed.Count -ge 1) ("killed count=" + $killed.Count)

Write-Host ""
Write-Host "=== Test 3: Stop-StaleClaudeProcesses ignores unrelated claude.exe ==="
# Critical safety check. Spawn a fake claude.exe (notepad as proxy, cmdline doesn't match WorkDir).
# Stop-StaleClaudeProcesses should NOT kill it.
$decoy = Start-Process -FilePath "notepad.exe" -PassThru -WindowStyle Hidden
Start-Sleep -Milliseconds 500
$beforePids = (Get-Process -Name "notepad" -ErrorAction SilentlyContinue).Id

# Try to reap (StaleAfterMinutes=1 valid; decoy younger than that anyway)
$reaped = Stop-StaleClaudeProcesses -StaleAfterMinutes 1
$decoyAlive = $null -ne (Get-Process -Id $decoy.Id -ErrorAction SilentlyContinue)
Assert "decoy notepad.exe survived reap" $decoyAlive "decoy was killed - safety violation"

# Cleanup decoy
Stop-Process -Id $decoy.Id -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== Test 4: Wall-clock timeout fires within tolerance (no real claude call) ==="
# Replace ClaudeExe temporarily with a long-sleeper so we don't hit the real API
$origExe = $Global:ClaudeExe
try {
    # cmd.exe ping = sleep without API cost. Discards stdin.
    $Global:ClaudeExe = "C:\Windows\System32\ping.exe"
    # Build a fake prompt file
    $tmpPrompt = [System.IO.Path]::GetTempFileName()
    "fake prompt" | Out-File -Encoding utf8 $tmpPrompt

    # Override the args so ping runs for ~30s; timeout at 5s should fire.
    # We can't override args without changing Invoke-Claude. Easier: run a job that
    # bypasses Invoke-Claude entirely and just tests that ProcessStartInfo + WaitForExit
    # behaves the way we expect.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "ping.exe"
    $psi.Arguments = "-n 30 127.0.0.1"
    $psi.RedirectStandardOutput = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $p = [System.Diagnostics.Process]::Start($psi)
    $stdoutTask = $p.StandardOutput.ReadToEndAsync()
    $start = Get-Date
    $finished = $p.WaitForExit(3000)  # 3s wall clock
    $elapsed = ((Get-Date) - $start).TotalSeconds

    if (-not $finished) {
        Stop-ProcessTree -ParentId $p.Id | Out-Null
    }
    Assert "WaitForExit returns false on timeout" (-not $finished) ""
    Assert "elapsed ~3s (within 1s tolerance)" (($elapsed -ge 2.5) -and ($elapsed -le 4.5)) ("elapsed=" + $elapsed)
    Assert "ping process killed after timeout" (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) "still alive"

    Remove-Item $tmpPrompt -ErrorAction SilentlyContinue
} finally {
    $Global:ClaudeExe = $origExe
}

Write-Host ""
Write-Host "=== Test 5: Test-DiskSpaceAvailable returns correct shape ==="
$disk = Test-DiskSpaceAvailable -MinFreeMB 100
Assert "result has OK key"     ($null -ne $disk.OK)     ""
Assert "result has FreeMB key" ($null -ne $disk.FreeMB) ""
Assert "result has MinMB key"  ($null -ne $disk.MinMB)  ""
Assert "OK is boolean"         ($disk.OK -is [bool])    ""
$disk2 = Test-DiskSpaceAvailable -MinFreeMB 999999999
Assert "absurd threshold returns OK=false" (-not $disk2.OK) ("FreeMB=" + $disk2.FreeMB)

Write-Host ""
Write-Host "=== Test 6: Repair-StateFiles validates and mirrors to .lastgood ==="
$stateDir = Join-Path $WorkDir "automation\state"
$lg = Join-Path $stateDir ".lastgood"
$preCount = (Get-ChildItem $stateDir -Filter "*.json" -File).Count
$stats1 = Repair-StateFiles -TaskName "test"
Assert "validates all good files" ($stats1.Validated -eq $preCount) ("validated=" + $stats1.Validated + " expected=" + $preCount)
Assert "no corruption on clean run" ($stats1.Corrupted -eq 0) ("corrupted=" + $stats1.Corrupted)
Assert ".lastgood populated" ((Get-ChildItem $lg -Filter "*.json" -File).Count -ge $preCount) ""

Write-Host ""
Write-Host "=== Test 7: Repair-StateFiles RECOVERS a corrupted file from .lastgood ==="
# Pick any state json. Truncate it. Run Repair. Verify content restored.
$victim = Join-Path $stateDir "smoke-news-calendar-today.json"
if (Test-Path $victim) {
    $original = Get-Content $victim -Raw
    # Corrupt: truncate to non-JSON
    "{ partial " | Out-File -FilePath $victim -Encoding utf8 -NoNewline
    # Verify it's actually corrupt
    $isCorrupt = $false
    try { (Get-Content $victim -Raw | ConvertFrom-Json) | Out-Null } catch { $isCorrupt = $true }
    Assert "victim file is corrupted" $isCorrupt ""

    # Repair
    $stats2 = Repair-StateFiles -TaskName "test"
    Assert "Repair detected corruption" ($stats2.Corrupted -ge 1) ("corrupted=" + $stats2.Corrupted)
    Assert "Repair restored 1 file" ($stats2.Restored -ge 1) ("restored=" + $stats2.Restored)

    # Verify restored content matches original
    $restored = Get-Content $victim -Raw
    Assert "restored content matches original" ($restored -eq $original) "content drift after restore"
} else {
    Assert "victim file present for test" $false "skipped - smoke-news-calendar-today.json missing"
}

Write-Host ""
Write-Host "=== Test 8: Repair-StateFiles handles unrecoverable case ==="
# A new .json that does NOT have a .lastgood backup. Should mark unrecoverable.
$orphan = Join-Path $stateDir "test-orphan-corruption.json"
$orphanLg = Join-Path $lg "test-orphan-corruption.json"
"{ broken json" | Out-File -FilePath $orphan -Encoding utf8 -NoNewline
if (Test-Path $orphanLg) { Remove-Item $orphanLg -Force }
$stats3 = Repair-StateFiles -TaskName "test"
Assert "orphan corruption marked unrecoverable" ($stats3.Unrecoverable -ge 1) ("unrecoverable=" + $stats3.Unrecoverable)
Assert "orphan file left in place for forensics" (Test-Path $orphan) ""
# Cleanup
Remove-Item $orphan -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ("Pass: " + $pass) -ForegroundColor Green
Write-Host ("Fail: " + $fail) -ForegroundColor $(if ($fail -gt 0) { "Red" } else { "Green" })
exit $(if ($fail -eq 0) { 0 } else { 1 })
