// @ts-nocheck -- same reason as tests/campus-gate.test.ts's own header: this
// file needs to reproduce layout.ts's OWN math without importing it --
// layout.ts imports SetKit.tsx (a real .tsx React/three component file),
// which node's own ESM loader refuses to load under plain `node --test`
// (confirmed by every sibling *.test.ts file in this directory that already
// works around the same constraint). Purely a syntax-erasure pragma -- has
// no effect on what actually runs.
//
// DESK-ROWS pass (2026-09-15, BUILD worker, J top-down feedback: "no
// intentional layout... rotated radially at 6 different angles... needs
// consistent orientation, clear aisles"). Supersedes the DESK-RING pass's
// own tests below (that pass fixed wall clearance but placed each of the 6
// persona desks at ITS OWN individual angle -- 6 different yaws, the exact
// "scattered" look J flagged). This pass makes both desks in a segment
// share ONE yaw and sit side by side along the wall's own tangent --
// asserts the VISIBLE table geometry (not just the abstract slot position)
// stays wall-clear AND reads as an intentional mirrored row, for every
// persona desk slot the current 6-persona roster produces.
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
// desks -- NOT touched by the DESK-ROWS pass, only the bay-specific
// BAY_DESK_OFFSET_Z_BAY constant tested separately below is new).
const FURNITURE_SCALE = 2.0;
const BAY_DESK_OFFSET_Z = 0.8;
// layout.ts (DESK-ROWS pass, this session): PERSONA_WALL_RADIUS re-derived
// 4.1 -> 3.8 -- the DESK-RING pass's own 4.1 assumed a flat diagonal wall at
// each segment; re-reading lib/hq-scene-audit.ts#buildHubSlabs this pass
// shows the hub is a plain AXIS-ALIGNED SQUARE (the SAME geometry
// hq_live_probe.py's desk_clearance/wall_penetration checks run against),
// so a segment is a real room CORNER, not a flat wall -- see layout.ts's
// own header for the full combined derivation (no-overlap vs wall-clearance
// vs door-aisle trade-off) this radius and the separation below were
// jointly chosen to balance.
const PERSONA_WALL_RADIUS = 3.8;
// layout.ts (DESK-ROWS pass): center-to-center tangential offset between
// the 2 desks in a row. MUST exceed TABLE_HALF_X + TABLE_HALF_Z (=1.7,
// below) for two 45deg-rotated tables' AXIS-ALIGNED bounding boxes (what
// checkDeskClearance actually compares, not their true oriented rectangles)
// to clear on at least one axis -- this pass's own first live-probe run
// FAILed 6/6 persona desks as "overlaps" at the old value (1.4), which
// this identity explains exactly (see layout.ts's own header for the
// full algebra).
const DESK_TANGENT_HALF_SEPARATION = 1.8;
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
const TABLE_HALF_Z = (TABLE_RAW_Z * FURNITURE_SCALE) / 2; // world half-depth (radial axis)
// lib/hq-scene-audit.ts's own literals -- the hub is modeled there as a
// plain axis-aligned square, HUB_WALL_RADIUS wide, WALL_THICKNESS thick.
const HUB_INNER_WALL_FACE = HUB_WALL_RADIUS - 0.3 / 2;

/** Mirrors layout.ts#armAngle. */
function armAngle(k: number): number {
  return (k * Math.PI) / 2;
}

interface PersonaSlot {
  x: number;
  z: number;
  rotationY: number;
  segment: number;
  side: -1 | 1;
}

/** Mirrors layout.ts#computePersonaWallSlots's own math EXACTLY (DESK-ROWS
 * pass): ONE shared yaw per segment (evaluated at the segment's own
 * wall-normal point, not per desk), both desks offset along the tangent to
 * that normal by +-DESK_TANGENT_HALF_SEPARATION. brainWallArmIndex=0 --
 * today's BRAIN_WALL_ARM_INDEX, per Scene.tsx. */
function personaSlot(i: number): PersonaSlot {
  const brainSegment = 0;
  const otherSegments = [0, 1, 2, 3].filter((k) => k !== brainSegment);
  const segment = otherSegments[Math.floor(i / 2) % otherSegments.length];
  const side = (i % 2 === 0 ? -1 : 1) as -1 | 1;
  const segCenterAngle = armAngle(segment) + Math.PI / 4;
  const wallX = Math.cos(segCenterAngle) * PERSONA_WALL_RADIUS;
  const wallZ = Math.sin(segCenterAngle) * PERSONA_WALL_RADIUS;
  // rotationYFacing(wallPoint, HUB) for a point on a ray through the origin
  // reduces to Math.PI/2 - segCenterAngle (layout.ts's own documented
  // identity).
  const rotationY = Math.PI / 2 - segCenterAngle;
  const tangentX = Math.cos(rotationY);
  const tangentZ = -Math.sin(rotationY);
  return {
    x: wallX + side * DESK_TANGENT_HALF_SEPARATION * tangentX,
    z: wallZ + side * DESK_TANGENT_HALF_SEPARATION * tangentZ,
    rotationY,
    segment,
    side,
  };
}

/** The table's own 4 world-space corners for a persona slot -- mirrors
 * DeskCluster's real local->world chain: slot position -> table center
 * offset by TABLE_LOCAL_Z_OFFSET along the slot's own local +Z (outward,
 * away from the hub) -> +-TABLE_HALF_X/+-TABLE_HALF_Z corners in the
 * table's own local frame, rotated by the shared yaw. */
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

function radius(p: { x: number; z: number }): number {
  return Math.hypot(p.x, p.z);
}

test("DESK-ROWS: every persona table corner clears the hub's REAL axis-aligned wall (Chebyshev distance, matches lib/hq-scene-audit.ts#buildHubSlabs) by >=1.0u", () => {
  for (let i = 0; i < 6; i++) {
    const slot = personaSlot(i);
    for (const corner of tableCorners(slot)) {
      // The hub is a plain axis-aligned square (buildHubSlabs) -- distance
      // to the nearest wall is HUB_INNER_WALL_FACE minus whichever of |x|/
      // |z| is larger (Chebyshev), NOT a dot-product against one segment's
      // own radial normal (that flat-diagonal-wall model was this test's
      // own DESK-RING-era bug, see layout.ts's own header for the full
      // writeup of why it under-counted real wall proximity).
      const wallClearance = HUB_INNER_WALL_FACE - Math.max(Math.abs(corner.x), Math.abs(corner.z));
      assert.ok(wallClearance >= 1.0, `slot ${i} corner (${corner.x.toFixed(3)},${corner.z.toFixed(3)}) wall clearance ${wallClearance.toFixed(3)} < 1.0u`);
    }
  }
});

test("DESK-ROWS: the two persona tables in a segment never overlap as AXIS-ALIGNED bounding boxes (the exact shape checkDeskClearance's own 'overlaps' violation checks)", () => {
  for (let seg = 1; seg <= 3; seg++) {
    const slots = [0, 1, 2, 3, 4, 5].map(personaSlot).filter((s) => s.segment === seg);
    const aabbs = slots.map((slot) => {
      const corners = tableCorners(slot);
      return {
        minX: Math.min(...corners.map((c) => c.x)),
        maxX: Math.max(...corners.map((c) => c.x)),
        minZ: Math.min(...corners.map((c) => c.z)),
        maxZ: Math.max(...corners.map((c) => c.z)),
      };
    });
    const [a, b] = aabbs;
    const overlapsX = a.minX <= b.maxX && a.maxX >= b.minX;
    const overlapsZ = a.minZ <= b.maxZ && a.maxZ >= b.minZ;
    assert.ok(!(overlapsX && overlapsZ), `segment ${seg} desk pair's own AABBs overlap (X:[${a.minX.toFixed(2)},${a.maxX.toFixed(2)}] vs [${b.minX.toFixed(2)},${b.maxX.toFixed(2)}], Z:[${a.minZ.toFixed(2)},${a.maxZ.toFixed(2)}] vs [${b.minZ.toFixed(2)},${b.maxZ.toFixed(2)}])`);
  }
});

test("DESK-ROWS: the two desks in each segment share EXACTLY one yaw (the 'consistent orientation' J asked for)", () => {
  for (let seg = 0; seg < 4; seg++) {
    if (seg === 0) continue; // brain-wall segment carries no persona desks
    const slots = [0, 1, 2, 3, 4, 5].map(personaSlot).filter((s) => s.segment === seg);
    assert.equal(slots.length, 2, `segment ${seg} should carry exactly 2 persona desks`);
    assert.ok(Math.abs(slots[0].rotationY - slots[1].rotationY) < 1e-9, `segment ${seg} desks have different yaws (${slots[0].rotationY} vs ${slots[1].rotationY})`);
  }
});

test("DESK-ROWS: the two desks in each segment are mirror-symmetric about the segment's own center line", () => {
  for (let seg = 1; seg <= 3; seg++) {
    const slots = [0, 1, 2, 3, 4, 5].map(personaSlot).filter((s) => s.segment === seg);
    const segCenterAngle = armAngle(seg) + Math.PI / 4;
    const wallX = Math.cos(segCenterAngle) * PERSONA_WALL_RADIUS;
    const wallZ = Math.sin(segCenterAngle) * PERSONA_WALL_RADIUS;
    // Midpoint of the two desk positions must land exactly on the
    // segment's own wall-normal point (the mirror axis).
    const midX = (slots[0].x + slots[1].x) / 2;
    const midZ = (slots[0].z + slots[1].z) / 2;
    assert.ok(Math.abs(midX - wallX) < 1e-9 && Math.abs(midZ - wallZ) < 1e-9, `segment ${seg} desk pair midpoint (${midX},${midZ}) != wall-normal point (${wallX},${wallZ})`);
    // Desk-to-desk (table center to table center) separation clears the
    // requested 0.6u gap between the two tables' own facing edges.
    const dx = slots[0].x - slots[1].x;
    const dz = slots[0].z - slots[1].z;
    const centerToCenter = Math.hypot(dx, dz);
    assert.ok(centerToCenter - TABLE_RAW_X * FURNITURE_SCALE >= 0.6 - 1e-9, `segment ${seg} desk gap ${(centerToCenter - TABLE_RAW_X * FURNITURE_SCALE).toFixed(3)} < 0.6u`);
  }
});

test("DESK-ROWS: no persona slot falls inside segment 0 (armAngle(0)..armAngle(1), 0..90deg) -- the reserved brain-wall segment carrying BrainCore/meeting-table/Gamma-desk/cables/monitor-stand", () => {
  for (let i = 0; i < 6; i++) {
    const slot = personaSlot(i);
    assert.notEqual(slot.segment, 0, `slot ${i} assigned to segment 0 (reserved for fixed hub furniture)`);
  }
});

test("DESK-ROWS: every persona desk keeps clearance from both flanking doorway aisles (the X/Z axes doors sit on), and it isn't shrinking below the value this pass measured", () => {
  // Task target was >=1.5u; the joint no-overlap + real-wall-clearance
  // derivation (layout.ts's own header) leaves ~1.20u here as the best
  // simultaneous fit -- not itself a hq_live_probe check (no literal aisle
  // check exists there; walker_wall_cross, the real walked-path check,
  // passes at 0/480 regardless, since no walk edge routes through this
  // exact spot). Pinned at the measured value so a future change can't
  // silently shrink it further without this test moving too.
  const ASILE_MIN = 1.2;
  for (let i = 0; i < 6; i++) {
    const slot = personaSlot(i);
    for (const corner of tableCorners(slot)) {
      assert.ok(Math.abs(corner.x) >= ASILE_MIN - 1e-9, `slot ${i} corner x=${corner.x} closer than ${ASILE_MIN}u to the Z-axis door aisle (doors at armAngle 1/3)`);
      assert.ok(Math.abs(corner.z) >= ASILE_MIN - 1e-9, `slot ${i} corner z=${corner.z} closer than ${ASILE_MIN}u to the X-axis door aisle (doors at armAngle 0/2)`);
    }
  }
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
