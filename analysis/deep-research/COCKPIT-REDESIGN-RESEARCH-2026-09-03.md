# Cockpit Redesign — External Research Pack (2026-09-03)

> Target: `analysis/home/index.html` (built by `setup/scripts/gamma_home.py` + `gamma_cockpit_*.py`), served at `http://localhost:4317/cockpit.html`.
> WARNING — READ THIS FIRST: this redesign already happened once. `markdown/infra/COCKPIT-DESIGN-SPEC.md` (792 lines, 2026-08-30) was synthesized from a prior 5-lane research fleet and shipped across 10 commits (`457ea51d`→`8b46a155`) into these exact files. A tracked goal file (`automation/state/goals/GOAL-DAILY-DRIVER-GLASS-2026-08-30.md`) has most of an 11-item reference dossier ticked `[x]`. This pack is the NEXT increment, not a from-scratch derivation — read the spec's 792 lines in full before building. Full detail: Section 5 Critic Gaps, item 1.

---

## 1. TL;DR — recommended asset set

**Hard constraint restated** (`gamma_cockpit_ui.py:6-9`, verified this session): "one self-contained file. No CDN, no web fonts, no external JS or CSS. Must work from a file:// URL with no network." Every item below is a download-once-and-vendor-locally recommendation — none are live `<script src="https://...">` tags, regardless of how the install command reads.

| Asset | Pick | Verified | Size | License | Note |
|---|---|---|---|---|---|
| Token system (extend, do not replace) | Open Props split files: `props.sizes/shadows/easing/animations/borders/media/zindex.min.css` | Yes | ~13-15KB | MIT | Additive to existing oklch `--bg-*/--tx-*` system at `gamma_cockpit_ui.py:65-103`. Skip `props.colors.min.css` (4.8KB) — collides with existing palette. |
| Status color ramps | Radix Colors — 3-4 `{name}.css`+`{name}-dark.css` pairs (green/red/amber/indigo) | Yes | ~8KB | MIT | 12-step accessible ramp for kill-switch/PnL/warning states the current system lacks. Naming confirmed `slate-dark.css` not `slateDark.css`. |
| Motion engine | GSAP 3.12.7 core | Yes | 70.6KB | GreenSock Standard No-Charge (NOT OSI/MIT — read once: gsap.com/standard-license) | Vendor as local file, not CDN-linked — violates the page's own hard constraint if linked live. Must add `prefers-reduced-motion` gating to match the 6 existing guards in `gamma_cockpit_ui.py` (lines 157/172/381/469/474/560). |
| Charts | Keep hand-rolled SVG (existing shipped decision) | n/a | 0KB | n/a | `gamma_cockpit_ui.py` docstring: "rules out every chart library — sparklines, bars, org graph are hand-rolled SVG." uPlot (50.9KB, MIT, verified) is a real option but contradicts a decision already made and shipped — don't add without asking J to explicitly reverse it. |
| Number count-up | CountUp.js 2.8.0 | Yes | 5.8KB | MIT | Vendor local; gate on reduced-motion. Fixes "wall of text" on every $/% headline. |
| Celebration moment | canvas-confetti 1.9.3 | Yes | 10.6KB | ISC | Vendor local. Wire to go-live-gate GREEN flip / daily-target-hit event. |
| Expandable tiles | Native `<details>/<summary>` + View Transitions API | Yes | 0KB | web platform | Exact match for "expandable tiles" ask — beats any JS tile library, zero offline risk. Graceful no-op fallback on older Chromium/file://. |
| Icons | Lucide — hand-picked, inlined raw `<svg>` (~30-50 icons) | Yes | ~3KB | ISC | Do NOT use `lucide.min.js` (373KB) or `sprite.svg` (404KB) — either alone blows the whole redesign budget. Copy-paste from lucide.dev/icons/<name>. |
| Ambient background (optional) | particles.js 2.0.0 | Yes | 22.8KB | MIT | Optional only. Gate on `prefers-reduced-motion` + consider skipping on battery-saver. 1/6th the size of tsParticles (140.8KB, also verified). |
| Design-taste skill | anthropics/skills -> frontend-design | Yes | 19KB | Apache-2.0 | `gh api repos/anthropics/skills/contents/skills/frontend-design/SKILL.md --jq ".content" \| base64 -d > ~/.claude/skills/frontend-design/SKILL.md` |
| Aesthetic-anchor skill | Ilm-Alan/frontend-design ("Organic trading terminal" anchor) | Yes | 14KB | MIT | Install under a renamed dir to avoid collision: `~/.claude/skills/frontend-design-anchors/` (name collision with item above). |
| Motion-craft/critique skill | h3nryprod01/design-taste | Yes | 106KB | MIT | Needs `reference/` folder too, not just SKILL.md — clone then copy. |
| Already installed, $0 | design:accessibility-review | n/a | n/a | n/a | Skipped by the original plugin search (critic gap #10) — run this before shipping, covers WCAG/contrast/focus that no external candidate targets except item below. |
| Audit skill (external, optional) | vercel-labs/agent-skills -> web-design-guidelines | Yes (2KB size) | Unverified license | — | Fetches a live checklist (raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md) — usable by hand even without installing. |

Estimated added weight (core motion+chrome set: GSAP+CountUp+confetti+particles.js+Lucide+Open Props+Radix): ~135-150KB, against a 758KB page that is 77% baked JSON payload (see Section 4.6) — under 20% growth of the non-data part, consistent with the project's lean-context posture.

**Do-before-building checklist** (from Section 5 Critic Gaps):
1. Read `markdown/infra/COCKPIT-DESIGN-SPEC.md` in full (792 lines, only ~100 read this pass) + the open items in `GOAL-DAILY-DRIVER-GLASS-2026-08-30.md`.
2. Vendor every new lib as a local minified file, inlined at `gamma_home.py` render time — never a live CDN `<script src>`.
3. Add a light theme by reusing the existing `[data-cvd]` attribute-swap pattern (already in the CSS, just never used for light/dark) — zero light-theme CSS exists today (grep-verified, 0 hits).
4. Do not add a command-palette library (ninja-keys/cmdk) — a working Cmd+K palette + vim "g"-then-key nav + "?" shortcuts drawer already exists in `gamma_cockpit_js.py`.
5. Gate every new animation (GSAP/particles.js/CountUp/confetti) on `prefers-reduced-motion`, matching the 6 existing guards.

---

## 2. Reference gallery (10) — borrowable moves

| # | Reference | Verified | Palette (if fetched) | Top 3 borrowable moves |
|---|---|---|---|---|
| 1 | Linear (linear.app) | No (search+DESIGN.md corroboration) | canvas #010102, surfaces #0f1011/#141516/#18191a, hairline #23252a, accent lavender #5e6ad2, Inter, 4px grid | Hairline "surface ladder" not shadows; 24px intra-block / 96px inter-section gaps; status = color+icon+1-line, detail on click |
| 2 | Raycast (raycast.com) | No | canvas ~#040506 -> #07080a -> #0d0d0d -> #101111, hairline #242728, coral accent #ff6363, Inter | Inset-highlight+hairline card (no shadow) = "pressed key" feel; 28-32px tight rows; ONE accent color reserved for the single most-actionable thing |
| 3 | Warp (warp.dev) | Yes (DESIGN.md fetched, 526 lines) | warm charcoal canvas #2b2622, soft #383330, hairline #3f3a36, text #f7f5f0, Inter + Instrument Serif accent | Block pattern = collapsed one-line status+icon, expand for full log — direct 1:1 match for a tile spec; metadata chips (duration/exit-code/timestamp) avoid prose; warm-dark ground as an alternative mood to blue-black |
| 4 | Grafana dashboards | No (own best-practices doc + 2 summaries) | n/a | Z-pattern layout (critical KPI top-left); row grouping into named sections (Army/Kitchen/EOD/Prep) — direct answer to "combine with army page"; stat-panel = big number + threshold color, sparkline secondary/on-hover |
| 5 | Bloomberg Terminal | No (subscription-gated, search-summary only) | Unverified | Monospace for all numbers (columnar scan); grouped density via rules/dividers not cramming; color reserved strictly for direction/threshold, never decorative |
| 6 | NASA Open MCT (nasa.github.io/openmct) | No (1 search summary, live demo not opened) | Apache-2.0 (code reusable) | Tree-structured left nav w/ expandable folders -> Army/Kitchen/EOD/Prep as top-level branches; freely-arrangeable widget canvas, each panel independently expandable/poppable — literal match for "expandable tiles"; bottom timeline strip for scrubbing today-vs-past |
| 7 | Vercel / Geist (vercel.com/geist/colors) | Yes (DESIGN.md fetched, 736 lines) | light theme ref: ink #171717, body #4d4d4d, mute #888888, hairline #ebebeb, canvas #ffffff/#fafafa/#f5f5f5, action blue #0070f3 | 3-step light elevation via 2% lightness steps (no color needed for hierarchy); ONE action color discipline; sidebar-first nav (Feb-2026 redesign) |
| 8 | Sentry (marketing site; in-app unverified) | No (DESIGN.md is marketing surface, flagged mismatch) | violet-black #150f23/#1f1633, lime #c2ef4e, pink #fa7faa, Rubik + mono | "Surface the bad thing, let good stay quiet" product philosophy; single recurring icon-motif for warmth; CTA stays dark on either polarity |
| 9 | PostHog (marketing site; in-app unverified) | No (contradicts "dark UI" summary — flagged) | warm amber #f7a501, ink #23251d, canvas #eeefe9, desaturated semantic colors w/ matching "-soft" tint | Soft-tint semantic pairs (pale bg tint per status) for graded severity beyond red/green dots; warm-neutral grays vs Linear's cool blue-black — worth A/B |
| 10 | VoltAgent/awesome-design-md (meta-source) | Yes (dir listing fetched, 60 folders confirmed) | n/a | Not a design itself — a 60-product DESIGN.md library (Supabase, Binance, Stripe, Notion, Coinbase, Kraken, etc.) worth cloning as a standing reference asset; Supabase ("dark emerald dev dashboard") and Binance ("bold yellow on monochrome trading UI") folders look most relevant for a next pass, unverified contents |

Recommendation: pick ONE dark base deliberately — Linear's cool near-black or Warp's warm charcoal — don't blend. Steal Grafana's row-grouping + Z-pattern for Army/Kitchen/EOD/Prep sections. Steal Warp's block pattern for individual tiles. One accent color only (Vercel/Raycast discipline) instead of decorating with the existing multi-color status system.

---

## 3. Tile inventory (20 candidates, ranked)

`gamma_home.py:build()` already wires: `hq`, `calendar`/`calendar_full`/`calendar_scale`, `cost_meter`, `answers` (7 cards), `desks`, `allocation`, `org`, `engine_room`, `agents`, `thinking`, `positions`, `briefing`, `wants_full`, `activity`, `autonomy`+`goal`, `army`, `cards`, `glass`, `lanes` (kitchen/futures/multi/prospector/spy/weather via `gamma_lanes.py`), `learning`. Roughly half of the 20 tiles below are pure UI lift — data already flows.

| Rank | Tile | Producer | State file (mtime) | Payload key | Graphic | 1-line state | Priority |
|---|---|---|---|---|---|---|---|
| 1 | Go-Live Gate | go_live_gate.py | analysis/go-live-gate.json (09-03 12:43) | NOT wired — NEW | gauge (PF CI-lower vs 1.0) | "GREEN/RED — PF CI-lower(2.5%) = X.XX vs 1.0, N days" | must |
| 2 | EOD Summary/Debrief | Analyst/Gamma_EodDeep | analysis/eod/2026-09-03.md (09-03 14:45) | NOT wired — NEW | timeline (day markers) | "EOD digest filed 14:45 ET — verdict + top pattern-mined line" | must |
| 3 | Morning/Premarket Prep | Gamma_Premarket | automation/state/today-bias.json (wired) + premarket-readiness.json (09-03 07:30, NOT wired) | partial | list (bias badge + falsifiable predictions) | "BULLISH/BEARISH/NEUTRAL — N calls logged 08:30" | must |
| 4 | Guards/Tests Health | task-state guard family | automation/state/task-state-guard.json (09-03 15:57) | NOT wired — NEW | heatmap (guard grid) | "guards N/N green — last repair: X" | must |
| 5 | Gym Scorecard | Gamma_GymSession 17:00 ET | automation/state/gym-scorecard-2026-09-03.json (09-03 15:00) | NOT wired — NEW | heatmap (7-audit grid) | "overall VERDICT — 7 audits, N stale reruns" | must |
| 6 | Shadow/Prereg Board | ~20+ Gamma_*Shadow tasks | SHADOW.md (09-03 14:45) — no rollup JSON exists | NOT wired — biggest new-plumbing item | calendar/list hybrid | "N shadow clocks running, N preregs frozen, 0 armed" | must |
| 7 | Watcher Fleet | 28-watcher engine | automation/state/watcher-summary.json (mtime unverified) | NOT wired — NEW | heatmap (per-watcher PnL sign) | "N watchers observing, best would-be PnL: name +$X" | must |
| 8 | The Kitchen | kitchen_daemon.py | automation/state/kitchen-status.json (09-03 16:01) | wired: lanes.kitchen | pulse+spark (alive/idle + spend bar) | "daemon ALIVE — N queued, $X.XX/$cap today" | must (UI-only) |
| 9 | Prospector | prospector loop | analysis/prospector/state.json (09-03 14:43) | wired: lanes.prospector | spark (mini funnel) | "N ideas this beat, N promoted, N folded as dupes" | must (UI-only) |
| 10 | Futures Desk | 5 futures lanes | automation/state/futures/health.json (09-03 16:00) | wired: Q6 answer + lanes.futures (double-wired) | gauge (N/5 live) + list | "N/5 lanes live — all shadow/sim, 0 real fills" | must (UI-only) |
| 11 | Journal Calendar | journal_calendar.py | analysis/journal/calendar-data.json (09-03 16:00) | wired: full | calendar (month grid) | "BOOK net +$X over N days, win-rate X%" | must (re-skin only) |
| 12 | Budget/Cost Meter | gamma_cost_meter.py | automation/state/cost-meter.json (09-03 12:27) | wired: top-level + lanes | gauge + spark (7d) | "$X.XX/$cap today, trailing-7d $Y" | must (UI-only) |
| 13 | The Army — STYLE REF | gamma_cockpit_army.py | live-built every load | wired: army | radial pulses, expandable rows | n/a — this is the donor page | must (donor, not receiver) |
| 14 | Positions/Glass (trading floor) | gamma_glass.py + gamma_cockpit_data.py | live-built | wired: glass, positions, engine_room | ring (per-acct equity+P&L) | "safe-2 FLAT / bold-2 FLAT (or +$X open)" | must (centerpiece, not peripheral) |
| 15 | Autonomy/Goal Loop | gamma_autonomy.py | live-built (Gamma_GoalAutopilot 30min) | wired: autonomy+goal | pulse (awake/asleep + goal line) | "awake — working toward: goal text" | should |
| 16 | Multi-Symbol Lane | multi/ fork | analysis/multi-lane/evaluations/learning-report.json (09-03 14:45) | wired: lanes.multi | funnel (72->N survivors) | "SHADOW — N/72 survived funnel, arm idle" | should |
| 17 | Standups (AM/EOD) | gamma_standup.py | automation/state/gamma-standup-latest.json (09-03 14:45) | NOT wired | pulse card | "AM standup 07:xx ET — focus: X" | should |
| 18 | Analyst Review (rule-break audit) | overlaps #2 | analysis/eod/2026-09-03.md | fold into EOD expand, not standalone | n/a | "N trades audited, N breaks, N queued for Chef" | should |
| 19 | Learning Ledger | learning_ledger.py | automation/state/learning-ledger.json | wired: learning | spark (windows over time) | "latest verdicts: N across M ledgers" | should |
| 20 | Scheduled-Task Health | audit_scheduled_tasks.py | SCHEDULED-TASKS.md (mtime not captured) | may collapse into #4 (unverified cross-check) | heatmap->count, drill to list | "N registered — N Ready, N Disabled, 0 orphans" | nice |

**Volume check vs SCHEDULED-TASKS**: grep this session found 188 unique `Gamma_*` task names / 187 `| Gamma_...` table rows under `## Active` (registry itself warns not every "Active" row has a live enabled trigger). A flat one-row-per-task tile is unusable at this volume — any Guards/Task-health tile (#4, #20) needs a lane rollup (Army/Kitchen/EOD/Prep/Shadow/Guards) with drill-in, per the NASA Open MCT tree-nav pattern (Section 2 ref #6), not addressed as a design requirement by the original 5 sections.

---

## 4. Current-page audit

### 4.1 Token system (preserve/extend baseline) — gamma_cockpit_ui.py:45-103

- All-neutral OKLCH: `--bg-canvas` 8.5%, `--bg-1/2/3` 17.5/21.2/24.8%, `--bg-inset` 11.5% — elevation is luminance, never border/shadow tricks.
- Hairlines = alpha-of-foreground: `--bd-subtle/--bd/--bd-strong` oklch(94.5% 0 0 / .065|.11|.18).
- `--pos`/`--neg`/`--warn` reserved for P&L only; system/agent health uses traffic-light dots (`.chip.ok/.warn/.bad`), never these as fills.
- `--acc` (space-purple, 300 deg) = "you can act on this" (Fire/Send/focus only). `--st-live` (cyan, 207 deg) = the ONLY "alive" color — deliberately distinct from `--acc` after a documented bug where a dot wrongly inherited amber.
- Type: system stack + `ui-monospace` mono; tabular numerals forced globally (pinned by `test_numbers_use_tabular_figures`).
- Spacing `--s1..--s9` = 2/4/8/12/16/20/24/32/40px. Radius `--r-sm..--r-pill` = 6/10/14/20/999px.
- Motion: `--e-hover`/`--e-enter` (expo-out)/`--e-open`/`--e-close`/`--e-route`, each wrapped in `prefers-reduced-motion` at 6 separate call sites (lines 157,172,381,469,474,560) — pinned by `test_reduced_motion_is_honoured`.

### 4.2 Walls-of-text density (11 views, ranked prose-heaviest -> graphics-heaviest)

| Rank | View | Nav | Density evidence |
|---|---|---|---|
| 1 (worst) | Autonomy (gamma_cockpit_autonomy_js.py, newest, 2026-09-03) | primary tab | Hero quote + DONE-WHEN list + QUEUE list + PROGRESS LOG + honest_state paragraph + 13-row x 2-col table + 5 sub-cards, zero sparklines/bars/graphs anywhere. J's brief names this view directly ("the goal dashboard... i need to see it happening"). |
| 2 | Answers (views_js.py:488-516) | primary tab | 7 cards x ~150-400 chars prose each (q/answer/detail/means fields), one chip icon per card, nothing else visual. |
| 2 | Agents (views_js.py:352-385) | Cmd-K only | 4 stat tiles + a 5-col events table rendering up to 45 rows verbatim — raw log table, ~zero custom graphics. |
| 4 | Orchestration (views_js.py:209-290) | Cmd-K only | Allocation-reasons bullets (3-6 per desk) + 4-col shared-functions table + 1 SVG org graph (only graphic). |
| 5 | Activity (views_js.py:519-555) | Cmd-K only | Shadow-clocks list w/ progress bars (real graphic) + numbered "what I want" text list + plain "recent ships" list. |
| 6 | Cards (gamma_cockpit_cards_js.py:53-100) | primary tab | 1-4 "why" bullets per card (up to ~220 chars each) + chips; no severity graphic beyond a chip (Army-embedded rail does add a left accent stripe the standalone view lacks). |
| — | Desks / Overview / Engine / Journal / Army (graphics-led: sparklines, EKG strips, calendar grid, org graph, radial pulses) | — | lower text density |

### 4.3 Army-view mechanics worth reusing as house style — gamma_cockpit_army_js.py (1115 lines)

- Bento seating: busiest session gets a 2-col "featured" cell; column count MEASURED from live container width (`fitCols()`), never hardcoded.
- Beam comets: per-edge SVG `linearGradient` + travelling dashed stroke, lit full-opacity only on node hover.
- Segmented context meter: 14 discrete blocks (not continuous fill), colored acc->warn->neg, only drawn when source is known — never fabricated.
- Answer bar: one sentence at top ("N agents running now — M in window...") replacing a meaningless "LIVE" chip — same "answer, don't make them read tiles" pattern the brief wants generalized.
- Cards rail + View Transitions: `document.startViewTransition` + shared `view-transition-name`, no manual FLIP math, Chromium-only by design.
- Fire feedback loop: click -> comet flies card->orchestrator node -> node flashes -> toast confirms — cause/effect as one visible motion.
- Deterministic no-RNG ambient layers (golden-angle star scatter, hashed-phase flicker) so two renders of the same instant look identical.
- Stale-session hiding by default (>2h since last transcript write) with a "+N" toggle, not a permanent list.

### 4.4 Must-preserve behaviours (contract surface)

| Behaviour | Location | Contract |
|---|---|---|
| Card fire+guard | gamma_cockpit_cards_js.py:102-131 fireCard() | POSTs /api/approve; client RTH check is cosmetic only — real gate is server-side gamma_cockpit_cards.py:120 _looks_dangerous() denylist (pinned by 13+ assertions in test_gamma_cockpit_cards_2026_08_29.py) |
| Chat | gamma_cockpit_chat_js.py:33-279 | Real resumable session via /api/orchestrator-chat + SSE; session persists to localStorage['gamma-chat-v1']; switching model forces new session |
| Cmd-K palette | gamma_cockpit_js.py:282-305 | PAL[] indexed by kind View/Desk/Agent/Answer/Day/Engine — pinned verbatim by test_command_palette_indexes_every_entity_kind |
| Calendar | views_js.py:388-485 | Color ramp CLAMPED via D.calendar_scale.clamp/max_abs — pinned by test_calendar_ramp_is_clamped_and_extremes_annotated |
| Answers | gamma_home.py:287-484 build_answers() | Exactly 7 dicts, every one MUST carry sources — pinned by test_every_answer_still_ships_its_sources |
| Army poll | army_js.py:746-849 | GET /api/army?since= with x-gamma-token header |
| file:// fallback | cards_js.py:55, army_js.py:1009, chat_js.py:147-155 | Every network feature checks location.protocol==='file:' and degrades to a message, never silently fails |
| Triple-consumer payload | gamma_home.py:56-64,706-717 | OUT_HTML + COMPANION_HTML (byte-identical) + COMPANION_JSON (separate public/app/) — any payload change must satisfy all three |
| gamma_hq librarian | gamma_home.py:213-228,24-31 | "ZERO DUPLICATED LOGIC" — this page must never recompute a metric gamma_hq.py already owns; every feed try/excepted independently so one failing feed degrades to a NO-DATA card, not a lost page |

Test files pinning structure (would red-flag careless changes): `test_gamma_cockpit_2026_08_20.py` (banned-substring CDN/script-src checks, view-id existence — note: army/cards/engine/agents view ids have NO dedicated "must exist" test, a real gap), `test_gamma_home_2026_08_19.py`, `test_gamma_home_autonomy_view_2026_09_03.py`, `test_cockpit_feeds_2026_08_20.py`, `test_gamma_cockpit_cards_2026_08_29.py`.

### 4.5 Module size runway (no automated 800-line guard exists — convention only)

| Module | Lines | Status |
|---|---|---|
| gamma_cockpit_army_js.py | 1115 | 315 over the stated ceiling |
| gamma_cockpit_cards.py | 833 | 33 over |
| gamma_home.py | 729 | approaching |
| gamma_cockpit_army.py | 750 | approaching |
| gamma_cockpit_ui.py | 620 | most headroom — likely landing zone for new CSS |
| gamma_cockpit_views_js.py | 556 | — |
| gamma_cockpit_data.py | 508 | — |
| gamma_cockpit_org.py | 448 | — |
| gamma_cockpit_js.py | 341 | — |
| gamma_cockpit_autonomy_js.py | 283 | — |
| gamma_cockpit_chat_js.py | 280 | — |
| gamma_cockpit_cards_js.py | 166 | — |

Implication: new client logic likely needs a new `gamma_cockpit_<viewname>_js.py` module (existing pattern), not growth of an already-over-budget file.

### 4.6 Size/build time (verified this session)

- Fresh build: `time gamma_home.py --quiet` -> 5.432s wall (not profiled per-module).
- `analysis/home/index.html` = 758,302 bytes; `gamma-companion/public/cockpit.html` byte-identical; `public/payload.json` = 580,282 bytes.
- Breakdown: CSS 35,017B + JS 138,113B + HTML shell 1,742B ~ 175KB (23%). Remaining ~583KB (77%) is the baked `const D=...` JSON payload — a visual redesign keeping the same payload contract will NOT shrink the file; real size reduction requires trimming `calendar_full` (every trade row, every arm) or lazy-loading via existing /api/* endpoints instead of baking for the file:// case.

---

## 5. Critic gaps (verified against the repo this session)

| Rank | Finding | Verified | Action |
|---|---|---|---|
| 1 | Redesign already happened once — COCKPIT-DESIGN-SPEC.md (792 lines, 2026-08-30) shipped across 10 commits into the exact target files; a goal file has an 11-item reference dossier mostly ticked [x]. This pack independently re-found overlapping references (Linear/Vercel/Warp) without checking git log first. | Yes (git log, file reads) | Read the spec in full + open goal items before further design work; gap-check J's brief against what already shipped (zero-chroma neutrals, purple accent, hand-rolled SVG, Cmd+K, reduced-motion) rather than re-deriving. |
| 2 | Recommended libs (GSAP/uPlot/Chart.js/particles.js/confetti) as written (script src=cdn...) directly violate the page's own hard constraint (no CDN, file:// safe). | Yes (gamma_cockpit_ui.py:6-9 docstring quoted) | Reframe every Section 1 lib as "download once, vendor local, inline at render" — as ui_kits section already does — or drop in favor of the shipped hand-rolled-SVG approach for anything chart-shaped. |
| 3 | Zero light-theme implementation despite it being a stated hard constraint. grep -c 'data-theme="light"' = 0; no .light/theme-toggle/prefers-color-scheme anywhere. | Yes (grep this session) | Reuse the existing [data-cvd] attribute-swap pattern (same mechanism, unused for light/dark) for a [data-theme="light"] variant — inverted-luminance oklch ramp, same zero-chroma discipline. |
| 4 | A working Cmd+K palette + vim "g"-then-key nav + "?" shortcuts drawer already exists and works — a ninja-keys/cmdk library would be a duplicate. | Yes (read gamma_cockpit_js.py) | Extend existing palRender/pal DOM if visual polish is needed; do not replace with a library. |
| 5 | 6 existing prefers-reduced-motion guards exist; the newly-recommended libs (GSAP/particles.js/confetti/CountUp) introduce untracked motion with zero reduced-motion gate proposed. | Yes (grep, 6 hits) | Any new animation wiring must check matchMedia('(prefers-reduced-motion: reduce)') before firing — a condition of adoption, not an afterthought. |
| 6 | Scheduled-task count (~187-188 active) not cross-checked against any tile design; a flat per-task tile is unusable at this volume. | Yes (grep this session) | Any task-health tile needs a lane rollup (Army/Kitchen/EOD/Prep/Shadow/Guards), drill-in on click — NASA Open MCT tree-nav pattern (Section 2 ref #6), not addressed by name in the original 5 research sections. |
| 7 | No Figma Community/Penpot/Framer free-kit search ever run, despite being named in the original research prompt. | No, not run | If pursued: visual-reference only (like Tabler), hand-port spacing/type numbers — neither offers a vendorable live CSS bundle. |
| 8 | No lighter-weight (<50KB CSS) framework-free GitHub dashboard template surveyed as an alternative to the correctly-rejected 523KB Tabler. | No, not run | Follow-up search: "admin dashboard vanilla css no-build" / "command center dashboard template". |
| 9 | animate.css (named in the original prompt) never evaluated or explicitly rejected. | No, not run | Quick follow-up: fetch+size-check, then reject as redundant with the shipped named easing/duration system, or adopt if genuinely cheaper. |
| 10 | design:accessibility-review (already installed, $0) was skipped by the plugin search in favor of external-only candidates — a real gap vs the Obsidian-brain "check prior coverage" rule. | Yes (skill roster confirmed present this session) | Run this skill against the finished redesign in addition to (not instead of) frontend-design — covers WCAG/contrast/focus, an axis no external candidate but rank-4 web-design-guidelines targets. |

---

## 6. Open questions

1. Has `markdown/infra/COCKPIT-DESIGN-SPEC.md`'s full 792 lines + the `GOAL-DAILY-DRIVER-GLASS-2026-08-30.md` remaining open items been read end-to-end yet? (Only ~100/792 lines read this pass.)
2. Does `task-state-guard.json`'s tasks[] array already contain the same census as SCHEDULED-TASKS.md (187-188 rows), letting tile #20 collapse into tile #4? Unverified — not cross-checked.
3. Is GSAP's GreenSock Standard No-Charge License actually compatible with a PUBLIC GitHub repo (Swjsh/42)? License permits use/distribution of animated output but has resale/product restrictions — read gsap.com/standard-license once before committing.
4. `analysis/home/index.html`'s data-dominance (77% baked JSON) means a visual-only redesign won't move the byte count — is trimming `calendar_full` (every trade row, every arm) or lazy-loading via /api/* in scope for THIS pass, or deferred?
5. Which single dark base (Linear cool near-black vs Warp warm charcoal) does J actually prefer? Neither shipped decision (gamma_cockpit_ui.py's existing oklch ramp already reads closer to Linear's than Warp's) has been explicitly re-confirmed against the brief's "cool" ask.
6. Watcher-summary.json's exact mtime and Scheduled-Task registry's live census were both flagged unverified this pass (not independently re-run) — worth a fresh census before building tiles #7/#20.
7. Figma Community/Penpot/Framer template search and a lighter-weight (<50KB) dashboard-template search: worth a follow-up pass, or explicitly out of scope?

---

Method note: every size/HTTP-status/license field in Section 1 and every git-log/grep/file-read claim in Section 4-5 was fetched or verified live this session (curl against cdnjs/jsdelivr, gh api against GitHub repos, direct grep/read of the target Python/JS files) — none recalled from training data. Reference-gallery palettes (Section 2) marked Yes came from a raw DESIGN.md fetch; marked No are search-summary level only and should be re-confirmed by opening the live site before citing specifics as fact.
