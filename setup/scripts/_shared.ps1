# Shared helpers for all autonomy task scripts. Sourced by each run-*.ps1.
# Do not run this directly.

$Global:WorkDir = "C:\Users\jackw\Desktop\42"
$Global:ClaudeExe = "C:\Users\jackw\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe"
$Global:LogDir = Join-Path $WorkDir "automation\state\logs"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

function Get-EtNow {
    # ET = UTC-4 (EDT) or UTC-5 (EST). Use system zone "Eastern Standard Time" which honors DST.
    $tz = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
    return [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $tz)
}

function Test-WeekDay {
    param([DateTime]$Et)
    return $Et.DayOfWeek -ne [DayOfWeek]::Saturday -and $Et.DayOfWeek -ne [DayOfWeek]::Sunday
}

function Test-MarketHours {
    param(
        [DateTime]$Et,
        [int]$StartHour = 9,
        [int]$StartMin = 30,
        [int]$EndHour = 15,
        [int]$EndMin = 50
    )
    $start = [DateTime]::new($Et.Year, $Et.Month, $Et.Day, $StartHour, $StartMin, 0)
    $end = [DateTime]::new($Et.Year, $Et.Month, $Et.Day, $EndHour, $EndMin, 0)
    return ($Et -ge $start) -and ($Et -le $end)
}

function Write-TaskLog {
    param(
        [string]$TaskName,
        [string]$Message
    )
    $today = Get-EtNow | ForEach-Object { $_.ToString("yyyy-MM-dd") }
    $logFile = Join-Path $LogDir "$TaskName-$today.log"
    $stamp = (Get-EtNow).ToString("yyyy-MM-dd HH:mm:ss") + " ET"
    "$stamp $Message" | Out-File -Append -Encoding utf8 -FilePath $logFile
}

function Invoke-PythonHidden {
    # Run a Python script via system python.exe with CREATE_NO_WINDOW + redirected stdio.
    # This is the ONLY supported way for scheduled-task PS1 scripts to invoke Python.
    # Bare `python script.py` in PS1 leaks conhost windows on Windows 11 default-terminal
    # configurations even when the parent PowerShell is launched -WindowStyle Hidden.
    # See CLAUDE.md OP-27 L41 (subprocess-spawn discipline) + 5/17 evening foot-gun.
    #
    # Returns @{ ExitCode = N; Stdout = "..."; Stderr = "..."; LogFile = "..." }.
    param(
        [Parameter(Mandatory)][string]$ScriptPath,
        [string[]]$ArgList = @(),
        [string]$TaskName = "",
        [string]$InputObject = "",
        [int]$TimeoutSec = 600
    )
    if (-not $TaskName) { $TaskName = [System.IO.Path]::GetFileNameWithoutExtension($ScriptPath) }

    # Resolve system python.exe (NOT venv pythonw stub which re-execs as console python).
    $sysPython = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\python.exe"
    if (-not (Test-Path $sysPython)) {
        $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($cmd) { $sysPython = $cmd.Source }
        else { throw "Invoke-PythonHidden: python.exe not found at $sysPython or in PATH" }
    }

    $today = (Get-Date -Format "yyyy-MM-dd")
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
    $logFile = Join-Path $LogDir "$TaskName-$today.python.log"

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $sysPython
    $allArgs = @($ScriptPath) + $ArgList
    $psi.Arguments = ($allArgs | ForEach-Object {
        if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
    }) -join ' '
    $psi.WorkingDirectory = $WorkDir
    $psi.UseShellExecute = $false
    # CreateNoWindow maps to CREATE_NO_WINDOW (0x08000000) -- Windows does NOT allocate a
    # console/conhost for the child, even though python.exe is console-subsystem.
    $psi.CreateNoWindow = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    # .NET's StreamReader for a redirected pipe decodes using the CONSOLE output
    # codepage by default (cp1252/OEM on this box), independent of what encoding the
    # CHILD process actually wrote in. Once PYTHONIOENCODING=utf-8 (below) makes the
    # child emit real UTF-8 bytes, decoding those bytes as cp1252 on this side produces
    # silent mojibake (proven empirically: U+2265 round-tripped as "Γ\xeb\xd1") --
    # not a crash, but corrupted text landing in every .python.log and any digest that
    # echoes captured stdout verbatim. Force both sides to agree on UTF-8.
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    if ($InputObject) { $psi.RedirectStandardInput = $true }

    # Resolve venv site-packages so 3rd-party deps (pandas, etc.) work without using the
    # venv's own python.exe stub (cleaner foot-gun surface). Mirrors the pattern in
    # ensure-discord-bridge-alive.ps1. Layer-4 of OP-27 L41.
    $venvDir = Join-Path $WorkDir "backtest\.venv"
    $venvSite = Join-Path $venvDir "Lib\site-packages"
    if (Test-Path $venvSite) {
        $psi.EnvironmentVariables["PYTHONPATH"] = $venvSite
        $psi.EnvironmentVariables["VIRTUAL_ENV"] = $venvDir
    }
    # FIX (2026-08-10, kitchen_reviewer UnicodeEncodeError incident): a headless
    # CREATE_NO_WINDOW child has no real console, so Python falls back to the Windows
    # ANSI codepage (cp1252 on this box) for stdout/stderr instead of UTF-8. Any script
    # that prints a non-cp1252 character (curly quotes, em-dash, >=/<=, emoji -- all
    # routine in free-LLM-generated text this repo pipes straight to print()) crashes
    # with UnicodeEncodeError and exits 1, silently, from Task Scheduler's point of view.
    # kitchen_reviewer.py hit this exact way (U+2265 "≥" in a followup string) on
    # 2026-08-10 04:50 ET. run-kalshi-tick.ps1/run-kalshi-auto.ps1 already carried this
    # fix locally (2026-08-09) but it was never backported to the shared launcher every
    # OTHER wrapper uses -- so the same crash was latent for all 37 Invoke-PythonHidden
    # callers, including the live heartbeat wrappers. Fixed once, here, for all of them.
    $psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"

    $proc = [System.Diagnostics.Process]::Start($psi)
    if ($InputObject) {
        $proc.StandardInput.WriteLine($InputObject)
        $proc.StandardInput.Close()
    }
    # FIX (2026-08-07, Lane 2 systemic-timeout-leak audit): the old code called the
    # SYNCHRONOUS StandardOutput/StandardError.ReadToEnd() before WaitForExit(). ReadToEnd()
    # blocks until the pipe's write end closes, which only happens on process exit -- so a
    # child that hangs (regardless of whether it ever writes output) blocks THIS LINE
    # forever and WaitForExit($TimeoutSec*1000) below is never even reached. -TimeoutSec was
    # dead in exactly the pathological case it exists for. It can also classically deadlock
    # if the child fills the stderr OS pipe buffer while we're blocked reading only stdout.
    # Fix: begin async reads first (mirrors Invoke-Claude's proven pattern above), so
    # WaitForExit is the only blocking call and the timeout is real.
    $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
    $stderrTask = $proc.StandardError.ReadToEndAsync()
    if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
        # FIX (2026-08-07, same audit): Process.Kill(Boolean) -- the process-tree overload --
        # does NOT exist on this box's Windows PowerShell 5.1 / .NET Framework and THROWS
        # "Cannot find an overload for 'Kill' and the argument count: 1", which the bare
        # try/catch here swallowed. Net effect: every timeout in this function leaked its
        # hung child instead of killing it. Proven empirically 2026-08-07: Kill($true) threw
        # that exact exception against a real spawned process; plain Kill() on an identical
        # process succeeded and the PID disappeared immediately. Invoke-PythonHidden's
        # children are plain leaf python.exe processes (no MCP/child subtree spawned under
        # them the way claude.exe spawns MCP servers under Invoke-Claude), so plain Kill()
        # is the correct PS5.1-safe call here -- no taskkill /T tree-kill needed.
        try { $proc.Kill() } catch {}
        $exit = -1
    } else {
        $exit = $proc.ExitCode
    }
    try {
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
    } catch {
        # Defensive: if the killed process's streams fault instead of completing cleanly,
        # don't let stdout/stderr capture failure mask the real ExitCode/timeout result above.
        if (-not $stdout) { $stdout = "" }
        if (-not $stderr) { $stderr = "" }
    }

    $ts = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    $shortArgs = ($ArgList -join ' ')
    Add-Content -Path $logFile -Value "[$ts] Invoke-PythonHidden $ScriptPath $shortArgs exit=$exit"
    if ($stdout) { Add-Content -Path $logFile -Value "STDOUT:`n$stdout" }
    if ($stderr) { Add-Content -Path $logFile -Value "STDERR:`n$stderr" }

    return @{ ExitCode = $exit; Stdout = $stdout; Stderr = $stderr; LogFile = $logFile }
}

function Get-ParamsMinDiskFreeMb {
    # RESTORE of the min_disk_free_mb dead knob (PARAMS-DEAD-KNOB-DISPOSITION 2026-07-19):
    # reads automation/state/params.json's min_disk_free_mb live so the value there is a
    # real read, not documentation. Fail-open to 100 (the pre-fix hardcoded literal) on any
    # read/parse error -- never let a malformed params.json block the disk pre-flight check.
    $paramsPath = Join-Path $WorkDir "automation\state\params.json"
    try {
        $p = Get-Content -Path $paramsPath -Raw -ErrorAction Stop | ConvertFrom-Json
        if ($null -ne $p.min_disk_free_mb) { return [int]$p.min_disk_free_mb }
        return 100
    } catch {
        return 100
    }
}

function Test-DiskSpaceAvailable {
    # Pre-flight: refuse to invoke claude if WorkDir's drive has < $MinFreeMB.
    # State writes, log writes, and JSONL session logs all need disk. A silent
    # ENOSPC during a state write produces a partial JSON the next task can't
    # parse. Refusing up-front is much better than recovering after.
    param([int]$MinFreeMB = (Get-ParamsMinDiskFreeMb))
    try {
        $drive = (Get-Item $WorkDir).PSDrive.Name
        $free = (Get-PSDrive -Name $drive).Free
        $freeMB = [math]::Round($free / 1MB)
        return @{ OK = ($freeMB -ge $MinFreeMB); FreeMB = $freeMB; MinMB = $MinFreeMB }
    } catch {
        # If we can't measure, assume OK (don't block on diagnostic failure)
        return @{ OK = $true; FreeMB = -1; MinMB = $MinFreeMB }
    }
}

function Repair-StateFiles {
    # Atomic state recovery. Validates every *.json in automation/state/, mirrors
    # known-good copies to automation/state/.lastgood/, and restores any file that
    # fails to parse from its last-known-good copy.
    #
    # Idempotent. Safe to call before AND after every Invoke-Claude -- and we do.
    # Call BEFORE to catch corruption inherited from a prior crashed task.
    # Call AFTER to refresh known-good and catch corruption introduced this tick.
    #
    # Returns @{ Validated, Corrupted, Restored, Unrecoverable } counts.
    param([string]$TaskName = "unknown")
    $stateDir = Join-Path $WorkDir "automation\state"
    $lastGood = Join-Path $stateDir ".lastgood"
    if (-not (Test-Path $lastGood)) {
        New-Item -ItemType Directory -Force -Path $lastGood | Out-Null
    }
    $stats = @{ Validated = 0; Corrupted = 0; Restored = 0; Unrecoverable = 0 }
    Get-ChildItem $stateDir -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
        $current = $_.FullName
        $backup = Join-Path $lastGood $_.Name
        $valid = $false
        # Parse-validate. ConvertFrom-Json throws on malformed JSON.
        try {
            $raw = Get-Content $current -Raw -ErrorAction Stop
            if ([string]::IsNullOrWhiteSpace($raw)) { throw "empty file" }
            $null = $raw | ConvertFrom-Json -ErrorAction Stop
            $valid = $true
        } catch {
            $valid = $false
        }
        if ($valid) {
            # Refresh known-good (overwrite any prior backup)
            Copy-Item -Path $current -Destination $backup -Force -ErrorAction SilentlyContinue
            $stats.Validated++
        } else {
            $stats.Corrupted++
            # Try to restore from last-known-good
            if (Test-Path $backup) {
                try {
                    # Verify backup is itself valid before restoring (paranoid)
                    $bakRaw = Get-Content $backup -Raw -ErrorAction Stop
                    $null = $bakRaw | ConvertFrom-Json -ErrorAction Stop
                    Copy-Item -Path $backup -Destination $current -Force -ErrorAction Stop
                    $stats.Restored++
                    Write-TaskLog -TaskName $TaskName -Message ("RECOVERED corrupted state file " + $_.Name + " from .lastgood")
                } catch {
                    $stats.Unrecoverable++
                    Write-TaskLog -TaskName $TaskName -Message ("CRITICAL unrecoverable corruption: " + $_.Name + " (current AND .lastgood unparseable)")
                }
            } else {
                $stats.Unrecoverable++
                Write-TaskLog -TaskName $TaskName -Message ("CRITICAL no .lastgood backup for " + $_.Name + " - corrupted file left in place for forensics")
            }
        }
    }
    return $stats
}

function Stop-ProcessTree {
    # Recursively kill a process AND all its descendants. Safe by construction:
    # only kills processes in the subtree rooted at $ParentId. Will NOT touch sibling
    # claude.exe processes (e.g., the user's interactive Claude Code session).
    #
    # Uses Win32_Process via CIM because Get-Process does not expose ParentProcessId.
    param(
        [Parameter(Mandatory)][int]$ParentId,
        [int[]]$Killed = @()
    )
    # Find direct children first
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ParentId" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        # Recurse depth-first: kill grandchildren before children, so we don't orphan them
        $Killed = Stop-ProcessTree -ParentId ([int]$child.ProcessId) -Killed $Killed
    }
    # Now kill the parent itself
    try {
        $proc = Get-Process -Id $ParentId -ErrorAction Stop
        Stop-Process -Id $ParentId -Force -ErrorAction Stop
        $Killed += $ParentId
    } catch {
        # Process already gone, or access denied. Either way, not our problem.
    }
    return ,$Killed
}

function Get-DescendantPids {
    # Return all descendant PIDs of $ParentId (does not include parent itself).
    # Used for diagnostic logging without killing.
    param([Parameter(Mandatory)][int]$ParentId)
    $all = @()
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ParentId" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        $all += [int]$child.ProcessId
        $all += Get-DescendantPids -ParentId ([int]$child.ProcessId)
    }
    return ,$all
}

function Stop-StaleClaudeProcesses {
    # Boot-time cleanup ONLY. Called at the top of each task script BEFORE we spawn
    # our own claude.exe. This is the safety net for the rare case where a prior
    # task script crashed (PowerShell host died, machine slept, etc.) leaving
    # claude.exe + MCP children behind with no parent script tracking them.
    #
    # Safety constraints:
    #   1. Only kills processes whose CommandLine contains BOTH "claude" AND a
    #      task-specific marker ("--print" + the project's WorkDir path).
    #   2. Only kills processes older than $StaleAfterMinutes (default 5).
    #      Anything younger is presumed in-flight from a fresh task, not stale.
    #   3. Refuses to run with $StaleAfterMinutes < 1 (would kill our own freshly-
    #      spawned process and the user's interactive Claude session).
    #   4. EXEMPT_DAEMONS list: persistent long-running daemons (Discord bridge,
    #      watcher, sniper grinder, etc.) MUST NOT be reaped. They live forever
    #      by design. Without this exemption, every heartbeat reaps Discord and
    #      the watchdog endlessly resurrects it (root cause of 26 restarts/day,
    #      diagnosed 2026-05-14 evening).
    #
    # Returns the array of killed PIDs (empty if nothing reaped).
    param(
        [int]$StaleAfterMinutes = 5
    )
    if ($StaleAfterMinutes -lt 1) {
        Write-Warning "Stop-StaleClaudeProcesses refused: StaleAfterMinutes=$StaleAfterMinutes is unsafe"
        return @()
    }

    # Persistent daemons that must NEVER be reaped, no matter how old.
    # Identified by substring in their python.exe CommandLine.
    $EXEMPT_DAEMONS = @(
        'discord-bridge.py',
        'discord-watcher.py',
        'discord-responder.py',
        # intraday_position_tracker.py (2026-08-10): read-only intraday capture of open
        # positions + exit-state (HWM / tp1_filled / profit_lock_armed). BY DESIGN a
        # long-running RTH daemon, so it belongs here on its own merits (it would be reaped
        # if ever launched with system python rather than the already-exempt backtest venv).
        #
        # CORRECTION OF RECORD, same session: the comment first committed here claimed the
        # reaper had killed its first run at the 5-minute mark. THAT WAS WRONG. Both early
        # exits were caused by piping the tracker through `head -N` -- head exits after N
        # lines, closes the pipe, and python dies on the broken pipe with exit 0. Run 1 was
        # piped through `head -40` and produced EXACTLY 40 lines; run 2 through `head -60`
        # and produced EXACTLY 60. The line counts matched the head limits precisely, and
        # unrelated python processes were still alive the whole time -- both facts were
        # available before the misdiagnosis and neither was checked. The 5-minute timing was
        # a coincidence that happened to match a documented scar. Kept as a warning: matching
        # a known failure signature is not the same as reading the evidence.
        'intraday_position_tracker.py',
        # market_hours_keepawake.py (2026-08-14): holds ES_SYSTEM_REQUIRED 09:10-16:10 ET so
        # the box cannot idle-sleep mid-session (the 2026-08-14 sleep gap 04:27-09:46 ET cost
        # -$1,569 via a wake-storm double entry + a stale-level top-tick buy). BY DESIGN a
        # long-running RTH daemon; reaping it silently re-enables mid-session sleep.
        'market_hours_keepawake.py',
        # guard_runner_slow.py / guard_runner_full.py (2026-08-20): both spawn a
        # `python -m pytest` child that runs for MINUTES -- the slow graduated guards
        # load the 16-month master CSV, and the full suite is ~9,895 tests. The reaper
        # kills project python older than 5 minutes, so without this exemption the
        # nightly guard runs would be silently truncated and would report whatever
        # partial result they had reached. Matching on the runner name covers the
        # parent AND the pytest child, since Stop-ProcessTree walks the subtree.
        'guard_runner_slow.py',
        'guard_runner_full.py',
        'sniper_pipeline.py',
        'sniper_overnight_grinder.py',
        'sniper_stage2_grinder.py',
        'sniper_stages345.py',
        'weekend-research-pipeline',
        'autoresearch\watcher_live.py',
        'autoresearch/watcher_live.py',
        # Backtest grind family: the backtest .venv interpreter is ONLY used for
        # long-running grids (mass_grind shards + phase2), never MCP servers. Exempting
        # the whole venv keeps the heartbeat reaper from killing the grind + its
        # multiprocessing.spawn workers mid-run (root cause of 12h of "silent crashes",
        # diagnosed 2026-06-25: heartbeat fires Stop-StaleClaudeProcesses every 3 min,
        # reaped the grind once it crossed the 5-min stale threshold).
        'backtest\.venv',
        'backtest/.venv',
        'mass_grind'
    )

    $cutoffUtc = [DateTime]::UtcNow.AddMinutes(-$StaleAfterMinutes)
    $killed = @()
    # CIM gives us CommandLine and CreationDate, neither of which Get-Process exposes.
    $candidates = Get-CimInstance Win32_Process -Filter "Name='claude.exe' OR Name='node.exe' OR Name='python.exe' OR Name='uv.exe' OR Name='uvx.exe'" -ErrorAction SilentlyContinue
    foreach ($p in $candidates) {
        if (-not $p.CommandLine) { continue }
        # Must reference our project workdir AND --print (the headless flag we use).
        # This refuses to touch interactive Claude sessions or unrelated node/python.
        $isOurs = ($p.CommandLine -like "*$WorkDir*") -or ($p.CommandLine -like "*tradingview-mcp*") -or ($p.CommandLine -like "*alpaca-mcp*") -or ($p.CommandLine -like "*alpaca_mcp*")
        if (-not $isOurs) { continue }
        # Daemon exemption: skip persistent long-running scripts (Discord, sniper, etc.).
        $isExempt = $false
        foreach ($marker in $EXEMPT_DAEMONS) {
            if ($p.CommandLine -like "*$marker*") { $isExempt = $true; break }
        }
        if ($isExempt) { continue }
        # Age check
        if ($p.CreationDate.ToUniversalTime() -gt $cutoffUtc) { continue }
        # Kill the whole subtree rooted here (so MCP grandchildren go too)
        try {
            $subKilled = Stop-ProcessTree -ParentId ([int]$p.ProcessId)
            $killed += $subKilled
        } catch {}
    }
    return ,$killed
}

function Get-RateLimitResetEt {
    # Parse a Claude Code rate-limit notice. Returns the next-occurrence [DateTime]
    # in ET, or $null if no rate-limit message is present.
    #
    # The Claude Code rate-limit emit format is:
    #   "You've hit your limit . resets H:MMam|pm (America/New_York)"
    # The middle separator is U+00B7 . but appears as cp1252 mojibake in some logs.
    # This regex matches on the time-and-zone tail and ignores the separator.
    param([string]$Text)
    if (-not $Text) { return $null }
    if ($Text -notmatch "hit your limit") { return $null }
    $rx = [regex]'resets\s+(\d{1,2}):(\d{2})\s*(am|pm)\s*\(America/New_York\)'
    $m = $rx.Match($Text)
    if (-not $m.Success) { return $null }
    $h = [int]$m.Groups[1].Value
    $min = [int]$m.Groups[2].Value
    $isPm = $m.Groups[3].Value.ToLower() -eq "pm"
    if ($h -eq 12) {
        if (-not $isPm) { $h = 0 }
    } elseif ($isPm) {
        $h += 12
    }
    $now = Get-EtNow
    $reset = [DateTime]::new($now.Year, $now.Month, $now.Day, $h, $min, 0)
    if ($reset -le $now) { $reset = $reset.AddDays(1) }
    return $reset
}

function Set-RateLimitCooldown {
    # Broadcast that we hit a rate limit, so other tasks (heartbeat ticks, watcher,
    # EOD wrappers) can skip-fast instead of spawning Claude only to fail.
    # File path: automation/state/rate-limit-cooldown.json
    # Schema: { reset_at_et, detected_at_et, detected_by_task }
    param(
        [Parameter(Mandatory)][DateTime]$ResetEt,
        [string]$TaskName = "unknown"
    )
    $cooldown = [ordered]@{
        reset_at_et      = $ResetEt.ToString("yyyy-MM-ddTHH:mm:ss")
        detected_at_et   = (Get-EtNow).ToString("yyyy-MM-ddTHH:mm:ss")
        detected_by_task = $TaskName
    }
    $file = Join-Path $WorkDir "automation\state\rate-limit-cooldown.json"
    try {
        ($cooldown | ConvertTo-Json -Compress) | Out-File -FilePath $file -Encoding utf8 -NoNewline -ErrorAction Stop
    } catch {
        Write-TaskLog -TaskName $TaskName -Message "RATE_LIMIT_COOLDOWN_WRITE_FAIL: $($_.Exception.Message)"
    }
}

function Test-RateLimitCooldown {
    # Returns the reset [DateTime] (ET) if a rate-limit cooldown is currently active,
    # else $null. Cleans up the file when the cooldown has passed.
    #
    # CLAUDE-PRINT-EXEMPT: if the cooldown file has "claude_print_exempt": true
    # (written by market_hours_circuit_breaker.py), scheduled `claude --print` tasks
    # (heartbeat, EOD, etc.) are exempt -- only interactive sessions are blocked.
    # Pass -TaskName "heartbeat" to benefit from this exemption.
    param([string]$TaskName = "")
    $file = Join-Path $WorkDir "automation\state\rate-limit-cooldown.json"
    if (-not (Test-Path $file)) { return $null }
    try {
        $cd = Get-Content $file -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        $reset = [DateTime]::Parse($cd.reset_at_et)
        if ((Get-EtNow) -ge $reset) {
            Remove-Item $file -Force -ErrorAction SilentlyContinue
            return $null
        }
        # claude_print_exempt: true means heartbeat/scheduled tasks bypass the cooldown.
        # Only interactive sessions (which the circuit breaker already killed) are blocked.
        if ($cd.claude_print_exempt -eq $true -and $TaskName -ne "") {
            # Exempt all scheduled tasks (they all have a TaskName). Only a bare
            # Test-RateLimitCooldown call with no TaskName blocks (i.e., interactive sessions).
            return $null
        }
        return $reset
    } catch {
        return $null
    }
}

function Invoke-ClaudeWithRetry {
    # Wrapper around Invoke-Claude that:
    #   1. Skips-ahead when a rate-limit cooldown is already known and the wait
    #      exceeds the budget.
    #   2. Detects rate-limit messages in the post-tick log, sleeps until the
    #      reset time + 30s buffer, and retries ONCE.
    #
    # Designed for low-cadence tasks (EOD summary, daily review, analyst, manager)
    # where a missed fire = lost daily artifact. NOT for heartbeat ticks (those
    # use Invoke-Claude directly + skip-ahead via Test-RateLimitCooldown).
    #
    # Passes every parameter through to Invoke-Claude verbatim, plus accepts
    # -MaxRateLimitWaitSec (default 7200 = 2h) which is consumed locally.
    param(
        [Parameter(Mandatory)][string]$PromptFile,
        [Parameter(Mandatory)][string]$TaskName,
        [double]$MaxBudgetUsd = 2,
        [string]$Model = "sonnet",
        [int]$TimeoutSec = 240,
        [ValidateSet("low","medium","high","xhigh","max")][string]$Effort = "medium",
        [string]$AgentName = "",
        [int]$MaxRateLimitWaitSec = 7200,
        # MiniMax fallback: when Claude is rate-limited AND retry would exceed budget,
        # run this Python script instead. The script must produce the canonical output
        # file (analyst/manager/eod-summary path) so downstream tasks see something.
        # Per CLAUDE.md L54 + OP-3 (cost discipline).
        [string]$FallbackScript = "",
        [string[]]$FallbackArgs = @(),
        [int]$FallbackTimeoutSec = 300
    )

    # Helper: invoke the MiniMax fallback Python script. Returns its exit code.
    $invokeFallback = {
        param($reason)
        if (-not $FallbackScript) { return $null }  # no fallback registered
        Write-TaskLog -TaskName $TaskName -Message "FALLBACK_INVOKE reason=$reason script=$FallbackScript args=$($FallbackArgs -join ' ')"
        $fb = Invoke-PythonHidden -ScriptPath $FallbackScript -ArgList $FallbackArgs `
            -TaskName "$TaskName-fallback" -TimeoutSec $FallbackTimeoutSec
        Write-TaskLog -TaskName $TaskName -Message "FALLBACK_RESULT exit=$($fb.ExitCode)"
        return [int]$fb.ExitCode
    }

    # Skip-ahead: if a cooldown is already known and the wait would exceed budget,
    # fail fast (or call the fallback if one is registered).
    # CRITICAL (OP-32 fix verification 2026-05-22): pass TaskName so claude_print_exempt
    # takes effect for scheduled tasks. Without this, every scheduled Claude call would
    # skip-ahead even when the circuit breaker wrote an exempt cooldown.
    $existingCooldown = Test-RateLimitCooldown -TaskName $TaskName
    if ($existingCooldown) {
        $waitSec = [int]([math]::Max(0, ($existingCooldown - (Get-EtNow)).TotalSeconds + 30))
        if ($waitSec -gt $MaxRateLimitWaitSec) {
            Write-TaskLog -TaskName $TaskName -Message "RATE_LIMIT cooldown active until $($existingCooldown.ToString('HH:mm')) ET; wait=${waitSec}s exceeds max=${MaxRateLimitWaitSec}s"
            $fbExit = & $invokeFallback "cooldown-exceeds-budget"
            if ($null -ne $fbExit) { return $fbExit }
            return 1
        }
        if ($waitSec -gt 0) {
            Write-TaskLog -TaskName $TaskName -Message "RATE_LIMIT cooldown active; sleeping ${waitSec}s before first attempt"
            Start-Sleep -Seconds $waitSec
        }
    }

    # First attempt
    $exit = Invoke-Claude -PromptFile $PromptFile -TaskName $TaskName `
        -MaxBudgetUsd $MaxBudgetUsd -Model $Model -TimeoutSec $TimeoutSec `
        -Effort $Effort -AgentName $AgentName

    # Inspect the tail of this task's log for a rate-limit notice. Invoke-Claude
    # writes stdout to the dated log file; we tail it to detect.
    $today = (Get-EtNow).ToString("yyyy-MM-dd")
    $logFile = Join-Path $LogDir "$TaskName-$today.log"
    $tail = ""
    if (Test-Path $logFile) {
        try { $tail = (Get-Content $logFile -Tail 50 -Raw -ErrorAction SilentlyContinue) } catch { $tail = "" }
    }

    if ($exit -ne 0 -and $tail -match "hit your limit") {
        $reset = Get-RateLimitResetEt -Text $tail
        if ($reset) {
            Set-RateLimitCooldown -ResetEt $reset -TaskName $TaskName
            $waitSec = [int][math]::Max(60, ($reset - (Get-EtNow)).TotalSeconds + 30)
            if ($waitSec -gt $MaxRateLimitWaitSec) {
                Write-TaskLog -TaskName $TaskName -Message "RATE_LIMIT retry skipped: wait=${waitSec}s exceeds max=${MaxRateLimitWaitSec}s (reset=$($reset.ToString('HH:mm')) ET)"
                $fbExit = & $invokeFallback "retry-exceeds-budget"
                if ($null -ne $fbExit) { return $fbExit }
                return $exit
            }
            Write-TaskLog -TaskName $TaskName -Message "RATE_LIMIT detected; sleeping ${waitSec}s until reset=$($reset.ToString('HH:mm')) ET"
            Start-Sleep -Seconds $waitSec
            Write-TaskLog -TaskName $TaskName -Message "RATE_LIMIT retry-attempt starting"
            $exit = Invoke-Claude -PromptFile $PromptFile -TaskName $TaskName `
                -MaxBudgetUsd $MaxBudgetUsd -Model $Model -TimeoutSec $TimeoutSec `
                -Effort $Effort -AgentName $AgentName
            Write-TaskLog -TaskName $TaskName -Message "RATE_LIMIT retry-attempt exit=$exit"
            # If the retry ALSO got rate-limited (rare but possible if reset window shifted), try fallback.
            if ($exit -ne 0) {
                $retryTail = ""
                if (Test-Path $logFile) {
                    try { $retryTail = (Get-Content $logFile -Tail 50 -Raw -ErrorAction SilentlyContinue) } catch {}
                }
                if ($retryTail -match "hit your limit") {
                    $fbExit = & $invokeFallback "retry-also-rate-limited"
                    if ($null -ne $fbExit) { return $fbExit }
                }
            }
        }
    }

    return $exit
}

function Invoke-Claude {
    # Run claude --print with a hard wall-clock timeout. On timeout, kill the entire
    # process tree we spawned (claude.exe + MCP children). Safe by construction:
    # we know our exact PID, we kill only our descendants, never sibling processes.
    #
    # claude --print has no native wall-clock cap (only --max-budget-usd, which a
    # slow-thinking model can sit inside for hours). 2026-05-07 first run: model
    # produced 4-minute reasoning blocks between tool calls, ate 12 min of wall
    # clock at $1.23 burn, exited budget-remaining but with zero state writes.
    param(
        [string]$PromptFile,
        [string]$TaskName,
        [double]$MaxBudgetUsd = 2,
        [string]$Model = "sonnet",
        [int]$TimeoutSec = 240,
        # Heartbeat = "low" (lean prompt, one-line output). Premarket/EOD/Review = "medium"
        # (deeper reasoning, still bounded). "high"/"xhigh"/"max" reserved for ad-hoc.
        [ValidateSet("low","medium","high","xhigh","max")]
        [string]$Effort = "medium",
        # Optional: persona name from .claude/agents/{name}.md (e.g. "analyst", "scout", "gamma")
        # When set, adds --agent <AgentName> to the claude invocation so the agent persona
        # file is loaded as the system prompt context. Persona scripts MUST use this instead
        # of bare "& claude.exe --agent X" to ensure correct $ClaudeExe path.
        [string]$AgentName = ""
    )
    if (-not (Test-Path $PromptFile)) {
        Write-TaskLog -TaskName $TaskName -Message "ERROR prompt file missing: $PromptFile"
        return 1
    }

    # Pre-flight: refuse to spawn if disk is critically low. A state write that
    # fails with ENOSPC produces a partial JSON the next task can't parse.
    $disk = Test-DiskSpaceAvailable
    if (-not $disk.OK) {
        $diskMsg = "ABORT_LOW_DISK: free=" + $disk.FreeMB + "MB threshold=" + $disk.MinMB + "MB - refusing to invoke claude (state writes would risk corruption)"
        Write-TaskLog -TaskName $TaskName -Message $diskMsg
        return 28  # ENOSPC convention
    }

    # Multi-Agent Gamma 2.0 Big Win #9: per-task PID lockfile.
    # Prevents two instances of the same task from running simultaneously
    # (e.g., a slow heartbeat tick still running when the next 3-min Task
    # Scheduler firing arrives). Source: claude-squad daemon PID pattern.
    $pidFile = Join-Path $WorkDir "automation\state\$TaskName.pid"
    if (Test-Path $pidFile) {
        try {
            $pidContent = Get-Content $pidFile -Raw -ErrorAction Stop
            $existingPid = [int]($pidContent.Trim().Split('|')[0])
            $startedAtRaw = if ($pidContent.Contains('|')) { $pidContent.Trim().Split('|')[1] } else { "" }
            $existingProc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
            if ($existingProc) {
                $ageSec = if ($startedAtRaw) {
                    try { ([DateTime]::UtcNow - [DateTime]::Parse($startedAtRaw).ToUniversalTime()).TotalSeconds } catch { 0 }
                } else { 0 }
                if ($ageSec -lt 300) {
                    Write-TaskLog -TaskName $TaskName -Message ("LOCK_BUSY pid=" + $existingPid + " age=" + [math]::Round($ageSec) + "s -- another instance running, skipping")
                    return 0
                }
                # Stale lock w/ live process older than 5 min -- kill it (claude-squad pattern).
                Write-TaskLog -TaskName $TaskName -Message ("LOCK_STALE killing pid=" + $existingPid + " age=" + [math]::Round($ageSec) + "s")
                try { Stop-ProcessTree -ParentId $existingPid | Out-Null } catch { }
            }
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        } catch {
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        }
    }
    # Write OUR pid + start time to the lock file. NOT under finally protection yet
    # (the existing finally below handles it via $pidFile remove).
    $startedAtIso = [DateTime]::UtcNow.ToString("o")
    "$PID|$startedAtIso" | Out-File -FilePath $pidFile -Encoding utf8 -NoNewline -ErrorAction SilentlyContinue

    # Pre-recovery: catch any corruption inherited from a prior crashed task before
    # we let claude read it. State files are the inputs to claude's reasoning;
    # corrupted inputs produce nonsense outputs.
    $preStats = Repair-StateFiles -TaskName $TaskName
    if ($preStats.Restored -gt 0 -or $preStats.Unrecoverable -gt 0) {
        $preMsg = "PRE_RECOVERY validated=" + $preStats.Validated + " restored=" + $preStats.Restored + " unrecoverable=" + $preStats.Unrecoverable
        Write-TaskLog -TaskName $TaskName -Message $preMsg
    }

    Push-Location $WorkDir
    $proc = $null
    $stdoutTask = $null
    $stderrTask = $null
    try {
        $startMsg = "=== START tick (timeout=" + $TimeoutSec + "s effort=" + $Effort + " budget=" + $MaxBudgetUsd + " model=" + $Model + " freeMB=" + $disk.FreeMB + ") ==="
        Write-TaskLog -TaskName $TaskName -Message $startMsg
        $logPath = Join-Path $LogDir "$TaskName-$((Get-EtNow).ToString('yyyy-MM-dd')).log"

        # Prepend a runtime-context header so prompts don't have to ask Claude what
        # time it is. Heartbeat prompts have asked the user "what is the current ET
        # time?" because they can't read system clock natively. Fix: tell them.
        $nowEt = (Get-EtNow).ToString("yyyy-MM-ddTHH:mm:ss")
        $todayEt = (Get-EtNow).ToString("yyyy-MM-dd")
        $weekday = (Get-EtNow).DayOfWeek.ToString()
        $contextHeader = @"
# RUNTIME CONTEXT (injected by wrapper, $TaskName)
- Current ET time: $nowEt
- Today's date (ET): $todayEt
- Weekday: $weekday
- Task: $TaskName
- Model: $Model
- Working directory: $WorkDir

---

"@

        # Multi-Agent Gamma 2.0 Big Win #6: state digest auto-injection.
        # Replaces 4-6 Read tool calls Claude would otherwise make to discover
        # current rule version, position state, kill-switch state, P&L. Saves
        # ~400-600 tokens/tick. Failure is non-fatal: if the digest script
        # crashes, we just skip it and Claude reads state files like before.
        $stateDigest = ""
        $digestScript = Join-Path $WorkDir "setup\scripts\session-start-digest.ps1"
        if (Test-Path $digestScript) {
            try {
                $stateDigest = & $digestScript -Markdown -WorkDir $WorkDir 2>$null | Out-String
                if ([string]::IsNullOrWhiteSpace($stateDigest)) { $stateDigest = "" }
            } catch {
                Write-TaskLog -TaskName $TaskName -Message ("DIGEST_FAIL: " + $_.Exception.Message + " (continuing without digest)")
                $stateDigest = ""
            }
        }
        $promptText = $contextHeader + $stateDigest + (Get-Content $PromptFile -Raw)

        # Build args. We pass --max-budget-usd as a string because PowerShell can
        # otherwise localize the decimal separator (e.g., "0,20" in some locales).
        $argList = @(
            "--print",
            "--permission-mode", "bypassPermissions",
            "--model", $Model,
            "--max-budget-usd", ($MaxBudgetUsd.ToString([System.Globalization.CultureInfo]::InvariantCulture)),
            "--effort", $Effort,
            "--output-format", "text"
        )
        # Persona agent: add --agent <name> when a .claude/agents/{name}.md persona is requested.
        # This loads the agent's system prompt so persona-specific context (Analyst, Scout, etc.)
        # is available. Uses $Global:ClaudeExe (full path) -- never bare "claude.exe".
        if ($AgentName -ne "") {
            $argList += @("--agent", $AgentName)
        }

        # ProcessStartInfo with redirected stdin/stdout/stderr. Async reads avoid
        # the classic deadlock where a full stdout pipe blocks the child process
        # while we're blocked waiting for stdin to be consumed.
        # PS 5.1 .NET Framework: Arguments is a single string (no ArgumentList).
        # We control the arg values, no embedded spaces/quotes, so simple join is safe.
        # Quote each arg defensively in case future args contain spaces.
        $argString = ($argList | ForEach-Object {
            if ($_ -match '\s|"') { '"' + ($_ -replace '"','\"') + '"' } else { $_ }
        }) -join ' '

        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $ClaudeExe
        $psi.Arguments = $argString
        $psi.RedirectStandardInput = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.WorkingDirectory = $WorkDir

        $proc = [System.Diagnostics.Process]::Start($psi)
        # Begin async reads BEFORE writing stdin (else child can block writing to a
        # full stdout buffer while we're trying to feed it).
        $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
        $stderrTask = $proc.StandardError.ReadToEndAsync()

        # Feed the prompt
        $proc.StandardInput.Write($promptText)
        $proc.StandardInput.Close()

        $rootPid = $proc.Id
        $timeoutMs = $TimeoutSec * 1000
        $completed = $proc.WaitForExit($timeoutMs)

        if (-not $completed) {
            # Wall-clock timeout fired. Enumerate descendants for the log, then
            # tree-kill from $rootPid. Bounded scope: only OUR subtree dies.
            $descendants = Get-DescendantPids -ParentId $rootPid
            $killMsg = "TIMEOUT after " + $TimeoutSec + "s - killing root pid=" + $rootPid + " plus " + $descendants.Count + " descendants"
            Write-TaskLog -TaskName $TaskName -Message $killMsg

            $killed = Stop-ProcessTree -ParentId $rootPid
            Write-TaskLog -TaskName $TaskName -Message ("  killed pids: " + (($killed | Sort-Object) -join ','))

            # Wait briefly for handles to release (CIM reports stale data otherwise)
            Start-Sleep -Milliseconds 300

            ("TIMEOUT_KILL: claude --print exceeded " + $TimeoutSec + "s wall clock. Tree-killed " + $killed.Count + " processes (root=" + $rootPid + "). Self-heal triggered.") | Out-File -Append -Encoding utf8 -FilePath $logPath

            # Mid-write kill recovery: if the kill happened during a state-file write,
            # restore from .lastgood so the next task isn't parsing torn JSON.
            $postKillStats = Repair-StateFiles -TaskName $TaskName
            if ($postKillStats.Restored -gt 0 -or $postKillStats.Unrecoverable -gt 0) {
                $postKillMsg = "POST_KILL_RECOVERY validated=" + $postKillStats.Validated + " restored=" + $postKillStats.Restored + " unrecoverable=" + $postKillStats.Unrecoverable
                Write-TaskLog -TaskName $TaskName -Message $postKillMsg
            }

            Write-TaskLog -TaskName $TaskName -Message "=== END tick exit=124 (timeout) ==="
            return 124
        }

        # Process exited cleanly. Drain async readers.
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        $exit = $proc.ExitCode

        # Write captured output
        if ($stdout) { $stdout | Out-File -Append -Encoding utf8 -FilePath $logPath }
        if ($stderr) { ("[stderr] " + $stderr) | Out-File -Append -Encoding utf8 -FilePath $logPath }

        # Rate-limit broadcast: if claude --print emitted a rate-limit notice,
        # write the cooldown state file so subsequent ticks/tasks can skip ahead
        # without spawning. This is fire-and-forget -- Invoke-Claude itself does
        # NOT retry (heartbeat needs that; EOD tasks use Invoke-ClaudeWithRetry).
        # See CLAUDE.md L54 (shared rate-limit foot-gun).
        $combinedOut = "$stdout`n$stderr"
        if ($combinedOut -match "hit your limit") {
            $resetEt = Get-RateLimitResetEt -Text $combinedOut
            if ($resetEt) {
                Set-RateLimitCooldown -ResetEt $resetEt -TaskName $TaskName
                Write-TaskLog -TaskName $TaskName -Message "RATE_LIMIT_BROADCAST reset_at=$($resetEt.ToString('yyyy-MM-ddTHH:mm:ss')) -- wrote cooldown for downstream tasks"
            }
        }

        # Post-recovery: validate everything claude wrote. Corruption introduced
        # this tick gets restored from .lastgood (which was refreshed by
        # pre-recovery, before this run made any writes). Net effect: this run
        # is essentially atomic at the state-file level.
        $postStats = Repair-StateFiles -TaskName $TaskName
        $postMsg = "POST_RECOVERY validated=" + $postStats.Validated + " corrupted=" + $postStats.Corrupted + " restored=" + $postStats.Restored + " unrecoverable=" + $postStats.Unrecoverable
        Write-TaskLog -TaskName $TaskName -Message $postMsg

        Write-TaskLog -TaskName $TaskName -Message "=== END tick exit=$exit ==="
        return $exit
    }
    catch {
        $errMsg = "EXCEPTION in Invoke-Claude: " + $_.Exception.Message
        Write-TaskLog -TaskName $TaskName -Message $errMsg
        # Best-effort cleanup if we have a PID
        if ($proc -and -not $proc.HasExited) {
            try { Stop-ProcessTree -ParentId $proc.Id | Out-Null } catch {}
        }
        return 1
    }
    finally {
        # Dispose to release handles. Idempotent.
        if ($proc) { try { $proc.Dispose() } catch {} }
        # Multi-Agent Gamma 2.0 Big Win #9: release PID lockfile.
        # Best-effort -- a leftover lockfile is reaped by the next tick's stale-lock check.
        if ($pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }
        Pop-Location
    }
}

function Test-HolidayFromAlpaca {
    # Lightweight holiday check: read the cached calendar in automation/state/calendar.json if present.
    # Otherwise default to "not holiday" -- Alpaca clock check inside the prompt is the real safety.
    $calFile = Join-Path $WorkDir "automation\state\calendar.json"
    if (-not (Test-Path $calFile)) { return $false }
    $cal = Get-Content $calFile -Raw | ConvertFrom-Json
    $today = (Get-EtNow).ToString("yyyy-MM-dd")
    return ($cal.holidays -contains $today)
}

function Test-CdpReady {
    # Poll the CDP /json/version endpoint with retries. Used to VERIFY a relaunch actually
    # worked instead of assuming "we ran the launch script" == "CDP is back" (2026-07-31
    # incident: Gamma_TvWatchdog logged RELAUNCH_KILL at both 09:05 and 09:10 ET while CDP
    # stayed down the whole time -- self_check.py was the only thing that eventually caught
    # it, ~5-10min later. Neither STATUS.md alert line distinguished "attempted" from
    # "worked", so the outage silently ran ~70+ min across multiple watchdog cycles before
    # a human/session noticed via a DIFFERENT producer. This closes that visibility gap.)
    param(
        [int]$Port = 9222,
        [int]$TimeoutSec = 12,
        [int]$PollIntervalSec = 2
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest "http://localhost:$Port/json/version" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds $PollIntervalSec
    }
    return $false
}

function Invoke-TvLaunchSafe {
    # FIX (2026-07-06): serialized, crash-safe wrapper around launch_tv_debug.ps1.
    #
    # (1) run-launch-tv.ps1 got a 2026-06-15 fix (ErrorActionPreference='Continue' around
    #     the child-process call) because PS 5.1 wraps a native command's stderr as a
    #     TERMINATING NativeCommandError under the inherited 'Stop' preference from this
    #     file -- that's the original "TV came up but CDP was never verified -> heartbeat
    #     ran all morning on ERROR_TV" bug. run-tv-watchdog.ps1 grew THREE separate call
    #     sites invoking the identical pattern and never got that fix -- confirmed via
    #     direct diff of both scripts, 2026-07-06.
    # (2) Gamma_LaunchTV and Gamma_TvWatchdog can both decide to kill+relaunch in the same
    #     tick (confirmed 2026-07-06: both fired the identical -Kill command at the
    #     identical second, 09:43:32 ET, after an overnight PC-off gap). A short lock file
    #     serializes them so only one kill+relaunch runs at a time.
    # (3) FIX (2026-07-31, live incident): the return value used to be {skipped} only -- a
    #     caller had NO way to know whether the relaunch actually restored CDP, only that it
    #     was attempted. Now self-verifies via Test-CdpReady and returns `healed` too, so
    #     run-tv-watchdog.ps1 can escalate LOUDLY the same tick a relaunch fails to fix CDP,
    #     instead of silently re-logging "relaunch_kill" every 5min while the outage grows.
    #
    # Guard OWED (executor died pre-guard, 2026-07-09): text-assertion test over this .ps1 (no
    # Pester harness, so the guard checks the shipped .ps1 text for the fixed pattern).
    param(
        [Parameter(Mandatory)][string]$LaunchScript,
        [Parameter(Mandatory)][string]$LogFile,
        [switch]$Kill,
        [int]$Port = 9222,
        # 12 -> 90 (2026-08-06, measured): a cold TV relaunch on this box takes >29s to serve
        # CDP (launch_tv_debug.ps1's own 20s poll expired at 18:49:14 ET with CDP still down;
        # CDP confirmed up by 18:52 ET). A 12s post-child poll structurally cannot see a
        # genuine heal on a cold relaunch, so every REAL relaunch would log *_FAILED and spam
        # the STATUS.md BROKEN block even when the heal worked. 90s keeps the whole tick
        # (child <=~25s + poll) well under Gamma_TvWatchdog's PT4M ExecutionTimeLimit.
        [int]$CdpTimeoutSec = 90
    )
    $lockFile = Join-Path $WorkDir "automation\state\tv-launch.lock"
    if (Test-Path $lockFile) {
        $ageSec = ((Get-Date) - (Get-Item $lockFile).LastWriteTime).TotalSeconds
        if ($ageSec -lt 30) {
            return @{ skipped = $true; healed = $false; reason = "lock_held age=$([int]$ageSec)s" }
        }
        Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType File -Path $lockFile -Force -ErrorAction SilentlyContinue | Out-Null
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # FIX (2026-08-05 live incident): `@killArg` array-SPLAT into a NATIVE command
        # (powershell.exe) does not splat the way it does for a cmdlet -- it emits a malformed
        # token that the child binds POSITIONALLY to launch_tv_debug.ps1's [int]$Port, throwing
        # `PSArgumentException: value of argument "name" is not valid` BEFORE the script body
        # runs. Net effect: Invoke-TvLaunchSafe -Kill NEVER launched anything; the script did
        # not execute a single line. Silent because (a) the child's failure only reached the
        # log file, and (b) `healed` is computed from Test-CdpReady, which returns TRUE whenever
        # TV happens to already be alive -- so a total no-op reported healed=true.
        # Observed: every 5-min tick of 2026-07-31 (relaunch_kill_FAILED x8) and 2026-08-05
        # 08:50 ET after J's PC restart. Build ONE explicit argv array instead -- no splat.
        # Guard: backtest/tests/test_tv_launch_argv_2026_08_05.py (text-assertion; no Pester).
        $psArgs = @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
            '-NonInteractive', '-File', $LaunchScript
        )
        if ($Kill) { $psArgs += '-Kill' }
        # FIX (2026-08-06 evening, live-proven during the Monday-readiness watchdog drill):
        # the previous `& powershell.exe $psArgs 2>&1 | Out-File` pipeline BLOCKED until
        # TradingView itself exited. Mechanism: launch_tv_debug.ps1 starts TradingView.exe
        # via [Diagnostics.Process]::Start with UseShellExecute=$false and NO redirection,
        # so TV INHERITS the child powershell's stdout/stderr handles -- a PS pipeline only
        # completes when every writer closes the handle, and TV (hours-long) never does.
        # MASKED until the 2026-08-05 argv fix because the malformed splat killed the child
        # instantly (pipeline closed, function returned fast). Live repro 2026-08-06
        # 18:48 ET: the tick healed TV+CDP fine but hung 12+ min past the heal; under
        # Gamma_TvWatchdog's PT4M ExecutionTimeLimit the production tick would be KILLED
        # before Test-CdpReady / healed-logging ever ran -- the 2026-07-31 *_FAILED
        # escalation path was unreachable in exactly the scenario it was built for.
        # Start-Process + Wait-Process waits on the CHILD POWERSHELL ONLY (it exits
        # deterministically after its own <=20s CDP poll); TV inherits the sidecar FILE
        # handles instead of our pipeline -- an open file handle blocks nobody. Child
        # output is copied into $LogFile afterward so the log keeps its old shape.
        # Guard: backtest/tests/test_tv_launch_argv_2026_08_05.py (argv + non-blocking).
        $childOut = "$LogFile.child-out.log"
        $childErr = "$LogFile.child-err.log"
        try {
            $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $psArgs `
                -WindowStyle Hidden -PassThru `
                -RedirectStandardOutput $childOut -RedirectStandardError $childErr
            $null = Wait-Process -Id $proc.Id -Timeout 90 -ErrorAction SilentlyContinue
        } catch {
            "Invoke-TvLaunchSafe: Start-Process failed: $($_.Exception.Message)" |
                Out-File -Append -Encoding utf8 -FilePath $LogFile
        }
        foreach ($side in @($childOut, $childErr)) {
            try {
                if ((Test-Path $side) -and ((Get-Item $side).Length -gt 0)) {
                    Get-Content $side -ErrorAction Stop |
                        Out-File -Append -Encoding utf8 -FilePath $LogFile
                }
            } catch {
                "Invoke-TvLaunchSafe: child output left in $side (handle held by live TV)" |
                    Out-File -Append -Encoding utf8 -FilePath $LogFile
            }
        }
    } finally {
        $ErrorActionPreference = $prevEAP
        Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    }
    $healed = Test-CdpReady -Port $Port -TimeoutSec $CdpTimeoutSec
    return @{ skipped = $false; healed = $healed }
}

function Invoke-LevelRefreshSafe {
    # Self-heal a stalled Gamma_LevelRefresh: kill any stuck level-refresh process tree
    # (WMI command-line match -- no assumption about which wrapper layer hung) and relaunch
    # run-level-refresh.ps1 directly via a hidden powershell.exe -File call, bypassing the
    # wscript->pythonw->run_ps1_hidden.py double-hop Task Scheduler normally uses (fewer
    # hops = fewer places for a hang to hide from ExecutionTimeLimit).
    #
    # WHY (2026-07-30 incident, root-caused by Gamma_Conductor): Gamma_LevelRefresh's own
    # PT5M-repetition / IgnoreNew / PT3M-ExecutionTimeLimit Task Scheduler config went
    # silently dark for ~20h -- last good run 07-29 22:43 ET, nothing until a manual repair
    # at 18:57 ET on 07-30 -- with ZERO errors in either day's level-refresh log and ZERO
    # Task Scheduler recovery of its own. Every one of the day's 770 RTH decision rows
    # carried levels_active=[], falling the engine through to its worst cohort
    # (trendline-only, -$1,830/WR .19 vs +$6,895/66 for level-tied trades). Nothing
    # previously force-killed+relaunched a stuck instance -- this closes that gap the same
    # way Invoke-TvLaunchSafe closes the analogous TV/CDP-hang gap (identical shape: a
    # scheduled 5-min refresher can wedge with no signal, and the fix is the same
    # kill-the-tree-then-relaunch pattern, not a diagnosis of the original hang mechanism).
    #
    # Lock file mirrors Invoke-TvLaunchSafe's lock pattern but with a longer hold (200s,
    # not 30s) because a real refresh_levels_intraday.py run can legitimately take up to
    # the task's own PT3M ExecutionTimeLimit before Task Scheduler itself would kill it --
    # a shorter lock would let the watchdog's OWN relaunch look "stale" and double-fire.
    #
    # -LockFile (2026-08-01, WATCHDOG-TEST-LOCK-RACE de-flake, chip task_a85b1cb3): optional
    # override, defaulting to the UNCHANGED production path so every existing caller (just
    # run-tv-watchdog.ps1 today) behaves byte-identically. Added because the test suite was
    # calling this function against the real production lock path -- a shared-mutable-file
    # race against ANY other concurrent invocation (a paired/parallel test run, another
    # worktree's pytest, or the live watchdog itself), not a fetch/logic bug. See
    # test_level_refresh_watchdog_2026_07_30.py for the isolated-tmp_path caller.
    param(
        [Parameter(Mandatory)][string]$Script,
        [Parameter(Mandatory)][string]$LogFile,
        [string]$LockFile = (Join-Path $WorkDir "automation\state\level-refresh-watchdog.lock")
    )
    $lockFile = $LockFile
    if (Test-Path $lockFile) {
        $ageSec = ((Get-Date) - (Get-Item $lockFile).LastWriteTime).TotalSeconds
        if ($ageSec -lt 200) {
            return @{ skipped = $true; reason = "lock_held age=$([int]$ageSec)s"; killed_pids = @() }
        }
        Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType File -Path $lockFile -Force -ErrorAction SilentlyContinue | Out-Null
    $killedPids = @()
    try {
        $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -like "*refresh_levels_intraday.py*" -or
                $_.CommandLine -like "*run-level-refresh.ps1*"
            )
        })
        foreach ($p in $procs) {
            $killedPids += Stop-ProcessTree -ParentId ([int]$p.ProcessId)
        }
    } catch { }
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File $Script 2>&1 |
            Out-File -Append -Encoding utf8 -FilePath $LogFile
    } finally {
        $ErrorActionPreference = $prevEAP
        Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    }
    return @{ skipped = $false; killed_pids = $killedPids }
}

function Enter-ConductorFireLock {
    # Cross-fire mutual-exclusion lock shared by run-conductor.ps1 and
    # run-conductor-weekend.ps1 -- the two heavy STAGE 1-5 loop wrappers that pick
    # from the SAME automation/overnight/queue.md and can genuinely fire close
    # together (conductor: hourly 18:00-07:00 ET every day; conductor-weekend: every
    # 2h all day Sat/Sun -- both cadences overlap on weekend evenings).
    #
    # 2026-07-18 self-audit gap ("cross-fire coordination... to prevent concurrent
    # conductor fires from clobbering") + same-day CONCRETE evidence in STATUS.md:
    # conductor and conductor-weekend fired ~16:00-16:20 ET and ~16:02-16:20 ET the
    # SAME afternoon, independently derived and built the byte-identical fix for
    # F7-EXIT-SELL-ALL-REFIRE (real wasted duplicate-work cost), and a SEPARATE
    # overlapping pair collided on a `git stash` mid-edit the same day
    # (SINGLE-STRATEGY-REGISTRY-DESIGN fire had to recover via
    # `git checkout stash@{0} -- <files>`).
    #
    # Same proven pattern as Invoke-TvLaunchSafe's tv-launch.lock above: a FRESH
    # lock = a live peer -> caller must SKIP (the next scheduled wake tries again);
    # a STALE lock = a dead/crashed instance -> overwrite and proceed. Fail-open
    # (rail 2): this NEVER blocks J's interactive session, only serializes
    # automated conductor fires against EACH OTHER -- a killed/crashed fire's lock
    # simply ages past StaleMinutes and the next wake reclaims it.
    #
    # Guard: backtest/tests/test_conductor_fire_lock_2026_07_18.py (text-assertion +
    # a real subprocess round-trip, same convention as test_tv_launch_safe_2026_07_06.py
    # per the "Guard OWED" note on Invoke-TvLaunchSafe above -- no Pester harness here).
    param(
        [int]$StaleMinutes = 20,
        [string]$LockFile = (Join-Path $WorkDir "automation\state\conductor-fire.lock")
    )
    if (Test-Path $LockFile) {
        $ageMin = ((Get-Date) - (Get-Item $LockFile).LastWriteTime).TotalMinutes
        if ($ageMin -lt $StaleMinutes) {
            return @{ acquired = $false; lockFile = $LockFile; ageMinutes = $ageMin }
        }
    }
    try { (Get-Date).ToString("o") | Out-File -FilePath $LockFile -Encoding utf8 -Force } catch { }
    return @{ acquired = $true; lockFile = $LockFile; ageMinutes = 0 }
}

function Exit-ConductorFireLock {
    # Releases a lock acquired via Enter-ConductorFireLock. Always call from a
    # `finally` block so a thrown/early-exited fire still releases promptly instead
    # of relying solely on the StaleMinutes timeout to recover.
    param([string]$LockFile)
    if ($LockFile) { Remove-Item $LockFile -Force -ErrorAction SilentlyContinue }
}
