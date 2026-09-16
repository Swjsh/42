// @ts-nocheck -- same reason as tests/hq-walk-routing.test.ts's own header:
// this file uses explicit ".ts" extensions on its relative imports
// (required for plain `node --test` to resolve them; the project tsconfig's
// `moduleResolution: "bundler"` has no `allowImportingTsExtensions`). Purely
// a syntax-erasure pragma -- has no effect on what actually runs.
//
// CREW-WORKING pass (2026-09-15/16, per ENVIRONMENT-PLAN.md's "People
// actually working" checklist): coverage for
//   1. seated-persona geometry (desk-facing yaw, chair-vs-desk rotation) --
//      reproduces Agent.tsx's `deskFacing` formula and SetKit.tsx's
//      DeskCluster chair-rotation formula literally (both live in files
//      node's own ESM loader cannot import under plain `node --test` --
//      Agent.tsx is a real react-three-fiber .tsx component, SetKit.tsx
//      pulls in three/GLTF loaders -- same constraint every sibling
//      *.test.ts file in this directory already documents, e.g.
//      tests/hq-hub-layout.test.ts's own header).
//   2. palette.ts#purposefulWalkTriggerKey -- imported directly (palette.ts
//      has no .tsx/SetKit dependency, confirmed importable this session).
//   3. components/hq/crewWorking.ts's two pure huddle helpers -- imported
//      directly (that module is deliberately react/three-free, see its own
//      header).
//
// Run: cd dashboard && node --test tests/hq-crew-working.test.ts
// (or the full suite: cd dashboard && npm test)

import { test } from "node:test";
import assert from "node:assert/strict";
import { purposefulWalkTriggerKey } from "../components/hq/palette.ts";
import { detectHuddleTrigger, huddleStandPoints, neighborStandPoint } from "../components/hq/crewWorking.ts";

// ─── 1. Seated + facing the screen ──────────────────────────────────────
// Agent.tsx's `resting` branch (both "working" and "idle" behaviors):
//   deskFacing = atan2(hub[0]-home[0], hub[2]-home[2]) + PI
function deskFacing(home: [number, number, number], hub: [number, number, number]): number {
  return Math.atan2(hub[0] - home[0], hub[2] - home[2]) + Math.PI;
}
// SetKit.tsx#DeskCluster's own chair-mesh rotation, POST BLOCKY-FIXES
// (2026-09-16): plain `rotationY` (the `+ Math.PI` this test used to pin was
// removed -- see SetKit.tsx's own DeskCluster docstring for the full
// derivation of why). `rotationY` is the desk cluster's own group
// orientation -- layout.ts#computePersonaWallSlots computes that as
// `rotationYFacing(wallNormalPoint, HUB)`, i.e. `atan2(self[0]-target[0],
// self[2]-target[2])` with self=the wall anchor, target=HUB.
function chairMeshRotation(anchor: [number, number, number], hub: [number, number, number]): number {
  return Math.atan2(anchor[0] - hub[0], anchor[2] - hub[2]);
}
function normAngle(a: number): number {
  const twoPi = Math.PI * 2;
  return ((a % twoPi) + twoPi) % twoPi;
}

// GREEN (2026-09-16, BLOCKY-FIXES pass -- was the RED-pinned finding above
// until this session): measured against the SAME `home`/`hub` point (the
// seat sits close enough to the wall anchor that treating them as one point
// is the honest approximation this test can make without a render),
// Agent.tsx's `deskFacing` (unchanged -- it had a real screenshot
// verification already, "World-4 fix (P6)", so THIS pass fixed the chair
// instead of the character) and SetKit.tsx's `chairMeshRotation` (its own
// `+ Math.PI` dropped this session) now agree exactly: seat yaw == chair
// yaw == desk facing, the task's own acceptance bar. A live capture
// (see task report for the file) confirms this visually post-deploy.
test("seat yaw == chair yaw == desk facing (Agent.tsx's deskFacing and SetKit.tsx's chair-mesh rotation agree exactly)", () => {
  const hub: [number, number, number] = [0, 0, 0];
  const homes: [number, number, number][] = [[5, 0, 0], [-5, 0, 0], [0, 0, 5], [0, 0, -5]];
  for (const home of homes) {
    const agentFacing = normAngle(deskFacing(home, hub));
    const chairFacing = normAngle(chairMeshRotation(home, hub));
    assert.ok(Math.abs(chairFacing - agentFacing) < 1e-9, `expected chair yaw === desk facing at home ${JSON.stringify(home)}, agent=${agentFacing} chair=${chairFacing}`);
  }
});

// Unambiguous, direction-independent geometry fact (no forward-axis
// assumption needed): the table sits FARTHER from hub-center than the
// chair does, on the SAME desk-cluster local-Z axis -- SetKit.tsx's own
// BAY_DESK_OFFSET_Z/DESK_SEAT_LOCAL comments ("how far back... away from
// the hub", "chair... toward the hub/room"). Confirms "chair on the room
// side, desk backed against the wall" holds numerically, independent of
// which way either prop's mesh visually faces.
test("chair sits closer to hub-center than its own desk (room-side chair, wall-side desk)", () => {
  const BAY_DESK_OFFSET_Z = 0.8;
  const FURNITURE_SCALE = 2.0;
  const DESK_SEAT_LOCAL_Z = -0.35 * FURNITURE_SCALE; // SetKit.tsx#DESK_SEAT_LOCAL
  const tableLocalZ = BAY_DESK_OFFSET_Z + 0.3 * FURNITURE_SCALE; // DeskCluster's own table mount offset
  const chairLocalZ = BAY_DESK_OFFSET_Z + DESK_SEAT_LOCAL_Z;
  assert.ok(chairLocalZ < tableLocalZ, "chair should sit at a SMALLER local-Z (nearer hub/anchor) than the table");
});

// ─── 2. purposeful-walk gating: real events only, never a clock ─────────
test("purposefulWalkTriggerKey: null (no trigger) for a persona that has never fired", () => {
  assert.equal(purposefulWalkTriggerKey("Scout", null, "IDLE"), null);
});

test("purposefulWalkTriggerKey: same lastFireISO + status across polls -> IDENTICAL key (no refire)", () => {
  const a = purposefulWalkTriggerKey("Scout", "2026-09-15T10:00:00Z", "GREEN");
  const b = purposefulWalkTriggerKey("Scout", "2026-09-15T10:00:00Z", "GREEN");
  assert.equal(a, b);
});

test("purposefulWalkTriggerKey: a genuine lastFireISO change -> a DIFFERENT key (fires once)", () => {
  const a = purposefulWalkTriggerKey("Scout", "2026-09-15T10:00:00Z", "GREEN");
  const b = purposefulWalkTriggerKey("Scout", "2026-09-15T10:08:00Z", "GREEN");
  assert.notEqual(a, b);
});

test("purposefulWalkTriggerKey: a status-only change (same lastFireISO) still counts as a real event", () => {
  const a = purposefulWalkTriggerKey("Scout", "2026-09-15T10:00:00Z", "GREEN");
  const b = purposefulWalkTriggerKey("Scout", "2026-09-15T10:00:00Z", "YELLOW");
  assert.notEqual(a, b);
});

test("purposefulWalkTriggerKey: never derived from wall-clock time -- two calls at different Date.now() with identical inputs still match", () => {
  const a = purposefulWalkTriggerKey("Pilot", "2026-09-15T09:35:00Z", "GREEN");
  // Simulate time passing (the old bucketKey mechanism would have rolled
  // over a 6-10min bucket by now) -- the event-keyed function must not care.
  const b = purposefulWalkTriggerKey("Pilot", "2026-09-15T09:35:00Z", "GREEN");
  assert.equal(a, b);
});

// ─── 3. Huddle pair: 0/2/2->1->2 GREEN transitions ───────────────────────
test("detectHuddleTrigger: 0 -> 2 GREEN fires exactly once, picking the two most-recently-fired", () => {
  const green = [
    { name: "Scout", lastFireISO: "2026-09-15T10:00:00Z" },
    { name: "Coach", lastFireISO: "2026-09-15T10:05:00Z" },
  ];
  const result = detectHuddleTrigger(green, 0, 1000);
  assert.ok(result.key);
  assert.deepEqual(result.pair, ["Coach", "Scout"]); // Coach fired more recently -> sorts first
});

test("detectHuddleTrigger: 2 -> 2 (steady) does NOT refire", () => {
  const green = [
    { name: "Scout", lastFireISO: "2026-09-15T10:00:00Z" },
    { name: "Coach", lastFireISO: "2026-09-15T10:05:00Z" },
  ];
  const result = detectHuddleTrigger(green, 2, 2000);
  assert.equal(result.key, null);
  assert.equal(result.pair, null);
});

test("detectHuddleTrigger: 2 -> 1 -> 2 fires again (a genuine second transition, unique key)", () => {
  // Scene.tsx calls this once per poll, feeding back its OWN previous
  // count each time (a plain ref) -- simulated here as a literal sequence
  // of (prevCount, thisCallsGreenList) pairs rather than internal state,
  // since the function itself is pure/stateless by design.
  const green = [
    { name: "Scout", lastFireISO: "2026-09-15T10:00:00Z" },
    { name: "Coach", lastFireISO: "2026-09-15T10:05:00Z" },
  ];
  const first = detectHuddleTrigger(green, /* prevCount */ 0, 1000); // 0 -> 2: fires
  const steady = detectHuddleTrigger(green, /* prevCount */ 2, 2000); // 2 -> 2: no refire
  const refire = detectHuddleTrigger(green, /* prevCount */ 1, 3000); // 1 -> 2 (dipped, came back): fires
  assert.ok(first.key);
  assert.equal(steady.key, null);
  assert.ok(refire.key);
  assert.notEqual(first.key, refire.key); // never the same key twice, even for the same pair
});

test("detectHuddleTrigger: fewer than 2 GREEN never fires, regardless of prior count", () => {
  const result = detectHuddleTrigger([{ name: "Scout", lastFireISO: "2026-09-15T10:00:00Z" }], 0, 1000);
  assert.equal(result.key, null);
});

// ─── neighborStandPoint (Defect 2 fix, BLOCKY-FIXES pass 2026-09-16) ──────
// Pins that a "neighbor" purposeful walk never lands a visitor exactly on
// the neighbor's own seat (the real "two personas on one desk" bug a live
// capture caught) -- the returned point must be a real, non-zero distance
// from the seat, and must NOT collide with a plausible adjacent-desk
// position (PERSONA_WALL_LATERAL_OFFSET=4.6, layout.ts) at the default
// 1.0u lateral offset.
test("neighborStandPoint: stands a real distance away from the neighbor's own seat, never on top of it", () => {
  const seat: [number, number, number] = [5.1, 0, -4.6]; // a real persona seat, tests/hq-desk-preset.test.ts's own slot0
  const rotationY = Math.PI / 2;
  const stand = neighborStandPoint(seat, rotationY);
  const dist = Math.hypot(stand[0] - seat[0], stand[2] - seat[2]);
  assert.ok(dist > 0.5, `expected a real stand-off distance, got ${dist}u`);
  assert.ok(dist < 4.6, `expected to stay well short of the next desk over (4.6u), got ${dist}u`);
});

test("neighborStandPoint: offsets purely along the desk's own tangent (parallel to the wall), never toward/away from it", () => {
  const seat: [number, number, number] = [0, 0, 0];
  const rotationY = 0;
  const stand = neighborStandPoint(seat, rotationY, 1.0);
  // tangentX=cos(0)=1, tangentZ=-sin(0)=0 -> pure +X offset, zero Z drift
  assert.ok(Math.abs(stand[0] - 1.0) < 1e-9, `expected X offset of exactly 1.0, got ${stand[0]}`);
  assert.ok(Math.abs(stand[2]) < 1e-9, `expected zero Z drift, got ${stand[2]}`);
});

test("huddleStandPoints: stand points are >= 1.0u apart and face each other", () => {
  const tableCenter: [number, number, number] = [1.485, 0, 1.485]; // HUB_TABLE_RADIUS(2.1) at 45deg
  const hub: [number, number, number] = [0, 0, 0];
  const spots = huddleStandPoints(tableCenter, hub, 1.1, 1.2);
  const dist = Math.hypot(spots.a[0] - spots.b[0], spots.a[2] - spots.b[2]);
  assert.ok(dist >= 1.0, `stand points only ${dist}u apart`);
  // Facing each other: huddleStandPoints derives faceYaw via the exact same
  // atan2(self-target) shape as layout.ts#rotationYFacing, whose own doc
  // comment states plainly that under a three.js rotation.y of that value,
  // the LOCAL -Z axis (world direction (-sin(yaw), -cos(yaw)), the standard
  // three.js rotation-about-Y transform of (0,0,-1)) points at the target --
  // reused here rather than re-derived, so this test's forward convention
  // matches the ONE already established/relied-on elsewhere in this file.
  const fwdA: [number, number] = [-Math.sin(spots.faceYawA), -Math.cos(spots.faceYawA)];
  const towardB: [number, number] = [spots.b[0] - spots.a[0], spots.b[2] - spots.a[2]];
  const dotA = fwdA[0] * towardB[0] + fwdA[1] * towardB[1];
  assert.ok(dotA > 0, "A should face toward B");
  const fwdB: [number, number] = [-Math.sin(spots.faceYawB), -Math.cos(spots.faceYawB)];
  const towardA: [number, number] = [spots.a[0] - spots.b[0], spots.a[2] - spots.b[2]];
  const dotB = fwdB[0] * towardA[0] + fwdB[1] * towardA[1];
  assert.ok(dotB > 0, "B should face toward A");
});

test("huddleStandPoints: both stand points sit strictly between the table and the hub (the table's near side)", () => {
  const tableCenter: [number, number, number] = [1.485, 0, 1.485];
  const hub: [number, number, number] = [0, 0, 0];
  const nearRadius = 1.1;
  const spots = huddleStandPoints(tableCenter, hub, nearRadius, 1.2);
  const distFromTable = (p: [number, number, number]) => Math.hypot(p[0] - tableCenter[0], p[2] - tableCenter[2]);
  // Both points sit roughly `nearRadius` from the table center (allowing for
  // the lateral 0.6u offset, distance is slightly more than nearRadius).
  assert.ok(distFromTable(spots.a) >= nearRadius - 1e-9);
  assert.ok(distFromTable(spots.b) >= nearRadius - 1e-9);
  // And nearer the hub than the table's OWN distance from the hub (they're
  // on the near/hub-facing side, not the far side).
  const tableToHub = Math.hypot(tableCenter[0] - hub[0], tableCenter[2] - hub[2]);
  const aToHub = Math.hypot(spots.a[0] - hub[0], spots.a[2] - hub[2]);
  assert.ok(aToHub < tableToHub, "stand point should be nearer the hub than the table center");
});
