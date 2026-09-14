"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { PALETTE } from "./palette";

// ─── LIVE-1 item 2e (2026-09-14, J: "it still a 'Dead' world") ─────────────
// "Two drones... circling the ring on a slow path is fine as ambience -- one
// instanced mesh, no new assets unless CC0 already in dashboard/public/
// hq-assets". Checked manifest.json + LICENSES.md before writing this: the
// full bundled pack list is characters / desk-furniture / corridor-room
// architecture / one astronaut figure / barrels / ceiling lights -- nothing
// reads as a drone or service bot. Built procedurally instead, the SAME
// "no matching kit piece -> plain three.js primitives" convention
// Courier.tsx's own little bot already uses elsewhere in this scene. ONE
// shared geometry + material via THREE.InstancedMesh (a single draw call
// regardless of instance count) -- cheap enough to run unconditionally on
// BOTH tiers, unlike the real kit-geometry pieces elsewhere in this file
// that are gated behind `ultra` specifically because they'd blow the TV's
// draw-call budget.

const DRONE_COUNT = 2;
// Outside RING_RADIUS(14)+BAY_HALF_DEPTH(~2.7=~16.7) so the patrol path
// clears the station's own outer wall instead of clipping through it, but
// close enough to actually cross the closer ultra-tier camera's own frame
// (Scene.tsx#CAMERA_DIST_ULTRA=16 -- LIVE-1 item 1) -- the original 19
// verified (real capture, hq-live-2-a.png) as too far out to ever enter
// frame from the fixed vantage point's own limited FOV, one orbit sampled.
const DRONE_RADIUS = 17.2;
const DRONE_HEIGHT = 4.4;
const DRONE_PERIOD_S = 110; // one slow revolution -- "ambience," not a hazard light

const _m = new THREE.Matrix4();
const _pos = new THREE.Vector3();
const _quat = new THREE.Quaternion();
const _scale = new THREE.Vector3(1, 1, 1);
const _up = new THREE.Vector3(0, 1, 0);

export default function ServiceDrones({ reducedMotion }: { reducedMotion: boolean }) {
  const mesh = useRef<THREE.InstancedMesh>(null);

  // Flattened octahedron -- a small angular "hover drone" hull. Geometry-
  // level scale (baked into the vertex data ONCE here, not a per-frame or
  // parent-object transform) so it never interferes with the per-instance
  // placement matrices written in useFrame below -- scaling the InstancedMesh
  // OBJECT itself would also scale each instance's world-space POSITION
  // offset, squashing the orbit radius/height along with the geometry.
  const geometry = useMemo(() => {
    const geo = new THREE.OctahedronGeometry(0.17, 0);
    geo.scale(1, 0.4, 1);
    return geo;
  }, []);

  useFrame((state) => {
    if (!mesh.current) return;
    const t = reducedMotion ? 0 : state.clock.elapsedTime;
    for (let i = 0; i < DRONE_COUNT; i++) {
      const phase = (i / DRONE_COUNT) * Math.PI * 2;
      const angle = (t / DRONE_PERIOD_S) * Math.PI * 2 + phase;
      const bob = Math.sin(t * 0.6 + phase * 1.7) * 0.25;
      _pos.set(Math.cos(angle) * DRONE_RADIUS, DRONE_HEIGHT + bob, Math.sin(angle) * DRONE_RADIUS);
      // Yaw only (around world-up) to face the direction of travel -- the
      // flattened geometry axis stays vertical, reading as a hovering disc
      // rather than tumbling nose-first through its own orbit.
      const yaw = angle + Math.PI / 2;
      _quat.setFromAxisAngle(_up, yaw);
      _m.compose(_pos, _quat, _scale);
      mesh.current.setMatrixAt(i, _m);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[geometry, undefined, DRONE_COUNT]} frustumCulled={false}>
      <meshBasicMaterial color={PALETTE.hubRing} toneMapped={false} />
    </instancedMesh>
  );
}
