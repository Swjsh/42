"use client";

import { Suspense, useEffect, useMemo } from "react";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import DeskScreen from "./DeskScreen";
import { PALETTE, type ScreenLine } from "./palette";

// ─── HQ kit rebuild (2026-09-13, HQ-SCENE-PLAN.md) ──────────────────────────
// Real CC0 GLB pieces (Kenney Space Station Kit / Modular Space Kit / Space
// Kit, all bundled under public/hq-assets/, see manifest.json + LICENSES.md)
// replacing StationModule.tsx's procedural box/plane geometry. ULTRA TIER
// ONLY -- the TV tier keeps its existing cheap primitive path unchanged (see
// StationModule.tsx's own tier branch): real indexed GLB meshes + this many
// draw calls would blow the Mali-G31's draw-call budget, a tradeoff this
// plan calls out explicitly rather than silently regressing the kiosk.
//
// Three independent scale classes (bounding boxes verified this session by
// parsing the raw GLB binaries directly -- see HQ-SCENE-PLAN.md's "Verified
// facts" section for the numbers and reasoning; Modular Space Kit and Space
// Station Kit are NOT mutually scaled, they're different Kenney kit series):
//   - CHARACTER: target 1.8 world units tall (this task's own spec).
//   - FURNITURE (desk/chair/computer/etc, Space Station Kit): 2.0x uniform.
//   - ARCHITECTURE (room/corridor/gate-door, Modular Space Kit): 0.45x for
//     department bays, 0.5x for the hub -- chosen so the resulting footprint
//     lands inside the ALREADY-PROVEN camera composition (RING_RADIUS etc.)
//     instead of forcing a from-scratch, unverifiable camera re-derivation.

const KIT_BASE = "/hq-assets";

export const KIT_PATHS = {
  characters: {
    "character-male-a": `${KIT_BASE}/kenney-mini-characters/character-male-a.glb`,
    "character-female-a": `${KIT_BASE}/kenney-mini-characters/character-female-a.glb`,
    "character-male-b": `${KIT_BASE}/kenney-mini-characters/character-male-b.glb`,
  },
  furniture: {
    table: `${KIT_BASE}/kenney-space-station-kit/table.glb`,
    chair: `${KIT_BASE}/kenney-space-station-kit/chair.glb`,
    computer: `${KIT_BASE}/kenney-space-station-kit/computer.glb`,
    computerScreen: `${KIT_BASE}/kenney-space-station-kit/computer-screen.glb`,
    displayWall: `${KIT_BASE}/kenney-space-station-kit/display-wall.glb`,
    structurePanel: `${KIT_BASE}/kenney-space-station-kit/structure-panel.glb`,
    pipe: `${KIT_BASE}/kenney-space-station-kit/pipe.glb`,
    pipeBend: `${KIT_BASE}/kenney-space-station-kit/pipe-bend.glb`,
  },
  architecture: {
    roomSmall: `${KIT_BASE}/kenney-modular-space-kit/room-small.glb`,
    roomLarge: `${KIT_BASE}/kenney-modular-space-kit/room-large.glb`,
    corridor: `${KIT_BASE}/kenney-modular-space-kit/corridor.glb`,
    gateDoor: `${KIT_BASE}/kenney-modular-space-kit/gate-door.glb`,
  },
  lights: `${KIT_BASE}/kaykit-space-base-bits/lights.gltf`,
  hdri: `${KIT_BASE}/polyhaven-dikhololo-night/dikhololo_night_1k.hdr`,
} as const;

export type CharacterBodyId = keyof typeof KIT_PATHS.characters;
export const CHARACTER_BODY_IDS: CharacterBodyId[] = ["character-male-a", "character-female-a", "character-male-b"];

// Raw bounding-box height (Y axis), parsed from each GLB's own POSITION
// accessor min/max this session -- see HQ-SCENE-PLAN.md. Used to derive a
// per-body scale that lands every body at the SAME 1.8-unit standing height
// despite their slightly different native proportions.
export const CHARACTER_RAW_HEIGHT: Record<CharacterBodyId, number> = {
  "character-male-a": 0.671,
  "character-female-a": 0.7755,
  "character-male-b": 0.6613,
};

export const CHARACTER_TARGET_HEIGHT = 1.8;

// LIVE-1 item 1 (2026-09-14, J: "i cant really see"): the closer default
// camera (Scene.tsx#CAMERA_DIST_ULTRA/CAMERA_HEIGHT_ULTRA) still left
// characters reading small against the real kit furniture/architecture --
// 1.25x lands every body at 2.25 world units standing height, legible at the
// new ~16-unit overview distance without dwarfing the (unchanged) desk/chair
// furniture scale (FURNITURE_SCALE=2.0 is independent of this). Ultra tier
// only in EFFECT (characterScale() is the ONLY place either tier computes a
// character's world scale, and only KitAgent.tsx/GammaCharacter.tsx -- both
// ultra-only callers, see Agent.tsx's own `ultra` branch -- ever call it; the
// TV tier's procedural capsule body in Agent.tsx has its own hardcoded
// geometry args, untouched by this constant).
export const CHARACTER_SCALE = 1.25;

export function characterScale(bodyId: CharacterBodyId): number {
  return (CHARACTER_TARGET_HEIGHT * CHARACTER_SCALE) / CHARACTER_RAW_HEIGHT[bodyId];
}

/** Deterministic body pick (never Math.random) -- same seeded-hash utility
 * convention as palette.ts#seededRandom, applied to a 3-way choice so a given
 * lane/persona name always gets the same body across reloads. */
export function pickCharacterBody(seed: string): CharacterBodyId {
  let h = 1779033703 ^ seed.length;
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(h ^ seed.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return CHARACTER_BODY_IDS[Math.abs(h) % CHARACTER_BODY_IDS.length];
}

export const FURNITURE_SCALE = 2.0;
export const ARCHITECTURE_SCALE_BAY = 0.45;
// 0.75, not the smaller number an earlier pass of this file used -- a
// concurrent hygiene commit (5090d5cc) bumped Scene.tsx's own
// PERSONA_RING_RADIUS 4.5->6.5 while this file was being written; re-read
// before wiring HubRoom into Scene.tsx and recomputed against the REAL
// value (room-large radius 10*0.75=7.5 clears 6.5 by 1.0u) -- see
// HQ-SCENE-PLAN.md's "corrected mid-session" note.
export const ARCHITECTURE_SCALE_HUB = 0.75;
// Raw corridor.glb footprint is 4x4 (see HQ-SCENE-PLAN.md) -- one segment's
// world-space length once scaled for bay-side corridors.
export const CORRIDOR_SEGMENT_LENGTH = 4 * ARCHITECTURE_SCALE_BAY;

// World-pass A fix (2026-09-13): the wall radii a corridor run must span
// BETWEEN -- room-large's raw radius is 10 (diameter 20), room-small's raw
// depth is 12 (half-depth 6). Exported so Scene.tsx can compute each lane's
// hub-wall-to-bay-wall endpoints along its own angle, INSTEAD OF running a
// corridor from the hub's/bay's CENTER (a bug caught from the first real
// screenshot this session -- center-to-center segments clip straight
// through both rooms' interiors instead of filling only the gap between
// their walls).
export const HUB_WALL_RADIUS = 10 * ARCHITECTURE_SCALE_HUB;
export const BAY_HALF_DEPTH = (12 * ARCHITECTURE_SCALE_BAY) / 2;

const _tintColor = new THREE.Color();

/** Clones every mesh material under `root` (never mutate a shared cached
 * material -- every instance loading the same GLB path via `useGLTF` shares
 * ONE parsed scene/material until this runs) and multiplies each clone's
 * `color` toward `tint` by `tintStrength`. Shared by every kit piece that
 * needs per-instance recoloring: static props (below, via useTintedClone)
 * AND skinned characters (KitAgent.tsx, which clones via SkeletonUtils
 * instead of `.clone(true)` but needs the IDENTICAL tint-blend math -- kept
 * here once rather than duplicated so the two never drift). Returns the
 * cloned materials so the caller can dispose them on unmount/tint-change.
 * A SUBTLE default blend (callers typically pass ~0.12-0.2) is the point:
 * every kit piece shares one baked "colormap" atlas texture (verified this
 * session -- see HQ-SCENE-PLAN.md), so a strong tint would flatten it into
 * a solid color block instead of keeping the kit's own shading legible. */
const _emissiveColor = new THREE.Color();

/** Pass F (2026-09-13, coordinator's own real-monitor capture): optional
 * emissive -- SELF-illuminating, independent of whether the scene's own
 * hemisphere/directional lights actually reach a given surface. Every
 * existing caller omits this (default undefined -> zero behavior change,
 * zero risk to the 10+ kit pieces already using tintObjectMaterials/
 * useTintedClone) -- added specifically because HubRoom's room-large.glb
 * shell (a large, doubleSided, externally-lit-only mesh) reads as flat
 * black in the coordinator's real capture: a big dark dome dominating the
 * frame, exactly what J flagged as a "black hole" on the STARFIELD planet
 * earlier this session -- except the planet (Starfield.tsx, radius 2.1 at
 * [-26,13,-34]) is angularly ~1.9deg from the camera (verified by the
 * actual CAMERA_DIST/CAMERA_HEIGHT/BASE_AZIMUTH math this session), nowhere
 * near large enough to fill "the upper half" of a 1080p frame -- the real
 * culprit is this room shell (world radius 7.5, i.e. HUB_WALL_RADIUS
 * itself), confirmed by parsing room-large.glb's own JSON chunk (one mesh,
 * doubleSided=true, Y bounds 0..4.25 raw). */
export function tintObjectMaterials(
  root: THREE.Object3D, tint: string, tintStrength: number,
  emissive?: { color: string; intensity: number },
): THREE.Material[] {
  _tintColor.set(tint);
  if (emissive) _emissiveColor.set(emissive.color);
  const clonedMaterials: THREE.Material[] = [];
  root.traverse((obj) => {
    if (!(obj instanceof THREE.Mesh)) return;
    const applyTint = (mat: THREE.Material) => {
      const cloneMat = mat.clone();
      clonedMaterials.push(cloneMat);
      const colorable = cloneMat as THREE.Material & { color?: THREE.Color; emissive?: THREE.Color; emissiveIntensity?: number };
      if (colorable.color) colorable.color.lerp(_tintColor, tintStrength);
      if (emissive && colorable.emissive) {
        colorable.emissive.copy(_emissiveColor);
        colorable.emissiveIntensity = emissive.intensity;
      }
      return cloneMat;
    };
    obj.material = Array.isArray(obj.material) ? obj.material.map(applyTint) : applyTint(obj.material);
  });
  return clonedMaterials;
}

/** Clones a loaded GLTF scene graph (safe to call once per mounted instance
 * -- these Space Station Kit / Modular Space Kit props are all STATIC,
 * unskinned meshes, so a plain deep `.clone(true)` is correct and cheap;
 * skinned/animated characters use SkeletonUtils.clone instead, see
 * KitAgent.tsx) and optionally tints it via `tintObjectMaterials` above. */
function useTintedClone(
  scene: THREE.Object3D, tint: string | undefined, tintStrength: number,
  emissive?: { color: string; intensity: number },
): THREE.Object3D {
  const cloned = useMemo(() => scene.clone(true), [scene]);

  useEffect(() => {
    if (!tint && !emissive) return;
    const clonedMaterials = tintObjectMaterials(cloned, tint ?? "#000000", tint ? tintStrength : 0, emissive);
    return () => {
      clonedMaterials.forEach((m) => m.dispose());
    };
  }, [cloned, tint, tintStrength, emissive]);

  return cloned;
}

interface KitPropProps {
  path: string;
  scale?: number | [number, number, number];
  position?: [number, number, number];
  rotation?: [number, number, number];
  /** Health/accent color -- subtly blended into the prop's own atlas color
   * (see useTintedClone). Omit to keep the kit's native coloring untouched. */
  tint?: string;
  tintStrength?: number;
  /** Pass F (2026-09-13): self-illuminating glow, independent of scene
   * lighting reaching this surface -- see tintObjectMaterials' own comment
   * for why this exists (a large kit shell reading flat black regardless
   * of ambient/directional light). Omit (every current caller except
   * HubRoom) for zero behavior change. */
  emissive?: { color: string; intensity: number };
  castShadow?: boolean;
  receiveShadow?: boolean;
}

/** Generic placer for any single static kit GLB -- one `useGLTF` call (drei
 * caches by path, so the 8 bays sharing e.g. `table.glb` parse it ONCE, not
 * 8 times) + a per-instance clone. This is the one building block every
 * component below is made of. */
export function KitProp({ path, scale = 1, position, rotation, tint, tintStrength = 0.15, emissive, castShadow, receiveShadow }: KitPropProps) {
  // useDraco=false EXPLICITLY -- verified this session by reading drei's own
  // useGLTF source (node_modules/@react-three/drei/core/Gltf.js): omitting
  // the arg defaults it to `true`, which points a DRACOLoader at a
  // gstatic.com CDN path. That decoder is only ever FETCHED if a loaded
  // file actually contains `KHR_draco_mesh_compression` (none of these
  // bundled Kenney/KayKit GLBs do -- confirmed by parsing their raw JSON
  // chunks directly), so it would stay dormant in practice -- but this
  // project's zero-network-requests rule is absolute, so it's set false
  // outright rather than left as an implicit, easy-to-miss assumption.
  const { scene } = useGLTF(path, false);
  const cloned = useTintedClone(scene, tint, tintStrength, emissive);

  useEffect(() => {
    if (!castShadow && !receiveShadow) return;
    cloned.traverse((obj) => {
      if (!(obj instanceof THREE.Mesh)) return;
      if (castShadow) obj.castShadow = true;
      if (receiveShadow) obj.receiveShadow = true;
    });
  }, [cloned, castShadow, receiveShadow]);

  return <primitive object={cloned} scale={scale} position={position} rotation={rotation} />;
}

/** Central hub interior shell -- one `room-large.glb` at ARCHITECTURE_SCALE_HUB
 * (-> 15x15 footprint, radius 7.5, clearing Scene.tsx's PERSONA_RING_RADIUS=6.5
 * by 1.0 unit -- see ARCHITECTURE_SCALE_HUB's own comment for why this isn't
 * the smaller number an earlier pass of this file used). Neutral (no tint)
 * -- the hub is shared/manager space, no single lane's health color belongs
 * on its walls. Plus 4 ceiling lights (decorative greeble only). */
export const HUB_CEILING_Y = 4.25 * ARCHITECTURE_SCALE_HUB - 0.4; // room-large raw height 4.25

export function HubRoom() {
  const lightRadius = 4;
  return (
    <>
      {/* Pass F emissive fix (2026-09-13, coordinator's real-monitor
          capture): this shell was reading flat BLACK -- a dome dominating
          the frame, exactly the earlier "black hole" complaint, but on the
          room shell, not the Starfield planet (see tintObjectMaterials' own
          comment for the angular-size math ruling the planet out). A warm
          emissive (never fully dark regardless of what light reaches it)
          plus a slight tint toward the same warm accent this scene already
          uses at the horizon (PALETTE.warmAccent).
          Pass G escalation (2026-09-13, coordinator: "the big black arch at
          the hub's top... reads as a cave mouth" -- STILL visible after
          Pass F's fix): emissive is UNIFORM across this whole mesh (one
          shared material, confirmed by parsing room-large.glb's own JSON
          chunk -- one mesh, one material), so a genuinely still-dark patch
          isn't a per-face lighting gap, it's that 0.4 wasn't bright enough
          for a surface receiving ZERO other light to read as clearly LIT
          rather than merely "not pure black" once tone-mapping/exposure
          compresses it back down next to a much brighter, directly-lit
          neighbor. 0.4->0.85 (a direct escalation of the SAME already-
          working mechanism, not a new one) plus one additional real
          pointLight below, centered and with a much longer falloff than
          the 4 existing ceiling fixtures (distance 9, tuned for the near
          desk/floor area) specifically so the far dome interior actually
          receives real, non-emissive light too, not just the emissive
          floor. */}
      {/* Pass G (2026-09-13): tried a 180deg Y rotation here to test whether
          the black patch was a camera-facing opening -- REVERTED after a
          real re-capture showed the patch UNCHANGED in shape/position,
          same evidence-based discipline as Pass F's ARC_SPAN revert. Two
          real data points now rule out both "not bright enough" (emissive
          0.4->0.85 + a new pointLight: no visible change) and "wrong side
          facing camera" (180deg rotation: no visible change) -- together
          these point at something the coordinator's own three suggested
          fixes don't cover: likely the mesh's actual OUTER silhouette
          against the sky/void (a real gap or funnel shape a rotation
          around the vertical axis can't hide), not a lighting or facing
          problem at all. Left honestly unresolved rather than guessed a
          third time -- needs either direct mesh inspection (Blender, not
          available this session) or a positioned patch mesh, flagged for
          next pass. The emissive+pointLight escalation stays (a real,
          if partial, improvement to the rest of the shell's lit look --
          see the room-wide comparison against Pass F's own capture). */}
      <KitProp
        path={KIT_PATHS.architecture.roomLarge}
        scale={ARCHITECTURE_SCALE_HUB}
        tint={PALETTE.warmAccent}
        tintStrength={0.08}
        emissive={{ color: PALETTE.warmAccent, intensity: 0.85 }}
        receiveShadow
      />
      <pointLight position={[0, HUB_CEILING_Y * 0.7, 0]} color="#ffd9a0" intensity={6} distance={16} decay={1.5} />
      {[0, 90, 180, 270].map((deg) => {
        const rad = (deg * Math.PI) / 180;
        const pos: [number, number, number] = [Math.cos(rad) * lightRadius, HUB_CEILING_Y, Math.sin(rad) * lightRadius];
        return (
          <group key={deg}>
            <CeilingLight position={pos} />
            {/* World pass A: 2 of the 4 hub fixtures are REAL warm-white
                pointLights (the other 2 stay decorative-only greeble) --
                part of the "~10-12 total" budget alongside each bay's own
                single pointLight (StationModule.tsx). */}
            {(deg === 0 || deg === 180) && (
              <pointLight position={pos} color="#ffe9c2" intensity={4} distance={9} decay={2} />
            )}
          </group>
        );
      })}
    </>
  );
}

/** One department bay's room shell + hub-facing gate-door, in the module's
 * OWN local space (parent <group> already carries position+rotationY -- see
 * StationModule.tsx). `room-small.glb` at ARCHITECTURE_SCALE_BAY -> 5.4x5.4.
 * The gate-door sits at local -Z (the hub-facing edge, matching the existing
 * beacon/edge-strip convention already in StationModule.tsx). */
export const BAY_CEILING_Y = 4.25 * ARCHITECTURE_SCALE_BAY - 0.35; // room-small raw height 4.25

export function DepartmentBayShell() {
  const halfDepth = (12 * ARCHITECTURE_SCALE_BAY) / 2; // room-small raw depth 12
  return (
    <>
      <KitProp path={KIT_PATHS.architecture.roomSmall} scale={ARCHITECTURE_SCALE_BAY} receiveShadow />
      <KitProp
        path={KIT_PATHS.architecture.gateDoor}
        scale={ARCHITECTURE_SCALE_BAY}
        position={[0, 0, -halfDepth]}
        castShadow
      />
      <CeilingLight position={[0, BAY_CEILING_Y, BAY_DESK_OFFSET_Z * 0.5]} />
    </>
  );
}

interface DeskClusterProps {
  /** Health/accent color, subtly tinted onto the furniture (kept faint --
   * the SAME reasoning as useTintedClone: real furniture should still read
   * as furniture, the strong health signal stays on the dedicated emissive
   * edge-strip/beacon/head-beacon, not the desk itself). */
  accentColor?: string;
  /** Local-space seat position this cluster implies, in the SAME [x,y,z]
   * shape Scene.tsx already threads through `localToWorld` for agent homes
   * -- callers read this back to place the matching <Agent>/<KitAgentBody>
   * exactly at the chair, never duplicating the offset math. */
  /** Pass B (2026-09-13): when given, the computer-screen slot below
   * renders a real DeskScreen (canvas-texture content) instead of the
   * plain accent-tinted KitProp -- omitted (the default) for every desk
   * that has no specific content spec (most persona desks), which keeps
   * their screen exactly as before this pass. */
  screenTitle?: string | null;
  screenLines?: ScreenLine[];
}

const DESK_TOP_HEIGHT = 0.4 * FURNITURE_SCALE; // table.glb raw height 0.4
/** Chair position WITHIN a <DeskCluster>'s own local space. */
export const DESK_SEAT_LOCAL: [number, number, number] = [0, 0, -0.35 * FURNITURE_SCALE];

/** How far back (local +Z, away from the hub) a <DeskCluster> sits inside
 * its parent bay/persona-desk group -- leaves the doorway-to-center floor
 * clear for the agent's walk-in path instead of blocking it with furniture.
 * `BAY_SEAT_LOCAL` folds this together with `DESK_SEAT_LOCAL` into the ONE
 * local-space point (module-local, pre-`localToWorld`) StationModule.tsx
 * positions `<DeskCluster>` at AND Scene.tsx feeds `localToWorld` for the
 * matching kit-tier agent home -- both call sites read the SAME constant so
 * the seated character and the visible chair can never drift apart. */
export const BAY_DESK_OFFSET_Z = 0.8;
export const BAY_SEAT_LOCAL: [number, number, number] = [0, 0, BAY_DESK_OFFSET_Z + DESK_SEAT_LOCAL[2]];

/** Table + chair + desk terminal + wall-mounted screen, arranged along one
 * local-Z axis: chair (near side, faces +Z toward the table) -> table ->
 * standing computer console (beside the table) -> computer-screen (mounted
 * above the table's far edge, facing back toward the chair). Orientation
 * (which way the character/screen actually face) is a COSMETIC assumption,
 * not yet confirmed against a render -- see HQ-SCENE-PLAN.md; flip the
 * `Math.PI` on computer-screen/chair if a screenshot shows it backwards. */
export function DeskCluster({ accentColor, screenTitle, screenLines }: DeskClusterProps) {
  const SCREEN_POSITION: [number, number, number] = [0, DESK_TOP_HEIGHT, 0.55 * FURNITURE_SCALE];
  return (
    <group>
      <KitProp path={KIT_PATHS.furniture.table} scale={FURNITURE_SCALE} position={[0, 0, 0.3 * FURNITURE_SCALE]} receiveShadow />
      <KitProp
        path={KIT_PATHS.furniture.chair}
        scale={FURNITURE_SCALE}
        position={DESK_SEAT_LOCAL}
        rotation={[0, Math.PI, 0]}
        castShadow
      />
      <KitProp
        path={KIT_PATHS.furniture.computer}
        scale={FURNITURE_SCALE}
        position={[0.55 * FURNITURE_SCALE, 0, 0.25 * FURNITURE_SCALE]}
        tint={accentColor}
        tintStrength={0.12}
        castShadow
      />
      {screenLines ? (
        <Suspense fallback={null}>
          <DeskScreen path={KIT_PATHS.furniture.computerScreen} position={SCREEN_POSITION} rotation={[0, Math.PI, 0]} scale={FURNITURE_SCALE} title={screenTitle ?? null} lines={screenLines} />
        </Suspense>
      ) : (
        <KitProp
          path={KIT_PATHS.furniture.computerScreen}
          scale={FURNITURE_SCALE}
          position={SCREEN_POSITION}
          rotation={[0, Math.PI, 0]}
          tint={accentColor}
          tintStrength={0.2}
        />
      )}
    </group>
  );
}

// World-2 item 3 (2026-09-14, J: "what I think are supposed to be hallways
// for the people aren't really connected at all... floating hubs on the
// outside"): a continuous floor plate under hub+corridors+bays, ultra tier
// only (mounted from Scene.tsx's own `{ultra && ...}` branch, matching every
// other real-kit-geometry piece in this file). Sits ~0.02 above Ground.tsx's
// own outer disc (that one stays mounted on both tiers, y=-0.06) so the
// station's own footprint reads as a deliberately-built, lighter-toned
// surface distinct from raw exterior ground -- with a raised edge lip (a
// flattened torus "curb") so the platform boundary reads as a real edge
// instead of an invisible blend into Ground beneath it. `radius` is passed
// in from Scene.tsx (RING_RADIUS + BAY_HALF_DEPTH + 1.5) rather than
// recomputed here, since RING_RADIUS is Scene.tsx's own constant and this
// file must never import back from its own caller.
const PLAZA_Y = -0.04;
const PLAZA_NIGHT = new THREE.Color(PALETTE.deskDark);
const PLAZA_DAY = new THREE.Color(PALETTE.plazaDay);
const _plazaColor = new THREE.Color();

export function Plaza({ radius, dayFactor = 1 }: { radius: number; dayFactor?: number }) {
  const color = useMemo(() => _plazaColor.copy(PLAZA_NIGHT).lerp(PLAZA_DAY, dayFactor).clone(), [dayFactor]);
  const lipTube = 0.09;
  return (
    <group>
      <mesh position={[0, PLAZA_Y, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <circleGeometry args={[radius, 96]} />
        <meshStandardMaterial color={color} roughness={0.85} metalness={0.05} />
      </mesh>
      {/* Edge lip -- a low curb ring at the plaza's own outer radius so the
          platform boundary reads as a real, deliberately-built edge. */}
      <mesh position={[0, PLAZA_Y + lipTube * 0.5, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[radius, lipTube, 8, 96]} />
        <meshStandardMaterial color={color} roughness={0.6} metalness={0.15} />
      </mesh>
    </group>
  );
}

const CORRIDOR_WIDTH = 2.6;
const CORRIDOR_RAIL_HEIGHT = 0.3;
const CORRIDOR_RAIL_THICKNESS = 0.07;

/** Real hallway from the hub's wall to one bay's door: a guaranteed-correct
 * procedural floor strip + low side rails (Scene.tsx's own `angle`, the
 * SAME `Math.PI/2 - angle` yaw StationModule.tsx's module group already
 * uses -- local -Z always faces the hub, matching the bay's own gate-door
 * placement exactly) PLUS the kit's real corridor.glb segments layered on
 * top as architectural detail.
 *
 * World-2 item 3(b) bug fix (2026-09-14, "check why the existing CorridorRun
 * does not read as connected... and fix the actual cause"): the OLD version
 * reused Corridor.tsx's own `quaternion.setFromUnitVectors(UP, dir)` --
 * correct THERE because that file's pulse tube is a raw CylinderGeometry,
 * whose long axis really is local Y by default, so tipping "up" over to
 * point along a horizontal direction is exactly right for a cylinder. This
 * asset is not a cylinder: parsing corridor.glb's own JSON chunk this
 * session (`node`, reading the accessor min/max directly, same technique
 * this file's own HQ-SCENE-PLAN.md verification already used elsewhere)
 * shows an UPRIGHT piece, Y 0..4.25 (matching room-large's own raw height),
 * a square 4x4 XZ footprint -- the same "modeled upright, faces -Z by
 * default" convention every OTHER Modular Space Kit piece in this file
 * (room-small, room-large, gate-door) already gets with a plain yaw
 * rotation, never a tip-over quaternion. Rotating "up" onto a near-
 * horizontal direction instead tipped every corridor segment ~90 degrees
 * onto its side -- geometry that never read as a flat, walkable hallway no
 * matter how correctly its segments were positioned along the ray. Fixed by
 * using the SAME plain-yaw convention as its own sibling kit pieces, which
 * also makes the kit segments' own facing agree with the procedural strip's
 * rails below (both share the identical `rotationY`). The procedural strip
 * is what actually GUARANTEES the continuous, correctly-sized (2.6u) floor
 * this item's deliverable needs -- the kit segments are detail on top of
 * it, not the sole source of the connection, so a kit-asset quirk this
 * session couldn't fully verify without a 3D inspector can never leave a
 * visible gap in the floor itself. */
export function CorridorRun({ from, to, angle }: { from: [number, number, number]; to: [number, number, number]; angle: number }) {
  const rotationY = Math.PI / 2 - angle;
  const { midpoint, length, segPositions } = useMemo(() => {
    const start = new THREE.Vector3(...from);
    const end = new THREE.Vector3(...to);
    const len = start.distanceTo(end) || 0.001;
    const mid: [number, number, number] = [(from[0] + to[0]) / 2, (from[1] + to[1]) / 2, (from[2] + to[2]) / 2];
    // draw-call sanity: segCount is small on purpose -- ARCHITECTURE_SCALE_BAY's
    // 1.8u segment length vs a ~4-5u hub-to-bay gap means 2-3 segments per
    // corridor, not a dozen, x8 lanes.
    const segCount = Math.max(1, Math.round(len / CORRIDOR_SEGMENT_LENGTH));
    const step = len / segCount;
    const dirX = (end.x - start.x) / len;
    const dirZ = (end.z - start.z) / len;
    const segs: [number, number, number][] = [];
    for (let i = 0; i < segCount; i++) {
      const d = step * (i + 0.5);
      segs.push([start.x + dirX * d, start.y, start.z + dirZ * d]);
    }
    return { midpoint: mid, length: len, segPositions: segs };
  }, [from[0], from[1], from[2], to[0], to[1], to[2]]);

  return (
    <group>
      <group position={midpoint} rotation={[0, rotationY, 0]}>
        <mesh position={[0, -0.01, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[CORRIDOR_WIDTH, length]} />
          <meshStandardMaterial color={PALETTE.floor} roughness={0.85} />
        </mesh>
        {[-1, 1].map((side) => (
          <mesh key={side} position={[(side * (CORRIDOR_WIDTH - CORRIDOR_RAIL_THICKNESS)) / 2, CORRIDOR_RAIL_HEIGHT / 2, 0]} castShadow>
            <boxGeometry args={[CORRIDOR_RAIL_THICKNESS, CORRIDOR_RAIL_HEIGHT, length]} />
            <meshStandardMaterial color={PALETTE.deskDark} roughness={0.6} metalness={0.2} />
          </mesh>
        ))}
      </group>
      {segPositions.map((pos, i) => (
        <KitProp
          key={i}
          path={KIT_PATHS.architecture.corridor}
          scale={ARCHITECTURE_SCALE_BAY}
          position={pos}
          rotation={[0, rotationY, 0]}
          receiveShadow
        />
      ))}
    </group>
  );
}

/** Brain-core "reactor" dressing (hub only): 4 pipe/pipe-bend props radiating
 * from the core, per this task's "brain core = a glowing reactor built from
 * kit pieces + emissive core" spec. Purely decorative greeble around the
 * EXISTING sphere/rings (kept, see BrainCore.tsx) -- not a replacement. */
export function ReactorGreeble() {
  const radius = 1.5;
  const positions: [number, number, number][] = [0, 90, 180, 270].map((deg) => {
    const rad = (deg * Math.PI) / 180;
    return [Math.cos(rad) * radius, -0.3, Math.sin(rad) * radius];
  });
  return (
    <group>
      {positions.map((pos, i) => (
        <KitProp
          key={i}
          path={i % 2 === 0 ? KIT_PATHS.furniture.pipe : KIT_PATHS.furniture.pipeBend}
          scale={FURNITURE_SCALE * 0.8}
          position={pos}
          rotation={[0, (i * Math.PI) / 2, 0]}
        />
      ))}
    </group>
  );
}

/** KayKit ceiling light fixture -- decorative greeble only, no dynamic
 * THREE.Light attached (cost discipline: this scene stays at 1 hemisphere +
 * 1 directional total, per every prior HQ pass). */
export function CeilingLight({ position }: { position: [number, number, number] }) {
  return <KitProp path={KIT_PATHS.lights} scale={FURNITURE_SCALE * 0.6} position={position} rotation={[Math.PI, 0, 0]} />;
}

// Preload the small, always-visible set eagerly (drei's suspense cache) --
// characters are preloaded per-body from KitAgent.tsx instead, since which
// bodies are actually needed depends on runtime lane/persona names. `false`
// (useDraco) on every call -- see KitProp's own comment on why this is
// explicit rather than left to the (network-pointing) default.
useGLTF.preload(KIT_PATHS.architecture.roomLarge, false);
useGLTF.preload(KIT_PATHS.architecture.roomSmall, false);
useGLTF.preload(KIT_PATHS.architecture.corridor, false);
useGLTF.preload(KIT_PATHS.architecture.gateDoor, false);
useGLTF.preload(KIT_PATHS.furniture.table, false);
useGLTF.preload(KIT_PATHS.furniture.chair, false);
useGLTF.preload(KIT_PATHS.furniture.computer, false);
useGLTF.preload(KIT_PATHS.furniture.computerScreen, false);
useGLTF.preload(KIT_PATHS.lights, false);
