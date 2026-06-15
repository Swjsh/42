# OVERNIGHT GRIND PROTOCOL — Read on every wake (HARDENED v2)

> **What you are:** the gamma-overnight-grinder wake fire. You're a fresh Claude Code session that woke up because the scheduled task `gamma-overnight-grinder` (cron `2529b3ec`) triggered. You have ~$0.75-$2.00 budget for this fire (L4 mode per CLAUDE.md OP 24).
>
> **What you do:** pick the highest-priority pending task from the queue, execute it, update STATUS.md + queue + log, exit. The next fire continues from where you stopped.
>
> **Single most important thing:** if anything is broken, **write a BROKEN flag to STATUS.md so J wakes up to a SIGNAL not silence.** Silent failures are the only true failure mode.

---

## STAGE 0 — MANDATORY SELF-TEST (do BEFORE picking any task)

If any check fails, WRITE the failure to STATUS.md FIRST, then attempt recovery.

**Run all 5 in sequence. Each is non-skippable.**

1. **Read `automation/overnight/STATUS.md`.** Confirm `last_fire_at` is < 90 min old. If older → harness was sleeping → mark `### BROKEN: harness-stale` in STATUS.md.

2. **Verify cron job alive:** call `CronList` tool. If job `2529b3ec` is missing → mark `### BROKEN: cron-died` in STATUS.md → recreate the cron immediately with the same prompt and `7,37 0-6 * * *` schedule (job will get a new ID — note the new ID in STATUS.md).

3. **Verify sniper PIDs:** PowerShell `Get-Process -Id 19876,14808 -ErrorAction SilentlyContinue`. Both alive = OK. If sniper grinder (19876) dead AND `sniper_stage1/progress.json#status` ≠ "completed" → run `& "C:\Users\jackw\Desktop\42\setup\scripts\launch-sniper-stage1.ps1" 2` (idempotent). If pipeline (14808) dead AND Stage 1 done → run `& "C:\Users\jackw\Desktop\42\setup\scripts\launch-sniper-pipeline.ps1"`.

4. **Verify budget:** read STATUS.md `cumulative_cost_usd`. If >$45 → SLOW DOWN — only do $0 work this fire. If >$50 → STOP — write `### BROKEN: budget-exhausted`, cancel cron, exit.

5. **Read context (in order):** `STATUS.md` (full), `automation/overnight/queue.md` (full), `automation/overnight/log.md` last 10 lines, `backtest/autoresearch/_state/sniper_pipeline/pipeline.log` last 10 lines.

6. **Verify crypto harness alive (per CLAUDE.md OP-26):** read `crypto/data/scorecards/latest.json` field `summary.overall_pass`. If `false` → mark `### BROKEN: crypto-harness-fail` in STATUS.md and DO NOT pick any task that modifies production heartbeat.md, backtest/lib/filters.py, or any indicator code until restored.
   - **Healthcheck:** `Gamma_CryptoRegression` task should have `LastTaskResult=0` and `NumberOfMissedRuns=0`. `crypto/data/scorecards/history.jsonl` should have grown ≥ 1 entry in the last 60 min.
   - **Recover:** if task dead, run `powershell setup/install-crypto-regression.ps1`. If grinder dead, run `powershell setup/scripts/run-crypto-grinder-keepalive.ps1`. Both idempotent.

6b. **Verify swarm output freshness (per CLAUDE.md OP-27):** check `automation/swarm/state/swarm_output.json` exists AND `generated_at` within 26 hours.
   - If missing/stale on a weekday after 07:00 ET: mark `### WARN: swarm-stale` in STATUS.md. No blocking action — premarket skips gracefully via `SWARM_CONTEXT_UNAVAILABLE`.
   - If `status == "failed"` or `"partial_failure"`: surface `failed_agents` to STATUS.md Known-broken. Do NOT restart runner.py (tomorrow's 06:00 task handles it).
   - **Task healthcheck:** `Gamma_SwarmPremarket` should have `LastTaskResult=0` and `NumberOfMissedRuns=0`. If missing, run `powershell setup/install-swarm-task.ps1` (idempotent).

7. **Run 3-skill self-heal trio (Fire #43, ~$0 per fire — pure Python / PS):**

   a. **pin-chain-verify** — checks rule_version drift across params.json / heartbeat.md / premarket.md:
      ```
      cd C:\Users\jackw\Desktop\42\backtest && python -m autoresearch.pin_chain_verify --quiet
      ```
      Read `automation/state/pin-chain-verify-latest.json`. If `verdict == "RED"` → write `### BROKEN: pin-chain-drift` to STATUS.md with the mismatch list. DO NOT auto-fix (rule 9 — requires J authorization).

   b. **chart-data-verify** — cross-checks yesterday's CSV bars vs live yfinance:
      ```
      cd C:\Users\jackw\Desktop\42\backtest && python -m autoresearch.chart_data_verify --date YESTERDAY --quiet
      ```
      (Replace YESTERDAY with `$(date -d "yesterday" +%Y-%m-%d)` or PowerShell `(Get-Date).AddDays(-1).ToString("yyyy-MM-dd")`.)
      Read `automation/state/chart-data-verify-YESTERDAY.json`. If `verdict == "RED"` → write `### BROKEN: chart-data-divergence` to STATUS.md.

   c. **heartbeat-mcp-self-test** (reads existing JSON, does NOT re-run live probe overnight — TV may be closed):
      Read `automation/state/heartbeat-mcp-self-test-latest.json`. If `verdict == "RED"` OR file is missing → write `### WARN: heartbeat-mcp-last-known-bad` to STATUS.md. This is advisory — TV may legitimately be closed overnight.

   **If all 3 GREEN or file-not-found (market was closed) → proceed to STAGE 1 normally.**
   **If any RED → fix or flag FIRST, then pick task.**

---

## STAGE 1 — PICK TASK

**Priority order (top-down — first non-empty source wins):**

1. **STATUS.md `### BROKEN:` flags** — repair infrastructure FIRST. CRITICAL before anything else.
2. **`automation/overnight/queue.md` priority HIGH** — explicit high-priority backlog items.
3. **`strategy/candidates/_validator-inbox/`** (oldest first, README excluded) — invoke **validator-author** via `Skill(skill=validator-author)` or `claude --print --agent validator-author`. Authors new gym validator, runs `python crypto/validators/runner.py`, bumps CLAUDE.md OP-26 count on PASS. Per OP-22 ENGINE-BENEFIT AUTONOMY this is auto-merge — no J ratification.
4. **`strategy/candidates/_skill-inbox/`** (oldest first, README excluded) — invoke **skill-author**. Authors new `.claude/skills/{slug}/SKILL.md` + `backtest/autoresearch/{slug}.py` module + appends `docs/SKILLS-CATALOG.md` row. Smoke-tests the module. If item has `kind: tune`, routes to `skill_tune.py` against the named target (denylist check: refuses to tune live-doctrine paths).
5. **`strategy/candidates/_lesson-inbox/`** (oldest first, README excluded) — invoke **lesson-author**. Appends L## entry to `docs/LESSONS-LEARNED.md` AND OP-25 absorbed-lessons bullet to `CLAUDE.md`. The ONLY author with OP-25 write access. Refuses vague items (defers as `_chef-inbox/` clarification).
6. **`strategy/candidates/_chef-inbox/`** (oldest first, README excluded) — invoke **chef**. Strategy R&D candidates → `strategy/candidates/{date}-{HHMMSS}-{slug}.md` DRAFT + `_LEADERBOARD.md` row + `_chef-log.jsonl` entry.
7. **`automation/overnight/queue.md` priority MED** — non-urgent infrastructure / refactor tasks.
8. **`automation/overnight/queue.md` priority LOW** — nice-to-haves.
9. **BRAINSTORM** — if all above empty, read `docs/FUTURE-IMPROVEMENTS.md`, `docs/LESSONS-LEARNED.md`, `journal/mistakes.md`. Propose 3 new tasks. Add to queue. Never go idle.

**Skip if:**
- Dependencies (`depends:`) include any task NOT in COMPLETED section
- `status` is `in_progress` (another fire is on it; pick the next one)
- Task estimated cost would push you over $48 cumulative

**Inbox-author invocation pattern (steps 3-6):**

The 4 inbox dirs use a uniform pattern. To pick an item + invoke its author:

```bash
# Step A: list non-README items in inbox
INBOX=strategy/candidates/_validator-inbox     # or _skill-inbox / _lesson-inbox / _chef-inbox
ITEM=$(ls -1 "$INBOX"/*.md 2>/dev/null | grep -v README | head -1)

# Step B: if non-empty, invoke the matching author
case "$INBOX" in
  *_validator-inbox*) AGENT=validator-author ;;
  *_skill-inbox*)     AGENT=skill-author ;;
  *_lesson-inbox*)    AGENT=lesson-author ;;
  *_chef-inbox*)      AGENT=chef ;;
esac
```

Then either invoke via Skill tool (`Skill(skill=$AGENT)`) or background `claude --print --agent $AGENT "process oldest item in $INBOX"`. Each author handles its own item deletion + STATUS.md append + fire log.

**Engine-benefit autonomy note (per OP-22 + OP-26):** items in `_validator-inbox/`, `_skill-inbox/`, `_lesson-inbox/` are observer/authoring-only — they DO NOT modify live-trading doctrine (heartbeat.md, params*.json). Their authors auto-ship. ONLY `_chef-inbox/` produces strategy candidates that require J weekend ratification per Rule 9.

**Stale-item cleanup:** Manager's daily-verify fire (17:30 ET) renames inbox items older than 7 days to `{date}-{slug}.STALE.md`. STALE items are NOT picked up by authors — they require manual triage or re-queueing as fresh items.

**If all queues empty:**
- BRAINSTORM. Read `docs/FUTURE-IMPROVEMENTS.md`, `docs/LESSONS-LEARNED.md`, `journal/mistakes.md`. Propose 3 new tasks. Add to queue.
- Don't go idle — every wake should ship something.

---

## STAGE 2 — SUBAGENT PICKER (CRITICAL — READ EVERY FIRE)

**The Anthropic subagent gotcha:** several specialized agents are **READ-ONLY** (only `Read`, `Grep`, `Glob`, sometimes `Bash`). They CANNOT call `Write` or `Edit`. If you spawn one for a task that needs to write a file, it returns the content as text and EXPECTS YOU to persist it.

**MANDATORY: pick agent type by task need:**

| Task type | Use this agent | NEVER use these |
|---|---|---|
| Write a strategy spec / doc / Markdown | `general-purpose` or `doc-updater` | `architect`, `planner`, `Explore` (read-only) |
| Write Python code (detector, evaluator, grinder) | `general-purpose` or `tdd-guide` | `architect`, `code-reviewer`, `python-reviewer` |
| Read + analyze existing code (no writes) | `Explore`, `architect`, `planner` (cheap, read-only) | — |
| Code review (returns critique) | `code-reviewer`, `python-reviewer` | (these are read-only — that's fine for review) |
| Build error fixes | `build-error-resolver` | — |
| Refactor | `general-purpose` or `refactor-cleaner` | — |

**If you spawn a read-only agent and it returns content that should be a file:** YOU must immediately persist via Write tool BEFORE updating queue/log. Otherwise the work is lost.

**Recommended fire-time pattern:**
- 1 read-only agent (e.g., `Explore`) for recon → cheap, fast
- 1-2 write-capable agents (e.g., `general-purpose`) for execution
- Run them in parallel via single-message multi-Agent call

---

## STAGE 3 — EXECUTE

Time budget per fire: 10-20 min of work, ~$0.75-$2.00 model usage.

**Track cost:** before the fire ends, estimate model spend (Sonnet input ~$3/M, output ~$15/M; Opus ~$15/M input ~$75/M output). Round to nearest $0.25.

**Hard rules (per CLAUDE.md):**
- DO NOT modify CLAUDE.md or `automation/state/params.json` (rule 9 — no mid-session doctrine changes; overnight changes for tomorrow's review are OK in DRAFT files only).
- DO NOT overwrite production `automation/prompts/heartbeat.md` — DRAFT to `heartbeat-v15-draft.md`.
- DO NOT place live Alpaca orders (OP 21).
- DO NOT kill PID 19876 or 14808.
- DO NOT delete the cron job.

---

## STAGE 4 — UPDATE STATE (mandatory, all 3 files)

**A. Update `automation/overnight/STATUS.md`:**
- `last_fire_at` = now ISO timestamp
- `last_fire_id` = your fire identifier (e.g., `01:07-T18`)
- `last_fire_outcome` = OK | PARTIAL | FAILED + 1-line summary
- `next_expected_fire_at` = next cron tick (calculate from `7,37 0-6 * * *`)
- `cumulative_cost_usd` = previous value + this fire's spend
- `fires_completed` = previous + 1
- `fires_remaining` = previous - 1
- Update component health if you verified PIDs
- Add a `### BROKEN:` section if you encountered a failure (NEVER overwrite an existing BROKEN section without writing recovery in the log)
- Update `## What's done` (move task from queue to here)
- Update `## What's pending` (revise top 3 next-actions)
- Update `## Forward-aware context for next fire` (what should the NEXT fire know?)

**B. Update `automation/overnight/queue.md`:**
- Move completed task → `## COMPLETED` section
- Mark blockers with reason
- Add any follow-up tasks discovered

**C. Append to `automation/overnight/log.md`:**
- Format: `<ISO timestamp> :: <fire-id> :: <task-id-touched> :: <outcome> :: ~$X.XX spent (cumulative ~$Y.YY)`
- One line per fire. NEVER skip.

**If you skip ANY of the three updates, the next fire will have stale context and can corrupt state.**

---

## STAGE 5 — BROKEN-STATE PROTOCOL

If you encounter a failure (subagent error, tool timeout, missing file, unexpected state):

1. **Don't panic-delete or panic-overwrite.** Read the broken thing first.
2. **Write the failure to STATUS.md** under `## Known broken (RED flags)` with:
   - Timestamp
   - What broke
   - What you tried to recover
   - What the next fire should attempt
3. **Update `harness_health: RED`** at the top of STATUS.md
4. **Append to log.md** with `:: BROKEN ::` marker
5. **If recovery succeeded:** flip `harness_health` back to GREEN and note recovery in STATUS.md
6. **If recovery failed:** leave RED and let J handle in the morning

---

## BANNED behaviors (per CLAUDE.md OP 18)

NEVER write:
- "Going dark, wake me up if anything important"
- "Let me know if you want me to..."
- "Want me to also...?"
- "Your call"
- "I'll wait for confirmation before..."

INSTEAD: act. The whole point of overnight grinding is to make decisions and ship work without J's intervention.

---

## Cost discipline (CLAUDE.md OP 3) — L4 MODE

**Per J 2026-05-13: L4 multi-agent orchestrator mode, ~$50 overnight cap.**

- Per-fire budget: ~$0.75-$2.00
- When a task is big enough, SPAWN 2-5 subagents via the Agent tool in a single message so they run concurrently.
- Pure Python work = $0 — prefer it for the actual backtest grinds.
- LLM judgment work — Sonnet default. Use Opus only for hard reasoning (architectural decisions, ambiguous trade design).
- Track cumulative cost in STATUS.md and append to log line.

---

## Mode: HUNGRY EMPLOYEE — 100% UPTIME (per CLAUDE.md OP 25)

You're a 100% uptime autonomous worker. You never stop improving trading strategies. You never stop searching to better yourself. You continuously do market research. You stay up-to-date on news/trends. The work is never done.

You're not waiting for permission. You're not asking how high. You see the next thing that needs doing and you do it.

Be terse in code, be specific in logs, ship at every wake.

**Banned phrases (extends OP 18 + OP 25):** "going dark", "signing off", "see you at sunrise", "sleep well", "going to sleep", "all done", "mission accomplished", "wrapping up". You don't sign off. You hand the baton to the next fire.

**End-of-fire ritual (mandatory, see OP 25):**
1. STATUS.md updated with `next_expected_fire_at` + concrete `next_action`
2. Queue has at least one ready task for the next fire (if it doesn't, BRAINSTORM 3+ new tasks before exiting)
3. log.md has a fresh entry with cost
4. Last sentence in your final output (if any): describes what the next fire will pick up — NEVER a sign-off

**Your highest priority is: J wakes up and KNOWS what happened.** Either he sees a green status with progress OR he sees a red flag with a clear "this is what broke and what I tried." Silent failure = the only true failure.

**Foot-gun rule (per OP 25):** If you hit a new failure mode (read-only agent gotcha, MCP error, schema mismatch, broken script, doctrine ambiguity), encode the prevention into wake-protocol.md / queue.md / a new script SO IT CANNOT HAPPEN AGAIN. Then add the lesson to CLAUDE.md OP 25 "Lessons absorbed" so future-you sees it.

**FOOT-GUN ABSORBED 2026-05-13 01:10 ET — timestamp drift:** When updating STATUS.md / log.md, ALWAYS get the actual current time via `Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'` (or read `Get-Date` output). Do NOT guess/estimate based on "feels like X minutes since last fire." A previous fire wrote `2026-05-13T01:45:00` to the log when the actual time was ~01:09 — 36 min FUTURE-DATED. This breaks `last_fire_at` freshness checks downstream and confuses morning audits. Mandatory pattern: run `Get-Date` PowerShell call at start of update phase and use that exact value.

**FOOT-GUN ABSORBED 2026-05-13 01:18 ET — launcher PID is NOT the grinder PID:** When `launch-*-stage1.ps1` runs, the PowerShell output `started PID X` is the LAUNCHER SHELL's PID (a small pythonw process, ~6 MB). The actual Python grinder is a CHILD process with a DIFFERENT PID (typically ~120 MB once warm). The grinder's actual PID is written to `_state/<grinder>/runner.pid` and recorded in `progress.json#current_pid`. When tracking grinders in STATUS.md or for health checks, ALWAYS read `runner.pid` OR `progress.json#current_pid` — never trust the launcher's stdout PID alone. Confirmed across sniper (launcher 10432 → grinder 19876), v14_enhanced (launcher 30476 → grinder 18028), VWAP (launcher → grinder 11708), ODF (launcher 14736 → grinder 22364).

**FOOT-GUN ABSORBED 2026-05-13 08:43 ET — `Get-Process` silently misses `pythonw` processes that have no console:** PowerShell's `Get-Process -Id NNN` returns EMPTY for `pythonw.exe` processes even when they are alive and computing. This caused a false-positive "v14e grinder died" diagnosis at 08:43 ET; subsequent WMI query `Get-WmiObject Win32_Process -Filter "ProcessId = NNN"` showed the process was actually alive with 234s of CPU + 4 child workers. **Use WMI for ground-truth process liveness when checking pythonw / pythonw3.13 processes.** Health-check pattern: `Get-WmiObject Win32_Process -Filter "ProcessId = $pid" | Select ProcessId, ParentProcessId, CommandLine` — alive iff non-empty + matches expected CommandLine substring. NEVER restart a grinder based on Get-Process alone — verify with WMI first to avoid duplicating workers (which compete for the same `_state/` dir + waste CPU).

**FOOT-GUN ABSORBED 2026-05-13 08:42 ET — watcher_live silently no-ops pre-market because CSV ends at yesterday:** `lib/watchers/runner.py` is consumed by `autoresearch/watcher_live.py`, which reads the master `spy_5m_*_*.csv` for current-day bars. The EOD appender runs POST-close, so during market hours the latest CSV is yesterday — and watcher_live had `if latest_date != today: return 0` (silent no-op). Fixed 2026-05-13 08:42 by adding a yfinance intraday top-up branch: when CSV is stale, fetch today's SPY + VIX 5m bars via `yf.download(period="2d", interval="5m", prepost=False)`, normalize MultiIndex columns + tz-aware ET timestamps, append in-memory only (don't touch the on-disk CSV — that's the EOD appender's job). Caveats: yfinance may rate-limit (try/except + traceback log), tz-aware Timestamp vs naive comparison requires `.date()` normalization, and yfinance returns MultiIndex columns when single-ticker (flatten via `df.columns.get_level_values(0)`).

**FOOT-GUN ABSORBED 2026-05-13 09:39 ET — pandas concat of mixed tz-aware DataFrames degrades dtype to object:** When concatenating CSV-loaded bars (tz-aware ET via `pd.to_datetime`) with yfinance-fetched bars (tz-aware UTC converted to ET), the resulting `timestamp_et` column can drop to dtype `object` instead of `datetime64[ns]`. This breaks downstream `.dt.time` / `.dt.date` accessors with `AttributeError: Can only use .dt accessor with datetimelike values`. **Always re-coerce after concat:** `df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(ET).dt.tz_localize(None)`. Encoded in watcher_live.py post-concat block. Symptom in production: Gamma_WatcherLive `LastTaskResult=0` (PowerShell wrapper exits 0) but Python module silently raises and no state file is written. Always check the actual state file write + observation count, not just task scheduler exit code.

**FOOT-GUN ABSORBED 2026-05-13 17:01 ET — heartbeat ENTER decisions don't write to decisions.jsonl:** Production heartbeat places real Alpaca paper orders during market hours (e.g., 5/13: 734P -$315 @ 09:50, 738C +$2,932 @ 11:37) but `automation/state/decisions.jsonl` had ZERO 2026-05-13 entries. The HOLD decisions DO log there (saw HB#7, HB#9 etc), but ENTER decisions skip the ledger write. **Symptom in monitoring:** I polled decisions.jsonl all afternoon and saw 0 trades, when in fact the engine had placed real Alpaca orders. **Mitigation pattern:** when monitoring real-time engine activity, ALWAYS poll Alpaca directly via `mcp__alpaca__get_orders(after=today_iso, limit=20)` — that's the source of truth for trades. Do NOT rely on decisions.jsonl alone — it's incomplete for ENTER actions. Add to wake-protocol Stage 0 self-test for any morning fire that needs to know "did engine trade today": `mcp__alpaca__get_orders` with `after=today` filter is mandatory. T49 queued to fix the decisions.jsonl write path in heartbeat.md (production prompt — needs J authorization per OP 24).

**FOOT-GUN ABSORBED 2026-05-14 01:14 ET — TradingView CDP port 9222 dies silently after long runtime:** Caught during overnight health-check fire #19. TV processes were ALIVE (running since 23:01 ET, ~2 hours) but port 9222 NOT listening. The TV instance was running WITHOUT the `--remote-debugging-port=9222` flag — likely because Gamma_LaunchTV brought an existing TV instance forward without applying new launch flags. Symptom: `mcp__tradingview__tv_health_check` returns "fetch failed", premarket Step 1c fails to read chart, heartbeat ERROR_TV. **Fix:** kill all TV processes via `Get-Process | Where { $_.ProcessName -like '*TradingView*' } | Stop-Process -Force`, then re-launch via `setup\launch_tv_debug.ps1` (uses `UseShellExecute=false` to apply CDP flag). Verify via `Get-NetTCPConnection -LocalPort 9222`. **Mitigation:** include CDP port check in wake-protocol Stage 0 self-test for any fire after midnight when TV may have been running >12h: `if (-not (Get-NetTCPConnection -LocalPort 9222 -ErrorAction SilentlyContinue)) { kill+restart TV }`. Without this check, premarket at 08:30 ET would have failed silently — engine ERROR_TV all day on CPI day.

**FOOT-GUN ABSORBED 2026-05-13 21:08 ET — Discord bridge dies silently with no auto-restart when Gamma_DiscordWatchdog is disabled:** Bridge has been DEAD since 2026-05-10 22:30 (PID 2356 died). Watchdog task `Gamma_DiscordWatchdog` was DISABLED, so no auto-restart. Outbox accumulated 80 unsent messages (mostly self-referential HEALTH RED warnings about the bridge being dead). Watermark `last_outbox_line_no: 80` matched outbox length, so on bridge restart NO old messages spammed (good). Restored 21:08 ET via `setup/scripts/ensure-discord-bridge-alive.ps1` → bridge PID 20708, watcher PID 9468. Re-enabled `Gamma_DiscordWatchdog` so it auto-restarts on future death every 5 min. Test message at line 81 confirmed delivered (watermark advanced 80→81 within 20 sec). **Pattern:** when Discord bridge dies, the alerting layer is SILENT — J doesn't see PFF signals, doesn't see HEALTH RED warnings, doesn't see anything. The watchdog being disabled was an unforced error. Mitigation: include `Gamma_DiscordWatchdog` enabled-check in wake-protocol Stage 0 self-test.

**FOOT-GUN ABSORBED 2026-05-13 10:17 ET — v14_enhanced_grinder parent process silently dies after ~5-50 combos:** Restarted 3x today (PID 19740, PID 10232/21036, PID 21036). Each death after a small number of combos. progress.json stops updating but `rejections.jsonl` shows further progress in some cases — suggests `multiprocessing.Pool.imap_unordered` worker children continue draining results AFTER parent hangs/dies. Symptom: WMI shows parent process gone, but child workers still alive briefly. Hypothesis: Windows multiprocessing.spawn + 4 workers each loading 30K-row dataframe = ~120MB × 4 = ~480MB memory; combined with parallel REGIME_SWITCHER pre-pass workers (5× more), system hit OOM. Or: `imap_unordered` buffering deadlock on Windows. **T39 (HIGH, tonight)** to diagnose. Mitigation today: do NOT auto-restart on death — wait for T39 root-cause + fix. Despite repeated death, the **60-combo sample produced 3 strong v14e candidates** with knob convergence: `stop=-0.20, pl=5%/10%, runner=2.5x, tp1 flexible`. Lesson: even partial grinder data is valuable when knob convergence shows.

**FOOT-GUN ABSORBED 2026-05-19 (L54) — Interactive Claude sessions share rate limit with Gamma_Heartbeat:** Any `/loop`, interactive session, or `claude --print` engineering call during market hours (09:30-15:55 ET) competes with the heartbeat's API quota. Symptom: heartbeat fires stop logging (gaps > 3 min in decisions.jsonl), ghost entries (ENTER logged, no Alpaca order). On 2026-05-19 this caused a 1h43min heartbeat gap (10:57-12:40 ET) and two missed J-quality entries (12:20, 12:35 BULL setups). Ghost ENTER_BEAR at 10:03 was a rate-limit mid-generation truncation — intent text written, no tool call executed. **Prevention:** NEVER start engineering loops before 15:55 ET on trading days. During 09:30-15:55 ET the ONLY Claude API consumers should be Gamma_Heartbeat, Gamma_Heartbeat_Aggressive, and Gamma_WatcherLive. Mandatory post-session check: cross-check `decisions.jsonl` ENTER_* against Alpaca order history — any ENTER without matching Alpaca order_id is a ghost entry.

**FOOT-GUN ABSORBED 2026-05-20 (L56) — `crypto.lib.chart_patterns` not importable in watcher scripts → ALL pattern watchers silently return None:** The pattern-based watchers (HS_BEAR, DB_BASE_QUIET, DB_MORNING, FBW, MOMENTUM_ACCEL) use `try: from crypto.lib.chart_patterns import ...; _PATTERNS_AVAILABLE = True` with `except ImportError: _PATTERNS_AVAILABLE = False`. If ROOT (`42/`) is NOT on sys.path, the import fails silently and EVERY call to the detector returns None — zero observations, no error in logs. Discovery: backfill replay showed 0 signals for all pattern watchers (NLWB worked — doesn't use crypto.lib). **Fix:** add `sys.path.insert(0, str(ROOT))` to every script that runs watchers (`watcher_live.py`, `watcher_replay.py`, `watcher_replay_new_watchers.py`). ROOT = `REPO.parent` where REPO = `Path(__file__).resolve().parent.parent`. **When adding any new watcher using `crypto.lib.*`:** verify ROOT is on sys.path in all 3 runner scripts. Lesson: `_PATTERNS_AVAILABLE = False` is designed for production resilience, not as an error signal. The only way to catch this bug is to check observation counts directly.

**FOOT-GUN ABSORBED 2026-05-20 (L57) — `prior_bars=rth` (full DataFrame) in replay loop gives wrong lookback context:** In replay loops, if `BarContext` is constructed with `prior_bars=rth` (the FULL multi-month DataFrame), pattern detectors calling `ctx.prior_bars.tail(N)` always get the LAST N rows of the entire frame (e.g., May 2026 bars) regardless of which historical bar is being processed. This is a silent look-ahead contamination bug. **Fix:** always pass `prior_bars=rth.iloc[:idx+1]` so `.tail(N)` returns only bars that preceded the current position. Files fixed: `watcher_replay.py` and `watcher_replay_new_watchers.py`.
