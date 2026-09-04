# AetherOps UI-kit — per-file vendor index

> Named `VENDOR-INDEX.md`, not `INDEX.md`: the repo's write-guard rejects any file
> literally named `INDEX.md` anywhere (that filename is reserved for
> `setup/scripts/obsidian_vault_sync.py`'s generated per-topic indexes and is
> hand-edit-protected repo-wide). This file serves the same purpose for this directory.

This directory holds **two separate deliverables** from two different vendoring passes —
they don't conflict, just don't confuse them:

1. **This pass (2026-09-03, per-file):** 41 standalone `<kind>-<slug>.html` snippets below,
   each self-contained with its own markup + `<style>` + optional `<script>`, meant to be
   dropped into a page individually. Covered by this file + `REFERENCE-ONLY.md` +
   `demo.html`.
2. **An earlier pass (also 2026-09-03, bundle-style):** `aetherops-ui-kit.css` +
   `aetherops-ui-kit.js`, a combined stylesheet/script covering the 16 `21st-featured`
   components as `uk-*` classes meant to be linked once. Covered by `MANIFEST.md` (that
   pass's own provenance table — do not overwrite it, it documents a different artifact
   shape) and `../../../../analysis/deep-research/2026-09-03-aetherops-ui-kit-port.md`.

The two passes overlap in **subject matter** (both port some of the same 21st.dev/MagicUI
components) but not in **file names** — nothing here was overwritten by either pass.
Whoever wires this into `gamma_cockpit_ui.py` should pick ONE shape (standalone per-file
snippets vs. one linked bundle) rather than shipping both, to stay inside the vendor byte
budget noted below.

41 vanilla HTML+CSS(+small JS) snippets, `uk-*` prefixed, self-contained (no CDN/build
step). Every file carries its own provenance comment at the top (name | source | license
| ported-by note) — this table is the at-a-glance summary. Colors intended to retheme
with the cockpit use CSS custom properties (`--uk-canvas`, `--uk-panel`, `--uk-line`,
`--uk-accent`, `--uk-accent-2`, `--uk-accent-3`, `--uk-glow`); status-semantic colors
(green/amber/red for chips, sparklines) are left literal since they're meaning-coded, not
part of the brand retheme surface. Items with no stated permissive license were **not**
vendored as code — see `REFERENCE-ONLY.md` for those recipes instead.

See also `demo.html` (renders every file below in one dark grid) and `../MANIFEST.md`
(the repo-wide vendor asset ledger, tracking a 250,000 B CSS+JS budget).

| File | Kind | Source | License | Cockpit use | Bytes |
|---|---|---|---|---|---|
| card-glow-border.html | card | uiverse.io/Daniel1227k/moody-newt-4 | MIT (Uiverse) | KPI stat card / queue-row glowing gradient-border shell | 1842 |
| card-spherical-gradient.html | card | uiverse.io/monkey_8812/curly-moth-56 | MIT (Uiverse) | Alt KPI card, spinning gradient orb icon tile | 1997 |
| card-frosted-glass.html | card | uiverse.io/vinodjangid07/grumpy-mule-23 | MIT (Uiverse) | Approval-queue row / Cost-pulse panel frosted-glass base | 1810 |
| button-blob-party.html | button | uiverse.io/Ashon-G/mean-mayfly-77 | MIT (Uiverse) | Decorative secondary CTA / promo-panel button | 4231 |
| button-glow-cta.html | button | uiverse.io/gharsh11032000/cuddly-turkey-5 | MIT (Uiverse) | PRIMARY header CTA ("New workflow") | 1592 |
| button-frosted-border-mask.html | button | uiverse.io/TaniaDou/witty-rabbit-59 | MIT (Uiverse) | Secondary nav/toolbar button ("Export") | 1821 |
| toggle-neon-power.html | toggle | uiverse.io/vinodjangid07/quick-moth-22 | MIT (Uiverse) | "Live" status toggle / agent enable switch | 1941 |
| loader-diamond-pulse.html | loader | uiverse.io/Zadrus/sweet-dragon-8 | MIT (Uiverse) | Compact processing loader / dotted-matrix accent | 1100 |
| loader-atom-orbit.html | loader | uiverse.io/OMPRABHU8125/nice-sheep-25 | MIT (Uiverse; page also credits Rahul Sahni as design inspiration) | "Live" chip spinner on routing-map header | 2017 |
| toggle-glow-radial-check.html | toggle | uiverse.io/gagan-gv/unlucky-yak-4 | MIT (Uiverse) | Approval-queue checkbox / "Approved" status dot | 1421 |
| tooltip-hover-reveal.html | tooltip | uiverse.io/themrsami/quick-zebra-71 | MIT (Uiverse) | Nav-rail icon tooltip / agent-health popover | 1190 |
| other-gradient-underline-input.html | other | uiverse.io/adamgiebl/hot-cat-14 | MIT (Uiverse) | Header search field with ⌘K hint | 1598 |
| card-stacked-layer-hover-lift.html | card | uiverse.io/gharsh11032000/fuzzy-robin-67 | MIT (Uiverse) | Approval-queue / agent-health row hover-lift | 2059 |
| background-dot-pattern.html | background | 21st.dev/dillionverma/dot-pattern -> magicui dot-pattern.tsx | MIT (magicuidesign/magicui) | Dotted-matrix decoration | 1315 |
| card-border-beam.html | card | 21st.dev (MagicUI re-embed) -> border-beam.tsx | MIT (magicuidesign/magicui) | Animated glowing border around any panel | 1598 |
| card-shine-border.html | card | 21st.dev (MagicUI re-embed) -> shine-border.tsx | MIT (magicuidesign/magicui) | Subtle traveling-shine panel border | 1382 |
| button-shimmer.html | button | 21st.dev (MagicUI re-embed) -> shimmer-button.tsx | MIT (magicuidesign/magicui) | Secondary gradient button, rotating shimmer spark | 1375 |
| button-rainbow.html | button | 21st.dev (MagicUI re-embed) -> rainbow-button.tsx | MIT (magicuidesign/magicui) | Tertiary gradient-outline button | 1120 |
| button-pulsating.html | button | 21st.dev (MagicUI re-embed) -> pulsating-button.tsx | MIT (magicuidesign/magicui) | Attention-drawing button (e.g. "Acknowledge alert") | 1007 |
| chart-number-ticker.html | chart | 21st.dev/featured -> number-ticker.tsx | MIT (magicuidesign/magicui) | KPI big-number count-up-into-view | 1864 |
| list-marquee.html | list | 21st.dev (MagicUI re-embed) -> marquee.tsx | MIT (magicuidesign/magicui) | Scrolling agent-name / status ticker strip | 1574 |
| card-magic-spotlight.html | card | 21st.dev (MagicUI re-embed) -> magic-card.tsx | MIT (magicuidesign/magicui) | Hover-spotlight card for queue rows / agent tiles | 2277 |
| chart-progress-ring.html | chart | 21st.dev (MagicUI re-embed) -> animated-circular-progress-bar.tsx | MIT (magicuidesign/magicui) | Per-agent uptime ring next to "Healthy" chip | 1714 |
| card-bento-grid.html | card | MagicUI bento-grid.tsx (21st.dev stats-bento used as layout target only, page code not extracted) | MIT (magicuidesign/magicui) | 4-KPI-card header row grid | 2700 |
| background-ripple.html | background | 21st.dev (MagicUI re-embed) -> ripple.tsx | MIT (magicuidesign/magicui) | Ambient background rings behind promo/empty state | 1782 |
| background-meteors.html | background | 21st.dev (MagicUI re-embed) -> meteors.tsx | MIT (magicuidesign/magicui) | Falling-meteor ambient decoration | 1835 |
| background-animated-grid.html | background | 21st.dev (MagicUI re-embed) -> animated-grid-pattern.tsx | MIT (magicuidesign/magicui) | Faint structural grid texture behind panels | 1177 |
| chip-animated-shiny-text.html | chip | 21st.dev (MagicUI re-embed) -> animated-shiny-text.tsx | MIT (magicuidesign/magicui) | Header subtitle shine-sweep text | 1005 |
| flow-animated-beam-ribbon.html | flow | 21st.dev (MagicUI re-embed) -> animated-beam.tsx | MIT (magicuidesign/magicui) | Single glowing connector between two nodes | 3202 |
| button-gradient-cta-glow.html | button | uiverse.io/nima-mollazadeh/terrible-panda-97 | MIT (Uiverse, crawled via browser pane) | Alt primary CTA / "Deploy smarter" button | 1584 |
| card-kpi-stat.html | card | uiverse.io/vk-uiux/nasty-chicken-72 | MIT (Uiverse) | 4 header KPI stat cards (icon tile + delta chip) | 2333 |
| flow-workflow-routing-map.html | flow | self-authored (standard SVG cubic-Bezier ribbon technique, no library copied) | Original, no third-party code | **Centerpiece** Workflow routing map (5-stage Sankey) | 6734 |
| chart-cost-pulse-area.html | chart | self-authored (generic SVG gradient-area + glow technique) | Original, no third-party code | Cost pulse panel area chart + hover tooltip | 4828 |
| chip-status.html | chip | self-authored (generic pill-badge convention, 4 tones) | Original, no third-party code | Approval-queue / alert status chips | 1474 |
| list-avatar-row.html | list | self-authored (generic gradient-initials avatar) | Original, no third-party code | Approval-queue rows | 1885 |
| nav-rail-active-pill.html | nav | self-authored (generic active-sidebar-pill convention) | Original, no third-party code | Left nav rail active pill | 1844 |
| background-panel-shell-canvas.html | background | self-authored (generic dark-panel/glow convention) | Original, no third-party code | Overall canvas + base panel shell | 1151 |
| chart-sparkline-card.html | chart | self-authored (gap-filler; generic inline SVG polyline sparkline) | Original, no third-party code | Agent-health row sparkline | 2069 |
| background-aurora-glow.html | background | self-authored (gap-filler; generic top-radial-bloom) | Original, no third-party code | Header hero band top glow | 1318 |
| list-alert-row.html | list | self-authored (gap-filler; composed from this kit's own chip/icon-tile pieces) | Original, no third-party code | System alerts rows (icon tile + Review button) | 2300 |
| card-promo-panel.html | card | self-authored (gap-filler; composed with button-gradient-cta-glow.html's MIT CTA) | Original composition; embedded CTA is MIT | "Deploy smarter" promo panel | 2316 |

**Total: 41 files, ~86 KB combined.** This is a SEPARATE byte pool from the earlier
bundle pass's 32,899 B (`aetherops-ui-kit.css`+`.js`) — combined the two passes' assets
run well past the 250,000 B CSS+JS vendor budget tracked in `../MANIFEST.md` (207,429 B
already spent there before either AetherOps pass). Flagged, not resolved here: whoever
wires this into `gamma_cockpit_ui.py` should inline only the specific `uk-*` snippets
actually used on the page (per-file shape makes this easy — copy only the files you need)
rather than linking everything.

## Coverage checklist (from the task brief)
glow/gradient-border cards ✓ (4: glow-border, border-beam, shine-border, magic-spotlight) ·
KPI stat card ✓ · spotlight hover card ✓ (magic-spotlight) · neon gradient button ✓ (5) ·
status chips (4 tones) ✓ · avatar row ✓ · nav rail w/ active pill ✓ · sankey ribbon recipe (SVG) ✓
(flow-workflow-routing-map + flow-animated-beam-ribbon) · glowing area chart recipe (SVG) ✓
(chart-cost-pulse-area) · sparkline card ✓ · progress ring ✓ · pulse loader ✓ (diamond-pulse
+ ripple) · orbit loader ✓ · animated toggle ✓ (2) · tooltip ✓ · aurora background ✓ ·
dot-matrix pattern ✓ · number ticker ✓ · alert row ✓ · promo panel ✓.

## What was skipped and why
- **uiverse.io items beyond the 14 already crawled** (13 in the original uiverse-glow pass
  + 1 CTA button reused from monet-devrev/reference-hunt) were not re-searched — the
  vendored set already covers every visual role in J's reference image.
- **21st.dev-native components** (Stats Bento, Skill Level Meters, Leaderboard Card, Area
  Chart, Grid Feature Cards, Bloom Field, generic background snippets): their `Component.tsx`
  is client-side-gated and never rendered to WebFetch/browser extraction in the source
  research — nothing was copied, so nothing is vendored for these. (Also listed in the
  earlier pass's `MANIFEST.md`.)
- **monet.design-derived recipes** (aurora glow, panel-shell colors, KPI-tile colors,
  node-routing diagram, sparkline/progress-bar colors, icon-tile+chip row, active-pill
  gradient composition, promo panel, search field): these carry **no stated license**
  (screenshot-gallery, DOM-extracted from someone else's live page) — recorded as
  recipe text only in `REFERENCE-ONLY.md`, not vendored as code. Where the cockpit needed
  the same visual role, a fresh self-authored file was written instead using only generic,
  independently-derived technique (listed above, "self-authored" rows).
- **File named `INDEX.md` as the task literally requested**: blocked by the repo's
  write-guard (reserved for `obsidian_vault_sync.py`-generated per-topic indexes); this
  file (`VENDOR-INDEX.md`) serves the same purpose instead.
