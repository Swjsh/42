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

# ============================================================================
# J-MIND CHECK harvest (OP-33(e)) -- a REPEATED state-question from J is a MISSING
# INSTRUMENT, not a query. Capture J's interrogatives-about-state to a ledger that
# friction_distiller counts (recurring_user_question, escalates at >=2 -> "build the
# standing surface that retires the question"). This is the harvest source the metacog
# dissection (2026-06-29) found was missing: the rig counted its own friction, never J's.
# Runs alongside the correction capture below (does NOT exit) so both can fire.
# ============================================================================
$qLedger = Join-Path $Repo 'automation\state\j-question-ledger.jsonl'
$qStamp  = Join-Path $Repo 'automation\state\.jquestion_last'
$qIntent = ''
$qRules = @(
    @{ rx = 'is it (actually |really )?trading'; intent = 'is_trading' },
    @{ rx = 'are we (actually )?(trading|live)'; intent = 'is_trading' },
    @{ rx = 'is it (running|working|live|on|up|firing)'; intent = 'is_running' },
    @{ rx = 'is .{0,25}(running|working|firing|trading|live)\b'; intent = 'is_running' },
    @{ rx = '(did|has) it (crash|crashed|die|died|stop|stopped|fail|failed)'; intent = 'did_crash' },
    @{ rx = 'did it (save|fire|work|run|output|actually)'; intent = 'did_it_x' },
    @{ rx = 'still (running|working|firing|alive)'; intent = 'is_running' },
    @{ rx = '^\s*well\s*\??\s*$'; intent = 'status_poke' },
    @{ rx = 'any update'; intent = 'status_poke' },
    @{ rx = "what'?s (the )?status"; intent = 'status_poke' },
    @{ rx = 'no (visibility|confidence)'; intent = 'no_visibility' },
    @{ rx = 'you (told|said) me.{0,40}(work|ran|run|fix|done|trad)'; intent = 'claim_mismatch' }
)
foreach ($qr in $qRules) {
    if ($scan -match $qr.rx) { $qIntent = $qr.intent; break }
}
if ($qIntent) {
    $qnow = Get-Date
    $qThrottleOk = $true
    if (Test-Path $qStamp) {
        try {
            $qlast = [datetime]::FromFileTimeUtc([int64](Get-Content $qStamp -Raw))
            if (($qnow.ToUniversalTime() - $qlast).TotalSeconds -lt 15) { $qThrottleOk = $false }
        } catch {}
    }
    # hash for exact-duplicate suppression (same message firing twice), NOT for repeat-intent
    $qHash = ''
    try {
        $qsha   = [System.Security.Cryptography.SHA256]::Create()
        $qbytes = [System.Text.Encoding]::UTF8.GetBytes($prompt)
        $qHash  = ([System.BitConverter]::ToString($qsha.ComputeHash($qbytes)) -replace '-', '').Substring(0, 16)
    } catch { $qHash = "len$($prompt.Length)" }
    $qDup = $false
    if (Test-Path $qLedger) {
        $qLastLine = Get-Content $qLedger -Tail 1
        if ($qLastLine -and $qLastLine -match [regex]::Escape($qHash)) { $qDup = $true }
    }
    if ($qThrottleOk -and -not $qDup) {
        $qSnippet = $prompt
        if ($qSnippet.Length -gt 400) { $qSnippet = $qSnippet.Substring(0, 400) + ' [truncated]' }
        $qEntry = [ordered]@{
            ts        = $qnow.ToString('yyyy-MM-ddTHH:mm:ssK')
            hash      = $qHash
            intent    = $qIntent
            prompt    = $qSnippet
            processed = $false
        }
        try {
            # BOM-less UTF-8 (PS 5.1 Add-Content -Encoding UTF8 prepends a BOM that breaks
            # json.loads on line 1 -- the exact silent-corruption class self-check guards).
            $qUtf8 = New-Object System.Text.UTF8Encoding($false)
            $qLine = ($qEntry | ConvertTo-Json -Compress -Depth 3)
            [System.IO.File]::AppendAllText($qLedger, $qLine + "`n", $qUtf8)
            $qnow.ToUniversalTime().ToFileTimeUtc() | Out-File -FilePath $qStamp -Encoding ascii -NoNewline
            $qAll = @(Get-Content $qLedger)
            if ($qAll.Count -gt 500) { [System.IO.File]::WriteAllLines($qLedger, $qAll[-500..-1], $qUtf8) }
        } catch {}
        Write-Output ("[j-mind-check] J asked a STATE question (intent=" + $qIntent + "). OP-33(e): a REPEATED question is a MISSING INSTRUMENT, not a query. If J has asked this kind before, STOP answering ad-hoc and BUILD the standing surface (state file + glanceable view + auto-ping) that retires it; then report you built it. Logged to automation/state/j-question-ledger.jsonl; friction_distiller escalates recurring_user_question at >=2.")
    }
}

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
