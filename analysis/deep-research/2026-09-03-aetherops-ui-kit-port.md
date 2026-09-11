# AetherOps UI-kit port — 21st.dev crawl → vanilla components

**Date:** 2026-09-03 · **Scope:** research/porting subagent, no repo edits — output lives entirely under `setup/scripts/vendor/ui-kit/` (new) and this file.

## Ask

J's reference: "AetherOps — AI Workflow Command Center", a dark navy dashboard with
KPI cards, a Sankey-style "Workflow routing map" centerpiece, an approval queue,
a cost-pulse area chart, agent-health rings, and a system-alerts panel — J's words:
*"its still just like basic ass text boxes dude ... crawl around these sites, get
everything from these sites do not just use basic ass shit."* Target: components
must be vanilla HTML+CSS(+JS) — no React, no Tailwind build, no runtime CDN —
because the cockpit is a single self-contained HTML file built by a Python script
(`gamma_cockpit_ui.py`, confirmed via `setup/scripts/vendor/MANIFEST.md`'s "nothing
here is loaded from a CDN at render or runtime" hard rule).

## What was crawled

1. `21st.dev/community/components/featured` — 48 featured components enumerated
   (name/author/URL). Most are React+Tailwind marketing blocks (SaaS templates,
   sign-in pages, footers) — not relevant to a dashboard cockpit.
2. Individual 21st.dev component pages for the visually relevant subset (dot
   patterns, gradient backgrounds, bento grids, area charts, meter/leaderboard
   cards). **Finding:** WebFetch only ever returns the page's `Usage.tsx` demo
   wrapper (an import + a one-line render call) — the actual `Component.tsx`
   implementation is fetched client-side by 21st.dev's own JS and never lands in
   the static HTML WebFetch converts to markdown. License badges DO render
   server-side and were captured where present (recorded per-item in the
   MANIFEST's "not ported" table).
3. Several 21st.dev pages that showed a real component (not a demo wrapper)
   turned out to be re-embeds of **Magic UI** (`magicuidesign/magicui`) —
   dillionverma is both a 21st.dev contributor and Magic UI's author, and the
   Dot Pattern / Number Ticker pages explicitly point at
   `magicui.design/docs/components/...`. Pivoted the crawl there.
4. `magicui.design/docs/components/*` — same problem: docs pages also only show
   a usage snippet, not the registry source, and state no explicit license on
   the page itself (just "source available on GitHub").
5. **Went straight to the GitHub repo** via `gh api` (read-only, no browser
   needed, no client-side JS gate): `magicuidesign/magicui`, commit `2d671cc6c0e0`.
   - `LICENSE.md` at repo root: plain **MIT**, copyright "Magic UI" — read
     verbatim, not inferred.
   - `apps/www/registry/magicui/*.tsx` — 74 component source files, all real
     implementations (not demos). Downloaded the 17 visually relevant ones in
     full (border-beam, shimmer-button, number-ticker, marquee, dot-pattern,
     magic-card, animated-grid-pattern, meteors, shine-border,
     animated-circular-progress-bar, bento-grid, ripple, rainbow-button,
     pulsating-button, animated-shiny-text, animated-beam, grid-pattern) into
     the scratchpad, read each, then hand-ported the CSS/SVG/animation
     *technique* to vanilla (Tailwind classes and `motion/react` calls have no
     vanilla equivalent to copy — the recipe is the thing being ported, not the
     JSX).
6. `uiverse.io` — searched (WebSearch, not a page crawl) for glow-card / status-
   badge components as a second MIT source per the brief. No specific component
   page came back with usable code in the search snippet; not pursued further
   given the MagicUI set already covered every visual element in the reference
   image. Flagged as a gap below rather than padding the deliverable with an
   under-verified port.

## Result

**16 ported recipes**, all traced to a real, license-confirmed (MIT) upstream
file, written to:

- [`setup/scripts/vendor/ui-kit/aetherops-ui-kit.css`](../../setup/scripts/vendor/ui-kit/aetherops-ui-kit.css) — 23,507 B
- [`setup/scripts/vendor/ui-kit/aetherops-ui-kit.js`](../../setup/scripts/vendor/ui-kit/aetherops-ui-kit.js) — 9,392 B
- [`setup/scripts/vendor/ui-kit/MANIFEST.md`](../../setup/scripts/vendor/ui-kit/MANIFEST.md) — full provenance table + the "not ported" list

Each CSS block carries an inline comment citing: the 21st.dev discovery page,
the exact GitHub source file it was read from, the license, what technique was
kept vs. dropped (mostly: `motion/react` spring/tween → CSS `transition`/
`@keyframes`, or a ~15-line vanilla-JS rAF loop where real per-frame JS state
was unavoidable — number-ticker, spotlight-card mouse tracking, progress-ring
math, ripple/meteor DOM generation, flow-ribbon path building), and which
cockpit element it becomes.

Direct hits against J's reference image:

| Reference element | Recipe(s) |
|---|---|
| Header gradient CTA (indigo→violet) | `uk-shimmer-btn` |
| KPI stat cards, big numbers | `uk-bento-grid`/`uk-bento-card` (layout) + `uk-number-ticker` (the numeral) + `uk-spotlight-card` (hover glow) |
| Workflow routing map — glowing gradient tubes between node bars | `uk-flow-ribbon` (ribbon + % label chip) + `uk-flow-node` (the bars) |
| Dotted-matrix decoration (left of the flow map) | `uk-dot-pattern` |
| "Live" chip | `uk-shine-border` + `uk-shiny-text` |
| Approval queue rows | `uk-spotlight-card` |
| Agent health rows (% + Healthy chip) | `uk-progress-ring` |
| System alerts / ticker rows | `uk-marquee` |
| "Deploy smarter" promo CTA | `uk-pulse-btn` / `uk-rainbow-btn` |
| Premium ambient glow behind the centerpiece | `uk-meteors`, `uk-ripple`, `uk-animated-grid`, `uk-border-beam` |

**Not covered by a real port:** the "Cost pulse" area-chart-with-gradient-fill.
21st.dev's `reaviz/area-chart-1` page stated no license and gated its code
client-side, so nothing was copied from it. An SVG area chart with a violet
gradient fill + highlighted-point tooltip is a generic, uncopyrightable
charting technique (path + linearGradient + a circle-on-hover) — not included
here as a `uk-*` recipe because it wasn't *ported from* a specific licensed
source; whoever builds the cockpit should treat it as a fresh implementation
(existing `gamma_cockpit_ui.py` already hand-rolls SVG sparklines/bars per
`../../setup/scripts/vendor/MANIFEST.md`'s "Skipped" section, so this is
consistent with how that file already handles charts).

## Byte-budget flag (for whoever wires this in)

`setup/scripts/vendor/MANIFEST.md` already tracks a 250,000 B CSS+JS vendor
budget with 207,429 B spent (42,571 B headroom). This port's 32,899 B does
**not** fit in that headroom as a flat add — either raise the budget, drop an
existing asset, or (more likely, since most cockpit pages won't need all 16
recipes at once) inline only the subset of `uk-*` classes actually used by the
generated page rather than the whole file. Left as a decision for the build
step, not resolved here — this deliverable is the recipe library, not the
integration.

## Gaps / honest limitations

- **uiverse.io** was not crawled component-by-component (WebSearch only) —
  the brief asked for it as a secondary MIT source but the MagicUI set already
  covered every element in the reference image, so this wasn't chased further.
  If a future pass wants uiverse-specific recipes (status badges, command
  palette, animated tabs — none of which appear in the reference image anyway),
  it needs a JS-capable fetch (claude-in-chrome), same as 21st.dev.
- **21st.dev-native components** (not MagicUI re-embeds) were **not** actually
  ported — every one WebFetch reached gated its real source behind client-side
  JS. The "not ported" table in the MANIFEST names them so a future session
  with browser tooling doesn't have to rediscover which ones are worth chasing.
- Component count is 16, not the requested 12–20 upper range, by design: quality
  (verified license + verified source + working vanilla recipe) over padding to
  20 with unverified reconstructions.
