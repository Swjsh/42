"""gamma_cockpit_ui_theme.py -- new CSS from the Fable review pass (2026-09-03).

Split out of gamma_cockpit_ui.py so that file can hold its 800-line ceiling
(it was already at 806 before this pass; every rule below is ADDITIVE -- new
selectors only, nothing here redefines a token or a selector gamma_cockpit_ui.py
already owns, so load order never matters). Concatenated onto gamma_cockpit_ui.CSS
at import time: `CSS = _BASE_CSS + gamma_cockpit_ui_theme.THEME_CSS`.

Covers the four visual fixes from that review that needed CSS, not just JS:
  1. First-viewport density -- `.stage--compact` (armyMount toggles it for
     <=3 live sessions) and the Goal/Budget band's one-row `.band__budget-*`
     layout (was a ~240px stacked column beside a 64px goal row).
  2. Hero hierarchy -- verdict-toned text colour on the sentence chips
     (`.statusitem` base sizing/weight is still gamma_cockpit_ui.py's, this
     only adds the colour-by-verdict rules layered on top of it).
Items 3 (light theme), 4 (card titles), 5 (row graphics) and 6 ("Untitled
chat") needed no new CSS -- their fixes live in the JS/Python builders.
"""
from __future__ import annotations

THEME_CSS = r"""
/* ---- item 1: first-viewport density ---- */
/* <=3 live sessions: armyMount toggles this class on `.stage` (cmdStage()'s
   own wrapper div) so a small roster stops eating the goal band and every
   producer row below it out of the first 950px. Compact session cards
   (army_js's own `compact` flag) shrink to fit most of this without
   scrolling; a larger roster still gets the 480px cap's scroll pocket. */
.stage.stage--compact{max-height:300px}
/* ONE 64-72px row: the budget side used to stack "Tonight, fires..." + a
   meter + "Spend exhausted" + a 28px figure + an over-line + a full-width
   sparkline + a cost-meter date + a source line (~240px) beside the goal
   row's single 64px line. Same content, one flex row: fires meter, spend
   figure, an inline (not full-width) sparkline, source+age.
   flex-wrap, not overflow:hidden: a 20px mono "$34.56 / $30.00" is already
   ~190px on its own, so these four groups cannot share one literal text line
   inside a ~1fr (~400px) column at any width this page actually ships at --
   clipping them would have silently hidden the spend figure and the
   source+age (the honesty rail this whole page exists to keep). Wrapping
   keeps the 64-72px promise as a HEIGHT, not a single unbroken line: one line
   at generous widths, two short ones at the widths this page renders at,
   never hiding a number. */
.band__budget-row{display:flex;align-items:center;gap:var(--s4);row-gap:2px;flex-wrap:wrap}
.band__budget-fires{display:flex;align-items:center;gap:var(--s3);flex:none}
.band__budget-meter svg{width:64px;height:18px;display:block}
.band__budget-figure{font-size:20px;flex:none;white-space:nowrap}
.band__budget-spark{flex:none;line-height:0}
.band__budget-spark svg{width:72px;height:18px;display:block}
.band__budget-src{margin-left:auto;flex:none;font-size:12px;color:var(--tx-3);white-space:nowrap}
.band__budget-src .src{margin:0}

/* ---- item 2: hero hierarchy ---- */
/* The state sentence was declared the hero at 20px in `.sentence`, but every
   child re-declared its own font at 15px, so nothing ever rendered at hero
   size -- the biggest, boldest thing on the page was the Army stage's own
   session id instead (now demoted, see gamma_cockpit_army_js.py). Base sizing
   (20px/28px/600) moved onto `.statusitem` itself in gamma_cockpit_ui.py;
   this layers verdict-toned TEXT colour on top -- red for a red verdict, the
   stage's own live cyan for a green/live one -- the one exception this page
   makes to "no colour on text" for the hero row specifically. Every other
   row keeps the dot-only rule untouched. */
.statusitem[data-verdict="red"] .statusitem__t,.statusitem[data-verdict="red"] .statusitem__t b{color:var(--neg)}
.statusitem[data-verdict="green"] .statusitem__t,.statusitem[data-verdict="green"] .statusitem__t b{color:var(--st-live)}
.statusitem[data-verdict="amber"] .statusitem__t,.statusitem[data-verdict="amber"] .statusitem__t b{color:var(--warn)}
"""
