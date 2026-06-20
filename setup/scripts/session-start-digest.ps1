# ============================================================================
# Project Gamma -- Session Start State Digest (Multi-Agent Gamma 2.0)
# ============================================================================
#
# Outputs a compact state summary to stdout. Designed to be prepended to every
# heartbeat/premarket/EOD prompt context by Invoke-Claude (in _shared.ps1).
#
# Replaces the discovery tool-calls Claude would otherwise make to learn:
#   - What rule version is pinned?
#   - Is a position open?
#   - Is the kill-switch tripped?
#   - What's today's P&L?
#   - What were the last 3 actions?
#
# Token savings: ~400-600 tokens per heartbeat tick (no Read tool calls for
# discovery). Across 127 ticks/day x 22 trading days x ~$0.0008/1k = ~$1.10/mo
# negative cost change. Plus latency: each Read call is 200-500ms vs <10ms here.
#
# Source pattern: obra/superpowers SessionStart hook injecting context via
# additionalContext. Gamma adapts: same idea, but implemented in the PowerShell
# harness since Gamma uses claude --print (no SessionStart hook event there).
#
# Doctrine: docs/plans/multi-agent-gamma.md, Big Win #6
# ============================================================================

[CmdletBinding()]
param(
    [string]$WorkDir = "C:\Users\jackw\Desktop\42",
    [switch]$Markdown   # default JSON; if -Markdown, emit a markdown header instead
)

$ErrorActionPreference = 'SilentlyContinue'

function Read-JsonSafe {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    try {
        $raw = Get-Content $Path -Raw
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
        return $raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

$stateDir = Join-Path $WorkDir "automation\state"
$tz = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
$nowEt = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $tz)
$today = $nowEt.ToString("yyyy-MM-dd")

# ---------------------------------------------------------------------------
# Read state files (best-effort; never throw)
# ---------------------------------------------------------------------------
$params         = Read-JsonSafe (Join-Path $stateDir "params.json")
$loopState      = Read-JsonSafe (Join-Path $stateDir "loop-state.json")
$position       = Read-JsonSafe (Join-Path $stateDir "current-position.json")
$circuitBreaker = Read-JsonSafe (Join-Path $stateDir "circuit-breaker.json")
$shadow         = Read-JsonSafe (Join-Path $stateDir "shadow-version.json")
$killSwitch     = Test-Path (Join-Path $stateDir "kill-switch")
$ctxBudget      = Read-JsonSafe (Join-Path $stateDir "context-budget.json")

# ---------------------------------------------------------------------------
# Last 3 actions from decisions.jsonl
# ---------------------------------------------------------------------------
$decisionsFile = Join-Path $stateDir "decisions.jsonl"
$lastActions = @()
if (Test-Path $decisionsFile) {
    try {
        $lines = Get-Content $decisionsFile -Tail 200 -ErrorAction Stop
        foreach ($line in $lines) {
            try {
                $rec = $line | ConvertFrom-Json
                if ($rec.action -and $rec.action -ne "HOLD") {
                    $lastActions += "$($rec.time_et) $($rec.action)"
                }
            } catch { continue }
        }
        $lastActions = $lastActions | Select-Object -Last 3
    } catch { }
}

# ---------------------------------------------------------------------------
# Discord inbox: any unread messages from J? (Multi-Agent Gamma 2.0 bridge)
# Tracks "last seen" via .discord-inbox-watermark.txt so each task only sees
# messages received AFTER the last task fired.
# ---------------------------------------------------------------------------
$inboxFile = Join-Path $stateDir "discord-inbox.jsonl"
$watermarkFile = Join-Path $stateDir ".discord-inbox-watermark.txt"
$unreadMsgs = @()
if (Test-Path $inboxFile) {
    $lastSeen = if (Test-Path $watermarkFile) { (Get-Content $watermarkFile -Raw -ErrorAction SilentlyContinue).Trim() } else { "" }
    $allLines = Get-Content $inboxFile -ErrorAction SilentlyContinue
    $foundLastSeen = [string]::IsNullOrEmpty($lastSeen)  # if no watermark, all messages are "new"
    $newest = $lastSeen
    foreach ($line in $allLines) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try {
            $rec = $line | ConvertFrom-Json -ErrorAction Stop
            if (-not $foundLastSeen) {
                if ($rec.discord_msg_id -eq $lastSeen) { $foundLastSeen = $true }
                continue
            }
            if (-not [string]::IsNullOrWhiteSpace($rec.content)) {
                $unreadMsgs += "[$($rec.author)]: $($rec.content)"
                $newest = $rec.discord_msg_id
            }
        } catch { continue }
    }
    if ($newest -ne $lastSeen) {
        $newest | Out-File -FilePath $watermarkFile -Encoding utf8 -NoNewline
    }
}
# Cap at 5 messages to avoid context bloat
if ($unreadMsgs.Count -gt 5) {
    $unreadMsgs = @("(only showing 5 most recent of $($unreadMsgs.Count))") + ($unreadMsgs | Select-Object -Last 5)
}

# ---------------------------------------------------------------------------
# Build digest
# ---------------------------------------------------------------------------
$digest = [ordered]@{
    generated_at_et = $nowEt.ToString("yyyy-MM-ddTHH:mm:ss")
    today = $today
    weekday = $nowEt.DayOfWeek.ToString()

    rule_version = $(if ($params) { $params.rule_version } else { "UNKNOWN" })
    rule_version_ratified_at = $(if ($params) { $params.rule_version_ratified_at } else { $null })

    kill_switch_active = $killSwitch
    circuit_breaker_tripped = $(if ($circuitBreaker) { [bool]$circuitBreaker.tripped } else { $false })

    position_status = $(if ($position) { $position.status } else { $null })
    position_summary = $(if ($position -and $position.status) {
        "$($position.side) $($position.qty)x SPY $($position.strike)$($position.right) @ $($position.entry_premium)"
    } else { "flat" })

    today_realized_pnl = $(if ($circuitBreaker) {
        if ($circuitBreaker.start_equity_today -and $circuitBreaker.current_equity) {
            [math]::Round($circuitBreaker.current_equity - $circuitBreaker.start_equity_today, 2)
        } else { 0 }
    } else { 0 })

    start_equity_today = $(if ($circuitBreaker) { $circuitBreaker.start_equity_today } else { $null })
    day_trades_used_5d = $(if ($circuitBreaker) { $circuitBreaker.day_trades_used_5d } else { 0 })

    current_mode = $(if ($loopState) { $loopState.current_mode } else { "BASE" })
    last_filter_score = $(if ($loopState) { $loopState.last_filter_score } else { $null })
    developing_setup = $(if ($loopState) { $loopState.developing_setup } else { $null })

    shadow_enabled = $(if ($shadow) { [bool]$shadow.enabled } else { $false })
    shadow_version = $(if ($shadow -and $shadow.enabled) { $shadow.version } else { $null })

    last_3_actions = $lastActions
    first_entry_lock_count = $(if ($loopState -and $loopState.first_entry_lock) { $loopState.first_entry_lock.Count } else { 0 })
}

# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------
if ($Markdown) {
    $md = @"
# STATE DIGEST (auto-injected at session start)

- **Now ET:** $($digest.generated_at_et) ($($digest.weekday))
- **Rule version:** $($digest.rule_version) (ratified $($digest.rule_version_ratified_at))
- **Kill-switch:** $(if ($digest.kill_switch_active) { "ACTIVE -- DO NOT TRADE" } else { "inactive" })
- **Circuit-breaker:** $(if ($digest.circuit_breaker_tripped) { "TRIPPED -- DO NOT TRADE" } else { "ok" })
- **Position:** $($digest.position_summary)
- **Today P&L:** `$$($digest.today_realized_pnl)` (start equity `$$($digest.start_equity_today)`)
- **Day-trades used 5d:** $($digest.day_trades_used_5d)
- **Current mode:** $($digest.current_mode)
- **Shadow:** $(if ($digest.shadow_enabled) { "ENABLED ($($digest.shadow_version))" } else { "off" })
- **Last 3 actions:** $(if ($digest.last_3_actions.Count -gt 0) { $digest.last_3_actions -join " | " } else { "(none)" })
- **First-entry-lock entries:** $($digest.first_entry_lock_count)
- **Context budget:** $(if ($ctxBudget) { "$($ctxBudget.status) ($($ctxBudget.tokens)/$($ctxBudget.budget) tok, $($ctxBudget.pct)%)" } else { "n/a" })

$(if ($unreadMsgs.Count -gt 0) {
"## NEW DISCORD MESSAGES FROM J (since last task tick)

$($unreadMsgs -join "`n")

If any of these change your decision (e.g. J says ``stop`` or ``halt``), honour it.
For routine chat, queue a reply via ``setup\scripts\gamma-notify.ps1 -Message ...`` if a response is warranted (don't reply to every msg -- only when J asked something or when status changed).
Match against ``markdown/doctrine/rationalization-counters.md`` -- if matched, cite the rule + counter and append to ``automation/state/rationalizations.jsonl``.
"
} else {
"_(no new Discord messages from J since last tick)_"
})

You can rely on these values without making Read tool calls. If you NEED a state field not in this digest, then call Read.

---

"@
    Write-Output $md
} else {
    $digest | ConvertTo-Json -Depth 6
}
