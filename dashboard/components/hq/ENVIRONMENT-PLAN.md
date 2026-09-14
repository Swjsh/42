# HQ Environment Plan — space-base-on-a-planet-surface (2026-09-14)

Trigger: J, 2026-09-14 ~13:10 ET, live on `/hq`: "it looks like the background is a
grey abyss. why not a space theme or a park or something real lol ... the design
needs work still." Coordinator decision: SPACE — every bundled kit
(kenney-space-station-kit, kenney-modular-space-kit, kenney-space-kit, kaykit-
space-base-bits, polyhaven dikhololo-night HDRI) is already a space-station kit,
so the fix is not a new theme, it's finishing the one already half-built: the
station currently floats in a flat fog void with no sky feature, no ground
feature, and no props beyond its own footprint. This doc is written BEFORE any
code edit per the standing design rule (external references first, never
iterate our own output).

## UX conventions (2026-09-14, UX-1 pass — onboarding hints, click-to-focus,
hover tooltips, focus-follow panels)

Trigger: J, "this needs to be a smooth intuitive user experience." Design rule
followed (≤10 min): WebSearched Two Point Hospital / Cities: Skylines / Planet
Coaster / Prison Architect UI conventions this session, then WebFetched
prisonarchitect.paradoxwikis.com/Controls and skylines.paradoxwikis.com/Info_views
directly. Disclosed honestly, matching this doc's own World-4-pass precedent for
a thin source: the live fetches documented KEYBINDS and info-view CONTENTS, not
hover/click/focus MECHANICS in enough granular detail to quote verbatim — the 3
conventions below are the well-established, widely-documented genre pattern this
class of management-sim is collectively known for (confirmed in part by the
search results: Prison Architect's left-click-to-select-and-open-panel, Cities:
Skylines' per-selection info views), not a single verbatim source quote.

1. **A dismissible control legend, not a permanent HUD tax.** Cities: Skylines/
   Planet Coaster show a control hint on first load that gets out of the way
   once the player has demonstrably started driving (real input seen), rather
   than taxing the screen forever. Adopted for U1: the legend now fades 8s
   after the FIRST real input (not a blind mount timer) and "?" brings it back.
2. **Hover = name-tag tooltip, click = select-and-focus — never conflated.**
   Two Point Hospital's hover nameplates (name + status, at the cursor/over the
   character) are the genre's "what is this" affordance; a CLICK is the
   heavier "commit to this one" action (Prison Architect: left-click selects
   an entity and opens its panel). Adopted for U2/U3: hover only ever shows a
   lightweight tooltip near the cursor (camera never moves on hover); click is
   the ONLY thing that flies the camera and pins the roster card.
3. **The panel tracks the selection; the selection never fights the panel.**
   Management-sim roster/inspector panels keep the current selection visible
   (scrolled/highlighted into view) rather than leaving the player to hunt for
   it in a long list. Adopted for U6: focusing a persona (hotkey or world
   click) scrolls its crew card into view and pins it under the sticky header.

## External references consulted (2026-09-14, via WebSearch/WebFetch/browser)

1. **kenney.nl/assets/space-kit** (the exact CC0 pack this task downloads from) —
   opened the page live and viewed its own hero diorama render directly (not just
   metadata): a low-poly base sits on a rounded terrain island, dark near-black
   void above/around it (no sky gradient at all in their marketing shot), warm
   orange-rust ground with visible darker circular crater depressions and dark
   grey-brown rock clusters at the terrain edges, white/light-grey structures
   trimmed in amber/yellow, a satellite dish mounted on a rock outcrop, a rover
   vehicle, pipe/tube walkways between buildings, small human figures for scale.
   This is the DIRECT visual language of the asset pack we're pulling pieces
   from — rock/crater/dish/rover silhouettes all confirmed real, not assumed.
2. **only-up.itch.io/space-assets-pack (MMSpicyStudios Low Poly Space Asset
   Pack)** — viewed the pack's own preview render: a Mars rock (reddish-brown/
   tan, low-poly facets), a rover (Curiosity-style, grey chassis + gold-foil
   accents), a communications satellite, an asteroid — cross-check for rock/
   rover/dish silhouette and color range against the Kenney render above.
3. **ESA "Artist impression of a Moon Base concept" (esa.int, P. Carril, 2019)**
   — page copy confirms the standard real-world base layout logic this plan
   reuses: solar arrays as their own zone (not mixed into the habitat cluster),
   regolith used as physical shielding banked against structures, functional
   zones kept visually distinct rather than scattered.
4. **RenderHub "Low Poly Moonbase Concept" (SimonTGriffiths)** — confirmed via
   its own listing (11 preview angles, game-ready low-poly) that a distinct
   moon-base genre with this exact silhouette vocabulary (domes/dishes/rover on
   a cratered grey plain) is an established, recognizable game-art target, not
   a one-off.

Net read: the Kenney pack's OWN reference render uses warm Mars-orange ground.
This plan deliberately shifts the ground hue cooler (grey-tan "regolith", not
Mars-orange) because this project's existing `palette.ts` already commits to a
cool-toned world (`planet:"#16324a"`, `planetRim:"#4fd6ff"`, hub cyan
`#7ad9ff`/`#22d3ee`) — a stated adaptation, not a blind copy. The amber/yellow
accent trim (`PALETTE.warmAccent`, already the scene's own established accent)
is kept as-is, matching the Kenney render's own white+amber prop language.

## The 6-line design plan

1. **Palette** — regolith (lit) `#8a8175`, crater/night shadow `#332e24`, space
   sky zenith `#03040a`→horizon-depth `#12203a` (black-to-deep-indigo, unchanged
   by day/night per the "not sky colour to grey" rule below), planet body lit
   `#9fb8c9` / dark terminator side `#0d1826`, accent (base lights, dish trim,
   antenna) `#ffb020` (existing `warmAccent`, reused not reinvented), thin
   atmosphere/horizon rim `#4fd6ff` (existing `planetRim`, reused).
2. **Sky/horizon** — sky stays black-to-deep-indigo at BOTH day and night (this
   is an airless body: no blue-atmosphere lerp, day/night only nudges the
   zenith/depth a shade lighter, never toward pale/grey); Starfield gets an
   opacity FLOOR so stars stay faintly visible at noon, not just at night; one
   large procedural planet disc (gradient + soft crater speckle + a lit/dark
   terminator line, `Planet.tsx`, no downloads) sits low, behind the hub from
   the default camera; a thin cyan atmosphere band hugs the true horizon ring.
3. **Ground** — `Ground.tsx`'s repeating grid-tile texture is replaced with a
   mottled regolith noise texture (no visible tiling beyond the plaza itself,
   which keeps its own built-surface look); 6–10 crater rings (dark floor,
   raised rim) at fixed deterministic radii/angles outside `PLAZA_RADIUS`;
   150–300 instanced rocks in 2–3 kit variants via a seeded RNG (never inside
   the plaza); 2–3 oversized boulders as landmarks framing the base.
4. **Props** — Kenney Space Kit CC0 pieces placed in fixed zones ringing the
   plaza, all outside `PLAZA_RADIUS`, none blocking a bay door or a camera
   preset 1–7: 2 satellite dishes angled toward the planet, a solar array field
   (row-instanced) on one flank, a landing-pad disc with a light ring on
   another, a rover parked near a bay, containers+barrels+pipes along the
   plaza's outer edge, 8 perimeter lights (kaykit), one antenna mast with a
   slow blinking red light (motion budget: lights only, per the HQ face rule —
   no moving vehicles/drones).
5. **Lighting** — day: harsh warm-white directional sun (existing light, kept),
   long shadow map, hemisphere fill lerped sky-indigo/ground-regolith (not
   sky-blue/ground-brown as today); night: cooler planet-glow-tinted fill +
   the base's own warm practical lights carry the scene, exactly as `palette.ts
   #dayNightFactor` already schedules. Day/night changes light COLOUR/INTENSITY
   and the base's own lights — never the sky hue itself (the literal bug this
   pass fixes: the old day sky lerped to pale `#a9c9e3`, and fog lerped to the
   same pale tone starting only 20 units out — that flat nearby pale wall, with
   nothing else in view, IS the "grey abyss").
6. **Composition** — from the default overview (key `0`) and `?camdist=36`: the
   planet reads in the upper third of frame roughly behind the hub, regolith +
   craters + rocks continue past the plaza to a soft dark haze (no hard grey
   wall, no visible flat circular cutoff), props frame the base without
   floating or clipping through a wall, and all 7 numbered camera presets keep
   clear sightlines to their own bay.

## Root cause of "grey abyss" (confirmed by reading every file in this tree first)

Three compounding bugs, not one:
- `Starfield.tsx` sets `opacity = (1-dayFactor)*0.75` — literally 0 at any
  daytime `dayFactor`, so at 13:10 ET (full day) the only background "texture"
  vanishes entirely.
- `SkyDome.tsx` lerps the WHOLE sky (not just the horizon glow) from a dark
  night gradient to a pale daytime blue (`DAY_ZENITH #4a7fb0`/`DAY_DEPTH
  #bcd9ee`) — an Earth-atmosphere sky on a body this project's own kit/HDRI/
  palette says is airless.
- `Scene.tsx`'s fog lerps to the SAME pale tone (`#a9c9e3`) starting at only 20
  world units (just past the plaza edge) — so by day, everything past the
  station is one flat pale wall, and (pre-Pass-G-2) there was never a planet or
  ground feature to look at anyway. Three independent "make it paler/emptier"
  choices stacked into exactly the flat, featureless wash J flagged.

## World-4 pass (2026-09-14) — in-world signage + ideas-board legibility

Trigger: coordinator work order, P2 ("floating lane labels… hover mid-air…
replace with IN-WORLD SIGNS") + P3's ideas-board-legibility half. Design rule
followed before writing any sign/panel code (WebSearch this session —
`kenney.nl` navigation and the ArtStation listing itself were both blocked/
403'd to this session, so this reads search-result/listing text, not a
directly-viewed render; disclosed rather than presented as a direct look):

1. **ArtStation "Sci-Fi Style Holograms and Signage"** listing text — "based
   on hologram designs found in Mass Effect on the Citadel… mimics the tones
   of a cyberpunk/futurist space aesthetic… individual elements ready to be
   tiled for rapid environmental design."
2. **itch.io "Sci-Fi Holographic HUD Kit"** listing text — "12 interactive
   holographic glass buttons with neon borders in cyan, blue, and tech-green
   plus 12 status bars with segmented designs and metallic brackets… flat
   vector/holographic neon style."
3. Cross-checked against this project's OWN already-shipped plaque language
   (`.hq-beam` border-glow on every existing Html plaque, Hud.tsx/
   StationModule.tsx/BrainCore.tsx) — confirms the SAME "dark panel body,
   bright THIN edge, not a filled wash" convention this codebase already
   committed to independently, rather than importing a clashing new style.

**3 choices taken into BaySign.tsx / IdeasWall.tsx this pass:**

1. **Edge-lit, not filled** — panel body stays dark/near-black (matches this
   tree's own established `rgba(3,4,10,0.7-0.93)` plaque background), the
   health/status color lives ONLY on a thin bright border strip, never as a
   full-panel tint — the "neon border" reading from both references, and
   already this codebase's own convention independently.
2. **A capped top bar, not a uniform box** — a distinct brighter accent strip
   across the TOP of the panel (the "segmented design / metallic bracket"
   framing both references use) rather than one same-weight border all the
   way around, so the sign reads as a technical readout/nameplate, not a
   generic rounded card.
3. **Short lines, high contrast, generous spacing** — every reference
   (hologram HUD kit, hologram-UI genre generally) favors a FEW bright lines
   on near-black over dense small text — reinforces going leaner on both the
   bay sign (lane name + one state word, nothing else) and the ideas-board
   panel (fewer/bigger lines, per P3's own "≤5 lines… ≥28px" spec) rather
   than trying to preserve every old field.
