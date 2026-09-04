# Cockpit build spec v2: "Glow Command" (2026-09-04, Fable)

> Supersedes `COCKPIT-DESIGN-SPEC-2026-09-03.md` for LOOK (its plumbing stays: `gamma_cockpit_tiles.py`
> payload builders, `gamma_cockpit_tiles_js.py` row/gfx component, `cockpit_screenshot.py`,
> `cockpit_dom_check.py`, `cockpit_exercise.py`, vendored fonts/icons/countUp/confetti).
> J, 2026-09-04 ~00:55 ET, with a reference image: *"still just like basic ass text boxes dude come on.
> here is your reference image you MUST absolutely shoot for dope something like this. you need to get
> visuals on there ... get everything from these sites do not just use basic ass shit."*
> Sites: uiverse.io · 21st.dev/community/components/featured · monet.design DevRev feature sections.
> Kit (vendored by the crawl workflow): `setup/scripts/vendor/ui-kit/` + `INDEX.md` + `demo.html`;
> doc: `analysis/deep-research/COCKPIT-VISUAL-KIT-2026-09-04.md`. Builders read the kit FIRST and
> compose from it; hand-rolled quiet CSS is the failure mode this spec replaces.

## 1. The reference, decoded (the judges' bar)

"AetherOps · AI Workflow Command Center". What makes it read as 8/10:

| Element | What it is | Why it lands |
|---|---|---|
| Canvas | deep navy `#0a0e1c → #0d1226` vertical gradient, faint dotted matrix top-left | depth without noise |
| Panels | `#111833`-ish, 1 px indigo-tinted hairline `rgba(120,130,255,.18)`, inner top glow `rgba(120,130,255,.06)`, radius 16 | layered, premium |
| Nav rail | left, 220 px, icon + label rows, active row = pill `rgba(99,102,241,.18)` + brighter icon | orientation in 1 s |
| Header | 28/600 title, 13 subtitle sentence, search with ⌘K, gradient CTA (indigo→violet, glow) | a product, not a log |
| KPI cards ×4 | gradient icon tile (28 px rounded), 11 px label, 26 px number, green delta chip "↗ 12.4% vs last month" | numbers first, trend second |
| **Routing map** | Sankey: 5 node columns, ribbons as glowing gradient tubes (indigo→violet→cyan), % labels on ribbons, "Live" chip, legend | THE centerpiece, alive |
| Approval queue | rows: icon tile, title, subtitle, status chip (amber/green/violet), avatar | actionable list, scannable by chip |
| Cost pulse | big figure + delta, area chart with violet gradient fill + glow, highlighted point + tooltip | money as a graphic |
| Agent health | rows: name, version, %, green "Healthy" chip, tiny green sparkline | health by shape |
| System alerts | icon tile (amber/blue), text, Review button | exceptions only |
| Type | Inter-like sans; numbers large and light (500), labels tracked uppercase | calm hierarchy |

## 2. Tokens (dark-first; light theme = same structure, canvas `#f3f5fb`, panels white, glow at 8 %)

```css
:root{
  --gc-canvas-0:#0a0e1c; --gc-canvas-1:#0d1226; --gc-panel:#111833; --gc-panel-2:#161f3f;
  --gc-line:rgba(120,130,255,.16); --gc-line-2:rgba(120,130,255,.28);
  --gc-ink-1:#eef1ff; --gc-ink-2:#aab3d6; --gc-ink-3:#7581a8;
  --gc-indigo:#6366f1; --gc-violet:#8b5cf6; --gc-cyan:#22d3ee; --gc-pink:#ec4899;
  --gc-grad:linear-gradient(135deg,var(--gc-indigo),var(--gc-violet) 55%,var(--gc-cyan));
  --gc-glow:0 0 24px rgba(99,102,241,.35); --gc-glow-cyan:0 0 18px rgba(34,211,238,.35);
  --gc-good:#34d399; --gc-warn:#fbbf24; --gc-bad:#fb7185; --gc-info:#60a5fa;
  --gc-chip-good:rgba(52,211,153,.14); --gc-chip-warn:rgba(251,191,36,.14); --gc-chip-bad:rgba(251,113,133,.14); --gc-chip-info:rgba(96,165,250,.14);
  --gc-r:16px; --gc-r-sm:10px; --gc-pad:20px;
  --gc-t-fast:150ms; --gc-t-base:240ms; --gc-t-open:320ms; --gc-t-draw:900ms;
  --gc-ease:cubic-bezier(.2,.8,.2,1); --gc-ease-ambient:cubic-bezier(.45,0,.55,1);
}
```
Money colours stay reserved for P&L (`--gc-good/--gc-bad` on figures only); health uses chips.
Every vendored kit snippet is rethemed through its `--uk-*` variables → these tokens.

## 3. Layout at 1600×950 (nav rail + 3-column content), nothing below the fold that matters

```
+------+--------------------------------------------------------------------------------+
| rail | Gamma Command Center            [search ⌘K]                    (● Not live) [Fire top] |
| Cmd  | Market closed · 2 agents running · 12 need you · Book flat                      |
| Jrnl | [Book $3,629 ↗7d spark] [Gate NOT LIVE ring 0.42] [Agents 5/5 ring] [Budget $0/30 ring] |
| Ans  | +--------------------------------------------+ +-----------------------------+ |
| Army | | ROUTING MAP  (Live)   fill funnel, today    | | NEEDS YOU  12       View all| |
| Ktch | | signals→gates→ENTER→accepted→fills→exits    | | [icon] title  chip  [Fire]  | |
| Rsrch| |  glowing ribbons, % labels, legend          | | ...×5                       | |
| Rig  | +--------------------------------------------+ +-----------------------------+ |
|      | +---------------------+ +-------------------+ +-----------------------------+ |
| ---- | | AGENT MAP (Army)    | | AGENT HEALTH      | | COST PULSE  $34.56 ↗ area   | |
| sys  | | stage, stars, beams | | kitchen/prospect. | | glowing chart, point tip    | |
| chat | +---------------------+ +-------------------+ +-----------------------------+ |
+------+--------------------------------------------------------------------------------+
```
Below the fold (Command scroll): Trading / Research / Rig row groups as **cards** (not rows): each
producer is a card with icon tile, title, one-line state, ONE graphic (existing gfx*), chip, age;
click = expand in place (existing `<details>` tile). System alerts (Known broken) as an alerts list.

## 4. Component map (reference → cockpit → data)

| Reference | Cockpit component | Data (payload key / builder) | Kit snippet kind |
|---|---|---|---|
| Nav rail | `gc-rail`: Command, Journal, Answers, Army, Kitchen, Research, Rig, Settings(theme) | VIEWS + section anchors | nav rail w/ active pill |
| Header + subtitle | title "Gamma Command Center"; the state sentence as subtitle (verdict words tinted) | `briefing`, `army`, `gate`, `cards`, `calendar` | header, ⌘K field, gradient CTA (= Fire the top card via existing fireCard) |
| KPI cards ×4-6 | Book (7d spark + net), Gate (ring CI-lower vs 1.0 + NOT LIVE/LIVE), Agents (ring running/total), Budget (ring spent/cap), + Kitchen (pulse), Shadow (heat) on wide screens | `calendar.views.BOOK.summary`, `gate`, `army`, `autonomy.budget`, `lanes.kitchen`, `shadow` | KPI stat card w/ gradient icon tile + delta chip |
| **Routing map** | **Fill funnel Sankey**: columns Ticks → Setup present → Gates passed (ENTER) → Accepted → Filled → Exited (TP / stop / time / flatten). Ribbon width ∝ count; tones indigo (flow) / cyan (accepted) / pink (refused); % labels; "Live" chip during RTH else "Today · closed"; legend. Hover a ribbon → tooltip with the cause counts (`cause_counts`). | `fill_funnel.compute_funnel(day)` (read its exact keys; per-account ticks, verdicts, `cause_counts`, `blocking_ticks`, `quiet_ticks`) + `autonomy-metric.json.function_latest` (enters/accepted/fills) as fallback; NO DATA state draws the columns with empty ribbons | sankey ribbon recipe (SVG cubic paths + gradient + glow filter + dash-flow animation) |
| Approval queue | **Needs you**: top 5 cards (icon tile by severity, title (human, ≤ 34 chars, word boundary), one short state clause, status chip RED/AMBER/QUEUE/GOAL, Fire button (existing guard path), expand for the full text) + "View all" opens the full list | `cards` | queue row w/ chip + icon tile |
| Cost pulse | Budget: `$spent / $cap` big figure, delta vs cap, glowing area chart of the last 14 fire costs, highlighted last point + tooltip | `conductor-outcomes.jsonl` (cost_usd by day) via a small builder in `gamma_cockpit_tiles.py`; `autonomy.budget` | glowing area chart recipe |
| Agent health | rows: Kitchen (alive/idle, done today), Prospector (ideas/promoted), Futures lanes (n/5 live), Multi-symbol (survivors), Watcher fleet (n watching) — each with a chip + a tiny sparkline (7-day counts from `learning-ledger.json` windows or the lane's own series) | `lanes.*`, `learning`, `watchers` | health row + sparkline |
| System alerts | Known broken entries (STATUS.md) + guards RED + gate expiry: icon tile, text, "Open" (drawer) | `guards`, `tasks`, `answers` with non-green verdicts | alert row |
| Agent map | the Army stage, re-framed as a panel with the glow language (stage bg navy, beams gradient, session cards as panels) | `army` (unchanged mechanics) | stage frame from kit glass/glow card |
| Promo panel | "Tonight's plan": the active goal + next item + next fire time, gradient panel | `goal`, `autonomy` | gradient promo panel |

## 5. Motion (J: "big on visuals and animations") — must exist AND be exercised headless
- Load (one WAAPI timeline): rail + header fade/rise 0–200 ms → KPI numbers CountUp + sparklines draw (path length) 150–800 → routing-map columns rise then ribbons draw left→right (stroke-dashoffset) 300–1100 → cost-pulse area fills 600–1000 → stage stars fade + beams 700–1100.
- Ribbons carry a slow dash-flow (8 s, ambient ease) while "Live"; hover brightens the ribbon and dims siblings.
- KPI cards: hover lift 2 px + glow; delta chips pulse once on change.
- Queue rows: hover surface; expand height + opacity; Fire = existing comet → flash → toast.
- Theme toggle crossfade 200 ms; prefers-reduced-motion collapses every duration to 0 and disables dash-flow.
- Confetti (existing wiring): gate GREEN flip / daily target hit, in-session only.

## 6. Non-negotiables (carry from v1)
Single self-contained file; no CDN; works from file:// and http://localhost:4317; vendored kit only
(`vendor_assets.py` + `vendor/ui-kit/`); every figure shows source + age (on hover/expand, not as a
second line of grey text on the glass); no text < 12 px; no page horizontal scroll; modules ≤ 800
lines (new modules: `gamma_cockpit_glow_ui.py` CSS, `gamma_cockpit_glow_js.py` layout + KPI + queue +
health + alerts, `gamma_cockpit_sankey_js.py`, `gamma_cockpit_costpulse_js.py`); keep the payload
contract; keep fireCard/guard, chat, palette, calendar, answers, army poll; guard suite green.
Headless only (J 23:33 ET): captures via `cockpit_screenshot.py`, interaction via `cockpit_exercise.py`.
Fix on the way: Kitchen KPI reads NO DATA although `lanes.kitchen` is populated (key mismatch).

## 7. Exit bar
Blind panel of 3 given J's reference description AND the after-captures: median ≥ 7, `wall_of_text=false`,
"looks like the reference family" = yes from ≥ 2 critics; headless exercise 0 console errors and ≥ 8/10
checks; DOM self-check clean both themes; guard suite green; committed with a one-line revert.
