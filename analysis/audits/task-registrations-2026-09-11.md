# Task registrations -- dry-run map, 2026-09-11 (GOAL-SUBTRACTION-2026-09-11 item (a))

> Read-only map taken **before** any delete (DONE-WHEN (a): dry-run committed first). Source: `Get-ScheduledTask`/`Get-ScheduledTaskInfo` at ~22:50 ET Fri 2026-09-11 (quiet-mode blackout active), `automation/state/quiet-mode-restore.json`, `quiet-mode-never-restore.json`, `manual-hold-2026-09-05.json`, `quiet_mode.py#ESSENTIAL`, every `setup/**/*.ps1` that calls `Register-ScheduledTask`, and every non-install script that `Start-`/`Enable-ScheduledTask`s a task by name (+ `preopen_readiness.py`'s roster). Script: session scratchpad `task_map.py` (deterministic, no LLM).

## 0. Correction to FABLE-FULL-AUDIT-2026-09-11 S3

The audit's metric line read "195 registered, 23 enabled (172 parked)". **"Parked" was wrong.** Quiet mode (`quiet_mode.py`, J directive 2026-08-24) is a nightly blackout -- weekday 18:00-23:00 ET + weekends -- that disables every non-ESSENTIAL task and restores it outside the window. Of the 195 registrations at 22:50 ET: **23 Ready** (the ESSENTIAL set), **135 Disabled but ran this week** (the blackout -- e.g. `Gamma_AnalystEodReview` ran today 14:45, next run Monday), **37 actually parked** (Disabled, last run before 2026-09-08). The subtraction target is the 37, not 172.

## 1. Rule applied (from the goal's DONE-WHEN (a))

Unregister only if ALL hold: (i) Disabled and last run >= 7 days ago; (ii) not on `restore_to_ready` / `never_restore`; (iii) an `install-*.ps1` re-registers it (restorable in one command); plus two blast-radius guards added by this map: not in `quiet_mode.py#ESSENTIAL`, and not named by any script that starts/enables it or by `preopen_readiness.py`. The 23 enabled tasks are never touched.

## 2. Result: 6 unregister, 1 hold, 30 stay

### 2a. UNREGISTER (6) -- restore command = the install script in the last column

| Task | Last run | Age (d) | Trigger | Why it is dead | Restore |
|---|---|---:|---|---|---|
| `Gamma_FuturesEod` | 1999-11-30 | 9782 | WeeklyTrigger | superseded duplicate -- Gamma_FuturesEod2 ran 2026-09-11 14:42 res 0 and is what futures_health.py checks; this one never ran (0x41303) | `setup/scripts/install-futures-eod.ps1` |
| `Gamma_Grind_Vwap` | 1999-11-30 | 9782 | none | never ran, no trigger; registry: DISABLED 2026-07-01 consolidate-hard | `setup/install-grind-vwap.ps1` |
| `Gamma_Drive` | 2026-06-30 | 73 | DailyTrigger | LLM gamma-drive fire, last 2026-06-30; replaced by goal_autopilot | `setup/install-gamma-drive-task.ps1` |
| `Gamma_ConductorRTH` | 2026-07-23 | 50 | WeeklyTrigger | registry: DISABLED in the 2026-07-25 cost pass (24.5 fires/weekday); last 2026-07-23 | `setup/install-conductor-rth-task.ps1` |
| `Gamma_MultiCore` | 2026-08-20 | 22 | WeeklyTrigger | registry: DISABLED 2026-08-20, lane STOPPED on its frozen null gate; tickers lane superseded it | `setup/scripts/install-multi-core.ps1` |
| `Gamma_TwinChaos` | 2026-08-30 | 12 | WeeklyTrigger | weekly drill for the crypto twin; last 2026-08-30, disabled by the 09-05 hold; twin runs as a resident loop, drill ledger unread since | `setup/scripts/install-twin-chaos-drill.ps1` |

### 2b. HOLD (1)

- `Gamma_DailyReview` -- last run 2026-07-02 (71 d), trigger WeeklyTrigger. **Held:** run-daily-review.ps1 IS the key-levels archiver (lines 15-26); the archive stopped 2026-07-02, the day this task last ran. Decide under GOAL-SUBTRACTION item (e): move the archive step into an existing daily fire, then unregister.

### 2c. Parked but NOT eligible (30) -- each with the blocker that keeps it

| Task | Last run | Age (d) | On 09-05 hold | Blockers |
|---|---|---:|---|---|
| `Gamma_FuturesHeartbeat` | 2026-06-17 | 86 | no | NO-INSTALL-SCRIPT |
| `Gamma_Grind_all` | 2026-06-25 | 78 | no | consumer:setup/scripts/grind-shard-watchdog.ps1 |
| `Gamma_Heartbeat` | 2026-06-25 | 78 | no | ESSENTIAL; consumer:setup/scripts/heartbeat-pulse-check.ps1,setup/scripts/preopen_readines |
| `Gamma_Heartbeat_Aggressive` | 2026-06-25 | 78 | no | ESSENTIAL; consumer:setup/scripts/preopen_readiness.py; NO-INSTALL-SCRIPT |
| `Gamma_Funnel_0` | 2026-06-26 | 77 | no | NO-INSTALL-SCRIPT |
| `Gamma_Funnel_1` | 2026-06-26 | 77 | no | NO-INSTALL-SCRIPT |
| `Gamma_Funnel_2` | 2026-06-26 | 77 | no | NO-INSTALL-SCRIPT |
| `Gamma_Funnel_3` | 2026-06-26 | 77 | no | NO-INSTALL-SCRIPT |
| `Gamma_Funnel_4` | 2026-06-26 | 77 | no | NO-INSTALL-SCRIPT |
| `Gamma_Funnel_5` | 2026-06-26 | 77 | no | NO-INSTALL-SCRIPT |
| `Gamma_Grind_Watchdog` | 2026-06-26 | 77 | no | NO-INSTALL-SCRIPT |
| `Gamma_ManagerOverseer` | 2026-07-02 | 71 | no | NO-INSTALL-SCRIPT |
| `Gamma_EveningNarrative` | 2026-07-23 | 50 | no | NO-INSTALL-SCRIPT |
| `Gamma_CompanionKeepalive` | 2026-09-05 | 6 | yes | on-never_restore; ESSENTIAL; age<7d(6) |
| `Gamma_CryptoGrinderKeepalive` | 2026-09-05 | 6 | no | age<7d(6) |
| `Gamma_CryptoTwin` | 2026-09-05 | 6 | yes | on-never_restore; age<7d(6) |
| `Gamma_CryptoTwinKeepalive` | 2026-09-05 | 6 | no | on-never_restore; age<7d(6) |
| `Gamma_DiscordBridge` | 2026-09-05 | 6 | yes | on-never_restore; age<7d(6) |
| `Gamma_EngineStressSwarm` | 2026-09-05 | 6 | no | age<7d(6) |
| `Gamma_KitchenDaemonKeepalive` | 2026-09-05 | 6 | yes | on-never_restore; age<7d(6) |
| `Gamma_ProcTraceKeepalive` | 2026-09-05 | 6 | no | on-never_restore; age<7d(6) |
| `Gamma_QuoteRecorderKeepalive` | 2026-09-05 | 6 | yes | on-never_restore; age<7d(6) |
| `Gamma_WindowLeakDetectorKeepalive` | 2026-09-05 | 6 | no | on-never_restore; ESSENTIAL; age<7d(6) |
| `Gamma_WindowLeakHookKeepalive` | 2026-09-05 | 6 | no | on-never_restore; age<7d(6) |
| `Gamma_FeeRecalibrate` | 2026-09-06 | 5 | yes | on-restore_to_ready; age<7d(5) |
| `Gamma_GateRecency` | 2026-09-06 | 5 | yes | on-restore_to_ready; age<7d(5) |
| `Gamma_RiskyDivergenceWeekly` | 2026-09-06 | 5 | yes | on-restore_to_ready; age<7d(5) |
| `Gamma_TreasurerWeekly` | 2026-09-06 | 5 | yes | on-restore_to_ready; age<7d(5) |
| `Gamma_WeeklyReview` | 2026-09-06 | 5 | yes | on-restore_to_ready; age<7d(5) |
| `Gamma_MondayVerify` | 2026-09-07 | 4 | yes | on-restore_to_ready; age<7d(4) |

## 3. What this map does NOT do

- It does not touch the 135 blackout-cycled tasks or the 23 ESSENTIAL ones. Whether the rig needs 158 daily tasks is a different question (the audit's answer is no); that is a per-task retirement decision on evidence, not a registration sweep.
- `NO-INSTALL-SCRIPT` tasks (Funnel_0-5, Grind_Watchdog, ManagerOverseer, EveningNarrative, FuturesHeartbeat, Heartbeat_Aggressive) stay registered-but-disabled because deleting them is not reversible in one command. Registry already documents the grind family as dead (2026-07-01).
- Tasks disabled by J's 2026-09-05 hold and now on `never_restore` (CryptoTwin*, DiscordBridge, KitchenDaemonKeepalive, ProcTrace/QuoteRecorder/WindowLeak* keepalives) stay: J turned them off by hand; `never_restore` is the standing record of that.

## 4. Verification after the delete (filled in by the executing session)

- count before: 195 -> after: (see PROGRESS LOG / STATUS line)
- `backtest/tests/test_scheduled_tasks_doc.py`: (result quoted in STATUS)
- `SCHEDULED-TASKS.md`: new section `## Unregistered 2026-09-11 (subtraction pass)` lists the six with restore commands.

