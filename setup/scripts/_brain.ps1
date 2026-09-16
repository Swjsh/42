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
#
# PROVENANCE (added 2026-09-15, OP-32 free-model trust gate): every Resolve-BrainModel call --
# whichever branch it takes, including the fail-open catch -- appends one row to
# automation/state/brain-provenance.jsonl (ts_et, task_name, requested tier, resolved model,
# mode, station mode, local_path_taken, reason) via Write-BrainProvenanceRow, and sets
# $env:GAMMA_BRAIN_STAMP to a short human string ("gamma-planner-fast (local)" /
# "sonnet (anthropic)") a wrapper's prompt can embed so the artifact records which brain wrote
# it. The ledger write is fail-open and never affects the returned model name (see
# Write-BrainProvenanceRow's own header). Retention: 90 days, matching quote_recorder.py's
# analysis/quote-tape/*.jsonl OP-22 pattern.

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

function Get-BrainStamp {
    # Human-readable one-line "which brain wrote this" string for artifacts (visible-stamp
    # requirement, GAMMA-STATION provenance item). Never throws; unknown inputs degrade to
    # a labeled UNVERIFIED string rather than a blank line.
    param(
        [string]$ResolvedModel,
        [bool]$LocalPathTaken
    )
    try {
        if ($LocalPathTaken) {
            return ($ResolvedModel + " (local)")
        }
        return ($ResolvedModel + " (anthropic)")
    } catch {
        return "brain unknown (stamp error)"
    }
}

function Write-BrainProvenanceRow {
    # Appends ONE JSONL row to automation/state/brain-provenance.jsonl per Resolve-BrainModel
    # call -- the provenance ledger requested by the free-model trust gate (OP-32 /
    # FREE-MODEL-AUDIT-HARNESS.md): which brain actually produced each fire's artifact, since
    # a qwen-authored analysis is otherwise indistinguishable from a Claude-authored one.
    #
    # FAIL OPEN, NO EXCEPTIONS: this is diagnostic logging bolted onto a routing function.
    # ANY error here (disk full, path locked, malformed JSON, ET clock unavailable) is
    # swallowed -- it must NEVER throw into Resolve-BrainModel and change what model gets
    # returned or block the fire that called it.
    #
    # RETENTION (OP-22): 90 days, matching quote_recorder.py's analysis/quote-tape/*.jsonl
    # cap -- this ledger is a low-frequency per-fire diagnostic (a handful of rows/day across
    # 4 launchers), not a hot path, so a full read+filter+rewrite on every append is cheap.
    param(
        [string]$TaskName,
        [string]$RequestedTier,
        [string]$ResolvedModel,
        [string]$Mode,
        [string]$StationMode,
        [bool]$LocalPathTaken,
        [string]$Reason
    )
    try {
        $path = Join-Path $Global:WorkDir "automation\state\brain-provenance.jsonl"
        $dir = Split-Path $path -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force -ErrorAction Stop | Out-Null }

        $tsEt = $null
        try { $tsEt = (Get-EtNow).ToString("yyyy-MM-dd HH:mm:ss") + " ET" } catch { $tsEt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss") + " (ET unavailable)" }

        $row = [ordered]@{
            ts_et             = $tsEt
            task_name         = $TaskName
            requested_tier    = $RequestedTier
            resolved_model    = $ResolvedModel
            mode              = $Mode
            station_mode      = $StationMode
            local_path_taken  = [bool]$LocalPathTaken
            reason            = $Reason
        }
        $line = ($row | ConvertTo-Json -Compress -ErrorAction Stop)
        Add-Content -Path $path -Value $line -Encoding UTF8 -ErrorAction Stop

        $allLines = @(Get-Content -Path $path -ErrorAction Stop)
        if ($allLines.Count -gt 200) {
            $cutoff = (Get-Date).AddDays(-90)
            $kept = New-Object System.Collections.Generic.List[string]
            foreach ($l in $allLines) {
                $keep = $true
                try {
                    $parsed = $l | ConvertFrom-Json -ErrorAction Stop
                    $tsRaw = ([string]$parsed.ts_et) -replace " ET$", "" -replace " \(ET unavailable\)$", ""
                    $tsParsed = [datetime]::MinValue
                    if ([datetime]::TryParse($tsRaw, [ref]$tsParsed)) {
                        if ($tsParsed -lt $cutoff) { $keep = $false }
                    }
                } catch {
                    # Unparseable row: keep it. Never destroy provenance on a parse miss.
                }
                if ($keep) { $kept.Add($l) }
            }
            if ($kept.Count -lt $allLines.Count) {
                $tmp = "$path.tmp"
                Set-Content -Path $tmp -Value $kept -Encoding UTF8 -ErrorAction Stop
                Move-Item -Path $tmp -Destination $path -Force -ErrorAction Stop
            }
        }
    } catch {
        # Swallow -- see FAIL OPEN note above. Optionally best-effort log, itself guarded.
        try {
            if (Get-Command Write-TaskLog -ErrorAction SilentlyContinue) {
                Write-TaskLog -TaskName $TaskName -Message ("brain-provenance ledger write failed (non-fatal): " + $_.Exception.Message)
            }
        } catch { }
    }
}

function Complete-BrainResolution {
    # Single exit point for Resolve-BrainModel: records the provenance ledger row, sets the
    # env var wrappers embed into their prompts as the human-visible stamp, and returns the
    # tier/model string Resolve-BrainModel itself should return. Centralizing this means every
    # return path -- including the fail-open catch -- gets logged and stamped identically.
    param(
        [string]$TaskName,
        [string]$RequestedTier,
        [string]$ResolvedModel,
        [string]$Mode = "unknown",
        [string]$StationMode = "unknown",
        [bool]$LocalPathTaken = $false,
        [string]$Reason = ""
    )
    try { $env:GAMMA_BRAIN_STAMP = Get-BrainStamp -ResolvedModel $ResolvedModel -LocalPathTaken $LocalPathTaken } catch { }
    Write-BrainProvenanceRow -TaskName $TaskName -RequestedTier $RequestedTier -ResolvedModel $ResolvedModel `
        -Mode $Mode -StationMode $StationMode -LocalPathTaken $LocalPathTaken -Reason $Reason
    return $ResolvedModel
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
        if ($cfg.mode -ne "local") {
            return (Complete-BrainResolution -TaskName $TaskName -RequestedTier $Tier -ResolvedModel $Tier `
                -Mode $cfg.mode -StationMode "n/a" -LocalPathTaken $false -Reason "mode!=local")
        }

        $station = Get-StationMode
        if ($station -in @("gaming", "off")) {
            if ($canLog) { Write-TaskLog -TaskName $TaskName -Message ("BRAIN=local but station mode=" + $station + " (GPU reserved for J) -> Claude path") }
            return (Complete-BrainResolution -TaskName $TaskName -RequestedTier $Tier -ResolvedModel $Tier `
                -Mode $cfg.mode -StationMode $station -LocalPathTaken $false -Reason ("station_mode:" + $station))
        }

        $busy = Test-GpuBusy
        if ($busy) {
            if ($canLog) { Write-TaskLog -TaskName $TaskName -Message ("BRAIN=local but the GPU is busy (" + $busy + ") -> Claude path (a game on the GPU drops local prefill to ~25 tok/s; root-caused 2026-09-13)") }
            return (Complete-BrainResolution -TaskName $TaskName -RequestedTier $Tier -ResolvedModel $Tier `
                -Mode $cfg.mode -StationMode $station -LocalPathTaken $false -Reason ("gpu_busy:" + $busy))
        }

        $ollamaOk = $false
        try { $null = Invoke-RestMethod -Uri ("http://localhost:" + $cfg.ollama_port + "/api/version") -TimeoutSec 3; $ollamaOk = $true } catch { }
        if (-not $ollamaOk) {
            if ($canLog) { Write-TaskLog -TaskName $TaskName -Message "BRAIN=local requested but Ollama is down -> Claude path (fail-open)" }
            return (Complete-BrainResolution -TaskName $TaskName -RequestedTier $Tier -ResolvedModel $Tier `
                -Mode $cfg.mode -StationMode $station -LocalPathTaken $false -Reason "ollama_down")
        }

        $model = $cfg.map[$Tier.ToLower()]
        if (-not $model) { $model = $cfg.map["sonnet"] }
        if (-not $model) {
            return (Complete-BrainResolution -TaskName $TaskName -RequestedTier $Tier -ResolvedModel $Tier `
                -Mode $cfg.mode -StationMode $station -LocalPathTaken $false -Reason "no_model_mapped")
        }

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
            return (Complete-BrainResolution -TaskName $TaskName -RequestedTier $Tier -ResolvedModel $Tier `
                -Mode $cfg.mode -StationMode $station -LocalPathTaken $false -Reason "tags_unreachable")
        }
        $found = $storeNames | Where-Object { $_ -eq $model -or $_ -eq ($model + ":latest") -or $_.Split(":")[0] -eq $model }
        if (-not $found) {
            if ($canLog) { Write-TaskLog -TaskName $TaskName -Message ("BRAIN=local: model_missing:" + $model + " (store has " + $storeNames.Count + " models) -> Claude path (fail-open)") }
            return (Complete-BrainResolution -TaskName $TaskName -RequestedTier $Tier -ResolvedModel $Tier `
                -Mode $cfg.mode -StationMode $station -LocalPathTaken $false -Reason ("model_missing:" + $model))
        }

        if (-not (Start-NoThinkProxy -Port $cfg.proxy_port -OllamaPort $cfg.ollama_port)) {
            if ($canLog) { Write-TaskLog -TaskName $TaskName -Message "BRAIN=local: no-think proxy failed to start -> Claude path (fail-open)" }
            return (Complete-BrainResolution -TaskName $TaskName -RequestedTier $Tier -ResolvedModel $Tier `
                -Mode $cfg.mode -StationMode $station -LocalPathTaken $false -Reason "proxy_start_failed")
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
        return (Complete-BrainResolution -TaskName $TaskName -RequestedTier $Tier -ResolvedModel $model `
            -Mode $cfg.mode -StationMode $station -LocalPathTaken $true -Reason "local_ok")
    } catch {
        if ($canLog) { Write-TaskLog -TaskName $TaskName -Message ("BRAIN resolve error -> Claude path: " + $_.Exception.Message) }
        # Fail-open path itself must not throw even if Complete-BrainResolution somehow does --
        # Complete-BrainResolution's own internals are already try/catch-wrapped, but guard here
        # too so a resolve-error NEVER escalates into "the fire never got a model name back."
        try {
            return (Complete-BrainResolution -TaskName $TaskName -RequestedTier $Tier -ResolvedModel $Tier `
                -Mode "unknown" -StationMode "unknown" -LocalPathTaken $false -Reason ("resolve_error:" + $_.Exception.Message))
        } catch {
            return $Tier
        }
    }
}
