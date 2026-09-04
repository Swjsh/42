# Reference-only recipes (no code vendored)

These items came back from the research pass with **no stated permissive license** — they
were extracted by DOM computed-style inspection from someone else's live page (monet.design
screenshot-gallery previews, mostly re-rendering a DevRev dashboard mock), not from a
licensed open-source file. Per the task's rule ("Only vendor items with a stated permissive
license... items with no stated license become entries in REFERENCE-ONLY.md"), these are
recorded as **recipe text only** — colors, layout math, and technique description — with
**no HTML/CSS file created**. Where the cockpit needed the same visual idea, a fresh
self-authored file was vendored instead (see INDEX.md's "self-authored, generic technique"
rows) rather than copying these values directly.

---

## Aurora glow panel (top radial bloom + gradient-border trick)
- Source: https://www.monet.design/c/stats-10 (rendered at registry.monet.design/live-preview/stats-10)
- License: N/A — monet.design is a screenshot/inspiration gallery; recipe only, no code copied.
- Recipe: outer page glow — `position:absolute; inset:0; background: radial-gradient(80% 50% at 50% 0%, rgba(59,130,246,.15) 0%, rgba(0,0,0,0) 60%); pointer-events:none`. Panel-hugging glow — `position:absolute; inset:-16px; border-radius:16px; opacity:.5; background: radial-gradient(60% 40% at 50% 0%, rgba(99,102,241,.30) 0%, rgba(0,0,0,0) 70%)`. Glowing 1px border via padding trick — wrapper `border-radius:12px; padding:1px; background: linear-gradient(180deg, rgba(59,130,246,.4) 0%, rgba(99,102,241,.2) 50%, transparent 100%)`, inner child `background: linear-gradient(180deg, rgba(30,32,60,.8) 0%, rgba(15,17,35,.9) 100%); border-radius:11px`.
- Vendored instead: `background-aurora-glow.html` (self-authored, same top-radial-bloom idea, original values).

## Deep navy dashboard canvas + panel shell (hairline border, inner glow)
- Source: https://www.monet.design/c/saaspo-feature-sections-devrev
- License: N/A — screenshot gallery, recipe only. Colors confirmed via live DOM computed-style extraction, not copied source.
- Recipe: root canvas `#0a0a0a`, panel `#111111` with `1px solid #2a2a2a`, `border-radius:12px`, large soft shadow (`~0 25px 50px -12px rgba(0,0,0,.5)`). Left icon-rail: `width:40px; background:#0d0d0d; border-right:1px solid #2a2a2a`, 20x20px icon tiles alternating `#2a2a2a`/`#1a1a1a`. Inner content tiles: `background:#0d0d0d; border:1px solid #1a1a1a; border-radius:8px; padding:12px` (recessed one level from the outer panel).
- Vendored instead: `background-panel-shell-canvas.html` (self-authored navy/indigo variant).

## KPI stat tile: colored dot + big metric + green delta chip
- Source: https://www.monet.design/c/saaspo-feature-sections-devrev
- License: N/A — recipe only, colors confirmed via live DOM extraction.
- Recipe: card `background:#1a1a1a; border-radius:8px; padding:12px`. Status dot 12x12px, one of green/purple/blue/amber/pink. Label row: dot + 12-13px label at ~70% white opacity. Big number 20-24px weight 600. Delta chip: `font-size:10px; padding:2px 6px; border-radius:4px; background: rgba(<accent>, .125)`, text = full-saturation accent, content "&uarr; 4%" / "&darr; 12%".
- Vendored instead: `card-kpi-stat.html` (real MIT port from uiverse.io vk-uiux/nasty-chicken-72, not this recipe).

## Node-and-line routing/tree diagram (teal glow connectors, dashed active node)
- Source: https://www.monet.design/c/conversion-integrations-section
- License: N/A — recipe only, colors/structure confirmed via live DOM extraction.
- Recipe: central 96x96px node `border:2px dashed #2DD4BF; background:#262626; border-radius:8px` (dashed = "active/hub"). Vertical connector to a horizontal trunk, branching into 80x80px child nodes (`border:1px solid #374151`). Connector lines solid teal `#2DD4BF`, 1-2px, with 8x8px teal square joint markers at corners.
- Vendored instead: `flow-workflow-routing-map.html` (self-authored 5-stage gradient-ribbon Sankey extending this idea, not this recipe's literal values) + `flow-animated-beam-ribbon.html` (real MIT port of MagicUI's animated-beam.tsx, the actual connector mechanism used).

## Glowing gradient area chart with highlighted point + tooltip
- Source: n/a — original recipe synthesizing a common dark-analytics-dashboard pattern; no single component page copied.
- License: N/A — generic charting/CSS technique, not extracted from a specific owned page.
- Vendored instead: `chart-cost-pulse-area.html` (self-authored, same technique, running code).

## Mini inline sparkline + health/progress bar
- Source: https://www.monet.design/c/saaspo-feature-sections-devrev
- License: N/A — recipe only, colors confirmed via live DOM extraction.
- Recipe: progress-bar track `width:48px; height:6px; background:#1F2937; border-radius:999px`. Fill `border-radius:999px; background:` solid green `#22C55E` (healthy) or amber `#F59E0B` (degraded), no gradient. Mini bar-chart bars: `width:24px; border-radius:4px 4px 0 0; background:` solid violet `#8B5CF6` or amber `#FBBF24`, heights vary. Sparkline: inline `<svg>` polyline, `stroke:#22C55E; stroke-width:1.5; fill:none`, 60-80px wide, 20px tall.
- Vendored instead: `chart-sparkline-card.html` (self-authored polyline sparkline card).

## Gradient CTA button with blurred hover-glow (dual-layer border trick)
- Source: https://uiverse.io/nima-mollazadeh/terrible-panda-97
- License: **MIT** (Uiverse.io element page states "MIT License") — NOT reference-only; this one IS vendored.
- Vendored as: `button-gradient-cta-glow.html`.

## Large promo panel with big radial highlight + gradient CTA
- Source: aurora-glow portion from https://www.monet.design/c/stats-10; embedded CTA from https://uiverse.io/nima-mollazadeh/terrible-panda-97
- License: mixed — aurora-glow portion N/A (monet.design, recipe only); CTA portion MIT.
- Recipe: panel `border-radius:16px; padding:32px; background: linear-gradient(160deg, #171c33 0%, #10142a 100%); border:1px solid #2a2f4d`, `::before` radial highlight `radial-gradient(70% 60% at 15% 0%, rgba(99,102,241,.25) 0%, transparent 65%)`. Headline 20-22px weight 700. Copy 13px at 60% white, max-width ~70%.
- Vendored instead: `card-promo-panel.html` (self-authored panel composed with the already-vendored MIT `button-gradient-cta-glow.html` CTA — no monet.design values copied).

## Icon-tile + status-chip list row (approval queue / alerts)
- Source: https://www.monet.design/c/saaspo-feature-sections-devrev
- License: N/A — recipe only, chip color-at-12.5%-alpha token confirmed via live DOM extraction.
- Recipe: row `padding:10px 12px; border-radius:8px; background:#1a1a1a`, hover border `#2a2a2a`. Icon tile 36x36px, `border-radius:8px`, gradient (approval) or flat `#262626` (alert). Title 13-14px weight 600 white. Subtitle 12px at 55% white. Chip: `padding:2px 8px; border-radius:4px; font-size:10px; font-weight:600`, three tones at `rgba(<accent>,.125)` background / full accent text. Avatar 28px circle, gradient or flat, initials centered.
- Vendored instead: `list-avatar-row.html` + `list-alert-row.html` (self-authored, composed from this kit's own chip/icon-tile conventions, no monet.design values copied).

## Active nav-rail pill (indigo->violet gradient highlight)
- Source: n/a — original recipe; gradient values reused from an MIT-licensed source (uiverse.io/nima-mollazadeh/terrible-panda-97) recolored; the pill/nav composition itself is a generic pattern.
- License: gradient values derive from an MIT source; the composition is original, no code copied.
- Vendored instead: `nav-rail-active-pill.html`.

## Search field with ⌘K hint chip
- Source: n/a — original recipe; standard command-palette-trigger pattern, no single source copied.
- License: N/A — generic CSS/markup pattern.
- Vendored instead: this exact idea was already covered by the reference-hunt kit's real MIT port `other-gradient-underline-input.html` (uiverse.io adamgiebl/hot-cat-14), which already has the ⌘K hint added during porting — no separate file needed.

---

### Not pursued (per the source research notes, carried forward)
- **monet.design**: screenshot-only gallery — correctly excluded from direct code copying per the brief; sampled only via live-DOM computed-style extraction (not source reading) for the recipes above.
- **21st.dev-native components** (Stats Bento, Skill Level Meters, Leaderboard Card, Area Chart, Grid Feature Cards, Bloom Field, generic background snippets): client-side-gated `Component.tsx`, never reached WebFetch/browser extraction — nothing copied, nothing vendored.
- **uiverse.io** additional searches beyond the 14 components actually crawled (13 in `uiverse-glow` + 1 in `monet-devrev`/`reference-hunt`) were not exhaustively re-run; the vendored set already covers every visual role in the AetherOps reference.
