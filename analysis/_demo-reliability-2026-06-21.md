# Gamma Companion — Demo Reliability Hunt (2026-06-21)

Scope: every way `gamma-companion/` can crash, hang, show a blank/broken frame, or look
fake in a live "show a friend" demo. Traced every fetch (`/api/state`, `/api/chat`,
`/api/diagram`, `/api/ask-result`, `/api/approve`, `/api/realtime-token`, the WebRTC
handshake) and every render path (tiles, feed, approvals, diagram focus, chat, voice).

**ANALYSIS ONLY** — no app files were modified. Each issue: severity, exact file+symptom, precise fix.
Severities: **DEMO-KILLER** (audience sees broken/fake) · **ROUGH** (visible jank) · **MINOR** (polish).

---

## TOP 5 DEMO-KILLERS (fix these first)

1. **D1 — Diagram escalation can render a BLANK iframe** if Claude returns prose instead of an SVG, or the SVG fails to extract. `app.js:311 renderDiagram` only handles the *no-svg* string case; a malformed/partial `<svg>` still gets stuffed into `srcdoc` and shows a blank/garbled box with no recovery. Plus the 110-try (≈4.5 min) poll wall is far longer than any demo attention span.
2. **D2 — First-load FOUC / "Loading…" + "connecting…" hangs visibly** until the first `/api/state` round-trips (≈5s poll, but the *first* `refresh()` only fires after `initGrid()`/`initVoice()`), and if the server isn't up the live pill silently flips to "offline" while the Next-card stays stuck on "Loading…" forever (`app.js:74` `#next-title` is only overwritten on a *successful* state). A friend sees a half-dead screen.
3. **D3 — Voice mic on a fresh `gpt-realtime-2` / SDP failure shows a cryptic error and a dead robot.** `realtime.js:55` surfaces `realtime connect failed (<status>)` raw; `app.js:269` renders `Voice: <msg>`. If the model id is wrong/unavailable, the OpenAI account has no Realtime credit, or `getUserMedia` is blocked (browser, not Electron), the mic just dies with a scary string mid-demo. No fallback to the typed face.
4. **D4 — Chat "thinking…" hangs up to 90s with no timeout on the client** if the Python face brain is slow/stuck (server timer is 90s for typed, `server.js:128`). The bubble sits on "thinking…" with no spinner and no abort — looks frozen. If ALL three free models are rate-limited, the user gets "(all free models busy…)" which reads as broken in front of a friend.
5. **D5 — Escalation result can be a 20k-char raw dump or never arrive.** `trackAsk` (`app.js:205`) polls 150×4s = 10 min, then leaves "(Claude is taking a while…)". `escalate.js:93` slices to 20000 chars and dumps it straight into a chat bubble (`app.js:215`) with no formatting — a wall of text or a tool-trace looks like a glitch, not an assistant.

---

## FULL PRIORITIZED LIST

### DEMO-KILLERS

**D1 — Blank diagram iframe / no validation of escalated SVG**
`public/app.js:280 extractSvg`, `:311 renderDiagram`, `:317` srcdoc.
- Symptom: `extractSvg` greedily grabs `<svg…</svg>`. If Claude returns a *truncated* SVG (escalation summary is sliced to 20k in `escalate.js:93`), or an SVG with a `<script>`/`<foreignObject>` that the `sandbox` (no `allow-scripts`) silently drops, the iframe renders blank or partial. Only the "no svg at all" branch shows a message.
- Also: `pollDiagram` (`:300`) waits `110 * 2500ms ≈ 4.6 min` before giving up — nobody waits that long in a demo, and there is no "still working" reassurance after the first frame.
- Fix: (a) After setting `srcdoc`, sanity-check the SVG has a `viewBox` and at least one `<rect`/`<path`; if not, fall back to `SYSTEM_DIAGRAM` (the instant hand-crafted one) so the focus pane is NEVER blank. (b) Lower the poll wall to ~40 tries and on timeout render the instant `SYSTEM_DIAGRAM` as a graceful fallback rather than a "took too long" string. (c) The "Diagram it" quick-button (`index.html:88` → `send()` → matches `/diagram/` → matches `/system|whole|everything/`) routes to the INSTANT diagram — good, keep that as the demo headline; route any *ambiguous* diagram ask to the instant one too when the server is the risk.

**D2 — First-load blank/stuck frame; no skeleton; Next-card stuck on "Loading…"**
`public/app.js:38 getState`, `:62 setNextCard`, `:155 refresh`, `:434 refresh()` call order; `index.html:74` `#next-title>Loading…`, `:110` feed `Listening…`.
- Symptom: On open, `#next-title` = "Loading…", feed = "Listening…", live pill = "connecting…". `refresh()` runs once at startup then every 5s. If `/api/state` is slow or the server isn't up, `refresh` catch only calls `renderLive({ok:false})` (`:166`) — it does NOT clear "Loading…"/"Listening…", so the hero Next-card and feed stay frozen on placeholder text indefinitely. A friend sees a permanently "loading" app.
- Race: `initGrid()` calls `grid.load(saved)` from `localStorage` (`:420`) BEFORE first state — fine — but GridStack is loaded from a remote CDN (`index.html:156`). **If the jsdelivr CDN is unreachable (offline demo / locked-down network), `window.GridStack` is undefined**, `initGrid` early-returns (`:418`), and the tiles render UNSTYLED/stacked because `.grid-stack` layout depends on the CDN CSS (`index.html:7`). The whole cockpit layout collapses.
- Fix: (a) In the `refresh()` catch, set `#next-title` to "Can't reach Gamma — is the server running?" and the feed to an explicit offline row, so the placeholders never persist. (b) Vendor GridStack (JS+CSS) locally into `public/` instead of the CDN — removes the single biggest "blank cockpit" risk for an offline/hotel-wifi demo. (c) Add a tiny first-paint skeleton or call `refresh()` synchronously before `initGrid()` so state lands ASAP.

**D3 — Voice failure path is scary + no graceful fallback to typed**
`public/realtime.js:21 start`, `:55` connect-failed throw, `:41 getUserMedia`; `public/app.js:259 mic.onclick`, `:269` error render; `server.js:295` model `gpt-realtime-2`.
- Symptom: Tapping the mic when `voiceAvailable` (`s.voice` true because a key file exists) but the OpenAI account lacks Realtime access/credit → token mint may succeed but `/v1/realtime/calls` returns non-2xx → `realtime.js:55` throws "realtime connect failed (4xx)" → robot dies, status shows raw error. In a plain browser (not Electron) `getUserMedia` may be blocked by permissions and throws an even worse string. The model id `gpt-realtime-2` (`server.js:295`) and endpoint `/v1/realtime/calls` are version-sensitive — if OpenAI's GA name differs, every voice attempt 4xxs.
- No fallback: when realtime fails, it does NOT fall back to the Web Speech API path (`SR`, `:253`) or to typed chat. The mic just goes dead.
- Fix: (a) On any realtime error, auto-fall-back: if `SR` exists, start Web-Speech dictation; else focus the text input and toast "Voice needs a moment — type to me here." (b) Make the error human: map `4xx` → "Voice isn't enabled on this OpenAI key yet — everything else works, just type to me." (c) Verify `gpt-realtime-2` + `/v1/realtime/calls` against the CURRENT OpenAI Realtime API before the demo (this is the single most likely live-demo breakage; the model name has churned). (d) For a friend demo, strongly prefer the **Electron shell** (`desktop/main.js` auto-grants mic) over a browser tab.

**D4 — Chat can hang on "thinking…" with no client timeout; "all models busy" reads as broken**
`public/app.js:180 send`, `:190` thinking bubble; `server.js:122` 90s typed timeout, `face_brain.py:174` all-busy reply.
- Symptom: The "thinking…" bubble (`:190`) has no client-side timeout — it relies entirely on the server's 90s kill (`server.js:128`). If the face brain hangs near 90s, the demo looks frozen for a minute and a half. If all 3 free models are rate-limited/down, the reply is literally "(all free models busy — try again in a moment)" — in front of a friend that's a visible failure of "the brain."
- Fix: (a) Add a client watchdog (~20s) that replaces "thinking…" with "Still thinking — the free brain is slow right now" so it never looks dead. (b) Lower the typed server timeout from 90s to ~30s (`server.js:128`) — 90s is far too long for an interactive demo. (c) Pre-warm: on app open, fire one throwaway `/api/chat` ("hello") so the first real question isn't the one that eats a cold rate-limit. (d) Consider a tiny canned "I'm here — one sec" instant reply while the model loads.

**D5 — Escalation output is an unformatted wall / can be a tool-trace**
`lib/escalate.js:63` result capture, `:93` 20k slice; `public/app.js:205 trackAsk`, `:215` render.
- Symptom: `runEscalation` captures only the final `result` message text and dumps up to 20000 chars into a single chat bubble (`app.js:215`). A long Claude answer = a giant scrolling wall; an error/partial = raw text. The 10-minute poll (`:218`) ending in "(Claude is taking a while…)" is a dead end in a demo.
- Also: if the SDK is misconfigured (no `ANTHROPIC_API_KEY` / not on a logged-in CLI session in the spawned process), `query()` throws and `escalate.js:71` logs "(escalation error — …)" which surfaces in chat as a failure. **Verify the SDK auth path works headlessly from the server process before demoing any "ask Claude to build X".**
- Fix: (a) Cap the chat-rendered summary to ~1200 chars with a "show full" affordance; keep the 20k in the JSONL. (b) Shorten the poll wall and end on a friendly "Claude's still on it — I'll surface it in the feed when it lands." (c) Smoke-test one real escalation end-to-end (`smoke-sdk.js`) right before the demo. (d) For the demo, lead with the INSTANT system diagram and status/voice — keep live Claude escalation as the "and it can actually build things" finale, not the opener.

### ROUGH

**R1 — `voiceAvailable` is true whenever a key FILE exists, even if the key is dead/empty-credit.**
`server.js:198` `voice: !!loadOpenAIKey(ROOT)`; `openai_key.js:14` only checks the string starts with `sk-`. A revoked/no-credit key still shows the mic as live → user taps → D3 failure. Fix: treat voice as "best-effort" in the UI copy; the real validation only happens at token mint.

**R2 — `/api/state` 500 → whole UI flips to "offline" on a single bad state file.**
`server.js:199` catches `buildState` throw and returns 500; `app.js:165` catch → `renderLive({ok:false})`. `buildState` is defensive (`state.js` reads degrade to null), so a 500 is unlikely — but `readApprovals`/`derivedCards` are NOT wrapped, and a malformed `companion-approvals.json` array element could throw inside `.filter`/`.map`. Fix: wrap `readApprovals` + `derivedCards` in try/catch inside `buildState` so one bad file never blanks the cockpit.

**R3 — Approvals optimistic UI: a failed `/api/approve` only dims, doesn't restore.**
`app.js:125 decide` sets `card.style.opacity=0.5` then on error sets `card.className="acard err"` but leaves the original buttons gone (card text was never replaced on the error branch — the buttons are still there but the card is half-faded red). Mildly confusing. Fix: on error, restore opacity to 1 and show "Couldn't log that — tap to retry."

**R4 — Diagram `sandbox` with no flags blocks SVG CSS animations only partially; data-q chips can be empty.**
`app.js:317` `sandbox` (fully locked). The hand-crafted `SYSTEM_DIAGRAM` uses CSS `@keyframes` inside `<style>` which works in a sandboxed iframe (no script needed) — good. But for a *Claude-drawn* diagram, if it emits no `data-q` attributes, `focus-chips` is empty and the focus pane looks bare. Fix: when zero `data-q` found, inject 2–3 generic follow-up chips ("Explain this", "Show me the code path").

**R5 — Feed/empty states are honest but read as "nothing works" in a fresh demo.**
`app.js:75` "Nothing here right now.", `index.html:96` "Nothing needs you right now." If the rig is idle (after hours / weekend), the friend sees three empty panels. Fix (demo-prep, not code): run `node seed-demo.js` before the demo to populate the Approvals loop, and ensure `dashboard-dialogue.json` + `kitchen-status.json` have recent rows so the feed shows real activity. Document this in a one-line DEMO-PREP checklist.

**R6 — `setNextCard` splits on `|`/`—`; a speech string with neither shows an empty subtitle and a long unwrapped title.**
`app.js:62`. Minor visual. Fix: clamp title length; fine as-is for most strings.

**R7 — Web Speech mic (`SR`) auto-sends on `onend` (`app.js:256`) even for an empty/garbled transcript** only if `v` truthy — ok — but interim results overwrite the input the user may be typing. Minor. Fix: guard against clobbering a focused input mid-type.

### MINOR

**M1 — `greet` uses local `getHours()` (`app.js:33`)** — says "Good morning" in the user's TZ, not ET. Cosmetic.

**M2 — `fetch` monkey-patch (`app.js:10`) attaches the token to ALL `/api/` URLs** including the external `https://api.openai.com/...` calls? No — those don't start with `/api/`, so they're untouched (correct). Verified safe.

**M3 — `server.js:84` injects the gamma-token meta only on `.html`** via a literal `</head>` replace. If `index.html` ever minifies `</head>` away, the token vanishes and every `/api/*` POST 403s. Low risk; keep `</head>` literal.

**M4 — No favicon** (`MIME` has `.ico` but none served) → 404 in console. Cosmetic.

**M5 — `pollDiagram`/`trackAsk` intervals are never cleared if the user closes the focus pane** (`focus-close`, `app.js:391` just hides). They keep polling in the background. Harmless but leaks timers across a long session. Fix: clear active interval on focus-close.

**M6 — Bottom-nav tabs (Today/Tasks/Reminders/Notes) all say "coming soon"** (`app.js:408`). Honest, but a friend tapping them four times sees four "coming soon" toasts. Fix (demo): mention Home is the live view, or hide the unbuilt tabs.

---

## DEMO-PREP CHECKLIST (no code; do before showing a friend)

1. Launch via **Electron** (`npm run app`), not a browser tab — mic auto-grants, no permission dialog.
2. Confirm the server booted: the live pill should read "live · market closed/open", not "connecting…"/"offline".
3. `node gamma-companion/seed-demo.js` to populate the Approvals loop.
4. Verify `gpt-realtime-2` + `/v1/realtime/calls` against the current OpenAI Realtime API, and that the key has Realtime credit — OR plan to demo voice via the typed face only.
5. Smoke one escalation (`node gamma-companion/smoke-sdk.js`) to confirm the Claude SDK auth works headlessly from the server process.
6. Lead with: status chips → **instant** "How Gamma works" diagram → voice → live Claude escalation as the finale. Avoid opening on a cold free-model chat call.
