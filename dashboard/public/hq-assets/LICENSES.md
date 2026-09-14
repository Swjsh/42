# HQ 3D asset licenses

All packs below are **CC0 1.0 Universal** (public domain dedication) — verified on each
pack's own page/license file, not assumed from the source site's general reputation.
No attribution is legally required for any of them; the "attribution text" column
records each creator's own *voluntary* credit line, included as good practice for a
public repo. No Mixamo/Synty/Sketchfab-store/NC/ND content is used anywhere below.

| # | Pack | Author | Source URL | License | License URL | Downloaded | Files kept | Attribution (voluntary) |
|---|---|---|---|---|---|---|---|---|
| 1 | Mini Characters (1.0) | Kenney | https://kenney.nl/assets/mini-characters | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-13 | `character-male-a.glb`, `character-female-a.glb`, `character-male-b.glb` | "Kenney" / "www.kenney.nl" |
| 2 | Space Station Kit (1.0) | Kenney | https://kenney.nl/assets/space-station-kit | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-13 | `table.glb`, `table-inset.glb`, `table-large.glb`, `chair.glb`, `chair-armrest.glb`, `computer.glb`, `computer-screen.glb`, `pipe.glb`, `pipe-bend.glb`, `door-single.glb`, `door-double.glb`, `container.glb`, `wall-window.glb`, `structure-panel.glb`, `display-wall.glb` | "Kenney" / "www.kenney.nl" |
| 3 | Modular Space Kit (1.0) | Kenney | https://kenney.nl/assets/modular-space-kit | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-13 | `corridor.glb`, `corridor-corner.glb`, `corridor-intersection.glb`, `corridor-wide.glb`, `room-small.glb`, `room-large.glb`, `gate-door.glb`, `cables.glb` | "Kenney" / "www.kenney.nl" |
| 4 | Space Kit (2.0) | Kenney | https://kenney.nl/assets/space-kit | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-13; terrain/prop pieces added 2026-09-14 | `astronautA.glb`, `barrels.glb`, `rock.glb`, `rocks_smallA.glb`, `rock_largeA.glb`, `rock_largeB.glb`, `crater.glb`, `craterLarge.glb`, `satelliteDish.glb`, `satelliteDish_large.glb`, `rover.glb`, `structure.glb`, `supports_high.glb`, `pipe_straight.glb`, `pipe_corner.glb` | "Kenney" / "www.kenney.nl" |
| 5 | KayKit: Space Base Bits (1.0) | Kay Lousberg | https://github.com/KayKit-Game-Assets/KayKit-Space-Base-Bits-1.0 (official mirror of https://kaylousberg.itch.io/space-base-bits) | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-13 | `lights.gltf`, `lights.bin`, `spacebits_texture.png` | "Kay Lousberg" / "www.kaylousberg.com" |
| 6 | Dikhololo Night (HDRI, 1k) | Poly Haven | https://polyhaven.com/a/dikhololo_night | CC0 1.0 | https://polyhaven.com/license | 2026-09-13 | `dikhololo_night_1k.hdr` | "Poly Haven" (not required) |
| 7 | Furniture Kit (2.0) | Kenney | https://kenney.nl/assets/furniture-kit | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-14 | `television-modern.glb` (renamed from `televisionModern.glb`; 1 of 116 models) | "Kenney" / "www.kenney.nl" |

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
