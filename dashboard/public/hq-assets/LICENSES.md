# HQ 3D asset licenses

All packs below are **CC0 1.0 Universal** (public domain dedication) — verified on each
pack's own page/license file, not assumed from the source site's general reputation.
No attribution is legally required for any of them; the "attribution text" column
records each creator's own *voluntary* credit line, included as good practice for a
public repo. No Mixamo/Synty/Sketchfab-store/NC/ND content is used anywhere below.

| # | Pack | Author | Source URL | License | License URL | Downloaded | Files kept | Attribution (voluntary) |
|---|---|---|---|---|---|---|---|---|
| 1 | Mini Characters (1.0) — **RETIRED 2026-09-15**, see row 11 | Kenney | https://kenney.nl/assets/mini-characters | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-13 | `character-male-a.glb`, `character-female-a.glb`, `character-male-b.glb` (kept on disk, unused by default — one-line revert, see SetKit.tsx#CHARACTER_PACK) | "Kenney" / "www.kenney.nl" |
| 2 | Space Station Kit (1.0) | Kenney | https://kenney.nl/assets/space-station-kit | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-13 | `table.glb`, `table-inset.glb`, `table-large.glb`, `chair.glb`, `chair-armrest.glb`, `computer.glb`, `computer-screen.glb`, `pipe.glb`, `pipe-bend.glb`, `door-single.glb`, `door-double.glb`, `container.glb`, `wall-window.glb`, `structure-panel.glb`, `display-wall.glb` | "Kenney" / "www.kenney.nl" |
| 3 | Modular Space Kit (1.0) | Kenney | https://kenney.nl/assets/modular-space-kit | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-13 | `corridor.glb`, `corridor-corner.glb`, `corridor-intersection.glb`, `corridor-wide.glb`, `room-small.glb`, `room-large.glb`, `gate-door.glb`, `cables.glb` | "Kenney" / "www.kenney.nl" |
| 4 | Space Kit (2.0) | Kenney | https://kenney.nl/assets/space-kit | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-13; terrain/prop pieces added 2026-09-14 | `astronautA.glb`, `barrels.glb`, `rock.glb`, `rocks_smallA.glb`, `rock_largeA.glb`, `rock_largeB.glb`, `crater.glb`, `craterLarge.glb`, `satelliteDish.glb`, `satelliteDish_large.glb`, `rover.glb`, `structure.glb`, `supports_high.glb`, `pipe_straight.glb`, `pipe_corner.glb` | "Kenney" / "www.kenney.nl" |
| 5 | KayKit: Space Base Bits (1.0) | Kay Lousberg | https://github.com/KayKit-Game-Assets/KayKit-Space-Base-Bits-1.0 (official mirror of https://kaylousberg.itch.io/space-base-bits) | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-13 | `lights.gltf`, `lights.bin`, `spacebits_texture.png` | "Kay Lousberg" / "www.kaylousberg.com" |
| 6 | Dikhololo Night (HDRI, 1k) | Poly Haven | https://polyhaven.com/a/dikhololo_night | CC0 1.0 | https://polyhaven.com/license | 2026-09-13 | `dikhololo_night_1k.hdr` | "Poly Haven" (not required) |
| 7 | Furniture Kit (2.0) | Kenney | https://kenney.nl/assets/furniture-kit | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-14 | `television-modern.glb` (renamed from `televisionModern.glb`); `potted-plant.glb` (renamed from `pottedPlant.glb`); `plant-small.glb` (renamed from `plantSmall1.glb`) -- 3 of 116 models | "Kenney" / "www.kenney.nl" |
| 8 | Spaceship (mirror) | Quaternius | https://poly.pizza/m/PQzePrvBCD (Quaternius's own model, re-hosted by Poly Pizza's static CDN) | CC0 1.0 | https://poly.pizza/m/PQzePrvBCD (page states "Public Domain (CC0)") | 2026-09-14 | `shuttle.glb` (renamed from the source's own generic "Spaceship" title) | "Quaternius" |
| 9 | Scifi Computer (mirror) | Quaternius | https://poly.pizza/m/U0xmt6tUlL | CC0 1.0 | https://poly.pizza/m/U0xmt6tUlL (page states "Public Domain (CC0)") | 2026-09-14 | `scifi-computer.glb` | "Quaternius" |
| 10 | Pipes Panel (mirror) | Quaternius | https://poly.pizza/m/rzvuy93JU3 | CC0 1.0 | https://poly.pizza/m/rzvuy93JU3 (page states "Public Domain (CC0)") | 2026-09-14 | `pipes-panel.glb` | "Quaternius" |
| 11 | Blocky Characters (2.0) — **ACTIVE character pack**, see Update note below | Kenney | https://kenney.nl/assets/blocky-characters | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-15 | `character-a.glb`, `character-b.glb`, `character-c.glb`, `character-e.glb` (4 of 18 letters; GLB format from the zip) | "Kenney" / "www.kenney.nl" |

## Update 2026-09-15 (BLOCKY-CHARACTERS builder, character body swap)

J, live on `/hq`: "find different character models, I don't like the current
ones" -- the Kenney Mini Characters rig's thin, straight-cylinder arms read
as "walking sticks." Fetched the Blocky Characters page directly this session
(WebFetch, not assumed from memory): license line quoted verbatim
`"Creative Commons CC0"`, download URL
`https://kenney.nl/media/pages/assets/blocky-characters/8369c0cf30-1749547469/kenney_blocky-characters_20.zip`.
`curl -L`'d the zip (2,148,510 bytes) to the session scratchpad, extracted,
and re-read the zip's own `License.txt` verbatim -- matches row 1's license
text word-for-word (CC0, "You can use this content for personal, educational,
and commercial purposes").

Inspected 5 of 18 letter variants (`character-a` through `character-e`) by
parsing each GLB's own JSON chunk directly (same from-the-binary technique
this file's prior passes use, via a small one-off Node script + the existing
`dashboard/scripts/glb_extents.mjs` for bounding-box height) and by eyeballing
each letter's own `Previews/character-*.png` thumbnail for wardrobe: all 5
share the IDENTICAL rig (8 nodes: `root/leg-left/leg-right/torso/arm-left/
arm-right/head` under a `character-<letter>` root; 6 meshes; 0 skins -- this
pack animates rigid body-part nodes directly via keyframed node TRS, not
mesh skinning, so `SkeletonUtils.clone` still applies cleanly as a plain
hierarchy clone) and the SAME 27-clip animation list. No mesh node in any of
the 5 bodies represents a held item/prop -- the "holding-*"/"attack-*"
animation *names* exist (shared across every letter, since it's one shared
rig) but only pose the empty hands, since no weapon/tool mesh ships in the
model itself. `character-d`'s preview reads as a hazmat/coverall suit
(rejected -- not office-appropriate); `character-a/b/c/e` all read as plain
civilian clothing (jacket, hoodie, sweater, cardigan) and were kept --
4 bodies total, one more than the retired 3-body Mini Characters roster, all
`pickCharacterBody`'s seeded hash needs. Raw bounding-box height (root-space
AABB via `glb_extents.mjs`): all 4 measure **Y = 2.700** identically (same
shared rig) -- legs 0.0-1.0, torso 1.0-1.9, head 1.9-2.7 in the model's own
native units; `characterScale()` (SetKit.tsx) derives each body's world scale
as `CHARACTER_TARGET_HEIGHT(1.8) / 2.7 = 0.6667` automatically, same formula
as before, no hardcoded scale added.

Every `KitAgent.tsx#CLIP_TABLE` clip name this project's animation states use
(`sit`, `emote-no`, `emote-yes`, `interact-right`, `interact-left`, `walk`,
`idle`) is present verbatim on all 4 kept bodies -- zero substitute/fabricated
clip names needed, a cleaner result than the retired Mini Characters pack's
seated-pose gaps (see `KitAgent.tsx`'s own LIVE-1 item 2a comment).

Total added: 4 files, 448,368 bytes (0.43 MB) under
`kenney-blocky-characters/` -- well under the 3 MB session budget. The
2,148,510-byte raw zip and the other 14 unused letters stay in the session
scratchpad, never committed. `SetKit.tsx#CHARACTER_PACK = "blocky"` is the one
flag switching KIT_PATHS/CHARACTER_BODY_IDS/CHARACTER_RAW_HEIGHT between the
two packs -- flipping it back to `"mini"` is a complete, tested revert since
every Mini Characters file stays on disk untouched (row 1 above).

## Update 2026-09-14 (MODELS builder, smart-board asset hunt)

J, live on `/hq` (relayed via the MODELS builder brief): "the ideas board needs
to basically be on a FLOATING SMART BOARD on the wall inside the main office
... go on an asset site and find something that looks like a screen ... open
them up and look at them, take your time." Real hunt performed this session
(browser tool, not assumed from memory), in this order:

1. **Already-bundled candidates inspected first** (Research & Reuse before any
   new download) -- parsed the raw GLB binaries directly (same technique this
   file's own prior passes use) for every plausible piece already in
   `kenney-space-station-kit/`: `display-wall.glb` (raw 0.400w x 0.461h x
   0.384d -- boxy/cube-like, reads as a control console, not a wide screen),
   `structure-panel.glb` (0.850w x 0.125h x 0.850d -- flat but built as a
   floor/ceiling panel, wrong proportions/orientation for a wall screen),
   `computer-screen.glb` (0.800w x 0.661h x 0.438d -- already every desk's own
   monitor via DeskScreen.tsx; reusing it at giant scale for "the board" would
   read as a blown-up desk monitor, not a distinct fixture). All three
   rejected -- none has the thin, wide, bezelled-screen silhouette J asked
   for.
2. **poly.pizza** (https://poly.pizza/search/monitor), CC0 filter -- 3 free
   "Monitor" results (CreativeTrio, Poly by Google, Zsky), all the same
   generic desk-monitor-on-a-stand shape already covered by
   `computer-screen.glb` above. Rejected: no size/format advantage, nothing
   reads as a "board" rather than a desk peripheral.
3. **poly.pizza's own mirror of Kenney's "Furniture Kit"** (116 models,
   browsed live via its in-page 3D viewer, orbited to see front/back) --
   found `Television` (a real flat-panel-on-a-small-stand silhouette: thin
   bezel, flat lighter-toned screen face, distinct from `Television Vintage`'s
   bulky CRT box and `Cabinet Television`'s enclosed-cabinet shape, both
   rejected as wrong silhouette for "smart board"). This is the candidate
   used -- see below.
4. **quaternius.com** -- browsed the live catalog (`Assets` page); no
   "Ultimate Office" pack exists in the current catalog (the name in this
   project's own HQ-ULTRA-TIER-BRIEF doesn't resolve to a live page today).
   Opened "Modular Sci-Fi Megakit" from the catalog grid; its card did not
   open a browsable detail view in this session (same JS-driven-catalog
   friction this file's own 2026-09-13 pass already documented for
   Quaternius's character packs) -- not pursued further given a verified,
   license-clean candidate was already in hand and the task's own 25-minute
   hunt budget.
5. **kaykit.itch.io** -- not separately browsed this pass; the only KayKit
   pack already in this project (`Space Base Bits`) is a lights/greeble set,
   and time budget favored confirming the strong Kenney lead over further
   exploratory browsing.

**Chosen: `televisionModern.glb`**, downloaded directly from kenney.nl's own
CDN (`https://kenney.nl/media/pages/assets/furniture-kit/440e0608a4-1677580847/kenney_furniture-kit.zip`,
5,130,729 bytes, `curl`), License.txt inside the zip re-quoted and confirmed
CC0 1.0 verbatim (same text as row 2 above). Parsed the extracted
`Models/GLTF format/televisionModern.glb` directly: glTF binary magic
confirmed at byte 0, 1 mesh / 1 node / 2 materials (`metalDark`, `metal`), raw
bbox 0.685w x 0.455h x 0.128d -- a genuine thin flat-screen-on-a-stand
silhouette, ~144 triangles. Only this one file (6,368 bytes) was kept and
copied to `kenney-furniture-kit/television-modern.glb`; the other 115 models
and the 5.1 MB raw zip stay in the session scratchpad, never committed.
SmartBoard.tsx layers its own canvas-texture plane on the model's front face
for the actual IdeasWall content (title/cards/verdict) rather than retexturing
either of the GLB's own 2 materials in place -- avoids needing to identify
which submesh is the screen vs. the bezel/stand, and matches this codebase's
own established DeskScreen.tsx/BaySign.tsx "separate canvas-texture face"
convention. Total added this pass: 6,368 bytes (0.006 MB), well under the
session budget.

**Procedural-fallback note (not needed):** the task brief authorized a clean
procedural board (bezel box + emissive face + wall arms + LED) if no CC0
model was convincing. Not used -- `televisionModern.glb` cleared the bar. The
wall-mount arms + backing plate + status LED are still added procedurally
around the found model (SmartBoard.tsx) since the kit piece itself ships only
its own small pedestal foot, not a wall-mount bracket.

## Update 2026-09-14 (World-3 environment pass, ENVIRONMENT builder)

J: "it looks like the background is a grey abyss... why not a space theme...
the design needs work still" -- coordinator decision: finish the space-base
theme the bundled kits already implied. Downloaded the SAME already-catalogued
Kenney Space Kit (2.0) zip directly from the URL above (`kenney_space-kit.zip`,
6,677,531 bytes, `curl`), extracted to a scratchpad, and confirmed its own
`license.txt` (root of the zip) states CC0 1.0 verbatim -- same text quoted in
row 4 above, re-verified from this fresh download rather than assumed from the
earlier 2026-09-13 pass. All 13 newly-kept `.glb` files were confirmed to
start with the glTF binary magic (`glTF` at byte 0, checked via `xxd`) before
copying into `kenney-space-kit/`; none reference an external `.bin`/texture
file (the zip's GLTF-format export is fully self-contained per-file, verified
by listing the extraction folder for any loose `.bin`/`.png` -- none found).
Total added: 148,724 bytes (0.14 MB) -- well under the 15 MB session budget.
Used by: `Ground.tsx`/`Rocks.tsx` (rocks, craters -- instanced + individual
boulders), `BaseProps.tsx` (dishes, rover, solar-array supports, pipes).

## Verification performed this session

- Every pack's license was read from **its own page or the `License.txt`/`LICENSE.txt`
  shipped inside its own zip** (quoted CC0 text, not inferred from the host site).
- Every kept `.glb` was parsed and confirmed to start with the glTF binary magic
  (`glTF` at byte 0) with a valid JSON chunk; `lights.gltf` was parsed as JSON and its
  `buffers`/`images` references (`lights.bin`, `spacebits_texture.png`) confirmed present
  alongside it; `dikhololo_night_1k.hdr` was confirmed to start with the Radiance
  (`#?RADIANCE`) magic bytes. See `manifest.json` for the per-file inspection results
  (mesh/skin counts, animation clip names).
- Total kept size: **4.46 MB** (raw downloads in the scratchpad total well under the
  200 MB/pack cap; nothing in the scratchpad was deleted).

## Sources evaluated and NOT used (with reasons)

- **Quaternius "Universal Base Characters"** (https://quaternius.com/packs/universalbasecharacters.html,
  CC0) — this is the pack the HQ-ULTRA-TIER-BRIEF names first, and independent web
  research confirms it's what other three.js/Godot/Unity developers actually reach for
  as the CC0 alternative to Mixamo. It was **not downloadable without a browser**: the
  page's own "Download here" button routes to `quaternius.itch.io/universal-base-characters`,
  which itch.io gates behind a JS-driven "Name your own price" purchase flow (even at
  $0) — there is no static file URL, and the task rules out headless browsers/login
  flows. Quaternius's own animation packs ("Universal Animation Library"/"2") ARE
  mirrored with genuine direct-download zips on opengameart.org and were fetched to the
  raw scratchpad for inspection, but they are rig+animation-only (no bundled body mesh)
  and retargeting them onto a different body requires Blender/a game engine — outside
  this task's no-build, no-GPU constraint. Quaternius's 2018-era "Animated LowPoly
  Robot" (opengameart.org, CC0, direct zip, 14 baked clips) was also fetched and
  inspected, but it only ships Blend/FBX/OBJ — no glTF/GLB — so it can't be loaded by
  `useGLTF` without an offline conversion step this task can't perform. All three raw
  zips are left in the scratchpad (`hq-assets-raw/quaternius_*.zip`) in case a future
  session gets Blender or itch access.
- **Kenney "Toon Characters"** — confirmed CC0/direct-download, but inspection of its
  own page shows it's a 2D sprite/platformer pack, not a rigged 3D glTF character.
- **Kenney "Modular Characters"** — direct-download CC0, but the zip (2014-era) contains
  only PNG paper-doll face/hair textures, no 3D geometry at all.
- **Quaternius "Sci-Fi Essentials Kit" / "Modular Sci-Fi MegaKit"** — both CC0 and
  directly downloadable via opengameart.org, but sized 87-160 MB combined; skipped in
  favor of Kenney's Space Station/Modular Space Kits, which already cover the same
  desk/console/corridor/door prop categories at a fraction of the size and share a
  consistent internal scale with the Kenney character pack (see `manifest.json`
  `scaleHintNote`).

## The one manual step for J (Mixamo)

Mixamo would materially beat every option above on ONE axis only: **animation breadth
and retargeting convenience** (drop any humanoid rig in, get 2,000+ clips auto-retargeted,
including genuine "type at keyboard"/"talk"/"hand off object" gestures that no CC0 pack
below ships). It is **not used here** — Mixamo's terms are a custom Adobe EULA, not
CC0/CC-BY, and redistributing the downloaded FBX/glTF in a public repo is against those
terms (personal/attributed-project use only, no restriction-free redistribution). If J
wants Mixamo-quality animation coverage specifically for the "typing at a desk" /
"handing something to another agent" gestures the CC0 packs above don't have natively,
the manual step is: J (not Claude) signs in to mixamo.com himself, downloads the
specific clips onto his own machine, and re-exports/re-targets them locally — those
files would then need to stay **out of the public GitHub repo** (gitignored, loaded from
a local-only path) rather than committed, since Mixamo content can't legally ship in a
public repo under these terms.

## Update 2026-09-14 (WORLD-6 builder, W2 asset hunt)

J's standing brief: "open them up and look at them, take your time." Real hunt performed
this session (browser tool + the Artifact/network layer to resolve each model's real
download URL, not assumed from a listing thumbnail), goal: "make the base read as a real
trading outpost and UNIQUE," at most 6 pieces, under 3 MB total.

**kenney.nl's own in-page search never filtered results this session** (typed/filled the
search box via both `computer.type` and `form_input`; the result grid never changed —
same JS-driven-catalog friction this file's own 2026-09-13 pass already documented for
Quaternius's character packs, now also hit on Kenney's own site) — worked around by
navigating directly to known asset-page URLs instead (`kenney.nl/assets/<slug>`).

**poly.pizza cracked further this pass**: the CC0-licence filter (Licence dropdown ->
"CC0 1.0") works via the UI, and the in-page 3D viewer was used to actually look at every
candidate below (orbited via the "Toggle Turntable" control) before picking one — never a
thumbnail-only guess. For 3 Quaternius pieces, itch.io's own "name your price" gate (the
blocker the 2026-09-13 pass hit and gave up on) is now confirmed **avoidable**: poly.pizza
re-hosts Quaternius's own uploads on its own static CDN, one static file per model, found
by reading each model's own `/api/model/<id>/bundles` response (`S3ID` field) and
confirming a live `HEAD https://static.poly.pizza/<S3ID>.glb` (200, `content-type:
gltf-binary`) before downloading — genuine direct file URLs, not a scrape/bypass of any
paywall (poly.pizza's own site openly re-hosts and serves these as free CC0 downloads).

**Candidates opened and REJECTED**:
- kenney.nl "Nature Kit" (330 files, CC0) — opened and viewed its own hero render: bright
  cartoon-saturated stylized trees/foliage (cyan/orange/purple), tonally wrong for this
  scene's cool Tron/Blade-Runner palette (`palette.ts`'s own established direction) —
  would read as a different game's asset dropped in, not a trading-outpost interior plant.
- poly.pizza "Potted plant" search, paid-tier results (Survival Engine, Toon Fantasy
  Nature, Ultimate Low Poly Nature Pack, Hyper Casual Trees And Plants) — all paid, not
  CC0, filtered out by the Licence dropdown itself.
- poly.pizza "Spaceship" by Quaternius, `/m/VSxUAFhzbA` (green/orange/black toy-like
  X-wing shape) and `/m/u105mYHLHU` (bulbous yellow/black "bee" pod with a huge blue
  window) — both viewed via the turntable, both read as too cartoonish/toy-scaled for a
  "shuttle parked on a landing pad" read; `/m/PQzePrvBCD` (chosen below) is a sleeker
  white/grey swept-wing shuttle silhouette from the SAME uploader/bundle, a much closer
  match, tints cleanly via `KitProp`'s existing `tint`/`tintStrength` mechanism regardless
  of its raw white base color.
- poly.pizza "server rack" search — no genuine server-rack silhouette in CC0 results
  ("Shelf Tall", "Coat Rack", "Corrugated Iron Sheet", "Dishrack" all rejected as wrong
  category entirely); pivoted the search term to "sci-fi terminal" / "computer server
  rack sci-fi", which surfaced the Quaternius "Scifi Computer" piece actually used below.
- Placing the "Scifi Computer"/"Pipes Panel" pair literally "along the hub's second wall"
  (the brief's own suggested location) was evaluated and set aside: every open radius on
  the hub's own brain-wall segment either collides with Gamma's own desk (radius 3.4,
  angle ~61deg — not this builder's file to move) or repeats the EXACT
  radius-6.8-is-invisible-from-the-default-camera failure `layout.ts#computeBrainWallMount`'s
  own header already documents and fixed once for the smart board itself; the hub's OTHER
  three wall segments are live persona-desk territory this session (LAYOUT/PEOPLE builders
  concurrently in that file tree — `git status` confirmed uncommitted changes there this
  session). Relocated to an exterior "server annex" cluster in `BaseProps.tsx` (this
  builder's own zero-contention file, with an already-proven `minClearRadius` placement
  pattern) instead of guessing at an interior spot this builder cannot verify is clear
  without risking another builder's own in-flight geometry.

**Verification performed this session (all 5 new files)**: every file's glTF binary magic
(`glTF` at byte 0) confirmed via `xxd`; every real-file byte size matches the `HEAD`
request's own `content-length` exactly (shuttle 62,668 B; scifi-computer 41,964 B;
pipes-panel 26,836 B; potted-plant 7,576 B; plant-small 8,224 B — total 147,268 B, 0.14 MB,
well under the 3 MB pass budget); the Kenney Furniture Kit zip's own `License.txt` was
re-extracted and re-read verbatim (byte-identical CC0 text to row 7's existing entry) from
THIS session's own fresh download, not assumed from the 2026-09-14 MODELS-builder pass;
every poly.pizza model page was read directly (`get_page_text`) for its own
"Public Domain (CC0)" license line before use. Every kept `.glb` was measured with
`dashboard/scripts/glb_extents.mjs` before being placed in any component — see
`BaseProps.tsx`/`HubInterior.tsx`/`BayInterior.tsx`'s own placement comments for the
per-piece raw bounds and the scale/offset derived from them.
