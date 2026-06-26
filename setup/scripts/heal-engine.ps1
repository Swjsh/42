#requires -Version 5.1
<#
.SYNOPSIS
  Engine auto-healer -- runs BEFORE the health beacon's assessment so the engine ACTS
  on a stall before it WATCHES (pings J). Closes the watch->act gap surfaced 2026-06-22:
  the HealthBeacon was notify-only, so a stalled engine just cry-wolf-pinged J on a loop
  while the actual healing was done by an interactive Claude. This runs that playbook
  automatically.

  REPOINTED 2026-06-26 onto the DETERMINISTIC engine (the LLM heartbeat is retired):
    * The eye  = setup/scripts/sight_beacon.py  -> automation/state/sight-beacon.json
                 (Gamma_SightBeacon, every 1 min; ts_utc + ok flag).
    * The brain = setup/scripts/heartbeat_core.py -> automation/state/core-decisions.jsonl
                 (Gamma_HeartbeatCore, every ~1 min; one row per account 'safe'/'bold',
                  field ts_et = naive ET wall-clock).
  The old healer keyed entirely off the RETIRED LLM heartbeat (loop-state.json staleness,
  heartbeat-state-hash skip, re-firing the now-DISABLED Gamma_Heartbeat[_Aggressive]) so it
  could not heal the new engine at all. This mirrors the freshness logic in
  engine_health.py (check_engine_core / check_sight_beacon, CORE_STALE_MIN /
  BEACON_STALE_MIN = 8) so the healer's heal-trigger == the monitor's RED-critical set.

  PLAYBOOK:
    1. If watcher-observations.jsonl has bloated (>1MB) -> rotate it (archive + keep tail).
       (Hygiene: keeps engine_health.py's watcher_feed read cheap + caps disk growth -- the
        producer still has no retention cap. The deterministic core does NOT load this file,
        so this is no longer the LLM-context fix it once was, just defensive housekeeping.)
    2. Per account, if the BRAIN's newest core-decisions row is stale (or the file/row is
       missing) during RTH -> re-fire the engine. If the EYE (sight-beacon) is stale/blind
       -> re-fire it too. Refresh the eye FIRST (the brain reads it), then re-tick the brain.
    3. Stamp a grace window so engine_health.py suppresses the J-ping (heartbeat_safe/bold)
       while the re-fired tick lands (~60-90s) -- J is only pinged if the heal FAILS (still
       RED after grace). A BLIND-eye red still pings immediately by design (J: "the engine
       can NOT be blind ever") while the heal runs in parallel.

  SAFETY: RTH-only (never fires off-hours), throttled to 1 heal / COOLDOWN_MIN (a re-fired
  tick needs time to land before re-trying), fully try/caught (never crashes the beacon),
  reuses _shared.ps1 Get-EtNow/Test-MarketHours. Touches only cache/state + fires existing
  (Ready) tasks -- never edits doctrine/params and never places an order.
#>
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_shared.ps1"

try {
    $et = Get-EtNow
    if (-not (Test-WeekDay $et)) { exit 0 }
    # Heal only inside the live trading window (the engine's own gate). Off-hours a stale
    # core is normal (engine_health reads GREEN) -- nothing to heal.
    if (-not (Test-MarketHours -Et $et -StartHour 9 -StartMin 35 -EndHour 15 -EndMin 50)) { exit 0 }

    $COOLDOWN_MIN     = 4
    $CORE_STALE_MIN   = 8   # mirror engine_health.py CORE_STALE_MIN (brain liveness budget)
    $BEACON_STALE_MIN = 8   # mirror engine_health.py BEACON_STALE_MIN (eye liveness budget)
    $GRACE_MIN        = 3
    $healState        = Join-Path $WorkDir "automation\state\engine-heal-state.json"

    # Throttle: a re-fired tick takes ~60-90s; don't re-heal until it has had a chance.
    if (Test-Path $healState) {
        try {
            $prev = Get-Content $healState -Raw -EA Stop | ConvertFrom-Json -EA Stop
            if ($prev.last_heal_at) {
                $mins = ((Get-Date).ToUniversalTime() - ([DateTimeOffset]::Parse($prev.last_heal_at)).UtcDateTime).TotalMinutes
                if ($mins -lt $COOLDOWN_MIN) { exit 0 }
            }
        } catch {}
    }

    function Get-CoreStale {
        # BRAIN liveness: heartbeat_core writes one core-decisions.jsonl row per account every
        # ~1-min tick (even on HOLD), so a stale newest row for an account means the engine
        # stopped ticking. Returns @{ stale=$bool; detail=$str }. stale=$true is heal-worthy
        # (missing file / no account row / age > CORE_STALE_MIN -- the monitor's RED-critical
        # set). A transient read error -> stale=$false (never act on a bad read). ts_et is
        # naive ET wall-clock; compared against $EtNow (also naive ET via Get-EtNow).
        param([string]$Account, [DateTime]$EtNow)
        $path = Join-Path $WorkDir "automation\state\core-decisions.jsonl"
        if (-not (Test-Path $path)) { return @{ stale = $true; detail = "$Account brain: core-decisions.jsonl missing" } }
        try { $lines = @(Get-Content -Path $path -Tail 120 -EA Stop) }
        catch { return @{ stale = $false; detail = "$Account brain: read error" } }
        for ($i = $lines.Count - 1; $i -ge 0; $i--) {
            $raw = "$($lines[$i])".Trim()
            if (-not $raw) { continue }
            try { $row = $raw | ConvertFrom-Json -EA Stop } catch { continue }
            if (("$($row.account)" -eq $Account) -and $row.ts_et) {
                try {
                    $ts  = [DateTime]::ParseExact("$($row.ts_et)".Substring(0, 19), "yyyy-MM-ddTHH:mm:ss", [System.Globalization.CultureInfo]::InvariantCulture)
                    $age = ($EtNow - $ts).TotalMinutes
                    if ($age -gt $CORE_STALE_MIN) { return @{ stale = $true;  detail = "$Account brain STALE $([math]::Round($age,1))m" } }
                    return @{ stale = $false; detail = "$Account brain fresh $([math]::Round($age,1))m" }
                } catch { return @{ stale = $false; detail = "$Account brain: unparseable ts_et" } }
            }
        }
        return @{ stale = $true; detail = "$Account brain: no row in tail" }
    }

    function Get-BeaconStale {
        # EYE liveness: sight-beacon.json must be fresh + ok during RTH. Returns
        # @{ stale=$bool; detail=$str }. stale=$true (heal-worthy) on missing/unparseable
        # file, ok=false (BLIND), or age > BEACON_STALE_MIN -- the monitor's RED-critical set.
        # A present-but-ageless beacon (no/garbled ts_utc, ok still true) is YELLOW in the
        # monitor -> stale=$false (don't act). ts_utc is ISO-with-offset; aged against UTC now.
        param([DateTime]$NowUtc)
        $path = Join-Path $WorkDir "automation\state\sight-beacon.json"
        if (-not (Test-Path $path)) { return @{ stale = $true; detail = "eye: sight-beacon.json missing" } }
        try { $b = Get-Content $path -Raw -EA Stop | ConvertFrom-Json -EA Stop }
        catch { return @{ stale = $true; detail = "eye: sight-beacon.json unparseable" } }
        if ($b.ok -eq $false) { return @{ stale = $true; detail = "eye BLIND (ok=false)" } }
        if (-not $b.ts_utc)   { return @{ stale = $false; detail = "eye: no ts_utc" } }
        try {
            $utc = ([DateTimeOffset]::Parse("$($b.ts_utc)")).UtcDateTime
            $age = ($NowUtc - $utc).TotalMinutes
        } catch { return @{ stale = $false; detail = "eye: unparseable ts_utc" } }
        if ($age -gt $BEACON_STALE_MIN) { return @{ stale = $true;  detail = "eye STALE $([math]::Round($age,1))m" } }
        return @{ stale = $false; detail = "eye fresh $([math]::Round($age,1))m" }
    }

    $healed   = @()
    $triggers = @()

    # (1) Rotate a bloated watcher-observations.jsonl (hygiene -- keeps the monitor's read
    #     cheap + caps disk; the deterministic core does not read this file).
    $watcher = Join-Path $WorkDir "automation\state\watcher-observations.jsonl"
    if ((Test-Path $watcher) -and ((Get-Item $watcher).Length -gt 1MB)) {
        try {
            $archDir = Join-Path $WorkDir "automation\state\archive"
            if (-not (Test-Path $archDir)) { New-Item -ItemType Directory -Force -Path $archDir | Out-Null }
            $arch = Join-Path $archDir ("watcher-observations-autoheal-" + $et.ToString("yyyyMMdd-HHmmss") + ".jsonl")
            $mb = [math]::Round((Get-Item $watcher).Length / 1MB, 1)
            Copy-Item $watcher $arch -Force
            $tail = Get-Content $watcher -Tail 8
            [System.IO.File]::WriteAllLines($watcher, $tail, (New-Object System.Text.UTF8Encoding($false)))
            $healed += "rotated watcher-observations.jsonl (${mb}MB -> tail)"
        } catch { Write-TaskLog -TaskName "engine-heal" -Message "watcher rotate failed: $_" }
    }

    # (2) Detect a stalled BRAIN (per account) or BLIND/stale EYE -> re-fire the engine.
    $nowUtc = (Get-Date).ToUniversalTime()
    $cs = Get-CoreStale -Account "safe" -EtNow $et
    $cb = Get-CoreStale -Account "bold" -EtNow $et
    $be = Get-BeaconStale -NowUtc $nowUtc
    if ($cs.stale) { $triggers += $cs.detail }
    if ($cb.stale) { $triggers += $cb.detail }
    if ($be.stale) { $triggers += $be.detail }

    if ($triggers.Count -gt 0) {
        # Refresh the EYE first (the brain reads sight-beacon), then re-tick the BRAIN. Both
        # tasks are on healthy daily triggers (Ready) and idempotent -- a re-fire is just an
        # extra tick. heartbeat_core ticks BOTH accounts in one run, so one re-fire covers
        # safe + bold.
        try { Start-ScheduledTask -TaskName "Gamma_SightBeacon" -EA Stop;   $healed += "re-fired Gamma_SightBeacon (eye)" }
        catch { Write-TaskLog -TaskName "engine-heal" -Message "SightBeacon re-fire failed: $_" }
        try { Start-ScheduledTask -TaskName "Gamma_HeartbeatCore" -EA Stop; $healed += "re-fired Gamma_HeartbeatCore (brain)" }
        catch { Write-TaskLog -TaskName "engine-heal" -Message "HeartbeatCore re-fire failed: $_" }
    }

    if ($healed.Count -gt 0) {
        $rec = @{
            last_heal_at = (Get-Date).ToUniversalTime().ToString("o")
            grace_until  = (Get-Date).ToUniversalTime().AddMinutes($GRACE_MIN).ToString("o")
            actions      = $healed
            triggers     = $triggers
            et           = $et.ToString("HH:mm:ss")
        }
        ($rec | ConvertTo-Json -Compress) | Set-Content -Path $healState -Encoding utf8
        Write-TaskLog -TaskName "engine-heal" -Message ("HEALED " + $et.ToString("HH:mm") + ": " + ($healed -join "; ") + " | triggers: " + ($triggers -join "; "))
    }
} catch {
    try { Write-TaskLog -TaskName "engine-heal" -Message "healer error: $_" } catch {}
}
exit 0
