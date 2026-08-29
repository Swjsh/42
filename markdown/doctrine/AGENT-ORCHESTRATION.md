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

### The cost reality on this box
Claude runs on the **$200/mo Max pool, shared with the live heartbeat** (already a documented
scar: interactive hours starve the heartbeat). A "Sonnet army" during RTH is not a budget
question, it is a **trading-outage** question. J's own prior lesson — *multi-agent = 3-10×
tokens, split by context* — was right and, per Anthropic's measurement, **understated**.

---

## The tier map — who does what

| Tier | Runs on | Cost | Job | Never |
|---|---|---|---|---|
| **Judgment** | Opus/Fable, 1 session | high | Decompose, adjudicate, synthesise, ship/kill calls | Mechanical execution |
| **Execution** | Sonnet subagents, **≤5**, bounded | 15× multiplier | Isolated verbose work whose output must NOT flood main context | Anything needing back-and-forth |
| **The army** | **Ollama, local, `$0`** — `qwen3:14b`, `qwen3.6:35b`, `claude-local` | free | Breadth: sweeps, candidate generation, adversarial refutation, scoring at n=hundreds | Any hot path or live-trade decision |
| **The spine** | Deterministic Python + hooks + Task Scheduler (152 tasks) | `$0` | Everything on a clock; all glue and routing | — |

**The army is Ollama, not Sonnet.** That is the answer to "army of Sonnet or bigger swarm": a
free local swarm can run 100 refutation passes for the token cost of zero Sonnet subagents, and
[`automation/swarm/`](../../automation/swarm/) is already wired for it. Sonnet is a *scalpel* —
five of them, each with a hard boundary. Paid breadth is the failure mode Anthropic names first:
> Early systems exhibited: spawning "50 subagents for simple queries".

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

1. **Default is ONE context.** Delegate only when a side task would flood main context, or needs
   tool restriction. "It feels parallel" is not a reason.
2. **Breadth goes to Ollama. Judgment goes to Opus. Sonnet is 5 scalpels, never an army.**
3. **No paid fan-out during 09:30–15:55 ET.** The heartbeat shares the pool.
4. **Every delegation carries the four things.** No objective + schema + boundaries → no spawn.
5. **Every autonomous fire states its $/day before it is scheduled** (OP-3), now measurable via
   `total_cost_usd`.
6. **A goal without a completion test is not a goal.**

## Related

[[markdown/infra/DOCTRINE-HOOKS]] · [[markdown/infra/KITCHEN-SPEC]] ·
[[markdown/research/BACKTEST-DESIGN-SWARM-ARCHITECTURE]] · [[markdown/meta/REFRAME-ENGINE]] ·
[[markdown/doctrine/LESSONS-LEARNED]]
