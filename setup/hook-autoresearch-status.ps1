# UserPromptSubmit hook — surfaces the autoresearch watchdog status to Claude.
#
# Output is appended to Claude's context as a system reminder, so Claude
# proactively reports progress without the user having to ask.
#
# Quiet mode: outputs nothing if the watchdog report is "healthy" AND the
# user's prompt mentions a non-autoresearch topic. The point is to surface
# *meaningful* status changes, not spam every turn.

$ErrorActionPreference = 'Continue'
$ReportMd = "C:\Users\jackw\Desktop\42\backtest\autoresearch\_state\watchdog_report.md"
$ReportJson = "C:\Users\jackw\Desktop\42\backtest\autoresearch\_state\watchdog_report.json"
$LastShownFile = "C:\Users\jackw\Desktop\42\backtest\autoresearch\_state\.hook_last_shown"

if (-not (Test-Path $ReportJson)) { exit 0 }

try {
    $rep = Get-Content $ReportJson -Raw | ConvertFrom-Json
} catch {
    exit 0
}

# Skip silently if the report hasn't changed since last shown to Claude.
$reportTime = (Get-Item $ReportJson).LastWriteTime.Ticks
$lastShownTime = if (Test-Path $LastShownFile) {
    [int64](Get-Content $LastShownFile -Raw)
} else { 0 }

if ($reportTime -le $lastShownTime) { exit 0 }

# Only show on meaningful events: any issue OR a new KEEP since last shown OR more iterations.
$shouldShow = $false
if ($rep.issues -and $rep.issues.Count -gt 0) { $shouldShow = $true }
if ($rep.overall_keeps -gt 0) { $shouldShow = $true }
# Always show on first run (lastShownTime == 0).
if ($lastShownTime -eq 0) { $shouldShow = $true }

if (-not $shouldShow) { exit 0 }

# Build a compact status block.
$lines = @()
$badge = if ($rep.healthy) { "HEALTHY" } else { "NEEDS ATTENTION" }
$lines += "===== AUTORESEARCH STATUS [$badge] ====="
$lines += "Generated: $($rep.generated_at)"
$lines += "Total iters: $($rep.overall_iterations) | KEEPs: $($rep.overall_keeps) | keep rate: $([math]::Round($rep.overall_keep_rate * 100, 1))%"
$lines += ""

if ($rep.issues -and $rep.issues.Count -gt 0) {
    $lines += "ISSUES:"
    foreach ($i in $rep.issues) { $lines += "  ! $i" }
    $lines += ""
}

foreach ($m in $rep.modes) {
    if (-not $m.state_exists) { continue }
    $line = "  [$($m.mode)] iter=$($m.iterations) kept=$($m.keeps) reverted=$($m.reverts)"
    if ($m.validate_baseline -and $m.validate_baseline.n_trades) {
        $v = $m.validate_baseline
        $wr = [math]::Round([double]$v.win_rate * 100, 0)
        $line += " | val: $($v.n_trades)t ${wr}%WR `$$([math]::Round([double]$v.total_pnl, 0)) sharpe=$([math]::Round([double]$v.sharpe_daily, 2))"
    }
    $lines += $line

    if ($m.top_keeps -and $m.top_keeps.Count -gt 0) {
        $top = $m.top_keeps[0]
        $lines += "    top KEEP: iter $($top.iter) - $($top.param) -> $($top.new) | val sharpe $([math]::Round([double]$top.val_sharpe, 2))"
    }
    if ($m.notable_rejections -and $m.notable_rejections.Count -gt 0) {
        $lines += "    NOTE: $($m.notable_rejections.Count) REVERTs had val P&L > `$200 - inspect for gate tuning"
    }
}

$lines += ""
$lines += "Full report: backtest/autoresearch/_state/watchdog_report.md"
$lines += "Claude: lead with a 1-2 sentence summary of any new KEEPs or ISSUES if relevant to the user's prompt."
$lines += "==================================================="

# Stamp this report as shown.
$reportTime | Out-File -FilePath $LastShownFile -Encoding ascii -NoNewline

# Output goes to stdout -> appended to Claude's context.
$lines | ForEach-Object { Write-Output $_ }
