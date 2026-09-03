# GOAL: COCKPIT-REDESIGN-2026-09-03

> J verbatim (2026-09-03 18:50 ET): *"re design the page http://localhost:4317/cockpit.html#autonomy
> its just a wall of text. i like visuals, sleek minamilist design. expandable tiles. combine it with
> the 'army' page since the autonomy is the army. use the army page as the style ref. redesign the
> whole page. this is a claude made webpage. we used no real design skills no real design templates
> or free things you can go out online and find like i asked for several times. new /goal is to find
> the best free web design plugins and utilize their skills to take our page from a 2/10 to a 7 or 8
> out of 10. it needs a complete overhaul to be stylish intuitive and look cool, remember big on
> visuals and animations etc ... this is literally the command center it needs to be my daily driver
> and look great but also it needs to be reviewed for more things like adding in the eod and morning
> preps and debriefs and the kitchen and all other things to visbility even if its just a tile or
> like a row with some graphics and we can click to expand or something."*

## WHY THIS IS THE 8th ASK, NOT THE 1st
Memory `feedback_design_starts_at_external_reference_2026_08_30`: every UI pass must open with
fresh external references and real design assets, never iterate Claude's own output. The
2026-08-29/30 cockpit goals (COCKPIT-BUILD, DAILY-DRIVER-GLASS, DESK-LEGIBILITY) improved
legibility but the page is still hand-rolled CSS with no design system, no motion library, no
icon set, and an Autonomy tab that is a wall of text (verified 2026-09-03 18:30 ET, J's words).

## DONE-WHEN
Falsifiable, each checked by a command or screenshot quoted in the PROGRESS LOG:
- (a) **Real design assets, not hand-rolled.** The generated page inlines at least: one vetted
  free (MIT/OFL/free-for-all) icon set, one motion library, one charting/sparkline library, and a
  documented token system adopted from a named open-source design system — every one listed in
  `setup/scripts/vendor/MANIFEST.md` with license, version, size, and source URL. Free design
  skills/plugins found in the research pass are installed (or their guidance vendored as a skill)
  and named in the manifest.
- (b) **One command surface.** Autonomy and Army are ONE default view ("Command"): the army graph
  (orchestrator → sessions → workers, live pulse over http) sits beside the active goal, next
  move, budget, and learning ledger — with no paragraph of prose on the glass; details live behind
  expand/drawer.
- (c) **Expandable tiles for everything that runs.** Every producer in the inventory (premarket
  prep, standups AM/EOD, EOD summary + debrief, analyst, kitchen, prospector, gym scorecard,
  shadow/prereg board, futures desk, multi-symbol lane, guards/tests, scheduled-task health,
  gate, journal calendar, watcher fleet, budget) is a tile with a graphic (ring/spark/timeline/
  heatmap/pulse) + freshness + one-line state, and click-to-expand detail. Missing data reads
  NO DATA, never a default.
- (d) **Judged ≥7/10 by a blind panel.** Three independent design-critique agents score the
  final screenshots (1600×950 and 1440×900, light and dark) against J's brief using the
  `design:design-critique` rubric; median ≥7 with no "wall of text" finding. The pre-redesign
  page is scored by the same panel first so the delta is on record.
- (e) **Nothing lost, nothing slow.** Every existing behaviour survives (card fire buttons +
  guard, chat pane, Cmd-K palette, journal calendar, answers, 1 s army poll on http, file://
  fallback), all cockpit/home guard tests green plus new ones, page builds in <5 s, 0 console
  errors, 0 visible text <12 px, no page-level horizontal scroll, `prefers-reduced-motion`
  honoured.
- (f) **Committed + on the surface.** `Gamma_Home` regenerates it every 30 min; STATUS entry at
  open and close; J gets a before/after screenshot pair.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 → 2026-10-30**: presentation + state readers only; no trading-path
  file, no order path, no `params*.json`. Read-only over state.
- Zero build step stays: one Python generator → one self-contained HTML (`gamma_home.py`).
  Libraries are VENDORED (minified files under `setup/scripts/vendor/`, inlined at render) —
  never a runtime CDN dependency (the page must work from file:// offline). Each vendored file
  carries its license header.
- Design starts at external reference: the research pack + reference gallery are read before
  any CSS is written; the design plan names the system/kit each token and component is adopted
  from.
- Every `Agent`/workflow fan-out passes `model:"sonnet"` for hands; judgment (design direction,
  critique synthesis) stays top-tier.
- Every fire calls `python setup/scripts/conductor_outcome.py record ...`.
- `STATUS.md` line at OPEN and CLOSE only. Never `/loop`.
- Module ceiling 800 lines; new views get their own `gamma_cockpit_*_js.py` modules.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [~] R1 — RESEARCH PACK (workflow): free design plugins/skills (marketplaces + GitHub), open-source
  UI kits usable without a build, motion/chart/icon libraries (license, size, UMD, offline), a
  10-item reference gallery with what to borrow from each, the repo inventory of every producer
  that deserves a tile, and an audit of the current page's tokens/constraints. Written to
  `analysis/deep-research/COCKPIT-REDESIGN-RESEARCH-2026-09-03.md`. DONE-WHEN (a) inputs.
- [ ] R2 — DESIGN DIRECTION (workflow): three independent directions (palette/type/layout/motion/
  tile system/IA) scored by a judge panel against J's brief; winning spec written to
  `markdown/specs/COCKPIT-DESIGN-SPEC-2026-09-03.md` with the component list and per-tile data
  contracts. Baseline critique score of the current page recorded first. DONE-WHEN (d) baseline.
- [ ] R3 — INSTALL + VENDOR: install the chosen free skills/plugins; vendor the chosen libraries
  under `setup/scripts/vendor/` with `MANIFEST.md`; wire an inliner into `gamma_cockpit_ui.py`.
  DONE-WHEN (a).
- [ ] R4 — BUILD (workflow, parallel builders on disjoint modules): token system + shell/nav,
  Command view (Army + Autonomy merged), tile system + expand drawer, per-producer tiles with
  data readers (new payload keys in `gamma_home.py`/`gamma_cockpit_data.py`), charts/motion.
  DONE-WHEN (b)(c).
- [ ] R5 — REVIEW LOOP (workflow): screenshot both viewports × both themes; blind critique panel;
  accessibility + legibility sweep (12 px, overflow, reduced motion); console errors; fix → re-shoot
  until median ≥7. DONE-WHEN (d)(e).
- [ ] R6 — SHIP: guard tests green, commit with one-line revert, STATUS entry, before/after
  screenshots to J, memory note. DONE-WHEN (f).
- [ ] R7 — Carried from GOAL-GAMMA-AUTONOMY A6: quote the first goal-driven conductor outcome row
  (task_id names a goal QUEUE item) once the 00:10 ET fire has run.

## J-DECISIONS
- None. Revoke = `git revert <sha>`; the previous page is one revert away.

## PROGRESS LOG
- 2026-09-03 18:55 ET — Opened by Fable from J's directive (ultracode on). Placed at the top of
  the ladder; GOAL-GAMMA-AUTONOMY closed with its A6 carried here as R7.
- 2026-09-03 18:55 ET — opened by goal_autopilot (first real close+open of the ladder: GAMMA-AUTONOMY closed as fully terminal)
- 2026-09-03 18:58 ET — R1 research workflow launched (6 sweeps, 2 refuters per recommended asset, critic, writer); session 42-98 owns R1–R6.
## HONEST STATE
Queued. Nothing built. Research workflow launching.
