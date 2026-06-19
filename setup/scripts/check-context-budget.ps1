# check-context-budget.ps1
# Tier 0 lean guard for always-loaded context (CLAUDE.md). Two jobs:
#   1) ALWAYS: score the file via context_audit.py, refresh
#      automation/state/context-budget.json, print a colored status line.
#      Fails OPEN -- never breaks the caller (CLAUDE.md OP-25: no automated
#      process may block J's session).
#   2) -AutoFix: if status is RED and it is OUTSIDE market hours and not in a
#      rate-limit cooldown, TRIP Claude to run the context-leanness skill via
#      Invoke-ClaudeWithRetry (reuses the full harness: lock, disk, retry, hidden).
#
# PowerShell 5.1 compatible. No em-dashes (repo rule).
# Benchmarks/scores live in context_audit.py -- this script does not duplicate them.
#
# Usage:
#   powershell -File setup\scripts\check-context-budget.ps1            # score + alert
#   powershell -File setup\scripts\check-context-budget.ps1 -AutoFix   # + self-heal on RED
# Exit: always 0 (fail-open). Read status from the state json if you need it.

param(
    [int]$BudgetTokens = 8000,
    [switch]$AutoFix
)
$ErrorActionPreference = "Continue"

. (Join-Path $PSScriptRoot "_shared.ps1")   # WorkDir, ClaudeExe, Get-EtNow, Test-MarketHours, Test-RateLimitCooldown, Invoke-ClaudeWithRetry, Write-TaskLog

$repo  = $WorkDir
$audit = Join-Path $repo "setup\scripts\context_audit.py"
$statePath = Join-Path $repo "automation\state\context-budget.json"
$task  = "context_guard"

# Resolve a python interpreter (engine is stdlib + optional tiktoken).
$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) { $pythonExe = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $pythonExe) {
    Write-Host "context_guard: python not found -- skipping (fail open)" -ForegroundColor Yellow
    exit 0
}

# 1) Score + refresh state (read-only on CLAUDE.md). Fail open on any error.
try {
    & $pythonExe $audit check --repo $repo --budget $BudgetTokens | Out-Null
} catch {
    Write-Host "context_guard: audit failed -- $($_.Exception.Message) (fail open)" -ForegroundColor Yellow
    exit 0
}

$status = "UNKNOWN"; $tokens = "?"; $pct = "?"
if (Test-Path $statePath) {
    try {
        $st = Get-Content $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $status = $st.status; $tokens = $st.tokens; $pct = $st.pct
    } catch { }
}

$color = switch ($status) { "GREEN" {"Green"} "YELLOW" {"Yellow"} "RED" {"Red"} default {"Gray"} }
Write-Host ("context_guard: {0}  CLAUDE.md {1} tok / {2} budget ({3}%)" -f $status, $tokens, $BudgetTokens, $pct) -ForegroundColor $color
Write-TaskLog -TaskName $task -Message ("status={0} tokens={1} pct={2}" -f $status, $tokens, $pct)

# 2) Self-heal on RED, only when -AutoFix is passed (heartbeat/session-start do NOT pass it).
if (-not $AutoFix) { exit 0 }
if ($status -ne "RED") { exit 0 }

$etNow = Get-EtNow
if ((Test-WeekDay -Et $etNow) -and (Test-MarketHours -Et $etNow)) {
    Write-TaskLog -TaskName $task -Message "RED but market hours -- alert only, no edit (Rule 9 / no mid-session changes)"
    Write-Host "context_guard: RED during market hours -- alert only (will self-heal after close)" -ForegroundColor Yellow
    exit 0
}
$cooldown = Test-RateLimitCooldown -TaskName $task
if ($cooldown) {
    Write-TaskLog -TaskName $task -Message "RED but rate-limit cooldown active until $($cooldown.ToString('HH:mm')) ET -- alert only"
    exit 0
}

$prompt = Join-Path $repo "automation\prompts\context-leanness-autofix.md"
if (-not (Test-Path $prompt)) {
    Write-TaskLog -TaskName $task -Message "RED but autofix prompt missing: $prompt"
    exit 0
}
Write-TaskLog -TaskName $task -Message "RED + after-hours -- tripping Claude to run context-leanness skill"
Write-Host "context_guard: RED -- tripping Claude to run the context-leanness skill..." -ForegroundColor Cyan
Invoke-ClaudeWithRetry -PromptFile $prompt -TaskName $task -MaxBudgetUsd 1.5 -Model "sonnet" -TimeoutSec 360 -Effort "medium" -MaxRateLimitWaitSec 3600 | Out-Null
exit 0
