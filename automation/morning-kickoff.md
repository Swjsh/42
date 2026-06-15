# Morning kickoff — autonomy is wired

> As of 2026-05-05 EOD, the full daily lifecycle runs autonomously via Windows Task Scheduler. **J does not need to manually start sessions anymore.** This file documents the autonomous schedule and the manual-override fallback.

---

## Autonomous schedule (live)

All registered with `setup\install-tasks.ps1`. Verify anytime with:
```powershell
Get-ScheduledTask -TaskName 'Gamma_*' | Format-Table
```

| Time ET | Task | What it does |
|---|---|---|
| 08:00 | `Gamma_LaunchTV` | Launches TradingView with `--remote-debugging-port=9222` |
| 08:30 | `Gamma_Premarket` | Reads carry-over levels, runs protocol audit, re-verifies stale levels (switches to D when needed), pulls VIX, writes `today-bias.json` with falsifiable hypothesis, draws levels, seeds journal |
| 09:30 | `Gamma_Heartbeat` (start) | First heartbeat tick |
| 09:30–15:50 | `Gamma_Heartbeat` (repeat 3m) | 127 ticks over the session — adaptive cadence inside the prompt (HOT/BASE/COOL), change-only state writes, scans both bearish and bullish setups |
| 15:55 | `Gamma_EodFlatten` | Safety net — closes any 0DTE position not already closed by 15:50 time stop |
| 16:00 | `Gamma_EodSummary` | Appends EOD reflection to journal, computes day metrics, updates equity curve |
| 16:30 | `Gamma_DailyReview` | Strategic review (predictions vs actual), generates tomorrow's `key-levels.json`, flags any setup ready for promotion |

All tasks:
- Skip on weekends (script-level check)
- Skip on holidays (if `automation/state/calendar.json` is present)
- Wake the PC if asleep
- Run as J's user, no admin needed
- Log to `automation/state/logs/{task}-{date}.log`

---

## What J does on a normal trading day

**Nothing.** Walk away. Check the journal and Daily Review when convenient.

The PC must be:
- Powered on (or sleeping — Task Scheduler will wake it via WakeToRun)
- Logged in to J's account
- Connected to internet
- Have TradingView Desktop installed (the launch-tv task starts it)
- Have the workspace folder accessible at `C:\Users\jackw\Desktop\42`

That's it. Everything else is automatic.

---

## Manual override fallback (if autonomy fails)

If a task fails or J wants to run something manually:

```powershell
# Run any task body manually
& "C:\Users\jackw\Desktop\42\setup\scripts\run-premarket.ps1"
& "C:\Users\jackw\Desktop\42\setup\scripts\run-heartbeat.ps1"
& "C:\Users\jackw\Desktop\42\setup\scripts\run-eod-flatten.ps1"
& "C:\Users\jackw\Desktop\42\setup\scripts\run-eod-summary.ps1"
& "C:\Users\jackw\Desktop\42\setup\scripts\run-daily-review.ps1"
```

Each script does its own market-hours / weekday gating, so running manually outside the right window will silent-skip.

---

## Interactive override (if J wants to be in the loop)

If J wants to talk to Gamma during market hours alongside the autonomous loop:

1. Open Claude Code interactive session.
2. Send a brief context message: "Autonomous loop is running. I'm just here to observe / override. Don't change state files unless I tell you to."

The autonomous heartbeat owns state writes. An interactive session reading state is fine; an interactive session WRITING state could collide with the heartbeat. Default: read-only observation.

---

## Logs and observability

Every task writes a log to `automation/state/logs/{task}-{YYYY-MM-DD}.log`. Logs include:
- Timestamp (ET)
- "FIRE" line when the task starts
- Full claude --print output
- Exit code

Quick health check:
```powershell
Get-ChildItem "C:\Users\jackw\Desktop\42\automation\state\logs\*$(Get-Date -Format 'yyyy-MM-dd').log" |
    Select-Object Name, LastWriteTime, Length
```

---

## Cost considerations

Each autonomous tick costs API tokens. Rough estimate per session:
- Premarket: 1 invocation, ~$0.30
- Heartbeat: ~127 ticks × ~$0.05 (light) to ~$0.20 (heavy) = $6–$25/day
- EOD: 2 invocations, ~$0.30
- Daily Review: 1 invocation, ~$0.30

**Per session budget: $7–$26/day. ~$1,500–$6,500/year for paper trading.**

Each script has a `--max-budget-usd` cap to prevent runaway costs. Heartbeat capped at $1/tick.

To cut costs: lengthen heartbeat cadence (5 min instead of 3 min would halve cost) or implement true adaptive cadence with multi-trigger Task Scheduler config.

---

## Uninstalling autonomy

If something is wrong and J wants to fully stop autonomy:

```powershell
& "C:\Users\jackw\Desktop\42\setup\uninstall-tasks.ps1"
```

This removes all 6 Gamma_* tasks. Re-install anytime with `install-tasks.ps1`.

---

## What's NOT autonomous (deferred)

- **Discord webhook for push notifications** — J explicitly skipped per request.
- **Real-money trade confirmation flow** — not relevant until paper graduation.
- **Automatic strategy parameter tuning** — manual via `params.json` for now.
- **Calendar integration for news/FOMC/CPI** — basic check inside premarket prompt; could be enhanced.

These are not blockers. The core loop is fully autonomous as of today.
