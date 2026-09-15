// @ts-nocheck -- same reason as tests/campus-gate.test.ts's own header: this
// file needs to reproduce layout.ts's OWN math without importing it --
// layout.ts imports SetKit.tsx (a real .tsx React/three component file),
// which node's own ESM loader refuses to load under plain `node --test`
// (confirmed by every sibling *.test.ts file in this directory that already
// works around the same constraint). Purely a syntax-erasure pragma -- has
// no effect on what actually runs.
//
// DESK-RING pass (2026-09-15, BUILD worker, J top-down feedback: "desks sit
// inside the walls, no intentional layout"). Regression coverage for the
// PERSONA_WALL_RADIUS fix (layout.ts, 6.5 -> 4.1): asserts the VISIBLE
// table geometry (not just the abstract slot radius) stays inside the hub's
// own wall, with a real clearance margin, for every persona desk slot the
// current 6-persona roster produces.
//
// All constants below are literal reproductions of the real, currently-
// shipping values in SetKit.tsx/layout.ts/HubInterior.tsx (never invented) --
// see each constant's own comment for its source. If any of those upstream
// numbers ever change, this test's own literals need updating too, exactly
// the same contract tests/campus-gate.test.ts already established for
// computeCampusGateGeometry.
//
// Run: cd dashboard && node --test tests/hq-hub-layout.test.ts
// (or the full suite: cd dashboard && npm test)

import { test } from "node:test";
import assert from "node:assert/strict";

// SetKit.tsx: ARCHITECTURE_SCALE_HUB=0.75 -> HUB_WALL_RADIUS=10*0.75=7.5.
const HUB_WALL_RADIUS = 7.5;
// SetKit.tsx: FURNITURE_SCALE=2.0, BAY_DESK_OFFSET_Z=0.8.
const FURNITURE_SCALE = 2.0;
const BAY_DESK_OFFSET_Z = 0.8;
// layout.ts (this pass): PERSONA_WALL_RADIUS moved 6.5 -> 4.1 (see that
// file's own header for the full 5.5-table-center derivation).
const PERSONA_WALL_RADIUS = 4.1;
// layout.ts: WALL_SEGMENT_SPREAD = +-18deg off a segment's own 45deg-offset
// center.
const WALL_SEGMENT_SPREAD = (18 * Math.PI) / 180;
// table.glb raw AABB, parsed directly via scripts/glb_extents.mjs this pass:
// root-space size X=1.100, Z=0.600 (Y/height irrelevant here).
const TABLE_RAW_X = 1.1;
const TABLE_RAW_Z = 0.6;
// SetKit.tsx#DeskCluster: table world center sits at LOCAL [0,0,
// BAY_DESK_OFFSET_Z + 0.3*FURNITURE_SCALE] relative to the slot's own
// position/rotationY (localToWorld call in DeskCluster's tablePlacements) --
// verified by reading that component directly, not assumed.
const TABLE_LOCAL_Z_OFFSET = BAY_DESK_OFFSET_Z + 0.3 * FURNITURE_SCALE;
const TABLE_HALF_X = (TABLE_RAW_X * FURNITURE_SCALE) / 2; // world half-width (tangential axis)
const TABLE_HALF_Z = (TABLE_RAW_Z * FURNITURE_SCALE) / 2; // world half-depth (radial axis)

/** Mirrors layout.ts#armAngle. */
function armAngle(k: number): number {
  return (k * Math.PI) / 2;
}

/** Mirrors layout.ts#computePersonaWallSlots's own angle/position math
 * (brainWallArmIndex=0 -- today's BRAIN_WALL_ARM_INDEX, per Scene.tsx). */
function personaSlotAngle(i: number): number {
  const brainSegment = 0;
  const otherSegments = [0, 1, 2, 3].filter((k) => k !== brainSegment);
  const segment = otherSegments[Math.floor(i / 2) % otherSegments.length];
  const side = i % 2 === 0 ? -1 : 1;
  const segCenterAngle = armAngle(segment) + Math.PI / 4;
  return segCenterAngle + side * WALL_SEGMENT_SPREAD;
}

/** The table's own 4 world-space corners for a persona slot at `angle`,
 * radius PERSONA_WALL_RADIUS -- mirrors DeskCluster's real local->world
 * chain: slot position (on the PERSONA_WALL_RADIUS ring, facing the hub via
 * rotationYFacing) -> table center offset by TABLE_LOCAL_Z_OFFSET along the
 * slot's own local +Z (which points OUTWARD/away from the hub, since local
 * -Z is defined to face HUB) -> +-TABLE_HALF_X/+-TABLE_HALF_Z corners in the
 * table's own local frame, rotated by the same yaw. */
function tableCorners(angle: number): { x: number; z: number }[] {
  // rotationYFacing(slotPos, HUB) for a point already on a ray through the
  // origin reduces to Math.PI/2 - angle (layout.ts's own documented
  // identity) -- local -Z then points toward the origin, local +Z outward.
  const rotationY = Math.PI / 2 - angle;
  const slotX = Math.cos(angle) * PERSONA_WALL_RADIUS;
  const slotZ = Math.sin(angle) * PERSONA_WALL_RADIUS;
  const cornersLocal = [
    [-TABLE_HALF_X, TABLE_LOCAL_Z_OFFSET - TABLE_HALF_Z],
    [TABLE_HALF_X, TABLE_LOCAL_Z_OFFSET - TABLE_HALF_Z],
    [-TABLE_HALF_X, TABLE_LOCAL_Z_OFFSET + TABLE_HALF_Z],
    [TABLE_HALF_X, TABLE_LOCAL_Z_OFFSET + TABLE_HALF_Z],
  ];
  const sinY = Math.sin(rotationY);
  const cosY = Math.cos(rotationY);
  // three.js Y-axis rotation of a local (x,z) vector: matches localToWorld's
  // own convention (SetKit.tsx), reproduced here rather than imported for
  // the same node-ESM-can't-load-SetKit.tsx reason as everything else in
  // this file.
  return cornersLocal.map(([lx, lz]) => ({
    x: slotX + lx * cosY + lz * sinY,
    z: slotZ + -lx * sinY + lz * cosY,
  }));
}

function radius(p: { x: number; z: number }): number {
  return Math.hypot(p.x, p.z);
}

test("DESK-RING: every persona table's own center lands at radius 5.5 (PERSONA_WALL_RADIUS + the DeskCluster-internal 1.4u offset)", () => {
  for (let i = 0; i < 6; i++) {
    const angle = personaSlotAngle(i);
    // center = slot + TABLE_LOCAL_Z_OFFSET outward along the same radial
    // direction the slot itself sits on (rotationYFacing reduces to a pure
    // radial rotation for any on-origin-ray slot).
    const cx = Math.cos(angle) * (PERSONA_WALL_RADIUS + TABLE_LOCAL_Z_OFFSET);
    const cz = Math.sin(angle) * (PERSONA_WALL_RADIUS + TABLE_LOCAL_Z_OFFSET);
    const r = Math.hypot(cx, cz);
    assert.ok(Math.abs(r - 5.5) < 1e-9, `slot ${i} table center radius ${r} !== 5.5`);
  }
});

test("DESK-RING: every persona table corner stays inside radius 7.0 (clears HUB_WALL_RADIUS=7.5 with margin)", () => {
  for (let i = 0; i < 6; i++) {
    const angle = personaSlotAngle(i);
    for (const corner of tableCorners(angle)) {
      const r = radius(corner);
      assert.ok(r < 7.0, `slot ${i} corner radius ${r} >= 7.0 (would clip the wall mesh)`);
    }
  }
});

test("DESK-RING: every persona table's OUTWARD (wall-facing) edge sits >=1.0u clear of HUB_WALL_RADIUS", () => {
  for (let i = 0; i < 6; i++) {
    const angle = personaSlotAngle(i);
    const backEdgeRadius = PERSONA_WALL_RADIUS + TABLE_LOCAL_Z_OFFSET + TABLE_HALF_Z;
    assert.ok(
      HUB_WALL_RADIUS - backEdgeRadius >= 1.0,
      `slot ${i} back-edge radius ${backEdgeRadius} leaves < 1.0u clearance to the wall (${HUB_WALL_RADIUS})`,
    );
  }
});

test("DESK-RING: no persona slot falls inside segment 0 (armAngle(0)..armAngle(1), 0..90deg) -- the reserved brain-wall segment carrying BrainCore/meeting-table/Gamma-desk/cables/monitor-stand", () => {
  const TWO_PI = Math.PI * 2;
  const normalize = (a: number) => ((a % TWO_PI) + TWO_PI) % TWO_PI;
  for (let i = 0; i < 6; i++) {
    const angle = normalize(personaSlotAngle(i));
    const inSegmentZero = angle >= 0 && angle <= Math.PI / 2;
    assert.ok(!inSegmentZero, `slot ${i} angle ${angle} falls inside segment 0 (reserved for fixed hub furniture)`);
  }
});

// ─── Monitor-stand / cable collision check (TWIN-MONITORS pass) ───────────
// Mirrors layout.ts#computeMonitorMount + HubInterior.tsx#CABLE_ANGLES_DEG's
// own post-fix values -- asserts the resolved collision (cable moved
// 45deg -> 28deg) actually clears the monitor pair's own angular footprint.
const MONITOR_STAND_RADIUS = 5.6;
const MONITOR_SEGMENT_CENTER_DEG = 45; // armAngle(0) + 45deg
const MONITOR_SCREEN_HALF_WIDTH = 1.1; // (2.0 screen + 0.2 gap)/2, see TwinMonitors.tsx
const CABLE_RADIUS = 5.5;
const CABLE_ANGLES_DEG = [12, 28, 78]; // HubInterior.tsx, post this-pass fix

function deg(d: number): number {
  return (d * Math.PI) / 180;
}

test("TWIN-MONITORS: the moved cable cluster (28deg) sits outside the monitor pair's own angular span at the shared 45deg corner", () => {
  const halfSpanDeg = (Math.atan(MONITOR_SCREEN_HALF_WIDTH / MONITOR_STAND_RADIUS) * 180) / Math.PI;
  const spanLo = MONITOR_SEGMENT_CENTER_DEG - halfSpanDeg;
  const spanHi = MONITOR_SEGMENT_CENTER_DEG + halfSpanDeg;
  for (const cableDeg of CABLE_ANGLES_DEG) {
    assert.ok(
      cableDeg < spanLo || cableDeg > spanHi,
      `cable at ${cableDeg}deg falls inside the monitor pair's own [${spanLo.toFixed(1)}, ${spanHi.toFixed(1)}]deg span`,
    );
  }
});

test("TWIN-MONITORS: monitor stand + screen pair stay inside the hub wall", () => {
  const angle = deg(MONITOR_SEGMENT_CENTER_DEG);
  const standX = Math.cos(angle) * MONITOR_STAND_RADIUS;
  const standZ = Math.sin(angle) * MONITOR_STAND_RADIUS;
  const standRadius = Math.hypot(standX, standZ);
  assert.ok(standRadius + MONITOR_SCREEN_HALF_WIDTH < HUB_WALL_RADIUS, "monitor stand + screen half-width reaches the wall");
});
