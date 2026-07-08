# launch_claude_local.ps1 — Claude Code on the LOCAL brain (zero Anthropic tokens).
# Ollama natively serves the Anthropic Messages API (/v1/messages), so the real
# `claude` binary runs against the RTX 5080 with two env vars — no router/proxy.
# Verified 2026-07-08. Doctrine: markdown/planning/BRAIN-SOVEREIGNTY.md sec 4.
#
# Usage:
#   .\setup\launch_claude_local.ps1                      # interactive, qwen3.6:35b
#   .\setup\launch_claude_local.ps1 -Model qwen3:14b     # faster, dumber
#   .\setup\launch_claude_local.ps1 -Prompt "..."        # one-shot print mode
param(
    [string]$Model = "qwen3.6:35b",
    [string]$Prompt = ""
)

# Fail loud if Ollama is down (C7: no silent degradation to a confusing auth error)
try {
    $null = Invoke-RestMethod -Uri "http://localhost:11434/api/version" -TimeoutSec 3
} catch {
    Write-Host "OLLAMA NOT RUNNING — start the Ollama app first, then re-run." -ForegroundColor Red
    exit 1
}

$env:ANTHROPIC_BASE_URL = "http://localhost:11434"
$env:ANTHROPIC_AUTH_TOKEN = "ollama"
$env:ANTHROPIC_MODEL = $Model
$env:ANTHROPIC_SMALL_FAST_MODEL = "qwen3:14b"

Write-Host "Local brain: $Model via http://localhost:11434 (zero Anthropic tokens)" -ForegroundColor Green
if ($Prompt) {
    claude -p $Prompt --model $Model
} else {
    claude --model $Model
}
