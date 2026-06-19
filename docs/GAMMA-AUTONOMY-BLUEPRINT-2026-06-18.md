# Gamma Autonomy & Architecture Blueprint — 2026-06-18

> Commissioned by J: "extensive audit… can we use Claude better… Gamma needs to be DRIVING this… engine not able to perform throughout the day… get 0DTE going… brainstorm extensively, look online for valid inspiration." Six parallel audit+research agents (3 internal, 3 external). This is the synthesis.

---

## TL;DR — one diagnosis, one move

**The architecture is RIGHT. The wiring is the problem.** Gamma is already an orchestrator-worker system (the exact pattern Anthropic recommends), trading a sound 6-setup strategy. But ~100+ components (28 watchers, 88 validators, ~34 tasks, prose prompts, ~560 state files) are wired by **string-matching, convention, and English prose with ZERO enforced contracts** — so every seam can break silently and only at runtime. That's why the engine couldn't see 26 of its own 28 watchers; why gates ship "in prose but not applied"; why a field-name typo silently drops every decision. **A single human in a chat window cannot hold 100+ un-contracted seams in his head — and isn't supposed to.**

**The one move, repeated everywhere: convert prose/convention into CODE ASSERTIONS at boundaries.** Contracts at every file read, a registry that fails if a component is orphaned, a drift test that kills manual sync, a risk gate every order must pass, a real-time health beacon. Then: **turn Gamma from a chat-responder into an actual conductor** (the wake-protocol that's written but never fires) using **model routing** (Opus to reason, Haiku for rote) and **Discord as the async approve/revoke bus** — so J approves rather than operates.

Every external source (Anthropic's own agent guidance, the Ralph-loop autonomy canon, NautilusTrader/LEAN/Freqtrade, the contract-testing literature, the 0DTE options literature) independently lands on these same moves. And most of them, Gamma already learned as prose lessons (C2, C7, C9, C14, C27, OP-22) — **the failure is that lessons-as-prose get re-violated; they must be graduated to assertions the build enforces.**

---

## Part 1 — The Diagnosis (why it keeps breaking)

**It is BOTH over-engineered AND under-structured, and the two reinforce each other.** ~290K LOC across 3,411 files for a job whose essence (trade SPY 0DTE on ~6 setups across 2 accounts) needs maybe 3,000. The complexity isn't in the trading — it's in 5 parallel meta-systems (research, validation, journaling, observability, autonomy), each justified alone, together 5× the surface area of the thing they serve.

**The 7 structural problems (ranked by error-risk):**

1. **The params ↔ prompt ↔ filters drift triangle (root cause).** The same rule values live in THREE incompatible forms with no enforced equality: `params.json` (JSON, "canonical," 181 keys / 29 prose essays), `heartbeat.md` (the LIVE engine — 751 lines of English an LLM re-derives every 3 min), and `filters.py` (the BACKTEST engine — 1,387 lines that load params.json **zero** times; every threshold hardcoded). "Does the backtest match what trades live?" is enforced only by a once-daily text pin-check + a manual `gamma-sync` skill. params.json line 62 literally documents the rot: a ratified gate marked "heartbeat.md activation pending."

2. **Coupling-by-string everywhere, no contracts.** 25+ `setup_name` literals must match action strings the heartbeat parses; the watcher→ledger link is schema-by-convention (needs a runtime "schema guard" for malformed rows); STATUS.md "Known broken" lists producer/consumer mismatches by name. Consumers silently see a subset (often zero) of what producers emit.

3. **State-file proliferation = ambiguous source of truth.** 5 files claim to be "the position"; 6 decisions ledgers; 144 `.lastgood` mirrors that can themselves go stale; a corrupted queue the daemon half-read (834 of 2,751 tasks).

4. **Append-only producers, no consolidation.** 520+ candidate files (mostly free-tier brainstorm noise), 63 stale CRITICALs in queue.md that nothing drains — the "accumulate, don't compound" failure OP-22 explicitly warns against, happening live.

5. **Dead/zombie code carried as live.** SNIPER (retired) still imported + ~30 scripts + a task; pinfade flag-disabled but in-tree; 4 stale prompt forks beside the live heartbeat; retired param overlays.

6. **Single points of failure the whole day rides on.** TradingView/CDP:9222 (one eye; a frozen-but-200 chart passes the watchdog); the shared Max rate-limit pool (no isolation — the dead `.heartbeat-api-key` code still claims protection that doesn't exist; **human discipline is the only guard**); the rolling CSV built at 14:00 ET (which blinded the entire watcher fleet all morning today); the EOD-flatten (the one task whose failure = real money via ITM assignment) depends on the same fragile LLM pool.

7. **No real-time health signal.** There is no `engine-health.json`. Degradation surfaces only at EOD or when J notices. `heartbeat_pulse_check` scores a total outage as PASS (an outage looks like a weekend). The staleness watchdog is itself orphaned and stale.

**The autonomy gap:** Gamma can already **execute, validate, report** — but cannot autonomously **decide-what-to-do-next** and **fan-out-then-ship**. The conductor logic exists (`wake-protocol.md`, a complete orchestrator spec) but is bound to a **dead cloud cron and never fires on this machine**. So when J opens a chat, J becomes the conductor — exactly his complaint.

**The Claude-efficiency gap:** all 10 agents are pinned to `model: sonnet`. **Zero Opus, zero Haiku routing.** Today: $31.82, 100% Sonnet, 58M cache-read tokens. The hardest cognitive work (strategy synthesis) runs on the WEAKEST model (free Nemotron in the Kitchen); rote read-and-tabulate work burns Sonnet. Under the new $200 plan the bottleneck was never budget — it's that **spend isn't tiered**.

---

## Part 2 — The Operating Model: "Gamma Drives" (the answer to "use Claude better")

**Today's pattern:** J opens a chat → J is the conductor → agents fan out on demand → J reviews in chat. One giant Sonnet session, J on the critical path for everything.

**The better pattern — four wires, not a rebuild:**

1. **Fire the conductor.** Register a `Gamma_Conductor` Windows task (after-hours cadence, e.g. hourly 16:00–08:00 ET — matching this machine's all-Task-Scheduler convention, replacing the dead cloud cron). It runs the EXISTING `wake-protocol.md` logic on **Opus**: read the prioritized queue → pick the top item → **fan out the right specialist personas IN PARALLEL** (Chef + validator-author + a backtest agent, via the Agent tool / a saved Workflow) → validate with backpressure (gym/pytest) → ship-if-gate-passes / else flag to J → update STATUS + queue + Discord. This turns 10 well-built personas into an actual firm. *The logic is already written — it just needs a trigger.*

2. **Route models by difficulty.** `model: haiku` for rote personas (scout/analyst/manager/coach/treasurer + the OP-29 authors — read/tabulate/file-write); `model: opus` for the conductor + Chef's strategy synthesis (genuinely hard reasoning); keep heartbeat on Sonnet (latency + judgment). Cache the CLAUDE.md/params prefix (90% discount on re-reads). Net cost ≈ flat, capability up sharply. On a Max plan the scarce resource is **rate-limit headroom**, so the conductor MUST be after-hours only (L54 — never starve the heartbeat) and fail-open (the OP-32 scar — never lock J out).

3. **Discord = the async approve/revoke bus.** The two-way responder is BUILT but disabled (`discord-responder.py`, `Gamma_DiscordResponder` "never enabled"). Enable it (Haiku, after-hours-gated). Protocol: Gamma pings a decision in SOUL voice — *"Cooked a winner: OOS +$840, WF 1.4, real-fills +, anchor-clean, scorecard filed. Ship? 👍/👎"* — J reacts from his phone; 👍 ships, 👎 shelves, silence-after-timeout = hold. **J becomes APPROVER, not driver.** Wire the auto-ship path so validated wins ship on Gamma's authority with J holding only REVOKE (the doctrine OP-22 already states but never plumbed — kitchen auto-promote dead-ends at a J-gated `_LEADERBOARD-pending.md`).

4. **Use Workflows for structured fan-out.** The nightly research/audit/fix loop should be a **saved, rerunnable Workflow** (self-caps at 16 concurrent / 1000 total agents, adversarial cross-review built in) — not hand-rolled chat orchestration. Anthropic's own `/deep-research` workflow is the template (votes on each claim, filters out what doesn't survive cross-checking).

**Net:** J's chat sessions become STEERING (set direction, ratify big calls) instead of OPERATING (fixing bugs one at a time). That is the whole ask.

**Architecture discipline from Anthropic (keep this line bright):** keep the **trade-execution path a deterministic WORKFLOW** (mechanical rules, single-threaded — "most coding is high-dependency → single agent"); make only the **R&D/research layer AGENTIC** (model-driven flexibility where it pays). Don't run the live trade loop as a fan-out; don't run research as a rigid script.

---

## Part 3 — The Technical North Star (the answer to "stop the errors")

The meta-fix, applied everywhere: **graduate prose/convention into code assertions at boundaries.** Specifics, leverage-ranked:

1. **Contracts at every state-file read (Pydantic / JSON Schema).** One model per state file, in one place, imported by BOTH producer and consumer. `ScoutOutput.model_validate(...)` instead of `json.load(...)`. The moment a producer drops a field a consumer needs, the consumer throws a typed error AT READ TIME instead of silently seeing `None`. *This single change kills the entire producer/consumer-silent-break class — the exact bug we've hand-fixed for three nights.* (Source: Fowler consumer-driven contracts; "parse don't validate"; Pydantic boundary validation.)

2. **A registry that makes orphaning impossible.** `@register_watcher` decorator → module-level `WATCHER_REGISTRY`; the heartbeat iterates the registry (no separate list to forget). Plus a **reconciliation test**: `set(files in watchers/) == set(registry) == set(heartbeat consumes)` — fails CI if any drift. *One test would have caught all 26 invisible watchers on the first run.* Apply identically to the 88 validators and ~34 tasks (reconcile `Get-ScheduledTask Gamma_*` vs `SCHEDULED-TASKS.md`). (Source: Python entry-points/registry pattern; "prevents silent orphaning.")

3. **A real-time health beacon (turn fail-green into fail-loud).** One `engine-health.json`, updated every tick + by a cheap 1-min Python watchdog, fusing: both-account last-fire age, TV chart freshness (CONTENT staleness, not just HTTP 200), both Alpaca auths, **watcher feed produced rows FOR TODAY** (distinguish "producer dark" from "no signal"), kill-switch state, rate-limit headroom. RED → Discord ping mid-day. *Would have caught today's all-day watcher blindness at 09:35 instead of at the post-mortem.* The fail-loud reference pattern already exists in-repo (`swarm_health.py`).

4. **A mandatory RiskGate every order passes through.** One `RiskGate.check(order) → Allow | Deny(reason)` the execution path CANNOT skip: daily-loss kill switch, per-trade cap, min-3-contracts, PDT, "already stopped out on this setup today," "is account flat as expected." **Fails CLOSED on any unreadable input; never locks out J (fails open for the human).** Today the kill switch lives in prose the heartbeat is *asked* to honor — which SEC 15c3-5 enforcement explicitly calls insufficient ("humans monitoring risk systems are not sufficient; order stops must be triggered automatically"). (Source: NautilusTrader RiskEngine; LEAN Risk module; SEC Market Access Rule.)

5. **Drift-detection test kills manual `gamma-sync`.** A pytest that loads `params.json` and asserts `filters.py` constants + prompt constants match — failing CI on divergence. Better: **generate** the derived copies from `params.json` (codegen) so they CAN'T diverge. The manual sync ritual IS the drift vector. (Source: config-drift literature; the v25 presence-guard we shipped this week is the first instance of this — generalize it.)

6. **Compile the decision core out of the prose (the deep fix).** The 21 filters + Gates A–I + sequence + sizing currently live as English the LLM re-derives every tick (non-deterministic; two ticks can disagree; gates ship in prose but mis-applied). Move deterministic gate evaluation into ONE Python module that BOTH the live tick and the backtest call. The LLM then does only judgment (chart read, trigger recognition) and calls the gate function for the verdict. This makes backtest=live parity STRUCTURAL, not a nightly hunt. (Source: NautilusTrader "same source code for backtest and live"; this finishes what `gamma-sync` started.)

7. **Detector → Insight registry (collapse the 28 watchers).** Each detector emits a uniform `Insight{direction, confidence, triggering_level, as_of_ts}` into a registry, merged by a composite (à la LEAN's CompositeAlphaModel). A detector that emits nothing does so VISIBLY. (Source: LEAN/Freqtrade/NautilusTrader plugin patterns.)

---

## Part 4 — The Trading Fixes (the answer to "make it actually trade 0DTE")

1. **Chart/underlying-level stops as DEFAULT; demote fixed-% premium stops to a catastrophe cap.** This is the single highest-leverage TRADING change, and it's triple-corroborated: the options literature (theta + vega + gamma corrupt a fixed premium stop on 0DTE — "a steady drip can trigger a stop on a trade that's just consolidating"), Gamma's OWN lessons (C2 "chart-stop only, premium-stop disabled"; C3 "SPY-price edge ≠ option edge / stop-misfire"), AND the `missed_week` backtest ("right direction, chopped by premium stops"). Yet v15 STILL uses fixed-% premium stops (−8%/−20%). *This is a Rule-9 doctrine change — needs J's nod — but the evidence is overwhelming.*

2. **Promotion rigor for the multiple-testing regime.** The Kitchen generates MANY candidates → an undeflated Sharpe/WR is "statistically meaningless" (Bailey & López de Prado). Add to the live gate: **Deflated Sharpe Ratio**, **Probability of Backtest Overfitting**, **Combinatorial Purged Cross-Validation** (not single-path walk-forward), **paper-vs-backtest divergence**, and a **system-restart stress test** during the paper window. (Caveat: the 7-trade J-anchor set is a known statistical-power ceiling — CPCV won't fix that; treat anchors as exceptional one-offs per C24.)

3. **Broker-as-source-of-truth reconciliation at the top of every tick** + `client_order_id` idempotency + broker-side OCO brackets (survive a process crash). Solves "is my position what I think it is" without a human watching. (Source: NautilusTrader live reconciliation.)

---

## Part 5 — The Phased Roadmap (what to do, in order)

**Phase 0 — Make failures loud + safe (reliability foundation). Start here.**
- (0a) **Engine health beacon** → Discord. *Additive, low-risk, makes every future bug visible.*
- (0b) **Contract + registry + drift tests** (Pydantic at reads; watcher/validator/task reconciliation; gamma-sync→failing test). *Additive tests; structurally ends the silent-drift class.*
- (0c) **Mandatory RiskGate** (fails closed, never locks J out). *Touches execution — needs care + J awareness.*

**Phase 1 — Make Gamma drive (autonomy).**
- (1a) **Fire `Gamma_Conductor`** (after-hours, Opus, fans out personas, drains one owned queue).
- (1b) **Model routing** (Haiku rote / Opus reason / Sonnet heartbeat) + prefix caching.
- (1c) **Discord approve/revoke bus** (enable the built responder; structured 👍/👎).

**Phase 2 — Make the engine trade well (the product).**
- (2a) **Chart-stops default** (Rule-9 — J ratifies).
- (2b) **Detector→Insight registry** + one shared decision library (backtest=live parity).
- (2c) **Promotion rigor** (DSR/PBO/CPCV/paper-divergence).

**Phase 3 — Reduce surface area (sustainability).**
- (3a) **Aggressive deletion** of what the new tests prove nothing consumes (SNIPER, pinfade, 4 prompt forks, 520-candidate pile, dead tasks); archive dated one-shot docs; collapse the 5 position files.

**Sequencing logic:** Phase 0 makes the rest SAFE to do autonomously (you can't let a conductor auto-ship until failures are loud and contracts are enforced). Phase 1 makes Gamma the driver. Phase 2 is the actual money. Phase 3 keeps it maintainable so it doesn't regrow the sprawl.

---

## Part 6 — External Inspiration (validated, credited)

**Claude / multi-agent (highest trust — Anthropic official):**
- [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) — the 5 patterns; workflow-vs-agent; "add agents only when simpler solutions fall short."
- [Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) — orchestrator-worker; evals/tracing/checkpoints; when multi-agent is NOT worth it ("most coding is high-dependency").
- [Claude Code Workflows](https://code.claude.com/docs/en/workflows) / [Subagents SDK](https://code.claude.com/docs/en/agent-sdk/subagents) / [Agent Teams](https://code.claude.com/docs/en/agent-teams) — the orchestration primitives + per-subagent `model` routing + adversarial-review gates.
- Ralph-loop autonomy pattern (Huntley/Cherny) — fresh context per fire, one bounded task, external memory, backpressure; **"drift has no auto-detection"** is the key warning.
- Repos (stars/credibility flagged): [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) (22k★, per-task model routing — direct analog to our personas); [ruvnet/claude-flow](https://github.com/ruvnet/claude-flow) (60k★ — mine for ideas, broad/marketing-heavy, don't adopt wholesale).

**Trading architecture (production OSS + regulatory + peer-reviewed):**
- [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) (~24k★, active) — backtest=live by construction; RiskEngine every order passes through; broker-as-truth reconciliation. **The single best architectural model for us.**
- [QuantConnect LEAN](https://github.com/QuantConnect/Lean) (16k★+) — the 5-stage decoupled pipeline (Alpha→Portfolio→**Risk**→Execution); CompositeAlphaModel (the watcher-registry pattern).
- [Freqtrade](https://www.freqtrade.io/en/stable/strategy-customization/) (~40k★) — the `IStrategy` plugin/registry contract.
- SEC Rule 15c3-5 (Market Access Rule) — automated risk controls are mandatory; human monitoring is "not sufficient."
- Bailey & López de Prado — [Deflated Sharpe](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551), [Prob. of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253) — the rigor for our multiple-testing regime.
- CBOE 0DTE research + options-stop literature — chart-stops over premium-stops on 0DTE.

**Complexity-taming (recognized engineering authorities):**
- [Fowler — Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html); Pact; "parse don't validate"; Confluent schema-evolution — the contract layer.
- [Out of the Tar Pit](https://curtclifton.net/papers/MoseleyMarks06a.pdf) (essential vs accidental complexity); Ousterhout "deep modules" (a real tension with our "many small files" rule — flagged); [Addy Osmani — LLM coding workflow 2026](https://addyosmani.com/blog/ai-coding-workflow/) (tests as the rails that keep an LLM-extended codebase coherent).

---

## The one-sentence north star

**Stop describing invariants in prose and start enforcing them in code at every boundary — then let Gamma, not J, hold the plan.** Everything else (the conductor, model routing, Discord, chart-stops, the registry) is downstream of that single discipline, and every credible external source agrees.

*Full audit reports (6 agents) are in this session's transcript. Key evidence files: `automation/state/params.json:62`, `automation/prompts/heartbeat.md`, `backtest/lib/filters.py`, `backtest/lib/watchers/runner.py`, `automation/overnight/wake-protocol.md`, `automation/state/SCHEDULED-TASKS.md`, `automation/state/spend-2026-06-18.json`, `setup/scripts/discord-responder.py`.*
