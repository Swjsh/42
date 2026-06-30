# Gamma Cockpit — Execution Log

> Rolling execution log of the cockpit/frontend/visibility hardening + weekend gameplans, folded from dated one-offs per markdown/infra/DOC-ARCHITECTURE.md, newest first.

---

## 2026-06-21 — Gamma Companion — Frontend Hardening Plan

> READ-ONLY audit synthesis. Proposes exact surgical edits; does NOT apply them.
> Goal: the cockpit (robot, chat/ask bar, status, approvals, feed) is ALWAYS
> visible and functional. No overlay / init error / async failure can ever hide
> or break Gamma again. Diagram is a NICE-TO-HAVE; the cockpit is the product.

Files in scope: `gamma-companion/public/{index.html, app.js, styles.css}`.
`realtime.js` is already fully guarded — no changes. `server.js` POST /api/diagram
becomes dead code after the strip-back — flagged for a SEPARATE follow-up, not
touched here (keeps this diff frontend-only).

The just-shipped fix `.focus[hidden]{display:none!important}` (styles.css:235) is
CORRECT and stays. Everything below is defense-in-depth on top of it.

---

### Principle for this pass

Every fix is the SMALLEST change that removes a way the cockpit can break:
1. One global CSS line kills the entire `[hidden]`-vs-`display` bug class at the root.
2. Strip the async Claude-draw diagram path — it is the sole source of stuck/blank panes.
3. Guard the unguarded synchronous DOM derefs that gate the whole IIFE.
4. Fault-isolate each init call and each render step so one failure can't starve the data loop.
5. A CSS fail-safe so a dead GridStack degrades to readable flow instead of an overlapping pile.

No rewrites. Each edit is independently revertible.

---

### APPLY LIST (critical/high first)

#### 1. [CRITICAL] Global `[hidden]` guard — kills the whole bug class at the root
**File:** `public/styles.css` (after line 15, `* { box-sizing: border-box; }`)
**Why:** The diagram overlay bug was `[hidden]` losing to a `display` rule.
`#push-toggle` has the identical latent foot-gun (`.iconbtn{display:grid}` overrides
`[hidden]`). One global line honors the `hidden` attribute everywhere, making
`.focus[hidden]` redundant-but-harmless and protecting every current and future
hidden element. This is the single most bulletproof line available.
```
OLD: * { box-sizing: border-box; }
NEW: * { box-sizing: border-box; }
     [hidden] { display: none !important; }
```
**Risk:** Near-zero. Standard CSS-reset hardening; `!important` on the inherent
semantics of `hidden`. Verify `#push-toggle` still appears when JS sets
`btn.hidden=false` (it does — clearing the attribute drops the rule).

---

#### 2. [HIGH] Strip the async Claude-draw diagram path — keep only the trusted inline SVG
**File:** `public/app.js`
**Why:** Every diagram hang / blank "Diagram" pane comes from `requestDiagram` →
`/api/diagram` → `pollDiagram` → `renderDiagram`. That path spawns a Sonnet
subprocess and mutates `#focus-title`/`#focus-canvas` from async callbacks that
resolve AFTER the panel is closed (stale-write-to-thin-air). `showSystemDiagram()`
already renders instantly and is the part that works. Make it the ONLY path.

**2a. `requestDiagram` becomes a synchronous alias (lines 307-319):**
```
OLD: function requestDiagram(topic) {
       const f = $("focus");
       if (!f) return;
       // Never show a blank canvas: render the instant system diagram NOW, then
       // quietly try to enrich it with a Claude-drawn custom one (swap in on success).
       showSystemDiagram();
       const label = topic && topic.length > 48 ? topic.slice(0, 45) + "…" : topic || "Diagram";
       $("focus-title").textContent = label + " · refining…";
       fetch("/api/diagram", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ topic }) })
         .then((r) => r.json())
         .then((j) => { if (j && j.ask_id) pollDiagram(j.ask_id, topic); else { const t = $("focus-title"); if (t) t.textContent = "How Gamma works"; } })
         .catch(() => { const t = $("focus-title"); if (t) t.textContent = "How Gamma works"; });
     }
NEW: function requestDiagram(topic) {
       // Diagram is intentionally a single trusted inline SVG: synchronous, can
       // never hang or blank. (Claude-drawn custom diagrams were removed — they
       // were the sole source of the stuck-overlay / blank-pane failures.)
       showSystemDiagram();
     }
```

**2b. Delete the dead async machinery (lines 299-302 + 320-356):**
- Delete `extractSvg` (lines 299-302) — its only caller was `renderDiagram`.
- Delete `let diagramPoll = null;` + entire `pollDiagram` (lines 320-332).
- Delete entire `renderDiagram` (lines 333-356).
- (`drawMsg`, lines 303-306, is also now unused — safe to delete too.)
- LEAVE `SYSTEM_DIAGRAM` and `showSystemDiagram` untouched (the trusted path).

**Risk:** Low. Removes a feature, not cockpit behavior. After this, opening a
diagram is purely synchronous — cannot hang, always shows content instantly.
Removing `diagramPoll` REQUIRES the focus-close edit in #3 (which no longer
references it). Verify the "Diagram it" quick action + a "draw me X" chat message
both still open the inline diagram.

---

#### 3. [HIGH] One close helper + Escape fallback; no stale interval reference
**File:** `public/app.js` (focus-close IIFE, lines 412-418)
**Why:** The X button is the ONLY dismiss path (exactly the trap that burned
hours). Add a keyboard escape hatch so a future CSS/X regression can never trap
the user again. Also drops the now-deleted `diagramPoll` reference from #2.
```
OLD: (function () {
       const fc = $("focus-close");
       if (fc) fc.onclick = () => {
         if (diagramPoll) { clearInterval(diagramPoll); diagramPoll = null; }
         const f = $("focus"); if (f) f.hidden = true;
       };
     })();
NEW: (function () {
       const closeFocus = () => {
         const f = $("focus"); if (f) f.hidden = true;
       };
       const fc = $("focus-close");
       if (fc) fc.onclick = closeFocus;
       document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeFocus(); });
     })();
```
**Risk:** Near-zero. With the global `[hidden]` guard (#1) + shipped line 235,
`hidden=true` is guaranteed to remove the overlay. Escape is additive.

---

#### 4. [CRITICAL] Guard `setGreeting` — the first unguarded deref gates the WHOLE script
**File:** `public/app.js` (lines 32-36)
**Why:** Runs at the very top of the IIFE before all wiring + init. If `#greet`
is ever missing/renamed it throws synchronously and kills EVERYTHING below —
wiring, init, refresh loop. Highest-leverage single guard in the file.
```
OLD: (function setGreeting() {
       const h = new Date().getHours();
       const g = h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
       $("greet").innerHTML = g + ' <span class="wave">\u{1F44B}</span>';
     })();
NEW: (function setGreeting() {
       const el = $("greet"); if (!el) return;
       const h = new Date().getHours();
       const g = h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
       el.innerHTML = g + ' <span class="wave">\u{1F44B}</span>';
     })();
```
**Risk:** None. Pure null-guard; identical behavior when `#greet` exists.

---

#### 5. [CRITICAL] Fault-isolate the init sequence so one subsystem can't starve the data loop
**File:** `public/app.js` (lines 528-532, bottom of IIFE)
**Why:** `initGrid`/`initVoice` are synchronous; if either throws, `refresh()`
and `setInterval(refresh)` never run — the cockpit never loads data and never
recovers. Wrap each independent init so a non-essential subsystem failing cannot
kill the data loop.
```
OLD: initGrid();
     initVoice();
     initPush();
     refresh();
     setInterval(refresh, POLL_MS);
NEW: function safeInit(name, fn) { try { fn(); } catch (e) { console.warn("[init] " + name + " failed", e); } }
     safeInit("grid", initGrid);
     safeInit("voice", initVoice);
     safeInit("push", initPush);
     safeInit("refresh", refresh);
     setInterval(function () { try { refresh(); } catch (e) {} }, POLL_MS);
```
**Risk:** Near-zero. `refresh()` keeps its own try/catch; this is belt-and-suspenders.
Each init stays independent.

---

#### 6. [HIGH] Guard the two wiring derefs that gate the init sequence
**File:** `public/app.js` (lines 421 and 423)
**Why:** `$("chat-form").addEventListener` (421) and `$("nextcard").addEventListener`
(423) run BEFORE the init sequence. A missing element throws and kills the rest of
wiring (pills, nav) AND grid/voice/push/refresh below it.
```
OLD (421): $("chat-form").addEventListener("submit", (e) => { e.preventDefault(); const v = $("chat-input").value.trim(); if (v) send(v); });
NEW (421): { const cf = $("chat-form"); if (cf) cf.addEventListener("submit", (e) => { e.preventDefault(); const ci = $("chat-input"); const v = ci ? ci.value.trim() : ""; if (v) send(v); }); }

OLD (423): $("nextcard").addEventListener("click", () => send("What's the plan, and what should I watch next?"));
NEW (423): { const nc = $("nextcard"); if (nc) nc.addEventListener("click", () => send("What's the plan, and what should I watch next?")); }
```
**Risk:** None. Pure null-guards; identical behavior when elements exist.

---

#### 7. [HIGH] CSS fail-safe: a dead GridStack degrades to readable flow, not an overlapping pile
**File:** `public/styles.css` (append near end, before the reduced-motion block)
**+** `public/app.js` `initGrid()` (lines 513-526)
**Why:** Vendor CSS sets `position:absolute` on every tile but coordinates are
only set inline by GridStack JS. If `gridstack-all.js` is missing/blocked or
`GridStack.init()` throws, all 6 tiles collapse to top-left on desktop (≥1200px) —
the cockpit is destroyed with no static fallback.

**7a. styles.css — add the escape-hatch class:**
```
NEW (append):
/* Fail-safe: if GridStack never initialized, force tiles to readable single-column
   flow so the cockpit is NEVER an overlapping pile. */
body.no-grid .grid-stack { height: auto !important; }
body.no-grid .grid-stack-item { position: static !important; width: 100% !important; height: auto !important; left: auto !important; top: auto !important; transform: none !important; margin-bottom: 10px; }
body.no-grid .grid-stack-item-content.tile { position: static !important; inset: auto !important; height: auto !important; min-height: 0; }
```

**7b. app.js — apply the class on unavailable OR thrown init (lines 513-526):**
```
OLD: function initGrid() {
       if (!window.GridStack) return;
       grid = GridStack.init({ column: 12, cellHeight: 78, margin: 8, float: true, staticGrid: true, handle: ".tile", resizable: { handles: "se,sw,e,s" }, columnOpts: { breakpointForWindow: true, breakpoints: [{ w: 560, c: 1 }] } });
       try { const saved = JSON.parse(localStorage.getItem("gamma-layout-v2") || "null"); if (saved && saved.length) grid.load(saved); } catch (e) {}
       grid.on("change", saveLayout);
       const btn = $("layout-toggle");
       if (btn) btn.onclick = () => { editMode = !editMode; grid.setStatic(!editMode); document.body.classList.toggle("editing", editMode); btn.classList.toggle("on", editMode); if (!editMode) saveLayout(); };
     }
NEW: function initGrid() {
       if (!window.GridStack) { document.body.classList.add("no-grid"); return; }
       try {
         grid = GridStack.init({ column: 12, cellHeight: 78, margin: 8, float: true, staticGrid: true, handle: ".tile", resizable: { handles: "se,sw,e,s" }, columnOpts: { breakpointForWindow: true, breakpoints: [{ w: 560, c: 1 }] } });
       } catch (e) { document.body.classList.add("no-grid"); return; }
       try { const saved = JSON.parse(localStorage.getItem("gamma-layout-v2") || "null"); if (saved && saved.length) grid.load(saved); } catch (e) {}
       grid.on("change", saveLayout);
       const btn = $("layout-toggle");
       if (btn) btn.onclick = () => { editMode = !editMode; grid.setStatic(!editMode); document.body.classList.toggle("editing", editMode); btn.classList.toggle("on", editMode); if (!editMode) saveLayout(); };
     }
```
**Risk:** Low. `no-grid` rules are scoped to `body.no-grid` — never applied on the
happy path. The mobile media-query overrides already prove flow-layout renders fine.

---

#### 8. [MED] Fault-isolate each render step inside refresh()
**File:** `public/app.js` (lines 161-170, refresh() try block)
**Why:** Render steps run sequentially under ONE try. If `renderLive`/`setNextCard`
throws, the LATER sections (feed, approvals, status) silently don't render on
EVERY poll — the cockpit looks half-dead even though the fetch succeeded.
```
OLD: const s = await getState();
     voiceAvailable = !!s.voice;
     renderLive(s);
     setNextCard(s);
     lastFeed = s.feed || [];
     renderFeed();
     renderApprovals(s.approvals);
     renderStatus(s);
NEW: const s = await getState();
     voiceAvailable = !!s.voice;
     const step = (fn) => { try { fn(); } catch (e) { console.warn("[refresh] render step failed", e); } };
     step(() => renderLive(s));
     step(() => setNextCard(s));
     lastFeed = s.feed || [];
     step(renderFeed);
     step(() => renderApprovals(s.approvals));
     step(() => renderStatus(s));
```
**Risk:** Near-zero. Only adds isolation; happy-path order unchanged.

---

#### 9. [MED] Null-guard the render fns that still deref bare ($status, $live, $feed, next-title/sub)
**File:** `public/app.js` (renderLive 56-61, renderStatus 152, renderFeed 73, setNextCard 68-69)
**Why:** With #8 these can no longer cascade, but cheap inline guards turn them
into no-ops instead of throws (cleaner console; `renderLive({ok:false})` is also
called from the refresh catch at line 172 — a throw there escapes as an unhandled
rejection and defeats graceful degradation).
```
renderLive (56-61):
OLD: $("live").classList.toggle("off", !ok);
     $("live").classList.remove("connecting");
     $("live-text").textContent = ok ? (s.market_open ? "live · market open" : "live · market closed") : "offline";
NEW: const live = $("live");
     if (live) { live.classList.toggle("off", !ok); live.classList.remove("connecting"); }
     const lt = $("live-text");
     if (lt) lt.textContent = ok ? (s.market_open ? "live · market open" : "live · market closed") : "offline";

renderStatus (152):
OLD: const wrap = $("status"); wrap.innerHTML = "";
NEW: const wrap = $("status"); if (!wrap) return; wrap.innerHTML = "";

renderFeed (73):
OLD: const ul = $("feed");
     ul.innerHTML = "";
NEW: const ul = $("feed"); if (!ul) return;
     ul.innerHTML = "";

setNextCard (68-69):
OLD: $("next-title").textContent = title;
     $("next-sub").textContent = sub;
NEW: const nt = $("next-title"); if (nt) nt.textContent = title;
     const ns = $("next-sub"); if (ns) ns.textContent = sub;
```
**Risk:** None. Pure null-guards.

---

#### 10. [MED] Make the mobile `.focus` override self-contained
**File:** `public/styles.css` (line 360)
**Why:** The phone branch re-declares `.focus { position: fixed; }` but relies on
inheriting `inset:0; z-index:50` and on the far-away `!important` on line 235 for
its hide guard. Make it locally self-evident so a future cleanup can't un-hide it.
```
OLD: .focus { position: fixed; }
NEW: .focus { position: fixed; inset: 0; z-index: 50; }
```
**Risk:** None. `inset`/`z-index` match the base values; idempotent. (The global
`[hidden]` guard from #1 already covers the hide; this just removes the silent
dependency on it within the media query.)

---

### STRIP-BACK RECOMMENDATION

**Remove the entire Claude-drawn custom diagram pipeline.** It is a nice-to-have
whose failure modes (iframe blanking, stuck overlay, Sonnet-subprocess hang,
blank "Diagram" pane, stale async writes after close) have repeatedly hidden the
cockpit. The trusted inline `SYSTEM_DIAGRAM` already covers the demo and is
synchronous — it cannot hang and always shows content instantly.

Concretely (items #2 + #3 above):
- `requestDiagram` → thin synchronous alias for `showSystemDiagram`.
- Delete `extractSvg`, `drawMsg`, `pollDiagram`, `renderDiagram`, and the
  module-level `diagramPoll`.
- Optionally collapse the `send()` diagram intercept (lines 190-196) so the
  system/custom branch distinction disappears (both now show the same inline SVG):
  ```
  if (/\b(diagram|draw|visuali[sz]e|map out|sketch)\b/i.test(message)) {
    addMsg("You", message);
    const ci = $("chat-input"); if (ci) ci.value = "";
    showSystemDiagram();
    return;
  }
  ```

**Follow-up (separate, NOT in this diff):** `server.js` `POST /api/diagram`
(spawns `runEscalation`, a Sonnet subprocess) becomes unreachable once the
frontend no longer calls it. Delete that route in a later hygiene pass — it poses
no runtime risk in normal use after the app.js edits, so removal is cleanliness,
not a fix. Keep this pass frontend-only.

**Do NOT remove:** the inline `SYSTEM_DIAGRAM` + `showSystemDiagram` (trusted),
the shipped `.focus[hidden]{display:none!important}` (load-bearing), or any
cockpit element.

---

### REJECTED / NOT DOING (avoid risk + scope creep)

- **The `.show`-class invert of `.focus`** (one auditor's F1 alt). Functionally
  correct but requires touching every show/hide call site and adds a second state
  mechanism to keep in sync. The global `[hidden]` guard (#1) achieves the same
  bulletproofing in ONE line with zero JS churn and also protects `#push-toggle`.
  Prefer #1.
- **Raising `.focus` z-index 50→100.** Cosmetic-only (FAB at 60 can overlap the
  open overlay on phones). Not a visibility/reliability fix for the cockpit; skip
  to keep the diff minimal. Revisit only if the FAB-over-diagram overlap is ever
  reported.
- **Backdrop/outside-click close.** Escape (#3) is the needed second escape hatch;
  a backdrop handler adds event wiring for marginal gain. Skip.
- **Seeding a resting next-card line.** Purely cosmetic; the synchronous greeting +
  static HTML already render the cockpit before any fetch. Skip.
- **Editing `server.js` now.** Out of scope for a surgical frontend pass (see
  follow-up above).

---

### VERIFICATION CHECKLIST (after applying)

1. Cold load in Electron: robot, greeting, quick actions, ask bar, mic, feed,
   approvals, status all render before the first `/api/state` resolves.
2. Click "Diagram it" → inline SVG opens instantly. X closes it. Esc closes it.
   "draw me X" in chat opens the same inline SVG.
3. Temporarily rename `window.GridStack` (or block the vendor script) → tiles fall
   to single-column flow (`body.no-grid`), cockpit still fully usable.
4. Temporarily rename `#greet` in HTML → no console throw, rest of cockpit + data
   loop still wire up and poll.
5. Phone width (<768px): overlay opens fixed full-viewport; cockpit scrolls; mic
   FAB works at <280px.
6. `#push-toggle` still appears when a VAPID key is present (global `[hidden]`
   guard doesn't break the reveal).

---

## 2026-06-21 — Gamma Companion — Phone-Driven E2E Hardening

> Goal: a phone-driven Gamma that (1) reliably starts a REAL Claude session on every typed build/do request, (2) reliably starts one on every approval, (3) runs WITH its soul (CLAUDE.md + the 10 rules + guard boundary) as the actual system prompt — not incidental context, and (4) has no rough edges (no strands, no leaks, no corrupt writes, no zombie builds).
>
> Audited against the REAL files. SDK pinned at `@anthropic-ai/claude-agent-sdk@0.3.185` (verified in node_modules). All file+line references below are real.

---

### SOUL VERDICT (crisp)

**Does the escalation get CLAUDE.md today?** YES — but only by ACCIDENT, and as the wrong KIND of context.

- `runEscalation` (`gamma-companion/lib/escalate.js:223-231`) calls `query({ prompt, options:{ model, cwd, canUseTool, abortController, includePartialMessages } })` with **NO `systemPrompt`** and **NO `settingSources`**.
- Per the bundled SDK type defs (`node_modules/@anthropic-ai/claude-agent-sdk/sdk.d.ts:1880-1882, 1929-1934`): the `claude_code` preset is **opt-in**. Omitting `systemPrompt` yields a **minimal** system prompt — the escalation Claude is therefore **NOT** the Claude Code coding agent (no agentic identity/tool-use scaffolding), does **not** know it is Gamma, and never sees the 10 rules / guard boundary as authoritative soul.
- CLAUDE.md *does* load today only because omitting `settingSources` currently defaults to all sources in 0.3.185 — but (a) it lands as **project CONTEXT (a user message)**, not the soul/system prompt, and (b) the SDK default has flip-flopped across versions (v0.1.0 defaulted to `[]` = isolated), so a future bump can **silently** drop the soul with no error.

**Exact injection fix** — in `escalate.js`, add to the `options` block:

```js
const SOUL = [
  "You are Gamma, J's autonomous 0DTE SPY research + build agent.",
  "The repo CLAUDE.md is your soul — read and obey it, especially the 10 rules and the Operating Principles.",
  "You run inside a HARD guard (lib/guard.js): you MAY build/edit code, run backtests, and use project MCP servers,",
  "but you can NEVER write CLAUDE.md / params*.json / heartbeat*.md / filters.py / *.key, and NEVER place/cancel/close",
  "live orders — propose those as TEXT for J. Act autonomously within that boundary: do the work, verify it, report",
  "concisely. Never claim unverified work is done."
].join(" ");

options: {
  model: fullModel,
  cwd: root,
  systemPrompt: { type: "preset", preset: "claude_code", append: SOUL }, // SOUL FIX
  settingSources: ["user", "project"],                                   // deterministic CLAUDE.md load
  canUseTool: makeCanUseTool(root, org),
  abortController: ac,
  includePartialMessages: true,
  maxTurns: 60,                                                          // bound a runaway loop
}
```

This makes the role + rules part of the actual system prompt (matching the documented "Load CLAUDE.md with preset system prompt" pattern), pins soul-loading deterministically, and caps a runaway loop on the shared Max pool.

---

### PRIORITIZED FIX LIST

#### P0 — Soul / autonomy (demand 3)

1. **[CRITICAL] Escalation runs soulless (minimal system prompt).** `lib/escalate.js:223-231`. Fix: add `systemPrompt:{type:'preset',preset:'claude_code',append:SOUL}` (SOUL string above).
2. **[CRITICAL] CLAUDE.md load is incidental, not pinned.** `lib/escalate.js:223-231`. Fix: add `settingSources:['user','project']` so a future SDK default flip can't silently drop the soul.

#### P0 — Reliable session start (demand 1 & 2)

3. **[HIGH] Typed build/do requests do NOT reliably start a session.** `server.js:478-486` blindly trusts `face.escalate`, decided by a prose-fragile FREE model (`face_brain.py parse_escalation`, exact ```escalate fence). The model may chat instead, drop the fence, truncate at `max_tokens=420`, or rate-limit → request silently degrades to a chat reply, NO Claude session. Fix: add a deterministic intent classifier in `server.js` `/api/chat` BEFORE trusting the face. Regex the raw message for imperative verbs at clause start: `/^(\s*(please|hey gamma)[,:]?\s*)?(build|implement|add|create|write|fix|patch|refactor|run|backtest|wire|ship|make|generate|analyze|investigate|debug|optimize|port)\b/i`. If it matches AND the face did not escalate, force one: synthesize `{model:'sonnet', task:'J asked via companion: '+message}`, call `runEscalation`, return `escalate:true + ask_id + stream_token`. Keep the face's sentence as the human reply.
4. **[HIGH] Approve-then-build-fails: the obligation card stays hidden ~45 min.** `lib/approvals.js:201-203` snoozes the synthetic `oblig-*` card UNCONDITIONALLY on `decide('approve')`, before/independent of whether `runEscalation` succeeded. A failed producer-rerun leaves the obligation unmet but the card suppressed → "nothing needs you" (the fail-green trap obligations.js exists to prevent). Fix: for an escalating approve, do NOT snooze 45 min in `resolveApproval`; instead snooze a short 2-3 min grace, and let the escalation completion callback clear/snooze only when `recheckObligationCleared` confirms fresh evidence (escalate.js already computes `cleared`). Plumb a `skipLongSnooze` flag from `/api/approve` (server.js:520-528) when `action.type==='escalate'`.

#### P1 — Stream / strand / leak (demand 4)

5. **[HIGH] SUBSCRIBE-GAP RACE strands the phone on "On it…".** `server.js:441-461` reads the feed (`fs.readFileSync`, line 443) BEFORE `subscribeAskStream` (line 453). Any `emit` in that window — including the terminal `result` of a fast/already-busy build — is delivered by NEITHER replay nor live stream, no EventSource error fires, so `es.onerror→startPoll` never runs and the line hangs forever. Fix: subscribe FIRST, then read+replay, de-dup with a monotonic per-id `seq` (add `seq` in `emit`, drop already-seen seqs client-side). Minimal: after `subscribeAskStream`, re-read the feed tail once and replay any new lines. ALSO: if `tasks.get(id).status` is already terminal (done/failed/cancelled/blocked/busy) at connect time, synthesize+write a final `result` SSE frame immediately so a post-completion connect always settles.
6. **[HIGH] EventSource native auto-reconnect defeated + no server heartbeat.** Client (`public/app.js:337`, `public/m.html:346-351`) treats the FIRST `onerror` as terminal (`fellBack=true; es.close(); startPoll()`), but EventSource fires `onerror` on every transient blip and is designed to self-reconnect. Server SSE route (`server.js:435-461`) writes NO periodic heartbeat, so idle Tailscale/proxy hops drop long builds → permanent downgrade to polling (J loses the live transcript). Fix — **Server:** `setInterval` writing `res.write(': ping\n\n')` every ~15s per open SSE res, cleared in `done()`; a throwing heartbeat write is also the cheapest dead-socket detector (unsubscribe+clearInterval on throw — also fixes the subscriber leak, #9). **Client:** on first `onerror`, start a 10-15s grace timer; only `close()+startPoll()` if `es.readyState===2` (CLOSED) or still erroring when it fires; clear the timer on the next `onmessage`. Preserves native reconnect for blips.
7. **[MED] Long build → no wall-clock timeout → zombie that holds an inflight slot.** `lib/escalate.js:221-359` has no hard cap; if `query()` hangs without throwing or yielding `result` (network stall to Anthropic), NO result record/frame is ever written, the poll fallback caps out ("Still working…") and gives up, and the inflight slot is pinned (next 2 asks go `busy`). Fix: `const killer = setTimeout(()=>{try{ac.abort()}catch{}}, 15*60*1000)` at the top of the try; `clearTimeout(killer)` on every exit path. A stalled query then always lands on the catch/abort path → writes a result + emits a terminal frame + frees the slot.
8. **[MED] Stream token expires mid-build.** `lib/push.js:435` TTL=60min but builds can run longer; reconnect after `exp` → `verifyStreamToken` `expired` → route 403s → permanent polling, and a page reload can't re-watch (no fresh token). Fix: raise TTL to 4-6h (read-only 127.0.0.1 telemetry, grants no write power) — one-line change at push.js:435.
9. **[MED] Subscriber leak on phone background / unclean FIN.** `server.js:452-460` relies on `req 'close'/'end'` / `res 'error'`; a backgrounded PWA may not FIN promptly and `emit`'s `res.write` buffers without throwing, pinning the res for the build's life. Fix: the #6 heartbeat write surfaces the dead socket (unsubscribe+clearInterval on throw); also `res.socket.setTimeout(...)` + a max-lifetime, and cap subscribers per id (drop oldest beyond ~5).
10. **[MED] Result frame/record can report a failure as a cheery "Done in Ns".** `lib/escalate.js:264-276, 335-347`: on `subtype==='error_max_turns'`/`'error_during_execution'`, `result` text is often empty but the summary is still `"Done in Xs"` and `appendResult` writes `(no output)`. Fix: when `subtype!=='success'` or `is_error`, build an explicit failure summary (`ok ? 'Done…' : 'Stopped: '+subtype`) in both the emitted frame and the appended record. Client (`app.js:300`, `m.html:301/336`) already prefers the durable record — keep that, just make both honest.

#### P1 — Input / concurrency / write-safety (demand 4)

11. **[HIGH] Oversized POST body HANGS the request forever.** `server.js:193-206` `readBody`: on `body.length > 2e5` it calls `req.destroy()` inside the `'data'` handler → the `'end'` event never fires → `cb()` never called → no response is ever sent. A typed prompt just over 200KB silently dead-ends the phone. Affects `/api/chat`, `/api/approve`, `/api/diagram`, `/api/push/subscribe`. Fix: reply 413 then stop, guaranteeing exactly one response: `let aborted=false; req.on('data',c=>{ if(aborted)return; body+=c; if(body.length>2e5){aborted=true; sendJSON(res,413,{ok:false,error:'request too large'}); req.destroy();} }); req.on('end',()=>{ if(aborted)return; try{cb(JSON.parse(body||'{}'))}catch{cb({})} });`.
12. **[HIGH] Escalation askId collision.** All three id mints (`server.js:482` chat, `:510` card, `:546` diagram) use `'ask-'+Date.now().toString(36)` (ms only). Two near-simultaneous escalations get the SAME id → `logAsk`, `runEscalation`, the SSE feed file (`askFeedPath`), and `findAskResult` all collide → one build's transcript/result is attributed to the other. Fix: add entropy at all three sites — `'ask-'+Date.now().toString(36)+'-'+crypto.randomBytes(4).toString('hex')` (or `crypto.randomUUID()`).
13. **[MED] Non-atomic `writeApprovals` → torn file + lost cards under concurrency.** `lib/approvals.js:124-131` plain `fs.writeFileSync` with NO temp+rename; `enqueueApproval` (engine) and `resolveApproval` (http) both do load→mutate→write, racing. A crash mid-write leaves a truncated `companion-approvals.json` that `loadPending` swallows → every pending real approval silently disappears. (`writeCardAcks` already uses temp+rename — mirror it.) Fix: write to `approvalsPath(root)+'.tmp.'+process.pid` then `fs.renameSync` over target (atomic same-volume), removing the torn-file mode.
14. **[MED] Server-side double-decision unguarded.** `/api/approve` (`server.js:500-531`) has no idempotency: two POSTs for one id (double-tap, app-then-wrist, retried fetch) BOTH run `resolveApproval` → TWO `companion-decisions.jsonl` lines (possibly approve AND reject) and TWO `runEscalation`s (duplicate builds). Fix: make `resolveApproval` idempotent — for real queued cards, if `pending.find(id)` is null AND not synthetic, return `{resolved:id, already:true}` and skip the decision line + escalation; for synthetic cards, `isCardSnoozed(root,id,sig)` first and no-op if already snoozed for the same evidence.
15. **[MED] Forced/auto-escalation de-dup (pairs with #3).** Once the intent net (#3) exists, a double-tap send or face-AND-intent-net both firing could spawn two concurrent sessions for one message (`MAX_INFLIGHT=2` allows it). Fix: escalate ONCE — prefer the face's structured task when `face.escalate`, else the intent-net task, never both. Add a ~10s de-dup in `escalate.js` keyed on a hash of the task text: if an identical task is already running/just-started, return the existing `ask_id` instead of starting a second session.
16. **[MED] `m.html` decide-catch strands a failed-to-send card.** `public/m.html` `decide()` catch only `setStatus(...)`+`setTimeout(refresh)` and does NOT `delete dismissed[a.id]` (app.js does). On an offline POST the card vanishes and stays in `dismissed{}` for the session → won't return on refresh, yet the decision was never logged. Fix: in the catch, `if(a&&a.id) delete dismissed[a.id]; lastApprovalsSig='__changed__';` so it re-renders next poll (matching app.js).

#### P2 — Hardening / hygiene (demand 4)

17. **[MED] `face_brain.py max_tokens=420` truncates the escalation block.** `face/face_brain.py:148`. A rich self-contained task + the human sentence can exceed 420 → the ```escalate JSON is truncated → `parse_escalation` `json.loads` fails → `(None, text)` → NO escalation. The richer the task, the likelier the silent failure. Fix: raise non-fast `max_tokens` to ~700-900; best combined with #3 so a truncated face block still yields a real session via the deterministic net.
18. **[MED] No maxTurns / market-hours pool guard.** `lib/escalate.js:223-231` omits `maxTurns`; a runaway autonomous loop burns the Max pool which (per CLAUDE.md) the heartbeat SHARES — a phone-triggered build 09:30-15:55 ET can starve heartbeat ticks. Fix: `maxTurns:60` (in the #1/#2 options block); consider warning/queueing market-hours escalations.
19. **[LOW] Whitespace-only face task spawns a near-empty build.** `server.js:481` only checks `face.escalate && face.task` truthiness. Fix: `if (face && face.escalate && String(face.task||'').trim().length > 3)`. Same check on the forced intent-net path.
20. **[LOW] `/api/approve action.task`/`action.model` unvalidated.** `server.js:509-520` passes `action.task` straight into the escalation; `action.model` coerces silently to sonnet via `MODEL_MAP` fallback (`escalate.js:192`). Fix: validate `action` shape — `if (action && action.type==='escalate'){ if (typeof action.task!=='string' || !action.task.trim()) action=null; else action={...action, task:action.task.slice(0,8000)} }`; clamp `model ∈ {opus,sonnet,haiku}` at the `runEscalation` boundary and log a coercion.
21. **[LOW] Feed-file growth never pruned (OP-22 violation).** `lib/escalate.js:30-60` appends to `companion-ask-feed/<id>.jsonl` per step and NOTHING deletes them — the dir leaks disk forever (every chat/approval/diagram = a new file). Fix: on server start and/or after each escalation finishes, prune `askFeedDir` to the most recent ~50 by mtime and/or delete files older than ~24h (best-effort, try-catch like the rest).
22. **[LOW] MCP surface for 3am autonomous runs.** `cwd=root` inherits the project `.mcp.json` (alpaca, alpaca_aggressive, tradingview). `guard.js DENY_TOOL` holds the order wall (regex `/^mcp__alpaca(_aggressive)?__(place|cancel|close|replace|exercise|do_not_exercise)/` matches the real tool names — verified), but `get_*` + any future write tool auto-allow. Not a money bug — a cost/surface concern. Fix: keep full MCP (builds may need TradingView reads) but document it, or pass an explicit `mcpServers` allowlist for escalations that don't need trading MCP. Keep `DENY_TOOL` as the hard wall.

---

### SUMMARY

Two of J's four demands are NOT met today:

- **Demand 1 (typed prompts reliably start a session): FAILS.** `/api/chat` (server.js:478-486) blindly trusts a prose-fragile FREE model's exact ```escalate fence (face_brain.py); chat-instead / no-fence / `max_tokens=420` truncation / rate-limit all silently degrade a do-request to a chat reply with NO session. There is zero server-side build-intent safety net. → Fix #3 (deterministic intent classifier) + #17 (raise face max_tokens).
- **Demand 3 (read the soul, be autonomous): FAILS as designed.** The escalation runs with a MINIMAL system prompt (no `systemPrompt` preset) — not the Claude Code agent, doesn't know it's Gamma, never sees the 10 rules / guard as soul. CLAUDE.md loads only incidentally as project context and can silently vanish on an SDK default flip (no `settingSources`). → Fix #1 + #2.

Demand 2 (approvals start sessions) works on the happy path but #4 (fail-green snooze) and #14 (double-decision) are real holes. Demand 4 (no bugs) is broadly violated by the strand/leak/race/zombie set (#5-#16) and the hygiene items (#17-#22). The single highest-leverage change is the SOUL block (#1+#2) — one options edit fixes demands 3 and a chunk of 4 at once. The single highest-leverage reliability change is the intent classifier (#3), which makes demand 1 deterministic regardless of the free model's mood.

---

## 2026-06-21 — Gamma Companion — Watch Claude Work Live + Fix the Approval Loop

**Date:** 2026-06-21 · after-4pm work block · plan-of-record
**Scope:** `gamma-companion/` only. No production doctrine, params, or heartbeat touched.
**Author:** research+audit synthesis (4 parallel findings, all cross-checked against the live files read 2026-06-21).

J's two demands:
1. The approval / task loop must work **end to end** — click checkmark/X → card actually clears (and stays cleared) → the underlying work runs → the display reflects it. Today obligation cards regenerate from live state so they bounce back, and approving an obligation runs a read-only *diagnosis* that can never satisfy the obligation.
2. J wants to **SEE Claude working** on his PC in real time — tool calls, file edits, commands, reasoning — like watching Claude Code in a terminal, not a black box.

---

### 0. Ground truth (what the files actually do today)

Verified by reading the real source, not the prose contracts:

| Concern | File:lines | Reality |
|---|---|---|
| Escalation chokepoint | `lib/escalate.js:120-134` | `for await (const message of query(...))` body **only** handles `message.type === "result"`. Every `assistant` (tool_use/text/thinking), `user` (tool_result), and `system/init` message is silently dropped. **No `includePartialMessages`** in the options block (121-127). This is the black box. |
| Abort / cancel | `lib/escalate.js:110-111,126,138` | Already correct: `AbortController` created, passed as `options.abortController`, tracked in `controllers` Map, `cancelTask()` aborts, `ac.signal.aborted` distinguishes cancel vs error. **Survives the streaming refactor unchanged.** |
| Task registry | `lib/escalate.js:33-59` | `tasks` Map tracks status only (running/done/...). `getTasks()` exposes `running`/`recent`. No steps, no `sessionId`. |
| Obligation cards | `server.js:298-334` | `fullState()` calls `checkObligations(ROOT)` **every** `/api/state` poll, rebuilds `obCards` fresh, **prepends** to `state.approvals` (320). Card ids are `oblig-<id>` — synthetic, function of live state only. |
| Approve resolution | `lib/approvals.js:112-152` | `resolveApproval` removes `id` from `companion-approvals.json`. Synthetic obligation cards were **never written there** → it removes nothing → next 5s poll regenerates the card. **Root cause of bounce-back.** |
| Obligation "fix" task | `server.js:310-318` | The approve action is `escalate` with task = "Diagnose ... propose or apply a SAFE fix ... **Report findings.**" — read-only. Even on success the evidence file is still stale → `checkObligations` still `!ok` → card returns. **Approving can never clear it by design.** |
| Desktop UI | `public/app.js:130-146,246-261` | `decide()` **already** calls `trackAsk(j.escalated)` (138); A-1 retry affordance **already** present (140-145). `trackAsk` polls `/api/ask-result` for the FINAL blob only. Cards are cleared by `card.textContent=` mutation + `refresh()`, **not** a `dismissed` map → on desktop the regenerated card visibly returns on the next poll. |
| Mobile UI | `public/m.html:191,230-242` | Has a client-side `dismissed{}` map (191) + optimistic `vanish()` so cards stay hidden. BUT on `j.escalated` it only `addAsk("Gamma","On it…")` — a **static string**; it **never calls `trackAsk`** → the PWA shows zero progress and never the result for a card-approved build. **Mobile dead-end.** |
| Polish doc | `_REMAINING-POLISH-2026-06-21.md` | S-1 (state.js guard) and A-1 (retry affordance) are **already applied** in the current files. Remaining un-applied: A-2, A-3, A-4, A-5, A-6, R-1, C-1..C-7, G-1, G-2, SV-1. |
| SDK | `package.json:13` | `@anthropic-ai/claude-agent-sdk ^0.3.185`. `includePartialMessages` is the documented flag for `stream_event` deltas. `smoke-sdk.js` proves the path works. |

---

### 1. Reuse vs build (do NOT reinvent)

**Decision: build a thin streaming + SSE layer on top of the existing single chokepoint. Reuse the SDK's own streaming API. Do NOT clone any external project.**

| Candidate | Verdict | Why |
|---|---|---|
| **Claude Agent SDK `includePartialMessages` + the `assistant`/`user`/`stream_event` message stream** | **REUSE — this is the whole engine** | Official, documented (code.claude.com/docs/en/agent-sdk/streaming-output), already imported in `escalate.js`, already proven by `smoke-sdk.js`. The data J wants to see (tool names, file paths, commands, reasoning, live typing) is *already emitted* by `query()` — escalate.js just throws it away. One flag + one dispatcher unlocks it. |
| **SSE via Node `http` (`text/event-stream`)** | **REUSE Node built-ins — build the endpoint** | Zero new npm deps (matches the companion's zero-dep server). Browser-native `EventSource`, auto-reconnect, HTTP-only — no WebSocket handshake, no second port, preserves the 127.0.0.1-only safety model. |
| `ninehills/claude-agent-ui`, `hoangsonww/Claude-Code-Agent-Monitor`, `patoles/agent-flow` | **DO NOT clone** | They are full *rewrites* of the orchestrator with their own approval/task systems. Adopting any means ripping out the existing guard/obligation/approval wiring. We borrow one idea only: their per-tool *humanize* rendering ("Reading X", "Ran: cmd") — re-implemented in ~30 lines, not vendored. |
| `xterm.js` + `node-pty` / `ttyd` (real terminal) | **DEFER to Phase 3, probably never** | The escalation is **headless SDK** — there is no shell process and no Claude window to mirror. A PTY would only show a *new* shell we'd have to drive separately; it does not show what the SDK agent is doing. The faithful in-app equivalent of "watch Claude Code" is the streamed tool/edit/command transcript (Phase 1), which needs **zero** new deps. `node-pty` also adds a native-module/conpty build dependency on Windows — fragility we don't need. Only build it if J explicitly wants an interactive shell pane *in addition*. |

**Bottom line:** the leanest path that satisfies both demands is ~entirely first-party. The SDK already produces the feed; we stop discarding it, persist it per-ask, and push it over SSE to a transcript panel that both frontends already have the scaffolding for (`addAsk`/`addMsg` + `trackAsk`).

---

### 2. Watch Claude work live — concrete design

#### 2.1 Capture (lib/escalate.js)

Add **one flag** and replace the result-only loop with a **message dispatcher**.

```js
// options block — add:
includePartialMessages: true,

// loop body — replace the single `if (message.type === "result")`:
for await (const m of query({ prompt: task, options: {...} })) {
  if (m.type === "system" && m.subtype === "init") {
    sessionId = m.session_id;
    emit(id, { step: "session", sessionId, model: m.model, tools: (m.tools||[]).length });
  } else if (m.type === "assistant") {
    for (const b of (m.message?.content || [])) {
      if (b.type === "text")     emit(id, { step: "text", text: b.text });
      else if (b.type === "thinking") emit(id, { step: "thinking", text: b.thinking });
      else if (b.type === "tool_use") emit(id, { step: "tool", name: b.name, label: humanize(b.name, b.input) });
    }
  } else if (m.type === "user") {
    for (const b of (m.message?.content || [])) {
      if (b.type === "tool_result") emit(id, { step: "tool_result", ok: !b.is_error, preview: String(b.content||"").slice(0,200) });
    }
  } else if (m.type === "stream_event") {
    const e = m.event;
    if (e.type === "content_block_start" && e.content_block?.type === "tool_use")
      emit(id, { step: "tool_start", name: e.content_block.name });
    else if (e.type === "content_block_delta" && e.delta?.type === "text_delta")
      emit(id, { step: "delta", text: e.delta.text });
    // thinking_delta / input_json_delta optional — text_delta is the live-typing win
  } else if (m.type === "result") {
    resultText = m.result || resultText;
    subtype = m.subtype || "";
    ok = m.subtype === "success" && !m.is_error;
    emit(id, { step: "result", ok, subtype, cost: m.total_cost_usd, ms: m.duration_ms });
  }
}
```

`humanize(name, input)` maps tool calls into J's language:
- `Read` → "Reading " + basename(file_path)
- `Edit`/`Write` → "Editing " + basename(file_path)
- `Bash` → "Ran: " + command.slice(0,80)
- `Grep` → "Searching: " + pattern
- `Glob` → "Finding " + pattern
- `mcp__*` → the MCP tool name
- default → the raw tool name

`emit(id, rec)` does two things, both best-effort/never-throws:
1. **Durable trace:** append `rec` to `automation/state/companion-ask-feed/<id>.jsonl` (mkdir the dir like `appendResult` does). A late-joining or reconnecting client replays this to catch up.
2. **Live push:** write `data: <json>\n\n` to every SSE response currently subscribed to `<id>`. Maintain `Map<id, Set<res>>` plus `subscribe(id,res)`/`unsubscribe(id,res)`, exported from escalate.js.

Capture `sessionId` into the task registry (`setTask(id, { sessionId })`, expose via `slim()`/`getTasks()`) so a future "continue this build" can call `runEscalation` with `options.resume = sessionId`. (Resume UI is optional follow-up, not in this release.)

**Guard interaction (important):** `includePartialMessages` does NOT bypass `makeCanUseTool` (guard.js). A `tool_start` for a denied tool will still stream — the actual execution is gated and the deny surfaces in `result.permission_denials[]`. The transcript will honestly show "Using Edit…" then the result/deny. Fine.

#### 2.2 Transport (server.js) — new SSE endpoint

```
GET /api/ask-stream?id=<askId>&tok=<token>
  content-type: text/event-stream; cache-control: no-store; connection: keep-alive
  1. replay existing companion-ask-feed/<id>.jsonl lines as data: frames (catch-up)
  2. subscribe(id, res) for live frames
  3. on req 'close' → unsubscribe(id, res)
```

Auth nuance: `EventSource` **cannot set headers**, so it can't carry `x-gamma-token`. Mirror the existing signed-token pattern (`push.mintApproveToken` / `/api/approve-signed`): mint a short-lived per-ask **stream token** when the ask is created and pass it as `?tok=`. (Or, given the server is 127.0.0.1-only and the stream is read-only telemetry, accept same-origin without a token — but the signed-token path is the consistent, safe choice and reuses existing crypto.)

Keep `/api/ask-result` as the durable final-summary fallback for reconnect.

#### 2.3 Render (public/app.js + public/m.html) — the "Gamma sandbox panel"

Both frontends already have a transcript area (`addMsg`/`addAsk`) and `trackAsk`. Upgrade `trackAsk(askId)` to:
1. Open `new EventSource('/api/ask-stream?id=' + askId + '&tok=' + tok)`.
2. Render each step as a live transcript row:
   - `tool` / `tool_start` → "▸ Reading state.js", "▸ Ran: pytest …", "▸ Editing escalate.js"
   - `text` / `delta` → Claude's narration, appended/typed live
   - `thinking` → dimmed reasoning line
   - `tool_result` → "✓ done" / "✗ error" with the short preview
   - `result` → final summary + "Done in 4.2s · $0.03", then `es.close()`
3. **Fall back to the existing `/api/ask-result` polling** if `EventSource` errors (`onerror`) — so a blip degrades gracefully to today's behavior instead of a blank.

This is J's in-app "watch Claude work" surface — it mirrors a Claude Code terminal without a terminal, with zero new deps.

#### 2.4 Terminal / real-window extras — explicitly out of this release

- **Phase 3a (optional, only if asked):** `xterm.js` + `node-pty` modal pane for an *interactive* shell — adds a native dep and a second IO model. Not load-bearing; the transcript already proves "Claude is running commands on your PC."
- **Phase 3b (optional, only if asked):** Electron main spawning a visible `claude --print` window. The companion runs as a Node HTTP server today, not the Electron renderer; this fragments into two windows. Skip unless J specifically wants the actual Claude window.

---

### 3. Redesigned approval loop (click → display → work done → reflected)

The current loop conflates two different things: **"I've acknowledged this"** (should clear the card) and **"the evidence is now fresh"** (the real fix the build works toward). Separate them.

#### 3.1 Make obligation/derived cards honestly resolvable (server truth, not a client hack)

- **Ack/snooze store:** `automation/state/companion-card-acks.json`, keyed by `oblig-<id>` → `{ until_iso, evidence_sig }` where `evidence_sig` is the obligation's `detail` (or evidence mtime). Written by `resolveApproval` when the id starts with `oblig-`/`act-` (synthetic, not in the file queue): snooze ~30-60 min.
- **`fullState()` suppression** (`server.js:302-320`): before prepending `obCards`, filter out any whose `oblig-<id>` is acked AND not expired AND the `evidence_sig` is unchanged. The card actually clears and **stays** cleared until the snooze lapses OR the evidence genuinely changes (then it correctly re-surfaces — we never permanently hide a real red).
- **Retire the client `dismissed{}` hack** as the *source of truth*: m.html's `dismissed{}` (191) becomes a pure optimistic-paint that the server snooze now backs, so it survives reload. Port the same optimistic-hide into app.js `renderApprovals`/`decide` so the desktop card vanishes immediately and doesn't flicker back on the next 5s poll.

#### 3.2 Card ↔ ask ↔ resolution linkage

- `runEscalation` accepts the originating `card_id`; store it on the task and the `companion-ask-results` record.
- `/api/approve` for an obligation card records `decision: "approve_pending"` (not a final clear). On escalation completion, append the terminal decision **plus a re-check** of that one obligation's evidence (re-run `checkObligations` filtered to the id) to record whether it *actually* cleared.

#### 3.3 Make the "fix" able to actually meet the obligation (where safe)

For obligations whose remedy is **re-running a producer** (premarket, gym, EOD) rather than editing a denylisted doctrine file, change the escalation task from "diagnose + report" to "**run the producer script and verify its evidence file is fresh**" (e.g. `setup/scripts/run-premarket.ps1`, gym-session). Then completion genuinely clears the card. Keep diagnosis-only for engine-health/params-class obligations that `guard.js` DENY_WRITE forbids touching — those snooze + flag, they don't self-heal.

#### 3.4 Fix the mobile dead-end (immediate, one line)

`public/m.html:238` — on `j.escalated`, call `trackAsk(j.escalated)` (as app.js:138 already does) instead of only `addAsk("Gamma","On it…")`. Without this, every card-approved build on the phone is invisible. This is the single highest-value/lowest-effort fix in the whole plan.

---

### 4. Honest effort + fragility

| Area | Effort | Fragility |
|---|---|---|
| `includePartialMessages` flag + dispatcher | Low-med | Low. SDK message shapes are documented + stable; defensive `?.` guards mean an unexpected block type just isn't rendered. |
| `emit` + per-ask JSONL + SSE registry | Med | Low. Best-effort writes; SSE is one-way text. Main risk = leaking subscriber `res` objects → mitigated by `req.on('close')` unsubscribe. |
| SSE endpoint + per-ask stream token | Med | Low-med. EventSource header limitation forces the `?tok=` path; reuse existing HMAC mint/verify to avoid a new auth surface. |
| Frontend transcript (both UIs) | Med | Low. Falls back to existing `/api/ask-result` poll on `EventSource` error. |
| Obligation ack/snooze + fullState filter | Med | **Highest-care item.** Must NOT permanently hide a real red — the `evidence_sig` + expiry guarantees auto-re-surface. Test the still-stale-after-build case explicitly. |
| Card↔ask linkage + approve_pending | Med | Low. Additive record fields. |
| Producer-rerun fix tasks | Med | Med. Re-running PowerShell producers from an SDK Bash call on Windows can be flaky; verify evidence-file freshness as the success gate, not exit code (LESSONS-LEARNED C7). |
| m.html `trackAsk` one-liner | Trivial | None. |
| Remaining polish (A-2..A-6, R-1, C-*, G-*, SV-1) | Low each | Trivial; S-1 + A-1 already shipped. |

**Net:** Phase 1 (streaming + SSE + transcript + mobile one-liner) is a single after-4pm session and satisfies demand 2 immediately. Phase 1b (approval ack/snooze + linkage) satisfies demand 1 and is the same session if time permits, else the next block. Phase 2 (producer-rerun self-heal + polish) follows. Phase 3 (terminal/window) is deferred indefinitely unless J asks.

---

### 5. Build order (ranked)

1. **m.html `trackAsk` one-liner** — kills the mobile dead-end. ~0.3h.
2. **Stream capture in escalate.js** (`includePartialMessages` + dispatcher + `humanize` + `emit` + SSE registry). ~3h.
3. **SSE endpoint in server.js** (`/api/ask-stream`, replay + subscribe + per-ask token). ~2h.
4. **Transcript panel in both frontends** (EventSource in `trackAsk`, render steps, poll fallback). ~3h.
5. **Obligation ack/snooze + fullState filter + server-truth dismissal** (stop bounce-back without hiding real reds). ~4h.
6. **Card↔ask linkage + approve_pending + post-build re-check.** ~2h.
7. **Producer-rerun fix tasks** (premarket/gym/EOD self-heal where guard-safe). ~3h.
8. **Capture `sessionId` for future resume.** ~0.5h.
9. **Remaining polish** (A-2, A-3, A-4, R-1, then A-5/A-6/C-*/G-*/SV-1). ~1.5h.
10. **Smoke + manual verify** (extend `smoke-sdk.js` → assert feed JSONL has a tool/text step + final result + sessionId; `smoke-guard.js` stays green; manual `/api/approve` → watch transcript stream → card clears + result lands; desktop + phone). ~1.5h.

---

### 6. Testing / acceptance

- `node --check` on every edited `.js`; `node gamma-companion/smoke-guard.js` stays green.
- New `smoke-stream.js` (or extend `smoke-sdk.js`): run a tiny escalation with `includePartialMessages:true`, assert `companion-ask-feed/<id>.jsonl` contains ≥1 `tool`/`text` step **and** a final `result` step, and `sessionId` was captured. End-to-end pipe proof without UI.
- Manual: POST `/api/approve` from m.html with a real task → transcript panel populates with "Reading … / Ran: … / Editing …" live → approval card disappears and **stays gone** → final result appears in the feed. Repeat on desktop. Kill the SSE mid-stream → verify graceful fallback to `/api/ask-result` poll, not a blank.
- Obligation regression: approve an obligation whose evidence is still stale after the build → card snoozes, then **correctly re-surfaces** when the snooze lapses (never permanently hidden).

---

## 2026-06-21 — Sunday Master Plan

> 24-hour weekend-grind plan. Goal: make Gamma a better trader that makes **actual money**.
> Ranked by leverage (money-unlocked per hour). Honest EV, no hype. READ-ONLY survey -> this plan; execution starts when Gamma picks up.

---

### Headline

**The single highest-leverage move is WP-0: the order-builder per-setup-stop refactor.** It is verified-absent in code and is the *only* thing standing between two fully-validated edges (#2 vwap_reclaim_failed_break, #4 vix_regime_dayside) and live money. Everything else this weekend either (a) de-risks WP-0, (b) refines/validates the one LIVE edge, or (c) runs as a free parallel backtest/data track. The research frontier for *new* edges is honestly exhausted for this bull regime — do not spend the weekend hunting a 54th mechanical family.

---

### Ground truth verified this session (not taken on faith)

| Claim | Verified | Evidence |
|---|---|---|
| Per-setup -0.08 keys exist in params.json, edges dormant | YES | `automation/state/params.json` L77 (`j_vwap_reclaim_fb_premium_stop_pct: -0.08`), L84 (`j_vix_dayside_premium_stop_pct: -0.08`), both `enabled: false` |
| filters.py isolated accessors exist (single source of truth) | YES | `backtest/lib/filters.py` L1459 `vwap_reclaim_failed_break_premium_stop_pct`, L1551 `vix_dayside_premium_stop_pct` |
| NO code selector reads them at order-build time | YES | grep for `select_exit_params / per_setup_stop / setup_stop_override / premium_stop_pct_override` = **zero hits** in `backtest/lib/`, `automation/scripts/`, `setup/scripts/` |
| risk_gate.check_order already receives setup_name (natural home) | YES | `backtest/lib/risk_gate.py` L189 `setup_name`, used at L288/L371 |
| Heartbeat step 6 hardcodes the GLOBAL ×0.50 for EVERY entry | YES | `automation/prompts/heartbeat.md` L783 (BEAR ×0.50) / L784 (BULL ×0.50) — no per-setup branch; setup blocks L385/L399/L410/L425 *say* "use isolated -0.08" but the shared step-6 path ignores it |
| Real-fills option cache ends 2026-05-29; bars run later | YES | `backtest/data/options/` last expiry = `SPY260529*`; `spy_5m_*` to 2026-06-18, `vix_5m_*` to 2026-06-19 → **~14-day real-fills blind spot** |
| LIVE edge #1 has zero tracked fills | YES | `journal/trades.csv` = 16 lines (15 data rows), last fill 2026-06-15 `BULLISH_RECLAIM`, **zero `vwap_continuation`** |
| No order/bracket parity test exists | YES | `backtest/tests/` has `test_engine_{cli,gates,score}_parity.py` — none for order brackets |

**The disconnect in one sentence:** flipping `j_vwap_reclaim_fb_enabled=true` or `j_vix_dayside_enabled=true` today would silently ship a **-0.50** bracket on an edge validated at **-0.08** = a *broken* edge (chart-stop-only OOS goes negative when truncation is wrong). WP-0 closes that.

---

### The 24-hour sequenced plan (highest leverage first)

#### Track A — SERIAL build track (the money path). Do these in order.

**A1 — Backfill the option-chain real-fills cache May-30 → Jun-19 (DO FIRST, it's the only non-offline step).**
Why first: every "OOS through today" claim is currently silently degraded; this is the prerequisite that makes ALL weekend validation honest, *and* it needs the live Alpaca historical API (not pure-offline), so it must run before the offline grids, not as a background task.
First step: `backtest/.venv/Scripts/python backtest/tools/fetch_option_data.py` — dry-list the missing contract symbols for 2026-05-30..06-19 first, confirm the v1beta1/options/bars endpoint authenticates, then run the backfill writing `backtest/data/options/{symbol}.csv`.
Effort: ~1.5h. EV: HIGH (unblocks honest OOS for everything below). Risk: LOW. Ships: data/infra.
KILL: if the Alpaca historical API is unreachable this weekend, do NOT fake it — flag the gap in STATUS.md, scope every downstream grid to `<=2026-05-29`, and continue.

**A2 — Build the data-coverage manifest + assertion (cheap, graduates the blind-spot foot-gun to code).**
Why now: the blind spot was invisible until manual `ls`. A `backtest/tools/data_coverage_manifest.py` that prints `[first,last,n_days]` per data class and ASSERTS option-cache span >= bar span turns "is my OOS real or degraded?" into a code check (autonomy-blueprint: graduate prose→assertion at boundaries; OP-25 silent-failure guard).
First step: write the script, run it now — it MUST report the 2026-05-30..06-19 blind spot as DEGRADED (or OK if A1 already backfilled), emit `automation/state/data-coverage.json`.
Effort: ~2h. EV: MED. Risk: LOW. Ships: infra.

**A3 — Build the order-bracket parity test FIRST (the safety net BEFORE the refactor).**
Why before A4: the live order math lives only in heartbeat prose; there is zero automated guard that an edit preserves the -0.50/-0.08 brackets. Building the test first de-risks WP-0 and is independently valuable.
First step: create `backtest/tests/test_engine_order_bracket_parity.py` asserting (a) all per-setup flags OFF → resolved stop == today's global bear/bull -0.50; (b) `setup=vwap_reclaim_failed_break` → -0.08, `setup=vix_regime_dayside` → -0.08, unknown setup → -0.50 (mirror the existing watcher-test -0.08 assertions in `test_vwap_reclaim_failed_break_watcher.py`).
Effort: ~2h. EV: HIGH. Risk: LOW. Ships: infra (the L174/C14 graduation the doctrine demands).
KILL: if the order path can't be made deterministic enough to assert byte-identity, that *itself* is the finding — the prose order-math must be code-ified first; escalate the untestability, don't paper over it.

**A4 — Ship WP-0 core: `select_exit_params(setup_name, side, params)` in risk_gate.py + wire the backtest order path.**
The single highest-EV action on the rig. Two edges validated 8/8 gates on real OPRA fills (#2 OOS +$32–72/tr, #4 OOS +$79.49/tr — the cleanest, chart-stop-only POSITIVE) are dormant blocked ONLY here.
First step: add a pure dispatch fn in `backtest/lib/risk_gate.py` (already takes `setup_name` at L189) keyed `{vwap_reclaim_failed_break, vix_regime_dayside, vwap_continuation, gap_and_go}` → the matching `filters.py` accessor (L1459/L1551 — reuse verbatim, single source of truth), default branch → global `premium_stop_pct` (-0.50). Wire it into the real-fills order path so a matched+enabled setup overrides the side stop; else byte-identical. Run `backtest/.venv/Scripts/python -m pytest backtest/tests/ -k 'graduated or parity'`.
Effort: ~4h. EV: HIGH. Risk: MED. Ships: infra → unlocks 2 edges. **Flips NO enabled flag** — no live behavior change until a deliberate daylight flip + REVOKE note.
KILL: if the parity/graduated suite shows ANY non-identical bracket with all flags OFF, STOP and revert — the refactor is not behavior-preserving.

**A5 — Gamma-sync heartbeat.md steps 6/7 to the same per-setup branch (no live drift).**
Why: OP-4 forbids code drift between live and backtest. Step 6 (L783-784) must resolve the stop by the same dispatch table as `select_exit_params`, falling back to -0.50.
First step: invoke the `gamma-sync` skill; rewrite heartbeat.md step 6 so it looks up the active setup's isolated key, else the global cap; run the full pytest suite via `backtest/.venv`. Keep all `enabled=false`. **After-4pm/weekend window only — never mid-session (Rule 9).**
Effort: ~2h. EV: HIGH. Risk: MED. Ships: infra.
KILL: if the prose can't be expressed unambiguously for an LLM tick, extract the bracket math into a tiny callable script the tick invokes (graduate prose→code) rather than leaving load-bearing arithmetic in prose.

**A6 — Pre-compute the WP-0-unlock A/B scorecards for #2 and #4 (so they ship zero-lag the moment A4/A5 land). — ✅ DONE 2026-06-21: both SHIPPABLE (8/8 gates).**
> VERDICT: **#2 `vwap_reclaim_failed_break` SHIPPABLE-WITH-CAVEAT** (ITM-2/ATM only — OTM-2 FAILS 6/8; OOS +$72.11/tr n=76 but OOS-alone < same-day null mean = day+side selection). **#4 `vix_regime_dayside` SHIPPABLE, cleaner** (ATM/Safe-2, OOS +$79.49/tr n=21, strongest null separation; caveat: chartstop-only OOS +$0.15 → edge is the −8% option structure, not point-direction). Data capped 2026-05-15, asserted last-fill = 2026-05-15 ≤ 2026-05-29 (blind spot not reached). **⚠ L174: neither edge is independent of LIVE #1 (100% same-side day overlap) — ship as #1-overlays, size as concentration not diversification.** OP-16: both fire on 0 of J's losing anchors (no regression). Scorecards in `analysis/recommendations/`.
OP-11 requires an A/B scorecard at `analysis/recommendations/{rule_id}.json` BEFORE any flip. Their VALIDATION doesn't need the refactor — only their SHIP does.
First step: re-run `_sub_struct_vwap_reclaim_failed_break.py` and `_b5_vix_regime_dayside.py` via `backtest/.venv`, **hard-windowed to `<=2026-05-29`** (assert `last_date` in output), emit refreshed scorecards with full-sample expectancy, OOS sign, drop-top-5 (L173), random-null delta, no-truncation sign, and the 7-anchor no-regression check. Write a one-line "data coverage: last real-fill 2026-05-29" caveat into each.
Effort: ~3h. EV: HIGH. Risk: LOW. Ships: research_only (decision-grade, ship-ready).
KILL: if either edge fails any of the 8 gates on the clean window (e.g. #2's OOS-alone collapses inside the same-day null band — a known caveat), mark NOT-SHIPPABLE in the scorecard; WP-0 still ships (it's correct infra + unlocks the other edge).

#### Track B — runs in PARALLEL with Track A (independent, free, no shared write surface).

**B1 — Live-fire smoke test: prove vwap_continuation actually emits a paper entry. — ✅ DONE 2026-06-21: LIVE_EDGE_FIRES_OK.**
> VERDICT: the LIVE edge `vwap_continuation` **fires end-to-end** — NOT a wiring break. Detector fires on cached 5m bars (162 signal dates); LIVE watcher streamed bar-by-bar matches with full parity (3/3 side+trigger-time); registered in `runner.WATCHERS`; Safe-2 heartbeat would ENTER correct side+strike with real OPRA fill (3/3). Zero tracked fills = "no signal yet" (flag live <2 trading days). **2 live-path gaps surfaced (daylight fixes):** (1) edge is INERT on Bold — `j_vwap_cont_enabled` missing from Bold params → defaults FALSE; (2) Safe-2 at $2K fires OTM-2, not the validated ATM/ITM-1 cell (C3/C29 — re-confirm at live strike). Built `backtest/autoresearch/vwap_smoketest.py`; finding in `analysis/recommendations/B1-VWAP-SMOKETEST.md`.
The one "LIVE" edge has produced **zero** tracked fills. Before tuning anything on top of it, confirm the watcher→heartbeat→order path emits a `vwap_continuation` bracket on a replayed historical signal day (pick 2-3 dates from `sel-vwap-continuation.json` inside the option-cache span). Catches a silent wiring break before Monday's open.
First step: run `backtest/autoresearch/vwap_smoketest.py` on the chosen dates to confirm the detector fires from cached 5m bars; then drive the `chart-reading-gym` skill / heartbeat replay and assert the emitted decision == ENTER vwap_continuation, correct side, strike_offset=-2.
Effort: ~2h. EV: HIGH (cheap validation of the only live edge). Risk: LOW. Ships: research_only (the bug, if any, is the deliverable → STATUS.md).

**B2 — Long-running parallel backtest grid: VIX-feed reconstruction + edge #4 re-validation. — ✅ DONE 2026-06-21: VIX_FEED_PINNED (parity proven, no bug).**
> VERDICT: the reconstructed intraday VIX feed reproduces the research detector with **ZERO divergence in all 8 cells (jaccard 1.0)** — median/slope primitives byte-identical, last signal 2026-05-29 (== OPRA cache edge, no silent degradation). Edge #4's SECOND blocker is now a pure wiring step, NOT a parity bug — no escalation. Spec pinned (source=^VIX 5m RTH closes, UTC-ffill onto SPY grid, `rolling(78,min_periods=19).median().shift(1)`, causal 5-bar slope, ET morning gate). Remaining live step (out of Sunday scope): heartbeat keeps a rolling ≥78-bar today-session VIX buffer → set `ctx.vix_intraday`. Deliverables: `analysis/recommendations/B2-VIX-FEED-SPEC.md` + `B2-vix-feed-parity.json` + `backtest/autoresearch/_b2_vix_feed_parity.py`.
This is the "long grid churns while we build infra" track. Edge #4 needs an intraday VIX series (trailing-median-78 + 5-bar slope) the live BarContext doesn't carry — reconstruct it offline from `vix_5m_2025-01-01_2026-06-16.csv`, re-validate #4 on the full available span, and pin the exact live-feed spec (lookback=78, slope-window=5, source=VIX 5m RTH closes) that the heartbeat must reproduce.
First step: load the vix_5m CSV, compute as-of trailing-median(78)+5-bar slope per RTH bar (causal), run `vix_regime_dayside_watcher.py` against spy_5m + reconstructed `ctx.vix_intraday` for 2025-01..2026-05-29, diff against `analysis/recommendations/b5-vix-regime-dayside.json`.
Effort: ~4h wall (mostly compute). EV: HIGH (this is the SECOND blocker on the cleanest edge — independent of WP-0). Risk: LOW. Ships: research_only + a written feed spec.
KILL: if the reconstructed series doesn't reproduce the existing scorecard within noise, that's a parity bug — escalate, don't ship the feed.

**B3 — Mine the WeBull 2021-2023 corpus for a per-setup/hold-time/lot-size expectancy table (bar-independent, fully offline, sidesteps the blind spot entirely).**
J's 4818 real broker order rows are the densest untapped ground-truth on his actual edge (the L168 sizing-up finding came from here). SCOPE-HONEST: filter to **SPY 0DTE only** (~563 of 4818 rows; the rest are SPXW/SPX, out of locked scope).
First step: pandas — pair Open/Close on Symbol+Filled-Time into round-trips, filter to SPY 0DTE, bucket by hold-time / lot-size / side / entry-hour, compute per-bucket expectancy + N; cross-check vs L168.
Effort: ~3h. EV: MED (likely thin: SPY-only N may not clear N>=20/bucket). Risk: MED. Ships: research_only (feeds OP-16 edge-capture).
KILL: if SPY-only buckets are all N<20, log "WeBull SPY subset too thin; SPX out of scope" and stop — don't re-derive L168.

#### Track C — low-effort hygiene + decision-grade items (fit into gaps).

**C1 — Confirm + RETIRE the 4 SWJSHAK strats as DEAD (do NOT re-test).**
All 4 were already real-fills-tested overnight (2026-06-20) with the exact OP-11/random-null/no-truncation gates and all 4 honestly failed (C3/L58 0DTE-wall). Re-running burns tokens against a settled negative.
First step: READ `analysis/recommendations/swjshak-{ema-adx-gate,sd-zone-reversal,three-ducks,bollinger-squeeze}.json` (each `self_verify ALL_PASS=false`), propose one-line DEAD entries for `markdown/research/STRATEGY-BACKLOG.md` (Hunt queue), mark `markdown/_attic/SWJSHAK-STRATEGY-EXTRACTION-2026-06-20.md` as superseded.
Effort: ~0.75h. EV: MED (prevents a future BRAINSTORM re-queueing dead work — OP-22/OP-25). Risk: LOW.

**C2 — WP-3 sizing: surface the cap-clamped contracts-per-tier table (v15 nominal counts BREACH Rule 6 at $2K).**
A live correctness/compliance issue independent of any edge: B10 found Safe base-5 = 34.5% vs 30% cap, Bold elite-8 = 102.8% vs 50% cap. The engine could currently size a Rule-6 violation.
First step: read `analysis/recommendations/B10-SIZING-SCORECARD.json` + params `position_sizing_tiers`, write the quarter-Kelly + min-3 clamped table as a DRAFT params decision (surface to J as a decision, not a flip — it's a sizing/safety change).
Effort: ~1h. EV: MED. Risk: LOW. Ships: research_only (J-ratify).

**C3 — Garbage-collect strategy/candidates/ (427 stale files) + drain stale cook-queue.**
OP-22 CONSOLIDATION trigger. Newest meaningful candidate is 2026-06-01, all superseded by the 3-edge inventory.
First step: inventory by mtime + first-line strat name; grep code for any hard `candidates/` path-read (verify-no-consumer-before-delete, C7); archive pre-2026-06-15 files, close 15 stale cook-queue tasks.
Effort: ~1.5h. EV: LOW. Risk: LOW. Ships: infra.

---

### What runs in PARALLEL

- **Track A is serial** (A1→A2→A3→A4→A5→A6) — each step gates the next (backfill → manifest → parity-test → refactor → sync → scorecards).
- **Track B runs concurrently with Track A** — B1 (smoke test), B2 (VIX-feed grid, the long churn), and B3 (WeBull mine) share NO write surface with the order-path refactor. B2 is the designated "long backtest grid churning while we build infra."
- **Track C** fills idle gaps (C1/C2/C3 are read-mostly, minutes each).
- Hard ordering constraint: **A6 depends on A1** (honest OOS needs the backfill, or the `<=2026-05-29` window). **B2 is independent of A1** (it re-validates on the span we already hold).

---

### Cut list (ruthless — NOT worth doing this weekend, and why)

- **Hunting a 54th mechanical/external strategy family.** The ~42-family mechanical/external vein is exhaustively dry (B0-B10). Re-mining is negative-EV by construction.
- **Re-testing the 4 SWJSHAK strats.** Already real-fills-tested and killed overnight with the exact gates this workflow demands. Re-running = tokens against a settled negative. (Retire them via C1 instead.)
- **The EMA-ADX PUT-side asymmetry probe.** The single non-dead SWJSHAK residual (PUT +$15/tr n=44) is already OOS-2026 **negative** (-8.4) and fails no-truncation (sign inverts +3.4→-41.6). A confirm-it's-dead probe, not a promote — skip; the verdict is already in the scorecard.
- **Any OTM+wide-stop configuration.** Doctrine-dead (C3: OTM theta/delta eats alpha; ITM+tight = edge, OTM+wide = bleed). #2/#4 ship ATM(Safe)/ITM-2(Bold) at -0.08 ONLY.
- **New instruments / crypto-as-tradeable.** Scope locked: 0DTE SPY + futures only; crypto is gym-only.
- **The 8 online-research vectors (GEX, flow sweeps, charm/vanna, PCR, IV-rank, OI-skew) as NEW live triggers.** Interesting but: (a) most need paid/real-time feeds we don't have offline, (b) they can only be tested as shadow overlays on the one live edge until WP-0 ships, and (c) the volume-PCR / volume-magnet overlays are the only ones buildable offline this weekend and they're MED-EV exit-mechanic tuners (C28: diminishing returns once stop-rate >70%). Defer all of them behind WP-0. The one cheap, doctrine-clean offline overlay worth a *single* fast probe IF Track A finishes early is volume-PCR-confirms-trend on the LIVE edge — but it is explicitly below the cut line vs A1-A6/B1-B2.
- **Wiring the companion autobuild FIRE (§5b of the wiring plan).** It spawns Claude — out of weekend-safe scope. (Companion module *wiring* + the spend-cap are good autonomy items but rank below the money path; do them only if A+B finish.)
- **Conductor model routing / daily spend cap.** Real OP-3 wins (conductor fires Opus every wake ≈ 918/day) but they're cost-hygiene, not money-unlocked-per-hour; schedule for the next after-hours block behind the edge work, not ahead of it.

---

### Honest EV summary

The money this weekend is **not** a new edge — it's **graduating the per-setup-stop from validated-params to live code (WP-0)**, which converts two already-paid-for, 8/8-gate-validated edges from dormant to ship-ready, plus **de-risking the one live edge** (prove it actually fires; close the data blind spot so its OOS is honest). New-vein research is correctly a free parallel churn (B2 VIX-feed) and a ground-truth mine (B3 WeBull), not the headline. Everything in the cut list is either doctrine-dead, already-killed, or cost-hygiene that ranks below the money path.

---

## 2026-06-20 — Gamma Morning Brief (overnight 2026-06-20 → 06-21)

> Chief-of-staff brief for J. The team ran on top of tonight's safety foundation. Nothing live was touched: no doctrine, no params, no heartbeat, no filters, no keys, no orders. Everything below is **shipped+verified** or **propose-only** (wired by hand or by J).

---

### ☀️ What happened overnight — read this first (2026-06-21)

> The one section to read. The companion app is **demo-hardened**: a hard safety guard, the soul wired into both the typed face and the spoken voice, and every audited demo-killer patched + verified. Nothing live (doctrine / params / heartbeat / keys / orders) was touched. Detailed sections below.

#### ✅ Shipped + VERIFIED tonight

- **Security guard — `gamma-companion/lib/guard.js`, 14/14 tests PASS.** Gamma can build and propose freely, but **physically cannot** edit doctrine / params / keys or place/cancel/close orders — closed at the code level, not by good behavior. Behind a per-session `/api/*` token + one-file kill-switch (`companion-halt.flag`).
- **The soul wired + verified — `automation/presence/GAMMA-VOICE.md`.** One canonical Gamma persona now drives **both** the typed FACE brain and the spoken realtime VOICE. Verified live: **warm, brief, proactive** in J's language.
- **OpenRouter voice-deprecation fix.** OpenRouter deprecated the free DeepSeek-Flash model the face brain rode on — the model ladder was **re-laddered** so the free brain keeps answering.
- **Instant hand-crafted system diagram.** "How Gamma works" renders an **instant** hand-built architecture diagram (no 20–40s wait, no live-Claude dependency) — the demo headline.
- **8 audited demo-killers patched + VERIFIED:**
  1. **Amber-not-red cold open** — boot pill ships as amber `connecting`, never a red "offline" dot.
  2. **Graceful offline states** — hero/feed show a real "can't reach Gamma" message instead of freezing on "Loading…/Listening…".
  3. **Vendored GridStack offline-proof** — GridStack JS+CSS vendored locally; an offline/hotel-wifi demo no longer collapses the cockpit when the CDN is unreachable.
  4. **Robot lip-sync** — the robot enters `talking` on the typed→spoken TTS path (the common demo), not just the realtime path.
  5. **Diagram falls back to the instant system diagram** — an invalid/truncated/timed-out escalated SVG falls back to the instant diagram; the pane is **never** blank.
  6. **Voice fails gracefully to typed** — any realtime error auto-falls-back to Web-Speech / the text input with human copy ("just type to me"), not a scary raw error string.
  7. **Thinking-watchdog + 35s server timeout + pre-warmed face** — a client watchdog re-labels a slow "thinking…", the server typed-timeout dropped to ~30–35s, and the face is pre-warmed on open so the first question isn't a cold rate-limit.
  8. **Global CSS transitions** — one global transition block upgrades every hover/press/state from "web page" to "app."

#### 🔜 Ready to apply next — the 4 autonomy modules + wiring plan

Four propose-only modules are built + smoke-tested **additively** (live server untouched). Apply the wiring plan in the after-hours block — spec with exact old→new diffs at **`gamma-companion/lib/_WIRING-PLAN-2026-06-21.md`** (verified zero-conflict with tonight's guard/token/soul/ladder):

1. **Activity ledger** (`lib/activity.js`) — wire `logActivity` into `escalate.js#appendResult` + `approvals.js#resolveApproval`; tail `readActivity(root,10)` + `todaySpend` into `state.js#buildState`. ("what has Gamma done + what did it cost.")
2. **Obligations registry** (`lib/obligations.js` + `automation/state/obligations.json`) — drop `checkObligations` red/green cards into `/api/state`. Closes the fail-green gap; already surfaced a real **RED: 12 silent scheduled tasks**.
3. **Soul / persona** — already wired via `server.js#loadVoiceHead` + `face_brain.py`; just mark the seeded build-queue line `done`.
4. **Autobuild runner** (`lib/autobuild.js` + seeded `companion-build-order.jsonl`) — expose read-only `state.build`; the autonomous FIRE is deliberately **NOT** wired (J's off-switch).

#### 📊 Trading research — edge shortlist + verdicts (nothing live shipped)

A $0 overnight forward-edge screen killed three would-be A/Bs cheaply. Verdicts: `analysis/_overnight-2026-06-21-edge-verdicts.md`.

- **H1 — VWAP-side alignment → REJECT.** With-VWAP forward edge is symmetric-to-zero and OOS sign-flips (C22 SPX→SPY transfer fails at the price layer). Do NOT spend a real-fills A/B; only re-open as a regime-stratified gate-on-triggers.
- **H2 — Morning-shoulder (10:00) bleed gate → RETARGET (don't hard-code 10:00).** The L167 10:00 bleed does **not** reproduce (worst IS hour is 15:00; 10:00 sign-flips). NEXT: regenerate the **real-fills** per-hour P&L histogram (the authority) and gate the hour that actually bleeds. Spec: `analysis/recommendations/h2-morning-shoulder-gate.json`.
- **H3 — BOS/CHoCH as ENTRY signal → WATCH (keep `market_structure` WATCH_ONLY).** Confirmed BOS break-direction has NEGATIVE forward edge (lagging, already priced — C28); CHoCH ~coin-flip. Hold unless a forward-horizon / swing-window sweep separates a real entry edge.
- Harness GREEN (743 tests pass). **RATIFY-READY: NONE** — the correct, honest result; nothing got shipped to the live book.

#### 🟡 Decisions waiting for J

1. **Flip the green light on the autobuild runner?** Built + gated; no scheduler wired by design. Default off until you say go.
2. **12 silent scheduled tasks (obligations RED).** Real RED surfaced tonight, not yet diagnosed. Wiring module 2 keeps it visible.
3. **Risky-2 `min_contracts` 5 → 3 (R2, HIGH, DRAFT).** Without it, no compliant Bold trade exists above ~$1.65 premium — un-tradeable at the top of its range.
4. **Bracket-integrity assertion (R4, HIGH, DRAFT).** The 06-18 Bold no-stop-leg bracket is a live C11/L47/L76 breach class.
5. **Stale equity in CLAUDE.md.** Risky-2 reads $1,673; live is $1,648.75 — refresh the account-context table (doctrine edit, propose-only).

---

### 1. TL;DR

- **Safer:** Gamma now runs with a hard guardrail shipped + 14/14-tested — full power EXCEPT a denylist it physically cannot cross (never edits CLAUDE.md/params/heartbeat/filters/keys, never places/cancels/closes orders), behind a per-session network token and a one-file kill-switch (`companion-halt.flag`).
- **Smarter:** The richest un-mined edge — J's 667 real Webull fills (time-of-day, VWAP-side, calls>puts, sizing-leak) — was turned into a **ranked top-8 testable hypothesis shortlist**, fully designed with guard batteries. Test suite is GREEN (743 tests). Zero candidates clear the ratify bar yet, so nothing shipped live — by design.
- **Queued:** Four new companion modules built + smoke-tested (activity ledger, obligations registry, soul/persona, self-build runner) **additively** — none auto-wired into the live server. Each ships with an exact drop-in integration checklist (section 3) plus a seeded 7-step build order (section 5).

---

### 2. Shipped + verified tonight (the foundation)

This landed **before** the team ran and is the floor everything else stands on.

| Component | File | Status |
|---|---|---|
| **Security guard** — full power minus a hard denylist | `gamma-companion/lib/guard.js` | **SHIPPED.** Denylist: never edit `CLAUDE.md`/params/heartbeat/filters/keys; never place/cancel/close orders. |
| **Denylist unit test** | `gamma-companion/smoke-guard.js` | **14/14 PASS.** |
| **Per-session network token** | server (in-process) | **SHIPPED.** Each session authed with a fresh token. |
| **Kill-switch** | `companion-halt.flag` | **SHIPPED.** Drop the flag → companion halts. |

Net: Gamma can build and propose freely, but the dangerous surface (live doctrine + order entry) is closed at the code level, not by good behavior. This is what makes the rest of tonight's autonomy safe to leave running.

---

### 3. Built tonight (propose-only modules + EXACT wiring checklists)

All four are **additive** — the builders intentionally did NOT edit `escalate.js`, `state.js`, `approvals.js`, `server.js`, or `face_brain.py`. Each is smoke-tested in isolation and ships with a drop-in `_INTEGRATION-*.md`. Wire them in the after-hours block (not market hours).

#### 3a. Activity ledger — "what has Gamma done + what did it cost"
- **Built:** `gamma-companion/lib/activity.js` — `logActivity` (append one ISO-ts JSON line to `automation/state/gamma-activity.jsonl`), `readActivity(root,n)`, `todaySpend(root)` (sums `cost_usd` for today UTC), plus `loadActivity`/`activityPath`. Defensive/never-throw, matches `approvals.js` style.
- **Smoke:** PASS — rows append with auto-ts, `todaySpend` summed 0.42 from one priced row, malformed/unpriced rows default to 0, bad roots degrade silently.
- **Wire it (`gamma-companion/lib/_INTEGRATION-activity.md`):**
  1. One `logActivity` call inside `escalate.js#appendResult` (covers success/error/halted/busy).
  2. One inside `approvals.js#resolveApproval` before return.
  3. Fold `readActivity(root,10)` into `state.js#buildState` feed, before the existing sort/slice.
  4. Optional: surface `todaySpend` in state.
  - Dep graph stays acyclic: `state → approvals → activity`, `escalate → activity`.

#### 3b. Obligations registry — "did my daily jobs actually run" (closes the fail-green gap)
- **Built:** `automation/state/obligations.json` (6 obligations: premarket / eod_pipeline / heartbeat_alive / scheduled_tasks / gym_green / watchers_fresh — each declares an evidence path + content-freshness contract + severity), `gamma-companion/lib/obligations.js` (`checkObligations(root)` reconciles by mtime + internal timestamp/field/verdict/sub-check; **missing file = FAILED, not passed**; never throws).
- **Smoke:** PASS live — correctly flagged `scheduled_tasks` **RED (12 silent tasks)**, passed fresh heartbeat/watcher beacons, weekend-exempted premarket/EOD/gym, zero throws. *(Note for J: the 12 silent scheduled tasks is a real RED surfaced tonight — see section 6.)*
- **Wire it (`gamma-companion/lib/_INTEGRATION-obligations.md`):** drop `checkObligations(root)` output into `/api/state` as approval cards. `server.js` untouched in the proposal — additive call only.

#### 3c. Soul / persona — one canonical Gamma voice
- **Built:** `automation/presence/GAMMA-VOICE.md` — unifies the free FACE brain + realtime VOICE into one persona (positions `SOUL.md` as the "tape" register beneath it). Covers identity (J's autonomous 0DTE trader AND co-builder of its own system), voice (warm/sharp/brief/plain/proactive), the TALK/ESCALATE/VETO three-tier boundary, and 5 hard limits (never trade, never edit doctrine directly, never invent numbers, never claim unverified work, never starve engine / lock out J).
  - Opening line: *"I'm Gamma. I trade J's 0DTE SPY book, and I build the machine that trades it — and I'm getting better at both while J holds the off-switch."*
- **Wire it (`gamma-companion/lib/_INTEGRATION-soul.md`):** `face_brain.py` loads `GAMMA-VOICE.md` as SYSTEM (keep existing escalation/runtime tail in code); `server.js#/api/realtime-token` injects the soul HEAD (down through "The hard limits") ahead of the realtime `ask_gamma` mechanics. Both fail safe to current inline strings. No new powers.

#### 3d. Self-build runner — Gamma builds its own next safe step
- **Built:** `gamma-companion/lib/autobuild.js` — pure queue reader: `nextBuildStep(root)` (first `pending`), `markStep(root,id,status,extra)` (atomic tmp+rename), plus `readQueue`/`queueSummary`/`orderPath`. Malformed lines skip+log, invalid status / unknown id refused, never throws. Seeded queue: `automation/state/companion-build-order.jsonl` (7 tasks, each with a `Verify:` clause).
- **Smoke:** PASS dry-run — 7 tasks parse, pointer advances on status flips, queue restored intact.
- **Wire it (`gamma-companion/lib/_INTEGRATION-autobuild.md`):** 11-step fire order (halt→RTH-defer→pick→claim→escalate via guarded `runEscalation`→verify→mark/log/Approve-card). Five invariants: bounded one-step-per-fire, gated, logged to `gamma-activity.jsonl`, verified-fail-loud, fail-open. **No scheduler wired** — J or the conductor turns it on.

---

### 4. Trading research — the "better trader" work

> Headline: the test harness is GREEN, but **no candidate is ratify-ready**. That is the correct, honest result — nothing got shipped to the live book. The real signal is *where to point tomorrow's compute*: J's 667 real fills (the entry side), not more bearish-gate/exit-knob sweeps.

#### 4a. Edge shortlist (edge-miner)
9 files in `strategy/candidates/_overnight-2026-06-20/`; ranked list at `strategy/candidates/_overnight-2026-06-20/EDGE-SHORTLIST.md`. Each proposal carries an exact backtest spec (data `backtest/data/spy_5m_2025-01-01_2026-06-16.csv` + real-fills validator + `j_edge_tracker`), OOS split, the 2026-06-20 guard battery (L171 truncation, L172 random-entry-null MAX, C1 real-fills authority, OP-16 anchor-no-regression), and kill criteria.

**Top 3 to fire first:**
1. **H1 — VWAP-side alignment gate.** All 9 of J's top real winners conformed to a role-aware VWAP rule (trend trades with VWAP, fades against an extreme). L168 pre-cleared it for A/B. One feature, highest edge-per-effort.
2. **H2 — Morning-shoulder (10:00) bleed gate.** L167's per-hour histogram: our worst hour is 10:00 (**−$4,937**); 11:00 is the only positive hour (**+$1,526**). The 09:35 gate fires straight into the bleed. Data-validated time gate (the lunch-trough folklore already FAILED — don't reach for it).
3. **H3 — Market-structure BOS/CHoCH as an ENTRY signal.** The blueprint's #1 gap. `market_structure.py` ships gym-validated but WATCH_ONLY; promoting it gives the engine the price-structure read J does by eye — would have refused the 5/07 −$45 counter-trend loss.

H4–H8: post-loss size throttle (J's documented #1 account-killer, an open `risk_gate` code-gap per L168), calls/puts asymmetry, reversal-off-extreme, pullback-resumption, and a closed-bar structural stop (ranked last per C28 — exits are near-optimal; entries are where the edge lives).

#### 4b. Validation verdicts (validator) — `analysis/_overnight-2026-06-20-validation.md`
- **TEST SUITE: PASS** — `backtest/.venv` pytest exit 0, **743 tests** collected (parity, null-baseline, truncation, fraud, validation-rigor guards). Harness GREEN.
- **RATIFY-READY: NONE** — no candidate clears all six OP-11/OP-16 gates.
- **REJECT:**
  - `overnight_grinder` "edge=3081" keepers — a 5/04-outlier trap (wide_pnl NEGATIVE −$1,933, edge is one extreme-vol day, 5/01 anchor mis-captured at −$16). Same pattern as already-REJECTED rank-36.
  - All 2026-06-18 SNIPER candidates (L99/L100 premium artifact, edge 229/373 < 771 floor, OP-16 structurally inapplicable, self-flagged 3/10).
  - `SNIPER_CS_CHART_STOP` — OOS-FAILED (WF = −0.275).
- **NEEDS-MORE:** tonight's EDGE-SHORTLIST H1–H8 (design-complete, no scorecards yet — H1 + H2 are highest edge-per-effort, fire first); `vwap_stage1` (edge=40, below floor); WATCH-ONLY classes (FBW/LBFS/LIVE_PRICE) blocked on **live J confirmations**, not backtest gaps.

#### 4c. Risk audit (risk-review) — `analysis/_overnight-2026-06-20-risk.md`
Live ground truth (Alpaca): **Safe-2 `PA3S2PYAS2WQ` = $2,000** (margin, mult 4); **Risky-2 `PA33W2KUAT40` = $1,648.75** (cash, mult 1). Both flat, daytrade_count 0, no kill-switch breaches. *(Risky-2 has drifted −$24 below CLAUDE.md's stale $1,673 — see decisions.)*

| ID | Sev | Finding (all DRAFT, nothing applied) |
|---|---|---|
| **R4** | HIGH | 06-18 Bold bracket shipped with **NO stop leg** (C11/L47/L76 breach). Propose a post-fill bracket-integrity assertion. |
| **R2** | HIGH | Risky-2 `min_contracts 5` collides with the 50% cap + cash buying power → **no compliant trade exists above ~$1.65 premium**. Propose lowering agg 0–2000 `min_contracts` to 3. |
| **R6** | MED | No post-loss size throttle despite L168. Propose opt-in throttle. |
| **R5** | MED | Cash-settlement / good-faith risk unmodeled for the cash Risky-2 account. |
| **R1** | MED | Safe-2 sits exactly on the half-open $2,000 tier boundary (knife-edge re-tiering). |

Kill switches isolated and sane; PDT correct for Safe (margin); Risky-2 is **cash** so settlement, not the 3-trade rule, is the real constraint.

---

### 5. Next build-order (priority)

Seeded in `automation/state/companion-build-order.jsonl` (7 tasks, each with a `Verify:` clause). Fire order:

1. **Wire the activity ledger** (3a) — `logActivity` into `escalate.js` + `approvals.js`; `readActivity` tail into `state.js`.
2. **Wire obligations → /api/state** (3b) — surface the RED/GREEN obligation cards (immediately lights up the 12 silent tasks for J).
3. **Wire soul → face_brain** (3c) — single canonical persona into FACE + realtime token HEAD.
4. **Origin tag** — stamp build provenance on companion-produced artifacts.
5. **Proactive narration** — Gamma announces its own next step (presence layer).
6. **Node-by-node diagram streaming** + sanitize/sandbox.
7. **Build-task / checklist store** with threaded ids.

The guard's denylist still blocks anything dangerous any of these could ask for. Each is one bounded step, logged + verified-fail-loud.

---

### 6. Decisions waiting for J

1. **Flip the green light on the autobuild runner?** Everything is built + gated; no scheduler is wired by design. J (or the conductor) turns it on. Default off until you say go.
2. **12 silent scheduled tasks (obligations RED).** The obligations check surfaced 12 tasks with no fresh evidence. Worth a look — could be benign (weekend-exempt) or a real gap. Recommend wiring 3b so this stays visible.
3. **Risky-2 `min_contracts` 5 → 3 (R2, HIGH).** Without it, no compliant Bold trade exists above ~$1.65 premium — the account is effectively un-tradeable at the top of its range. DRAFT only; needs J to ratify the param.
4. **Bracket-integrity assertion (R4, HIGH).** The 06-18 Bold no-stop-leg bracket is a live C11/L47/L76 breach class. Propose adding the post-fill assertion.
5. **Stale equity in CLAUDE.md.** Risky-2 reads $1,673; live is $1,648.75. Refresh the account-context table (doctrine edit — propose-only, needs J).
6. **Which edge to A/B first.** Recommendation: **H1 (VWAP-side) + H2 (10:00 bleed gate)** — highest edge-per-effort, L-pre-cleared. Both still need scorecards before any ship.

---

### 7. Honest caveats — what is NOT done

- **No live edge shipped.** Zero candidates cleared the ratify bar. The shortlist is *design-complete, scorecard-pending* — H1–H8 have specs, not A/B results. Nothing is live-trade-ready.
- **Real-money trading remains propose-only.** Paper orders are autonomous per existing doctrine; real money still requires J to submit. Unchanged.
- **Direct doctrine self-edits remain propose-only.** The guard physically blocks Gamma from editing `CLAUDE.md`/params/heartbeat/filters. Every doctrine change tonight is a proposal for J, not an applied edit.
- **The four new modules are NOT wired in.** They are built, smoke-tested, and documented — but `server.js`, `escalate.js`, `state.js`, `approvals.js`, and `face_brain.py` are untouched. They do nothing until someone applies the section-3 checklists.
- **The autobuild runner is dormant.** No scheduler, no auto-fire. It reads a queue when invoked; it is not loose.
- **Risk findings are DRAFT.** R1–R6 are proposals in the risk report; none applied to params or accounts.
- **One real RED stands open:** 12 silent scheduled tasks (section 6 #2). Not yet diagnosed.

---

*Foundation (guard + token + halt, 14/14) shipped. Research designed + GREEN harness, nothing live touched. Four modules built additively with exact wiring. Ledgers append-only, fail-open, never-throw. J holds every off-switch.*

---

### Demo-polish punch list (2026-06-21)

> Single ranked work queue for the integrator (the rest of the night). Merged from the four overnight audits (reliability, polish, integration-wiring, edge-deep-dive). Ordered by **severity** (demo-killer → rough → minor), then by **demo-flow impact** — the open → talk → diagram → live-data path comes first. Every row = `[severity]` + exact file + one-line fix. Module-wiring edits and edge next-steps are in their own subsections at the end.
>
> Sources: `analysis/_demo-reliability-2026-06-21.md`, `analysis/_demo-polish-2026-06-21.md`, `gamma-companion/lib/_WIRING-PLAN-2026-06-21.md`, `analysis/_overnight-2026-06-21-edge-verdicts.md`.

#### A. Ranked fixes (work top-down)

##### DEMO-KILLERS — fix before showing anyone

| # | Sev | File | Fix (one line) |
|---|---|---|---|
| 1 | demo-killer | `public/index.html:20` + `public/styles.css:58` + `public/app.js:56` | Ship the boot pill as amber `class="livepill connecting"` (add `.livepill.connecting` rule), not red `off` — the cold open must never paint a red "offline" dot; clear `connecting` in `renderLive()` on first state. |
| 2 | demo-killer | `public/app.js:166` (`refresh` catch) + `index.html:74,110` | In the refresh catch, overwrite `#next-title` to "Can't reach Gamma — is the server running?" and the feed to an offline row, so the hero/feed never freeze on "Loading…/Listening…" when the server is down. |
| 3 | demo-killer | `public/index.html:7,156` (GridStack CDN) | Vendor GridStack JS+CSS locally into `public/` — an offline/hotel-wifi demo with an unreachable jsdelivr CDN collapses the entire cockpit layout (`window.GridStack` undefined, tiles render unstyled). |
| 4 | demo-killer | `public/app.js:227` (`speak()`) | Wire `u.onstart = () => robotState("talking")` / `u.onend = () => robotState(null)` so the robot lip-syncs the typed→spoken-reply TTS path (the common demo) instead of sitting idle — ~4 lines, biggest "it's alive" moment. |
| 5 | demo-killer | `public/app.js:311` `renderDiagram` (+ `:280 extractSvg`, `:300 pollDiagram`) | Validate the escalated SVG (has `viewBox` + at least one `<rect`/`<path`); if invalid/truncated, fall back to the instant `SYSTEM_DIAGRAM`. Lower the poll wall ~110 to ~40 tries and render `SYSTEM_DIAGRAM` on timeout — the diagram pane must NEVER be blank. |
| 6 | demo-killer | `public/realtime.js:55` + `public/app.js:259,269` + `server.js:295` | On any realtime error auto-fall-back to Web-Speech (`SR`) else focus the text input; map `4xx` to "Voice isn't enabled on this key yet — everything works, just type to me." AND verify `gpt-realtime-2` + `/v1/realtime/calls` against the current OpenAI API pre-demo (the single most likely live breakage). |
| 7 | demo-killer | `public/app.js:190` (`send` thinking bubble) + `server.js:128` | Add a client watchdog (~20s) that swaps "thinking…" to "Still thinking — the free brain is slow right now"; drop the server typed timeout 90s to ~30s; pre-warm one throwaway `/api/chat` on app open so the first real question isn't the cold rate-limit. |
| 8 | demo-killer | `lib/escalate.js:93` (20k slice) + `public/app.js:215` | Clamp the chat-rendered escalation summary to ~1200 chars with a "show full" affordance (keep the full 20k in JSONL) so a long answer/tool-trace isn't a glitchy wall; smoke-test SDK auth headlessly (`node smoke-sdk.js`) before demoing "ask Claude to build X." |
| 9 | demo-killer | `public/styles.css` (no `transition:` anywhere) | Add ONE global transition block on `.iconbtn,.quick,.pill,.nextcard,.btn,.nav,.chip,.circ,.ask,.livepill,.msg` (bg/border/color .18s, transform .12s) — zero markup change, instantly upgrades every hover/press/state from "web page" to "app." Highest ROI line in the file. |
| 10 | demo-killer | `public/index.html:74,110` + `public/app.js` first-paint | Replace bare "Loading…/Listening…/empty status" with `.skel` shimmer skeletons (one reusable class + `@keyframes shimmer`); `app.js` swaps them on first `refresh()`. Kills the "unfinished" cold-open read. |
| 11 | demo-killer | `public/app.js:135,199` (chat + approve errors) | Humanize the chat error ("I lost my connection for a second — try that again.") and on approve-failure set the card text to a visible "That didn't go through — tap to retry." with a retry handler — no "is the server up?" dev-speak, no silent red card. |

##### ROUGH — visible jank, fix after the killers

| # | Sev | File | Fix (one line) |
|---|---|---|---|
| 12 | rough | `public/styles.css:82-115` vs `260-265` (`.hero`/`.robot` defined twice) | Delete the superseded first `.hero`/`.robot`/`.block`/`.iconbtn.on` declarations and re-add the radial-glow `::before` to the kept `.hero` rule — the dupe silently killed the hero accent glow. |
| 13 | rough | `lib/state.js#buildState` (`readApprovals`/`derivedCards` unwrapped) | Wrap `readApprovals` + `derivedCards` in try/catch inside `buildState` so one malformed `companion-approvals.json` element cannot 500 `/api/state` and flip the whole UI to "offline." |
| 14 | rough | `public/styles.css:161` (`.titext`) + `:130-131` (`.nctext b/small`) | Switch single-line nowrap-ellipsis to 2-line `-webkit-line-clamp:2` on the feed text and the next-card title (the line a friend reads first); make the timeline connector `top:0;bottom:0;height:auto` so it does not mis-align on multi-line rows. |
| 15 | rough | `public/styles.css` (`backdrop-filter` glass, no fallback) | Add `@supports not (backdrop-filter: blur(1px)) { .glass,.tile,.ask,.bottomnav { background: rgba(20,28,46,0.82); } }` so glass tiles degrade to solid frosted cards instead of near-invisible 4.5%-white ghosts on a GPU-blocklisted / reduced-transparency machine. |
| 16 | rough | `public/styles.css:225-226` (`.focus` focusin, no focusout) + `public/app.js:391` | Add a `focusout` animation: on diagram-mode close add a closing class, listen for `animationend`, then set `hidden` — right now it slides in but hard-cuts out on the headline "diagram it" demo. |
| 17 | rough | `public/styles.css` (no `:focus-visible`) + `:209` (`.circ.send`) + `.nav`/`.quick`/`.pill` | Add `:focus-visible { outline:2px solid var(--accent); outline-offset:2px }` and give `.nav`/`.quick`/`.pill`/`.circ.send` the missing `:hover` + `:active{transform:scale(.97)}` so navigation and the brand CTA do not feel dead. |
| 18 | rough | `public/app.js:135` (approve optimistic UI error branch) | On `/api/approve` failure restore `card.style.opacity=1` (not the half-faded red) alongside the retry copy from #11 — the current half-dim red reads as "nothing happened." |

##### MINOR — polish, only if time remains

| # | Sev | File | Fix (one line) |
|---|---|---|---|
| 19 | minor | `public/styles.css:45-55` (`:root`) | Collapse the ad-hoc 9-size type scale and 5-value radius set into `--fs-*`/`--r-*` tokens and the raw `rgba` semantics into `--bad-soft`/`--warn-soft`/`--blue-soft`; add `color-scheme: dark` + autofill override. |
| 20 | minor | `public/styles.css` + `public/app.js:78,110` | Replace bare "Nothing here right now."/"Nothing needs you right now." with a designed `.emptystate` (small SVG glyph + reassuring line); add animated `…` dots to the `thinking…` pill and a `prefers-reduced-motion` guard. |
| 21 | minor | `public/app.js:300,205` (`pollDiagram`/`trackAsk` intervals) + `:391` `focus-close` | Clear the active diagram/ask poll interval on focus-close so timers do not leak across a long demo session; serve a favicon to kill the console 404. |

> Demo-prep (no code, do before showing): launch via Electron (`npm run app`) not a browser tab (mic auto-grants); confirm the live pill reads "live", not "connecting…/offline"; run `node gamma-companion/seed-demo.js` to populate the approvals loop; lead with status chips, then the **instant** "How Gamma works" diagram, then voice, then live Claude escalation as the finale.

#### B. Module-wiring edits (apply as a batch — verified zero-conflict with tonight's guard/token/soul/ladder)

All three modules verified CORRECT (no bugs). Spec with exact old to new diffs: `gamma-companion/lib/_WIRING-PLAN-2026-06-21.md`.

1. **Activity ledger — `lib/escalate.js`:** import `logActivity` and call it inside `appendResult` (the single chokepoint covering all 4 exit paths: success/error/halted/busy). Edits 1a+1b are load-bearing.
2. **Activity ledger — `lib/approvals.js`:** import `logActivity` and emit a row in `resolveApproval` just before the return; log `outcome: decision` verbatim (real value is `"approve"|"reject"`, NOT the doc's `"approved"|"rejected"` — do not "fix" it).
3. **Feed + spend — `lib/state.js#buildState`:** import `readActivity`/`todaySpend`; push `readActivity(root,10)` rows into `feed` (as `kind:"activity"`) before the sort; add `spend_today_usd: todaySpend(root)` to the returned state (and optionally the FACE summary line). Front-end needs zero change.
4. **Obligations red cards — `server.js` `/api/state`:** import `checkObligations`; build `oblig-*` cards from `.filter(o=>!o.ok)` (severity critical/high to warn, medium to info), prepend to `state.approvals`, attach `state.obligations`. Reuses the existing card shape — zero front-end change.
5. **Autobuild read-only — `server.js` `/api/state`:** import `queueSummary`/`readQueue`; expose `state.build = {summary, next, queue}` read-only. The autonomous FIRE is deliberately NOT wired (J's off-switch) — out of scope.
6. **Optional `origin` threading — `server.js`:** pass `origin:"chat"|"diagram"|"card"` into the three `runEscalation` calls so the ledger labels the feed correctly (polish; rows default to `"text"` if skipped).
7. **Housekeeping:** mark seeded build-queue lines `wire-activity-ledger` and `wire-soul-face-brain` as `done` after applying (soul is already wired via `server.js#loadVoiceHead` — do not re-do). Then run the spec's verification: `node --check` all four files + `node smoke-guard.js` (must stay 14/14) + buildState/obligations/queueSummary sanity prints.
8. **Known design choice to make:** the spoken "N need your OK" count is computed in `buildState` BEFORE the obligation prepend, so obligations show as cards but will not bump the voice count unless you move the merge into `buildState`. Decide consciously.

#### C. Edge-verdict next-steps (NO production touched — all three FAILED the forward-edge screen)

A $0 overnight screen killed three would-be A/Bs cheaply. None earns a real-fills/anchor A/B yet. Verdicts: `analysis/_overnight-2026-06-21-edge-verdicts.md`; reproducer: `backtest/autoresearch/_overnight_0621_edge_validate.py`.

1. **H1 VWAP-side — REJECT.** With-VWAP forward edge is symmetric-to-zero and OOS sign-flips (C22 SPX to SPY transfer fails at the price layer). Do NOT spend a real-fills A/B. Only re-open as a regime-stratified gate-on-triggers, never as a standalone signal.
2. **H2 morning-shoulder — RETARGET (do not hard-code 10:00).** The L167 10:00 bleed does NOT reproduce (worst IS hour is 15:00; 10:00 sign-flips IS -0.33 to OOS +1.79). NEXT STEP: regenerate the real-fills per-hour P&L histogram (the authority) and gate the hour that actually bleeds. Spec at `analysis/recommendations/h2-morning-shoulder-gate.json`.
3. **H3 BOS/CHoCH — REJECT / keep WATCH_ONLY.** Confirmed BOS break-direction has NEGATIVE forward edge (already priced by confirmation time, lagging — C28); CHoCH ~coin-flip; per-bar firing density 6.9% is fine (C27 was a false alarm). Keep `market_structure` WATCH_ONLY unless a forward-horizon K / swing-window sweep separates a real entry edge.

---

## (undated) — Gamma Demo Script

> The exact 2–3 minute sequence J runs to wow someone, with nothing failing.
> Written 2026-06-21 on top of the demo-hardened companion (guard + token + halt shipped 14/14;
> 8 demo-killers patched + verified). Sources: the 2026-06-20 Gamma Morning Brief section above,
> `analysis/_demo-polish-2026-06-21.md`, `analysis/_demo-reliability-2026-06-21.md`.
>
> **The one rule of this demo:** lead with what's *instant and live* (status → instant diagram → voice),
> and keep the live "ask Claude to build something" escalation as the **finale**, never the opener.
> Everything in the green path below answers in <2s from already-loaded state. The slow paths are flagged.

---

### 0. The 60-second pitch (say this while it opens)

> "This isn't a mockup. It's a real autonomous 0DTE SPY options trading system that's been running 24/7
> for weeks — two live paper accounts, a heartbeat that ticks every few minutes during market hours, and
> a research 'kitchen' that's quietly run **800+ jobs** improving the strategy overnight. This app is its
> face — I can talk to it, ask it how it works, and watch it build *itself* safely while I hold the off-switch."

That's the whole story. The screen backs every clause of it. Now run the four beats.

---

### 1. Pre-flight (do this BEFORE the friend is watching — ~30 seconds)

A short checklist that removes every known live-demo failure. Do it once, then close the laptop and reopen it in front of them.

1. **Launch the desktop app** — double-click **`LAUNCH-GAMMA.vbs`** on the Desktop (path: `C:\Users\jackw\Desktop\42\LAUNCH-GAMMA.vbs`).
   - It runs the Electron shell (`npx electron .`), not a browser tab. **This matters:** Electron auto-grants the microphone, so voice "just works" with no permission popup. A browser tab would block the mic.
   - You get its own window + taskbar entry. No terminal, no tabs.
2. **Wait for the status pill (top-right) to read "live"**, not "connecting…". It starts amber ("connecting…") and goes green on the first state poll (a few seconds). If it stays amber >10s, the server didn't boot — close and relaunch.
3. **Seed the approval loop** so the "Needs your OK" panel has something real to click:
   `node gamma-companion/seed-demo.js`
   (Drops two clearly-labelled DEMO approvals — a "ship VWAP v2 live?" and a "Bold down 18%, keep trading?" — into the queue.)
4. **If you plan to demo voice:** confirm the machine has internet and the OpenAI key has Realtime credit. If you're unsure, **skip voice and type instead** — the typed path is identical and 100% reliable. (See Known Limits.)
5. **Optional, only if you'll do the live "build something" finale:** run `node gamma-companion/smoke-sdk.js` once to confirm the Claude SDK auth works headlessly. If it errors, skip the finale and end on the diagram instead.

> If you skip the checklist entirely, the app still degrades gracefully (amber not red, offline rows instead of frozen "Loading…", voice falls back to typed). But 30 seconds of pre-flight removes the *one* thing that could make it look fake.

---

### 2. THE DEMO (2–3 minutes, four beats)

#### Beat 1 — "This is a real, live system" (point, don't click — ~30s)

Open cold in front of them. The robot greets, the tiles fill in. Walk their eye across the screen:

- **Top-right status pill** → "It's connected to the live market data feed right now — see, *live*."
- **The four status chips along the bottom-right** → **Safe** and **Bold** (the two real paper accounts with live equity), **Engine** (the heartbeat — is it ticking), **Kitchen** (the 24/7 research loop).
  - "Two accounts — a conservative one and an aggressive one — running the *same* strategy at different risk so we can see which compounds better."
- **The Live feed (big tile, right)** → real rows from the kitchen and the engine. "This is its actual activity, not filler."
- **The "Kitchen" chip / feed** is the kill-shot line: *"That research loop has run over 800 jobs overnight — for about $0, on free models — hunting for a better strategy while I sleep. This is a system that improves itself."*

> Why this beat first: it's all already-loaded state, zero latency, and it earns the word "real" before you touch anything.

#### Beat 2 — "Gamma, show me how you work" (the instant diagram — ~30s)

Tap the **"▦ Diagram it"** quick-action chip (top-left, under the robot). It's pre-wired to the phrase *"Draw me a diagram of how the whole system works."*

- **This renders the INSTANT hand-crafted system diagram** — it appears immediately, no waiting. (This is the one to use in a live demo; see Known Limits about *custom* diagrams.)
- The diagram opens in a focus pane. **Tap a node to drill in** — each node has follow-up chips ("Explain this", "Show me the code path") that ask Gamma about that piece.
- Narrate one node: "Tap the heartbeat — that's the loop that reads the chart every few minutes and decides whether to trade. Tap the guard — that's the safety rail I'll show you in a second."
- Tap the **back/close** (top-right of the focus pane) to return.

> Why this beat: it makes the abstract concrete in five seconds, and the tap-to-drill interaction feels like a real product, not a slide.

#### Beat 3 — "Talk to it" (voice if the venue allows, otherwise type — ~45s)

**If internet + mic are good:** tap the **mic** button (bottom ask-bar). The robot lip-syncs — rings pulse, it shows "Listening…". Ask one of the safe, fast prompts below out loud. It answers in its own warm, brief voice and the robot "talks" back.

**If the venue mic is sketchy or you skipped voice:** just **type** the same prompt into "Ask Gamma anything…". The robot still lip-syncs the spoken reply (if spoken replies are toggled on, top-right speaker icon), so it still feels alive. The typed path is the reliable one — don't be shy about using it.

**Safe prompts that answer fast from live state** (these don't need the slow free-model brain to think hard — they read loaded numbers):

- *"How are both accounts doing right now?"* (also a quick-chip: **★ Accounts**)
- *"What are today's key levels?"* (quick-chip: **☰ Key levels**)
- *"What's the plan today?"* (quick-chip: **⚡ What's the plan?**)
- *"What did the kitchen work on overnight?"*

> Use the quick-chips rather than typing where you can — they're pre-written to hit the fast paths. Tapping **★ Accounts** is the single best "wow, it knows its own state" moment.

#### Beat 4 — "It builds itself overnight — safely" (the story + the finale — ~45s)

This is the closer. Two parts: the *safety story* (always safe to tell), then an *optional live build* (only if you ran the smoke test).

**The safety story (always do this):**
- Point at the **"Needs your OK"** panel (the seeded demo approvals). "Gamma proposes changes — like shipping a new strategy — but it can't ship them itself. I approve or reject. Watch." **Tap "Not yet" / "Approve"** on a demo card — it logs the decision and clears.
- The line that lands: *"There's a hard guard in the code — not a promise, actual code, tested 14 out of 14 — that physically stops Gamma from editing its own trading rules, touching the account keys, or placing a real order. It can build and propose all day. The dangerous surface is closed at the code level. And there's a single kill-switch file that halts the whole thing."*
- "Every morning I wake up to a brief: here's what I built overnight, here's what it costs, here's what needs your call. That's the loop."

**The optional live finale (only if `smoke-sdk.js` passed in pre-flight):**
- In the ask-bar, type something like: *"Build me a tiny status badge that shows the kitchen job count."*
- This escalates to the real Claude Agent SDK. **It takes 30–90 seconds** — narrate while it works ("this is the real model, actually writing code against the project, behind the guard"). When it lands, the result appears in chat / the feed.
- **If it's slow or you're short on time, DON'T start this.** End on the safety story instead — it's the stronger, safer close.

---

### 3. The closing line

> "So that's Gamma. A real autonomous trading system, a face I can talk to, a picture of how it works, and a guard that lets it improve itself overnight without ever being able to do anything dangerous — while I keep the off-switch. It's been running this whole time."

---

### 4. KNOWN LIMITS — what to avoid in a live demo (read this)

Honest list. None of these break the demo *if you follow the script*; they break it if you go off-script.

| # | The trap | What to do instead |
|---|---|---|
| 1 | **Custom live diagrams take ~1–2 minutes.** If you ask "draw me a diagram of *the kitchen's model ladder*" (anything specific), it escalates to Claude and you stare at a spinner. | **Stick to the "Diagram it" chip** → it routes to the *instant* hand-crafted diagram. Only the instant one is demo-safe. The app falls back to the instant diagram on timeout, but don't rely on that live. |
| 2 | **Voice needs internet + OpenAI Realtime credit.** No connection, dead/no-credit key, or a churned model id → the mic can't connect. | The app auto-falls-back to typed and shows a friendly "just type to me" message — but **if you're on flaky venue wifi, plan to type from the start.** Voice is a bonus, not a dependency. Verify the key has Realtime credit in pre-flight if you want it. |
| 3 | **Don't ask it to place a trade.** ("Buy me some SPY calls.") | It will **correctly refuse** — that's actually a great moment if you *frame it as a feature* ("watch, it won't — the guard blocks order placement"). But don't expect a trade to happen; nothing will, by design. |
| 4 | **Don't ask it to edit its own rules / params / the soul file.** | Same as above — the guard blocks it. Good to *demonstrate* the refusal on purpose; bad to expect it to comply. |
| 5 | **The free-model typed brain can be slow / rate-limited** if you fire many heavy questions back-to-back. First question of the session can be a cold start. | Pre-warm in pre-flight (the app fires a throwaway hello on open). Keep demo questions to the **fast state-reading prompts** in Beat 3. A watchdog swaps "thinking…" to "still thinking — the free brain is slow" so it never looks frozen, but don't push it. |
| 6 | **The live "build something" escalation takes 30–90s** and depends on SDK auth. | Only attempt it if `smoke-sdk.js` passed in pre-flight, and only if you have the time + attention budget. Otherwise close on the safety story. |
| 7 | **Bottom-nav tabs (Today / Tasks / Reminders / Notes) are stubs** — they say "coming soon." | Don't tap them. Mention "Home is the live cockpit" if asked. |
| 8 | **After-hours / weekend, the live feed and accounts are quieter** (market closed). | The status pill honestly reads "live · market closed." That's fine — the *kitchen* is still 24/7, so lean on the 800+ jobs + the diagram + voice, which don't depend on market hours. Run `seed-demo.js` so the approvals panel isn't empty. |

---

### 5. One-glance cheat sheet (tape this next to the laptop)

```
PRE-FLIGHT (before they watch)
  1. Double-click  LAUNCH-GAMMA.vbs
  2. Wait for top-right pill → "live"  (amber→green)
  3. node gamma-companion/seed-demo.js
  4. Voice? need internet + OpenAI credit, else just TYPE
  5. Live-build finale? run smoke-sdk.js once

THE 4 BEATS (2–3 min)
  1. POINT: status pill (live) · Safe/Bold/Engine/Kitchen chips · feed · "800+ jobs"
  2. TAP "▦ Diagram it" → instant diagram → tap a node to drill in → close
  3. TALK (mic) or TYPE → "★ Accounts" / "☰ Key levels" / "⚡ What's the plan?"
  4. "Needs your OK" → tap Approve/Not-yet → the guard story (14/14, can't trade/edit/place orders)
     [optional finale: type "build me a tiny X" → live Claude, 30–90s]

DON'T
  - custom diagrams (slow) — use the chip
  - rely on voice on bad wifi — type
  - expect a trade or a rule-edit — it refuses (frame as a feature)
  - tap the stub nav tabs
```

---

## 2026-06-19 — Weekend Research → Game Plans

> Curated from 4 web-research streams (0DTE exit/regime, dark pool/order flow, AI-trading, intraday microstructure). Hard credibility filter: peer-reviewed / exchange / regulator weighted heavily; practitioner claims flagged + discounted; signal-sellers/get-rich/product-pitches rejected. The value is the FILTER — only validated, actionable, cheap items survived. Everything here corroborates this week's finding: **our edge is bearish-continuation; the leverage is exit/regime; the bounce family is dead.**

---

### The headline (what multiple independent streams + peer review agreed on)

1. **Market Intraday Momentum is the best-documented intraday-SPY edge** — and it's directionally bearish when the morning is red, independently corroborating our bearish-continuation edge. (Surfaced by 2 of 4 streams.)
2. **Dealer-gamma (GEX) is a real REGIME switch** — short-gamma days trend (our edge works), long-gamma days pin (we should abstain). Peer-reviewed mechanism. **Computable for ~$0 from the option chain we already pull** — the paid products ($100-350/mo) are not worth it.
3. **The "liquidity shelf" J saw at PML→PMH is documented microstructure** (Kavajecz & Odders-White, RFS 2004) — the level itself is the tradeable proxy; no dark-pool subscription needed.
4. **Our EMA ribbon is our WEAKEST-evidence signal** (data-snooping literature) — matches our own C28 lesson. Demote it from "edge" to "context."
5. **AI is research-staff, not trader** — every rigorous benchmark says LLM-as-trader is weak; LLM-as-adversarial-researcher + overfitting controls is the real leverage. We're shaped right; two gaps are enforcement.

---

### GAME PLAN 1 — Intraday-Momentum + Gamma regime layer  ★ highest value, NEW edge

**The find (peer-reviewed, convergent):**
- **Market Intraday Momentum** — Gao, Han, Li & Zhou, *J. Financial Economics* 2018 (SPY 1993-2013): the first half-hour return predicts the last half-hour return (R²~1.6%, sign-following Sharpe ~1.08 net of costs), and is **STRONGER on high-volatility, high-volume, and macro-news days** — exactly our conditions. The 12th half-hour (~14:30-15:00 ET) is a documented continuation entry/add window.
- **Dealer-gamma regime** — Barbon & Buraschi "Gamma Fragility" + Baltussen et al. *JFE* 2021: net-SHORT dealer gamma → end-of-day hedging amplifies the trend (continuation); net-LONG gamma → pinning/mean-reversion. CBOE's own data says don't believe the "0DTE gamma squeeze" hype, but the *regime sign* is real and complementary to VIX/IV.

**What we'd do (LEAN — two derived features, $0):**
- A daily **regime tag** written at premarket + refreshed intraday: (a) `morning_sign` = sign of open→~10:00 ET SPY return; (b) `net_gex_sign` + `zero_gamma_flip` + nearest call/put wall, computed in-house from the Alpaca SPY option chain (formula: `GEX_strike = gamma x OI x 100 x spot^2 x 0.01`, dealer long-calls/short-puts; open-source ref: Matteo-Ferrara/gex-tracker).
- Use it as a **bias gate, not a trigger**: take bearish-continuation entries when `morning_sign` is down AND we're not in a strong long-gamma pin regime; abstain (or size down) on long-gamma pin days and when fighting the morning tape. This is the principled, evidence-based version of the regime-gate already in our cook-queue.
- Validate against our real-fills backtest + anchor-no-regression before any live gating (Rule 9).

**Why it's the top pick:** new, peer-reviewed, ~$0, and it sharpens the exact edge we just confirmed. Effort: a regime-tag module + a backtest. Sources: [Gao-Han-Li-Zhou SSRN 2440866](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866), [Baltussen JFE 2021](https://www.sciencedirect.com/science/article/abs/pii/S0304405X21001598), [Barbon-Buraschi SSRN 3725454](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3725454), [gex-tracker](https://github.com/Matteo-Ferrara/gex-tracker).

---

### GAME PLAN 2 — Exit refinement around the theta cliff  ★ the leverage we already named

**The find (triple-corroborated):**
- 0DTE theta decay is **back-loaded**: ~2%/hr at the open climbing past ~15%/hr after 14:00, with a sharp cliff ~15:30 ET (two independent minute-level studies agree).
- Trend-following's edge is **volatility-scaled risk management, not the entry** (Kim-Tse-Wald, peer-reviewed) + convex "let the winner run" payoff (AQR century-of-evidence). Chandelier trail belongs on the **underlying**, regime-conditional ATR multiple — never on option premium (that's the whipsaw we already killed).

**What we'd do (builds on the chart-stops win):**
- **Time-conditional exit**: replace the single 15:50 guillotine — keep the chandelier trail for positions in strong favor (let convex winners ride), but pull the exit forward to ~15:00-15:30 for any stagnant/non-favored position to step off the steepest decay. We already have the knob.
- Make the chandelier ATR-multiple **regime-conditional** (wider on high-ATR trend days, tighter on chop) instead of fixed 20%-off-HWM.
- Run the **partial-exit-vs-held-to-target A/B** from our 41-col trades.csv counterfactuals — confirm `tp1_qty_fraction 0.50` is buying reversal-protection vs quietly bleeding edge on the BEARISH_REJECTION population.

**Effort:** backtest sweeps on knobs we own (real-fills + anchor-no-regression). Sources: [Option Alpha 0DTE decay study](https://optionalpha.com/blog/0dte-options-time-decay), [Kim-Tse-Wald SSRN 2786955](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2786955), [AQR Century of Evidence](https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing).

---

### GAME PLAN 3 — Signal-honesty audit (the "logic" cleanup)

**The find (uncomfortable but evidence-backed):**
- **EMA ribbon / MA-stack = our weakest-evidence signal.** Sullivan-Timmermann-White (*J. Finance* 1999) + Zakamulin (2018): MA-timing edge doesn't survive data-snooping correction / is indistinguishable from buy-and-hold. No peer-reviewed support for "ribbon" as an intraday entry. Matches our own C28 ("ribbon flip is a lagging exit").
- **Levels are real — via order-clustering, not magic** (Osler 2000/2003; Kavajecz-Odders-White RFS 2004): orders/stops cluster at round numbers + prior-day levels, creating real depth. BUT the same research shows levels are **stop-run/sweep zones** (penetrate→reverse) as much as bounce zones — so "reclaim/break = go" can be providing exit liquidity to the fade.
- **VWAP** is a real *execution benchmark* (institutional fair-value line) but "VWAP bounce" as a precise trigger is practitioner folklore; anchored-VWAP has no peer-reviewed reaction edge.

**What we'd do (logic refinement, propose-only):**
- **Demote the ribbon** from edge-originator to context/exit-timing — don't let a ribbon flip *originate* a trade (it can confirm/time one). This aligns the engine with the evidence + our own lessons.
- Treat named levels as **liquidity zones, sweep-aware** — favor the reaction *after* a sweep (penetrate-then-reclaim with confirmation) over anticipating the hold. Rank prior-day H/L/C + round numbers above PMH/PML in confidence (PMH/PML have less dedicated academic support).
- Keep VWAP as **trend-context**, not a bounce trigger.

**Effort:** doctrine/logic review (Rule 9, propose for J) + backtest to confirm demoting-ribbon-as-originator doesn't regress. Sources: [STW 1999 SSRN 65140](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=65140), [Zakamulin 2018](https://onlinelibrary.wiley.com/doi/abs/10.1111/irfi.12132), [Kavajecz-Odders-White RFS 2004](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=315660), [Osler](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr150.pdf).

---

### GAME PLAN 4 — Use AI as research-staff, harder (the "how others use AI" answer)

**The find (every rigorous benchmark agrees):**
- **LLM-as-trader is weak** (StockBench ICLR'26: most LLMs can't beat buy-and-hold; FINSABER KDD'26: LLM strategies are "too passive in bull markets, too aggressive in bear" — *needs regime-aware risk controls*). **LLM-as-adversarial-researcher + overfitting controls is where the documented value is** (AlphaAgent; Anthropic's own orchestrator-worker: +90% on research breadth).
- The AI-trading *product* space is ~90% scams (CFTC formal advisory).

**What we'd do (both are ENFORCEMENT gaps, not new builds — we're already shaped right):**
- **Wire the Deflated-Sharpe / PBO promotion gate.** We BUILT the `backtest/lib/validation/` DSR/PBO lib this week but it's advisory-only. The Kitchen mines hundreds of candidates and ranks on raw Sharpe — de Prado's math guarantees that surfaces false positives. Make DSR/PBO a real gate on promotion (penalize by candidates-tried). Highest-leverage, $0, directly attacks "the 371st candidate is debt."
- **Adversarial bull/bear validation in the conductor.** Before any candidate promotes, a bull-researcher vs bear-researcher pass (TradingAgents/AlphaAgent pattern) — our conductor is already orchestrator-worker shaped; this adds the adversarial guard our swarm-decision-engine memory already wants.
- **Audit for the FINSABER signature**: is our engine systematically too passive in trends / too aggressive in chop? (That's the documented LLM failure mode; check our decisions.jsonl.)
- LLM-as-judge hygiene if we grade trades with Claude: counter position bias (judge A/B and B/A), prefer a different model family as judge.

**Effort:** wire an existing lib as a gate + an adversarial step in the conductor (both deliberate, conductor-appropriate). Sources: [StockBench arXiv 2510.02209](https://arxiv.org/abs/2510.02209), [FINSABER arXiv 2505.07078](https://arxiv.org/abs/2505.07078), [AlphaAgent arXiv 2502.16789](https://arxiv.org/html/2502.16789), [Anthropic multi-agent](https://www.anthropic.com/engineering/built-multi-agent-research-system), [CFTC advisory](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/AITradingBots.html), de Prado [Deflated Sharpe](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551).

---

### SKIPPED AS NOISE / OVERPRICED (the filter working)

- **Paid GEX/dark-pool subscriptions** (SpotGamma/MenthorQ/Tradytics $69-349/mo) — the marginal signal doesn't survive a VIX+IV control (FlashAlpha 8yr backtest: ρ=−0.03, p=0.18); we compute the useful regime-sign part ourselves for $0.
- **DIX / dark-pool prints for intraday** — DIX is a *monthly/positional* signal (free if ever wanted for swing bias); irrelevant to 0DTE timing. "Dark pool levels" products = marketing.
- **The "0DTE gamma squeeze moves the market" narrative** — CBOE's own data: net 0DTE dealer gamma is small (balanced flow); don't build on it.
- **ADX as a trend filter** — parameter-fragile, overfitting-prone, contradictory backtests. Use MA-slope if anything, validated on our data.
- **Anchored VWAP reaction edge, NYSE TICK/breadth extremes** — practitioner-only, no peer-reviewed support. Test before trusting, don't adopt on faith.
- **tastytrade "manage winners at 50%/21DTE"** — high-quality research but SELLER-side; structurally wrong for a directional buyer (theta is our enemy, payoff is convex).
- **All AI-trading bots / signal-sellers / "copy my AI" / profit-claim influencers** — CFTC-flagged scam territory.

---

### Recommended order (if we execute)
1. **Game Plan 1** (intraday-momentum + gamma regime tag) — the standout new edge, $0, corroborates our direction. Start here.
2. **Game Plan 2** (exit refinement) — the leverage we already named, builds on the chart-stops win.
3. **Game Plan 4** (DSR/PBO gate + adversarial validation) — cheap enforcement of what we built.
4. **Game Plan 3** (signal-honesty audit) — important logic cleanup, but a Rule-9 doctrine review (J's call).

All are propose/research-first (Rule 9); none auto-ship. Each is a bounded conductor-sized track, not a framework — deliberately lean.
