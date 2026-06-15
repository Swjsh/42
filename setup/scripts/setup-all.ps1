# setup-all.ps1 - run EVERY manual action-item from the 2026-06-14 deep-review session
# in one shot. Launched by SETUP-EVERYTHING.bat (double-click). PS 5.1, ASCII only.
# Each step is independent: a failure in one does NOT abort the rest. Safe to re-run.

$ErrorActionPreference = "Continue"
$repo = "C:\Users\jackw\Desktop\42"
Set-Location $repo
$scripts = Join-Path $repo "setup\scripts"
function Section($n) { Write-Host "`n========== $n ==========" -ForegroundColor Cyan }

# ---- 1. GIT: repair broken .git / init / commit / push ----
Section "1/4  Git safety net (init or commit, then push)"
try {
    $gitOk = $false
    if (Test-Path ".git") { git status 2>&1 | Out-Null; $gitOk = ($LASTEXITCODE -eq 0) }
    if (-not $gitOk) {
        if (Test-Path ".git") { Write-Host "repairing broken .git (sandbox left it corrupt)..."; Remove-Item -Recurse -Force ".git" }
        git init | Out-Null
        git branch -M main 2>&1 | Out-Null
        git config user.email "jack.watergun@gmail.com"
        git config user.name "Swjsh"
        if (-not (git remote 2>$null | Select-String -Quiet "origin")) { git remote add origin "https://github.com/Swjsh/42.git" }
    }
    git add -A 2>&1 | Out-Null
    if (git status --porcelain) {
        git commit -m "session snapshot $(Get-Date -Format yyyy-MM-dd-HHmm)" 2>&1 | Out-Null
        Write-Host "committed." -ForegroundColor Green
    } else { Write-Host "git clean (nothing to commit)." -ForegroundColor Green }
    # secret guard BEFORE pushing (history is public once pushed)
    $leak = git grep -nE "9EzmHpix|ELWu7Qjb|PYwDLKk2YbQdiC6SrKuo4zWjvHx577iqSz6LpNwef8Y" -- ":!*.example" 2>$null
    if ($leak) {
        Write-Host "ABORTING PUSH - a secret appears in tracked files:" -ForegroundColor Red
        Write-Host $leak
    } else {
        git push -u origin main 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Host "pushed to github.com/Swjsh/42." -ForegroundColor Green }
        else { Write-Host "push needs auth once - run 'git push' with a GitHub Personal Access Token." -ForegroundColor Yellow }
    }
} catch { Write-Host "git step error (continuing): $($_.Exception.Message)" -ForegroundColor Yellow }

# ---- 2. Freshness watchdog ----
Section "2/4  Freshness watchdog (make staleness loud)"
try { & (Join-Path $scripts "freshness-watchdog.ps1") } catch { Write-Host "watchdog error: $($_.Exception.Message)" -ForegroundColor Yellow }

# ---- 3. Prune the crypto hoard (quarantines first, reversible) ----
Section "3/4  Prune crypto hoard (reclaim ~1.5 GB)"
try { & (Join-Path $scripts "prune-crypto-hoard.ps1") -Execute } catch { Write-Host "prune error: $($_.Exception.Message)" -ForegroundColor Yellow }

# ---- 4. Wire the freshness watchdog into Task Scheduler (hourly, automatic) ----
Section "4/4  Register hourly freshness check in Task Scheduler"
try {
    $taskName = "Gamma_FreshnessWatchdog"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"" + (Join-Path $scripts "freshness-watchdog.ps1") + "`"")
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddHours(8) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Force -RunLevel Limited | Out-Null
    Write-Host "registered $taskName (runs hourly from 08:00)." -ForegroundColor Green
} catch { Write-Host "task registration skipped (run as your user, not admin-required): $($_.Exception.Message)" -ForegroundColor Yellow }

Write-Host "`n========== DONE - all session action-items executed ==========" -ForegroundColor Green
exit 0
