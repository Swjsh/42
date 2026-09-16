// @ts-nocheck -- same reason as tests/campus-gate.test.ts's own header: this
// file needs to reproduce layout.ts's OWN math without importing it --
// layout.ts imports SetKit.tsx (a real .tsx React/three component file),
// which node's own ESM loader refuses to load under plain `node --test`
// (confirmed by every sibling *.test.ts file in this directory that already
// works around the same constraint). Purely a syntax-erasure pragma -- has
// no effect on what actually runs.
//
// DESKS-AGAINST-WALLS pass (2026-09-15, BUILD worker, J: "put the computer
// in a way that it would actually be... up against the wall, not inside the
// wall"). Supersedes the DESK-ROWS pass's own tests below (that pass fixed
// wall clearance and shared yaw, but still placed both desks of a segment
// on the room's DIAGONAL -- the "why are the desks diagonal in the middle
// of the room" shape). This pass moves persona desks onto the 4 real WALLS
// themselves (one on each side of that wall's own door), axis-aligned --
// asserts the VISIBLE table geometry backs against a real wall, in a
// 0.2-0.6u band, with the 2 slots nearest the brain corner dropped.
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
// SetKit.tsx: FURNITURE_SCALE=2.0, BAY_DESK_OFFSET_Z=0.8 (persona/Gamma
// desks -- unchanged by this pass).
const FURNITURE_SCALE = 2.0;
const BAY_DESK_OFFSET_Z = 0.8;
// layout.ts (DESKS-AGAINST-WALLS pass): PERSONA_WALL_RADIUS is now the
// anchor's distance from hub-center along the WALL'S OWN outward normal
// (armAngle(k)), not a diagonal-corner radius -- see layout.ts's own header
// for the full back-edge-clearance derivation (anchor = wall inner face
// 7.35 - target clearance 0.35 - table's own local reach 2.0 = 5.0).
const PERSONA_WALL_RADIUS = 5.1;
// layout.ts: center-to-center-from-wall-normal-point tangential offset for
// each of a wall's 2 desks -- "midway between the door's clear edge (+1.5u
// aisle) and the corner (-1.0u)", see layout.ts's own header.
const PERSONA_WALL_LATERAL_OFFSET = 4.6;
// table.glb raw AABB, parsed directly via scripts/glb_extents.mjs:
// root-space size X=1.100, Z=0.600 (Y/height irrelevant here).
const TABLE_RAW_X = 1.1;
const TABLE_RAW_Z = 0.6;
// SetKit.tsx#DeskCluster: table world center sits at LOCAL [0,0,
// BAY_DESK_OFFSET_Z + 0.3*FURNITURE_SCALE] relative to the slot's own
// position/rotationY (localToWorld call in DeskCluster's tablePlacements) --
// verified by reading that component directly, not assumed.
const TABLE_LOCAL_Z_OFFSET = BAY_DESK_OFFSET_Z + 0.3 * FURNITURE_SCALE;
const TABLE_HALF_X = (TABLE_RAW_X * FURNITURE_SCALE) / 2; // world half-width (tangential axis)
const TABLE_HALF_Z = (TABLE_RAW_Z * FURNITURE_SCALE) / 2; // world half-depth (radial/wall-normal axis)
// lib/hq-scene-audit.ts's own literals -- the hub is modeled there as a
// plain axis-aligned square, HUB_WALL_RADIUS wide, WALL_THICKNESS thick.
const HUB_INNER_WALL_FACE = HUB_WALL_RADIUS - 0.3 / 2;
const HUB_DOOR_HALF_WIDTH = (4.2 * 0.75) / 2; // gate-door.glb raw 4.2 * ARCHITECTURE_SCALE_HUB(0.75), /2

/** Mirrors layout.ts#armAngle. */
function armAngle(k: number): number {
  return (k * Math.PI) / 2;
}

interface PersonaSlot {
  x: number;
  z: number;
  rotationY: number;
  wall: number;
  lateralSign: -1 | 1;
}

/** Mirrors layout.ts#computePersonaWallSlots's own math EXACTLY
 * (DESKS-AGAINST-WALLS pass): ONE shared yaw per WALL (evaluated at the
 * wall's own outward-normal point, not per desk), both desks offset along
 * the wall's own tangent by +-PERSONA_WALL_LATERAL_OFFSET. Drops the one
 * candidate on `brainWall` nearest its OWN high corner (lateralSign=-1) and
 * the one on `brainWall+1` nearest ITS OWN low corner (lateralSign=+1) --
 * both the SAME 45deg corner the monitor stand/BrainCore/Gamma's desk
 * already occupy. brainWallArmIndex=0 -- today's BRAIN_WALL_ARM_INDEX, per
 * Scene.tsx. */
function personaSlots(): PersonaSlot[] {
  const brainWall = 0;
  const highCornerWall = (brainWall + 1) % 4;
  const candidates: Array<{ wall: number; lateralSign: -1 | 1 }> = [];
  for (let offset = 0; offset < 4; offset++) {
    const wall = (brainWall + offset) % 4;
    for (const lateralSign of [-1, 1] as const) {
      if (wall === brainWall && lateralSign === -1) continue;
      if (wall === highCornerWall && lateralSign === 1) continue;
      candidates.push({ wall, lateralSign });
    }
  }
  return candidates.map(({ wall, lateralSign }) => {
    const wallAngle = armAngle(wall);
    const wallX = Math.cos(wallAngle) * PERSONA_WALL_RADIUS;
    const wallZ = Math.sin(wallAngle) * PERSONA_WALL_RADIUS;
    // rotationYFacing(wallNormalPoint, HUB) for a point on a ray through the
    // origin reduces to Math.PI/2 - wallAngle (layout.ts's own documented
    // identity).
    const rotationY = Math.PI / 2 - wallAngle;
    const tangentX = Math.cos(rotationY);
    const tangentZ = -Math.sin(rotationY);
    return {
      x: wallX + lateralSign * PERSONA_WALL_LATERAL_OFFSET * tangentX,
      z: wallZ + lateralSign * PERSONA_WALL_LATERAL_OFFSET * tangentZ,
      rotationY,
      wall,
      lateralSign,
    };
  });
}

/** The table's own 4 world-space corners for a persona slot -- mirrors
 * DeskCluster's real local->world chain: slot position -> table center
 * offset by TABLE_LOCAL_Z_OFFSET along the slot's own local +Z (outward,
 * away from the hub, toward the wall) -> +-TABLE_HALF_X/+-TABLE_HALF_Z
 * corners in the table's own local frame, rotated by the shared yaw. */
function tableCorners(slot: PersonaSlot): { x: number; z: number }[] {
  const cornersLocal = [
    [-TABLE_HALF_X, TABLE_LOCAL_Z_OFFSET - TABLE_HALF_Z],
    [TABLE_HALF_X, TABLE_LOCAL_Z_OFFSET - TABLE_HALF_Z],
    [-TABLE_HALF_X, TABLE_LOCAL_Z_OFFSET + TABLE_HALF_Z],
    [TABLE_HALF_X, TABLE_LOCAL_Z_OFFSET + TABLE_HALF_Z],
  ];
  const sinY = Math.sin(slot.rotationY);
  const cosY = Math.cos(slot.rotationY);
  // three.js Y-axis rotation of a local (x,z) vector: matches localToWorld's
  // own convention (SetKit.tsx), reproduced here rather than imported for
  // the same node-ESM-can't-load-SetKit.tsx reason as everything else in
  // this file.
  return cornersLocal.map(([lx, lz]) => ({
    x: slot.x + lx * cosY + lz * sinY,
    z: slot.z + -lx * sinY + lz * cosY,
  }));
}

test("DESKS-AGAINST-WALLS: exactly 6 persona slots, one per real wall side minus the 2 dropped at the brain corner", () => {
  const slots = personaSlots();
  assert.equal(slots.length, 6);
  const perWall = [0, 1, 2, 3].map((w) => slots.filter((s) => s.wall === w).length);
  // brainWall(0) keeps 1, highCornerWall(1) keeps 1, the other two keep 2 each.
  assert.deepEqual(perWall, [1, 1, 2, 2], `expected [1,1,2,2] desks per wall, got [${perWall.join(",")}]`);
});

test("DESKS-AGAINST-WALLS: every persona table's BACK edge (the side nearest its own wall) sits 0.2-0.6u off the hub's real axis-aligned wall", () => {
  for (const slot of personaSlots()) {
    const corners = tableCorners(slot);
    // The back edge is whichever corner pair sits FARTHEST from hub-center
    // along the wall's own normal -- for an axis-aligned desk this is
    // simply the corner set with the largest Chebyshev coordinate.
    const wallClearances = corners.map((c) => HUB_INNER_WALL_FACE - Math.max(Math.abs(c.x), Math.abs(c.z)));
    const backEdgeClearance = Math.min(...wallClearances);
    assert.ok(
      backEdgeClearance >= 0.2 - 1e-9 && backEdgeClearance <= 0.6 + 1e-9,
      `wall ${slot.wall} side ${slot.lateralSign} back-edge clearance ${backEdgeClearance.toFixed(3)} outside [0.2,0.6]u`,
    );
  }
});

test("DESKS-AGAINST-WALLS: every persona table is axis-aligned (yaw a multiple of 90deg) -- long axis parallel to its own wall", () => {
  for (const slot of personaSlots()) {
    const normalized = ((slot.rotationY % (Math.PI / 2)) + Math.PI / 2) % (Math.PI / 2);
    const distToAxis = Math.min(normalized, Math.PI / 2 - normalized);
    assert.ok(distToAxis < 1e-9, `wall ${slot.wall} side ${slot.lateralSign} rotationY ${slot.rotationY} is not a multiple of 90deg`);
  }
});

test("DESKS-AGAINST-WALLS: the two desks sharing a wall share exactly one yaw", () => {
  for (let w = 0; w < 4; w++) {
    const slots = personaSlots().filter((s) => s.wall === w);
    if (slots.length < 2) continue;
    assert.ok(Math.abs(slots[0].rotationY - slots[1].rotationY) < 1e-9, `wall ${w} desks have different yaws`);
  }
});

// SELF-CORRECTION regression pin (see layout.ts#PERSONA_WALL_RADIUS's own
// header): the first derivation of these two constants (5.0/4.7875) passed
// every SAME-wall check above but a real hq_live_probe --plausibility run
// FAILed desk_clearance 6/6 -- TWO desks from ADJACENT, PERPENDICULAR walls
// both reach toward the SAME real room corner (the 3 corners this pass
// doesn't reserve for the brain wall) and their axis-aligned AABBs clip by
// up to 0.09u there, a cross-wall interaction no same-wall-only check (like
// the one just above) can ever catch. This test checks EVERY pair, not
// just same-wall pairs.
test("DESKS-AGAINST-WALLS: no two persona tables overlap as AABBs, including desks on DIFFERENT (perpendicular) walls sharing a real room corner", () => {
  const slots = personaSlots();
  const aabbs = slots.map((slot) => {
    const corners = tableCorners(slot);
    return {
      minX: Math.min(...corners.map((c) => c.x)), maxX: Math.max(...corners.map((c) => c.x)),
      minZ: Math.min(...corners.map((c) => c.z)), maxZ: Math.max(...corners.map((c) => c.z)),
    };
  });
  for (let i = 0; i < slots.length; i++) {
    for (let j = i + 1; j < slots.length; j++) {
      const a = aabbs[i], b = aabbs[j];
      const overlapsX = a.minX <= b.maxX && a.maxX >= b.minX;
      const overlapsZ = a.minZ <= b.maxZ && a.maxZ >= b.minZ;
      assert.ok(!(overlapsX && overlapsZ), `slot ${i} (wall ${slots[i].wall}) overlaps slot ${j} (wall ${slots[j].wall})`);
    }
  }
});

test("DESKS-AGAINST-WALLS: no persona slot lands nearer than 1.0u to the room's real corner, or inside the door's own clear aisle (+1.5u)", () => {
  for (const slot of personaSlots()) {
    for (const corner of tableCorners(slot)) {
      // Whichever coordinate is on the wall's own tangent axis must clear
      // both the door aisle (near 0) and the room corner (near +-7.5).
      const lateralCoord = slot.wall % 2 === 0 ? corner.z : corner.x;
      assert.ok(Math.abs(lateralCoord) >= HUB_DOOR_HALF_WIDTH + 1.5 - 1e-6, `wall ${slot.wall} corner lateral ${lateralCoord.toFixed(3)} inside the door's own +1.5u aisle`);
      assert.ok(Math.abs(lateralCoord) <= HUB_WALL_RADIUS - 1.0 + 1e-6, `wall ${slot.wall} corner lateral ${lateralCoord.toFixed(3)} closer than 1.0u to the room corner`);
    }
  }
});

test("DESKS-AGAINST-WALLS: no persona slot falls on the brain wall's own reserved high corner or the neighboring wall's low corner (BrainCore/meeting-table/Gamma-desk/cables/monitor-stand keep-out)", () => {
  const slots = personaSlots();
  assert.equal(slots.filter((s) => s.wall === 0 && s.lateralSign === -1).length, 0, "brainWall(0) high-corner slot must be dropped");
  assert.equal(slots.filter((s) => s.wall === 1 && s.lateralSign === 1).length, 0, "highCornerWall(1) low-corner slot must be dropped");
});

// ─── Bay desk clearance (DESK-ROWS pass, audit desk_clearance FAIL fix) ───
// SetKit.tsx: BAY_DESK_OFFSET_Z_BAY=0.15 (bay-only desk offset, replacing
// the shared BAY_DESK_OFFSET_Z=0.8 for StationModule.tsx's 8 real bays --
// see that constant's own header for the full derivation, reproduced here).
const BAY_HALF_EXTENT = 2.7; // lib/hq-scene-audit.ts's own literal (BAY_HALF_DEPTH, SetKit.tsx)
const WALL_THICKNESS = 0.3; // lib/hq-scene-audit.ts's own literal
const BAY_DESK_OFFSET_Z_BAY = 0.15;
const BAY_INNER_WALL_FACE = BAY_HALF_EXTENT - WALL_THICKNESS / 2;

test("DESK-ROWS: bay desk table back edge clears >=1.0u from its own bay wall (audit desk_clearance)", () => {
  const tableLocalZOffset = BAY_DESK_OFFSET_Z_BAY + 0.3 * FURNITURE_SCALE;
  const backEdge = tableLocalZOffset + TABLE_HALF_Z;
  const clearance = BAY_INNER_WALL_FACE - backEdge;
  assert.ok(clearance >= 1.0, `bay desk back-edge clearance ${clearance} < 1.0u`);
});

test("DESK-ROWS: bay desk chair keeps >=1.2u clearance from the door-side (near) wall", () => {
  const DESK_SEAT_LOCAL_Z = -0.35 * FURNITURE_SCALE; // SetKit.tsx#DESK_SEAT_LOCAL
  const chairZ = BAY_DESK_OFFSET_Z_BAY + DESK_SEAT_LOCAL_Z;
  const clearance = chairZ - -BAY_INNER_WALL_FACE;
  assert.ok(clearance >= 1.2, `bay desk chair-to-door-wall clearance ${clearance} < 1.2u`);
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
