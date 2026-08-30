# GAMMA COCKPIT — DESIGN SPEC v1

**Fork resolved up front (this is the one real judgment call in the research):** the lanes offer two mutually exclusive directions — Vercel/Axiom **zero-chroma neutrals + rare accent**, or Railway **accent-tinted canvas**. This spec commits to **zero-chroma**. Every gray is `C = 0` in oklch (R=G=B). Purple appears only where something is *actionable, alive, or in flight*. The existing aurora is the single biggest risk to this — it bleeds hue into everything downstream and produces exactly the "half-tinted = looks like a color-management bug" failure the research flags. It is **replaced**, not tuned: one contained radial bloom behind the graph canvas only (§2 canvas), nothing page-wide.

Weight note: the no-web-fonts constraint means the Mercury "480 weight" recipe is unbuildable — system stacks expose 400/500/600/700 only. Translation: **500 is the considered weight for all hero numbers; 600 is reserved for genuinely urgent state.** Never 700.

---

## 1. TOKENS

```css
:root {
  /* ── TYPEFACES (system only, no @font-face, no CDN) ───────────── */
  --font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI Variable Text",
               "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono: ui-monospace, "Cascadia Mono", "Cascadia Code", "SF Mono",
               Menlo, Consolas, "Liberation Mono", monospace;

  /* ── NEUTRAL RAMP — chroma is ZERO on every step. Non-negotiable. ──
     Canvas is DARKER than cards: elevation is luminance, not shadow.    */
  --s-void:      oklch(0.085 0 0);            /* #050505  page shell, gutters   */
  --s-canvas:    oklch(0.115 0 0);            /* #070707  graph canvas floor    */
  --s-panel:     oklch(0.145 0 0);            /* #0a0a0a  nav rail, chat, rails */
  --s-card:      oklch(0.175 0 0);            /* #0e0e0e  cards, session boxes  */
  --s-raised:    oklch(0.212 0 0);            /* #141414  card headers, chips   */
  --s-well:      oklch(0.248 0 0);            /* #1a1a1a  inputs, code wells    */
  --s-hi:        oklch(0.300 0 0);            /* #222222  hover-lifted rows     */

  /* ── FOREGROUND ─────────────────────────────────────────────────── */
  --fg-hi:       oklch(0.945 0 0);            /* #ededed  headings, hero digits */
  --fg:          oklch(0.800 0 0);            /* #c2c2c2  body                  */
  --fg-mut:      oklch(0.620 0 0);            /* #8a8a8a  labels, secondary     */
  --fg-dim:      oklch(0.480 0 0);            /* #616161  disabled, timestamps  */
  --fg-ghost:    oklch(0.380 0 0);            /* #4a4a4a  placeholder, rules    */

  /* ── HAIRLINES = ALPHA OF THE FOREGROUND, never a fixed gray hex ──
     Scales with whatever surface sits under it. Load-bearing recipe.   */
  --line-weak:   oklch(0.945 0 0 / 0.065);
  --line:        oklch(0.945 0 0 / 0.110);
  --line-strong: oklch(0.945 0 0 / 0.180);
  --line-accent: oklch(0.720 0.185 300 / 0.400);

  /* ── TRANSIENT OVERLAYS — one value works on every surface ──────── */
  --ov-hover:    oklch(0.945 0 0 / 0.035);
  --ov-active:   oklch(0.945 0 0 / 0.065);
  --ov-select:   oklch(0.720 0.185 300 / 0.085);

  /* ── THE ONE ACCENT: space-purple, two forms + one glow ─────────── */
  --acc-text:    oklch(0.735 0.185 300);      /* ≈#C27AFF bright form — TEXT, strokes, dots */
  --acc-fill:    oklch(0.410 0.098 299);      /* ≈#553F83 deep form  — FILLS only (Fire btn) */
  --acc-fill-hi: oklch(0.470 0.115 300);      /* ≈#654C99 fill hover                        */
  --acc-fill-lo: oklch(0.355 0.085 298);      /* ≈#48366F fill pressed                      */
  --acc-wash:    oklch(0.735 0.185 300 / 0.10);
  --acc-glow:    oklch(0.735 0.185 300 / 0.28);

  /* ── SEMANTIC (desaturated; pure hues vibrate on near-black) ────── */
  --st-live:     oklch(0.790 0.125 207);      /* ≈#22D3EE cyan — ALIVE only, never actionable */
  --st-pos:      oklch(0.660 0.098 182);      /* ≈#26A69A gain                                */
  --st-neg:      oklch(0.660 0.170 022);      /* ≈#EF5350 loss                                */
  --st-warn:     oklch(0.760 0.140 078);      /* ≈#D9A21B degraded / awaiting                 */
  --st-flat:     oklch(0.590 0 0);            /* ≈#828282 no change                           */
  --st-pos-cvd:  oklch(0.560 0.140 245);      /* ≈#0072B2 colour-blind pairing…               */
  --st-neg-cvd:  oklch(0.740 0.150 070);      /* ≈#E69F00 …swap via [data-cvd] on <html>       */

  /* ── RINGS & SHADOWS — a ring is light catching an edge, not a line ─ */
  --ring:        inset 0 0 0 1px var(--line);
  --ring-weak:   inset 0 0 0 1px var(--line-weak);
  --ring-acc:    inset 0 0 0 1px var(--line-accent);
  --lift-1:      inset 0 0 0 1px var(--line), 0 1px 2px oklch(0 0 0 / 0.40);
  --lift-2:      inset 0 0 0 1px var(--line-strong),
                 0 8px 24px -8px oklch(0 0 0 / 0.70);
  --focus:       0 0 0 1px var(--s-void), 0 0 0 3px oklch(0.735 0.185 300 / 0.55);
  --glow-acc:    0 0 16px -2px var(--acc-glow);

  /* ── RADII — small = engineered. Nothing above 12px except pills. ── */
  --r-xs: 3px; --r-row: 6px; --r-ctl: 8px; --r-panel: 12px; --r-pill: 999px;

  /* ── SPACING (4px grid) ─────────────────────────────────────────── */
  --sp-1: 2px;  --sp-2: 4px;  --sp-3: 6px;  --sp-4: 8px;  --sp-5: 12px;
  --sp-6: 16px; --sp-7: 24px; --sp-8: 32px; --sp-9: 48px; --sp-10: 64px;

  /* ── DENSITY ────────────────────────────────────────────────────── */
  --h-rail: 56px; --h-toolbar: 48px; --w-actions: 344px;
  --row-dense: 28px; --row: 32px; --row-tap: 44px;

  /* ── TYPE SCALE (size / line-height / weight / tracking) ────────── */
  --t-hero:    500 44px/44px var(--font-sans);   /* letter-spacing:-0.025em */
  --t-display: 500 28px/32px var(--font-sans);   /* -0.020em */
  --t-title:   500 17px/24px var(--font-sans);   /* -0.011em */
  --t-card:    500 13px/18px var(--font-sans);   /* -0.006em */
  --t-body:    400 13px/19px var(--font-sans);   /*  0       */
  --t-sub:     400 12px/17px var(--font-sans);   /*  0       */
  --t-label:   500 10px/12px var(--font-sans);   /* +0.085em, uppercase */
  --t-data:    400 12px/16px var(--font-mono);   /* +0.005em */
  --t-data-sm: 400 11px/15px var(--font-mono);   /* +0.010em */

  /* ── MOTION — two classes only: UI FEEDBACK and AMBIENT ─────────── */
  --dur-ui:      150ms;   --ease-ui:    cubic-bezier(0.4, 0, 0.2, 1);
  --dur-enter:   220ms;   --ease-enter: cubic-bezier(0.16, 1, 0.3, 1);
  --dur-exit:    120ms;   --ease-exit:  cubic-bezier(0.4, 0, 1, 1);
  --dur-pulse:  1800ms;   --ease-amb:   cubic-bezier(0.22, 0.61, 0.36, 1);
  --dur-ring:   1600ms;   --ease-travel: linear;
  --dur-breathe:2000ms;   --ease-breathe: cubic-bezier(0.4, 0, 0.6, 1);
}

html[data-cvd="1"] { --st-pos: var(--st-pos-cvd); --st-neg: var(--st-neg-cvd); }

*, *::before, *::after { box-sizing: border-box; }

html, body {
  margin: 0; height: 100%;
  background: var(--s-void);
  color: var(--fg);
  font: var(--t-body);
  -webkit-font-smoothing: antialiased;
  font-variant-numeric: lining-nums tabular-nums slashed-zero;
  font-feature-settings: "tnum" 1, "lnum" 1, "zero" 1, "ss01" 1;
}

/* Every number on screen, everywhere, no exceptions. */
.num, td, .data, input[type="number"] {
  font-variant-numeric: lining-nums tabular-nums slashed-zero;
}

:focus-visible { outline: none; box-shadow: var(--focus); border-radius: var(--r-row); }

@media (prefers-reduced-motion: reduce) {
  :root { --dur-pulse: 5400ms; --dur-ring: 4800ms; --dur-breathe: 6000ms; }
  *, *::before, *::after { transition-duration: 1ms !important; }
}
```

**Page grid (1920×1080, no scroll on the shell):**

```css
.app {
  display: grid;
  grid-template-columns: var(--h-rail) minmax(0, 1fr) var(--w-actions);
  grid-template-rows: var(--h-toolbar) minmax(0, 1fr) auto;
  grid-template-areas: "rail toolbar actions" "rail canvas actions" "rail chat actions";
  height: 100dvh; overflow: hidden; gap: 0;
}
```

---

## 2. COMPONENT RECIPES

### 2.1 Nav rail

```css
.rail {
  grid-area: rail;
  background: var(--s-panel);
  box-shadow: inset -1px 0 0 0 var(--line-weak);
  display: flex; flex-direction: column; align-items: center;
  padding: var(--sp-5) 0; gap: var(--sp-2);
}
.rail__mark { width: 22px; height: 22px; margin-bottom: var(--sp-6);
              color: var(--acc-text); opacity: .9; }
.rail__btn {
  position: relative; width: 40px; height: 40px;
  display: grid; place-items: center;
  border: 0; border-radius: var(--r-ctl);
  background: transparent; color: var(--fg-mut);
  transition: background var(--dur-ui) var(--ease-ui),
              color var(--dur-ui) var(--ease-ui);
}
.rail__btn:hover   { background: var(--ov-hover);  color: var(--fg); }
.rail__btn:active  { background: var(--ov-active); }
.rail__btn[aria-current="page"] { background: var(--ov-select); color: var(--fg-hi); }
.rail__btn[aria-current="page"]::before {
  content: ""; position: absolute; left: -8px; top: 11px;
  width: 2px; height: 18px; border-radius: var(--r-pill);
  background: var(--acc-text); box-shadow: var(--glow-acc);
}
.rail__btn svg { width: 17px; height: 17px; stroke-width: 1.6; }
.rail__spacer { flex: 1; }
.rail__rule { width: 20px; height: 1px; background: var(--line-weak); margin: var(--sp-3) 0; }
```

*WHY:* the accent appears as a 2px lit bar, not a filled tile — the rail reads as chrome and the purple stays scarce enough to still mean something on the Fire button.

### 2.2 View toolbar

```css
.toolbar {
  grid-area: toolbar; display: flex; align-items: center; gap: var(--sp-5);
  padding: 0 var(--sp-6); background: var(--s-void);
  box-shadow: inset 0 -1px 0 0 var(--line-weak);
}
.toolbar__title { font: var(--t-title); letter-spacing: -0.011em; color: var(--fg-hi); }
.toolbar__crumb { font: var(--t-sub); color: var(--fg-dim); }
.toolbar__crumb::before { content: "/"; margin: 0 var(--sp-3); color: var(--fg-ghost); }

.seg { display: flex; padding: 2px; gap: 2px;
       background: var(--s-card); border-radius: var(--r-ctl); box-shadow: var(--ring-weak); }
.seg__btn {
  height: 26px; padding: 0 10px; border: 0; border-radius: var(--r-row);
  background: transparent; color: var(--fg-mut);
  font: var(--t-card); letter-spacing: -0.006em;
  transition: all var(--dur-ui) var(--ease-ui);
}
.seg__btn:hover { color: var(--fg); background: var(--ov-hover); }
.seg__btn[aria-pressed="true"] { background: var(--s-hi); color: var(--fg-hi); box-shadow: var(--ring-weak); }

.stat { display: flex; align-items: baseline; gap: var(--sp-2); }
.stat__k { font: var(--t-label); letter-spacing: .085em; text-transform: uppercase; color: var(--fg-dim); }
.stat__v { font: var(--t-data); color: var(--fg-hi); }
.stat__v[data-sign="pos"] { color: var(--st-pos); }
.stat__v[data-sign="neg"] { color: var(--st-neg); }
.toolbar__spacer { margin-left: auto; }
```

*WHY:* the toolbar sits on `--s-void` (darker than the panels it borders), so the whole center column reads as a recessed well the canvas lives inside.

### 2.3 Session box — hand-rolled SVG

Boxes are `<g>` groups inside one root `<svg>` with `overflow:visible`. Ports at left/right vertical centre.

```html
<g class="node" data-state="running" transform="translate(320,180)">
  <rect class="node__body" x="0" y="0" width="248" height="104" rx="6"/>
  <path  class="node__head" d="M0,6 A6,6 0 0 1 6,0 H242 A6,6 0 0 1 248,6 V34 H0 Z"/>
  <line  class="node__rule" x1="0" y1="34" x2="248" y2="34"/>
  <rect  class="node__ring" x=".5" y=".5" width="247" height="103" rx="5.5"/>
  <text class="node__title"  x="12" y="22">safe-2 · heartbeat</text>
  <text class="node__meta"   x="12" y="56">PA3POKNV46VG</text>
  <text class="node__metric" x="236" y="56" text-anchor="end">+$142.10</text>
  <text class="node__label"  x="12" y="88">TOKENS</text>
  <text class="node__data"   x="236" y="88" text-anchor="end">38.2K / 200K</text>
</g>
```

```css
.node__body { fill: var(--s-card); }
.node__head { fill: var(--s-raised); }
.node__rule { stroke: var(--line-weak); stroke-width: 1; }
.node__ring { fill: none; stroke: var(--line); stroke-width: 1; }
.node__title{ font: var(--t-card); letter-spacing: -0.006em; fill: var(--fg-hi); }
.node__meta { font: var(--t-data-sm); fill: var(--fg-dim); }
.node__metric{font: var(--t-data);   fill: var(--fg); }
.node__label{ font: var(--t-label); letter-spacing: .085em; fill: var(--fg-ghost); }
.node__data { font: var(--t-data-sm); fill: var(--fg-mut); }

.node { cursor: pointer; transition: transform var(--dur-ui) var(--ease-ui); }
.node:hover .node__body { fill: var(--s-raised); }
.node:hover .node__ring { stroke: var(--line-strong); }

.node[data-state="running"] .node__ring  { stroke: var(--line-accent); }
.node[data-state="running"] .node__metric{ fill: var(--acc-text); }
.node[data-state="done"]    { opacity: .62; }          /* done DIMS. never green. */
.node[data-state="idle"]    { opacity: .45; }
.node[data-state="idle"] .node__ring { stroke-dasharray: 4 5; }
.node[data-state="error"] .node__ring   { stroke: var(--st-neg); }
.node[data-state="error"] .node__metric { fill: var(--st-neg); }
.node[data-selected] .node__ring { stroke: var(--acc-text); stroke-width: 1.5; }
.node[data-selected] .node__body { fill: var(--s-raised); }
```

*WHY:* a distinctly-toned header band separated by a hairline reads as "title bar + payload" across a whole canvas of boxes, and finished sessions dim rather than turning green so the one thing still moving is the only bright thing.

**Canvas + the contained bloom (this replaces the page-wide aurora):**

```css
.canvas { grid-area: canvas; position: relative; background: var(--s-canvas); overflow: hidden; }
.canvas::before {                       /* ONE bloom. Behind the graph. Nowhere else. */
  content: ""; position: absolute; inset: -20%;
  background: radial-gradient(52% 44% at 50% 42%,
              oklch(0.735 0.185 300 / 0.055) 0%,
              oklch(0.735 0.185 300 / 0.018) 44%,
              transparent 72%);
  pointer-events: none;
}
.canvas::after {                        /* 24px dot grid, sub-perceptual */
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background-image: radial-gradient(circle at 1px 1px, var(--line-weak) 1px, transparent 0);
  background-size: 24px 24px;
  mask-image: radial-gradient(70% 60% at 50% 45%, #000 0%, transparent 100%);
}
```

### 2.4 Orchestrator hero

The centre node. Same skeleton, larger, plus a slow ambient ring — the only element on the page allowed a glow.

```css
.hero__body { fill: var(--s-raised); }
.hero__ring { fill: none; stroke: var(--line-accent); stroke-width: 1; }
.hero__aura { fill: none; stroke: var(--acc-text); stroke-width: 1;
              transform-box: fill-box; transform-origin: center;
              animation: hero-breathe 4s var(--ease-amb) infinite; }
@keyframes hero-breathe {
  0%   { opacity: .32; transform: scale(1); }
  60%  { opacity: .04; transform: scale(1.045); }
  100% { opacity: 0;   transform: scale(1.06); }
}
.hero__num   { font: var(--t-hero); letter-spacing: -0.025em; fill: var(--fg-hi); }
.hero__unit  { font: var(--t-sub);  fill: var(--fg-dim); opacity: .55; }
.hero__label { font: var(--t-label); letter-spacing: .085em; fill: var(--fg-mut); }
```

*WHY:* one 44px/weight-500 tabular hero number with a de-emphasised unit reads as authoritative without shouting; weight 600+ is held in reserve for a kill-switch state so it still means something when it fires.

### 2.5 Worker dots

Under each session box, a row of 8px dots — one per worker. Live workers get an expanding ring; nothing else does.

```html
<g class="dots" transform="translate(12, 96)">
  <circle class="dot" data-state="live"  cx="0"  cy="0" r="4"/>
  <circle class="dot" data-state="done"  cx="14" cy="0" r="4"/>
  <circle class="dot" data-state="idle"  cx="28" cy="0" r="4"/>
</g>
```

```css
.dot { fill: var(--fg-ghost); transition: fill var(--dur-ui) var(--ease-ui); }
.dot[data-state="done"]  { fill: var(--fg-dim); }
.dot[data-state="error"] { fill: var(--st-neg); }
.dot[data-state="live"]  { fill: var(--st-live); }
.dot[data-state="live"] + .dot__ring { display: block; }

.dot__ring { display: none; fill: none; stroke: var(--st-live); stroke-width: 1;
             transform-box: fill-box; transform-origin: center;
             animation: dot-pulse var(--dur-ring) var(--ease-amb) infinite; }
@keyframes dot-pulse {
  0%   { opacity: .70; transform: scale(1); }
  70%  { opacity: .12; transform: scale(2.8); }
  100% { opacity: 0;   transform: scale(3); }
}
```

*WHY:* "alive" gets its own hue (cyan) so purple never has to mean both *actionable* and *running* — and only `transform`/`opacity` animate, so 40 dots cost nothing on the main thread.

### 2.6 Message pulse (edge + travelling dot)

Bezier control points at the horizontal midpoint. Reuse the identical `d` string on both the path and the `animateMotion`.

```html
<defs>
  <filter id="pulseGlow" x="-200%" y="-200%" width="500%" height="500%">
    <feGaussianBlur stdDeviation="2.4" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
</defs>

<!-- idle wire: exists, carries no traffic -->
<path class="edge" d="M 568,232 C 700,232 700,410 832,410"/>

<!-- active wire + travelling pulse -->
<path class="edge" data-active d="M 568,232 C 700,232 700,410 832,410"/>
<circle class="pulse" r="3" filter="url(#pulseGlow)">
  <animateMotion dur="1.8s" repeatCount="indefinite" calcMode="linear"
                 path="M 568,232 C 700,232 700,410 832,410"/>
</circle>
```

```css
.edge { fill: none; stroke: var(--line); stroke-width: 1; stroke-dasharray: 4 6; opacity: .55; }
.edge[data-active] { stroke: var(--line-accent); stroke-dasharray: none; opacity: 1; }
.pulse { fill: var(--acc-text); }
/* burst arrival: fire on animationend / a JS timer at the far port */
.port--recv[data-hit] { animation: port-hit 320ms var(--ease-enter); }
@keyframes port-hit {
  from { r: 3; fill: var(--acc-text); opacity: 1; }
  to   { r: 7; fill: var(--acc-text); opacity: 0; }
}
```

`animateMotion` at `1.8s linear` is deliberately **not** the UI curve — travelling pulses are ambient motion, not interaction feedback, and must never share `--ease-ui`. Dashed-static vs solid-animated gives idle-wire / live-wire for free with no extra markup.

### 2.7 Action card — rail form

```css
.actions { grid-area: actions; background: var(--s-panel);
           box-shadow: inset 1px 0 0 0 var(--line-weak);
           display: flex; flex-direction: column; overflow: hidden; }
.actions__head { height: var(--h-toolbar); display: flex; align-items: center;
                 gap: var(--sp-3); padding: 0 var(--sp-5);
                 box-shadow: inset 0 -1px 0 0 var(--line-weak); }
.actions__list { flex: 1; overflow-y: auto; padding: var(--sp-4); display: grid; gap: var(--sp-3); }

.card {
  position: relative; padding: var(--sp-5);
  background: var(--s-card); border: 0; border-radius: var(--r-ctl);
  box-shadow: var(--ring-weak); text-align: left; width: 100%;
  transition: background var(--dur-ui) var(--ease-ui),
              box-shadow var(--dur-ui) var(--ease-ui),
              transform  var(--dur-ui) var(--ease-ui);
}
.card:hover  { background: var(--s-raised); box-shadow: var(--ring); }
.card:active { background: var(--s-well);  transform: translateY(1px); }

.card__top   { display: flex; align-items: center; gap: var(--sp-3); margin-bottom: var(--sp-3); }
.card__rank  { font: var(--t-data-sm); color: var(--fg-ghost); min-width: 16px; }
.card__title { font: var(--t-card); letter-spacing: -0.006em; color: var(--fg-hi);
               overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card__body  { font: var(--t-sub); color: var(--fg-mut);
               display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card__foot  { display: flex; align-items: center; gap: var(--sp-4);
               margin-top: var(--sp-4); padding-top: var(--sp-3);
               box-shadow: inset 0 1px 0 0 var(--line-weak); }

.chip { display: inline-flex; align-items: center; gap: var(--sp-2);
        height: 20px; padding: 0 var(--sp-3); border-radius: var(--r-pill);
        background: var(--ov-active); box-shadow: var(--ring-weak);
        font: var(--t-label); letter-spacing: .085em; text-transform: uppercase; color: var(--fg-mut); }
.chip[data-tone="run"]  { color: var(--st-live);  animation: breathe var(--dur-breathe) var(--ease-breathe) infinite; }
.chip[data-tone="warn"] { color: var(--st-warn); }
.chip[data-tone="err"]  { color: var(--st-neg); }
.chip[data-tone="ok"]   { color: var(--fg-mut); }   /* done is quiet, not green */
@keyframes breathe { 0%,100% { opacity: 1 } 50% { opacity: .5 } }

.card__score { margin-left: auto; font: var(--t-data); color: var(--fg); }
```

*WHY:* one white-alpha step for hover and a second for pressed works identically over every surface, so hover feedback never needs per-surface tuning.

### 2.8 Action card — promoted form

The single top-ranked card. The **only** card allowed a drop shadow and an accent edge.

```css
.card--promoted {
  background: var(--s-raised);
  box-shadow: var(--lift-2), inset 0 0 0 1px var(--line-accent);
  padding: var(--sp-6);
  margin-bottom: var(--sp-4);
}
.card--promoted::before {                 /* lit top edge */
  content: ""; position: absolute; inset: 0 12px auto 12px; height: 1px;
  background: linear-gradient(90deg, transparent, var(--acc-text), transparent);
  opacity: .55;
}
.card--promoted .card__title { font: var(--t-title); letter-spacing: -0.011em; }
.card--promoted .card__body  { -webkit-line-clamp: 3; color: var(--fg); }
```

*WHY:* elevation is earned once per screen — if every card lifts, none do.

### 2.9 Fire button — full state machine

Two-step by design: `idle → armed (2.5s) → firing → done`. Reverts on blur or timeout.

```css
.fire {
  position: relative; height: 34px; padding: 0 var(--sp-6);
  border: 0; border-radius: var(--r-ctl);
  background: var(--acc-fill); color: var(--fg-hi);
  box-shadow: inset 0 1px 0 0 oklch(1 0 0 / 0.10), inset 0 0 0 1px var(--line-accent);
  font: var(--t-card); letter-spacing: -0.006em;
  transition: background var(--dur-ui) var(--ease-ui),
              box-shadow var(--dur-ui) var(--ease-ui),
              transform  var(--dur-ui) var(--ease-ui);
}
.fire:hover  { background: var(--acc-fill-hi); box-shadow: inset 0 1px 0 0 oklch(1 0 0 / .12),
               inset 0 0 0 1px var(--line-accent), var(--glow-acc); }
.fire:active { background: var(--acc-fill-lo); transform: translateY(1px); }

.fire[data-state="armed"] {
  background: var(--acc-fill-hi); color: #fff;
  box-shadow: inset 0 0 0 1px var(--acc-text), var(--glow-acc);
}
.fire[data-state="armed"]::after {          /* 2.5s disarm countdown hairline */
  content: ""; position: absolute; left: 0; bottom: 0; height: 2px;
  background: var(--acc-text); border-radius: 0 0 var(--r-ctl) var(--r-ctl);
  animation: disarm 2500ms linear forwards;
}
@keyframes disarm { from { width: 100% } to { width: 0 } }

.fire[data-state="firing"] { pointer-events: none; color: oklch(0.945 0 0 / .7); }
.fire[data-state="firing"]::before {
  content: ""; position: absolute; inset: 0; border-radius: inherit;
  background: linear-gradient(90deg, transparent, oklch(1 0 0 / .10), transparent);
  background-size: 220% 100%;
  animation: sweep 1.1s var(--ease-travel) infinite;
}
@keyframes sweep { from { background-position: 120% 0 } to { background-position: -20% 0 } }

.fire[disabled] {
  background: var(--s-well); color: var(--fg-dim);
  box-shadow: var(--ring-weak); cursor: not-allowed;
}
```

*WHY:* this is the only deep-fill purple surface in the entire cockpit — its rarity is what makes it read as *the* consequential control, and the countdown hairline turns a modal confirm into an inline one.

### 2.10 Chat pane + turns + streaming

Flat rows with an accent rail, **no bubbles** — bubbles are consumer chat, rails are a log.

```css
.chat { grid-area: chat; height: 292px; display: flex; flex-direction: column;
        background: var(--s-panel); box-shadow: inset 0 1px 0 0 var(--line-weak); }
.chat__scroll { flex: 1; overflow-y: auto; padding: var(--sp-5) var(--sp-6); display: grid; gap: var(--sp-5); }

.turn { display: grid; grid-template-columns: 2px 1fr; gap: var(--sp-5); }
.turn__rail { border-radius: var(--r-pill); background: var(--line-weak); }
.turn[data-who="user"]   .turn__rail { background: var(--acc-text); opacity: .8; }
.turn[data-who="gamma"]  .turn__rail { background: var(--line); }
.turn[data-who="system"] .turn__rail { background: var(--st-warn); opacity: .5; }

.turn__who  { font: var(--t-label); letter-spacing: .085em; text-transform: uppercase;
              color: var(--fg-dim); margin-bottom: var(--sp-2); }
.turn__body { font: var(--t-body); color: var(--fg); }
.turn__body code, .turn__pre {
  font: var(--t-data); background: var(--s-well); color: var(--fg-hi);
  border-radius: var(--r-xs); padding: 1px 5px; box-shadow: var(--ring-weak);
}
.turn__pre { display: block; padding: var(--sp-4); border-radius: var(--r-row);
             white-space: pre-wrap; max-height: 168px; overflow: auto; }
.turn__time { font: var(--t-data-sm); color: var(--fg-ghost); }

/* STREAMING: sweeping mask on the text itself. No spinner anywhere. */
.streaming {
  color: transparent;
  background-image:
    linear-gradient(var(--fg-mut), var(--fg-mut)),
    linear-gradient(90deg, transparent calc(50% - 44px), var(--fg-hi), transparent calc(50% + 44px));
  background-size: 100% 100%, 240% 100%;
  background-repeat: no-repeat, no-repeat;
  background-position: 0 0, 120% center;
  -webkit-background-clip: text; background-clip: text;
  animation: shimmer 1600ms var(--ease-travel) infinite;
}
@keyframes shimmer { to { background-position: 0 0, -20% center; } }

.caret { display: inline-block; width: 7px; height: 14px; margin-left: 2px;
         vertical-align: -2px; background: var(--fg-hi);
         animation: breathe var(--dur-breathe) var(--ease-breathe) infinite; }

.composer { display: flex; gap: var(--sp-4); align-items: flex-end;
            padding: var(--sp-4) var(--sp-6) var(--sp-5);
            box-shadow: inset 0 1px 0 0 var(--line-weak); }
.composer__input {
  flex: 1; min-height: 38px; max-height: 120px; resize: none;
  padding: var(--sp-4) var(--sp-5);
  background: var(--s-card); border: 0; border-radius: var(--r-ctl);
  box-shadow: var(--ring-weak); color: var(--fg-hi); font: var(--t-body);
  transition: box-shadow var(--dur-ui) var(--ease-ui), background var(--dur-ui) var(--ease-ui);
}
.composer__input::placeholder { color: var(--fg-ghost); }
.composer__input:focus { background: var(--s-raised); box-shadow: var(--ring), var(--focus); outline: none; }
```

*WHY:* a text-mask shimmer scales to long streaming paragraphs without a bouncing icon, and a *breathing* caret (opacity 1↔0.5) reads as "generating" where a hard 1s blink reads as "waiting for input" — the wrong signal.

### 2.11 Context gauge

Segmented bar + tabular readout. Neutral until it actually matters.

```html
<div class="gauge" data-pct="61">
  <div class="gauge__bar"><i class="gauge__fill" style="width:61%"></i></div>
  <span class="gauge__read"><b>122.4K</b><span class="gauge__unit"> / 200K</span></span>
</div>
```

```css
.gauge { display: flex; align-items: center; gap: var(--sp-4); }
.gauge__bar { position: relative; width: 96px; height: 4px; border-radius: var(--r-pill);
              background: var(--s-well); overflow: hidden; }
.gauge__bar::after {                      /* 25/50/75 ticks */
  content: ""; position: absolute; inset: 0;
  background: repeating-linear-gradient(90deg,
    transparent 0 23px, var(--line-weak) 23px 24px);
}
.gauge__fill { display: block; height: 100%; border-radius: var(--r-pill);
               background: var(--fg-dim);
               transition: width 400ms var(--ease-enter), background var(--dur-ui) var(--ease-ui); }
.gauge[data-tone="warn"] .gauge__fill { background: var(--st-warn); }
.gauge[data-tone="crit"] .gauge__fill { background: var(--st-neg); }
.gauge[data-tone="crit"] .gauge__read b { color: var(--st-neg); font-weight: 600; }
.gauge__read { font: var(--t-data); color: var(--fg-mut); }
.gauge__read b { color: var(--fg-hi); font-weight: 400; }
.gauge__unit  { opacity: .5; }
```

Set `data-tone` in JS: `>= 88 → crit`, `>= 70 → warn`, else none.

*WHY:* the unit is de-emphasised and the digits are tabular so the readout never reflows as it ticks; weight 600 appears only at crit, which is what makes it register.

### 2.12 Empty states

```css
.empty {
  display: grid; place-items: center; gap: var(--sp-4);
  min-height: 160px; padding: var(--sp-8) var(--sp-6);
  border-radius: var(--r-panel);
  box-shadow: inset 0 0 0 1px var(--line-weak);
  background: transparent;
  text-align: center;
}
.empty__icon  { width: 20px; height: 20px; color: var(--fg-ghost); stroke-width: 1.4; }
.empty__title { font: var(--t-card); color: var(--fg-mut); }
.empty__hint  { font: var(--t-sub); color: var(--fg-ghost); max-width: 30ch; }
.empty__hint kbd { font: var(--t-data-sm); background: var(--s-well); color: var(--fg-mut);
                   padding: 1px 5px; border-radius: var(--r-xs); box-shadow: var(--ring-weak); }
```

Copy rule: state what will appear here and the one keystroke that fills it — no illustrations, no exclamation marks.

*WHY:* a hairline-only container with no fill keeps empty regions visually recessive; a filled empty card competes with real cards for attention.

### 2.13 Toasts

```css
.toasts { position: fixed; right: calc(var(--w-actions) + var(--sp-6)); bottom: var(--sp-6);
          display: grid; gap: var(--sp-3); width: 320px; z-index: 60; }
.toast {
  position: relative; overflow: hidden;
  padding: var(--sp-5) var(--sp-5) var(--sp-5) var(--sp-6);
  background: var(--s-raised); border-radius: var(--r-ctl);
  box-shadow: var(--lift-2);
  animation: toast-in var(--dur-enter) var(--ease-enter);
}
.toast[data-leaving] { animation: toast-out var(--dur-exit) var(--ease-exit) forwards; }
@keyframes toast-in  { from { opacity: 0; transform: translateY(8px) scale(.98) } }
@keyframes toast-out { to   { opacity: 0; transform: translateY(4px) } }

.toast::before { content: ""; position: absolute; left: 0; top: 10px; bottom: 10px;
                 width: 2px; border-radius: var(--r-pill); background: var(--fg-ghost); }
.toast[data-tone="ok"]::before   { background: var(--st-pos); }
.toast[data-tone="err"]::before  { background: var(--st-neg); }
.toast[data-tone="warn"]::before { background: var(--st-warn); }
.toast[data-tone="fire"]::before { background: var(--acc-text); }

.toast__title { font: var(--t-card); color: var(--fg-hi); }
.toast__body  { font: var(--t-sub);  color: var(--fg-mut); margin-top: var(--sp-2); }
.toast__life  { position: absolute; left: 0; bottom: 0; height: 1px;
                background: var(--line-strong); animation: disarm 6000ms linear forwards; }
```

*WHY:* toasts are the only floating layer, so they get the only real drop shadow — that alone separates them from the flat plane without any other treatment.

---

## 3. THE FIVE MOVES

Ranked by visual yield against the described current state (aurora background, hairline cards, deep violet fill buttons).

1. **Kill the page-wide aurora; contain the bloom.** *Before:* purple haze washes across the whole page, so every "neutral" gray is faintly violet and the accent has nothing to pop against. *After:* one radial bloom at 5.5% alpha lives inside `.canvas::before` only, every gray in the ramp is `C = 0`, and the purple reads as light emitted by the graph rather than a tint applied to the app.

2. **Cards get lighter than the canvas, and every border becomes a foreground-alpha ring.** *Before:* cards sit at the same value as the page and rely on a fixed-hex border to separate — the single most reliable tell of a generated dark UI. *After:* `--s-void 0.085 → --s-canvas 0.115 → --s-card 0.175 → --s-raised 0.212` does the elevation work with zero shadows, and `inset 0 0 0 1px oklch(0.945 0 0 / .11)` replaces every `border` so edges scale coherently across nested surfaces.

3. **Demote purple from decoration to signal; give "alive" its own hue.** *Before:* deep violet fills every button, so the Fire button looks like the segmented toolbar looks like the nav. *After:* `--acc-fill` appears on exactly one element (Fire), `--acc-text` on active nodes / pulses / focus rings, and cyan `--st-live` takes over every "is running" cue — so purple consistently means *you can act on this* and never has to also mean *this is breathing*.

4. **Numeric typography pass across every digit on screen.** *Before:* proportional digits jitter columns on every tick and hero numbers are bolded to 700, so routine P&L reads as an alarm. *After:* `font-variant-numeric: lining-nums tabular-nums slashed-zero` globally, hero numbers at weight 500 with the unit at 55% opacity and 0.7em, and weight 600 reserved so the kill-switch state is the only thing on the page that shouts.

5. **Collapse motion to two classes.** *Before:* mixed ad-hoc durations and default `ease` make interactions feel unrelated to each other. *After:* everything interactive is `150ms cubic-bezier(0.4,0,0.2,1)` with no exceptions, and a separate **ambient** class — `1.8s linear` travelling pulses, `1.6s cubic-bezier(0.22,0.61,0.36,1)` status rings, `2s` breathing — is used *only* for things the machine is doing on its own, so the eye learns instantly which motion is a response to it and which is the rig running.

---

## 4. ANTI-PATTERNS — remove or refuse

**Colour**
- **A half-tinted gray ramp.** Grays that are *slightly* purple but not clearly so read as a colour bug. If any neutral in the shipped file has non-zero chroma, it is a defect — this is the specific failure mode an aurora background creates downstream.
- **Pure `#000` + pure `#fff`.** Canvas floors at `oklch(0.085 0 0)`, text ceilings at `oklch(0.945 0 0)`. The maximum-contrast pairing halates on OLED and reads dated.
- **Saturated status hues** (`#00ff00`, `#ff0000`, a light-mode brand purple like `#A020F0`). Every semantic colour here is pulled down in chroma and up slightly in lightness. A saturated purple on near-black reads neon, not premium.
- **Green for "complete."** Finished sessions and finished steps **dim** (`opacity .62`, `--fg-dim`). Colour is spent on what is running or what broke. A canvas of green boxes hides the one box that matters.
- **The accent as decoration** — background tints, dividers, icon colour, section headers. Every non-functional purple burns the signal the Fire button depends on.

**Surface**
- **Fixed mid-gray hex borders** (`#2a2a2a`, `#333`) as the separator technique. Alpha-of-foreground only.
- **Drop shadows for elevation on cards.** Shadow blur goes muddy on near-black. Only two elements carry a real shadow: the promoted action card and toasts.
- **Card background equal to canvas background.** If a card needs its border to be visible as a card, the elevation is wrong.
- **Radii above 12px** on anything but pills. 16–24px reads consumer app; 6/8/12 reads instrument.

**Motion**
- **Spinners as the primary "still working" cue** on inline text. The shimmer mask replaces them entirely.
- **Hard on/off caret blink** (`step-end`, 1s). That is a shell prompt waiting for input, not a model generating.
- **Sharing `--ease-ui` with ambient motion.** Travelling pulses, status rings and breathing chips must never use the interaction curve, or the user starts reading the rig's own activity as feedback to their clicks.
- **Ad-hoc durations.** If a transition duration in the file is not one of the five motion tokens, it is a bug.

**Type & density**
- **Proportional digits** anywhere a value updates live.
- **Weight 700 on routine numbers.** Reserved for kill-switch / catastrophic states only.
- **Variable-font weights (360/420/480).** Unbuildable under the system-font constraint — do not write them into the file and hope; they silently snap to 400.
- **Rows below 28px** for anything not monospace, and interactive rows without ≥44px of padded tap area even when the visible row is 28–32px.

**Scope**
- Refuse any CDN link, `@font-face`, `@import` of a remote stylesheet, or framework import. The spec above is complete in vanilla CSS/JS/SVG; if a recipe seems to need a library, the recipe is wrong.
---

## Ratified recipes — 2026-08-30 deep-research pass (provenance attached)

Two Sonnet crawls (production design systems + Claude design-skill repos) audited this spec
against the field. Read this section before any restyle: it separates what is VALIDATED
(change needs new evidence) from what was ADDED (revert = git revert).

**Validated by independent convergence — do not relitigate without new evidence:**
- Zero-chroma OKLCH surface ramp: Vercel Geist ships `oklch(0.027/0.205 0 0)`, Midday
  (funded finance SaaS) ships HSL 5%/7%/11%L — three unrelated systems, same strategy.
- Alpha-of-foreground hairlines: Vercel (`gray-alpha-300/400/700`) and Grafana
  (`rgba(204,204,220,.12/.20/.30)`) both do borders as alpha, never flat hex.
- Same-hue radial glow (`0 0 Npx` no offset, accent at 20-35% alpha) over drop shadows:
  Resend's entire elevation model. Our deep-fill buttons already carry it.
- No backdrop-filter / no glassmorphism blur: banned independently by nothing-design-skill
  (2.8K★) and ibelick/ui-skills baseline-ui.
- tabular-nums on live numerals, grain layer, one-accent-per-view: all field-standard.

**Added this pass (all in the generators, `git revert` to undo):**
- SEGMENTED context meters (army tiles): 14 square-ended blocks, 3px gaps, rx 1 —
  discrete blocks read as an instrument with a resolution; a continuous bar reads as
  loading. Source: nothing-design-skill's signature data-viz.
- Card ambient light-bleed: trailing `inset 0 -20px 70px -24px rgba(255,255,255,.055)`
  on `.card` (magicui bento recipe at lower alpha). SVG tiles: cardGrad top stop .035→.05.

**Ratified rules for FUTURE work (not yet wired anywhere):**
- P&L color: never traffic-light saturation. Split fill vs text variants —
  `--pnl-pos-fill oklch(62% .16 155)` / `--pnl-pos-text oklch(78% .18 155)`,
  `--pnl-neg-fill oklch(58% .20 25)` / `--pnl-neg-text oklch(72% .22 25)`.
  Grafana, TradingView convention and Linear's blog all split solid vs on-dark-text.
- Hover/selected = exactly ONE step up the same luminance scale, never a jump to accent
  (Vercel Geist state convention). If hover states multiply, add a separate control
  ladder (`--ctl-idle/hover/active`, Trigger.dev pattern) instead of reusing bg tokens.
- Status pills: solid hue for dot+text, same hue at 15% alpha for the pill fill
  (Raycast). Scales to N statuses with zero new tokens.
- One pattern-break per screen (the featured bento tile is ours). A second break is chaos.

**21st.dev CLI** (J sent /mcp link 2026-08-30): search needs login. After a one-time
`npx -y @21st-dev/cli@latest login` (browser, J-only), any session can pull real
component code loginless-ly via the saved token: `npx 21st search/get/theme`.

**Third crawl (Anthropic frontend-design + Wondelai top-design/refactoring-ui) deltas:**
- `--pos`/`--neg` audited compliant (desaturated OKLCH, never traffic-light) — no change.
- `text-wrap:balance` on h1-h3 (applied). `::selection` tint already present.
- Hierarchy LEVER rule (recorded): a value emphasizes via ONE of size/weight/color;
  stacking all three is reserved for the single hero number per view.
- Multi-series rule (recorded): blue+orange for 2 simultaneous series
  (deuteranopia-safe); red/green are reserved for P&L sign, NEVER series identity.
