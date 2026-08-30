# GOAL: COMMAND-CENTER-2026-08-30

> J verbatim (2026-08-30 13:24 ET): *"review the last response from fable and scrutinize
> it and then review and then build it out, i want to be wow'd when I return /goal
> ultra code on. go out on the web and find claude website helper things people are
> doing to build epic sites and make my dashboard like single pane of glass ai trading
> command center"*

## THE SCRUTINY THAT OPENED THIS (measured, not asserted)

The prior goal's shipped claims were independently re-verified and HOLD: 168 visible text
nodes at 1600x950, zero under 12px, page scroll false, zero raw commit codes in the feed,
humanizer live, org rebuilt in HTML, beams carrying real pulses.

What it did NOT do, and what J is actually asking for:

    payload sections available : 18
    rendered on the desk       : 3   (army, autonomy, activity)
    dropped                    : 15  (hq, positions, briefing, allocation, calendar,
                                      calendar_full, cost_meter, desks, engine_room,
                                      org, agents, thinking, cards, answers, wants_full)

Every dropped section is the TRADING half. The page currently shows no equity, no P&L, no
position, no bias, no arm roster — `hasEquity:false, hasPosition:false` measured in the
live DOM. It is an excellent agent-orchestration console wearing the name of a trading
command center. That is the whole of this goal.

## DONE-WHEN
Falsifiable, asserted against the RUNNING page at 1600x950 and 1440x900:
- (a) TRADING IS ON THE GLASS: the DOM contains, without a click — book equity, today's
  P&L, position/flat state, today's bias, and a per-arm roster. Asserted by regex over
  `document.body.innerText`, not by eye.
- (b) NO REGRESSION on what the last goal won: zero visible text nodes under 12px,
  `document.body.scrollHeight <= innerHeight+1`, zero raw commit prefixes / guard codes /
  absolute paths in any glanceable row.
- (c) PAYLOAD COVERAGE: >= 12 of the 18 payload sections reachable from the one page
  (visible or one interaction away, counted in the DOM).
- (d) EVERY NUMBER IS SOURCED OR ABSENT: no fabricated or placeholder figure; a missing
  input renders `miss()` naming the file it wanted. Asserted by grepping the render path
  for fallback literals.
- (e) MOTION ENCODES STATE: every animation on the page maps to a real state change
  (working / alive / P&L direction / message in flight). No decorative loops.
- (f) RESEARCH-GROUNDED: the build cites the workflow's verified findings; the dossier in
  COCKPIT-DESIGN-SPEC.md gains the new entries. Design pass without fresh references is a
  violation (memory: design-starts-at-external-reference).
- (g) It survives an adversarial review pass by agents that did not build it.
A null result is reported as a null.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> ~2026-09-29**: app/companion surface only. No trading-path
  file is touched by this goal. Read-only against every trading state file.
- Green/red are RESERVED for P&L. State uses cyan/amber/violet.
- Text never inside a scaled SVG viewBox.
- Every fire records `conductor_outcome.py record`.
- Any Agent/Workflow fan-out passes `model:"sonnet"` explicitly (opus only for synthesis
  and adjudication).
- STATUS.md gets a line at OPEN and CLOSE only.
- Never `/loop /gamma-goal`.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [ ] C1 — Trading data slice: `setup/scripts/gamma_glass.py` — book equity + today/WTD
  P&L per arm, flat-or-open, bias + last verdict + why, arm roster with fills, engine
  cadence + last tick. READ-ONLY, fast (<0.5s), served fresh on /api/desk beside
  army/autonomy/lanes. DONE-WHEN: `/api/desk` returns a `glass` key with all five groups
  and the endpoint still answers under 3s.
- [ ] C2 — The trading strip: always-visible top band carrying equity, day P&L, position
  state, bias. DONE-WHEN: DONE-WHEN (a) regex passes.
- [ ] C3 — Equity sparkline + P&L calendar heat strip from `calendar`/`calendar_full`,
  vanilla SVG/CSS-grid, per the research spec. DONE-WHEN: renders real per-arm days and
  matches calendar-data.json for a spot-checked date.
- [ ] C4 — Arm roster + engine room: the 5 fleet arms with their real fill counts and
  last close, engine cadence and last verdict. DONE-WHEN: matches positions.arms.
- [ ] C5 — Motion + polish pass from the verified findings; dossier updated with new
  entries. DONE-WHEN: DONE-WHEN (e) + (f).
- [ ] C6 — Adversarial review fan-out (agents that did not build it) + fix what they
  confirm. DONE-WHEN: DONE-WHEN (g), findings triaged, real ones fixed.
- [ ] C7 — Final assertion sweep at both sizes + screenshot to J. DONE-WHEN: (a)-(e) all
  green in one run.
- [B-J] Firebase credential, admin/multi-user boundary, `/` root repoint — carried from
  the prior two goals, still J's.

## J-DECISIONS
- Whether `/` becomes this app (would repoint the installed phone PWA).
- Firebase credential + friends access, which needs token verification built first.

## PROGRESS LOG
- 2026-08-30 13:2x ET — Opened after scrutinizing the prior turn. Prior goal closed with
  its gap stated. Research workflow launched (6 lenses, adversarial verify, opus synthesis).

## HONEST STATE
Scrutiny done and quantified. Research in flight. No build work shipped yet under this goal.
