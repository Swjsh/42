# Gamma companion — desktop presence layer

> Status: **shipped 2026-06-20 (after-hours), iterated 2026-06-21 (v0.3.0).** Local Node app — the friendly *face* for the autonomous engine. J's ask: "a little Gamma in the window… notifications, speech bubbles, and approve things from the dashboard."

## What it is

- `gamma-companion/` — local app. **`npm install` IS required** (`package.json` v0.3.0): runtime deps `@anthropic-ai/claude-agent-sdk` + `gridstack`, `electron` as a devDependency. No longer a zero-dependency Node-built-ins app.
- Reads the **real** state files (mirrors the path contract in `dashboard/lib/workspace.ts`): `engine-health.json`, `kitchen-status.json`, `dashboard-dialogue.json`, `current-position-*.json`, `loop-state.json`.
- Pixel robot in a room + speech bubble + live feed + Approve/Reject cards + dual-account status footer.

## Run

- Double-click **`LAUNCH-COMPANION.vbs`** (window-free: starts the server hidden, opens your browser).
- Or: `node gamma-companion/server.js` then open `http://localhost:4317`.
- Data-layer check (no server): `node gamma-companion/selftest.js`.
- See the Approve/Reject loop: `node gamma-companion/seed-demo.js`.

## Approval contract — the "accept from the dashboard" loop

- **Pending queue:** `automation/state/companion-approvals.json`
  `{ schema, updated_at, pending: [ { id, severity, title, detail, created_at } ] }`
- **Resolutions (immutable log):** appended to `automation/state/companion-decisions.jsonl`
  `{ ts, id, decision: "approve"|"reject", note, title }`
- Today the companion **writes** decisions. The next wiring step is producers (heartbeat / conductor) **writing real items** into the queue and **reading decisions back** — folded into the existing Discord approve/revoke bus. Not yet done (stated honestly, not faked).

## The face + Claude escalation (added 2026-06-20)

- **Chat:** `POST /api/chat {message, history}` → `face/face_brain.py` (spawned by the Node server) reuses `setup/scripts/run_minimax.call_minimax` on the FREE ladder (Nemotron → DeepSeek → MiniMax). $0. It reads a compact live-state summary, so it answers status questions directly without spending Claude tokens.
- **Escalation:** when the face decides real work is needed it emits a fenced `escalate {model, task}` block; `lib/escalate.js` calls the official `@anthropic-ai/claude-agent-sdk` — `query({ prompt, options: { model, permissionMode: 'bypassPermissions', cwd } })` (adopted after a GitHub sweep, replacing a hand-rolled `claude -p` spawn). **J chose FULL bypass (2026-06-20)** over the scoped/approve-gated option — escalated Claude acts with no prompts. Results append to `automation/state/companion-ask-results.jsonl`; the UI polls `GET /api/ask-result?id=`.
- **Real action cards:** `lib/state.js#derivedCards` builds cards from live state (e.g. the kitchen failed-task backlog). Approve runs the card's `action` (an escalation), not a demo.
- **Windows gotcha (fixed):** Node spawns python with cp1252 stdout → `UnicodeEncodeError` on the em-dashes/middots in the state summary. `face_brain.py` reconfigures stdio to UTF-8; the interpreter is pinned to the Store Python 3.13 (which has `openai`) via `server.js#pickPython()`.
- **Market-hours note:** heavy Opus escalations during RTH compete with the live heartbeat for the shared Max pool — `GAMMA_FACE_MARKET_GUARD` is reserved for deferral (a scheduling guard, never a permission gate).

## Security guard

- `lib/guard.js#makeCanUseTool` is the SDK `canUseTool` boundary for every companion-driven Claude escalation: **full autonomy by default (auto-allow), minus a hard denylist** of catastrophic/irreversible actions. It can NEVER write/edit `CLAUDE.md`, `params*.json`, `heartbeat*.md`, `filters.py`, or any `*.key`, and NEVER place/cancel/close/replace/exercise an Alpaca order — those are propose-only (draft + Approve card). Enforced programmatically, NOT via prose and NOT via `bypassPermissions` (which would skip the check).
- Global kill-switch: if `automation/state/companion-halt.flag` exists, every tool is denied (J holds the off-switch, OP-25 / OP-32).
- Guarded behavior is locked by `smoke-guard.js` — **14/14 cases** pass (deny doctrine writes + live orders, allow benign reads/builds).

## Soul

- The companion's voice/personality lives in **`automation/presence/GAMMA-VOICE.md`** (already wired). Treat it as the single source of truth for how Gamma speaks; don't re-author tone in app code.

## Voice — OpenAI Realtime (added 2026-06-20)

- **Talk to Gamma, it talks back.** OpenAI Realtime (`gpt-realtime-2`) is the voice; when it needs real work it calls the `ask_gamma` tool, which routes into `/api/chat` → free face → Claude SDK, then speaks the result.
- **Key handling:** `automation/state/.openai.key` (gitignored via `**/*.key`). `lib/openai_key.js` reads it server-side ONLY. `GET /api/realtime-token` mints a short-lived ephemeral token via `POST https://api.openai.com/v1/realtime/client_secrets` — the real key never reaches the browser. `/api/state` exposes a `voice` boolean (key present?).
- **Browser:** `public/realtime.js` (`window.GammaRealtime`) does the WebRTC handshake (`getUserMedia` mic → `RTCPeerConnection` → SDP POST to `https://api.openai.com/v1/realtime/calls` with the ephemeral token), plays the remote audio, and handles `response.function_call_arguments.done` by calling `/api/chat` and returning a `function_call_output`.
- **Mic logic:** the `🎤` button picks Realtime when `voice` is true, else free browser Web Speech (dictation) as a fallback. The `🔊` toggle is Web Speech TTS for **typed** replies only — Realtime speaks natively.
- **Cost:** usage-billed on J's OpenAI key (~few $/hr of active voice), separate from the Max pool. End the session (tap mic again) to stop billing.

## UI (redesigned 2026-06-20)

Full-screen, app-like skin matching J's reference (the first cut was "a tiny phone on a black background"). Files: `public/index.html`, `public/styles.css`, `public/app.js`.

- Radial-gradient ambient background, `.app` fills `100vh`, glass cards (`backdrop-filter: blur`). One centered column (max 540px), so it reads as an app, not a floating card.
- **Robot hero is voice-reactive:** `.robot.listening` shows ripple rings, `.robot.talking` pulses eyes/chevron — driven by `realtime.js` status events (`input_audio_buffer.speech_started`, `response.audio.delta`, `response.done`, …). `#robot-status` shows "Listening…" / "Gamma is talking…".
- Time-based greeting, quick-action chips (canned prompts → `/api/chat`), feed timeline with **Alert/Note/System** tag pills + client-side filter, polished Ask bar (sparkle/mic/send), bottom nav (Home live; others say "coming soon").
- **Launch:** `LAUNCH-GAMMA.vbs` → starts the server hidden + opens Chrome/Edge `--app=http://localhost:4317 --window-size=470,900` (native-feeling window, no browser chrome, voice works).

## Shipped (was "next increments")

- **Electron desktop shell** — `desktop/main.js` + `electron` devDependency; `npm run app` loads the same `localhost:4317` server in a native window (`npm run server` still runs headless for the browser/VBS launch path).
- **GridStack dashboard layout** — `gridstack` runtime dep; draggable/resizable card grid.

## Built but not yet wired

Four autonomy modules exist in `gamma-companion/lib/` and are verified-correct in isolation but not yet called from the live server — full integration steps in **`gamma-companion/lib/_WIRING-PLAN-2026-06-21.md`**:

- `lib/activity.js` — append-only activity ledger (`gamma-activity.jsonl`).
- `lib/obligations.js` — daily obligation registry / evidence freshness check.
- `lib/autobuild.js` — queue reader for the self-build order (`companion-build-order.jsonl`); never spawns Claude on its own.
- The soul (`automation/presence/GAMMA-VOICE.md`) is the 4th piece and is **already** wired.

## Next increments

1. **Always-on-top / frameless** polish on the Electron shell → pin to a screen corner (true desktop-pet).
2. **Wire engine producers** to enqueue real approvals (ship-edge, kill-switch-continue, candidate-promote) and consume `companion-decisions.jsonl`.
3. **Optional richer art** via OpenAI `gpt-image` ($20 ChatGPT): generate a Gamma sprite sheet + room, drop the PNGs in `gamma-companion/public/`, swap in.

Port **4317** (never 3000 — that's the Next.js dashboard). Preview launch config: `.claude/launch.json` → name `companion`.
