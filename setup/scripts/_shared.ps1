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

    $proc = [System.Diagnostics.Process]::Start($psi)
    if ($InputObject) {
        $proc.StandardInput.WriteLine($InputObject)
        $proc.StandardInput.Close()
    }
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
        try { $proc.Kill($true) } catch {}
        $exit = -1
    } else {
        $exit = $proc.ExitCode
    }

    $ts = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    $shortArgs = ($ArgList -join ' ')
    Add-Content -Path $logFile -Value "[$ts] Invoke-PythonHidden $ScriptPath $shortArgs exit=$exit"
    if ($stdout) { Add-Content -Path $logFile -Value "STDOUT:`n$stdout" }
    if ($stderr) { Add-Content -Path $logFile -Value "STDERR:`n$stderr" }

    return @{ ExitCode = $exit; Stdout = $stdout; Stderr = $stderr; LogFile = $logFile }
}

function Test-DiskSpaceAvailable {
    # Pre-flight: refuse to invoke claude if WorkDir's drive has < $MinFreeMB.
    # State writes, log writes, and JSONL session logs all need disk. A silent
    # ENOSPC during a state write produces a partial JSON the next task can't
    # parse. Refusing up-front is much better than recovering after.
    param([int]$MinFreeMB = 100)
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
        'sniper_pipeline.py',
        'sniper_overnight_grinder.py',
        'sniper_stage2_grinder.py',
        'sniper_stages345.py',
        'weekend-research-pipeline',
        'autoresearch\watcher_live.py',
        'autoresearch/watcher_live.py'
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
    $disk = Test-DiskSpaceAvailable -MinFreeMB 100
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
