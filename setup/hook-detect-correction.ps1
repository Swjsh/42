# UserPromptSubmit hook -- INLINE SKILL SELF-IMPROVEMENT (Hermes background_review port).
#
# When J corrects Gamma mid-session ("stop doing X", "that's wrong", "do it this
# way"), this captures a durable "correction candidate" to the skill-learning queue
# so skill-author triages it next fire, AND nudges the in-session Gamma to honor the
# correction immediately this turn. Dumb capture ONLY -- all judgment + Rule-9
# denylist routing happen in skill-author Stage 0, never here.
#
# Design contract:
#   - Fail-open + silent: any error exits 0 with no output. Never blocks J's turn.
#   - Quiet: emits a single context line ONLY when a correction is captured.
#   - No window flash: runs in the existing -NoProfile UserPromptSubmit chain.
#   - PS 5.1 compatible (no ternary, no null-coalescing, no em-dashes).

$ErrorActionPreference = 'SilentlyContinue'

$Repo  = 'C:\Users\jackw\Desktop\42'
$Queue = Join-Path $Repo 'strategy\candidates\_skill-inbox\_correction-queue.jsonl'
$Stamp = Join-Path $Repo 'strategy\candidates\_skill-inbox\.correction_last'

# --- read the prompt from stdin JSON (Claude Code hook contract) ---
$raw = ''
try { $raw = [Console]::In.ReadToEnd() } catch { exit 0 }
if (-not $raw) { exit 0 }

$prompt = ''
try {
    $payload = $raw | ConvertFrom-Json
    $prompt = [string]$payload.prompt
} catch {
    $prompt = [string]$raw  # not JSON -- treat raw text as the prompt
}
if (-not $prompt -or $prompt.Trim().Length -eq 0) { exit 0 }

$low = $prompt.ToLowerInvariant()

# --- strip trading-jargon false positives BEFORE matching ("stop loss" is not a correction) ---
$scan = $low -replace 'stop[\s\-]?loss', '' -replace 'stop(ped)?\s+out', '' -replace 'stop[\s\-]?out', ''

# --- high-precision correction phrases (curated for low false-positive rate) ---
$patterns = @(
    "stop doing", "quit doing", "stop trying to", "stop being",
    "don'?t do that", "don'?t ever", "never do that", "never say that",
    "you('?re| are) wrong", "that'?s wrong", "that'?s incorrect", "you got (that|it) wrong",
    "do it this way", "do this instead", "instead of (doing|that)",
    "you should(n'?t| not) have", "you should have", "that'?s not what i", "not what i asked",
    "i (told|said) you", "next time,? (don'?t|do)"
)
$matched = ''
foreach ($p in $patterns) {
    if ($scan -match $p) { $matched = $p; break }
}
if (-not $matched) { exit 0 }

# --- throttle: at most one capture per 30s ---
$now = Get-Date
if (Test-Path $Stamp) {
    try {
        $last = [datetime]::FromFileTimeUtc([int64](Get-Content $Stamp -Raw))
        if (($now.ToUniversalTime() - $last).TotalSeconds -lt 30) { exit 0 }
    } catch {}
}

# --- dedupe by prompt hash vs last queue line ---
$hash = ''
try {
    $sha   = [System.Security.Cryptography.SHA256]::Create()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($prompt)
    $hash  = ([System.BitConverter]::ToString($sha.ComputeHash($bytes)) -replace '-', '').Substring(0, 16)
} catch { $hash = "len$($prompt.Length)" }

if (Test-Path $Queue) {
    $lastLine = Get-Content $Queue -Tail 1
    if ($lastLine -and $lastLine -match [regex]::Escape($hash)) { exit 0 }
}

# --- coarse skill attribution: which skill dirs are named in the prompt? ---
$skillsDir = Join-Path $Repo '.claude\skills'
$mentioned = @()
if (Test-Path $skillsDir) {
    foreach ($d in (Get-ChildItem $skillsDir -Directory)) {
        if ($low -match [regex]::Escape($d.Name.ToLowerInvariant())) { $mentioned += $d.Name }
    }
}

# --- Rule-9 denylist tag (capture-only; skill-author enforces the actual gate) ---
$denylist = @('heartbeat-pulse-check', 'heartbeat-decision-trace', 'pin-chain-verify',
              'heartbeat', 'params', 'risk_gate', 'kill switch', 'kill-switch')
$denyHit = $false
foreach ($d in $denylist) { if ($low -match [regex]::Escape($d)) { $denyHit = $true; break } }

# --- bound stored prompt size ---
$snippet = $prompt
if ($snippet.Length -gt 1200) { $snippet = $snippet.Substring(0, 1200) + ' [truncated]' }

# --- append the correction candidate (JSONL) ---
$entry = [ordered]@{
    ts             = $now.ToString('yyyy-MM-ddTHH:mm:ssK')
    hash           = $hash
    matched_phrase = $matched
    prompt         = $snippet
    skills_named   = $mentioned
    denylist_hit   = $denyHit
    processed      = $false
}
try {
    $line = ($entry | ConvertTo-Json -Compress -Depth 4)
    Add-Content -Path $Queue -Value $line -Encoding UTF8
    $now.ToUniversalTime().ToFileTimeUtc() | Out-File -FilePath $Stamp -Encoding ascii -NoNewline
} catch { exit 0 }

# --- retention cap: keep last 500 lines (OP-22) ---
try {
    $all = Get-Content $Queue
    if ($all.Count -gt 500) { $all[-500..-1] | Set-Content $Queue -Encoding UTF8 }
} catch {}

# --- single context line (the only output): nudge immediate honor + durable backstop ---
$note = '[correction-capture] Logged a likely correction from J to the skill-learning queue (strategy/candidates/_skill-inbox/_correction-queue.jsonl); skill-author triages it Stage-0 next fire.'
if ($denyHit) {
    $note += ' NOTE: references live doctrine -- any skill change is Rule-9 (J ratifies via _lesson-inbox), but honor the intent in HOW I respond now.'
} else {
    $note += ' If this is about HOW I work, honor it immediately this turn too.'
}
Write-Output $note
exit 0
