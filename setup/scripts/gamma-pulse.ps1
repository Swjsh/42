#requires -Version 5.1
<#
.SYNOPSIS
  One-screen Gamma autonomy pulse — answers "is everything running and how do I know?"
.DESCRIPTION
  Outputs a single-screen dashboard:
    1. Scheduled tasks state (LastRun / Result / NextRun)
    2. Live grinder PID + activity
    3. Validator pass rate trend (last 6 fires)
    4. Drift health + foot-gun catch rate
    5. Scheduled-task audit health
    6. Personas (Coach, Chef) — file presence + last invocation
    7. Background Claude agents in agent view
    8. Latest daily digest
  All read-only. ~1 second to run.
#>
$ErrorActionPreference = "Continue"
$root = "C:\Users\jackw\Desktop\42"
Set-Location $root

function _hr { Write-Host ("=" * 78) -ForegroundColor DarkGray }
function _h([string]$t) { Write-Host ""; Write-Host $t -ForegroundColor Cyan; _hr }

_hr
Write-Host "  GAMMA PULSE  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  ($(($env:USERDOMAIN + '\' + $env:USERNAME)))" -ForegroundColor White
_hr

# 1. Scheduled tasks (active Gamma_*)
_h "1. SCHEDULED TASKS"
$tasks = Get-ScheduledTask -TaskName "Gamma_*" -ErrorAction SilentlyContinue | Where-Object { $_.State -ne "Disabled" }
$tasks | ForEach-Object {
    $info = $_ | Get-ScheduledTaskInfo
    $neverRan = (-not $info.LastRunTime) -or ($info.LastRunTime.Year -lt 2020) -or ($info.LastTaskResult -eq 267011)
    $result = if ($neverRan) { "NEW  " } elseif ($info.LastTaskResult -eq 0) { "OK   " } elseif ($info.LastTaskResult -eq 267009) { "RUN  " } else { "FAIL " }
    $last = if ($neverRan) { "never " } else { $info.LastRunTime.ToString("MM/dd HH:mm") }
    $next = if ($info.NextRunTime) { $info.NextRunTime.ToString("MM/dd HH:mm") } else { "------" }
    $missed = $info.NumberOfMissedRuns
    Write-Host ("  {0,-35} {1} last={2} next={3} missed={4}" -f $_.TaskName, $result, $last, $next, $missed)
}

# 2. Live grinder process
_h "2. LIVE GRINDER"
$grinder = Get-WmiObject Win32_Process -Filter "Name='pythonw.exe' OR Name='pythonw3.13.exe' OR Name='python.exe' OR Name='python3.13.exe'" |
    Where-Object { $_.CommandLine -like '*live_grinder*' }
if ($grinder) {
    foreach ($p in $grinder) {
        $startStr = if ($p.CreationDate) {
            try { ([Management.ManagementDateTimeConverter]::ToDateTime($p.CreationDate)).ToString("MM/dd HH:mm") }
            catch { "?" }
        } else { "?" }
        Write-Host ("  ALIVE  PID={0,-7} name={1,-18} started={2}" -f $p.ProcessId, $p.Name, $startStr) -ForegroundColor Green
    }
} else {
    Write-Host "  DEAD  (Gamma_CryptoGrinderKeepalive should restart within 5 min)" -ForegroundColor Yellow
}
if (Test-Path "$root\crypto\data\scorecards\grinder.jsonl") {
    $iters = (Get-Content "$root\crypto\data\scorecards\grinder.jsonl" -ErrorAction SilentlyContinue).Count
    $lastWrite = (Get-Item "$root\crypto\data\scorecards\grinder.jsonl").LastWriteTime.ToString("MM/dd HH:mm")
    Write-Host ("  iterations={0}  last_write={1}" -f $iters, $lastWrite)
}

# 3. Validator pass rate trend (last 6)
_h "3. VALIDATORS (last 6 fires)"
if (Test-Path "$root\crypto\data\scorecards\history.jsonl") {
    $lines = Get-Content "$root\crypto\data\scorecards\history.jsonl" -Tail 6
    foreach ($line in $lines) {
        try {
            $d = $line | ConvertFrom-Json
            $verdict = if ($d.overall_pass) { "PASS " } else { "FAIL " }
            $color = if ($d.overall_pass) { "Green" } else { "Red" }
            Write-Host ("  {0,-25}  {1}  {2}/{3} stages" -f $d.started_at.Substring(0,19), $verdict, $d.passed, $d.stages) -ForegroundColor $color
        } catch {}
    }
}

# 4. Drift report
_h "4. DRIFT HEALTH + FOOT-GUN CATCH"
if (Test-Path "$root\crypto\data\scorecards\drift_report.json") {
    $d = Get-Content "$root\crypto\data\scorecards\drift_report.json" | ConvertFrom-Json
    $color = if ($d.overall_health -eq "GREEN") { "Green" } else { "Yellow" }
    Write-Host ("  overall_health  : {0}" -f $d.overall_health) -ForegroundColor $color
    Write-Host ("  fail_streak     : {0}" -f $d.consecutive_fail_streak)
    if ($d.foot_gun_catch_rate_24h) {
        Write-Host ("  foot-gun catch  : {0}/{1} = {2}%" -f $d.foot_gun_catch_rate_24h.catches, $d.foot_gun_catch_rate_24h.eligible_iterations, $d.foot_gun_catch_rate_24h.catch_rate_pct)
    }
    if ($d.source_parity_drift_24h) {
        Write-Host ("  v02 drift 24h   : {0}/{1} iters ({2}%)" -f $d.source_parity_drift_24h.iters_with_drift, $d.source_parity_drift_24h.iterations, $d.source_parity_drift_24h.drift_rate_pct)
    }
    if ($d.alerts.Count -gt 0) {
        Write-Host "  alerts          :"
        foreach ($a in $d.alerts) { Write-Host "    - $a" -ForegroundColor Yellow }
    } else {
        Write-Host "  alerts          : none" -ForegroundColor Green
    }
}

# 5. Task audit
_h "5. SCHEDULED-TASKS AUDIT"
if (Test-Path "$root\automation\state\scheduled-tasks-audit.json") {
    $a = Get-Content "$root\automation\state\scheduled-tasks-audit.json" | ConvertFrom-Json
    $color = if ($a.health -eq "GREEN") { "Green" } else { "Yellow" }
    Write-Host ("  health     : {0}" -f $a.health) -ForegroundColor $color
    Write-Host ("  active     : {0} registered, {1} in registry" -f $a.active_registered, $a.registry_active)
    Write-Host ("  disabled   : {0} registered, {1} in registry" -f $a.disabled_registered, $a.registry_disabled)
    Write-Host ("  flags      : {0}" -f $a.flags_count)
    foreach ($f in $a.flags) { Write-Host ("    [{0}] {1}: {2}" -f $f.flag, $f.task, $f.note) -ForegroundColor Yellow }
}

# 6. Personas
_h "6. PERSONAS (.claude/agents/)"
$personaDir = "$root\.claude\agents"
if (Test-Path $personaDir) {
    Get-ChildItem $personaDir -Filter "*.md" | ForEach-Object {
        $lines = (Get-Content $_.FullName).Count
        Write-Host ("  {0,-20}  {1,5} lines  modified={2}" -f $_.BaseName, $lines, $_.LastWriteTime.ToString("MM/dd HH:mm"))
    }
} else {
    Write-Host "  (no .claude/agents/ directory)"
}

# 7. Background Claude agents (if claude CLI available)
_h "7. BACKGROUND CLAUDE AGENTS (agent view)"
$claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
if ($claudeCmd) {
    $jobsDir = Join-Path $env:USERPROFILE ".claude\jobs"
    if (Test-Path $jobsDir) {
        $sessions = Get-ChildItem $jobsDir -Directory -ErrorAction SilentlyContinue
        if ($sessions) {
            Write-Host ("  {0} background sessions found:" -f $sessions.Count)
            foreach ($s in ($sessions | Sort-Object LastWriteTime -Descending | Select-Object -First 6)) {
                $stateFile = Join-Path $s.FullName "state.json"
                if (Test-Path $stateFile) {
                    try {
                        $state = Get-Content $stateFile | ConvertFrom-Json
                        $name = if ($state.name) { $state.name } else { $s.Name }
                        $status = if ($state.status) { $state.status } else { "?" }
                        Write-Host ("    {0,-12}  {1,-30}  {2}" -f $s.Name.Substring(0,8), $name, $status)
                    } catch {
                        Write-Host ("    {0}  (state.json unreadable)" -f $s.Name.Substring(0,8))
                    }
                }
            }
            Write-Host "  Tip: run 'claude agents' to open the full live view"
        } else {
            Write-Host "  no background sessions"
            Write-Host "  Tip: 'claude --bg --agent coach `"audit gym`"' to launch one"
        }
    } else {
        Write-Host "  agent view not yet initialized (no ~/.claude/jobs/)"
        Write-Host "  Tip: run 'claude agents' once to initialize"
    }
} else {
    Write-Host "  claude CLI not on PATH"
}

# 8. Latest daily digest
_h "8. LATEST DAILY DIGEST"
$today = Get-Date -Format "yyyy-MM-dd"
$digestPath = "$root\crypto\data\scorecards\daily\$today.md"
if (Test-Path $digestPath) {
    Write-Host "  $digestPath"
    Write-Host "  --- first 10 lines ---" -ForegroundColor DarkGray
    Get-Content $digestPath -Head 10 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host "  no digest for today yet (Gamma_CryptoDaily fires 06:00 ET)"
    $latest = Get-ChildItem "$root\crypto\data\scorecards\daily\" -Filter "*.md" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latest) {
        Write-Host "  most recent: $($latest.Name)"
    }
}

# 9. Quick commands
_h "9. QUICK COMMANDS"
Write-Host "  /coach              invoke Coach (1-fire audit)"
Write-Host "  /chef               invoke Chef (1-fire R&D iteration)"
Write-Host "  /pulse              re-run this status screen"
Write-Host "  claude agents       open Anthropic's background-agent view (live)"
Write-Host "  claude --bg --agent coach `"audit gym`"    launch Coach as detached background session"
Write-Host "  claude --bg --agent chef `"cook a new candidate`"   launch Chef detached"
Write-Host "  python crypto/validators/runner.py    run validator suite directly"
_hr
Write-Host ""
