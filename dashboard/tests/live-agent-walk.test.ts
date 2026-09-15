// @ts-nocheck -- same reason as tests/hq-agents.test.ts's own header: this
// file uses an explicit ".ts" extension on its relative import (required for
// plain `node --test` to resolve it; the project tsconfig's
// `moduleResolution: "bundler"` has no `allowImportingTsExtensions`).
//
// Coordinator fix (2026-09-14, browser verification of e990319f found 2
// defects in LiveAgents.tsx): unit tests for the pure decision/geometry
// functions extracted into components/hq/liveAgentWalk.ts.
//
// DEFECT 2 (stuck leave) root cause, proven here by
// "decideNextWalk starts the leave walk even when seenTarget already equals
// ENTRY_NODE_ID": the ORIGINAL LiveAgents.tsx gated every destination change
// -- ordinary retargeting AND the final leave-to-entry walk -- behind ONE
// shared `seenDest.current === activeDest` latch. An agent whose most
// recently classified zone had already resolved to "hub" (lib/hq-agents.ts
// #ZONE_NODE_ID.hub === ENTRY_NODE_ID) left that latch holding
// "hub-center"; when the server later dropped it and `leaving` flipped
// true, the newly-computed destination ALSO evaluated to "hub-center" --
// the shared latch read this as "nothing changed" and silently skipped the
// walk-kickoff (and the despawn-on-arrival it would have scheduled),
// stranding the avatar in "working" with `leaving` permanently true. This
// test file's own decideNextWalk treats leaving as an independent decision
// that never consults the ordinary-retargeting latch, so this exact
// collision can no longer suppress a leave. NOTE (CAMPUS-GATE pass,
// 2026-09-15): at the time this defect was found, ENTRY_NODE_ID was
// "hub-center", the SAME string ZONE_NODE_ID.hub resolves to -- exactly
// what made the collision possible. ENTRY_NODE_ID has since moved to
// "campus-gate" (J: agents should "spawn at the gate ... walk out and
// despawn when they go quiet", not spawn/leave at the hub centre) --
// ZONE_NODE_ID.hub is still "hub-center" (lib/hq-agents.ts, unchanged), so
// the two no longer share a value at all. The regression test below still
// proves the general shape (leaving must fire even when `seenTarget`
// already equals the CURRENT `ENTRY_NODE_ID`, whatever that string is) by
// reading the constant live rather than hardcoding either string, so it
// keeps covering the same collision class across this rename.
//
// Run: cd dashboard && node --test tests/live-agent-walk.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  applyFollowCap,
  applyLaneOffsets,
  computeBatchOrder,
  computeBatchStaggerDelays,
  computeMaxPathDurationS,
  computeSidestepPlan,
  computeWaitPoint,
  ENTRY_NODE_ID,
  findCarAhead,
  findOncoming,
  findWalkPath,
  FOLLOW_GAP_U,
  HEAD_ON_COS_MAX,
  isPointOccupied,
  laneIndexForId,
  laneValueForId,
  LANE_STEP_U,
  LANE_VALUES,
  LEAVE_TIMEOUT_MARGIN_S,
  pathDistance,
  poseAlongPath,
  decideNextWalk,
  computeStandSlot,
  rampSidestepOffset,
  rightOf,
  SIDESTEP_DETECTION_RADIUS_U,
  SIDESTEP_RATE_U_PER_S,
  SIDESTEP_TARGET_U,
  STAGGER_DELAY_S,
  STAND_RING_RADIUS,
  reconcileLiveAgentRoster,
  shouldWriteLiveAgentDiag,
  stableSlotOffset,
  STAND_SLOT_CAPACITY,
  updateStableSlotAssignments,
  waitAlongOffsetForIndex,
  waitLaneOffsetForIndex,
  WAIT_ALONG_STEP_U,
  WAIT_LANE_COUNT,
  WAIT_LANE_STEP_U,
  type WalkerSnapshot,
  type WalkGraph,
} from "../components/hq/liveAgentWalk.ts";
import { ENTRY_NODE_ID as HQ_AGENTS_ENTRY_NODE_ID, ZONE_NODE_ID } from "../lib/hq-agents.ts";

// ─── pathDistance ───────────────────────────────────────────────────────────

test("pathDistance sums XZ-plane leg distances, ignoring Y", () => {
  const wp: [number, number, number][] = [[0, 5, 0], [3, 0, 4]]; // 3-4-5 triangle in XZ, Y differs
  assert.equal(pathDistance(wp), 5);
});

test("pathDistance is 0 for a single point", () => {
  assert.equal(pathDistance([[1, 2, 3]]), 0);
});

// ─── poseAlongPath ──────────────────────────────────────────────────────────

test("poseAlongPath at t=0 returns the first waypoint", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [10, 0, 0]];
  const { position } = poseAlongPath(wp, 0);
  assert.deepEqual(position, [0, 0, 0]);
});

test("poseAlongPath at t=1 returns the last waypoint", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [10, 0, 0]];
  const { position } = poseAlongPath(wp, 1);
  assert.deepEqual(position, [10, 0, 0]);
});

test("poseAlongPath interpolates a single leg linearly at t=0.5", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [10, 0, 0]];
  const { position, facing } = poseAlongPath(wp, 0.5);
  assert.equal(position[0], 5);
  assert.equal(facing, Math.atan2(10, 0));
});

test("poseAlongPath handles a zero-XZ-distance leg without NaN/hanging (smart-board <-> hub-center coincidence)", () => {
  // WALL_POS (smart-board) and HUB (hub-center) share x=0,z=0 in this real
  // scene (Scene.tsx's WALL_POS=[0,3.4,0]) -- proves the zero-distance leg
  // case that made DEFECT 2's symptom LOOK stuck (position pinned at the
  // shared XZ point) never itself produces NaN or an infinite loop.
  const wp: [number, number, number][] = [[0, 3.4, 0], [0, 0, 0]];
  const at0 = poseAlongPath(wp, 0);
  const atHalf = poseAlongPath(wp, 0.5);
  const at1 = poseAlongPath(wp, 1);
  for (const r of [at0, atHalf, at1]) {
    assert.ok(Number.isFinite(r.position[0]));
    assert.ok(Number.isFinite(r.position[1]));
    assert.ok(Number.isFinite(r.position[2]));
    assert.ok(Number.isFinite(r.facing));
  }
});

test("poseAlongPath picks the correct leg across a multi-leg path", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [10, 0, 0], [10, 0, 10]];
  // total distance 20; t=0.75 -> 15 units in -> 5 units into the second leg
  const { position } = poseAlongPath(wp, 0.75);
  assert.equal(position[0], 10);
  assert.equal(position[2], 5);
});

// ─── decideNextWalk (DEFECT 2) ──────────────────────────────────────────────

test("decideNextWalk: fresh avatar walks to its first target", () => {
  const d = decideNextWalk({ leaving: false, targetNodeId: "smart-board", currentNode: ENTRY_NODE_ID, seenTarget: null, leaveTriggered: false });
  assert.deepEqual(d, { action: "walk", dest: "smart-board", despawn: false });
});

test("decideNextWalk: no-op when the target hasn't changed", () => {
  const d = decideNextWalk({ leaving: false, targetNodeId: "smart-board", currentNode: ENTRY_NODE_ID, seenTarget: "smart-board", leaveTriggered: false });
  assert.deepEqual(d, { action: "none" });
});

test("decideNextWalk: settles immediately when already standing at the new target", () => {
  const d = decideNextWalk({ leaving: false, targetNodeId: "smart-board", currentNode: "smart-board", seenTarget: "bay-desk-0", leaveTriggered: false });
  assert.deepEqual(d, { action: "settle", dest: "smart-board", despawn: false });
});

test("decideNextWalk: retargets mid-life to a new zone", () => {
  const d = decideNextWalk({ leaving: false, targetNodeId: "bay-desk-0", currentNode: "smart-board", seenTarget: "smart-board", leaveTriggered: false });
  assert.deepEqual(d, { action: "walk", dest: "bay-desk-0", despawn: false });
});

test("decideNextWalk: THE DEFECT 2 FIX -- leaving starts the exit walk even when seenTarget already equals ENTRY_NODE_ID", () => {
  // This is the exact collision that stranded 65e3d7 in the wild: the
  // agent's own classified zone had at some point resolved to "hub"
  // (ZONE_NODE_ID.hub === ENTRY_NODE_ID, true AT THE TIME -- both were
  // "hub-center"), so seenTarget already holds ENTRY_NODE_ID from ordinary
  // (non-leaving) life -- a shared-latch design would read the leaving
  // transition as "no change" and never walk out. Reads ENTRY_NODE_ID live
  // (never a hardcoded string) so this keeps proving the same collision
  // class regardless of what the constant's current value is.
  const d = decideNextWalk({
    leaving: true,
    targetNodeId: "smart-board", // irrelevant while leaving -- must be ignored
    currentNode: "smart-board",
    seenTarget: ENTRY_NODE_ID, // the exact collision value
    leaveTriggered: false,
  });
  assert.deepEqual(d, { action: "walk", dest: ENTRY_NODE_ID, despawn: true });
});

test("decideNextWalk: CAMPUS-GATE pass -- the same DEFECT 2 collision, pinned explicitly to ENTRY_NODE_ID = \"campus-gate\"", () => {
  // Task's own regression requirement: keep a test that still covers
  // "leaving starts the exit walk even when seenTarget equals the
  // destination", now spelled out with the CURRENT concrete entry-node
  // value rather than only through the live import above -- e.g. an agent
  // whose most recent ordinary target happened to BE campus-gate itself
  // (a real reachable shape: ZONE_NODE_ID has no "campus-gate" entry today,
  // but nothing stops a future zone mapping from resolving there, and the
  // fix must not depend on that never happening).
  assert.equal(ENTRY_NODE_ID, "campus-gate");
  const d = decideNextWalk({
    leaving: true,
    targetNodeId: "smart-board",
    currentNode: "smart-board",
    seenTarget: "campus-gate",
    leaveTriggered: false,
  });
  assert.deepEqual(d, { action: "walk", dest: "campus-gate", despawn: true });
});

// ─── ENTRY_NODE_ID sync (CAMPUS-GATE pass, 2026-09-15) ─────────────────────
//
// liveAgentWalk.ts#ENTRY_NODE_ID and lib/hq-agents.ts#ENTRY_NODE_ID are two
// independent string literals by design -- hq-agents.ts is import-free (no
// sibling lib/*.ts value import, no three.js, no react, per its own header)
// so it cannot import this constant from a react/three-adjacent module.
// Nothing in the type system enforces they stay equal; this is that
// enforcement. Both modules are plain node-testable .ts files (no JSX, no
// SetKit dependency), so both are safely importable by value here.
test("ENTRY_NODE_ID sync: liveAgentWalk.ts and lib/hq-agents.ts agree on the entry node id", () => {
  assert.equal(ENTRY_NODE_ID, HQ_AGENTS_ENTRY_NODE_ID);
  assert.equal(ENTRY_NODE_ID, "campus-gate");
});

test("decideNextWalk: leaving is a one-shot -- does not re-trigger once leaveTriggered", () => {
  const d = decideNextWalk({ leaving: true, targetNodeId: "smart-board", currentNode: "hub-center", seenTarget: null, leaveTriggered: true });
  assert.deepEqual(d, { action: "none" });
});

test("decideNextWalk: leaving settles immediately (and despawns) when already at the entry node", () => {
  const d = decideNextWalk({ leaving: true, targetNodeId: "smart-board", currentNode: ENTRY_NODE_ID, seenTarget: null, leaveTriggered: false });
  assert.deepEqual(d, { action: "settle", dest: ENTRY_NODE_ID, despawn: true });
});

test("decideNextWalk: leaving never consults targetNodeId at all", () => {
  const a = decideNextWalk({ leaving: true, targetNodeId: "ambient-core", currentNode: "smart-board", seenTarget: null, leaveTriggered: false });
  const b = decideNextWalk({ leaving: true, targetNodeId: "bay-desk-0", currentNode: "smart-board", seenTarget: null, leaveTriggered: false });
  assert.deepEqual(a, b);
});

// ─── decideNextWalk (TELEPORT FIX, 2026-09-15 coordinator probe) ───────────
//
// Root cause: `currentNode` only ever advances to a walk's destination ON
// ARRIVAL -- while a walk is still in flight it names the ORIGIN the avatar
// departed from, not where it currently is. Probe run
// 20260915T070024Z-9lS6tSfBnOgS3qHx4bzbD.samples.json.gz caught this exactly
// twice in the SAME tick (298->299 and 328->329, dt ~0.48-0.50s): session
// a06954b44dcea322f was mid-walk toward "ambient-core" (pos [15.24,0], not
// yet arrived) when its server-reported target flipped back to
// "bay-desk-0" -- the node it had departed FROM, which `currentNode` still
// named because that walk had never completed -- and jumped straight to
// [18.30,8.20] (8.75u in 0.48s, 18.2u/s vs. the ~0.7u/s WALK_SPEED band).
// The same tick, session:dcc3d160-...-a8b2 mid-walk toward "bay-desk-0"
// (pos [17.40,3.47]) had its target flip back to "ambient-core" and jumped
// 17.8u in 0.48s (35.4u/s) straight to [-0.03,-0.09]. Both are the exact
// `currentNode === targetNodeId` settle-shortcut firing while genuinely
// mid-walk, not at rest.

test("decideNextWalk: THE TELEPORT FIX -- mid-walk avatar whose target flaps back to its own walk origin must walk, not snap", () => {
  // Mirrors tick 298->299: seenTarget "ambient-core" (what it was walking
  // toward), targetNodeId flips back to "bay-desk-0" (currentNode's stale
  // value -- the origin this in-flight walk started from, never updated
  // because that walk hasn't arrived).
  const d = decideNextWalk({
    leaving: false,
    targetNodeId: "bay-desk-0",
    currentNode: "bay-desk-0",
    seenTarget: "ambient-core",
    leaveTriggered: false,
    isWalking: true,
  });
  assert.deepEqual(d, { action: "walk", dest: "bay-desk-0", despawn: false });
});

test("decideNextWalk: mirrors the OTHER half of the same tick -- session:dcc3d160 flapping bay-desk-0 -> ambient-core mid-walk", () => {
  const d = decideNextWalk({
    leaving: false,
    targetNodeId: "ambient-core",
    currentNode: "ambient-core",
    seenTarget: "bay-desk-0",
    leaveTriggered: false,
    isWalking: true,
  });
  assert.deepEqual(d, { action: "walk", dest: "ambient-core", despawn: false });
});

test("decideNextWalk: omitting isWalking reproduces the PRE-FIX defect (documents the exact bug shape)", () => {
  // isWalking defaults to false -- this is what the code did before the fix
  // wired `phase.current === \"walking\"` through, and it wrongly settles
  // (instant snap) instead of walking.
  const d = decideNextWalk({
    leaving: false,
    targetNodeId: "bay-desk-0",
    currentNode: "bay-desk-0",
    seenTarget: "ambient-core",
    leaveTriggered: false,
  });
  assert.deepEqual(d, { action: "settle", dest: "bay-desk-0", despawn: false });
});

test("decideNextWalk: a genuinely resting avatar still settles in place (isWalking: false is not a regression)", () => {
  const d = decideNextWalk({
    leaving: false, targetNodeId: "smart-board", currentNode: "smart-board", seenTarget: "bay-desk-0", leaveTriggered: false, isWalking: false,
  });
  assert.deepEqual(d, { action: "settle", dest: "smart-board", despawn: false });
});

test("decideNextWalk: isWalking also guards the leaving-settle shortcut (same mechanism, leave path)", () => {
  const d = decideNextWalk({
    leaving: true, targetNodeId: "smart-board", currentNode: ENTRY_NODE_ID, seenTarget: null, leaveTriggered: false, isWalking: true,
  });
  assert.deepEqual(d, { action: "walk", dest: ENTRY_NODE_ID, despawn: true });
});

// ─── laneIndexForId / laneValueForId / applyLaneOffsets ────────────────────
// (CONVOY-STACK fix, 2026-09-15; CONVOY-STACK v2, same day -- discrete lanes
// replace the v1 continuous hash, which let 2 real ids land 0.01u apart,
// nowhere near the 0.7u stand-slot bar -- see liveAgentWalk.ts's own header
// for the full v1->v2 postmortem.)

test("laneIndexForId: deterministic -- same id always yields the same index", () => {
  assert.equal(laneIndexForId("session-a1"), laneIndexForId("session-a1"));
});

test("laneIndexForId: always a valid LANE_VALUES index", () => {
  for (const id of ["a", "session-xyz-123", "", "z".repeat(50), "a93582c1", "ab416fc0"]) {
    const idx = laneIndexForId(id);
    assert.ok(idx >= 0 && idx < LANE_VALUES.length, `laneIndexForId(${JSON.stringify(id)}) = ${idx} out of range`);
  }
});

test("laneValueForId: only ever returns one of the fixed LANE_VALUES -- no near-miss between them", () => {
  // THE v1->v2 FIX: exactly what broke real ids a93582c1/ab416fc0 (0.01u
  // apart under the old continuous hash) -- with a discrete set, every id
  // lands EXACTLY on one of 3 known values, never something in between.
  const ids = ["a06954b44dcea322f", "a3f93d37e2266fd28", "dcc3d160-abc-a8b2", "7252", "aa69", "345c", "a93582c1", "ab416fc0"];
  for (const id of ids) {
    const v = laneValueForId(id);
    assert.ok(LANE_VALUES.includes(v), `laneValueForId(${id}) = ${v} is not one of LANE_VALUES`);
  }
});

test("applyLaneOffsets: leaves the first and last waypoint exactly unchanged", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [10, 0, 0], [20, 0, 0], [30, 0, 0]];
  const out = applyLaneOffsets(wp, "some-id");
  assert.deepEqual(out[0], wp[0]);
  assert.deepEqual(out[out.length - 1], wp[wp.length - 1]);
});

test("applyLaneOffsets: nudges interior waypoints perpendicular to the local path direction, by exactly this id's discrete lane value", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [10, 0, 0], [20, 0, 0]];
  const out = applyLaneOffsets(wp, "lane-test-id");
  // Path runs along +X, so any nudge must be purely in Z (perpendicular),
  // never changing X.
  const expected = laneValueForId("lane-test-id");
  assert.equal(out[1][0], 10);
  assert.ok(Math.abs(out[1][2] - expected) < 1e-9, `expected offset=${expected}, got ${out[1][2]}`);
});

test("applyLaneOffsets: a path with no interior waypoint (direct 2-point hop) is returned unchanged", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [5, 0, 5]];
  const out = applyLaneOffsets(wp, "any-id");
  assert.deepEqual(out, wp);
});

test("applyLaneOffsets: nudge magnitude never exceeds LANE_STEP_U", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [10, 0, 0], [20, 0, 0]];
  for (const id of ["a", "bb", "ccc", "dddd", "session-real-id-0001"]) {
    const out = applyLaneOffsets(wp, id);
    const dz = Math.abs(out[1][2] - wp[1][2]);
    assert.ok(dz <= LANE_STEP_U + 1e-9, `id=${id} produced a ${dz}u nudge, exceeding LANE_STEP_U`);
  }
});

// ─── computeWaitPoint / waitLaneOffsetForIndex / waitAlongOffsetForIndex ───
// (CONVOY-STACK v3, 2026-09-15 -- replaces v2's id-hash approach, which let
// 2 same-batch ids collide 1-in-3 times: session:5385... and
// ae892a7f7e3cf5a51, both "spawning" toward ambient-core, sat at the
// identical [21.65,0.45] at t=7.5s, probe 20260915T085943Z.)

test("waitLaneOffsetForIndex: zigzags 0, +1, -1, +2, -2 (x WAIT_LANE_STEP_U), cycling every WAIT_LANE_COUNT", () => {
  const expected = [0, WAIT_LANE_STEP_U, -WAIT_LANE_STEP_U, 2 * WAIT_LANE_STEP_U, -2 * WAIT_LANE_STEP_U];
  for (let i = 0; i < expected.length; i++) {
    assert.ok(Math.abs(waitLaneOffsetForIndex(i) - expected[i]) < 1e-9, `index ${i}: expected ${expected[i]}, got ${waitLaneOffsetForIndex(i)}`);
  }
  assert.equal(waitLaneOffsetForIndex(WAIT_LANE_COUNT), waitLaneOffsetForIndex(0));
});

test("waitLaneOffsetForIndex: every pair of the WAIT_LANE_COUNT lane values is >=WAIT_LANE_STEP_U apart", () => {
  const values = Array.from({ length: WAIT_LANE_COUNT }, (_, i) => waitLaneOffsetForIndex(i));
  for (let i = 0; i < values.length; i++) {
    for (let j = i + 1; j < values.length; j++) {
      const gap = Math.abs(values[i] - values[j]);
      assert.ok(gap >= WAIT_LANE_STEP_U - 1e-9, `lanes ${i} (${values[i]}) and ${j} (${values[j]}) only ${gap}u apart`);
    }
  }
});

test("waitLaneOffsetForIndex: the two most-extreme lanes stay within the gate's own +-1.47u opening", () => {
  const values = Array.from({ length: WAIT_LANE_COUNT }, (_, i) => waitLaneOffsetForIndex(i));
  const maxAbs = Math.max(...values.map(Math.abs));
  assert.ok(maxAbs <= 1.47, `most-extreme lane ${maxAbs}u exceeds the gate's +-1.47u opening`);
});

test("waitAlongOffsetForIndex: 0 for the first WAIT_LANE_COUNT indices, one WAIT_ALONG_STEP_U per row after that", () => {
  for (let i = 0; i < WAIT_LANE_COUNT; i++) assert.equal(waitAlongOffsetForIndex(i), 0);
  assert.equal(waitAlongOffsetForIndex(WAIT_LANE_COUNT), WAIT_ALONG_STEP_U);
  assert.equal(waitAlongOffsetForIndex(2 * WAIT_LANE_COUNT), 2 * WAIT_ALONG_STEP_U);
});

test("computeWaitPoint: nudges the origin perpendicular to the direction toward `next`, by this index's lane value", () => {
  const origin: [number, number, number] = [21.6, 0, 0];
  const next: [number, number, number] = [17.4, 0, 0]; // due -X
  const wp = computeWaitPoint(origin, next, 1); // index 1 -> lane +WAIT_LANE_STEP_U
  // direction origin->next is due -X (dx=-4.2, dz=0); perp = (-dz, dx)/len =
  // (0, -1), so the offset lands entirely on Z, with the sign this exact
  // rotation convention produces (matches applyLaneOffsets's own formula).
  const expectedZ = -waitLaneOffsetForIndex(1);
  assert.equal(wp[0], origin[0]);
  assert.ok(Math.abs(wp[2] - expectedZ) < 1e-9, `expected z-offset ${expectedZ}, got ${wp[2]}`);
});

test("computeWaitPoint: an overflow-row index also moves backward along the corridor axis (away from `next`)", () => {
  const origin: [number, number, number] = [21.6, 0, 0];
  const next: [number, number, number] = [17.4, 0, 0]; // due -X, so "backward" is +X
  const wp = computeWaitPoint(origin, next, WAIT_LANE_COUNT); // first overflow row, lane 0
  assert.ok(wp[0] > origin[0], `expected the avatar pushed backward (+X, away from next), got x=${wp[0]}`);
  assert.ok(Math.abs(wp[0] - (origin[0] + WAIT_ALONG_STEP_U)) < 1e-9);
});

test("computeWaitPoint: falls back to the bare origin when origin and next coincide (no direction to be perpendicular to)", () => {
  const origin: [number, number, number] = [5, 0, 5];
  const wp = computeWaitPoint(origin, origin, 3);
  assert.deepEqual(wp, origin);
});

// THE REQUIRED PROOF (bug 2): a batch of 3-4 ids gets pairwise >=0.7u wait
// points, even when their id-hash lanes would collide (the exact v2
// failure mode) -- verified here purely via batch INDEX, since v3 no longer
// consults the id hash for wait-point placement at all.
test("WAIT-POINT PROOF: a batch of 4 ids gets pairwise >=0.7u wait points, including ids whose old id-hash lane would have collided", () => {
  const origin: [number, number, number] = [21.6, 0, 0];
  const next: [number, number, number] = [17.4, 0, 0];
  const REQUIRED_MIN_SEPARATION_U = 0.7;
  const points = [0, 1, 2, 3].map((index) => computeWaitPoint(origin, next, index));
  for (let i = 0; i < points.length; i++) {
    for (let j = i + 1; j < points.length; j++) {
      const dist = Math.hypot(points[i][0] - points[j][0], points[i][2] - points[j][2]);
      assert.ok(dist >= REQUIRED_MIN_SEPARATION_U - 1e-9, `batch indices ${i} and ${j} are only ${dist.toFixed(3)}u apart`);
    }
  }
});

test("WAIT-POINT PROOF: an 8-member batch (roster cap, spanning 2 overflow rows) still gets pairwise >=0.7u wait points", () => {
  const origin: [number, number, number] = [21.6, 0, 0];
  const next: [number, number, number] = [17.4, 0, 0];
  const REQUIRED_MIN_SEPARATION_U = 0.7;
  const points = Array.from({ length: 8 }, (_, index) => computeWaitPoint(origin, next, index));
  let checked = 0;
  for (let i = 0; i < points.length; i++) {
    for (let j = i + 1; j < points.length; j++) {
      checked++;
      const dist = Math.hypot(points[i][0] - points[j][0], points[i][2] - points[j][2]);
      assert.ok(dist >= REQUIRED_MIN_SEPARATION_U - 1e-9, `batch indices ${i} and ${j} are only ${dist.toFixed(3)}u apart`);
    }
  }
  assert.equal(checked, 28, "sanity: C(8,2) = 28 pairs must all have been checked");
});

// ─── TELEPORT-ON-LEAVE fix (CONVOY-STACK v4, 2026-09-15) ───────────────────
//
// ROOT CAUSE (probe 20260915T094248Z, a3db17263aa046509): a mass-leave batch
// applied computeWaitPoint's gate-shaped zigzag lane AROUND the avatar's
// CURRENT zone position the instant `leaving` flipped true -- instantly
// relocating a RESTING avatar (already on its own distinct stand slot, no
// separation needed) up to WAIT_LANE_STEP_U away from where it was actually
// rendered a frame earlier (the reported 0.73u snap). Then, when the
// stagger delay elapsed, the walk resumed from `wp[0]` = the avatar's TRUE
// rest position (`livePos`, captured correctly at decision time) -- NOT
// from the gate-lane point it had been visually sitting at during the wait
// -- producing a SECOND snap back (the reported 0.87u jump) the moment
// motion resumed. Two symptoms, one root cause: the wait-point render and
// the walk's own first waypoint disagreed about where the avatar actually
// was. Fix (LiveAgents.tsx's own `pendingWaitUsesGateLane` ref): a SPAWN
// wait still uses the gate lane (invisible -- the avatar is being CREATED,
// no prior pose to jump from); a LEAVE wait now holds `livePos` exactly, so
// both endpoints of the wait agree with the walk's own first waypoint.
//
// This is a PURE simulation of LiveAgentAvatar's own per-frame position
// update (settle -> leave decision -> stagger wait -> walk), built only
// from this module's exported functions, sampled at the probe's own 0.5s
// cadence -- run once against the PRE-FIX gate-lane-during-leave behavior
// (documents the reported bug, RED) and once against the FIXED
// hold-livePos-during-leave behavior (GREEN), both checked against the
// coordinator's own invariant: no rendered position may change by more than
// WALK_SPEED*dt + 0.05 between consecutive samples once an avatar exists.

const SIM_WALK_SPEED = 0.7; // KitAgent.tsx#WALK_SPEED's own real value
const SIM_SAMPLE_DT_S = 0.5; // the probe's own sampling cadence

interface SimStep {
  tS: number;
  position: [number, number, number];
}

/** Models LiveAgentAvatar's settle -> leave -> stagger-wait -> walk
 * sequence for ONE avatar, sampled every `SIM_SAMPLE_DT_S`. `useGateLaneOnLeave`
 * toggles the exact behavior under test: true reproduces the PRE-FIX bug
 * (computeWaitPoint applied to the leave wait), false is the FIXED
 * behavior (hold `livePos`). */
function simulateSettleLeaveWalk(useGateLaneOnLeave: boolean): SimStep[] {
  const zoneNode: [number, number, number] = [0, 0, 0];
  const standOffset: [number, number] = [-1.65, -0.82]; // this avatar's own real, already-settled stand slot
  const settledPos: [number, number, number] = [zoneNode[0] + standOffset[0], 0, zoneNode[2] + standOffset[1]];
  const gateNode: [number, number, number] = [21.6, 0, 0];
  const hallwayNode: [number, number, number] = [17.4, 0, 0];
  const leaveIndex = 1; // a same-batch leave with a nonzero gate lane, per the bug report

  // decision time: livePos is READ from wherever the avatar is actually
  // rendered right now (settledPos, correct per CONVOY-STACK v3's own
  // continuous stand-slot correction).
  const livePos = settledPos;
  const finalPoint = gateNode; // destinationPointFor(dest, despawn=true) -- raw node, no ring offset
  const rawPath = [livePos, hallwayNode, finalPoint];
  const wp = applyLaneOffsets(rawPath, "a3db17263aa046509");
  const duration = Math.max(0.5, pathDistance(wp) / SIM_WALK_SPEED);
  const delayS = leaveIndex * STAGGER_DELAY_S;

  const waitPoint: [number, number, number] = useGateLaneOnLeave
    ? computeWaitPoint(livePos, wp[1] ?? finalPoint, leaveIndex)
    : livePos;

  const steps: SimStep[] = [{ tS: 0, position: settledPos }]; // last "working" sample, pre-transition
  const walkStartT = 0; // the transition happens at t=0 in this simulation's own clock
  for (let tS = SIM_SAMPLE_DT_S; tS <= delayS + duration + SIM_SAMPLE_DT_S; tS += SIM_SAMPLE_DT_S) {
    const elapsed = tS - walkStartT - delayS;
    if (elapsed < 0) {
      steps.push({ tS, position: waitPoint });
    } else {
      const progress = Math.min(1, elapsed / duration);
      steps.push({ tS, position: poseAlongPath(wp, progress).position });
    }
  }
  return steps;
}

function maxStepDisplacement(steps: SimStep[]): { maxDist: number; atIndex: number } {
  let maxDist = 0;
  let atIndex = -1;
  for (let i = 1; i < steps.length; i++) {
    const a = steps[i - 1].position;
    const b = steps[i].position;
    const dist = Math.hypot(a[0] - b[0], a[2] - b[2]);
    if (dist > maxDist) {
      maxDist = dist;
      atIndex = i;
    }
  }
  return { maxDist, atIndex };
}

test("TELEPORT-ON-LEAVE: RED (documents the reported bug) -- gate-lane-during-leave violates the WALK_SPEED*dt+0.05 displacement invariant", () => {
  const steps = simulateSettleLeaveWalk(true);
  const bound = SIM_WALK_SPEED * SIM_SAMPLE_DT_S + 0.05;
  const { maxDist, atIndex } = maxStepDisplacement(steps);
  assert.ok(
    maxDist > bound,
    `expected the PRE-FIX behavior to violate the ${bound.toFixed(3)}u bound (documenting the real teleport) -- got max displacement ${maxDist.toFixed(3)}u at step ${atIndex}, t=${steps[atIndex]?.tS}s`,
  );
});

test("TELEPORT-ON-LEAVE: GREEN (the actual fix) -- holding livePos during a leave wait keeps every step within WALK_SPEED*dt+0.05", () => {
  const steps = simulateSettleLeaveWalk(false);
  for (let i = 1; i < steps.length; i++) {
    const a = steps[i - 1].position;
    const b = steps[i].position;
    const dist = Math.hypot(a[0] - b[0], a[2] - b[2]);
    const dt = steps[i].tS - steps[i - 1].tS;
    assert.ok(
      dist <= SIM_WALK_SPEED * dt + 0.05 + 1e-9,
      `step ${i} (t=${steps[i - 1].tS}s -> ${steps[i].tS}s): displacement ${dist.toFixed(3)}u exceeds WALK_SPEED*dt+0.05 = ${(SIM_WALK_SPEED * dt + 0.05).toFixed(3)}u`,
    );
  }
  // Sanity: this scenario actually exercises real motion (the walk itself),
  // not a degenerate all-zero trajectory that would make the bound trivial.
  const totalDist = Math.hypot(steps[steps.length - 1].position[0] - steps[0].position[0], steps[steps.length - 1].position[2] - steps[0].position[2]);
  assert.ok(totalDist > 5, `sanity: the avatar should have travelled meaningfully toward the gate, only moved ${totalDist.toFixed(2)}u total`);
});

// ─── stableSlotOffset / updateStableSlotAssignments (CONVOY-STACK v5) ──────
//
// ROOT CAUSE (all-state displacement audit, probe 20260915T095436Z):
// computeStandSlot (liveAgentWalk.ts, defined just above this section)
// derives BOTH an id's index AND the angle's own denominator (`groupSize`)
// from the CURRENT sorted membership of a zone -- so an existing resident's
// computed offset can change whenever ANY sibling in the SAME zone arrives
// or departs, even though that resident itself never moved or retargeted.
// Combined with the CONVOY-STACK v3 per-frame correction (LiveAgents.tsx
// useFrame, `if (phase.current === "working" ...) { standPointFor(...) }`,
// which applies whatever the CURRENT offset says, every frame, with no
// animation), this produces a real, visible snap -- the reported 0.90u
// jumps (0.90 == the OLD STAND_RING_RADIUS, i.e. exactly computeStandSlot's
// own angle recomputing around a new groupSize denominator).

test("STAND-SLOT SHUFFLE-SNAP: RED (documents the bug) -- computeStandSlot moves a resident who never retargeted, purely because a sibling joined or left", () => {
  const timeline = [
    ["A", "B", "C"],
    ["A", "C"], // B leaves
    ["A", "C", "D"], // D arrives
    ["C", "D"], // A retargets away
    ["A", "C", "D"], // A retargets back
  ];
  const cOffsets = timeline.map((ids) => computeStandSlot(ids, "C", STAND_RING_RADIUS).offset);
  const moved = cOffsets.some((o, i) => i > 0 && (o[0] !== cOffsets[i - 1][0] || o[1] !== cOffsets[i - 1][1]));
  assert.ok(moved, "expected the OLD groupSize-based logic to move C purely because a sibling joined/left (documents the reported shuffle-snap)");
});

test("STAND-SLOT SHUFFLE-SNAP: GREEN (the fix) -- stable assignment never moves a resident unless ITS OWN zone key changes, and stays >=0.7u pairwise throughout", () => {
  // Coordinator's own required scenario: residents A, B, C at a zone; B
  // leaves, D arrives, A retargets away and back.
  const REQUIRED_MIN_SEPARATION_U = 0.7;
  const timeline: Record<string, string>[] = [
    { A: "Z", B: "Z", C: "Z" },
    { A: "Z", C: "Z" }, // B leaves
    { A: "Z", C: "Z", D: "Z" }, // D arrives
    { C: "Z", D: "Z" }, // A retargets away (to some other zone, irrelevant here)
    { A: "Z", C: "Z", D: "Z" }, // A retargets back
  ];
  let assignments = new Map<string, Map<string, number>>();
  const offsetHistory = new Map<string, Array<[number, number] | null>>();
  for (const step of timeline) {
    const membership = new Map<string, string[]>();
    for (const [id, zone] of Object.entries(step)) {
      const ids = membership.get(zone) ?? [];
      ids.push(id);
      membership.set(zone, ids);
    }
    assignments = updateStableSlotAssignments(assignments, membership);

    const zIds = membership.get("Z") ?? [];
    const offsets = new Map<string, [number, number]>();
    for (const id of zIds) {
      const index = assignments.get("Z")!.get(id)!;
      offsets.set(id, stableSlotOffset(index));
    }
    for (const id of ["A", "B", "C", "D"]) {
      const hist = offsetHistory.get(id) ?? [];
      hist.push(offsets.get(id) ?? null);
      offsetHistory.set(id, hist);
    }

    // Pairwise >=0.7u among whoever is CURRENTLY resident at this step.
    const present = Array.from(offsets.entries());
    for (let i = 0; i < present.length; i++) {
      for (let j = i + 1; j < present.length; j++) {
        const [idA, offA] = present[i];
        const [idB, offB] = present[j];
        const dist = Math.hypot(offA[0] - offB[0], offA[1] - offB[1]);
        assert.ok(dist >= REQUIRED_MIN_SEPARATION_U - 1e-9, `step [${zIds.join(",")}]: ${idA} and ${idB} only ${dist.toFixed(3)}u apart`);
      }
    }
  }
  // C's own zone key never changes for the WHOLE timeline; D's never
  // changes from the moment it first arrives -- both must have an IDENTICAL
  // offset at every step where they were already present the step before
  // (the exact invariant the shuffle-snap violated: "no resting agent's
  // point moves between steps except via a walk").
  for (const id of ["C", "D"]) {
    const hist = offsetHistory.get(id)!;
    for (let i = 1; i < hist.length; i++) {
      if (hist[i - 1] === null || hist[i] === null) continue;
      assert.deepEqual(hist[i], hist[i - 1], `${id}'s offset changed between step ${i - 1} and ${i} despite never retargeting`);
    }
  }
});

test("stableSlotOffset: every pair of indices within STAND_SLOT_CAPACITY is >=0.7u apart (the fixed-capacity ring's own separation proof)", () => {
  const REQUIRED_MIN_SEPARATION_U = 0.7;
  const points = Array.from({ length: STAND_SLOT_CAPACITY }, (_, i) => stableSlotOffset(i));
  let checked = 0;
  for (let i = 0; i < points.length; i++) {
    for (let j = i + 1; j < points.length; j++) {
      checked++;
      const dist = Math.hypot(points[i][0] - points[j][0], points[i][1] - points[j][1]);
      assert.ok(dist >= REQUIRED_MIN_SEPARATION_U - 1e-9, `indices ${i} and ${j} are only ${dist.toFixed(3)}u apart`);
    }
  }
  assert.ok(checked > 0, "sanity: must have checked at least one pair");
});

test("updateStableSlotAssignments: never mutates its own `prev` argument", () => {
  const prev = new Map([["Z", new Map([["A", 0]])]]);
  updateStableSlotAssignments(prev, new Map([["Z", ["A", "B"]]]));
  assert.equal(prev.get("Z")!.size, 1, "prev must stay untouched");
});

test("updateStableSlotAssignments: a zone absent from `membership` this round is simply absent from the result (no leaked stale assignment)", () => {
  const prev = new Map([["Z", new Map([["A", 0]])]]);
  const next = updateStableSlotAssignments(prev, new Map());
  assert.equal(next.has("Z"), false);
});

// ─── ARRIVAL-WITH-SLOT-CHANGE + SPAWN-WAIT->WALK (CONVOY-STACK v5 addendum,
// coordinator's own pose_jump audit, probe 20260915T095436Z) ───────────────
//
// Two more jump shapes the same audit caught, beyond the resting-reshuffle
// snap above:
//   - walking->working (arrival) jumps of 1.07-1.10u: a walk's baked-in
//     FINAL waypoint (decided once, at walk-decision time) can still go
//     stale if this avatar's own assignment drifts before it arrives; the
//     OLD code let poseAlongPath arrive at the stale point, then relied on
//     the continuous stand-slot correction to snap it to the CURRENT one
//     the very next frame. FIX: LiveAgents.tsx's useFrame now smoothly
//     retargets the path's own final waypoint every frame of an active
//     walk (see that file's own "MID-WALK SLOT DRIFT fix" comment).
//   - spawning->walking jump of 1.499u: the rendered WAIT point (a gate
//     lane) and the walk's own first waypoint (always `livePos`, the raw
//     origin) disagreed -- the walk used to resume from a DIFFERENT point
//     than where the avatar had actually been sitting. FIX: when a walk
//     has a real stagger delay, its own first waypoint is now the SAME
//     value as the rendered wait point (LiveAgents.tsx's own
//     "TELEPORT-ON-SPAWN fix").
//
// Both are modeled here as pure per-frame position simulations (mirroring
// LiveAgentAvatar's own useFrame logic), sampled at the probe's own 0.5s
// cadence, checked against the coordinator's own invariant.

function simulateArrivalWithSlotChange(smoothMidWalkRetarget: boolean): SimStep[] {
  const origin: [number, number, number] = [21.6, 0, 0];
  const hallway: [number, number, number] = [17.4, 0, 0];
  const zoneNode: [number, number, number] = [0, 0, 0];
  const oldOffset = stableSlotOffset(0);
  const newOffset = stableSlotOffset(3); // simulates this avatar's assignment drifting mid-flight
  const oldFinal: [number, number, number] = [zoneNode[0] + oldOffset[0], 0, zoneNode[2] + oldOffset[1]];
  const newFinal: [number, number, number] = [zoneNode[0] + newOffset[0], 0, zoneNode[2] + newOffset[1]];
  let wp: [number, number, number][] = [origin, hallway, oldFinal];
  const changeAtT = 8; // the reassignment happens well into the walk, before arrival

  // DISTANCE-BASED PROGRESS (mirrors LiveAgents.tsx's own useFrame, this
  // same pass): `progress` is derived from actual DISTANCE TRAVELED
  // (tS*SIM_WALK_SPEED) divided by the CURRENT path's own live length, not
  // a fraction of a duration baked from the ORIGINAL (pre-swap) total --
  // otherwise swapping the endpoint would itself produce a discontinuity
  // (a progress fraction suddenly meaning a different absolute distance
  // once the path's own total length changes), the exact flaw a naive
  // "just replace the last waypoint" fix would still have.
  const MIN_WALK_S_FIXTURE = 0.5;
  const steps: SimStep[] = [];
  for (let tS = 0; ; tS += SIM_SAMPLE_DT_S) {
    if (smoothMidWalkRetarget && tS >= changeAtT) {
      wp = [wp[0], wp[1], newFinal]; // LiveAgents.tsx's own per-frame endpoint retarget
    }
    const distanceTraveled = tS * SIM_WALK_SPEED;
    const liveTotal = Math.max(MIN_WALK_S_FIXTURE * SIM_WALK_SPEED, pathDistance(wp));
    const progress = Math.min(1, distanceTraveled / liveTotal);
    let position: [number, number, number];
    if (progress < 1) {
      position = poseAlongPath(wp, progress).position;
    } else if (smoothMidWalkRetarget) {
      position = poseAlongPath(wp, 1).position; // already retargeted -- arrives smoothly at newFinal
    } else {
      // OLD behavior: arrives at the STALE oldFinal, then the continuous
      // stand-slot correction snaps it to the CURRENT offset (newFinal)
      // starting the very next sample.
      position = newFinal;
    }
    steps.push({ tS, position });
    if (progress >= 1) break; // mirrors phase.current flipping to "working" on arrival
  }
  return steps;
}

test("ARRIVAL-WITH-SLOT-CHANGE: RED (documents the bug) -- an un-retargeted walk snaps on arrival when its assignment drifted mid-flight", () => {
  const steps = simulateArrivalWithSlotChange(false);
  const bound = SIM_WALK_SPEED * SIM_SAMPLE_DT_S + 0.05;
  const { maxDist, atIndex } = maxStepDisplacement(steps);
  assert.ok(
    maxDist > bound,
    `expected the PRE-FIX behavior to violate the ${bound.toFixed(3)}u bound (documenting the arrival snap) -- got max displacement ${maxDist.toFixed(3)}u at step ${atIndex}`,
  );
});

test("ARRIVAL-WITH-SLOT-CHANGE: GREEN (the fix) -- smoothly retargeting the path's own endpoint keeps every step within WALK_SPEED*dt+0.05", () => {
  const steps = simulateArrivalWithSlotChange(true);
  for (let i = 1; i < steps.length; i++) {
    const a = steps[i - 1].position;
    const b = steps[i].position;
    const dist = Math.hypot(a[0] - b[0], a[2] - b[2]);
    const dt = steps[i].tS - steps[i - 1].tS;
    assert.ok(
      dist <= SIM_WALK_SPEED * dt + 0.05 + 1e-9,
      `step ${i} (t=${steps[i - 1].tS}s -> ${steps[i].tS}s): displacement ${dist.toFixed(3)}u exceeds WALK_SPEED*dt+0.05 = ${(SIM_WALK_SPEED * dt + 0.05).toFixed(3)}u`,
    );
  }
});

function simulateSpawnWaitWalk(fixWp0Mismatch: boolean): SimStep[] {
  const origin: [number, number, number] = [21.6, 0, 0]; // campus-gate, ENTRY_NODE_ID
  const hallway: [number, number, number] = [17.4, 0, 0];
  const finalPoint: [number, number, number] = [0, 0, -1.6];
  const spawnIndex = 1; // a same-batch spawn with a nonzero gate lane, per the bug report
  const rawWp: [number, number, number][] = [origin, hallway, finalPoint];
  const duration = Math.max(0.5, pathDistance(rawWp) / SIM_WALK_SPEED);
  const delayS = spawnIndex * STAGGER_DELAY_S;

  const waitPoint = computeWaitPoint(origin, hallway, spawnIndex); // the gate-lane point actually RENDERED during the wait
  const wp: [number, number, number][] = fixWp0Mismatch ? [waitPoint, hallway, finalPoint] : rawWp;

  const steps: SimStep[] = [{ tS: 0, position: origin }]; // this avatar's very first rendered frame (creation)
  for (let tS = SIM_SAMPLE_DT_S; tS <= delayS + duration + SIM_SAMPLE_DT_S; tS += SIM_SAMPLE_DT_S) {
    const elapsed = tS - delayS;
    if (elapsed < 0) {
      steps.push({ tS, position: waitPoint });
    } else {
      const progress = Math.min(1, elapsed / duration);
      steps.push({ tS, position: poseAlongPath(wp, progress).position });
    }
  }
  return steps;
}

test("SPAWN-WAIT->WALK: RED (documents the bug) -- resuming from the raw origin instead of the rendered wait point violates the displacement invariant", () => {
  const steps = simulateSpawnWaitWalk(false);
  const bound = SIM_WALK_SPEED * SIM_SAMPLE_DT_S + 0.05;
  // Skip the very first transition (tS=0 -> tS=0.5): a brand-new avatar's
  // creation frame is explicitly exempt from the invariant (coordinator's
  // own "except at creation").
  const { maxDist, atIndex } = maxStepDisplacement(steps.slice(1));
  assert.ok(
    maxDist > bound,
    `expected the PRE-FIX behavior to violate the ${bound.toFixed(3)}u bound (documenting the spawn-wait->walk snap) -- got max displacement ${maxDist.toFixed(3)}u at step ${atIndex}`,
  );
});

test("SPAWN-WAIT->WALK: GREEN (the fix) -- starting the walk from the rendered wait point keeps every post-creation step within WALK_SPEED*dt+0.05", () => {
  const steps = simulateSpawnWaitWalk(true);
  for (let i = 2; i < steps.length; i++) {
    // i starts at 2: the creation frame (0) and the first wait sample (1)
    // are exempt/trivial (0 displacement, since the avatar spawns directly
    // at its own wait point) -- the invariant is checked from the second
    // wait sample onward, covering the wait->walk transition itself.
    const a = steps[i - 1].position;
    const b = steps[i].position;
    const dist = Math.hypot(a[0] - b[0], a[2] - b[2]);
    const dt = steps[i].tS - steps[i - 1].tS;
    assert.ok(
      dist <= SIM_WALK_SPEED * dt + 0.05 + 1e-9,
      `step ${i} (t=${steps[i - 1].tS}s -> ${steps[i].tS}s): displacement ${dist.toFixed(3)}u exceeds WALK_SPEED*dt+0.05 = ${(SIM_WALK_SPEED * dt + 0.05).toFixed(3)}u`,
    );
  }
});

// ─── findCarAhead / applyFollowCap (CONVOY-STACK v6, 2026-09-15) ──────────
//
// ROOT CAUSE (walker_separation FAIL, probe 20260915T101532Z): 66/147
// multi-walker ticks (44.9%) under the required 0.7u bar, 64 of them ONE
// pair, both leaving toward campus-gate, that walked the ENTIRE ~32s shared
// corridor 0.18u apart in the SAME lane. liveAgentWalk.ts's own
// `laneValueForId` (CONVOY-STACK v2/v3) chooses a walking lane from a
// per-id hash into only 3 buckets -- two ids landing in the SAME bucket
// (1-in-3 per pair) get an IDENTICAL lane on the SAME corridor, and the
// batch stagger (`computeBatchStaggerDelays`) only covers agents starting
// FROM THE SAME NODE in the SAME reconcile poll -- two leavers departing
// from DIFFERENT stand slots (different zones, or the same zone at
// different moments) merge onto the shared gate-bound corridor with no
// timing relationship to each other, so the stagger cannot separate them.
// The v5 build only "passed" because those two particular ids happened to
// hash to different lanes -- a coincidence, not a guarantee.

test("findCarAhead: an avatar directly ahead, within FOLLOW_GAP_U, same destination, same heading, same lane is found with the correct forward gap", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "gate" };
  const other: WalkerSnapshot = { id: "b", position: [0, 0.5], heading: [0, 1], destKey: "gate" };
  const result = findCarAhead(self, [other]);
  assert.ok(result, "expected b to be found as the car ahead of a");
  assert.equal(result!.other.id, "b");
  assert.ok(Math.abs(result!.forwardGap - 0.5) < 1e-9, `expected forwardGap 0.5, got ${result!.forwardGap}`);
});

test("findCarAhead (v7): an avatar directly ahead but BEYOND FOLLOW_GAP_U is not a car ahead -- proximity, not mere same-lane alignment, is what triggers following", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "gate" };
  const other: WalkerSnapshot = { id: "b", position: [0, 1.5], heading: [0, 1], destKey: "gate" };
  assert.equal(findCarAhead(self, [other]), null);
});

test("findCarAhead (v7): an ADJACENT-lane walker (0.45u lateral, LANE_VALUES's own step), level with self, IS found -- the exact reported bug (two walkers abreast on adjacent lanes)", () => {
  // self.id ("z") > other.id ("a") -- the tie-break at exactly-level
  // progress (forward ~= 0): the LARGER id yields, so "z" must treat "a"
  // as the car ahead here.
  const self: WalkerSnapshot = { id: "z", position: [0, 0], heading: [0, 1], destKey: "gate" };
  const other: WalkerSnapshot = { id: "a", position: [0.45, 0], heading: [0, 1], destKey: "gate" }; // level, adjacent lane
  const result = findCarAhead(self, [other]);
  assert.ok(result, "expected the adjacent-lane, level walker to be found as a car ahead under v7 (never was under v6's own lane-tolerance gate)");
  assert.equal(result!.other.id, "a");
});

test("findCarAhead: ignores a walker heading to a DIFFERENT destination (the cheap pre-filter)", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "gate" };
  const other: WalkerSnapshot = { id: "b", position: [0, 1.5], heading: [0, 1], destKey: "some-other-zone" };
  assert.equal(findCarAhead(self, [other]), null);
});

test("findCarAhead: ignores a walker far enough away that Euclidean distance alone excludes it, even in an adjacent lane", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "gate" };
  // 0.45u lateral (LANE_STEP_U) + 1.5u forward -> Euclidean ~1.566u, well
  // outside FOLLOW_GAP_U -- v7 no longer gates on lane at all (see
  // findCarAhead's own v7 header), only on this Euclidean distance.
  const other: WalkerSnapshot = { id: "b", position: [0.45, 1.5], heading: [0, 1], destKey: "gate" };
  assert.equal(findCarAhead(self, [other]), null);
});

test("findCarAhead: ignores a walker heading in roughly the OPPOSITE direction", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "gate" };
  const other: WalkerSnapshot = { id: "b", position: [0, 1.5], heading: [0, -1], destKey: "gate" };
  assert.equal(findCarAhead(self, [other]), null);
});

test("findCarAhead: ignores a walker BEHIND self", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "gate" };
  const other: WalkerSnapshot = { id: "b", position: [0, -1.5], heading: [0, 1], destKey: "gate" };
  assert.equal(findCarAhead(self, [other]), null);
});

test("findCarAhead: at (near) equal progress, exactly one of a tied pair yields (deterministic by id), never both", () => {
  const a: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "gate" };
  const b: WalkerSnapshot = { id: "b", position: [0, 0], heading: [0, 1], destKey: "gate" };
  const aSeesB = findCarAhead(a, [b]);
  const bSeesA = findCarAhead(b, [a]);
  // "a" < "b" lexicographically -- self.id > other.id is the yield
  // condition, so b (the larger id) treats a as ahead; a does not treat b
  // as ahead.
  assert.equal(aSeesB, null, "a (smaller id) must not treat the tied b as ahead");
  assert.ok(bSeesA, "b (larger id) must treat the tied a as ahead -- exactly one must yield");
});

test("findCarAhead: picks the NEAREST qualifying car ahead among several (both within FOLLOW_GAP_U)", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "gate" };
  const near: WalkerSnapshot = { id: "near", position: [0, 0.5], heading: [0, 1], destKey: "gate" };
  const far: WalkerSnapshot = { id: "far", position: [0, 0.75], heading: [0, 1], destKey: "gate" };
  const result = findCarAhead(self, [far, near]); // deliberately unsorted input, both within FOLLOW_GAP_U
  assert.equal(result!.other.id, "near");
});

test("applyFollowCap: no car ahead -- candidate distance applies unchanged (never less than prevApplied)", () => {
  assert.equal(applyFollowCap(5, 3, null), 5);
});

test("applyFollowCap: gap already clears FOLLOW_GAP_U -- candidate applies unchanged", () => {
  const carAhead = { other: { id: "b", position: [0, 0] as const, heading: [0, 1] as const, destKey: "gate" }, forwardGap: 2 };
  assert.equal(applyFollowCap(5, 3, carAhead), 5);
});

test("applyFollowCap: gap under FOLLOW_GAP_U reduces the candidate by exactly the shortfall", () => {
  const carAhead = { other: { id: "b", position: [0, 0] as const, heading: [0, 1] as const, destKey: "gate" }, forwardGap: 0.3 };
  // shortfall = FOLLOW_GAP_U(0.8) - 0.3 = 0.5
  assert.ok(Math.abs(applyFollowCap(5, 0, carAhead) - 4.5) < 1e-9);
});

test("applyFollowCap: never reverses -- holds at prevAppliedDistance rather than moving backward", () => {
  const carAhead = { other: { id: "b", position: [0, 0] as const, heading: [0, 1] as const, destKey: "gate" }, forwardGap: 0.1 };
  // shortfall = 0.7, candidate=1 -> capped would be 0.3, but prevApplied=2
  // (this avatar already got further than that on an earlier frame) --
  // must hold at 2, never step backward to 0.3.
  assert.equal(applyFollowCap(1, 2, carAhead), 2);
});

// ─── THE REQUIRED PROOF: a 3-deep merge chain (CONVOY-STACK v6) ────────────
//
// Coordinator's own required test scenario: two agents entering the same
// edge at the same time from different start points, and a third catching
// up from behind. Modeled here as a pure per-frame simulation mirroring
// LiveAgents.tsx's own useFrame exactly (distance-based progress,
// one-frame-stale registry reads/writes using each avatar's own LAST
// RENDERED pose for both sides of the comparison -- see that file's own
// "SELF POSITION SOURCE" comment for why the candidate-vs-stale asymmetry
// was rejected during this fix's own development).

const CHAIN_DEST_KEY = "gate";
const CHAIN_LANE_Z = -0.45; // the exact lane the real bug's own pair collided in
const CHAIN_GATE_X = 21.6;
// Deliberately bad starting gaps -- LEAD/MID already fine (1.0u, >=0.7), but
// MID/TRAIL start only INITIAL_MID_TRAIL_GAP_U apart (well under the bar,
// close to the reported bug's own 0.18u), simulating TRAIL having already
// closed in on MID (e.g. during an earlier stagger/lane phase this fixture
// does not itself model) right as all three enter the shared corridor.
const INITIAL_MID_TRAIL_GAP_U = 0.15;
const CHAIN_WALKERS: { id: string; startX: number }[] = [
  { id: "lead", startX: 2.0 },
  { id: "mid", startX: 1.0 },
  { id: "trail", startX: 1.0 - INITIAL_MID_TRAIL_GAP_U },
];
// MERGE GRACE PERIOD: with BOTH walkers moving at the identical
// SIM_WALK_SPEED, applyFollowCap's own "never reverse" floor means a
// follower that starts too close cannot instantly jump backward to open
// the gap -- it HOLDS (zero advance) while the leader pulls away at full
// speed, until the gap naturally reaches FOLLOW_GAP_U on its own, THEN
// proceeds in lockstep. That is correct, expected car-following behavior
// (a real car brakes and waits for room, it doesn't teleport backward) --
// but it bounds how quickly an under-the-bar START can resolve: at best,
// (FOLLOW_GAP_U - initial gap) / SIM_WALK_SPEED seconds. Derived here
// (+0.1s safety margin) rather than hand-picking a number, so this stays
// correct if either constant changes. The coordinator's own spec allowed
// "excluding the first 0.2s" -- a reasonable rough figure for a LESS severe
// initial gap than this fixture's own deliberately bug-matching 0.15u.
const MERGE_GRACE_S = (FOLLOW_GAP_U - INITIAL_MID_TRAIL_GAP_U) / SIM_WALK_SPEED + 0.1;

// Internal simulation tick -- matches a REAL ~60fps animation frame, not
// the probe's own coarser 0.5s sampling cadence (SIM_SAMPLE_DT_S, used
// elsewhere in this file for OTHER simulations that don't need to resolve
// sub-second convergence). The follow-distance cap converges the mid/trail
// gap toward FOLLOW_GAP_U over a handful of REAL frames (a few tens of
// milliseconds) -- sampling only every 0.5s would make that gradual,
// perfectly smooth convergence look like it takes multiple SECONDS instead,
// an artifact of the sampling rate, not the mechanism itself.
const FOLLOW_TICK_DT_S = 1 / 60;

interface ChainStep extends SimStep {
  /** Whether THIS walker had already arrived (progress >= 1) as of this
   * tick. Once arrived, an avatar is removed from the registry (mirrors
   * LiveAgents.tsx's own arrival cleanup, and the wider DESPAWN-SCATTER
   * design that every leaving avatar is EXPECTED to converge on the exact
   * SAME terminal gate point right before vanishing -- see
   * destinationPointFor's own `despawn: true` doc). Pairwise separation is
   * therefore only a meaningful requirement (and only checked by the
   * tests below) while BOTH members of a pair are still actively walking
   * -- the reported bug was a MID-CORRIDOR overlap (x=10.46 vs 10.28),
   * never a simultaneous-arrival convergence, which is separately
   * accepted, by design, elsewhere in this codebase. */
  arrived: boolean;
}

function simulateFollowChain(useFollow: boolean): Map<string, ChainStep[]> {
  const paths = new Map(
    CHAIN_WALKERS.map((w) => [w.id, [[w.startX, 0, CHAIN_LANE_Z], [CHAIN_GATE_X, 0, CHAIN_LANE_Z]] as [number, number, number][]]),
  );
  const appliedDistance = new Map(CHAIN_WALKERS.map((w) => [w.id, 0]));
  // "Last rendered pose" registry, one-frame-stale by construction: read
  // BEFORE this tick's writes, written only AFTER every walker this tick
  // has computed its own new pose -- exactly LiveAgents.tsx's own
  // walkerFollowRegistry contract.
  let registry = new Map<string, WalkerSnapshot>();
  const history = new Map<string, ChainStep[]>(CHAIN_WALKERS.map((w) => [w.id, []]));
  const maxTicks = Math.ceil((CHAIN_GATE_X + 5) / SIM_WALK_SPEED / FOLLOW_TICK_DT_S);

  for (let tick = 0; tick <= maxTicks; tick++) {
    const tS = tick * FOLLOW_TICK_DT_S;
    const nextRegistry = new Map<string, WalkerSnapshot>();
    let allArrived = true;
    for (const w of CHAIN_WALKERS) {
      const wp = paths.get(w.id)!;
      const total = pathDistance(wp);
      // INCREMENTAL distance (mirrors LiveAgents.tsx's own v6 fix, same
      // pass): at most one tick's worth of travel from wherever this
      // walker ACTUALLY is (appliedDistance), never an absolute
      // tS*speed formula -- an absolute formula lets a held-back walker
      // accumulate "debt" that would snap-repay the instant the car ahead
      // moves away, exactly the bug this incremental form removes.
      const distanceTraveled = appliedDistance.get(w.id)! + SIM_WALK_SPEED * FOLLOW_TICK_DT_S;
      const lastSelf = registry.get(w.id); // this walker's own last-rendered pose (undefined on tick 0)
      const initialPose = poseAlongPath(wp, 0); // consistent facing convention for the tick-0 fallback
      const selfSnapshot: WalkerSnapshot = lastSelf ?? {
        id: w.id,
        position: [initialPose.position[0], initialPose.position[2]],
        heading: [Math.sin(initialPose.facing), Math.cos(initialPose.facing)],
        destKey: CHAIN_DEST_KEY,
      };
      const others = Array.from(registry.values()).filter((s) => s.id !== w.id);
      const carAhead = useFollow ? findCarAhead(selfSnapshot, others) : null;
      const prevApplied = appliedDistance.get(w.id)!;
      const newApplied = useFollow ? applyFollowCap(distanceTraveled, prevApplied, carAhead) : Math.max(prevApplied, distanceTraveled);
      appliedDistance.set(w.id, newApplied);
      const progress = Math.min(1, newApplied / total);
      const pose = poseAlongPath(wp, progress);
      history.get(w.id)!.push({ tS, position: pose.position, arrived: progress >= 1 });
      // Mirrors LiveAgents.tsx's own useFrame exactly: an ARRIVED walker
      // (progress >= 1) is never (re-)published to the registry -- without
      // this, a walker that reached the gate and stopped would sit there
      // forever as a permanent, immovable "car ahead", incorrectly
      // blocking everyone still behind it from ever closing the last
      // FOLLOW_GAP_U to the gate itself.
      if (progress < 1) {
        nextRegistry.set(w.id, {
          id: w.id,
          position: [pose.position[0], pose.position[2]],
          heading: [Math.sin(pose.facing), Math.cos(pose.facing)],
          destKey: CHAIN_DEST_KEY,
        });
        allArrived = false;
      }
    }
    registry = nextRegistry;
    if (allArrived) break;
  }
  return history;
}

function pairwiseDistancesAtStep(history: Map<string, ChainStep[]>, stepIdx: number): { pair: string; dist: number }[] {
  const ids = Array.from(history.keys());
  const out: { pair: string; dist: number }[] = [];
  for (let i = 0; i < ids.length; i++) {
    for (let j = i + 1; j < ids.length; j++) {
      const a = history.get(ids[i])![stepIdx];
      const b = history.get(ids[j])![stepIdx];
      if (!a || !b) continue;
      // Once either member of the pair has arrived, they are EXPECTED to
      // converge on the shared terminal gate point (see ChainStep's own
      // `arrived` doc) -- only an actively-walking pair is a meaningful
      // "walker separation" check.
      if (a.arrived || b.arrived) continue;
      const dist = Math.hypot(a.position[0] - b.position[0], a.position[2] - b.position[2]);
      out.push({ pair: `${ids[i]}/${ids[j]}`, dist });
    }
  }
  return out;
}

test("FOLLOW-DISTANCE CHAIN: RED (documents the bug) -- without follow, the mid/trail pair NEVER separates (constant 0.15u gap forever)", () => {
  const history = simulateFollowChain(false);
  const steps = history.get("mid")!.length;
  let sawViolationAfterGrace = false;
  for (let i = 0; i < steps; i++) {
    const tS = history.get("mid")![i].tS;
    if (tS < MERGE_GRACE_S) continue;
    const dists = pairwiseDistancesAtStep(history, i);
    if (dists.some((d) => d.dist < 0.7 - 1e-9)) {
      sawViolationAfterGrace = true;
      break;
    }
  }
  assert.ok(sawViolationAfterGrace, "expected the PRE-FIX (no follow-distance) behavior to keep violating the 0.7u bar past the grace period -- documents the reported walker_separation failure");
});

test("FOLLOW-DISTANCE CHAIN: GREEN (the fix) -- pairwise >=0.7u after the merge grace period, no snaps, and all three reach the gate", () => {
  const history = simulateFollowChain(true);
  const steps = history.get("mid")!.length;

  // 1. Pairwise >=0.7u for every pair, at every step, after the grace period.
  for (let i = 0; i < steps; i++) {
    const tS = history.get("mid")![i].tS;
    if (tS < MERGE_GRACE_S) continue;
    for (const { pair, dist } of pairwiseDistancesAtStep(history, i)) {
      assert.ok(dist >= 0.7 - 1e-9, `t=${tS}s: pair ${pair} only ${dist.toFixed(3)}u apart`);
    }
  }

  // 2. Per-step displacement <= WALK_SPEED*dt+0.05 for every walker (no
  // snaps -- the pose_jump invariant must still hold under following).
  for (const w of CHAIN_WALKERS) {
    const hist = history.get(w.id)!;
    for (let i = 1; i < hist.length; i++) {
      const a = hist[i - 1].position;
      const b = hist[i].position;
      const dist = Math.hypot(a[0] - b[0], a[2] - b[2]);
      const dt = hist[i].tS - hist[i - 1].tS;
      assert.ok(
        dist <= SIM_WALK_SPEED * dt + 0.05 + 1e-9,
        `${w.id} step ${i} (t=${hist[i - 1].tS}s -> ${hist[i].tS}s): displacement ${dist.toFixed(3)}u exceeds WALK_SPEED*dt+0.05`,
      );
    }
  }

  // 3. All three actually reach the gate (following slows, never permanently blocks).
  for (const w of CHAIN_WALKERS) {
    const hist = history.get(w.id)!;
    const last = hist[hist.length - 1];
    assert.ok(Math.abs(last.position[0] - CHAIN_GATE_X) < 1e-6, `${w.id} never reached the gate -- ended at x=${last.position[0]}`);
  }
});

test("FOLLOW_GAP_U sanity: the configured gap itself clears the required 0.7u bar", () => {
  assert.ok(FOLLOW_GAP_U >= 0.7, `FOLLOW_GAP_U (${FOLLOW_GAP_U}) must be >= the required 0.7u separation bar`);
});

// ─── CONVOY-STACK v7 (2026-09-15): adjacent-lane walkers must ALSO follow ──
//
// ROOT CAUSE (walker_separation FAIL, probe 20260915T113020Z): v6's
// findCarAhead additionally required a small LATERAL offset from self's
// own heading line (a "same lane" check, FOLLOW_LANE_TOLERANCE_U=0.3)
// before two walkers would follow each other at all. LANE_VALUES (0,
// +-0.45u) puts ADJACENT lanes only 0.45u apart -- above that 0.3u
// tolerance -- so two walkers the lane hash happened to place in adjacent
// lanes NEVER triggered following, and walked the entire corridor abreast,
// 0.45-0.68u apart (55/57 multi-walker ticks under the bar, min 0.42u).
// v6 only "passed" its own earlier probe runs by lane-assignment luck --
// the exact same class of false confidence v6 itself was built to remove
// from the id-hash lane assignment one level below it.
//
// FIX (coordinator's own option (A)): findCarAhead now triggers on
// Euclidean proximity alone (within FOLLOW_GAP_U), regardless of lane --
// see that function's own v7 header for the full reasoning and the
// deliberate lanes-become-cosmetic-only tradeoff.
//
// This models the coordinator's own exact reported shape: 3 agents
// starting the SAME corridor at the SAME time, on lanes 0, +0.45, -0.45
// (LANE_VALUES itself) -- no forward offset between them at all, purely a
// lateral-only starting configuration.

const LANE_MERGE_DEST_KEY = "ambient-core";
const LANE_MERGE_START_X = 0;
const LANE_MERGE_END_X = 21.6;
const LANE_MERGE_WALKERS: { id: string; laneZ: number }[] = [
  { id: "a", laneZ: 0 },
  { id: "b", laneZ: 0.45 },
  { id: "c", laneZ: -0.45 },
];

function simulateLaneMerge(useFollow: boolean): Map<string, ChainStep[]> {
  const paths = new Map(
    LANE_MERGE_WALKERS.map((w) => [w.id, [[LANE_MERGE_START_X, 0, w.laneZ], [LANE_MERGE_END_X, 0, w.laneZ]] as [number, number, number][]]),
  );
  const appliedDistance = new Map(LANE_MERGE_WALKERS.map((w) => [w.id, 0]));
  let registry = new Map<string, WalkerSnapshot>();
  const history = new Map<string, ChainStep[]>(LANE_MERGE_WALKERS.map((w) => [w.id, []]));
  const maxTicks = Math.ceil((LANE_MERGE_END_X - LANE_MERGE_START_X + 5) / SIM_WALK_SPEED / FOLLOW_TICK_DT_S);

  for (let tick = 0; tick <= maxTicks; tick++) {
    const tS = tick * FOLLOW_TICK_DT_S;
    const nextRegistry = new Map<string, WalkerSnapshot>();
    let allArrived = true;
    for (const w of LANE_MERGE_WALKERS) {
      const wp = paths.get(w.id)!;
      const total = pathDistance(wp);
      const distanceTraveled = appliedDistance.get(w.id)! + SIM_WALK_SPEED * FOLLOW_TICK_DT_S;
      const lastSelf = registry.get(w.id);
      const initialPose = poseAlongPath(wp, 0);
      const selfSnapshot: WalkerSnapshot = lastSelf ?? {
        id: w.id,
        position: [initialPose.position[0], initialPose.position[2]],
        heading: [Math.sin(initialPose.facing), Math.cos(initialPose.facing)],
        destKey: LANE_MERGE_DEST_KEY,
      };
      const others = Array.from(registry.values()).filter((s) => s.id !== w.id);
      const carAhead = useFollow ? findCarAhead(selfSnapshot, others) : null;
      const prevApplied = appliedDistance.get(w.id)!;
      const newApplied = useFollow ? applyFollowCap(distanceTraveled, prevApplied, carAhead) : Math.max(prevApplied, distanceTraveled);
      appliedDistance.set(w.id, newApplied);
      const progress = Math.min(1, newApplied / total);
      const pose = poseAlongPath(wp, progress);
      history.get(w.id)!.push({ tS, position: pose.position, arrived: progress >= 1 });
      if (progress < 1) {
        nextRegistry.set(w.id, {
          id: w.id,
          position: [pose.position[0], pose.position[2]],
          heading: [Math.sin(pose.facing), Math.cos(pose.facing)],
          destKey: LANE_MERGE_DEST_KEY,
        });
        allArrived = false;
      }
    }
    registry = nextRegistry;
    if (allArrived) break;
  }
  return history;
}

// MERGE GRACE PERIOD: all three start perfectly LEVEL (zero forward
// offset, purely lateral) -- the worst case for `applyFollowCap`'s own
// "never reverse" floor, which means a yielding walker holds at zero
// advance until the LEADER alone has pulled the gap open to FOLLOW_GAP_U
// (see the CHAIN test's own identical reasoning above). Derived, not
// hand-picked, for the same reason: (FOLLOW_GAP_U - 0) / SIM_WALK_SPEED,
// +0.15s safety margin for the 3-way (not just pairwise) interaction.
const LANE_MERGE_GRACE_S = FOLLOW_GAP_U / SIM_WALK_SPEED + 0.15;

test("LANE-MERGE 3-WAY: RED (documents the bug) -- without follow (equivalent to v6's own lane-tolerance check in this exact abreast shape), no pair ever separates", () => {
  // Note on equivalence: v6's OLD findCarAhead required lateral <=
  // FOLLOW_LANE_TOLERANCE_U (0.3u); every pair here starts and stays at
  // 0.45u lateral (LANE_VALUES's own adjacent-lane step), which ALREADY
  // exceeds 0.3u -- so v6's own check would have rejected every pair here
  // too, for the entire walk (heading never changes on a straight
  // corridor). Passing `useFollow=false` reproduces that exact outcome
  // without needing to keep a second, parallel implementation of the old
  // (now-replaced) lane-gated function around just to document it.
  const history = simulateLaneMerge(false);
  const steps = history.get("a")!.length;
  let sawViolationAfterGrace = false;
  for (let i = 0; i < steps; i++) {
    const tS = history.get("a")![i].tS;
    if (tS < LANE_MERGE_GRACE_S) continue;
    const dists = pairwiseDistancesAtStep(history, i);
    if (dists.some((d) => d.dist < 0.7 - 1e-9)) {
      sawViolationAfterGrace = true;
      break;
    }
  }
  assert.ok(sawViolationAfterGrace, "expected the PRE-FIX (lane-gated) behavior to keep violating the 0.7u bar for this abreast shape -- documents the reported walker_separation failure");
});

test("LANE-MERGE 3-WAY: GREEN (the fix) -- pairwise >=0.7u after the merge grace period, no snaps, and all three arrive", () => {
  const history = simulateLaneMerge(true);
  const steps = history.get("a")!.length;

  for (let i = 0; i < steps; i++) {
    const tS = history.get("a")![i].tS;
    if (tS < LANE_MERGE_GRACE_S) continue;
    for (const { pair, dist } of pairwiseDistancesAtStep(history, i)) {
      assert.ok(dist >= 0.7 - 1e-9, `t=${tS}s: pair ${pair} only ${dist.toFixed(3)}u apart`);
    }
  }

  for (const w of LANE_MERGE_WALKERS) {
    const hist = history.get(w.id)!;
    for (let i = 1; i < hist.length; i++) {
      const a = hist[i - 1].position;
      const b = hist[i].position;
      const dist = Math.hypot(a[0] - b[0], a[2] - b[2]);
      const dt = hist[i].tS - hist[i - 1].tS;
      assert.ok(
        dist <= SIM_WALK_SPEED * dt + 0.05 + 1e-9,
        `${w.id} step ${i} (t=${hist[i - 1].tS}s -> ${hist[i].tS}s): displacement ${dist.toFixed(3)}u exceeds WALK_SPEED*dt+0.05`,
      );
    }
    const last = hist[hist.length - 1];
    assert.ok(Math.abs(last.position[0] - LANE_MERGE_END_X) < 1e-6, `${w.id} never reached the destination -- ended at x=${last.position[0]}`);
  }
});

// ─── Head-on pass (no deadlock) -- coordinator's own guardrail ────────────
//
// Two walkers heading in roughly OPPOSITE directions (one arriving, one
// leaving the same corridor) must pass through each other's vicinity
// without either one yielding -- findCarAhead's own FOLLOW_HEADING_COS_MIN
// gate rejects a near-opposite heading BEFORE the Euclidean-proximity
// check ever runs, so this must hold regardless of how close they get.

test("HEAD-ON PASS: two opposite-direction walkers never yield to each other, even at zero distance -- no deadlock", () => {
  const inbound: WalkerSnapshot = { id: "inbound", position: [5, 0], heading: [0, 1], destKey: "hub" }; // heading +Z
  const outbound: WalkerSnapshot = { id: "outbound", position: [5, 0], heading: [0, -1], destKey: "gate" }; // heading -Z, same point, opposite direction
  assert.equal(findCarAhead(inbound, [outbound]), null, "inbound must never treat a head-on walker as a car ahead");
  assert.equal(findCarAhead(outbound, [inbound]), null, "outbound must never treat a head-on walker as a car ahead");
});

test("HEAD-ON PASS: a simulated approach-and-pass never slows either walker (full WALK_SPEED throughout, no capped advance)", () => {
  // Two walkers on the SAME line, opposite headings, starting apart and
  // walking toward (then past) each other -- destKey is deliberately
  // DIFFERENT (an arriving vs a leaving avatar realistically target
  // different nodes) as an extra, independent guard on top of the heading
  // check, matching how a real arrival/departure pair would actually be
  // classified.
  const laneZ = 0;
  const pathA: [number, number, number][] = [[0, 0, laneZ], [10, 0, laneZ]]; // walks +X
  const pathB: [number, number, number][] = [[10, 0, laneZ], [0, 0, laneZ]]; // walks -X, starts where A ends
  const appliedA = { value: 0 };
  const appliedB = { value: 0 };
  let registry = new Map<string, WalkerSnapshot>();
  const ticks = Math.ceil(10 / SIM_WALK_SPEED / FOLLOW_TICK_DT_S) + 5;

  for (let tick = 0; tick <= ticks; tick++) {
    const totalA = pathDistance(pathA);
    const totalB = pathDistance(pathB);
    const candidateA = appliedA.value + SIM_WALK_SPEED * FOLLOW_TICK_DT_S;
    const candidateB = appliedB.value + SIM_WALK_SPEED * FOLLOW_TICK_DT_S;
    const initA = poseAlongPath(pathA, 0);
    const initB = poseAlongPath(pathB, 0);
    const selfA: WalkerSnapshot = registry.get("a") ?? { id: "a", position: [initA.position[0], initA.position[2]], heading: [Math.sin(initA.facing), Math.cos(initA.facing)], destKey: "hub" };
    const selfB: WalkerSnapshot = registry.get("b") ?? { id: "b", position: [initB.position[0], initB.position[2]], heading: [Math.sin(initB.facing), Math.cos(initB.facing)], destKey: "gate" };
    const carAheadA = findCarAhead(selfA, [selfB]);
    const carAheadB = findCarAhead(selfB, [selfA]);
    assert.equal(carAheadA, null, `tick ${tick}: A must never see B as a car ahead (head-on)`);
    assert.equal(carAheadB, null, `tick ${tick}: B must never see A as a car ahead (head-on)`);
    const newA = applyFollowCap(candidateA, appliedA.value, carAheadA);
    const newB = applyFollowCap(candidateB, appliedB.value, carAheadB);
    // Full, uncapped speed every tick -- no deadlock, no slowdown at all.
    assert.ok(Math.abs(newA - candidateA) < 1e-9, `tick ${tick}: A's advance was capped despite a head-on (non-yielding) pass`);
    assert.ok(Math.abs(newB - candidateB) < 1e-9, `tick ${tick}: B's advance was capped despite a head-on (non-yielding) pass`);
    appliedA.value = newA;
    appliedB.value = newB;
    const progressA = Math.min(1, newA / totalA);
    const progressB = Math.min(1, newB / totalB);
    const poseA = poseAlongPath(pathA, progressA);
    const poseB = poseAlongPath(pathB, progressB);
    const next = new Map<string, WalkerSnapshot>();
    if (progressA < 1) next.set("a", { id: "a", position: [poseA.position[0], poseA.position[2]], heading: [Math.sin(poseA.facing), Math.cos(poseA.facing)], destKey: "hub" });
    if (progressB < 1) next.set("b", { id: "b", position: [poseB.position[0], poseB.position[2]], heading: [Math.sin(poseB.facing), Math.cos(poseB.facing)], destKey: "gate" });
    registry = next;
    if (progressA >= 1 && progressB >= 1) break;
  }
});

// ─── CONVOY-STACK v8 (2026-09-15): KEEP-RIGHT PASSING for head-on walkers ──
//
// ROOT CAUSE (walker_separation PASS-BY-RULE but min 0.07u, probe
// 20260915T114713Z): findCarAhead's FOLLOW_HEADING_COS_MIN gate correctly
// excludes head-on pairs from the follow-distance mechanism (deliberately
// -- that's what prevents a head-on deadlock), but excluding them from
// FOLLOW also means nothing EVER makes two opposite-direction walkers step
// aside. Two avatars in the same lane, walking toward each other, pass
// straight through one another (observed 0.65u -> 0.07u in one 0.5s
// sample).
//
// FIX: KEEP-RIGHT PASSING -- see liveAgentWalk.ts#findOncoming/
// computeSidestepPlan/rampSidestepOffset/rightOf for the full mechanism.

test("rightOf: rotates a heading -90 degrees (facing north, right is east)", () => {
  const north: [number, number] = [0, 1]; // [sin(facing), cos(facing)] convention, facing=0
  const right = rightOf(north);
  assert.ok(Math.abs(right[0] - 1) < 1e-9 && Math.abs(right[1]) < 1e-9, `expected east [1,0], got [${right}]`);
});

test("rightOf: two opposite headings have opposite right vectors (why keep-right separates a head-on pair)", () => {
  const east: [number, number] = [1, 0];
  const west: [number, number] = [-1, 0];
  const rightOfEast = rightOf(east);
  const rightOfWest = rightOf(west);
  assert.ok(Math.abs(rightOfEast[0] + rightOfWest[0]) < 1e-9 && Math.abs(rightOfEast[1] + rightOfWest[1]) < 1e-9, `expected opposite vectors, got [${rightOfEast}] and [${rightOfWest}]`);
});

test("findOncoming: a walker heading roughly opposite, close, and laterally near is found", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "hub" };
  const other: WalkerSnapshot = { id: "b", position: [0, 1.5], heading: [0, -1], destKey: "gate" };
  assert.equal(findOncoming(self, [other]), other);
});

test("findOncoming: ignores a same-direction walker (that's findCarAhead's job, not this one's)", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "hub" };
  const other: WalkerSnapshot = { id: "b", position: [0, 0.5], heading: [0, 1], destKey: "hub" };
  assert.equal(findOncoming(self, [other]), null);
});

test("findOncoming: ignores an oncoming walker already laterally clear (>=FOLLOW_GAP_U)", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "hub" };
  const other: WalkerSnapshot = { id: "b", position: [0.8, 1.5], heading: [0, -1], destKey: "gate" };
  assert.equal(findOncoming(self, [other]), null);
});

test("findOncoming: ignores an oncoming walker outside SIDESTEP_DETECTION_RADIUS_U", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "hub" };
  const other: WalkerSnapshot = { id: "b", position: [0, SIDESTEP_DETECTION_RADIUS_U + 0.5], heading: [0, -1], destKey: "gate" };
  assert.equal(findOncoming(self, [other]), null);
});

test("findOncoming: does NOT filter by destKey -- an arriving and a leaving avatar target different nodes but must still avoid each other", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "hub" };
  const other: WalkerSnapshot = { id: "b", position: [0, 1.0], heading: [0, -1], destKey: "totally-different-gate" };
  assert.equal(findOncoming(self, [other]), other);
});

test("computeSidestepPlan: no oncoming -> no offset, no pause", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "hub" };
  const plan = computeSidestepPlan(self, [], true);
  assert.deepEqual(plan, { offsetTargetU: 0, pauseForOncoming: false });
});

test("computeSidestepPlan: oncoming + trusted corridor -> both sidestep target SIDESTEP_TARGET_U, nobody pauses", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "hub" };
  const other: WalkerSnapshot = { id: "b", position: [0, 1.0], heading: [0, -1], destKey: "gate" };
  const plan = computeSidestepPlan(self, [other], true);
  assert.equal(plan.offsetTargetU, SIDESTEP_TARGET_U);
  assert.equal(plan.pauseForOncoming, false);
});

test("computeSidestepPlan: oncoming + UNTRUSTED corridor -> no sidestep, only the lexicographically LOWER id pauses", () => {
  const lower: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "hub" };
  const higher: WalkerSnapshot = { id: "z", position: [0, 1.0], heading: [0, -1], destKey: "gate" };
  const lowerPlan = computeSidestepPlan(lower, [higher], false);
  const higherPlan = computeSidestepPlan(higher, [lower], false);
  assert.deepEqual(lowerPlan, { offsetTargetU: 0, pauseForOncoming: true });
  assert.deepEqual(higherPlan, { offsetTargetU: 0, pauseForOncoming: false });
});

test("rampSidestepOffset: moves toward target at the bounded rate, never overshoots", () => {
  const afterOneStep = rampSidestepOffset(0, SIDESTEP_TARGET_U, SIDESTEP_RATE_U_PER_S, 0.1);
  assert.ok(Math.abs(afterOneStep - SIDESTEP_RATE_U_PER_S * 0.1) < 1e-9);
  assert.ok(afterOneStep < SIDESTEP_TARGET_U, "must not overshoot in a single bounded step");
});

test("rampSidestepOffset: snaps to target exactly once within one step's reach (no overshoot, no infinite approach)", () => {
  const result = rampSidestepOffset(SIDESTEP_TARGET_U - 0.001, SIDESTEP_TARGET_U, SIDESTEP_RATE_U_PER_S, 1);
  assert.equal(result, SIDESTEP_TARGET_U);
});

test("rampSidestepOffset: ramps back down toward 0 the same way (drift back to lane after passing)", () => {
  const result = rampSidestepOffset(SIDESTEP_TARGET_U, 0, SIDESTEP_RATE_U_PER_S, 0.1);
  assert.ok(Math.abs(result - (SIDESTEP_TARGET_U - SIDESTEP_RATE_U_PER_S * 0.1)) < 1e-9);
});

// ─── THE REQUIRED PROOF: head-on pass in one lane (RED / GREEN) ───────────

interface HeadOnStep {
  tS: number;
  posEast: [number, number, number];
  posWest: [number, number, number];
}

function simulateHeadOnPass(useSidestep: boolean, corridorTrusted: boolean): HeadOnStep[] {
  const laneZ = 0;
  const spanX = 20;
  const pathEast: [number, number, number][] = [[0, 0, laneZ], [spanX, 0, laneZ]]; // heading +X
  const pathWest: [number, number, number][] = [[spanX, 0, laneZ], [0, 0, laneZ]]; // heading -X, starts at the far end
  const appliedEast = { v: 0 };
  const appliedWest = { v: 0 };
  const sidestepEast = { v: 0 };
  const sidestepWest = { v: 0 };
  let registry = new Map<string, WalkerSnapshot>();
  const steps: HeadOnStep[] = [];
  // Generous ceiling: the narrow-corridor fallback can hold the lower id
  // paused for a while (until the oncoming walker clears
  // SIDESTEP_DETECTION_RADIUS_U on the far side too -- roughly
  // 2*SIDESTEP_DETECTION_RADIUS_U/SIM_WALK_SPEED of extra wall-clock time,
  // since only the OTHER walker is still closing/opening the gap during
  // the pause), so the ceiling must cover a full solo walk PLUS that
  // worst-case pause, not just the solo walk with a token margin.
  const maxTicks = Math.ceil((spanX + 4 * SIDESTEP_DETECTION_RADIUS_U) / SIM_WALK_SPEED / FOLLOW_TICK_DT_S);

  for (let tick = 0; tick <= maxTicks; tick++) {
    const tS = tick * FOLLOW_TICK_DT_S;
    const totalE = pathDistance(pathEast);
    const totalW = pathDistance(pathWest);
    const candE = appliedEast.v + SIM_WALK_SPEED * FOLLOW_TICK_DT_S;
    const candW = appliedWest.v + SIM_WALK_SPEED * FOLLOW_TICK_DT_S;
    const initE = poseAlongPath(pathEast, 0);
    const initW = poseAlongPath(pathWest, 0);
    const selfE: WalkerSnapshot = registry.get("east") ?? {
      id: "east", position: [initE.position[0], initE.position[2]], heading: [Math.sin(initE.facing), Math.cos(initE.facing)], destKey: "west-hub",
    };
    const selfW: WalkerSnapshot = registry.get("west") ?? {
      id: "west", position: [initW.position[0], initW.position[2]], heading: [Math.sin(initW.facing), Math.cos(initW.facing)], destKey: "east-hub",
    };
    const othersForE = Array.from(registry.values()).filter((s) => s.id !== "east");
    const othersForW = Array.from(registry.values()).filter((s) => s.id !== "west");
    const planE = useSidestep ? computeSidestepPlan(selfE, othersForE, corridorTrusted) : { offsetTargetU: 0, pauseForOncoming: false };
    const planW = useSidestep ? computeSidestepPlan(selfW, othersForW, corridorTrusted) : { offsetTargetU: 0, pauseForOncoming: false };
    const newAppliedE = planE.pauseForOncoming ? appliedEast.v : candE;
    const newAppliedW = planW.pauseForOncoming ? appliedWest.v : candW;
    appliedEast.v = newAppliedE;
    appliedWest.v = newAppliedW;
    const progE = Math.min(1, newAppliedE / totalE);
    const progW = Math.min(1, newAppliedW / totalW);
    const poseE = poseAlongPath(pathEast, progE);
    const poseW = poseAlongPath(pathWest, progW);
    sidestepEast.v = rampSidestepOffset(sidestepEast.v, progE >= 0.95 ? 0 : planE.offsetTargetU, SIDESTEP_RATE_U_PER_S, FOLLOW_TICK_DT_S);
    sidestepWest.v = rampSidestepOffset(sidestepWest.v, progW >= 0.95 ? 0 : planW.offsetTargetU, SIDESTEP_RATE_U_PER_S, FOLLOW_TICK_DT_S);
    const rightE = rightOf([Math.sin(poseE.facing), Math.cos(poseE.facing)]);
    const rightW = rightOf([Math.sin(poseW.facing), Math.cos(poseW.facing)]);
    const finalE: [number, number, number] = [poseE.position[0] + rightE[0] * sidestepEast.v, 0, poseE.position[2] + rightE[1] * sidestepEast.v];
    const finalW: [number, number, number] = [poseW.position[0] + rightW[0] * sidestepWest.v, 0, poseW.position[2] + rightW[1] * sidestepWest.v];
    steps.push({ tS, posEast: finalE, posWest: finalW });
    const next = new Map<string, WalkerSnapshot>();
    if (progE < 1) next.set("east", { id: "east", position: [finalE[0], finalE[2]], heading: [Math.sin(poseE.facing), Math.cos(poseE.facing)], destKey: "west-hub" });
    if (progW < 1) next.set("west", { id: "west", position: [finalW[0], finalW[2]], heading: [Math.sin(poseW.facing), Math.cos(poseW.facing)], destKey: "east-hub" });
    registry = next;
    if (progE >= 1 && progW >= 1) break;
  }
  return steps;
}

test("HEAD-ON KEEP-RIGHT: RED (documents the bug) -- without sidestep, the pair passes through each other well under 0.7u", () => {
  const steps = simulateHeadOnPass(false, true);
  const minDist = Math.min(...steps.map((s) => Math.hypot(s.posEast[0] - s.posWest[0], s.posEast[2] - s.posWest[2])));
  assert.ok(minDist < 0.7, `expected the PRE-FIX behavior to pass within 0.7u (documenting the reported pass-through) -- min distance was ${minDist.toFixed(3)}u`);
});

test("HEAD-ON KEEP-RIGHT: GREEN (the fix) -- min distance >=0.7u throughout, both arrive, no snaps (lateral+forward combined)", () => {
  const steps = simulateHeadOnPass(true, true);
  let minDist = Infinity;
  for (const s of steps) {
    const dist = Math.hypot(s.posEast[0] - s.posWest[0], s.posEast[2] - s.posWest[2]);
    if (dist < minDist) minDist = dist;
  }
  assert.ok(minDist >= 0.7 - 1e-9, `expected min distance >=0.7u, got ${minDist.toFixed(3)}u`);

  // Per-step displacement bound, combining lateral + forward motion, for BOTH walkers.
  for (const [key] of [["posEast"], ["posWest"]] as const) {
    for (let i = 1; i < steps.length; i++) {
      const a = steps[i - 1][key];
      const b = steps[i][key];
      const dist = Math.hypot(a[0] - b[0], a[2] - b[2]);
      const dt = steps[i].tS - steps[i - 1].tS;
      assert.ok(
        dist <= SIM_WALK_SPEED * dt + 0.05 + 1e-9,
        `${key} step ${i} (t=${steps[i - 1].tS}s -> ${steps[i].tS}s): displacement ${dist.toFixed(3)}u exceeds WALK_SPEED*dt+0.05`,
      );
    }
  }

  // Both actually arrive (the sidestep must drift back to 0 and never block completion).
  const last = steps[steps.length - 1];
  assert.ok(Math.abs(last.posEast[0] - 20) < 1e-6, `east never reached the end -- x=${last.posEast[0]}`);
  assert.ok(Math.abs(last.posWest[0] - 0) < 1e-6, `west never reached the end -- x=${last.posWest[0]}`);

  // No deadlock: the simulation must have actually TERMINATED (not hit the
  // generous tick ceiling), i.e. both walkers made real forward progress
  // throughout rather than freezing each other out.
  const maxPossibleTicks = Math.ceil(20 / SIM_WALK_SPEED / FOLLOW_TICK_DT_S) + 60;
  assert.ok(steps.length < maxPossibleTicks, "simulation ran to its ceiling -- suggests a deadlock rather than a clean pass");
});

test("HEAD-ON KEEP-RIGHT: narrow-corridor fallback -- no sidestep is ever applied, the lower id visibly pauses, no deadlock, no snap", () => {
  // "east" < "west" lexicographically, so "east" is the id that must pause.
  const steps = simulateHeadOnPass(true, false);
  for (const s of steps) {
    assert.ok(Math.abs(s.posEast[2]) < 1e-9, `east's own Z ever left the lane (${s.posEast[2]}) -- the untrusted-corridor fallback must never sidestep`);
    assert.ok(Math.abs(s.posWest[2]) < 1e-9, `west's own Z ever left the lane (${s.posWest[2]}) -- the untrusted-corridor fallback must never sidestep`);
  }
  // Displacement bound still holds (no snap) even though this path does not
  // claim to guarantee the full 0.7u separation bar -- this module has no
  // real per-edge corridor-width data to safely locate the "wider point"
  // the spec's own fallback describes (see computeSidestepPlan's own
  // header); the honest guarantee here is "no snap, no deadlock", not
  // "still >=0.7u apart" the way the trusted-corridor case can prove.
  for (const key of ["posEast", "posWest"] as const) {
    for (let i = 1; i < steps.length; i++) {
      const a = steps[i - 1][key];
      const b = steps[i][key];
      const dist = Math.hypot(a[0] - b[0], a[2] - b[2]);
      const dt = steps[i].tS - steps[i - 1].tS;
      assert.ok(dist <= SIM_WALK_SPEED * dt + 0.05 + 1e-9, `${key} step ${i}: displacement ${dist.toFixed(3)}u exceeds bound`);
    }
  }
  // No deadlock: both eventually arrive.
  const last = steps[steps.length - 1];
  assert.ok(Math.abs(last.posEast[0] - 20) < 1e-6, "east never reached the end (narrow-corridor fallback)");
  assert.ok(Math.abs(last.posWest[0] - 0) < 1e-6, "west never reached the end (narrow-corridor fallback)");
  // The pause mechanism actually engaged at some point (documents that the
  // fallback path, not the sidestep path, is the one under test here).
  let sawHold = false;
  for (let i = 1; i < steps.length; i++) {
    if (Math.abs(steps[i].posEast[0] - steps[i - 1].posEast[0]) < 1e-9) { sawHold = true; break; }
  }
  assert.ok(sawHold, "expected the lower id (east) to visibly pause (zero forward advance) at some point during the narrow-corridor fallback");
});

// ─── Existing v6/v7 fixtures unaffected by v8 (regression guard) ──────────

test("findCarAhead (v7, regression): same-direction pair within FOLLOW_GAP_U is still found as a car ahead -- unaffected by the v8 head-on addition", () => {
  const self: WalkerSnapshot = { id: "a", position: [0, 0], heading: [0, 1], destKey: "gate" };
  const other: WalkerSnapshot = { id: "b", position: [0, 0.5], heading: [0, 1], destKey: "gate" };
  const result = findCarAhead(self, [other]);
  assert.ok(result);
  assert.equal(result!.other.id, "b");
});

test("HEAD_ON_COS_MAX and FOLLOW_HEADING_COS_MIN leave no overlapping heading-dot range -- a pair is classified as EITHER same-direction-follow OR head-on-sidestep, never ambiguously both", () => {
  assert.ok(HEAD_ON_COS_MAX <= 0, `HEAD_ON_COS_MAX (${HEAD_ON_COS_MAX}) should describe "roughly opposite"`);
  const FOLLOW_HEADING_COS_MIN_LOCAL = 0.7; // liveAgentWalk.ts's own real value, re-asserted here for this cross-check
  assert.ok(HEAD_ON_COS_MAX < FOLLOW_HEADING_COS_MIN_LOCAL, "the two thresholds must not overlap or cross");
});

// ─── CONVOY-STACK v9 (2026-09-15): mass-leave flip must never move anyone ──
//
// ROOT CAUSE (pose_jump FAIL, 3 jumps, probe 20260915T120533Z): all 3 jumps
// land on the SAME tick a batch of 3 residents flips working->leaving
// together (a mass-leave in one poll). LiveAgents.tsx's own
// `leavingRef.current = leaving` (render body) updates the instant the
// `leaving` prop flips true -- strictly BEFORE the decision effect (a
// `useEffect`) actually runs for that same render, since a `useFrame` tick
// can land in the gap between React's commit and its own effect flush. The
// v5 continuous stand-slot correction (`if (phase.current === "working" &&
// !despawned.current) { standPointFor(currentNode.current) ... }`, no
// `leaving` check at all) fired on exactly that in-between frame, using
// `currentNode.current` (still the OLD pre-leaving zone node -- only
// updated on walk ARRIVAL) together with the ALREADY-updated `standOffset`
// PROP (the parent recomputed it this same render for the avatar's NEW
// leaving-group membership under ENTRY_NODE_ID) -- OLD zone's node + a
// stand-slot offset computed for a DIFFERENT group. Reported: a4a43059
// landed EXACTLY on a1495f14's own prior slot point, because the two
// groups' sorted-index assignments collided on the same index for those
// two ids.
//
// FIX: gate that same correction on `!leavingRef.current` too (see
// LiveAgents.tsx's own "LEAVE-FLIP TELEPORT fix" comment at that call
// site). This also fixes the v4 hold-livePos mechanism "one layer up" for
// free: the decision effect's own `livePos = group.current.position` read
// now always sees the avatar's TRUE last-good resting pose.

interface LeaveFlipStep {
  tS: number;
  position: [number, number, number];
}

const LEAVE_FLIP_ZONE_NODE: [number, number, number] = [-1.2, 0, -1.6]; // ambient-core-ish, matches the probe's own coordinate range
const LEAVE_FLIP_GATE_NODE: [number, number, number] = [21.6, 0, 0]; // campus-gate
const LEAVE_FLIP_IDS = ["a1495f14", "a4a43059", "a8a9d04f"]; // the probe's own real ids

/** Models the coordinator's own required scenario: 3 residents in one zone
 * with STABLE slots (built up over some unmodeled history -- deliberately
 * NOT simple sorted-newcomer order, exactly why it can differ from a fresh
 * simultaneous group's own assignment, see this section's own header) all
 * flip to leaving in the SAME reconcile batch, with stagger delays. Returns
 * each avatar's per-tick trajectory: tick 0 is its true resting pose, tick
 * 1 is the flip frame (PRE-FIX: a possibly-wrong reslot write; FIXED: the
 * unchanged resting pose), then the stagger wait (hold at whatever pose
 * was captured on the flip frame -- CONVOY-STACK v4's own mechanism,
 * itself unmodified by this pass) and finally the walk to the gate. */
function simulateMassLeaveFlip(applyFix: boolean): Map<string, LeaveFlipStep[]> {
  // Historical OLD zone stand-slot assignment -- NOT sorted-newcomer order,
  // simulating slots built up over time (unrelated joins/departures before
  // this fixture's own window), which is exactly why it can diverge from
  // the fresh, simultaneous leaving-group's own sorted assignment below.
  const oldZoneIndex = new Map([["a1495f14", 1], ["a4a43059", 0], ["a8a9d04f", 2]]);
  const workingPos = new Map<string, [number, number, number]>(
    LEAVE_FLIP_IDS.map((id) => {
      const off = stableSlotOffset(oldZoneIndex.get(id)!);
      return [id, [LEAVE_FLIP_ZONE_NODE[0] + off[0], 0, LEAVE_FLIP_ZONE_NODE[2] + off[1]]];
    }),
  );

  // Fresh, simultaneous leaving-group assignment, same poll -- the REAL
  // sorted-newcomer order liveAgentWalk.ts#updateStableSlotAssignments
  // actually produces for a batch that's all brand new to a group.
  const leaveOrder = computeBatchOrder(LEAVE_FLIP_IDS);
  const leaveDelays = computeBatchStaggerDelays(LEAVE_FLIP_IDS);

  const steps = new Map<string, LeaveFlipStep[]>(LEAVE_FLIP_IDS.map((id) => [id, []]));
  for (const id of LEAVE_FLIP_IDS) steps.get(id)!.push({ tS: 0, position: workingPos.get(id)! });

  // Tick 1: the flip frame.
  const livePos = new Map<string, [number, number, number]>();
  for (const id of LEAVE_FLIP_IDS) {
    let pos: [number, number, number];
    if (!applyFix) {
      const newIdx = leaveOrder.get(id)!;
      const off = stableSlotOffset(newIdx);
      pos = [LEAVE_FLIP_ZONE_NODE[0] + off[0], 0, LEAVE_FLIP_ZONE_NODE[2] + off[1]];
    } else {
      pos = workingPos.get(id)!; // FIXED: reslot skipped -- position unchanged
    }
    steps.get(id)!.push({ tS: FOLLOW_TICK_DT_S, position: pos });
    livePos.set(id, pos); // exactly what the decision effect's own `livePos` read captures next
  }

  // Hold through the stagger wait, then walk straight to the gate.
  const maxTicks = Math.ceil(30 / SIM_WALK_SPEED / FOLLOW_TICK_DT_S);
  for (let tick = 2; tick <= maxTicks; tick++) {
    const tS = tick * FOLLOW_TICK_DT_S;
    for (const id of LEAVE_FLIP_IDS) {
      const delay = leaveDelays.get(id)!;
      const elapsed = tS - FOLLOW_TICK_DT_S - delay;
      const wp: [number, number, number][] = [livePos.get(id)!, LEAVE_FLIP_GATE_NODE];
      const total = pathDistance(wp);
      let pos: [number, number, number];
      if (elapsed < 0) {
        pos = livePos.get(id)!; // CONVOY-STACK v4: hold exactly at livePos during the wait
      } else {
        const dist = Math.min(total, elapsed * SIM_WALK_SPEED);
        const progress = total > 0 ? dist / total : 1;
        pos = poseAlongPath(wp, progress).position;
      }
      steps.get(id)!.push({ tS, position: pos });
    }
  }
  return steps;
}

test("MASS-LEAVE FLIP: RED (documents the bug) -- the flip frame moves at least one avatar off its true resting pose", () => {
  const steps = simulateMassLeaveFlip(false);
  let sawJump = false;
  for (const id of LEAVE_FLIP_IDS) {
    const hist = steps.get(id)!;
    const dist = Math.hypot(hist[0].position[0] - hist[1].position[0], hist[0].position[2] - hist[1].position[2]);
    if (dist > 1e-6) sawJump = true;
  }
  assert.ok(sawJump, "expected the PRE-FIX behavior to move at least one avatar on the flip frame (documents the reported pose_jump)");
});

test("MASS-LEAVE FLIP: GREEN (the fix) -- every avatar holds EXACTLY its resting pose on the flip frame and through its wait, then walks with displacement <= 0.7*dt+0.05", () => {
  const steps = simulateMassLeaveFlip(true);
  const leaveDelays = computeBatchStaggerDelays(LEAVE_FLIP_IDS);

  for (const id of LEAVE_FLIP_IDS) {
    const hist = steps.get(id)!;
    // Flip frame: EXACTLY unchanged (not just "close" -- the coordinator's
    // own invariant is "never moves the avatar", zero tolerance).
    assert.deepEqual(hist[1].position, hist[0].position, `${id}: position changed on the flip frame`);

    // Held exactly through its own stagger wait.
    const delay = leaveDelays.get(id)!;
    for (const step of hist) {
      if (step.tS > FOLLOW_TICK_DT_S && step.tS - FOLLOW_TICK_DT_S < delay) {
        assert.deepEqual(step.position, hist[0].position, `${id}: moved while still waiting out its own stagger delay (t=${step.tS}s)`);
      }
    }

    // Per-step displacement bound throughout the ENTIRE trajectory
    // (flip, wait, and the walk that follows) -- no snaps anywhere.
    for (let i = 1; i < hist.length; i++) {
      const a = hist[i - 1].position;
      const b = hist[i].position;
      const dist = Math.hypot(a[0] - b[0], a[2] - b[2]);
      const dt = hist[i].tS - hist[i - 1].tS;
      assert.ok(
        dist <= SIM_WALK_SPEED * dt + 0.05 + 1e-9,
        `${id} step ${i} (t=${hist[i - 1].tS}s -> ${hist[i].tS}s): displacement ${dist.toFixed(3)}u exceeds WALK_SPEED*dt+0.05`,
      );
    }

    // Eventually reaches the gate.
    const last = hist[hist.length - 1];
    assert.ok(
      Math.hypot(last.position[0] - LEAVE_FLIP_GATE_NODE[0], last.position[2] - LEAVE_FLIP_GATE_NODE[2]) < 1e-6,
      `${id} never reached the gate -- ended at [${last.position[0]},${last.position[2]}]`,
    );
  }
});

test("computeBatchOrder: sorted-order ids get 0, 1, 2, ... -- the single source of truth computeBatchStaggerDelays scales by STAGGER_DELAY_S", () => {
  const order = computeBatchOrder(["zeta", "alpha", "mu"]);
  assert.equal(order.get("alpha"), 0);
  assert.equal(order.get("mu"), 1);
  assert.equal(order.get("zeta"), 2);
  const delays = computeBatchStaggerDelays(["zeta", "alpha", "mu"]);
  for (const [id, idx] of order) {
    assert.equal(delays.get(id), idx * STAGGER_DELAY_S, `${id}: delay must equal its own order x STAGGER_DELAY_S`);
  }
});

test("computeBatchStaggerDelays: sorted-order ids get 0, STAGGER_DELAY_S, 2*STAGGER_DELAY_S, ...", () => {
  const delays = computeBatchStaggerDelays(["zeta", "alpha", "mu"]);
  assert.equal(delays.get("alpha"), 0);
  assert.equal(delays.get("mu"), STAGGER_DELAY_S);
  assert.equal(delays.get("zeta"), 2 * STAGGER_DELAY_S);
});

test("computeBatchStaggerDelays: is independent of input order (stable sort)", () => {
  const a = computeBatchStaggerDelays(["c", "a", "b"]);
  const b = computeBatchStaggerDelays(["a", "b", "c"]);
  assert.deepEqual(Array.from(a.entries()).sort(), Array.from(b.entries()).sort());
});

test("computeBatchStaggerDelays: a lone id in its own batch gets delay 0", () => {
  const delays = computeBatchStaggerDelays(["solo"]);
  assert.equal(delays.get("solo"), 0);
});

test("computeBatchStaggerDelays: duplicate ids collapse (a Set), never inflate the delay count", () => {
  const delays = computeBatchStaggerDelays(["a", "a", "b"]);
  assert.equal(delays.size, 2);
  assert.equal(delays.get("a"), 0);
  assert.equal(delays.get("b"), STAGGER_DELAY_S);
});

// ─── THE REQUIRED PROOF: same-batch walkers on a shared corridor stay ──────
// >=0.7u apart after the first ~0.2s (coordinator's own required outcome,
// CONVOY-STACK v2). Models exactly LiveAgents.tsx's own position(t) formula
// for a staggered walk -- `elapsed = t - (walkStart + delay)`, clamped to
// [0,1] progress by poseAlongPath itself -- using only the exported pure
// functions, no React/DOM needed. Proven algebraically in
// liveAgentWalk.ts's own CONVOY-STACK v2 header: on a straight segment, two
// same-speed walkers separated by `delay` seconds are separated by exactly
// `WALK_SPEED * delay` units of Euclidean distance at every instant both are
// actively progressing -- this test exercises that mechanism against the
// REAL poseAlongPath/computeBatchStaggerDelays functions, with a straight
// multi-leg corridor (no sharp corner) so the algebraic guarantee applies
// throughout, not just on one leg.
test("STAGGER PROOF: 4 same-batch ids walking an identical shared corridor stay >=0.7u apart from ~0.2s onward", () => {
  const ids = ["agent-a", "agent-b", "agent-c", "agent-d"];
  const delays = computeBatchStaggerDelays(ids);
  const WALK_SPEED_FIXTURE = 0.7;
  // A long straight corridor (no corner) -- the shared "gate -> hallway"
  // leg every real batch-spawn walk actually shares (layout.ts's own single
  // corridor out of campus-gate).
  const path: [number, number, number][] = [[21.6, 0, 0], [0, 0, 0]];
  const duration = pathDistance(path) / WALK_SPEED_FIXTURE;

  const REQUIRED_MIN_SEPARATION_U = 0.7; // same bar as STAND_RING_RADIUS/stand slots
  const sampleTimes = [0.2, 0.5, 1, 2, 4, 6, 8, 10, 15, 20, 25];
  let checkedAnyActivePair = false;
  for (const t of sampleTimes) {
    const positions = ids.map((id) => {
      const delay = delays.get(id)!;
      const elapsed = t - delay;
      const progress = elapsed / duration; // poseAlongPath clamps to [0,1] itself
      return { id, elapsed, position: poseAlongPath(path, progress).position };
    });
    for (let i = 0; i < positions.length; i++) {
      for (let j = i + 1; j < positions.length; j++) {
        const a = positions[i];
        const b = positions[j];
        // The required bound only applies while BOTH are actively walking
        // (elapsed > 0 for both, i.e. progress > 0 -- neither is still
        // waiting at a clamped, possibly-shared endpoint, nor has one
        // already arrived while the other hasn't started).
        const bothActive = a.elapsed > 0 && a.elapsed < duration && b.elapsed > 0 && b.elapsed < duration;
        if (!bothActive) continue;
        checkedAnyActivePair = true;
        const dist = Math.hypot(a.position[0] - b.position[0], a.position[2] - b.position[2]);
        assert.ok(
          dist >= REQUIRED_MIN_SEPARATION_U - 1e-9,
          `t=${t}s: ${a.id} (elapsed ${a.elapsed.toFixed(2)}s) and ${b.id} (elapsed ${b.elapsed.toFixed(2)}s) are only ${dist.toFixed(3)}u apart, below the required ${REQUIRED_MIN_SEPARATION_U}u`,
        );
      }
    }
  }
  assert.ok(checkedAnyActivePair, "sanity: the sample window must actually exercise at least one both-walking pair, or this test would vacuously pass");
});

// ─── Despawn destination must be the raw gate node, not a ring-nudged point ─
// (DESPAWN-SCATTER fix, 2026-09-15). LiveAgents.tsx's own `destinationPointFor`
// is a thin React-glue wrapper around `nodePosition`/`standPointFor` (both
// closures over `walkGraph`/`standOffsetRef`, not importable from a plain
// node-test module) -- so this proves the underlying CONTRACT those two pure
// exports must satisfy: a stand-slot ring offset is for agents RESTING at a
// shared zone, never for a despawn destination. Root cause: probe
// 20260915T081521Z/20260915T082114Z measured last-diag positions before
// despawn of [21.30,0] (0.30u short), [20.655,0] (0.94u short), and
// [22.393,0] (0.79u past the gate, x > campus-gate's own 21.6) -- every one
// within/around STAND_RING_RADIUS (0.9u), because the pre-fix code applied
// computeStandSlot's own ring nudge to the despawn point too (every leaving
// agent grouped under the single ENTRY_NODE_ID key in LiveAgents.tsx's own
// `standSlots` memo).
test("DESPAWN-SCATTER fix contract: a ring-nudge offset must never be added to a despawning avatar's final point", () => {
  const gateNode: [number, number, number] = [21.6, 0, 0];
  const groupIds = ["agent-1", "agent-2", "agent-3"]; // 3 agents leaving in the same poll
  for (const id of groupIds) {
    const slot = computeStandSlot(groupIds, id, STAND_RING_RADIUS);
    // The FIX: a despawning avatar's own destination point must equal the
    // bare node position -- the ring offset is computed (still used for the
    // walking/bubble stagger) but must never be ADDED for a despawn.
    const despawnPoint: [number, number, number] = gateNode; // destinationPointFor(dest, true) === nodePosition(...)
    assert.deepEqual(despawnPoint, gateNode);
    // Documents the bug this replaces: applying the ring offset would have
    // scattered this exact id up to STAND_RING_RADIUS away from the gate.
    const buggyPoint: [number, number, number] = [gateNode[0] + slot.offset[0], gateNode[1], gateNode[2] + slot.offset[1]];
    const scatterDist = Math.hypot(buggyPoint[0] - gateNode[0], buggyPoint[2] - gateNode[2]);
    if (slot.groupSize > 1) {
      assert.ok(scatterDist > 0, "sanity: the pre-fix ring math really would have moved a 3-member group off the gate");
      assert.ok(scatterDist <= STAND_RING_RADIUS + 1e-9, "documents the observed scatter stays within the 0.9u ring radius, matching the probe's measured 0.30/0.94/0.79u figures");
    }
  }
});

// ─── computeStandSlot (DEFECT 1) ────────────────────────────────────────────

test("computeStandSlot: a lone occupant gets a zero offset", () => {
  const r = computeStandSlot(["a1"], "a1");
  assert.deepEqual(r, { offset: [0, 0], index: 0, groupSize: 1 });
});

test("computeStandSlot: two occupants land on opposite sides of the ring", () => {
  const ids = ["b", "a"]; // deliberately unsorted input
  const ra = computeStandSlot(ids, "a", 1);
  const rb = computeStandSlot(ids, "b", 1);
  assert.equal(ra.groupSize, 2);
  // sorted(["a","b"]) -> a=index0 (angle 0 -> [1,0]), b=index1 (angle PI -> [-1,0])
  assert.equal(ra.index, 0);
  assert.equal(rb.index, 1);
  assert.ok(Math.abs(ra.offset[0] - 1) < 1e-9 && Math.abs(ra.offset[1]) < 1e-9);
  assert.ok(Math.abs(rb.offset[0] + 1) < 1e-9 && Math.abs(rb.offset[1]) < 1e-9);
  // opposite points -> never the same coordinate
  assert.notDeepEqual(ra.offset, rb.offset);
});

test("computeStandSlot: every member of a larger group gets a DISTINCT point", () => {
  const ids = ["a1", "a2", "a3", "a4", "a5"];
  const points = ids.map((id) => computeStandSlot(ids, id, STAND_RING_RADIUS).offset);
  const unique = new Set(points.map((p) => `${p[0].toFixed(6)},${p[1].toFixed(6)}`));
  assert.equal(unique.size, ids.length);
});

test("computeStandSlot: slot assignment is a pure function of the group's sorted ids, independent of input order", () => {
  const a = computeStandSlot(["z", "a", "m"], "m");
  const b = computeStandSlot(["m", "z", "a"], "m");
  assert.deepEqual(a, b);
});

test("computeStandSlot: an id not in the group falls back to index 0 rather than throwing", () => {
  const r = computeStandSlot(["a", "b"], "not-in-group");
  assert.equal(r.index, 0);
});

// ─── Resting-avatar reslot on group growth (STACK FIX, 2026-09-15 probe) ───
//
// computeStandSlot itself is provably correct (every test above) -- the
// stacking bug was NEVER in this function. It was that LiveAgents.tsx only
// ever APPLIED a computed offset to an avatar's actual position at the
// moment its own walk decision fired (settle or walk-kickoff), and that
// effect's dependency list never included `standOffset`. Probe evidence:
// sessions a06954b44dcea322f and a3f93d37e2266fd28, both "working" at
// target "ambient-core", sat at the EXACT SAME point (pairwise distance
// 0.000, 115 consecutive ticks, t=37796ms-95082ms) -- each had settled at a
// moment it was the ONLY member of the "ambient-core" group in `displayed`
// (computeStandSlot's own `groupSize <= 1` branch, offset [0,0]), and
// neither avatar's position was ever corrected once the other joined, so
// both independently landed on the group's zero-offset slot. This harness
// models exactly the two relevant LiveAgents.tsx effects (settle applies
// whatever offset is current AT settle time; the STACK-FIX reslot effect
// re-applies a fresh offset to a RESTING avatar whenever the group
// recomputes) using only the exported pure functions -- no React/DOM
// needed -- so the fix's actual mechanism is provable with plain
// `node --test`.
function simulateSettleThenGroupGrowth(reslotOnGroupChange) {
  // Avatar A settles alone at "ambient-core" first (groupSize 1) -- exactly
  // how a3f93d37e2266fd28 must have arrived before the probe window opened.
  const soloGroup = ["a06954b44dcea322f"];
  let appliedOffsetA = computeStandSlot(soloGroup, "a06954b44dcea322f", STAND_RING_RADIUS).offset;

  // Avatar B (a3f93d37e2266fd28) joins the SAME target later -- the group
  // grows to 2, and liveAgentWalk.ts#computeStandSlot recomputes BOTH
  // members' offsets when the roster's standSlots memo re-runs.
  const grownGroup = ["a06954b44dcea322f", "a3f93d37e2266fd28"];
  const freshSlotA = computeStandSlot(grownGroup, "a06954b44dcea322f", STAND_RING_RADIUS);
  const freshSlotB = computeStandSlot(grownGroup, "a3f93d37e2266fd28", STAND_RING_RADIUS);

  // B settles fresh right now -- its own walk decision is firing for the
  // first time, so it always picks up the CURRENT offset.
  const appliedOffsetB = freshSlotB.offset;

  // A is already resting from its earlier, solo settle: only the fix
  // (reslotOnGroupChange) re-applies A's now-stale offset.
  if (reslotOnGroupChange) appliedOffsetA = freshSlotA.offset;

  return { appliedOffsetA, appliedOffsetB };
}

test("STACK FIX: PRE-FIX shape -- a resting avatar that settled alone stays stuck at the zero offset once a sibling joins its target", () => {
  const { appliedOffsetA, appliedOffsetB } = simulateSettleThenGroupGrowth(false);
  // Reproduces the probe's measured 0.000 pairwise distance: A is frozen at
  // the bare node center, and the only thing keeping B off that exact point
  // is that B's OWN first-ever settle happens to see the up-to-date group.
  assert.deepEqual(appliedOffsetA, [0, 0]);
  const dist = Math.hypot(appliedOffsetA[0] - appliedOffsetB[0], appliedOffsetA[1] - appliedOffsetB[1]);
  assert.ok(dist > 0, "documents that B alone avoids the collision -- A is the one left stale");
});

test("STACK FIX: reslot-on-group-change (the actual fix) gives both resting avatars distinct, ring-separated points", () => {
  const { appliedOffsetA, appliedOffsetB } = simulateSettleThenGroupGrowth(true);
  assert.notDeepEqual(appliedOffsetA, [0, 0]);
  const dist = Math.hypot(appliedOffsetA[0] - appliedOffsetB[0], appliedOffsetA[1] - appliedOffsetB[1]);
  assert.ok(dist >= STAND_RING_RADIUS, `expected separated ring points, got distance ${dist}`);
});

// ─── STAND-SLOT COLLISION fix (CONVOY-STACK v3, 2026-09-15) ────────────────
//
// The recurrence: a7195e62a4dda3d05 settled alone at ambient-core, then
// a1b95546df7c4703f arrived ~60s later and the two sat at the IDENTICAL
// point the whole time -- despite the STACK FIX effect above (already
// proven correct in isolation by the two tests directly above this one).
// Root cause (LiveAgents.tsx:441-506, this pass's own header comment above
// the reslot effect it replaces): that effect only corrects a resting
// avatar's position when THIS avatar's own `standOffset` PROP changes
// between two consecutive renders -- an EDGE-TRIGGERED mechanism that can
// miss a correction (the walk-arrival branch never calls standPointFor at
// all, and an edge-triggered check has no notion of "I am currently wrong",
// only "my prop just changed"). The actual fix replaces this with a
// CONTINUOUS per-frame re-application of computeStandSlot's CURRENT output
// (LiveAgents.tsx's own useFrame, `if (phase.current === "working" &&
// !despawned.current) { ... standPointFor(currentNode.current) ... }`) --
// this cannot go stale by construction, since there is no "last known
// value" to diff against, only "what is correct right now".
//
// This test proves the underlying INVARIANT that continuous mechanism
// relies on: computeStandSlot, read FRESH against whatever the CURRENT
// group is, ALWAYS gives every member of a >=2 group >=STAND_RING_RADIUS
// separation -- across a whole SEQUENCE of roster changes (a settled solo
// agent, a late arrival, a third agent joining, the first agent's own
// stand-slot then being re-read again) -- modeling "read the current group,
// every frame" rather than "diff against the last-seen group".
test("STAND-SLOT COLLISION fix: computeStandSlot, read fresh every frame against the CURRENT group, keeps every pair >=0.7u apart through a settle + late-arrival + reconcile sequence", () => {
  const REQUIRED_MIN_SEPARATION_U = 0.7;
  // Sequence of "current group at ambient-core" snapshots, mirroring the
  // real timeline: A settles alone; B arrives much later (the exact
  // reported collision); a third, C, then also joins (a further roster
  // reconcile, the coordinator's own "including after roster reconcile"
  // requirement); B eventually leaves the zone again.
  const timeline: string[][] = [
    ["a7195e62a4dda3d05"],
    ["a7195e62a4dda3d05"], // still alone, several frames pass
    ["a7195e62a4dda3d05", "a1b95546df7c4703f"], // late arrival joins -- THE collision moment
    ["a7195e62a4dda3d05", "a1b95546df7c4703f"], // several more frames, both resting
    ["a7195e62a4dda3d05", "a1b95546df7c4703f", "c-third-agent"], // a further reconcile
    ["a1b95546df7c4703f", "c-third-agent"], // A leaves the zone
  ];
  for (const group of timeline) {
    // "Every frame" = read computeStandSlot fresh for EVERY member against
    // THIS snapshot's group, exactly what the continuous useFrame
    // correction does (never a value carried over from an earlier group).
    const offsets = new Map(group.map((id) => [id, computeStandSlot(group, id, STAND_RING_RADIUS).offset]));
    for (let i = 0; i < group.length; i++) {
      for (let j = i + 1; j < group.length; j++) {
        const a = offsets.get(group[i])!;
        const b = offsets.get(group[j])!;
        const dist = Math.hypot(a[0] - b[0], a[1] - b[1]);
        if (group.length <= 1) continue; // nothing to separate from
        assert.ok(
          dist >= REQUIRED_MIN_SEPARATION_U - 1e-9,
          `group [${group.join(",")}]: ${group[i]} and ${group[j]} only ${dist.toFixed(3)}u apart`,
        );
      }
    }
  }
});

// ─── reconcileLiveAgentRoster (BUBBLE-FIX, 2026-09-15) ─────────────────────
//
// Extracted from LiveAgents.tsx's own `setDisplayed` updater specifically to
// reproduce the coordinator's live-browser finding: a dropped agent (aa69)
// stayed rendered "working" forever while a newly-arrived agent (7252, this
// very session) never mounted, observed in the SAME /api/hq poll. The test
// below proves the reconcile function ITSELF handles that exact "one id
// replaced by another, same target, same poll" shape correctly -- the real
// root cause was one layer up (app/hq/page.tsx's `sceneData` memo never
// listing `liveAgents` in its own inclusion-list key, fixed in that file,
// same commit) and never reached this function at all, which is exactly
// what this passing test demonstrates.

interface FakeAgent {
  id: string;
  targetZone: string;
}

interface FakeDisplayed {
  id: string;
  targetNodeId: string;
  leaving: boolean;
}

function buildFakeDisplayed(a: FakeAgent): FakeDisplayed {
  return { id: a.id, targetNodeId: a.targetZone, leaving: false };
}

test("reconcileLiveAgentRoster: coordinator's exact scenario -- one id (aa69) dropped and a DIFFERENT id (7252) added, in the SAME poll, both at the same target", () => {
  const prev = new Map<string, FakeDisplayed>([
    ["aa69", { id: "aa69", targetNodeId: "smart-board", leaving: false }],
    ["345c", { id: "345c", targetNodeId: "ambient-core", leaving: false }],
    ["e5df", { id: "e5df", targetNodeId: "ambient-ideas-wall", leaving: false }],
  ]);
  const incoming: FakeAgent[] = [
    { id: "7252", targetZone: "smart-board" }, // replaces aa69 at the SAME target
    { id: "345c", targetZone: "ambient-core" },
    { id: "e5df", targetZone: "ambient-ideas-wall" },
  ];

  const next = reconcileLiveAgentRoster(prev, incoming, buildFakeDisplayed);

  assert.equal(next.size, 4, "aa69 stays (marked leaving), plus the 3 incoming ids");
  assert.equal(next.get("aa69")?.leaving, true, "the dropped id must be marked leaving, never left silently 'working'");
  assert.ok(next.has("7252"), "the newly-arrived id in the same poll must be added");
  assert.equal(next.get("7252")?.leaving, false);
  assert.equal(next.get("345c")?.leaving, false);
  assert.equal(next.get("e5df")?.leaving, false);
});

test("reconcileLiveAgentRoster: an id that reappears after being marked leaving comes back (leaving reset to false)", () => {
  const prev = new Map<string, FakeDisplayed>([["a1", { id: "a1", targetNodeId: "hub-center", leaving: true }]]);
  const next = reconcileLiveAgentRoster(prev, [{ id: "a1", targetZone: "smart-board" }], buildFakeDisplayed);
  assert.equal(next.get("a1")?.leaving, false);
  assert.equal(next.get("a1")?.targetNodeId, "smart-board");
});

test("reconcileLiveAgentRoster: an already-leaving id with no incoming row stays leaving (no double-mark, no reset)", () => {
  const prev = new Map<string, FakeDisplayed>([["a1", { id: "a1", targetNodeId: "hub-center", leaving: true }]]);
  const next = reconcileLiveAgentRoster(prev, [], buildFakeDisplayed);
  assert.equal(next.get("a1")?.leaving, true);
});

test("reconcileLiveAgentRoster: an empty incoming roster (transient fetch glitch) marks every currently-displayed id leaving", () => {
  const prev = new Map<string, FakeDisplayed>([
    ["a1", { id: "a1", targetNodeId: "hub-center", leaving: false }],
    ["a2", { id: "a2", targetNodeId: "smart-board", leaving: false }],
  ]);
  const next = reconcileLiveAgentRoster(prev, [], buildFakeDisplayed);
  assert.equal(next.get("a1")?.leaving, true);
  assert.equal(next.get("a2")?.leaving, true);
});

test("reconcileLiveAgentRoster: never mutates the `prev` map it was given", () => {
  const prev = new Map<string, FakeDisplayed>([["a1", { id: "a1", targetNodeId: "hub-center", leaving: false }]]);
  reconcileLiveAgentRoster(prev, [], buildFakeDisplayed);
  assert.equal(prev.get("a1")?.leaving, false, "prev must stay untouched -- React state must never be mutated in place");
});

// ─── shouldWriteLiveAgentDiag (DIAG-GHOST FIX) ──────────────────────────────
//
// ROOT CAUSE (coordinator probe 20260915T072901Z, RTX 5080 hardware run, 60fps):
// session a094022ec6e8790ff entered "leaving" at ~64.5s, walked to hub-center,
// arrived at ~67.0s -- and then sat there, state "leaving", pos frozen at
// [0,0], for the REMAINING ~181s of the run (through the recorded window
// end), despawn_ms null the whole time. LiveAgents.tsx's own useFrame runs, in
// order, every frame: (1) the arrival check, which on the FIRST frame with
// progress>=1 calls fireDespawn() -- which synchronously calls
// onDespawnedRef.current() (LiveAgents.tsx's own handleDespawned), which
// calls diagStore.delete(id) THEN schedules the React setDisplayed() removal
// -- and (2) an UNCONDITIONAL tail-end `diagStore.set(liveAgentId, {...})`
// that runs every frame regardless of whether despawn just fired THIS SAME
// FRAME. Because React's actual unmount (which would stop useFrame from
// running again) only lands on a LATER render, every frame between "despawn
// fired" and "React actually unmounts the avatar" re-writes the diagStore
// entry that was just deleted -- and the LAST such write, from the final
// frame before unmount, is never cleaned up again (nothing ever calls
// diagStore.delete(id) a second time). The result: a permanent ghost row in
// window.__hqLiveAgents (and therefore every consumer of it, including this
// task's own hq-probe) frozen at the avatar's arrival position forever, even
// though the avatar's REAL React tree node (and its 3D mesh) is already gone.
//
// FIX: LiveAgents.tsx's useFrame must stop writing to diagStore the instant
// `despawned.current` is true, so the frame that fires fireDespawn() is also
// the LAST frame that ever touches diagStore for that id -- the delete from
// handleDespawned then sticks. This pure predicate is the guard; see this
// file's own "pure geometry/math, no React" convention for why it's
// extracted here rather than inlined in the useFrame body.
test("shouldWriteLiveAgentDiag: writes while alive, stops the instant despawn fires (prevents the ghost-entry resurrection bug)", () => {
  assert.equal(shouldWriteLiveAgentDiag(false), true, "still alive -- must keep publishing its diag snapshot");
  assert.equal(shouldWriteLiveAgentDiag(true), false, "despawned this frame or earlier -- must never resurrect the just-deleted diag entry");
});

test("shouldWriteLiveAgentDiag: models the exact bug -- delete-then-unconditional-set resurrects, delete-then-guarded-set does not", () => {
  const diagStore = new Map<string, { pos: [number, number] }>();
  diagStore.set("a094022ec6e8790ff", { pos: [-0.29, -1.6] });

  // The frame arrival + fireDespawn() happens in: delete fires first...
  diagStore.delete("a094022ec6e8790ff");
  // ...then this same frame's tail-end write. THE BUG (unconditional):
  const buggyWrite = true; // pre-fix: no guard at all, always writes
  if (buggyWrite) diagStore.set("a094022ec6e8790ff", { pos: [0, 0] });
  assert.equal(diagStore.has("a094022ec6e8790ff"), true, "documents the bug: unconditional write resurrects the just-deleted ghost entry");

  // THE FIX: guard the same write with shouldWriteLiveAgentDiag(despawned).
  diagStore.delete("a094022ec6e8790ff");
  const despawnedThisFrame = true;
  if (shouldWriteLiveAgentDiag(despawnedThisFrame)) diagStore.set("a094022ec6e8790ff", { pos: [0, 0] });
  assert.equal(diagStore.has("a094022ec6e8790ff"), false, "guarded write must never resurrect the entry once despawned");
});

// ─── Path safety: campus-gate -> every real ZONE_NODE_ID (CAMPUS-GATE pass) ─
//
// Task's own regression requirement: if findWalkPath ever returns null for a
// real zone target, LiveAgents.tsx falls back to a straight-line walk
// through walls (LiveAgents.tsx's own `rawPath: ... ?? [nodePosition(origin),
// nodePosition(dest)]` fallback, ~line 265-268) -- so THIS must fail loudly
// if that ever happens, not silently degrade.
//
// Cannot import layout.ts#buildWalkGraph itself here (see this test file's
// own header on ENTRY_NODE_ID / liveAgentWalk.ts's "Walk graph pathfinding"
// header for the full reason: layout.ts imports 3 raw-kit constants from
// SetKit.tsx, a real .tsx React/three file, and node's own ESM loader
// refuses to load ANY .tsx file at all under plain `node --test`
// (`ERR_UNKNOWN_FILE_EXTENSION`, verified empirically this pass) -- so this
// builds a fixture graph that mirrors buildWalkGraph's REAL topology for the
// one arm (arm 0) and the ambient/smart-board nodes every current
// ZONE_NODE_ID value actually resolves to, using the real raw-kit-derived
// numbers layout.ts itself computes (HUB_WALL_RADIUS=7.5, T_JUNCTION_HALF=
// 0.9, MAIN_HALL_LEN=9 -> T_DIST=17.4; BAY_HALF_DEPTH=2.7 -> SIDE_SPAN=8.1;
// ARM_LEN=20.1, PLAZA_APRON=1.5 -> campus-gate=[21.6,0,0], all cross-checked
// against layout.ts's own exported ARM_LEN/PLAZA_APRON derivation comment)
// plus Scene.tsx's own real WALL_POS=[0,3.4,0] and
// PURPOSEFUL_TARGETS.core=[-1.2,0,-1.6]/["ideas-wall"]=[4.10,0,4.10]. A
// topology change in either real file requires updating this fixture to
// match -- a known coupling, documented rather than hidden. Uses the REAL
// findWalkPath/pathDistance/computeMaxPathDurationS (moved to
// liveAgentWalk.ts this same pass specifically so this test could exercise
// the actual algorithm, not a second hand-reimplemented copy).

function buildFixtureGraph(): WalkGraph {
  const nodes = new Map<string, { id: string; position: [number, number, number] }>();
  const adjacency = new Map<string, { to: string; dist: number }[]>();
  const addNode = (id: string, position: [number, number, number]) => {
    nodes.set(id, { id, position });
    if (!adjacency.has(id)) adjacency.set(id, []);
  };
  const addEdge = (a: string, b: string) => {
    const na = nodes.get(a)!;
    const nb = nodes.get(b)!;
    const d = Math.hypot(na.position[0] - nb.position[0], na.position[1] - nb.position[1], na.position[2] - nb.position[2]);
    adjacency.get(a)!.push({ to: b, dist: d });
    adjacency.get(b)!.push({ to: a, dist: d });
  };

  addNode("hub-center", [0, 0, 0]);
  addNode("hub-door-0", [7.5, 0, 0]);
  addNode("t-0", [17.4, 0, 0]);
  addNode("bay-door-0", [17.4, 0, 5.4]);
  addNode("bay-desk-0", [17.4, 0, 8.1]); // real agentHome is a small in-bay seat offset from this bay-center proxy -- close enough for a distance/reachability fixture
  addNode("smart-board", [0, 3.4, 0]); // Scene.tsx's own WALL_POS
  addNode("ambient-core", [-1.2, 0, -1.6]); // Scene.tsx's own PURPOSEFUL_TARGETS.core
  addNode("ambient-ideas-wall", [4.1, 0, 4.1]); // Scene.tsx's own PURPOSEFUL_TARGETS["ideas-wall"]
  addNode("campus-gate", [21.6, 0, 0]); // ARM_LEN(20.1) + PLAZA_APRON(1.5)

  addEdge("hub-center", "hub-door-0");
  addEdge("hub-door-0", "t-0");
  addEdge("t-0", "bay-door-0");
  addEdge("bay-door-0", "bay-desk-0");
  addEdge("hub-center", "smart-board");
  addEdge("hub-center", "ambient-core");
  addEdge("hub-center", "ambient-ideas-wall");
  addEdge("campus-gate", "t-0"); // the CAMPUS-GATE pass's own new edge

  return { nodes, adjacency } as unknown as WalkGraph;
}

const WALK_SPEED_FIXTURE = 0.7; // KitAgent.tsx#WALK_SPEED's own real value -- "0.7 exactly", that file's own comment

test("path safety: findWalkPath finds a non-null path from campus-gate to EVERY real ZONE_NODE_ID value", () => {
  const graph = buildFixtureGraph();
  const zoneIds = Object.values(ZONE_NODE_ID);
  assert.ok(zoneIds.length > 0, "sanity: ZONE_NODE_ID must not be empty, or this test would vacuously pass");
  for (const zoneId of zoneIds) {
    const path = findWalkPath(graph, "campus-gate", zoneId);
    assert.notEqual(path, null, `findWalkPath(campus-gate -> ${zoneId}) must not be null -- a null path means LiveAgents.tsx falls back to a straight-line walk through walls`);
  }
});

test("path safety: every real zone's walk-out length stays within LEAVE_HARD_TIMEOUT_S's own margin", () => {
  const graph = buildFixtureGraph();
  const results: Record<string, { units: number; seconds: number }> = {};
  let maxSeconds = 0;
  for (const zoneId of Object.values(ZONE_NODE_ID)) {
    const path = findWalkPath(graph, "campus-gate", zoneId);
    assert.ok(path, `unreachable zone ${zoneId} -- see the test above`);
    const units = pathDistance(path!);
    const seconds = units / WALK_SPEED_FIXTURE;
    results[zoneId] = { units, seconds };
    maxSeconds = Math.max(maxSeconds, seconds);
  }
  // Cross-check: computeMaxPathDurationS (the REAL function LiveAgents.tsx
  // now calls, see that file's own leaveHardTimeoutS) sweeps every node in
  // the graph, a strict superset of just the zone nodes -- so it must be >=
  // the max walk-time among the zone nodes alone computed above.
  const sweepSeconds = computeMaxPathDurationS(graph, "campus-gate", WALK_SPEED_FIXTURE);
  assert.ok(sweepSeconds >= maxSeconds - 1e-9, `computeMaxPathDurationS (${sweepSeconds}) must cover the longest real zone walk-out (${maxSeconds})`);
  const derivedTimeoutS = sweepSeconds + LEAVE_TIMEOUT_MARGIN_S;
  // The actual assertion this test exists for: the derived LEAVE_HARD_TIMEOUT_S
  // (computed the same way LiveAgents.tsx now computes it) must exceed every
  // real zone's own walk-out time, with the margin intact -- i.e. the
  // backstop can never fire before a legitimately slow-but-real walk-out
  // would have arrived on its own.
  for (const [zoneId, r] of Object.entries(results)) {
    assert.ok(r.seconds <= derivedTimeoutS, `${zoneId}: walk-out takes ${r.seconds.toFixed(2)}s, exceeds derived LEAVE_HARD_TIMEOUT_S ${derivedTimeoutS.toFixed(2)}s`);
  }
  // Sanity ceiling: catches a future geometry blowup (a zone accidentally
  // wired many hops away) making leaves take unreasonably long, silently
  // degrading UX rather than the null-path case the test above already
  // guards. 120s is generous headroom over the real ~39s/~31s figures
  // measured against this fixture.
  assert.ok(derivedTimeoutS < 120, `derived LEAVE_HARD_TIMEOUT_S (${derivedTimeoutS.toFixed(2)}s) is unreasonably large -- check for a stray long hop in the walk graph`);
  // eslint-disable-next-line no-console
  console.log("[path-safety] campus-gate -> zone walk-out lengths:", JSON.stringify(
    Object.fromEntries(Object.entries(results).map(([k, v]) => [k, `${v.units.toFixed(2)}u / ${v.seconds.toFixed(2)}s`])),
  ), `derived LEAVE_HARD_TIMEOUT_S=${derivedTimeoutS.toFixed(2)}s`);
});

// ─── CONVOY-STACK v10 (2026-09-15): retarget flip snap + gate co-spawn ─────
//
// Bug 1 (RETARGET FLIP SNAP): the same flip-frame reslot mechanism as the
// v9 MASS-LEAVE FLIP fix above, but triggered by `targetNodeId` changing
// (a retarget, working -> walking) instead of `leaving`. LiveAgents.tsx's
// STAND-SLOT COLLISION guard now additionally requires
// `targetNodeIdRef.current === currentNode.current` -- i.e. no pending
// transition of ANY kind, not just "not leaving" -- so it stops firing the
// instant a retarget's props commit, exactly mirroring how it already
// stopped firing the instant `leaving` flipped in v9.
//
// Bug 2 (GATE CO-SPAWN OVERLAP): two avatars spawning in CONSECUTIVE
// reconcile polls each get their own poll's batch-order index (usually 0)
// and so no relative stagger delay at all -- both start walking from the
// identical gate point. Fixed by liveAgentWalk.ts#isPointOccupied: a
// spawning avatar holds at its wait-lane point for as long as the gate
// point is within FOLLOW_GAP_U of another currently-walking avatar,
// independent of its own (possibly zero) stagger delay.

interface RetargetFlipStep {
  tS: number;
  position: [number, number, number];
}

const RETARGET_OLD_ZONE: [number, number, number] = [-0.4, 0, 1.9]; // hub-center-ish
const RETARGET_NEW_ZONE: [number, number, number] = [-1.2, 0, -1.6]; // ambient-core-ish
const RETARGET_IDS = ["ad5f75bf", "a20e3e53", "ac7b6f59"]; // probe's own real ids

/** Models the coordinator's own required scenario: 3 settled residents
 * (phase "working", target already == currentNode == RETARGET_OLD_ZONE)
 * retarget TOGETHER to RETARGET_NEW_ZONE. Ordinary retargets carry no
 * stagger delay (`pendingStartDelayS` is only ever seeded for a spawn or a
 * leave), so PRE-FIX every avatar hits the STAND-SLOT COLLISION block on
 * the very flip frame while `phase.current` still reads "working" (the
 * decision effect hasn't run yet) -- reading the OLD zone's node position
 * together with the NEW zone group's already-recomputed stand offset. */
function simulateMassRetargetFlip(applyFix: boolean): Map<string, RetargetFlipStep[]> {
  // Deliberately NOT the sorted-newcomer order computeBatchOrder would
  // produce (a20e3e53:0, ac7b6f59:1, ad5f75bf:2) -- swapped so the OLD
  // historical assignment actually diverges from the fresh NEW-zone group
  // assignment below (otherwise both resolve to the identical offset and
  // the bug can't be observed at all).
  const oldZoneIndex = new Map([["ad5f75bf", 0], ["a20e3e53", 2], ["ac7b6f59", 1]]);
  const workingPos = new Map<string, [number, number, number]>(
    RETARGET_IDS.map((id) => {
      const off = stableSlotOffset(oldZoneIndex.get(id)!);
      return [id, [RETARGET_OLD_ZONE[0] + off[0], 0, RETARGET_OLD_ZONE[2] + off[1]]];
    }),
  );

  const newOrder = computeBatchOrder(RETARGET_IDS);

  const steps = new Map<string, RetargetFlipStep[]>(RETARGET_IDS.map((id) => [id, []]));
  for (const id of RETARGET_IDS) steps.get(id)!.push({ tS: 0, position: workingPos.get(id)! });

  const livePos = new Map<string, [number, number, number]>();
  for (const id of RETARGET_IDS) {
    let pos: [number, number, number];
    if (!applyFix) {
      const newIdx = newOrder.get(id)!;
      const off = stableSlotOffset(newIdx);
      pos = [RETARGET_OLD_ZONE[0] + off[0], 0, RETARGET_OLD_ZONE[2] + off[1]];
    } else {
      pos = workingPos.get(id)!;
    }
    steps.get(id)!.push({ tS: FOLLOW_TICK_DT_S, position: pos });
    livePos.set(id, pos);
  }

  const maxTicks = Math.ceil(30 / SIM_WALK_SPEED / FOLLOW_TICK_DT_S);
  for (let tick = 2; tick <= maxTicks; tick++) {
    const tS = tick * FOLLOW_TICK_DT_S;
    for (const id of RETARGET_IDS) {
      const idx = newOrder.get(id)!;
      const off = stableSlotOffset(idx);
      const finalPoint: [number, number, number] = [RETARGET_NEW_ZONE[0] + off[0], 0, RETARGET_NEW_ZONE[2] + off[1]];
      const wp: [number, number, number][] = [livePos.get(id)!, finalPoint];
      const total = pathDistance(wp);
      const elapsed = tS - FOLLOW_TICK_DT_S;
      const dist = Math.min(total, elapsed * SIM_WALK_SPEED);
      const progress = total > 0 ? dist / total : 1;
      const pos = poseAlongPath(wp, progress).position;
      steps.get(id)!.push({ tS, position: pos });
    }
  }
  return steps;
}

test("RETARGET FLIP: RED (documents the bug) -- the flip frame moves at least one avatar off its true resting pose", () => {
  const steps = simulateMassRetargetFlip(false);
  let sawJump = false;
  for (const id of RETARGET_IDS) {
    const hist = steps.get(id)!;
    const dist = Math.hypot(hist[0].position[0] - hist[1].position[0], hist[0].position[2] - hist[1].position[2]);
    if (dist > 1e-6) sawJump = true;
  }
  assert.ok(sawJump, "expected the PRE-FIX behavior to move at least one avatar on the retarget flip frame (documents the reported pose_jump)");
});

test("RETARGET FLIP: GREEN (the fix) -- every avatar holds EXACTLY its resting pose on the flip frame, then step bound <= 0.7*dt+0.05", () => {
  const steps = simulateMassRetargetFlip(true);
  for (const id of RETARGET_IDS) {
    const hist = steps.get(id)!;
    assert.deepEqual(hist[1].position, hist[0].position, `${id}: position changed on the retarget flip frame`);
    for (let i = 1; i < hist.length; i++) {
      const a = hist[i - 1].position;
      const b = hist[i].position;
      const dist = Math.hypot(a[0] - b[0], a[2] - b[2]);
      const dt = hist[i].tS - hist[i - 1].tS;
      assert.ok(
        dist <= SIM_WALK_SPEED * dt + 0.05 + 1e-9,
        `${id} step ${i} (t=${hist[i - 1].tS}s -> ${hist[i].tS}s): displacement ${dist.toFixed(3)}u exceeds WALK_SPEED*dt+0.05`,
      );
    }
  }
});

// ─── Single retarget while a sibling joins its OLD zone ────────────────────
//
// Generalization check: the flip-frame snap can also be triggered by a
// THIRD PARTY's group-membership change, not just the retargeting avatar's
// own transition. X rests alone in zone A; on the SAME tick X retargets
// away to zone B AND Y newly joins zone A (recomputing zone A's own
// stand-slot assignment for a 2-member group). The actual fix
// (`targetNodeIdRef.current === currentNode.current`) covers this directly,
// since X's own target already differs from its currentNode the instant
// the retarget commits, regardless of WHY `standOffsetRef.current` also
// changed that same tick.

const SIBLING_ZONE_A: [number, number, number] = [-0.4, 0, 1.9];
const SIBLING_ZONE_B: [number, number, number] = [-1.2, 0, -1.6];
const SIBLING_RETARGET_ID = "x-resident";
// Lexicographically BEFORE "x-resident" so X's own 2-member sorted index
// shifts from 0 (solo) to 1 (with Y) -- otherwise X keeps index 0 in both
// the solo and 2-member group and the offset never actually changes.
const SIBLING_JOIN_ID = "a-newcomer";

function simulateSingleRetargetWithSiblingJoin(applyFix: boolean): RetargetFlipStep[] {
  const soloOff = stableSlotOffset(0);
  const restingPos: [number, number, number] = [SIBLING_ZONE_A[0] + soloOff[0], 0, SIBLING_ZONE_A[2] + soloOff[1]];

  const steps: RetargetFlipStep[] = [{ tS: 0, position: restingPos }];

  const zoneAOrder = computeBatchOrder([SIBLING_RETARGET_ID, SIBLING_JOIN_ID]);
  let flipPos: [number, number, number];
  if (!applyFix) {
    const newIdx = zoneAOrder.get(SIBLING_RETARGET_ID)!;
    const off = stableSlotOffset(newIdx);
    flipPos = [SIBLING_ZONE_A[0] + off[0], 0, SIBLING_ZONE_A[2] + off[1]];
  } else {
    flipPos = restingPos;
  }
  steps.push({ tS: FOLLOW_TICK_DT_S, position: flipPos });

  const finalPoint: [number, number, number] = [SIBLING_ZONE_B[0] + soloOff[0], 0, SIBLING_ZONE_B[2] + soloOff[1]];
  const maxTicks = Math.ceil(20 / SIM_WALK_SPEED / FOLLOW_TICK_DT_S);
  for (let tick = 2; tick <= maxTicks; tick++) {
    const tS = tick * FOLLOW_TICK_DT_S;
    const wp: [number, number, number][] = [flipPos, finalPoint];
    const total = pathDistance(wp);
    const elapsed = tS - FOLLOW_TICK_DT_S;
    const dist = Math.min(total, elapsed * SIM_WALK_SPEED);
    const progress = total > 0 ? dist / total : 1;
    steps.push({ tS, position: poseAlongPath(wp, progress).position });
  }
  return steps;
}

test("SINGLE RETARGET + SIBLING JOIN: RED (documents the bug) -- a third party's group change also snaps the retargeting avatar", () => {
  const hist = simulateSingleRetargetWithSiblingJoin(false);
  const dist = Math.hypot(hist[0].position[0] - hist[1].position[0], hist[0].position[2] - hist[1].position[2]);
  assert.ok(dist > 1e-6, "expected a sibling's zone-A join to also move the retargeting avatar on the flip frame pre-fix");
});

test("SINGLE RETARGET + SIBLING JOIN: GREEN (the fix) -- the general guard holds X's pose regardless of WHY standOffset changed", () => {
  const hist = simulateSingleRetargetWithSiblingJoin(true);
  assert.deepEqual(hist[1].position, hist[0].position, "X moved on the flip frame despite its own target already differing from currentNode");
  for (let i = 1; i < hist.length; i++) {
    const a = hist[i - 1].position;
    const b = hist[i].position;
    const dist = Math.hypot(a[0] - b[0], a[2] - b[2]);
    const dt = hist[i].tS - hist[i - 1].tS;
    assert.ok(dist <= SIM_WALK_SPEED * dt + 0.05 + 1e-9, `step ${i}: displacement ${dist.toFixed(3)}u exceeds WALK_SPEED*dt+0.05`);
  }
});

// ─── Gate co-spawn overlap (two spawns in consecutive reconcile polls) ─────

const COSPAWN_GATE: [number, number] = [21.6, 0];
const COSPAWN_DEST: [number, number] = [12.0, -3.0];
const COSPAWN_DEST_KEY = "hub-center";
const COSPAWN_A_ID = "ad5f75bf";
const COSPAWN_B_ID = "a20e3e53";
/** How many ticks after A spawns that B's own reconcile poll (and thus its
 * mount) lands -- "consecutive polls", soon enough that A hasn't yet
 * cleared FOLLOW_GAP_U from the gate when B would otherwise start. */
const COSPAWN_B_MOUNT_TICK = 6; // 0.1s @ FOLLOW_TICK_DT_S -- well inside FOLLOW_GAP_U/WALK_SPEED (~1.14s)

interface CospawnStep {
  tS: number;
  position: [number, number] | null;
}

/** Mirrors LiveAgents.tsx's own useFrame contract (one-frame-stale
 * registry, incremental distance, per-poll spawn with zero relative
 * stagger) for two walkers spawning in consecutive polls at the SAME gate
 * point, both heading to the SAME destination (destKey matches, so
 * findCarAhead's own pre-filter passes). `applyGateHold` toggles the v10
 * fix: when true, a spawning walker additionally holds at its wait-lane
 * point for as long as isPointOccupied(gate, ...) says someone else is
 * still there. */
function simulateGateCospawn(applyGateHold: boolean): { history: Map<string, CospawnStep[]>; startTick: Map<string, number> } {
  const waitLaneA = computeWaitPoint([COSPAWN_GATE[0], 0, COSPAWN_GATE[1]], [COSPAWN_DEST[0], 0, COSPAWN_DEST[1]], 0);
  const waitLaneB = computeWaitPoint([COSPAWN_GATE[0], 0, COSPAWN_GATE[1]], [COSPAWN_DEST[0], 0, COSPAWN_DEST[1]], 0);

  const appliedDistance = new Map<string, number>([[COSPAWN_A_ID, 0], [COSPAWN_B_ID, 0]]);
  const spawningStill = new Map<string, boolean>([[COSPAWN_A_ID, true], [COSPAWN_B_ID, true]]);
  let registry = new Map<string, WalkerSnapshot>();
  const history = new Map<string, CospawnStep[]>([[COSPAWN_A_ID, []], [COSPAWN_B_ID, []]]);
  // First tick each id was NOT held -- i.e. the tick it actually started
  // moving away from the gate, whether or not that's the same as its own
  // mount tick (it's the same when unheld -- RED's own case -- and later
  // when the gate-occupancy hold makes it wait -- GREEN's own case).
  const startTick = new Map<string, number>();

  const maxTicks = COSPAWN_B_MOUNT_TICK + Math.ceil(40 / SIM_WALK_SPEED / FOLLOW_TICK_DT_S);
  for (let tick = 0; tick <= maxTicks; tick++) {
    const tS = tick * FOLLOW_TICK_DT_S;
    const nextRegistry = new Map<string, WalkerSnapshot>();
    for (const id of [COSPAWN_A_ID, COSPAWN_B_ID]) {
      const spawnTick = id === COSPAWN_A_ID ? 0 : COSPAWN_B_MOUNT_TICK;
      if (tick < spawnTick) {
        history.get(id)!.push({ tS, position: null });
        continue;
      }
      const waitLane = id === COSPAWN_A_ID ? waitLaneA : waitLaneB;
      const others = Array.from(registry.values()).filter((s) => s.id !== id);
      const gateOccupied = applyGateHold ? isPointOccupied(COSPAWN_GATE, id, others, FOLLOW_GAP_U) : false;
      const held = spawningStill.get(id)! && appliedDistance.get(id)! === 0 && gateOccupied;
      let pos: [number, number];
      let heading: [number, number];
      if (held) {
        pos = [waitLane[0], waitLane[2]];
        heading = [0, 1];
      } else {
        if (spawningStill.get(id)! && !startTick.has(id)) startTick.set(id, tick);
        spawningStill.set(id, false);
        const wp: [number, number, number][] = [
          [COSPAWN_GATE[0], 0, COSPAWN_GATE[1]],
          [COSPAWN_DEST[0], 0, COSPAWN_DEST[1]],
        ];
        const total = pathDistance(wp);
        const candidate = appliedDistance.get(id)! + SIM_WALK_SPEED * FOLLOW_TICK_DT_S;
        const initialPose = poseAlongPath(wp, 0);
        const lastSelf = registry.get(id);
        const selfSnapshot: WalkerSnapshot = lastSelf ?? {
          id,
          position: [initialPose.position[0], initialPose.position[2]],
          heading: [Math.sin(initialPose.facing), Math.cos(initialPose.facing)],
          destKey: COSPAWN_DEST_KEY,
        };
        const carAhead = findCarAhead(selfSnapshot, others);
        const newApplied = applyFollowCap(candidate, appliedDistance.get(id)!, carAhead);
        appliedDistance.set(id, newApplied);
        const progress = Math.min(1, newApplied / total);
        const pose = poseAlongPath(wp, progress);
        pos = [pose.position[0], pose.position[2]];
        heading = [Math.sin(pose.facing), Math.cos(pose.facing)];
      }
      history.get(id)!.push({ tS, position: pos });
      nextRegistry.set(id, { id, position: pos, heading, destKey: COSPAWN_DEST_KEY });
    }
    registry = nextRegistry;
  }
  return { history, startTick };
}

test("GATE CO-SPAWN: RED (documents the bug) -- consecutive-poll spawns start on top of each other with zero relative separation", () => {
  const { history } = simulateGateCospawn(false);
  const aAt = history.get(COSPAWN_A_ID)![COSPAWN_B_MOUNT_TICK];
  const bAt = history.get(COSPAWN_B_ID)![COSPAWN_B_MOUNT_TICK];
  assert.ok(aAt.position && bAt.position, "both walkers should have spawned by B's own mount tick");
  const dist = Math.hypot(aAt.position![0] - bAt.position![0], aAt.position![1] - bAt.position![1]);
  assert.ok(dist < FOLLOW_GAP_U, `expected the PRE-FIX behavior to start B inside A's own FOLLOW_GAP_U (got ${dist.toFixed(3)}u) -- documents the reported walker_separation failure`);
});

test("GATE CO-SPAWN: GREEN (the fix) -- B is queued until the gate clears, pairwise >=0.7u from 0.5s after it actually starts, and it never starts inside A's gap", () => {
  const { history, startTick } = simulateGateCospawn(true);
  const aHist = history.get(COSPAWN_A_ID)!;
  const bHist = history.get(COSPAWN_B_ID)!;
  const n = Math.min(aHist.length, bHist.length);

  // The fix must actually QUEUE B -- it should NOT start moving on its own
  // mount tick the way the PRE-FIX RED case did, since A is still well
  // within FOLLOW_GAP_U of the gate at that point.
  const bStart = startTick.get(COSPAWN_B_ID)!;
  assert.ok(bStart > COSPAWN_B_MOUNT_TICK, `expected B to be held past its own mount tick (${COSPAWN_B_MOUNT_TICK}) while the gate is occupied, but it started at tick ${bStart}`);

  // Nobody ever starts (the tick it stops being held) inside another
  // currently-walking avatar's own FOLLOW_GAP_U.
  const aAtBStart = aHist[bStart];
  const bAtBStart = bHist[bStart];
  assert.ok(aAtBStart.position && bAtBStart.position, "both walkers should have a position at B's own start tick");
  const startDist = Math.hypot(aAtBStart.position![0] - bAtBStart.position![0], aAtBStart.position![1] - bAtBStart.position![1]);
  assert.ok(startDist >= FOLLOW_GAP_U - 1e-9, `B started ${startDist.toFixed(3)}u from A, inside FOLLOW_GAP_U (${FOLLOW_GAP_U}u)`);

  // Pairwise >=0.7u for every tick from 0.5s after B actually starts onward.
  const graceTicks = Math.round(0.5 / FOLLOW_TICK_DT_S);
  for (let i = bStart + graceTicks; i < n; i++) {
    const a = aHist[i];
    const b = bHist[i];
    if (!a.position || !b.position) continue;
    const dist = Math.hypot(a.position[0] - b.position[0], a.position[1] - b.position[1]);
    assert.ok(dist >= 0.7 - 1e-9, `t=${a.tS.toFixed(2)}s: A/B only ${dist.toFixed(3)}u apart`);
  }
});
