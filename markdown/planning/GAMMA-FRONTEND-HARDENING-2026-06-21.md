# Gamma Companion — Frontend Hardening Plan (2026-06-21)

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

## Principle for this pass

Every fix is the SMALLEST change that removes a way the cockpit can break:
1. One global CSS line kills the entire `[hidden]`-vs-`display` bug class at the root.
2. Strip the async Claude-draw diagram path — it is the sole source of stuck/blank panes.
3. Guard the unguarded synchronous DOM derefs that gate the whole IIFE.
4. Fault-isolate each init call and each render step so one failure can't starve the data loop.
5. A CSS fail-safe so a dead GridStack degrades to readable flow instead of an overlapping pile.

No rewrites. Each edit is independently revertible.

---

## APPLY LIST (critical/high first)

### 1. [CRITICAL] Global `[hidden]` guard — kills the whole bug class at the root
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

### 2. [HIGH] Strip the async Claude-draw diagram path — keep only the trusted inline SVG
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

### 3. [HIGH] One close helper + Escape fallback; no stale interval reference
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

### 4. [CRITICAL] Guard `setGreeting` — the first unguarded deref gates the WHOLE script
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

### 5. [CRITICAL] Fault-isolate the init sequence so one subsystem can't starve the data loop
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

### 6. [HIGH] Guard the two wiring derefs that gate the init sequence
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

### 7. [HIGH] CSS fail-safe: a dead GridStack degrades to readable flow, not an overlapping pile
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

### 8. [MED] Fault-isolate each render step inside refresh()
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

### 9. [MED] Null-guard the render fns that still deref bare ($status, $live, $feed, next-title/sub)
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

### 10. [MED] Make the mobile `.focus` override self-contained
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

## STRIP-BACK RECOMMENDATION

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

## REJECTED / NOT DOING (avoid risk + scope creep)

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

## VERIFICATION CHECKLIST (after applying)

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
