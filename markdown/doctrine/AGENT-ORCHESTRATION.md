# Agent orchestration — how Gamma runs an army without going broke

> Written 2026-08-29 against Anthropic's published guidance, after J: *"Gamma needs to be a
> master subagent orchestrator… whether that's an army of Sonnet or an even bigger swarm using
> Ollama. Gamma needs to become autonomous finally."*
> Companion: [`../infra/DOCTRINE-HOOKS.md`](../infra/DOCTRINE-HOOKS.md) — hooks make the rules
> stick; this file decides who does the work.

---

## The two numbers that decide the whole architecture

From [Anthropic's multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system):

| Finding | Number |
|---|---|
| Orchestrator-worker (Opus lead + Sonnet subagents) **vs** single Opus, on breadth-first research | **+90.2%** |
| Agents vs a chat turn | **~4× tokens** |
| **Multi-agent** vs a chat turn | **~15× tokens** |
| Variance in research performance explained by token usage alone | **80%** |

**Both are true at once, and that is the whole design problem.** Multi-agent is dramatically
better *and* dramatically more expensive. The architecture below spends the 15× only where the
90.2% is actually available.

### Where the 90.2% is NOT available
> Poor fits: domains "that require all agents to share the same context or involve many
> dependencies between agents"… most coding tasks have "fewer truly parallelizable tasks".

That is most of what this repo does. Engine work, exit-manager changes, gate wiring — one
context, many dependencies. **Spawning agents at those is paying 15× for a worse answer.**

### The cost reality on this box — corrected 2026-08-29
> ⚠️ **This section's first draft was wrong, and J caught it within the hour.** It claimed a
> Sonnet army during RTH was a "trading-outage question" because the heartbeat shares the Max
> pool. **That mechanism is dead.** Classic gate-provenance failure: I optimised under a
> constraint without auditing where it came from.

**The live engine spends zero Anthropic tokens.** `heartbeat_core.py` is 3,267 lines of
deterministic Python; its docstring states *"No LLM on the hot path"*, and its only model layer
(2 **free** models via groq/cerebras/gemini) has been disabled since 2026-08-12
(`GAMMA_FREE_MODEL_VETO` defaults `0`). The LLM heartbeat was retired **2026-06-25** — the
"shared pool starves ticks" line in CLAUDE.md outlived the thing it described by two months.

**The only paid process inside 09:30–15:55 ET** is `Gamma_ConductorRTH`: Sonnet, low effort,
**$0.50/day cap**, 13 fires, and by its own registration it *"NEVER fans out an agent, NEVER
ships, NEVER places an order."*

**So: nothing a Claude session does can starve the trading engine.** The market-hours discipline
rule stands on **Rule 9** (no mid-session rule changes) — a real reason — not on tokens.

What survives unchanged: the **15× token multiple is Anthropic's own measurement**, and the
+90.2% applies to *breadth-first research*, not shared-context coding. That is a spend-efficiency
argument, not a safety one. Spend is J's call; the engine is not at risk either way.

---

## The tier map — who does what

**J directive 2026-08-29: "Opus orchestrator with Sonnet, Ollama only for menial small tasks."**
This is the shape Anthropic measured the +90.2% on, and with the heartbeat myth dead there is no
safety argument against it.

| Tier | Runs on | Job | Never |
|---|---|---|---|
| **Orchestrator** | **Opus/Fable — exactly one** | Decompose, set task boundaries, adjudicate, synthesise, ship/kill | Mechanical execution — it writes the spec, workers run it |
| **The army** | **Sonnet subagents** — the real workers, scaled to task complexity | Parallel investigation, review, sweeps, per-item verification, migration | Work needing tight back-and-forth with the orchestrator |
| **Menial** | Ollama local `$0` — `qwen3:14b`, `qwen3.6:35b` | Small mechanical jobs: classify, extract, dedupe, summarise-one-file, format | Judgment, adjudication, anything on a live-trade path |
| **The spine** | Deterministic Python + hooks + Task Scheduler (152 tasks) | Everything on a clock; all glue and routing | — |

**Sizing, per Anthropic — scale effort to complexity, do not fix a number:**
> simple fact-finding needs one agent with 3-10 tool calls; complex research may use "more than
> 10 subagents with clearly divided responsibilities."

The named failure mode is the opposite of caution — it is *indiscriminate* fan-out:
> Early systems exhibited: spawning "50 subagents for simple queries", agents "scouring the web
> endlessly for nonexistent sources", and subagent work duplication from vague task descriptions.

So the discipline is **boundaries, not headcount.** Ten Sonnets with disjoint, well-specified
scopes is cheap and correct; three with overlapping vague scopes is waste at any size.

---

## The orchestrator contract

Anthropic's stated requirement — every delegation carries **four things**:
> "an objective, an output format, guidance on the tools and sources to use, and clear task
> boundaries."

Vague delegation is the named cause of **duplicated subagent work**. So Gamma never writes
"look into X". It writes: *objective · exact return schema · which files/tools · what NOT to
touch.*

**Scale effort to complexity, don't fix it:**
> simple fact-finding needs one agent with 3-10 tool calls; complex research may use "more than
> 10 subagents with clearly divided responsibilities."

**Hard limits** (Claude Code): 20 concurrent subagents (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`),
nesting depth 3 (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`).

### What a subagent actually inherits
Load-bearing and easy to get wrong:

- ✅ CLAUDE.md at every level — **except built-in `Explore` and `Plan`, which skip it entirely**
- ❌ Conversation history (forks excepted)
- ❌ **Auto memory** — unless the agent declares `memory: project`
- ✅ Preloaded `skills:`, sibling roster, its own `hooks:`

Two consequences already handled: `SubagentStart` injects the prime card (covers Explore/Plan),
and any agent that must carry J's corrections needs `memory: project` in its frontmatter.

### Model routing, in resolution order
`CLAUDE_CODE_SUBAGENT_MODEL` env → per-invocation `model` → agent frontmatter → main session.
Default here is `model: sonnet` in frontmatter; the env var is the single lever to force the
whole fleet down a tier during a quota crunch.

---

## Autonomy: goals, not prompts

Gamma is not autonomous today because every loop restarts from a *prompt*. Autonomy needs a
**goal ledger that outlives the session** — the thing a fresh session reads to know what it is
in the middle of.

**The loop:**
```
GOAL (has a completion test)  →  decompose  →  route by tier  →  execute
   ↑                                                              ↓
   └────────  update ledger: done / blocked / evidence  ←─────────┘
```

Three properties, all missing today:
1. **Every goal carries a falsifiable completion test.** "Improve entries" is not a goal;
   "entry-quality ledger shows PF CI-lower > 1.0 over n≥30" is.
2. **The ledger is the only source of what's in flight** — so parallel sessions and scheduled
   fires stop duplicating each other. (Today's evidence: a background auto-committer swept this
   session's staged files into its own commit.)
3. **Blocked is a logged state, not silence.** OP-22 already bans silent stopping; the ledger is
   where that ban becomes checkable.

**Headless is the execution surface** ([`claude -p`](https://code.claude.com/docs/en/headless)):
`--bare` for reproducible scripted runs, `--append-system-prompt` for doctrine at the *system*
level (stronger than CLAUDE.md, which is only a user message), `--output-format json` which
returns **`total_cost_usd` per invocation** — so every autonomous fire can be budgeted and
capped instead of estimated.

---

## The rules that keep this from bankrupting the pool

1. **Opus orchestrates, Sonnet works, Ollama does menial.** Opus never does mechanical execution;
   Ollama never makes a judgment call.
2. **Fan out on breadth, stay single-context on depth.** Independent parallel investigation →
   agents. Shared-context engine work with many dependencies → one context. This is Anthropic's
   own boundary, and it is about answer *quality*, not cost.
3. **Every delegation carries the four things**: objective · exact return schema · which
   tools/files · what NOT to touch. No boundaries → no spawn. Vague scopes are the documented
   cause of duplicated work. The working form an orchestrating session loads is
   [`automation/prompts/orchestrator.md`](../../automation/prompts/orchestrator.md); a
   `PreToolUse` hook warns (never blocks) on a spawn that carries none of them.
4. **Size to the task, not to a constant.** 1 agent for a fact; 10+ for a real sweep.
5. **Every autonomous fire states its $/day before it is scheduled** (OP-3) — now *measurable*,
   not estimated, via `--output-format json` → `total_cost_usd`.
6. **A goal without a falsifiable completion test is not a goal.**
7. **Audit a constraint's provenance before optimising under it.** This file's own first draft
   failed that test within an hour of being written (see the corrected cost section).

## External reference: Meta Muse / SpaceXAI Grok Bot — what "alive" means, measured against this rig (2026-09-13)

> J (2026-09-13, Sunday): *"a long running autonomous agent system on your computer that works on
> your behalf, and they communicate with each other … in order for us to keep this going, we need it
> to develop into this and not a chatbot interaction."* Research: one Sonnet pass, 8 fetches; sources
> inline. "FAIRA" did not resolve to any Meta product — the closest real thing is **Muse** (Meta
> Superintelligence Labs, consumer agent announced ~2026-09-08, Bloomberg) and **Muse Code** (terminal
> agent, 2026-08-05, TechCrunch). "Grokbot" = **Grok Bot** (SpaceXAI, launched 2026-08-11 via Cursor;
> xAI was acquired by SpaceX Feb 2026 — VentureBeat, Wikipedia).

**What they are, stripped of marketing.** Both give each user/agent its own persistent CLOUD machine
(Muse "Secure VM", Grok Bot "cloud computer") that keeps running when the laptop is closed, holds
state and logins across sessions, runs scheduled/overnight jobs, and comes back to the human "when it
needs approval or has finished" (Grok Bot). Both claim agents that talk to each other; neither
publishes the mechanism, and neither exposes an open protocol (no MCP/A2A spec found). Independent
takes on Grok Bot: beta, "rough edges", "should not be trusted unsupervised" (Composio, layer3labs);
its finance use is research-desk automation, not order execution (Medium/Moonsat). Nothing ties Muse
to finance. Muse Code is pitched on cost, not capability (Wang, Yahoo Finance).

**The five properties that make them feel alive — and what this rig already has:**

| Property | Muse / Grok Bot | Gamma today (verified 2026-09-13) | Gap |
|---|---|---|---|
| Persistent process | own cloud VM, always on | Windows Task Scheduler + `Gamma_SupervisorKeepalive`; conductor 3 fires/night + weekend 2h, governed by a $30/day corrected-spend cap (`conductor-budget.json`) — hit twice on 09-12 | none structural; the cap is a real bound (measured, not a bug) |
| Self-initiated work | overnight runs, cron jobs | goal ladder (`LADDER.md`) + `goal_autopilot` + Stop-hook continuation; 30 goals closed 09-03..09-12 — all machinery, 0 on the signal until 09-11 | **which work it picks**, not whether it works |
| Agent-to-agent messaging | "team … can communicate" (mechanism undocumented) | shared state files + `queue.md` + `STATUS.md`; subagents talk only through the orchestrator | not a gap: a file bus is auditable and deterministic, which a trading rig needs more than chat between agents |
| Memory across sessions | VM state | auto-memory, goal files, LESSONS-LEARNED, journal | none |
| Returns to the human | "comes back when it needs approval or is done" | `Gamma_MorningBrief` 08:45 + `Gamma_EodBrief` 16:20 (voice, since 07-22) + `Gamma_FirmBrief` — all fired 09-11 exit 0 — **buried under 150 outbox rows/day, 141 with an @mention** (09-11: 81 unsourced watcher cards every 5 min, 27 `trade_today_watcher`, 9 prospector, 6 level-memory). J muted the channel 07-08. | **the one real gap: signal-to-noise on the only channel that reaches J** |

**Verdict.** The rig is not missing an agent platform; it is missing *discipline on the human
channel* and *judgment about which work to pick*. Copying Muse/Grok Bot would add a VM and a
subscription and change neither. What ships instead (GOAL-EARN-YOUR-KEEP item 6): the Discord
channel carries at most the two daily briefs, RED `Known broken` alarms, and J-decisions — per-signal
watcher cards and watcher pings stay in their ledgers; the EOD brief carries the "What Gamma learned
today" block (challenger vs control + tomorrow's change) so the daily touchpoint says what the rig
LEARNED and CHANGED, not what it noticed. Target: ≤3 Discord messages per trading day, @mention only
on a J-decision. Revoke = the per-source flag the builder adds.

## Related

[[markdown/infra/DOCTRINE-HOOKS]] · [[markdown/infra/KITCHEN-SPEC]] ·
[[markdown/research/BACKTEST-DESIGN-SWARM-ARCHITECTURE]] · [[markdown/meta/REFRAME-ENGINE]] ·
[[markdown/doctrine/LESSONS-LEARNED]]

### 2026-09-13 fold: AutoGen / SuperAGI / SimWorld (J asked to review; verdict = no adoption, grow the three.js HQ)

- **AutoGen** (microsoft/autogen): legacy repo in maintenance mode; Microsoft names Microsoft Agent Framework (GA Apr 2026) as the successor and the maintained community line is AG2. The 2026-08-19 topology swarm above already tested AutoGen and nothing survived verification. A bounded nightly group chat on the local brain would be a real but marginal capability over the free swarm_client roles -- logged as an option, not built (freeze to 10-30).
- **SuperAGI** (TransformerOptimus/SuperAGI): a generic agent platform (Docker + Celery + Redis + Postgres + Next.js GUI) that duplicates dashboard/ + conductor.md + the worker registry; low maintenance signal. REJECTED, filed next to the 2026-06-21 Hermes verdict -- do not re-litigate.
- **SimWorld** (SimWorld-AI/SimWorld): NeurIPS-2025-spotlight UE5 research simulator for embodied/social LLM agents (Apache-2.0 code; bundled asset licenses UNVERIFIED); Windows OK, dedicated GPU >= 6 GB, 32 GB RAM, 50-200 GB disk; windowed UE binary, no documented headless or browser-streaming path; LLM hook shown with an OpenAI model string (Ollama base_url support UNVERIFIED). It is a physics/social research world, not a state visualizer; it would contend with J gaming on the same GPU and reach the TV only via a streaming layer. Verdict: grow the three.js Gamma HQ into the world instead (day-cycle on et_clock, persona routines from the real schedule + handoff mtimes, a city block around the station), $0 marginal, browser-native, pausable. Reusable from SimWorld: ideas only (observation -> language -> action loop; city-scene framing). Third independent evaluation to converge on "do not re-platform" (Hermes 06-21, topology swarm 08-19, this one). Full review: session scratchpad hq-visuals/AUTOGEN-SUPERAGI-SIMWORLD-REVIEW.md (2026-09-13).
