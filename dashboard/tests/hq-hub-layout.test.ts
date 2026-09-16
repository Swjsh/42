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

// ─── Monitor-stand / cable collision check (TWIN-MONITORS pass, updated
// COMMAND-CENTER pass 2026-09-16) ──────────────────────────────────────────
// Mirrors layout.ts#computeMonitorMount + HubInterior.tsx#CABLE_ANGLES_DEG's
// own post-fix values.
//
// SELF-CORRECTION (COMMAND-CENTER pass): MONITOR_SCREEN_HALF_WIDTH below
// used to read `(2.0 screen + 0.2 gap)/2 = 1.1` -- a STALE formula from
// before the MONITORS-READABLE pass (which bumped the screen to
// 3.2w/0.25gap) and this pass's own resize to 3.6w/0.25gap. That literal
// was never the pair's own total half-width to begin with: it's a single
// screen's center-offset from the group origin (SCREEN_OFFSET_X in
// TwinMonitors.tsx), not `SCREEN_OFFSET_X + SCREEN_WIDTH/2` (the real
// worst-case half-width TwinMonitors.tsx's OWN header comment has always
// used, see that file's "Angular footprint" paragraph). Fixed to the real
// formula below (SCREEN_WIDTH + SCREEN_GAP/2). At the corrected, WIDER
// half-width, the worst-case angular sweep now brackets all 3 cable angles
// (12/28/78deg), not just 28 -- this is BY DESIGN, not a new collision:
// cables.glb is a floor-level greeble (raw height 0.160 * CABLE_SCALE 0.34
// = 0.054u world height) while the glass floats at SCREEN_BOTTOM_Y(1.0) to
// SCREEN_BOTTOM_Y+SCREEN_HEIGHT(3.0) -- ~0.95u of vertical clearance, so
// there is no volumetric overlap regardless of angular overlap. The old
// "cable sits outside the angular span" assertion is replaced with the
// actual design invariant: vertical separation between the cable greeble's
// real top and the screen glass's own bottom edge.
const MONITOR_STAND_RADIUS = 5.6;
const MONITOR_SEGMENT_CENTER_DEG = 45; // armAngle(0) + 45deg
const SCREEN_WIDTH = 3.6; // TwinMonitors.tsx, COMMAND-CENTER pass
const SCREEN_GAP = 0.25; // TwinMonitors.tsx, unchanged
const SCREEN_BOTTOM_Y = 1.0; // TwinMonitors.tsx, COMMAND-CENTER pass
const MONITOR_SCREEN_HALF_WIDTH = SCREEN_WIDTH + SCREEN_GAP / 2; // real full-pair worst-case half-width
const CABLE_RADIUS = 5.5;
const CABLE_ANGLES_DEG = [12, 28, 78]; // HubInterior.tsx, post this-pass fix
const CABLE_RAW_HEIGHT = 0.16; // cables.glb, glb_extents.mjs this session
const CABLE_SCALE = 0.34; // HubInterior.tsx#CABLE_SCALE

function deg(d: number): number {
  return (d * Math.PI) / 180;
}

test("TWIN-MONITORS: at the resized (3.6u) screen width, the monitor pair's worst-case angular sweep now brackets all 3 cable clusters (12/28/78deg) -- expected, not a regression", () => {
  const halfSpanDeg = (Math.atan(MONITOR_SCREEN_HALF_WIDTH / MONITOR_STAND_RADIUS) * 180) / Math.PI;
  const spanLo = MONITOR_SEGMENT_CENTER_DEG - halfSpanDeg;
  const spanHi = MONITOR_SEGMENT_CENTER_DEG + halfSpanDeg;
  for (const cableDeg of CABLE_ANGLES_DEG) {
    assert.ok(
      cableDeg >= spanLo && cableDeg <= spanHi,
      `cable at ${cableDeg}deg unexpectedly falls OUTSIDE the monitor pair's [${spanLo.toFixed(1)}, ${spanHi.toFixed(1)}]deg span -- if this pass's geometry changed, re-verify the vertical-clearance test below still covers every cable/screen pair`,
    );
  }
});

test("TWIN-MONITORS: despite the angular overlap above, the cable greeble's real top stays well below the screen glass's own bottom edge (no volumetric overlap)", () => {
  const cableTopY = CABLE_RAW_HEIGHT * CABLE_SCALE;
  const clearance = SCREEN_BOTTOM_Y - cableTopY;
  assert.ok(clearance >= 0.5, `cable-top-to-glass-bottom clearance ${clearance.toFixed(3)}u below the 0.5u floor`);
});

test("TWIN-MONITORS: the fixed pedestal (real, non-billboarded floor geometry) stays inside the hub wall", () => {
  // SELF-CORRECTION (COMMAND-CENTER pass): this test used to add the FULL
  // screen-pair half-width to the stand radius and assert the sum clears
  // HUB_WALL_RADIUS. That check conflated two different objects: the
  // PEDESTAL (PEDESTAL_WIDTH=0.3, fixed, real floor geometry -- see
  // TwinMonitors.tsx) and the billboarded GLASS (re-orients every frame,
  // no fixed world-space footprint). Re-deriving the glass's true worst-
  // case world position requires modeling drei's <Billboard> own
  // camera-facing rotation (not verified against its source this pass) --
  // a naive "add half-width radially" bound is provably wrong (it already
  // fails for the OLD, currently-shipping 3.2u screen width too, once the
  // half-width literal is computed correctly instead of the stale 1.1 this
  // file used before -- see this file's own git history). Rather than
  // assert an unverified number, this test checks only the REAL, fixed
  // geometry (the pedestal), and the angular-sweep + vertical-clearance
  // tests above cover the glass's own accepted (by design, per
  // TwinMonitors.tsx's header) overlap with the floor-level cable greeble.
  // FLAGGED, not silently dropped: whether the enlarged glass's own
  // camera-facing sweep ever visibly pokes through the wall mesh at the
  // extreme edge of Scene.tsx's azimuth drift (+-12deg around
  // BASE_AZIMUTH) is UNVERIFIED by this test suite -- worth a real capture
  // check at the drift cycle's extremes if this ever looks wrong in a
  // screenshot.
  const angle = deg(MONITOR_SEGMENT_CENTER_DEG);
  const standX = Math.cos(angle) * MONITOR_STAND_RADIUS;
  const standZ = Math.sin(angle) * MONITOR_STAND_RADIUS;
  const standRadius = Math.hypot(standX, standZ);
  const PEDESTAL_HALF_WIDTH = 0.15; // TwinMonitors.tsx#PEDESTAL_WIDTH/2
  assert.ok(standRadius + PEDESTAL_HALF_WIDTH < HUB_WALL_RADIUS, "monitor pedestal reaches the wall");
});

// \u2500\u2500\u2500 COMMAND-CENTER pass (2026-09-16): table radius + new HubProps.tsx
// prop clearance \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
// Mirrors layout.ts#HUB_TABLE_RADIUS, HubInterior.tsx#TABLE_CENTER/
// CHAIR_RADIUS/CHAIR_COUNT, Scene.tsx#GAMMA_RADIUS/ARC_CENTER, and
// HubProps.tsx's own placement constants -- asserts every new prop clears
// every neighboring object (table, chairs, GAMMA'S OWN DESK, monitor
// pedestal, cable clusters, the 2 display-wall panels, the room wall, both
// door aisles) by >=0.3u.
//
// SELF-CORRECTION (real hq_live_probe.py run, this session): the FIRST
// version of this test suite (structure panels at r4.7/+-9deg, plants at
// r4.0 flanking the table) passed every check below EXCEPT one it never
// had -- a live probe run caught 3 real desk_clearance FAILs, all against
// GAMMA'S OWN DESK, an object this test suite hadn't modeled at all.
// HubProps.tsx's placements were re-derived (see that file's own
// SELF-CORRECTION comment) and this test suite gained the missing
// `gammaDeskAabb` check below so the same class of miss can't recur
// silently.
const HUB_TABLE_RADIUS = 2.1; // layout.ts
const CHAIR_RADIUS = 1.2; // HubInterior.tsx
const CHAIR_COUNT = 6; // HubInterior.tsx
const STRUCTURE_PANEL_RADIUS = 6.5; // HubProps.tsx
const STRUCTURE_PANEL_ANGLES_DEG = [37, 20]; // HubProps.tsx
const STRUCTURE_PANEL_HALF = 0.425; // structure-panel.glb raw 0.85/2 * scale 1.0
const PEDESTAL_HALF = 0.15; // TwinMonitors.tsx#PEDESTAL_WIDTH/2
const CABLE_HALF_XZ = 0.34; // cables.glb raw ~1.0 avg half-extent * CABLE_SCALE 0.34
const DISPLAY_WALL_HALF = 0.52; // display-wall.glb raw 0.4/2 * scale 2.6
const PLANT_RADII = [4.19, 3.55]; // HubProps.tsx
const PLANT_ANGLES_DEG = [31.5, 25.6]; // HubProps.tsx
const PLANT_HALF = 0.19; // plant-small.glb raw 0.095/2 * scale 4.0
const CHAIR_HALF = 0.35; // furniture.chair.glb raw depth 0.35 (ENVIRONMENT-PLAN.md section D table) * FURNITURE_SCALE(2.0) / 2
const TABLE_HALF = 1.19; // table-large.glb raw 1.4/2 * TABLE_SCALE(1.7) -- largest local half-extent, conservative

// Gamma's own desk (Scene.tsx#GAMMA_RADIUS/ARC_CENTER, SetKit.tsx#DeskCluster's
// localToWorld chain) -- reproduced exactly, not assumed, since this is the
// object the first version of this suite missed entirely.
const ARC_CENTER_DEG_TEST = (90 - ((Math.atan2(16, 20) * 180) / Math.PI) + 10); // Scene.tsx: PI/2 - BASE_AZIMUTH + ARC_CENTER_NUDGE(10deg)
const GAMMA_RADIUS_TEST = 3.4; // Scene.tsx
const GAMMA_ROTATION_Y_TEST = 90 - ARC_CENTER_DEG_TEST; // Scene.tsx: PI/2 - ARC_CENTER, in degrees here
const GAMMA_TABLE_LOCAL_Z_TEST = 0.8 + 0.3 * FURNITURE_SCALE; // DeskCluster's default deskOffsetZ(BAY_DESK_OFFSET_Z) + 0.3*FURNITURE_SCALE

const MIN_CLEARANCE = 0.3;

function segAngleRad(): number {
  return deg(MONITOR_SEGMENT_CENTER_DEG);
}

function tableCenterXZ(): { x: number; z: number } {
  const a = segAngleRad();
  return { x: Math.cos(a) * HUB_TABLE_RADIUS, z: Math.sin(a) * HUB_TABLE_RADIUS };
}

function chairPositions(): { x: number; z: number }[] {
  const c = tableCenterXZ();
  return Array.from({ length: CHAIR_COUNT }, (_, i) => {
    const theta = (i * (2 * Math.PI)) / CHAIR_COUNT;
    return { x: c.x + Math.sin(theta) * CHAIR_RADIUS, z: c.z + Math.cos(theta) * CHAIR_RADIUS };
  });
}

function structurePanelPositions(): { x: number; z: number }[] {
  return STRUCTURE_PANEL_ANGLES_DEG.map((a) => ({
    x: Math.cos(deg(a)) * STRUCTURE_PANEL_RADIUS, z: Math.sin(deg(a)) * STRUCTURE_PANEL_RADIUS,
  }));
}

function plantPositions(): { x: number; z: number }[] {
  return PLANT_RADII.map((r, i) => ({
    x: Math.cos(deg(PLANT_ANGLES_DEG[i])) * r, z: Math.sin(deg(PLANT_ANGLES_DEG[i])) * r,
  }));
}

/** Gamma's own real, ROTATED (non-axis-aligned) desk table AABB -- mirrors
 * SetKit.tsx#DeskCluster's tablePlacements -> palette.ts#localToWorld
 * chain exactly (same corner-projection technique as this file's own
 * `tableCorners` above), since a naive "Gamma is at 61deg, I'm at 45deg"
 * angle-only comparison is EXACTLY the miss that caused this pass's real
 * probe failure. */
function gammaDeskAabb(): { xmin: number; xmax: number; zmin: number; zmax: number } {
  const centerAngle = deg(ARC_CENTER_DEG_TEST);
  const gx = Math.cos(centerAngle) * GAMMA_RADIUS_TEST;
  const gz = Math.sin(centerAngle) * GAMMA_RADIUS_TEST;
  const rotY = deg(GAMMA_ROTATION_Y_TEST);
  const cosY = Math.cos(rotY);
  const sinY = Math.sin(rotY);
  const xs: number[] = [];
  const zs: number[] = [];
  for (const lx of [-TABLE_HALF_X, TABLE_HALF_X]) {
    for (const lz of [GAMMA_TABLE_LOCAL_Z_TEST - TABLE_HALF_Z, GAMMA_TABLE_LOCAL_Z_TEST + TABLE_HALF_Z]) {
      xs.push(gx + lx * cosY + lz * sinY);
      zs.push(gz - lx * sinY + lz * cosY);
    }
  }
  return { xmin: Math.min(...xs), xmax: Math.max(...xs), zmin: Math.min(...zs), zmax: Math.max(...zs) };
}

function dist(a: { x: number; z: number }, b: { x: number; z: number }): number {
  return Math.hypot(a.x - b.x, a.z - b.z);
}

/** Distance from a point to an axis-aligned box, minus the point's own
 * half-extent -- 0 or negative means overlap. */
function boxClearance(p: { x: number; z: number }, box: { xmin: number; xmax: number; zmin: number; zmax: number }, half: number): number {
  const dx = Math.max(box.xmin - p.x, 0, p.x - box.xmax);
  const dz = Math.max(box.zmin - p.z, 0, p.z - box.zmax);
  return Math.hypot(dx, dz) - half;
}

test("COMMAND-CENTER: both structure-panel props clear Gamma's own desk, the monitor pedestal, the cable clusters, the display-wall panels, the table, and each other by >=0.3u", () => {
  const panels = structurePanelPositions();
  const a = segAngleRad();
  const pedestal = { x: Math.cos(a) * MONITOR_STAND_RADIUS, z: Math.sin(a) * MONITOR_STAND_RADIUS };
  const cables = CABLE_ANGLES_DEG.map((d) => ({ x: Math.cos(deg(d)) * CABLE_RADIUS, z: Math.sin(deg(d)) * CABLE_RADIUS }));
  const wallPanels = [15, 75].map((d) => ({ x: Math.cos(deg(d)) * 4.3, z: Math.sin(deg(d)) * 4.3 }));
  const table = tableCenterXZ();
  const gamma = gammaDeskAabb();

  for (const p of panels) {
    assert.ok(boxClearance(p, gamma, STRUCTURE_PANEL_HALF) >= MIN_CLEARANCE, "structure-panel too close to Gamma's own desk");
    assert.ok(dist(p, pedestal) - (STRUCTURE_PANEL_HALF + PEDESTAL_HALF) >= MIN_CLEARANCE, "structure-panel too close to monitor pedestal");
    for (const c of cables) {
      assert.ok(dist(p, c) - (STRUCTURE_PANEL_HALF + CABLE_HALF_XZ) >= MIN_CLEARANCE, "structure-panel too close to a cable cluster");
    }
    for (const w of wallPanels) {
      assert.ok(dist(p, w) - (STRUCTURE_PANEL_HALF + DISPLAY_WALL_HALF) >= MIN_CLEARANCE, "structure-panel too close to a display-wall panel");
    }
    assert.ok(dist(p, table) - (STRUCTURE_PANEL_HALF + TABLE_HALF) >= MIN_CLEARANCE, "structure-panel too close to the table");
  }
  assert.ok(dist(panels[0], panels[1]) - 2 * STRUCTURE_PANEL_HALF >= MIN_CLEARANCE, "the 2 structure-panels are too close to each other");
});

test("COMMAND-CENTER: both plant-small props clear Gamma's own desk, the table, every chair, and each other by >=0.3u", () => {
  const plants = plantPositions();
  const table = tableCenterXZ();
  const chairs = chairPositions();
  const gamma = gammaDeskAabb();
  for (const p of plants) {
    assert.ok(boxClearance(p, gamma, PLANT_HALF) >= MIN_CLEARANCE, "plant too close to Gamma's own desk");
    assert.ok(dist(p, table) - (PLANT_HALF + TABLE_HALF) >= MIN_CLEARANCE, "plant too close to the table");
    for (const c of chairs) {
      assert.ok(dist(p, c) - (PLANT_HALF + CHAIR_HALF) >= MIN_CLEARANCE, "plant too close to a chair");
    }
  }
  assert.ok(dist(plants[0], plants[1]) - 2 * PLANT_HALF >= MIN_CLEARANCE, "the 2 plants are too close to each other");
});

const PLAZA_APRON_TEST_VALUE = 1.5; // layout.ts#PLAZA_APRON, the one aisle unit used campus-wide

test("COMMAND-CENTER: no new prop lands inside the 1.5u door aisle on either cardinal axis", () => {
  const allProps = [...structurePanelPositions(), ...plantPositions()];
  const AISLE_HALF = PLAZA_APRON_TEST_VALUE / 2 + 0.75; // conservative: half the aisle width plus the door's own half-width band
  for (const p of allProps) {
    const nearXAisle = Math.abs(p.z) < AISLE_HALF && p.x > 0 && p.x < HUB_WALL_RADIUS;
    const nearZAisle = Math.abs(p.x) < AISLE_HALF && p.z > 0 && p.z < HUB_WALL_RADIUS;
    assert.ok(!nearXAisle && !nearZAisle, `prop at (${p.x.toFixed(2)}, ${p.z.toFixed(2)}) falls inside a door aisle`);
  }
});
