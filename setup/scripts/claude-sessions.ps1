# claude-sessions.ps1 — one-glance view of what Claude is actually running.
# Separates: (1) the Desktop app shell, (2) live agent-mode chat backends (token burners),
# (3) the Gamma trading rig (Python — never kill). Read-only. Kills nothing.
# Usage:  powershell -ExecutionPolicy Bypass -File setup\scripts\claude-sessions.ps1

$ErrorActionPreference = 'SilentlyContinue'

function Age([datetime]$t) {
  if (-not $t) { return '   ?   ' }
  $d = (Get-Date) - $t
  if ($d.TotalDays  -ge 1) { return ('{0:0}d {1:0}h' -f $d.Days, $d.Hours) }
  if ($d.TotalHours -ge 1) { return ('{0:0}h {1:0}m' -f [math]::Floor($d.TotalHours), $d.Minutes) }
  return ('{0:0}m' -f $d.TotalMinutes)
}

# Walk up from this PowerShell's own PID to find the claude-code backend that spawned it.
$ppid = @{}; foreach ($x in (Get-CimInstance Win32_Process)) { $ppid[[int]$x.ProcessId] = [int]$x.ParentProcessId }
$procs = Get-CimInstance Win32_Process -Filter "Name='claude.exe'"
$codePids = @{}; foreach ($x in $procs) { if ($x.CommandLine -match 'claude-code\\[\d.]+\\claude\.exe') { $codePids[[int]$x.ProcessId] = $true } }
$me = 0; $cur = $PID; $hops = 0
while ($cur -and $hops -lt 12) { if ($codePids[$cur]) { $me = $cur; break }; $cur = $ppid[$cur]; $hops++ }
$live  = Get-Process -Id ($procs.ProcessId) -ErrorAction SilentlyContinue
$cpu   = @{}; foreach ($p in $live) { $cpu[$p.Id] = [math]::Round($p.CPU,0) }
$start = @{}; foreach ($p in $live) { $start[$p.Id] = $p.StartTime }
$ram   = @{}; foreach ($p in $live) { $ram[$p.Id] = [math]::Round($p.WorkingSet64/1MB,0) }

# --- Agent-mode chat backends = the claude-code CLI children (the token burners) ---
$sessions = @()
foreach ($p in $procs) {
  if ($p.CommandLine -match 'claude-code\\[\d.]+\\claude\.exe') {
    $model  = if ($p.CommandLine -match '--model\s+(\S+)')  { $matches[1] } else { '?' }
    $effort = if ($p.CommandLine -match '--effort\s+(\S+)') { $matches[1] } else { '?' }
    $resumed = if ($p.CommandLine -match '--resume') { 'resume' } else { 'new' }
    $sessions += [pscustomobject]@{
      PID     = $p.ProcessId
      Model   = $model -replace '^claude-',''
      Effort  = $effort
      Kind    = $resumed
      CPUsec  = [int]($cpu[[int]$p.ProcessId])
      RAM_MB  = [int]($ram[[int]$p.ProcessId])
      Age     = Age $start[[int]$p.ProcessId]
      This    = if ([int]$p.ProcessId -eq $me) { '<< THIS' } else { '' }
    }
  }
}

$appCount = ($procs | Where-Object { $_.CommandLine -notmatch 'claude-code\\[\d.]+\\claude\.exe' }).Count

Write-Host ""
Write-Host "CLAUDE SESSION MAP  ($((Get-Date).ToString('MM-dd HH:mm')) local)" -ForegroundColor Cyan
Write-Host ("-" * 64)
Write-Host ("Desktop app shell (Electron helpers) : {0} process(es) - ONE app, leave alone" -f $appCount) -ForegroundColor DarkGray
Write-Host ""
Write-Host ("Agent-mode chat backends : {0}  (these burn tokens)" -f $sessions.Count) -ForegroundColor Yellow
$sessions | Sort-Object CPUsec -Descending |
  Format-Table PID, Model, Effort, Kind,
    @{N='CPUsec';E={$_.CPUsec};A='right'},
    @{N='RAM_MB';E={$_.RAM_MB};A='right'},
    Age, This -AutoSize | Out-String | Write-Host

$heavy = $sessions | Where-Object { $_.This -eq '' -and $_.CPUsec -gt 300 } | Sort-Object CPUsec -Descending
if ($heavy) {
  Write-Host "Heaviest non-current sessions (close the tab if you're done with it):" -ForegroundColor Red
  foreach ($h in $heavy) { Write-Host ("  PID {0}  {1}/{2}  {3}s CPU  (age {4})" -f $h.PID,$h.Model,$h.Effort,$h.CPUsec,$h.Age) }
  Write-Host "  -> Close the CHAT TAB in the desktop app (clean). Don't End-Task mid-turn." -ForegroundColor DarkGray
  Write-Host ""
}

# --- Gamma trading rig (never kill) ---
$rig = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'kitchen_daemon|discord-bridge|discord-watcher|live_grinder|tv-watchdog|companion|shotgun_scalper|heartbeat|grinder|autoresearch|conductor|watcher' -and $_.CommandLine -notmatch 'multiprocessing.spawn' }
Write-Host ("Gamma trading rig : {0} python proc(es) - DO NOT KILL" -f ($rig.Count)) -ForegroundColor Green
foreach ($r in $rig) {
  $tag = if ($r.CommandLine -match '([\w-]+\.py)') { $matches[1] } elseif ($r.CommandLine -match '([\w-]+\.ps1)') { $matches[1] } else { 'python' }
  Write-Host ("  {0,-6} {1}" -f $r.ProcessId, $tag) -ForegroundColor DarkGreen
}
$workers = (Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -match 'multiprocessing.spawn' }).Count
if ($workers) { Write-Host ("  (+{0} backtest worker subprocesses)" -f $workers) -ForegroundColor DarkGreen }
Write-Host ""
