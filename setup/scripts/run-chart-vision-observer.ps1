# Chart-Vision Observer -- DRAFT (scaffold only, scheduled task NOT yet registered).
#
# Fires every 3 min during 09:30-15:55 ET weekdays alongside Gamma_Heartbeat as an
# OBSERVER-ONLY layer. Captures a SPY 5m chart screenshot via TV MCP, passes it to a
# vision-capable Claude (haiku) model with the chart_vision_observer.md prompt, and
# appends one structured JSON record to automation/state/vision-observations.jsonl.
#
# Per CLAUDE.md OP-27 L41 / 5-layer subprocess-spawn discipline: this script is
# designed to be invoked via `wscript.exe //nologo run_exe_hidden.vbs <pythonw>
# <run_ps1_hidden.py> <THIS SCRIPT>` -- see install-chart-vision-observer.ps1 (TODO,
# not shipped tonight) for the task registration pattern.
#
# Cost: ~$0.05/tick. Budget per fire capped at $0.15 (3x typical) to absorb single
# tick budget overshoots without runaway. Daily budget governed by tick count, not a
# script-side gate.
#
# Hard constraints (mirror chart_vision_observer.md):
#   - Vision prompt MUST NOT place orders (enforced in the prompt body -- Claude
#     refuses; no Allowed Tools enforcement at the wrapper level beyond the prompt
#     itself).
#   - One JSON record per fire, appended to vision-observations.jsonl. The Python
#     emit-record stage is fail-soft -- bad JSON gets logged to .raw and skipped, not
#     crashed.
#   - Production state files are NEVER touched.

. "$PSScriptRoot\_shared.ps1"

$task = "chart-vision-observer"
$et = Get-EtNow

# === GATE 1: weekday + market hours + holiday ===
if (-not (Test-WeekDay $et)) { exit 0 }
if (Test-HolidayFromAlpaca) { exit 0 }
if (-not (Test-MarketHours -Et $et -StartHour 9 -StartMin 30 -EndHour 15 -EndMin 55)) { exit 0 }

# === GATE 2: derive tick index (same convention as heartbeat) ===
$marketOpen = [DateTime]::new($et.Year, $et.Month, $et.Day, 9, 30, 0)
$tickIndex = [int][Math]::Floor(($et - $marketOpen).TotalMinutes / 3)
$today = $et.ToString("yyyy-MM-dd")

# === GATE 3: per-tick screenshot path ===
$snapshotDir = Join-Path $WorkDir "automation\state\vision-snapshots\$today"
if (-not (Test-Path $snapshotDir)) {
    New-Item -ItemType Directory -Force -Path $snapshotDir | Out-Null
}
$tickPadded = "{0:D3}" -f $tickIndex
$screenshotPath = Join-Path $snapshotDir "tick_$tickPadded.png"

# === GATE 4: skip if observation already exists for this tick (idempotent) ===
# Multiple firings of the same tick (e.g., scheduler retries) MUST NOT produce
# duplicate observations. The grader keys on (date, tick_id).
$obsFile = Join-Path $WorkDir "automation\state\vision-observations.jsonl"
if (Test-Path $obsFile) {
    try {
        # Cheap scan: read last 50 lines, look for matching tick_id+date.
        $tail = Get-Content $obsFile -Tail 50 -ErrorAction SilentlyContinue
        $marker = '"tick_id":' + $tickIndex + ',"date":"' + $today + '"'
        $altMarker = '"tick_id": ' + $tickIndex + ', "date": "' + $today + '"'
        foreach ($line in $tail) {
            if ($line -match [Regex]::Escape($marker) -or $line -match [Regex]::Escape($altMarker)) {
                Write-TaskLog -TaskName $task -Message "SKIP idempotent -- tick_id=$tickIndex already observed today"
                exit 0
            }
        }
    } catch {
        Write-TaskLog -TaskName $task -Message "WARN idempotent-check failed ($($_.Exception.Message)) -- proceeding"
    }
}

# === GATE 5: throttle if heartbeat is currently in-flight ===
# Heartbeat tick takes 90-160s. If it's running, we don't want TV CDP contention.
# Wait 30s and skip if still busy (next tick fires in 3 min anyway).
$hbPidFile = Join-Path $WorkDir "automation\state\heartbeat.pid"
if (Test-Path $hbPidFile) {
    try {
        $hbPidRaw = Get-Content $hbPidFile -Raw -ErrorAction Stop
        $hbPid = [int]($hbPidRaw.Trim().Split('|')[0])
        $hbProc = Get-Process -Id $hbPid -ErrorAction SilentlyContinue
        if ($hbProc) {
            Write-TaskLog -TaskName $task -Message "WAIT heartbeat in-flight pid=$hbPid, sleeping 30s"
            Start-Sleep -Seconds 30
            $hbProcRe = Get-Process -Id $hbPid -ErrorAction SilentlyContinue
            if ($hbProcRe) {
                Write-TaskLog -TaskName $task -Message "SKIP heartbeat still in-flight after 30s wait -- yielding this tick"
                exit 0
            }
        }
    } catch { }
}

# === GATE 6: state self-heal ===
$preStats = Repair-StateFiles -TaskName $task
if ($preStats.Restored -gt 0) {
    Write-TaskLog -TaskName $task -Message "PRE_RECOVERY restored=$($preStats.Restored) unrecoverable=$($preStats.Unrecoverable)"
}

Write-TaskLog -TaskName $task -Message "FIRE tick_id=$tickIndex screenshot=$screenshotPath"

# === STEP 1: pre-capture the screenshot via TV MCP ===
# We could let the vision prompt itself capture the screenshot, but pre-capturing
# (a) reduces vision-prompt tool calls (cheaper, faster), (b) gives the prompt
# a deterministic file path injected via the wrapper's runtime context, and
# (c) means a TV MCP failure aborts BEFORE any LLM tokens are spent.
#
# We invoke a tiny Python shim that calls the TV MCP REST endpoint OR -- if the
# vision prompt is the simpler integration path -- we skip pre-capture and let the
# prompt do it. For the DRAFT scaffold we let the prompt do the capture (single
# tool call inside its tick budget); the path injection still works because the
# prompt knows where to write it (under `automation/state/vision-snapshots/{date}/`).
#
# NOTE: a future optimization will pre-capture via a Python TV MCP client and
# pass the local PNG path to Claude vision as a multimodal input. Tonight's
# scaffold defers that -- the prompt handles it.

# === STEP 2: build per-tick context header file ===
# The wrapper exposes screenshot_path + tick_index + today_date so the prompt
# can reference them without re-deriving.
$ctxHeaderPath = Join-Path $WorkDir "automation\state\.chart-vision-observer-ctx.md"
$ctxHeader = @"
# Per-tick context (injected by run-chart-vision-observer.ps1)

- tick_index: $tickIndex
- today_date: $today
- expected_screenshot_path: $screenshotPath
- snapshot_dir: $snapshotDir
- observations_jsonl: $obsFile

The screenshot has NOT been pre-captured. Call ``mcp__tradingview__capture_screenshot(region="chart")`` ONCE inside your fire, then save the returned bytes to ``expected_screenshot_path`` above. (If your MCP returns base64, the wrapper will detect the file on disk after the fire.)
"@
$ctxHeader | Out-File -FilePath $ctxHeaderPath -Encoding utf8 -Force

# === STEP 3: invoke vision-capable Claude ===
# Per OP-3 cost discipline: haiku for image input ($0.04-0.06/tick at current
# Sonnet pricing tiers). MaxBudgetUsd 0.15 = 3x typical, hard ceiling on runaway.
# Timeout 60s -- vision call should be 10-25s including one MCP call + image
# decode + structured emit. 60s is the buffer.
$exit = Invoke-Claude `
    -PromptFile (Join-Path $WorkDir "automation\prompts\chart_vision_observer.md") `
    -TaskName $task `
    -MaxBudgetUsd 0.15 `
    -Model haiku `
    -TimeoutSec 60 `
    -Effort low

if ($exit -ne 0) {
    Write-TaskLog -TaskName $task -Message "EXIT non-zero exit=$exit (vision tick failed -- no observation appended)"
}

exit $exit
