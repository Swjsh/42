# prepare-for-tomorrow.ps1 - one-shot pre-trading-day readiness + safety snapshot.
# Launched by PREPARE-FOR-TOMORROW.bat (double-click). PowerShell 5.1, ASCII only.
# Never hard-stops: reports every check, counts blockers, gives a final verdict.

$ErrorActionPreference = "Continue"
$repo = "C:\Users\jackw\Desktop\42"
Set-Location $repo
$state = Join-Path $repo "automation\state"
$script:fail = 0
function Ok($m)   { Write-Host "  [OK]  $m" -ForegroundColor Green }
function Bad($m)  { Write-Host "  [!!]  $m" -ForegroundColor Red; $script:fail++ }
function Info($m) { Write-Host "  [..]  $m" -ForegroundColor Gray }

Write-Host "==================================================================="
Write-Host " GAMMA - PREPARE FOR TOMORROW   $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
Write-Host "==================================================================="

# ---- 1. Canonical params.json valid + v15 exits (C3 reconciliation) ----
Write-Host "`n[1/6] Canonical params.json..."
try {
    $p = Get-Content (Join-Path $state 'params.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Ok "parses OK (rule_version $($p.rule_version))"
    if ($p.tp1_qty_fraction -eq 0.5)        { Ok "tp1_qty_fraction = 0.5" }       else { Bad "tp1_qty_fraction = $($p.tp1_qty_fraction) (expected 0.5)" }
    if ($p.runner_max_premium_pct -eq 2.5)  { Ok "runner_max_premium_pct = 2.5" } else { Bad "runner_max_premium_pct = $($p.runner_max_premium_pct) (expected 2.5)" }
    if ($p.premium_stop_pct_bear -eq -0.2)  { Ok "premium_stop_pct_bear = -0.20" } else { Bad "premium_stop_pct_bear missing/!= -0.20" }
} catch { Bad "params.json INVALID JSON: $($_.Exception.Message)" }

# ---- 2. Dual-account params present ----
Write-Host "`n[2/6] Account params..."
foreach ($pair in @(@("params_safe.json","Safe"), @("aggressive\params.json","Bold"))) {
    $fp = Join-Path $state $pair[0]
    if (Test-Path $fp) {
        try { Get-Content $fp -Raw -Encoding UTF8 | ConvertFrom-Json | Out-Null; Ok "$($pair[1]) params present + valid" }
        catch { Bad "$($pair[1]) params INVALID JSON" }
    } else { Info "$($pair[1]) params not found at $($pair[0])" }
}

# ---- 3. Engine self-tests (proves the OP-11 / C3 / guard fixes) ----
Write-Host "`n[3/6] Engine self-tests (OP-11 loop + graduated guards)..."
$py = Join-Path $repo "backtest\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
Push-Location (Join-Path $repo "backtest")
& $py -m pytest tests/test_op11_loop.py tests/test_graduated_guards.py -q 2>&1 | Select-Object -Last 4 | ForEach-Object { Info $_ }
if ($LASTEXITCODE -eq 0) { Ok "all engine tests passed" }
else { Bad "engine tests failed OR deps missing -> run: `"$py`" -m pip install pytest scipy pandas numpy" }
Pop-Location

# ---- 4. Freshness (staleness should be LOUD) ----
Write-Host "`n[4/6] Freshness watchdog..."
$wd = Join-Path $repo "setup\scripts\freshness-watchdog.ps1"
if (Test-Path $wd) { & $wd } else { Info "freshness-watchdog.ps1 not found" }

# ---- 5. Tomorrow's scheduled tasks will fire ----
Write-Host "`n[5/6] Scheduled tasks (premarket + heartbeat)..."
$tasks = Get-ScheduledTask -TaskName 'Gamma_*' -ErrorAction SilentlyContinue
if ($tasks) {
    Ok "$($tasks.Count) Gamma_* tasks registered"
    foreach ($t in @('Gamma_Premarket','Gamma_Heartbeat','Gamma_LaunchTV','Gamma_EodFlatten')) {
        $found = $tasks | Where-Object { $_.TaskName -eq $t }
        if ($found) {
            if ($found.State -eq 'Disabled') { Bad "$t is DISABLED" } else { Ok "$t ready ($($found.State))" }
        } else { Bad "$t MISSING - it will not fire tomorrow" }
    }
} else { Bad "NO Gamma_* scheduled tasks - premarket/heartbeat will not run tomorrow" }

# ---- 6. Git safety snapshot (repairs broken .git, commits, tries push) ----
Write-Host "`n[6/6] Git safety snapshot..."
$gitOk = $false
if (Test-Path ".git") { git status 2>&1 | Out-Null; $gitOk = ($LASTEXITCODE -eq 0) }
if (-not $gitOk) {
    Info "no usable .git - running setup-git.ps1 (first-time / repair)"
    & (Join-Path $repo "setup\setup-git.ps1")
} else {
    git add -A 2>&1 | Out-Null
    if (git status --porcelain) {
        git commit -m "evening snapshot $(Get-Date -Format yyyy-MM-dd)" 2>&1 | Out-Null
        Ok "committed evening snapshot"
    } else { Ok "git clean (nothing to commit)" }
    git push 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Ok "pushed to GitHub" } else { Info "push skipped - run 'git push' once authenticated (GitHub PAT)" }
}

# ---- Verdict ----
Write-Host "`n==================================================================="
if ($script:fail -eq 0) { Write-Host " READY FOR TOMORROW - no blockers found." -ForegroundColor Green }
else { Write-Host " $($script:fail) BLOCKER(S) above (marked [!!]) - fix before open." -ForegroundColor Red }
Write-Host "==================================================================="
exit 0
