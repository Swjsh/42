# [ARCHIVED 2026-05-08] Cron entries — original Linux/macOS scheduler — SUPERSEDED

> **STATUS: SUPERSEDED.** This was the 2026-05-04 design for invoking the heartbeat via Linux/macOS `crontab`. The live system runs on Windows via Task Scheduler (deployed 2026-05-05). Six tasks registered, install via `setup\install-tasks.ps1`, see [`automation/morning-kickoff.md`](../morning-kickoff.md) for the live architecture.
>
> **Read instead:** [`automation/morning-kickoff.md`](../morning-kickoff.md) for the live Windows Task Scheduler architecture, plus `setup/install-tasks.ps1` / `setup/uninstall-tasks.ps1` / `setup/scripts/run-*.ps1` for the actual implementation.

---

# Cron entries — the heartbeat scheduler

> Add these to the trading rig's crontab (`crontab -e`). All times are local-rig time; ensure your rig's time zone is set to America/New_York or the cron times are converted accordingly.

---

## Assumptions

- Trading rig: Linux/macOS. (Windows: use Task Scheduler with equivalent commands.)
- Claude Code installed and `claude` is on the PATH.
- Workspace folder: `~/projects/gamma` (or wherever you put it — adjust the `cd` accordingly).
- The CLAUDE.md, MCPs, and state files are in the workspace folder.

---

## crontab entries

```cron
# Project Gamma — automated SPY 0DTE paper trading
# Time zone: assumes system clock is America/New_York. If not, convert.
# All cron lines source ~/.bashrc to inherit MCP env (e.g., Alpaca keys).

# 08:30 ET — premarket scan (Mon-Fri)
30 8 * * 1-5 cd ~/projects/gamma && /bin/bash -lc 'echo "Run premarket routine per automation/premarket.md" | claude --print --no-confirm >> automation/state/cron.log 2>&1'

# 09:30–15:50 ET — heartbeat every 3 minutes (Mon-Fri)
*/3 9 * * 1-5 cd ~/projects/gamma && /bin/bash -lc 'echo "Run heartbeat per automation/heartbeat.md" | claude --print --no-confirm >> automation/state/cron.log 2>&1'
*/3 10-15 * * 1-5 cd ~/projects/gamma && /bin/bash -lc 'echo "Run heartbeat per automation/heartbeat.md" | claude --print --no-confirm >> automation/state/cron.log 2>&1'

# 15:55 ET — EOD flatten (Mon-Fri)
55 15 * * 1-5 cd ~/projects/gamma && /bin/bash -lc 'echo "Run EOD flatten per automation/eod.md" | claude --print --no-confirm >> automation/state/cron.log 2>&1'

# 16:30 ET — EOD summary (Mon-Fri)
30 16 * * 1-5 cd ~/projects/gamma && /bin/bash -lc 'echo "Run EOD summary per automation/eod.md" | claude --print --no-confirm >> automation/state/cron.log 2>&1'
```

> **Note:** the heartbeat cron uses two lines (`*/3 9 * * 1-5` for the 09:00–09:59 hour and `*/3 10-15 * * 1-5` for 10:00–15:59) because cron doesn't natively express "every 3 min from 9:30 to 15:50." The heartbeat itself enforces the 9:30 start and 15:50 stop via the time-window check in step 2 of `heartbeat.md` — extra ticks before/after are no-ops.

---

## Sanity-check the install

After adding to crontab:
```bash
# View installed cron
crontab -l

# Tail the cron log to confirm heartbeats are firing during market hours
tail -f ~/projects/gamma/automation/state/cron.log

# Manual fire (to test outside market hours — heartbeat will exit early but log)
cd ~/projects/gamma && echo "Run heartbeat per automation/heartbeat.md (manual test)" | claude --print
```

---

## Pause the system

- **Soft pause:** `touch ~/projects/gamma/automation/state/kill-switch`
  - Heartbeat sees the file, logs "PAUSED", exits without trading.
  - Open positions still get managed (stops still fire) — only *new entries* are blocked.
- **Hard pause:** `crontab -e` and comment out the heartbeat lines.
  - System fully off. Open positions will NOT be managed by Gamma. Use only when system fully offline.

To resume: `rm ~/projects/gamma/automation/state/kill-switch` (soft) or restore the crontab lines (hard).

---

## DST and timezone gotchas

- US markets are in America/New_York. DST shifts twice a year.
- If the rig is set to a different time zone (e.g., UTC), ALL cron times shift. Either:
  - Set the rig system clock to America/New_York, OR
  - Use `CRON_TZ=America/New_York` at the top of the crontab (Linux only):
    ```cron
    CRON_TZ=America/New_York
    30 8 * * 1-5 ...
    ```
- Verify timezone on Sunday nights when DST changes.

---

## What happens if the rig is asleep / offline?

- Cron jobs miss. State is preserved. The next live tick picks up wherever it left off (heartbeat is stateless across ticks; state is on disk).
- If the rig sleeps mid-trade: open positions are NOT managed. **Don't let the rig sleep during market hours** when an autonomous position is open.
- Recommended: disable sleep on the trading rig during market hours. macOS: `caffeinate -d` while the heartbeat is supposed to be running. Or use a power profile that prevents sleep 9:00–16:30 ET on weekdays.
