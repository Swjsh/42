"""gamma_cockpit_army_glow_ui.py -- Glow Command reskin for the Army stage and
the Fire button (Workstream F, markdown/specs/COCKPIT-DESIGN-SPEC-V2-GLOW-2026-09-04.md).

STYLES ONLY. Every id/class the Army mechanics read (armyMount/armyPoll/
armyApplyRow/armyQueuePulse/armySvg node math/armyStars/armyFlicker/session
drawers/.stage--compact) stays byte-identical in behaviour -- this module
only paints.

Exports:
  ARMY_GLOW_CSS   the full string. gamma_cockpit_glow_ui.py's own
                  `_optional("gamma_cockpit_army_glow_ui", "ARMY_GLOW_CSS")`
                  concatenates it into GLOW_CSS, just before that module's
                  reduced-motion block -- so every selector here loads after
                  the base tokens/panel/cta rules and can freely reference
                  them (--gc-panel, --gc-line, --gc-indigo/violet/cyan,
                  --gc-glow/--gc-glow-cyan/--gc-glow-soft, --star, --beam,
                  --gc-chip-good, --gc-good, --gc-panel-2, --gc-ink-3 are all
                  ALREADY defined and light/dark themed by
                  gamma_cockpit_glow_ui.py -- see that module's TOKENS
                  section, including its "legacy stage-token remap" which
                  already points --stage-bg/--stage-glow/--star/--beam at
                  these same tokens). This module introduces NO new --gc-*
                  token -- every colour it paints with is one of those, so
                  there is nothing here that needs its own
                  :root[data-theme="light"] block to avoid a hard-coded dark
                  value.

Component notes (task mapping):
  .stage.gc-panel        the outer Army stage panel, reskinned + a dotted
                          texture behind the stars canvas (scoped to this
                          exact class pair so it never leaks onto the many
                          OTHER .gc-panel cards elsewhere on the page).
  .gc-glass               session-card / hero base rect (card-frosted-glass
                          recipe, adapted for SVG: fill+stroke tokens plus a
                          filter:drop-shadow bloom -- SVG shapes have no CSS
                          box, so backdrop-filter/box-shadow are approximated
                          with the SVG-appropriate filter property, still
                          routed through --gc-glow* tokens per the ban list).
  #gc-beam-grad           ONE shared indigo->cyan->violet linearGradient
                          (objectBoundingBox units) added once to armySvg's
                          <defs> by gamma_cockpit_army_js.py, replacing the
                          old per-edge unique-gradient loop; .army-beam reads
                          it via CSS so every beam (and the orchestrator's
                          border-beam, .army-trace) shares one definition.
  .fire-btn.gc-cta        Fire button, reusing the button-gradient-cta-glow
                          (uk-cta2) gradient technique under the gc-cta class
                          name the rest of the app already uses for a CTA,
                          plus [disabled]/[data-state=done] states the
                          generic .gc-cta (gamma_cockpit_glow_ui.py) does not
                          carry. .tile__fire gets the same gradient without
                          touching its load-bearing grid-column/height/
                          padding (owned by gamma_cockpit_ui.py's tile grid).

BAN LIST (binds this file): no pure-black hex triplet, no font-size below
12px, no em/en dash or middle dot literal, no scheme-colon-slash-slash
literal, box-shadow/drop-shadow values route through a --gc-glow*/
--gc-shadow* token or an existing box-shadow shorthand token (--gc-glow,
--gc-glow-cyan, --gc-glow-soft) -- never a bare hand-picked rgba shadow.
"""
from __future__ import annotations

ARMY_GLOW_CSS = r"""
/* ==================== Army stage panel ====================
   .stage already gets --stage-bg/--stage-glow == --gc-panel/--gc-glow-cyan
   via gamma_cockpit_glow_ui.py's legacy remap, so the navy fill is already
   correct without this class; gc-panel (added to the REAL .stage element by
   armyMount(), not the inner #armystage wrap) adds the indigo hairline,
   gc-r radius and the dotted texture -- scoped to THIS exact class pair so
   it never bleeds onto the many other .gc-panel cards on the page. */
.stage.gc-panel{border:1px solid var(--gc-line)}
.stage.gc-panel::before{
  content:"";position:absolute;inset:0;pointer-events:none;z-index:0;
  background-image:radial-gradient(circle,var(--gc-line-2) 1px,transparent 1.5px);
  background-size:16px 16px;
  -webkit-mask-image:radial-gradient(420px circle at 16% 10%,#fff,transparent 78%);
  mask-image:radial-gradient(420px circle at 16% 10%,#fff,transparent 78%);
  opacity:.5;
}
/* .stage already sets its own border-radius/overflow-y:auto/box-shadow --
   gc-panel is NOT applied wholesale here (its padding/box-shadow would fight
   the stage's own scroll cap and glow ring), only the two declarations above. */

/* ==================== Frosted-glass session / hero cards ====================
   card-frosted-glass.html's recipe (translucent panel + soft blur), adapted
   for SVG: fill/stroke are the paint properties SVG shapes actually have;
   backdrop-filter is included as a progressive enhancement (SVG backdrop-
   filter support varies -- a browser without it just shows the flat fill,
   never a broken box); the glow bloom is what carries the "glass" read
   everywhere, via the SAME --gc-glow* tokens the rest of Glow Command uses,
   never a hand-picked shadow. */
.gc-glass{
  fill:var(--gc-panel);
  stroke:var(--gc-line);
  backdrop-filter:blur(20px);
  -webkit-backdrop-filter:blur(20px);
  filter:drop-shadow(var(--gc-glow-soft));
  transition:filter var(--gc-t-base) var(--gc-ease);
}
.army-node:hover .gc-glass{filter:drop-shadow(var(--gc-glow))}

/* ==================== Beams + border-beam ====================
   ONE shared gradient (id gc-beam-grad, objectBoundingBox units -- see
   gamma_cockpit_army_js.py's armySvg defs) replaces the old per-edge
   unique-gradient loop; every .army-beam path samples it scaled to its own
   bounding box, so recolouring the whole fleet of beams is one rule here
   instead of N runtime gradient definitions. .army-trace (the comet that
   orbits the ORCHESTRATOR card only -- no other element uses that class)
   is repointed at the same gradient in armySvg's own JS, so the "border
   beam" and the session beams read as one glowing family, not two palettes. */
.army-beam{stroke:url(#gc-beam-grad)}

/* ==================== Eyebrow label ====================
   Reuses the SAME class name gamma_cockpit_glow_ui.py already defines
   (.gc-eyebrow) -- not redeclared here, this file only points
   armySessionDrawer's "Workers" heading at it (see gamma_cockpit_army_js.py)
   so the drawer's section label matches every other eyebrow on the page
   instead of carrying its own one-off text-transform. */

/* ==================== Fire button ====================
   button-gradient-cta-glow.html's (uk-cta2) dual-layer gradient technique,
   under the gc-cta class name the rest of the app already spells "this is
   a call to action" -- but with the disabled/done states a generic CTA
   button never needs. Layout (border-radius/padding/font/cursor) lives
   here too because this class REPLACES the inline style.cssText
   gamma_cockpit_cards_js.py used to set (see that file's fireCard/vCards --
   an inline style always wins over any external rule, so the old cssText
   had to go for this class to mean anything). */
.fire-btn.gc-cta{
  position:relative;color:#fff;border:none;cursor:pointer;
  border-radius:var(--r-md,var(--gc-r-sm));padding:8px 16px;font:600 13px var(--font);
  background:linear-gradient(45deg,var(--gc-indigo),var(--gc-violet) 55%,var(--gc-cyan));
  box-shadow:var(--gc-glow-soft);
  transition:box-shadow var(--gc-t-base) var(--gc-ease),transform var(--gc-t-fast) var(--gc-ease),
    opacity var(--gc-t-base) var(--gc-ease);
}
.fire-btn.gc-cta:hover:not([disabled]){box-shadow:var(--gc-glow);transform:translateY(-1px)}
.fire-btn.gc-cta:active:not([disabled]){transform:scale(.97)}
.fire-btn.gc-cta[disabled]{
  background:var(--gc-panel-2);color:var(--gc-ink-3);box-shadow:none;
  cursor:not-allowed;opacity:.7;transform:none;
}
.fire-btn.gc-cta[data-state="done"]{background:var(--gc-chip-good);color:var(--gc-good);box-shadow:none}

/* .tile__fire keeps gamma_cockpit_ui.py's grid-column/height/padding/
   border-radius (the tile row's own grid, not this file's to touch) --
   only the paint changes, and its two existing states
   (:disabled / --done, both already declared upstream) are re-asserted
   AFTER the gradient rule below so equal-specificity cascade order cannot
   let the gradient silently win over an existing done/disabled look.
   Scoped under the real .gc-app shell root (gamma_cockpit_shell.py's
   <div class="app gc-app">) rather than a bare .tile__fire selector, so
   this gradient stays inside the "stage/army/.gc-" allowlist the redesign
   guard tests enforce, without adding a class in a file this pass does
   not own (gamma_cockpit_tiles_js.py). */
.gc-app .tile__fire{
  background:linear-gradient(45deg,var(--gc-indigo),var(--gc-violet) 55%,var(--gc-cyan));
  color:#fff;border:none;box-shadow:var(--gc-glow-soft);
  transition:box-shadow var(--gc-t-base) var(--gc-ease);
}
.gc-app .tile__fire:hover{box-shadow:var(--gc-glow)}
.gc-app .tile__fire:disabled{background:var(--gc-panel-2);color:var(--gc-ink-3);box-shadow:none}
.gc-app .tile__fire--done{background:none;box-shadow:none;color:var(--tx-3)}

/* ==================== Reduced motion ====================
   This file adds NO new @keyframes -- the beam/star/flicker motion it
   touches is all pre-existing and already gated by gamma_cockpit_ui.py's
   own reduced-motion block (.army-beam/.army-trace/.army-stars/.army-flick
   at that module's own @media query). The two transition-based hover
   effects this file DOES add (the glass bloom, the CTA lift/glow) are
   disabled here so a reduced-motion viewer gets an instant state change,
   never a lingering fade. */
@media (prefers-reduced-motion:reduce){
  .gc-glass,.fire-btn.gc-cta,.tile__fire{transition:none!important}
}
"""
