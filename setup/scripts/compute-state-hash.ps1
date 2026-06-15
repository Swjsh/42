# ============================================================================
# Project Gamma -- State Hash Computer (Multi-Agent Gamma 2.0 Big Win #7)
# ============================================================================
#
# Computes a SHA-256 hash of the heartbeat-relevant state. Used by
# run-heartbeat.ps1 to skip the Claude call when nothing has materially
# changed since the prior tick.
#
# Hashed fields (anything that would influence the heartbeat decision):
#   - last_bar_timestamp (5m bar)
#   - ribbon spread cents (rounded to 1c granularity)
#   - VIX value rounded to 5 cents
#   - current-position.status (null|open|...)
#   - circuit-breaker.tripped (bool)
#   - developing_setup.score (int)
#
# Source pattern: smtg-ai/claude-squad tmux/tmux.go HasUpdated() -- SHA-256
# of captured pane content used to detect activity without storing raw output.
#
# Output: hex string (sha256), or "ERROR" on failure.
# ============================================================================

[CmdletBinding()]
param(
    [string]$WorkDir = "C:\Users\jackw\Desktop\42"
)

$ErrorActionPreference = 'SilentlyContinue'

function Read-JsonSafe {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    try {
        $raw = Get-Content $Path -Raw
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
        return $raw | ConvertFrom-Json
    } catch { return $null }
}

$stateDir = Join-Path $WorkDir "automation\state"
$loop = Read-JsonSafe (Join-Path $stateDir "loop-state.json")
$pos  = Read-JsonSafe (Join-Path $stateDir "current-position.json")
$cb   = Read-JsonSafe (Join-Path $stateDir "circuit-breaker.json")

# Build the input string. Order MUST be deterministic.
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendFormat("bar={0}|", $(if ($loop) { $loop.last_bar_timestamp } else { 0 }))
[void]$sb.AppendFormat("ribbon={0}|", $(if ($loop -and $loop.ribbon) { $loop.ribbon.spread_cents } else { 0 }))

# VIX rounded to 5 cents -- avoids hash churn from microscopic moves.
$vixVal = if ($loop -and $loop.vix_cache) { [double]$loop.vix_cache.value } else { 0.0 }
$vixRounded = [math]::Round($vixVal * 20) / 20.0
[void]$sb.AppendFormat("vix={0:F2}|", $vixRounded)

[void]$sb.AppendFormat("pos={0}|", $(if ($pos -and $pos.status) { $pos.status } else { "null" }))
[void]$sb.AppendFormat("cb={0}|", $(if ($cb -and $cb.tripped) { "trip" } else { "ok" }))

$score = 0
if ($loop -and $loop.developing_setup -and $loop.developing_setup.score) {
    $score = [int]$loop.developing_setup.score
}
[void]$sb.AppendFormat("score={0}", $score)

$input = $sb.ToString()
$bytes = [System.Text.Encoding]::UTF8.GetBytes($input)
$sha = [System.Security.Cryptography.SHA256]::Create()
try {
    $hash = $sha.ComputeHash($bytes)
    $hex = ($hash | ForEach-Object { $_.ToString("x2") }) -join ''
    Write-Output $hex.Substring(0, 16)  # 16 chars is plenty for change detection
} finally {
    $sha.Dispose()
}
