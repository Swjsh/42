# ============================================================================
# gamma-notify.ps1 -- queue a Discord message to J via the bridge
# ============================================================================
#
# Usage:
#   .\setup\scripts\gamma-notify.ps1 -Message "Premarket failed -- engine drift detected"
#   .\setup\scripts\gamma-notify.ps1 -Message "v15 ratified" -Channel "1484377912328192022"
#
# Just appends a JSONL row to automation/state/discord-outbox.jsonl. The
# discord-bridge.py background process picks it up within 15 seconds.
#
# Best practice: keep messages concise (1-3 lines). Discord caps at 2000 chars
# but humans don't read walls of text from a bot.
# ============================================================================

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Message,

    [string]$Channel = $null,   # default: HQ #general from config

    [switch]$NoMention,         # by default we @-mention J per his 2026-05-09 PM request

    [string]$WorkDir = "C:\Users\jackw\Desktop\42"
)

$outbox = Join-Path $WorkDir "automation\state\discord-outbox.jsonl"
$cfgPath = Join-Path $WorkDir "automation\state\.discord-config.json"

# Prepend @mention if J's user_id is configured and -NoMention not set
$prefix = ""
if (-not $NoMention) {
    try {
        $cfg = Get-Content $cfgPath -Raw -ErrorAction Stop | ConvertFrom-Json
        if ($cfg.user_id) { $prefix = "<@$($cfg.user_id)> " }
    } catch { }
}

$content = $prefix + $Message

$row = [ordered]@{
    queued_at = [DateTime]::UtcNow.ToString("o")
    content   = $content
}
if ($Channel) { $row.channel_id = $Channel }

$json = $row | ConvertTo-Json -Compress
Add-Content -Path $outbox -Value $json -Encoding utf8

Write-Output ("queued: " + ($content.Substring(0, [Math]::Min(80, $content.Length))))
