# Gamma Mobile + Samsung-Watch Buildout

**Date:** 2026-06-21
**Status:** Approved design — ready to build. Synthesizes 4 research agents + verified against the live `gamma-companion/` code.
**Scope:** Push notifications with Approve/Reject to J's Galaxy Watch + voice/chat from his phone, over a private reachability layer that never touches the public internet.
**OP-3 cost:** $0 recurring. Tailscale personal tier (free), Web Push via VAPID (free, no service), ntfy NOT used.

---

## 1. The final stack (one line)

**Transport = Web Push (VAPID, Node built-in `crypto`, $0) → phone PWA service worker → Wear OS auto-bridge.
Reachability = Tailscale Serve (HTTPS → 127.0.0.1:4317, private tailnet only).
App = the existing companion turned into an installable PWA (manifest + service worker + mobile CSS).**

### Why this stack over the alternatives

- **Web Push over ntfy.sh.** Both are $0 and both auto-bridge to Wear OS. Web Push wins because (a) the Approve/Reject buttons fire **into our own service worker**, so the callback URL is same-origin (`/api/approve-signed?tok=…`) and rides the Tailscale tunnel we already need for voice — no second always-on daemon (ntfy needs a Docker host that never sleeps), no second open port, no second device-app to manage. (b) It reuses the HTTPS/Tailscale layer that voice **requires anyway** (getUserMedia needs a secure context). ntfy would be a parallel, redundant transport. (c) Zero npm deps: VAPID JWT (ES256) + aes128gcm payload encryption are doable with Node built-in `crypto`, matching `server.js`'s existing `crypto.randomBytes` usage. `web-push` (npm) is the battle-tested fallback if the hand-rolled RFC8291 encryption proves fiddly.
- **Tailscale over Cloudflare Tunnel / mDNS / raw LAN.** Cloudflare Tunnel defaults to a **public** URL — categorically unsuitable for a process that can drive Claude and holds an OpenAI key. mDNS/`http://192.168.x.x` fails the getUserMedia secure-context requirement (Android Chrome rejects HTTP outright) and breaks on roaming. Tailscale gives a private MagicDNS host with an auto-provisioned Let's Encrypt cert (secure context ✓), WireGuard device-auth, and **the server stays bound to 127.0.0.1** — Serve proxies inbound, the port is never exposed.
- **PWA over native (per the brief).** Add-to-Home-Screen + service worker + Web Push covers phone voice/chat and watch notifications with no Play Store, no Wear OS app. Wear OS has **no Tailscale client** (GitHub #3972 open) and needs none: Android auto-bridges a paired phone's notifications — action buttons included — to the watch.

---

## 2. Security model (crisp)

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

## 3. Ordered build plan

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

## 4. J device-steps (app by app, in order)

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

## 5. Gotchas locked in (from research, de-duped)

- **Wrist route is the one intentionally-unauthenticated endpoint** — safe ONLY because the token is unforgeable + single-use + exp-bounded AND the route can do exactly one thing. If anyone later adds escalate handling there, it reopens the exact hole guard.js exists to close → smoke-guard assertion guards this.
- **Single-use enforced server-side** — `resolveApproval` re-resolving a removed id still appends a duplicate decision row, so `verifyApproveToken` must persist + check a consumed-jti set; short exp stops a stale tap approving a later id-reusing card.
- **Push is best-effort** — Android throttles push if the PWA hasn't been opened recently; the 5s-polled in-app queue stays the source of truth.
- **Never block the primary write on push** — `sendPush` does network I/O to FCM/Mozilla endpoints; every call site is fire-and-forget, never awaited on the critical path, never throws.
- **Pin the Origin host** — exact MagicDNS host from env, never `*.ts.net`, or you accept any tailnet's origin.
- **Tailscale-dead = localhost-only** (good: fails private). Hard-coded `.ts.net` refs won't resolve when Tailscale is off — keep them env-driven.
- **Watch must be phone-paired**; Wear OS has no Tailscale client and needs none (phone bridges).

---

## 6. Map to existing code (verified 2026-06-21)

- `authed()` server.js:27-31, Origin regex line 29 — widen here.
- `resolveApproval` lib/approvals.js:50-76 — the single approve chokepoint for BOTH UI and wrist; `decision` is `'approve'|'reject'` (NOT `'approved'`), validated server.js:279.
- The escalate/guard path is server.js:283 (`action.type==='escalate'` → `runEscalation` → `makeCanUseTool`) — the wrist route must never reach it.
- `guard.js` DENY_WRITE line 25, DENY_TOOL line 34 — add the 3 key/subscription regexes.
- `serveStatic` fallback server.js:371 — wrist route goes ABOVE it.
- Token injected into `<meta name="gamma-token">` (serveStatic:88), wrapped by app.js:8-16 — confirms the SW cannot carry it ⇒ signed-token design is mandatory, not optional.
- `enqueueApproval` does NOT exist yet; only `writeApprovals`/`resolveApproval` + `seed-demo.js` write the queue. The conductor writes `dashboard-dialogue.json`, not approvals — step 11 wires the real producer.

This buildout is fully additive: nothing changes the trading engine, doctrine, params, or the guard's behavior except to *tighten* it.
