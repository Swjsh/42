# hook-emit.ps1 — Claude Code hook emitter for Gamma Cockpit
# Called by PreToolUse / PostToolUse / Stop hooks.
# Reads hook input from $env:CLAUDE_TOOL_INPUT (JSON) or stdin, POSTs to cockpit.
# Silent — never blocks Claude; cockpit being down is NOT an error.

param(
    [string]$HookType = "tool"
)

$ErrorActionPreference = 'SilentlyContinue'

try {
    # Read hook payload from stdin (Claude pipes it as JSON)
    $raw = $null
    if ($null -ne $input) {
        $raw = $input | Out-String
    }
    if ([string]::IsNullOrWhiteSpace($raw)) {
        $raw = '{}'
    }

    $payload = $raw | ConvertFrom-Json -ErrorAction SilentlyContinue
    if ($null -eq $payload) { $payload = @{} }

    # Build compact event
    $evt = @{
        hook_type  = $HookType
        session_id = if ($payload.session_id) { $payload.session_id } elseif ($env:CLAUDE_SESSION_ID) { $env:CLAUDE_SESSION_ID } else { "unknown" }
        tool_name  = if ($payload.tool_name) { $payload.tool_name } else { "" }
        tool_input = if ($payload.tool_input) { $payload.tool_input } else { $null }
        ts         = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    }

    $body = $evt | ConvertTo-Json -Compress -Depth 4

    # POST to cockpit — 500ms timeout, fire-and-forget
    $null = Invoke-WebRequest `
        -Uri "http://localhost:4500/event" `
        -Method POST `
        -Body $body `
        -ContentType "application/json" `
        -TimeoutSec 1 `
        -UseBasicParsing `
        -ErrorAction SilentlyContinue
} catch {
    # Silent — cockpit being offline must never block Claude
}
