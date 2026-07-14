# launch_claude_local.ps1 - Claude Code on the LOCAL brain (zero Anthropic tokens).
# Ollama natively serves the Anthropic Messages API (/v1/messages), so the real
# `claude` binary runs against the RTX 5080 - no router/proxy.
# Verified 2026-07-08. Doctrine: markdown/planning/BRAIN-SOVEREIGNTY.md sec 4.
#
# ISOLATED CONFIG (root-caused 2026-07-08): the global ~/.claude/settings.json
# has apiKeyHelper + an env block that FORCE-sets ANTHROPIC_BASE_URL to the
# claude-code-router (127.0.0.1:3456). That router 401s the 'ollama' key. To be
# immune to it, this launcher points CLAUDE_CONFIG_DIR at its OWN config dir
# (setup/ollama/cfg) which has NO apiKeyHelper and NO router - just Ollama. The
# global config is never read, so the router can never hijack the base URL.
#
# claude-local = qwen3.6:35b + num_ctx 40960 + temp 0.7. Rebuild after updates:
#   ollama create claude-local -f setup/ollama/Modelfile.claude-local
#
# SPEED (root-caused 2026-07-08): qwen3.6:35b is thinking-native and "thinks"
# for 30-120s/turn because Claude Code never sends thinking:disabled. Fix =
# nothink_proxy.py on :11435, which injects thinking:disabled into every request
# -> warm answers in ~2-5s. This script auto-starts it. Direct Ollama = :11434.
# --bare keeps the prompt lean (repo 42 ships ~44K ctx tokens -> truncation).
#
# Usage:
#   .\setup\launch_claude_local.ps1                       # interactive, lean (recommended)
#   .\setup\launch_claude_local.ps1 -Prompt "..."         # one-shot print mode
#   .\setup\launch_claude_local.ps1 -Model qwen3:14b      # faster, dumber
param(
    [string]$Model = "claude-local",
    [string]$Prompt = ""
)

# Fail loud if Ollama is down (C7: no silent degradation to a confusing auth error)
try {
    $null = Invoke-RestMethod -Uri "http://localhost:11434/api/version" -TimeoutSec 3
} catch {
    Write-Host "OLLAMA NOT RUNNING - start the Ollama app first, then re-run." -ForegroundColor Red
    exit 1
}

# Ensure the no-think proxy is up on :11435 (auto-start if not). It forces
# thinking:disabled so the model answers in seconds instead of minutes.
# Use a raw TCP port check - reliable regardless of HTTP response shape.
$proxyUp = (Test-NetConnection -ComputerName 127.0.0.1 -Port 11435 -InformationLevel Quiet -WarningAction SilentlyContinue)
if (-not $proxyUp) {
    $proxyScript = Join-Path $PSScriptRoot "ollama\nothink_proxy.py"
    $pyw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
    if (-not (Test-Path $pyw)) { $pyw = "pythonw" }
    Start-Process -FilePath $pyw -ArgumentList @($proxyScript, "11435", "http://localhost:11434") -WindowStyle Hidden | Out-Null
    Start-Sleep -Milliseconds 1500
    Write-Host "Started no-think proxy on :11435" -ForegroundColor DarkGray
}

# Point Claude Code at the ISOLATED config dir (no router, no apiKeyHelper).
$env:CLAUDE_CONFIG_DIR = Join-Path $PSScriptRoot "ollama\cfg"

# Belt-and-suspenders: also set the process env directly, and NEUTRALIZE any
# router vars this shell may have inherited so nothing points at 3456.
# Base URL -> the no-think proxy (:11435), NOT Ollama direct (:11434).
$env:ANTHROPIC_BASE_URL = "http://localhost:11435"
$env:ANTHROPIC_API_KEY = "ollama"
$env:ANTHROPIC_AUTH_TOKEN = "ollama"
$env:ANTHROPIC_MODEL = $Model
# Point the small/fast model at the SAME model so Claude Code's background calls
# (title-gen etc.) reuse the already-warm model instead of cold-loading qwen3:14b
# (which added ~23s). Override with -Model if you want the 14b as primary.
$env:ANTHROPIC_SMALL_FAST_MODEL = $Model
$env:MAX_THINKING_TOKENS = "0"
$env:ANTHROPIC_API_BASE_URL = ""
$env:CLAUDE_AGENT_API_BASE_URL = ""
$env:CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY = ""

# Style directive: qwen defaults to verbose exploratory rambling; pin it terse.
$style = "RESPONSE STYLE (mandatory): Answer directly and concisely. Lead with the result or decision, not your reasoning process. No filler phrases, no restating the question, no speculative tool suggestions. Use tools only when needed to complete the task. If unsure, say so in one line rather than guessing at length."

Write-Host "Local brain: $Model via :11435 no-think proxy (zero Anthropic tokens) [isolated, fast]" -ForegroundColor Green
if ($Prompt) {
    claude -p $Prompt --model $Model --append-system-prompt $style --bare
} else {
    claude --model $Model --append-system-prompt $style --bare
}
