# DOCTRINE-ARCHIVE.md

> Operating principles removed from CLAUDE.md on 2026-05-23 during the infrastructure reset.
> Verbatim text — no edits. History preserved. Reason: these OPs describe systems/processes
> that were nuked in the reset (OP-24 overnight grinder, OP-26 crypto harness, OP-27 scheduled-task
> discipline, OP-28 swarm + personas, OP-29 skills pipeline, OP-30 effort tiers, OP-32 market firewall),
> or encode behavior already captured in heartbeat.md (OP-12 tiered runner), or were superseded by
> the simpler 9-task surface. The load-bearing 7 OPs remain in CLAUDE.md.
>
> Reference: [docs/RESET-2026-05-23.md](RESET-2026-05-23.md)

---

## OP-1: Fix-on-find

**Fix-on-find.** When a review or audit uncovers a problem, fix it now. Exception: if the fix touches live production logic during market hours (rule 9), defer to 16:01 ET that day.

---

## OP-2: No speculation in doctrine

**No speculation in doctrine.** Cite evidence (specific bars, dates, observed outcomes) or don't write the claim. Mark speculation explicitly: `(speculative — needs evidence)`.

---

## OP-4: No code drift

**No code drift.** When two systems implement the same logic, they must update together. Drift detection during any review = immediate sync.

---

## OP-5: Round numbers awareness-only

**Round numbers are awareness-only.** NOT auto-Carry, NOT score-modifiers, NOT trigger sources. Promote only after 3+ chart-confirmed defenses across sessions.

---

## OP-6: Candlestick names awareness-only

**Candlestick names always in live-chat.** AWARENESS language, NOT entry triggers. DO NOT promote candlesticks to a trigger source without a backtest showing positive expectancy uplift over ≥30 trading days.

---

## OP-7: Daily backtest ritual

**Daily backtest ritual.** EOD-summary auto-refreshes dataset + reruns rolling 60-day backtest. Divergence > 30% on any metric → flag in journal, surface in next premarket. Cost: ~$0.05/day.

---

## OP-8: No deferral, no fallback to manual

**No deferral, no fallback to manual.** When a problem surfaces, fix it. When stuck, ask J — don't write "we'll do this later" or "manual override."

---

## OP-9: Goal is autonomous execution

**Goal is autonomous execution, full stop.** When backtest results are bad: "make the engine smarter." When engine misses J's edge: "encode J's edge into the engine."

---

## OP-10: Build winners, not max-profit gambles

**Build winners, not max-profit gambles.** Tiered exits, ribbon-rides, scaling out — all serve consistency over peak.

---

## OP-12: Tiered runner doctrine

**Tiered runner doctrine — exit logic for ride-the-ribbon trades.**

**Conservative runner (first to lock):** Early exit = reversal candle + volume ≥ 1.5× 20-bar avg + within $0.30 of Active/Carry level. ALL three required. Fallback: ribbon stack inversion.

**Aggressive runner (rides for deep level):** Early exit = reversal candle + volume ≥ 2.0× 20-bar avg + within $0.30 of CARRY level only. Fallbacks: ribbon inversion / premium ≥ 3× entry / 15:50 ET stop.

**Single-runner (qty=3):** use conservative rules. Locking > maxing.

**Ribbon flip definition:** stack must be FULLY OPPOSITE (BULL for puts / BEAR for calls) AND spread ≥ 30¢. Sub-30¢ = chop, no real bias. Intermediate signal: bar closes across Fast EMA but stack holds → tighten conservative runner stop to prior bar's high.

---

## OP-13: Weekend research is autonomous

**Weekend research is autonomous.** `setup\run-weekend-research.ps1` runs autoresearch waves Saturday morning → Sunday 17:30 ET. Cost: pure Python = $0. Progress: `backtest/autoresearch/_state/weekend-progress.json`. Findings → weekly-review Sunday 18:00 ET → J reviews → yes/no on single proposal. No auto-write to heartbeat.md without J's explicit ratification.

---

## OP-14: WR is NOT primary metric

**WR is NOT primary metric.** Sharpe + expectancy + max-drawdown + validate-window P&L drive KEEP decisions. WR is awareness-only. Hard floor: WR ≥ 10%. Use `--objective validate_sharpe` or `validate_pnl` for regime-robust selection.

---

## OP-15: Multi-Agent Gamma 2.0

**Multi-Agent Gamma 2.0.** Uses `multiprocessing.Pool` for research, Claude Agent SDK + parallel `Invoke-Claude` for EOD analysis. Master plan: [`docs/plans/multi-agent-gamma.md`](plans/multi-agent-gamma.md). **Hard caps:** `MAX_PARALLEL_RESEARCH_WORKERS = 4`, `MAX_PARALLEL_EOD_WORKERS = 4`. **Safety:** research MUST use `multiprocessing.Pool` (process-based), never `ThreadPoolExecutor` — `runner._patched_filter_constants` is NOT thread-safe.

---

## OP-17: First-try shipping + 3-of-3 + GRIND-UNTIL-DONE

**First-try shipping + 3-of-3 + GRIND-UNTIL-DONE.**

**GRIND-UNTIL-DONE:** When work is required to meet a stated standard, do NOT ask J's permission to continue. Keep working until: (a) standard met, (b) blocked on J's credential/decision only, or (c) J says STOP. **Banned phrases:** "Want me to keep going?" / "should I keep grinding?" / "let me know if you want me to continue."

**3-of-3 + BEAT-J target (done when ALL conditions met):**
- 4/29 engine_pnl > $342 | 5/01 engine_pnl > $470 | 5/04 engine_pnl > $730 (currently $820 ✓)
- All 4 loser days: engine_pnl ≥ $0

**4 locked exit knobs (apply on EVERY winner):** `tp1_premium_pct=+75%`, `tp1_qty_fraction=50%`, `runner_target_premium_pct=2x`, `premium_stop_pct_bear=-20%`. See `doctrine/seed10095-exit-doctrine.md`.

**Standard for every change:** define unit test first → hand-compute expected → run test in isolation → only wire into engine after pass. Ship-then-revert in same session = process failure, log to LESSONS-LEARNED.

---

## OP-18: Truly autonomous research mode

**Truly autonomous research mode.**

**BANNED phrases (chatbot reflexes):** "Going dark…" / "Let me know if you want me to…" / "Your call." / "Want me to also…?" Publish status proactively — don't wait to be asked.

**Required status update format:** (1) Current state with numbers. (2) J's concerns addressed proactively (regime-robustness, concentration, sub-window stability, max drawdown). (3) What I'm doing next + when I check back + what triggers what.

**Pre-plan full pipelines before running stage 1.** Each stage adds stricter gates than the prior:
- Stage 1: floor protection (4/29 + 5/04 + losers_added=0)
- Stage 2: refine top-5 keepers (tighter neighborhoods)
- Stage 3: regime-robustness (concentration ≤ 200%, ≥4 of 6 quarters net-positive)
- Stage 4: sub-window stability (Q1/Q2/Q3/Q4 2025 all positive)
- Stage 5: final ratification scorecard

**Before reporting any candidate "done," verify:** OP 14 (sharpe/expectancy/max-DD, not WR alone) + OP 16 (edge_capture primary) + OP 11 (per-quarter stability) + concentration disclosure. Any check fails = intermediate, not finished.

---

## OP-19: Self-healing/self-improving research pipeline

**Self-healing/self-improving research pipeline.** Each stage MUST: read prior stage's keepers as seeds; apply STRICTER gates; auto-trigger via `Gamma_GrinderMonitor`; write `progress.json`; preserve doctrine floors (4/29 + 5/04 + losers_added=0) — never auto-lower. Hourly monitor: PID-check all stages, restart dead stages (idempotent via PID file), auto-launch next stage on completion, generate 08:00 ET morning summary. Every `evaluate_combo` MUST store: `top5_pct`, `quarter_pnl`, `positive_quarters`, `max_drawdown`, `wide_n_trades`, `wide_wr`.

---

## OP-20: Non-theatre validation

**Non-theatre validation.** Every result/recommendation/"ready" claim MUST bundle:
1. Account-size assumption (qty=28 requires $25K+; $1K paper = ~14% of headline)
2. Sample-bias disclosure (selection from 1000-combo grinder = overfit risk)
3. Out-of-sample test result (walk-forward: train ≤T-1 years, test held-out window)
4. Real-fills check on top-3 J days (`simulator_real.py` — BS-sim ≠ OPRA fills)
5. Failure-mode enumeration (worst day, max drawdown, blow-up scenario)
6. Concentration disclosure (if top-5 days = X% of P&L, state X)

**BANNED:** "Strategy works" without OOS evidence | "Monday ready" before Monday-Ready Checklist passes | any "ready" claim without the 6 disclosures.

**Default pipeline before ratification:** Stage 1-5 grinder → walk-forward (`walk_forward_validate.py`) → real-fills (`simulator_real.py`) → Monday-Ready Checklist (`docs/MONDAY-READY-CHECKLIST.md`) → J ratification.

---

## OP-21: Watch-First Promotion Path

**Watch-First Promotion Path.** Every new strategy starts WATCH-ONLY, logging to `automation/state/watcher-observations.jsonl`. **Promotion requires all of:** 3+ historical observations that would have won (graded via `watcher_grader.py`) + 3+ live observations confirmed by J + positive expectancy over 16-month full backfill + per-confidence-tier expectancy positive + per-quality scorecard showing complement (not cancel) + J's explicit ratification.

**Economics gate:** per-trade expectancy MUST be positive over full backfill before any live promotion. Cherry-picks are theatre (PIN-FADE: 1 win in 53 fires = -$7,900 net).

**Default watcher knobs:** qty=3, premium_stop_pct=-0.10, tp1_premium_pct=+0.30, runner_target=1.5x.

**Watchers shipped 2026-05-10:** `orb_watcher` (ORB GOAT 30-min break), `bullish_watcher` (BULLISH_RECLAIM_RIDE_THE_RIBBON), `pinfade_watcher` (PIN_FADE on chop days only). All in `lib/watchers/`. Daily replay via `Gamma_WatcherReplay` task at 17:00 ET.

---

## OP-23: SNIPER_LEVEL_BREAK setup (DRAFT)

**SNIPER_LEVEL_BREAK setup (DRAFT 2026-05-12).** Extracted from J's real-money trades on 2026-05-11 (738.10 break + ATH rejection) and 2026-05-12 (736.13 ★★★ break-down). Trigger: named ★★+ level (prior day RTH H/L, 5-day H/L) broken or reclaimed on 5m bar with vol ≥ 1.5× 20-bar avg + body ≥ 10c past the level. Bypasses v14's 10:00 ET gate and ribbon ≥30c spread filter — the level break IS the trigger. Strike: ATM or ITM-2 (knob). Profit-lock: once favor_premium ≥ entry × (1+threshold), stop floor moves to entry × (1+offset) so a winning trade never goes negative.

**Backtest pipeline:** `backtest/autoresearch/sniper_overnight_grinder.py` (Stage 1, 1728 combos) → `sniper_stage2_grinder.py` (refine top-5) → `sniper_stages345.py` (regime-robustness + sub-window stability + ratification). Orchestrator: `sniper_pipeline.py`. Watch-only via OP 21 — no live orders until: (1) Stage 5 scorecard passes 4-of-4 + walk-forward + real-fills, (2) 3+ live wins observed by J, (3) J explicit ratification.

**Status as of 2026-05-12 23:50 ET:** Stage 1 + pipeline orchestrator running. Final scorecard expected at `analysis/recommendations/sniper-v1.json` by ~05:00 ET 5/13.

---

## OP-24: Overnight Grind Mode

**Overnight Grind Mode (autonomous Claude wake-loop, ratified 2026-05-13).** A recurring scheduled task `gamma-overnight-grinder` fires every 30 min from 00:00-07:00 ET, opening a fresh Claude Code session. Each fire reads `automation/overnight/wake-protocol.md` (the operating manual), then `automation/overnight/STATUS.md` (single-source-of-truth health), `automation/overnight/queue.md` (the task queue) and `automation/overnight/log.md` (recent wake history), picks the highest-priority pending task whose dependencies are met, executes it, updates STATUS.md + queue + log, and exits. Budget per fire: ~$0.75-$2.00 (Sonnet, L4 mode). Total overnight cost: ~$50/night.

**What wake fires do:** review pipeline scorecards, write walk-forward + real-fills scripts, design new strategy candidates, audit lessons-learned, refactor code, queue follow-up tasks. **What wake fires DON'T do:** modify production CLAUDE.md (additions to operating principles by user-authorized turns are OK), modify production params.json (rule 9), overwrite production heartbeat.md (DRAFT only to `-v15-draft.md`), place live trades (OP 21), ping J (OP 18), kill the sniper pipeline PIDs.

**The queue is the contract.** Seed tasks live in `automation/overnight/queue.md`. Wake fires consume top of queue + brainstorm new tasks when queue runs low. STATUS.md is the cross-fire health beacon — every fire updates it; if it's stale > 90 min the harness is broken. J reviews STATUS.md + queue + log in the morning to see what got done. Health-check via `pwsh setup\scripts\overnight-health-check.ps1`.

---

## OP-26: Crypto harness

**Crypto harness is the 24/7 vision-validation surface for the SPY engine (ratified 2026-05-16).** Every chart-reading primitive the heartbeat depends on (bar selection, indicator math, candlestick recognition, level events, sweep / failed-breakout detection, ribbon stack, regime classification, multi-timeframe alignment, volume confirmation, trendlines, divergence) lives in `crypto/lib/` and is exercised continuously against live BTC bars.

**Mandatory checks:**
- **Session startup (premarket + wake fires):** read `crypto/data/scorecards/latest.json`. If `summary.overall_pass == false`, surface to `automation/overnight/STATUS.md` known-broken section AND do not modify production heartbeat.md / params.json until green.
- **Pre-merge any heartbeat.md / backtest/lib/filters.py / indicator code edit:** run `python crypto/validators/runner.py --skip-replay` — must show `overall_pass=True`. Total stages: 77 (--skip-replay; benchmark.replay_5_14 requires `backtest/data/spy_5m_2026-05-08_2026-05-14.csv`). [bumped 2026-05-24: +2 for v40_bearish_rejection_morning_gate.offline + .live]. Two live-source parity validators are carved out of `overall_pass` as KNOWN_FLAKY: `v02_source_parity` and `v15_three_source_parity.live`.
- **Pre-merge any new primitive added to crypto/lib/:** write a `crypto/validators/vNN_*.py` with offline + live mode that passes BEFORE the primitive is referenced elsewhere.

**Healthcheck the harness itself:**
- `Gamma_CryptoRegression` task (every 30 min) — verify with `Get-ScheduledTask -TaskName 'Gamma_CryptoRegression' | Get-ScheduledTaskInfo`. `LastTaskResult=0` AND `NumberOfMissedRuns=0` expected.
- `Gamma_CryptoGrinderKeepalive` task (every 5 min) — keeps `live_grinder.py` alive. Verify a python process with `live_grinder` in its command-line is alive via `Get-WmiObject Win32_Process` (per L27).
- `crypto/data/scorecards/history.jsonl` should grow ≥ 2 lines per hour. If stagnant > 90 min, restart `Gamma_CryptoRegression`.
- `crypto/data/scorecards/grinder.jsonl` should grow ≥ 25 lines per hour. If stagnant, keepalive is broken — investigate.

**Foot-gun-to-primitive port path** (the load-bearing payoff): when a heartbeat foot-gun surfaces:
1. Reproduce it in `crypto/validators/vNN_*.py` as a synthetic test case.
2. Fix the primitive in `crypto/lib/`.
3. Re-run runner.py — must show overall_pass=True again.
4. Port the corrected primitive into production per `crypto/docs/HEARTBEAT-INTEGRATION.md`.
5. Append the lesson to `docs/LESSONS-LEARNED.md`.

**The 5/14 floor is the regression gate.** `python crypto/benchmarks/replay_5_14.py` must always report `NEW_logic.error_rate_pct == 0.0` AND `critical_decisions_misread_by_new == 0`. Any change that flips either is REJECTED.

**Banned:** placing live crypto orders from anywhere in `crypto/`. If we ever trade crypto, it goes in a separate folder. Hard rule in `crypto/CLAUDE.md`.

**Cost:** $0/mo recurring (pure Python, no LLM in the validation loop).

---

## OP-27: Scheduled-task discipline

**Scheduled-task discipline — lean, hidden, registered, audited (ratified 2026-05-16).**

**Source of truth:** [`automation/state/SCHEDULED-TASKS.md`](../automation/state/SCHEDULED-TASKS.md). Every active task must have an entry with: cadence, what it produces, what it reads, cost/fire, and a 1-sentence "why it exists".

**Mandatory window-hidden convention.** All scheduled-task actions MUST use the canonical spawn chain:
```
Task Scheduler → wscript.exe //nologo run_exe_hidden.vbs
               → sys-pythonw.exe (C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe)
               → run_ps1_hidden.py (Python launcher)
               → subprocess.Popen("powershell.exe", creationflags=0x08000000)
               → .ps1 script runs
```

**Subprocess-spawn discipline (5-layer rule — L41):**
1. `subprocess.run()`/`Popen()` from Python MUST pass `creationflags=0x08000000` (CREATE_NO_WINDOW).
2. `claude --print` for MCP-free agents MUST include `--strict-mcp-config --mcp-config <empty-mcp.json>`.
3. Long-running scripts launched as `pythonw.exe` MUST redirect stdout/stderr to log files at the TOP.
4. Use SYSTEM `C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe` (true GUI subsystem), NOT the venv stub.
5. Launch via `wscript.exe //nologo setup\scripts\run_exe_hidden.vbs` for guaranteed hidden spawn.

**Registry baseline:** `HKCU\Console\%%Startup\DelegationConsole` AND `DelegationTerminal` = `{B23D10C0-E52E-411E-9D5B-C09FDF709C7D}` (legacy conhost).

**Daily audit:** `python setup/scripts/audit_scheduled_tasks.py` → `automation/state/scheduled-tasks-audit.json`. Flags: ORPHAN_TASK, STALE_REGISTRY_ENTRY, VISIBLE_WINDOW, PYTHON_NOT_PYTHONW, SILENT_TASK, CANDIDATE_FOR_REMOVAL.

**Adding a new task — protocol:**
1. Update registry first (`automation/state/SCHEDULED-TASKS.md`).
2. Register using the canonical spawn chain.
3. Run the audit — must report 0 flags.
4. Note doctrine significance.

**Removing a task — protocol:**
1. Disable for ≥ 7 days first.
2. Confirm no other process expects the file it produces.
3. `Unregister-ScheduledTask -TaskName <name> -Confirm:$false`.
4. Remove registry entry. Audit must re-pass.

---

## OP-28a: Swarm (replay-able, benchmarked, advisory-only)

**Swarm — replay-able, benchmarked, advisory-only (ratified 2026-05-16 evening).** The 6-agent swarm shipped 5/16 morning is offline-replay-able against any historical day in the `spy_5m`/`vix_5m` cache (16 months back). Stages 2-4 (specialists + validator + synthesis) are MCP-free by design — only `data_fetcher.md` touches TV+Alpaca MCP.

**Production rules:**
- Swarm output is **advisory** — premarket Step 1c reads `swarm_output.json` as context, heartbeat does NOT consume it as a trigger or block source.
- Swarm replay files NEVER auto-update production heartbeat.md or params.json. J ratification required per rule 9 + OP 20.
- Swarm formula calibration is engine improvement — backtest, pick winner, ship it. No ratification needed.
- Current formula: v4 (x60 base + v3 structural gates + NO_TRADE gate for conf<40). ECE = 3.00% on 39/55 signal days.

**Cost discipline:** $0.07/day replay × 5 days/week = $0.35/week. 90-day one-shot ≈ $6. Total recurring ≈ $3/mo.

**Encoded in:** `automation/swarm/replay/` + `docs/SWARM-REPLAY-PLAYBOOK.md` + `docs/SWARM-BENCHMARK-WEEK-1.md` + `analysis/swarm-benchmark/aggregate.json`.

---

## OP-28b: Persona-bounded subagents

**Persona-bounded subagents — Coach + Chef as the always-on team (ratified 2026-05-16).**

**The roster (7-persona trading firm):**

| Persona | File | Role | Model |
|---|---|---|---|
| Gamma | `CLAUDE.md` + `.claude/agents/gamma.md` | Conductor / orchestrator | sonnet |
| Scout | `.claude/agents/scout.md` | Pre-market macro/news intelligence | sonnet |
| Coach | `.claude/agents/coach.md` | Gym supervisor | sonnet |
| Pilot | `.claude/agents/pilot.md` | LIVE 0DTE SPY trader | haiku → sonnet |
| Analyst | `.claude/agents/analyst.md` | Post-trade reviewer + pattern miner | sonnet |
| Chef | `.claude/agents/chef.md` | Strategy R&D scientist | sonnet |
| Treasurer | `.claude/agents/treasurer.md` | Risk + money management auditor | sonnet |

**Hard guardrails:**
- Only Pilot can place live orders (everyone else has `mcp__alpaca__place_*` denied)
- No persona except J can modify production `heartbeat.md`, `params*.json`, `CLAUDE.md` (rule 9)
- All Chef proposals are DRAFT in `strategy/candidates/`
- All Treasurer proposals are DRAFT in `analysis/treasury/draft-params-changes.md`

**The daily loop with persona hand-offs:**
```
05:30 Scout → scout_output.json
08:00 LaunchTV → TV CDP up
08:10 Swarm → swarm_output.json
08:30 Premarket → today-bias.json (reads Scout + Swarm)
09:30-15:55 Pilot (via Heartbeat task)
15:55 EodFlatten → position cleared
16:00 EodSummary → journal/{today}.md
16:05 EodDeepDive → eod_deep/output/{today}/
16:30 DailyReview → tomorrow's key-levels.json
16:45 Analyst → analysis/eod/{today}.md
17:30 Gamma Manager → analysis/daily-brief/{today}.md
[overnight] Chef wake fires → strategy/candidates/
[Sun 16:00] Treasurer → analysis/treasury/{date}.md
[Sun 18:00] WeeklyReview → analysis/{YYYY-Www}.md
```

---

## OP-29: Skills pipeline

**Skills pipeline — Findings → Validators / Skills / Lessons (ratified 2026-05-18).**

**The 4 inboxes (under `strategy/candidates/`):**

| Inbox | Author | Output | Doctrine touched |
|---|---|---|---|
| `_chef-inbox/` | `chef` | strategy DRAFT | NONE — Rule 9 |
| `_validator-inbox/` | `validator-author` | `crypto/validators/v{NN}_{slug}.py` | OP-26 stage count only |
| `_skill-inbox/` | `skill-author` | `.claude/skills/{slug}/SKILL.md` | NONE |
| `_lesson-inbox/` | `lesson-author` | `docs/LESSONS-LEARNED.md` L## entry | OP-25 absorbed-lessons only |

**Engine-benefit autonomy:** validator-author, skill-author, lesson-author all auto-merge without weekend ratification. Only `_chef-inbox/` items require J ratification per Rule 9.

**The daily gym session (`Gamma_GymSession`, 17:00 ET weekdays):** unified "physical exam." Reads 7 audit scorecards, classifies GREEN/YELLOW/RED, aggregates into ONE overall verdict. Writes `analysis/gym/{date}.md` + `automation/state/gym-scorecard-{date}.json`. Cost: $0.

---

## OP-30: Effort-tier + concurrency discipline + free-tier-first routing

**Effort-tier + concurrency discipline + free-tier-first routing (ratified 2026-05-21 by J).**

**Three hard rules:**
1. **Default `--effort medium`.** `effort=max` is reserved for NAMED architectural problems only.
2. **One interactive Claude session at a time.** Concurrent sessions share the rate-limit pool.
3. **Free-tier-first for autonomous R&D.** Model ladder: `nvidia/nemotron-3-super-120b-a12b:free` → `deepseek/deepseek-v4-flash:free` → `minimax/minimax-m2.5:free` → `minimax/minimax-m2.5` paid ($3/day cap). Claude kept for: live trading, MCP work, vision tasks.

**Cost target:** Daily Claude burn ≤$250/day. Haiku heartbeat unchanged (~$130/day). Free-tier autonomous work: $0.

**The reword test:** Before starting an interactive Claude session, ask: "Can a `python chef_nemotron.py --task ...` do this for $0?" If yes → use that.

---

## OP-32: Market-hours Claude firewall

**Market-hours Claude firewall — two mechanical layers (ratified 2026-05-21 night).**

> **STATUS: NUKED 2026-05-23.** Both `Gamma_SessionGuard` and `Gamma_MarketHoursCircuitBreaker` unregistered in reset Phase A because they locked J out on 2026-05-22. The A3-followup doctrine reminder at the top of CLAUDE.md replaces automated enforcement with self-discipline.

**Layer 1 (nuked):** `Gamma_SessionGuard` HARD mode — killed interactive Claude CLI processes ≥5 min old during 09:30-15:55 ET every 2 min.

**Layer 2 (nuked):** `Gamma_MarketHoursCircuitBreaker` — killed interactive sessions at $100 daily spend threshold, wrote `rate-limit-cooldown.json` with `claude_print_exempt: true` to exempt `claude --print` scheduled tasks.

**Why nuked:** Layer 1 had no exception for J's own interactive sessions. On 2026-05-22 J was locked out 09:30-15:55 ET — could not use Claude at all. Over-corrected.

**`claude_print_exempt` remains in `_shared.ps1`** — the Test-RateLimitCooldown -TaskName exemption logic is preserved for if the circuit breaker is ever reinstated.

**The permanent fix:** separate Anthropic API accounts (J action, billing decision needed). Until then: self-discipline per the CLAUDE.md top-of-file reminder.

---

*Archive created 2026-05-23. Full lesson text lives in [docs/LESSONS-LEARNED.md](LESSONS-LEARNED.md).*
