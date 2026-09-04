# AetherOps UI-kit ports — MANIFEST

> Neither file here is a vendored byte-copy — both are **from-scratch vanilla
> CSS/JS re-implementations** of the cited components' visual technique (Tailwind
> classes + `motion/react` hooks removed, replaced with plain CSS
> keyframes/`@property`/`offset-path` and small rAF/pointermove handlers). Every
> recipe cites the exact upstream `.tsx` file it was read from so the technique
> can be checked against the original. No CDN at runtime — same "vendor it once,
> commit the bytes" rule as `../MANIFEST.md`.
>
> Research pass: 2026-09-03. Full crawl notes + why each item was/wasn't ported:
> [`analysis/deep-research/2026-09-03-aetherops-ui-kit-port.md`](../../../../analysis/deep-research/2026-09-03-aetherops-ui-kit-port.md).

**Totals** — `aetherops-ui-kit.css`: 23,507 B · `aetherops-ui-kit.js`: 9,392 B · **32,899 B** (within the existing 250,000 B CSS+JS vendor budget — 217,101 B headroom against the current 207,429 B already spent by `../MANIFEST.md`'s assets, so 32,899 B does NOT yet fit without also trimming something; flag to whoever wires this into `gamma_cockpit_ui.py` before inlining both).

| recipe (`uk-*` class) | discovered via (21st.dev) | ported from (GitHub, exact file) | license | cockpit element |
|---|---|---|---|---|
| `uk-dot-pattern` | [dillionverma/dot-pattern](https://21st.dev/dillionverma/dot-pattern) | [magicuidesign/magicui@2d671cc/apps/www/registry/magicui/dot-pattern.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/dot-pattern.tsx) | MIT | dotted-matrix decoration, left of flow map |
| `uk-border-beam` | (21st.dev embeds magicui) | [.../border-beam.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/border-beam.tsx) | MIT | glowing tube edges on flow-map nodes, KPI card hover accent |
| `uk-shine-border` | (21st.dev embeds magicui) | [.../shine-border.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/shine-border.tsx) | MIT | "Live" chip ring, active nav pill |
| `uk-shimmer-btn` | (21st.dev embeds magicui) | [.../shimmer-button.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/shimmer-button.tsx) | MIT | header indigo→violet gradient CTA |
| `uk-rainbow-btn` | (21st.dev embeds magicui) | [.../rainbow-button.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/rainbow-button.tsx) | MIT | secondary CTA (re-tuned to indigo/violet/cyan, not full rainbow) |
| `uk-pulse-btn` | (21st.dev embeds magicui) | [.../pulsating-button.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/pulsating-button.tsx) | MIT | "Deploy smarter" promo primary action |
| `uk-number-ticker` | [21st.dev featured: "Number Ticker" (12.4k installs/wk)](https://21st.dev/community/components/featured) | [.../number-ticker.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/number-ticker.tsx) | MIT | 4 KPI stat-card big numbers |
| `uk-marquee` | (21st.dev embeds magicui) | [.../marquee.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/marquee.tsx) | MIT | system-alerts / agent-roster scrolling strip |
| `uk-spotlight-card` | (21st.dev embeds magicui) | [.../magic-card.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/magic-card.tsx) | MIT | approval-queue rows, KPI cards, agent-health rows (mouse-glow hover) |
| `uk-progress-ring` | (21st.dev embeds magicui) | [.../animated-circular-progress-bar.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/animated-circular-progress-bar.tsx) | MIT | agent-health per-row % ring |
| `uk-bento-grid` / `uk-bento-card` | [ui layout/stats-bento](https://21st.dev/uilayout.contact/stats-bento) (layout only — exact source gated client-side, not extracted) + [.../bento-grid.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/bento-grid.tsx) | MIT (magicui) | REFERENCE-ONLY for the 21st.dev stats-bento page itself (license stated MIT on page, code not extracted) | KPI stat-card grid, bottom-row layout |
| `uk-ripple` | (21st.dev embeds magicui) | [.../ripple.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/ripple.tsx) | MIT | ambient rings behind header CTA |
| `uk-meteors` | (21st.dev embeds magicui) | [.../meteors.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/meteors.tsx) | MIT | premium-glow decoration behind flow-map centerpiece |
| `uk-animated-grid` | (21st.dev embeds magicui) | [.../animated-grid-pattern.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/animated-grid-pattern.tsx) | MIT | header / nav-rail backdrop texture |
| `uk-shiny-text` | (21st.dev embeds magicui) | [.../animated-shiny-text.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/animated-shiny-text.tsx) | MIT | "Live" chip label / header subtitle micro-shimmer |
| `uk-flow-ribbon` | (21st.dev embeds magicui) | [.../animated-beam.tsx](https://github.com/magicuidesign/magicui/blob/2d671cc6c0e0/apps/www/registry/magicui/animated-beam.tsx) + border-beam.tsx (blur treatment, row above) | MIT | the 5 flow ribbons: Intake→Classify→Review→Fallback→Deliver |

License basis: `magicuidesign/magicui` repo root `LICENSE.md` read verbatim via `gh api repos/magicuidesign/magicui/contents/LICENSE.md` on 2026-09-03 — plain MIT, copyright "Magic UI". Commit pinned: `2d671cc6c0e0` (main @ time of crawl).

## Not ported (REFERENCE-ONLY — visual recipe / no code copied)

These 21st.dev pages state a license but only exposed a `Usage.tsx` demo wrapper to WebFetch — the actual `Component.tsx` implementation loads client-side and was not extracted, so nothing from them was copied. Listed here so a later session doesn't re-crawl them expecting different results without a browser-rendered fetch:

| page | author | license stated on page | why skipped |
|---|---|---|---|
| [Stats Bento](https://21st.dev/uilayout.contact/stats-bento) | ui layout | MIT | Component.tsx not visible to WebFetch |
| [Skill Level Meters](https://21st.dev/cnippet.dev/v-meter-6) | Cnippet | MIT | Component.tsx not visible to WebFetch |
| [Leaderboard Card](https://21st.dev/trophyso/leaderboard-card) | trophyso | not stated on page | Component.tsx not visible to WebFetch |
| [Area Chart](https://21st.dev/reaviz/area-chart-1) | REAVIZ | not stated on page | Component.tsx not visible; upstream is `reaviz.dev`, license unconfirmed |
| [Grid Feature Cards](https://21st.dev/efferd/grid-feature-cards) | Efferd | not stated on page | Component.tsx not visible to WebFetch |
| [Bloom Field gradient](https://21st.dev/joinceleste/bloom-field-gradient) | Celeste | MIT | Component.tsx not visible to WebFetch |
| [Background snippets](https://21st.dev/ibelick/background-snippets) | Julien Thibeaut | not stated on page | collection index only, no per-snippet code visible |

If a later session wants these specifically, they need a JS-rendering fetch (headless browser / claude-in-chrome MCP) against the 21st.dev page, not plain WebFetch — 21st.dev loads `Component.tsx` via client-side JS, not in the initial HTML.
