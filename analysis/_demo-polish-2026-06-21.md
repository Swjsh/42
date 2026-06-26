# Gamma Companion — Apple-Level Visual + Interaction Polish Audit
**2026-06-21 · overnight · scope: `public/styles.css`, `public/index.html`, `public/app.js` (+ `realtime.js`)**

Goal: the app must be *stunning instantly*, demo-proof, and never read as smoke-and-mirrors. This is the gap list. Each item: the exact element/file, why it reads as unpolished, the precise fix. The integrator applies these coherently — do NOT ship piecemeal CSS that fights the GridStack layout.

Legend: **[P0]** breaks first-impression / demo · **[P1]** clearly unpolished · **[P2]** refinement.

---

## A. FIRST IMPRESSION — the open-cold moment

### A1 [P0] Boot state shows RED "offline" pill for ~5s — reads as broken
`index.html:20` ships the live pill as `class="livepill off"` with text `connecting…`. `off` paints the dot **red** (`styles.css:58`). The first `refresh()` only runs after `app.js:434`, and the poll is 5s — so for up to 5 seconds on a cold open the headline status is a **red dot = "offline"**. A friend opening the app sees "broken" before they see anything.
**Fix:** ship a neutral *connecting* state, not the error state. Add to CSS:
```css
.livepill.connecting .ldot { background: var(--warn); box-shadow: 0 0 8px var(--warn); animation: pip 1.4s infinite; }
```
`index.html:20` → `class="livepill connecting"`. In `renderLive()` (`app.js:56`) clear `connecting` once the first state lands. Fire `refresh()` is already first-thing; also reduce the *perceived* gap by painting "connecting" amber not red.

### A2 [P0] No first-paint skeleton — three tiles say "Loading…", "Listening…", empty
On open: next-card = `Loading…` (`index.html:74`), feed = `Listening…` (`index.html:110`), status row = **completely empty** (`#status` populated only after first poll). Empty + "Loading" + a lone robot = unfinished, not premium. Apple apps never show a bare "Loading…" string.
**Fix:** add shimmer skeletons. One reusable class:
```css
@keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
.skel { background: linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.09) 37%, rgba(255,255,255,0.04) 63%); background-size: 200% 100%; animation: shimmer 1.4s infinite; border-radius: 8px; color: transparent; }
```
Seed the next-card title, two feed rows, and 3 status chips with `.skel` placeholders in markup; `app.js` replaces them on first `refresh()`. Removes the dead "Loading…/Listening…" strings.

### A3 [P1] The hero greeting reflows on load (FOUC of text)
`index.html:70` hard-codes `Hello 👋`, then `setGreeting()` (`app.js:32`) rewrites it to "Good morning/afternoon/evening" on first JS tick. The visible word **changes** right after paint — a tiny but cheap-feeling jump.
**Fix:** render the time-of-day greeting server-side in `index.html`, OR set `visibility:hidden` on `#greet` until JS paints (it runs synchronously at top of the IIFE, so the flash is ~1 frame but real on slow loads). Cleanest: have the server inject the greeting like it injects the token.

### A4 [P2] Robot is the hero but has no entrance — it just *is* there
`.robot` (`styles.css:262`) floats/blinks immediately. A premium open animates the protagonist in. Add a one-shot scale+fade on `.botbody` (separate from the infinite `float`):
```css
.botbody { animation: botIn .6s cubic-bezier(.2,.9,.25,1) both, float 4s ease-in-out 0.6s infinite; }
@keyframes botIn { from { opacity:0; transform: translateY(14px) scale(.92); } to { opacity:1; transform:none; } }
```
(Note: `botIn` and `float` both target `transform` — chain them by delaying `float` 0.6s as above, do NOT stack two transform animations simultaneously or they'll fight. This is the correct sequencing.)

---

## B. CONSISTENCY — spacing, type scale, radius, color

### B1 [P1] Type scale is ad-hoc — 9 different font-sizes, several with .5px
Across the files: `22px, 25px, 14px, 12px, 12.5px, 13px, 13.5px, 14.5px, 15px, 11px`. The fractional sizes (`12.5`, `13.5`, `14.5`) are a tell of hand-tuning without a scale. Apple uses a tight ramp.
**Fix:** collapse to a token scale in `:root`:
```css
--fs-xs:12px; --fs-sm:13px; --fs-md:14px; --fs-lg:16px; --fs-xl:20px; --fs-2xl:25px;
```
Replace the `.5px` sizes with the nearest token. Biggest offenders: `.bsub` 12px, `.livepill` 12.5px, `.quick` 13.5px, `.titext` 14.5px, `.chip` 13px → normalize.

### B2 [P1] Radius is inconsistent — 12 / 16 / 20 / 24px + 999 all in play
`.glass` 24px, `.tile` 20px, `.acard`/`.nextcard` 16px, `.btn`/`.chip` 12px, `.msg` 16px (but 5px on the tail). No system → corners feel arbitrary tile-to-tile.
**Fix:** define `--r-sm:12px; --r-md:16px; --r-lg:20px; --r-xl:24px; --r-pill:999px;` and map every literal to one. Decide ONE card radius (recommend `--r-lg:20px` to match the tiles, since cards live inside tiles) so nested corners are concentric, not clashing.

### B3 [P2] Spacing values are unsystematic (`6/8/9/10/11/13/14/16/18px`)
e.g. `.quickrow gap:9px`, `.brand gap:11px`, `.timeline li gap:13px`. Move to an 8pt-ish grid (`4/8/12/16/20/24`). Pick the nearest step; nobody will miss the odd 9s and 11s, and rhythm tightens noticeably.

### B4 [P1] Two color systems for the same semantic — bad/warn defined as both vars and raw rgba
`--bad:#ff6b6b` exists, but the mic listening state hard-codes `rgba(255,107,107,...)` six times (`styles.css:207-208`), and the timeline tags hard-code `rgba(240,178,74,...)`/`rgba(110,168,255,...)` (`styles.css:163-164`) instead of using `--warn`/`--blue`. Drift risk + can't theme.
**Fix:** add `--bad-soft`, `--warn-soft`, `--blue-soft` rgba tokens and replace every raw rgba of an existing semantic color.

### B5 [P2] Accent green hard-coded in markup defeats the CSS var
The brand SVG (`index.html:15`) and robot gradients (`index.html:41-46`) hard-code `#34e0a1`/`#7af7d0`. The SYSTEM_DIAGRAM (`app.js:336+`) hard-codes the full palette again (`#eef2f6`, `#9aa6bd`, `#34e0a1`...). Three copies of the brand palette. Not a visual bug today but guarantees future drift. Acceptable for SVG fills; at minimum add a comment block naming these as the canonical brand hexes.

---

## C. MICRO-INTERACTIONS — hover / active / focus

### C1 [P0] No `transition` on ANY interactive element — every state change snaps
There is not a single `transition:` rule in `styles.css`. Every hover (`.nextcard:hover`, `.quick:hover`, `.pill`, `.iconbtn.on`), every `:active` scale, the live-pill color, the focus-within border — all **snap instantly**. This is the #1 thing that separates "web demo" from "Apple app."
**Fix:** add a global interaction transition:
```css
.iconbtn, .quick, .pill, .nextcard, .btn, .nav, .chip, .circ, .ask, .livepill, .msg {
  transition: background .18s ease, border-color .18s ease, color .18s ease,
              transform .12s cubic-bezier(.2,.9,.25,1), box-shadow .18s ease;
}
```
This single block transforms the entire feel.

### C2 [P1] Buttons have hover OR active but never both, and several have neither
- `.quick` (`styles.css:142`) has `:hover` border but no `:active` press.
- `.nav` (bottom nav, `styles.css:220`) has **no hover and no active** — the primary navigation feels dead.
- `.iconbtn` (top-right) has no `:hover` — only the toggled `.on` state.
- `.pill` filter buttons — no hover.
- `.nextcard` has hover bg but no press feedback.
**Fix:** give each a `:hover` (subtle bg/border lift) and `:active { transform: scale(.97); }`. For `.nav:hover { color: var(--muted); }` and `.nav:active { transform: scale(.92); }`.

### C3 [P1] No `:focus-visible` anywhere — keyboard nav is invisible, fails a11y demo
Zero focus-ring styling. Tab through the app in front of a friend and nothing shows where focus is. (The mic/send/nav are all `<button>`s.)
**Fix:**
```css
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 8px; }
.ask:focus-within { box-shadow: 0 0 0 3px var(--accent-soft); }
```

### C4 [P2] Send button (the brand-green CTA) has active but no hover
`.circ.send` (`styles.css:209`) is the primary action — full accent green — but only has `:active`. A premium CTA brightens on hover.
**Fix:** `.circ.send:hover { filter: brightness(1.08); box-shadow: 0 4px 16px rgba(52,224,161,.4); }`

### C5 [P2] Quick-action chips: no pressed/selected affordance when tapped
`.quick` chips fire `send()` (`app.js:396`) but give no tactile confirmation the tap registered before the chat populates. Add the `:active { transform: scale(.96); }` from C1/C2.

---

## D. ROBOT + VOICE-REACTIVE STATES

### D1 [P1] Robot state transitions are abrupt — class swap with no easing
`robotState()` (`app.js:232`) removes/adds `listening`/`talking` classes. The ripple rings and eye-bounce **pop in/out** because there's no transition on opacity/scale of `.ring`. Going idle→listening, the rings appear hard.
**Fix:** `.ring { transition: opacity .3s ease; }` and ensure the idle state fades the rings rather than cutting them.

### D2 [P1] `.robot-status` text changes with no crossfade — "Tap the mic to talk" → "Listening…" jumps
`#robot-status` (`app.js:238`) hard-swaps text. A 150ms fade reads as intentional.
**Fix:** wrap the swap: add `transition: opacity .15s` on `.robot-status`, set opacity 0 → change text → opacity 1 (tiny JS helper), or use a CSS class toggle. At minimum `transition: color .2s` so the idle→accent color (`styles.css:115`) eases.

### D3 [P0] The "talking" state is driven by audio deltas but has no fallback for TTS path
When `ttsOn` and the browser SpeechSynthesis speaks a typed reply (`app.js:227`), the robot **never enters `talking`** — only the OpenAI Realtime path drives `robotState("talking")` (`app.js:266`). So in the common demo (type a question, hear it spoken), the robot sits idle while a voice comes out. Reads as disconnected.
**Fix:** in `speak()` (`app.js:227`), wire `u.onstart = () => robotState("talking")` and `u.onend = () => robotState(null)`. Now the robot lip-syncs the typed-reply TTS too — a huge "it's alive" demo moment essentially free.

### D4 [P2] Antenna blink + float + wave are all infinite & unsynchronized — slightly chaotic at rest
Three independent infinite loops (`float` 4s, `blink` 2.4s, `wave` 3s) on the idle robot. Fine, but the `wave` arm snaps (`@keyframes wave` 92%→96%→100%, `styles.css:113`) which can look like a glitch. Soften: widen the wave window and ease it, or drop the idle wave entirely and reserve the wave for the *greeting* moment only (more meaningful).

---

## E. TRANSITIONS — mode changes / focus mode

### E1 [P1] Focus (diagram) mode: nice entrance, NO exit animation
`.focus` has `@keyframes focusin` (`styles.css:225-226`), but close just sets `f.hidden = true` (`app.js:391`) — it **vanishes instantly**. Asymmetric: slides in, hard-cuts out. Jarring on the headline "diagram it" demo.
**Fix:** add a `focusout` animation; on close, add a closing class, listen for `animationend`, then set `hidden`. Or simpler — transition `opacity`/`transform` on a `[hidden]`-replacement class instead of the `hidden` attribute (which can't animate).

### E2 [P2] Diagram spinner → rendered SVG is a hard swap
`drawMsg()` shows a spinner (`app.js:294`), then `renderDiagram()` replaces `innerHTML` with the iframe (`app.js:317`). The spinner-to-diagram cut is abrupt. Cross-fade the iframe in (`opacity 0→1` on iframe load) so the assembled diagram "arrives."

### E3 [P2] Bottom-nav tab switch only recolors — no indicator movement
Tapping a nav item just toggles `.on` color (`app.js:404`). Premium tab bars slide an indicator or scale the icon. Since non-home tabs are stubs ("coming soon", `app.js:408`), at minimum animate the icon: `.nav.on .ic { transform: translateY(-1px) scale(1.05); }` with the C1 transition.

### E4 [P1] GridStack edit-mode toggle is instant — tiles snap to dashed outline
Entering edit mode (`app.js:423`) adds `body.editing` → dashed outlines + dotted bg appear instantly (`styles.css:239,254`). A gentle transition on the outline/opacity sells "now editable." Add `transition: outline-color .2s` and a subtle `body.editing .tile { transform: scale(.995); }` settle.

---

## F. LOADING / EMPTY / ERROR STATES

### F1 [P1] Empty states are bare gray text, not designed
- Approvals empty: `Nothing needs you right now.` (`app.js:110`) — plain `.muted-empty` text, left-aligned, no icon.
- Feed empty: `Nothing here right now.` (`app.js:78`) — centered gray.
- Chat log empty: hidden entirely (`styles.css:189`).
None feel intentional. Apple empty states have a glyph + a reassuring line.
**Fix:** give the approvals + feed empty states a small centered SVG (a check-circle / a calm robot) + the line beneath, in a `.emptystate` flex-column. Turns "nothing" into "all clear."

### F2 [P0] Error states are silent or cryptic in the demo path
- Chat failure (`app.js:199`): `(couldn't reach the face — is the server up?)` — developer language, shown to a *friend*.
- Approve failure (`app.js:135`): just turns the card red (`acard err`) with **no message** — the card keeps its old text, so it looks like nothing happened.
- Diagram failures: `Couldn't reach the server.` / `That took too long — tap close and try again.` — acceptable but plain.
**Fix:** (a) humanize the chat error: "I lost my connection for a second — try that again." (b) On approve error, set the card text to a visible "That didn't go through — tap to retry." with a retry handler, not just a red border. (c) Keep diagram errors but add the warn icon.

### F3 [P1] The 20-40s diagram wait has a spinner but no progress sense
`requestDiagram` (`app.js:294`) shows "about 20–40s". A 30-second spinner is an eternity in a live demo and feels hung. Add staged status text that advances ("reading the project…" → "sketching nodes…" → "almost there…") on a timer, OR show the instant `SYSTEM_DIAGRAM` skeleton greyed-out behind the spinner. The instant hand-crafted diagram already exists for "how gamma works" — lean on it; for *custom* diagrams the staged text is the cheap win.

### F4 [P2] `thinking…` chat placeholder is a dashed pill, fine, but no animated dots
`addMsg("Gamma","thinking…","work")` (`app.js:190`). Add an animated `…` (three pulsing dots) so it reads as alive not stuck. Pure CSS `@keyframes` on `::after`.

---

## G. TEXT OVERFLOW / TRUNCATION / ALIGNMENT

### G1 [P1] Feed text is single-line ellipsis — long alerts get chopped mid-word with no recovery
`.titext` (`styles.css:161`) is `white-space:nowrap; overflow:hidden; text-overflow:ellipsis`. The `title` attr (`app.js:93`) gives a tooltip, but in a touch/demo context the tooltip is invisible. Important alerts get truncated to "SPY reclaimed 6,0…".
**Fix:** allow 2 lines with `-webkit-line-clamp:2` instead of single-line nowrap:
```css
.titext { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; white-space:normal; overflow:hidden; }
```
Adjust the timeline connector height (`styles.css:159`, fixed `42px`) which assumes single-line rows — it will mis-align once rows vary in height. Make the connector `top:0;bottom:0;height:auto` relative to the row.

### G2 [P1] Next-card title + sub both `nowrap` ellipsis — the headline "what's next" line gets cut
`.nctext b` and `small` (`styles.css:130-131`) are nowrap ellipsis. The hero's primary CTA — Gamma's current read — truncates on a narrow tile. This is the line a friend reads first.
**Fix:** let the title clamp to 2 lines (as G1); keep the sub to 1. The `setNextCard` split on `|`/`—` (`app.js:65`) already separates title/sub, so the title has room.

### G3 [P2] `.greet` 25px on a 134px-column hero can collide with the robot on the 1-col breakpoint
At `breakpoints:[{w:560,c:1}]` (`app.js:419`) the hero tile goes full-width but the `.hero` grid stays `134px 1fr` (`styles.css:260`). On a very narrow window the robot + 25px greeting compete. Verify at ~360px; consider stacking `.hero` to a single column under a media query (robot on top, text below).

### G4 [P2] Status chips wrap but the tile is `tile-flush` height 1 row — chips can clip
`#status` lives in a `gs-h="1"` tile (`index.html:114`) with `.status { flex-wrap:wrap }` (`styles.css:180`). Four chips (Safe/Bold/Engine/Kitchen) at equity text width can wrap to 2 rows and clip inside the 1-row tile (`overflow:auto` gives an ugly scrollbar). Either bump that tile to `gs-h` 1.5 equivalent or guarantee chips fit on one line at the design width.

---

## H. DARK-MODE CORRECTNESS / RENDERING

### H1 [P2] App is dark-only but declares no `color-scheme` — form controls + scrollbars render light
No `color-scheme: dark` on `:root`/`html`. The `<input>` (`index.html:138`) text caret, autofill background, and native scrollbars (where `-webkit-scrollbar` isn't honored) render in light-mode chrome on some engines. Autofill especially paints a white box over the dark ask-bar.
**Fix:**
```css
:root { color-scheme: dark; }
input:-webkit-autofill { -webkit-box-shadow: 0 0 0 1000px transparent inset; -webkit-text-fill-color: var(--ink); transition: background-color 9999s; }
```

### H2 [P1] `backdrop-filter: blur` with no opaque fallback — on unsupported/disabled GPU the glass tiles go nearly invisible
`.glass`/`.tile`/`.ask`/`.bottomnav` all rely on `backdrop-filter` over a `--glass` of `rgba(255,255,255,0.045)` — *4.5% white*. If backdrop-filter is off (Electron flag, GPU blocklist, reduced-transparency OS setting), the tiles render as a 4.5%-white wash with no blur = barely-there ghosts on the dark bg. Demo-fragile.
**Fix:** `@supports not (backdrop-filter: blur(1px)) { .glass,.tile,.ask,.bottomnav { background: rgba(20,28,46,0.82); } }` so it degrades to a solid frosted card, never invisible.

### H3 [P2] No `prefers-reduced-motion` guard — float/ripple/shimmer run for motion-sensitive users
Many infinite animations (robot float, antenna blink, pip pulse, mic pulse). A friend with reduced-motion set sees a busy screen.
**Fix:** `@media (prefers-reduced-motion: reduce) { *,*::before,*::after { animation-duration:.001ms !important; animation-iteration-count:1 !important; transition-duration:.001ms !important; } }` — keep the one-shot entrances, kill the loops.

### H4 [P1] Scrollbars: custom on `.scroll`/`.tile` but the chatlog + focuschips use default
`.chatlog` (`styles.css:188`, `overflow-y:auto`) and `.focuschips` (`styles.css:235`) get the **native** scrollbar (light, chunky) while `.scroll`/`.tile` get the slim custom one. Inconsistent.
**Fix:** apply the `::-webkit-scrollbar` slim treatment globally or to these two.

---

## I. STRUCTURAL / CSS HYGIENE (causes the bugs above)

### I1 [P1] `styles.css` defines the hero/robot/quickrow/status TWICE — first block is dead/overridden
Lines 82-115 define `.hero` (grid `150px 1fr`, `padding 16px`, `::before` glow) and `.robot` (150px); then lines 260-265 **redefine** `.hero` (grid `134px 1fr`, padding 0, `::before` display:none) and `.robot` (134px). The first definitions are largely overridden — the glow `::before` is killed, the original padding/margin discarded. This is confusing dead CSS and a source of "why doesn't my change work" bugs.
**Fix:** delete the superseded first declarations; keep one canonical `.hero`/`.robot`. Re-add the radial glow `::before` to the *kept* rule if the glow is wanted (right now it's disabled — the hero lost its accent glow, arguably a downgrade worth restoring inside the tile).

### I2 [P1] `.iconbtn.on` defined twice with different bg (line 65 vs 256)
`styles.css:65` sets `.iconbtn.on { color + border }`; `styles.css:256` re-sets `.iconbtn.on { color + border + background:var(--accent-soft) }`. Second wins; first is redundant. Consolidate.

### I3 [P2] `.block` defined twice (line 145 `margin-top:18px` vs line 263 `margin-top:0`)
Same dead-override pattern. The tiles own spacing now, so `margin-top:0` wins — remove the first.

### I4 [P2] `.app` has `width:100%; margin:0 auto` (`styles.css:28`) — the `margin:auto` is a no-op at 100% width
Leftover from a max-width layout. Harmless but signals the CSS wasn't cleaned after the GridStack migration. Remove `margin:0 auto` or restore an intended `max-width`.

---

## TOP 5 POLISH WINS (do these first — biggest perceived-quality jump per line of CSS)

1. **C1 — add one global `transition:` block.** Zero markup change; instantly upgrades every hover/press/state from "web page" to "app." Highest ROI in the file.
2. **A1+A2 — kill the red-"offline"-on-boot + add shimmer skeletons.** Removes the two things that make a cold open read as "broken/unfinished" in the first 5 seconds.
3. **D3 — robot lip-syncs typed-reply TTS (`speak()` → `onstart/onend`).** Makes the robot feel *alive* in the most common demo path (type → spoken answer) for ~4 lines of JS.
4. **F2 — humanize error states + visible approve-failure message.** No "is the server up?" dev-speak in front of a friend; failures look handled, not crashed.
5. **I1 — delete the duplicated hero/robot CSS + restore the hero glow.** Removes the dead-override trap and brings back the accent halo the tile migration silently dropped.
