# Frontend / UI Work Guidelines (relocated from CLAUDE.md 2026-06-28)

- When J provides a reference image/screenshot, USE IT as the background or direct asset — do not rebuild from scratch procedurally.
- Do not resize based on screenshots alone; screenshots can misrepresent actual browser rendering. Confirm with J before resize-only changes.

## HQ scene acceptance — judge it like a human, not a checkbox (J 2026-09-15, appended 2026-09-15 19:03:19 Tuesday EDT)

J: "The fact that I had to point all this out tells me whatever's auditing it isn't looking at it like a human would … the object was placed on the screen, checkbox, move on." Desks inside walls, a pitched unreadable board and an agent pacing through a wall all PASSED because every check asked "is it present / are the numbers right", never "would a person accept this room".

**Binding for every HQ / 3D / UI pass (worker briefs inherit this verbatim):**

1. **Acceptance wording is "physically plausible to a human", never "visible".** A thing that renders but clips a wall, faces away from the camera, or is unreadable at the viewing distance is a FAIL.
2. **Deterministic plausibility audit before any PASS** — `setup/scripts/hq_live_probe.py --plausibility` (also rides along in a normal full run's `environment.plausibility`) runs the check family: wall_penetration, walker_wall_cross for residents AND live agents, screen_facing per camera preset including top-down, desk_clearance ≥ 1 u to walls, desk_orientation consistency, label legibility. Pure geometry lives in `dashboard/lib/hq-scene-audit.ts` (unit-tested via `node --test dashboard/tests/hq-scene-audit.test.ts`, including regression pins against the fixed desk-in-wall and alert-pace-through-wall bugs). Quote its verdict lines. If the audit can't run, the item stays UNVERIFIED — it is never inferred green.
3. **Two-view capture rule** — every real-screen capture set includes the default preset AND the top-down view. One angle hides half the problems (the pitched board only looked wrong from above; the wall-clipped desks only from above).
4. **Plain-language rubric, answered in writing when reading a capture** (all six, one line each, before the verdict):
   - Is anything embedded in, or passing through, a wall/floor/other object?
   - Can I read every screen from this camera? (If not: is it facing me, is the text big enough?)
   - Are there real aisles and doors, and would a person walk that route?
   - Is everything the same "kind" oriented the same way (desks, chairs, signs)?
   - Does any label/plaque cover something it shouldn't?
   - Would an office manager accept this room as built? If no, what is the first thing they'd say?
5. **A repeat of the same complaint from J = a missing check.** Add it to the audit the same session (OP-25 / repeated-question rule), never just fix the instance.

Provenance: memory `feedback_hq_audit_like_a_human_not_checkbox_2026_09_15`; design references live in `dashboard/components/hq/ENVIRONMENT-PLAN.md`.

## HQ usability — the questions the default view must answer (J 2026-09-16, appended 2026-09-16 00:11:42 Wednesday EDT)

J, after the plausibility pass: "it still needs a lot of design work to look good and be actually usable." Passing every plausibility check is necessary, not sufficient. Usable = the scene answers J's questions at a glance (default view, no interaction) or in ONE click. This list is the spec for the `usability` check family in `hq_live_probe.py` (each question → one check that FAILs when the answer is not legible ≥12 px from the default camera, or needs more than one click):

| # | Question | Where the answer must live |
|---|---|---|
| U1 | Is the market open, and when is the next open/close? | banner, always visible |
| U2 | Book P&L today, per active arm (gross, labelled) | fleet panel or the right monitor |
| U3 | Which lane is RED, and why (one line) | that bay's sign + one click on the bay |
| U4 | What is each persona doing right now, and on what model? | head label (dot+name+glyph) + hover/click |
| U5 | Which live Claude agents are here, and what are they working on? | head label + hover; walking = real events |
| U6 | Last fill: arm, side, price, result | HoloChart marker + plaque |
| U7 | What needs J? | NEEDS-J panel, always visible, count in the banner |
| U8 | Is anything broken? (stale data, dead task, RED health) | one place, red, never buried |

Rules: every answer surface is either always-visible or exactly one click away from the default view; no answer may require reading the flat HUD panel to disambiguate the 3D scene (they must agree); when a check fails, the layout changes, not the threshold.

Visual direction: "looks good" is J's taste call — every look pass starts from 2–3 external references with screenshots that J picks between (design-starts-at-external-reference rule); workers build to the picked reference, never to their own output.
