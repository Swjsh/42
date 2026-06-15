# Discord Bridge Death-Loop Diagnostic — 2026-05-14

## Symptom

User reports: "Discord bridge keeps dying every ~15 min. We've restarted it multiple times today; it dies again."

Watchdog log evidence (`automation/state/logs/discord-watchdog-2026-05-14.log`):
- 26 RESTART events for `discord-bridge` between 08:32 and 16:32 ET (~one every 15-30 min)
- Same pattern for `discord-watcher`
- Each restart succeeds ("OK"), then bridge dies again 15 min later

## Root cause (confirmed)

`Stop-StaleClaudeProcesses` in `setup/scripts/_shared.ps1` was killing the Discord daemons.

Every Claude task script (`run-heartbeat.ps1`, `run-premarket.ps1`, `run-eod-summary.ps1`, `run-daily-review.ps1`, etc.) calls `Stop-StaleClaudeProcesses -StaleAfterMinutes 5` at startup as a safety net to reap orphaned `claude.exe` + MCP children from prior crashed task scripts.

The function's filter (line 187-192 pre-fix):
1. Enumerated all `python.exe` processes via WMI
2. Kept any whose CommandLine contained the project `$WorkDir` path (`C:\Users\jackw\Desktop\42`)
3. Reaped any older than 5 min

**Discord bridge and watcher both:**
- Run from `C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe` (matches `*$WorkDir*`)
- Are intentionally long-running (matches "older than 5 min")

Result: every heartbeat tick (every 3 min during market hours) reaped the bridge and watcher. The watchdog (every 15 min) resurrected them. The bridge process never lived more than ~5 min before getting killed by the next reap, but appeared "alive" briefly between reaps.

### Smoking gun

`heartbeat-2026-05-14.log` line: `09:57:03 ET REAPED stale: 31276,27800,29536,13416,12648,29820`

PID 29820 was a `discord-watcher.py` process. Heartbeat reaped it at 09:57:03. Watchdog rebooted it at 10:02:22. Same pattern repeated all day.

### Why the OP-25 lesson "Get-Process misses pythonw" did NOT apply

That earlier lesson was about diagnostic *liveness checks*. This bug is about an *aggressive killer*. Different layer, different bug.

## Fix applied

**File:** `setup/scripts/_shared.ps1`, function `Stop-StaleClaudeProcesses`.

Added an `$EXEMPT_DAEMONS` whitelist of CommandLine substrings for persistent long-running daemons that must NEVER be reaped:

```
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
```

Logic flow inside the foreach loop:
1. Old: workdir-match → age-check → kill
2. New: workdir-match → exempt-check → age-check → kill

Backward-compatible: any future short-lived python script under workdir is still reaped after 5 min as before.

## Verification (in-process, OP-22 verify-now-not-later)

Sourced the patched `_shared.ps1` and replicated the function's selection logic against the live process table. Result:

```
Would EXEMPT (saved by fix):
  PID=26888  discord-bridge.py
  PID=2996   discord-bridge.py
  PID=29820  discord-watcher.py
  PID=19468  discord-watcher.py

Would KILL:
  PID=4520   uvx alpaca-mcp-server
  PID=30076  uv tool uvx alpaca-mcp-server
  PID=25772  alpaca-mcp-server.exe
  PID=29964  cpython-3.10 alpaca-mcp-server
  PID=21868  node tradingview-mcp/server.js
```

All 4 Discord daemon PIDs exempted. Healthy stale MCP processes still reaped. Fix works.

Then performed a clean restart:
1. Killed all 4 stale Discord PIDs (duplicates from earlier today's death-loop)
2. Removed both `.pid` files
3. Manually invoked the watchdog → spawned ONE bridge (PID 11212) + ONE watcher (PID 34572), both writing to PID files correctly
4. Confirmed bridge logged `Discord bridge starting (poll=15s)` cleanly

## How to verify it stays up tomorrow

### Real-time (next 15-60 min)
```powershell
Get-Content C:\Users\jackw\Desktop\42\automation\state\logs\discord-watchdog-2026-05-14.log -Tail 5
```
After 17:00 ET, no new RESTART entries should appear unless the bridge genuinely crashed (which would be a different bug).

### Tomorrow morning (08:00 ET)
```powershell
$today = (Get-Date).ToString('yyyy-MM-dd')
$bridgeRestarts = Get-Content "C:\Users\jackw\Desktop\42\automation\state\logs\discord-watchdog-$today.log" | Select-String 'RESTART discord-bridge'
Write-Output "Restart count today: $($bridgeRestarts.Count)"
```
Pre-fix baseline: 26+/day. Post-fix expected: 0 (or 1-2 if Windows sleep/wake forced a real restart).

### Continuous (Wmi)
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*discord-bridge.py*' } | Select-Object ProcessId, CreationDate
```
The CreationDate should be from late evening 2026-05-14 onward, NOT recent (last few minutes), confirming the process is genuinely stable.

## Related cleanup (not done in this session, queued)

- `discord-bridge.py:57` and `discord-watcher.py:52` use deprecated `datetime.datetime.utcnow()`. Replace with `datetime.datetime.now(datetime.UTC)` (queued).
- The watchdog's `Start-Process -RedirectStandardOutput $log -RedirectStandardError "$log.err"` overwrites both files on every restart, losing prior log history. Consider `>>` append mode or rotated logs (queued).
- Bridge does not write a heartbeat timestamp to a file; only thing it writes during quiet ticks is the PID file (which doesn't update unless restarted). A bridge that's frozen but not dead would not be detected. Add `last_tick_at` to PID file or separate heartbeat file (queued).
