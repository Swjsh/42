"use client";

import { useEffect, useMemo } from "react";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";

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

export function characterScale(bodyId: CharacterBodyId): number {
  return CHARACTER_TARGET_HEIGHT / CHARACTER_RAW_HEIGHT[bodyId];
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
export function tintObjectMaterials(root: THREE.Object3D, tint: string, tintStrength: number): THREE.Material[] {
  _tintColor.set(tint);
  const clonedMaterials: THREE.Material[] = [];
  root.traverse((obj) => {
    if (!(obj instanceof THREE.Mesh)) return;
    const applyTint = (mat: THREE.Material) => {
      const cloneMat = mat.clone();
      clonedMaterials.push(cloneMat);
      const colorable = cloneMat as THREE.Material & { color?: THREE.Color };
      if (colorable.color) colorable.color.lerp(_tintColor, tintStrength);
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
function useTintedClone(scene: THREE.Object3D, tint: string | undefined, tintStrength: number): THREE.Object3D {
  const cloned = useMemo(() => scene.clone(true), [scene]);

  useEffect(() => {
    if (!tint) return;
    const clonedMaterials = tintObjectMaterials(cloned, tint, tintStrength);
    return () => {
      clonedMaterials.forEach((m) => m.dispose());
    };
  }, [cloned, tint, tintStrength]);

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
  castShadow?: boolean;
  receiveShadow?: boolean;
}

/** Generic placer for any single static kit GLB -- one `useGLTF` call (drei
 * caches by path, so the 8 bays sharing e.g. `table.glb` parse it ONCE, not
 * 8 times) + a per-instance clone. This is the one building block every
 * component below is made of. */
export function KitProp({ path, scale = 1, position, rotation, tint, tintStrength = 0.15, castShadow, receiveShadow }: KitPropProps) {
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
  const cloned = useTintedClone(scene, tint, tintStrength);

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
const HUB_CEILING_Y = 4.25 * ARCHITECTURE_SCALE_HUB - 0.4; // room-large raw height 4.25

export function HubRoom() {
  const lightRadius = 4;
  return (
    <>
      <KitProp path={KIT_PATHS.architecture.roomLarge} scale={ARCHITECTURE_SCALE_HUB} receiveShadow />
      {[0, 90, 180, 270].map((deg) => {
        const rad = (deg * Math.PI) / 180;
        return (
          <CeilingLight
            key={deg}
            position={[Math.cos(rad) * lightRadius, HUB_CEILING_Y, Math.sin(rad) * lightRadius]}
          />
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
const BAY_CEILING_Y = 4.25 * ARCHITECTURE_SCALE_BAY - 0.35; // room-small raw height 4.25

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
export function DeskCluster({ accentColor }: DeskClusterProps) {
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
      <KitProp
        path={KIT_PATHS.furniture.computerScreen}
        scale={FURNITURE_SCALE}
        position={[0, DESK_TOP_HEIGHT, 0.55 * FURNITURE_SCALE]}
        rotation={[0, Math.PI, 0]}
        tint={accentColor}
        tintStrength={0.2}
      />
    </group>
  );
}

/** Chains N straight `corridor.glb` segments along the line from `from` to
 * `to` (both WORLD-space points) -- same quaternion-from-direction approach
 * already proven in Corridor.tsx's pulse tube, so the corridor's real
 * geometry now runs along the identical path the pulse sprite travels.
 * Segment count is computed from the actual distance, never hardcoded, so
 * this works unchanged for the hub's 8 (differently-spaced) lane corridors. */
const CORRIDOR_UP = new THREE.Vector3(0, 1, 0);

export function CorridorRun({ from, to }: { from: [number, number, number]; to: [number, number, number] }) {
  const { positions, quaternion } = useMemo(() => {
    const start = new THREE.Vector3(...from);
    const end = new THREE.Vector3(...to);
    const dir = new THREE.Vector3().subVectors(end, start);
    const length = dir.length() || 0.001;
    dir.normalize();
    const q = new THREE.Quaternion().setFromUnitVectors(CORRIDOR_UP, dir);
    // draw-call sanity: segCount is small on purpose -- ARCHITECTURE_SCALE_BAY's
    // 1.8u segment length vs a ~4-5u hub-to-bay gap means 2-3 segments per
    // corridor, not a dozen, x8 lanes.
    const segCount = Math.max(1, Math.round(length / CORRIDOR_SEGMENT_LENGTH));
    const step = length / segCount;
    const segs: [number, number, number][] = [];
    for (let i = 0; i < segCount; i++) {
      const d = step * (i + 0.5);
      segs.push([start.x + dir.x * d, start.y, start.z + dir.z * d]);
    }
    return { positions: segs, quaternion: q };
  }, [from[0], from[1], from[2], to[0], to[1], to[2]]);

  const euler = useMemo(() => new THREE.Euler().setFromQuaternion(quaternion), [quaternion]);

  return (
    <group>
      {positions.map((pos, i) => (
        <KitProp
          key={i}
          path={KIT_PATHS.architecture.corridor}
          scale={ARCHITECTURE_SCALE_BAY}
          position={pos}
          rotation={[euler.x, euler.y, euler.z]}
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
