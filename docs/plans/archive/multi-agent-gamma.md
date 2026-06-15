# Multi-Agent Gamma 2.0 — Master Plan

> Ratified 2026-05-09 by J. Synthesis of three sources (Claude multi-agent orchestration + obra/superpowers patterns + smtg-ai/claude-squad architecture) applied to Project Gamma's autonomous 0DTE SPY trading system.
>
> **Status:** Build in progress. See "Phase tracking" at bottom for live status.
>
> **Authority:** This plan is doctrine. Items here override prior assumptions about Gamma serial-only execution. Cross-references in CLAUDE.md operating principle 15.

---

## The thesis

Three primitives converge:

| Primitive | Source | What it gives Gamma |
|---|---|---|
| **Parallelism** | Claude Agent SDK + Python `multiprocessing.Pool` | 10× research throughput, 3× faster EOD analysis |
| **Discipline** | obra/superpowers (skill pack, MIT, ~184k stars) | Rules→Gates conversion, Iron Law verification, adversarial review patterns |
| **Safe parallel state** | smtg-ai/claude-squad architecture (Go TUI, AGPL — patterns only, do NOT vendor) | Hash-detection, daemon safety, content-addressed paths, hard concurrency caps |

**What we are NOT doing:** running claude-squad as a binary (tmux dependency = Windows blocker; spawning N independent Claude sessions blows operating principle 3 budget cap; interactive-only design incompatible with Task Scheduler). We steal patterns, not code. AGPL viral clause means we never vendor source.

---

## The 10 Big Wins (ratified)

### #1 — Parallel weekend autoresearch ⭐ HIGHEST ROI

**What:** Replace sequential per-seed evaluation in `random_eval.py` with `multiprocessing.Pool` workers. Each worker process gets its own copy of `lib.filters` module so the contextmanager-based parameter patching (`runner._patched_filter_constants`) works in isolation. Update `setup\run-weekend-research.ps1` to launch parallel batches.

**Why:** `runner._patched_filter_constants` mutates module-level constants in `lib.filters`. **It is NOT thread-safe and NOT reentrant.** Process-based parallelism is mandatory — each worker imports its own copy.

**Files:**
- New: `backtest/autoresearch/parallel_eval.py` (multiprocessing.Pool wrapper)
- New: `backtest/autoresearch/parallel_sub_window.py` (5×N tasks parallelized)
- Modified: `backtest/autoresearch/random_eval.py` (add `--workers N` flag)
- Modified: `setup/run-weekend-research.ps1` (parallel wave launcher)

**Cost:** $0 LLM (pure Python). Wall-time: 30-seed batch from ~4hr to ~25min on 4 cores. 300-seed run becomes feasible in a single weekend.

**Concurrency cap:** Hard-coded `MAX_PARALLEL_WORKERS = 4` (Windows + 16GB RAM headroom). Borrowed from claude-squad's `GlobalInstanceLimit = 10`.

---

### #2 — Adversarial bull/bear v15 review

**What:** Sunday evening, before any v15 ratification, dispatch TWO subagents via the Agent SDK pattern:
- Agent BULL: defend the candidate, justify ratification on every gate
- Agent BEAR: find every reason to reject, every cherry-pick, every sub-window weakness
- Coordinator: assigns +5 points to whichever finds more serious issues; surfaces only objections that survive both

**Why:** v14 was ratified on a 38-day cherry-picked window. The single weakest link is `synthesize_v15.py` — one eye on the sweep results. Adversarial review is the cheapest insurance against bias.

**Files:**
- New: `automation/prompts/adversarial-review.md` (Sunday-only invocation)
- New: `setup/scripts/run-adversarial-review.ps1` (Sunday 19:00 ET, after weekly-review)
- Modified: `automation/prompts/weekly-review.md` (Section 7 calls out adversarial verdict)

**Cost:** ~$0.10 per Sunday = ~$0.40/mo.

**Source pattern:** Jesse Vincent (obra) blog, "Adversarial review" (May 1, 2026). Verbatim quote: *"Please ask two subagents to review this work. Tell them that whomever finds the largest number of serious issues gets five points."*

---

### #3 — Rules → Gates conversion

**What:** Each of Gamma's 10 trading rules is currently *rule-shaped* (rationalizable). Convert each to *gate-shaped* (the next action is blocked until an observable check executes).

**Example transformations:**

| Rule (rationalizable) | Gate (observable check) |
|---|---|
| "No trade after daily loss limit" | Before `place_option_order` → read `decisions.jsonl` for today → sum realized P&L → if ≤ -50% × start_equity, REPLACE the call with a journal-only entry |
| "No setup, no trade" | Before `place_option_order` → match developing_setup.name against `strategy/playbook.md` setup names → if not in list, BLOCK |
| "Wait for the trigger" | Before `place_option_order` → developing_setup.score must equal score_max from a *closed* bar AND triggers_fired must contain ≥1 named trigger → if anticipating, BLOCK |
| "Defined stop on entry" | Before `place_option_order` → `current-position.json` write must include both `premium_stop` and `chart_stop` fields → if either null, BLOCK |
| "PDT awareness" | Before `place_option_order` → read `circuit-breaker.json#day_trades_used_5d` → if ≥3 AND account.equity<25k, BLOCK |

**Files:**
- New: `doctrine/rules-as-gates.md` (the 10-row gate table)
- Modified: `automation/prompts/heartbeat.md` (entry branch gate sequence)
- Modified: `CLAUDE.md` (rule wording aligns with gate phrasing)

**Cost:** $0 (doctrine doc + prompt update).

**Source pattern:** Jesse Vincent blog, "Rules and Gates" (Apr 7, 2026). *"A rule has an opt-out path. A gate doesn't — the next action is blocked until the gate condition is met."*

---

### #4 — Parallel EOD analysis

**What:** Split `eod-summary.md` into orchestrator + worker prompts. Worker prompts run as parallel `Invoke-Claude` PowerShell jobs. Orchestrator aggregates JSON outputs at the end.

**Independent EOD steps (can parallelize):** 1 (metrics), 2 (predictions), 3 (rule-break audit), 6 (trades.csv close-out), 7a-7i (trade grading suite — 9 substeps), 8b (shadow scorecard), 8c (dark-pool aggregation).

**Sequential dependencies:** Step 4 (reflection) needs 1-3. Step 5 (journal append) needs 4. Step 8 (setup-performance) needs 1+7a-7f. Step 9 (logging) needs all.

**Files:**
- New: `automation/prompts/eod-orchestrator.md` (coordinator, ~30s)
- New: `automation/prompts/eod-workers/metrics.md`
- New: `automation/prompts/eod-workers/predictions.md`
- New: `automation/prompts/eod-workers/rule-audit.md`
- New: `automation/prompts/eod-workers/trade-grading.md` (combines 7a-7f, low-cost)
- New: `automation/prompts/eod-workers/chart-walk.md` (combines 7b/7e/7g/7h/7i, chart-heavy)
- New: `automation/prompts/eod-workers/shadow-darkpool.md` (combines 8b+8c)
- Modified: `setup/scripts/run-eod-summary.ps1` (parallel job launcher with `Start-ThreadJob`)
- Deprecated (kept for fallback): `automation/prompts/eod-summary.md`

**Cost:** Each worker uses ~200-400 tokens vs ~1200 in monolithic. Net cost: roughly flat (workers redundantly load context, but each has tighter scope = fewer wasted reasoning tokens). **Wall time: 8 min → 3 min.**

**Concurrency cap:** Hard-coded `MAX_PARALLEL_EOD_WORKERS = 4` to respect rate limits.

---

### #5 — Iron Law verification gate before trades.csv writes

**What:** Codify the rule that nothing gets written to `journal/trades.csv` or `decisions.jsonl` until fill confirmation is in hand. Use Jesse's "Claim → Required-Evidence" table format.

**Claim/Evidence table:**

| Claim Gamma is about to make | Required evidence (must execute before claim) |
|---|---|
| "Order filled" → trades.csv ENTRY row | `mcp__alpaca__get_order_by_id(order_id)` returns `status: "filled"` AND `filled_qty > 0` |
| "Position closed" → trades.csv EXIT row | `mcp__alpaca__get_open_position(symbol)` returns 404 OR position.qty == 0 |
| "Stop triggered" → decisions.jsonl EXIT_STOP | exit_order.status == "filled" AND exit_order.side opposite of entry |
| "TP1 hit" → decisions.jsonl EXIT_TP1 | exit_order.filled_qty == tp1_qty AND remaining position.qty > 0 (runner survives) |
| "Daily kill-switch tripped" → circuit-breaker.tripped=true | sum(today's realized P&L) ≤ -50% × start_equity (computed from filled exits, NOT estimated marks) |

**Files:**
- New: `doctrine/iron-law-trades.md` (the verification gate table)
- Modified: `automation/prompts/heartbeat.md` (Position branch — prefix every CSV/JSONL write with the verification step)

**Cost:** ~1 extra MCP call per exit ≈ $0.001/exit. Negligible.

**Source pattern:** Jesse Vincent blog "verification-before-completion" skill: *"The Iron Law: NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE."*

---

### #6 — SessionStart hook auto-injection of state digest

**What:** A SessionStart hook that runs a 50-line PowerShell script summarizing current state (rule_version, kill-switch status, open position, today's P&L, last 3 decisions) and injects it as `additionalContext`. Every premarket/heartbeat/EOD invocation starts with state already loaded — no token spent on tool calls to discover.

**Token savings:** Heartbeat currently spends ~400-600 tokens on initial state-discovery tool calls. 127 ticks/day × 22 trading days × 500 tokens × ~$0.0008/1k Haiku output = **~$1.10/mo savings**. Plus latency improvement: each state read = 200-500ms via Read tool, vs <10ms via pre-injected context.

**Files:**
- New: `setup/scripts/session-start-digest.ps1` (the digest generator)
- New: `setup/hooks/session-start.json` (Claude Code hook config matching `startup|clear|compact`)
- Modified: `~/.claude/settings.json` (register the hook)

**Cost:** Negative (saves money). One-time PowerShell run per session start = <100ms.

**Source pattern:** obra/superpowers `hooks/hooks.json` matcher `"startup|clear|compact"` — hook re-fires on context reset, ensuring state stays injected even after `/compact`.

---

### #7 — Hash-based heartbeat early-exit

**What:** Heartbeat computes `state_hash = sha256(loop_state.last_bar_timestamp + loop_state.last_filter_score + current_position.status + circuit_breaker.tripped + vix_cache.value_rounded_to_5_cents)`. If hash equals `loop-state.last_state_hash`, skip the Claude call entirely — write a single-line log row and exit.

**Why:** 127 heartbeat ticks/day. Many ticks have **literally nothing changed** since last tick (same 5m bar, same VIX, same ribbon). Today these still fire a Claude call to verify nothing happened. Hash check is ~5ms in PowerShell.

**Estimated skip rate:** 30-50% of ticks on quiet days. At ~$0.005/Haiku tick, that's $0.05-$0.10/day saved = **~$1.50-$3/mo**.

**Files:**
- New: `setup/scripts/compute-state-hash.ps1` (10-line helper)
- Modified: `setup/scripts/run-heartbeat.ps1` (hash check before `Invoke-Claude`)
- Modified: `automation/state/loop-state.json` schema (add `last_state_hash` field, schema bump v3 → v4)

**Cost:** Negative (saves money + latency).

**Source pattern:** claude-squad `tmux/tmux.go` `HasUpdated()` — SHA-256 of captured pane content used to detect activity without storing raw output.

**Safety:** Hash check is BYPASSED if (a) tickIndex % 5 == 1 (HTF tick), (b) position is open, (c) developing_setup.score ≥ 7 (escalation territory). These conditions guarantee Claude always sees high-stakes ticks.

---

### #8 — Pressure-test-driven filter writing (TDD for rules)

**What:** Every recurring loss fingerprint in weekly-review Section 3.5 becomes a failing replay test BEFORE any filter is written. The minimal filter is added; replay must now block the loss; ratify.

**Workflow:**
1. Weekly-review Section 3.5 mines `journal/losses/*.md` for recurring patterns → `R-NNNN` candidate IDs
2. For each R-NNNN, write `backtest/tests/pressure_tests/test_R{NNNN}.py` — replays the historical bars, asserts current engine takes the loss, FAILS the test (this is RED)
3. Write minimal filter addition in `lib/filters.py`
4. Re-run pressure test — must now PASS without filter (loss blocked)
5. Run full backtest — net P&L must not regress > 5% (no over-fitting)
6. Ratify: bump rule version, update params.json, log to CHANGELOG

**Files:**
- New: `backtest/tests/pressure_tests/__init__.py`
- New: `backtest/tests/pressure_tests/conftest.py` (fixtures: load historical bars by date+time)
- New: `backtest/tests/pressure_tests/README.md` (the methodology)
- New: `setup/scripts/run-pressure-tests.ps1` (CI hook for premarket)
- Modified: `automation/prompts/weekly-review.md` (Section 3.5 outputs R-NNNN proposals → routes to pressure-test queue)

**Cost:** Pure Python tests = $0 LLM. Manual filter writing = ~$0.20 per R-NNNN if I dispatch a subagent.

**Source pattern:** obra/superpowers `writing-skills/SKILL.md` meta-skill — every new skill is RED-GREEN-REFACTOR. Applied to filter creation.

---

### #9 — Daemon PID + signal handlers for heartbeat

**What:** Wrap `Invoke-Claude` (in `_shared.ps1`) so each heartbeat tick:
1. Writes its PID to `automation/state/heartbeat.pid` on start
2. Registers a Ctrl+C / SIGTERM handler that flushes any in-flight `current-position.json` write before exit
3. Removes the PID file on graceful exit

**Why:** Today, Task Scheduler can interrupt mid-write. If `current-position.json` is half-written when Task Scheduler kills the task at the timeout, the `Repair-StateFiles` recovery loses the in-flight state (restores to `.lastgood/` which may be one tick stale). A signal handler that completes the write atomically before exit closes this hole.

**Files:**
- Modified: `setup/scripts/_shared.ps1` — `Invoke-Claude` writes PID; `Stop-ProcessTree` checks for the pidfile-handler hint
- New: Inline PowerShell signal handler in `Invoke-Claude` (uses `[Console]::CancelKeyPress` + `[AppDomain]::CurrentDomain.ProcessExit`)

**Cost:** $0.

**Source pattern:** claude-squad `daemon/daemon.go` — `signal.Notify(sigChan, SIGINT, SIGTERM)` + on-signal save-instances-then-exit.

---

### #10 — Two-stage subagent review for param promotions

**What:** Every param promotion (v14 → v15, v15 → v15.1, etc.) gets reviewed by TWO subagents:
- Stage 1: **Spec-compliance reviewer** — does the candidate satisfy every gate in `analysis/recommendations/SCORECARD_TEMPLATE.json` (data_hash_match, sub_window_stable, evidence_n ≥ 20, dominates flag, thresholds 4-of-4)? Pure check.
- Stage 2: **Quality reviewer** — IS the gate the right gate? Are we measuring the right thing? Did the candidate over-fit a sub-window?

**Why:** Different reviewers, fresh context. Avoids the "reviewer-is-author" conflict.

**Files:**
- New: `automation/prompts/param-promotion-spec-review.md`
- New: `automation/prompts/param-promotion-quality-review.md`
- New: `setup/scripts/run-param-promotion-review.ps1` (called by weekly-review when scorecard verdict == "auto_ratify")
- Modified: `automation/prompts/weekly-review.md` (Section 7: route auto_ratify → spec-review → quality-review → final verdict)

**Cost:** ~$0.05 per promotion. Promotions are rare (monthly at most) → ~$0.20/mo cap.

**Source pattern:** obra/superpowers `subagent-driven-development` — two-stage review (spec compliance → code quality) with model-tier selection.

---

## Hidden Gem #1 — Rationalization counter-table

**What:** A 12-row table mapping J's known emotional failure modes to canonical counters, injected at heartbeat startup. When J sends a message containing matching language, Gamma cites the rule.

**Sample rows:**

| Trigger language | Counter |
|---|---|
| "It's cheaper now" | Rule 4: adding requires fresh trigger fire |
| "I'll size up to win it back" | Rule 5: hard veto on revenge |
| "Just one more, market's about to bounce" | Rule 1: no setup, no trade |
| "Move the stop, just this once" | Rule 3: stop is mechanical |
| "Skip the journal entry, I'll do it later" | Rule 8: pre-trade thesis BEFORE order |
| "But the backtest..." | Rule 9: no mid-session rule changes |

**Files:**
- New: `doctrine/rationalization-counters.md` (the table)
- Modified: `automation/prompts/heartbeat.md` (load table on startup; check user messages)

**Cost:** $0 (~50 tokens of injected context).

---

## Hidden Gem #2 — Writing-skills TDD methodology applied to filters

Already covered in Big Win #8. Just calling out that this isn't a separate item; it's the method behind #8.

---

## Phase rollout

### Phase 0 — Research throughput (BUILD FIRST)

- [ ] #1 Parallel weekend autoresearch
- [ ] Kick off weekend autoresearch with new infra
- [ ] #4 Parallel EOD analysis

**Goal:** Make weekend research 10× more thorough. v15 candidate selection benefits immediately.

### Phase 1 — Discipline layer

- [ ] #3 Rules → Gates conversion
- [ ] #5 Iron Law verification gate
- [ ] #2 Adversarial bull/bear v15 review

**Goal:** Tighten the doctrine before next ratification cycle.

### Phase 2 — Performance layer

- [ ] #6 SessionStart hook
- [ ] #7 Hash-based heartbeat early-exit
- [ ] #9 Daemon PID + signal handlers

**Goal:** Cut token spend, cut latency, harden against crashes.

### Phase 3 — Self-improvement layer

- [ ] #8 Pressure-test methodology
- [ ] #10 Two-stage param promotion review
- [ ] HG1 Rationalization counter-table

**Goal:** Close the Karpathy outer loop.

---

## Cost ledger

| Item | LLM cost/mo | Net change |
|---|---|---|
| #1 Parallel autoresearch | $0 | $0 |
| #4 Parallel EOD | +$2.40 | +$2.40 |
| #2 Adversarial review | +$0.40 | +$0.40 |
| #3 Rules→Gates | $0 | $0 |
| #5 Iron Law gate | +$0.10 | +$0.10 |
| #6 SessionStart hook | -$1.10 | **-$1.10** |
| #7 Hash early-exit | -$2.00 | **-$2.00** |
| #8 Pressure-tests | $0 | $0 |
| #9 Daemon safety | $0 | $0 |
| #10 Two-stage review | +$0.20 | +$0.20 |
| HG1 Rationalization | $0 | $0 |
| **Total** | | **+$0.00 net** (savings offset additions) |

Compliance with operating principle 3 (cost-effectiveness gate): **PASS.** Net effect is approximately budget-neutral.

---

## Phase tracking

| Phase | Item | Status | Built at |
|---|---|---|---|
| 0 | #1 Parallel autoresearch | ✅ shipped | 2026-05-09 12:18 ET |
| 0 | Kickoff weekend research | ✅ live (PID 23208) | 2026-05-09 12:20 ET |
| 0 | #4 Parallel EOD | ✅ shipped (legacy wrapper preserved) | 2026-05-09 12:23 ET |
| 1 | #3 Rules→Gates | ✅ shipped | 2026-05-09 12:25 ET |
| 1 | #5 Iron Law | ✅ shipped (heartbeat.md updated) | 2026-05-09 12:26 ET |
| 1 | #2 Adversarial review | ✅ shipped | 2026-05-09 12:27 ET |
| 2 | #6 SessionStart hook | ✅ shipped (Invoke-Claude integrated) | 2026-05-09 12:29 ET |
| 2 | #7 Hash early-exit | ✅ shipped (run-heartbeat.ps1 wired) | 2026-05-09 12:31 ET |
| 2 | #9 Daemon safety | ✅ shipped (Invoke-Claude PID lockfile) | 2026-05-09 12:32 ET |
| 3 | #8 Pressure-tests | ✅ shipped (template + conftest + README) | 2026-05-09 12:34 ET |
| 3 | #10 Two-stage review | ✅ shipped (spec + quality prompts) | 2026-05-09 12:35 ET |
| 3 | HG1 Rationalization table | ✅ shipped | 2026-05-09 12:36 ET |
| 3 | HG2 Skill TDD | ✅ covered by #8 (same methodology) | 2026-05-09 12:34 ET |

**All 10 Big Wins + 2 Hidden Gems shipped 2026-05-09. Migration path:** legacy wrappers
(`run-eod-summary.ps1`, `run-weekend-research.ps1`) preserved as fallback. When parallel
weekend research completes successfully + parallel EOD has run cleanly for 3 sessions, J
flips Task Scheduler targets to `-parallel` variants and removes legacy wrappers.

---

## Source attribution

- **Multi-agent orchestration:** Anthropic Claude Agent SDK (Python) — `claude_agent_sdk` library, `asyncio.gather` patterns, Managed Agents API (rejected for Gamma due to per-thread context cost; Agent SDK preferred)
- **obra/superpowers:** https://github.com/obra/superpowers (MIT, Jesse Vincent). Patterns extracted: gates vs rules, iron law, adversarial review, two-stage review, writing-skills TDD, SessionStart auto-injection, rationalization tables.
- **smtg-ai/claude-squad:** https://github.com/smtg-ai/claude-squad (AGPL-3.0). Patterns extracted (NO source vendored): Instance composition, hash-based change detection, daemon PID+signal pattern, content-addressed paths, GlobalInstanceLimit hard cap. NOT deployed (Windows blocker, cost blocker).

---

*Last updated by Gamma: see git log for `docs/plans/multi-agent-gamma.md`.*
