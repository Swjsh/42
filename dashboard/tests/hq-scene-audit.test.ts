// @ts-nocheck -- same reason as tests/hq-walk-routing.test.ts's own header:
// plain `node --test` needs the explicit ".ts" extension on the relative
// import below (this repo's tsconfig moduleResolution is "bundler", no
// allowImportingTsExtensions), which tsc itself would otherwise flag. Pure
// syntax-erasure pragma, no runtime effect.
//
// SCENE-AUDIT pass (2026-09-15): unit coverage for dashboard/lib/
// hq-scene-audit.ts's pure geometry -- wall-slab construction with door
// gaps, AABB-vs-slab penetration, segment-vs-slab crossing (outside a
// door), and screen-facing cosines. Two tests are REGRESSION PINS against
// real bugs J watched happen and this project already fixed:
//   1. wall_penetration must FAIL a desk at the OLD PERSONA_WALL_RADIUS=6.5
//      (commit 7700c4bd moved it to 4.1, table-center radius 5.5) and PASS
//      at today's radius.
//   2. walker_wall_cross must FAIL the OLD "alert pace toward hub center"
//      formula (commit d3da0581's own fix target: paceDist =
//      min(3.4, homeToHubDist*0.4) straight toward HUB=[0,0,0]) for a bay
//      agent, and PASS the NEW formula (home -> the bay's own doorWorldPos).
//
// Run: cd dashboard && node --test tests/hq-scene-audit.test.ts
// (or the full suite: cd dashboard && npm test)

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildRoomWallSlabs,
  buildHubSlabs,
  buildBaySlabs,
  aabbsOverlap,
  aabbPenetrationDepth,
  aabbDistance,
  segmentIntersectsAabbXZ,
  screenFacingCosine,
  checkWallPenetration,
  checkWalkerWallCross,
  checkScreenFacing,
  checkDeskClearance,
  checkDeskOrientation,
  nearestHubWallYaw,
  rectOverlapFractionOfScreen,
  checkLabelScreenOverlap,
  type AABB,
  type WallSlab,
  type ScreenViewportRect,
  type ViewportLabelRect,
} from "../lib/hq-scene-audit.ts";

// ─── buildRoomWallSlabs: door-gap construction ─────────────────────────────

test("buildRoomWallSlabs: a hub-shaped room (rotationY=0) produces 4 walls x 2 segments (door gap cut from each)", () => {
  const slabs = buildHubSlabs();
  assert.equal(slabs.length, 8, "4 walls, each split into 2 segments by its own door gap");
  // Every slab is a THIN box (one axis' extent equals the wall thickness).
  for (const s of slabs) {
    const dx = s.aabb.max[0] - s.aabb.min[0];
    const dz = s.aabb.max[2] - s.aabb.min[2];
    assert.ok(Math.min(dx, dz) <= 0.3 + 1e-6, `slab ${s.id} is not thin: dx=${dx} dz=${dz}`);
  }
  // The +x wall's door gap (centered on z=0) must NOT be covered by either
  // of its own two segments -- a point at [7.5, 0, 0] is the doorway itself.
  const plusXSlabs = slabs.filter((s) => s.id.includes("wall-+x"));
  assert.equal(plusXSlabs.length, 2);
  for (const s of plusXSlabs) {
    const coversDoorCenter = s.aabb.min[2] <= 0 && s.aabb.max[2] >= 0;
    assert.ok(!coversDoorCenter, `${s.id} should not cover the doorway center (z=0)`);
  }
});

test("buildRoomWallSlabs: no door produces exactly 1 (uncut) slab per wall", () => {
  const slabs = buildRoomWallSlabs({
    id: "solid", center: [0, 0], rotationY: 0,
    halfExtentLocalX: 5, halfExtentLocalZ: 5, thickness: 0.2, height: 3, doors: [],
  });
  assert.equal(slabs.length, 4);
});

test("buildRoomWallSlabs: a 90deg-rotated room's wall AABBs sit on the SWAPPED world axis", () => {
  // rotationY = PI/2 swaps local x/z onto world z/-x (three.js Y-rotation
  // convention) -- a room's local +x wall becomes a world -z-ish wall.
  const slabs = buildRoomWallSlabs({
    id: "rot", center: [10, 0], rotationY: Math.PI / 2,
    halfExtentLocalX: 2, halfExtentLocalZ: 2, thickness: 0.2, height: 2, doors: [],
  });
  assert.equal(slabs.length, 4);
  // Every wall must still be centered near world x=10 (the room's own
  // center), never drifted to some unrelated location.
  for (const s of slabs) {
    const cx = (s.aabb.min[0] + s.aabb.max[0]) / 2;
    assert.ok(Math.abs(cx - 10) <= 2.2, `slab ${s.id} drifted off the room's own center: cx=${cx}`);
  }
});

// ─── AABB primitives ────────────────────────────────────────────────────

test("aabbsOverlap / aabbPenetrationDepth: disjoint boxes", () => {
  const a: AABB = { min: [0, 0, 0], max: [1, 1, 1] };
  const b: AABB = { min: [5, 0, 0], max: [6, 1, 1] };
  assert.equal(aabbsOverlap(a, b), false);
  assert.equal(aabbPenetrationDepth(a, b), 0);
});

test("aabbPenetrationDepth: reports the SHALLOWEST axis overlap", () => {
  const a: AABB = { min: [0, 0, 0], max: [2, 2, 2] };
  const b: AABB = { min: [1.9, -5, -5], max: [10, 5, 5] }; // overlaps x by 0.1, y/z fully
  assert.ok(Math.abs(aabbPenetrationDepth(a, b) - 0.1) < 1e-9);
});

test("aabbDistance: 0 when overlapping, positive gap otherwise", () => {
  const a: AABB = { min: [0, 0, 0], max: [1, 1, 1] };
  const b: AABB = { min: [3, 0, 0], max: [4, 1, 1] };
  assert.ok(Math.abs(aabbDistance(a, b) - 2) < 1e-9);
  assert.equal(aabbDistance(a, { min: [0.5, 0, 0], max: [1.5, 1, 1] }), 0);
});

// ─── segment-vs-slab (walker crossing a wall) ──────────────────────────────

test("segmentIntersectsAabbXZ: a straight line clean through a thin wall is detected even with both endpoints outside it", () => {
  const wall: AABB = { min: [-0.1, 0, -5], max: [0.1, 3, 5] }; // thin wall along x=0
  const crossing = segmentIntersectsAabbXZ([-2, 0], [2, 0], wall);
  assert.equal(crossing, true, "a segment straddling the thin wall must register as crossing it");
  const parallel = segmentIntersectsAabbXZ([-2, 10], [2, 10], wall); // same x-span, well outside z-range
  assert.equal(parallel, false);
});

test("segmentIntersectsAabbXZ: passing through a door gap (no slab there) never crosses", () => {
  const slabs = buildHubSlabs();
  // A path from inside the hub straight out through the +x doorway (z=0,
  // well within the door's own half-width) must not cross ANY hub slab.
  const p1: [number, number] = [5, 0];
  const p2: [number, number] = [9, 0];
  const anyCross = slabs.some((s) => segmentIntersectsAabbXZ(p1, p2, s.aabb));
  assert.equal(anyCross, false, "walking straight out the doorway must not register as a wall crossing");
});

// ─── screenFacingCosine ─────────────────────────────────────────────────

test("screenFacingCosine: 1.0 dead-on, ~0 edge-on, negative when facing away", () => {
  const screenPos: [number, number, number] = [0, 1, 0];
  const normal: [number, number, number] = [0, 0, 1]; // faces +z
  assert.ok(Math.abs(screenFacingCosine(normal, screenPos, [0, 1, 5]) - 1) < 1e-9, "viewer straight ahead of the face");
  assert.ok(Math.abs(screenFacingCosine(normal, screenPos, [5, 1, 0])) < 1e-9, "viewer directly to the side");
  assert.ok(screenFacingCosine(normal, screenPos, [0, 1, -5]) < -0.9, "viewer behind the screen (facing away)");
});

// ─── check_* verdict contracts ──────────────────────────────────────────

test("checkWallPenetration: NO-DATA with nothing to check, PASS when clear, FAIL when overlapping", () => {
  const slabs = buildHubSlabs();
  assert.equal(checkWallPenetration([], slabs).verdict, "NO-DATA");
  const clear = checkWallPenetration([{ id: "d1", label: "desk", aabb: { min: [-0.5, 0, -0.5], max: [0.5, 1, 0.5] } }], slabs);
  assert.equal(clear.verdict, "PASS");
  // z=[3,4] is well clear of the +x wall's own door gap (|z|<=1.575) --
  // this hits the REAL wall segment, not the doorway opening.
  const inWall = checkWallPenetration([{ id: "d2", label: "desk", aabb: { min: [7.3, 0, 3], max: [8.3, 1, 4] } }], slabs);
  assert.equal(inWall.verdict, "FAIL");
});

test("checkScreenFacing: FAILs only READABLE screens below the cos threshold; informational screens never gate it", () => {
  const camera = { position: [0, 1, 5] as [number, number, number] };
  const topDown = { position: [0, 60, 0] as [number, number, number] };
  const backwardsReadable = checkScreenFacing(
    [{ id: "s1", label: "twin-monitor", position: [0, 1, 0], normal: [0, 0, -1], readable: true }],
    camera, topDown,
  );
  assert.equal(backwardsReadable.verdict, "FAIL");
  const backwardsInformational = checkScreenFacing(
    [{ id: "s2", label: "desk-screen", position: [0, 1, 0], normal: [0, 0, -1], readable: false }],
    camera, topDown,
  );
  assert.equal(backwardsInformational.verdict, "PASS", "an informational-only screen must never fail the check");
});

test("checkDeskClearance: FAILs a desk closer than the minimum wall clearance", () => {
  const slabs = buildHubSlabs();
  const tooClose = checkDeskClearance(
    // z=[3,3.6] clears the +x wall's own door gap (|z|<=1.575) -- this is a
    // real wall segment, ~0.5u away, not the doorway opening.
    [{ id: "d1", label: "desk", aabb: { min: [6.8, 0, 3], max: [7.0, 1, 3.6] } }],
    slabs, [],
  );
  assert.equal(tooClose.verdict, "FAIL");
  const clear = checkDeskClearance(
    [{ id: "d2", label: "desk", aabb: { min: [-0.5, 0, -0.5], max: [0.5, 1, 0.5] } }], // near hub center, far from any wall
    slabs, [],
  );
  assert.equal(clear.verdict, "PASS");
});

test("checkDeskClearance: a chair pulled up to its OWN desk (AABBs touching) is normal furniture, never a FAIL; a desk overlapping ANOTHER desk still FAILs", () => {
  const desk: ObjectAabb = { id: "desk-1", label: "desk", aabb: { min: [0, 0, 0], max: [2, 1, 1] } };
  const chair: ObjectAabb = { id: "chair-1", label: "chair", aabb: { min: [1.5, 0, 0.8], max: [2.3, 1, 1.6] } }; // overlaps the desk's own AABB, as a real tucked-in chair does
  const ok = checkDeskClearance([desk], [], [desk, chair]);
  assert.equal(ok.verdict, "PASS", "a chair overlapping its own desk must never be flagged");

  const otherDesk: ObjectAabb = { id: "desk-2", label: "desk", aabb: { min: [1, 0, 0], max: [3, 1, 1] } };
  const collision = checkDeskClearance([desk], [], [desk, otherDesk]);
  assert.equal(collision.verdict, "FAIL", "two desks overlapping is a real placement bug, still caught");
});

test("checkDeskOrientation: FAILs a desk whose yaw is more than tolDeg off its own target", () => {
  const result = checkDeskOrientation([
    { id: "d1", actualYaw: 0, targetYaw: 0 },
    { id: "d2", actualYaw: (25 * Math.PI) / 180, targetYaw: 0 },
  ], 10);
  assert.equal(result.verdict, "FAIL");
  assert.equal((result.detail.violations as unknown[]).length, 1);
});

// ═══ DESKS-AGAINST-WALLS pass (2026-09-15) ══════════════════════════════
// nearestHubWallYaw is the INDEPENDENT (not layout.ts-derived) target this
// pass added specifically so checkDeskOrientation stops being tautological
// ("matches whatever layout.ts's own computePersonaWallSlots already
// claims for this slot"). A desk sitting on the room's old DIAGONAL (the
// DESK-RING/DESK-ROWS corner model, e.g. radius 3.8 at 45deg) computes a
// nearest-wall yaw 45deg off its own real placement angle and must FAIL;
// a desk on one of the new axis-aligned wall slots computes a nearest-wall
// yaw that matches its own real yaw exactly and must PASS.
test("nearestHubWallYaw + checkDeskOrientation: a 45deg-diagonal desk (the OLD corner model) FAILs against the independently-derived nearest-wall yaw", () => {
  const diagonalRadius = 3.8;
  const angle = Math.PI / 4; // 45deg -- the room's own corner, not a real wall
  const position: [number, number, number] = [Math.cos(angle) * diagonalRadius, 0, Math.sin(angle) * diagonalRadius];
  const actualYaw = Math.PI / 2 - angle; // the OLD computePersonaWallSlots's own formula for this point
  const targetYaw = nearestHubWallYaw(position);
  const result = checkDeskOrientation([{ id: "diagonal", actualYaw, targetYaw }], 10);
  assert.equal(result.verdict, "FAIL", "a diagonal desk must fail the independent wall-parallel check");
});

test("nearestHubWallYaw + checkDeskOrientation: an axis-aligned wall-backed desk (the NEW slot model) PASSes against the independently-derived nearest-wall yaw", () => {
  const wallRadius = 5.1;
  const lateralOffset = 4.6;
  // wall 0 (+X, armAngle=0), lateral side +1 -- layout.ts's own
  // computePersonaWallSlots formula, reproduced here (not imported, this
  // file's own no-SetKit.tsx-import constraint per its header).
  const wallAngle = 0;
  const wallNormalPoint: [number, number, number] = [Math.cos(wallAngle) * wallRadius, 0, Math.sin(wallAngle) * wallRadius];
  const rotationY = Math.PI / 2 - wallAngle;
  const tangentX = Math.cos(rotationY);
  const tangentZ = -Math.sin(rotationY);
  const position: [number, number, number] = [wallNormalPoint[0] + lateralOffset * tangentX, 0, wallNormalPoint[2] + lateralOffset * tangentZ];
  const targetYaw = nearestHubWallYaw(position);
  const result = checkDeskOrientation([{ id: "wall-desk", actualYaw: rotationY, targetYaw }], 10);
  assert.equal(result.verdict, "PASS", "an axis-aligned wall-backed desk must pass the independent wall-parallel check");
});

test("checkDeskClearance: back-wall band mode PASSes a desk 0.35u from its own wall but FAILs one flush inside it or floating 2u away", () => {
  const slabs = buildHubSlabs();
  const band = { min: 0.2, max: 0.6 };
  // +X wall inner face at 7.35 (HUB_HALF_EXTENT 7.5 - WALL_THICKNESS 0.3/2).
  // z=[3,3.6] clears the door gap (|z|<=1.575) -- a real wall segment, same
  // spot the existing "closer than min wall clearance" test above uses. A
  // desk whose back edge sits at x=7.0 clears 0.35u -- inside the band.
  const backed = checkDeskClearance(
    [{ id: "d1", label: "desk", aabb: { min: [6.4, 0, 3], max: [7.0, 1, 3.6] } }],
    slabs, [], 1.0, band,
  );
  assert.equal(backed.verdict, "PASS");
  const insideWall = checkDeskClearance(
    [{ id: "d2", label: "desk", aabb: { min: [7.2, 0, 3], max: [7.4, 1, 3.6] } }],
    slabs, [], 1.0, band,
  );
  assert.equal(insideWall.verdict, "FAIL", "closer than the band's own minimum must FAIL (reads as inside the wall)");
  const floating = checkDeskClearance(
    [{ id: "d3", label: "desk", aabb: { min: [4.0, 0, 3], max: [4.6, 1, 3.6] } }],
    slabs, [], 1.0, band,
  );
  assert.equal(floating.verdict, "FAIL", "further than the band's own maximum must FAIL (reads as floating, not backed against the wall)");
});

// ═══ REGRESSION PIN 1 ═══════════════════════════════════════════════════
// wall_penetration must FAIL the pre-7700c4bd desk placement and PASS
// today's. Table footprint (kenney-space-station-kit/table.glb, per
// layout.ts#PERSONA_WALL_RADIUS's own header): raw X=1.100/Z=0.600 at
// FURNITURE_SCALE=2 -> world 2.2w x 1.2d, table CENTER at
// PERSONA_WALL_RADIUS + 1.4 (DeskCluster's own outward offset, same header).

function personaDeskAabb(radius: number): AABB {
  const centerZ = radius + 1.4; // table center sits 1.4u further out than the seat radius
  // Real persona-wall slots sit at a segment CENTER (45deg off a doorway,
  // WALL_SEGMENT_SPREAD in layout.ts), never straddling a doorway's own
  // axis -- xOffset=3 keeps this synthetic desk clear of the +z wall's own
  // door gap (|x|<=1.575) so the test measures wall clipping, not a false
  // "clear" reading caused by accidentally aiming the desk through the door.
  const xOffset = 3;
  return { min: [xOffset - 1.1, 0, centerZ - 0.6], max: [xOffset + 1.1, 1, centerZ + 0.6] };
}

test("REGRESSION PIN (7700c4bd): wall_penetration FAILs at the OLD PERSONA_WALL_RADIUS=6.5, PASSes at today's 4.1", () => {
  const slabs = buildHubSlabs();
  const oldDesk = checkWallPenetration([{ id: "old", label: "desk", aabb: personaDeskAabb(6.5) }], slabs);
  assert.equal(oldDesk.verdict, "FAIL", "old radius 6.5 -> table back edge at 8.5u, well past HUB_HALF_EXTENT=7.5");
  const newDesk = checkWallPenetration([{ id: "new", label: "desk", aabb: personaDeskAabb(4.1) }], slabs);
  assert.equal(newDesk.verdict, "PASS", "today's radius 4.1 -> table back edge at 6.1u, 1.4u clear of the 7.5u wall");
});

// ═══ REGRESSION PIN 2 ═══════════════════════════════════════════════════
// walker_wall_cross must FAIL the pre-d3da0581 "alert pace toward hub
// center" formula for a bay agent, and PASS the fixed home->doorWorldPos
// route. Geometry reproduced verbatim from tests/hq-walk-routing.test.ts's
// own already-verified derivation chain (that file's own header explains
// why layout.ts/SetKit.tsx can't be imported directly under node --test).

const HUB_WALL_RADIUS_ = 7.5;
const T_JUNCTION_HALF_ = 0.9;
const MAIN_HALL_LEN_ = 9;
const SIDE_HALL_LEN_ = 4.5;
const BAY_HALF_DEPTH_ = 2.7;
const T_DIST_ = HUB_WALL_RADIUS_ + MAIN_HALL_LEN_ + T_JUNCTION_HALF_; // 17.4
const SIDE_SPAN_ = T_JUNCTION_HALF_ + SIDE_HALL_LEN_ + BAY_HALF_DEPTH_; // 8.1

function armAngle_(armIndex: number): number {
  return (armIndex * Math.PI) / 2;
}

function bay2Geometry() {
  const armIndex = 1; // bay index 2 -> armIndex 1, sideIndex 0 (matches hq-walk-routing.test.ts's own "Futures" bay)
  const mainAngle = armAngle_(armIndex);
  const tCenter: [number, number, number] = [Math.cos(mainAngle) * T_DIST_, 0, Math.sin(mainAngle) * T_DIST_];
  const perpAngle = mainAngle + Math.PI / 2;
  const pDirX = Math.cos(perpAngle);
  const pDirZ = Math.sin(perpAngle);
  const position: [number, number, number] = [tCenter[0] + pDirX * SIDE_SPAN_, 0, tCenter[2] + pDirZ * SIDE_SPAN_];
  const doorWorldPos: [number, number, number] = [position[0] - pDirX * BAY_HALF_DEPTH_, 0, position[2] - pDirZ * BAY_HALF_DEPTH_];
  const agentHome: [number, number, number] = [position[0] + pDirX * (BAY_HALF_DEPTH_ * 0.4), 0, position[2] + pDirZ * (BAY_HALF_DEPTH_ * 0.4)];
  // rotationY: local -Z (this kit's "front") points from `position` toward
  // `tCenter` -- same rotationYFacing formula layout.ts uses, reproduced
  // inline (atan2(selfX-targetX, selfZ-targetZ)).
  const rotationY = Math.atan2(position[0] - tCenter[0], position[2] - tCenter[2]);
  return { position, doorWorldPos, agentHome, rotationY };
}

test("REGRESSION PIN (d3da0581): walker_wall_cross FAILs the old toward-hub alert pace, PASSes the new home->door route", () => {
  const bay = bay2Geometry();
  const slabs = buildBaySlabs("bay-2", [bay.position[0], bay.position[2]], bay.rotationY);

  // OLD formula: pace toward HUB=[0,0,0] from home, capped at min(3.4, dist*0.4).
  const HUB: [number, number, number] = [0, 0, 0];
  const homeToHubDist = Math.hypot(HUB[0] - bay.agentHome[0], HUB[2] - bay.agentHome[2]);
  const paceDist = Math.min(3.4, homeToHubDist * 0.4);
  const dirX = (HUB[0] - bay.agentHome[0]) / homeToHubDist;
  const dirZ = (HUB[2] - bay.agentHome[2]) / homeToHubDist;
  const oldPacePoint: [number, number, number] = [bay.agentHome[0] + dirX * paceDist, 0, bay.agentHome[2] + dirZ * paceDist];

  const oldTrack = [{ id: "alert-agent-old", points: [{ t: 0, pos: [bay.agentHome[0], bay.agentHome[2]] as [number, number] }, { t: 1, pos: [oldPacePoint[0], oldPacePoint[2]] as [number, number] }] }];
  const oldResult = checkWalkerWallCross(oldTrack, slabs);
  assert.equal(oldResult.verdict, "FAIL", "the old toward-hub pace must be caught cutting through the bay's own side wall");

  // NEW formula: pace toward the bay's own doorWorldPos (the real door).
  const newTrack = [{ id: "alert-agent-new", points: [{ t: 0, pos: [bay.agentHome[0], bay.agentHome[2]] as [number, number] }, { t: 1, pos: [bay.doorWorldPos[0], bay.doorWorldPos[2]] as [number, number] }] }];
  const newResult = checkWalkerWallCross(newTrack, slabs);
  assert.equal(newResult.verdict, "PASS", "the fixed home->door route must stay clear of every wall slab");
});

// ─── SCREEN-KEEP-OUT pass (2026-09-15): checkLabelScreenOverlap ────────────
// FAIL/PASS pins for the missing "label-vs-screen-face overlap" sub-check
// check_label_legibility's own docstring named as a stated follow-up.

function screenRect(id: string, x: number, y: number, width: number, height: number, readable = true): ScreenViewportRect {
  return { id, label: "twin-monitor", readable, x, y, width, height };
}
function labelRect(x: number, y: number, width: number, height: number): ViewportLabelRect {
  return { x, y, width, height };
}

test("rectOverlapFractionOfScreen: half the screen covered reads as 0.5, no overlap reads as 0", () => {
  const screen = screenRect("s1", 0, 0, 100, 100);
  const halfCover = labelRect(0, 0, 100, 50); // covers exactly the top half
  assert.equal(rectOverlapFractionOfScreen(halfCover, screen), 0.5);
  const noCover = labelRect(200, 200, 50, 50);
  assert.equal(rectOverlapFractionOfScreen(noCover, screen), 0);
});

test("rectOverlapFractionOfScreen: fraction is of the SCREEN's area, not the label's (a huge label barely clipping a corner is a small fraction)", () => {
  const screen = screenRect("s1", 0, 0, 100, 100);
  const hugeLabelClippingCorner = labelRect(-1000, -1000, 1010, 1010); // covers only the [0,0]-[10,10] corner of the screen
  const frac = rectOverlapFractionOfScreen(hugeLabelClippingCorner, screen);
  assert.ok(frac > 0 && frac < 0.02, `expected a tiny fraction of the screen, got ${frac}`);
});

test("checkLabelScreenOverlap: FAIL -- a label covering >10% of a READABLE screen (real scenario: a head label drifting over TwinMonitors' glass)", () => {
  const screen = screenRect("twin-monitor-left", 800, 400, 300, 180);
  const gammaHeadLabel = labelRect(820, 410, 160, 70); // (160*70)/(300*180) ~= 21% of the screen, well over the 10% threshold
  const result = checkLabelScreenOverlap([gammaHeadLabel], [screen]);
  assert.equal(result.verdict, "FAIL");
  const violations = result.detail.violations as Array<{ screenId: string }>;
  assert.equal(violations.length, 1);
  assert.equal(violations[0].screenId, "twin-monitor-left");
});

test("checkLabelScreenOverlap: PASS -- every label sits clear of every readable screen", () => {
  const screen = screenRect("twin-monitor-left", 800, 400, 300, 180);
  const farLabel = labelRect(0, 0, 140, 30);
  const result = checkLabelScreenOverlap([farLabel], [screen]);
  assert.equal(result.verdict, "PASS");
  assert.equal((result.detail.violations as unknown[]).length, 0);
});

test("checkLabelScreenOverlap: an informational screen (readable:false) never gates the verdict even when fully covered", () => {
  const deskMonitor = screenRect("desk-screen-3", 100, 100, 50, 50, false);
  const coveringLabel = labelRect(100, 100, 50, 50);
  const result = checkLabelScreenOverlap([coveringLabel], [deskMonitor]);
  assert.equal(result.verdict, "PASS", "informational screens are reported, never a FAIL gate");
});

test("checkLabelScreenOverlap: a small overlap under the 10% threshold PASSes", () => {
  const screen = screenRect("twin-monitor-right", 0, 0, 1000, 1000);
  const tinyClip = labelRect(-50, -50, 60, 60); // ~ (10*10)/(1000*1000), well under 10%
  const result = checkLabelScreenOverlap([tinyClip], [screen]);
  assert.equal(result.verdict, "PASS");
});

test("checkLabelScreenOverlap: NO-DATA with no screens or no labels supplied", () => {
  const screen = screenRect("s1", 0, 0, 100, 100);
  assert.equal(checkLabelScreenOverlap([labelRect(0, 0, 10, 10)], []).verdict, "NO-DATA");
  assert.equal(checkLabelScreenOverlap([], [screen]).verdict, "NO-DATA");
});
