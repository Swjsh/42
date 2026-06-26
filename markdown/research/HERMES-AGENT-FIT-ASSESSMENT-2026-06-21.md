# Hermes Agent — Fit / Cost / Migration Assessment for Project Gamma

> **Date:** 2026-06-21 · **Trigger:** J — "check this out [hermes-agent.nousresearch.com], we should turn Gamma into this."
> **Method:** Sparse clone of `NousResearch/hermes-agent` @ HEAD (2026-06-22 push) + 5 parallel read-only subsystem deep-dives (runtime/cost, memory/learning, cron/deploy, gateway, tools/MCP/safety). All claims below cite real files in the repo.
> **Verdict (one line):** **Do NOT re-platform Gamma onto Hermes.** Gamma is already a domain-specialized instance of the same architecture; Hermes is the generic substrate. Mine it for 3-4 specific parts; keep the Claude Code runtime and the trading IP.

---

## 0. What Hermes Agent actually is (grounded)

`NousResearch/hermes-agent` — MIT, **199K stars**, ~46 MB of Python (+7.5 MB TS for web/TUI), created 2025-07-22, pushed daily. A genuinely production-grade, general-purpose autonomous-agent OS. Not vaporware. Concretely it ships:

- **9+ inference providers** behind a `ProviderProfile` registry (`providers/base.py`) — Anthropic, OpenAI, OpenRouter, Nous Portal, Gemini, Bedrock, DeepSeek, Qwen, Kimi, Ollama, custom.
- **28 real messaging adapters** (`gateway/platforms/`, `plugins/platforms/`) — Discord, Telegram, Slack, WhatsApp (Cloud + Web), Signal, SMS/Twilio, Email, Matrix, Teams, Feishu, Line, IRC, … all real integrations, no stubs.
- **60+ built-in tools** in composable "toolsets" (`toolsets.py`), full **MCP client** (stdio/HTTP/SSE, `tools/mcp_tool.py`) and an **MCP server** mode (`mcp_serve.py`).
- **Isolated subagents** (`tools/delegate_tool.py`) with restricted toolsets, parallel + async-background.
- **Closed learning loop** — SQLite+FTS5 memory (`hermes_state.py`, schema v16), a **curator** (`agent/curator.py`) and per-turn **background_review** (`agent/background_review.py`) that auto-creates/patches skills.
- **Natural-language cron** (`cron/scheduler.py`) + **6 execution backends** (local/docker/ssh/singularity/modal/daytona) + optional Nous-hosted **Chronos** scale-to-zero scheduler.

### The realization that frames everything

**Gamma already IS a domain-specialized Hermes.** You independently built the same architecture and bent it around 0DTE trading:

| Hermes subsystem | Gamma's hand-rolled equivalent | Who's ahead |
|---|---|---|
| `ProviderProfile` multi-model registry | Free-tier model ladder (Nemotron→DeepSeek→MiniMax) + Claude main loop | Hermes (breadth) |
| 28-platform gateway | Discord presence layer + companion app | Hermes (breadth), Gamma (working today) |
| curator + background_review learning loop | conductor + kitchen + skill/validator/lesson-authors + Karpathy loops | **Gamma (domain depth)** |
| SQLite+FTS5 memory | `memory/` + MEMORY.md + LESSONS-LEARNED | Even |
| NL cron + 6 backends | 35 Windows scheduled tasks | Hermes (portability), Gamma (works now) |
| delegate_task subagents | the agent fleet (pilot/chef/analyst/treasurer…) | Even |
| MCP client | Alpaca + TradingView MCP + 28 watchers | Gamma (depth), Hermes (cleaner) |

Your **edge** — the 10 rules, `risk_gate`, `daily_loss_guard.py`, the real-fills simulator, J-edge scoring, chart-stops — is **none of this machinery**. It is IP that rides *on top of* whatever agent runtime you pick. Re-platforming touches the plumbing and leaves the alpha untouched — which is exactly why it's all cost and no gain.

---

## 1. The decision: three independent killers for wholesale re-platform

### KILLER 1 — Cost: you lose Max-plan economics, and the workaround is fragile + Windows-incompatible

Hermes has **no Anthropic subscription billing**. `agent/anthropic_adapter.py:build_anthropic_client()` accepts OAuth tokens (incl. Claude Code creds at `~/.claude/.credentials.json` via the `claude_code` credential source in `agent/credential_pool.py`) but routes them **as Bearer auth to the metered public Anthropic API** — billed per-token, *not* drawn from the Max pool. Nous says so in their own marketing (`hermes-already-has-routines.md`: *"Cost: your API key, your rates"*, explicitly contrasted against the Claude subscription).

- **Budget enforcement: none.** `agent/account_usage.py` only parses Nous's `x-nous-credits-*` headers; Anthropic spend is estimate-only (`agent/usage_pricing.py`). The only "limit" is `agent/iteration_budget.py` (iteration count, not dollars). Gamma's OP-3 ($100/mo cap) and the $3/day kitchen cap would have to be re-implemented externally.
- **The "use your Max sub" workaround exists but is a trap.** Community repo `kristianvast/hermes-claude-auth` monkey-patches `build_anthropic_kwargs` to pass Anthropic's server-side OAuth validation (added 2026-04-04). It is: a **third-party OAuth bypass** (ToS-grey), **Linux/macOS only** (Gamma runs on Windows), and a **9-layer spoof** (billing-header signature, system-prompt relocation, Stainless SDK header spoofing, tool-name namespacing…) that breaks whenever either side changes an interface. Betting the firm's 24/7 heartbeat on a cat-and-mouse patch is precisely the **06-17 credit-cliff scar** (dedicated API key went dark mid-FOMC) in a new costume.

**Net:** either run the heartbeat on metered tokens (blows the $100/mo plan) or depend on a fragile, unsupported, Windows-incompatible bypass. Both are worse than today.

### KILLER 2 — Safety regression: Hermes can't gate `place_option_order`

Hermes's safety floor is **shell-command-scoped**, not tool-scoped (`tools/approval.py`: 12 hardline blocks like `rm -rf /` + 47 dangerous patterns + optional smart-LLM review). **There is no per-MCP-tool approval.** A `place_option_order` call to the Alpaca MCP server **does not pass through any gate** (confirmed: MCP tool results never hit the dangerous-command path). There is no built-in "flat-verified before entry," no agent-level kill-switch, no per-trade cap.

By the deep-dive's own comparison, **Claude Code *does* support per-tool approval** — the substrate you'd be leaving is *stronger* for this exact need. Re-platforming means re-coding Gamma's entire safety spine (10 rules, `risk_gate`, `daily_loss_guard.py`, kill switches, `connectivity-gate`) as custom MCP-handler wrappers on a runtime that gives you less help than the one you have. That is moving the crown jewels onto a weaker mount.

### KILLER 3 — The headline host-resilience win doesn't actually apply to Gamma

The genuine attraction (get off the single Windows rig) is **bottlenecked by TradingView, which Hermes cannot move.** Hermes cleanly separates scheduling from execution (6 backends; Modal/Daytona are serverless), so you *could* run the agent loop off-laptop. **But:**

- Gamma's real single point of failure is **TradingView Desktop (MSIX) + CDP port 9222** — a GUI app pinned to a real Windows machine. The Alpaca/TV MCP servers and the `setup/launch_tv_debug.ps1` hack live there too. Moving the *agent loop* to Modal/Daytona leaves the *chart feed* on the rig. Hermes offers nothing here.
- The serverless backends' value prop is **"hibernate when idle, cost nearly nothing"** — irrelevant to a heartbeat that must be *awake every 3 min for 6.5 continuous hours*. There's no idle to hibernate during the session.
- True scale-to-zero + sub-minute + multi-region needs **Chronos = Nous-hosted infrastructure** — swapping a Windows-rig dependency for a Nous-cloud dependency, against OP-25's "J holds the off-switch" and OP-3's cost gate.
- On Windows specifically, Hermes cron has **no native Task Scheduler integration** (`cron/scheduler.py` is a 60s in-process ticker; the Windows story is "wrap it in Docker, or use Task Scheduler" — i.e. what Gamma already does). So Hermes's scheduler does not beat Windows Task Scheduler *on Windows*.

**Plus the opportunity cost:** re-platforming = rewriting the whole harness (agents, skills, 35 scheduled tasks, MCP wiring, dashboards) for **zero trading-edge gain**. Textbook foot-gun.

---

## 2. Where Hermes genuinely beats Gamma (the parts worth stealing)

Re-platforming is wrong, but Hermes is a high-quality parts bin. Ranked by value/effort:

### ① Port the `background_review` *idea* — inline skill self-improvement (HIGH value, LOW effort)
`agent/background_review.py` spawns a forked agent **after each turn** (restricted to `memory_*`/`skill_manage`) that detects "the user corrected my style/workflow/approach" and **auto-patches the relevant skill's SKILL.md** so the next session already knows. Gamma's learn loop is *batch* (lesson-author drains `_lesson-inbox/` on a fire). Hermes does it *inline, on the correction*. Worth porting the pattern into Gamma's learn loop: when J corrects Gamma in a session, queue an auto-patch as a new turn. **Cost caveat:** it's +1 aux LLM call/turn — gate it to after-hours / explicit-correction only (OP-3).

### ② Docker-wrap the headless engine for crash self-heal (MED value, LOW-MED effort)
Hermes's `docker-compose.yml` + s6-overlay supervision (`hermes_cli/container_boot.py`) is a clean template for **restart-on-crash** of the non-GUI parts of Gamma (kitchen_daemon, conductor, the Python backtest/engine services). You don't need Hermes for this — Hermes just *validates the pattern*. TradingView stays pinned to the rig regardless, but the engine/kitchen/conductor self-healing improves. Aligns with the existing self-healing mandate (OP-25, `Repair-StateFiles`).

### ③ Adopt the curator's archive state-machine for OP-22 retention caps (MED value, LOW effort)
`agent/curator.py` runs a **deterministic, no-LLM** `ACTIVE → STALE (30d) → ARCHIVED (90d)` transition with pre-mutation tar.gz snapshots + `hermes curator rollback` (`agent/curator_backup.py`). Gamma already mandates retention caps + CONSOLIDATION on append-only producers (OP-22); this is a cleaner, safer encoding (snapshot-before-prune + rollback) to graduate those caps into code.

### ④ Phone-native messaging adapters — ONLY if J wants beyond Discord (MED value, MED effort)
`gateway/platforms/base.py` is a clean `BasePlatformAdapter` (4 abstract methods; ~200 lines for a minimal adapter). If J wants Signal/WhatsApp/Telegram/SMS reach, **extract the specific adapter** rather than rebuild a bridge. Caveats: sessions are **per-chat, not unified per-user across surfaces** (only WhatsApp identity normalization exists — `gateway/whatsapp_identity.py`), and the full `GatewayRunner` is tightly coupled to `AIAgent` (~7K lines), so adopt *individual adapters*, not the whole gateway. Gamma's Discord bridge already works, so this is additive, not a replacement.

---

## 3. What NOT to touch

- **Honcho dialectic user-modeling** (`plugins/memory/honcho/`) — a **paid external cloud service** (`api.honcho.dev`, +LLM calls per dialectic pass). Violates OP-3; adds an outage dependency. Skip.
- **Chronos managed cron** (`plugins/cron/chronos/`) — Nous-hosted infra lock-in; against "J holds the off-switch." Skip.
- **The `hermes-claude-auth` OAuth bypass** — fragile, ToS-grey, Linux/macOS-only. Skip (see Killer 1).
- **Wholesale gateway adoption** — `GatewayRunner`↔`AIAgent` coupling means "just the gateway" really means "all of Hermes." Skip; extract adapters only.

---

## 4. Recommendation & next step

**Keep Gamma on Claude Code.** Treat Hermes as (a) external validation that the orchestrator-worker + closed-learning-loop architecture is correct (it independently converged, at 199K-star scale), and (b) a parts bin for the four items above.

Default next action if J wants movement: **ship ① (inline skill self-improvement)** — it's the highest value-per-token, needs no new infra, no new cost surface beyond a gated aux call, and directly compounds the engine (OP-22). ②/③ are clean after-hours infra wins. ④ waits on an explicit "I want Gamma on my phone via <channel>."

If J's underlying want was actually **host resilience** (the real risk Hermes exposed), that's a *separate* spec — and the binding constraint is decoupling the TradingView chart read from the single rig (headless TV / a hosted data feed), which Hermes does not solve. Worth its own assessment if prioritized.

---

## Appendix — evidence map (file : finding)

| Claim | Evidence |
|---|---|
| OAuth → metered public API, no subscription draw | `agent/anthropic_adapter.py:build_anthropic_client()`, `_is_oauth_token()`; `agent/credential_pool.py` (`claude_code` source) |
| No dollar budget enforcement | `agent/account_usage.py` (Nous-only), `agent/usage_pricing.py` (estimate), `agent/iteration_budget.py` (iters only) |
| Max-plan bypass is 3rd-party/fragile/Linux-mac-only | `kristianvast/hermes-claude-auth` README (9 spoof layers; "Linux and macOS"; monkey-patches `build_anthropic_kwargs`) |
| No per-MCP-tool approval; shell-scoped gate | `tools/approval.py` (hardline + 47 patterns); MCP results bypass `detect_dangerous_command` |
| Cron = 60s in-process ticker, no native Windows scheduler | `cron/scheduler_provider.py:InProcessCronScheduler.start()`; `cron/jobs.py:TICKER_INTERVAL_SECONDS=60`; `docker-compose.windows.yml` |
| 6 backends; Modal/Daytona serverless; Chronos = Nous infra | `tools/environments/{local,docker,ssh,singularity,modal,daytona}.py`; `plugins/cron/chronos/`, `docs/chronos-managed-cron-contract.md` |
| Inline skill self-improvement | `agent/background_review.py` (per-turn forked review; `skill_manage` patch) |
| Curator archive state-machine + rollback | `agent/curator.py:apply_automatic_transitions()`; `agent/curator_backup.py:snapshot_skills()/rollback()` |
| 28 real platform adapters, clean ABC, per-chat sessions | `gateway/platforms/base.py:BasePlatformAdapter`; `gateway/session.py:SessionSource`; `gateway/whatsapp_identity.py` |
| Full MCP client + server | `tools/mcp_tool.py` (stdio/HTTP/SSE); `mcp_serve.py` (11 conversation tools) |
| Honcho is paid external cloud | `plugins/memory/honcho/README.md` (`api.honcho.dev`, `honcho-ai` dep) |
| Nous's own "your API key, your rates" framing | `hermes-already-has-routines.md` comparison table |
