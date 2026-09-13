#requires -Version 5.1
<#
.SYNOPSIS
  Station kiosk launcher -- the TV face (GOAL-GAMMA-STATION-2026-09-13 item 5 +
  the 2026-09-13 Wi-Fi/security amendments).

.DESCRIPTION
  -Start   1. Runs station_presence.py --once FIRST, same fire, before the kiosk
              check (per spec -- presence rides this same 5-min cadence, no new
              task).
           2. If a kiosk Edge PID is already alive (kiosk.pid), no-op -- this
              makes -Start idempotent, so both the AtLogOn trigger and the 5-min
              keepalive trigger can safely call the exact same action.
           3. SAFETY GATE (found during verification 2026-09-13): the
              config.json key `hdmi_kiosk_enabled` must be TRUE before this
              script will EVER launch a local Edge kiosk window, regardless of
              display count. Verified live on this box: it already reports 2
              displays for J's own normal desk setup (a real -Snapshot capture
              showed DISPLAY2 running his live Claude Code session + Discord,
              not a TV) -- a bare ">=2 displays" check would hijack his own
              active monitor the instant this task fires. Defaults false, so
              the safe Wi-Fi path (step 5) is what actually runs today; a human
              flips it to true only after physically confirming the TV is the
              genuine HDMI-connected display.
           4. Only when hdmi_kiosk_enabled=true AND >=2 displays exist:
              launches Edge in --kiosk mode on the configured (or first non-
              primary) display, pointed at http://127.0.0.1:3000/station?kiosk=1
              -- LOCAL loopback, since Edge runs on this same PC. Records the PID.
           5. Else if tv.json has a tv_host configured: calls
              `station_tv.py --face` (Wi-Fi wake + open the LAN-proxied Station
              page on the TV's OWN browser) and logs {"event":"tv_browser_face"}.
           6. Else logs {"event":"no_tv_display"} and exits 0 -- NEVER opens the
              kiosk on J's own main (or, per the safety gate above, secondary)
              monitor.
  -Stop    Closes ONLY the PID recorded in kiosk.pid.
  -Snapshot Captures the TV/second-display's bounds to kiosk-snapshot.png via
              System.Drawing (CopyFromScreen). Skips (event logged, exit 0) if
              fewer than 2 displays exist -- there is no local screen to capture
              for a Wi-Fi-only TV face.
  -Status  Prints displays found, kiosk PID alive?, last snapshot age, whether
              a tv_host is configured.

  SECURITY: tv_host/pc_lan_ips are read from the gitignored tv.json only (never
  config.json, which is tracked in a public repo) via station_tv.py's own
  loader -- this script never reads tv.json's fields directly except the
  single boolean "is a tv_host configured at all", used only to pick a branch.
#>
[CmdletBinding()]
param(
    [switch]$Start,
    [switch]$Stop,
    [switch]$Snapshot,
    [switch]$Status
)
$ErrorActionPreference = "Stop"

$WorkDir      = "C:\Users\jackw\Desktop\42"
$ScriptsDir   = Join-Path $WorkDir "setup\scripts"
$StationDir   = Join-Path $WorkDir "automation\state\station"
$PidFile      = Join-Path $StationDir "kiosk.pid"
$LedgerFile   = Join-Path $StationDir "kiosk-ledger.jsonl"
$SnapshotFile = Join-Path $StationDir "kiosk-snapshot.png"
$ConfigFile   = Join-Path $StationDir "config.json"
$TvJsonFile   = Join-Path $StationDir "tv.json"
$backtestPy   = Join-Path $WorkDir "backtest\.venv\Scripts\python.exe"
$presenceScript = Join-Path $ScriptsDir "station_presence.py"
$serveScript  = Join-Path $ScriptsDir "station_serve.py"
$tvScript     = Join-Path $ScriptsDir "station_tv.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$LocalStationUrl = "http://127.0.0.1:3000/station?kiosk=1"

function Start-StationServeIfNeeded {
    # "run it under the kiosk keepalive fire, start only if the port is free"
    # (amendment 1/3, 2026-09-13). Reads the port from config.json only (never
    # tv_host/pc_lan_ips -- those stay in tv.json, station_serve.py resolves
    # its own bind address itself); if nothing is listening on that port yet,
    # launches station_serve.py hidden via the same wscript -> run_exe_hidden.vbs
    # -> pythonw chain every other always-on daemon in this repo uses.
    $port = 8420
    if (Test-Path $ConfigFile) {
        try {
            $cfg = Get-Content $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($cfg.station_serve_port) { $port = [int]$cfg.station_serve_port }
        } catch {}
    }
    $listening = $null -ne (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    if ($listening) { return }
    if (-not (Test-Path $serveScript) -or -not (Test-Path $runExeHidden)) { return }

    $vbsArgs = @($backtestPy, $serveScript)
    $quoted = $vbsArgs | ForEach-Object { '"' + $_ + '"' }
    $cmd = "//nologo `"$runExeHidden`" " + ($quoted -join " ")
    Start-Process -FilePath "wscript.exe" -ArgumentList $cmd -WindowStyle Hidden
    Write-KioskLedger @{ event = "station_serve_started"; port = $port }
}

function Get-EtNowLabel {
    try {
        $tz = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
        return ([TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $tz)).ToString("yyyy-MM-dd HH:mm:ss") + " ET"
    } catch {
        return (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss") + " UTC (tz lookup failed)"
    }
}

function Write-KioskLedger {
    param([hashtable]$Row)
    $Row["ts_et"] = Get-EtNowLabel
    New-Item -ItemType Directory -Force -Path (Split-Path $LedgerFile) | Out-Null
    ($Row | ConvertTo-Json -Compress) | Add-Content -Path $LedgerFile -Encoding utf8
}

function Get-Displays {
    Add-Type -AssemblyName System.Windows.Forms
    return [System.Windows.Forms.Screen]::AllScreens
}

function Get-KioskProcId {
    if (-not (Test-Path $PidFile)) { return $null }
    $raw = (Get-Content $PidFile -Raw -ErrorAction SilentlyContinue)
    if (-not $raw) { return $null }
    $parsed = 0
    if (-not [int]::TryParse($raw.Trim(), [ref]$parsed)) { return $null }
    $proc = Get-Process -Id $parsed -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -match "msedge") { return $parsed }
    return $null
}

function Get-TvHostConfigured {
    # tv_host lives ONLY in tv.json (security amendment 6) -- config.json never
    # carries it. A missing/garbled tv.json reads as "not configured", never
    # a guessed true.
    if (-not (Test-Path $TvJsonFile)) { return $false }
    try {
        $tv = Get-Content $TvJsonFile -Raw -Encoding UTF8 | ConvertFrom-Json
        return [bool]($tv.tv_host)
    } catch {
        return $false
    }
}

function Get-HdmiKioskEnabled {
    # SAFETY GATE (2026-09-13): must be explicitly true in config.json before
    # -Start will ever consider the local-display kiosk path. Defaults false
    # (safe) on any missing/garbled config -- never defaults to true.
    if (-not (Test-Path $ConfigFile)) { return $false }
    try {
        $cfg = Get-Content $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
        return [bool]($cfg.hdmi_kiosk_enabled -eq $true)
    } catch {
        return $false
    }
}

function Get-KioskDisplayIndex {
    $idx = 2
    if (Test-Path $ConfigFile) {
        try {
            $cfg = Get-Content $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($cfg.kiosk_display_index) { $idx = [int]$cfg.kiosk_display_index }
        } catch {}
    }
    return $idx
}

function Select-TargetDisplay {
    param($Displays)
    $idx = (Get-KioskDisplayIndex) - 1
    $target = $null
    if ($idx -ge 0 -and $idx -lt $Displays.Count) { $target = $Displays[$idx] }
    if (-not $target -or $target.Primary) {
        # Out-of-range config, or the configured index resolved to J's own main
        # monitor (a misconfiguration) -- fall back to the first NON-primary
        # display. Never returns the primary screen.
        $target = $Displays | Where-Object { -not $_.Primary } | Select-Object -First 1
    }
    return $target
}

if ($Start) {
    if (Test-Path $presenceScript) {
        try { & $backtestPy $presenceScript --once 2>&1 | Out-Null } catch {}
    }
    try { Start-StationServeIfNeeded } catch {}

    $existingProcId = Get-KioskProcId
    if ($existingProcId) {
        Write-Output "OK: kiosk already running, pid=$existingProcId"
        exit 0
    }

    $displays = Get-Displays
    $hdmiEnabled = Get-HdmiKioskEnabled
    if ($displays.Count -ge 2 -and $hdmiEnabled) {
        $target = Select-TargetDisplay -Displays $displays
        if (-not $target) {
            Write-KioskLedger @{ event = "no_tv_display"; reason = "all displays report Primary=true" }
            Write-Output "OK: no non-primary display found -- no_tv_display logged"
            exit 0
        }
        $edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        if (-not (Test-Path $edge)) { $edge = "C:\Program Files\Microsoft\Edge\Application\msedge.exe" }
        if (-not (Test-Path $edge)) {
            Write-KioskLedger @{ event = "edge_not_found" }
            Write-Output "FAIL: msedge.exe not found in either Program Files location"
            exit 0
        }
        $bounds = $target.Bounds
        $edgeArgs = @(
            "--kiosk", $LocalStationUrl,
            "--edge-kiosk-type=fullscreen",
            "--window-position=$($bounds.X),$($bounds.Y)",
            "--no-first-run",
            "--disable-translate"
        )
        $proc = Start-Process -FilePath $edge -ArgumentList $edgeArgs -PassThru
        Set-Content -Path $PidFile -Value $proc.Id -Encoding ascii
        Write-KioskLedger @{ event = "kiosk_started"; display = $target.DeviceName; edge_pid = $proc.Id; url = $LocalStationUrl }
        Write-Output "OK: kiosk started on display $($target.DeviceName), pid=$($proc.Id)"
        exit 0
    }

    if (Get-TvHostConfigured) {
        $why = if ($displays.Count -ge 2 -and -not $hdmiEnabled) { "hdmi_kiosk_enabled=false" } else { "fewer than 2 displays" }
        # Don't re-launch the TV browser while the face is already alive: the kiosk page polls /api/station
        # every 60 s, so a TV request in the page server's log within the last 3 minutes means the page is up.
        # Re-sending the launch every 5 min would re-front the Internet app on the TV (2026-09-13).
        try {
            $serveLog = Join-Path 'E:\Gamma\logs' ("station-serve-" + (Get-Date).ToString('yyyy-MM-dd') + ".log")
            $tvIp = $null
            try { $tvIp = (Get-Content (Join-Path $StationDir 'tv.json') -Raw | ConvertFrom-Json).tv_host } catch {}
            if ($tvIp -and (Test-Path $serveLog)) {
                $recent = Get-Content $serveLog -Tail 400 | Where-Object { $_ -match ("client_ip=" + [regex]::Escape($tvIp)) } | Select-Object -Last 1
                if ($recent -and $recent -match '^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})') {
                    # The page-server log stamps ET; this box runs Mountain -- compare in ET (a raw Get-Date diff
                    # came out -7138 s on 2026-09-13 and made the guard fire forever).
                    $nowEt = [TimeZoneInfo]::ConvertTime((Get-Date), [TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time'))
                    $age = $nowEt - [datetime]::ParseExact($matches[1], 'yyyy-MM-dd HH:mm:ss', $null)
                    if ($age.TotalMinutes -lt 3) {
                        Write-KioskLedger @{ event = "tv_face_alive"; last_tv_request_age_s = [int]$age.TotalSeconds }
                        Write-Output "OK: TV face alive (last TV request $([int]$age.TotalSeconds)s ago) -- not re-launching"
                        exit 0
                    }
                }
            }
        } catch {}
        Write-Output "Using the Wi-Fi TV face ($why -- station_tv.py --face)"
        try {
            & $backtestPy $tvScript --face 2>&1 | ForEach-Object { Write-Output $_ }
        } catch {
            Write-Output "station_tv.py --face threw: $($_.Exception.Message)"
        }
        Write-KioskLedger @{ event = "tv_browser_face"; reason = $why }
        exit 0
    }

    Write-KioskLedger @{ event = "no_tv_display" }
    Write-Output "OK: no eligible kiosk target (hdmi_kiosk_enabled=$hdmiEnabled, displays=$($displays.Count)) and no tv_host configured -- no_tv_display logged, nothing opened"
    exit 0
}

if ($Stop) {
    $existingProcId = Get-KioskProcId
    if ($existingProcId) {
        Stop-Process -Id $existingProcId -Force -ErrorAction SilentlyContinue
        Write-Output "OK: stopped pid=$existingProcId"
    } else {
        Write-Output "OK: nothing to stop (no live kiosk PID on file)"
    }
    Remove-Item -Path $PidFile -ErrorAction SilentlyContinue
    exit 0
}

if ($Snapshot) {
    $displays = Get-Displays
    if ($displays.Count -lt 2) {
        Write-KioskLedger @{ event = "snapshot_skipped_single_display" }
        Write-Output "SKIPPED: fewer than 2 displays -- no local TV screen to capture (Wi-Fi face has none)"
        exit 0
    }
    $target = Select-TargetDisplay -Displays $displays
    if (-not $target) {
        Write-KioskLedger @{ event = "snapshot_skipped_no_target" }
        Write-Output "SKIPPED: no non-primary display found"
        exit 0
    }
    Add-Type -AssemblyName System.Drawing
    $bounds = $target.Bounds
    $bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    New-Item -ItemType Directory -Force -Path (Split-Path $SnapshotFile) | Out-Null
    $bmp.Save($SnapshotFile, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose()
    $bmp.Dispose()
    Write-Output "OK: snapshot saved -> $SnapshotFile"
    exit 0
}

if ($Status) {
    $displays = Get-Displays
    $existingProcId = Get-KioskProcId
    $snapAge = "never"
    if (Test-Path $SnapshotFile) {
        $age = (Get-Date) - (Get-Item $SnapshotFile).LastWriteTime
        $snapAge = "{0:N1} min ago" -f $age.TotalMinutes
    }
    Write-Output "Displays found: $($displays.Count)"
    Write-Output "HDMI kiosk enabled (config.json): $(Get-HdmiKioskEnabled)"
    Write-Output "Kiosk PID alive: $(if ($existingProcId) { $existingProcId } else { 'no' })"
    Write-Output "Last snapshot: $snapAge"
    Write-Output "TV host configured (tv.json): $(Get-TvHostConfigured)"
    exit 0
}

Write-Output "Usage: station_kiosk.ps1 -Start | -Stop | -Snapshot | -Status"
exit 0
