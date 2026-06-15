# Continuous Auto-Research Subagent (CARS) — Design

**Status:** DRAFT — design only, no code shipped. Awaiting J ratification on §9 open questions.
**Author:** architect subagent (2026-05-14 evening, after-4pm work block per OP 22).
**Owner once approved:** main session implements; CARS itself is the runtime.

---

## Executive Summary

**Problem.** Per J's exact requirement: the auto-research workflow that picks the lowest-scoring EOD category and investigates it must NOT be coupled to the EOD pipeline. Today, all research-style work either (a) rides on `Gamma_EodSummary`/`Gamma_EodDeepDive` cron, (b) lives in the manually-launched weekend grinders, or (c) runs as the once-per-30-min `gamma-overnight-grinder` wake fires (00:00–07:00 ET only). None of these continuously hunt for weak categories independent of EOD timing.

**Solution.** A dedicated, always-on **Continuous Auto-Research Subagent (CARS)** running as a long-lived Python process orchestrated by Windows Task Scheduler watchdog (not by EOD). Every 15 min during the **after-4pm work block (16:00–23:59 ET)** plus the **overnight wake window (00:00–07:00 ET)**, CARS reads the rolling 30-day category-score history from `analysis/sessions.jsonl`, picks the weakest category, runs a targeted research routine, and queues findings for J.

**Trigger choice.** **Option A: Long-lived Python daemon launched + watchdogged by Windows Task Scheduler.** A single `Gamma_AutoResearchDaemon` task at 16:00 ET launches `cars_daemon.py` (pythonw.exe, no console). Daemon does its own internal 15-min loop with sleep. A separate `Gamma_AutoResearchWatchdog` task runs every 30 min checking the daemon's PID + heartbeat file; restarts if dead. Same pattern as `overnight_grinder.py` but with a market-hour exclusion zone (sleeps 09:30–15:55 ET to avoid contention with `Gamma_Heartbeat`). Justified below in §3.

**Independence from EOD.** CARS reads `analysis/sessions.jsonl` (which EOD writes) but never *blocks* on EOD. If the latest sessions.jsonl entry is older than 24h, CARS computes a fallback rolling-window score from the most recent 30 entries, regardless of date. EOD is a *data source*, not a *trigger*.

**Cost.** ~$0.05/cycle (Sonnet research call ~$0.02 + small tool calls). At 24 cycles/weekday + 4 cycles/weekend day = ~140 cycles/week = **~$15-25/week, ~$60-90/month**. Sits inside the $100/mo Max 5x budget alongside the existing $50/night overnight grinder cap (which only fires when triggered, typically not every night). Hard caps documented in §6.

**Output.** Findings land in `analysis/recommendations/cars-findings.jsonl` (append-only, dedupe by category+fingerprint hash). Doctrine candidates flow to existing `analysis/recommendations/queue.jsonl`. Critical alerts to `analysis/recommendations/alerts.jsonl`. Discord ping only for CRITICAL severity (matches existing `Gamma_DiscordWatchdog` discipline).

**Integration.** Read-side integrates with EOD via `sessions.jsonl`. Write-side integrates with grinder pipeline via `queue.jsonl`. Watch-only per OP 21 — no live trades, no production doctrine writes.

**Scope of this doc.** Design only. No code. No new scheduled tasks. J reviews + approves before implementation begins.

---

## Architecture Diagram

```
                          PROJECT GAMMA — CARS DATA FLOW
                    (independent of EOD timing — runs continuously)

                           DATA SOURCES (READ-ONLY)
+-----------------------------------------------------------------------------+
|  analysis/sessions.jsonl     <-- per-day category scores (written by EOD)   |
|  analysis/eod-deep-*.json    <-- full EOD output (read for narrative)       |
|  analysis/recommendations/   <-- existing queue (read for dedup)            |
|  automation/state/decisions  <-- live decision log (live-aware)             |
|  journal/mistakes.md         <-- recent J flags                             |
|  docs/LESSONS-LEARNED.md     <-- absorbed anti-patterns                     |
|  backtest/_state/<grinder>/  <-- in-flight grinder progress                 |
+-----------------------------------------------------------------------------+
                                     |
                                     v
+-----------------------------------------------------------------------------+
|  CARS_DAEMON.PY (pythonw.exe long-lived process; PID file)                  |
|                                                                             |
|  +---------------------------------+   +---------------------------------+  |
|  |   1. SCORE READER               |   |   5. SAFETY GATES               |  |
|  |   - Load last 30 sessions.jsonl |   |   - Market hours? sleep         |  |
|  |   - Compute rolling-30 score    |   |   - >=4 research workers? skip  |  |
|  |     per category                |   |   - Daily cost cap reached?     |  |
|  |   - Mean / std / trend          |   |     pause                       |  |
|  +---------------------------------+   |   - Production lock files held? |  |
|                  |                     |     skip writes                 |  |
|                  v                     +---------------------------------+  |
|  +---------------------------------+                  ^                     |
|  |   2. TARGET PICKER              |                  |                     |
|  |   - Lowest mean score           |       +-----------------+              |
|  |   - Tie-break: worst trend      |       | 6. PROCESS MGR  |              |
|  |   - Skip if same category       |       | - tracks active |              |
|  |     researched within 24h       |       |   research subs |              |
|  +---------------------------------+       | - enforces cap=4|              |
|                  |                         +-----------------+              |
|                  v                                                          |
|  +---------------------------------+                                        |
|  |   3. RESEARCH DISPATCHER        |                                        |
|  |   - Load category-specific      |                                        |
|  |     research recipe             |                                        |
|  |     (cars/recipes/<cat>.py)     |                                        |
|  |   - Spawn isolated work:        |                                        |
|  |     option A: pure-Python sweep |                                        |
|  |     option B: claude --print    |                                        |
|  |       subagent for narrative    |                                        |
|  +---------------------------------+                                        |
|                  |                                                          |
|                  v                                                          |
|  +---------------------------------+                                        |
|  |   4. FINDING WRITER             |                                        |
|  |   - Append to                   |                                        |
|  |     cars-findings.jsonl         |                                        |
|  |   - Dispatch to existing        |                                        |
|  |     queues (queue / alerts /    |                                        |
|  |     lessons-candidates)         |                                        |
|  |   - Update STATUS-CARS.md       |                                        |
|  +---------------------------------+                                        |
|                  |                                                          |
|                  v                                                          |
|         sleep(900 sec) -> back to step 1                                    |
+-----------------------------------------------------------------------------+
                                     |
                                     v
                             OUTPUT SINKS (WRITE-ONLY)
+-----------------------------------------------------------------------------+
|  analysis/recommendations/cars-findings.jsonl    <-- primary output         |
|  analysis/recommendations/queue.jsonl            <-- shared with EOD/J      |
|  analysis/recommendations/alerts.jsonl           <-- CRITICAL only          |
|  automation/state/cars/STATUS.md                 <-- harness health beacon  |
|  automation/state/cars/heartbeat.json            <-- watchdog probe         |
|  automation/state/cars/research-targets.jsonl    <-- target+verdict log     |
|  automation/state/cars/blocked-on-J.jsonl        <-- items needing J review |
+-----------------------------------------------------------------------------+
                                     |
                                     v
                             WATCHDOG LAYER
+-----------------------------------------------------------------------------+
|  Gamma_AutoResearchWatchdog (30-min Windows scheduled task)                 |
|  - Reads automation/state/cars/heartbeat.json                               |
|  - If stale > 20 min: kill -> relaunch via run-cars-daemon.ps1              |
|  - Logs every action to automation/state/logs/cars-watchdog-YYYY-MM-DD.log  |
+-----------------------------------------------------------------------------+

                           NOT SHOWN, BUT IMPORTANT:
   - CARS does NOT call EOD. EOD does NOT call CARS. They share files only.
   - CARS shares analysis/recommendations/queue.jsonl with EOD's feedback.py
     dispatcher; both use the same fingerprint-hash dedupe so duplicates
     collapse cleanly.
   - During market hours (09:30-15:55 ET) CARS sleeps to avoid resource
     contention with Gamma_Heartbeat / Gamma_WatcherLive.
```

---

## 1. Scope

CARS is a single-purpose subagent with **one job**: continuously identify the weakest-scoring EOD category from rolling history, pick a research recipe targeted at that weakness, run it, and queue findings.

**13 categories CARS monitors** (from `backtest/autoresearch/eod_deep/schema.py` `CATEGORY_KEYS`):
execution, detection, edge, doctrine, risk, process, macro, technical, engine_health, watcher_fleet, lessons, forensics, tomorrow.

**Score interpretation** (from `analysis/sessions.jsonl` history):
- Each category writes 0–100 score per day.
- CARS computes rolling-30-day mean per category.
- Lowest mean = primary research target.
- Tiebreak: most negative 14-day trend (regression risk).
- Skip: same category researched in past 24h (avoid thrashing).

**Per-category research recipes** (lives in `backtest/autoresearch/cars/recipes/<category>.py`):
Each recipe is a small Python module with two functions:
- `gather_evidence(score_history, latest_eod_json) -> dict`: pulls the data needed
- `produce_finding(evidence) -> Finding`: returns structured finding (severity, narrative, action proposal)

**Examples of category-specific recipes** (illustrative, not exhaustive):
- `watcher_fleet.py` → "Which watchers fired 0 times in last 30 days? For each, run `audit-silent-watcher-days.ps1` and capture the silence pattern."
- `detection.py` → "List bars flagged 'missed' in last N EOD outputs. Bucket by setup type. If >5 missed in same setup → propose grinder run with relaxed gate."
- `edge.py` → "Edge_capture_pct < 50% on >3 of last 7 days? Re-run forensics on losing days; check for missed counterfactual."
- `engine_health.py` → "Heartbeat error count in decisions.jsonl trending up? Tail recent stderr logs, propose fix."
- `macro.py` → "VIX regime flip detected? Re-run regime classifier; check if news.json was stale on those days."

Each recipe is **bounded**: must finish in <10 min wall-clock, <$0.20 LLM cost.

---

## 2. Trigger Cadence

**EVALUATED OPTIONS**

| Option | Pros | Cons |
|---|---|---|
| **A. Long-lived Python daemon + watchdog** (RECOMMENDED) | Single process, low scheduler load, full state in-process, easy to add cooldowns/rate-limiting, trivial to pause via touch-file | Needs watchdog (Windows scheduled task) for resilience; daemon-style debugging harder than per-fire |
| **B. Multiple Windows scheduled tasks every 30 min** | Familiar pattern (matches existing Gamma_* tasks), per-fire isolation, easy "skip if X" logic, every fire is independent | Scheduler bloat (more tasks to manage), state must be on disk every time, no in-memory caching, no easy pause |
| **C. Cron via Claude Code's CronCreate** | Stays inside Claude session (matches `gamma-overnight-grinder` pattern) | DIES on Claude exit (per OP 25 absorbed lesson 2026-05-13 — "Claude Code's CronCreate session-scoped"); requires interactive approval at create time per absorbed lesson — UNUSABLE for unsupervised continuous operation |

**DECISION: Option A (long-lived Python daemon with Windows Scheduler watchdog).**

**Rationale.**
1. The existing `overnight_grinder.py` already proves the pattern works (pythonw.exe, PID file, watchdog-friendly progress.json). CARS reuses ~80% of its launch + lifecycle skeleton.
2. CARS needs **stateful cooldowns** ("don't research watcher_fleet twice in 24h") that Option B's stateless per-fire model would force into JSONL reads/writes every cycle — wasteful and racy.
3. CARS needs **rate-limited LLM spend** (track $/day, throttle if >$15) — natural in a daemon, painful to coordinate across N independent scheduled-task fires.
4. Option C is ruled out by OP 25 absorbed lesson — `mcp__scheduled-tasks` requires interactive approval and can't be created by unsupervised wake fires.

**Active windows** (when CARS does work):
- **16:00–23:59 ET weekdays** — primary block (matches OP 22 after-4pm work block)
- **00:00–07:00 ET nightly** — overnight (overlaps gamma-overnight-grinder wake fires; CARS coordinates via shared lock file to avoid double-research same target)
- **All day weekends** (Saturday + Sunday)

**Quiet windows** (CARS sleeps):
- **08:00–09:30 ET weekdays** — premarket (Gamma_Premarket runs)
- **09:30–15:55 ET weekdays** — market hours (Gamma_Heartbeat / Gamma_WatcherLive run; resource contention forbidden per CLAUDE.md rule 9)
- **15:55–16:00 ET weekdays** — EOD flatten / EOD summary windows

**Cycle interval:** 15 min during active windows. ~24 cycles/weekday × 8 hours active + ~4 cycles/hour overnight × 7 hours = ~52 cycles/weekday, ~96 cycles/weekend day. Cap enforced at 100/day.

**Pause mechanism:** touch-file `automation/state/cars/PAUSE` halts all CARS cycles. Same UX as the existing `kill-switch` file.

---

## 3. State

All CARS state lives under `automation/state/cars/` (new directory, parallel to existing `automation/overnight/`).

### 3.1 `automation/state/cars/STATUS.md` (single source of truth)

Mirrors the format of `automation/overnight/STATUS.md` so J reads them with the same eyes.

```markdown
# CARS HARNESS STATUS — single source of truth

## At-a-glance
| Field | Value |
|---|---|
| `daemon_pid` | 21456 |
| `daemon_started_at` | 2026-05-14T16:00:03 |
| `last_cycle_at` | 2026-05-14T20:45:12 |
| `last_cycle_id` | CYCLE-87 |
| `cycles_completed_today` | 18 |
| `cycles_completed_lifetime` | 412 |
| `target_picked_last_cycle` | watcher_fleet (mean=32.1, trend=-1.4) |
| `last_finding_severity` | MED |
| `cumulative_cost_usd_today` | $4.20 |
| `cumulative_cost_usd_lifetime` | $87.40 |
| `daemon_health` | GREEN |
| `next_expected_cycle_at` | 2026-05-14T21:00:12 |
| `pending_findings_for_J` | 3 |

## Current research target
- category: watcher_fleet
- score_30d_mean: 32.1
- score_14d_trend: -1.4
- recipe: watcher_fleet.audit_silent_days
- started_at: 2026-05-14T20:45:00
- expected_completion: 2026-05-14T20:55:00

## Recent findings (last 5)
| Cycle | Category | Severity | Action |
|---|---|---|---|
| 87 | watcher_fleet | MED | queued recipe to grinder |
| 86 | edge | LOW | observation only |
| 85 | detection | HIGH | proposed gate relax |
```

### 3.2 `automation/state/cars/heartbeat.json` (watchdog probe)

Touched on every cycle (success OR failure). Watchdog reads this file's mtime — if older than 20 min during an active window, restart daemon.

```json
{
  "ts": "2026-05-14T20:45:12",
  "cycle_id": 87,
  "pid": 21456,
  "status": "ok",
  "phase": "research_active"
}
```

### 3.3 `automation/state/cars/research-targets.jsonl` (append-only target log)

Every cycle's pick. Used for cooldown lookups + audit.

```json
{"cycle_id": 87, "ts": "2026-05-14T20:45:00", "category": "watcher_fleet", "score_30d_mean": 32.1, "score_14d_trend": -1.4, "recipe": "watcher_fleet.audit_silent_days", "verdict": "completed", "finding_id": "F-2026-05-14-87"}
```

### 3.4 `automation/state/cars/blocked-on-J.jsonl` (J review queue)

Findings that need J's call (production doctrine change, ambiguous). One row per blocked item; J marks them resolved by editing the row's `j_decision` field or by acknowledging in the morning brief.

```json
{"finding_id": "F-2026-05-14-12", "ts": "2026-05-14T17:30:00", "category": "doctrine", "severity": "HIGH", "summary": "Profit-lock trail_pct 0.20 -> 0.10 candidate from analog sweep n=8", "ask": "Ratify the change to params.json?", "scorecard_path": "analysis/recommendations/cars-doctrine-trail-pct.json", "j_decision": null}
```

### 3.5 `analysis/recommendations/cars-findings.jsonl` (primary output, append-only)

Same JSONL pattern as existing `queue.jsonl` / `alerts.jsonl`. Dedupe via fingerprint hash:

```json
{
  "finding_id": "F-2026-05-14-87",
  "ts": "2026-05-14T20:50:00",
  "cycle_id": 87,
  "category": "watcher_fleet",
  "severity": "MED",
  "score_30d_mean": 32.1,
  "score_14d_trend": -1.4,
  "summary": "5 of 8 watchers silent for >7 consecutive days",
  "narrative": "...",
  "evidence": {},
  "proposed_action": {
    "type": "queue_for_grinder",
    "details": {}
  },
  "fingerprint_hash": "9f3a2c1b8e4d6f72"
}
```

### 3.6 Self-healing (mirrors `_shared.ps1#Repair-StateFiles`)

- Last-good copies under `automation/state/cars/.lastgood/` for STATUS.md and heartbeat.json
- Daemon validates JSONL files before append (jsonline-by-jsonline parse), repairs from .lastgood if corrupted
- Append-only files capped at 10K rows; rotate to `.archive/` directory monthly

---

## 4. Output Integration with EOD

### 4.1 Reads from EOD (no dependency on EOD running)

- `analysis/sessions.jsonl` — primary score history. CARS reads tail of file. If empty/stale, falls back to direct globbing `analysis/eod-deep-*.json` and computing scores in-process.
- `analysis/eod-deep-{date}.json` — full EOD output for narrative context (e.g., to read forensics evidence when targeting `forensics` category).

### 4.2 Writes shared with EOD pipeline

CARS writes to the same `analysis/recommendations/` JSONL files that EOD's `feedback.py` writes to. Dedupe is automatic via fingerprint hash (same scheme as `feedback._fingerprint_hash`):

| Sink file | Owner | Contributors |
|---|---|---|
| `cars-findings.jsonl` | **CARS only** | (new file) |
| `queue.jsonl` | EOD primary | + CARS appends |
| `alerts.jsonl` | EOD primary | + CARS appends (CRITICAL only) |
| `lessons-candidates.jsonl` | EOD primary | + CARS appends |
| `future-improvements-candidates.jsonl` | EOD primary | + CARS appends |

### 4.3 What CARS does NOT do

- **Does not invoke EOD.** EOD is a daily cron at 16:05 ET; CARS reads its outputs as a passive consumer.
- **Does not block on EOD running.** If today's `eod-deep-{today}.json` doesn't exist (e.g., 16:00 ET hasn't arrived yet), CARS uses prior days' data.
- **Does not auto-write doctrine.** Per CLAUDE.md rule 9 + OP 24: any change to `automation/state/params.json`, `automation/prompts/heartbeat.md`, or `CLAUDE.md` requires J ratification. CARS writes proposals to `blocked-on-J.jsonl` instead.

### 4.4 Discovery flow

CARS discovers "category X scored 67/100" by:
1. Read last 30 lines of `analysis/sessions.jsonl` (each line has `categories_summary: {execution: 95, ...}`).
2. Group by category, compute mean + 14-day trend.
3. Sort ascending; pick lowest with cooldown filter applied.
4. **Fallback:** if `sessions.jsonl` missing/empty, glob `analysis/eod-deep-*.json` (last 30), parse `categories.{cat}.score` from each, recompute.

---

## 5. Safety Guardrails

### 5.1 Concurrency caps (per OP 15)

- `MAX_PARALLEL_RESEARCH_WORKERS = 4` (CLAUDE.md OP 15) is global. CARS respects this by:
  - Reading PID files of all known grinders (`backtest/autoresearch/_state/*/runner.pid`) at cycle start
  - Counting alive PIDs via WMI (per OP 25 absorbed lesson 2026-05-13 08:43 ET — Get-Process misses pythonw)
  - If >= 3 grinders alive, CARS skips the cycle (writes "deferred:concurrency_cap" finding)
- CARS itself counts as 1 worker; never spawns multiprocessing.Pool of its own without explicit recipe gating.

### 5.2 Watch-only enforcement (per OP 21)

- CARS cannot place Alpaca orders. Module imports are explicitly forbidden:
  - `cars_daemon.py` top-level: `assert "mcp__alpaca" not in sys.modules` defensive check
  - Recipe modules forbidden from importing `lib.simulator_real.execute_*` / Alpaca clients
- New strategy candidates emitted by CARS go through OP-21 promotion path: `watcher` → 3+ historical confirmations + 3+ live confirmations + J ratification. CARS proposes the watcher; J approves the watcher; CARS never auto-trades.

### 5.3 Non-theatre validation (per OP 20)

Every CARS finding with severity >= HIGH must include the 6-disclosure bundle:
1. Account-size assumption
2. Sample-bias disclosure
3. Out-of-sample test result (or explicit "N/A — observation only")
4. Real-fills check on top-3 J days (or explicit "N/A — observation only")
5. Failure-mode enumeration
6. Concentration disclosure

If a recipe can't produce all 6, severity is downgraded to MED automatically.

### 5.4 Production lock files (rule 9 enforcement)

CARS reads `automation/state/PRODUCTION_LOCK` (touch-file, doesn't exist by default). When file exists:
- All writes to `analysis/recommendations/queue.jsonl` are deferred
- All writes to `blocked-on-J.jsonl` are still allowed (J review is non-production-affecting)
- Findings still appended to `cars-findings.jsonl`
- STATUS.md notes lock state

J creates PRODUCTION_LOCK file when shipping a major change to avoid CARS's queue noise during deploy.

### 5.5 Banned operations

- DO NOT modify `CLAUDE.md`, `automation/state/params.json`, `automation/prompts/heartbeat.md`, `automation/prompts/premarket.md`, or any production prompt
- DO NOT kill any PID listed in `backtest/autoresearch/_state/*/runner.pid` or `automation/overnight/STATUS.md` known-PIDs
- DO NOT call MCP tools that have side effects on TV chart, Alpaca account, or Discord (read-only TV calls + read-only Alpaca calls are OK)
- DO NOT delete any file under `automation/state/`, `analysis/`, `journal/`, `docs/`, `backtest/data/`

### 5.6 Failure isolation (per OP 25 silent-failure rule)

- Every recipe exception → caught at dispatcher level, written to STATUS.md `## Known broken (RED flags)` section + `cars-watchdog.log`
- If the SAME recipe fails 3 cycles in a row → CARS quarantines that recipe (skips it for 24h), writes HIGH-severity finding to alerts.jsonl
- Daemon-level uncaught exception → process exits non-zero → watchdog's next 30-min check restarts it; restart event logged

---

## 6. Cost Analysis

### 6.1 Per-cycle cost breakdown

| Phase | Tool | Tokens (est) | Cost (est) |
|---|---|---|---|
| Score read + target pick | pure Python (tail JSONL, compute mean) | 0 | $0.00 |
| Recipe `gather_evidence` | pure Python (file reads, simple analysis) | 0 | $0.00 |
| Recipe `produce_finding` LLM call | claude --print Sonnet, ~2K input + 1K output | 3K | ~$0.020 |
| Finding write + dispatch | pure Python | 0 | $0.00 |
| Status update | pure Python | 0 | $0.00 |
| **Per-cycle total** | | | **~$0.02–$0.05** |

Some recipes need a heavier LLM call (e.g., `lessons` recipe asks Sonnet to compose a lesson candidate from rule_breaks + journal; ~$0.10). Hard cap per cycle: $0.20.

### 6.2 Daily / monthly totals

| Window | Cycles | $/cycle | $/day |
|---|---|---|---|
| Weekday after-4pm (16:00-23:59 ET) | 32 | $0.05 | $1.60 |
| Weekday overnight (00:00-07:00 ET) | 28 | $0.05 | $1.40 |
| Weekend day (24h, ex 09:30-15:55 buffer) | 64 | $0.05 | $3.20 |

**Weekday total:** ~$3.00/day × 5 = $15/week
**Weekend total:** ~$3.20/day × 2 = $6.40/week
**Weekly total:** ~$21.40/week
**Monthly total:** ~$92/month

That fits inside the **$100/mo Max 5x plan** if and only if other research budgets stay nominal. Reality check: the existing `gamma-overnight-grinder` is budget-capped at $50/night (per OP 24) but doesn't fire every night — typical real spend is ~$10-20/wk. Combined CARS + overnight = ~$30/wk = ~$130/mo, which **exceeds** the $100/mo plan.

**Mitigation A (recommended):** Cap CARS at $15/wk via per-day spend limit ($2.15/day weekday, $3.50/day weekend). When daily cap hit, CARS skips LLM-using recipes for the remainder of the day — pure-Python recipes still run.

**Mitigation B:** Use Haiku 4.5 for routine research, Sonnet only for HIGH+ severity (per CLAUDE.md performance.md guidance). Drops cost ~3x to ~$30/mo.

**Mitigation C:** Reduce cycle frequency to 30 min during active windows (halves cost to ~$45/mo).

### 6.3 Hard caps

| Cap | Value | Enforcement |
|---|---|---|
| Cost per cycle | $0.20 | recipe stops calling LLM if spend exceeded |
| Cost per day | $5 | CARS pauses LLM recipes for the day; pure-Python recipes still run |
| Cost per week | $25 | CARS sets `daemon_health: YELLOW`, writes WARNING alert, drops to "essential only" recipes |
| Cycles per day | 100 | CARS adds extra sleep if exceeded |

All caps tracked in STATUS.md `cumulative_cost_usd_today` and `cumulative_cost_usd_lifetime` fields.

---

## 7. Failure Handling

### 7.1 Recipe exception

- Caught at dispatcher
- Written to STATUS.md `## Known broken` section with: timestamp, recipe name, exception type, traceback excerpt, recovery attempted
- Append to `automation/state/logs/cars-recipe-errors.jsonl` (daily rotation)
- 3 consecutive same-recipe failures → recipe quarantined for 24h
- HIGH-severity alert ONLY if 5+ consecutive cycles fail across multiple recipes (suggests daemon-wide issue)

### 7.2 Daemon crash

- Watchdog (Windows scheduled task `Gamma_AutoResearchWatchdog`, every 30 min) reads `heartbeat.json` mtime
- If stale > 20 min during active window:
  1. Try `taskkill /PID {daemon_pid} /F` (defensive cleanup of stuck process)
  2. Launch fresh via `setup\scripts\run-cars-daemon.ps1` (mirrors `launch-overnight-grinder.ps1` pattern — pythonw.exe, PID file, log file)
  3. Append restart event to `automation/state/logs/cars-watchdog-{date}.log`
  4. If 3 restarts within 4 hours → watchdog writes RED alert to alerts.jsonl + Discord ping (matches existing `Gamma_DiscordWatchdog` pattern)

### 7.3 Stale data

- If `analysis/sessions.jsonl` last entry > 48h old (EOD broken)
- If `analysis/eod-deep-*.json` newest is > 48h old
→ CARS writes HIGH alert "EOD pipeline appears broken" to alerts.jsonl, but **continues running** with whatever historical data it has. CARS's job is research; if EOD is broken, that's a separate fire to fix.

### 7.4 J surfacing without spam

Discord ping rules (uses existing `setup\scripts\gamma-notify.ps1`):
- **CRITICAL severity only** → Discord ping (e.g., daemon down 3+ restarts, or finding that says "production doctrine broken")
- **HIGH severity** → write to `blocked-on-J.jsonl`; J reads in next morning brief
- **MED / LOW** → silent appends to `cars-findings.jsonl` only

Morning brief integration: existing `docs/MORNING-BRIEF-{date}.md` should add a section "## CARS findings since last brief" populated from `cars-findings.jsonl` newer than 24h, grouped by severity. (Tracked as a one-line addition to whatever script generates the morning brief.)

---

## 8. Implementation Plan (5 Steps)

| # | Step | Description | Effort estimate | Output |
|---|---|---|---|---|
| **1** | **Skeleton + state files** | Create `backtest/autoresearch/cars/` package: `__init__.py`, `daemon.py` (skeleton with sleep loop + STATUS.md write), `score_reader.py` (parse sessions.jsonl, compute means + trends). Create `automation/state/cars/` directory + `.lastgood/` subdir + initial empty STATUS.md / heartbeat.json. Smoke test: daemon runs 3 cycles, writes status, exits cleanly. | **3 hrs** | Daemon process working, no recipes wired |
| **2** | **First two recipes (cheap pure-Python)** | Implement `recipes/watcher_fleet.py` (read watcher-observations.jsonl, count silent watchers, propose audit) and `recipes/forensics.py` (read latest eod-deep-*.json forensics evidence, propose follow-up). Both pure-Python, no LLM calls. Wire into `daemon.py` dispatcher. Verify findings land in `cars-findings.jsonl`. | **4 hrs** | 2 recipes working; daemon picks lowest of 13 categories and runs the right recipe if one of those 2 |
| **3** | **LLM-using recipe + cost tracking** | Implement `recipes/lessons.py` and `recipes/edge.py` using `claude --print` Sonnet calls (mirror `setup\scripts\run-overnight-grinder.ps1` pattern for LLM invocation). Add cost tracking to STATUS.md (`cumulative_cost_usd_today`). Wire daily/weekly caps with daily reset at 16:00 ET. | **5 hrs** | 4 of 13 recipes working with cost discipline |
| **4** | **Watchdog + scheduled-task installer** | Write `setup\scripts\run-cars-daemon.ps1` (launcher, mirrors `launch-overnight-grinder.ps1`). Write `setup\scripts\run-cars-watchdog.ps1` (every-30-min health check). Write `setup\scripts\install-cars-tasks.ps1` (idempotent installer for `Gamma_AutoResearchDaemon` + `Gamma_AutoResearchWatchdog` tasks; mirrors `install-tasks.ps1` pattern). Smoke test: kill daemon → watchdog restarts within 30 min. | **4 hrs** | CARS resilient to crashes; auto-starts at 16:00 ET daily |
| **5** | **Remaining 9 recipes + integration polish** | Build out remaining recipes (`execution`, `detection`, `doctrine`, `risk`, `process`, `macro`, `technical`, `engine_health`, `tomorrow`). Add `blocked-on-J.jsonl` writer + morning-brief integration. Add Discord CRITICAL alerts. Update `automation/overnight/wake-protocol.md` so wake fires know CARS exists and don't double-research same target (shared lock-file pattern). Final integration test: 24h continuous run with cost tracking + restart resilience. | **8 hrs** | Full system shipped; documented in `docs/CARS-README.md`. Update CHANGELOG.md + LESSONS-LEARNED if new foot-guns surfaced. |

**Total: ~24 hours of focused work** (could be 2-3 after-4pm sessions per OP 22, OR one weekend block). Recommend sequencing into Steps 1+2 first session (~7 hrs), Steps 3+4 second session (~9 hrs), Step 5 third session (~8 hrs).

---

## 9. Open Questions for J

1. **Cost ceiling.** Comfortable with $30-90/mo CARS budget on top of existing overnight grinder? Or should I cap harder (e.g., Mitigation B Haiku-default brings to ~$30/mo)?

2. **Quiet hours during the trading day.** Confirmed CARS sleeps 09:30-15:55 ET to avoid contention with heartbeat. Should it ALSO sleep during 08:00-09:30 ET (premarket) and the EOD window 15:55-16:30 ET, or is the 09:30-15:55 sleep enough?

3. **Discord pings.** Currently spec'd at "CRITICAL only." OK to start with that and tune up if you feel under-informed, or do you want HIGH-severity findings to ping too?

4. **Recipe priority for Step 2.** I picked `watcher_fleet` and `forensics` as cheap pure-Python first recipes. Want a different starting pair?

5. **Production-lock semantics.** Should `automation/state/PRODUCTION_LOCK` block ALL CARS writes, or should `cars-findings.jsonl` writes still proceed (since they're informational, not action-triggering)?

6. **Coordination with overnight wake fires.** Both CARS (long-lived daemon, 15-min cycles, 16:00-23:59 + 00:00-07:00) and gamma-overnight-grinder wake fires (every 30 min, 00:00-07:00 ET) operate during overnight window. Lock-file coordination is straightforward, but do you want CARS to **pause entirely** during the overnight window (00:00-07:00 ET) and only run after-4pm + weekends? Cleaner separation; gives wake fires full ownership of overnight.

7. **Naming.** "CARS" is what I picked for shorthand. Want a different name (Continuous Auto-Research Subagent / CARS feels right, but you might prefer something matching the Gamma-* convention like `Gamma_CategoryGuardian`)?

---

## 10. Implementation Status

- [ ] Step 1: Skeleton + state files
- [ ] Step 2: First two recipes (watcher_fleet, forensics)
- [ ] Step 3: LLM-using recipe + cost tracking
- [ ] Step 4: Watchdog + scheduled-task installer
- [ ] Step 5: Remaining 9 recipes + integration polish

**Awaiting J ratification on §9 open questions before Step 1 begins.**
