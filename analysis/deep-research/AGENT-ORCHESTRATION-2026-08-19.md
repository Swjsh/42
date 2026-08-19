# Agent Orchestration — research + the Gamma org chart (2026-08-19)

> **Trigger:** J, 2026-08-19 — "look online for current best practices for agent orchestration, take a look at this diagram [centralized Master → Workers → Tools], figure out how we turn Gamma into the master agent and our worker agents into all the repeated things I ask for, and give them tools." Success criteria J set: **a fully autonomous Gamma.**
>
> **Method:** `/deep-research` fan-out — 109 agents, 758 tool calls, 10.2M tokens, 19 min. Every claim went through 3-vote adversarial verification (≥2/3 refutes kills it). Most candidate claims DIED. What survives below is what survived that.

---

## Verdict

**The diagram is already built here — three times over, un-unified — and more agents is the wrong next move.**

1. Anthropic's own 2026 guidance is **single-agent-first**: multi-agent costs **3–10x the tokens** for equivalent tasks and is *contraindicated* exactly where agents share context. Gamma's live trading path is already the right shape (deterministic, $0, no LLM on the hot path). Don't "agentify" it.
2. The measured failure in this rig is **not missing workers — it is unverified worker output and undelivered results.** 12 of 690 free-tier worker reports fabricated artifacts that never existed, undetected for two months. 4 of 6 things J repeatedly asks for already have complete machinery that simply never *pushes* him an answer.
3. So the master's missing arm is the diagram's own third bullet — **"interpret worker response / task reassignment"** — not its second.

---

## Part 1 — What the research actually established

11 findings survived adversarial verification. Confidence is the swarm's own vote.

### The default is NOT multi-agent — high confidence (3-0)

> "we recommend finding the simplest solution possible, and only increasing complexity when needed" … "This might mean not building agentic systems at all."
> — [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents), Dec 2024

Reaffirmed Jan 2026: teams "invested months building" multi-agent architectures "only to [find] improved prompting on a single agent achieved equivalent results." **This is a vendor arguing against its own token revenue** — weight it accordingly. It is a *starting default, not a ceiling*: the same post names three situations where multi-agent consistently wins — context pollution, genuinely parallel subtasks, and specialisation improving tool selection **when there are 40+ tools**.

### Decompose by CONTEXT boundary, never by role — high confidence (3-0)

> "When agents are split by problem type, they engage in a 'telephone game,' passing information back and forth with each handoff degrading fidelity."
> — [Building multi-agent systems](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them), Jan 2026

Named anti-patterns: sequential phases of the same work (plan → implement → test); "one agent writes features, another writes tests, a third reviews." Independently corroborated by a *competitor* — Cognition's [Don't Build Multi-Agents](https://cognition.com/blog/dont-build-multi-agents). **Scope qualifier that matters:** the objection bites on the **write path**. Read-only fan-out (search, exploration, review) is still endorsed, and writing worker output to the *filesystem* — which is what this repo already does — defeats the telephone game.

### The cost multiplier — medium confidence (2-1), and deliberately hedged

> "agents typically use about 4x more tokens than chat interactions, and multi-agent systems use about 15x more tokens than chats" … "token usage by itself explains 80% of the variance"
> — [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system), Jun 2025

Jan 2026 restates it as **3–10x vs single-agent**. **Why only medium:** both are informal ("in our data"), no n, no methodology, no task set. The 15x figure predates compaction, prompt caching and code-execution-with-MCP. Independent work shows the multiplier is workload-dependent and can even invert. The load-bearing implication is not the number — it is that **token usage explains 80% of quality variance**, i.e. *multi-agent is a token-delivery vehicle, not an architectural cause of quality.*

### The delegation contract — high confidence (3-0)

> "Each subagent needs an objective, an output format, guidance on the tools and sources to use, and clear task boundaries. Without detailed task descriptions, agents duplicate work, leave gaps, or fail to find necessary information."

Concrete failure they document: from "research the semiconductor shortage", "one subagent explored the 2021 automotive chip crisis while 2 others duplicated work investigating current 2025 supply chains." Effort tiers: 1 worker / 3–10 calls for fact-finding · 2–4 workers for comparisons · 10+ for complex research. Reinstated in the 2026 SDK as first-class fields (`description`, `prompt`, `tools`/`disallowedTools`) — plus: **"The only content you pass from parent to subagent is the Agent tool's prompt string."**

### Blast-radius caps now ship — high confidence

Agent SDK defaults: **depth 3**, **concurrency 20**, **spend UNCAPPED by default**. Motivated by a filed incident where one Agent call spawned **48+ background agents / ~1.5M tokens**. Caveats carried forward: version-gated, and the budget cap is a *soft post-hoc* check (an observed test overshot a $0.01 cap to $0.084).

### Scale boundary — high confidence (3-0)

> "Subagents work well for a few delegated tasks per turn. For runs that coordinate dozens to hundreds of agents, use the Workflow tool, which moves the orchestration into a script the runtime executes outside the conversation context."

Intermediate results live in **script variables** instead of the context window. Disclosed downside: a workflow "can use meaningfully more tokens than working through the same task in conversation."

### Tools deserve more engineering than prompts — high confidence (3-0)

> "While building our agent for SWE-bench, we actually spent more time optimizing our tools than the overall prompt."

Worked example: forcing **absolute filepaths** eliminated an entire error class. Caveat: unquantified vendor self-report — a strong design heuristic, not proof.

### Also verified

- **OpenAI Agents SDK** makes master/worker a first-class primitive: `Agent.as_tool()` — "A manager agent keeps control of the conversation and calls specialist agents." Selection rule vs handoffs: agents-as-tools for a **bounded subtask where the manager owns the final answer**; handoffs when **routing itself is the workflow**. Gotcha: **parent conversation state is not inherited** by a tool-invoked worker.
- **Context compression at the worker boundary** is one of three stated mechanisms (2000+ raw tokens in → 50–100 out). It is a *context-quality* win for the orchestrator, explicitly **not** a total-token saving.
- Agentic systems "trade latency and cost for better task performance"; autonomy brings "the potential for compounding errors" — mitigation is **guardrails and sandboxed testing**, not trust.

### What the research could NOT establish — read this before citing it

Four of six sub-questions produced **zero** surviving claims:

| Asked | Result |
|---|---|
| State/memory passing, compaction between master↔workers | **All candidates refuted 0-3.** No verified position. |
| Comparative topology benchmarks (supervisor vs swarm vs hierarchical) | **All refuted 0-3.** Topology guidance below is *vendor prescription, not measurement.* |
| Reliability / eval / observability / durable execution | Nothing survived. |
| LangGraph · CrewAI · AutoGen · Google ADK · A2A protocol status | Nothing survived. A2A/MCP layering claim refuted 0-3. |

Every surviving finding is Anthropic or OpenAI first-party documentation — the right authority for *"what does the SDK do"*, the **wrong** authority for *"which architecture performs better."*

---

## Part 2 — What Gamma actually is today (measured, this session)

### Three orchestration layers already exist

| Layer | Master | Workers | Cost |
|---|---|---|---|
| **Deterministic** | Windows Task Scheduler | ~118 `Gamma_*` tasks; `heartbeat_core.py` is the live engine | **$0** — no LLM on the hot path |
| **Claude** | `conductor.md` + `.claude/agents/gamma.md` | 9 specialist personas via the Agent tool, each model-pinned + tool-scoped, orders in `disallowedTools` | Max pool |
| **Free** | `gamma_manager.py` | 6 roles (strategist/coder/critic/validator/forager/chef) via `swarm_client` | $0 |

This is **already the diagram**, and the deterministic layer being the biggest is exactly right per the research.

### Three measured defects

**1. Worker output was never verified — 12 fabricated reports over 2 months.**
`analysis/manager/2026-08-18-2253-strategist-weekly-options-build.md` reported the weekly-options Phase 0 build complete, citing `expiry_selector.py`, `blast_radius_20260818.json`, `sector_heat_signals.csv` — **none of which were ever written**, while the real work ran elsewhere. A sweep of all 690 reports found **12 with the same shape** (2026-06-25 → 2026-08-18), a 1.7% base rate. The existing `_looks_like_garbage()` catches token-salad; it cannot catch a *fluent* lie. This is the structural exposure of master/worker: **the orchestrator only ever sees the summary, never the trace.**

**2. Escalation had no dedupe — one blocker, nine queue lines.**
`gamma_manager.escalate()` appended to `queue.md` unconditionally on a 20-minute cadence. One unresolved blocker produced 9 near-identical `ESCALATION (manager_flagged)` entries in a day. The coordinator re-words each time, so string equality never matched.

**3. Fan-out is expensive here and was uncapped.**

| Date | Notional | Sessions |
|---|---|---|
| 2026-08-13 | $1,554.74 | 16 |
| 2026-08-15 | $1,008.94 | 26 |
| 2026-08-18 | $891.85 | 18 |
| 2026-08-19 | $461.47 | 10 |

Mean ≈ **$780/day** over the last 10 logged days. The registry's own 2026-07-25 census put the conductor family at **93.3%** of automation burn. *Honest framing: this is `spend_summary.py` pricing tokens at API list rates — on the Max plan it is **capacity, not a bill**. But it is the same rate-limit pool the live heartbeat ticks on, which is why market-hours fan-out is banned.*

### What J actually repeats — mined from `j-question-ledger.jsonl`

29 genuine prompts (of 52 rows; 23 are audit-harness pollution — filed as `T-JQL-CLASSIFIER-2026-08-18`). They collapse to **six intents**:

| Intent | Asked | Owner | Machinery exists? | Delivered? |
|---|---|---|---|---|
| `is_everything_running` | 4 | coach | ✅ full | ❌ PULL_ONLY |
| `status_tldr` | 3 | coach | ✅ full | ❌ PULL_ONLY |
| `new_lane` | 3 | chef | ✅ full | ⚠️ PARTIAL |
| `edge_review` | 2 | analyst | ✅ full | ⚠️ PARTIAL |
| `todays_theory` | 1 | scout | ✅ full | ❌ PULL_ONLY |
| `explain_for_me` | 1 | **UNOWNED** | ❌ none | ❌ NONE |

**The finding that matters: five of six already have complete machinery. J keeps asking because nothing pushes.** Adding worker agents to answer these would add cost and telephone-game risk to problems that are already solved on disk. This matches the standing memory *"Gamma works but is invisible; the fix is self-initiated briefs, never more machinery."*

---

## Part 3 — The org chart, made enforceable

`automation/state/worker-registry.json` is now the single machine-readable source of truth, validated by `setup/scripts/worker_registry.py --check`.

Every worker must declare four things, each derived from a verified finding:

| Field | Why it is mandatory |
|---|---|
| `context_boundary` | Anthropic: decompose by **context**, not role. A worker that cannot name the bulky thing it reads *so the master doesn't have to* is a prompt, not an agent — it belongs inline. |
| `verified_by` | The master cannot bank an unverified completion claim (the 12-report scar). Must be a **deterministic** gate. |
| `delivers_to` | Work that lands nowhere gets redone by the next session. |
| model pin | Subagents cannot switch their own model; an in-prompt "run /model sonnet first" is a **no-op** (2026-07-23 scar: 2.2M tokens on mechanical grid work). |

The validator RED-proofs against 8 injected drift classes — model drift, missing persona, fake scheduled task, missing boundary/gate, unknown intent owner, bad delivery status, missing machinery path. All 8 caught; baseline is 0 drift.

Master caps, wired at automation's own launch point (never a global interactive default, L213): **depth 1** (specialists may not spawn their own subagents) · **concurrency 5** (matches `conductor.md` STAGE 2's own "2–5 agents" ceiling) vs Anthropic's defaults of 3 / 20.

---

## Part 4 — What shipped this session

| Artifact | What it does |
|---|---|
| `setup/scripts/worker_output_verify.py` | **Anti-fabrication gate.** Extracts every file-path and git-SHA claim from a worker report, resolves each against disk + `git cat-file`, and returns VERIFIED / UNVERIFIED / FABRICATED. `--only-bad` batch mode sweeps all 690 historical reports in one pass. |
| `setup/scripts/gamma_manager.py` | Gate wired into dispatch: a FABRICATED report is **quarantined with a banner, logged `ok:false`, and escalated** — never banked as work done. Plus fuzzy escalation dedupe (see below). |
| `setup/scripts/worker_registry.py` | Validates the org chart against `.claude/agents/*.md`, `SCHEDULED-TASKS.md` and disk. `--show` / `--intents` render it. `--contract` validates a delegation spec against the four-part contract. |
| `automation/state/worker-registry.json` | The org chart itself: master, caps, 9 workers, 6 J-intents with ownership + delivery status + named gaps. |
| `setup/scripts/run-conductor.ps1` | Fan-out depth/concurrency caps at the launch point. |
| `backtest/tests/test_worker_output_verify_2026_08_19.py` | 13 guard tests, all passing. |

**Escalation dedupe threshold is measured, not guessed.** Jaccard over stemmed content words, scored on the seven real `queue.md` appends:

| Class | Score |
|---|---|
| Same blocker, reworded (the real dupes) | **0.367 – 0.913** |
| Related but genuinely different (lane garbage, 429s) | 0.176 – 0.206 |
| Unrelated (engine RED, sizing breach) | 0.000 – 0.065 |

Threshold **0.30** sits in the gap with margin both ways. Too high and the spam returns; **too low and dedupe becomes a gag that hides a second real blocker from J** — so there is an explicit anti-gag test.

### Verification quoted, not claimed

```
worker-registry: GREEN (9 workers, 6 j-intents, 0 drift)
13 passed in 1.53s
[!!] FABRICATED  analysis\manager\2026-08-18-2253-strategist-weekly-options-build.md  (3/8 artifacts resolve)
[OK] VERIFIED    analysis\daily-brief\2026-08-19-WEEKLY-LANE-MORNING-BRIEF.md  (16/16 artifacts resolve)
sweep of 690 reports: 611 NO_CLAIMS - 40 VERIFIED - 27 UNVERIFIED - 12 FABRICATED
```

RED-proof, fabrication gate — disable the bare-filename extraction and the detector goes blind:
```
WITH fix   : ['sector_heat.py', 'expiry_test_20260818.json', 'sector_heat_signals.csv', 'blast_radius.json', 'blast_radius_20260818.json']
WITHOUT fix: []
```

---

## Part 5 — What is NOT done (the honest gap to "fully autonomous")

Autonomy is not blocked on orchestration machinery. It is blocked on **delivery** and on **one unowned intent**:

1. **4 of 6 J-intents are PULL_ONLY.** The answer is written to disk before J asks and he still has to ask. Until a pre-open readiness line and an EOD "here's our edge" line *push* to him, he remains the scheduler.
2. **`explain_for_me` has no owner** — nothing translates machine output into "what this means for you and what to do."
3. **`max_budget_usd_per_fire`** is declared (3.0) but the wrapper still passes `-MaxBudgetUsd 10.00`; tightening needs a measured per-fire distribution, not a guess.
4. **Runtime honoring of the depth/concurrency env vars is UNVERIFIED** this session — names come from Anthropic's docs (verified 2026-08-19) and are version-gated. Setting an unknown name is a no-op, so this fails open.
5. **The free tier remains unaudited beyond artifacts.** The gate proves a named file exists — it does *not* prove a number is real. Numeric fabrication is still open.
6. **Known false-positive class:** a post-mortem that *quotes* fabricated filenames as evidence trips the gate. This document does — running it against itself returns `FABRICATED (17/19)` on `blast_radius_20260818.json` and `sector_heat_signals.csv`, the exact names it is reporting. No escape-hatch marker was added on purpose: a worker could write one to evade the gate. The gate is scoped to `analysis/manager/` worker output, where the trade-off is correct.

## Do NOT do these (research-backed kills)

- ❌ Don't add a worker per J-question. Five of six already have full machinery; a new agent adds 3–10x tokens and a telephone-game hop to a solved problem.
- ❌ Don't split the trading path plan→implement→test across agents. Named anti-pattern; sequential phases of one feature share too much context.
- ❌ Don't put an LLM back on the live tick. The deterministic hot path is the architecture the research endorses, and it already works.
- ❌ Don't trust a worker summary. It is the one thing the orchestrator structurally cannot see behind.
