# Gamma Jarvis Unification — One Gamma, Two Faces

**Date:** 2026-06-21
**Status:** Build plan — synthesizes 4 design pillars, verified head-to-toe against the live `gamma-companion/` + `automation/` code.
**Goal:** Collapse the "two Gammas" (the autonomous OPERATOR and the conversational ASSISTANT) into ONE assistant J can talk to from his Samsung watch / phone that (a) KNOWS exactly what the operator is doing, (b) lets him brainstorm by voice like talking to Claude, (c) drives the real Claude on the always-on PC to keep the project moving while he's away.
**OP-3 cost:** $0 recurring. Only true $ spend is OpenAI Realtime audio minutes (J's own key, bounded by talk time) + Max-pool rate-limit budget on escalations J explicitly triggers.

---

## Headline

One autonomous operator + one voice assistant + one phone/watch PWA, fused over a shared filesystem spine and a single guarded escalation chokepoint — J talks to Gamma from his wrist, sees every operator move, and approves irreversible changes with a tap. Tailscale-private, guard-held, $0.

---

## What ALREADY exists (honest inventory — the skeleton is mostly built)

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
| **Mobile/watch reach design** | `markdown/planning/GAMMA-MOBILE-WATCH-BUILDOUT-2026-06-21.md` | DESIGNED (approved, not built). Web Push (VAPID, Node crypto, $0) → PWA service worker → Wear OS bridge; Tailscale Serve → `127.0.0.1:4317`; signed single-use HMAC wrist route. |

**Net:** the spine, the guard, the escalation chokepoint, the approval queue, the obligation cards, the voice channel, and the SDK resume primitives are all already present. The four missing connections are: (1) the operator never writes the spine; (2) the face summary is too narrow to "know everything"; (3) escalation is stateless one-shot, not a warm Claude conversation; (4) the two approval ledgers never merge and there's no wrist reach.

---

## The four seams to close (and the order that maximizes leverage)

1. **SHARED CONTEXT SPINE** — make the operator write the spine + widen `summarize()` so the assistant literally sees every move. *Mostly a `state.js` widen + a tiny Python logger. The literal ask. #1.*
2. **UNIFIED BRAIN** — a warm, resumable, streaming Claude session (deep mode) for brainstorm turns; free face kept as router/glue; market-hours starvation guard.
3. **ALWAYS-ON LOOP + ONE ACTION BUS** — voice→tracked-task→push-report-back; merge the two approval ledgers into one wrist-resolvable queue.
4. **REACH LAYER** — Web Push + PWA + Tailscale (the mobile buildout doc), so all of the above lands on the wrist. Device-dependent → last.

---

## Build order (ranked)

> `safe_now` = additive, no device dependency, no doctrine/order surface, ships today under the auto-ratify gate. The heartbeat-prompt edit and the device runbook are the only non-safe-now items.

### Phase A — Shared context spine ($0, all defensive, the literal ask)

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

### Phase B — Unified brain (warm resumable Claude + market-hours guard)

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

### Phase C — Always-on loop + one action bus

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

### Phase D — Reach layer (Web Push + PWA + Tailscale; device-dependent → last)

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

## J's device steps (one-time, in order)

1. **Tailscale** — install on the always-on PC and the Galaxy phone; sign both into the same tailnet (free personal tier, $0). On the PC: `tailscale serve https://gamma.<tailnet>.ts.net → http://127.0.0.1:4317` (server stays bound to localhost; Serve proxies inbound; auto Let's Encrypt cert = secure context for the mic).
2. **Set `GAMMA_TAILNET_HOST`** env on the PC to the exact MagicDNS host (e.g. `gamma.j-tailnet.ts.net`) so the Origin allowlist pins it — never a wildcard.
3. **Generate keys on-machine** (never in any transcript): `.vapid.json` (VAPID keypair) and `.approve-hmac.key` (32 random bytes) into `automation/state/` via the provided Node crypto script.
4. **Install the PWA** — open `https://gamma.<tailnet>.ts.net` in phone Chrome → Add to Home Screen → launch the installed app → grant notification permission → tap "Enable wrist alerts" (subscribes the device).
5. **Pair the Galaxy Watch** (standard Wear OS) and enable notification bridging in the Galaxy Wearable app so phone notifications + their Approve/Reject action buttons surface on the wrist.
6. **Verify** — trigger a test approval; confirm the wrist buzzes with Approve/Reject; tap Approve; check the correct ledger logged it. (Wear OS notification-action bridging on J's specific watch model is the one unverified assumption — this step confirms it.)

No app store, no Wear OS app, no second daemon, no public port.

---

## Security + cost model

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

## Why this order

Phase A is #1 because it IS the literal ask ("the assistant knows everything") and it's the cheapest, most defensive, no-device work — a `state.js` widen + a ~100-line Python logger + four one-line operator appends, all $0, all fail-safe, gym-testable today. It also unlocks everything downstream: deep mode (B) and the always-on loop (C) are only as smart as the context the brain receives, and the reach layer (D) is only worth building once the assistant has something complete to say from the wrist.
