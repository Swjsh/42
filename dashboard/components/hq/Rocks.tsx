"use client";

import { useEffect, useMemo, useRef } from "react";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { seededRandom } from "./palette";
import { KIT_PATHS, KitProp } from "./SetKit";

// ─── E2, World-3 environment pass (2026-09-14, J: "grey abyss... regolith
// ground with craters and scattered rocks") ─────────────────────────────────
// Instanced rock field + 2 hero boulder landmarks, kenney-space-kit CC0
// pieces (LICENSES.md's own "Update 2026-09-14" entry). Ultra tier only --
// "the heavier set" per this pass's own brief, matching every other real-
// kit-geometry-at-volume piece in this tree (HubRoom/DeskCluster/Plaza are
// all `{ultra && ...}` in Scene.tsx). Exactly 2 InstancedMesh draw calls
// total regardless of instance count (one per rock variant) -- the whole
// POINT of instancing over KitProp's per-instance clone+useEffect path,
// which would cost 150-300 individual scene-graph nodes + material clones
// at this count (KitProp stays right for the 8-count craters in Ground.tsx
// and the 2 hero boulders below -- counts where per-instance tinting/
// shadow-flags actually matter and setup cost is negligible).

const PLAZA_CLEARANCE = 19; // just past Scene.tsx's own PLAZA_RADIUS (~18.2)
const FIELD_MAX_RADIUS = 60; // stays inside SkyDome/Ground's own shared 70-radius edge

interface RockInstance {
  position: [number, number, number];
  rotationY: number;
  scale: number;
}

/** Deterministic annulus scatter (seededRandom, never Math.random -- this
 * tree's own standing convention). sqrt-biased radius so density is uniform
 * per unit AREA, not per unit radius (a plain linear radius pick would
 * over-cluster rocks near the inner edge, where less area exists per radius
 * step). Computed ONCE at module load (fixed seed -> fixed layout every
 * reload), never recomputed per-render. */
function scatterRocks(seed: string, count: number, minR: number, maxR: number, minScale: number, maxScale: number): RockInstance[] {
  const rng = seededRandom(seed);
  return Array.from({ length: count }, () => {
    const angle = rng() * Math.PI * 2;
    const radius = minR + Math.sqrt(rng()) * (maxR - minR);
    return {
      position: [Math.cos(angle) * radius, -0.05, Math.sin(angle) * radius],
      rotationY: rng() * Math.PI * 2,
      scale: minScale + rng() * (maxScale - minScale),
    };
  });
}

// 2 variants, ~240 rocks total -- inside the task's own 150-300 budget.
const FIELD_A = scatterRocks("hq-rocks-a-v1", 150, PLAZA_CLEARANCE, FIELD_MAX_RADIUS, 0.5, 1.3);
const FIELD_B = scatterRocks("hq-rocks-b-v1", 90, PLAZA_CLEARANCE, FIELD_MAX_RADIUS, 0.35, 0.95);

const _matrix = new THREE.Matrix4();
const _pos = new THREE.Vector3();
const _quat = new THREE.Quaternion();
const _scaleVec = new THREE.Vector3();
const _euler = new THREE.Euler();

/** First mesh's geometry+material out of a static (unskinned) GLB scene --
 * the raw building blocks InstancedMesh needs (it draws ONE geometry/
 * material pair N times via a per-instance matrix; it can't consume a whole
 * cloned scene graph the way KitProp's `<primitive>` path does). Kenney's
 * rock pieces are single-mesh (confirmed by traversing the loaded scene --
 * the loop below takes the first Mesh found, correct for these assets). */
function useInstancedSource(path: string): { geometry: THREE.BufferGeometry; material: THREE.Material } | null {
  const { scene } = useGLTF(path, false);
  return useMemo(() => {
    let found: { geometry: THREE.BufferGeometry; material: THREE.Material } | null = null;
    scene.traverse((obj) => {
      if (found || !(obj instanceof THREE.Mesh)) return;
      found = { geometry: obj.geometry, material: obj.material as THREE.Material };
    });
    return found;
  }, [scene]);
}

function RockField({ path, instances }: { path: string; instances: RockInstance[] }) {
  const source = useInstancedSource(path);
  const meshRef = useRef<THREE.InstancedMesh>(null);

  // Matrices written ONCE -- `instances` is a module-level constant (stable
  // forever) and `source` only changes if the GLB itself reloads, so this
  // never re-runs per-frame; the rock field never moves.
  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh || !source) return;
    instances.forEach((inst, i) => {
      _pos.set(inst.position[0], inst.position[1], inst.position[2]);
      _euler.set(0, inst.rotationY, 0);
      _quat.setFromEuler(_euler);
      _scaleVec.setScalar(inst.scale);
      _matrix.compose(_pos, _quat, _scaleVec);
      mesh.setMatrixAt(i, _matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  }, [source, instances]);

  if (!source) return null;
  return (
    <instancedMesh ref={meshRef} args={[source.geometry, source.material, instances.length]} castShadow receiveShadow />
  );
}

interface RocksProps {
  ultra: boolean;
}

/** Instanced rock field (2 variants, ~240 total) + 2 hero boulder landmarks
 * -- ultra tier only. See this file's own top comment for why InstancedMesh
 * beats KitProp at this count. */
export default function Rocks({ ultra }: RocksProps) {
  if (!ultra) return null;
  return (
    <>
      <RockField path={KIT_PATHS.terrain.rock} instances={FIELD_A} />
      <RockField path={KIT_PATHS.terrain.rockSmallA} instances={FIELD_B} />
      {/* Hero boulders -- individually placed landmarks (fixed positions,
          not part of the seeded scatter above) so they read as deliberate
          composition anchors, not just denser scatter. */}
      <KitProp path={KIT_PATHS.terrain.rockLargeA} scale={2.6} position={[-24, -0.05, 14]} rotation={[0, 0.6, 0]} castShadow receiveShadow />
      <KitProp path={KIT_PATHS.terrain.rockLargeB} scale={2.2} position={[22, -0.05, -20]} rotation={[0, 2.1, 0]} castShadow receiveShadow />
    </>
  );
}

useGLTF.preload(KIT_PATHS.terrain.rockLargeA, false);
useGLTF.preload(KIT_PATHS.terrain.rockLargeB, false);
