# Gamma Crypto Heartbeat runner - BTC/USD EMA ribbon scalper (24/7, watch-only).
# Task Scheduler fires every 15 min via Gamma_CryptoHeartbeat.
# Watch-only until 20+ would-be trades with WR >= 45%.

. "$PSScriptRoot\_shared.ps1"

$task    = "Gamma_CryptoHeartbeat"
$Prompt  = Join-Path $WorkDir "automation\prompts\crypto-heartbeat.md"
$StateDir = Join-Path $WorkDir "automation\state\crypto"
$AccountFile = Join-Path $StateDir "account.json"
$PositionFile = Join-Path $StateDir "position.json"

# Validate prompt exists
if (-not (Test-Path $Prompt)) {
    Write-TaskLog -TaskName $task -Message "ERROR: crypto-heartbeat.md not found at $Prompt"
    exit 1
}

# Repair state files before tick
Repair-StateFiles -TaskName $task | Out-Null

# Kill switch check
if (Test-Path $AccountFile) {
    try {
        $acct = Get-Content $AccountFile -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        $killDollar = $acct.day_start_equity * 0.10
        if ($acct.daily_pnl -le -$killDollar) {
            Write-TaskLog -TaskName $task -Message "KILL_SWITCH: daily_pnl=$($acct.daily_pnl) <= -$killDollar. Skipping tick."
            exit 0
        }
    } catch {
        Write-TaskLog -TaskName $task -Message "WARN: account.json unreadable - proceeding"
    }
}

# Model: Sonnet when position is open, Haiku otherwise
$model = "claude-haiku-4-5-20251001"
if (Test-Path $PositionFile) {
    try {
        $pos = Get-Content $PositionFile -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        if ($pos.side -and $pos.side -ne "flat" -and $pos.qty_crypto -gt 0) {
            $model = "claude-sonnet-4-6"
            Write-TaskLog -TaskName $task -Message "Crypto position open ($($pos.side) qty=$($pos.qty_crypto)) - escalating to Sonnet"
        }
    } catch {
        Write-TaskLog -TaskName $task -Message "WARN: position.json unreadable"
    }
}

$timeout = if ($model -eq "claude-sonnet-4-6") { 180 } else { 120 }

Write-TaskLog -TaskName $task -Message "FIRE crypto-heartbeat model=$model"

$exit = Invoke-Claude `
    -PromptFile $Prompt `
    -TaskName $task `
    -MaxBudgetUsd 0.08 `
    -Model $model `
    -TimeoutSec $timeout

$postStats = Repair-StateFiles -TaskName $task
Write-TaskLog -TaskName $task -Message "Done exitCode=$exit corrupted=$($postStats.Corrupted)"
