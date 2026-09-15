# _brain.ps1 -- per-fire brain routing for automation launchers (GAMMA-STATION item 8, 2026-09-13).
# Dot-source AFTER _shared.ps1 in an opted-in run-*.ps1, then pass the model through Resolve-BrainModel:
#     . "$PSScriptRoot\_shared.ps1"
#     . "$PSScriptRoot\_brain.ps1"
#     ... -Model (Resolve-BrainModel "sonnet" -TaskName $TaskName) ...
#
# What it does: when automation/state/brain-mode.json says {"mode":"local"} AND automation/state/station/mode.json
# is not "gaming"/"off", the CURRENT PROCESS gets the same isolated environment setup/launch_claude_local.ps1 uses
# (Ollama's native Anthropic Messages API through the normalizing no-think proxy on :11435, an isolated
# CLAUDE_CONFIG_DIR with no router/apiKeyHelper), and the tier name ("sonnet"/"opus"/"haiku") is mapped to a local
# model. Invoke-Claude's child process inherits that env. Otherwise NOTHING changes -- the tier name is returned as-is.
#
# Rules this honours: per-fire opt-in only, never a global env var, never under J's interactive tools
# (feedback_interactive_surfaces_never_gatewayed 2026-07-14 / 08-23); fail-open (any error -> Claude path);
# silent rig (proxy starts hidden). Revoke: set "mode":"claude" in brain-mode.json, or `gamma_mode.ps1 -Mode off`.

function Get-BrainMode {
    $path = Join-Path $Global:WorkDir "automation\state\brain-mode.json"
    $default = @{ mode = "claude"; map = @{ sonnet = "gamma-planner-fast"; opus = "gamma-planner-fast"; haiku = "qwen3:14b" }; proxy_port = 11435; ollama_port = 11434 }
    if (-not (Test-Path $path)) { return $default }
    try {
        $j = Get-Content $path -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        $map = @{}
        if ($j.map) { foreach ($p in $j.map.PSObject.Properties) { $map[$p.Name] = [string]$p.Value } }
        if ($map.Count -eq 0) { $map = $default.map }
        return @{
            mode        = $(if ($j.mode) { [string]$j.mode } else { "claude" })
            map         = $map
            proxy_port  = $(if ($j.proxy_port) { [int]$j.proxy_port } else { 11435 })
            ollama_port = $(if ($j.ollama_port) { [int]$j.ollama_port } else { 11434 })
        }
    } catch {
        return $default
    }
}

function Get-StationMode {
    # automation/state/station/mode.json written by setup/scripts/gamma_mode.ps1 (J's gaming / off switch).
    $path = Join-Path $Global:WorkDir "automation\state\station\mode.json"
    if (-not (Test-Path $path)) { return "work" }
    try { $m = (Get-Content $path -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop).mode; if ($m) { return [string]$m } } catch { }
    return "work"
}

function Get-StationYieldConfig {
    # gpu_util_yield_pct + yield_processes from automation/state/station/config.json (the Station loop's own
    # yield rule); defaults mirror station_loop.DEFAULT_CONFIG. Fail-open: unreadable -> defaults.
    $path = Join-Path $Global:WorkDir "automation\state\station\config.json"
    $cfg = @{ gpu_util_yield_pct = 50; yield_processes = @("obs64.exe", "r5apex_dx12.exe", "r5apex.exe") }  # games + GPU encoders only; launchers removed 2026-09-13 (Steam in the tray froze the evening)
    if (Test-Path $path) {
        try {
            $j = Get-Content $path -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
            if ($j.gpu_util_yield_pct) { $cfg.gpu_util_yield_pct = [int]$j.gpu_util_yield_pct }
            if ($j.yield_processes) { $cfg.yield_processes = @($j.yield_processes | ForEach-Object { [string]$_ }) }
        } catch { }
    }
    return $cfg
}

function Test-GpuBusy {
    # Root-caused 2026-09-13 17:1x ET: Apex Legends on the RTX 5080 (99% util, 15.8/16.3 GB) dropped the planner's
    # prefill from ~1,700 to ~25 tok/s and every local-brain fire (weekend conductor 16:00, conductor 16:17, two dry
    # runs) timed out. The Station loop already yields on this rule; launchers must too. Returns "" when the GPU is
    # free, else the reason. Fail-open: any error -> "" (proceed local).
    try {
        $cfg = Get-StationYieldConfig
        $util = $null
        try {
            $out = & nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>$null
            if ($out) { $util = [int](([string]($out | Select-Object -First 1)).Trim()) }
        } catch { }
        if ($null -ne $util -and $util -gt $cfg.gpu_util_yield_pct) { return ("gpu_util " + $util + "% > " + $cfg.gpu_util_yield_pct + "%") }
        $alive = @{}
        foreach ($p in (Get-Process -ErrorAction SilentlyContinue)) { $alive[($p.ProcessName + ".exe").ToLower()] = $true }
        foreach ($n in $cfg.yield_processes) { if ($alive[([string]$n).ToLower()]) { return ("denylisted_process:" + $n) } }
        return ""
    } catch { return "" }
}

function Start-NoThinkProxy {
    param([int]$Port = 11435, [int]$OllamaPort = 11434)
    $up = Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($up) { return $true }
    $proxy = Join-Path $Global:WorkDir "setup\ollama\nothink_proxy.py"
    if (-not (Test-Path $proxy)) { return $false }
    $pyw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
    if (-not (Test-Path $pyw)) { $pyw = "pythonw" }
    Start-Process -FilePath $pyw -ArgumentList @($proxy, "$Port", "http://localhost:$OllamaPort") -WindowStyle Hidden | Out-Null
    Start-Sleep -Milliseconds 1500
    return (Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue)
}

function Resolve-BrainModel {
    # Returns the model name to pass to Invoke-Claude. Side effect (local mode only): the current process env
    # now points Claude Code at Ollama. Fail-open: any problem -> the tier name unchanged, Claude path.
    param(
        [string]$Tier = "sonnet",
        [string]$TaskName = "brain"
    )
    $canLog = [bool](Get-Command Write-TaskLog -ErrorAction SilentlyContinue)
    try {
        $cfg = Get-BrainMode
        if ($cfg.mode -ne "local") { return $Tier }

        $station = Get-StationMode
        if ($station -in @("gaming", "off")) {
            if ($canLog) { Write-TaskLog -TaskName $TaskName -Message ("BRAIN=local but station mode=" + $station + " (GPU reserved for J) -> Claude path") }
            return $Tier
        }

        $busy = Test-GpuBusy
        if ($busy) {
            if ($canLog) { Write-TaskLog -TaskName $TaskName -Message ("BRAIN=local but the GPU is busy (" + $busy + ") -> Claude path (a game on the GPU drops local prefill to ~25 tok/s; root-caused 2026-09-13)") }
            return $Tier
        }

        $ollamaOk = $false
        try { $null = Invoke-RestMethod -Uri ("http://localhost:" + $cfg.ollama_port + "/api/version") -TimeoutSec 3; $ollamaOk = $true } catch { }
        if (-not $ollamaOk) {
            if ($canLog) { Write-TaskLog -TaskName $TaskName -Message "BRAIN=local requested but Ollama is down -> Claude path (fail-open)" }
            return $Tier
        }

        $model = $cfg.map[$Tier.ToLower()]
        if (-not $model) { $model = $cfg.map["sonnet"] }
        if (-not $model) { return $Tier }

        # Empty/partial model-store guard (2026-09-14 incident): /api/version answered 200
        # even though Ollama's model store was completely empty (the desktop app launched
        # against C:\Users\jackw\.ollama\models, ignoring OLLAMA_MODELS=E:\Gamma\models, before
        # the coordinator's junction fix) -- a fire proceeded straight to a 404 on the actual
        # chat call. Fail open exactly like the Ollama-down check above, but name the reason.
        $storeNames = @()
        $tagsOk = $false
        try {
            $tags = Invoke-RestMethod -Uri ("http://localhost:" + $cfg.ollama_port + "/api/tags") -TimeoutSec 5
            if ($tags -and $tags.models) { $storeNames = @($tags.models | ForEach-Object { [string]$_.name }) }
            $tagsOk = $true
        } catch { }
        if (-not $tagsOk) {
            if ($canLog) { Write-TaskLog -TaskName $TaskName -Message "BRAIN=local: /api/tags unreachable -> Claude path (fail-open)" }
            return $Tier
        }
        $found = $storeNames | Where-Object { $_ -eq $model -or $_ -eq ($model + ":latest") -or $_.Split(":")[0] -eq $model }
        if (-not $found) {
            if ($canLog) { Write-TaskLog -TaskName $TaskName -Message ("BRAIN=local: model_missing:" + $model + " (store has " + $storeNames.Count + " models) -> Claude path (fail-open)") }
            return $Tier
        }

        if (-not (Start-NoThinkProxy -Port $cfg.proxy_port -OllamaPort $cfg.ollama_port)) {
            if ($canLog) { Write-TaskLog -TaskName $TaskName -Message "BRAIN=local: no-think proxy failed to start -> Claude path (fail-open)" }
            return $Tier
        }

        $env:CLAUDE_CONFIG_DIR = Join-Path $Global:WorkDir "setup\ollama\cfg"
        $env:ANTHROPIC_BASE_URL = "http://localhost:" + $cfg.proxy_port
        $env:ANTHROPIC_API_KEY = "ollama"
        $env:ANTHROPIC_AUTH_TOKEN = "ollama"
        $env:ANTHROPIC_MODEL = $model
        $env:ANTHROPIC_SMALL_FAST_MODEL = $model
        $env:MAX_THINKING_TOKENS = "0"
        $env:ANTHROPIC_API_BASE_URL = ""
        $env:CLAUDE_AGENT_API_BASE_URL = ""
        $env:CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY = ""
        $env:GAMMA_BRAIN = "local"
        if ($canLog) { Write-TaskLog -TaskName $TaskName -Message ("BRAIN=local tier=" + $Tier + " -> model=" + $model + " via :" + $cfg.proxy_port + " (zero Anthropic tokens)") }
        return $model
    } catch {
        if ($canLog) { Write-TaskLog -TaskName $TaskName -Message ("BRAIN resolve error -> Claude path: " + $_.Exception.Message) }
        return $Tier
    }
}
