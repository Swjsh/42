# Futures Heartbeat tick — Gamma Futures Edition (MNQ/MES, watch-only until TT approved).
# Task Scheduler fires every 3 min from 09:30 to 15:55 ET weekdays.
# WATCH-ONLY: logs would-be trades while Tastytrade account is under review (3-5 days).
# Flip WATCH_ONLY = False in backtest/futures/tastytrade_paper.py after account approval.

. "$PSScriptRoot\_shared.ps1"

# Load Tastytrade sandbox credentials into process env so claude subprocess inherits them
$EnvFile = Join-Path $WorkDir ".env.tastytrade"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^([^#=][^=]*)=(.+)$') {
            [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process')
        }
    }
}

$task = "futures-heartbeat"
$et   = Get-EtNow

if (-not (Test-WeekDay $et))  { exit 0 }
if (Test-HolidayFromAlpaca)   { exit 0 }
if (-not (Test-MarketHours -Et $et -StartHour 9 -StartMin 30 -EndHour 15 -EndMin 55)) { exit 0 }

# Skip EOD-flatten window — let futures-eod-flatten handle it
if (Test-MarketHours -Et $et -StartHour 15 -StartMin 55 -EndHour 23 -EndMin 59) {
    Write-TaskLog -TaskName $task -Message "SKIP in EOD window (>=15:55 ET)"
    exit 0
}

$cooldownReset = Test-RateLimitCooldown -TaskName $task
if ($cooldownReset) {
    Write-TaskLog -TaskName $task -Message "SKIP rate_limit_cooldown reset_at=$($cooldownReset.ToString('HH:mm')) ET"
    exit 0
}

$PositionFile = Join-Path $WorkDir "automation\state\futures\position.json"

# Pre-tick state repair
Repair-StateFiles -TaskName $task | Out-Null

# Model: Haiku for watch-only watch ticks, Sonnet when position is open (live paper trade)
$model = "claude-haiku-4-5-20251001"
if (Test-Path $PositionFile) {
    try {
        $pos = Get-Content $PositionFile -Raw | ConvertFrom-Json
        if ($pos.side -and $pos.side -ne "flat" -and $pos.qty -gt 0) {
            $model = "claude-sonnet-4-6"
            Write-TaskLog -TaskName $task -Message "Futures position open ($($pos.side) qty=$($pos.qty)) - escalating to Sonnet"
        }
    } catch {
        Write-TaskLog -TaskName $task -Message "WARN futures position.json unreadable"
    }
}

# Simple throttle: every 3rd tick when no position (watch-only is cheap but no need to spam)
$marketOpen  = [DateTime]::new($et.Year, $et.Month, $et.Day, 9, 30, 0)
$tickIndex   = [int][Math]::Floor(($et - $marketOpen).TotalMinutes / 3)
$positionOpen = ($model -eq "claude-sonnet-4-6")

if (-not $positionOpen -and ($tickIndex % 2) -ne 0) {
    Write-TaskLog -TaskName $task -Message "SKIP throttle idx=$tickIndex (every-other tick, no position)"
    exit 0
}

$tickTimeout = if ($model -eq "claude-sonnet-4-6") { 180 } else { 160 }

Write-TaskLog -TaskName $task -Message "FIRE futures-heartbeat model=$model idx=$tickIndex watch_only=true"

$preStats = Repair-StateFiles -TaskName $task

$exit = Invoke-Claude `
    -PromptFile (Join-Path $WorkDir "automation\prompts\futures-heartbeat.md") `
    -TaskName $task `
    -MaxBudgetUsd 0.25 `
    -Model $model `
    -TimeoutSec $tickTimeout

$postStats = Repair-StateFiles -TaskName $task
Write-TaskLog -TaskName $task -Message "Done exitCode=$exit corrupted=$($postStats.Corrupted)"
