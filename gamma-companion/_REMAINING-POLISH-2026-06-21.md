# Gamma Companion — Remaining Polish (ready-to-apply edits)

**2026-06-21 · overnight · analysis-only.** Source audits: `analysis/_demo-polish-2026-06-21.md`,
`analysis/_demo-reliability-2026-06-21.md`. This file lists every **"rough"** and **"minor"** item from
those two audits that is **NOT already in the current code** — turned into exact `old → new` snippets,
verified against the CURRENT `gamma-companion/public/*` + `server.js` + `lib/*` (read 2026-06-21).

> **IMPORTANT — the integrator already shipped far more than the top-8.** Verified already present and
> therefore **dropped from this list**: the global `transition:` block (C1), the amber `.livepill.connecting`
> rule (A1), the robot lip-sync on typed-reply TTS via `u.onstart/onend` (D3), the `refresh()`-catch offline
> copy on `#next-title`/`#feed` (D2), **GridStack vendored locally** at `public/vendor/` (D2b/#3), the 20s chat
> watchdog + pre-warm + 16s/35s server timeouts (D4), the restored hero glow (`.hero::before` + `#glow`
> gradient, I1), `origin` threading into `runEscalation` (escalate.js), and the no-SVG diagram fallback to
> `SYSTEM_DIAGRAM` (part of D1/#5). Do not re-apply those.

Each edit below is small and surgical. `old_string` is copied verbatim from the live file. Apply in one pass.

---

## `gamma-companion/lib/state.js`

### S-1 [rough · audit R2] Wrap `readApprovals` + `derivedCards` so one bad state file can't 500 `/api/state`
`buildState` calls both unguarded (lines 145–146). A malformed `companion-approvals.json` element throwing
inside `readApprovals`/`derivedCards` makes `/api/state` 500 → the whole UI flips to "offline." Make it degrade
to an empty approvals list instead.

```js
  const fileApprovals = readApprovals(root);
  const approvals = [...fileApprovals, ...derivedCards(health, kitchen)];
```
→
```js
  let approvals = [];
  try {
    approvals = [...readApprovals(root), ...derivedCards(health, kitchen)];
  } catch {
    /* one bad state file must never blank the cockpit */
  }
```

---

## `gamma-companion/public/app.js`

### A-1 [rough · audit R3/#18] Show a retry affordance on approve failure (opacity restore already done)
Current `catch` restores opacity (good) but leaves the card as a silent red border — the old buttons are gone
and nothing tells J it failed. Add visible copy + a click-to-retry. (Note: the retry re-runs `decide`, so the
card text is rebuilt by the next `refresh()` on success.)

```js
    } catch (e) { card.className = "acard err"; card.style.opacity = "1"; }
```
→
```js
    } catch (e) {
      card.className = "acard err"; card.style.opacity = "1";
      card.textContent = "That didn't go through — tap to retry.";
      card.style.cursor = "pointer";
      card.onclick = () => { card.onclick = null; card.style.cursor = ""; decide(a, decision, card); };
    }
```

### A-2 [rough · audit D1/#5 remainder] Validate the escalated SVG (viewBox + a real shape) before rendering
The no-SVG branch already falls back, but a **truncated/garbled** `<svg>` (escalation is sliced to 20k) still
gets stuffed into the iframe and shows a blank/partial box. Reject an SVG that lacks a `viewBox` or any
`<rect`/`<path`/`<circle`/`<line` and fall back to the instant diagram.

```js
  function renderDiagram(result, topic) {
    const svg = extractSvg(result && result.summary);
    if (!svg) { showSystemDiagram(); return; }
```
→
```js
  function renderDiagram(result, topic) {
    const svg = extractSvg(result && result.summary);
    const valid = svg && /viewBox/i.test(svg) && /<(rect|path|circle|line)\b/i.test(svg);
    if (!valid) { showSystemDiagram(); return; }
```

### A-3 [rough · audit D1/#5 remainder] Lower the diagram poll wall from 110 (~4.6 min) to 40 (~1.7 min)
A 4.6-minute wall is far past any demo's patience; it already falls back to `showSystemDiagram()` on timeout —
just trip it sooner.

```js
      if (tries > 110) { clearInterval(iv); showSystemDiagram(); }
```
→
```js
      if (tries > 40) { clearInterval(iv); showSystemDiagram(); }
```

### A-4 [rough · audit R4] Generic follow-up chips when a Claude-drawn diagram has zero `data-q`
A custom SVG with no `data-q` attributes leaves `#focus-chips` empty and the focus pane looks bare. Seed 3
generic chips in that case. (The instant `SYSTEM_DIAGRAM` always has `data-q`, so this only affects custom draws.)

```js
    const chips = $("focus-chips");
    chips.innerHTML = "";
    qs.slice(0, 6).forEach((q) => {
      const b = document.createElement("button");
      b.className = "quick";
      b.textContent = q;
      b.onclick = () => requestDiagram(q);
      chips.appendChild(b);
    });
  }
  // Instant, accurate system diagram (no Claude wait) for the headline demo.
```
→
```js
    const chips = $("focus-chips");
    chips.innerHTML = "";
    const chipQs = qs.length ? qs.slice(0, 6) : ["Explain this", "Show me the code path", "How does Gamma work?"];
    chipQs.forEach((q) => {
      const b = document.createElement("button");
      b.className = "quick";
      b.textContent = q;
      b.onclick = () => requestDiagram(q);
      chips.appendChild(b);
    });
  }
  // Instant, accurate system diagram (no Claude wait) for the headline demo.
```

### A-5 [minor · audit M5/#21] Clear the active diagram / ask poll interval on focus-close (timer leak)
`pollDiagram`/`trackAsk` intervals keep running after the user closes the focus pane. Track the active diagram
interval and clear it on close. (Two coordinated edits.)

**A-5a** — capture the interval id in `pollDiagram`:
```js
  function pollDiagram(id, topic) {
    let tries = 0;
    const iv = setInterval(async () => {
```
→
```js
  let diagramPoll = null;
  function pollDiagram(id, topic) {
    let tries = 0;
    const iv = setInterval(async () => {
```
…and record it right after the `setInterval(...)` block closes (the line that currently ends the interval):
```js
    }, 2500);
  }
  function renderDiagram(result, topic) {
```
→
```js
    }, 2500);
    diagramPoll = iv;
  }
  function renderDiagram(result, topic) {
```

**A-5b** — clear it on focus-close:
```js
  (function () {
    const fc = $("focus-close");
    if (fc) fc.onclick = () => { const f = $("focus"); if (f) f.hidden = true; };
  })();
```
→
```js
  (function () {
    const fc = $("focus-close");
    if (fc) fc.onclick = () => {
      if (diagramPoll) { clearInterval(diagramPoll); diagramPoll = null; }
      const f = $("focus"); if (f) f.hidden = true;
    };
  })();
```

### A-6 [minor · audit F4/#20] Animated dots on the `thinking…` pill so it reads as alive, not stuck
The watchdog text swap is already wired; this just animates the resting bubble via a class the CSS below targets.
```js
    const thinking = addMsg("Gamma", "thinking…", "work");
```
→
```js
    const thinking = addMsg("Gamma", "thinking", "work");
    if (thinking.lastChild) thinking.lastChild.classList.add("dots");
```
(Pair with CSS **C-6** below. The watchdog at +20s overwrites `lastChild.textContent`, which clears the dots —
acceptable: the message changes to "still working on it…" at that point.)

---

## `gamma-companion/public/realtime.js`

### R-1 [rough · audit D3/#6 remainder] Make the realtime connect error human (caller already shows a typed-fallback hint)
`app.js` already catches `error:*` and shows "Voice hiccup — you can type to me instead", but the raw status
string (`realtime connect failed (4xx)`) is what gets logged/surfaced. Humanize the common 4xx (no Realtime
access/credit on the key) at the source.

```js
      if (!sdpRes.ok) throw new Error("realtime connect failed (" + sdpRes.status + ")");
```
→
```js
      if (!sdpRes.ok) {
        throw new Error(
          sdpRes.status >= 400 && sdpRes.status < 500
            ? "Voice isn't enabled on this OpenAI key yet — everything else works, just type to me."
            : "Voice service is unavailable right now (" + sdpRes.status + ") — type to me instead."
        );
      }
```

---

## `gamma-companion/public/styles.css`

> All CSS below is **additive** — append the new rules; only G-1/G-2 replace existing single-line-ellipsis rules.

### C-1 [minor · audit H1/#19] Declare `color-scheme: dark` + neutralize autofill (light caret / white autofill box)
Add to the existing `:root` block.
```css
:root {
  --accent: #34e0a1;
```
→
```css
:root {
  color-scheme: dark;
  --accent: #34e0a1;
```
…and append (anywhere, e.g. after the `.ask input` rules):
```css
input:-webkit-autofill,
input:-webkit-autofill:focus {
  -webkit-box-shadow: 0 0 0 1000px transparent inset;
  -webkit-text-fill-color: var(--ink);
  transition: background-color 9999s;
}
```

### C-2 [rough · audit H2/#15] Opaque fallback for glass tiles where `backdrop-filter` is off
On a GPU-blocklisted / reduced-transparency machine the 4.5%-white glass becomes near-invisible. Append:
```css
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .glass,
  .grid-stack-item-content.tile,
  .ask,
  .bottomnav { background: rgba(20, 28, 46, 0.82); }
}
```

### C-3 [rough · audit C3/#17] `:focus-visible` ring (keyboard nav is currently invisible)
Append:
```css
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 8px; }
.ask:focus-within { box-shadow: 0 0 0 3px var(--accent-soft); }
```

### C-4 [minor · audit H3/#20] `prefers-reduced-motion` guard (float / ripple / pulse loops)
Append (last, so it wins). Keeps one-shot entrances, kills the infinite loops:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
  }
}
```

### C-5 [minor · audit H4/#21] Slim scrollbar on the chat log + focus chips (currently native/chunky)
Append:
```css
.chatlog::-webkit-scrollbar,
.focuschips::-webkit-scrollbar { width: 7px; }
.chatlog::-webkit-scrollbar-thumb,
.focuschips::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.08); border-radius: 4px; }
```

### C-6 [minor · audit F4/#20] Animated `…` for the `thinking` bubble (pairs with app.js A-6)
Append:
```css
.msg.work .dots::after { content: ""; animation: dots 1.4s steps(4, end) infinite; }
@keyframes dots { 0% { content: ""; } 25% { content: "."; } 50% { content: ".."; } 75% { content: "..."; } 100% { content: ""; } }
```

### G-1 [rough · audit G1/#14] Feed text: 2-line clamp instead of single-line ellipsis (long alerts get chopped)
Replace the `.titext` rule.
```css
.titext { flex: 1; font-size: 14.5px; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
```
→
```css
.titext { flex: 1; font-size: 14.5px; line-height: 1.4; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; white-space: normal; }
```
…and make the timeline connector tolerate variable-height rows (it currently assumes a fixed 42px single-line row):
```css
.timeline li:not(:last-child) .tdot::after { content: ""; position: absolute; left: 50%; top: 14px; transform: translateX(-50%); width: 2px; height: 42px; background: rgba(255,255,255,0.07); }
```
→
```css
.timeline li:not(:last-child) .tdot::after { content: ""; position: absolute; left: 50%; top: 14px; bottom: -12px; transform: translateX(-50%); width: 2px; background: rgba(255,255,255,0.07); }
```

### G-2 [rough · audit G2/#14] Next-card title: clamp to 2 lines (the first line a friend reads)
Replace the `.nctext b` rule (leave `.nctext small` 1-line as-is).
```css
.nctext b { font-size: 14px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
```
→
```css
.nctext b { font-size: 14px; font-weight: 600; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
```

### C-7 [minor · audit F1/#20] Optional: designed empty state for approvals + feed
Lowest priority. The current empties (`.muted-empty` "Nothing needs you right now.", `li.empty` "Nothing here
right now.") are honest but plain. If time remains, add a `.emptystate` flex-column with a small check-circle SVG
above the line — but this needs matching markup changes in `renderApprovals`/`renderFeed` (app.js:111, :79),
so it is a *paired* JS+CSS change, not a drop-in. Recommend deferring unless the demo opens on an idle rig
(`node seed-demo.js` is the cheaper fix — populates real cards so the empty state is never seen).

---

## `gamma-companion/server.js`

### SV-1 [minor · audit M4/#21] Serve a favicon to kill the console 404
Two surgical adds. **SV-1a** — append a tiny inline-SVG favicon link in the HTML head injection (reuse the
existing `</head>` replace so it ships on every page load, no new file):
```js
        buf.toString("utf8").replace("</head>", '<meta name="gamma-token" content="' + GAMMA_TOKEN + '" />\n  </head>')
```
→
```js
        buf.toString("utf8").replace(
          "</head>",
          '<meta name="gamma-token" content="' + GAMMA_TOKEN + '" />\n' +
            '  <link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2040%2040%22%3E%3Crect%20x%3D%228%22%20y%3D%2212%22%20width%3D%2224%22%20height%3D%2220%22%20rx%3D%227%22%20fill%3D%22%2334e0a1%22%2F%3E%3C%2Fsvg%3E" />\n  </head>'
        )
```
This embeds the brand-green robot body as the tab icon; no static file required and no new route. (If you'd
rather, the alternative is a real `public/favicon.svg` + the same `<link>` — but the data-URI keeps it zero-file.)

---

## Apply order (suggested)

1. **S-1, A-1, A-2, A-3, A-4, R-1** — the *reliability* rough items (no blank diagram, no silent approve fail,
   no offline-on-one-bad-file, human voice error). Highest demo value remaining.
2. **C-1, C-2, C-3** — `color-scheme` + glass fallback + focus ring (cross-engine / a11y robustness).
3. **G-1, G-2** — text clamping (stop chopping the lines a friend reads first).
4. **A-5, A-6, C-4, C-5, C-6, SV-1** — minor polish (timer leak, animated dots, reduced-motion, scrollbars, favicon).
5. **C-7** — defer (paired markup change; `seed-demo.js` is the cheaper demo fix).

## Verify after applying
```
node --check gamma-companion/server.js
node --check gamma-companion/lib/state.js
node --check gamma-companion/public/app.js
node --check gamma-companion/public/realtime.js
node gamma-companion/smoke-guard.js     # must stay 14/14
```
(CSS has no syntax checker here; eyeball the appended blocks — all are additive except G-1/G-2 which are
1:1 rule replacements.)
