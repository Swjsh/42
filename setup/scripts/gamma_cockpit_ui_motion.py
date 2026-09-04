"""gamma_cockpit_ui_motion.py -- CSS for spec section 10 (Iteration 2, the
GLANCE layer), split out of gamma_cockpit_ui.py so that module's own 800-line
ceiling is never touched by this pass (project instruction: "ui.py is at 806
lines -- do not grow it").

Owns: the Vitals grid + its 6 stat tiles, the goal strip that replaces the
old 2-column Goal/Budget band, the day-line's breathing now-marker + the
label-collision rule, the Army stage's zero-session state, and the load-
choreography's CSS half (the JS half is pure WAAPI -- gamma_cockpit_command_js
-- so almost nothing new is needed here beyond an opacity/transform resting
state for the elements that animation targets, all gated by the same
prefers-reduced-motion query the rest of the app already uses).

BAN LIST (same as gamma_cockpit_ui.py, enforced by the SAME tests against the
concatenated ui.CSS -- see test_gamma_cockpit_vendor_2026_09_03.py /
test_cockpit_redesign_2026_09_03.py): no new box-shadow (cap of 3 is already
spent), no new gradient (cap of 1 is already spent), no font-size below
12px, no text-transform:uppercase (sentence case everywhere -- so the Vitals
label below is tracked with letter-spacing, NOT rendered upper-case via CSS,
a deliberate deviation from spec 10.1's literal "uppercase-tracked" wording
in favour of the repo's own standing invariant), no em/en dash or middle dot.
"""
from __future__ import annotations

MOTION_CSS = r"""
/* ============================================================
   VITALS GRID (spec 10.1 band 3) -- 6 stat tiles, one row, above the
   Army stage. Each is a <details> too (spec: "Tiles are <details> too");
   its own expand affordance jumps to the matching producer row via
   tileOpen() rather than re-rendering that row's body inline -- one body
   per fact, never two copies that can drift apart.
   ============================================================ */
.vitals{display:grid;grid-template-columns:repeat(6,1fr);gap:var(--s4);min-width:0}
.vital{background:var(--bg-1);border:1px solid var(--line);border-radius:var(--r-md);
  min-width:0;display:flex;flex-direction:column;overflow:hidden}
/* round-2 review fix (critical): gfx/figure/state moved INTO .vital__head
   (the <summary>) so they render at rest -- a native <details> hides
   everything else until opened, which was silently swallowing the one
   graphic + one figure spec 10.1 calls the "glance". .vital__head is now a
   flex COLUMN holding the whole visible stack; .vital__top is just the old
   icon+label row inside it. Only the optional jump link stays in the real
   (collapsible) .vital__body. */
.vital__head{display:flex;flex-direction:column;padding:var(--s4);cursor:pointer;
  list-style:none;transition:background var(--t-fast) var(--e-hover)}
.vital__head::-webkit-details-marker{display:none}
.vital__head::marker{content:""}
.vital__head:focus-visible{outline:2px solid var(--accent-line);outline-offset:-2px}
.vital__top{display:flex;align-items:flex-start;gap:6px}
.vital__ic{color:var(--tx-3);display:flex;flex:none;margin-top:1px}
.vital__ic svg{width:14px;height:14px}
/* tracked with letter-spacing only, sentence case (see module docstring
   for why the CSS keyword this label's spec wording implies is avoided).
   ROUND-3 POLISH item 3: nowrap+ellipsis truncated short 2-3 word labels
   ("This month" -> "This mo...") at 1440px card widths -- these titles are
   never long enough to need an ellipsis, so let them wrap to a 2nd line
   instead (align-items:flex-start above keeps the icon pinned to the first
   line rather than re-centering on a taller 2-line label). */
.vital__label{font:600 12px/1.3 var(--font);letter-spacing:.06em;color:var(--tx-3);
  white-space:normal;overflow:hidden;text-overflow:clip;word-break:break-word;min-width:0}
.vital__gfx{min-height:56px;display:flex;align-items:center;justify-content:center;margin-top:2px}
.vital__gfx svg{display:block;max-width:100%;height:auto}
.vital__figure{font:500 22px/26px var(--mono);color:var(--ink-1);font-variant-numeric:tabular-nums;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}
.vital__state{font:400 12px/16px var(--font);color:var(--tx-3);white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:6px;margin-top:2px}
/* ROUND-3 POLISH item 7: the "no prior period to compare" case (spec.noPrior
   in cmdVitalTile) -- plain muted text, deliberately NOT a .gc-delta pill,
   so it never visually competes with a sibling card's real up/down/info
   delta chip. 12px is this project's text-size floor, same as .vital__state. */
.vital__no-delta{font:400 12px/1 var(--font);color:var(--tx-4)}
.vital__body{padding:0 var(--s4) var(--s4)}
.vital__more{padding-top:var(--s3);font:400 12px/18px var(--mono);color:var(--tx-3);
  border-top:1px solid var(--line);margin-top:var(--s3)}
.vital__more a{color:var(--acc)}
.vital--stale .vital__gfx{opacity:.6}
@media (hover:hover) and (pointer:fine){.vital__head:hover{background:var(--surface-1)}}
@media (max-width:1360px){.vitals{grid-template-columns:repeat(3,1fr)}}
@media (max-width:680px){.vitals{grid-template-columns:repeat(2,1fr)}}

/* spec 10.4: Answers' right column (2 vitals tiles, Gate + Book) and
   Journal's summary tiles reuse .vitals but as a single stacked column
   rather than the Command view's 6-across row. */
.vitals--col{grid-template-columns:1fr;flex:none;width:240px}
.answerslayout{display:grid;grid-template-columns:1fr 240px;gap:var(--s6);align-items:start;min-width:0}
@media (max-width:1000px){.answerslayout{grid-template-columns:1fr}.vitals--col{width:auto}}

/* ============================================================
   GOAL STRIP -- one line, replaces the old 96px 2-column band (spec 10.1:
   "Goal + Budget band collapses INTO the Vitals grid (Budget tile) and a
   one-line goal strip directly above 'Needs you'").
   ============================================================ */
.goalstrip{display:flex;align-items:center;gap:var(--s4);height:40px;padding:0 var(--s4);
  border-radius:var(--r-md);background:var(--bg-1);border:1px solid var(--line);min-width:0}
.goalstrip__ring{flex:none;display:flex}
.goalstrip__ring svg{width:20px;height:20px;display:block}
.goalstrip__t{font:500 13px/1 var(--font);color:var(--ink-1);white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;min-width:0}
.goalstrip__next{font:400 12px/1 var(--font);color:var(--tx-3);white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;min-width:0}
.goalstrip__days{margin-left:auto;flex:none;font:400 12px/1 var(--mono);color:var(--tx-4)}

/* ============================================================
   DAY-LINE: label-collision drop + breathing now-marker (spec 10.1 band 2).
   A tick whose label would sit within 56px of its neighbour's is marked
   [data-hide-label] by the builder and simply renders no text -- never a
   second row of alternating labels, so nothing below the track competes
   with the now-marker's halo for attention.
   ============================================================ */
.dayline__tick[data-hide-label] .dayline__lbl{display:none}
.dayline__now::before{content:"";position:absolute;left:-5px;top:-5px;width:18px;height:18px;
  border-radius:50%;background:var(--accent-fill);opacity:.28;
  animation:daylinebreathe 2s var(--e-hover) infinite}
@keyframes daylinebreathe{0%,100%{transform:scale(.7);opacity:.35}50%{transform:scale(1.15);opacity:.08}}

/* ============================================================
   ARMY STAGE: zero-session state (spec 10.1 band 4) -- the stage still
   earns its space empty: the star-field alone plus a centred sentence,
   never a blank rectangle.
   ============================================================ */
.stage__empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  pointer-events:none;z-index:1}
.stage__empty span{font:400 13px/1.4 var(--mono);color:var(--tx-3);text-align:center;max-width:60%}
/* an expanding ring "ping" -- both of this file's usual near-cap properties
   stay untouched here: a plain 1px border ring that grows and fades, reused
   three times on a stagger for a slow radar-sweep read without a single new
   occurrence of either banned pattern (see module docstring). */
.stage__sweep{position:absolute;inset:0;border-radius:inherit;pointer-events:none;overflow:hidden}
.stage__sweep i{position:absolute;left:50%;top:50%;width:16px;height:16px;margin:-8px 0 0 -8px;
  border-radius:50%;border:1px solid var(--accent-line);opacity:0;
  animation:stagesweep 4s var(--e-hover) infinite}
.stage__sweep i:nth-child(2){animation-delay:1.3s}
.stage__sweep i:nth-child(3){animation-delay:2.6s}
@keyframes stagesweep{0%{transform:scale(1);opacity:.5}85%,100%{transform:scale(9);opacity:0}}

/* ============================================================
   LOAD CHOREOGRAPHY (spec 10.5) -- almost entirely WAAPI in JS
   (gamma_cockpit_command_js.py's cmdChoreograph()); the CSS half is just the
   resting state each animated element starts from so a reduced-motion
   viewer (or a re-render after the first paint) never sees a flash of the
   pre-animation state.
   ============================================================ */
@media (prefers-reduced-motion:reduce){
  .dayline__now::before,.stage__sweep i{animation:none}
}
"""
