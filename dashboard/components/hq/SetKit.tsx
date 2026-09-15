"use client";

import { Suspense, useEffect, useId, useLayoutEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import DeskScreen from "./DeskScreen";
import { lerp, localToWorld, PALETTE, type ScreenLine } from "./palette";

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
    // LAYOUT builder pass (2026-09-14, campus-cross rebuild): both already
    // on disk (manifest.json) but never wired into KIT_PATHS until now --
    // corridorWide dresses the 4 main hub-to-T spines ("corridor-wide or 2x
    // corridor" per the layout brief, CorridorRun's own `wide` option),
    // corridorIntersection dresses each T-junction (TJunction below).
    corridorWide: `${KIT_BASE}/kenney-modular-space-kit/corridor-wide.glb`,
    corridorIntersection: `${KIT_BASE}/kenney-modular-space-kit/corridor-intersection.glb`,
    gateDoor: `${KIT_BASE}/kenney-modular-space-kit/gate-door.glb`,
  },
  lights: `${KIT_BASE}/kaykit-space-base-bits/lights.gltf`,
  hdri: `${KIT_BASE}/polyhaven-dikhololo-night/dikhololo_night_1k.hdr`,
  // World-3 environment pass (2026-09-14, J: "grey abyss... space theme or a
  // park or something real"): kenney-space-kit terrain/prop pieces --
  // downloaded fresh this pass (LICENSES.md's own "Update 2026-09-14" note),
  // same CC0 pack the pre-existing astronautA.glb/barrels.glb already come
  // from. `terrain` feeds Rocks.tsx's instanced rock field + Ground.tsx's
  // individually-placed craters; `baseProps` feeds BaseProps.tsx.
  terrain: {
    rock: `${KIT_BASE}/kenney-space-kit/rock.glb`,
    rockSmallA: `${KIT_BASE}/kenney-space-kit/rocks_smallA.glb`,
    rockLargeA: `${KIT_BASE}/kenney-space-kit/rock_largeA.glb`,
    rockLargeB: `${KIT_BASE}/kenney-space-kit/rock_largeB.glb`,
    crater: `${KIT_BASE}/kenney-space-kit/crater.glb`,
    craterLarge: `${KIT_BASE}/kenney-space-kit/craterLarge.glb`,
  },
  baseProps: {
    satelliteDish: `${KIT_BASE}/kenney-space-kit/satelliteDish.glb`,
    satelliteDishLarge: `${KIT_BASE}/kenney-space-kit/satelliteDish_large.glb`,
    rover: `${KIT_BASE}/kenney-space-kit/rover.glb`,
    structure: `${KIT_BASE}/kenney-space-kit/structure.glb`,
    supportsHigh: `${KIT_BASE}/kenney-space-kit/supports_high.glb`,
    pipeStraight: `${KIT_BASE}/kenney-space-kit/pipe_straight.glb`,
    pipeCorner: `${KIT_BASE}/kenney-space-kit/pipe_corner.glb`,
    // Already downloaded/catalogued (2026-09-13 curation pass, manifest.json)
    // but never wired into KIT_PATHS until now -- both are real CC0 pieces
    // already on disk, no new download needed.
    barrels: `${KIT_BASE}/kenney-space-kit/barrels.glb`,
    container: `${KIT_BASE}/kenney-space-station-kit/container.glb`,
  },
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
// 1.25x landed every body at 2.25 world units standing height, legible at
// the ~16-unit overview distance without dwarfing the (unchanged) desk/chair
// furniture scale (FURNITURE_SCALE=2.0 is independent of this).
// SCALE-2 (2026-09-15, J live: "make the characters a bit smaller"): 1.25
// read as oversized next to the enlarged hub screens (SmartBoard.tsx's
// BOARD_SCALE, HoloChart.tsx's HOLO_CHART_SCALE, same pass) -- 1.0 puts
// every body back at its CHARACTER_TARGET_HEIGHT (1.8) exactly, still well
// clear of the old pre-LIVE-1 dwarfed look this constant was introduced to
// fix. Every consumer (ULTRA_HEAD_Y, Scene.tsx's headOffset, KitAgent.tsx's
// characterScale() call) reads this constant, never a second hardcoded
// 1.25/1.0 literal, so nothing else needed a manual edit for this change --
// see this file's own git history if a future pass needs the derivation
// chain re-verified. Ultra tier only in EFFECT (characterScale() is the
// ONLY place either tier computes a character's world scale, and only
// KitAgent.tsx/GammaCharacter.tsx -- both ultra-only callers, see Agent.tsx's
// own `ultra` branch -- ever call it; the TV tier's procedural capsule body
// in Agent.tsx has its own hardcoded geometry args, untouched by this
// constant).
export const CHARACTER_SCALE = 1.0;

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

// ─── P3 perf pass (POLISH-1, 2026-09-14): cross-scene instancing pool ──────
// Real capture (world6-preset0-fixed.png) reads 1151 draw calls at the wide
// overview because every corridor segment / gate-door / T-junction / bay
// shell is its OWN full KitProp mount -- a separate THREE.Mesh object per
// mount, even though geometry is drei-cached (SHARED buffers) and every
// piece measured this session (a one-off GLB-JSON-chunk dump, same
// technique dashboard/scripts/glb_extents.mjs already uses, not guessed):
// corridor.glb / corridor-wide.glb / corridor-intersection.glb / room-small.glb
// are each exactly ONE mesh primitive, ONE shared "colormap" material,
// IDENTITY local-to-root matrix; gate-door.glb is exactly TWO (frame + door
// panel), same material, same identity matrix -- three.js still issues one
// draw call per Mesh OBJECT regardless of shared underlying data.
//
// Fix: one real THREE.InstancedMesh per (kit GLB primitive, material) pair,
// fed by every hallway/junction/bay's own placement instead of each
// spawning its own clone. The hard part: CorridorRun/TJunction/
// DepartmentBayShell mount MANY TIMES as SIBLINGS scattered across Scene.tsx's
// whole JSX tree (4 main spines + 8 side halls + 4 junctions + 8 bays) --
// not descendants of one shared ancestor -- so a React Context provider
// (drei's own <Instances>/<Instance> pattern) can't reach across them
// without wrapping Scene.tsx's ENTIRE render tree, which this task's
// file-ownership rule forbids editing. A plain MODULE-SCOPE registry
// sidesteps the tree entirely -- the SAME "shared across every mounted
// instance regardless of tree position" convention Agent.tsx's own
// `lastGlobalWalkStartT` already uses in this exact codebase (module scope,
// not React state/Context) -- each CorridorRun/TJunction/DepartmentBayShell
// instance REGISTERS its own placement(s) via `usePooledKitProps` (a
// useEffect, batched per call site to respect the rules of hooks -- never
// one hook call per array item) and ONE always-mounted <InstancedKitPool>
// per (path, variant) -- mounted from HubRoom below, itself a
// guaranteed-single Scene.tsx mount -- subscribes to the registry via
// React's own useSyncExternalStore and renders the real InstancedMesh(es).
//
// Placement math: every targeted piece's own local-to-glTF-root matrix is
// IDENTITY (verified above), so a registered instance's matrix is exactly
// `compose(position, quaternion-from-Euler(rotation), scale)` -- the SAME
// three numbers every current KitProp mount already receives, just fed into
// a shared buffer instead of a per-instance clone.
//
// Tint: CorridorRun's own segments/main-spines tint toward `plateColorStyle`
// (dayFactor-driven). Verified this session (Scene.tsx's own call sites,
// grepped): EVERY CorridorRun/TJunction/HubRoom call receives the IDENTICAL
// `dayFactor={nightFactor}` value in any one render, so every "tinted"
// instance in a pool always wants the SAME color at any given moment -- no
// per-instance instanceColor needed, just ONE shared material whose
// `.color` the pool itself derives from its OWN `dayFactor` prop (HubRoom
// already receives it), recomputed with the IDENTICAL formula
// CorridorRun/Plaza already use for `plateColorStyle`. Untinted pieces
// (gate-door, T-junction intersection+cap, room-small) use the GLB's own
// native material, unmodified.
//
// Scope (this pass): corridor.glb, corridor-wide.glb, gate-door.glb,
// corridor-intersection.glb, room-small.glb -- every piece this task names
// ("corridor.glb / corridor-wide.glb / gate-door.glb / wall segments").
// NOT instanced, deliberately: room-large.glb (HubRoom's own hub shell --
// exactly ONE mount, nothing to batch, AND uses a per-instance `emissive`
// prop today -- this task's own explicit "leave it" case); CeilingLight
// (12 mounts across HubRoom+DepartmentBayShell) -- same infra could extend
// to it, deprioritized this pass for risk/time budget, flagged as a
// follow-up; DeskCluster's furniture (table/chair/computer/screen, x8 bays)
// and HubInterior's own table/chairs/cables -- table/chair are clean (no
// tint), but the desk's own computer-screen carries UNIQUE per-bay canvas
// content (P&L/state text, DeskScreen.tsx), which an InstancedMesh's ONE
// shared material cannot represent -- exactly the "multi-material/
// per-instance content" case this task says to leave; instancing table/
// chair alone without the screen felt like a partial win not worth the
// added surface this pass, flagged as a follow-up too.

interface PoolInstance {
  matrix: THREE.Matrix4;
}
type PoolKey = string; // `${glbPath}::${variant}`
export type { PoolPlacement, InstancedKitPoolProps };

const poolRegistry = new Map<PoolKey, Map<string, PoolInstance>>();
const poolListeners = new Set<() => void>();
let poolVersion = 0;
function notifyPool(): void {
  poolVersion += 1;
  poolListeners.forEach((l) => l());
}
function subscribePool(cb: () => void): () => void {
  poolListeners.add(cb);
  return () => poolListeners.delete(cb);
}
function getPoolVersion(): number {
  return poolVersion;
}

const _poolPos = new THREE.Vector3();
const _poolQuat = new THREE.Quaternion();
const _poolEuler = new THREE.Euler();
const _poolScale = new THREE.Vector3();

interface PoolPlacement {
  /** Stable across re-renders for the SAME logical instance (this call
   * site's own useId() + a per-item suffix) -- the registry keys on this,
   * never array index (index would silently reassign a DIFFERENT
   * instance's matrix if the array ever reordered). */
  id: string;
  position: [number, number, number];
  /** Euler XYZ (three.js default order). Every placement pooled so far
   * (corridor/gate-door/junction/room, and DeskCluster's table+chair below)
   * needs at most ONE non-zero axis (a plain Y-facing rotation), where
   * axis order is moot -- use this field for those. Mutually exclusive
   * with `quaternion`; exactly one of the two must be given. */
  rotation?: [number, number, number];
  /** Precomposed world quaternion -- for a placement whose rotation is a
   * composition of axes that three.js's default XYZ Euler order can't
   * express directly. CeilingLight is the case that needs this: its own
   * local orientation is a pure X-axis flip, nested inside a Y-rotated
   * parent (a department bay's own `rotationY`; 0 for the hub's 4
   * fixtures, which have no parent rotation) -- the real nested-group
   * composition is `Ry(rotationY) * Rx(Math.PI)` (apply the fixture's own
   * flip first, THEN the bay's rotation, matching how two nested
   * `<group rotation=[...]>` transforms actually multiply). A single Euler
   * triple `[Math.PI, rotationY, 0]` under the default 'XYZ' order instead
   * composes to `Rx(Math.PI) * Ry(rotationY)` (apply Ry first, then Rx) --
   * the WRONG order whenever rotationY != 0 -- so this case computes the
   * quaternion explicitly via real quaternion multiplication instead (see
   * `ceilingLightWorldQuaternion` below). Mutually exclusive with
   * `rotation`. */
  quaternion?: THREE.Quaternion;
  scale: number;
}

/** Registers a BATCH of placements into a shared cross-tree pool (see this
 * section's own header) in ONE effect -- never one hook call per array item
 * (rules of hooks forbid a hook inside a .map() callback). Re-registers only
 * when the batch's own VALUES change (a stable serialized dep key, not the
 * array reference -- callers often rebuild the array every render even when
 * every number inside is unchanged). */
// PERF-3 (2026-09-15): exported (was file-private) so callers outside this
// file -- Ground.tsx (craters), BaseProps.tsx (cables/supportsHigh/barrels
// callers, follow-up scope), HubInterior.tsx (hub chairs/cables),
// BayInterior.tsx (second chair) -- can register into the SAME cross-tree
// pool this section already built for corridor/gate-door/table/chair,
// instead of each mounting its own un-instanced KitProp. No behavior change
// for existing in-file callers (HubRoom/DeskCluster/CorridorRun/TJunction).
export function usePooledKitProps(path: string, variant: string, placements: PoolPlacement[]): void {
  const key: PoolKey = `${path}::${variant}`;
  const depsKey = placements
    .map((p) => {
      const rot = p.quaternion
        ? `q:${p.quaternion.x},${p.quaternion.y},${p.quaternion.z},${p.quaternion.w}`
        : `e:${p.rotation![0]},${p.rotation![1]},${p.rotation![2]}`;
      return `${p.id}:${p.position[0]},${p.position[1]},${p.position[2]}:${rot}:${p.scale}`;
    })
    .join("|");
  useEffect(() => {
    let pool = poolRegistry.get(key);
    if (!pool) {
      pool = new Map();
      poolRegistry.set(key, pool);
    }
    for (const p of placements) {
      const q = p.quaternion ?? _poolQuat.setFromEuler(_poolEuler.set(p.rotation![0], p.rotation![1], p.rotation![2]));
      const m = new THREE.Matrix4().compose(
        _poolPos.set(p.position[0], p.position[1], p.position[2]),
        q,
        _poolScale.set(p.scale, p.scale, p.scale),
      );
      pool.set(p.id, { matrix: m });
    }
    notifyPool();
    return () => {
      const live = poolRegistry.get(key);
      if (live) for (const p of placements) live.delete(p.id);
      notifyPool();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, depsKey]);
}

interface InstancedKitPoolProps {
  path: string;
  variant: string;
  /** Overrides the shared material's OWN color (native kit color if
   * omitted). Computed by the CALLER from the SAME dayFactor every tinted
   * mount already reads -- see this section's own header for why this
   * sidesteps per-instance instanceColor entirely (every instance sharing
   * one pool in THIS scene always agrees on one color at any moment). */
  tintColor?: string;
  tintStrength?: number;
  castShadow?: boolean;
  receiveShadow?: boolean;
}

/** Renders ONE real InstancedMesh per mesh primitive in `path`'s GLB, fed by
 * every placement currently registered under (path, variant) -- see this
 * section's own header. Mounted once per (path, variant) combo, from
 * HubRoom below. */
export function InstancedKitPool({ path, variant, tintColor, tintStrength = 0, castShadow, receiveShadow }: InstancedKitPoolProps) {
  const version = useSyncExternalStore(subscribePool, getPoolVersion, getPoolVersion);
  const { scene } = useGLTF(path, false);
  const key: PoolKey = `${path}::${variant}`;
  const pool = poolRegistry.get(key);
  const matrices = useMemo(
    () => (pool ? Array.from(pool.values()).map((v) => v.matrix) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pool, version],
  );

  const meshes = useMemo(() => {
    const out: THREE.Mesh[] = [];
    scene.traverse((obj) => {
      if (obj instanceof THREE.Mesh) out.push(obj);
    });
    return out;
  }, [scene]);

  // ONE cloned material PER mesh primitive (not per instance -- shared
  // across every instance in this pool): tinted the SAME way
  // tintObjectMaterials already blends a single material
  // (color.lerp(tint, strength)), just computed ONCE here instead of
  // once-per-mount.
  const materials = useMemo(
    () => meshes.map((mesh) => {
      const src = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
      const clone = src.clone() as THREE.Material & { color?: THREE.Color };
      if (tintColor && clone.color) clone.color.lerp(new THREE.Color(tintColor), tintStrength);
      return clone;
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [meshes, tintColor, tintStrength],
  );
  useEffect(() => () => materials.forEach((m) => m.dispose()), [materials]);

  const instRefs = useRef<(THREE.InstancedMesh | null)[]>([]);
  useLayoutEffect(() => {
    instRefs.current.forEach((im) => {
      if (!im) return;
      matrices.forEach((m, idx) => im.setMatrixAt(idx, m));
      im.count = matrices.length;
      im.instanceMatrix.needsUpdate = true;
    });
  }, [matrices]);

  if (matrices.length === 0) return null;

  return (
    <>
      {meshes.map((mesh, i) => (
        <instancedMesh
          key={i}
          ref={(el) => { instRefs.current[i] = el; }}
          args={[mesh.geometry, materials[i], Math.max(1, matrices.length)]}
          castShadow={castShadow}
          receiveShadow={receiveShadow}
          frustumCulled={false}
        />
      ))}
    </>
  );
}

/** Central hub interior shell -- one `room-large.glb` at ARCHITECTURE_SCALE_HUB
 * (-> 15x15 footprint, radius 7.5, clearing Scene.tsx's PERSONA_RING_RADIUS=6.5
 * by 1.0 unit -- see ARCHITECTURE_SCALE_HUB's own comment for why this isn't
 * the smaller number an earlier pass of this file used). Neutral (no tint)
 * -- the hub is shared/manager space, no single lane's health color belongs
 * on its walls. Plus 4 ceiling lights (decorative greeble only). */
export const HUB_CEILING_Y = 4.25 * ARCHITECTURE_SCALE_HUB - 0.4; // room-large raw height 4.25

// World-2 coordinator review (2026-09-14, "DAYTIME BLOWOUT... the whole hub
// is washed-out orange with no wall edges") root cause (a) of 3: these
// interior fixtures (the room shell's own warm emissive AND every ceiling
// pointLight below) were tuned for the night look and never faded by day,
// stacking on top of (now much brighter) day sky/ambient/environment
// lighting. lerp(1, 0.15, dayFactor) -- "interior lamps off in daylight",
// never fully to 0 (a lit interior at night still needs SOME practical
// glow once the sun's gone). Shared by HubRoom and DepartmentBayShell below
// so both fade identically.
function interiorLampFactor(dayFactor: number): number {
  return lerp(1, 0.15, dayFactor);
}

// P3 perf pass, item 2 (POLISH-1 follow-up, 2026-09-14): CeilingLight is
// now pooled the SAME way -- see PoolPlacement's own `quaternion` field
// header for why this needs a real quaternion multiply rather than a
// single Euler triple. `CEILING_LIGHT_LOCAL_QUAT` is the fixture's own
// fixed local orientation (CeilingLight's old KitProp always passed
// `rotation={[Math.PI, 0, 0]}`, never anything else); a fresh Y-axis
// quaternion multiplies it PER CALL (never mutating this shared constant --
// `.multiply` runs on the fresh per-call quaternion, matching the
// immutability convention every other pooled placement in this file
// already follows for its own scratch math).
const _ceilingLightYAxis = new THREE.Vector3(0, 1, 0);
const CEILING_LIGHT_LOCAL_QUAT = new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI, 0, 0));
function ceilingLightWorldQuaternion(rotationY: number): THREE.Quaternion {
  return new THREE.Quaternion().setFromAxisAngle(_ceilingLightYAxis, rotationY).multiply(CEILING_LIGHT_LOCAL_QUAT);
}

export function HubRoom({ dayFactor = 1 }: { dayFactor?: number }) {
  const lightRadius = 4;
  const lampFactor = interiorLampFactor(dayFactor);
  const instanceIdBase = useId();
  // Memoized on dayFactor alone (not every render) -- same "rebuild only
  // when the value the object depends on actually changes" discipline
  // SkyDome.tsx's own useMemo-on-dayFactor uses; a fresh object literal
  // every render would re-run KitProp's tint/emissive useEffect (material
  // clone + dispose, a real GPU op) on every poll instead of only when the
  // clock genuinely moves.
  const hubEmissive = useMemo(() => ({ color: PALETTE.warmAccent, intensity: 0.85 * lampFactor }), [lampFactor]);
  // P3 perf pass (POLISH-1, 2026-09-14): the SAME dayFactor-driven color
  // CorridorRun's own `plateColorStyle` already computes -- recomputed here
  // (not threaded/imported) so the tinted architecture pool's shared
  // material can derive its color WITHOUT depending on which specific
  // CorridorRun call happens to be mounted (there are up to 12; every one
  // of them shares this exact value in any one render -- see this file's
  // own "P3 perf pass" header for the verification).
  const archPlateColor = useMemo(() => _plazaColor.copy(PLAZA_NIGHT).lerp(PLAZA_DAY, dayFactor).getStyle(), [dayFactor]);
  // P3 perf pass, item 2 (POLISH-1 follow-up, 2026-09-14): the hub's 4
  // ceiling-light fixtures, registered into the SAME pool the 8 department
  // bays' own single fixture each (DepartmentBayShell below) also register
  // into -- called at the component's own top level (never inside a nested
  // closure/JSX callback -- rules of hooks), same convention every other
  // usePooledKitProps call site in this file already follows.
  const ceilingLightPlacements = useMemo(
    () => [0, 90, 180, 270].map((deg) => {
      const rad = (deg * Math.PI) / 180;
      return {
        id: `${instanceIdBase}-hub-ceiling-${deg}`,
        position: [Math.cos(rad) * lightRadius, HUB_CEILING_Y, Math.sin(rad) * lightRadius] as [number, number, number],
        quaternion: ceilingLightWorldQuaternion(0),
        scale: FURNITURE_SCALE * 0.6,
      };
    }),
    [instanceIdBase, lightRadius],
  );
  usePooledKitProps(KIT_PATHS.lights, "native", ceilingLightPlacements);
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
        emissive={hubEmissive}
        receiveShadow
      />
      <pointLight position={[0, HUB_CEILING_Y * 0.7, 0]} color="#ffd9a0" intensity={6 * lampFactor} distance={16} decay={1.5} />
      {[0, 90, 180, 270].map((deg) => {
        const rad = (deg * Math.PI) / 180;
        const pos: [number, number, number] = [Math.cos(rad) * lightRadius, HUB_CEILING_Y, Math.sin(rad) * lightRadius];
        return (
          <group key={deg}>
            {/* World pass A: 2 of the 4 hub fixtures are REAL warm-white
                pointLights (the other 2 stay decorative-only greeble) --
                part of the "~10-12 total" budget alongside each bay's own
                single pointLight (StationModule.tsx). The fixture's own
                GEOMETRY is registered into the shared CeilingLight pool
                below instead of a direct <CeilingLight> mount (P3 perf
                pass, item 2, POLISH-1 follow-up, 2026-09-14). */}
            {(deg === 0 || deg === 180) && (
              <pointLight position={pos} color="#ffe9c2" intensity={4 * lampFactor} distance={9} decay={2} />
            )}
          </group>
        );
      })}

      {/* P3 perf pass (POLISH-1, 2026-09-14): cross-hallway/cross-bay
          InstancedMesh pools, fed by every CorridorRun/TJunction/
          DepartmentBayShell instance's own usePooledKitProps registration --
          see this file's own "P3 perf pass" header. Mounted ONCE here
          (HubRoom is itself a guaranteed-single Scene.tsx mount) instead of
          once per hallway/bay, which IS the draw-call win. Suspense-scoped
          (world pass A convention, see ReactorGreeble's own comment in
          BrainCore.tsx) so a still-loading pool never unmounts HubRoom's
          own shell/lights above. P3 item 2 follow-up: CeilingLight
          (hub+bay fixtures) and DeskCluster's table/chair (8 bays each)
          join the same pool set here. */}
      <Suspense fallback={null}>
        <InstancedKitPool path={KIT_PATHS.architecture.corridor} variant="tinted" tintColor={archPlateColor} tintStrength={0.6} receiveShadow />
        <InstancedKitPool path={KIT_PATHS.architecture.corridor} variant="native" receiveShadow />
        <InstancedKitPool path={KIT_PATHS.architecture.corridorWide} variant="tinted" tintColor={archPlateColor} tintStrength={0.6} receiveShadow />
        <InstancedKitPool path={KIT_PATHS.architecture.gateDoor} variant="native" castShadow />
        <InstancedKitPool path={KIT_PATHS.architecture.corridorIntersection} variant="native" receiveShadow />
        <InstancedKitPool path={KIT_PATHS.architecture.roomSmall} variant="native" receiveShadow />
        <InstancedKitPool path={KIT_PATHS.lights} variant="native" />
        <InstancedKitPool path={KIT_PATHS.furniture.table} variant="native" receiveShadow />
        <InstancedKitPool path={KIT_PATHS.furniture.chair} variant="native" castShadow />
      </Suspense>
    </>
  );
}

/** One department bay's room shell + hub-facing gate-door, in the module's
 * OWN local space (parent <group> already carries position+rotationY -- see
 * StationModule.tsx). `room-small.glb` at ARCHITECTURE_SCALE_BAY -> 5.4x5.4.
 * The gate-door sits at local -Z (the hub-facing edge, matching the existing
 * beacon/edge-strip convention already in StationModule.tsx). */
export const BAY_CEILING_Y = 4.25 * ARCHITECTURE_SCALE_BAY - 0.35; // room-small raw height 4.25

/** P3 perf pass (POLISH-1, 2026-09-14): `position`/`rotationY` -- the SAME
 * two values StationModule.tsx's own outer `<group position={position}
 * rotation={[0, rotationY, 0]}>` already applies -- are now REQUIRED props
 * (the shell's own room-small.glb and gate-door.glb no longer mount as
 * KitProp children of that group; they register into the shared
 * cross-scene pool instead, which renders from HubRoom, a sibling
 * elsewhere in the tree -- see SetKit.tsx's own "P3 perf pass" header for
 * why a pooled instance needs its WORLD placement computed explicitly
 * rather than inheriting a parent group's transform). */
export function DepartmentBayShell({ position, rotationY }: { position: [number, number, number]; rotationY: number }) {
  const halfDepth = (12 * ARCHITECTURE_SCALE_BAY) / 2; // room-small raw depth 12
  const instanceIdBase = useId();

  const roomPlacements = useMemo(
    () => [{ id: `${instanceIdBase}-room`, position, rotation: [0, rotationY, 0] as [number, number, number], scale: ARCHITECTURE_SCALE_BAY }],
    [instanceIdBase, position, rotationY],
  );
  usePooledKitProps(KIT_PATHS.architecture.roomSmall, "native", roomPlacements);

  // Gate-door's OLD local position [0,0,-halfDepth] had NO rotation prop of
  // its own (identity local rotation), so its world rotation was always
  // exactly the parent group's rotationY -- reproduced directly here too.
  const doorWorldPos = useMemo(() => localToWorld(position, rotationY, [0, 0, -halfDepth]), [position, rotationY, halfDepth]);
  const doorPlacements = useMemo(
    () => [{ id: `${instanceIdBase}-door`, position: doorWorldPos, rotation: [0, rotationY, 0] as [number, number, number], scale: ARCHITECTURE_SCALE_BAY }],
    [instanceIdBase, doorWorldPos, rotationY],
  );
  usePooledKitProps(KIT_PATHS.architecture.gateDoor, "native", doorPlacements);

  // P3 perf pass, item 2 (POLISH-1 follow-up, 2026-09-14): this bay's own
  // ceiling light, into the SAME shared pool the hub's 4 fixtures also
  // register into (see HubRoom's own registration + PoolPlacement's
  // `quaternion` field header for why a real quaternion multiply is
  // required here, unlike every OTHER pooled piece in this file). The
  // fixture used to be a direct `<CeilingLight position={...} />` child of
  // this component, itself nested inside StationModule.tsx's own
  // `<group position={position} rotation={[0, rotationY, 0]}>` -- so its
  // effective world rotation was already `Ry(rotationY) * Rx(Math.PI)` (the
  // nested group's own rotation applied AFTER the fixture's local flip).
  // Reproduced explicitly here since the pooled instance now renders from
  // HubRoom, a sibling elsewhere in the tree.
  const ceilingLightWorldPos = useMemo(
    () => localToWorld(position, rotationY, [0, BAY_CEILING_Y, BAY_DESK_OFFSET_Z * 0.5]),
    [position, rotationY],
  );
  const ceilingLightQuat = useMemo(() => ceilingLightWorldQuaternion(rotationY), [rotationY]);
  const ceilingLightPlacements = useMemo(
    () => [{ id: `${instanceIdBase}-ceiling`, position: ceilingLightWorldPos, quaternion: ceilingLightQuat, scale: FURNITURE_SCALE * 0.6 }],
    [instanceIdBase, ceilingLightWorldPos, ceilingLightQuat],
  );
  usePooledKitProps(KIT_PATHS.lights, "native", ceilingLightPlacements);

  return null;
}

interface DeskClusterProps {
  /** P3 perf pass, item 2 (POLISH-1 follow-up, 2026-09-14): the SAME
   * `position`/`rotationY` StationModule.tsx's own outer
   * `<group position={position} rotation={[0, rotationY, 0]}>` already
   * applies -- REQUIRED (same convention as DepartmentBayShell's own props
   * above) because the table/chair below no longer mount as KitProp
   * children of that group; they register into the shared cross-scene pool
   * instead, rendered from HubRoom, a sibling elsewhere in the tree. The
   * computer/screen below stay LOCAL KitProp/DeskScreen mounts (unaffected,
   * still nested under the caller's own group) -- they carry per-instance
   * tint/canvas content an InstancedMesh's one shared material can't
   * represent, this task's own explicit "leave it" case. */
  position: [number, number, number];
  rotationY: number;
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
export function DeskCluster({ position, rotationY, accentColor, screenTitle, screenLines }: DeskClusterProps) {
  const SCREEN_POSITION: [number, number, number] = [0, DESK_TOP_HEIGHT, 0.55 * FURNITURE_SCALE];
  const instanceIdBase = useId();

  // P3 perf pass, item 2: table+chair pooled the SAME way SetKit's
  // architecture pieces already are (see this file's own "P3 perf pass"
  // header). Both had IDENTITY within this component's own local space
  // (table: no own rotation; chair: a plain Y-axis rotation) nested inside
  // the caller's `<group position={[0,0,BAY_DESK_OFFSET_Z]}>` (itself
  // inside StationModule's own `<group position={position} rotation={[0,
  // rotationY, 0]}>`) -- since every rotation in that chain is a plain
  // Y-axis rotation, world rotation is just the SUM of the Y angles (no
  // quaternion needed here, unlike CeilingLight's X+Y case -- see that
  // fixture's own `quaternion` field for why it's different). World
  // position folds BAY_DESK_OFFSET_Z into the local offset before
  // `localToWorld` rotates it by the bay's own rotationY, reproducing the
  // exact nested-group math this used to get for free from JSX nesting.
  const tablePlacements = useMemo(
    () => [{
      id: `${instanceIdBase}-table`,
      position: localToWorld(position, rotationY, [0, 0, BAY_DESK_OFFSET_Z + 0.3 * FURNITURE_SCALE]),
      rotation: [0, rotationY, 0] as [number, number, number],
      scale: FURNITURE_SCALE,
    }],
    [instanceIdBase, position, rotationY],
  );
  usePooledKitProps(KIT_PATHS.furniture.table, "native", tablePlacements);

  const chairPlacements = useMemo(
    () => [{
      id: `${instanceIdBase}-chair`,
      position: localToWorld(position, rotationY, [DESK_SEAT_LOCAL[0], DESK_SEAT_LOCAL[1], BAY_DESK_OFFSET_Z + DESK_SEAT_LOCAL[2]]),
      rotation: [0, rotationY + Math.PI, 0] as [number, number, number],
      scale: FURNITURE_SCALE,
    }],
    [instanceIdBase, position, rotationY],
  );
  usePooledKitProps(KIT_PATHS.furniture.chair, "native", chairPlacements);

  return (
    <group>
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
// flattened torus "curb") on the central circle so that boundary reads as a
// real edge instead of an invisible blend into Ground beneath it.
//
// LAYOUT builder pass (2026-09-14, campus-cross rebuild, task: "Plaza plate
// becomes the union footprint (rounded cross/square under hub + hallways +
// bays, ~1.5u apron)"): a single big circle sized to the OLD ring's outer
// edge doesn't fit the new orthogonal cross at all -- it would either clip
// a bay's own corner (if sized to the cross's on-axis reach) or waste a
// huge area of open floor in the diagonal gaps between arms (if sized to
// the cross's own corner reach). Replaced with the union shape the task
// asks for: the same central circle (now scoped to just the hub + apron)
// plus 4 flat rectangular slabs, one per arm, each sized to carry that
// arm's own T-junction + both its bays. All three dimensions
// (`centerRadius`/`armLen`/`armHalfWidth`) are passed in from Scene.tsx,
// already apron-inclusive -- layout.ts computes them, this file stays a
// pure renderer of whatever size it's given, the same "receives computed
// dimensions as props" convention this component already used before this
// pass (just three numbers instead of one).
const PLAZA_Y = -0.04;
const PLAZA_NIGHT = new THREE.Color(PALETTE.deskDark);
const PLAZA_DAY = new THREE.Color(PALETTE.plazaDay);
const _plazaColor = new THREE.Color();

export function Plaza({ centerRadius, armLen, armHalfWidth, dayFactor = 1 }: {
  centerRadius: number; armLen: number; armHalfWidth: number; dayFactor?: number;
}) {
  const color = useMemo(() => _plazaColor.copy(PLAZA_NIGHT).lerp(PLAZA_DAY, dayFactor).clone(), [dayFactor]);
  const lipTube = 0.09;
  return (
    <group>
      <mesh position={[0, PLAZA_Y, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <circleGeometry args={[centerRadius, 64]} />
        <meshStandardMaterial color={color} roughness={0.85} metalness={0.05} />
      </mesh>
      {/* Edge lip -- a low curb ring at the CENTRAL circle's own outer
          radius so that boundary reads as a real, deliberately-built edge.
          The 4 arm slabs below stay plain-edged (a lip framing every side
          of a plus-sign is a lot of extra geometry for a secondary polish
          item -- Ground.tsx's own different tone underneath already gives
          the arm's own edge some contrast; flagged as a possible follow-up,
          not silently dropped). */}
      <mesh position={[0, PLAZA_Y + lipTube * 0.5, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[centerRadius, lipTube, 8, 64]} />
        <meshStandardMaterial color={color} roughness={0.6} metalness={0.15} />
      </mesh>
      {/* 4 arm slabs -- one per cardinal spine, each starting at the hub
          center (so it seamlessly unions with the central circle, no gap)
          and reaching out to `armLen`, wide enough (`armHalfWidth`, both
          sides) to carry both of that arm's bays + the T-junction between
          them. Arms 0/2 (+-X) run long-axis-X; arms 1/3 (+-Z) run
          long-axis-Z -- a flat `rotation={[-Math.PI/2,0,0]}` plane's own
          local X always maps to world X and local Y to world (mirrored) Z,
          so swapping which planeGeometry argument is the long one is all
          that's needed, no extra per-arm Y-rotation. */}
      {[0, 1, 2, 3].map((armIndex) => {
        const angle = (armIndex * Math.PI) / 2;
        const center: [number, number, number] = [(Math.cos(angle) * armLen) / 2, PLAZA_Y, (Math.sin(angle) * armLen) / 2];
        const alongX = armIndex % 2 === 0;
        return (
          <mesh key={armIndex} position={center} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
            <planeGeometry args={alongX ? [armLen, armHalfWidth * 2] : [armHalfWidth * 2, armLen]} />
            <meshStandardMaterial color={color} roughness={0.85} metalness={0.05} />
          </mesh>
        );
      })}
    </group>
  );
}

const CORRIDOR_WIDTH = 2.6;
const CORRIDOR_RAIL_HEIGHT = 0.3;
const CORRIDOR_RAIL_THICKNESS = 0.07;
// LAYOUT builder pass (2026-09-14, campus-cross rebuild): main spines
// (hub wall -> T-junction) use the doubled-width corridor-wide.glb kit
// piece instead of corridor.glb -- "corridor-wide or 2x corridor" per the
// layout brief, chosen since one wide piece is both fewer draw calls per
// unit length AND reads as the more important "main hallway" against the
// narrower bay-side spurs. Raw footprint 8x8 (parsed this session, see
// layout.ts's own header) -- exactly 2x corridor.glb's 4x4, so both the
// segment length and the strip width double together (it's square).
const CORRIDOR_WIDE_SEGMENT_LENGTH = 8 * ARCHITECTURE_SCALE_BAY;
const CORRIDOR_WIDE_WIDTH = CORRIDOR_WIDE_SEGMENT_LENGTH;

// HALLWAY-FIX builder pass (2026-09-14, J: "the walls are the wrong way --
// how are those going to contain anything?"): measured, not assumed --
// `node dashboard/scripts/glb_extents.mjs corridor.glb corridor-wide.glb`
// walks each piece's real node hierarchy and buckets every triangle's face
// normal by axis. Both corridor.glb and corridor-wide.glb report a SQUARE
// XZ footprint (4x4 / 8x8, matching this file's own already-correct
// CORRIDOR_SEGMENT_LENGTH/CORRIDOR_WIDE_SEGMENT_LENGTH), so -- unlike
// gate-door.glb's obviously-asymmetric 4.2x1.4 box -- the piece's own
// bounding box can NOT tell you which way it opens (a square footprint has
// no visually-obvious "front"). The triangle-normal wall-axis measurement
// can: corridor.glb's wall-like (near-vertical) area facing Z is ~142.4 vs
// facing X ~27.4 (a 5.2x margin); corridor-wide.glb is ~292.4 vs ~78.2
// (3.7x) -- BOTH pieces' solid walls run along Z, meaning the piece's real
// OPEN/walkway axis is local X, not local Z. The old
// `rotation={[0, rotationY, 0]}` reused on these KitProp segments (below)
// was copy-pasted from gate-door/room's genuinely-verified "-Z is front"
// convention without re-measuring it for this different, square-footprint
// asset -- that put each segment's solid Z-facing wall directly ACROSS the
// walkway instead of along it, exactly J's "rows of wall slabs standing
// across the walkway" complaint (real captures: layout-default-1726.png,
// layout-bay0-1755.png, layout-hall0-1758.png). +90deg re-aligns local X
// (the piece's real open axis) with `rotationY`'s own direction-of-travel
// instead of local Z -- a symmetric tunnel piece is visually identical
// under +90 vs -90 here (no directional asymmetry in the measured
// geometry), so the sign was picked and then verified against a real
// capture, not guessed twice. Applies ONLY to the corridor KIT PIECE prop
// below -- the procedural floor strip/rails (drawn from its own
// `stripWidth`/`length` against a planeGeometry that every prior real
// capture already shows correctly shaped) and the gate-door KitProp
// (verified real -Z-front asymmetric geometry, 4.2 wide x 1.4 deep,
// unaffected by this bug) both keep using the original, unmodified
// `rotationY`.
const CORRIDOR_KIT_YAW_OFFSET = Math.PI / 2;

/** Real hallway between two real building openings (a hub doorway and a
 * T-junction, or a T-junction and a bay door): a guaranteed-correct
 * procedural floor strip + low side rails PLUS the kit's real corridor.glb/
 * corridor-wide.glb segments layered on top as architectural detail.
 *
 * LAYOUT builder pass (2026-09-14, J: "the doors... jumbled mess... you
 * have stuff connecting to the corner where there's no wall for it to
 * connect to"): `angle` is GONE -- the old ring layout passed a separate
 * `angle` prop the caller had to keep hand-in-sync with `from`/`to`, and a
 * corridor whose real endpoints disagreed with its own passed-in angle is
 * exactly the bug class that produced the jumble (4 of 8 corridors ran at
 * an angle with no doorway behind it). `rotationY` is now derived DIRECTLY
 * from the two real endpoints below -- see layout.ts#rotationYFacing's own
 * comment for the algebraic check that this reduces to the OLD `Math.PI/2 -
 * angle` formula for every case the ring layout ever used, so nothing that
 * used to face the hub correctly stops doing so; it now ALSO works for the
 * new off-origin side hallways (T-junction -> bay) the old formula could
 * never express (those don't lie on a ray through the world origin).
 *
 * World-2 item 3(b) bug fix (2026-09-14, prior pass): corridor.glb is an
 * UPRIGHT piece (Y 0..4.25, a square 4x4 XZ footprint, parsed from its own
 * JSON chunk), the same "modeled upright, faces -Z by default" convention
 * every other Modular Space Kit piece in this file uses -- a plain yaw
 * rotation, never a tip-over quaternion (that earlier bug tipped every
 * segment ~90deg onto its side). The procedural strip is what actually
 * GUARANTEES the continuous, correctly-sized floor; the kit segments are
 * detail on top of it, never the sole source of the connection. */
export function CorridorRun({
  from, to, dayFactor = 1, wide = false, doorAtFrom = true,
}: {
  from: [number, number, number]; to: [number, number, number]; dayFactor?: number;
  /** Main spines only -- see this function's own header for why. */
  wide?: boolean;
  /** Side hallways (T-junction -> bay) must NOT get a second door frame at
   * their T-junction end -- a junction has no door, only the two real
   * building entrances (hub doorway, bay doorway) do. Defaults true,
   * unchanged behavior for every hub-wall caller. */
  doorAtFrom?: boolean;
}) {
  const instanceIdBase = useId();
  const rotationY = Math.atan2(to[0] - from[0], to[2] - from[2]);
  // See CORRIDOR_KIT_YAW_OFFSET's own header -- the kit piece's real open
  // axis is local X, not local Z, so its yaw needs the +90deg correction
  // the procedural strip/rails and the gate-door frame (both verified
  // correct already) must NOT receive.
  const corridorKitRotationY = rotationY + CORRIDOR_KIT_YAW_OFFSET;
  const corridorPath = wide ? KIT_PATHS.architecture.corridorWide : KIT_PATHS.architecture.corridor;
  const segmentLength = wide ? CORRIDOR_WIDE_SEGMENT_LENGTH : CORRIDOR_SEGMENT_LENGTH;
  const stripWidth = wide ? CORRIDOR_WIDE_WIDTH : CORRIDOR_WIDTH;
  // World-2 coordinator polish (2026-09-14, "HALLWAYS still read as short
  // dark bridges between pods... make each corridor floor the SAME plate
  // tone/height as the plaza (continuous, no dark step)"): the strip now
  // shares Plaza's OWN color pair (was a static PALETTE.floor tone,
  // visibly darker than Plaza's own lighter tones -- exactly the "dark
  // step" reported) and near-enough Y (PLAZA_Y+0.002, a hair above Plaza's
  // own disc which already covers this same footprint underneath, purely
  // to avoid z-fighting -- not the old -0.01, a real ~0.03u ledge against
  // Plaza's -0.04). `.getStyle()` (a string) covers both the strip's own
  // `color` prop and the kit segments' `tint` below, which specifically
  // needs a string, not a THREE.Color instance.
  const plateColorStyle = useMemo(() => _plazaColor.copy(PLAZA_NIGHT).lerp(PLAZA_DAY, dayFactor).getStyle(), [dayFactor]);
  const lampFactor = interiorLampFactor(dayFactor);
  const { midpoint, length, segPositions } = useMemo(() => {
    const start = new THREE.Vector3(...from);
    const end = new THREE.Vector3(...to);
    const len = start.distanceTo(end) || 0.001;
    const mid: [number, number, number] = [(from[0] + to[0]) / 2, (from[1] + to[1]) / 2, (from[2] + to[2]) / 2];
    // draw-call sanity: segCount is small on purpose -- a 1.8u (or 3.6u
    // wide) segment length vs a ~4.5-9u hallway span means 2-3 segments
    // per run, not a dozen, x12 hallways (4 main + 8 side).
    const segCount = Math.max(1, Math.round(len / segmentLength));
    const step = len / segCount;
    const dirX = (end.x - start.x) / len;
    const dirZ = (end.z - start.z) / len;
    const segs: [number, number, number][] = [];
    for (let i = 0; i < segCount; i++) {
      const d = step * (i + 0.5);
      segs.push([start.x + dirX * d, start.y, start.z + dirZ * d]);
    }
    return { midpoint: mid, length: len, segPositions: segs };
  }, [from[0], from[1], from[2], to[0], to[1], to[2], segmentLength]);

  // P3 perf pass (POLISH-1, 2026-09-14): segments used to be one KitProp
  // clone each (a full THREE.Mesh object per segment, ~2-3 per run x up to
  // 12 hallways) -- now REGISTERED into the shared cross-hallway
  // InstancedMesh pool (see this file's own "P3 perf pass" header) instead,
  // rendered ONCE from HubRoom. "tinted" variant: that pool's own material
  // color is dayFactor-driven, computed independently there from the SAME
  // dayFactor every CorridorRun call already receives -- see that header
  // for why this never needs per-instance color, so `plateColorStyle` is
  // no longer passed as a per-segment tint here (still used just below, for
  // the strip/rail meshes, which stay un-pooled procedural geometry).
  const segPlacements = useMemo(
    () => segPositions.map((pos, i) => ({
      id: `${instanceIdBase}-seg${i}`, position: pos, rotation: [0, corridorKitRotationY, 0] as [number, number, number], scale: ARCHITECTURE_SCALE_BAY,
    })),
    [segPositions, corridorKitRotationY, instanceIdBase],
  );
  usePooledKitProps(corridorPath, "tinted", segPlacements);

  // Hub-end door frame -- "the goal is the eye tracing hub -> hallway -> bay
  // without a break." The bay end already has its own gate-door
  // (DepartmentBayShell, own pool registration); a T-junction end
  // (doorAtFrom=false, side hallways) gets neither -- an open junction, not
  // a mystery door with no room behind it. Empty array (no registration at
  // all) when doorAtFrom is false, matching the old JSX's own `{doorAtFrom
  // && ...}` -- never a phantom zero-scale instance.
  const doorPlacements = useMemo(
    () => (doorAtFrom
      ? [{ id: `${instanceIdBase}-door`, position: from, rotation: [0, rotationY, 0] as [number, number, number], scale: ARCHITECTURE_SCALE_BAY }]
      : []),
    [doorAtFrom, from, rotationY, instanceIdBase],
  );
  usePooledKitProps(KIT_PATHS.architecture.gateDoor, "native", doorPlacements);

  return (
    <group>
      <group position={midpoint} rotation={[0, rotationY, 0]}>
        <mesh position={[0, PLAZA_Y + 0.002, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[stripWidth, length]} />
          <meshStandardMaterial color={plateColorStyle} roughness={0.85} metalness={0.05} />
        </mesh>
        {[-1, 1].map((side) => (
          <mesh key={side} position={[(side * (stripWidth - CORRIDOR_RAIL_THICKNESS)) / 2, CORRIDOR_RAIL_HEIGHT / 2, 0]} castShadow>
            <boxGeometry args={[CORRIDOR_RAIL_THICKNESS, CORRIDOR_RAIL_HEIGHT, length]} />
            <meshStandardMaterial color={PALETTE.deskDark} roughness={0.6} metalness={0.2} />
          </mesh>
        ))}
      </group>
      {doorAtFrom && (
        <pointLight position={[from[0], 0.9, from[2]]} color="#ffe9c2" intensity={1.5 * lampFactor} distance={3} decay={2} />
      )}
    </group>
  );
}

// HALLWAY-FIX builder, T-junction outward-cap follow-up (2026-09-14,
// coordinator: "the spine, seen from just inside the hub doorway, ends in
// open sky/horizon... the junction's outward face reads as an open 4th
// leg"). Measured (dashboard/scripts/glb_extents.mjs, per-side triangle-
// normal breakdown -- see that tool's own analyzeWallAxis header), not
// assumed: corridor-intersection.glb reports EQUAL wall-like area on all 4
// local sides (+X=-X=+Z=-Z=8.631) with a large unclassified/diagonal area
// (23.06 vs 17.262 per axis) -- the signature of corner-pillar/pilaster
// framing (matching room-large/room-small's own pillar-and-collar look
// already visible in every real capture), not a flat blocking wall on any
// single face. That measurement alone can't PROVE a given face is fully
// open (small symmetric corner stubs would read the same way), but real
// captures from the prior pass already did: layout-hall0-1758.png (BEFORE
// this pass' corridor-rotation fix) and hallfix-tjunction-inside-1824.png
// (AFTER it) both show a clean, unbroken sightline straight through this
// piece along its own local Z axis -- exactly the "4-way piece used for a
// 3-way join" gap this component's own prior comment already named but
// never closed. This component's own `rotation={[0, rotationY, 0]}` puts
// local -Z toward the hub (layout.ts#computeArmLayout's own rotationY,
// `rotationYFacing(tCenter, HUB)`), so local +Z is the unused, outward-
// facing 4th side -- the one that needs capping, leaving the two side-
// hallway openings (local +-X, see CorridorRun's own side-hallway callers)
// untouched.
//
// Cap piece choice: no dedicated end-wall/cap piece exists in this kit
// (kenney-modular-space-kit dir listing checked this session) -- using a
// plain corridor.glb per the task's own "a corridor segment placed across
// works if the kit has no dedicated end-wall" allowance. corridor.glb's OWN
// per-side measurement (also this session) confirms it has REAL, substantial
// solid wall area on BOTH its local +Z and -Z faces (71.216 each, ~5x its
// X-faces' 13.681) -- exactly the two flat panels needed to block a
// sightline. Mounted as a CorridorRun-independent sibling inside THIS
// SAME rotated group with rotation OMITTED (identity relative to the
// parent) -- deliberately the OPPOSITE choice from CorridorRun's own
// CORRIDOR_KIT_YAW_OFFSET: an in-line hallway segment needs its OPEN axis
// (local X) aligned with the direction of travel, but a cap needs the
// opposite -- its WALL axis (local Z, unrotated here) aligned with the
// spine so the solid panel actually faces the sightline it's blocking, not
// the open ends aiming down it. Positioned at local (0,0,+CORRIDOR_SEGMENT_
// LENGTH/2) -- CORRIDOR_SEGMENT_LENGTH/2 is algebraically the SAME value as
// layout.ts#T_JUNCTION_HALF (both `(4 * ARCHITECTURE_SCALE_BAY) / 2`, the
// raw corridor/intersection footprint's own half-extent) computed locally
// so this file never has to import from layout.ts (see that module's own
// header: the dependency runs ONE way only, layout.ts -> SetKit.tsx) --
// flush with the intersection piece's own outward edge, overlapping halfway
// into it for a guaranteed no-gap seal.
const T_JUNCTION_CAP_OFFSET = CORRIDOR_SEGMENT_LENGTH / 2;

/** T-junction dressing -- one corridor-intersection.glb piece + a light, at
 * a spine's own T-junction center (layout.ts#computeArmLayout's `tCenter`).
 * Visually a 4-way crossing piece used for a 3-way join (only 3 real
 * hallways ever meet here: the main spine + 2 side hallways) -- the kit has
 * no dedicated T-piece, so the unused 4th "arm" stub is explicitly CAPPED
 * below rather than left open (see T_JUNCTION_CAP_OFFSET's own header for
 * the measured evidence + reasoning). */
export function TJunction({ position, rotationY, dayFactor = 1 }: {
  position: [number, number, number]; rotationY: number; dayFactor?: number;
}) {
  const instanceIdBase = useId();
  const lampFactor = interiorLampFactor(dayFactor);

  // P3 perf pass (POLISH-1, 2026-09-14): both pieces used to be direct
  // KitProp children of this component's own <group> below -- now
  // REGISTERED into the shared cross-junction InstancedMesh pool (see
  // SetKit.tsx's own "P3 perf pass" header) instead, rendered ONCE from
  // HubRoom. "native": neither piece was ever tinted here.
  const intersectionPlacements = useMemo(
    () => [{ id: `${instanceIdBase}-intersection`, position, rotation: [0, rotationY, 0] as [number, number, number], scale: ARCHITECTURE_SCALE_BAY }],
    [instanceIdBase, position, rotationY],
  );
  usePooledKitProps(KIT_PATHS.architecture.corridorIntersection, "native", intersectionPlacements);

  // Cap piece -- WORLD position/rotation computed explicitly (localToWorld)
  // since the pooled instance renders from HubRoom (a sibling elsewhere in
  // the tree), not nested inside this component's own <group> any more.
  // Rotation OMITTED relative to the group in the ORIGINAL code (see
  // T_JUNCTION_CAP_OFFSET's own header: "rotation OMITTED (identity
  // relative to the parent)") -- so its WORLD rotation is exactly this
  // junction's OWN rotationY, reproduced directly here.
  const capWorldPos = useMemo(() => localToWorld(position, rotationY, [0, 0, T_JUNCTION_CAP_OFFSET]), [position, rotationY]);
  const capPlacements = useMemo(
    () => [{ id: `${instanceIdBase}-cap`, position: capWorldPos, rotation: [0, rotationY, 0] as [number, number, number], scale: ARCHITECTURE_SCALE_BAY }],
    [instanceIdBase, capWorldPos, rotationY],
  );
  usePooledKitProps(KIT_PATHS.architecture.corridor, "native", capPlacements);

  return (
    <group position={position} rotation={[0, rotationY, 0]}>
      <pointLight position={[0, 1.6, 0]} color="#ffe9c2" intensity={2.5 * lampFactor} distance={5} decay={2} />
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

// P3 perf pass, item 2 (POLISH-1 follow-up, 2026-09-14): the old
// `CeilingLight` component (a plain KitProp, `rotation={[Math.PI, 0, 0]}`)
// is gone -- both its call sites (HubRoom, DepartmentBayShell above) now
// register directly into the shared `KIT_PATHS.lights` pool instead (see
// `ceilingLightWorldQuaternion` and each call site's own registration).

// Preload the small, always-visible set eagerly (drei's suspense cache) --
// characters are preloaded per-body from KitAgent.tsx instead, since which
// bodies are actually needed depends on runtime lane/persona names. `false`
// (useDraco) on every call -- see KitProp's own comment on why this is
// explicit rather than left to the (network-pointing) default.
useGLTF.preload(KIT_PATHS.architecture.roomLarge, false);
useGLTF.preload(KIT_PATHS.architecture.roomSmall, false);
useGLTF.preload(KIT_PATHS.architecture.corridor, false);
useGLTF.preload(KIT_PATHS.architecture.corridorWide, false);
useGLTF.preload(KIT_PATHS.architecture.corridorIntersection, false);
useGLTF.preload(KIT_PATHS.architecture.gateDoor, false);
useGLTF.preload(KIT_PATHS.furniture.table, false);
useGLTF.preload(KIT_PATHS.furniture.chair, false);
useGLTF.preload(KIT_PATHS.furniture.computer, false);
useGLTF.preload(KIT_PATHS.furniture.computerScreen, false);
useGLTF.preload(KIT_PATHS.lights, false);
// World-3 environment pass: terrain/prop pieces, same eager-preload
// convention as every other always-visible piece above (`false` = no Draco,
// see KitProp's own comment for why that's explicit here).
useGLTF.preload(KIT_PATHS.terrain.rock, false);
useGLTF.preload(KIT_PATHS.terrain.rockSmallA, false);
useGLTF.preload(KIT_PATHS.terrain.crater, false);
useGLTF.preload(KIT_PATHS.terrain.craterLarge, false);
useGLTF.preload(KIT_PATHS.baseProps.satelliteDish, false);
useGLTF.preload(KIT_PATHS.baseProps.rover, false);
