# SCHEDULED-TASKS.md — single source of truth for all Gamma_* scheduled tasks

> **Last reconciled:** 2026-06-01 (full audit + EOD/review/premarket pipeline re-added per J. Registry had drifted to claim 35 active vs 15 real; brought to truth, then 12 tasks re-registered → 27 active).
>
> **Governance:** Every active task must have an entry in "## Active". Registered-but-missing → ORPHAN_TASK. Active-entry-with-no-task → STALE_REGISTRY_ENTRY. Tasks under "## Reference" are intentionally NOT parsed (knowledge only).
>
> **Audit:** `python setup/scripts/audit_scheduled_tasks.py` runs daily via `Gamma_CryptoDaily` → `automation/state/scheduled-tasks-audit.json` + STATUS.md alerts.

## Active tasks (current production)

27 registered: 6 trading + 1 TV-health + 1 exec-watch + 2 watcher + 2 premarket-intel + 9 EOD/review + 3 crypto + 3 kitchen.

| Task | Cadence | Cost/fire | Why it exists |
|---|---|---|---|
| `Gamma_LaunchTV` | 08:00 ET weekdays | $0 | Launches TradingView + CDP:9222. No-op if already live. |
| `Gamma_TvWatchdog` | every 5 min, 08:05-16:00 ET wd | $0 | **"no TV = no trades" fix (2026-06-01).** Relaunches TV/CDP on mid-session death; flags stale heartbeat. Idempotent. |
| `Gamma_Premarket` | 08:30 ET weekdays | ~$0.20 | Daily bias, levels, journal seed, rule-pin check. |
| `Gamma_Heartbeat` | every 3 min, 09:30-15:55 ET | ~$0.05/tick | THE engine — Gamma-Safe-1. |
| `Gamma_Heartbeat_Aggressive` | every 3 min, 09:30-15:55 ET | ~$0.05/tick | THE engine — Gamma-Risky-2. |
| `Gamma_EodFlatten` | 15:55 ET weekdays | ~$0.10 | Force-close open 0DTE (Safe). |
| `Gamma_EodFlatten_Aggressive` | 15:55 ET weekdays | ~$0.10 | Force-close open 0DTE (Bold). |
| `Gamma_GhostOrderReconciler` | every 1 min, 09:30-15:55 ET wd | $0 | Detects ENTER decisions with no matching Alpaca fill (silent MCP order failures). Alert-only, never places orders. Re-added 2026-06-01. |
| `Gamma_WatcherLive` | every 5 min, market hours | $0 | OP-21 watch-only setups (ORB, RECLAIM, PIN_FADE, BEARISH_REJECTION_MORNING). |
| `Gamma_WatcherGrader` | 17:10 ET weekdays | $0 | Grades watcher observations (would_be_outcome). |
| `Gamma_ScoutPremarket` | 05:30 ET weekdays | ~$0.30 | OP-28 macro/news scan → Premarket. Re-added 2026-06-01. |
| `Gamma_SwarmPremarket` | 08:15 ET weekdays | ~$0.25 | 13-agent ensemble bias vote → Premarket. Re-added 2026-06-01. |
| `Gamma_EodSummary` | 16:00 ET weekdays | ~$0.50 | Daily EOD reflection + backtest sync. Re-added 2026-06-01. |
| `Gamma_SniperShadowEOD` | 16:05 ET weekdays | $0 | OP-16 SNIPER anchor-build shadow log. Re-added 2026-06-01. |
| `Gamma_EodDeepDive` | 16:30 ET weekdays | $0 | 13-stage Phase-2 EOD analysis. Re-added 2026-06-01. |
| `Gamma_DailyReview` | 16:30 ET weekdays | ~$0.10 | Predictions-vs-actual + tomorrow's levels. Re-added 2026-06-01. |
| `Gamma_AnalystEodReview` | 16:45 ET weekdays | ~$0.40 | OP-28 Analyst post-trade review → Chef inbox + mistakes log. Re-added 2026-06-01. |
| `Gamma_GymSession` | 17:00 ET weekdays | $0 | OP-29 daily chart-reading "physical exam" GREEN/YELLOW/RED. Re-added 2026-06-01. |
| `Gamma_ManagerDailyVerify` | 17:30 ET weekdays | ~$0.50 | OP-28 Manager verifies the daily loop, writes J's brief. Re-added 2026-06-01. |
| `Gamma_TreasurerWeekly` | Sun 16:00 ET | ~$0.20 | OP-28 risk + sizing audit, both accounts. Re-added 2026-06-01. |
| `Gamma_WeeklyReview` | Sun 18:00 ET | ~$0.50 | Weekly metrics + recommendations. Re-added 2026-06-01. |
| `Gamma_CryptoDaily` | 06:00 ET daily | $0 | OP-26 harness health + **runs the task-registry + leak audit** + grinder rotation. |
| `Gamma_CryptoRegression` | every 30 min, 24/7 | $0 | OP-26 chart-reading primitives regression (24/7 validation surface). |
| `Gamma_CryptoGrinderKeepalive` | every 5 min, 24/7 | $0 | OP-26 keeps `live_grinder.py` alive. |
| `Gamma_KitchenDaemonKeepalive` | every 5 min, 24/7 | $0 (daemon free-tier, $3/day cap) | OP-31 keeps `kitchen_daemon.py` alive. |
| `Gamma_KitchenSeeder` | hourly @ :20, 24/7 | $0 | OP-31 generates cook tasks. Skipped if backlog >= 25. |
| `Gamma_KitchenReviewer` | every 2h @ :45, 24/7 | $0 | OP-31 triages cook outputs. |

**Est. added daily cost from the 2026-06-01 re-add: ~$2.75/day LLM** (Scout $0.30 + Swarm $0.25 + EodSummary $0.50 + DailyReview $0.10 + Analyst $0.40 + Manager $0.50 + weekend Treasurer/WeeklyReview amortized). Within the $100/mo Max-5x budget (OP-3).

## Disabled tasks (registered but intentionally off)

_None currently registered in Disabled state._

## Reference — still removed since the 2026-05-23 reset (NOT registered; not parsed by audit)

> Run-scripts (`setup/scripts/run-*.ps1`) still exist for all of these; re-registering is fast if J wants them.

**Engine-eyes / observability:**
- `Gamma_WindowLeakDetectorKeepalive` — real-time EnumWindows leak detector. (Daily *static* leak scan still runs via `Gamma_CryptoDaily`; this was the real-time layer.) → `run-window-leak-detector-keepalive.ps1`
- `Gamma_PatternGymOvernight` (03:30) — nightly chart-pattern detector regression → `run-pattern-gym-overnight.ps1`
- `Gamma_NumericPulse1m` (1 min, mkt hrs) — minute chart-pattern forensics → `run-numeric-pulse-1m.ps1`
- `Gamma_ChartVisionObserver` (6 min, mkt hrs) — **~$67/mo, the only expensive one** — vision observation layer → `run-chart-vision-observer.ps1`
- `Gamma_WatcherMorningReport` (08:00) → `run-watcher-morning-report.ps1`
- `Gamma_WatcherReplay` (Sun 17:00) → `run-watcher-replay.ps1`
- `Gamma_SelfAudit` — superseded by `Gamma_CryptoDaily`'s audit.
- `Gamma_DiscordWatchdog` (5 min) — discord bridge restart → `run-discord-responder.ps1` (handled ad-hoc).

**DO NOT RE-ADD — deliberately removed:**
- `Gamma_SessionGuard` + `Gamma_MarketHoursCircuitBreaker` — the OP-32 market-hours firewall that **locked J out of Claude entirely on 2026-05-22**. Self-discipline replaces it (CLAUDE.md top-of-file). Do not re-register without J authorizing a redesigned fail-open version.

**Already-superseded (pre-reset):**
- `Gamma_AR_Watchdog`, `Gamma_GrinderMonitor`, `Gamma_GrinderDiscordNotify` (grinder watchdogs — superseded by in-launcher PID tracking)
- `Gamma_DailyStatus`, `Gamma_MondayReadyCheck` (superseded by EOD/weekly pipelines)
- `Gamma_DiscordResponder` (2-way Discord, never enabled)

## Conventions (enforced by `audit_scheduled_tasks.py`)

1. **Window hidden.** `Execute=wscript.exe` (+ `run_hidden.vbs`/`run_exe_hidden.vbs`) OR `powershell.exe -WindowStyle Hidden`. Else → VISIBLE_WINDOW.
2. **Long-running Python uses `pythonw.exe`.** Else → PYTHON_NOT_PYTHONW.
3. **Every "## Active" entry must match a registered task** (STALE_REGISTRY_ENTRY) and **vice-versa** (ORPHAN_TASK).
4. **Silent > 26h → SILENT_TASK** (weekend false-positives expected for weekday-only tasks on Monday).

## Adding a new task — protocol

1. Update this file's "## Active" table FIRST.
2. Register via the `wscript + run_exe_hidden.vbs + run_ps1_hidden.py` hidden chain (clone an existing Principal: LaunchTV/TvWatchdog for GUI/TV tasks, Heartbeat for `claude --print` tasks).
3. Verify: `python setup/scripts/audit_scheduled_tasks.py` → no ORPHAN/STALE.
4. Note in CLAUDE.md / the relevant OP if doctrine-significant.

If you can't justify a task in one sentence in "Why it exists", **the task should not exist.**
