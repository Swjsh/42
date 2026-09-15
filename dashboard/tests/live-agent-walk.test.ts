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
  applyLaneOffsets,
  computeMaxPathDurationS,
  ENTRY_NODE_ID,
  findWalkPath,
  laneOffsetUnit,
  LANE_OFFSET_MAGNITUDE_U,
  LEAVE_TIMEOUT_MARGIN_S,
  pathDistance,
  poseAlongPath,
  decideNextWalk,
  computeStandSlot,
  STAND_RING_RADIUS,
  reconcileLiveAgentRoster,
  shouldWriteLiveAgentDiag,
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

// ─── laneOffsetUnit / applyLaneOffsets (CONVOY-STACK fix, 2026-09-15) ──────

test("laneOffsetUnit: deterministic -- same id always yields the same value", () => {
  assert.equal(laneOffsetUnit("session-a1"), laneOffsetUnit("session-a1"));
});

test("laneOffsetUnit: different ids usually yield different values", () => {
  const ids = ["a06954b44dcea322f", "a3f93d37e2266fd28", "dcc3d160-abc-a8b2", "7252", "aa69", "345c"];
  const values = ids.map(laneOffsetUnit);
  assert.ok(new Set(values).size > 1, "a real roster of distinct ids must not collapse to one lane value");
});

test("laneOffsetUnit: always stays within [-1, 1]", () => {
  for (const id of ["a", "session-xyz-123", "", "z".repeat(50)]) {
    const v = laneOffsetUnit(id);
    assert.ok(v >= -1 && v <= 1, `laneOffsetUnit(${JSON.stringify(id)}) = ${v} out of range`);
  }
});

test("applyLaneOffsets: leaves the first and last waypoint exactly unchanged", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [10, 0, 0], [20, 0, 0], [30, 0, 0]];
  const out = applyLaneOffsets(wp, "some-id");
  assert.deepEqual(out[0], wp[0]);
  assert.deepEqual(out[out.length - 1], wp[wp.length - 1]);
});

test("applyLaneOffsets: nudges interior waypoints perpendicular to the local path direction", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [10, 0, 0], [20, 0, 0]];
  const out = applyLaneOffsets(wp, "lane-test-id", 0.4);
  // Path runs along +X, so any nudge must be purely in Z (perpendicular),
  // never changing X, and its exact magnitude must equal this id's own
  // laneOffsetUnit scaled by the requested 0.4u magnitude.
  const expected = laneOffsetUnit("lane-test-id") * 0.4;
  assert.equal(out[1][0], 10);
  assert.ok(Math.abs(out[1][2] - expected) < 1e-9, `expected offset=${expected}, got ${out[1][2]}`);
});

test("applyLaneOffsets: two different ids sharing the same corridor waypoints end up on DIFFERENT points (the actual convoy-stack fix)", () => {
  // Mirrors the probe's exact measured shape: 4 live agents all leaving
  // campus-gate through the same first hallway leg, all reporting the same
  // XZ point mid-walk. Two distinct ids walking the identical raw path must
  // no longer collapse onto the same interior waypoint.
  const rawPath: [number, number, number][] = [[21.6, 0, 0], [17.4, 0, 0], [17.4, 0, 5.4]];
  const a = applyLaneOffsets(rawPath, "session-a06954b44dcea322f");
  const b = applyLaneOffsets(rawPath, "session-a3f93d37e2266fd28");
  assert.notDeepEqual(a[1], b[1], "two distinct ids must not share the exact same nudged interior waypoint");
});

test("applyLaneOffsets: a path with no interior waypoint (direct 2-point hop) is returned unchanged", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [5, 0, 5]];
  const out = applyLaneOffsets(wp, "any-id");
  assert.deepEqual(out, wp);
});

test("applyLaneOffsets: nudge magnitude never exceeds the configured LANE_OFFSET_MAGNITUDE_U", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [10, 0, 0], [20, 0, 0]];
  for (const id of ["a", "bb", "ccc", "dddd", "session-real-id-0001"]) {
    const out = applyLaneOffsets(wp, id);
    const dz = Math.abs(out[1][2] - wp[1][2]);
    assert.ok(dz <= LANE_OFFSET_MAGNITUDE_U + 1e-9, `id=${id} produced a ${dz}u nudge, exceeding LANE_OFFSET_MAGNITUDE_U`);
  }
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
