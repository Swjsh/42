# Unifying Gamma: The JARVIS Design — 2026-06-21

**Status:** Research synthesis + concrete architecture design. Builds on the existing `gamma-companion` (v0 shipped) and the validated mobile buildout plan (`GAMMA-MOBILE-WATCH-BUILDOUT-2026-06-21.md`). This document covers the **operator↔assistant unification**, the **voice+brainstorm→action loop**, and the **security model** for an always-on AI agent that can drive a home PC from a phone/watch.

**What you get:** A single unified Gamma that J can talk to from his wrist, that knows exactly what the autonomous operator is doing, that brainstorms with Claude-grade thinking, and that pushes actions back to the PC to execute — all without exposing private keys or doctrine to the phone, and without starving the live heartbeat. $0 recurring cost (Tailscale free, Web Push free). Proven patterns from Home Assistant, NautilusTrader, and Anthropic's own agent guidance.

---

## Part 1: The Unified Gamma Architecture

### 1.1 Today's two-Gamma problem

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

### 1.2 The unified design: "Gamma is the operator's voice + eyes"

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

### 1.3 The contract: activity spine + shared state

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

## Part 2: Voice + Brainstorm → Action Loop

### 2.1 The conversation arc (the "ask Gamma" flow)

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

### 2.2 The approval case (the other 5%)

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

## Part 3: Security Model (defense in depth)

### 3.1 The three-layer sandwich

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

### 3.2 Key material management

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

### 3.3 Guard tightening (6 lines of code)

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

## Part 4: Proven Patterns from the Wild (2025-2026)

### 4.1 Home Assistant + Assist (local voice control on your home PC)

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

### 4.2 Tailscale + LM Link (remote access to local LLMs safely)

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

### 4.3 OpenAI Realtime API + WebRTC (phone voice to Claude)

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

### 4.4 Web Push (notifications on phone + watch, $0 cost)

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

### 4.5 PWA (Installable web app, no Play Store, stays on home screen)

**What it does:** A web app (HTML + CSS + JS) can be installed on Android via "Add to Home Screen." It runs in a full-screen standalone mode (no address bar), has a home screen icon, and can register a Service Worker to cache assets and handle background events (like push notifications).

**Why for Gamma:** Zero app store friction, zero review delays, works on phone and watch (watch gets notifications auto-bridged), can be updated by pushing new HTML/CSS/JS (no rebuild, no APK).

**Sources:**
- [PWA Install Capability (Chrome Developers)](https://developers.google.com/web/fundamentals/app-install-prompts)
- [Web App Manifest (MDN)](https://developer.mozilla.org/en-US/docs/Web/Manifest)
- [Service Worker Lifecycle (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API)

---

## Part 5: Cost Discipline (OP-3 — Lean by Design)

### 5.1 Per-day cost breakdown

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

### 5.2 Rate-limit discipline (shared Max pool)

**Today's bottleneck:** J's Claude session + the heartbeat share the Max rate-limit pool. A heavy interactive session during 09:30-15:55 ET can starve the heartbeat (the L54 incident, 2026-06-17).

**New design:** The conductor (Phase 1a) and model routing (Phase 1b) are **after-hours only** (16:00–09:30 ET). The heartbeat is Sonnet, continuous. Escalations during market hours are Haiku (cheap, fast). The guardian rule lives in CLAUDE.md:
> **Market-hours discipline:** No heavy interactive work during 09:30-15:55 ET. The heartbeat runs on the shared Max pool; starving it is starving real money. Use the wrist voice to chat (Nemotron, free) and ask questions (Haiku escalations, $0.01-0.05 each). Full Claude brainstorms happen after 16:00 ET or weekends.

This is ENFORCED by:
1. The companion can sense market hours and throttle Sonnet escalations (force Haiku during 09:30-15:55).
2. The conductor only fires after-hours.
3. The status beacon will flag "market-hours escalation attempted" if it ever happens.

---

## Part 6: Implementation Roadmap (integrating into existing build plan)

### 6.1 The critical path (what to build first)

The `GAMMA-MOBILE-WATCH-BUILDOUT` already has a 12-step plan (steps 1–11 are Gamma-buildable, step 12 is device-gated). This unification design **extends** that plan with the operator→assistant bridge.

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

### 6.2 File structure (what lives where)

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

### 6.3 Key integration points

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

## Part 7: Design Decisions & Tradeoffs

### 7.1 Why NOT ngrok or a public URL

- **Ngrok:** Exposes a public URL (the guard is only a software gate; ngrok sees the raw traffic).
- **Cloudflare Tunnel:** Same risk (defaults to public).
- **Our choice:** Tailscale (private by network, not software). The server stays `127.0.0.1:4317`; Tailscale Serve is a **proxy**, not a tunnel. Port never leaves the machine. J's tailnet only.

### 7.2 Why Web Push over ntfy.sh or FCM direct

- **ntfy.sh:** Requires a Docker host that runs 24/7 (another service to keep alive, cost risk if scaled). Our choice: use Android's built-in FCM.
- **FCM direct:** Requires a Firebase project + credentials. Web Push abstracts it (uses the browser's FCM endpoint).
- **Web Push:** VAPID keypair is local, no SaaS, no keys to rotate in the cloud, $0.

### 7.3 Why Wear OS notification bridge (not a native app)

- **Native Wear OS app:** Would require installation on the watch, APK signing, Google Play (friction + delays).
- **Our choice:** Android auto-bridges PWA notifications to the paired watch via the notification system. Zero installation, zero approval friction.
- **Caveat:** Wear OS 3+ only (Galaxy Watch 4+). If J is on older hardware, this won't work. Test early (step 12 of the buildout).

### 7.4 Why separate activity spine (gamma-activity.jsonl) instead of querying heartbeat logs

- **If we read heartbeat logs:** Would need to parse markdown (`automation/prompts/heartbeat.md`) in real-time, fragile.
- **Our choice:** The heartbeat already writes JSON to `gamma-activity.jsonl` (fire log, append-only). The assistant reads JSON. Schema is stable, parseable.
- **Downside:** Adds a small append-only file (immaterial, rows are ~500 bytes each, ~288 rows/day = ~150KB/day).

### 7.5 Why the wrist route is intentionally unauthenticated (but safe)

- **The problem:** Service Worker `notificationclick` handlers run in a different scope, can't access the page's `<meta name="gamma-token">`.
- **Wrong solution:** Make the route `authed()` (won't work, token isn't available in the SW).
- **Right solution:** Use a separate signed HMAC token, single-use, per-notification. Unforgeable, can't be replayed, expires.
- **Why it's safe:** The route can do exactly one thing (resolveApproval: plain fs ops), can't reach the escalate path (code assertion + smoke-guard), and even if the token leaks, it's consumed on first use.

---

## Part 8: Security Checklist (for code review)

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

## Part 9: Known Gotchas Locked In

1. **Tailscale must be running.** If Tailscale client on the PC or phone dies, the tunnel closes. Fallback: localhost-only (phone can't reach). Not a catastrophe; the operator still works.

2. **Watch requires phone to be nearby (Bluetooth).** The watch bridges notifications via the phone. If the phone's Bluetooth is off, the watch won't see notifications. Test during device verification.

3. **Web Push throttling.** Android throttles notifications if the PWA hasn't been opened recently (power-saving). The in-app queue (5s poll) is the source of truth; a missed push doesn't mean a missed approval.

4. **VAPID keypair rotation is not automatic.** If the keys are lost, J needs to re-generate and re-subscribe devices. Build a runbook for this (future work).

5. **HMAC key compromise = forgeable tokens.** If the key leaks, an attacker can forge approval tokens. But they can't reach the escalate path (guard blocks it) and can only resolve ONE existing queued decision. The damage is bounded.

6. **Origins that resolve to the Tailscale IP but use different hostnames are accepted.** The regex on line 29 checks the exact `GAMMA_TAILNET_HOST`. If it's pinned to `gamma.j-tailnet.ts.net`, then `gamma.j-tailnet.ts.net` is accepted but `localhost` is rejected (good). If someone DNS-rebinds to the Tailscale IP but uses a different hostname, they pass the regex check. Mitigation: Ensure `GAMMA_TAILNET_HOST` is a secret (hardcoded in launch env), not something the user supplies.

---

## Part 10: Timeline & Sequencing

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

## Part 11: Evidence & External Validation

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

## Summary

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
