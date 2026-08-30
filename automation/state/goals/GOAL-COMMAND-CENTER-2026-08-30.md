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
- [x] C1 (VERIFIED: /api/desk returns `glass` with all 5 groups + calendar; 0.7s; arm nets cross-foot to the book to the cent) — Trading data slice: `setup/scripts/gamma_glass.py` — book equity + today/WTD
  P&L per arm, flat-or-open, bias + last verdict + why, arm roster with fills, engine
  cadence + last tick. READ-ONLY, fast (<0.5s), served fresh on /api/desk beside
  army/autonomy/lanes. DONE-WHEN: `/api/desk` returns a `glass` key with all five groups
  and the endpoint still answers under 3s.
- [x] C2 (VERIFIED: hasEquity/hasNet/hasPosition/hasBias/hasSPY all true in the live DOM; band 104px measured into --band) — The trading strip: always-visible top band carrying equity, day P&L, position
  state, bias. DONE-WHEN: DONE-WHEN (a) regex passes.
- [x] C3 (VERIFIED: 195 cells / 5 rows behind the NET cell + #/pnl deep link; 3 independent paths agree on 1814.86) — Equity sparkline + P&L calendar heat strip from `calendar`/`calendar_full`,
  vanilla SVG/CSS-grid, per the research spec. DONE-WHEN: renders real per-arm days and
  matches calendar-data.json for a spot-checked date.
- [x] C4 (VERIFIED: 4 arms with real equity/net/win-rate + engine mind with numbered blockers) — Arm roster + engine room: the 5 fleet arms with their real fill counts and
  last close, engine cadence and last verdict. DONE-WHEN: matches positions.arms.
- [x] C5 (VERIFIED: M1 keyframe-pair alternation proven flash-dn1->flash-dn2; roll writes truth before rAF; dossier R12-R19) — Motion + polish pass from the verified findings; dossier updated with new
  entries. DONE-WHEN: DONE-WHEN (e) + (f).
- [x] C6 (29 agents, 6 lenses, 23 raised / 21 confirmed / 2 refuted; ALL 21 fixed, incl. 2 criticals) — Adversarial review fan-out (agents that did not build it) + fix what they
  confirm. DONE-WHEN: DONE-WHEN (g), findings triaged, real ones fixed.
- [x] C7 (VERIFIED at 1600x950 AND 1440x900 in one run) — Final assertion sweep at both sizes + screenshot to J. DONE-WHEN: (a)-(e) all
  green in one run.
- [B-J] Firebase credential, admin/multi-user boundary, `/` root repoint — carried from
  the prior two goals, still J's.

## J-DECISIONS
- Whether `/` becomes this app (would repoint the installed phone PWA).
- Firebase credential + friends access, which needs token verification built first.

## PROGRESS LOG
- 2026-08-30 13:2x ET — Opened after scrutinizing the prior turn. Prior goal closed with
  its gap stated. Research workflow launched (6 lenses, adversarial verify, opus synthesis).
- 2026-08-30 14:04 ET — C1 PARTIAL: `gamma_glass.py` exists and produces all 5 groups
  (equity 23660.27, pnl net_all 1814.86, position unknown, bias HOLD, 4 arms) in 0.53s.
  Created `dashboard/app/api/desk/route.ts` shelling out to the script; tsc clean.
  UNVERIFIED: live /api/desk endpoint (dev server not running). Queue: mark C1 ~wip.

- 2026-08-30 ~14:0x ET — C1-C5 shipped and verified. Trading is on the glass: 217
  visible text nodes, ZERO under 12px, page scroll false, centre overflow 0. Found and
  fixed en route: 3 shape bugs in the data slice (pnl_net vs the payload's `n` alias, a
  missing `last` key, a fleet registry that is a list), the payload floor (baked payload
  had no `glass` so the band degraded with the companion down), a STALE-NUMBER bug where
  an rAF roll left the old figure on a trading cell, an invisible-from-state animation
  class of bug (now enforced by a stylesheet sweep), and a 12px floor held by ~30
  override rules that is now fixed at source. 86 guards green.

## HONEST STATE
C1-C5 shipped and verified in the running page. C6 (adversarial review by agents that did
not build it) is in flight. C7 is the final sweep.

Payload coverage against DONE-WHEN (c): the page now reaches glass (equity, pnl,
position, bias, arms, calendar), lanes, army, autonomy, activity — and calendar_full's
content is served through the glass slice. Sections still NOT surfaced: cards, answers,
desks, engine_room, org, agents, thinking, wants_full, cost_meter. Several are
duplicates of what the glass now shows (thinking == bias; desks/engine_room overlap the
lanes rail), but cards and cost_meter are genuinely absent and are honest gaps, not
oversights — recorded here rather than closed around.


## CLOSE (2026-08-30 ~14:35 ET)

DONE-WHEN, every item measured in the running page, both mandated viewports:

| # | criterion | 1600x950 | 1440x900 |
|---|---|---|---|
| a | trading on the glass (equity/net/position/bias/arms) | all true, 4 arms | all true |
| b | no regression: <12px type / page scroll / centre overflow | 0 / false / 0 | 0 / false / 0 |
| c | payload coverage >= 12 of 18 sections reachable | 14 reachable | same |
| d | every number sourced or absent | 0 raw rows, 0 fabrication guards failing | same |
| e | motion encodes state | M1/M2/M3/M6/M9/M10, keyframe-pair alternation proven | same |
| f | research-grounded, dossier updated | 51 findings / 17 verified, dossier R12-R19 | -- |
| g | survives adversarial review | 23 raised / 21 confirmed / ALL fixed | -- |

Nine commits. 132 guards green.

WHAT THIS GOAL ACTUALLY CHANGED: the desk went from rendering 3 of 18 payload sections to
carrying the whole trading state -- book $23,660, +$1,815 net over 39 sessions with its
equity curve, position, live tape, per-arm roster, the engine's verdict WITH the numbered
gates that blocked it, a P&L-by-session sheet behind the NET cell, and the decision queue
with its fire button. `hasEquity:false, hasPosition:false` this morning; both true now.

THE FINDINGS THAT MATTERED MOST were not the features:
* guard.js enforced the config freeze on only 2 of the 5 files it names -- the companion
  chat could have written heartbeat_core.py, risk_gate.py or fleet/* mid-freeze.
* The tape's "live" badge could never say stale (age_s is a hardcoded 0), so the page
  could claim the engine was watching the market while it was blind.
* Three regexes were silently dead from literal 0x08 bytes that every tool renders as
  "" -- including the one meant to stop a real failure reading as "did some work".
* An rAF number-roll could leave a STALE figure on a trading cell.
Each is now fixed AND guarded by a test that fails if it returns.

HONEST GAPS, recorded rather than closed around:
* cost_meter is still not on the page. It is real data and it is absent by choice --
  the rails were full and spend is not a glance-critical number.
* The org cards render other Claude sessions' chat TITLES, which reads oddly beside
  trading rows. Accurate, just not beautiful.
* The autofire loop's first real unattended fire is still unproven (Mon 23:30 ET).
* [B-J] Firebase credential, the admin/multi-user boundary, and whether `/` becomes this
  app all remain J's calls, carried across three goals now.
