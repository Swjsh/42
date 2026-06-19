# SCHEDULED-TASKS.md — single source of truth for all Gamma_* scheduled tasks

> **Last reconciled:** 2026-06-01 (full audit + EOD/review/premarket pipeline re-added per J. Registry had drifted to claim 35 active vs 15 real; brought to truth, then 12 tasks re-registered → 27 active).
>
> **Governance:** Every active task must have an entry in "## Active". Registered-but-missing → ORPHAN_TASK. Active-entry-with-no-task → STALE_REGISTRY_ENTRY. Tasks under "## Reference" are intentionally NOT parsed (knowledge only).
>
> **Audit:** `python setup/scripts/audit_scheduled_tasks.py` runs daily via `Gamma_CryptoDaily` → `automation/state/scheduled-tasks-audit.json` + STATUS.md alerts.

## Active tasks (current production)

36 registered: 8 trading + 1 health-beacon + 2 watcher + 3 premarket-intel + 8 EOD/review + 1 context-guard + 1 mcp-audit + 1 discord-presence + 3 crypto-gym + 3 kitchen + 3 futures (1 disabled) + 1 spend-summary + 1 level-alert-daemon. _Crypto TRADING heartbeat + 6 one-off Gamma_Sweep_* tasks retired 2026-06-17; see Reference._ _Gamma_HealthBeacon added 2026-06-18 (Phase 0a) — install via `setup/install-engine-health.ps1` (J/installer registers the live task)._ _Gamma_SniperShadowEOD retired 2026-06-18 (de-sprawl) — dead SNIPER autoresearch cluster archived; see Reference._ _Gamma_SpendSummary + Gamma_LevelAlertDaemon documented 2026-06-18 (the reconciliation test caught them registered-but-undocumented)._ _Gamma_Conductor + Gamma_DiscordResponder WIRED but NOT enabled — see the dedicated section below; they are intentionally absent from this Active table._

| Task | Cadence | Cost/fire | Why it exists |
|---|---|---|---|
| `Gamma_LaunchTV` | 08:00 ET weekdays | $0 | Launches TradingView + CDP:9222. No-op if already live. |
| `Gamma_TvWatchdog` | every 5 min, 08:05-16:00 ET wd | $0 | **"no TV = no trades" fix (2026-06-01).** Relaunches TV/CDP on mid-session death; flags stale heartbeat. Idempotent. |
| `Gamma_EmaSnapshot` | 08:20 ET weekdays | $0 | Phase 2 C1 fix (2026-06-18): computes EMA 13/20/48 + SMA 50 from SPY CSV → `automation/state/ema-snapshot.json` → patches today-bias.json key_levels EMA fields. Premarket TradingView read is primary; this is fallback + pre-seeder. |
| `Gamma_Premarket` | 08:30 ET weekdays | ~$0.20 | Daily bias, levels, journal seed, rule-pin check. |
| `Gamma_Heartbeat` | every 3 min, 09:30-15:55 ET | ~$0.05/tick | THE engine — Gamma-Safe-1. |
| `Gamma_Heartbeat_Aggressive` | every 3 min, 09:30-15:55 ET | ~$0.05/tick | THE engine — Gamma-Risky-2. |
| `Gamma_EodFlatten` | 15:55 ET weekdays | ~$0.10 | Force-close open 0DTE (Safe). |
| `Gamma_EodFlatten_Aggressive` | 15:55 ET weekdays | ~$0.10 | Force-close open 0DTE (Bold). |
| `Gamma_GhostOrderReconciler` | every 1 min, 09:30-15:55 ET wd | $0 | Detects ENTER decisions with no matching Alpaca fill (silent MCP order failures). Alert-only, never places orders. Re-added 2026-06-01. |
| `Gamma_HealthBeacon` | every 1 min, 24/7 | $0 | **Phase 0a fail-loud (2026-06-18).** Fuses both heartbeats + watcher feed (producer-dark detector) + TV watchdog + kill-switches + positions into ONE GREEN/YELLOW/RED verdict → `automation/state/engine-health.json`. Discord ping on RED *transition* only (no spam). Market-hours aware (quiet=GREEN overnight). Reads existing state only. Install: `setup/install-engine-health.ps1`. |
| `Gamma_WatcherLive` | every 5 min, market hours | $0 | OP-21 watch-only setups (ORB, RECLAIM, PIN_FADE, BEARISH_REJECTION_MORNING). |
| `Gamma_WatcherGrader` | 17:10 ET weekdays | $0 | Grades watcher observations (would_be_outcome). |
| `Gamma_ScoutPremarket` | 05:30 ET weekdays | ~$0.30 | OP-28 macro/news scan → Premarket. Re-added 2026-06-01. |
| `Gamma_SwarmPremarket` | 08:15 ET weekdays | ~$0.25 | 13-agent ensemble bias vote → Premarket. Re-added 2026-06-01. |
| `Gamma_EodSummary` | 16:00 ET weekdays | ~$0.50 | Daily EOD reflection + backtest sync. Re-added 2026-06-01. |
| `Gamma_EodDeepDive` | 16:30 ET weekdays | $0 | 13-stage Phase-2 EOD analysis. Re-added 2026-06-01. |
| `Gamma_DailyReview` | 16:30 ET weekdays | ~$0.10 | Predictions-vs-actual + tomorrow's levels. Re-added 2026-06-01. |
| `Gamma_AnalystEodReview` | 16:45 ET weekdays | ~$0.40 | OP-28 Analyst post-trade review → Chef inbox + mistakes log. Re-added 2026-06-01. |
| `Gamma_GymSession` | 17:00 ET weekdays | $0 | OP-29 daily chart-reading "physical exam" GREEN/YELLOW/RED. Re-added 2026-06-01. |
| `Gamma_ManagerDailyVerify` | 17:30 ET weekdays | ~$0.50 | OP-28 Manager verifies the daily loop, writes J's brief. Re-added 2026-06-01. |
| `Gamma_TreasurerWeekly` | Sun 16:00 ET | ~$0.20 | OP-28 risk + sizing audit, both accounts. Re-added 2026-06-01. |
| `Gamma_WeeklyReview` | Sun 18:00 ET | ~$0.50 | Weekly metrics + recommendations. Re-added 2026-06-01. |
| `Gamma_ContextGuard` | 16:10 ET daily | $0 (~$0.10 on RED) | Keeps CLAUDE.md <= 8K tokens (cache-read prefix); auto-trips `context-leanness` skill on RED, after-hours only. Spec: `docs/CONTEXT-LEANNESS.md`. Promoted from Proposed 2026-06-17 (was already registered). |
| `Gamma_McpWeeklyAudit` | Sun 18:30 ET | ~$0.10 | Weekly MCP round-trip health check (Alpaca Safe+Bold + TradingView tools) -- catches a hung-but-alive bridge the CDP port check misses. Added 2026-06-17. |
| `Gamma_DiscordBridge` | every 5 min, 24/7 | $0 | Keepalive for the Discord presence layer: bridge (outbox->Discord + inbox<-Discord) + trade-watcher (ENTER/EXIT/kill-switch -> Sharp-voice pings per automation/presence/SOUL.md). Idempotent. Added 2026-06-17. |
| `Gamma_CryptoDaily` | 06:00 ET daily | $0 | OP-26 harness health + **runs the task-registry + leak audit** + grinder rotation. |
| `Gamma_CryptoRegression` | every 30 min, 24/7 | $0 | OP-26 chart-reading primitives regression (24/7 validation surface). |
| `Gamma_CryptoGrinderKeepalive` | every 5 min, 24/7 | $0 | OP-26 keeps `live_grinder.py` alive. |
| `Gamma_KitchenDaemonKeepalive` | every 5 min, 24/7 | $0 (daemon free-tier, $3/day cap) | OP-31 keeps `kitchen_daemon.py` alive. |
| `Gamma_KitchenSeeder` | hourly @ :20, 24/7 | $0 | OP-31 generates cook tasks. Skipped if backlog >= 25. |
| `Gamma_KitchenReviewer` | every 2h @ :45, 24/7 | $0 | OP-31 triages cook outputs. |
| `Gamma_FuturesHeartbeat` | every 3 min, 09:30-15:55 ET weekdays | **DISABLED** — shares Max plan rate-limit pool with interactive sessions. Re-enable when shadow loop validates a free-tier model OR a dedicated API key is added. |
| `Gamma_FuturesPremarket` | 08:30 ET weekdays | ~$0.30 | MNQ key levels, VIX gate, bias, journal seed. Registered 2026-06-17. |
| `Gamma_FuturesEod` | 16:05 ET weekdays | ~$0.30 | Daily review: replay vs heartbeat, trades.csv update, running WR/expectancy. Registered 2026-06-17. |
| `Gamma_SpendSummary` | 23:30 ET daily | $0 | OP-3 cost discipline: walks Claude Code session JSONL + MiniMax telemetry -> `automation/state/spend-{date}.json` + `spend-daily.jsonl`; STATUS.md WARN if >$50/day. Pure Python. Install: `setup/install-spend-summary.ps1`. Documented 2026-06-18. |
| `Gamma_LevelAlertDaemon` | 09:25 ET weekdays (daemon runs to 16:05 ET) | $0 | Local SPY level-alert daemon: polls yfinance, writes `automation/state/live-alerts.jsonl`. No Claude cost. Install: `setup/scripts/install-level-alert-daemon-task.ps1`. Documented 2026-06-18 (experimental; uses `pwsh.exe` wrapper, not the canonical hidden chain). |

**Est. added daily cost from the 2026-06-01 re-add: ~$2.75/day LLM** (Scout $0.30 + Swarm $0.25 + EodSummary $0.50 + DailyReview $0.10 + Analyst $0.40 + Manager $0.50 + weekend Treasurer/WeeklyReview amortized). Within the $100/mo Max-5x budget (OP-3).

## Wired — NOT yet enabled (install script authored; J enables deliberately)

> These tasks have a complete install script + wrapper + prompt but are intentionally NOT registered as live tasks (same pattern as the health beacon: J runs the installer when ready). They are documented here so the registry is honest and the doc↔script reconciliation test stays green. To enable: run the named install script. To verify after: `python setup/scripts/audit_scheduled_tasks.py`.

| Task | Intended cadence | Install script | Why it exists |
|---|---|---|---|
| `Gamma_Conductor` | hourly 18:00–07:00 ET (after-hours ONLY) | `setup/install-conductor-task.ps1` | **The "Gamma drives" engine (Phase 1a).** Operationalizes `automation/overnight/wake-protocol.md`. Each fire = ONE bounded task: read `engine-health.json` + STATUS + the prioritized queue, pick the single highest-value ready item, fan out the right specialist persona via the Agent tool, validate (gym/tests), SHIP only if it clears the auto-ratify gate ELSE propose-and-ping-J. Prompt: `automation/prompts/conductor.md` (opus, `--agent gamma`). **Safety rails (baked into prompt + wrapper):** after-hours ONLY (never 09:30–15:55 ET — L54, don't starve the heartbeat), FAIL-OPEN (never blocks J — OP-32 scar), one-task-per-fire (no runaway), doctrine/params/orders are PROPOSE-only (reward-hacking guard). ~$1.50/fire. |
| `Gamma_DiscordResponder` | every 15 min 16:00–09:30 ET (after-hours) | `setup/install-discord-responder-task.ps1` | **The async approve/revoke bus (Phase 1c).** Consumes J's `ship <id>` / `shelve <id>` Discord replies (and 👍/👎 + id) -> resolves Conductor proposals in `conductor-proposals.jsonl`, appends audit to `conductor-approvals.jsonl` (pure Python, $0, works anytime). Free-form J Q&A via `claude --print` on **Haiku** (cheap), **after-hours only** — self-gates RTH per L54 so it never competes with `Gamma_Heartbeat` on the shared Max pool. Script: `setup/scripts/discord-responder.py`. Needs `Gamma_DiscordBridge` (inbound `poll_inbox`) alive. Fail-open. Was previously listed under Reference as "never enabled"; now wired. |

## Proposed (not yet registered — install when J approves)

| Proposed Task | Slot | Script | Why |
|---|---|---|---|
| `Gamma_ArchiveKeyLevels` | 16:05 ET weekdays | `setup/scripts/run-archive-key-levels.ps1` | Snapshots key-levels.json + today-bias.json daily for level-quality benchmarking. Phase 0 of trustworthy-levels milestone. $0 cost. |
| `Gamma_LevelQualityGym` | Sun 17:30 ET | `python analysis/level-quality/level_quality_gym.py` | Weekly level-quality scorecard GREEN/YELLOW/RED vs DM-null baseline. RED appends Known-broken to STATUS.md. $0 cost. |

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

**Retired 2026-06-17 (consolidation — J: two instruments only, crypto = gym-only):**
- `Gamma_CryptoHeartbeat` — BTC/USD scalper on Safe-2 paper (watch-only, never live). Files -> `archive/crypto-trading-retired-2026-06-17/`. The 3 Crypto* gym tasks are unaffected.
- `Gamma_Sweep_*` (Chandelier, ChandelierParams, NoTradeAfter, Runner, Tp1Frac, Tp1Prem) — one-off research sweeps; conclusions in CHANGELOG (context-24/26/27/28) + L132-135. Task XML -> `archive/sweep-tasks-retired-2026-06-17/`.

**Retired 2026-06-18 (de-sprawl Phase 3 — dead SNIPER research cluster):**
- `Gamma_SniperShadowEOD` — OP-16 SNIPER anchor-build shadow log. The SNIPER strategy never promoted (0 leaderboard citations, real-fills never validated). The `backtest/autoresearch/sniper_*.py` research scripts + `t48_sniper_*.py` -> `backtest/autoresearch/_archive/sniper/`; wrapper `run-sniper-shadow-eod.ps1` -> `setup/scripts/_archive/`. NOTE: `backtest/lib/sniper_detector.py` is KEPT (still consumed by `watcher_live.py` + several lib detectors). Worker `automation/scripts/sniper_shadow_eod.py` left in place (orphaned, harmless — imports only kept modules). If the live task still exists in Task Scheduler, J/installer should unregister `Gamma_SniperShadowEOD`.

**DO NOT RE-ADD — deliberately removed:**
- `Gamma_SessionGuard` + `Gamma_MarketHoursCircuitBreaker` — the OP-32 market-hours firewall that **locked J out of Claude entirely on 2026-05-22**. Self-discipline replaces it (CLAUDE.md top-of-file). Do not re-register without J authorizing a redesigned fail-open version.

**Already-superseded (pre-reset):**
- `Gamma_AR_Watchdog`, `Gamma_GrinderMonitor`, `Gamma_GrinderDiscordNotify` (grinder watchdogs — superseded by in-launcher PID tracking)
- `Gamma_DailyStatus`, `Gamma_MondayReadyCheck` (superseded by EOD/weekly pipelines)
- `Gamma_DiscordResponder` — _superseded note 2026-06-18: NO LONGER "never enabled". Now WIRED (see "## Wired — NOT yet enabled" above): install via `setup/install-discord-responder-task.ps1`._

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
