#requires -Version 5.1
<#
.SYNOPSIS
  Engine auto-healer -- runs BEFORE the health beacon's assessment so the engine ACTS
  on a RED before it WATCHES (pings J). Closes the watch->act gap surfaced 2026-06-22:
  the HealthBeacon was notify-only, so a stalled heartbeat just cry-wolf-pinged J on a
  loop (4 pings in one session) while the actual healing was done by an interactive
  Claude. This runs that exact manual playbook automatically.

  PLAYBOOK (the proven 2026-06-22 fixes):
    1. If watcher-observations.jsonl has bloated (>1MB) -> rotate it (archive + keep tail).
       (Root cause of the morning context-blowout that stalled both heartbeats.)
    2. Per account, if loop-state is stale during RTH -> clear the stuck state-hash and
       re-fire the heartbeat task (unsticks the hash-skip loop + forces a fresh tick).
    3. Stamp a grace window so engine_health.py suppresses the J-ping while the re-fired
       tick lands (~60-90s) -- J is only pinged if the heal FAILS (still RED after grace).

  SAFETY: RTH-only (never fires heartbeats off-hours), throttled to 1 heal / COOLDOWN_MIN
  (a re-fired tick needs time to land before re-trying), fully try/caught (never crashes
  the beacon), reuses _shared.ps1 Get-EtNow/Test-MarketHours. Touches only cache/state +
  fires existing tasks -- never edits doctrine/params and never places an order.
#>
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_shared.ps1"

try {
    $et = Get-EtNow
    if (-not (Test-WeekDay $et)) { exit 0 }
    # Heal only inside the live trading window (the heartbeat's own gate). Off-hours a
    # stale heartbeat is normal (beacon reads GREEN) -- nothing to heal.
    if (-not (Test-MarketHours -Et $et -StartHour 9 -StartMin 35 -EndHour 15 -EndMin 50)) { exit 0 }

    $COOLDOWN_MIN = 4
    $STALE_MIN    = 8
    $GRACE_MIN    = 3
    $today        = $et.ToString("yyyy-MM-dd")
    $healState    = Join-Path $WorkDir "automation\state\engine-heal-state.json"

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

    function Get-StaleMin($lsPath) {
        if (-not (Test-Path $lsPath)) { return $null }
        try {
            $ls = Get-Content $lsPath -Raw -EA Stop | ConvertFrom-Json -EA Stop
            if ("$($ls.session_id)" -ne $today) { return $null }  # only today's session
            $lc = ([DateTimeOffset]::Parse($ls.last_change_at)).UtcDateTime
            return ((Get-Date).ToUniversalTime() - $lc).TotalMinutes
        } catch { return $null }
    }

    function Set-ModeHot($lsPath) {
        # Value-only replace so a stalled account's re-fired tick (and the next few) are
        # NOT throttle-skipped: BASE mode skips 2 of 3 ticks, so a plain re-fire usually
        # hits 'SKIP throttle' and never ticks. HOT fires every tick; the heartbeat
        # self-downgrades back to BASE once it is producing again.
        try {
            $raw = Get-Content $lsPath -Raw -EA Stop
            $raw2 = $raw -replace '("current_mode"\s*:\s*")[^"]*(")', '${1}HOT${2}'
            [System.IO.File]::WriteAllText($lsPath, $raw2, (New-Object System.Text.UTF8Encoding($false)))
        } catch {}
    }

    $healed = @()

    # (1) Rotate a bloated watcher-observations.jsonl (shared context-blowout root cause).
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

    # (2) Per account: stale loop-state -> clear hash + re-fire the heartbeat.
    $safeStale = Get-StaleMin (Join-Path $WorkDir "automation\state\loop-state.json")
    if (($null -ne $safeStale) -and ($safeStale -gt $STALE_MIN)) {
        Set-ModeHot (Join-Path $WorkDir "automation\state\loop-state.json")
        Remove-Item (Join-Path $WorkDir "automation\state\heartbeat-state-hash.txt") -Force -EA SilentlyContinue
        try { Start-ScheduledTask -TaskName "Gamma_Heartbeat" -EA Stop; $healed += "re-fired Safe heartbeat (stale $([math]::Round($safeStale,1))m, ->HOT)" }
        catch { Write-TaskLog -TaskName "engine-heal" -Message "Safe re-fire failed: $_" }
    }
    $boldStale = Get-StaleMin (Join-Path $WorkDir "automation\state\aggressive\loop-state.json")
    if (($null -ne $boldStale) -and ($boldStale -gt $STALE_MIN)) {
        Set-ModeHot (Join-Path $WorkDir "automation\state\aggressive\loop-state.json")
        Remove-Item (Join-Path $WorkDir "automation\state\heartbeat-state-hash-aggressive.txt") -Force -EA SilentlyContinue
        try { Start-ScheduledTask -TaskName "Gamma_Heartbeat_Aggressive" -EA Stop; $healed += "re-fired Bold heartbeat (stale $([math]::Round($boldStale,1))m, ->HOT)" }
        catch { Write-TaskLog -TaskName "engine-heal" -Message "Bold re-fire failed: $_" }
    }

    if ($healed.Count -gt 0) {
        $rec = @{
            last_heal_at = (Get-Date).ToUniversalTime().ToString("o")
            grace_until  = (Get-Date).ToUniversalTime().AddMinutes($GRACE_MIN).ToString("o")
            actions      = $healed
            et           = $et.ToString("HH:mm:ss")
        }
        ($rec | ConvertTo-Json -Compress) | Set-Content -Path $healState -Encoding utf8
        Write-TaskLog -TaskName "engine-heal" -Message ("HEALED " + $et.ToString("HH:mm") + ": " + ($healed -join "; "))
    }
} catch {
    try { Write-TaskLog -TaskName "engine-heal" -Message "healer error: $_" } catch {}
}
exit 0
