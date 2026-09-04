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
- **J 2026-09-03 23:10 ET: "remember visuals and designs and styling and animations."** Density and hierarchy are table stakes; the bar is VISUAL. Every spec §4.1 motion moment must exist in code AND be exercised in a live browser (expand, hover, theme toggle, load choreography, live count-up), with the check quoted. Headless stills do not prove motion.
- **J 2026-09-03 19:30 ET: "do not honour any of my previous designs ... maybe the plumbing."** The prior spec's and current page's LOOK are not inputs; plumbing only survives. Design from the research pack's references + the installed design skills.
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
- [x] R1 (DONE 19:25 ET: 52 agents, pack at analysis/deep-research/COCKPIT-REDESIGN-RESEARCH-2026-09-03.md, 197 lines; key finds: prior spec markdown/infra/COCKPIT-DESIGN-SPEC.md exists, 0 light-theme CSS, page 77% baked JSON, 20-tile inventory w/ 6 needing new plumbing) — RESEARCH PACK (workflow): free design plugins/skills (marketplaces + GitHub), open-source
  UI kits usable without a build, motion/chart/icon libraries (license, size, UMD, offline), a
  10-item reference gallery with what to borrow from each, the repo inventory of every producer
  that deserves a tile, and an audit of the current page's tokens/constraints. Written to
  `analysis/deep-research/COCKPIT-REDESIGN-RESEARCH-2026-09-03.md`. DONE-WHEN (a) inputs.
- [x] R2 (DONE 19:50 ET: baseline panel 3/2/2 all 'wall of text'; 3 directions, judges 26.9 linear-minimal vs 25.1 mission-control; spec markdown/specs/COCKPIT-DESIGN-SPEC-2026-09-03.md 'Quiet Command' — Radix gray-dark ladder + cyan accent rhyming with the Army stage, 56px <details> rows with a 160px graphic spine, hero rings, choreographed load, light theme net-new) — DESIGN DIRECTION (workflow): three independent directions (palette/type/layout/motion/
  tile system/IA) scored by a judge panel against J's brief; winning spec written to
  `markdown/specs/COCKPIT-DESIGN-SPEC-2026-09-03.md` with the component list and per-tile data
  contracts. Baseline critique score of the current page recorded first. DONE-WHEN (d) baseline.
- [x] R3 (VERIFIED by Fable: 3 design skills installed under ~/.claude/skills; vendor_assets.py --check 106 ok / 0 failed; 23 tests green; CSS 57 KB + JS 149 KB + icons 26 KB + fonts 94 KB all MIT/ISC/OFL, GSAP excluded; commit 82184a74; inliner wiring into gamma_cockpit_ui.py is R4's job) — INSTALL + VENDOR: install the chosen free skills/plugins; vendor the chosen libraries
  under `setup/scripts/vendor/` with `MANIFEST.md`; wire an inliner into `gamma_cockpit_ui.py`.
  DONE-WHEN (a).
- [x] R4 (VERIFIED by Fable 22:20 ET: gamma_home.py builds, index.html 1,087,398 B; cockpit_dom_check overflow_x=False tiles=31 small_text=0; 223 guard tests green; Command view = sentence + day-line + Army stage + goal/budget band + Needs-you/Trading/Research/Rig row groups with graphics; light theme wired; checkpoint commit 93b36e6e, pushed) — BUILD (workflow, parallel builders on disjoint modules): token system + shell/nav,
  Command view (Army + Autonomy merged), tile system + expand drawer, per-producer tiles with
  data readers (new payload keys in `gamma_home.py`/`gamma_cockpit_data.py`), charts/motion.
  DONE-WHEN (b)(c).
- [~] R5 (3 blind rounds 5/4/4 -> 6/5/4 -> 5/6/5, median 5; plateau = first-viewport density + hero hierarchy + light stage; Fable directed pass running) — REVIEW LOOP (workflow): screenshot both viewports × both themes; blind critique panel;
  accessibility + legibility sweep (12 px, overflow, reduced motion); console errors; fix → re-shoot
  until median ≥7. DONE-WHEN (d)(e).
- [ ] R5b — VISUAL + MOTION POLISH (workflow): audit every §4.1 motion row against the shipped JS/CSS (grep, not memory); implement what is missing (page-load choreography: stars -> orchestrator rise -> bento settle -> beams power-up -> rings fill -> figures count up; row expand height+opacity; hover surface; verdict-flip dot pulse + body tint; theme crossfade; day-line cursor breathing; live pulse on the stage over http); graphics pass (rings/sparks/heat get gradient strokes, end-point dots, faint grids); exercise expand/hover/theme/j-k keys in the in-app browser at localhost:4317 and quote console = 0 errors; capture two stills mid-animation via a --delay flag on cockpit_screenshot.py; blind panel re-scores with a MOTION lens. DONE-WHEN (d) + J's 23:10 emphasis.
- [ ] R6 — SHIP: guard tests green, commit with one-line revert, STATUS entry, before/after
  screenshots to J, memory note. DONE-WHEN (f).
- [ ] R7 — Carried from GOAL-GAMMA-AUTONOMY A6: quote the first goal-driven conductor outcome row
  (task_id names a goal QUEUE item) once the 00:10 ET fire has run.

## J-DECISIONS
- None. Revoke = `git revert <sha>`; the previous page is one revert away.

## PROGRESS LOG
- 2026-09-03 23:20 ET — Stop-hook continuation 2/3, session 76844c47 (non-SPY lane, not this goal's owner). **R5b PARTIALLY DONE: shipped the one item that does not collide; held the rest.** R4 has landed (`93b36e6e`) but R5's directed pass is being written RIGHT NOW — verified cold, 6 cockpit files dirty and 0 committed since 93b36e6e, newest write `gamma_cockpit_ui.py` at **23:06 ET, ten minutes before this fire**, plus a brand-new untracked `gamma_cockpit_ui_theme.py` at 23:05 ET. Every remaining R5b item (§4.1 motion audit, implement missing motion, graphics pass, browser exercise, re-score) edits exactly those files — a direct integrator collision (C34).
  **SHIPPED `9baf5238`: `--delays-ms` on cockpit_screenshot.py**, the R5b line item 'capture two stills mid-animation via a --delay flag'. That file was clean, so it could land. Chrome's `--virtual-time-budget` IS the clock, so a mid-animation still is a SMALLER budget, not a sleep; with `--run-all-compositor-stages-before-draw` the same delay gives the same frame every run. Verified: no flag = byte-identical single shot; non-integer and 0 both rejected loudly with exit 1; `--delays-ms 300,900,2000` produced 4 captures with 4 DISTINCT sha256 frames, 0 failures; eyeballed 300ms shows Army cards semi-risen and a beam mid-power-up, so it samples the choreography rather than a ticking clock digit.
  **LEAD FOR WHOEVER RUNS THE REST OF R5b (a lead, NOT a verdict):** 300ms and 6000ms look ~95% alike and the goal ring is a partial arc in BOTH — it never fills. That is consistent with 'the choreography is barely present', which is R5b's own suspicion. But virtual-time capture can FAST-FORWARD CSS animations instead of sampling them, so an absent-looking animation in a virtual-time still is not proof it is absent on a real machine. R5b's own 'exercise it in the in-app browser at localhost:4317' is the instrument that settles it. Screens are gitignored; the tool is the artifact.
- 2026-09-03 22:17 ET — Stop-hook continuation 1/3 reached session 76844c47 (the non-SPY expansion session, NOT this goal's owner). **R5 NOT STARTED, and it is not a judgement call: R4 is being written to disk right now by the owning session.** Verified cold, not assumed: `git status` shows 12 cockpit files dirty and ZERO committed (6 modified — army_js, autonomy_js, cards_js, cockpit_js, ui, views_js, gamma_home; 5 untracked — command_js, producers_js, tiles, tiles_js, vendor), and the newest write is `gamma_cockpit_ui.py` at 2026-09-03 20:07:55 -0600 = **22:07 ET, ten minutes before this fire**. The last cockpit commit is still `3eda8574` (the spec). R5 is screenshot -> blind critique -> fix -> re-shoot; running it against a half-integrated build critiques a state that will never exist, and any fix would collide with the owning session's integrator on the same files (C34). Same call, same reason, as the 19:03 ET entry above. No file in this goal's lane was touched. Owning session continues; R5 unblocks when R4 commits.
- 2026-09-03 19:03 ET — Stop-hook continuation 3/3 reached session b6eea006 (the money-leak/security session, NOT this goal's owner). **R2 SKIPPED, not started, for two independent reasons:** (1) it is blocked on R1, which is `[~]` wip in the owning session (that session committed the goal switch `19d87d7a` at 18:57 ET, four minutes before the hook fired) -- starting R2 here would clobber an in-flight lane; (2) R2 is a design-direction call (palette/type/layout/motion), and doctrine routes aesthetic judgement away from Claude and requires every UI pass to open from FRESH EXTERNAL REFERENCES (J, 8th ask, 2026-08-30) -- which is precisely what R1's research pack is for. Doing R2 before R1 lands would iterate on our own output, the exact anti-pattern. No files in this goal's lane were touched. Owning session continues.
- 2026-09-03 18:55 ET — Opened by Fable from J's directive (ultracode on). Placed at the top of
  the ladder; GOAL-GAMMA-AUTONOMY closed with its A6 carried here as R7.
- 2026-09-03 18:55 ET — opened by goal_autopilot (first real close+open of the ladder: GAMMA-AUTONOMY closed as fully terminal)
- 2026-09-03 18:58 ET — R1 research workflow launched (6 sweeps, 2 refuters per recommended asset, critic, writer); session 42-98 owns R1–R6.
- 2026-09-03 19:20 ET — J correction mid-run: prior designs not to be honoured (plumbing only). Design workflow stopped, brief corrected, resumed from cache (baseline critics kept).

- 2026-09-03 19:26 ET — Stop-hook continuation 3/3: R4 (build) is blocked on R2 (design spec workflow, running with the corrected brief) and R3 (vendoring agent, running). Build workflow script is drafted (planner -> parallel builders -> integrator -> screenshot critique loop to median >= 7) and launches on the spec. Screenshot instrument committed bbf34333.

- 2026-09-03 19:52 ET — R4 build workflow launched (planner -> parallel Sonnet builders on disjoint files -> integrator -> screenshot critique loop, target median >= 7). Deviation from spec §9: NO feature branch — this is a shared checkout with peer sessions committing to main (C34 scar); work lands as scoped commits on main, revert = `git revert <sha>` per commit. Spec + research pack committed 3eda8574.

## HONEST STATE
Queued. Nothing built. Research workflow launching.
