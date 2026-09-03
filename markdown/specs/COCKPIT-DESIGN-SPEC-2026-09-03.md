# Cockpit build spec: "Quiet Command" (2026-09-03)

> Supersedes `markdown/infra/COCKPIT-DESIGN-SPEC.md` (2026-08-30) for LOOK. That spec's plumbing decisions survive only where restated here. J, 19:30 ET: "do not honour any of my previous designs ... maybe the plumbing."
> Inputs: `analysis/deep-research/COCKPIT-REDESIGN-RESEARCH-2026-09-03.md` (cited as **RP §n**), `~/.claude/skills/frontend-design`, `frontend-design-anchors`, `design-taste` (+ `reference/anti-slop.md`, `reference/motion.md`), the winning "linear-minimal" direction, and the judges' grafts. Every "already exists" claim below was re-grepped this session (19:43 ET); the results are in §1.

---

## 1. Verdict

**Baseline 2.3/10 (judges: 3, 2, 2). Target 7-8/10.** One matte near-black page, one accent, one column of 56 px rows, one glowing object (the Army stage). "Cool" comes from contrast: a silent page where the only things that move are alive.

| What the judges scored against | How this spec answers it |
|---|---|
| Autonomy = unbroken prose wall, no tiles | Every producer becomes one 56 px `<details>` row with a graphic; the goal body is an expansion, not a page |
| Fragmented style (Army rich, rest flat) | ONE Command view; Army is the stage at its heart; rows share one anatomy |
| No graphics outside Army | Fixed 160 px graphic column on every row (the "spine") + two hero rings in the Goal/Budget band |
| No severity encoding, no live signal | Verdict dots, soft-tint expanded bodies, CountUp + ink-wash on change, day-line cursor |
| Cards burn a screen each | Cards become rows in "Needs you", Fire button at the row's right edge |

**Repo facts verified this session (builders: re-run these greps, never trust a doc):**

| Claim | Command | Result |
|---|---|---|
| `[data-cvd]` theme swap exists (RP §5 #3) | `grep -rn "data-cvd\|data-theme" setup/scripts/*.py` | **0 hits. FALSE.** Light theme is net-new |
| Vendor assets exist | `ls setup/scripts/vendor/` + `MANIFEST.md` | **TRUE**: Inter 400/500/600 + JetBrains Mono, anime 4.5.0, countUp 2.8.0, confetti 1.9.3, Open Props 8 files, Radix 7 hues x4, 59 Lucide icons |
| Vendor assets are inlined into the page | `grep -n vendor setup/scripts/gamma_cockpit_ui.py gamma_home.py gamma_cockpit_js.py` | **0 hits.** Downloaded, tested, NOT wired. `vendor_assets.py` exposes `css() js() icon() font_face_css() manifest()` |
| CSS+JS vendor budget | `MANIFEST.md` totals | 207,429 B of 250,000 B **if anime.js is included**; anime alone is 118,043 B |
| Tokens JS modules depend on | `grep -oh "var(--[a-z0-9-]*)" setup/scripts/gamma_cockpit_*_js.py` | `--tx-1..4 --s2..s8 --acc --acc-dim --acc-deep --st-live --bd --bd-subtle --bd-strong --bg-1 --bg-2 --bg-inset --pos --neg --warn --pos-dim --neg-dim --font --mono --r-md --topline --ring` (must stay defined as ALIASES, §2.1) |
| Screenshot path | `setup/scripts/cockpit_screenshot.py` | exists; captures light via `?theme=light`, so the theme bootstrap must honour that query param |
| ET now | `et_clock.py` | 2026-09-03 19:43 EDT, market closed |

---

## 2. Design plan

**Anchor** (frontend-design-anchors §3): closest legitimate territory is **Industrial** (flat, hairlines not shadows, tabular numerics, one signal colour) held with a proportional text face for prose rows. Stated as a deliberate deviation: Industrial's all-mono body would put 13 px mono prose in 20 rows, which fails J's skim test. Differentiator: **the spine**, a vertical strip of 160 px graphics at one x on every row, and **one luminous window** (the Army stage) cut into an otherwise silent slate.

**Category-reflex check** (anti-slop "AI slop test"): "trading dashboard" reflex = navy + neon green + hero-metric cards. Second-order reflex = "terminal-native black + acid accent". This spec avoids both: off-black gray-dark ramp, a cyan accent that is EARNED (it is the Army beam hue, graft #2), no hero-metric template, no cards.

### 2.1 Tokens (authored in `gamma_cockpit_ui.py`; values copied from vendored Radix files so the page never depends on `--cyan-9` names)

Sources: neutrals = `vendor/radix.gray-dark.css` / `radix.gray.css`; accent = `radix.cyan-dark.css` / `radix.cyan.css` (the Army stage already uses cyan `--st-live`; the accent now rhymes with the one glowing object instead of introducing a second hue); money/warn = green/red/amber pairs; easing/sizes = `openprops.easings.min.css`, `openprops.sizes.min.css`. Surface ladder idea = Linear (RP §2 #1); light ladder = Vercel Geist (RP §2 #7).

```css
/* ============ DARK (default) ============ */
:root{
  /* surfaces: Radix gray-dark 1..6 as the Linear-style ladder; no pure black (anti-slop 9.A) */
  --canvas:#111111;  --surface-1:#191919;  --surface-2:#222222;  --surface-3:#2a2a2a;
  --line:#313131;    --line-strong:#3a3a3a;                       /* gray-dark 5 / 6 */
  /* ink: gray-dark 12 / 11 / 10 / 9 */
  --ink-1:#eeeeee;   --ink-2:#b4b4b4;  --ink-3:#7b7b7b;  --ink-4:#6e6e6e;
  /* THE accent: Radix cyan-dark. 11 = text/stroke, 9 = fill, 10 = hover, 3 = wash, 7 = ring */
  --accent:#4ccce6;  --accent-fill:#00a2c7;  --accent-fill-hover:#23afd0;
  --accent-soft:#082c36;  --accent-line:#12677e;
  /* TONE TAXONOMY (closed enum, graft #1): act | live | gain | loss | caution | nodata.
     gain/loss are accepted ONLY by a spark/ring/figure whose series IS P&L.
     Verdict dots and health never use them (test_health_uses_dots_not_pnl_colours). */
  --pos:#3dd68c;  --pos-fill:#30a46c;  --pos-soft:#132d21;          /* gain: green-dark 11/9/3 */
  --neg:#ff9592;  --neg-fill:#e5484d;  --neg-soft:#3b1219;          /* loss: red-dark 11/9/3 */
  --warn:#ffca16; --warn-fill:#ffc53d; --warn-soft:#302008;         /* caution: amber-dark 11/9/3 */
  --dot-green:#30a46c; --dot-red:#e5484d; --dot-amber:#ffc53d; --dot-off:#484848; /* verdict dots; off = gray-dark 7 */
  /* the ONE glowing object */
  --stage-bg:#0e1416;                 /* canvas pulled 3% toward cyan-dark 1 (#0b161a) */
  --stage-glow:rgba(0,162,199,.12);   /* accent-fill @12% radial bloom */
  --beam:#4ccce6;  --star:#eeeeee;
  /* spacing (Open Props sizes), radius, easing (Open Props), durations (motion.md 120-320 band) */
  --sp-1:var(--size-1);--sp-2:var(--size-2);--sp-3:.75rem;--sp-4:var(--size-3);--sp-6:var(--size-5);
  --sp-8:var(--size-7);--sp-12:var(--size-8);--sp-16:var(--size-9);
  --r-1:4px; --r-2:8px; --r-pill:999px;
  --ease-out:var(--ease-out-4); --ease-in:var(--ease-in-3); --ease-std:var(--ease-3);
  --t-fast:120ms; --t-base:200ms; --t-open:320ms; --t-wash:600ms;
  --content-max:1360px; --graphic-col:160px; --row-h:56px; --topbar-h:48px;
  --font:"Inter","Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;
  --mono:"JetBrains Mono","Cascadia Mono",Consolas,ui-monospace,monospace;
  color-scheme:dark;
  /* ---- ALIASES: the names army_js / chat_js / cards_js / views_js already reference.
     Values are the new system; names survive so 1,115 lines of army_js need no edit. ---- */
  --bg-canvas:var(--canvas); --bg-1:var(--surface-1); --bg-2:var(--surface-2); --bg-3:var(--surface-3);
  --bg-inset:var(--stage-bg); --bd-subtle:var(--line); --bd:var(--line); --bd-strong:var(--line-strong);
  --tx-1:var(--ink-1); --tx-2:var(--ink-2); --tx-3:var(--ink-3); --tx-4:var(--ink-4);
  --acc:var(--accent); --acc-dim:var(--accent-line); --acc-deep:var(--accent-fill);
  --acc-soft:var(--accent-soft); --acc-line:var(--accent-line); --st-live:var(--accent-fill);
  --pos-dim:var(--pos-fill); --neg-dim:var(--neg-fill); --ring:var(--accent-line);
  --topline:transparent; --glow:var(--stage-glow); --glow-soft:transparent;
  --s1:2px;--s2:4px;--s3:8px;--s4:12px;--s5:16px;--s6:20px;--s7:24px;--s8:32px;--s9:40px;
  --r-sm:var(--r-1); --r-md:var(--r-2); --r-lg:var(--r-2); --r-pill:999px;
  --e-hover:var(--ease-std); --e-close:var(--ease-in); --sh-1:none;--sh-2:none;--sh-3:none;--sh-4:none;
}
/* ============ LIGHT ============ */
:root[data-theme="light"]{
  --canvas:#fcfcfc; --surface-1:#f9f9f9; --surface-2:#f0f0f0; --surface-3:#e8e8e8;   /* gray 1..4 */
  --line:#e0e0e0; --line-strong:#d9d9d9;                                             /* gray 5 / 6 */
  --ink-1:#202020; --ink-2:#646464; --ink-3:#838383; --ink-4:#8d8d8d;               /* gray 12/11/10/9 */
  --accent:#107d98; --accent-fill:#00a2c7; --accent-fill-hover:#0797b9; --accent-soft:#def7f9; --accent-line:#7dcedc;
  --pos:#218358; --pos-fill:#30a46c; --pos-soft:#e6f6eb;
  --neg:#ce2c31; --neg-fill:#e5484d; --neg-soft:#feebec;
  --warn:#ab6400; --warn-fill:#ffc53d; --warn-soft:#fff7c2;
  --dot-green:#30a46c; --dot-red:#e5484d; --dot-amber:#ffc53d; --dot-off:#cecece;
  /* the stage stays DARK in light mode: a glowing star-field on white is a contradiction */
  --stage-bg:#0e1416; --stage-glow:rgba(0,162,199,.12); --beam:#4ccce6; --star:#eeeeee;
  color-scheme:light;
}
```

**Ban list (builders enforce; a test greps for violations):**

| Banned | Only exception |
|---|---|
| `box-shadow` | Army stage bloom; Cmd-K palette `0 8px 24px rgba(0,0,0,.4)`; chat drawer top edge |
| gradients | stage radial bloom; per-edge beam gradient inside `#armysvg` |
| colour on text | `--pos/--neg` on money; `--warn` on stale ages and YELLOW words; `--accent` on links + Fire/Send |
| filled verdict pills, chips | none: verdict = 6 px dot + word in `--ink-1` |
| side-stripe borders > 1 px (anti-slop Part 1) | none |
| `border-radius` > 8 px on any container | pills on buttons only |
| all-caps labels, eyebrows, numbered section markers | none (day-line ticks are a real sequence, so labels there are times, not numbers) |
| em/en dashes in Gamma-authored on-page strings (design-taste 9.G) | strings arriving verbatim from state files |
| middle-dot `·` more than once per line | none |
| `body::after` grain, page-wide aurora, hover transforms, entrance stagger on rows | none |
| `#000` | none |

### 2.2 Typography (vendored, verified present; judges' graft #5: do NOT add Geist/Plex)

| Role | Size/LH | Weight | Face | Where |
|---|---|---|---|---|
| meta | 12/16 | 400 | JetBrains Mono | source path, age, key hints. **THE FLOOR: nothing visible below 12 px** |
| body | 13/20 | 400 | Inter | row state sentence, expansions, chat |
| row title | 15/20 | 500 | Inter | producer name |
| group title | 15/20 | 600 | Inter | "Needs you", "Trading", "Research", "Rig" + count in `--ink-3` |
| the sentence | 20/28 | 500 | Inter, letter-spacing -0.01em | answer bar |
| figure | 28/32 | 500 | JetBrains Mono | the ONE number a row owns |
| figure-lg | 40/44 | 500 | JetBrains Mono | Money row book net; Positions open P&L |

Rules: weights 400/500/600 only; no italics except the goal's verbatim quote; sentence case everywhere (current caps nav ANSWERS/ARMY and "WORKING ON"/"DONE-WHEN" eyebrows go); prose max 72ch; `body{font-feature-settings:"tnum" 1;font-variant-numeric:tabular-nums}` kept (test_numbers_use_tabular_figures). Fonts inlined via `vendor_assets.font_face_css()` with `font-display:swap` (93,556 B, already budgeted outside the CSS+JS cap).

### 2.3 Spacing / radius / elevation / motion tokens

| Scale | Values | Source |
|---|---|---|
| Spacing | 4 · 8 · 12 · 16 · 24 · 32 · 48 · 64 | Open Props `--size-*` (vendored) |
| Radius | 4 (inputs, dots' bounding), 8 (stage, drawers), pill (buttons) | anti-slop over-rounding ban |
| Elevation | none. Hierarchy = luminance ladder canvas -> surface-1 -> surface-2 -> surface-3 + 1 px `--line` | Linear surface ladder (RP §2 #1) |
| Easing | open `--ease-out-4`, close `--ease-in-3`, colour `--ease-3` | Open Props (vendored) |
| Durations | 120 hover / 200 base / 320 open / 600 wash | motion.md 120-320 band |

---

## 3. Information architecture

**Nav (48 px sticky top bar, `--canvas`, 1 px `--line` bottom, no blur):** `Gamma` wordmark 15/600 · tabs **Command / Journal / Answers** (sentence case; active = `--ink-1` + 2 px `--accent` underline) · right: ET clock (mono 13) · phase word (Premarket / Live / After hours; replaces the RESEARCHING chip) · theme toggle (`sun`/`moon` icon) · `⌘K` keycap.

**Routes.** `PRIMARY=['command','autonomy','journal','answers']` where `autonomy` is a registered alias that routes to Command scrolled to the Goal band and opens it (keeps `test_view_wired_into_render_and_nav`'s "'autonomy' in PRIMARY" assertion literally true; render it visually hidden in the tab strip via `data-alias`). Every old id (`overview desks orchestration engine agents army cards activity`) stays in `VIEWS[]` with its `vX` renderer name intact; each renderer now returns the Command view scrolled + expanded to its row (`test_every_view_is_defined_and_navigable`). Cmd-K keeps all PAL kinds.

**Command view** (default; replaces Overview + Autonomy + Army), one centred column, `max-width:1360px`, 40 px gutters:

| # | Band | Height | Contents (all from existing payload unless marked NEW) |
|---|---|---|---|
| 1 | The sentence | 44 | `D.briefing` + `D.army` + `D.gate` (NEW): "Market closed. **2** agents running, **0** waiting for you. Book flat. Gate RED, **0.42** vs 1.0." Generalises the Army answer bar (RP §4.3) |
| 2 | The day-line | 40 | 1 px `--line` track; ticks 08:00 TV up · 08:30 Premarket · 09:30 open · 15:55 flatten · 16:45 EOD · 17:00 Gym · 00:10 Conductor (from SCHEDULED-TASKS trading-critical table); live window 09:30-15:55 as 2 px `--ink-2`; now = 6 px `--accent-fill` dot + 8 px hairline; fired ticks `--ink-2`, upcoming `--ink-4`, failed today `--dot-red` (from `D.tasks` NEW) |
| 3 | The Army stage | 440 | `armySvg()` + stars canvas UNCHANGED mechanics: bento seating, `fitCols()`, beam comets, 14-block context meter, stale hiding, 1 s poll, View Transitions. Frame `--stage-bg`, radius 8, radial bloom, 24 px inset feather of `--canvas` (a window cut into slate, not a card). Controls (pause/play/refresh/+N stale/?) move to a 28 px icon row top-right. Cards rail REMOVED from the stage (goes to 5a). One 13 px line under it: latest pulse from the ledger |
| 4 | Goal + Budget band | 96 | 2fr/1fr, hairline above/below. **Left:** goal title 15/500 + id mono 12; next open item; **hero ring** (graft: mission-control rings) 40 px showing QUEUE done/open with the count inside; "N days left" mono. Click = expands DONE-WHEN / QUEUE / PROGRESS LOG inline (old vAutonomy body). **Right:** tonight's fires as the 14-block meter; spend today as 28 px mono figure + 7 d sparkline from `cost_meter` (currently 2026-08-30, so its age renders amber: that is the honesty working, not a bug) |
| 5 | Row groups | n x 56 | Grafana row grouping (RP §2 #4): **5a Needs you** (cards, worst first, Fire on row) · **5b Trading** · **5c Research** · **5d Rig**. Group header 15/600 + count + "Expand all" 12 px link. Groups 48 px apart; rows 0 apart (hairline). Collapsed state per group in `localStorage['gamma-groups']` |
| 6 | Footer | 32 | "Built 18:38 ET, payload 580 KB, 77% data" mono 12 `--ink-3`; `D.built_at_et` stays ISO (test_build_stamp_is_machine_parseable) |

**Chat pane:** bottom drawer, 320 open / 40 handle, `--surface-2`, hairline top; toggled by `/` or the handle. `gamma_cockpit_chat_js.py` unchanged except mount id. Send is the second `--accent-fill` button on the page (Fire is the first).

**Journal:** calendar grid re-skinned (44x44 cells, mono 12 values, ramp clamped exactly as today). **Answers:** the 7 answers as rows (same component; q = title, verdict dot, answer = sentence, detail + means + sources in the body). `build_answers()` untouched.

**ASCII wireframe, 1600x950, nothing expanded:**
```
+-----------------------------------------------------------------------------------------------+
| Gamma   Command  Journal  Answers                        19:43 ET   After hours   (moon)  ⌘K  | 48
+-----------------------------------------------------------------------------------------------+
|                                                                                               |
|   Market closed. 2 agents running, 0 waiting for you. Book flat. Gate RED, 0.42 vs 1.0.       | 44
|                                                                                               |
|   |------|------|=====================|------|------|------|-------------------------------o   | 40
|   08:00  08:30  09:30           15:55  16:45  17:00  00:10                            now      |
|                                                                                               |
|   +---------------------------------------------------------------------------------------+   |
|   |  .     .    .       .         .      .          .       .        [||] [+1] [o] [?]     |   |
|   |            .      +------------------------------+        .                .          |   |
|   |   .               | 42-32  orchestrator          |                 .                  |   |
|   |          .        | 2 agents running now  ###### |     .                    .         |   | 440
|   |                   +------------------------------+                                    |   |
|   |        +---------------------+   +---------------------+        .                      |   |
|   |   .    | Goal dashboard      |   | Premarket self-heal |               .               |   |
|   |        | active, 4 finished  |   | idle, 1 finished    |    .                          |   |
|   |        +---------------------+   +---------------------+                    .          |   |
|   +---------------------------------------------------------------------------------------+   |
|   42-98  Editing gamma_cockpit_ui.py  4s ago                                                  | 20
|  ---------------------------------------------------------------------------------------------|
|   Gamma autonomy  GOAL-GAMMA-AUTONOMY-2026-09-03   (5/7)  |  Tonight  ########....  3 of 8    | 96
|   Next: A6 next-fire verification         14 days left    |  Spend  $0.00 / $3.00  ~~/\~~      |
|                                                           |  cost-meter.json  4d (amber)      |
|  ---------------------------------------------------------------------------------------------|
|   Needs you  9                                                             Expand all         |
|   (target)  Goal A6 next-fire verification   [no graphic]   status 32m           Fire   v    | 56
|  ---------------------------------------------------------------------------------------------|
|   (target)  TASK-OUTPUT-FRESHNESS 1 finding  [no graphic]   STATUS.md 32m        Fire   v    | 56
+-----------------------------------------------------------------------------------------------+ 950
```
Second viewport (the spine; every graphic starts at x = 40+24+12+200+24 and is 160 wide):
```
|   Trading  6                                                               Expand all        |
|  (gauge)  Go-live gate     [====o----]  RED. PF CI-lower 0.42 vs 1.0, 42 days  go-live-gate.json 5h  v |
|  ---------------------------------------------------------------------------------------------|
|  (layers) Positions        (o o o o o)  Flat on all arms. 998 fills net to zero  fills-ledger 3.0h v |
|  ---------------------------------------------------------------------------------------------|
|  ($)      Money            _-=^-=_-^_   +$1,916 net, 42 days, 38% day win rate  calendar-data 39m v |
|  ---------------------------------------------------------------------------------------------|
|  (sunrise) Premarket prep   oooooo.o     YELLOW at 09:30. 12 checks, 0 red     premarket-readiness 11h v|
|  ---------------------------------------------------------------------------------------------|
|  (moon)   EOD debrief      |||.||.|     DEGRADED. 13 filled of 89 ENTER, 4 arms  eod/2026-09-03.md 4h v|
```
Expanded row (inline accordion; graphic column stays put, body opens under the words, left edge aligned to the graphic column):
```
|  (gauge)  Go-live gate     [====o----]  RED. PF CI-lower 0.42 vs 1.0, 42 days  go-live-gate.json 5h  ^ |
|      analysis/go-live-gate.json   2026-09-03 14:43 ET   5h ago            (mono, first line, graft #4) |
|      as-traded [===o---]  ex-best-day [==o----]  cost-adjusted [==o----]                              |
|      operational 4/4 green   reconciliation GREEN   prod-shadow safe-3, day 3 of 20 (to 2026-10-30)   |
|      distance to bar 0.677   n 294 trades   42 days   designated 2026-09-01                            |
|  ---------------------------------------------------------------------------------------------|
```
Row grid (px, left to right): 24 icon | 12 | 200 title | 24 | 160 graphic | 24 | 1fr sentence (ellipsis) | 24 | auto source+age mono 12 right | 12 | 20 chevron. Below 1100 px graphic = 120 and source drops under the title; below 800 px the row wraps to two lines. Wide expansions scroll in their own `overflow-x:auto`; the body never scrolls horizontally.

---

## 4. Tile system

**Component:** `tileRow(spec)` in `gamma_cockpit_tiles_js.py`. Native `<details>/<summary>` (RP §1 "Expandable tiles"). Every producer, every action card, every answer uses it.

```html
<details class="row" id="tile-gate" data-verdict="red" data-src="analysis/go-live-gate.json" data-stamp="2026-09-03T14:43:34">
  <summary class="row__head">
    <span class="row__ic"><!-- vendor icon('gauge') --></span>
    <span class="row__title">Go-live gate</span>
    <span class="row__gfx"><!-- gfxGauge svg 160x24 --></span>
    <span class="row__say"><i class="vd"></i>RED. PF CI-lower <b>0.42</b> vs 1.0, <b>42</b> days</span>
    <span class="row__src">go-live-gate.json <time class="age" datetime="2026-09-03T14:43:34">5h</time></span>
    <span class="row__chev"><!-- icon('chevron-down') --></span>
  </summary>
  <div class="row__body"><div class="src"><!-- srcRow(): full path, absolute stamp, age --></div> ... </div>
</details>
```

| Aspect | Rule |
|---|---|
| Sizes | collapsed 56 px, padding 0 8 px; `.row + .row{border-top:1px solid var(--line)}` (never top+bottom); body padding `8px 0 24px 236px`, 13/20, prose 72ch, tables 12 px mono |
| Graphic | exactly one, 160x24 (heat 160x32), drawn only when its source is known, else the slot is empty. **"If it cannot be drawn it is not a tile"** (graft #3): a producer with nothing graphable renders in its group as a plain row with an empty slot, never a fake graphic |
| Graphic kinds (one fn each) | `gfxGauge(v,bar,min,max)` bar + 1 px marker + 6 px dot · `gfxMeter(n,of)` the Army 14-block meter reused · `gfxSpark(vals)` polyline, `--ink-2`, last-point dot, `--pos/--neg` ONLY when the series is P&L · `gfxHeat(cells)` 7x4 of 8 px squares in `--dot-*` · `gfxRings(arms)` up to 6 x 12 px rings · `gfxFunnel(stages)` 3-4 shrinking bars · `gfxDots(states)` 5-9 verdict dots · `gfxBars(vals)` 7 columns · `gfxRingBig(n,of)` 40 px hero ring (Goal band only) |
| Sentence | one line; verdict word first (preceded by the dot); numbers in `<b>` (mono, `--ink-1`); rest `--ink-2`; composed by the Python builder from real fields, never guessed; no "undefined"/"None" (test) |
| Freshness | `row__src` = basename + `<time class="age">`; age computed on the existing 30 s `paintAge()` timer from the absolute stamp (feeds tests); past the tile's window (`gamma_lanes.STALE_MIN` where it exists, else `D.stale_hours`) the age turns `--warn` and the graphic drops to 60% opacity |
| Verdict | `data-verdict` in {green, amber, red, off, none}; drives the dot and the expanded body tint (`--neg-soft` red, `--warn-soft` amber, else transparent; PostHog soft-tint idea RP §2 #9). Never a fill on the collapsed row |
| States | default · hover (`background:var(--surface-1)` 120 ms, no transform, gated `@media (hover:hover) and (pointer:fine)`) · focus-visible (2 px `--accent-line` outline inset) · open (chevron 180) · stale · nodata (`data-verdict="off"`, sentence "NO DATA, looked for `<path>`", no graphic; test_missing_source_reports_no_data_not_a_default) · fired (action rows: 1.5 s `--accent-soft` wash then mono "Fired 18:41" replaces the button) |
| Expand | inline accordion for every row. Primary: `:root{interpolate-size:allow-keywords}` + `details::details-content{height:0;overflow:clip;transition:height var(--t-open) var(--ease-out),content-visibility var(--t-open) allow-discrete} details[open]::details-content{height:auto}`. Fallback when `!CSS.supports('interpolate-size','allow-keywords')`: on `toggle`, measure `scrollHeight`, `body.animate([{height:0,opacity:0},{height:h+'px',opacity:1}],{duration:320,easing:'cubic-bezier(0,0,.2,1)'})`, close 200 ms `--ease-in`. Many rows may be open (no `name`). Open ids persisted in `localStorage['gamma-open']` (try/catch) |
| Drawer exceptions | agent transcript from an Army node; a full day from the Journal calendar. Both via existing `openDrawer`. Everything else inline |
| Keyboard | `j`/`k` move focus between summaries; Enter/Space toggle (native); `o` opens the focused row's source in the drawer; `e` expand group, `Shift+E` collapse; `f` fires the focused card (same confirm as the button); `/` chat; `t` theme; `?` shortcuts drawer; `g`-then-key + Cmd-K exactly as today. No animation on keyboard-initiated palette open/close (motion.md: 100+/day actions never animate) |
| Reduced motion | `@media (prefers-reduced-motion:reduce){:root{--t-fast:0ms;--t-base:0ms;--t-open:0ms;--t-wash:0ms}}` + no height transition; JS keeps `const RM=matchMedia('(prefers-reduced-motion:reduce)').matches` and `if(RM` guards (test_reduced_motion_is_honoured greps both) |
| Fire | `.row--act` adds the Fire button (28 px, `--accent-fill`, `--canvas` text, `:active{transform:scale(.97)}`) between source and chevron; client RTH check stays cosmetic; `gamma_cockpit_cards.py::_looks_dangerous` server denylist stays the gate, untouched |

### 4.1 Motion table (no motion library inlined; CSS + WAAPI; CountUp + confetti vendored)

| Moment | Moves | Timing | Reduced motion |
|---|---|---|---|
| Page load, the ONE orchestrated moment (graft: mission-control choreography) | stars fade in (0-300) -> orchestrator node rises (200-600) -> bento cells settle in 60 ms steps (400-800) -> beams power on (existing `beamin`, 800-1800) -> day-line cursor draws 00:00 to now via stroke-dashoffset (600) | 1.8 s total, `--ease-out` | stage per its 6 existing guards; cursor instant; nothing on rows ever |
| Hover row | background only | 120 ms `--ease-std` | kept |
| Expand row | height + opacity (opacity delayed 80 ms); chevron 180 | 320 open / 200 close | instant + 120 ms opacity |
| Figure changed (1 s poll / 30 s timer) | CountUp old -> new; one-shot `.wash` `--accent-soft` -> transparent | 240 / 600 ms | value set; single-frame wash |
| Verdict flip | dot scales .6 -> 1 + colour; body tint fades | 200 ms | colour only |
| Fire card | existing comet -> node flash -> toast | 900 ms existing | existing single-frame |
| Route change | View Transition crossfade, shared `view-transition-name` on the top bar | 200 ms | `::view-transition-*{animation:none}` |
| Theme toggle | colour transition on body/rows | 200 ms | instant |
| Cmd-K | opacity + scale .98 -> 1, origin top centre | 160 ms | opacity |
| Chat drawer | translateY(100%) -> 0 | 240 / 160 | instant |
| Buttons | `:active{transform:scale(.97)}` | 160 ms | kept |
| Celebration | canvas-confetti 80 particles [`--accent-fill`,`--pos-fill`,`--ink-1`] from the row that flipped | 1.2 s once | never; dot + wash is the signal |

Confetti fires on exactly two events, both observed IN-SESSION (previous payload seen RED/YELLOW, never from a cold load) and deduped in `localStorage['gamma-celebrated']`: (1) `D.gate.overall_verdict` -> GREEN; (2) any single arm's day P&L crosses +$100 (per-account target, CLAUDE.md), key = arm+date. Ambient motion budget = the Army stage only.

---

## 5. Tile map (every producer in RP §3; NEW keys built in `gamma_cockpit_tiles.py`, each try/excepted to `{"ok":False,"path":...}`)

Icon names are from the 59 on disk (`vendor/icons/`); substitutions from the direction's wish-list are marked (was: x).

| Group | Producer | Icon | Graphic | One-line state (template, real fields) | Expand | State file(s) | Fresh window | Payload key |
|---|---|---|---|---|---|---|---|---|
| Needs you | Action cards | `target` (was flag) | none | "{title}" / "{kind}, {why[0]}" | all why bullets, objective, done-when, source, Fire | cards builder | live | `cards` (existing) |
| Trading | Go-live gate | `gauge` | gauge(ci_lower vs 1.0, 0..3) | "{overall_verdict}. PF CI-lower {criteria.statistical.<ci_lower field>} vs 1.0, {n days}" | 3 gauges as-traded / ex-best-day / cost-adjusted; operational guards dots; reconciliation; prod_shadow (arm, window, days scored/min 20); disclosures label | `analysis/go-live-gate.json` (keys verified: `overall_verdict`, `criteria.{statistical,operational,reconciliation,behavioural,prod_shadow}`, `generated_et`, `disclosures`, `futures`) | 24 h | **NEW `gate`** |
| Trading | Positions | `layers` | rings(per-arm share, filled when open) | "Flat on all arms. {fills} fills net to zero" or "{arm} {side} {symbol} x{qty}, {pnl}" | per-arm equity, last close, fills, stale files; `/api/desk` stays authoritative live | `positions`, `glass` builders | live | existing |
| Trading | Money | `dollar-sign` (was circle-dollar-sign) | spark(last 30 daily net, gain/loss colour allowed) | "+$1,916 net, 42 days, 38% day win rate" | per-arm net table (per-desk test), best/worst day, fees, "Open journal" | `analysis/journal/calendar-data.json` | 24 h | existing `calendar`, `calendar_full` |
| Trading | Premarket prep | `sunrise` | dots(checks[].status) | "{verdict} at {ts_et time}. {len(checks)} checks, {len(reds)} red" | each check name/status/detail; falsifiable predictions as claims (test); reds | `automation/state/premarket-readiness.json` (verified: `ts_et`, `verdict`, `checks[12]`, `reds`) + today-bias | 24 h | **NEW `prep`** |
| Trading | EOD debrief | `moon` | bars(per-account filled) | "{Funnel verdict}. {TOTAL.filled} filled of {TOTAL.ENTER} ENTER, {n} arms" | funnel table per account (scrollable); why-each-arm table; Analyst verdict + rule-break count when present (quoted, never parsed for numbers) | `analysis/eod/{today}.md` between `<!-- QUANT:BEGIN -->` / `<!-- QUANT:END -->` (verified lines 1 and 135) | 24 h | **NEW `eod`** |
| Trading | Standup | `radio` (was mic) | none | "{mode upper} standup {generated_et time}. {focus}" | text body, markdown stripped (test); wants_shown as plain words | `automation/state/gamma-standup-latest.json` (verified: `mode`, `generated_et`, `text`, `focus`, `wants_shown`) | 24 h | **NEW `standup`** |
| Research | Kitchen | `flame` | meter(today_cost_usd_paid_tier, today_cost_cap_usd) | "{Alive/Down}, {idle/cooking}. {by_status.pending} queued, ${cost} of ${cap}" | current task id, recent_completed_top_10, model_ladder, by_status | `automation/state/kitchen-status.json` (verified keys) | 90 min (`STALE_MIN`) | existing `lanes.kitchen` |
| Research | Prospector | `radar` (was compass) | funnel(ideas, promoted, folded) | "{n} ideas this beat, {n} promoted, {n} folded" | latest ideas ledger rows | `analysis/prospector/state.json` | 24 h | existing `lanes.prospector` |
| Research | Shadow board | `hourglass` | heat(preregs by status bucket) | "{n} shadow clocks, {n} preregs, 0 armed" | live instruments with latest verdict line; prereg groups collapsed per status with counts ("no status field (49)" shown as such) | `SHADOW.md` parsed from headings (verified: `## Live shadow instruments`, `## Frozen preregs ... (95 non-terminal)`, 30+ `### bucket (n)` headings) | 24 h | **NEW `shadow`** (largest plumbing item, RP §3 #6) |
| Research | Watcher fleet | `eye` | heat(would_be_pnl_by_watcher sign) | "{n} watching, {total_observations} observations, best {top} +${v}" | table watcher / observations / would-be P&L sorted | `automation/state/watcher-summary.json` (verified: `graded_at`, `total_observations`, `would_be_pnl_by_watcher` 12 keys) | 24 h | **NEW `watchers`** |
| Research | Learning ledger | `book-open` | bars(windows.today) | "Today: {tasks} tasks, {keepers} keepers, {preregs} preregs" | today vs 7 d table; latest_verdicts with kind dot | learning-ledger.json | 24 h | existing `learning` |
| Research | Multi-symbol | `layout-grid` (was grid-3x3) | funnel(72, survivors, armed) | "Shadow. {survivors} of 72 survived, arm idle" | learning-report summary | multi-lane learning-report.json | 24 h | existing `lanes.multi` |
| Research | Futures | `trending-up` | dots(5 lanes) | "{live} of 5 lanes live, all shadow, 0 real fills" | per-lane health + `D.gate.futures` | futures/health.json | 24 h | existing `lanes.futures` (Q6 answer row links here; no duplicate body) |
| Rig | Guards | `shield` (was shield-check) | heat(tasks[] by tier) | "{verdict}. {len(tasks)} tasks watched, {len(problems)} problems, {len(repairs)} repairs" | problems + repairs verbatim; tasks table non-green first | `automation/state/task-state-guard.json` (verified: `ts_et`, `verdict`, `tasks[11]`, `problems`, `repairs`) | 6 h | **NEW `guards`** |
| Rig | Task lanes | `timer` (was calendar-clock) | dots(6 lanes worst state) | "{n} registered, {ready} ready, {disabled} disabled, {failed} failed today" | one line per lane (Trading / Premarket / EOD / Kitchen / Shadow / Guards) + nested `<details>` per lane listing its tasks (Open MCT tree, RP §2 #6). Never a flat 188-row list | `automation/state/SCHEDULED-TASKS.md` registry rows joined to `task-state-guard.tasks[]` by name (RP §6 Q2 resolved by joining; guard covers only 11 of 188 today, so unmatched rows show "not guarded") | 24 h | **NEW `tasks`** |
| Rig | Gym | `activity` | heat(audits[].verdict, 7 cells) | "{overall_verdict}. {len(audits)} audits, {len(stale_reruns)} rerun stale" | audit / source_file / verdict table; stale rerun tails mono | `automation/state/gym-scorecard-{today}.json` (verified: `overall_verdict`, `audits[7]`, `stale_reruns`); fallback newest file + stale flag | 24 h | **NEW `gym`** |
| Rig | Agents | `bot` (was users) | spark(events/hour, 24 pts) | "{running} running, {finished} finished today, fabrication {verdict}" | events table newest first, cap 45, scrollable | agent feed | live | existing `agents` |
| Rig | Activity | `list-checks` (was list) | meter(nearest shadow clock progress) | "{headline}" | shadow clocks w/ progress, recent ships, wants | whats-changed.json | 24 h | existing `activity`, `wants_full` |
| Rig | Orchestration / Desks | `network` | none | "{n} desks, {n} shared functions" | org SVG + allocation reasons + desks stat tiles (old views' bodies) | org/allocation/desks builders | build | existing `org`, `allocation`, `desks` |
| Stage | The Army | (stage, not a row) | star-field | feeds THE SENTENCE | n/a | live | 1 s | existing `army` |
| Band | Goal + Budget | `target` / `wallet` | ringBig + meter + spark | see §3 band 4 | old vAutonomy body | goal file, cost-meter.json (stale since 08-30: renders amber) | 30 min / 24 h | existing `goal`, `autonomy`, `cost_meter` |
| Tab | Journal | `calendar` | month grid | "BOOK net +$X over N days" | day drawer | calendar-data.json | 24 h | existing |
| Tab | Answers (7) | per answer | verdict dot | answer text | detail, means, sources | build_answers() | per source | existing `answers` |

Controls/chrome icons: `pause play refresh-cw sun moon chevron-down chevron-right x search` (all on disk). "?" and "⌘K" render as keycap TEXT (keyboard hints, not icons), which sidesteps the missing `command`/`circle-help` icons. A build-time assertion in `gamma_cockpit_vendor.py` fails loudly if any icon name referenced by a tile is absent from `MANIFEST.md` (graft #6).

New payload keys (9): `gate prep eod standup shadow watchers guards tasks gym`. Each = `{ok, path, stamp_et, ...fields}`; ages client-side only. Each lands in all three consumers (OUT_HTML, COMPANION_HTML, COMPANION_JSON).

---

## 6. Vendor manifest (all files ALREADY under `setup/scripts/vendor/`; nothing new to download)

| Inlined into the page | Bytes | Licence | How |
|---|---|---|---|
| `Inter-Regular/Medium/SemiBold.woff2`, `JetBrainsMono-Regular.woff2` | 93,556 | OFL-1.1 | `vendor_assets.font_face_css()` -> `<style>` in `<head>` |
| `openprops.sizes.min.css`, `openprops.easings.min.css`, `openprops.borders.min.css` | 8,745 | MIT | `vendor_assets.css([...])` before the token block |
| `countup.umd.js` 2.8.0 | 6,077 | MIT | `vendor_assets.js(["countup.umd.js"])` before the app JS |
| `confetti.browser.js` 1.9.3 | 24,906 | ISC | same |
| Lucide icons (about 30 of 59) | ~14,000 | ISC | `vendor_assets.icon(name)` into `ICONS={}` in `gamma_cockpit_vendor.py`; 16x16, stroke 1.5, `currentColor` |
| Radix CSS files | 0 inlined | MIT | hex values copied into the tokens; files stay on disk for provenance + the light/dark parity test |
| **`anime.umd.min.js` 4.5.0** | **0 inlined** | MIT | **NOT inlined this pass.** 118,043 B = 57% of the CSS+JS budget for a motion vocabulary CSS + WAAPI already covers. Stays vendored; revisit only if a timeline need appears |

Inlined non-font total about 54 KB against the 250,000 B cap (headroom about 196 KB once anime is excluded; the MANIFEST total of 207,429 B counts anime). Page grows by roughly +150 KB (fonts + libs + new payload keys) on a 758 KB file that is 77% baked JSON (RP §4.6): **the redesign does not shrink the file and this spec does not promise it will.** If size matters more than type, fonts are cut first (system stack fallback is declared).

Wiring rule: `gamma_cockpit_ui.py` calls `vendor_assets` at render; `vendor_assets.py --check` runs in `test_gamma_cockpit_vendor_2026_09_03.py` so a missing or resized file fails the suite (C7: silent success is failure). `test_no_external_resource_tags` stays green (data: URIs are not external).

---

## 7. Module plan

| Module | Status | Owns | Ceiling |
|---|---|---|---|
| `setup/scripts/gamma_cockpit_ui.py` (620) | REPLACED CSS, kept API (`CSS`, `render()` shape, docstring keeps the word "traffic-light") | tokens dark+light, alias block, ban-list CSS, row/group/band/stage/topbar/drawer styles, `@font-face` via vendor, `prefers-reduced-motion` block, exact substring `.chip.ok .dot{background:var(--pos)}` retained | 800 |
| `setup/scripts/gamma_cockpit_vendor.py` | NEW | `ICONS` dict, `vendor_head()` (fonts + Open Props subset + token CSS order), `vendor_scripts()` (countUp + confetti), icon-manifest assertion | 400 |
| `setup/scripts/gamma_cockpit_tiles_js.py` | NEW | `tileRow()`, `groupRows()`, 9 `gfx*` functions, `paintAge` hook for rows, expand primary+fallback, open-state persistence | 800 |
| `setup/scripts/gamma_cockpit_command_js.py` | NEW | `vCommand()`, the sentence, day-line, Goal/Budget band, group composition, theme bootstrap/toggle, keyboard map j/k/o/e/f/t, confetti triggers, load choreography scheduler | 800 |
| `setup/scripts/gamma_cockpit_tiles.py` | NEW | 9 payload builders (`gate prep eod standup shadow watchers guards tasks gym`), `SHADOW.md` parser, SCHEDULED-TASKS join, `build_tiles()` returning the 9-key dict | 800 |
| `setup/scripts/gamma_cockpit_views_js.py` (556) | EDITED | `vOverview/vDesks/vOrch/vEngine/vAgents/vActivity` become thin wrappers that call `vCommand()` then scroll+open the matching row; `vJournal` re-skin; `vAnswers` uses `tileRow`; `srcRow()`, `health()`, `agoOf()`, `paintAge()`, `deskDrawer/dayDrawer/answerDrawer` kept by name | 800 |
| `setup/scripts/gamma_cockpit_autonomy_js.py` (283) | EDITED | `vAutonomy()` kept by name; body becomes the Goal band's expansion content (`goalBody()`) | 800 |
| `setup/scripts/gamma_cockpit_js.py` (341) | EDITED | `VIEWS[]` adds `command` (+ all old ids kept), `PRIMARY=['command','autonomy','journal','answers']` with `autonomy` flagged alias; palette `PAL[]` kinds untouched; `route(want)` signature and `a.onclick=e=>{e.preventDefault();route(v.id)` literal kept | 800 |
| `setup/scripts/gamma_cockpit_army_js.py` (1115) | DELETE-ONLY | remove the cards rail render + its styles; move controls markup into the stage header; zero additions | must shrink |
| `gamma_cockpit_cards_js.py`, `gamma_cockpit_chat_js.py`, `gamma_cockpit_cards.py`, `gamma_cockpit_army.py`, `gamma_cockpit_data.py`, `gamma_cockpit_org.py`, `gamma_lanes.py` | KEPT | `fireCard()`, chat SSE session, `_looks_dangerous`, army poll, feeds | untouched |
| `setup/scripts/gamma_home.py` (729) | EDITED (+ about 12 lines) | `from gamma_cockpit_tiles import build_tiles`; `payload.update(build_tiles())` inside its own try/except; footer size line | if > 800, move payload assembly into `gamma_cockpit_tiles.py` |
| `backtest/tests/test_gamma_cockpit_tiles_2026_09_03.py` | NEW | 9 builders return `ok:False` + path when file missing; no "undefined"/"None" in sentences; SHADOW.md fixture parses 95 non-terminal preregs; payload carries all 9 keys; every `--` token on `:root` also defined under `[data-theme="light"]`; ban-list grep (`box-shadow` count <= 3, no `#000`, no `—`/`–` in Gamma-authored JS/py string literals); icon names exist in MANIFEST | n/a |

**Preserved by name (tests grep for these exact strings):** `id:'overview'..'activity'`, `const RENDER={`, `vOverview vDesks vOrch vJournal vAnswers vActivity vAutonomy`, `autonomy:vAutonomy`, `label:'Autonomy'`, `function route(want)`, `deskDrawer dayDrawer answerDrawer openDrawer closeDrawer`, `'View' 'Desk' 'Agent' 'Answer' 'Day'`, `function srcRow(`, `D.stale_hours`, `D.calendar_scale` + `clamp` + `max_abs`, `function health(`, `.chip.ok .dot{background:var(--pos)}`, `traffic-light`, `prefers-reduced-motion`, `const RM=matchMedia('(prefers-reduced-motion:reduce)').matches`, `if(RM`, `tabular-nums`, `function agoOf(`, `function paintAge(`, `setInterval`, `.age`, `Date.now()`, `D.built_at_et`, the word "Autonomy" in rendered HTML, `[object Object]`/`undefined` absent from the `const D=` blob. Payload contract: OUT_HTML == COMPANION_HTML byte-identical; COMPANION_JSON separate.

---

## 8. Work breakdown: 6 parallel Sonnet builders on disjoint files

Each builder opens with "worker-tier: run /model sonnet first", reads §1's grep table and re-runs it, and reads the test files named in its row BEFORE editing.

| WS | Owner files | Inputs | Outputs | Acceptance |
|---|---|---|---|---|
| **A. Tokens + vendor** | `gamma_cockpit_ui.py`, `gamma_cockpit_vendor.py` (new), `test_gamma_cockpit_vendor_2026_09_03.py` (new) | §2, §6, `vendor_assets.py` API, `MANIFEST.md` | dark+light tokens with the alias block; ban-list CSS; fonts/OpenProps/countUp/confetti inlined; ICONS dict; theme bootstrap `<head>` script honouring `localStorage['gamma-theme']`, `?theme=`, `prefers-color-scheme` | `pytest backtest/tests/test_gamma_cockpit_2026_08_20.py` green; `vendor_assets.py --check` exit 0; `grep -c "box-shadow" ui.CSS <= 3`; light/dark parity test green |
| **B. Payload builders** | `gamma_cockpit_tiles.py` (new), `test_gamma_cockpit_tiles_2026_09_03.py` (new), `gamma_home.py` (import + update only) | §5 state files (read each one; confirm the exact `criteria.statistical` field for CI-lower before templating) | 9 keys in all three consumers | new test file green; `python setup/scripts/gamma_home.py --quiet` exits 0; `payload.json` has all 9 keys; deleting any one state file yields `ok:False` with a path, never a crash |
| **C. Row component + graphics** | `gamma_cockpit_tiles_js.py` (new) | §4 | `tileRow`, `groupRows`, 9 `gfx*`, expand primary + WAAPI fallback, persistence, keyboard j/k/o/e | unit smoke: render a fixture spec for each `gfx*` in a headless page via `cockpit_screenshot.py --tag gfx`; both expand paths screenshotted (force fallback via a `?nointerp=1` flag) |
| **D. Command view + choreography** | `gamma_cockpit_command_js.py` (new), `gamma_cockpit_js.py` (VIEWS/PRIMARY/theme key), `gamma_cockpit_autonomy_js.py` (goalBody) | §3, §4.1, WS-C's component API (agree signatures in the first hour: `tileRow(spec)`, `gfx*(data)->svgString`) | sentence, day-line, stage frame, Goal/Budget band, 4 groups, load choreography, confetti triggers, theme toggle | `test_gamma_home_autonomy_view_2026_09_03.py` green; screenshots `after-command-1600x950-{dark,light}.png` |
| **E. Old views -> rows, Army delete-only** | `gamma_cockpit_views_js.py`, `gamma_cockpit_army_js.py` | §7 | old renderers as wrappers; Answers as rows; Journal re-skin; cards rail removed from stage; controls row | `test_every_view_is_defined_and_navigable`, `test_drilldowns_exist`, `test_calendar_ramp_*` green; `wc -l gamma_cockpit_army_js.py` < 1115 |
| **F. Review loop** (runs after A-E merge) | none (read-only + screenshots) | `setup/scripts/cockpit_screenshot.py --tag after --views command,journal,answers --sizes 1600x950,1440x900` in dark and light | blind critique JSON (same rubric as the baseline: score, wall_of_text, findings by severity); legibility sweep (`font-size` < 12 px anywhere visible = fail; contrast `--ink-3` on `--canvas` >= 4.5:1); `design:accessibility-review` pass (RP §5 #10) | score >= 7 from two independent critics, else findings go back to the owning WS as a list; full `pytest backtest/tests/test_gamma_cockpit* test_gamma_home* test_cockpit_feeds* test_companion*` green |

Merge order: A -> (B, C in parallel) -> D -> E -> F. WS-C and WS-D negotiate the `tileRow` spec shape in writing (a 10-line JSON example committed in `gamma_cockpit_tiles_js.py`'s docstring) before either writes rendering code.

---

## 9. Risks + revert line

| Risk | Mitigation |
|---|---|
| `::details-content` + `interpolate-size` need Chromium 131+; the companion's engine version is UNVERIFIED | WAAPI fallback behind `CSS.supports`; WS-C screenshots both paths |
| Token rename breaks army_js / chat_js var references | alias block in §2.1 keeps every referenced name (`--tx-*`, `--s*`, `--acc`, `--st-live`, `--bd*`, `--bg-*`, `--pos/neg/warn(-dim)`, `--ring`, `--topline`, `--r-md`) defined; a test asserts each name in the grep list resolves |
| Greppable test anchors on old names | listed in §7; builders keep anchors rather than editing tests; any deliberate test change is labelled in the commit |
| Light theme is net-new (RP's `[data-cvd]` claim was false) | budgeted as WS-A work; parity test; `cockpit_screenshot.py` light capture must NOT be labelled UNVERIFIED after WS-A |
| `gate` CI-lower field path unverified inside `criteria.statistical` | WS-B reads the JSON before templating; sentence falls back to "{verdict}. see expansion" if the field is absent, never a fabricated number |
| SHADOW.md parser depends on `obsidian_vault_sync.py` heading format | fixture test pins today's format; row renders "NO DATA, parser found 0 sections in SHADOW.md" rather than "0 clocks" |
| Task lanes join: guard covers 11 of 188 tasks | unmatched rows render "not guarded" explicitly; never inferred green |
| Goal band and Needs-you both show the goal's next item | the band owns it; WS-D filters `cards[]` where `kind=='goal'` and id matches the band's item (`test_cards_active_goal_picks_first_open_item` stays) |
| Em-dash removal vs `test_briefing_repeats_exactly_on_identical_state` | briefing templates left alone this pass; only NEW copy obeys 9.G |
| Confetti re-fires on a cleared profile | requires in-session flip observation, never cold load |
| Page grows ~+150 KB | stated in §6; fonts first to cut |
| Module ceilings | new code only in new modules; army_js delete-only; gamma_home gains <= 12 lines |
| cost-meter.json stale (2026-08-30) | Budget band shows amber age and the stale date; not this spec's bug, but the first thing J will see: WS-F notes it in the critique so it is not mistaken for a render fault |
| UNVERIFIED in a browser until WS-F | no "done" claim before after-*.png exist and are compared against `analysis/home/screens/before-*.png` (OP-33) |

**Revert line:** all work lands as one branch `cockpit-quiet-command`; `git revert <merge-sha>` restores the 2026-08-30 page byte-for-byte because `analysis/home/index.html` and `gamma-companion/public/cockpit.html` are regenerated from the reverted modules by `python setup/scripts/gamma_home.py --quiet`. Vendor files stay (already committed, harmless). No state file, no params, no scheduled task is touched by this work.
