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
| 4 | Space Kit (2.0) | Kenney | https://kenney.nl/assets/space-kit | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-13 | `astronautA.glb`, `barrels.glb` | "Kenney" / "www.kenney.nl" |
| 5 | KayKit: Space Base Bits (1.0) | Kay Lousberg | https://github.com/KayKit-Game-Assets/KayKit-Space-Base-Bits-1.0 (official mirror of https://kaylousberg.itch.io/space-base-bits) | CC0 1.0 | https://creativecommons.org/publicdomain/zero/1.0/ | 2026-09-13 | `lights.gltf`, `lights.bin`, `spacebits_texture.png` | "Kay Lousberg" / "www.kaylousberg.com" |
| 6 | Dikhololo Night (HDRI, 1k) | Poly Haven | https://polyhaven.com/a/dikhololo_night | CC0 1.0 | https://polyhaven.com/license | 2026-09-13 | `dikhololo_night_1k.hdr` | "Poly Haven" (not required) |

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
