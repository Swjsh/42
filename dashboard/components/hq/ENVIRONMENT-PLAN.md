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

## World-6 pass (2026-09-14, WORLD-6 builder) — the holo chart + reputable assets + atmosphere

J's mandate this pass: "keep going... this automated trading agent world to
be self learning, improving, and awesome as fuck... even more graphics and
awesome animations from online sources that are reputable." Delivered:

1. **W1, the signature piece** — `HoloChart.tsx`, a holographic SPY intraday
   ribbon floating above the hub's round table, real data only (`spy_5m_*.csv`
   5-min bars — the finest resolution that exists locally, no `spy_1m_*.csv`
   file exists in this repo — + `key-levels.json` + `journal/trades.csv`'s
   real fills, never `core-decisions.jsonl`'s verdict-only log, see
   `lib/hq-chart-data.ts`'s own header for why). Own `/api/hq-chart` route,
   own 60s SWR poll, zero Scene.tsx/route.ts edits. 3 references looked at
   before writing a line of scene code (cited in `HoloChart.tsx`'s own header):
   threejs-journey.com's hologram-shader lesson (the Fresnel-rim idea, reused
   via Planet.tsx's own proven glow-shell technique rather than a new
   ShaderMaterial — this codebase has zero custom shaders, grepped this
   session), a CodePen "Holographic Projection" (the visible-emission-base-
   plate composition), and a Behance 3D-candlestick-chart gallery (the
   green/up red/down convention, adapted to this scene's own established
   HEALTH_COLOR palette rather than the reference's fill/hollow one). Animation
   is 100% event/data-driven per the HQ face rule: a bar grows in ONLY when a
   genuinely new one lands, a level plane flashes ONCE only on a real
   price-touch, nothing loops or spins.
2. **W2, reputable assets** — 5 new CC0 pieces (poly.pizza's own static CDN
   mirror of 3 Quaternius uploads: a shuttle for the landing pad, a "Scifi
   Computer" console + "Pipes Panel" greeble for an exterior server annex;
   Kenney Furniture Kit's `potted-plant.glb`/`plant-small.glb` for interior
   plants), every one opened and orbited in poly.pizza's own 3D viewer before
   picking it (J: "open them up and look at them"), full hunt + rejected
   candidates in `public/hq-assets/LICENSES.md`'s own "Update 2026-09-14
   (WORLD-6 builder, W2 asset hunt)" section.
3. **W3, atmosphere** — 2 techniques, both zero-motion: static additive light
   cones under the 8 perimeter lamp posts (day/night-aware opacity, not a
   timer), and flat additive ground-glow discs under the new hero props. A
   reflective hub floor (the brief's own third option) was evaluated and
   SKIPPED — `StationModule.tsx`'s own comment documents a real
   `MeshReflectorMaterial` artifact from an earlier pass ("double-reflection
   wedge"), and this codebase has zero current `MeshReflectorMaterial` usage
   to build on; not worth the risk for a "nice to have" given the safer
   options already covered the brief.
4. **Draw-call discipline** — a coordinator flag mid-pass (real capture
   hq-20260914-1725.png: 1093/1100) caught 2 first-draft W2 placements that
   were real value-per-draw-call outliers: `plant-small.glb` (2 primitives,
   raw GLB inspection) one-per-bay = 16 calls for a barely-visible desk
   succulent, cut entirely; a 2nd `scifi-computer.glb` instance (5
   primitives) for a "server bank" read, cut to 1. Verified own contribution
   lean via a real capture's own HUD line before/after (1093 -> 1013 calls,
   full chart + all W2 props present) — later readings in the shared tree
   climbed again from a different builder's own concurrent `Scene.tsx`
   change (+398 lines, confirmed via `git diff --stat`, outside this
   builder's ownership).

## Design pass 2026-09-15 (J top-down feedback) — external references (RESEARCH worker)

Timestamp: 2026-09-15 18:27 ET (`et_clock.py`). Scope: RESEARCH ONLY, no code touched.
J reviewed a top-down `/hq` screenshot and gave four items: hub floor plan (desks
sit inside the wall geometry), a two-monitor "brain wall" replacing the tilted
smart board, a compact name/status label per character, and a different
character pack (purple-shirt Kenney minis read as having "walking sticks").
Per standing design rule, every claim below traces to an external source
fetched this session (WebSearch/WebFetch), not to this file's own prior passes.
References already burned by earlier passes (Two Point Hospital / Prison
Architect / Cities: Skylines / Planet Coaster UI conventions, poly.pizza/
kenney.nl/quaternius.com as pack sources) are not re-cited as "new" below except
where a DIFFERENT fact is pulled from them (e.g. Two Point Hospital's staff
label shape, not its UI-flow conventions already logged in the UX-1 pass).

### A. Office floor-plan references (5 sources) + 3 options for the 15x15 u hub

Sources:
1. **arcedior.com/blog/open-office-layout-standards-clearances-2025** — desk
   fronts need >=800-900mm (31-35 in) clearance from a wall/obstruction behind
   them; secondary aisles between workstation rows need 36-48 in (0.9-1.2 m).
2. **upliftdesk.com/blog/open-office-desk-spacing** — corroborates the 36-48 in
   secondary-aisle band and adds that high-traffic main corridors (paths to
   exits/meeting rooms/common areas) want >=48-60 in.
3. **sustema.com/post/ergonomic-clearances-for-room-layouts** (control-room
   specific — closest analog to a trading HQ) — control-room desks want a
   walk-behind zone even beyond open-office norms because operators roll
   chairs back to confer; recommends the 42-48 in band for a chair pushed back
   plus a person walking past it.
4. **ergoprise.com/blog/how-much-space-for-office-chair** — 36 in behind a
   standard task chair is the ergonomics-specialist consensus baseline; 42-48
   in is the "recline/swivel without grazing the wall" ideal for a high-back
   chair, which is what our `chair-armrest.glb` reads as.
5. **oxygennotincluded.wiki.gg/wiki/Room_Overlay** + gametruth.com ONI base
   layout guide (management-sim convention, not already cited) — ONI's base
   convention is 4-tile-high rooms sized as 2D area (a 10x4 room = "40 tiles"
   of room-bonus budget), and workstation placement is optimized to minimize
   dupe travel distance to the room's functional core — i.e. rooms are built
   AROUND their fixed anchor furniture, not the anchor squeezed into a
   pre-drawn ring. That is the actual bug in our current layout: desks were
   placed on a fixed radius-6.5 ring computed independently of the fixed hub
   furniture (BrainCore r2.24, meeting table r2.5, Gamma desk r3.4, board r6.3)
   and the ring math didn't reconcile with the 7.5 u wall.

Converting inches to world units (1 u ~= 1 m; 36 in = 0.91 u, 42 in = 1.07 u,
48 in = 1.22 u): a desk's OUTER edge (not center) needs to sit at radius <=
7.5 - 0.5 (wall thickness/greeble buffer) = ~7.0 u to clear the wall, and the
walk-behind zone behind each desk (control-room band, source 3) wants >=1.0 u
of clear floor before hitting the wall or another desk. Our desk table is 2.2
w x 1.8 d at scale 2; if desks face inward (chair-to-wall), the chair back +
walk zone needs radius(table back edge) + 1.0-1.2 u <= 7.5 u, i.e. table BACK
edge at radius <= ~6.3-6.5 u, meaning table CENTER at roughly radius 5.4-5.5 u
(half-depth 0.9 u forward of that back edge). That is materially INSIDE the
current radius-6.5-with-0.8-offset (~7.3-8.2 u) placement — the fix is
pulling the whole ring inward by ~1.5-2 u, not just nudging it.

**Option 1 — Inward ring, desks face wall (RECOMMENDED).**
```
              +Z door
                 |
      D2      [gap]      D3
        \               /
   -X door--- BrainCore ---+X door
        /      (r2.24)     \
      D1                   D4
   [meeting table r2.5, 6 chairs]
        \                   /
      D6                  D5      Gamma r3.4 (SE, ~61deg)
                 |
              -Z door
   Monitors: corner between +X/+Z doors (~45deg), r~6.0-6.3
```
- 6 persona desks at radius 5.5 u, spaced on the 4 wall segments BETWEEN doors
  (same angular slots as today, 2-2-2), desks rotated so the character's back
  is to the room and the character faces outward toward the wall (control-room
  "face your station" convention) — walk-behind aisle between desk back and
  BrainCore/meeting-table cluster is then ~5.5 - 2.5 (meeting table) = 3.0 u,
  well over the 1.0-1.2 u minimum.
- Gamma's desk stays at r3.4 (already inside the safe band).
- Monitors mount in the 45 deg corner at r~6.0, inside the wall-clearance
  band, replacing the board that currently sits at r6.3 (already close, so
  this is a small pull-in, not a redesign).
- Aisle from any door to BrainCore: >=7.5 - 5.5 = 2.0 u radial gap, comfortably
  over the 48-60 in (1.2-1.5 u) main-corridor guidance (source 2).

**Option 2 — Two concentric rings (denser, ONI-style "build around the
anchor").** Inner ring at r3.4 for 2 desks flanking Gamma (matches Gamma's own
existing radius, reads as a "core team" cluster), outer ring at r5.8 for the
remaining 5 desks. Aisle between rings = 2.4 u (source 1's high end x2,
generous). Risk: inner-ring desks sit close to BrainCore's r2.24 footprint —
needs a per-desk angular offset check against BrainCore's own clearance, not
just radius, so this option carries more geometry risk than Option 1.

**Option 3 — Straight-wall bays (Cities: Skylines info-view "each building
reads independently" convention — desks in flat clusters against each of the
4 wall segments rather than a smooth ring, echoing how the 8 lane-bay rooms
already read).** 3 flat desk-rows of 2 (one per wall segment minus the door
walls), aisle width fixed at 1.2 u between each desk's back and the wall
consistent with source 1/2's 36-48in band, Gamma's desk placed as the 7th unit
on whichever wall segment is nearest the monitor corner. Reads more "office
row" than "circular command center"; loses the radial symmetry the hub's
BrainCore-centric design currently has.

**Recommended: Option 1.** It is the smallest structural change (same 2-2-2
angular slots, same door positions, same fixed-furniture radii), it fixes the
wall-clipping bug with a single radius parameter change (6.5+0.8 offset -> 5.5
flat), and it is the only option that keeps every clearance number traceable
to a cited source rather than an invented one. J picks; this is not applied.

### B. Two-monitor / wall-display references (3 sources)

1. **viewsonic.com/library/business/best-monitors-traders** — trading-desk
   guidance: main display top edge at or slightly below eye level, set height
   FIRST then tilt/distance; side/secondary panels angled 15-30 deg inward so
   their face points at the viewer rather than the opposite wall — this is a
   DESK-monitor convention (viewer close, seated), which does NOT transfer
   directly to a WALL-mounted pair viewed from across a room (our case) —
   flagging this explicitly rather than misapplying a close-viewing-distance
   rule to a far-viewing fixture.
2. **atdec.com/lp/day-traders** and **atdec.com/know-how/day-trader-desk-setups**
   — professional trading-desk mount hardware photos: multi-monitor arrays are
   consistently mounted FLAT (no pitch/tilt) when the array is meant to be read
   by more than one seated position or from a standing/walking vantage — tilt
   is reserved for a single dedicated seat looking straight up at a stacked
   monitor, which is the opposite of our case (camera orbits at ~38.7 deg
   azimuth AND goes top-down).
3. **us.ktcplay.com/blogs/desk-setups/how-to-arrange-monitors-asymmetric-tasks**
   — states the general "viewing distance" legibility heuristic used across
   monitor-arrangement guidance: text should be sized so stroke width is a
   fixed fraction of viewing distance (the classic sign-design rule this
   traces back to is 1 inch of letter height per ~10 ft / ~3 m of viewing
   distance, i.e. viewing-distance / 10 in inches, or viewing-distance / ~250
   in mm — the source states the *practice* of scaling text to distance for
   asymmetric/far monitors, not the exact ratio; the ratio itself is the
   well-known ADA/signage convention, flagged as such rather than presented as
   a verbatim quote from this page).

**Recommendation for our corner:** given source 2 (flat, not pitched, for a
multi-vantage viewer) and our ceiling of 3.19 u, mount the two monitors FLAT
against the wall (0 deg tilt, matching `display-wall.glb`'s existing flush
mounting rather than the current smart board's pitched panel), bottom edge at
1.4 u (character eye height ~1.6 u of an 1.8 u character, so bottom-at-1.4/
top-at-2.0 keeps the panel centered slightly below standing eye level per
source 1's "top edge at/below eye level" principle, adapted for a wall/room
context rather than a desk), each panel ~1.0 u wide x 0.6 u tall (matches
`display-wall.glb`'s existing ~1.0 w proportions doubled from a single-desk
monitor), with a 0.15-0.2 u gap between the two panels (source 2's photos show
side-by-side video-wall panels gapped roughly 10-15% of one panel's width,
read qualitatively from the photos, not a numeric spec on the page — flagged
as an estimate). Total footprint ~2.15-2.2 u wide, well inside the 45 deg
corner's available wall run. Legibility check (source 3's heuristic): at the
default camera's approximate viewing distance to that corner (~6-8 u from a
mid-room vantage), any label text on the panels should render at >= ~0.6-0.8 u
character height by the viewing-distance/10 rule-of-thumb to stay readable —
i.e. don't put paragraph-scale text on these, headline/number-scale only.

### C. Character nameplate / label conventions (5 sources) + model-tier icon set

1. **support.discord.com — "What do those colored dots next to my avatar
   mean?"** — exact color-to-state mapping: green=online, yellow=idle (shown
   as a moon shape, not just a color), red=do-not-disturb, gray=offline/
   invisible, purple=streaming. Dot sits at the avatar's bottom-right corner,
   small relative to the avatar (roughly 1/4-1/3 of avatar diameter based on
   Discord's own UI proportions).
2. **estudy247.com — Slack presence guide** — simpler 2-state convention:
   green dot = active now, yellow dot = away/idle, NO dot at all = offline —
   i.e. absence-of-indicator is itself a valid third state, which is cheaper
   to implement than a 3rd dot color.
3. **among-us.fandom.com/wiki/Fonts** — Among Us renders player names above
   the character model in a bold, high-contrast font (Arimo-derived) chosen
   specifically for legibility "even at small in-game text sizes" — i.e. the
   genre answer to "will this read from camera distance" is bold weight +
   high contrast outline, not a larger font size.
4. **RimWorld mood-bar color convention** (CM-Color-Coded-Mood-Bar mod page,
   steamcommunity.com/sharedfiles/filedetails/?id=2006605356) — status color
   ladder: red=critical/extreme, orange=major concern, yellow=minor concern,
   blue/gray=neutral, green=good — a 5-step traffic-light-plus-neutral ramp,
   richer than Discord's 4-state but same "red=bad, green=good, gray=neutral"
   logic.
5. **Two Point Hospital staff label convention** (genre knowledge cross-
   referenced against this file's own UX-1 pass, which already cited Two Point
   Hospital for hover-tooltip UX — reusing the SAME game for a DIFFERENT fact
   here: its on-character labels are name-only text with a small skill/mood
   icon set to the side, revealed on hover rather than always-on, keeping the
   permanent on-screen footprint to just the name).

**Label design for HQ:** name (bold, high-contrast/outlined text, per source
3) + one small status dot (per sources 1/2, sized ~1/4 of the label's own
height) + one model-tier glyph immediately after the name (per source 5's
"icon beside name" placement) + hover-only detail card (consistent with this
file's own UX-2 convention already logged above: hover=tooltip, click=focus).
Truncate names to a fixed character budget the way Among Us caps at 10 chars
(source 3) — recommend 12-14 chars given our labels carry a name AND a glyph.

**Model-tier icon set (emoji/glyph only — verified against Anthropic's own
brand-guidelines skill/press materials: third-party use of the actual
Anthropic wordmark/logo requires grabbing assets from Anthropic's own official
source and is trademark-protected, so a generic in-scene label is the safer
choice; we ship NO Anthropic logo, wordmark, or brand color combination,
using plain glyphs instead):**

| Runtime | Glyph | Why it reads |
|---|---|---|
| Claude Sonnet | lightning bolt | mid-tier "fast/frequent worker" connotation, distinct from Opus |
| Claude Opus | crown or sparkle | top-tier/"judgment" connotation without using any Anthropic mark |
| Claude Haiku | leaf | "light/cheap" connotation, distinct silhouette from the other two |
| Local qwen (Ollama) | house | "runs at home/on-box", clearly non-cloud |
| Plain Python/cron | gear | mechanical/deterministic, no LLM at all |
| Unknown | question mark | explicit "not yet classified" rather than a blank |

### D. Character pack options (3 candidates + rejected list)

**Candidate 1 — Kenney "Blocky Characters" (RECOMMENDED).**
Author: Kenney. Page: https://kenney.nl/assets/blocky-characters . License
quoted from the page: **"Creative Commons CC0"** (fetched live this session).
Also independently confirmed via Kenney's own announcement
(x.com/KenneyNL/status/1932369466249142622, quoted): "Blocky Characters has
been released! Features 18 characters with 27 animations. The whole package
is CC0 so completely free to use in any sort of project, by anyone." Format:
separate FBX/OBJ/glTF exports, 18 skins, 27 animations, direct CDN zip:
https://kenney.nl/media/pages/assets/blocky-characters/8369c0cf30-1749547469/kenney_blocky-characters_20.zip
— no login/name-your-price gate (same direct-CDN pattern already used for
every other Kenney pack in LICENSES.md). No preview screenshot fetched this
pass (page renders a live 3D viewer, not a static image URL) — note as
unverified visual until a build worker opens it. Judgment: this is the SAME
publisher and CC0 license as our existing Mini Characters, and "blocky" is
Kenney's own naming for a chunkier, more legible-from-distance silhouette
than the "Mini" line — directly targets the walking-sticks complaint by
construction (thicker limb geometry is the stated design intent of a
"blocky" pack vs. a "mini" one), while staying visually consistent (same
flat-shaded low-poly Kenney house style) next to our existing furniture.

**Candidate 2 — KayKit "Character Pack: Adventurers" (ALTERNATE).**
Author: Kay Lousberg. Page: https://kaylousberg.itch.io/kaykit-adventurers .
License quoted: "Free for personal and commercial use, no attribution
required. (CC0 Licensed)" — also independently confirmed on the GitHub
mirror (https://github.com/KayKit-Game-Assets/KayKit-Character-Pack-Adventures-1.0),
quoted: "Licensed under CC0 1.0 Universal, see LICENSE.txt for more
information." Format: FBX + GLTF, free tier = 5 characters (Barbarian, Mage,
Rogue, Rogue Hooded, Knight), Extra tier ($7.95+, NOT free, adds
Engineer/Druid/larger Barbarian — excluded from consideration since it fails
the "no login/paywall" requirement), 75 total animations across the pack per
the GitHub README, single shared 1024x1024 texture atlas. Download: itch.io
page requires visiting the store listing but the FREE tier button does not
demand payment (itch.io's own "$0 or more" pattern) — flagged as a MILD gate
vs. Kenney's zero-friction CDN link, not a hard blocker. Also listed on the
Godot Asset Library (godotengine.org/asset-library/asset/2129) as a possible
lower-friction mirror, not independently verified this pass. Judgment:
stylized fantasy-adventurer aesthetic (capes, armor, weapons) reads as a
harder visual clash against our sci-fi-office Kenney kit than Candidate 1 or
3 — a Barbarian at a trading desk is a bigger stretch than a blocky Kenney
office worker. Limbs are chunkier/more human-proportioned than Kenney Mini's
thin blocky arms, so it WOULD fix the walking-sticks read, at the cost of a
bigger genre mismatch.

**Candidate 3 — Quaternius "Universal Base Characters" (ALTERNATE, WITH
CAVEAT).** Author: Quaternius. Page:
https://quaternius.com/packs/universalbasecharacters.html (also
quaternius.itch.io/universal-base-characters). License quoted: "CC0" /
"Free to use in personal, educational and commercial projects." Format: FBX,
OBJ, Blend, glTF. 6 base body models (Superhero/Regular/Teen x male/female)
plus 20 hairstyles for mix-and-match variety (more visual diversity per-pack
than either candidate above). **Caveat, UNVERIFIED severity:** the fetched
page shows this pack itself marked **"Animated: No."** The earlier WebSearch
summary's mention of animations refers to a SEPARATE "Universal Animation
Library" pack the models are built to be retargeted onto, not bundled
animation clips in this download. That means Candidate 3 needs a second pack
fetched and a rig-retarget step to satisfy the "walk+idle+sit/typing clips"
requirement — meaningfully more integration work than Candidates 1 or 2,
which ship animations in the same download. Judgment: Quaternius's house
style (rounder, more human proportions, thicker limbs than Kenney Mini) would
also fix the walking-sticks read, but the animation-retarget dependency is a
real cost the other two candidates don't carry — demoted to alternate for
that reason, not for license or visual-fit concerns.

**Rejected without full write-up:** KayKit "Skeletons" pack (wrong genre,
horror/undead, worse mismatch than Adventurers) and "Prototype Bits" (no
character meshes, primitives only); poly.pizza's plain "character" search CC0
filter (returned mostly single-pose static props, not rigged animated
humanoids, when spot-checked in this file's earlier MODELS-builder pass for a
different asset, and no new evidence this session that the character results
differ); opengameart.org rigged-character search (not opened this pass —
Kenney/KayKit/Quaternius already gave 3 clean, license-verified candidates
within the time budget, so the lower-curation OGA aggregator wasn't needed).

**Walking-sticks artifact — root-cause paragraph (UNVERIFIED, cheap test
proposed).** Given the confirmed GLB facts (Kenney Mini Characters GLB has no
held-item/prop mesh node — only root/leg-left/leg-right/torso/arm-left/
arm-right/head — and the "interact-right/left" clips are being reused as a
typing stand-in), the most likely visual cause is that those interact clips
pose one arm in a straight, extended, low-amplitude bend that reads as a thin
rigid rod against the character's flat-shaded, uniformly-purple-shirted arm
geometry — with no elbow bend or hand-prop mesh to break up the silhouette, a
fully-extended thin blocky arm limb photographs as a "stick" rather than a
"reaching arm," and the effect is likely WORSE on the purple-shirt variant
specifically if that variant's arm material has less shading/AO contrast than
the other skins (unverified — needs a side-by-side material diff, not
checked this pass). Cheap test: re-render the scene with the interact-right/
left clips DISABLED (characters holding idle/walk poses only) and compare —
if the "stick" read disappears, the animation choice is the cause, not the
mesh/material; if it persists even at idle, the mesh/material is the cause
and a character-pack swap (Candidate 1/2/3 above) is the only real fix.

### E. One-screen summary

**DECISIONS FOR J:**
1. Floor plan: **Option 1 (inward ring, r5.5, desks face wall)** — pulls
   desks off the wall by ~1.5-2u, keeps existing door/furniture layout.
   Alternates: Option 2 (two rings, denser, more geometry risk), Option 3
   (flat wall-bay rows, loses radial symmetry).
2. Character pack: **Kenney "Blocky Characters"** (CC0, same publisher/style
   as current, zero-friction CDN download, chunkier limbs fix walking-sticks
   read). Alternates: KayKit Adventurers (chunkier but fantasy-genre clash),
   Quaternius Universal Base Characters (best variety, but needs a second
   animation-library pack + retarget work).
3. Monitor mount: **flat (0deg tilt)**, bottom edge ~1.4u / top ~2.0u, two
   panels ~1.0u wide each with ~0.15-0.2u gap, centered in the 45deg corner
   at r~6.0-6.3, replacing the pitched smart board.
4. Label icon set: **lightning=Sonnet / crown-or-sparkle=Opus / leaf=Haiku /
   house=local-qwen / gear=script-cron / question-mark=unknown** — glyphs
   only, no Anthropic brand marks (brand guidelines reserve the actual
   logo/wordmark for Anthropic-sanctioned use).
5. Label shape: bold outlined name + small status dot (Discord-style
   green/yellow/red/gray) + tier glyph, hover-only detail card, ~12-14 char
   name truncation.

**MECHANICAL (ship now, no J needed):**
1. Fix the desk-ring math bug: DeskCluster radius 6.5+0.8-offset -> flat 5.5
   is a pure numeric correction against the ALREADY-established 7.5u wall
   half-extent — not a design judgment call, it's fixing desks currently
   inside the wall mesh.
2. Pull the smart-board/monitor corner from r6.3 to r6.0-6.3 (already close;
   confirm against final monitor panel width once Kenney/display-wall asset
   is chosen).
3. Wire the Discord-style status-dot + bold-name label component (colors:
   green/yellow/red/gray per source 1/2 above) — this is a UI-component add,
   not an asset swap, so it doesn't block on J picking a character pack.
4. Download Kenney Blocky Characters zip via the same direct-CDN pattern
   already used for every other Kenney pack in LICENSES.md (no new vendor,
   no login) — but WAIT for J's pack pick before swapping it in, since two
   valid alternates exist.
5. Run the walking-sticks cheap test (disable interact clips, screenshot,
   compare) — pure diagnostic, no asset change, answers the UNVERIFIED item
   above before any pack-swap effort is spent.

### Pathing pass references (WALK-ROUTING worker)
Waypoint graphs (points of interest connected by edges, A*/Dijkstra) are the classic pre-NavMesh approach used by management/strategy sims for door-aware routing — see [Pathfinding in Video Games: A*, Dijkstra and NavMesh](https://www.udit.es/en/pathfinding-en-videojuegos-a-a-estrella-dijkstra-y-navmesh-con-ejemplos-paso-a-paso/) and [Navigation mesh (Wikipedia)](https://en.wikipedia.org/wiki/Navigation_mesh) on off-mesh links/dynamic obstacles for door interactions specifically. This matches this codebase's own choice (layout.ts#buildWalkGraph + liveAgentWalk.ts#findWalkPath) over a full navmesh, given the small (~30) fixed node count.
