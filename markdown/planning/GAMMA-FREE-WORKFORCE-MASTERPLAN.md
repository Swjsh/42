# Gamma Free-Workforce Masterplan — CEO / Manager / Employees

**Date:** 2026-06-24 (ultracode planning fire)
**Status:** CANONICAL PLAN — the whole-project map for moving recurring work off paid Claude onto free models.
**Built on:** a 7-agent codebase+web mapping (data routes, task inventory, org design, specialist benchmark, external-AI, cost model) + the live lane pool ([`swarm_client.py`](../../setup/scripts/swarm_client.py), [`model-roster.json`](../../automation/state/model-roster.json), [`lane-bench.json`](../../automation/state/lane-bench.json)).
**Companion:** [`FREE-AGENT-PLAN-B-KITCHEN.md`](FREE-AGENT-PLAN-B-KITCHEN.md) (the lane-pool build + super-free throughput engine).

> **One-line thesis:** the free workforce is **~90% built, not built** — the remaining work is *wiring* existing primitives, not new code. Move recurring labor (kitchen seed/triage, EOD/premarket workers, macro foraging, conductor recon, DRAFT authoring) onto free **Employees** + the local Ollama **Manager**; reserve **Claude (CEO)** for ratification, doctrine, order placement, and the SHIP/REVOKE call. Projected: **~55–70% of non-trading token volume** and **~35–50% of notional cost** moves to **$0** — and the biggest win is a *safety* win (stop opus recon from starving the heartbeat on the shared Max pool).

---

## 1. The org — three tiers, mapped 1:1 onto what already exists

| Tier | Who | Is | Does | Cost |
|---|---|---|---|---|
| **CEO** | **Claude (opus)** | `automation/prompts/conductor.md` + `/gamma-drive` | Hard design, "is this the highest-leverage thing" judgment, the **SHIP/REVOKE** call, and the **only** tier allowed to touch the `LIVE_DOCTRINE_DENYLIST` (CLAUDE.md, params*.json, heartbeat*.md, filters.py, orders) — and even then only as a DRAFT + `apply_ops` proposal. Invoked **sparingly**. | $200/mo Max (shared pool) |
| **Manager** | **local Ollama `qwen3:14b`** (RTX 5080) | the brain of `kitchen_daemon` | The 24/7 loop: polls `cook-queue.jsonl`, does its own cheap triage/dedup/routing locally, and **dispatches** specialist labor to Employees by role. Never-dark (no quota/ToS/rate-limit, fully private). ~30s/JSON — fine for a background loop, too slow for high-volume per-item work (which is why it *dispatches* that). | **$0** |
| **Employees** | **free cloud lanes by ROLE** | `swarm_client.call_role(role, prompt)` | Specialist labor. Resolve role → ordered lanes → skip 429-cooled → cross-provider failover → terminate in the local floor; privacy gate drops train-on-input lanes for sensitive roles; JSON validate-or-repair-once. **7 roles built:** coordinator, strategist, coder, validator, critic, forager, chef. | **$0** |

**The roster IS the org chart.** [`model-roster.json`](../../automation/state/model-roster.json) is the employee registry: to *hire an Employee* add a role; to *hire a provider* add it to `providers` with `key_file` + `trains_on_input`. No new env needed.

### Control flow — the Manager's cost-ordered cascade (per task)
1. **DO-IT-LOCALLY** (Manager, $0/unlimited/private) — cheap bookkeeping/triage/dedup/routing, OR `privacy=sensitive` with no live no-train cloud lane, OR all cloud lanes 429-cooled.
2. **DISPATCH-TO-EMPLOYEE** (`call_role`, $0, faster/stronger) — the task names a specialist role AND clears the privacy gate AND a live lane exists.
3. **ESCALATE-TO-CEO** (enqueue a signal — **never halt-and-wait**) — a guard trips.

### Escalation ladder (3 hops, each with a concrete trigger)
- **HOP 1 — Employee → Manager: automatic + silent (already built).** A lane 429s/errors/bad-JSON → `swarm_client` cools it + fails over → terminates at the local floor. The never-dark guarantee absorbs it; no escalation event.
- **HOP 2 — Manager → CEO: the real escalation.** The Manager *enqueues* a signal (`automation/overnight/queue.md` + a Discord outbox row with a reason code) — never blocks — when: (a) the task would touch a `LIVE_DOCTRINE_DENYLIST` surface; (b) an Employee role fails MAX_RETRY(3) across **all** its lanes incl. local (a true blocker); (c) a candidate clears cheap gates but needs the SHIP/REVOKE call; (d) a Critic approval-rate stays low after N rounds (a demote-the-model decision); (e) a genuine design fork the Manager can't resolve mechanically.
- **HOP 3 — conductor STAGE 4:** ship if the auto-ratify gate clears (OOS+ AND WF≥0.70 AND sub-window-stable AND anchor-no-regression AND A/B scorecard filed), else DRAFT + ping J.

### The ONE genuinely-new build
Verified unbuilt (0 cook-queue events carry a structured role key today): **add `role` + `tier` + `privacy` to `kitchen_daemon.enqueue_task()` and the `_load_queue` create-branch** (backward-compatible defaults `coordinator`/`manager`/`sensitive`); `_run_task` reads `task_state['role']` and calls `call_role(role,…)`; seeder/reviewer/conductor stamp the role on enqueue. Plus a thin Manager `decide(task)→{do_local|dispatch:<role>|escalate}` + an `escalate(reason)` helper. **Everything else is repointing existing calls.**

---

## 2. Specialist assignments (benchmark-driven — from [`lane-bench.json`](../../automation/state/lane-bench.json))

Floor = `ollama::qwen3:14b` for **every** role (never-dark).

| Role | Primary free lane | Why / gotcha |
|---|---|---|
| **coordinator** (classify/route) | `groq::llama-3.1-8b-instant` (1.8s, clean JSON) | canonical fast clean-JSON, no think-leak. Cap `max_tokens≤256`; don't route reasoning here. |
| **coder** (structured JSON) | **⚠ FIX: should be `gemini-flash-lite` or `groq-8b`** (clean JSON) | **MISMATCH FOUND:** roster currently primaries coder on `cerebras::gpt-oss-120b` which benched **json_ok=FALSE** (think-blocks break strict JSON). A coder that emits backtest-config JSON **must** lead with a json_ok=true lane. **Reorder.** |
| **strategist** (ideation, prose) | `openrouter::nemotron-super-120b` (2.9s, deepest) + `cerebras::zai-glm-4.7` assist | output is prose rationale → think-leak harmless. Raise `max_tokens≥1500` so zai-glm's answer survives its think-block (it benched empty at 600 — *budget artifact, not a dead lane*). |
| **critic** (adversarial) | 2-family panel: `nemotron-super` + `cerebras::zai-glm-4.7` | diversity > redundancy; zai-glm's think-block IS the product here. Post-process the verdict with the `</think>` stripper, don't demand strict JSON. |
| **validator** (DT-agreement) | `openrouter::nemotron-super` (the 27/27-DT workhorse) | must emit clean `{action}` JSON for scoring. Shares OpenRouter's throttled free floor with the kitchen → frequent failover to local **by design**. Never add Cerebras (json_ok=false fails the scoring contract). |
| **forager** (data/strategy harvest) | `google_aistudio::gemini-flash-lite` (1.0s, 1M ctx) | only lane that swallows a full scraped page, on its **own** Google quota. `privacy=public_ok` so Gemini's train-on-input is acceptable — **public pages only, never state/keys/edge** (input-construction discipline). This is the role for the new FRED/macro feed. |
| **chef** (kitchen cook) ✅ LIVE | `groq::llama-3.3-70b-versatile` → `nemotron-super` → `groq::gpt-oss-120b` | big ctx (~31K-token prompts) + no-train; Cerebras 8K cap excludes it. **Already wired** in `kitchen_daemon._run_task`. |

**Cross-cutting gotchas:** (1) Only **two** remote lanes pass strict-JSON at ~1s: **`groq-8b` + `gemini-flash-lite`** — the backbone of every high-volume JSON job. (2) **Both Cerebras lanes** are sub-second strong reasoners but **json_ok=FALSE** → Cerebras = *prose-reasoning roles only*, never a strict-JSON contract. (3) Codify a JSON-safe default lane set `{groq-8b, gemini-flash-lite, nemotron-super}` before wiring any JSON role.

---

## 3. Data route map — four planes (verified topology)

**PLANE 1 — LIVE MARKET (paid, read+write):** TradingView MCP (SPY 5m/VIX/ribbon/Pine levels; SPOF, has Alpaca fallback) · Alpaca Safe (account/chain/fills/orders; flat-verify source of truth; `stock_bars` doubles as TV-stale redundancy) · Alpaca Bold (separate key, Heartbeat_Aggressive only). **KEEP all.**

**PLANE 2 — HISTORICAL/BACKTEST:** OPRA option-bar cache (~23,200 CSVs/67MB, the real-fills WR authority; **GAP:** lags the spot feed → OOS silently scores fewer days → *fix: daily incremental `fetch_option_data` backfill*) · Spot+VIX 5m CSVs (FREE yfinance; **GAP:** 34 overlapping dated files, no canonical pointer → *fix: one rolling canonical file + manifest*).

**PLANE 3 — JOURNAL/LEDGER (OP-11 flywheel, append-only):** `decisions.jsonl` (20+ consumers) → `trades.csv`/journal/mistakes → `analysis/recommendations` (358 A/B scorecards) → weekly. **GAPS:** unbounded ledgers (`watcher-observations.jsonl` hit 5.1MB → stalled the heartbeat 06-22; `cook-queue.jsonl` ~1.3MB) need *retention caps graduated to code assertions*; 358 flat scorecards need *archiving*.

**PLANE 4 — COMPUTE (the new free plane):** the lane pool + Ollama floor (**only non-test consumer today = the kitchen *cook* path**; seeder/reviewer still off-pool — the real wiring gap) · shadow-eval (Nemotron 27/27 DT=100%; graduating it flips the heartbeat off Claude — the single largest cost) · kitchen queue · spend telemetry (`spend-daily.jsonl`, `swarm-calls.jsonl` — the migration's measurement backbone).

**BIGGEST MISSING FEED:** macro-calendar is **hand-curated + weekly-WebFetch-refreshed**; `news.json` is **manually edited** (stale at 06-15). Documented single-point silent-fail (the 5/07 FOMC miss). **Fix:** wire a free **FRED API / scheduled WebFetch** as a *feed* (not a weekly prompt step), routed to the **forager** Employee (public_ok); retire hand-edited `news.json`.

---

## 4. External AI — Grok & Cursor (your question), answered

**Is Grok free, or do we need Cursor? → Grok is NOT genuinely free, and you do NOT need Cursor.**
- The only free **Grok** API path is xAI's **data-sharing program** (~$150/mo credits + $25 signup, credits expire 30 days) which **requires letting xAI train on your inputs** (`trains_on_input=true`) → forbidden by the roster's `privacy=sensitive` rule. Grok could only serve the `public_ok` forager — a slot already covered $0 by Gemini + Nemotron with no opt-in and no expiry. It's OpenAI-compatible (`api.x.ai/v1`) so it *fits* mechanically, but it **buys nothing**.
- **Cursor's** free Hobby tier *does* include a Grok model, but it's **editor-locked with no callable API** → it can't be a lane. So Cursor is the wrong tool, and you don't need it to reach Grok. **Skip both for the workforce.**

**Worth adding instead (API-first, OpenAI-compatible, no editor):**
- **Cloudflare Workers AI** — best net-new add. ~10k Neurons/day (resets 00:00 UTC), 20+ no-train open models. Drops in as a new provider lane → an independent failover bucket above the Ollama floor. Verify the no-train ToS clause before a sensitive role; smoke-test via `roster_liveness`.
- **GitHub Models** — uniquely gives the open-weight pool **frontier-class** models at $0 (GPT-4o/Claude-3.5/Llama/Phi via an Azure OpenAI-compatible endpoint), authed with the repo's existing `gh` token. Confirm June-2026 limits + input-retention; if unclear, scope to forager (public_ok) only.

**Dead ends (editor-bound, no scriptable free API — they *consume* inference, don't provide it):** Sourcegraph Cody (free tier ended 2025), Continue.dev (BYO-model), Zed AI (BYO-key), Windsurf (editor), Copilot-free (plugin). *Inverse note:* Continue.dev/Zed could optionally **front our Ollama+lane pool as your interactive editor copilot** ($0, reuses the pool) — human tooling, not workforce capacity.

**Already wired:** Mistral Experiment (~1B tok/mo free, train-on-input, correctly fenced to public_ok) captures the best high-volume train-on-input option, making Grok's expiring credits strictly redundant.

---

## 5. Cost model — where the money/pool goes, and what stays on Claude

**Current burn (verified `spend-daily.jsonl`; Max is flat $200/mo — the *real* constraint is the SHARED rate-limit pool starving the heartbeat):**
- **DOMINANT — opus sessions** (after-hours interactive + Gamma_Conductor + Gamma_Drive), driven by huge cache-read: **06-21 = $918 (8 sessions)**, 06-22 = $147 (5), 06-24 = $56 (2). Conductor ~$1.50/fire, drive ~$3–6/fire.
- **MID — Sonnet sub-agent pipeline:** EOD (~$1.50/day, 4 workers) + premarket Scout/Swarm (~$0.75/day) ≈ **$2.75/recurring-day**.
- **LOW — heartbeat** already Haiku + hash-skip ~$0.05/tick; kitchen minimax ~$0.

**Projected savings:** ~55–70% of non-trading **token volume** is free-movable, but only ~35–50% of **notional cost** (cost concentrates in opus cache-read). The levers, biggest first:
1. **P2 — local Manager runs conductor STAGE 0–3 recon, escalates only STAGE 4 to Claude.** The biggest opus cut **and** the highest-value move — it strips opus recon off the shared pool: a **heartbeat-starvation SAFETY win** more than a dollar win. On a $918 spike day, this is the lever.
2. **P1 — EOD + premarket workers → `call_role`:** ~$2.75/recurring-day notional.
3. **Seeder repoint** (`call_minimax` → `call_role('strategist')`): removes the last paid exposure (the $3/day MiniMax cap) → **$0 strict** (every role terminates in the unlimited local floor — the paid LAST_RESORT tier can be **deleted**).
4. **Shadow-eval graduation** (≥85% DT over ≥15 days) → flip the heartbeat to Nemotron → retires the single largest recurring Claude cost.

**What MUST stay on Claude (hard guardrails):** live trades (heartbeat ENTER + `place_option_order` + EodFlatten + risk_gate — free lanes shadow-only until graduated); ratification + edits to the `LIVE_DOCTRINE_DENYLIST` (propose-not-apply); hard architecture/doctrine reasoning + the SHIP/REVOKE call; MCP-bound probes (free lanes have no MCP).

**Measurement:** add a daily **claude-vs-free ratio** metric (read `spend-daily.jsonl` + `swarm-calls.jsonl`) so "work moved off Claude this week" is a surfaced **number**, and tag each migrated stage in SpendSummary.

---

## 6. Migration roadmap (impact × safety ordered)

| Phase | Moves | Impact | Risk |
|---|---|---|---|
| **P0 — Reliability soak + retire paid fallback** | Run all 7 roles through `call_role`/`call_role_json` under real 429s; pytest asserts never-dark + schema-pass + privacy-gate. Repoint kitchen **seeder** → `call_role('strategist')` + **reviewer** → `call_role('critic')`. **Delete the paid LAST_RESORT tier.** Reorder **coder** off the json_ok=false Cerebras lane. Add retention caps (rotate/archive) to the unbounded ledgers + graduate to a code assertion. | HIGH — proves the pool survives failover; removes the last paid exposure; closes the ledger-bloat foot-gun that already stalled the engine. | LOW — observer/infra, ships without ratification (OP-25). |
| **P1 — Wire Employee roles + task schema; EOD/premarket off Claude** | Add `role`/`tier`/`privacy` to `enqueue_task` + `_load_queue`; `_run_task` dispatches via `call_role(task.role)`. Repoint EOD workers (Summary/DeepDive/DailyReview/Analyst) + premarket Scout/Swarm/level-prose onto roles (keep ManagerVerify + rule-pin on Claude/python). Stand up the FRED/macro **forager** feed; retire `news.json`. Schedule the daily OPRA incremental backfill. | HIGH — ~$2.75/day; closes the biggest missing data route (the 5/07 FOMC scar) + the OPRA freshness gap. | LOW-MED — workers run on immutable inputs; ManagerVerify stays the Claude integrity check; forager is public_ok. |
| **P2 — Promote the Ollama Manager + dispatch/escalate shim** | Make qwen3:14b the brain of `kitchen_daemon`: `decide(task)→{do_local\|dispatch\|escalate}` + `escalate(reason)` (enqueue, never halt). Route conductor STAGE 0–3 recon to the local Manager; CEO only runs STAGE 4. Add an RTH-courtesy gate so a heavy local cook never contends with a heartbeat tick on the 5080. | **HIGHEST** — strips opus recon off the shared pool; protects the heartbeat on $147–$918 spike days. | MED — wall-clock test Manager-mode STAGE 0–3 first (qwen3:14b ~30s JSON may be too slow in a time-boxed fire; Groq/Cerebras may need to be recon-primary with local as fallback). |
| **P3 — Route DRAFT authoring to free lanes; Claude reviews the diff** | Move specialist DRAFT authoring (lesson/validator/chef/doc) + weekly-review narration + Treasurer params-DRAFT onto free lanes; Claude reviews only the final diff before the auto-ratify gate. Re-enable the Futures heartbeat at $0 on the pool. | MED — broadens the offload + re-enables a disabled product. | LOW-MED — every artifact passes gym/pytest/schema before ship; params DRAFT stays propose-only. |
| **P4 — Verify, ratchet, consolidate** | Add the daily claude-vs-free ratio metric + per-stage tagging. Optionally add Cloudflare Workers AI + GitHub Models (after liveness + ToS check). Consolidate the 34 overlapping CSVs to one canonical file; archive stale scorecards. | MED — makes the migration measurable; removes foot-guns; optionally adds frontier-class free capacity. | LOW — pure infra; rewire-and-verify on CSV relocation (C9). |

---

## 7. Guardrails (non-negotiable)

- **Live trades stay on Claude** — heartbeat ENTER + `place_option_order` + EodFlatten + risk_gate are CEO-only; free lanes shadow-only until shadow-eval graduates (≥85% DT over ≥15 diverse days). Never route an order to a free model.
- **Propose-not-apply for the `LIVE_DOCTRINE_DENYLIST`** — only the CEO touches CLAUDE.md/params*.json/heartbeat*.md/filters.py/orders, and only as a DRAFT + `apply_ops` proposal the AutoApply actuator applies post-approval.
- **Fail-open, always** — no guard/Manager loop/escalation may ever kill/block/starve J's interactive session, the dev server (port 3000), or a heartbeat task (OP-25/OP-32 scar). Escalation is *enqueue a signal*, never *halt-and-wait*. The local floor under every role IS the fail-open guarantee.
- **Privacy gate is structural** — `privacy=sensitive` roles can never resolve a train-on-input lane (`resolve_lanes` enforces it). The **forager** is the only `public_ok` role and must never be passed account state, keys, or edge logic.
- **Market-hours discipline** — no conductor/Manager fan-out and no heavy local cook during 09:30–15:55 ET (the heartbeat shares the Max pool AND the RTX 5080). The Manager loop needs an RTH-courtesy gate (Plan B SYS-6).
- **Retention caps are mandatory + graduated** — every append-only producer gets a cap that graduates to a code assertion (the 06-22 stall: a re-violated lesson MUST become a test).
- **Validate before ship** — engine-benefit changes ship only through the auto-ratify gate with gym/pytest GREEN; a red gym/test = NOT shipped, flag it.
- **New providers are gated** — Cloudflare/GitHub Models/any new lane require a `roster_liveness` probe + explicit no-train ToS confirmation before a sensitive role; ambiguous retention → scope to forager only. Grok's data-sharing credits are forbidden on sensitive roles.

---

## 8. Quick wins (do first — all $0 / free-pool or pure-python)

1. **Repoint kitchen seeder → `call_role('strategist')` + reviewer → `call_role('critic')`** — finishes the kitchen migration (cook path already on the pool) + removes the last paid ($3/day MiniMax) exposure. **Delete the LAST_RESORT_PAID tier.**
2. **Reorder the `coder` role** off `cerebras::gpt-oss-120b` (json_ok=FALSE) to a json_ok=true lane (gemini-flash-lite for 1M-ctx specs, or groq-8b) + add a graduated guard asserting coder output is valid JSON.
3. **Retention caps** (rotate/archive) on `watcher-observations.jsonl` + `cook-queue.jsonl` + `discord-outbox.jsonl`, graduated to a code assertion — prevents a repeat of the 06-22 watcher-bloat → heartbeat stall.
4. **Daily OPRA incremental backfill** (`fetch_option_data` to the spot last-day) — closes the silent real-fills OOS day gap.
5. **Add `role`+`tier`+`privacy` to `enqueue_task` + `_load_queue`** (backward-compatible defaults) — the single unbuilt primitive that unlocks the whole CEO→Manager→Employee dispatch.
6. **Stand up the FRED/macro forager feed** (public_ok) + retire the stale hand-edited `news.json` — closes the biggest missing data route at $0.
7. **Consolidate the 34 overlapping spy_5m/vix_5m CSVs** to one rolling canonical file + manifest pointer.

---

*Canonical plan. The workforce is wiring, not building. CEO judgment is the scarce resource — spend it on SHIP/REVOKE and hard design; delegate the rest to the Manager + Employees for $0.*
