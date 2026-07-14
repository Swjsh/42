# Premarket routine — fires at 08:30 ET weekdays.
# Self-heal: hard wall-clock cap 6 min, retry once on timeout/failure (but only
# if there's enough buffer before market open at 09:30).
. "$PSScriptRoot\_shared.ps1"

$task = "premarket"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) {
    Write-TaskLog -TaskName $task -Message "SKIP weekend"
    exit 0
}
if (Test-HolidayFromAlpaca) {
    Write-TaskLog -TaskName $task -Message "SKIP holiday"
    exit 0
}

# Self-heal: kill any stale claude/MCP processes from a prior crashed run.
$reaped = Stop-StaleClaudeProcesses -StaleAfterMinutes 5
if ($reaped.Count -gt 0) {
    Write-TaskLog -TaskName $task -Message "REAPED stale: $($reaped -join ',')"
}

# DETERMINISTIC breaker re-arm (2026-07-09 root-cause fix) -- runs BEFORE the LLM attempt
# and does NOT depend on it. Root cause of the 2026-07-09 incident: both circuit-breaker
# files stayed dated 2026-07-08 while the engine traded 2026-07-09 because the ONLY prior
# writer of a fresh starting_equity_today/equity_start_of_day was this script's LLM step
# (automation/prompts/premarket.md) -- and both claude attempts that morning failed
# instantly with "API Error: Unable to connect to API (ConnectionRefused)" because
# ~/.claude/settings.json now routes every claude session through a local
# claude-code-router gateway (127.0.0.1:3456, apiKeyHelper) that had died overnight with
# no auto-restart/keepalive (confirmed: no listener on 3456-3459, its own service.json PID
# long dead). daily_loss_guard.rearm() fetches live equity directly via Alpaca REST (same
# un-blockable path sight_beacon.py already uses) and idempotently re-arms ONLY when the
# breaker's stamped date != today ET -- so the kill-switch anchor can no longer silently go
# stale just because claude/CCR/the LLM step had a bad morning. Fail-open: any error here
# is logged and premarket continues exactly as before (this is a pure ADDITION, never a
# gate). The LLM step below still runs afterward and will simply see an already-armed-today
# breaker.
foreach ($acct in @("safe", "bold")) {
    try {
        $rearm = Invoke-PythonHidden -ScriptPath "setup\scripts\daily_loss_guard.py" `
            -ArgList @("--account", $acct, "--rearm", "--silent") `
            -TaskName "daily-loss-guard-rearm-$acct" `
            -TimeoutSec 15
        Write-TaskLog -TaskName $task -Message "REARM $acct exit=$($rearm.ExitCode) $($rearm.Stdout.Trim())"
    } catch {
        Write-TaskLog -TaskName $task -Message "REARM $acct failed (fail-open, premarket continues): $_"
    }
}

function Invoke-PremarketAttempt {
    param([int]$AttemptNum)
    Write-TaskLog -TaskName $task -Message "FIRE attempt=$AttemptNum et=$((Get-EtNow).ToString('HH:mm:ss'))"
    # 2026-05-07: bumped 360s -> 540s. Premarket prompt has 9 steps including options
    # chain, dealer levels, ES overnight, dark-pool aggregation. 360s wasn't enough for
    # Sonnet to complete reliably; first attempt today timed out at exactly 360s.
    # 540s + 540s retry = 1080s = 18min, but Task Scheduler ExecutionTimeLimit on
    # Gamma_Premarket is PT14M = 840s. So retry will only fit if attempt 1 finished
    # under ~290s. That's the deliberate trade — long timeout helps single-attempt
    # success rate; short retry budget is a fallback only.
    return Invoke-Claude `
        -PromptFile (Join-Path $WorkDir "automation\prompts\premarket.md") `
        -TaskName $task `
        -MaxBudgetUsd 3 `
        -TimeoutSec 540 `
        -Effort "medium"
}

$exit = Invoke-PremarketAttempt -AttemptNum 1

# Retry-once self-heal — only if there's still time before market open.
# Market opens at 09:30 ET. We need at least 5 min buffer for a retry to be useful.
if ($exit -ne 0) {
    $now = Get-EtNow
    $marketOpen = [DateTime]::new($now.Year, $now.Month, $now.Day, 9, 30, 0)
    $minutesUntilOpen = ($marketOpen - $now).TotalMinutes
    if ($minutesUntilOpen -gt 11) {
        Write-TaskLog -TaskName $task -Message ("RETRY exit=" + $exit + ", " + ([math]::Round($minutesUntilOpen,1)) + "min until open - attempting once more")
        # Reap anything left from the failed first attempt before retry. Use 1 min
        # cutoff (the prior attempt's processes were tree-killed at timeout, but MCP
        # children that the kill missed will be older than 1min by now). Avoids the
        # StaleAfterMinutes=0 refusal-write-warning path that broke retry on 2026-05-07.
        Stop-StaleClaudeProcesses -StaleAfterMinutes 1 | Out-Null
        Start-Sleep -Seconds 5
        $exit = Invoke-PremarketAttempt -AttemptNum 2
    } else {
        Write-TaskLog -TaskName $task -Message ("NO_RETRY exit=" + $exit + ", only " + ([math]::Round($minutesUntilOpen,1)) + "min until open - give up cleanly")
    }
}

# OP-33 / insight-#1: VERIFY THE WORK, not the exit code. The LLM can exit 0 without writing a
# bias (the 06-30 silent failure: claude returned 0, today-bias stayed dated yesterday, engine
# would have opened on a stale read). If today-bias is not dated today, the run FAILED -- fail
# LOUDLY (force a non-zero scheduler result + STATUS.md BROKEN) instead of exit-0-silent.
try {
    $biasFile = Join-Path $WorkDir "automation\state\today-bias.json"
    $todayEt  = $et.ToString("yyyy-MM-dd")
    $bias     = (Get-Content $biasFile -Raw -ErrorAction Stop | ConvertFrom-Json)
    $biasDate = $bias.date

    # 2026-06-30 / insight-#17b: the .date check ALONE is not enough. Both
    # refresh_levels_intraday and a manual hand-rebuild stamp today's date, so the gate
    # went GREEN on 06-30 even though the LLM "produced NO bias" (the today-bias was a
    # by-hand rebuild after a silent LLM failure). The gate must check that the
    # DELIVERABLE was authored THIS run, not just that the date is fresh.
    #   (a) updated_by must NOT look like a hand-rebuild / non-LLM author.
    #   (b) falsifiable_predictions must be a non-empty array (the LLM's actual work).
    #   (c) bias_note must be a real paragraph (length > 80), not a stub.
    $deliverableMsg = $null
    if ($biasDate -ne $todayEt) {
        $deliverableMsg = "today-bias.date=$biasDate != today $todayEt (no fresh bias written). Engine would open on a STALE bias."
    } else {
        $updatedBy = [string]$bias.updated_by
        $updatedByLc = $updatedBy.ToLowerInvariant()
        $bannedAuthor = @("interactive", "rebuilt", "by hand", "by_hand")
        $hitAuthor = $null
        foreach ($b in $bannedAuthor) {
            if ($updatedByLc.Contains($b)) { $hitAuthor = $b; break }
        }
        $preds = $bias.falsifiable_predictions
        $predCount = 0
        if ($null -ne $preds) { $predCount = @($preds).Count }
        $biasNote = [string]$bias.bias_note
        $biasNoteLen = $biasNote.Length

        if ($null -ne $hitAuthor) {
            $deliverableMsg = "today-bias.updated_by='$updatedBy' looks like a non-LLM hand-rebuild (matched '$hitAuthor') -- the premarket LLM did NOT author this run's deliverable."
        } elseif ($predCount -lt 1) {
            $deliverableMsg = "today-bias.falsifiable_predictions is empty ($predCount) -- the premarket LLM produced no predictions (silent failure)."
        } elseif ($biasNoteLen -le 80) {
            $deliverableMsg = "today-bias.bias_note is too short ($biasNoteLen chars <= 80) -- stub, not a real LLM-authored bias."
        }
    }

    if ($null -ne $deliverableMsg) {
        $msg = "PREMARKET SILENT FAILURE: claude exit=$exit but $deliverableMsg"
        Write-TaskLog -TaskName $task -Message $msg
        $statusMd = Join-Path $WorkDir "automation\overnight\STATUS.md"
        try { Add-Content -Path $statusMd -Value ("`n### BROKEN: premarket " + $todayEt + "`n- " + $msg + "`n") -Encoding utf8 } catch {}
        if ($exit -eq 0) { $exit = 3 }   # force a LOUD non-zero result so the scheduler + self_check see it

        # A5 (2026-07-14, analysis/deep-research/2026-07-14-premarket-reliability.md):
        # the LLM step just failed one of the 3 documented shapes (auth/routing outage,
        # hollow-success, or reaped-silent) -- before giving up, run the pure-Python
        # DETERMINISTIC fallback so the engine is not left on a fully stale bias. $0, no
        # LLM/MCP, un-blockable by the same CCR/auth outages that just killed the attempts
        # above (reuses sight_beacon/daily_loss_guard's direct Alpaca REST + yfinance
        # paths). It marks its own output degraded=true/source=deterministic_fallback and
        # writes ZERO falsifiable_predictions (never fabricates a qualitative call it can't
        # back) -- so it must be verified and reported SEPARATELY from a real LLM pass,
        # never silently reclassified as a full VERIFIED success.
        try {
            $fb = Invoke-PythonHidden -ScriptPath "setup\scripts\premarket_deterministic_fallback.py" `
                -ArgList @() -TaskName "premarket-deterministic-fallback" -TimeoutSec 30
            Write-TaskLog -TaskName $task -Message "FALLBACK exit=$($fb.ExitCode) $($fb.Stdout.Trim())"
        } catch {
            Write-TaskLog -TaskName $task -Message "FALLBACK invoke failed (fail-open, premarket stays BROKEN): $_"
        }

        try {
            $fbBias = (Get-Content $biasFile -Raw -ErrorAction Stop | ConvertFrom-Json)
            if ($fbBias.date -eq $todayEt -and $fbBias.degraded -eq $true -and $fbBias.source -eq "deterministic_fallback") {
                $degMsg = "PREMARKET DEGRADED: deterministic fallback covered for the failed LLM step ($deliverableMsg)"
                Write-TaskLog -TaskName $task -Message $degMsg
                # Distinct heading from BROKEN above -- self_check.py / a human diffing
                # STATUS.md must be able to tell "fallback covered it" (fresh, minimal,
                # honestly-labeled bias) apart from "still fully stale" (see spec point 4).
                try { Add-Content -Path $statusMd -Value ("`n### DEGRADED: premarket " + $todayEt + "`n- " + $degMsg + "`n") -Encoding utf8 } catch {}
                $exit = 0   # covered, not silent -- a degraded-fresh bias is not a hard scheduler failure
            } else {
                Write-TaskLog -TaskName $task -Message "FALLBACK did not produce a fresh degraded bias -- premarket stays BROKEN (exit=$exit)."
            }
        } catch {
            Write-TaskLog -TaskName $task -Message "FALLBACK verify errored (premarket stays BROKEN): $($_.Exception.Message)"
        }
    } else {
        Write-TaskLog -TaskName $task -Message ("VERIFIED today-bias dated " + $todayEt + " - premarket LLM authored a fresh bias (predictions + note + non-hand author).")
    }
} catch {
    Write-TaskLog -TaskName $task -Message ("premarket bias-verify errored (fail-open): " + $_.Exception.Message)
}
exit $exit
