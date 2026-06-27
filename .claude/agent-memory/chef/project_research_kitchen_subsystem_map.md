---
name: research-kitchen-subsystem-map
description: Full wiring map of the research-kitchen subsystem: kitchen_daemon/seeder/reviewer, mass-grind funnel, strategy/candidates, shadow_model_eval, recency_check/license_monitor — including promotion stall points and TZ bugs found 2026-06-26.
metadata:
  type: project
---

## Subsystem map — research-kitchen (audited 2026-06-26)

### Components
1. `setup/scripts/kitchen_daemon.py` — 24/7 LLM-cook worker. Reads `cook-queue.jsonl`, routes through free-pool (swarm_client) → OpenRouter ladder. Also dispatches `grinder_sweep` tasks (pure-Python param sweeps). Has its own DST-aware `_et_now()` (UTC→ET). Writes to `strategy/candidates/`.
2. `setup/scripts/kitchen_seeder.py` — hourly :20. Reads leaderboard + lessons + decisions.jsonl + inbox depths. Asks Nemotron for 5 tasks. Filters forbidden surfaces. Has own `_et_now()`. Enqueues via `kitchen_daemon.enqueue_task()`.
3. `setup/scripts/kitchen_reviewer.py` — every 2h :45. Reads recent `*chef-nemo*.md` from `strategy/candidates/`. Reviews against leaderboard. Can auto-promote (OP-20+OP-16 check) or write to `_LEADERBOARD-pending.md`. Has own `_et_now()`.
4. `backtest/autoresearch/*_grinder.py` (10 grinders registered in GRINDER_REGISTRY) — pure-Python param sweeps launched by daemon as subprocess. Write `keepers.jsonl` + `progress.json`.
5. `backtest/autoresearch/mass_grind_vwap.py` (+ funnel + consolidate_elites_vwap) — SECOND strategy family. On-demand via `Gamma_Grind_Vwap` scheduled task. Different path from daemon (not in cook-queue).
6. `setup/scripts/shadow_model_eval.py` — daily Nemotron agreement scorer. Reads `decisions.jsonl` (both accounts). Uses `datetime.now(timezone.utc)` correctly (UTC-based). Runs at 16:05 ET via `Gamma_ShadowEval`.
7. `backtest/autoresearch/recency_check.py` — contemporaneous recency gate. No `datetime.now()` calls in the searched lines; clean.
8. `backtest/autoresearch/license_monitor.py` — transition detector (BLOCKED→ELIGIBLE→LICENSED). Uses `dt.datetime.utcnow()` in two places (lines 152, 223) for timestamp metadata only — not for ET-logic — LOW risk.
9. `strategy/candidates/_LEADERBOARD.md` — the promotion destination. ONLY Claude (Chef) writes promotion rows here by spec; reviewer writes to `_LEADERBOARD-pending.md` for failed OP-20/OP-16 candidates.
10. `strategy/candidates/_chef-log.jsonl` — append-only fire log.
11. `strategy/candidates/_review-log.jsonl` — reviewer triage decisions.

### Data / control flow

```
SEEDER (hourly :20 ET)
  → reads: leaderboard, decisions.jsonl, LESSONS, playbook, inbox counts
  → calls Nemotron free tier
  → appends CREATE events → cook-queue.jsonl
              ↓
DAEMON (24/7, polls every 60s)
  → pops pending task from cook-queue.jsonl
  → if task_type=llm_cook:  swarm_client pool → OpenRouter ladder
  → if task_type=grinder_sweep: subprocess grinder → keepers.jsonl
  → on grinder complete: auto-enqueues LLM analysis task (priority=high)
  → writes DRAFT to strategy/candidates/*.md
  → appends complete event → cook-queue.jsonl
  → updates automation/state/kitchen-status.json
              ↓
REVIEWER (every 2h :45 ET)
  → reads last 24h of *chef-nemo*.md files not already in _review-log.jsonl
  → calls Nemotron → PROMOTE/VALIDATE/DUPLICATE/LOW_QUALITY verdict
  → if PROMOTE: _check_op20_disclosures() AND _check_op16_floor()
      → if both PASS: appends row to _LEADERBOARD.md (auto-promote)
      → if either FAILS: appends to _LEADERBOARD-pending.md (stall point A)
  → if VALIDATE: enqueues follow-up cook task
  → writes review digest to analysis/kitchen-review/{datetime}-review.md
  → appends rows to _review-log.jsonl

CLAUDE-WHEN-AWAKE (this session)
  → reads kitchen-status.json + latest review + _chef-log.jsonl
  → steers: enqueues high-value tasks
  → promotes: appends to _LEADERBOARD.md (only Claude does this intentionally)

SHADOW_MODEL_EVAL (16:05 ET weekdays)
  → reads decisions.jsonl + aggressive/decisions.jsonl
  → replays ticks through Nemotron rubric
  → writes scorecard to analysis/shadow-model/YYYY-MM-DD-scorecard.md

LICENSE_MONITOR (nightly, manual/on-demand)
  → reads recency-confirmation.json (output of recency_check.py)
  → diffs vs last snapshot in license-monitor-last.json
  → on RED→ELIGIBLE/LICENSED transition: pings Discord + STATUS.md
  → NEVER flips anything (notify-only)
```

### Where promotions stall

**Stall point A (main one): _LEADERBOARD-pending.md.**
The reviewer auto-promotes ONLY when the cook's `.md` file contains both:
- All 6 OP-20 keywords (account-size, sample-bias, OOS, real-fills, failure-mode, concentration)
- edge_capture >= 771 OR "new trade class" + "guard pass"

Kitchen's free-tier Nemotron outputs rarely include all 6 OP-20 disclosures in a single cook. So nearly every PROMOTE verdict goes to `_LEADERBOARD-pending.md`, not directly to `_LEADERBOARD.md`. Claude's job during a wake session is to read pending + promote the ones that have real backing.

**Stall point B: reviewer only scans `*chef-nemo*.md`.**
The `_collect_recent_outputs()` function in kitchen_reviewer.py line 129 globs for `"*chef-nemo*.md"`. Chef-authored candidate files (e.g. `2026-06-26-160000-structure-veto-direction-vs-trend.md`) do NOT match this glob. They are never auto-reviewed; they go straight to Claude-manual leaderboard action only.

**Stall point C: grinder summaries need LLM interpretation before leaderboard.**
Grinder tasks auto-enqueue an LLM analysis task. The daemon must then complete THAT analysis cook, and the reviewer must then triage the analysis output, before a grinder result ever becomes a leaderboard candidate. Two extra pipeline hops.

### TZ bugs found

1. `setup/scripts/audit_scheduled_tasks.py:207` — `datetime.now().weekday()` is local (Mountain) time. The STALENESS detection "weekend suppression" logic runs in local TZ, not ET. If a task fired at 23:00 ET Friday (01:00 MT Saturday), `weekday()==5` (local Saturday) suppresses the stale alert even though the task may be a genuine miss. LOW severity (weekday-boundary edge only).

2. `setup/scripts/grade_decisions.py:253` — `datetime.now().astimezone().strftime("%Y-%m-%d")` — `.astimezone()` on a naive datetime gives local (Mountain) time, NOT ET. Will produce date "2026-06-26" when ET is still "2026-06-26" but local is already "2026-06-27" after midnight ET (i.e. 22:00-midnight Mountain). MEDIUM severity: could grade yesterday's decisions as today's.

3. `setup/scripts/crypto_grinder_keepalive.py:43`, `discord_watchdog.py:50`, `window_leak_detector_keepalive.py:45`, `run_cmd_hidden.py:54`, `run_ps1_hidden.py:50` — `datetime.now()` used in log timestamps only (no ET labeling, just "current time"). These are log-label TZ bugs only — they will stamp Mountain time in logs labeled as if ET. LOW severity (log cosmetics; no logic gate).

4. `setup/scripts/heartbeat_persist_writer.py:306` — `datetime.utcnow()` is a FALLBACK when `zoneinfo` fails to import. The primary path uses `datetime.now(_ET)` with ZoneInfo("America/New_York"). On Python 3.9+ (which this rig runs), zoneinfo always imports → fallback never reached. NO BUG in practice.

5. **Scheduled task TZ: all three kitchen tasks fire CORRECTLY.** Verified 2026-06-26: KitchenSeeder last=19:20 ET / next=20:20 ET (hourly :20 ET correct). KitchenReviewer last=18:45 ET / next=20:45 ET (every 2h :45 ET correct). KitchenDaemonKeepalive last=20:10 ET / next=20:15 ET (every 5min correct). ShadowEval last=16:05 ET / next=06-29 16:05 ET (weekday-only correct, today was the last weekday before weekend). All fire at correct ET times = NOT the local-as-ET foot-gun.

6. **task_health_et.ps1 exists** at `setup/scripts/task_health_et.ps1` and correctly converts local→ET via `[System.TimeZoneInfo]::ConvertTime(..., 'Eastern Standard Time')`. Use this before declaring any task stuck.

### Key cross-links
- `[[feedback_bash_tz_broken_use_powershell_clock]]` — Bash TZ broken on this rig, use PS for clock verification
- `[[project_scheduled_task_tz]]` — mountain TZ rig; tasks set in ET work because scheduler stores local, and the TZ offset is baked in at install
