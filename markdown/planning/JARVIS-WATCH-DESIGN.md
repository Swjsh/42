# Jarvis / Mobile-Watch Design

> Living design doc for the operator↔assistant unification + mobile/watch reach, folded from four 2026-06-21 one-offs per markdown/infra/DOC-ARCHITECTURE.md.

---

## Gamma Jarvis Unification — One Gamma, Two Faces (2026-06-21)

**Date:** 2026-06-21
**Status:** Build plan — synthesizes 4 design pillars, verified head-to-toe against the live `gamma-companion/` + `automation/` code.
**Goal:** Collapse the "two Gammas" (the autonomous OPERATOR and the conversational ASSISTANT) into ONE assistant J can talk to from his Samsung watch / phone that (a) KNOWS exactly what the operator is doing, (b) lets him brainstorm by voice like talking to Claude, (c) drives the real Claude on the always-on PC to keep the project moving while he's away.
**OP-3 cost:** $0 recurring. Only true $ spend is OpenAI Realtime audio minutes (J's own key, bounded by talk time) + Max-pool rate-limit budget on escalations J explicitly triggers.

---

### Headline

One autonomous operator + one voice assistant + one phone/watch PWA, fused over a shared filesystem spine and a single guarded escalation chokepoint — J talks to Gamma from his wrist, sees every operator move, and approves irreversible changes with a tap. Tailscale-private, guard-held, $0.

---

### What ALREADY exists (honest inventory — the skeleton is mostly built)

A surprising amount is already wired. The unification is mostly *connecting* and *widening*, not building net-new engines.

| Piece | File | State |
|---|---|---|
| **Activity spine contract** | `gamma-companion/lib/activity.js` | BUILT. `logActivity/readActivity/todaySpend/loadActivity`, defensive, `{ts,source,origin,tier,model,cost_usd,action,outcome}`. **BUT `automation/state/gamma-activity.jsonl` is EMPTY** — only the companion writes to it; the operator writes nothing, so the assistant is blind. |
| **State merge + face summary** | `gamma-companion/lib/state.js` | BUILT. `buildState()` (line 113) merges engine-health, kitchen, positions, loop-state, dialogue, approvals, `readActivity(root,10)`. `summarize()` (line 214) emits the compact face context. This is the function to WIDEN. |
| **Escalation chokepoint** | `gamma-companion/lib/escalate.js` | BUILT. `runEscalation(root,{id,model,task,origin})` — the ONE place Gamma drives Claude. `MAX_INFLIGHT=2`. Logs to `companion-ask-results.jsonl` + spine. **Stateless one-shot per turn** (no resume) — this is the deep-mode gap. |
| **The guard** | `gamma-companion/lib/guard.js` | BUILT + CORRECT. `makeCanUseTool` DENY_WRITE (CLAUDE.md/params/heartbeat/filters.py/`*.key`) + DENY_TOOL (alpaca place/cancel/close/replace/exercise/do_not_exercise) + `companion-halt.flag` checked first. Do NOT touch semantics — only widen the denylist. |
| **Approval queue** | `gamma-companion/lib/approvals.js` | BUILT. `readApprovals/resolveApproval/writeApprovals` → `companion-approvals.json` + `companion-decisions.jsonl`. No `enqueueApproval` yet. |
| **Obligation/derived cards** | `state.js#derivedCards` (line 65) | BUILT. Synthesizes kitchen-failed + engine-RED cards into `state.approvals` with an `escalate` action on Approve. |
| **Server + routes** | `gamma-companion/server.js` | BUILT. `127.0.0.1:4317`, `authed()` (token + localhost-origin), `/api/state`, `/api/chat` (→ face → escalate), `/api/approve`, `/api/diagram`, `/api/realtime-token` (gpt-realtime-2, ephemeral mint). |
| **Free face brain + router** | `gamma-companion/face/face_brain.py` | BUILT. Free OpenRouter ladder, classifies glue-vs-escalate, ` ```escalate ``` ` fenced directive (`parse_escalation` line 105), opus/sonnet model pick. No deep/resume tier. |
| **Realtime voice** | `gamma-companion/public/realtime.js` | BUILT. `ask_gamma` tool → POST `/api/chat` → speaks `r.reply`; escalation is fire-and-forget ("lands in the feed"). One-shot, no streaming. |
| **OpenAI key handling** | `gamma-companion/lib/openai_key.js` | BUILT. Server-side only; ephemeral token mint — key never reaches browser. |
| **Agent SDK** | `node_modules/@anthropic-ai/claude-agent-sdk@0.3.185` | INSTALLED. Verified `resume?` (sdk.d.ts:1715), `includePartialMessages?` (1543), `forkSession?` (1412), `session_id` on init system msg (157). All deep-mode primitives present. |
| **Operator producers** | `automation/prompts/conductor.md`, `heartbeat.md`, `setup/scripts/kitchen_daemon.py` | LIVE. Conductor STAGE 5 (line ~126) already appends a STATUS.md fire-line. Kitchen has a single status-snapshot chokepoint (`_write_status_snapshot` line 389). None write the spine yet. |
| **Operator-side approval bus** | `setup/scripts/discord-responder.py` | LIVE. `conductor-proposals.jsonl` → `_try_resolve_proposal` (line 236) → `conductor-approvals.jsonl`. `market_is_open` (line 98). **A SECOND approval ledger the companion never reads.** |
| **Mobile/watch reach design** | the Mobile-Watch Buildout section below | DESIGNED (approved, not built). Web Push (VAPID, Node crypto, $0) → PWA service worker → Wear OS bridge; Tailscale Serve → `127.0.0.1:4317`; signed single-use HMAC wrist route. |

**Net:** the spine, the guard, the escalation chokepoint, the approval queue, the obligation cards, the voice channel, and the SDK resume primitives are all already present. The four missing connections are: (1) the operator never writes the spine; (2) the face summary is too narrow to "know everything"; (3) escalation is stateless one-shot, not a warm Claude conversation; (4) the two approval ledgers never merge and there's no wrist reach.

---

### The four seams to close (and the order that maximizes leverage)

1. **SHARED CONTEXT SPINE** — make the operator write the spine + widen `summarize()` so the assistant literally sees every move. *Mostly a `state.js` widen + a tiny Python logger. The literal ask. #1.*
2. **UNIFIED BRAIN** — a warm, resumable, streaming Claude session (deep mode) for brainstorm turns; free face kept as router/glue; market-hours starvation guard.
3. **ALWAYS-ON LOOP + ONE ACTION BUS** — voice→tracked-task→push-report-back; merge the two approval ledgers into one wrist-resolvable queue.
4. **REACH LAYER** — Web Push + PWA + Tailscale (the mobile buildout doc), so all of the above lands on the wrist. Device-dependent → last.

---

### Build order (ranked)

> `safe_now` = additive, no device dependency, no doctrine/order surface, ships today under the auto-ratify gate. The heartbeat-prompt edit and the device runbook are the only non-safe-now items.

#### Phase A — Shared context spine ($0, all defensive, the literal ask)

**A1. `automation/scripts/log_activity.py` — the Python twin of activity.js.**
`log_activity(source, action, outcome, *, origin=None, tier=None, model=None, cost_usd=0.0)` writing the EXACT `{ts,source,origin,tier,model,cost_usd,action,outcome}` contract atomically to `automation/state/gamma-activity.jsonl` (ts stamped inside — caller never supplies, matching activity.js:33). Defensive: never throws (telemetry must not crash its producer). Plus an `argparse __main__` CLI so prose-driven prompts append via one Bash line. Mirror the contract comment block from activity.js verbatim so the two writers cannot drift. Include the **retention cap** here (OP-22): when the ledger exceeds N (5000) rows, archive the oldest to `gamma-activity-archive.jsonl`. Files: `automation/scripts/log_activity.py` (new).

**A2. `backtest/tests/test_log_activity.py` — graduate the contract (C7/C14).**
Asserts: a written row round-trips through the same keys activity.js's `readActivity` expects; `ts` is stamped not supplied; a malformed pre-existing line is skipped not fatal; the CLI exits 0 and appends exactly one line; the retention cap archives correctly. Runs in `backtest/.venv`. Files: `backtest/tests/test_log_activity.py` (new).

**A3. Wire KITCHEN to the spine (pure code, $0).**
In `kitchen_daemon.py` add `_log_spine(task)` and call it at the per-task-completion site, inside try/except (the daemon must never die on a telemetry write). Writes `{source:"kitchen", tier:"kitchen", model:task.model, cost_usd:task.cost_usd, action:"cooked "+task.task[:60], outcome:task.status}`. The single chokepoint is near `_write_status_snapshot` (line 389) / the completion transition (status→"completed", line ~355). Files: `setup/scripts/kitchen_daemon.py`.

**A4. Wire CONDUCTOR to the spine (prose, $0).**
Add STAGE 5 step "5.4 — append to the shared spine" after the existing STATUS.md fire-line (conductor.md line ~126): one `python automation/scripts/log_activity.py --source conductor --tier conductor --action "<item id + verb>" --outcome "<OK|FLAGGED|SKIP> — <1-line>" --cost <rounded $>`. This edits the conductor's OWN operational prompt — NOT params/heartbeat/CLAUDE.md — so rail 4 is clear. Files: `automation/prompts/conductor.md`.

**A5. Widen `buildState()` so the brain sees the FULL operator picture.**
Add four cheap defensive reads (each in a `readJSON`-style try/catch → null):
- `status_tail`: last ~6 STATUS.md fire-lines (read `automation/overnight/STATUS.md`, filter lines starting with `[` or `## [`, take last 6, tidy to ~90 chars) — the conductor's last fires.
- `decisions_tail`: last 5 `decisions.jsonl` rows parsed to `{time_et,action,setup_name,spy,reason}`, **pre-filtered to non-HOLD** (decisions.jsonl is 127 ticks/day, mostly HOLD) — the engine's actual decisions.
- `journal_headline`: newest `journal/YYYY-MM-DD.md` first non-blank heading (glob newest, read first ~3 lines) — the human day narrative.
- `pnl`: extend `accountView()` to surface day P&L from `pos.unrealized_pl` / `loop.day_pnl`, not just equity.
Files: `gamma-companion/lib/state.js`.

**A6. Widen `summarize()` so the face reads it ($0, capped ~1.2KB).**
After the existing feed block, append "Conductor last fires:", "Engine decisions:", "Today's journal:" using the new fields, each `tidy()`-clipped, whole summary capped ~1.2KB (sent every face turn — the free model budget guard is real but small). Files: `gamma-companion/lib/state.js`.

**A7. Escalation asymmetry — the PC-side Claude gets the FULLER dump.**
In `escalate.js`, prepend a `## Operator context` block = `summarize(state)` + the RAW tails at fuller depth (`status_tail` 12 not 6, `decisions_tail` 15 not 5) so when J brainstorms by voice the real Claude already knows exactly what the operator did. Asymmetry: face = lean summary ($0 to assemble, cheap free model); escalation = fuller dump (still $0 to assemble; cost only on the escalation tokens J triggered). Files: `gamma-companion/lib/escalate.js`.

**A8 (J-GATED DRAFT). Wire HEARTBEAT to the spine — state-change ticks only.**
In `heartbeat.md` Writes section: on `action != HOLD/SKIP_STALE/PAUSED`, append one spine row (`--source heartbeat_safe --tier engine --action "<ENTER_BULL 5c @752 / EXIT TP1 / kill-switch>" --outcome "<fill px / $risk / reason>" --model <model>`). Bold mirrors with `heartbeat_bold`. Plus a once-per-session "session start" + "EOD flat" pair so the face never says "engine silent" on a quiet no-trade day. This edits the LIVE heartbeat prompt — a trading-doctrine surface — so per conductor rail 4 it ships as a **DRAFT** (`heartbeat-spine-draft` note) + J REVOKE-review, NOT auto-applied, even though the change is append-only telemetry with no decision-logic change. Files: `automation/prompts/heartbeat.md` (DRAFT — J-gated).

#### Phase B — Unified brain (warm resumable Claude + market-hours guard)

**B1. `lib/deepsession.js` — the DeepSession manager.**
`query()` with `includePartialMessages:true`; capture `session_id` from the init `SDKSystemMessage` (sdk.d.ts:157); store `{convId → {sessionId, model, lastActive}}` in-memory + mirror to `automation/state/companion-sessions.json` for crash recovery; pass `resume: stored.sessionId` on turn 2+ (full history, no re-priming — the cost win); 20-min idle evict; wrap every turn in `makeCanUseTool` (guard.js unchanged — deep mode inherits the full denylist, adds NO privilege). Export `startTurn(convId,text,model,origin)` → async iterator of `{delta}|{done,text,sessionId}`. Share the `MAX_INFLIGHT` counter with `escalate.js` so brainstorm + card-escalation don't together hammer the Max pool. Files: `gamma-companion/lib/deepsession.js` (new).

**B2. Market-hours STARVATION GUARD (the load-bearing one).**
Before starting/resuming ANY heavy (deep/opus) Claude turn during 09:30–15:55 ET on a trading day, read `engine-health.json` `market_open` (state.js already reads it, line 193); if open + heavy, refuse with a SPOKEN "I keep heavy thinking off during market hours so I don't starve the live engine — want me to queue it for after the close?" Mirror the conductor STAGE 0 rail-1 gate (L54). GLUE (free face) always allowed. **Soft, not a hard lockout** (OP-25/OP-32 scar — fail open, never block J). Add `isMarketHoursHeavyBlocked(root)` helper to `guard.js`. Files: `gamma-companion/lib/deepsession.js`, `gamma-companion/lib/guard.js`, `gamma-companion/server.js`.

**B3. `face_brain.py` router — add the deep tier.**
Add a ` ```deepmode {"model":...} ``` ` parse (sibling to `parse_escalation` line 105) OR a `"mode":"deep"` field in the existing escalate block. Refine the model/mode heuristic (lines 60/89) so multi-turn brainstorm/strategy turns route DEEP, one-shot build/fix stays escalate, status stays glue. Files: `gamma-companion/face/face_brain.py`.

**B4. `server.js` — `POST /api/chat/stream` (SSE).**
On a deep directive, drive `deepsession.js` and forward each partial delta as an SSE event + a final `done`. Keep `/api/chat` for glue + one-shot. Reuse `authed()` + GAMMA_TOKEN. Log each deep turn via `logActivity` (tier 'agent', model, cost from the SDK result `usage`). Files: `gamma-companion/server.js`.

**B5. `realtime.js` — streaming voice bridge.**
Replace the one-shot `function_call_output` (lines 88–100) for deep turns: speak a short "let me think this through out loud…" immediately, consume `/api/chat/stream`, then speak a 1–2 sentence summary + push the full answer to the feed on `done`. Keep the one-shot path for glue/status. (v1 = spoken-bridge + summary; true token-by-token TTS is v2 once the stream is proven — half-formed sentences stutter the Realtime TTS.) Files: `gamma-companion/public/realtime.js`.

**B6. `app.js` — render streamed deep tokens live + warm-session indicator.**
Consume the same SSE so typed brainstorm matches the voice experience. Files: `gamma-companion/public/app.js`.

#### Phase C — Always-on loop + one action bus

**C1. `lib/tasks.js` — durable task ledger.**
`appendTask/markTask/readTasks/queueSummary` → `companion-tasks.jsonl`, defensive never-throw house-style. One row per voice/chat/card/discord-spawned task `{id, source, request, model, status:'queued'|'running'|'done'|'failed'|'deferred', created_at, updated_at, summary, ask_id}`. Files: `gamma-companion/lib/tasks.js` (new), `automation/state/companion-tasks.jsonl` (runtime).

**C2. Wire `runEscalation` to the task ledger + market-hours defer.**
Write a 'running' row at start, flip to 'done'/'failed' with summary at finish (wrap the existing `appendResult`). Stamp `source` from `origin`. Add a deferred-if-market-open branch reusing the same ET/market check (mirror `discord-responder.py:98`) so a market-hours escalate is QUEUED (`status:'deferred'`) not run, with a one-line ack. Files: `gamma-companion/lib/escalate.js`.

**C3. `lib/proposals_bridge.js` — merge the operator approval ledger.**
Read pending `conductor-proposals.jsonl` rows, project each as a card `{id:'prop-<id>', source:'conductor', proposal_id, severity, title, detail}`. Factor the `discord-responder.py#_try_resolve_proposal` status-flip (proposals → approved/shelved + `conductor-approvals.jsonl` append) into a SHARED resolve helper so the wrist tap, the Discord "ship <id>" reply, and the in-app tap all hit IDENTICAL code. Files: `gamma-companion/lib/proposals_bridge.js` (new), `setup/scripts/discord-responder.py` (refactor to call the shared flip).

**C4. `server.js` — merge conductor cards into `/api/state` + branch `/api/approve`.**
Merge `proposals_bridge` cards beside the obligation-card mapping (state.js:148). Branch `/api/approve` on `card.source`: `conductor` → ledger flip via the bridge; `obligations`/`card` → existing `resolveApproval`. Expose tasks summary in state. **Wrist tap records approval only — the next conductor fire does the actual J-gated param edit** (per current doctrine, the wrist never mutates params.json directly). Files: `gamma-companion/server.js`.

**C5. `lib/approvals.js` — `enqueueApproval` + clear-on-resolve.**
`enqueueApproval(root, item)` calls `writeApprovals([...pending, item])` then fire-and-forget `push.sendPush` with Approve/Reject actions bound to signed-token URLs. Extend `resolveApproval` to fire-and-forget a same-tag push so resolving on one device clears the notification on all. Files: `gamma-companion/lib/approvals.js`.

#### Phase D — Reach layer (Web Push + PWA + Tailscale; device-dependent → last)

**D1. `lib/push.js` — Web Push transport (VAPID, Node crypto, $0).**
`loadVapid/loadSubs/saveSub` (atomic tmp+rename), `sendPush` (RFC8291 aes128gcm + VAPID ES256 JWT, per-sub try/catch, fire-and-forget), `mintApproveToken` (HMAC-SHA256 of `id|decision|exp`, base64url), `verifyApproveToken` (constant-time compare, exp, jti consumption). Absent `.vapid.json` ⇒ all push is a $0 no-op (fail open). **Persist the consumed-jti set to `.approve-consumed.json`** (survive server restart — open Q resolved: persist it). Files: `gamma-companion/lib/push.js` (new), `automation/state/.vapid.json` + `.approve-hmac.key` (J generates on-machine), `push-subscriptions.json` + `.approve-consumed.json` (auto).

**D2. Guard tightening + smoke-guard (defense in depth).**
Add explicit DENY_WRITE regexes for `.vapid.json`, `push-subscriptions.json`, `.approve-hmac.key` (the `/.key$/i` already covers the last — be explicit). Add smoke-guard cases: denies write to `.vapid.json` / `.approve-hmac.key`; allows other `.json`; **asserts `/api/approve-signed` never imports `runEscalation`** (the capability boundary as a compile-time check). Files: `gamma-companion/lib/guard.js`, `gamma-companion/smoke-guard.js`.

**D3. Push + wrist routes in `server.js`.**
`POST /api/push/subscribe` (authed) → `saveSub`; `GET /api/push/vapid-public` (authed) → `{publicKey}`; `GET /api/approve-signed?tok=…` (NOT authed — SW scope has no token — placed above the static fallback) → `verifyApproveToken` → 403 on fail OR the SHARED resolver (plain fs ledger flip only, never an SDK tool) → tiny 200 "Logged". Widen the Origin regex to accept the exact `GAMMA_TAILNET_HOST` env (never a `*.ts.net` wildcard; empty env → localhost-only, fails private). Files: `gamma-companion/server.js`.

**D4. Rising-edge push for ALL new cards.**
In `/api/state`, diff vs `.push-seen.json`; fire-and-forget `push.sendPush` only on NEW obligation/conductor-proposal/done-failed-task cards (never re-push on re-poll), rate-limited per id; push a same-tag "resolved" replacement on resolve. Files: `gamma-companion/server.js`.

**D5. PWA shell — manifest + service worker + mobile CSS.**
`manifest.webmanifest` (standalone, theme/bg, 192/512 maskable icons from the Gamma robot SVG); `service-worker.js` (precache assets, cache-first assets / network-first `/api/*`, `push` → `showNotification` with Approve/Reject actions, `notificationclick` → fetch the signed-token URL + close); `index.html` head (manifest link, theme-color, apple-mobile-web-app metas); `app.js` (SW register, "Enable wrist alerts" button → `Notification.requestPermission` → `pushManager.subscribe` → `/api/push/subscribe`); `styles.css` (mobile-first, 44px targets, 16px inputs to kill iOS zoom, `≤280px` watch breakpoint). Files: `public/manifest.webmanifest` + `service-worker.js` + icons (new), `public/index.html` + `app.js` + `styles.css`.

**D6 (RUNBOOK — J's hands, not Gamma-buildable). Device verification.**
Tailscale up on PC + phone; `tailscale serve https://gamma.<tailnet>.ts.net → :4317`; J generates `.vapid.json` + `.approve-hmac.key` on-machine; install PWA (phone Chrome → Add to Home Screen); grant notifications; Galaxy Watch pairing + enable notification bridging in Galaxy Wearable; end-to-end test: `/api/state` returns operator state, a test approval pushes to the wrist, tap Approve, verify the right ledger (`companion-decisions.jsonl` for companion cards, `conductor-approvals.jsonl` for conductor cards); voice "go research X" round-trips to a tracked task with a push report-back. Files: runbook (no code).

---

### J's device steps (one-time, in order)

1. **Tailscale** — install on the always-on PC and the Galaxy phone; sign both into the same tailnet (free personal tier, $0). On the PC: `tailscale serve https://gamma.<tailnet>.ts.net → http://127.0.0.1:4317` (server stays bound to localhost; Serve proxies inbound; auto Let's Encrypt cert = secure context for the mic).
2. **Set `GAMMA_TAILNET_HOST`** env on the PC to the exact MagicDNS host (e.g. `gamma.j-tailnet.ts.net`) so the Origin allowlist pins it — never a wildcard.
3. **Generate keys on-machine** (never in any transcript): `.vapid.json` (VAPID keypair) and `.approve-hmac.key` (32 random bytes) into `automation/state/` via the provided Node crypto script.
4. **Install the PWA** — open `https://gamma.<tailnet>.ts.net` in phone Chrome → Add to Home Screen → launch the installed app → grant notification permission → tap "Enable wrist alerts" (subscribes the device).
5. **Pair the Galaxy Watch** (standard Wear OS) and enable notification bridging in the Galaxy Wearable app so phone notifications + their Approve/Reject action buttons surface on the wrist.
6. **Verify** — trigger a test approval; confirm the wrist buzzes with Approve/Reject; tap Approve; check the correct ledger logged it. (Wear OS notification-action bridging on J's specific watch model is the one unverified assumption — this step confirms it.)

No app store, no Wear OS app, no second daemon, no public port.

---

### Security + cost model

**Tiering (who answers what):**
- **GLUE** (status / "what's Gamma doing" / a number) → free face from `summarize(buildState)`, $0, no Claude, no Max-pool draw — always allowed, even RTH.
- **DEEP / one-shot** (brainstorm / build / fix / analyze) → the real Claude via the SDK. Default deep to **sonnet**; reserve **opus** for explicit strategy/reasoning. Warm resume is the cost win — a 6-turn brainstorm doesn't re-explore the project 6 times.

**Two independent meters:**
1. **Claude (Max pool):** every deep/one-shot turn runs the local Agent SDK on J's Max subscription — the SAME shared rate-limit pool as the heartbeat (the dedicated API key was retired 2026-06-17 after burning ~$30 and going dark mid-FOMC). So deep mode is ~$0 in dollars but COSTS rate-limit budget. Hence the market-hours starvation guard is load-bearing, not cosmetic.
2. **OpenAI Realtime (real $):** `gpt-realtime-2` bills per audio minute on J's own key (server-side mint, key never reaches the browser). The only true $ spend, bounded by talk time (~+$1.50 on a chatty 15-min day — within OP-3's $3.33/day). Realtime stays transport+TTS only; all reasoning is on Claude.

**Spine + summary widening = $0:** pure file-append + file-read. Operator appends are sub-ms `fs.appendFile`/atomic-write, adding nothing to per-fire model spend. `summarize()` reads ~4 small files per face turn. Heartbeat logs only state-change ticks (~0–4 rows/day) + a session start/EOD pair, not 127 HOLDs, so `readActivity`/`todaySpend` stay fast; the retention cap (5000 rows → archive) prevents unbounded growth (OP-22). The only incremental token cost is the fuller operator-context preamble on escalations J explicitly triggers (~1–2KB, a few cents) — which is the whole point.

**Security — three boundaries, the guard untouched:**
1. **Network:** server stays `127.0.0.1:4317`; Tailscale Serve (WireGuard device-auth, private tailnet only) proxies inbound; if Tailscale dies it falls back localhost-only — **fails private, not open**. Categorically never a public port (the companion can drive Claude + holds an OpenAI key).
2. **App:** `authed()` token (`crypto.randomBytes(24)`/boot) + Origin pinned to the exact MagicDNS host. Every state-changing POST stays token-gated.
3. **Capability:** the ONE intentionally-unauthenticated route (`/api/approve-signed`) is provably narrow — single-use HMAC token (id|decision|exp, constant-time verify, consumed-jti persisted), resolves at most ONE pre-queued approval, calls only the plain-fs ledger flip, and a smoke-guard assertion proves it never imports `runEscalation`. A captured wrist URL can at worst approve one already-queued decision once.

**The guard semantics are UNCHANGED across the whole build** — every deep/one-shot/voice/wrist-spawned turn goes through the SAME `makeCanUseTool`, so the escalated Claude can edit the companion, run backtests, author validators, draft proposals — but can NEVER write CLAUDE.md/params/heartbeat/filters.py/`*.key` (DENY_WRITE) or place/cancel an order (DENY_TOOL), and `companion-halt.flag` is J's global wrist-accessible kill-switch (fail-open, never blocks his interactive session). Irreversible changes are propose-only → a wrist card → J taps → the next conductor fire applies the still-J-gated edit. The project moves; nothing irreversible happens without a wrist tap. This pillar set only WIDENS what the assistant SEES and adds producers/reach in FRONT of the chokepoint — it never widens what tools can be CALLED.

**Open questions carried forward** (don't block Phase A): conductor spine row carrying `proposal_id` on a FLAG (so obligation cards can join a flagged fire to its outbox proposal) — worth it, needs the contract test updated; whether a conductor wrist-approval auto-applies vs. stays a separate J-gated conductor-fire apply (current doctrine = stays gated); the deferred-queue drain policy after 15:55 (reuse the next conductor fire rather than a new task, to stay lean); face mis-classification burning Max budget on a should-have-been-glue turn (tighten the explicit-build/fix/run rule, or a cheap server-side confirm card above a cost threshold when J is away).

---

### Why this order

Phase A is #1 because it IS the literal ask ("the assistant knows everything") and it's the cheapest, most defensive, no-device work — a `state.js` widen + a ~100-line Python logger + four one-line operator appends, all $0, all fail-safe, gym-testable today. It also unlocks everything downstream: deep mode (B) and the always-on loop (C) are only as smart as the context the brain receives, and the reach layer (D) is only worth building once the assistant has something complete to say from the wrist.

---

## Unifying Gamma: The JARVIS Design — 2026-06-21 (2026-06-21)

**Status:** Research synthesis + concrete architecture design. Builds on the existing `gamma-companion` (v0 shipped) and the validated mobile buildout plan (see the Mobile-Watch Buildout section below). This document covers the **operator↔assistant unification**, the **voice+brainstorm→action loop**, and the **security model** for an always-on AI agent that can drive a home PC from a phone/watch.

**What you get:** A single unified Gamma that J can talk to from his wrist, that knows exactly what the autonomous operator is doing, that brainstorms with Claude-grade thinking, and that pushes actions back to the PC to execute — all without exposing private keys or doctrine to the phone, and without starving the live heartbeat. $0 recurring cost (Tailscale free, Web Push free). Proven patterns from Home Assistant, NautilusTrader, and Anthropic's own agent guidance.

---

### Part 1: The Unified Gamma Architecture

#### 1.1 Today's two-Gamma problem

**OG Gamma (the operator)** fires 24/7 on the PC:
- Scheduled tasks (Premarket 08:30, Heartbeat 09:30-15:55, EOD-Flatten, Kitchen daemon)
- Reads live TradingView + Alpaca state
- Executes trades, journals decisions, produces `automation/state/*.json`
- NEVER touches: doctrine, params, keys (guard.js blocks it)

**Companion Gamma (the assistant)** runs on-demand in the Node server (127.0.0.1:4317):
- Web UI (localhost:3000 via port 3000) + voice (OpenAI Realtime)
- Free-model face (Nemotron) for chat + brainstorm
- Escalate button → Claude via Agent SDK (uses guard.js denylist)
- Knows NOTHING about: overnight news, the heartbeat's state, what trades happened

**The gap:** J can't talk to Gamma from his phone while trading. He can't see "what is the operator doing right now?" He has to switch apps and contexts. The two don't share state.

#### 1.2 The unified design: "Gamma is the operator's voice + eyes"

**One Gamma. Two faces.**

```
┌─────────────────────────────────────────────────────┐
│ PC (127.0.0.1)                                      │
├─────────────────────────────────────────────────────┤
│                                                       │
│  ┌─ Heartbeat (Sonnet, 09:30-15:55, live trades)   │
│  │  + Premarket (08:30, bias/levels)                │
│  │  + Kitchen daemon (24/7 research)                │
│  │  + Watchers (28, reading TradingView/Alpaca)     │
│  └─> SHARED STATE: automation/state/*               │
│                                                       │
│  ┌─ Companion Server (Node, 4317)                   │
│  │  ├─ Face: Nemotron (free, ~2s latency)           │
│  │  ├─ Brain: Claude via Agent SDK (escalate)       │
│  │  ├─ Guard: lib/guard.js (DENY_WRITE + DENY_TOOL) │
│  │  ├─ Activity spine: gamma-activity.jsonl         │
│  │  └─ Approval queue: companion-decisions.jsonl    │
│  └─> HTTP API: /api/state, /api/chat, /api/approve │
│      + Push API: /api/push/subscribe, /api/push/vapid-public
│                                                       │
└────────────────────────────────────────────────────┬─
                                                    │
                    Tailscale Serve (HTTPS)
                                                    │
         ┌─────────────────────────────────────────┘
         │
      ┌──┴──────────────────┐
      │ Samsung Phone        │
      ├─────────────────────┤
      │ ┌─ PWA (installed)   │
      │ │  └─ Voice mic      │
      │ │  └─ Approve/Reject │
      │ │  └─ Web Push       │
      │ └─ Tailscale client  │
      │    (WireGuard)       │
      └─────────────────────┘
         │
      ┌──┴──────────────────┐
      │ Samsung Galaxy Watch │
      ├─────────────────────┤
      │ Wear OS (phone-paired)
      │ ┌─ Notification      │
      │ │  bridge            │
      │ │  └─ Approve/Reject │
      │ └─ NO app install    │
      │   (auto-bridge)      │
      └─────────────────────┘
```

**Key insight:** The operator's state is already written to JSON. The assistant reads it. A voice command from the phone becomes a task in the operator's queue. The operator executes it, writes results back, the assistant reads them. **The shared state file is the contract.**

#### 1.3 The contract: activity spine + shared state

The operator logs **everything** to:
- `automation/state/gamma-activity.jsonl` — append-only fire log (already exists, already written by heartbeat)
- `automation/state/engine-health.json` — one live snapshot (health beacon, Phase 0b in the blueprint)

The assistant reads:
- All of `automation/state/` (engine health, decisions, yesterday's journal, pending approvals)
- `journal/YYYY-MM-DD.md` (today's bias, levels, entries/exits)
- `analysis/eod/<yesterday>.md` (post-trade reflection, regrets, edge-capture)

The assistant produces:
- `automation/state/companion-decisions.jsonl` — approvals/rejections from the UI and wrist
- `automation/state/companion-dialogue.jsonl` — voice chat history (face + escalations)
- Pushes work into the Kitchen queue when J says "brainstorm X"

**Why this works:** No tight coupling. The operator doesn't know the assistant exists. The assistant is a read-heavy stateless client. No token passing, no API key on the phone.

---

### Part 2: Voice + Brainstorm → Action Loop

#### 2.1 The conversation arc (the "ask Gamma" flow)

```
┌─ J on phone: "Ask Gamma how many 0DTE sessions has it run?"
│
├─> Web mic → Whisper (OpenAI Realtime) → text
│
├─> POST /api/chat { message, history? }
│   │
│   ├─ [Simple] Nemotron face reads gamma-activity.jsonl
│   │  (free model, ~2 second latency, fireside chat, context retrieval)
│   │  → "139 sessions, 42% win rate, today's up $147 before fees"
│   │  → Response delivered
│   │  → Save to companion-dialogue.jsonl
│   │  → Done
│   │
│   └─ [Complex] "Is the vwap_continuation edge still live?"
│      │
│      ├─ Nemotron says "I should escalate this"
│      │  (face detects: needs Claude, needs code read, or ambiguous)
│      │
│      └─ Escalate button → /api/escalate
│         │
│         ├─ Guard check: allowed? (yes, no DENY_TOOL/WRITE match)
│         │
│         ├─ makeCanUseTool(guard.js) → SDK runs Claude
│         │  (Sonnet, full project context, can read backtest/*)
│         │
│         ├─ Claude: reads markdown/0dte/playbook.md,
│         │  analysis/recommendations/vwap_continuation_edge.json,
│         │  backtest/autoresearch/_state/vwap_stage1/results.jsonl
│         │
│         ├─ Claude: "vwap_continuation LIVE, OOS +$105/trade, 6/6 days,
│         │  ITM-2 only, −8% stop. Killed 3 other families yesterday —
│         │  the ITM+tight = the edge. Confidence 92%."
│         │
│         └─ Result stored, voice read to J, saved to dialogue log
│            (nothing was executed, just reported)
│
└─> TTS (Piper) → wrist speaker
```

This is the **read-heavy, no-mutation case.** It's 95% of use. The voice is responsive (Nemotron for hot-path chat, Claude for deep questions), the knowledge is live (reads the operator's state JSON), and the guard never trips.

#### 2.2 The approval case (the other 5%)

```
┌─ Conductor (or Chef via escalation) bakes a decision
│  "Should we ship vwap_reclaim? OOS +$840, WF 1.4, A/B scorecard clean."
│
├─> Conductor: enqueueApproval(root, { id, title, body, actions })
│
├─> Companion: enqueueApproval() calls push.sendPush()
│   ├─ Generates signed HMAC token (exp 15min, single-use)
│   ├─ Creates Web Push notification with Approve/Reject buttons
│   └─ Payload encrypted (RFC8291 aes128gcm)
│
├─> Android PWA: receives push
│   ├─ Service worker → showNotification
│   └─ Action buttons bound to signed-token URLs
│
├─> Wear OS bridge: receives notification
│   └─ Auto-forward to wrist + action buttons
│
├─> J taps "Approve" on wrist
│   └─ Notification action → notificationclick handler
│      └─ fetch GET /api/approve-signed?tok=HMAC…
│         ├─ verifyApproveToken: valid? not expired? not already used?
│         ├─ If yes → resolveApproval(id, 'approve')
│         │  └─ Remove from queue, append to companion-decisions.jsonl
│         ├─ If no → 403 "Token expired or invalid"
│         └─ POST /api/clear-notification (replace/hide on all devices)
│
└─> Conductor reads companion-decisions.jsonl
    "vwap_reclaim approved at 20:35 ET by wrist"
    → Ships it (params.json bump, backtest re-run, goes LIVE next session)
```

**Why this is safe:**
1. **Network:** Tailscale WireGuard, private, J's tailnet only.
2. **App:** Token + origin check (page can't be spoofed).
3. **Wrist:** Signed one-time token (can't replay, can't forge, expires).
4. **Action:** resolveApproval is **plain fs ops only** (no escalate path reachable).
5. **Guard:** smoke-guard assertion prevents future edits from adding the escalate path.

---

### Part 3: Security Model (defense in depth)

#### 3.1 The three-layer sandwich

| Layer | Mechanism | Breach Cost | Who |
|-------|-----------|-------------|-----|
| **Network** | Tailscale (WireGuard, private MagicDNS) | 0 risk — no public port | Device auth (WireGuard key) |
| **App** | Token + Origin (per-session, page-bound) | Token is 24 random bytes; swapping origin requires DNS or ARP spoof on tailnet | Page fetch wrapper |
| **Capability** | Signed HMAC token (single-use, exp, consumed-jti) | Need server's HMAC key + valid id + window; can resolve ONE queued decision once | Notificationclick handler (no token in scope) |

**Fail modes:**
- **Tailscale dies** → companion is localhost:4317 only (J's PC can use it, phone can't). Fails private.
- **Phone is stolen** → Tailscale client is at risk, but companion still requires a valid x-gamma-token (rotates per boot) + Approve tokens are time-limited.
- **HMAC key is leaked** → attacker can forge approval tokens, BUT can't reach the escalate path (resolveApproval has no escalate logic by design + smoke-guard blocks it).
- **Malicious Claude is run via escalation** → guard.js DENY_WRITE stops it from editing doctrine/params/keys, guard.js DENY_TOOL stops it from placing orders. It can read and brainstorm, not act.

#### 3.2 Key material management

**VAPID keypair** (Web Push):
- Generated on-machine: `npx web-push generate-vapid-keys` or the 5-line Node script
- Stored: `automation/state/.vapid.json` (privateKey, publicKey, subject)
- Never leaves the PC or a transcript
- Lost VAPID keys = lost ability to push; new keys = re-subscribe all devices (minor UX)
- `DENY_WRITE: /\.vapid\.json$/` — escalated Claude can't read/exfiltrate it

**HMAC key** (approval token signing):
- 32 random bytes: `crypto.randomBytes(32)`
- Stored: `automation/state/.approve-hmac.key`
- Lost HMAC key = can't verify new tokens (old ones still valid until exp); new key can be provisioned and already-signed URLs stop working
- `DENY_WRITE: /\.approve-hmac\.key$/` — guarded

**Session token** (x-gamma-token):
- `crypto.randomBytes(24)` per boot
- In-memory in server.js, injected into `<meta name="gamma-token">`
- Lost on reboot; can't be recovered (design choice for ephemeral sessions)
- Rotates automatically

**No OpenAI key on phone:**
- The companion server holds `process.env.OPENAI_API_KEY`
- Phone never sees it; calls go PC → OpenAI directly
- Guard blocks escalated Claude from writing `.key` files

#### 3.3 Guard tightening (6 lines of code)

The existing guard.js (lib/guard.js:25-30) already blocks DENY_WRITE and DENY_TOOL. The pull request is:

```javascript
// Existing (safe)
const DENY_WRITE = [
  /(^|[\\/])CLAUDE\.md$/i,
  /automation[\\/]state[\\/](aggressive[\\/])?params[^\\/]*\.json$/i,
  /automation[\\/]prompts[\\/].*heartbeat[^\\/]*\.md$/i,
  /backtest[\\/]lib[\\/]filters\.py$/i,
  /\.key$/i,  // <- catches .approve-hmac.key, .vapid.json, any *.key
];

// NEW: tighten the last line to be explicit
const DENY_WRITE = [
  /(^|[\\/])CLAUDE\.md$/i,
  /automation[\\/]state[\\/](aggressive[\\/])?params[^\\/]*\.json$/i,
  /automation[\\/]prompts[\\/].*heartbeat[^\\/]*\.md$/i,
  /backtest[\\/]lib[\\/]filters\.py$/i,
  /\.key$/i,                                    // Covers .approve-hmac.key
  /\.vapid\.json$/i,                            // Covers .vapid.json
  /push-subscriptions\.json$/i,                 // Covers push-subscriptions.json
];
```

**Why:** A stray regex on `\.key$/i` *could* be tightened to require a path, so Gamma explicitly lists what can't be written. This prevents future drift.

---

### Part 4: Proven Patterns from the Wild (2025-2026)

#### 4.1 Home Assistant + Assist (local voice control on your home PC)

**What it does:** Home Assistant runs on a PC/Raspberry Pi, has a local Voice Assistant ("Assist"), talks to you via a mic/speaker or a Companion App on your phone. No cloud required.

**Relevant parts:**
- **Integration:** Home Assistant ships a native integration for any LLM (Ollama, Anthropic, etc.). Claude can be the conversation engine.
- **Companion app:** Home Assistant Companion app (on phone) connects back to the PC via WireGuard (same tunnel strategy as our Tailscale design).
- **Voice:** Whisper (speech-to-text) + Piper (text-to-speech), both open-source, run on the PC. Low latency, all local.
- **State:** Everything is stored in Home Assistant's state database, read by the voice assistant in real-time.

**Sources:**
- [Home Assistant Assist + Voice Control](https://www.home-assistant.io/voice_control/)
- [Home Assistant AI Voice with Local LLM (2026)](https://www.home-assistant.io/blog/2025/09/11/ai-in-home-assistant/)
- [Self-Hosted Voice Assistant (2026 Guide)](https://www.kunalganglani.com/blog/self-hosted-voice-assistant-home-assistant-2026-guide)

**Why it's relevant:** Proves the pattern — PC runs the operator, phone app is a stateless client reading PC state, voice is real-time, all private.

#### 4.2 Tailscale + LM Link (remote access to local LLMs safely)

**What it does:** Tailscale's LM Link lets you query a local Ollama instance from your phone over Tailscale (no public ports, no ngrok).

**Key insight:** Tailscale + WireGuard handles the **network boundary** part. You bind the service to `127.0.0.1:PORT`, Tailscale Serve proxies inbound from the tailnet, and the port never touches the public internet.

**How to scale it:** Taiscale's new **Aperture** service (2026, private alpha) provides:
- API key obfuscation behind tailnet IPs
- Per-user audit logs
- Rate limiting without exposing the key

**Limitation in 2026:** Aperture is not yet GA, but the idea is solid — J's PC is already behind Tailscale on the safe lab, so the simpler approach (bind 127.0.0.1, let Serve proxy) is production-ready today.

**Sources:**
- [How to Access Ollama Remotely with Tailscale](https://logarithmicspirals.com/blog/using-tailscale-to-access-private-llms/)
- [LM Link: Tailscale Blog](https://tailscale.com/blog/lm-link-remote-llm-access)
- [Aperture by Tailscale (AI Gateway)](https://tailscale.com/use-cases/securing-ai)
- [AI Agents are a Security Nightmare for Home Labs (and Tailscale shipped a fix)](https://www.xda-developers.com/tailscale-helps-secure-ai-agents/)

#### 4.3 OpenAI Realtime API + WebRTC (phone voice to Claude)

**What it does:** OpenAI Realtime API can connect via WebRTC (browser) or WebSocket (server relay). For phone voice, use WebRTC from the browser, or WebSocket via a server relay.

**Relevant parts:**
- **WebRTC:** Direct browser-to-Realtime connection, lowest latency, audio is opus-codec compressed.
- **WebSocket:** Server relay (the companion server acts as a proxy), needs a token, can add per-server logic.
- **SIP:** VoIP trunking (e.g., via Twilio), if J wants phone-number dialing.

**Why it matters:** The companion server **today** uses OpenAI Realtime (already wired in face/face_brain.py). The phone PWA just needs to connect to the companion's `/api/realtime-token` endpoint (which returns a session token for Realtime), then the phone can stream audio directly to OpenAI or relay through the companion. **Today's code already supports this.**

**Sources:**
- [OpenAI Realtime API Docs](https://platform.openai.com/docs/guides/realtime)
- [Realtime API with WebRTC](https://developers.openai.com/api/docs/guides/realtime-webrtc)
- [Realtime API Server-Side Controls](https://platform.openai.com/docs/guides/realtime-server-controls)

#### 4.4 Web Push (notifications on phone + watch, $0 cost)

**What it does:** A server sends a **Web Push notification** to a client via the browser's notification API. The notification appears on the phone's home screen and auto-bridges to the paired watch.

**Why it beats ntfy.sh or FCM:**
1. **Same-origin Approve callbacks:** The Approve button can call `/api/approve-signed` on your own origin (no second webhook, no second daemon).
2. **No infrastructure:** Uses the FCM/Mozilla endpoint that Android/Firefox already maintain; no Docker host to keep alive.
3. **$0 cost:** VAPID keypair is generated on-machine. No SaaS, no per-notification cost.
4. **Already async-in-waiting:** The in-app approval queue (polled every 5s) is the source of truth; the push is a best-effort nudge.

**Encryption (RFC8291):** Payloads are encrypted with AES-128-GCM, keyed by the subscription's public key. Only that specific device can decrypt. Built into Node `crypto` module (no npm deps needed).

**Watch bridge:** Wear OS automatically bridges PWA notifications to the paired watch via Android's notification system. You don't install an app on the watch; the phone bridges for you.

**Sources:**
- Web Push API: [MDN Web Docs](https://developer.mozilla.org/en-US/docs/Web/API/Push_API)
- Service Worker: [MDN Web Docs](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API)
- RFC8291: [Message Encryption for Web Push](https://www.rfc-editor.org/rfc/rfc8291)
- [Wear OS Notification Bridging](https://developer.android.com/training/wearables/notifications)

#### 4.5 PWA (Installable web app, no Play Store, stays on home screen)

**What it does:** A web app (HTML + CSS + JS) can be installed on Android via "Add to Home Screen." It runs in a full-screen standalone mode (no address bar), has a home screen icon, and can register a Service Worker to cache assets and handle background events (like push notifications).

**Why for Gamma:** Zero app store friction, zero review delays, works on phone and watch (watch gets notifications auto-bridged), can be updated by pushing new HTML/CSS/JS (no rebuild, no APK).

**Sources:**
- [PWA Install Capability (Chrome Developers)](https://developers.google.com/web/fundamentals/app-install-prompts)
- [Web App Manifest (MDN)](https://developer.mozilla.org/en-US/docs/Web/Manifest)
- [Service Worker Lifecycle (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API)

---

### Part 5: Cost Discipline (OP-3 — Lean by Design)

#### 5.1 Per-day cost breakdown

| Component | Cost | Notes |
|-----------|------|-------|
| **Tailscale free tier** | $0 | Personal/hobby, up to 3 devices, WireGuard only |
| **Web Push (VAPID)** | $0 | Uses Android/Firefox FCM endpoints (no SaaS) |
| **Companion server (Node)** | $0 | Runs on J's PC (electricity already spent) |
| **Nemotron face** | $0 | Free tier, OpenRouter (rate-limited but sufficient) |
| **Heartbeat + premarket** | ~$0.50 | Sonnet 3.5, already budgeted (OP-3: Max $100/mo) |
| **Escalations (Claude via SDK)** | $0.15/request | Sonnet 3.5, pay-as-you-go, ~1-2 per day |
| **Conductor (after-hours)** | $0.20/run | Haiku 4.5, model routing (new, Phase 1b) |
| **OpenAI Realtime** | $0.10/min | Voice call to Claude, only when J talks (peak 10 min/day = ~$1.50 peak) |
| **Total per day (light usage)** | ~$0.75 | Breakeven; no new $0/mo recurring |

**Tailscale premium escalation:** If J wants >3 devices (e.g., desktop + laptop + phone) or Tailscale Funnel for public URLs (not applicable here), $5/mo.

**Cost guard:** None of this scales with usage. The heartbeat is fixed-cost (already $0.50). Escalations and Realtime calls are pay-as-you-go. The whole wrist-approval path is $0.

#### 5.2 Rate-limit discipline (shared Max pool)

**Today's bottleneck:** J's Claude session + the heartbeat share the Max rate-limit pool. A heavy interactive session during 09:30-15:55 ET can starve the heartbeat (the L54 incident, 2026-06-17).

**New design:** The conductor (Phase 1a) and model routing (Phase 1b) are **after-hours only** (16:00–09:30 ET). The heartbeat is Sonnet, continuous. Escalations during market hours are Haiku (cheap, fast). The guardian rule lives in CLAUDE.md:
> **Market-hours discipline:** No heavy interactive work during 09:30-15:55 ET. The heartbeat runs on the shared Max pool; starving it is starving real money. Use the wrist voice to chat (Nemotron, free) and ask questions (Haiku escalations, $0.01-0.05 each). Full Claude brainstorms happen after 16:00 ET or weekends.

This is ENFORCED by:
1. The companion can sense market hours and throttle Sonnet escalations (force Haiku during 09:30-15:55).
2. The conductor only fires after-hours.
3. The status beacon will flag "market-hours escalation attempted" if it ever happens.

---

### Part 6: Implementation Roadmap (integrating into existing build plan)

#### 6.1 The critical path (what to build first)

The Mobile-Watch Buildout (see the Mobile-Watch Buildout section below) already has a 12-step plan (steps 1–11 are Gamma-buildable, step 12 is device-gated). This unification design **extends** that plan with the operator→assistant bridge.

**New steps (interleaved):**

| Phase | Existing Step | New Work | Files | hrs | safe_now |
|-------|---|---|---|---|---|
| **0** | Prelude | **Activity spine reader** — `lib/activityBridge.js` reads `gamma-activity.jsonl` (last 100 rows), summarizes for the UI (What did the operator do in the last N minutes?) | `gamma-companion/lib/activityBridge.js` | 1 | true |
| **1** | 1-6 | Push layer + approval HMAC (existing plan, 8 hrs) | see buildout plan | 8 | true |
| **1b** | 7 | **Operator state reader** — `lib/operatorState.js` reads `automation/state/engine-health.json`, `automation/state/today-bias.json`, `automation/state/decisions.jsonl`. Caches with 10s TTL. | `gamma-companion/lib/operatorState.js` | 2 | true |
| **1c** | 8 | **Unified `/api/state` response.** Merge: operator state + activity + approvals + obligations. Single GET endpoint, polled by UI. | `gamma-companion/server.js` — widen `/api/state` handler | 1 | true |
| **2** | 9-11 | PWA + responsive CSS (existing plan) | see buildout plan | 6.5 | true |
| **2b** | 9 | **PWA brain wiring.** Face calls new operatorState functions. On `/api/chat`, if user asks "how is the session going?" or "show me today's trades," the face now reads the operator's live state and responds. | `gamma-companion/face/face_brain.py`, `public/app.js` | 2 | true |
| **3** | 12 | Device verification (Tailscale + PWA install) | Runbook | 2 | false |

**Total new (unified) work:** 6 hours (plus the 17-hour existing buildout = 23 hours total).

#### 6.2 File structure (what lives where)

```
gamma-companion/
├── lib/
│   ├── push.js                    ← Web Push + HMAC signing (existing buildout)
│   ├── activityBridge.js          ← NEW: Read gamma-activity.jsonl
│   ├── operatorState.js           ← NEW: Read automation/state/* (health, bias, decisions)
│   ├── guard.js                   ← Tighten DENY_WRITE (6 lines)
│   ├── approvals.js               ← Extend with enqueueApproval (existing buildout)
│   ├── state.js                   ├─ Already reads automation/state (no change)
│   ├── escalate.js                ├─ Already has SDK + guard (no change)
│   └── ...
├── face/
│   └── face_brain.py              ← Wire operatorState into prompt context
├── public/
│   ├── app.js                     ← Register SW, subscribe to push, add operatorState calls
│   ├── styles.css                 ← Mobile-first CSS (existing buildout)
│   ├── manifest.webmanifest       ← PWA manifest (existing buildout)
│   ├── service-worker.js          ← Push handler + cache strategy (existing buildout)
│   ├── index.html                 ├─ Manifest link, SW registration
│   └── icon-*.png                 ├─ 192/512 maskable icons (existing buildout)
├── server.js                      ← Widen /api/state, add /api/push/* (buildout + merge)
├── smoke-guard.js                 ├─ Smoke tests (extend with push + wrist routes)
└── ...

automation/state/
├── engine-health.json             ← NEW (Phase 0b of blueprint, separate PR)
├── gamma-activity.jsonl           ← Already exists (heartbeat appends)
├── today-bias.json                ├─ Already exists (premarket writes)
├── decisions.jsonl                ├─ Already exists (heartbeat appends)
├── .approve-hmac.key              ← NEW (one-time gen, 32 bytes)
├── .vapid.json                    ← NEW (one-time gen, VAPID keypair + subject)
└── ...
```

#### 6.3 Key integration points

**1. The operator writes, the assistant reads:**

Heartbeat already writes:
```
automation/state/gamma-activity.jsonl
{"fired_at": "...", "tick_n": 123, "account": "Safe-2", "chart_levels": {...}, "orders_placed": [...], ...}
```

Assistant reads (every 10s):
```javascript
const activity = await readActivityBridge(10); // last 100 entries
const operatorState = await readOperatorState(); // health + bias + decisions
// Merge into /api/state response
```

**2. The voice asks questions:**

```
User: "What's my current P&L today?"
Face: reads operatorState.decisions → sums P&L → responds
→ No escalation needed, Nemotron can answer (free)

User: "Should I add to the VWAP trade?"
Face: "I should ask Claude" → escalate button
→ Claude reads all the context, looks at the chart state,
   checks the rules, says "No, size cap is hit" or "Yes, here's how"
```

**3. The operator enqueues approvals:**

```python
# In conductor.md or Chef escalation
from lib.approvals import enqueueApproval
enqueueApproval(root, {
    "id": "vwap_reclaim_2026_06_21_1",
    "title": "Ship vwap_reclaim (OOS +$840)?",
    "body": "6/6Q, WF=1.4, A/B clean, anchor-no-regression.",
    "actions": [{"label": "Approve"}, {"label": "Reject"}]
})
# This calls push.sendPush → Web Push → wrist notification
# J taps Approve → /api/approve-signed?tok=HMAC… → resolveApproval
# Conductor reads companion-decisions.jsonl → "approved" → ships it
```

---

### Part 7: Design Decisions & Tradeoffs

#### 7.1 Why NOT ngrok or a public URL

- **Ngrok:** Exposes a public URL (the guard is only a software gate; ngrok sees the raw traffic).
- **Cloudflare Tunnel:** Same risk (defaults to public).
- **Our choice:** Tailscale (private by network, not software). The server stays `127.0.0.1:4317`; Tailscale Serve is a **proxy**, not a tunnel. Port never leaves the machine. J's tailnet only.

#### 7.2 Why Web Push over ntfy.sh or FCM direct

- **ntfy.sh:** Requires a Docker host that runs 24/7 (another service to keep alive, cost risk if scaled). Our choice: use Android's built-in FCM.
- **FCM direct:** Requires a Firebase project + credentials. Web Push abstracts it (uses the browser's FCM endpoint).
- **Web Push:** VAPID keypair is local, no SaaS, no keys to rotate in the cloud, $0.

#### 7.3 Why Wear OS notification bridge (not a native app)

- **Native Wear OS app:** Would require installation on the watch, APK signing, Google Play (friction + delays).
- **Our choice:** Android auto-bridges PWA notifications to the paired watch via the notification system. Zero installation, zero approval friction.
- **Caveat:** Wear OS 3+ only (Galaxy Watch 4+). If J is on older hardware, this won't work. Test early (step 12 of the buildout).

#### 7.4 Why separate activity spine (gamma-activity.jsonl) instead of querying heartbeat logs

- **If we read heartbeat logs:** Would need to parse markdown (`automation/prompts/heartbeat.md`) in real-time, fragile.
- **Our choice:** The heartbeat already writes JSON to `gamma-activity.jsonl` (fire log, append-only). The assistant reads JSON. Schema is stable, parseable.
- **Downside:** Adds a small append-only file (immaterial, rows are ~500 bytes each, ~288 rows/day = ~150KB/day).

#### 7.5 Why the wrist route is intentionally unauthenticated (but safe)

- **The problem:** Service Worker `notificationclick` handlers run in a different scope, can't access the page's `<meta name="gamma-token">`.
- **Wrong solution:** Make the route `authed()` (won't work, token isn't available in the SW).
- **Right solution:** Use a separate signed HMAC token, single-use, per-notification. Unforgeable, can't be replayed, expires.
- **Why it's safe:** The route can do exactly one thing (resolveApproval: plain fs ops), can't reach the escalate path (code assertion + smoke-guard), and even if the token leaks, it's consumed on first use.

---

### Part 8: Security Checklist (for code review)

- [ ] `lib/guard.js` has `DENY_WRITE: [..., /\.vapid\.json$/, ...]` (tighten .key line)
- [ ] `lib/push.js` exists: `loadVapid`, `sendPush`, `mintApproveToken`, `verifyApproveToken`
- [ ] `verifyApproveToken` constant-time-compares the HMAC (not `===`)
- [ ] `verifyApproveToken` checks exp and consumed-jti (no replay)
- [ ] `/api/approve-signed` route does **not** import `runEscalation` (smoke-guard assertion prevents this)
- [ ] `/api/approve-signed` only calls `resolveApproval` (no escalate path reachable)
- [ ] `server.js` line 29 (Origin regex) accepts `GAMMA_TAILNET_HOST` env var (exact MagicDNS host, never `*.ts.net`)
- [ ] `GAMMA_TAILNET_HOST` is only set when Tailscale is up (fallback: localhost-only)
- [ ] `.vapid.json`, `.approve-hmac.key` are in `.gitignore` (never committed)
- [ ] Service Worker `push` handler calls `showNotification` with Approve/Reject actions bound to the signed-token URLs
- [ ] Companion-decisions.jsonl is appended (never mutated in-place)

---

### Part 9: Known Gotchas Locked In

1. **Tailscale must be running.** If Tailscale client on the PC or phone dies, the tunnel closes. Fallback: localhost-only (phone can't reach). Not a catastrophe; the operator still works.

2. **Watch requires phone to be nearby (Bluetooth).** The watch bridges notifications via the phone. If the phone's Bluetooth is off, the watch won't see notifications. Test during device verification.

3. **Web Push throttling.** Android throttles notifications if the PWA hasn't been opened recently (power-saving). The in-app queue (5s poll) is the source of truth; a missed push doesn't mean a missed approval.

4. **VAPID keypair rotation is not automatic.** If the keys are lost, J needs to re-generate and re-subscribe devices. Build a runbook for this (future work).

5. **HMAC key compromise = forgeable tokens.** If the key leaks, an attacker can forge approval tokens. But they can't reach the escalate path (guard blocks it) and can only resolve ONE existing queued decision. The damage is bounded.

6. **Origins that resolve to the Tailscale IP but use different hostnames are accepted.** The regex on line 29 checks the exact `GAMMA_TAILNET_HOST`. If it's pinned to `gamma.j-tailnet.ts.net`, then `gamma.j-tailnet.ts.net` is accepted but `localhost` is rejected (good). If someone DNS-rebinds to the Tailscale IP but uses a different hostname, they pass the regex check. Mitigation: Ensure `GAMMA_TAILNET_HOST` is a secret (hardcoded in launch env), not something the user supplies.

---

### Part 10: Timeline & Sequencing

**Week of 2026-06-24 (next week):**

**Phase 0: Operator state bridge** (2 hrs)
- [ ] Write `lib/operatorState.js` (read + cache engine-health.json, today-bias.json, decisions.jsonl)
- [ ] Write `lib/activityBridge.js` (read gamma-activity.jsonl, last 100 rows)
- [ ] Test both with existing automation/state/* files

**Week of 2026-07-01 (if approved):**

**Phase 1: Push infrastructure** (8 hrs, from buildout plan)
- [ ] `lib/push.js` (VAPID + HMAC + sendPush)
- [ ] Guard tightening (6 lines)
- [ ] `/api/approve-signed` route (1.5 hrs)

**Phase 2: Unified API & PWA** (6.5 hrs, from buildout plan)
- [ ] Merge `/api/state` (operator + activity + approvals)
- [ ] PWA manifest + service worker
- [ ] Mobile-first CSS

**Phase 3: Brain wiring** (2 hrs)
- [ ] Face reads operatorState, augments prompt
- [ ] App.js calls new endpoints

**Phase 4: Device gating** (2 hrs)
- [ ] Tailscale setup runbook
- [ ] PWA install + notification bridging test
- [ ] End-to-end wrist Approve test

**Total:** 20.5 hrs over 4 weeks (5-6 hrs/week). Safe to parallelize phases 0-2.

---

### Part 11: Evidence & External Validation

**From research (Section 4):**
- Home Assistant Assist proves PC-as-operator, phone-as-client, real-time state-sharing works in production
- Tailscale + LM Link proves private-by-network (not VPN tunnel) is the right pattern for LLM agents
- Web Push is standard (used by Discord, Slack, Google Drive for push notifications)
- Wear OS notification bridge is documented, tested, works on Galaxy Watch 4+

**From Gamma's own design:**
- The guard.js denylist already exists and is proven (guards the escalate path)
- The activity spine (gamma-activity.jsonl) is already being written by the heartbeat
- The operator-state files (engine-health.json, decisions.jsonl) are being produced (engine-health.json is Phase 0b of the blueprint; it's not yet live but the plumbing is clear)

**From security literature:**
- HMAC-SHA256 for signing is standard (RFC 4868, used in OAuth, JWT)
- Single-use tokens with expiry + consumed-jti set are per [OWASP Token Expiration](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html#token-expiration)
- Tailscale's WireGuard + MagicDNS is the approved pattern for homelab security (endorsed by [Tailscale's own AI agent security post](https://www.xda-developers.com/tailscale-helps-secure-ai-agents/))

---

### Summary

**The unified Gamma is:**

1. **One operator** (heartbeat, watchers, kitchen, conductor) writing live state to JSON.
2. **One assistant** (companion server on the PC) reading that state, offering voice/chat, and escalating to Claude via a guarded API.
3. **One phone app** (PWA, no Play Store) connecting via Tailscale, able to ask questions, approve decisions, and see the operator's state in real-time.
4. **One watch** (Wear OS, auto-notified) bridging from the phone, able to tap Approve/Reject with unforgeable signed tokens.

**The security model:**
- Network: Tailscale private mesh
- App: Token + origin gating
- Capability: Signed HMAC, single-use, resolveApproval-only (no escalate)
- Guard: Unchanged (blocks DENY_TOOL + DENY_WRITE)

**The cost:**
- $0 recurring (Tailscale free + Web Push free)
- $0.75/day peak (Realtime calls only during voice use)
- Fits in existing OP-3 budget

**What it enables:**
- J can ask Gamma from his phone what happened in the last 5 minutes (Nemotron, free)
- J can ask a hard question (Claude via escalation, Haiku during market hours, Sonnet after)
- J can approve a cooked edge from his wrist (one HMAC-signed token, bounds-checked)
- The operator keeps running autonomously, J is in the loop for big decisions only

This is **Jarvis**: a persistent, voice-accessible AI agent that knows what its autonomous operator is doing, can be talked to from anywhere via Tailscale, and can drive decisions back to the PC without exposing secrets or breaking the guard.

---

## Gamma Mobile + Samsung-Watch Buildout (2026-06-21)

**Date:** 2026-06-21
**Status:** Approved design — ready to build. Synthesizes 4 research agents + verified against the live `gamma-companion/` code.
**Scope:** Push notifications with Approve/Reject to J's Galaxy Watch + voice/chat from his phone, over a private reachability layer that never touches the public internet.
**OP-3 cost:** $0 recurring. Tailscale personal tier (free), Web Push via VAPID (free, no service), ntfy NOT used.

---

### 1. The final stack (one line)

**Transport = Web Push (VAPID, Node built-in `crypto`, $0) → phone PWA service worker → Wear OS auto-bridge.
Reachability = Tailscale Serve (HTTPS → 127.0.0.1:4317, private tailnet only).
App = the existing companion turned into an installable PWA (manifest + service worker + mobile CSS).**

#### Why this stack over the alternatives

- **Web Push over ntfy.sh.** Both are $0 and both auto-bridge to Wear OS. Web Push wins because (a) the Approve/Reject buttons fire **into our own service worker**, so the callback URL is same-origin (`/api/approve-signed?tok=…`) and rides the Tailscale tunnel we already need for voice — no second always-on daemon (ntfy needs a Docker host that never sleeps), no second open port, no second device-app to manage. (b) It reuses the HTTPS/Tailscale layer that voice **requires anyway** (getUserMedia needs a secure context). ntfy would be a parallel, redundant transport. (c) Zero npm deps: VAPID JWT (ES256) + aes128gcm payload encryption are doable with Node built-in `crypto`, matching `server.js`'s existing `crypto.randomBytes` usage. `web-push` (npm) is the battle-tested fallback if the hand-rolled RFC8291 encryption proves fiddly.
- **Tailscale over Cloudflare Tunnel / mDNS / raw LAN.** Cloudflare Tunnel defaults to a **public** URL — categorically unsuitable for a process that can drive Claude and holds an OpenAI key. mDNS/`http://192.168.x.x` fails the getUserMedia secure-context requirement (Android Chrome rejects HTTP outright) and breaks on roaming. Tailscale gives a private MagicDNS host with an auto-provisioned Let's Encrypt cert (secure context ✓), WireGuard device-auth, and **the server stays bound to 127.0.0.1** — Serve proxies inbound, the port is never exposed.
- **PWA over native (per the brief).** Add-to-Home-Screen + service worker + Web Push covers phone voice/chat and watch notifications with no Play Store, no Wear OS app. Wear OS has **no Tailscale client** (GitHub #3972 open) and needs none: Android auto-bridges a paired phone's notifications — action buttons included — to the watch.

---

### 2. Security model (crisp)

Three independent layers; a wrist tap can resolve an approval but **nothing reachable from a phone/watch can drive Claude**.

1. **Network boundary — Tailscale (private-by-design).** The companion stays `server.listen(PORT, "127.0.0.1", …)` (server.js:384). `tailscale serve https://gamma.<tailnet>.ts.net → http://localhost:4317` proxies inbound. Only devices in **J's tailnet** (WireGuard key signed by the control plane) can reach it. The public internet sees nothing. If Tailscale dies, the tunnel closes and the companion is localhost-only again — fails private.
2. **App boundary — token + origin (defense in depth).** `authed(req)` (server.js:27) still requires `x-gamma-token` (per-session `crypto.randomBytes(24)`) on every state-changing `/api/*` POST. The **only** change: widen the Origin regex to also accept the exact MagicDNS host (read from `GAMMA_TAILNET_HOST` env — pin the specific host, **never** a bare `.ts.net` wildcard). The page DOM has the token, so `/api/chat`, `/api/approve`, `/api/realtime-token`, and the new `/api/push/subscribe` all stay token-gated exactly as today.
3. **Capability boundary — the wrist-tap route is deliberately narrow + the guard is untouched.** This is the core design problem: a service-worker `notificationclick` fetch runs in SW global scope, has **no** access to the page's `<meta>` token, and is **not** covered by app.js's fetch wrapper — so a wrist tap physically cannot carry `x-gamma-token`. Resolution:
   - The notification's Approve/Reject action URLs carry a **signed one-time token**: `HMAC-SHA256(`id|decision|exp`)` keyed by a server-side secret, base64url-encoded. Unforgeable (HMAC), single-use (consumed-jti set persisted server-side), short-lived (~15 min exp).
   - A **new** route `GET /api/approve-signed?tok=…` validates the token (constant-time compare, exp check, replay check) and then calls **`resolveApproval(root, id, decision)` and NOTHING ELSE.** It does **not** call `authed()` (it can't — see above), and it **must refuse any `action`/`escalate` payload.**
   - **Why this is safe:** `resolveApproval` is plain `fs` (remove queue item + append to `companion-decisions.jsonl`) — it is **never an SDK tool call**, so `guard.js`'s `canUseTool`/`DENY_WRITE`/`DENY_TOOL` denylist is irrelevant to it (same reasoning the wiring-plan gives for `logActivity`). The guard **only** matters on the `action.type==='escalate'` path (server.js:283 → `runEscalation` → `makeCanUseTool`). By construction the wrist route can reach the escalate path **only if someone adds it** — so the route gets a code comment + a smoke-guard assertion that it never imports `runEscalation`. A captured-but-unforgeable URL can, at worst, approve/reject **one pre-existing queue id once** — it can never place an order (DENY_TOOL), edit doctrine/params/keys (DENY_WRITE), or spawn Claude.
   - **Guard tightening (only guard.js edit needed):** add explicit `DENY_WRITE` regexes for `.vapid.json`, `push-subscriptions.json`, and `.approve-hmac.key` so an escalated Claude can never read-modify-exfiltrate the VAPID private key or rewrite subscriptions. This only *narrows* the denylist.
   - **ID unguessability:** approval ids must be unique+nonced (e.g. `oblig-<id>-<rand>`) so a token for one card can never be replayed against a later card that reuses a base id.
   - **HMAC key choice:** key the approve-HMAC off a **persisted** `automation/state/.approve-hmac.key` (not the per-boot `GAMMA_TOKEN`) so in-flight notification tokens survive a server restart within their exp. Either is safe; persisted is chosen for UX. (`.approve-hmac.key` matches the existing `/\.key$/i` DENY_WRITE — already protected.)

**Net:** Tailscale = who can reach it. Token+origin = which page can act. Signed one-time token = the wrist can resolve exactly one queued approval and can never reopen the guard's denylist. Push is best-effort nudge; the in-app queue (polled every 5s) stays authoritative — a missed push never means a missed approval.

---

### 3. Ordered build plan

`safe_now=true` ⇒ additive, no device/Tailscale dependency, Gamma can build + unit-test immediately. `safe_now=false` ⇒ needs J's phone/watch/Tailscale to verify.

| # | Step | Files | hrs | safe_now |
|---|------|-------|-----|----------|
| 1 | **`lib/push.js` leaf module** — `loadVapid`/`loadSubs`/`saveSub` (atomic tmp+rename), `sendPush({title,body,tag,url,actions})` (RFC8291 aes128gcm + VAPID JWT via Node `crypto`; per-sub try/catch; prune on 404/410; never throws, fire-and-forget — telemetry-grade like `activity.js`), `mintApproveToken`/`verifyApproveToken` (HMAC, constant-time, exp, single-use jti set in `.approve-consumed.json`). Absent `.vapid.json` ⇒ push silently disabled ($0 no-op). | `gamma-companion/lib/push.js` (new) | 4 | true |
| 2 | **Guard tightening** — add `DENY_WRITE` regexes for `\.vapid\.json$`, `push-subscriptions\.json$`, `\.approve-hmac\.key$`; add 3 PASS cases to smoke-guard. | `gamma-companion/lib/guard.js`, `gamma-companion/smoke-guard.js` | 0.5 | true |
| 3 | **`enqueueApproval(root,item)` in approvals.js** — the missing writer. After `writeApprovals([...pending,item])`, fire-and-forget `push.sendPush` with the two signed-token actions. (Queue today has only `writeApprovals`/`resolveApproval`; nothing creates cards except seed-demo.) | `gamma-companion/lib/approvals.js` | 1 | true |
| 4 | **`resolveApproval` push-clear** — one added fire-and-forget line: `push.sendPush` a "resolved" confirmation with the **same `tag`** (`approval-<id>`) so the OS replaces/clears the still-pinned notification on every device. | `gamma-companion/lib/approvals.js` | 0.5 | true |
| 5 | **Subscription + vapid routes** — `POST /api/push/subscribe` (gated by existing `authed()` — page has the token) → `push.saveSub`; `GET /api/push/vapid-public` (authed) → public key for `pushManager.subscribe`. | `gamma-companion/server.js` | 1 | true |
| 6 | **Wrist-tap route** — `GET /api/approve-signed?tok=…` ABOVE the `serveStatic` fallback (server.js:371). NO `authed()`. `verifyApproveToken` → 403 on fail → else `resolveApproval(id,decision)` + mark consumed → tiny 200 HTML "Logged — close this." Code comment + smoke-guard assertion: never imports `runEscalation`. | `gamma-companion/server.js`, `gamma-companion/smoke-guard.js` | 1.5 | true |
| 7 | **Origin allowlist widen** — server.js:29 regex also accepts the exact `GAMMA_TAILNET_HOST` (env, pinned host, not `*.ts.net`). Falls back to localhost-only when env empty. | `gamma-companion/server.js` | 0.5 | true |
| 8 | **Obligation rising-edge push** — in the `/api/state` handler, diff newly-red obligation ids vs `.push-seen.json`, `push.sendPush` on the rising edge only, rate-limited per id. Keep `state.js` a pure read. | `gamma-companion/server.js` | 1 | true |
| 9 | **PWA shell** — `public/manifest.webmanifest` (display:standalone, start_url `/`, theme-color, 192+512 maskable icons generated from the Gamma SVG); `public/service-worker.js` (`install` precache; `fetch` cache-first assets / network-first `/api/*`; `push` handler → `showNotification` with Approve/Reject actions; `notificationclick` → `fetch(event.action url)`); `index.html` head gets manifest link + apple-mobile meta + SW registration; app.js gets an "Enable wrist alerts" button that calls `Notification.requestPermission` + `pushManager.subscribe` + POSTs to `/api/push/subscribe`. | `public/manifest.webmanifest` (new), `public/service-worker.js` (new), `public/index.html`, `public/app.js`, `public/icon-192.png`/`icon-512.png` (new) | 3 | true |
| 10 | **Mobile-first responsive CSS** — base single-column flex; `@media (min-width:768px)` 2-col; `@media (min-width:1200px)` restore gridstack; `@media (max-width:280px)` watch (hide hero, mic bottom-right, compress); 44px touch targets, `#chat-input` 16px (no iOS zoom). | `public/styles.css` | 2.5 | true |
| 11 | **Conductor enqueue contract** — one-line instruction so the engine raises approvals via `node -e "require('./lib/approvals').enqueueApproval(...)"` instead of editing `dashboard-dialogue.json`. Wires the push pipeline to the real engine. | `automation/prompts/conductor.md`, `setup/scripts/run-conductor.ps1` | 1 | true |
| 12 | **Device verification** — Tailscale up (desktop+phone), `tailscale serve`, set `GAMMA_TAILNET_HOST`, J generates `.vapid.json`, install PWA on phone, grant notifications, verify watch bridge, end-to-end wrist Approve writes to `companion-decisions.jsonl`. | (no files — runbook below) | 2 | false |

**Total Gamma-buildable now (steps 1–11): ~17 hrs. Device-gated (12): ~2 hrs.**
**Critical path to value:** 1 → 3 → 5 → 6 → 9 → 12 (push + wrist approve). Voice/chat is already built — it only needs steps 7, 9, 10, 12 (Tailscale + PWA + responsive).

---

### 4. J device-steps (app by app, in order)

**A. Desktop (one-time):**
1. Install Tailscale (Windows MSI, tailscale.com/download/windows) → `tailscale up` (browser SSO) → note tailnet from `tailscale status`.
2. `tailscale serve https://gamma.<tailnet>.ts.net:443 http://localhost:4317`.
3. Set `GAMMA_TAILNET_HOST=gamma.<tailnet>.ts.net` and `GAMMA_BIND_HOST` stays `127.0.0.1` in the companion launch env.
4. Generate the VAPID keypair on-machine (`npx web-push generate-vapid-keys` or the 5-line Node `crypto` script Gamma provides) → drop at `automation/state/.vapid.json` `{publicKey, privateKey, subject:"mailto:jack.watergun@gmail.com"}`. Born on J's machine, never in a transcript.
5. Create `automation/state/.approve-hmac.key` (32 random bytes) once.

**B. Android phone:**
6. Install Tailscale (Google Play) → `tailscale up` (same tailnet, auto-auth).
7. Chrome → `https://gamma.<tailnet>.ts.net/` → confirm green lock (secure context) → menu → **Install app** (Add to Home Screen).
8. Open the installed PWA → tap **"Enable wrist alerts"** → **Grant** notification permission (must be a user gesture or `pushManager.subscribe` fails).
9. Voice smoke-test: tap mic, speak, confirm `ask_gamma` round-trips.

**C. Samsung Galaxy Watch (Wear OS):**
10. Confirm the watch is paired to this phone (standard Wear OS setup).
11. In the Galaxy Wearable app → Notifications → ensure Chrome/PWA notification bridging is **on**. No app install — bridging is a per-device toggle.
12. End-to-end: trigger a test approval → Approve/Reject buttons appear on the wrist → tap Approve → confirm a row lands in `automation/state/companion-decisions.jsonl`.

---

### 5. Gotchas locked in (from research, de-duped)

- **Wrist route is the one intentionally-unauthenticated endpoint** — safe ONLY because the token is unforgeable + single-use + exp-bounded AND the route can do exactly one thing. If anyone later adds escalate handling there, it reopens the exact hole guard.js exists to close → smoke-guard assertion guards this.
- **Single-use enforced server-side** — `resolveApproval` re-resolving a removed id still appends a duplicate decision row, so `verifyApproveToken` must persist + check a consumed-jti set; short exp stops a stale tap approving a later id-reusing card.
- **Push is best-effort** — Android throttles push if the PWA hasn't been opened recently; the 5s-polled in-app queue stays the source of truth.
- **Never block the primary write on push** — `sendPush` does network I/O to FCM/Mozilla endpoints; every call site is fire-and-forget, never awaited on the critical path, never throws.
- **Pin the Origin host** — exact MagicDNS host from env, never `*.ts.net`, or you accept any tailnet's origin.
- **Tailscale-dead = localhost-only** (good: fails private). Hard-coded `.ts.net` refs won't resolve when Tailscale is off — keep them env-driven.
- **Watch must be phone-paired**; Wear OS has no Tailscale client and needs none (phone bridges).

---

### 6. Map to existing code (verified 2026-06-21)

- `authed()` server.js:27-31, Origin regex line 29 — widen here.
- `resolveApproval` lib/approvals.js:50-76 — the single approve chokepoint for BOTH UI and wrist; `decision` is `'approve'|'reject'` (NOT `'approved'`), validated server.js:279.
- The escalate/guard path is server.js:283 (`action.type==='escalate'` → `runEscalation` → `makeCanUseTool`) — the wrist route must never reach it.
- `guard.js` DENY_WRITE line 25, DENY_TOOL line 34 — add the 3 key/subscription regexes.
- `serveStatic` fallback server.js:371 — wrist route goes ABOVE it.
- Token injected into `<meta name="gamma-token">` (serveStatic:88), wrapped by app.js:8-16 — confirms the SW cannot carry it ⇒ signed-token design is mandatory, not optional.
- `enqueueApproval` does NOT exist yet; only `writeApprovals`/`resolveApproval` + `seed-demo.js` write the queue. The conductor writes `dashboard-dialogue.json`, not approvals — step 11 wires the real producer.

This buildout is fully additive: nothing changes the trading engine, doctrine, params, or the guard's behavior except to *tighten* it.

---

## Watch → Build Pipeline Validation — 2026-06-21 (2026-06-21)

> Synthesis of a 4-area rigorous code audit of `gamma-companion/`. Every claim below was verified against the actual source (file + line). Honest picture: the **desktop build chokepoint is genuinely solid**; the **watch/phone path is broken at three hard points** and the headline "talk from my watch → it builds → it tells me what it did" loop is **not closed today**.

---

### The one-line truth

The engine that turns a request into a built file works and is well-guarded **on the desktop**. But the watch/phone can't actually reach it (403), the phone screen has no way to type a build or see a result, the voice loop never speaks the outcome, and the guard that protects doctrine/keys is bypassable with one Bash command. "Seamless from the watch" is **PARTIAL → MISSING**, not done.

---

### VALIDATION MATRIX — every hop of watch → build

| # | Part of the chain | Status | Note (file:line) |
|---|---|---|---|
| 1 | Watch push notification + tappable Approve/Reject | **WORKS** | `lib/push.js` RFC8291/8292 encryption + `/api/approve-signed` (server.js:492) HMAC single-use signed link. The ONE deliberately-unauthed route, scoped to `resolveApproval` only. Solid. |
| 2 | Reach PC over HTTPS (Tailscale Serve → localhost:4317) | **PARTIAL** | Designed clean (auto-TLS, MagicDNS `dabox.tail2641b2.ts.net`). But `tailscale serve` has not been confirmed run, and the origin gate below blocks it anyway. |
| 3 | Cross-origin auth gate for tailnet | **MISSING** | `originAllowed()` (server.js:32) allows localhost OR exact `GAMMA_TAILNET_HOST`. That env var is read at server.js:31 and **set by NOBODY** — `LAUNCH-COMPANION.vbs` runs `node server.js` with no env; `desktop/main.js:13` requires server.js with no env. → every cross-origin `/api/chat` from the tailnet 403s. **Watch/phone build flow dies at the first hop.** |
| 4 | Phone/watch can TYPE a build request | **MISSING** | `public/m.html` has NO text input, NO `/api/chat` call, NO `ask_id` tracking (it only renders approvals + the mic). A typed build from the phone is impossible. |
| 5 | Voice request → ask_gamma → /api/chat | **WORKS** | `realtime.js:82-102` routes `response.function_call_arguments.done` → POST `/api/chat`. Live-proven: `companion-ask-results.jsonl` shows real Opus/Sonnet/Haiku builds completed today. |
| 6 | Free FACE reliably escalates real build requests | **PARTIAL** | `face_brain.py` parse depends on a free 30–120B model emitting an exact ```` ```escalate {json} ```` block. No fallback heuristic. AND `parse_escalation` only guards `if not task` — it **accepted the literal `<precise, self-contained instruction…>` placeholder today** (ask-mqns25hv), burning a full Opus run. |
| 7 | Escalate → Claude Agent SDK build | **WORKS** | `escalate.js:91 runEscalation` → `query({prompt, options:{model,cwd,canUseTool,abortController}})`. Durable result → `companion-ask-results.jsonl` + activity spine. Clean chokepoint. |
| 8 | Guard at the SDK boundary | **PARTIAL** | `guard.js` IS enforced at the real `canUseTool` boundary (not prose, not bypassPermissions); `smoke-guard.js` asserts 18 cases. BUT it only inspects `file_path` on Write/Edit/MultiEdit/NotebookEdit. **Bash is unconditionally allowed** → `echo x >> CLAUDE.md`, `cat .approve-hmac.key`, `cp /tmp/p params.json` all defeat the denylist. #1 security hole. |
| 9 | Halt kill-switch | **WORKS** | `companion-halt.flag` checked in `guard.makeCanUseTool` AND at top of `runEscalation` (escalate.js:97). Belt + suspenders. |
| 10 | Cancel a running build | **WORKS (desktop)** | Per-task `AbortController` in `controllers` Map; `cancelTask` → `ac.abort()`; catch distinguishes `ac.signal.aborted` → "(cancelled by you)". Desktop UI wires it. No phone cancel UI. |
| 11 | Concurrency / overflow handling | **PARTIAL** | `MAX_INFLIGHT=2`; 3rd request is **dropped** with "(busy…)", not queued. On voice the busy result is never spoken → 3rd voice request vanishes silently. |
| 12 | Per-task SDK timeout | **MISSING** | `runEscalation` awaits the full `query()` stream with only the user AbortController. A hung build holds an inflight slot forever; two hung builds wedge the whole pipeline until restart. |
| 13 | State durability across restart | **MISSING** | `tasks`/`controllers`/`inflight` are in-memory only. Server restart / PC sleep-wake orphans the in-flight build, resets inflight to 0, and leaves the UI spinning on a result that may never be written. |
| 14 | SDK auth/credit failure handling | **MISSING** | `query()` runs with no explicit auth. Credential lapse/credit-cliff (the exact 06-17 heartbeat failure) throws → generic "(escalation error…)". Indistinguishable from a build failure, unmonitored on the live path. |
| 15 | Result polling (desktop) | **WORKS** | `app.js trackAsk` polls `/api/ask-result` every 4s, 150 tries (~10min) then logs gracefully. |
| 16 | Result delivered to phone/watch | **MISSING** | m.html has no feed/result view. Voice path (realtime.js:94) is fire-and-forget — says "lands in the feed" and never polls or speaks the outcome. The loop is open-ended on J's actual device. |
| 17 | "What's cooking / up next" visible on FACE (voice/chat) | **MISSING** | `summarize()` (state.js:214) reads only verdict/accounts/kitchen-COUNTS/spend/approvals/feed. `state.build`, `state.claude`, `state.obligations` are bolted onto the **/api/state HTTP response** (server.js:300-307) — never onto the object `summarize()` reads. Voice literally cannot answer J's two named questions. |
| 18 | "What's cooking" = in-flight kitchen task | **PARTIAL** | state.js maps `recent_completed_top_10` but ignores `current_task_id` and `by_priority_pending`. Shows "N done, M pending", not what's cooking right now. |
| 19 | "Up next" visible on phone | **MISSING** | m.html refresh() reads `s.approvals` and discards `s.build` / `s.claude` / `s.kitchen`. Data arrives in the payload; it's dropped client-side. |
| 20 | Scheduled-tasks "what fires next" | **MISSING** | Zero references to `SCHEDULED-TASKS.md` / `scheduled-tasks-audit.json` anywhere in gamma-companion. Never surfaced. |
| 21 | Multi-turn build conversation memory | **MISSING** | `realtime.js` sends no `history`; every escalation is a FRESH `query({prompt})` with no `resume`. J cannot say "now add a stop-loss to that". Specced `lib/deepsession.js` (warm resumable Claude) **does not exist** (confirmed: no file). |
| 22 | Autobuild build-queue drains autonomously | **MISSING** | `autobuild.js` (lines 16-18, by design) "ONLY reads the queue and flips one task's status. It NEVER spawns Claude." Nothing calls `runEscalation` for queued tasks → `state.build.queue` sits pending forever. |
| 23 | Ephemeral-token field mapping | **PARTIAL** | realtime.js:27 reads `tok.value`; server.js:449 returns raw OpenAI JSON unmodified. If the API nests under `{client_secret:{value}}`, `tok.value` is undefined → voice silently fails "no token". Unverified external contract. |
| 24 | Realtime model/voice ids | **PARTIAL** | `gpt-realtime-2` / `marin` (server.js:413,417) hardcoded, unverified, not env-overridable. A rename = opaque 400 for ALL users. |
| 25 | PWA service worker on phone | **PARTIAL** | `service-worker.js` exists + registered in `index.html:186` — but **NOT registered in m.html** (grep confirms index.html only). Phone view has no offline fallback / install path. |
| 26 | Per-process token vs cached PWA | **PARTIAL** | `GAMMA_TOKEN = crypto.randomBytes` per server start, injected into HTML `<head>` at serve time. A cached m.html from a prior run carries a stale token → every authed POST 403s after any restart until hard reload. |
| 27 | Mic on Wear OS watch (WebRTC getUserMedia) | **MISSING/UNVERIFIED** | No evidence getUserMedia works in a Wear OS browser. Untested external assumption. |
| 28 | PNG icons on disk | **WORKS** | `public/icon-192.png` + `icon-512.png` present (earlier gap now closed). |

---

### "WHERE'S THE WATCH APP?" — the straight answer

**There is no native Wear OS app, and there should not be one yet.** What exists for the watch:

1. **Push notifications — REAL and working.** End-to-end encrypted, fire to every subscribed device including the watch, with tappable Approve/Reject in the native notification shade via the signed `/api/approve-signed` route. This is the genuine watch surface today.
2. **`m.html` (the "phone view")** is a 240px web page — openable in a Wear OS browser but unusable at ≤280px (robot alone renders ~174px wide), and it can only show approvals + a mic. It is NOT a watch app.
3. A **native Wear OS app** (Tile/complication/Kotlin) is a **60–80h** build and is overkill for 0DTE — the notification path is the right watch UX.

**The honest gap:** even the *notification* watch path can't currently kick off a build, because (a) the tailnet origin is 403'd (`GAMMA_TAILNET_HOST` never set) and (b) the voice/phone loop never returns the result. So today the watch can approve a card, but "talk from my watch → it builds → it tells me" does not complete.

**Recommended path:** Do NOT build a native watch app. Make the existing surfaces bulletproof in this order — (1) set `GAMMA_TAILNET_HOST` + persist `GAMMA_TOKEN` so the watch/phone can reach the PC at all; (2) build the `m.html` chat + result + push-on-completion loop so a request closes the loop on the wrist; (3) wire voice to speak the result; (4) harden the guard/queue/timeout/auth. That delivers the Jarvis loop on the watch J already owns, at ~$0 and ~2 focused days, vs 60–80h for native.

---

### RANKED ROADMAP TO SEAMLESS

1. **Set `GAMMA_TAILNET_HOST` in every launcher** — without it the watch/phone build path 403s at the auth gate. Add to `LAUNCH-COMPANION.vbs` (`sh.Environment("PROCESS")("GAMMA_TAILNET_HOST")="dabox.tail2641b2.ts.net"` before `sh.Run`) and `desktop/main.js` (`process.env.GAMMA_TAILNET_HOST ||= ...` before `require(server.js)`). Verify with a real cross-origin curl.
2. **Persist `GAMMA_TOKEN`** to a gitignored `automation/state/.gamma-token` (or add `/api/token` + retry-once on 403) so a cached PWA stays valid across restarts; make m.html/index.html network-first so the injected token is never stale.
3. **Build the `m.html` build loop** — add a text input + `send()` → POST `/api/chat`, on `escalate` poll `/api/ask-result` (port `app.js trackAsk`), render the result card, and a "Claude is working" strip from `state.claude.running`. This is the device J actually uses.
4. **Fire a Web Push on escalation completion** — in `escalate.js appendResult`, when origin is chat/voice/card, `push.sendPush` the truncated summary keyed on `ask_id`, so the watch/voice loop closes without needing the desktop feed.
5. **Add a Bash inspector to `guard.js`** — block redirection/mv/cp/rm/tee/sed -i/git checkout targeting any `DENY_WRITE` path, and any read of `*.key`/`.vapid.json`/`.approve-hmac.key`/`push-subscriptions.json`. Add cases to `smoke-guard.js`. Closes the #1 security hole.
6. **Feed enriched state into `summarize()`** — factor `buildEnrichedState(ROOT)` (build + claude + obligations + kitchen current_task) and call `summarize(enriched)` in `/api/chat`. Add "What's cooking now" + "Up next" blocks. Without this voice cannot answer J's two named questions.
7. **Classify SDK auth/credit failures** — in `escalate.js` catch, if `/401|403|auth|credit|unauthorized|login/i`, write a distinct "(Claude auth/credit problem — re-login/top-up; build NOT run)" summary + Web Push. Add a periodic SDK health check → obligation card.
8. **Replace inflight-drop with a bounded FIFO queue** in `escalate.js` (cap ~10, status "queued", drain on `inflight--`); bump `MAX_INFLIGHT` to 3–4; make queued status pollable. Stops the silent 3rd-request drop on voice.
9. **Per-task SDK watchdog timeout** (10–20 min, env-configurable) → `ac.abort()` + "(timed out…)" result, freeing the slot. Stops two hung builds wedging the pipeline.
10. **Restart reconciliation** — on boot, scan `companion-asks.jsonl` vs `companion-ask-results.jsonl` for ask ids with no result, write a synthetic "(interrupted by a server restart)" result so `trackAsk` resolves instead of spinning forever.
11. **Placeholder-task guard in `face_brain.py`** — reject tasks containing `<…>` angle-bracket placeholders or the "precise, self-contained instruction" sentinel; on voice fold J's spoken words into the task. Plus a server-side build-intent regex safety net in `/api/chat` for missed escalations.
12. **Add kitchen `current_task` + `pending_by_priority`** to `buildState` and a "Kitchen cooking now" line to `summarize()`.
13. **Render build/claude/kitchen on `m.html`** — additive "Now / Next" card from the already-arriving `/api/state` payload.
14. **Multi-turn memory** — keep a rolling transcript passed as `history`; build `lib/deepsession.js` wrapping the Agent SDK with `options.resume` keyed per voice session so "now change that" works. Highest-value for true Jarvis conversation.
15. **Voice result callback** — realtime.js polls `/api/ask-result?id=<ask_id>` and on done injects `conversation.item.create` + `response.create` so the model speaks "that build is done — <summary>".
16. **Normalize ephemeral-token shape + pin/env model+voice ids** in `/api/realtime-token`; surface the OpenAI error body in the toast. Removes the two opaque single-point voice failures.
17. **Register the service worker in `m.html`** (5 min) + make `/api/` network-first; add an autobuild drainer (gated on halt flag) so `state.build.queue` actually runs.
18. **Add `lib/schedule.js`** reading `scheduled-tasks-audit.json` → `state.schedule` + a "Scheduled next" line, so "what's up next" includes upcoming Gamma_* fires.

---

### Bottom line

The **build chokepoint itself is the strong part** — guard at the real boundary, deterministic test, working cancel, durable results, graceful degradation to logged messages. The weakness is entirely in **reach and round-trip on the watch/phone**: the tailnet is 403'd, the phone has no build/result UI, the voice loop never speaks the outcome, the FACE brain is blind to what's cooking, and the guard is one `Bash` command from being defeated. Closing items 1–6 makes the watch loop actually work and safe; 7–18 make it bulletproof and conversational. None of it requires a native watch app.
