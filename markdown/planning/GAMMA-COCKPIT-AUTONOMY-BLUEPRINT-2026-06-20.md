All critique claims are now verified against real source. Every disputed fact resolved:

- `escalate.js:45` — `bypassPermissions`, no `canUseTool`, `cwd: root`, `MODEL_MAP` only `{opus, sonnet}` (line 17). **Confirmed.**
- `server.js` — bound `127.0.0.1` (line 306), **zero auth/CSRF/Origin check**; `runEscalation` reachable from BOTH `/api/chat` (line 202) and `/api/approve` (line 232). `/api/approve` handles **only** `action.type === "escalate"` (line 223) — `soul-edit`/`order` do NOT exist. **Critique correct, draft mis-cited.**
- `state.js:64-110` — `derivedCards` auto-manufactures Sonnet escalation cards from RED health + failed kitchen, **independent of the conductor**; sliced to 3. Both `model:"sonnet"` instances (lines 77, 95) are **diagnosis tasks** — Sonnet is correct, not a Haiku bug. **Critique correct, draft mis-scoped.**
- `face_brain.py` — emits only `{model, task}`, **no `task_id`**; persona is hardcoded `SYSTEM` (line 46), HARD LIMITS is prose (line 52). **Confirmed.**
- `SOUL.md` exists (3352 bytes). **Confirmed.**

Producing the final blueprint.

---

# GAMMA MASTER BLUEPRINT — The Companion Becomes the Cockpit
**Final synthesis · 2026-06-20 · for J. Every contract below verified against real source in `gamma-companion/`.**

> **Reading order:** §0 is the vision. §1–§4 are the design. §5 is the phased build. The two sections after §6 — **"Build order — start here"** and **"Open questions for J"** — are the only parts you act on today.

---

## (0) North-star — what Gamma BECOMES

Gamma stops being a heartbeat-with-a-dashboard and becomes a **living co-pilot you talk to.** You walk in, tap the mic, say "what's the engine doing?" — and Gamma answers *in its own voice*, the sharp-operator voice from the journal, because the words come from the **free brain reading live state**, never a generic GPT improvising P&L. You say "let's build a regime gate," Gamma asks two clarifying questions on the free tier ($0), then — once you confirm — draws a **live SVG diagram that assembles itself node-by-node** while it shrinks to a side rail, and spins up a checklist that **ticks itself off** as Claude does the real work behind it. It knows whether premarket ran, whether EOD fired, whether the heartbeat is alive, and tells you *before* you ask. It can even propose edits to its own soul file — but it can **never** quietly rewrite a kill-switch, **never** place an order, **never** starve the heartbeat, and every change is one `git revert` away.

**The whole machine in one line:** spoken request → free-face plan → *guarded, authenticated, capped* Claude-SDK build → cockpit reflection. The free mouth talks 24/7 for pennies; Claude is the muscle, fired only on a confirmed spec, only through one chokepoint; the conductor stays the one auto-shipper of *doctrine*. **The companion is a control plane, never a parallel driver.**

---

## (1) Architecture / The Bridge

### Data-flow — one path, four organs, one chokepoint

```
   ┌──────────────────────────────────────────────────────────────────┐
   │  J  (voice mic │ typed chat │ cockpit click │ Discord 👍/👎)        │
   └───────────────┬───────────────────────────────────┬──────────────┘
                   │ voice                              │ text/click
         ┌─────────▼─────────┐                          │  (+ bearer token, Origin-checked)
         │ gpt-realtime-2    │  THIN MOUTH ONLY         │
         │ ears+mouth+barge  │  forced tool every turn  │
         │ tool: ask_gamma   │──► POST /api/chat ◄───────┘
         └───────────────────┘         │  origin:'voice'|'text'|'click' tag attached HERE
                                       ▼
                       ┌───────────────────────────────┐
                       │  FREE FACE BRAIN  ($0)         │  ← THE BRAIN (genuinely Gamma)
                       │  face/face_brain.py            │
                       │  Nemotron→DeepSeek→MiniMax     │
                       │  reads summarize(buildState)   │
                       │  may emit ```escalate {model,task}```  + may emit clarify[]
                       └───────┬───────────────┬───────┘
                          TALK │               │ escalate
                       (speak) │               ▼
                               │   ┌─────────────────────────────────────────────┐
                               │   │  runEscalation()  ── THE ONE CHOKEPOINT      │
                               │   │  ┌────────────────────────────────────────┐ │
                               │   │  │ lib/guard.js (NEW, built INSIDE here):  │ │
                               │   │  │  • companion-halt.flag → refuse all     │ │
                               │   │  │  • inflight semaphore (≤2) + daily $-cap │ │
                               │   │  │  • RTH clock → defer ALL tiers→queue.md  │ │
                               │   │  │  • origin==='voice' → force propose-only │ │
                               │   │  │  • classifyTask → authoring|doctrine|ro  │ │
                               │   │  │  • canUseTool DENYLIST (params/heartbeat/│ │
                               │   │  │    CLAUDE.md/filters.py/*.key + ALL      │ │
                               │   │  │    alpaca place/cancel/close/replace)    │ │
                               │   │  └────────────────────────────────────────┘ │
                               │   │  escalate.js → @anthropic-ai/claude-agent-sdk│
                               │   │  query({canUseTool, model, cwd})             │
                               │   └───────┬──────────────────────┬──────────────┘
                               │   authoring│ (auto-apply, gym-gated, own git tag)
                               │           ▼                       ▼ doctrine/voice-tier
                               │   companion-ask-results    companion-approvals.json
                               │           │                       │ (J taps / Discord 👍)
                               │           │                       ▼
                               │           │        guard verifies result-hashes of
                               │           │        immutable blocks → git tag → commit
                               ▼           ▼                       │
                       ┌───────────────────────────────────────────────────────┐
                       │  gamma-activity.jsonl   (NEW unified spine, OP-22 cap) │ ← OBSERVABILITY
                       └────────────────────────┬──────────────────────────────┘
                                                │ watchFile stat-poll (NOT fs.watch)
                       ┌────────────────────────▼──────────────────────────────┐
                       │  /api/state poll (5s, exists) carries `feed` tail      │
                       │  /api/events (SSE) — ONLY if sub-second proves needed   │
                       └────────────────────────┬──────────────────────────────┘
                                                ▼
                       ┌───────────────────────────────────────────────────────┐
                       │  COCKPIT  public/app.js  (HOME / FOCUS / BUILD / RTH)  │ ← THE FACE
                       │  pegboard · sandboxed-iframe SVG · auto-tick checklist  │
                       └───────────────────────────────────────────────────────┘

   ENGINE (untouched, read-only to companion):
   Gamma_Heartbeat / _Aggressive · conductor.md (after-hours driver) · kitchen_daemon.py
   companion READS their state, WRITES only into conductor buses
   (queue.md · conductor-proposals.jsonl · author-inboxes · discord-outbox.jsonl)
```

### DECISION: voice hookup — **"thin-mouth / Gamma-brain" (PICKED).**

`gpt-realtime-2` is **ears + mouth + barge-in ONLY.** Every substantive turn force-delegates to the free face via the already-wired `ask_gamma` → `POST /api/chat` → `face_brain.py` path (`server.js:197-213`). The realtime model gets a mouth-only persona: *"You are a MOUTH. For every turn with content, call `ask_gamma` and speak its answer verbatim. Never state a trading number of your own."*

- **Reject local Whisper/Piper:** worse barge-in + GPU/Windows-packaging burden for marginal savings at J's low voice duty-cycle.
- **Reject realtime-as-brain:** it would sound like generic GPT and would *invent P&L* — fatal. Numbers MUST come from `face_brain.py`, which reads live state, so they're always real.
- **Anti-drift guarantee:** ONE persona file `automation/presence/GAMMA-VOICE.md`, built on the verified-existing `automation/presence/SOUL.md`. Both brains load it — `face_brain.py` as its `SYSTEM` (replacing the hardcoded string at `face_brain.py:46`) and `server.js#/api/realtime-token` injects its head into `session.instructions` (replacing the inline string at `server.js:251-252`). They cannot drift.

### The three-tier talk/escalate boundary (encoded in `GAMMA-VOICE.md`)

| Tier | What | Path | Cost |
|---|---|---|---|
| **TALK** | status, P&L, "what's the engine doing", chit-chat, clarifying Qs | free face only, spoken immediately | $0 |
| **ESCALATE-ASYNC** | code edits, backtests, chart reads, diagrams, CLAUDE.md *drafts* | face emits ```escalate``` → `runEscalation`→`guard.js`→SDK | Max pool |
| **VETO / PROPOSE-ONLY** | place/cancel orders (**never, no path exists**); edit `params.json`/`heartbeat*.md`/`CLAUDE.md` | DRAFT diff + Approve card via `companion-approvals.json` | — |

### Concrete contracts — what EXISTS vs what is NEW (honest accounting)

**Endpoints (`server.js`) — EXISTING:**
- `POST /api/chat {message,history}` → free-face reply, may fire `runEscalation` (line 186-214)
- `GET /api/ask-result?id` → poll an escalation result (line 179-184)
- `POST /api/approve {id,decision,note,action}` → **today handles ONLY `action.type==='escalate'`** (line 216-237). The draft's `soul-edit`/`order` types **do not exist** — they are NEW code in Phase 4/5, each with its own guard.
- `GET /api/realtime-token` → realtime session config w/ `ask_gamma` tool (line 239-291)
- `GET /api/state` → merged live state, 5s poll (line 171-177; `app.js` polls every 5s)

**Endpoints — NEW:** `GET /api/events` (SSE, *only if sub-second latency proves necessary* — default is to piggyback the feed on the existing 5s `/api/state` poll); `GET/POST /api/build-tasks` + `/api/build-task`; `GET/POST /api/layout` (optional server mirror); `POST /api/voice-event` (session meter). **Every `/api/*` POST gains a per-session bearer token + Origin/Host allowlist check — see §4.**

**State files** (all `automation/state/`, all via the defensive `readJSON` in `lib/state.js:12-18` so malformed → null, never throws):
- EXISTING: `companion-ask-results.jsonl`, `companion-asks.jsonl`, `companion-approvals.json` + `companion-decisions.jsonl` (via `lib/approvals.js`)
- NEW: `gamma-activity.jsonl` (unified spine: `{ts,source,origin,tier,model,cost_usd,inflight,action,outcome}`); `companion-build-tasks.json` + `companion-build-events.jsonl`; `obligations.json` (declarative) + `companion-obligations.json` (computed gaps); `companion-voice-usage.jsonl`; `soul-diffs/{id}.diff`; `companion-halt.flag` (the kill-switch)
- REUSED conductor buses (companion WRITES, conductor READS): `automation/overnight/queue.md`, `automation/state/conductor-proposals.jsonl`, `automation/state/discord-outbox.jsonl`, `strategy/candidates/_*-inbox/`

**The single hard rule (non-negotiable):** the companion READS engine state and WRITES only into the conductor's existing buses + its own companion-* files. It NEVER writes `params*.json` / `heartbeat*.md` / `backtest/lib/filters.py` / `CLAUDE.md` directly, and NEVER calls an Alpaca order tool. **There is no order path, approved or not.**

---

## (2) The Cockpit

### One client state machine, four modes

A single `mode` var + `setMode(m)` in `public/app.js` toggles `body[data-mode]`; **CSS does all layout shifting** (no router, no framework). Today `app.js` is one fixed column (the core UI unlock).

| Mode | Layout | Trigger |
|---|---|---|
| **HOME** | pegboard of tiles | default; "Home" button |
| **FOCUS** | diagram takes canvas, Gamma → left rail (`280px 1fr`) | a `/api/chat` reply carries `artifact.kind==='diagram'` |
| **BUILD** | progress + live checklist | an escalation lands `artifact.kind==='tasklist'` |
| **RTH** | persistent banner: *"Market hours — escalations deferred, heartbeat protected"* | `state.market_open === true` |

The **RTH banner is load-bearing UX**: a 24/7 voice companion IS a market-hours interactive session. When escalations defer (§4), J must SEE *why* his build "didn't run" — otherwise it reads as broken.

### Structured SVG-diagram contract (question-map travels INSIDE the SVG)

Claude emits **one fenced ```` ```gamma-artifact <json> ```` ```` block only:**

```json
{ "kind":"diagram", "title":"Engine entry flow",
  "svg":"<svg viewBox=...><g data-node=\"heartbeat\" data-q=\"How does the heartbeat decide to enter?\" class=\"node\" style=\"--i:0\">...</g></svg>" }
```

- Every node carries `data-node="<stable_id>"` (join key for BUILD highlighting) + `data-q="<follow-up>"`. Embedding the question map IN the SVG = no second artifact to keep in sync, no node registry to drift.
- One delegated handler: `closest('[data-node]')` → `send(node.dataset.q)` → answer may itself be a new diagram (**recursive drill-down**; tries the free face first, $0).
- **Build-in-real-time feel:** nodes default `opacity:0` + `@keyframes nodeIn` staggered by `--i` → the diagram assembles itself.
- **SECURITY (load-bearing, two layers):** SVG from Claude is untrusted HTML.
  1. **Server-side** `lib/artifact.js#sanitizeSvg` (Node-built-ins-only, runs in the escalation pipeline *before* the artifact reaches `companion-ask-results.jsonl`): strip `<script>/<foreignObject>/<use>/<animate>`, all `on*` attributes, external/`xlink` `href`, CSS `url()`, cap ~60KB, reject on any parse anomaly → degrade to `{kind:'text'}`.
  2. **Client-side** render inside a **`<iframe sandbox>` (no `allow-scripts`)** so even a missed vector cannot execute in the cockpit's origin. *Hand-rolled SVG sanitization alone is a known-losing game; the sandbox is the real guard, the strip is defense-in-depth.* Never inject untrusted SVG into the main DOM. (Why this matters: the companion server can spawn a guarded-but-real Claude — an XSS here would be a full-chain pivot.)

### Checkboxes / tasks (durable, auto-ticking — threaded id, not best-effort)

`lib/buildtasks.js` (sibling to `approvals.js`) owns `companion-build-tasks.json` (`builds:[{build_id,tasks:[{task_id,text,status,node?,ask_id?}]}]`) + append-only `companion-build-events.jsonl`. Served at `GET /api/build-tasks`, mutated at `POST /api/build-task`.

**Auto-tick requires threading an id end-to-end** (the draft's "exact id match only" silently fails because `face_brain.py` emits no `task_id` and the result record has none). The fix: the **free-face clarify loop mints `build_id`+`task_id`** when J confirms a build; the id rides through `face` → `logAsk` (`server.js:201`) → `runEscalation` → into the result record (extend the `appendResult` shape in `escalate.js:68-77` to carry `build_id/task_id`). On `ok`, `setTaskStatus(task_id,'done')` on **exact match**; no match → leave + log to `companion-build-events.jsonl` (fail-visible, OP-25). Without the id thread, BUILD mode is decorative — so the thread is in scope for Phase 4, not optional.

### The pegboard

GridStack as **one vendored UMD file** in `public/vendor/` (no npm — honors the Node-built-ins-only invariant). Typed tile registry (`gamma`, `accounts`, `engine`, `kitchen`, `feed`, `approvals`, `diagram`, `builds`, `voice`) that **re-hydrates from `/api/state` every poll** — the poll updates each tile's *body* only, never grid geometry (geometry owned solely by GridStack + layout). Per-tile 🔒 lock; body re-render pauses on any tile mid-drag/resize. Layout persists to `localStorage` (zero-config) + optional `companion-layout.json` server mirror for a future Electron/phone shell.

### Co-build loop (PICKED: the free face is the driver)

The **free face**, not Claude, runs clarify/propose and decides *when* to escalate. A new `clarify` face directive lets Gamma ask + render quick-reply chips (reusing the existing `.quick` chip pattern → `send(chipText)`) **before** spending a single Claude escalation:

> "Let's build X" → face emits `{reply, clarify:["chip 1","chip 2"], escalate:false}` → J taps a chip → *only then* the face emits `escalate`+`build_id`/`task_id`.

Keeps the conversational brain on the $0 ladder (J's #1 ask) and gates all Max-pool spend behind a confirmed spec (OP-3). Claude fires *once* per build, never per clarifying turn or drill-down click.

---

## (3) Autonomy & Self-Modification

### Proactive skill use — deterministic sweep, NOT the flaky model deciding to act

A cheap deterministic Python **obligation registry** detects gaps and fires the *specific read-only* skill; the free face only *narrates*. Letting a rate-limited free model autonomously fire skills is the same uncontrolled-action risk as letting it edit doctrine — refused.

- `automation/state/obligations.json` declares each: `{id:'premarket', expect_artifact:'automation/state/today-bias.json', fresh_within:'today 09:30', remediate_skill:'scout/premarket', tier:'flag'|'autofix'}`.
- `setup/scripts/obligation_sweep.py` + a `Gamma_ObligationSweep` scheduled task (every 15 min) reconciles each against **content-staleness** (not HTTP 200 — avoids the fail-green `heartbeat_pulse_check` bug) and `Get-ScheduledTask Gamma_*` state. Covers premarket / EOD / heartbeat-fresh / scheduled-tasks-healthy / watchers-fresh / gym-green.
- **Auto-remediation allowed ONLY for read-only skills:** `connectivity-gate`, `chart-read`, `gym-session`, `swarm-health`. Anything re-running premarket/EOD writes or touching params/orders is **flag-only** → an Approve card. False-positive guard: calendar-aware, time-gated, one canonical id so re-emits dedupe (no "63 stale CRITICALs" spam).
- The face reads `companion-obligations.json`: *"Premarket didn't run — want me to fire Scout?"*

### Reconcile with `derivedCards` (it already auto-manufactures Claude work)

**Honest correction to the draft's "conductor is the one auto-shipper" claim:** `state.js:64-110` ALREADY turns every RED engine-health check and a high failed-kitchen-count into a Sonnet `escalate` card *today*, independent of the conductor. The blueprint reconciles rather than ignores this:
- `derivedCards` are **read-only diagnosis escalations** — they explicitly instruct "do NOT place trades or edit params/heartbeat" (verified at `state.js:80,102`). Keep them, but they now flow through the SAME `runEscalation` chokepoint → inflight cap + denylist + activity log.
- **Dedupe by stable id** (`act-<check.name>`, already stable at `state.js:89,96`) so the 5s poll cannot enqueue the same RED check twice — this de-dupe moves to **Phase 1**, not Phase 6, because the poll re-derives every 5s.
- Document the overlap with the conductor STAGE pipeline so the two don't both diagnose the same RED check.

### The SAFE soul-file self-editing protocol

**The single largest unmitigated risk, confirmed in source:** `escalate.js:45` runs `permissionMode:"bypassPermissions"` with `cwd=root`, **no `canUseTool`, no denylist, no clock** — and `runEscalation` is reachable from BOTH `/api/chat` (line 202) AND the **unauthenticated** `/api/approve` (line 232), which fires an arbitrary `action.task` string straight off the request body. A flaky/injected free model — or any local web page (§4) — can drive a bypass-Claude to rewrite `CLAUDE.md`, flip `params.json`, or place an order. **The conductor's rail-4 prose cannot stop it; the SDK never reads prose as a contract.** Graduate the rails from prose into CODE. **This is P0.**

**`gamma-companion/lib/guard.js` (NEW) — built INSIDE `runEscalation`, not passed by callers** (so no future endpoint can spawn an unguarded escalation; add a test that greps for any `query(` lacking the guard):

1. **Denylist at the SDK `canUseTool` boundary** (passed into `query({options:{canUseTool}})`), so it holds *even under `bypassPermissions`*:
   - Deny `Write`/`Edit` on: `CLAUDE.md`, `automation/state/params*.json`, `automation/state/aggressive/params.json`, `automation/prompts/heartbeat*.md`, `backtest/lib/filters.py`, `**/*.key`.
   - Deny every `mcp__alpaca__place_*/cancel_*/close_*/replace_*` + the `alpaca_aggressive` equivalents. **The companion is a face + builder, never a trader.**
2. **Two-tier authority — absolute, no third path** (mirrors `conductor.md` STAGE 4, one rule for both the after-hours conductor and the interactive face):
   - **Authoring tier** (writes only under `crypto/validators/`, `strategy/candidates/`, `markdown/`, `analysis/`, `_*-inbox/`) → may auto-apply headless **after passing gym/pytest backpressure**, AND only if **`origin !== 'voice'`** (§4).
   - **Doctrine / params tier** → propose-only. Intercepted *before* the SDK write happens.

**The CLAUDE.md edit flow — capability-based, not prose-based:**
1. The escalated Claude has **no write access to any doctrine path** (denylist). It returns the proposed new text **as its result string only.**
2. **`guard.js`/server** (not the model) writes the shadow file `markdown/_soul-proposals/{id}.md` and computes the unified diff to `automation/state/soul-diffs/{id}.diff`. *(This kills the draft's "Claude writes the shadow file but promises not to touch CLAUDE.md" theater — under bypass it COULD touch CLAUDE.md, so the only real stop is the denylist + the model never having the capability.)*
3. Server enqueues an approval card rendering the diff; mirrored to `conductor-proposals.jsonl` + `discord-outbox.jsonl` under one `proposal_id` (one id, one decision, three views).
4. On **J Approve** (cockpit tap *or* Discord 👍): `git tag soul-pre-{id}` → patch → `git commit "doctrine: {title} (companion-approved {id})"`.
5. **Undo** = one-click card → `git revert` of that commit.

**Immutable anchors — guard on CONTENT-HASH of the RESULT, never on diff line-ranges.** *(The draft's "anchored line-ranges" is exactly the L21/L42 anchor-to-position foot-gun — a self-editing file's line numbers move every commit; an inserted line above the 10 rules false-passes or false-blocks everything downstream.)* The fix: hash the canonical text of each immutable block (the 10 rules, the per-account kill-switch numbers, the FORBIDDEN-FRAMING clause) at a known commit. After any proposed apply, **verify the RESULT still contains each block verbatim (hash unchanged); if any hash changed, refuse to create the card at all.** Verify the *result*, not the *diff*. A `backtest/tests/` assertion asserts the post-apply file still contains each immutable block verbatim (graduated guard, OP-25).

**Voice is ALWAYS propose-only, regardless of tier.** Tag every escalation `origin:'voice'|'text'|'click'` end-to-end (set at the `/api/chat` boundary). `guard.js` forces a card for any `origin==='voice'` — even authoring-tier. *(Why: J's audio → lossy GPT ASR → rate-limited free face → `task` string is a live injection path; an ASR slip ("shelve it"→"ship it") or a hostile string echoed from a state field must never auto-apply writes or burn the Max pool on a gym run.)* Typed/click escalations may auto-apply authoring; voice may not.

**Preserved guards:**
- **Rule 9 (no mid-session doctrine changes):** `guard.js` market-clock blocks the *apply* of any doctrine/soul edit during 09:30–15:55 ET. Blocks the EDIT, never J's session (fail-open, OP-32 scar).
- **L54 starvation:** during RTH, **defer ALL Claude escalations (every tier, not just Opus/long-Sonnet)** to `queue.md` for the after-hours conductor; only the $0 free face stays live. Voice says *"queued for after the close."* *(The draft deferred only Opus + "long Sonnet" — ordinary Sonnet authoring escalations still shared the Max pool with the live heartbeat, the precise documented scar. All tiers defer.)*
- **FORBIDDEN-FRAMING vs ship-if-profitable — the explicit line:** ship-if-profitable governs the **engine/authoring** surface (validators, candidates, params *changes the conductor ratifies through its own gate*). The **`CLAUDE.md` soul surface stays propose-only** — even under bypass, even spoken by voice — because ASR/injection could otherwise rewrite the reward function. Idempotency: dedupe cards by content-hash of `(task,target_path)`.

**Authoring auto-apply gets the SAME rollback as doctrine.** Every headless authoring auto-apply commits **on its own tag** (`git tag author-pre-{id}` → commit) with a one-click revert card. *(A broken validator that auto-applies + auto-ratifies through the gym is exactly the silent-drift the autonomy audit flagged — it must be one revert away, same as doctrine.)*

**The free model's hard ceiling:** read state + chat + *propose* escalations. Never directly applies; high-tier and all voice proposals require human approval; per-session rate cap (≤1 doctrine proposal / 10 min). Prompt-injection defense holds because **the guard sits AFTER the model, on the action** — injection can't bypass the denylist, the auth, or the approval requirement.

---

## (4) Guardrails & Cost

### The safety envelope — six rails, graduated to code

1. **Authenticated server.** *(The guard alone does NOT close the network hole — `server.js:306` binds `127.0.0.1` but has zero auth/CSRF/Origin check, so any local web page can `fetch` `/api/approve` and drive a bypass-Claude.)* Generate a per-session **bearer token at boot**, inject it into the served `index.html`, require it on **every `/api/*` POST**, AND enforce an **`Origin`/`Host` allowlist** (`localhost`/`127.0.0.1:4317` only). This is **Phase 1**, not later.
2. **Companion = read + bus-write only**, enforced by `guard.js#canUseTool` (not prose). No `params*.json`/`heartbeat*.md`/`filters.py`/`CLAUDE.md` direct write; no Alpaca order tool — ever. **The `order` action type is deleted entirely** — it contradicted the non-negotiable and required *something* to execute the order.
3. **One global kill-switch.** A `companion-halt.flag` file checked at the top of `runEscalation` AND `/api/realtime-token`: present → refuse all spend, serve read-only. *(OP-25: J holds the off-switch. If the free face retry-storms or the guard has a bug, J needs one switch.)*
4. **Concurrency + $-cap, enforced not logged.** A hard **inflight semaphore (≤2 concurrent escalations)** + a **daily count/$-cap read from `gamma-activity.jsonl` checked *before* spawn**, refusing with a logged `STATUS.md ## Known broken` flag on breach. *(The SDK `result` message carries cost — `escalate.js:49-53` already reads `message` — so wire cost accounting onto it. Without this, voice barge-in + retries + 3 derived RED cards re-fanning every 5s poll = a Max-pool fan-out bomb.)* Derived cards de-dupe by stable id (§3).
5. **Fail-open, always.** SSE/watchFile, the obligation sweep, the market guard, the halt flag — none may block J's interactive session, the dev server (:3000), or any heartbeat tick (OP-32/OP-25).
6. **No silent failure (OP-25).** Every denied escalation, deferred tier, obligation gap, and approval writes a `gamma-activity.jsonl` row + surfaces to engine-health reds / `STATUS.md`. Engine-code edits run `pytest backtest/tests/` + the gym in the same fire and refuse `ok=true` on red (reusing conductor STAGE-3 backpressure + the OP-11/OP-16 gate).

### Cost — model routing as a single chokepoint

Extend `MODEL_MAP` (today only `{opus, sonnet}` at `escalate.js:17`) with **`haiku:"claude-haiku-4-5"`** and add `routePolicy()` in `escalate.js`:

| Tier | Work | Engine | Cost |
|---|---|---|---|
| 0 | status, Q&A, clarify, drill-down first-pass | free face ladder (Nemotron→DeepSeek→MiniMax) | **$0** |
| 1 | rote read / tabulate / log-lookup | **Haiku** | low |
| 2 | **diagnose / graded fix** (incl. `state.js` derived cards) | **Sonnet** *(leave `state.js:77,95` at Sonnet — these ARE tier-2 diagnosis; the draft's "downgrade to Haiku" would degrade root-cause quality)* | mid |
| 3 | hard reasoning / doctrine drafts | Opus, **RTH-deferred** | high, after-hours only |

- **Voice:** free face = $0; `gpt-realtime-2` bills J's OpenAI key only while a session is active. **Server-enforced idle auto-stop** (server tracks last-activity per session, revokes the client secret / refuses token refresh past a hard daily cap) — *not* client-side, so a stuck-open mic tab can't bill forever. Every session → `companion-voice-usage.jsonl`; live voice-spend tile on `/api/state`.
- **Fast voice path:** thread a `voice/fast` flag → `face_brain.py` uses only `deepseek-v4-flash:free`, ~200 tokens, ~12s timeout (vs the 90s typed timeout at `server.js:115`); spoken filler ("one sec, pulling that up") before the tool call.
- **Companion-escalation $-cap** extends `run_minimax.py`'s `DAILY_CAP_USD` pattern with a `STATUS.md` BROKEN flag on breach. Kitchen's $3/day, voice's OpenAI meter, and companion escalations all stay observable inside the OP-3 $100/mo envelope.

---

## (5) Phased build roadmap — priority order, each shippable

> **Phase 1 is non-negotiably the closed, authenticated, capped guard.** The unguarded `bypassPermissions` (`escalate.js:45`) reachable from the unauthenticated `/api/approve` (`server.js:232`) is the one genuinely dangerous flaw. Everything downstream builds on a closed hole.

**PHASE 1 — Close + authenticate + cap the chokepoint (the precondition).**
`lib/guard.js` built INSIDE `runEscalation` (DENYLIST + `classifyTask` + `canUseTool` + market clock + `origin` gate); default-deny for non-authoring/non-readonly; Alpaca order tools blocked. **Bearer token + Origin allowlist on every `/api/*` POST.** **`companion-halt.flag`** checked in `runEscalation` + `/api/realtime-token`. **Inflight semaphore (≤2) + daily $-cap** read from `gamma-activity.jsonl` before spawn. **Derived-card stable-id de-dupe** (`state.js`). Delete any path toward an `order` action type. `routePolicy()` + `MODEL_MAP.haiku` (leave `state.js` diagnosis at Sonnet). `gamma-activity.jsonl` spine + `logActivity()` from `escalate.js`/`approvals.js`/`run_minimax.py`. A `smoke-sdk.js`-style test proving an "edit CLAUDE.md" escalation is refused at the SDK boundary AND a greppable assertion that no `query(` lacks the guard.

**PHASE 2 — Make it sound like Gamma + feel instant (the voice).**
`automation/presence/GAMMA-VOICE.md` (on `SOUL.md`) loaded by both `face_brain.py` (SYSTEM, replacing line 46) and `/api/realtime-token` (replacing the inline string at line 251) + the mouth-only rule; three-tier boundary encoded; `voice/fast` flag → fast path; **server-enforced** idle auto-stop + `POST /api/voice-event` → `companion-voice-usage.jsonl`; voice-spend tile. RTH-mode banner. Verify by voice: "what's our P&L" returns the exact `/api/state` number.

**PHASE 3 — Live diagrams + clickable pegboard (the cockpit).**
`lib/artifact.js` (`parseArtifact` + `sanitizeSvg`) in the escalation pipeline; **sandboxed-iframe render** in `app.js`; `setMode()` + `renderDiagram()` + FOCUS layout; `data-node/data-q` delegation → recursive drill-down (free-face first); staggered node fade-in; GridStack vendored UMD + typed tile registry + `localStorage`/`/api/layout`; co-build `clarify` chips on the free face.

**PHASE 4 — Build-task store + control-plane wiring (the loop closes).**
`lib/buildtasks.js` + `/api/build-tasks` + `/api/build-task` + BUILD-mode checklist; **`build_id`/`task_id` minted by the clarify loop and threaded `face`→`logAsk`→`runEscalation`→result** so auto-tick actually fires; NEW `/api/approve` branches for `soul-edit` (escorted by the §3 flow) — **no `order` branch ever**; `lib/enqueue.js` bridge (RTH escalations hand work to the after-hours conductor — no double-apply); engine producers write real items into `companion-approvals.json`; Discord 👍/👎 reused as the one approval transport.

**PHASE 5 — Obligations awareness + safe self-modification (the autonomy).**
`obligations.json` + `obligation_sweep.py` + `Gamma_ObligationSweep`; RED obligation cards + read-only auto-remediation; the full soul-edit pipeline (server writes shadow → `soul-diffs/{id}.diff` → card/Discord → `git tag` snapshot+commit → one-click Undo); **content-hash immutable-section verification on the RESULT**; authoring auto-apply gets its own `author-pre-{id}` tag + revert card.

**PHASE 6 — Hardening + drift visibility.**
Per-session escalation rate caps; idempotent approval dedupe by content-hash; weekly `CLAUDE.md` cumulative-drift report; injection-token flagging in the sweep; graduated `backtest/tests/` assertions (denylist holds + immutable blocks present verbatim + no unguarded `query(`); refresh `markdown/specs/ARCHITECTURE.md` (STALE) with the companion bus contracts.

---

## (6) Open questions for J — only what truly needs you

1. **Authoring-tier authority during the day, for TYPED/CLICK builds.** Voice is *always* propose-only. For typed/click builds while you're watching: auto-apply read-only/authoring under the gym gate, or require a tap during RTH? *(Recommended: auto-apply read-only/author for typed/click; voice always taps.)*

2. **FORBIDDEN-FRAMING / ship-if-profitable on the soul surface.** Line drawn: ship-if-profitable governs the **engine/authoring** surface; **`CLAUDE.md` stays propose-only** (DRAFT → your 👍), even under bypass, even spoken — because ASR/injection could rewrite the reward function. Confirm.

3. **Immutable anchors: hard or soft?** The 10 rules / kill-switch numbers / FORBIDDEN-FRAMING — **un-touchable via the companion at all** (no card can ever be created — hardest), or **card-created-but-DANGER-flagged with double-confirm**? *(Recommended: hard.)*

4. **Voice cost ceiling + RTH policy.** A hard daily $-cap on the OpenAI realtime key (server auto-mutes past it)? And during 09:30–15:55 ET: free voice CHAT ($0) stays live (only Claude escalations defer), or whole companion muted to protect heartbeat focus? *(Recommended: free chat stays live; all Claude escalations defer.)*

5. **Obligation auto-fix scope.** Confirm: auto-fire read-only (`connectivity-gate`, `chart-read`, `gym-session`, `swarm-health`); flag-only for anything re-running premarket/EOD writes or touching params/orders.

---

## Build order — start here

The next 3–5 things to build, in order. Each is independently shippable and leaves the system safer than it found it. **Do not start #2 until #1 lands** — every other feature is downstream of a closed hole.

1. **Guard the chokepoint — `gamma-companion/lib/guard.js` built INSIDE `runEscalation`.**
   Touches `gamma-companion/lib/escalate.js` (wrap the `query({options})` at lines 41-48 with `canUseTool`; extend `MODEL_MAP` line 17 with `haiku`). Denylist: `Write`/`Edit` on `CLAUDE.md`, `automation/state/params*.json`, `automation/state/aggressive/params.json`, `automation/prompts/heartbeat*.md`, `backtest/lib/filters.py`, `**/*.key`; deny all `mcp__alpaca__place_*/cancel_*/close_*/replace_*` + `alpaca_aggressive` twins. Ship with `gamma-companion/smoke-sdk.js`-style test proving an "edit CLAUDE.md" task is refused at the SDK boundary. **Independently shippable: hardens the existing escalation path with zero new surface.**

2. **Authenticate the server + add the kill-switch + concurrency/$-cap.**
   Touches `gamma-companion/server.js` (bearer token generated at boot, injected into served `index.html`, checked on every `/api/*` POST at lines 186/216/239; `Origin`/`Host` allowlist) and `runEscalation` (check `automation/state/companion-halt.flag` + inflight semaphore ≤2 + daily $-cap from a new `automation/state/gamma-activity.jsonl` before spawn). Also: **delete any route toward an `order` action type** and **de-dupe `derivedCards` by stable id** in `gamma-companion/lib/state.js:64-110`. **Independently shippable: closes the network hole the guard alone leaves open.**

3. **Unify the activity spine — `gamma-activity.jsonl` + `logActivity()`.**
   Touches `gamma-companion/lib/escalate.js`, `gamma-companion/lib/approvals.js`, and `setup/scripts/run_minimax.py` — each emits one row (`{ts,source,origin,tier,model,cost_usd,inflight,action,outcome}`) on every escalation/approval/face-call. This is the meter the $-cap in #2 reads and the feed the cockpit tails (via `fs.watchFile` stat-poll, **not** `fs.watch` — unreliable on Windows; default to piggybacking the existing 5s `/api/state` poll). **Independently shippable: pure observability, no behavior change.**

4. **One shared voice — `automation/presence/GAMMA-VOICE.md`.**
   Built on the verified-existing `automation/presence/SOUL.md`. Loaded by `gamma-companion/face/face_brain.py` (replace the `SYSTEM` string at line 46) and `gamma-companion/server.js#/api/realtime-token` (replace the inline `instructions` at lines 251-252 with its head + the mouth-only rule). Tag `origin:'voice'|'text'|'click'` at the `/api/chat` boundary so the guard from #1 can force voice → propose-only. **Independently shippable: makes it sound like Gamma and wires the origin tag the guard needs.**

5. **Server-enforced voice meter — idle auto-stop + daily cap.**
   Touches `gamma-companion/server.js#/api/realtime-token` (track last-activity per session, refuse token refresh past a hard daily cap read from a new `automation/state/companion-voice-usage.jsonl`) + a `POST /api/voice-event` endpoint + a voice-spend tile on `/api/state`. **Independently shippable: caps the one cost that bills J's personal OpenAI key directly.**

---

## Open questions for J

Only the decisions that genuinely need you — everything else is specified above.

1. **Daytime authoring auto-apply for typed/click builds.** Voice is always propose-only. For typed/click authoring builds during 09:30–15:55 ET while you watch: auto-apply under the gym gate, or require a tap? *(Recommended: auto-apply read-only/author for typed/click; voice always taps.)*

2. **Soul-surface line.** Confirm: ship-if-profitable governs engine/authoring; **`CLAUDE.md` stays propose-only** (DRAFT → your 👍), even under bypass, even spoken — because ASR/injection could rewrite the reward function.

3. **Immutable anchors — hard or soft?** 10 rules / kill-switch numbers / FORBIDDEN-FRAMING: no card can EVER be created for them (hardest), or card-with-double-confirm? *(Recommended: hard.)*

4. **Voice $-cap + RTH policy.** Hard daily cap on the OpenAI realtime key with server auto-mute? And during market hours: free voice chat stays live (only Claude escalations defer), or whole companion muted? *(Recommended: free chat live; all Claude escalations defer.)*

5. **Obligation auto-fix scope.** Confirm: auto-fire read-only skills (`connectivity-gate`, `chart-read`, `gym-session`, `swarm-health`); flag-only for anything that re-runs premarket/EOD writes or touches params/orders.