# Watch → Build Pipeline Validation — 2026-06-21

> Synthesis of a 4-area rigorous code audit of `gamma-companion/`. Every claim below was verified against the actual source (file + line). Honest picture: the **desktop build chokepoint is genuinely solid**; the **watch/phone path is broken at three hard points** and the headline "talk from my watch → it builds → it tells me what it did" loop is **not closed today**.

---

## The one-line truth

The engine that turns a request into a built file works and is well-guarded **on the desktop**. But the watch/phone can't actually reach it (403), the phone screen has no way to type a build or see a result, the voice loop never speaks the outcome, and the guard that protects doctrine/keys is bypassable with one Bash command. "Seamless from the watch" is **PARTIAL → MISSING**, not done.

---

## VALIDATION MATRIX — every hop of watch → build

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

## "WHERE'S THE WATCH APP?" — the straight answer

**There is no native Wear OS app, and there should not be one yet.** What exists for the watch:

1. **Push notifications — REAL and working.** End-to-end encrypted, fire to every subscribed device including the watch, with tappable Approve/Reject in the native notification shade via the signed `/api/approve-signed` route. This is the genuine watch surface today.
2. **`m.html` (the "phone view")** is a 240px web page — openable in a Wear OS browser but unusable at ≤280px (robot alone renders ~174px wide), and it can only show approvals + a mic. It is NOT a watch app.
3. A **native Wear OS app** (Tile/complication/Kotlin) is a **60–80h** build and is overkill for 0DTE — the notification path is the right watch UX.

**The honest gap:** even the *notification* watch path can't currently kick off a build, because (a) the tailnet origin is 403'd (`GAMMA_TAILNET_HOST` never set) and (b) the voice/phone loop never returns the result. So today the watch can approve a card, but "talk from my watch → it builds → it tells me" does not complete.

**Recommended path:** Do NOT build a native watch app. Make the existing surfaces bulletproof in this order — (1) set `GAMMA_TAILNET_HOST` + persist `GAMMA_TOKEN` so the watch/phone can reach the PC at all; (2) build the `m.html` chat + result + push-on-completion loop so a request closes the loop on the wrist; (3) wire voice to speak the result; (4) harden the guard/queue/timeout/auth. That delivers the Jarvis loop on the watch J already owns, at ~$0 and ~2 focused days, vs 60–80h for native.

---

## RANKED ROADMAP TO SEAMLESS

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

## Bottom line

The **build chokepoint itself is the strong part** — guard at the real boundary, deterministic test, working cancel, durable results, graceful degradation to logged messages. The weakness is entirely in **reach and round-trip on the watch/phone**: the tailnet is 403'd, the phone has no build/result UI, the voice loop never speaks the outcome, the FACE brain is blind to what's cooking, and the guard is one `Bash` command from being defeated. Closing items 1–6 makes the watch loop actually work and safe; 7–18 make it bulletproof and conversational. None of it requires a native watch app.
